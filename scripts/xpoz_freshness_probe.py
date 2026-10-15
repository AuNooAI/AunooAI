"""Is Xpoz serving current data? One small search per platform.

From 13 Oct 20:00 to 15 Oct 01:00 2026 Xpoz served a frozen copy of Reddit.
Every call succeeded, so the sites' Reddit collection saw nothing new for 29
hours and nothing flagged it. The sites cannot watch for this themselves:
their searches are brand and topic keywords, and many get a few posts a day
or none, so "nothing new" is often normal for them.

So this asks Xpoz one general, busy question per platform and reads how old
the newest result is. Each search is recorded in the shared credit file
(app/services/xpoz_budget.py) under the site name "xpoz-freshness-probe";
run hourly it costs about 21 credits a round (2 X, 2 Reddit, 5 TikTok, 12
Instagram), about 500 a day. Instagram and TikTok are budgeted platforms, so
the cron entry sets their daily allowances for this site name.

Prints the same JSON shape as the honeypot's /api/freshness, which
saasmvp-app/scripts/honeypot_freshness_check.sh reads to send the alert. A
platform is stale when its search succeeded and the newest result is older
than its limit. A failed or skipped search gives no verdict, and a paused key
(the shared ledger's quota pause) is reported as paused, not stale.

    cd bugfixing.aunoo.ai && PYTHONPATH=. .venv/bin/python scripts/xpoz_freshness_probe.py
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.INFO)

from app.collectors.xpoz_collector import _FIELDS, _pub_iso  # noqa: E402
from app.services import xpoz_budget  # noqa: E402

SITE = "xpoz-freshness-probe"
# Busy, general terms, so the newest result tracks the platform, not a topic.
TERMS = {"twitter": "news", "reddit": "news", "tiktok": "fyp", "instagram": "travel"}
# Hours. Measured on 15 Oct 2026 12:00: X 0.5, Reddit 0.6, TikTok 0.7,
# Instagram 9.1 (Xpoz's Instagram results run well behind). Each run logs its
# readings so these can be set from more than one sample.
MAX_H = {"twitter": 4.0, "reddit": 4.0, "tiktok": 6.0, "instagram": 36.0}
LIMIT = 50
LEDGER = "/home/orochford/tenants/_shared/collector_ledger.sqlite"


def _paused() -> bool:
    try:
        conn = sqlite3.connect(LEDGER, timeout=5)
        row = conn.execute(
            "SELECT quota_exhausted_until FROM provider_quota WHERE provider = 'xpoz'"
        ).fetchone()
        conn.close()
    except sqlite3.Error:
        return False
    if not row or not row[0]:
        return False
    until = datetime.fromisoformat(str(row[0]).replace("Z", "+00:00"))
    return (until if until.tzinfo else until.replace(tzinfo=timezone.utc)) > datetime.now(timezone.utc)


def main() -> int:
    from xpoz import XpozClient

    now = datetime.now(timezone.utc)
    out: dict = {"checked_at": now.isoformat(), "platforms": {}, "stale": [], "paused": False}
    if _paused():
        out["paused"] = True
        print(json.dumps(out))
        return 0
    client = XpozClient(os.environ["XPOZ_API_KEY"], check_update=False)
    try:
        for plat, term in TERMS.items():
            row = {"newest_reply_at": None, "lag_h": None, "max_h": MAX_H[plat],
                   "polls_ok_last_hour": 0, "stale": False, "error": None}
            out["platforms"][plat] = row
            if not xpoz_budget.reserve(plat, xpoz_budget.SEARCH_COST.get(plat, 2), tenant=SITE):
                row["error"] = f"skipped: {xpoz_budget.last_reason}"
                continue
            try:
                result = getattr(client, plat).search_posts(
                    term, fields=_FIELDS[plat],
                    start_date=(now - timedelta(days=2)).date().isoformat(),
                    end_date=now.date().isoformat(), limit=LIMIT,
                )
            except Exception as exc:  # noqa: BLE001 - no verdict on a failed search
                row["error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
                continue
            times = []
            for post in getattr(result, "data", None) or []:
                iso = _pub_iso(post)
                if not iso:
                    continue
                t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
                times.append(t if t.tzinfo else t.replace(tzinfo=timezone.utc))
            row["polls_ok_last_hour"] = 1
            if times:
                newest = max(times)
                row["newest_reply_at"] = newest.isoformat()
                row["lag_h"] = round((now - newest).total_seconds() / 3600, 1)
            row["stale"] = row["lag_h"] is None or row["lag_h"] > row["max_h"]
    finally:
        try:
            client.close()
        except Exception:  # noqa: BLE001
            pass
    out["stale"] = sorted(p for p, v in out["platforms"].items() if v["stale"])
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
