"""Host-wide provider quota ledger, circuit breaker and per-host budget.

Several customer sites on this host share one provider key, but each site
counted its own requests. wbm and wileytest share a NewsAPI key limited to
100 requests a day; each site compared its own counter with 100, so the
guard never fired and the provider rejected 615 requests in a week. NewsData
showed the same across four sites, Xpoz across seven.

This module keeps one ledger per provider and key fingerprint, in a SQLite
file every site process can reach. Each request reserves a unit before it is
sent and records the provider's answer afterwards. A 429 or an "exceeded
credits" body sets ``quota_exhausted_until`` and every site stops polling that
key until then. The same store keeps a per-host request budget for hosts that
rate-limit by client IP (reddit.com), because every site fetches them from
the same address.

SQLite rather than a table in a tenant database: the sites have separate
databases and separate credentials, and a file under a lock is the one store
they all already have access to. WAL mode and ``BEGIN IMMEDIATE`` make the
reserve-then-record sequence safe across processes.

Allocation across sites is configuration, not code: ``quota_policy.json``
next to the ledger, or ``AUNOO_QUOTA_POLICY_JSON``. Default is equal shares
with borrowing of what other sites have not used.

Identical in both repositories; import nothing from either application.
Spec: docs/COLLECTOR_DATA_QUALITY_SPEC.md, work packages 20 and 21.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_LEDGER_DIR = "/home/orochford/tenants/_shared"
DEFAULT_LEDGER_PATH = os.path.join(DEFAULT_LEDGER_DIR, "collector_ledger.sqlite")

#: Documented provider budgets. ``period`` is ``day`` (UTC calendar day),
#: ``month`` (UTC calendar month) or ``rolling:<seconds>``. ``budget`` None
#: means the budget is unknown: the ledger still counts and still breaks the
#: circuit on an exhaustion response, it just cannot pre-empt one.
DEFAULT_POLICY: Dict[str, Dict[str, Any]] = {
    "newsapi": {"period": "day", "budget": 100},
    "newsdata": {"period": "day", "budget": 200},
    "thenewsapi": {"period": "day", "budget": None},
    "xpoz": {"period": "month", "budget": None},
    # Unauthenticated Semantic Scholar is about one request a second shared
    # by everyone on the host; with a key it is 100 per five minutes.
    "semantic_scholar": {"period": "rolling:300", "budget": 100},
    "arxiv": {"period": "rolling:3", "budget": 1},
    "firecrawl": {"period": "month", "budget": None},
}

DEFAULT_HOST_BUDGETS: Dict[str, Dict[str, Any]] = {
    # Reddit allows roughly 10 unauthenticated requests a minute per IP.
    "reddit.com": {"period": "rolling:60", "budget": 10},
    "www.reddit.com": {"period": "rolling:60", "budget": 10},
}

#: When an exhaustion response gives no Retry-After and the policy has no
#: reset time, pause this long.
DEFAULT_PAUSE = timedelta(minutes=15)


def key_fingerprint(key: Optional[str]) -> str:
    """Twelve hex characters that identify a key without storing it."""
    return hashlib.sha256((key or "").encode("utf-8")).hexdigest()[:12]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.astimezone(timezone.utc).isoformat() if dt else None


def _parse(text: Optional[str]) -> Optional[datetime]:
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def period_start(period: str, now: datetime, first_seen: Optional[datetime] = None) -> datetime:
    """When the current budget period began."""
    if period == "day":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "month":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if period.startswith("rolling:"):
        seconds = int(period.split(":", 1)[1])
        if first_seen and (now - first_seen) < timedelta(seconds=seconds):
            return first_seen
        return now
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def period_end(period: str, start: datetime) -> datetime:
    if period == "day":
        return start + timedelta(days=1)
    if period == "month":
        nxt = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
        return nxt
    if period.startswith("rolling:"):
        return start + timedelta(seconds=int(period.split(":", 1)[1]))
    return start + timedelta(days=1)


@dataclass
class Reservation:
    ok: bool
    reason: str                      # "ok", "exhausted", "budget", "share"
    provider: str
    fingerprint: str
    used: int
    budget: Optional[int]
    period_start: str
    exhausted_until: Optional[datetime] = None
    tenant_used: int = 0
    tenant_share: Optional[int] = None

    @property
    def retry_at(self) -> Optional[datetime]:
        return self.exhausted_until


class SharedLedger:
    """One ledger file; one instance per process is plenty."""

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS provider_quota (
        provider TEXT NOT NULL,
        fingerprint TEXT NOT NULL,
        period_start TEXT NOT NULL,
        used INTEGER NOT NULL DEFAULT 0,
        budget INTEGER,
        quota_exhausted_until TEXT,
        last_response TEXT,
        last_response_at TEXT,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (provider, fingerprint)
    );
    CREATE TABLE IF NOT EXISTS provider_quota_tenant (
        provider TEXT NOT NULL,
        fingerprint TEXT NOT NULL,
        period_start TEXT NOT NULL,
        tenant TEXT NOT NULL,
        used INTEGER NOT NULL DEFAULT 0,
        refused INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (provider, fingerprint, period_start, tenant)
    );
    CREATE TABLE IF NOT EXISTS host_budget (
        host TEXT PRIMARY KEY,
        window_start TEXT NOT NULL,
        used INTEGER NOT NULL DEFAULT 0,
        paused_until TEXT,
        last_tenant TEXT,
        updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS quota_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        at TEXT NOT NULL,
        provider TEXT NOT NULL,
        fingerprint TEXT NOT NULL,
        tenant TEXT,
        event TEXT NOT NULL,
        detail TEXT
    );
    """

    def __init__(self, path: Optional[str] = None, *, policy: Optional[Dict[str, Any]] = None,
                 host_budgets: Optional[Dict[str, Any]] = None, tenant: Optional[str] = None):
        self.path = path or os.getenv("AUNOO_SHARED_LEDGER_PATH") or DEFAULT_LEDGER_PATH
        self.tenant = tenant or os.getenv("AUNOO_TENANT_NAME") or os.path.basename(os.getcwd())
        self._lock = threading.Lock()
        self._policy = {**DEFAULT_POLICY, **(policy or {}), **self._file_policy().get("providers", {})}
        self._host_budgets = {**DEFAULT_HOST_BUDGETS, **(host_budgets or {}),
                              **self._file_policy().get("hosts", {})}
        self._tenant_shares: Dict[str, Dict[str, float]] = self._file_policy().get("shares", {})
        self._ensure()

    # -- setup --------------------------------------------------------------

    def _file_policy(self) -> Dict[str, Any]:
        if getattr(self, "_file_policy_cache", None) is not None:
            return self._file_policy_cache
        data: Dict[str, Any] = {}
        raw = os.getenv("AUNOO_QUOTA_POLICY_JSON", "").strip()
        if raw:
            try:
                data = json.loads(raw)
            except ValueError:
                logger.warning("AUNOO_QUOTA_POLICY_JSON is not valid JSON; ignored")
        else:
            candidate = os.path.join(os.path.dirname(self.path), "quota_policy.json")
            if os.path.isfile(candidate):
                try:
                    with open(candidate, "r", encoding="utf-8") as fh:
                        data = json.load(fh)
                except (OSError, ValueError) as exc:
                    logger.warning("quota_policy.json unreadable: %s", exc)
        self._file_policy_cache = data if isinstance(data, dict) else {}
        return self._file_policy_cache

    def _ensure(self) -> None:
        directory = os.path.dirname(self.path)
        try:
            os.makedirs(directory, exist_ok=True)
            # Sites run as different users; every one of them must be able to
            # create the WAL and lock files beside the database. No sticky
            # bit: with fs.protected_regular set, a sticky world-writable
            # directory stops one user opening another user's file with
            # O_CREAT, which is exactly what SQLite does for its -wal and
            # -shm files, and root then sees "attempt to write a readonly
            # database".
            try:
                os.chmod(directory, 0o777)
            except OSError:
                pass
        except OSError as exc:
            logger.warning("shared ledger directory %s unavailable: %s", directory, exc)
        existed = os.path.exists(self.path)
        with self._connect() as conn:
            conn.executescript(self._SCHEMA)
        if not existed:
            try:
                os.chmod(self.path, 0o666)
            except OSError:
                pass

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            pass
        conn.execute("PRAGMA busy_timeout=10000")
        return conn

    def policy_for(self, provider: str) -> Dict[str, Any]:
        return dict(self._policy.get(provider) or {"period": "day", "budget": None})

    # -- provider quota -----------------------------------------------------

    def _row(self, conn: sqlite3.Connection, provider: str, fingerprint: str) -> Optional[sqlite3.Row]:
        return conn.execute(
            "SELECT * FROM provider_quota WHERE provider=? AND fingerprint=?",
            (provider, fingerprint)).fetchone()

    def _current_period(self, provider: str, row: Optional[sqlite3.Row], now: datetime) -> "tuple[str, int]":
        """Period start for ``now`` and the count that still applies."""
        pol = self.policy_for(provider)
        stored_start = _parse(row["period_start"]) if row else None
        start = period_start(pol["period"], now, stored_start)
        if row and stored_start and stored_start == start:
            return _iso(start), int(row["used"])
        if row and stored_start and pol["period"].startswith("rolling:") and \
                now < period_end(pol["period"], stored_start):
            return _iso(stored_start), int(row["used"])
        return _iso(start), 0

    def exhausted_until(self, provider: str, key: Optional[str]) -> Optional[datetime]:
        fp = key_fingerprint(key)
        with self._connect() as conn:
            row = self._row(conn, provider, fp)
        until = _parse(row["quota_exhausted_until"]) if row else None
        if until and until > _now():
            return until
        return None

    def reserve(self, provider: str, key: Optional[str], *, tenant: Optional[str] = None,
                units: int = 1) -> Reservation:
        """Claim ``units`` before sending a request. ``ok`` False means do not
        send: the key is paused, the period budget is spent, or this site has
        used its share and nothing is left to borrow."""
        tenant = tenant or self.tenant
        fp = key_fingerprint(key)
        pol = self.policy_for(provider)
        budget = pol.get("budget")
        now = _now()
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = self._row(conn, provider, fp)
                until = _parse(row["quota_exhausted_until"]) if row else None
                pstart, used = self._current_period(provider, row, now)
                if until and until > now:
                    self._bump_tenant(conn, provider, fp, pstart, tenant, refused=1)
                    conn.execute("COMMIT")
                    return Reservation(False, "exhausted", provider, fp, used, budget, pstart, until)
                tenant_used = self._tenant_used(conn, provider, fp, pstart, tenant)
                share = self._share_for(provider, fp, pstart, tenant, budget, conn)
                if budget is not None and used + units > budget:
                    self._bump_tenant(conn, provider, fp, pstart, tenant, refused=1)
                    conn.execute("COMMIT")
                    return Reservation(False, "budget", provider, fp, used, budget, pstart,
                                       period_end(pol["period"], _parse(pstart)), tenant_used, share)
                if budget is not None and share is not None and tenant_used + units > share:
                    # Borrow only from what the other sites cannot still claim.
                    others_claimable = self._others_claimable(conn, provider, fp, pstart, tenant, budget)
                    if used + units + others_claimable > budget:
                        self._bump_tenant(conn, provider, fp, pstart, tenant, refused=1)
                        conn.execute("COMMIT")
                        return Reservation(False, "share", provider, fp, used, budget, pstart,
                                           period_end(pol["period"], _parse(pstart)), tenant_used, share)
                conn.execute(
                    """INSERT INTO provider_quota (provider, fingerprint, period_start, used, budget, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?)
                       ON CONFLICT(provider, fingerprint) DO UPDATE SET
                         period_start=excluded.period_start, used=?, budget=excluded.budget,
                         updated_at=excluded.updated_at""",
                    (provider, fp, pstart, used + units, budget, _iso(now), used + units))
                self._bump_tenant(conn, provider, fp, pstart, tenant, used=units)
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        return Reservation(True, "ok", provider, fp, used + units, budget, pstart, None,
                           tenant_used + units, share)

    def record_response(self, provider: str, key: Optional[str], outcome: str, *,
                        retry_after_seconds: Optional[float] = None,
                        reset_at: Optional[datetime] = None, detail: str = "",
                        tenant: Optional[str] = None) -> Optional[datetime]:
        """Tell the ledger what the provider said. ``outcome`` is ``ok``,
        ``quota`` (429 or an exhaustion body) or ``error``. Returns the pause
        end when one was set."""
        tenant = tenant or self.tenant
        fp = key_fingerprint(key)
        now = _now()
        until: Optional[datetime] = None
        if outcome == "quota":
            pol = self.policy_for(provider)
            if retry_after_seconds and retry_after_seconds > 0:
                until = now + timedelta(seconds=min(float(retry_after_seconds), 86400 * 2))
            elif reset_at is not None:
                until = reset_at
            elif pol["period"] in ("day", "month"):
                until = period_end(pol["period"], period_start(pol["period"], now))
            else:
                until = now + DEFAULT_PAUSE
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = self._row(conn, provider, fp)
                pstart, used = self._current_period(provider, row, now)
                conn.execute(
                    """INSERT INTO provider_quota (provider, fingerprint, period_start, used, budget,
                                                   quota_exhausted_until, last_response, last_response_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(provider, fingerprint) DO UPDATE SET
                         period_start=excluded.period_start, used=?,
                         quota_exhausted_until=CASE WHEN ? THEN excluded.quota_exhausted_until
                                                    WHEN excluded.last_response='ok' THEN NULL
                                                    ELSE provider_quota.quota_exhausted_until END,
                         last_response=excluded.last_response, last_response_at=excluded.last_response_at,
                         updated_at=excluded.updated_at""",
                    (provider, fp, pstart, used, self.policy_for(provider).get("budget"),
                     _iso(until), outcome, _iso(now), _iso(now), used, 1 if until else 0))
                conn.execute(
                    "INSERT INTO quota_events (at, provider, fingerprint, tenant, event, detail) VALUES (?,?,?,?,?,?)",
                    (_iso(now), provider, fp, tenant, outcome, (detail or "")[:300]))
                conn.execute("DELETE FROM quota_events WHERE id < (SELECT MAX(id) FROM quota_events) - 5000")
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        if until:
            logger.warning("%s quota exhausted for key %s; every site pauses until %s (%s)",
                           provider, fp, until.isoformat(), (detail or "")[:120])
        return until

    def _bump_tenant(self, conn: sqlite3.Connection, provider: str, fp: str, pstart: str,
                     tenant: str, *, used: int = 0, refused: int = 0) -> None:
        conn.execute(
            """INSERT INTO provider_quota_tenant (provider, fingerprint, period_start, tenant, used, refused, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(provider, fingerprint, period_start, tenant) DO UPDATE SET
                 used=provider_quota_tenant.used+?, refused=provider_quota_tenant.refused+?, updated_at=excluded.updated_at""",
            (provider, fp, pstart, tenant, used, refused, _iso(_now()), used, refused))

    def _tenant_used(self, conn: sqlite3.Connection, provider: str, fp: str, pstart: str, tenant: str) -> int:
        row = conn.execute(
            "SELECT used FROM provider_quota_tenant WHERE provider=? AND fingerprint=? AND period_start=? AND tenant=?",
            (provider, fp, pstart, tenant)).fetchone()
        return int(row["used"]) if row else 0

    def _tenants_in_period(self, conn: sqlite3.Connection, provider: str, fp: str, pstart: str) -> Dict[str, int]:
        rows = conn.execute(
            "SELECT tenant, used FROM provider_quota_tenant WHERE provider=? AND fingerprint=? AND period_start=?",
            (provider, fp, pstart)).fetchall()
        return {r["tenant"]: int(r["used"]) for r in rows}

    def _share_for(self, provider: str, fp: str, pstart: str, tenant: str, budget: Optional[int],
                   conn: sqlite3.Connection) -> Optional[int]:
        """This site's share of the period budget. Configured fractions win;
        otherwise equal shares among the sites seen on this key this period."""
        if budget is None:
            return None
        configured = self._tenant_shares.get(provider) or {}
        if configured:
            frac = configured.get(tenant)
            if frac is None:
                frac = configured.get("*", 0)
            return int(budget * float(frac))
        seen = self._tenants_in_period(conn, provider, fp, pstart)
        seen.setdefault(tenant, 0)
        return max(1, budget // max(1, len(seen)))

    def _others_claimable(self, conn: sqlite3.Connection, provider: str, fp: str, pstart: str,
                          tenant: str, budget: int) -> int:
        seen = self._tenants_in_period(conn, provider, fp, pstart)
        seen.setdefault(tenant, 0)
        total = 0
        for other, used in seen.items():
            if other == tenant:
                continue
            share = self._share_for(provider, fp, pstart, other, budget, conn) or 0
            total += max(0, share - used)
        return total

    # -- per-host budget (work package 21) ----------------------------------

    def host_policy(self, host: str) -> Optional[Dict[str, Any]]:
        h = (host or "").lower()
        if h in self._host_budgets:
            return self._host_budgets[h]
        parts = h.split(".")
        for i in range(1, len(parts) - 1):
            parent = ".".join(parts[i:])
            if parent in self._host_budgets:
                return self._host_budgets[parent]
        return None

    def host_paused_until(self, host: str) -> Optional[datetime]:
        with self._connect() as conn:
            row = conn.execute("SELECT paused_until FROM host_budget WHERE host=?", (self._host_key(host),)).fetchone()
        until = _parse(row["paused_until"]) if row else None
        return until if until and until > _now() else None

    def _host_key(self, host: str) -> str:
        """The row a host is budgeted under: the policy's domain when a parent
        domain has one (``old.reddit.com`` shares ``reddit.com``'s budget and
        its pause), otherwise the host without ``www.``."""
        h = (host or "").lower()
        if h.startswith("www."):
            h = h[4:]
        parts = h.split(".")
        for i in range(len(parts) - 1):
            parent = ".".join(parts[i:])
            if parent in self._host_budgets:
                return parent[4:] if parent.startswith("www.") else parent
        return h

    def host_acquire(self, host: str, *, tenant: Optional[str] = None, units: int = 1) -> Reservation:
        """Claim a request against a host budget. Hosts without a policy are
        always allowed but still subject to a pause set by ``host_record_429``."""
        tenant = tenant or self.tenant
        key = self._host_key(host)
        pol = self.host_policy(key)
        now = _now()
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute("SELECT * FROM host_budget WHERE host=?", (key,)).fetchone()
                until = _parse(row["paused_until"]) if row else None
                if until and until > now:
                    conn.execute("COMMIT")
                    return Reservation(False, "exhausted", f"host:{key}", "", int(row["used"]),
                                       pol.get("budget") if pol else None, row["window_start"], until)
                if pol is None:
                    conn.execute("COMMIT")
                    return Reservation(True, "ok", f"host:{key}", "", 0, None, _iso(now))
                wstart = _parse(row["window_start"]) if row else None
                start = period_start(pol["period"], now, wstart)
                used = int(row["used"]) if row and wstart == start else 0
                if used + units > int(pol["budget"]):
                    conn.execute("COMMIT")
                    return Reservation(False, "budget", f"host:{key}", "", used, int(pol["budget"]), _iso(start),
                                       period_end(pol["period"], start))
                conn.execute(
                    """INSERT INTO host_budget (host, window_start, used, last_tenant, updated_at)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(host) DO UPDATE SET window_start=excluded.window_start, used=?,
                         last_tenant=excluded.last_tenant, updated_at=excluded.updated_at""",
                    (key, _iso(start), used + units, tenant, _iso(now), used + units))
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        return Reservation(True, "ok", f"host:{key}", "", used + units, int(pol["budget"]), _iso(start))

    def host_record_429(self, host: str, *, retry_after_seconds: Optional[float] = None,
                        tenant: Optional[str] = None) -> datetime:
        key = self._host_key(host)
        now = _now()
        pause = timedelta(seconds=min(float(retry_after_seconds), 3600)) if retry_after_seconds else timedelta(minutes=10)
        until = now + pause
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    """INSERT INTO host_budget (host, window_start, used, paused_until, last_tenant, updated_at)
                       VALUES (?, ?, 0, ?, ?, ?)
                       ON CONFLICT(host) DO UPDATE SET paused_until=excluded.paused_until,
                         last_tenant=excluded.last_tenant, updated_at=excluded.updated_at""",
                    (key, _iso(now), _iso(until), tenant or self.tenant, _iso(now)))
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        logger.warning("host %s answered 429; every site pauses it until %s", key, until.isoformat())
        return until

    # -- reporting ----------------------------------------------------------

    def status(self) -> Dict[str, Any]:
        """Everything the health probe wants: per-key use, pauses, per-site
        shares, host pauses."""
        now = _now()
        out: Dict[str, Any] = {"ledger_path": self.path, "providers": [], "hosts": []}
        with self._connect() as conn:
            for row in conn.execute("SELECT * FROM provider_quota ORDER BY provider, fingerprint"):
                pstart, used = self._current_period(row["provider"], row, now)
                until = _parse(row["quota_exhausted_until"])
                tenants = self._tenants_in_period(conn, row["provider"], row["fingerprint"], pstart)
                out["providers"].append({
                    "provider": row["provider"], "key": row["fingerprint"],
                    "period_start": pstart, "used": used, "budget": row["budget"],
                    "exhausted_until": _iso(until) if until and until > now else None,
                    "last_response": row["last_response"], "last_response_at": row["last_response_at"],
                    "tenants": tenants,
                })
            for row in conn.execute("SELECT * FROM host_budget ORDER BY host"):
                until = _parse(row["paused_until"])
                out["hosts"].append({
                    "host": row["host"], "window_start": row["window_start"], "used": row["used"],
                    "paused_until": _iso(until) if until and until > now else None,
                })
        return out


_default: Optional[SharedLedger] = None
_default_lock = threading.Lock()


def get_ledger() -> SharedLedger:
    """The process-wide ledger. Falls back to a per-process temporary file
    when the shared path cannot be opened, so a collector never stops
    because the ledger is unavailable; it just loses cross-site sharing."""
    global _default
    if _default is not None:
        return _default
    with _default_lock:
        if _default is None:
            try:
                _default = SharedLedger()
            except Exception as exc:  # noqa: BLE001
                import tempfile
                fallback = os.path.join(tempfile.gettempdir(), f"collector_ledger_{os.getpid()}.sqlite")
                logger.error("shared ledger unavailable (%s); using per-process %s", exc, fallback)
                _default = SharedLedger(fallback)
    return _default


def parse_retry_after(value: Any) -> Optional[float]:
    """Seconds from a Retry-After header, which may be a delay or a date."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return max(0.0, float(text))
    except ValueError:
        pass
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, (dt - _now()).total_seconds())
    except (TypeError, ValueError, IndexError):
        return None
