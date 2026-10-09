"""Weekly consensus and horizons runs for a fixed list of topics.

A consensus or horizons run is otherwise only made when someone presses the
button on the Explore page, so a topic's saved run just gets older. The market
refresh (``app/services/market_foresight.py``) covers a market's collection
topic once a month; this task covers any topics a site names, on a weekly
slot, for sites whose reports read brand topics rather than a market.

It makes each run the way an operator's browser does: a GET to the
trend-convergence route over loopback, with a session it signs with the app's
own secret, so the route writes its usual run rows, cache keys and logs. A
horizons run also gets its executive-summary cards, as in the market refresh.

Off unless both of these are set in ``.env``:

    FORESIGHT_REFRESH_TOPICS      topic names separated by "|" (names can hold commas)
    FORESIGHT_REFRESH_PROFILE_ID  the organisational profile the runs are written for

A run with no profile is written for the site's default profile, which can
be another customer's, so the task refuses to run without one.

Optional:

    FORESIGHT_REFRESH_WEEKDAY     0=Monday .. 6=Sunday (default 6)
    FORESIGHT_REFRESH_HOUR        local hour the slot opens (default 2)
    FORESIGHT_REFRESH_TIMEFRAME_DAYS  coverage window each run reads (default 365)
    FORESIGHT_REFRESH_MODEL       default claude-sonnet-4-5; Kimi K2.5 moved
                                  facts between companies in consensus runs
    FORESIGHT_REFRESH_PERSONA     default executive
    FORESIGHT_REFRESH_USER        whose session the runs use (default admin)

A kind is due when its newest run is older than the latest slot (last
Sunday 02:00 by default), so a restart or a missed slot catches up on the
next check instead of waiting a week. A failure backs that topic off for a
day.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from sqlalchemy import text
from app.model_tiers import default_model

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 3600
KINDS = ("consensus", "horizons")
_TABLES = {"consensus": "consensus_analysis_runs", "horizons": "future_horizons_runs"}
_RETRY_AFTER: Dict[str, datetime] = {}
_status: Dict[str, Any] = {"enabled": False, "last_check_time": None, "last_runs": [], "last_error": None}


def get_task_status() -> dict:
    return dict(_status)


def _settings() -> Optional[Dict[str, Any]]:
    topics = [t.strip() for t in (os.getenv("FORESIGHT_REFRESH_TOPICS") or "").split("|") if t.strip()]
    profile = (os.getenv("FORESIGHT_REFRESH_PROFILE_ID") or "").strip()
    if not topics or not profile.isdigit():
        return None
    return {
        "topics": topics,
        "profile_id": int(profile),
        "weekday": int(os.getenv("FORESIGHT_REFRESH_WEEKDAY", "6")),
        "hour": int(os.getenv("FORESIGHT_REFRESH_HOUR", "2")),
        "timeframe_days": int(os.getenv("FORESIGHT_REFRESH_TIMEFRAME_DAYS", "365")),
        "model": os.getenv("FORESIGHT_REFRESH_MODEL") or default_model("standard"),
        "persona": os.getenv("FORESIGHT_REFRESH_PERSONA", "executive"),
        "user": os.getenv("FORESIGHT_REFRESH_USER", "admin"),
    }


def last_slot(now: datetime, weekday: int, hour: int) -> datetime:
    """The most recent weekly slot at or before ``now`` (naive local time)."""
    slot = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    slot -= timedelta(days=(slot.weekday() - weekday) % 7)
    if slot > now:
        slot -= timedelta(days=7)
    return slot


def _session_cookie(user: str) -> str:
    import itsdangerous

    secret = os.getenv("FLASK_SECRET_KEY") or ""
    if not secret:
        raise RuntimeError("FLASK_SECRET_KEY unset; cannot mint a session")
    data = base64.b64encode(json.dumps({"user": user}).encode())
    return itsdangerous.TimestampSigner(secret).sign(data).decode()


def _newest_runs(topics: List[str]) -> Dict[tuple, Optional[datetime]]:
    from app.database import get_database_instance
    conn = get_database_instance()._temp_get_connection()
    try:
        out = {}
        for kind in KINDS:
            for topic in topics:
                out[(kind, topic)] = conn.execute(text(
                    f"SELECT MAX(created_at) FROM {_TABLES[kind]} WHERE topic = :t"), {"t": topic}).scalar()
        return out
    finally:
        conn.close()


def due(newest: Dict[tuple, Optional[datetime]], slot: datetime) -> List[tuple]:
    """(kind, topic) pairs whose newest run predates the slot. Run times are
    stored naive in the database's local time, as the slot is."""
    out = []
    for key, at in newest.items():
        if at is not None and at.tzinfo is not None:
            at = at.astimezone().replace(tzinfo=None)
        if at is None or at < slot:
            out.append(key)
    return out


async def _executive_summary(client, payload: Dict[str, Any], topic: str, s: Dict[str, Any],
                             base: str, cookies: Dict[str, str], headers: Dict[str, str]) -> None:
    run_id = payload.get("analysis_id")
    scenarios = payload.get("scenarios") or []
    if not run_id or not scenarios:
        return
    r = await client.post(f"{base}/api/trend-convergence/horizons/{run_id}/executive-summary",
                          json={"scenarios": scenarios, "topic": topic, "model": s["model"],
                                "profile_id": s["profile_id"]},
                          cookies=cookies, headers=headers)
    if r.status_code != 200:
        raise RuntimeError(f"executive summary: HTTP {r.status_code} {r.text[:200]}")


async def refresh_once(now: Optional[datetime] = None) -> List[str]:
    """Make every due run. Returns "kind:topic" for each run made."""
    import httpx

    s = _settings()
    if s is None:
        return []
    now = now or datetime.now()
    slot = last_slot(now, s["weekday"], s["hour"])
    newest = await asyncio.to_thread(_newest_runs, s["topics"])
    todo = [(k, t) for k, t in due(newest, slot) if _RETRY_AFTER.get(t, now) <= now]
    if not todo:
        return []

    base = f"http://127.0.0.1:{os.getenv('PORT', '10015')}"
    cookies = {"session": _session_cookie(s["user"])}
    headers = {"X-Forwarded-Proto": "https"}
    params = {"model": s["model"], "timeframe_days": s["timeframe_days"], "persona": s["persona"],
              "profile_id": s["profile_id"], "enable_caching": "false"}
    done: List[str] = []
    async with httpx.AsyncClient(timeout=900) as client:
        for kind, topic in todo:
            if _RETRY_AFTER.get(topic, now) > now:
                continue
            try:
                r = await client.get(f"{base}/api/trend-convergence/{quote(topic)}",
                                     params={**params, "tab": kind}, cookies=cookies, headers=headers)
                if r.status_code != 200:
                    raise RuntimeError(f"HTTP {r.status_code} {r.text[:200]}")
                payload = r.json() or {}
                logger.info("foresight refresh: new %s run for %r (%s)", kind, topic, payload.get("analysis_id"))
                if kind == "horizons":
                    await _executive_summary(client, payload, topic, s, base, cookies, headers)
                done.append(f"{kind}:{topic}")
            except Exception as exc:  # noqa: BLE001
                logger.warning("foresight refresh: %s run for %r failed: %s", kind, topic, exc)
                _status["last_error"] = f"{kind}:{topic}: {exc}"
                _RETRY_AFTER[topic] = now + timedelta(days=1)
    return done


async def run_foresight_refresh():
    """Main loop. Exits at once unless the topics and a profile are set."""
    s = _settings()
    if s is None:
        logger.info("Foresight refresh disabled (FORESIGHT_REFRESH_TOPICS / _PROFILE_ID unset)")
        return
    _status["enabled"] = True
    logger.info("Foresight refresh started: %d topics, profile %s, weekday %s %02d:00, model %s",
                len(s["topics"]), s["profile_id"], s["weekday"], s["hour"], s["model"])
    while True:
        try:
            _status["last_check_time"] = datetime.now().isoformat()
            made = await refresh_once()
            if made:
                _status["last_runs"] = made
        except Exception as e:  # noqa: BLE001
            logger.error("Foresight refresh loop error: %s", e, exc_info=True)
            _status["last_error"] = str(e)
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
