"""Daily credit budget for the shared Xpoz key, per platform.

Xpoz bills by platform, not by call: X and Reddit cost 2 credits a call,
TikTok 5, Instagram 12, and an Instagram post lookup is 12 credits per post
id. Measured on 11 Oct 2026 by reading the account balance around each call.
The plan is 120,000 credits a month, so this module keeps every site on the
host inside a daily allowance, with a smaller allowance for Instagram and
TikTok where most of the money went.

Every caller asks ``reserve(platform, credits)`` before a paid call and skips
the call when it returns False. Spend is kept in one SQLite file shared by all
sites, per UTC day, platform and site, so the allowance is for the key, not for
one site. A broken file never stops collection: on any error the call is
allowed and a warning is logged.

Allowances come from the environment, in credits per UTC day:

    XPOZ_CREDITS_PER_DAY            whole key, default 4000 (120k / 30)
    XPOZ_INSTAGRAM_CREDITS_PER_DAY  default 1300 (about 110 searches)
    XPOZ_TIKTOK_CREDITS_PER_DAY     default 400 (about 80 searches)
    XPOZ_BUDGET_PATH                the SQLite file (default under _shared)

Run ``python -m app.services.xpoz_budget`` for today's spend by site and
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


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except ValueError:
        return default


def allowances() -> Dict[str, int]:
    """Daily caps in credits: ``all`` for the key plus any platform caps."""
    caps = {"all": _int_env("XPOZ_CREDITS_PER_DAY", 4000)}
    for plat, default in (("instagram", 1300), ("tiktok", 400)):
        caps[plat] = _int_env(f"XPOZ_{plat.upper()}_CREDITS_PER_DAY", default)
    for plat in ("twitter", "reddit"):
        v = os.getenv(f"XPOZ_{plat.upper()}_CREDITS_PER_DAY")
        if v:
            caps[plat] = _int_env(f"XPOZ_{plat.upper()}_CREDITS_PER_DAY", 0)
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


def _spent(conn: sqlite3.Connection, day: str, platform: Optional[str]) -> int:
    if platform:
        row = conn.execute("SELECT COALESCE(SUM(credits), 0) FROM spend WHERE day = ? AND platform = ?",
                           (day, platform)).fetchone()
    else:
        row = conn.execute("SELECT COALESCE(SUM(credits), 0) FROM spend WHERE day = ?", (day,)).fetchone()
    return int(row[0] or 0)


def reserve(platform: str, credits: int, *, tenant: Optional[str] = None) -> bool:
    """Charge ``credits`` to today's allowance for ``platform``.

    Returns False, and records a refusal, when the platform's cap or the
    key's cap would be exceeded. Returns True on any storage error so a
    broken budget file never stops collection."""
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
            total = _spent(conn, day, None)
            plat_total = _spent(conn, day, platform)
            reason = None
            if platform in caps and plat_total + credits > caps[platform]:
                reason = f"{platform} daily allowance {caps[platform]} credits spent ({plat_total} used)"
            elif total + credits > caps["all"]:
                reason = f"Xpoz daily allowance {caps['all']} credits spent ({total} used)"
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
    caps = allowances()
    rep = report(day)
    totals: Dict[str, int] = {}
    print(f"Xpoz credits on {day} (caps: {caps})")
    for tenant, plats in rep.items():
        for plat, v in plats.items():
            totals[plat] = totals.get(plat, 0) + v["credits"]
            print(f"  {tenant:<24} {plat:<10} credits={v['credits']:<6} calls={v['calls']:<5} refused={v['refused']}")
    print(f"  total: {sum(totals.values())} credits  by platform: {totals}")
