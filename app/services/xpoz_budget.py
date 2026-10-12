"""Daily credit budget for the expensive Xpoz platforms, per site.

Xpoz bills by platform, not by call: X and Reddit cost 2 credits a call,
TikTok 5, Instagram 12, and an Instagram post lookup is 12 credits per post
id. Measured on 11 Oct 2026 by reading the account balance around each call.
X and Reddit are cheap and are not budgeted. Instagram and TikTok are, and
each site has its own allowance, because most clients do not need them and a
consumer-brand client that does should pay for its own.

Every caller asks ``reserve(platform, credits)`` before a paid call and skips
the call when it returns False. Spend is recorded for every platform in one
SQLite file shared by all sites (per UTC day, platform and site) so the key's
whole spend can be read in one place, but only the budgeted platforms are ever
refused. A broken file never stops collection: on any error the call is
allowed and a warning is logged.

Allowances come from each site's environment, in credits per UTC day:

    XPOZ_INSTAGRAM_CREDITS_PER_DAY  default 0: the site does not use Instagram
    XPOZ_TIKTOK_CREDITS_PER_DAY     default 0: the site does not use TikTok
    XPOZ_CREDITS_PER_DAY            optional cap on the site's whole spend
    XPOZ_BUDGET_PATH                the SQLite file (default under _shared)

The engagement refresh re-polls stored posts and is the lower-value use, so it
reserves with ``keep_fraction=0.5``: it only spends while at least half of
the day's allowance is still free, leaving the rest for searches.

Run ``python -m app.services.xpoz_budget [day]`` for the spend by site and
platform.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_PATH = "/home/orochford/tenants/_shared/xpoz_credits.sqlite"

#: Platforms with a budget. Everything else is recorded but never refused.
BUDGETED = ("instagram", "tiktok")

#: Credits for one keyword search, by platform (measured 11 Oct 2026).
SEARCH_COST: Dict[str, int] = {"twitter": 2, "reddit": 2, "tiktok": 5, "instagram": 12}
#: Credits for one get_posts_by_ids batch (per batch, except Instagram).
LOOKUP_BATCH_COST: Dict[str, int] = {"twitter": 2, "tiktok": 5}
#: Credits per post for the platforms billed per item.
LOOKUP_PER_POST_COST: Dict[str, int] = {"instagram": 12, "reddit": 2}

_lock = threading.Lock()
last_reason: str = ""


def lookup_cost(platform: str, n_posts: int) -> int:
    """Credits for looking up ``n_posts`` stored posts on ``platform``."""
    if platform in LOOKUP_PER_POST_COST:
        return LOOKUP_PER_POST_COST[platform] * max(n_posts, 0)
    return LOOKUP_BATCH_COST.get(platform, 2)


def _int_env(name: str) -> Optional[int]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        logger.warning("%s=%r is not a number; ignored", name, raw)
        return None


def allowances() -> Dict[str, int]:
    """This site's daily caps in credits. Budgeted platforms default to 0;
    ``all`` is present only when XPOZ_CREDITS_PER_DAY is set."""
    caps: Dict[str, int] = {}
    for plat in BUDGETED:
        caps[plat] = _int_env(f"XPOZ_{plat.upper()}_CREDITS_PER_DAY") or 0
    total = _int_env("XPOZ_CREDITS_PER_DAY")
    if total:
        caps["all"] = total
    return caps


def _tenant() -> str:
    return os.getenv("DOMAIN") or os.getenv("TENANT") or os.path.basename(os.getcwd()) or "unknown"


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _connect() -> sqlite3.Connection:
    path = os.getenv("XPOZ_BUDGET_PATH") or DEFAULT_PATH
    new = not os.path.exists(path)
    conn = sqlite3.connect(path, timeout=10)
    conn.execute("""CREATE TABLE IF NOT EXISTS spend (
        day TEXT NOT NULL, platform TEXT NOT NULL, tenant TEXT NOT NULL,
        credits INTEGER NOT NULL DEFAULT 0, calls INTEGER NOT NULL DEFAULT 0,
        refused INTEGER NOT NULL DEFAULT 0, updated_at TEXT,
        PRIMARY KEY (day, platform, tenant))""")
    if new:
        # Monolith sites run as orochford and the saas worker as root; both
        # must be able to write the same file.
        try:
            os.chmod(path, 0o666)
        except OSError:
            pass
    return conn


def _spent(conn: sqlite3.Connection, day: str, tenant: str, platform: Optional[str]) -> int:
    if platform:
        row = conn.execute("SELECT COALESCE(SUM(credits), 0) FROM spend WHERE day = ? AND tenant = ? AND platform = ?",
                           (day, tenant, platform)).fetchone()
    else:
        row = conn.execute("SELECT COALESCE(SUM(credits), 0) FROM spend WHERE day = ? AND tenant = ?",
                           (day, tenant)).fetchone()
    return int(row[0] or 0)


def reserve(platform: str, credits: int, *, tenant: Optional[str] = None,
            keep_fraction: float = 0.0) -> bool:
    """Charge ``credits`` to this site's allowance for ``platform``.

    Returns False, and records a refusal, when a budgeted platform's cap (or
    the optional site-wide cap) would be exceeded, or when the call would
    leave less than ``keep_fraction`` of the platform's allowance free.
    Platforms without a budget are recorded and always allowed. Returns True
    on any storage error so a broken budget file never stops collection."""
    global last_reason
    platform = (platform or "").lower()
    credits = int(credits or 0)
    if credits <= 0:
        return True
    tenant = tenant or _tenant()
    day = _today()
    caps = allowances()
    try:
        with _lock, _connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            reason = None
            if platform in caps:
                cap = caps[platform]
                used = _spent(conn, day, tenant, platform)
                floor = int(cap * keep_fraction) if keep_fraction else 0
                if cap <= 0:
                    reason = f"{platform} is not budgeted on this site (XPOZ_{platform.upper()}_CREDITS_PER_DAY unset)"
                elif used + credits > cap - floor:
                    kept = f", keeping {floor} for searches" if floor else ""
                    reason = f"{platform} daily allowance {cap} credits spent ({used} used{kept})"
            if reason is None and "all" in caps:
                used_all = _spent(conn, day, tenant, None)
                if used_all + credits > caps["all"]:
                    reason = f"site daily allowance {caps['all']} credits spent ({used_all} used)"
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            if reason:
                conn.execute("""INSERT INTO spend (day, platform, tenant, refused, updated_at)
                                VALUES (?, ?, ?, 1, ?)
                                ON CONFLICT(day, platform, tenant) DO UPDATE SET
                                  refused = refused + 1, updated_at = excluded.updated_at""",
                             (day, platform, tenant, now))
                conn.commit()
                last_reason = reason
                return False
            conn.execute("""INSERT INTO spend (day, platform, tenant, credits, calls, updated_at)
                            VALUES (?, ?, ?, ?, 1, ?)
                            ON CONFLICT(day, platform, tenant) DO UPDATE SET
                              credits = credits + excluded.credits, calls = calls + 1,
                              updated_at = excluded.updated_at""",
                         (day, platform, tenant, credits, now))
            conn.commit()
            last_reason = ""
            return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("xpoz budget unavailable (%s); allowing the call", exc)
        last_reason = ""
        return True


def report(day: Optional[str] = None) -> Dict[str, Dict[str, Dict[str, int]]]:
    """``{tenant: {platform: {credits, calls, refused}}}`` for one day."""
    day = day or _today()
    out: Dict[str, Dict[str, Dict[str, int]]] = {}
    with _connect() as conn:
        for tenant, platform, credits, calls, refused in conn.execute(
                "SELECT tenant, platform, credits, calls, refused FROM spend WHERE day = ? ORDER BY tenant, platform",
                (day,)):
            out.setdefault(tenant, {})[platform] = {"credits": credits, "calls": calls, "refused": refused}
    return out


if __name__ == "__main__":
    import sys
    day = sys.argv[1] if len(sys.argv) > 1 else _today()
    rep = report(day)
    totals: Dict[str, int] = {}
    print(f"Xpoz credits on {day} (this site's caps: {allowances()})")
    for tenant, plats in rep.items():
        for plat, v in plats.items():
            totals[plat] = totals.get(plat, 0) + v["credits"]
            print(f"  {tenant:<24} {plat:<10} credits={v['credits']:<6} calls={v['calls']:<5} refused={v['refused']}")
    print(f"  total: {sum(totals.values())} credits  by platform: {totals}")
