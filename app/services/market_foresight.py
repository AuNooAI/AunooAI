"""The market's Consensus and Three-Horizons reports, public and dated.

saas.aunoo.ai shares these reports as frozen token links; the operator
tenants download them as self-contained HTML. Here they are pages of the
market site, built from the newest stored run for the market's collection
topic with the same builders the download uses (``consensus_html`` and
``horizons_html``), so a reader of aisocnews.com sees exactly what the
operator sees. Each page lists the earlier runs and can open any of them,
which is the first form of tracking over time: the runs are dated, and
what the coverage agreed on in September stays readable in December.

The second form is the Forecast Tracker, enrolled separately: the horizons
run is the forecast, and a monthly paired assessment scores each scenario
against the events that followed.

The runs themselves are made by the trend-convergence route, whose
generation is inline in that route. Rather than copy 500 lines, the monthly
refresh calls the route over loopback with a session it mints from the
app's own secret, the same way an operator's browser does. That keeps the
cache keys, run logs and executive summaries the route writes.

These pages are our writing about the coverage, not the vendor roster, so
they are public in full, as the editorial pieces are (decision of 29
August 2026); the withheld-names gate is not applied to them.
"""

import asyncio
import base64
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from app.services.html_report_common import esc

logger = logging.getLogger(__name__)

REFRESH_DAYS = 30                      # one new run of each report a month
TIMEFRAME_DAYS = 30                    # the coverage window each run reads
DEFAULT_MODEL = os.getenv("MARKET_FORESIGHT_MODEL",
                          os.getenv("MARKET_TOPICS_MODEL", "bedrock-kimi-k2-5"))
SESSION_USER = os.getenv("MARKET_FORESIGHT_USER", "admin")   # whose session the refresh runs as
HISTORY_LIMIT = 12
KINDS = ("consensus", "horizons")
_TABLES = {"consensus": "consensus_analysis_runs", "horizons": "future_horizons_runs"}
_LABELS = {"consensus": "Consensus analysis", "horizons": "Three horizons"}


def topic_for(market: Dict[str, Any]) -> Optional[str]:
    cfg = market.get("config") or {}
    if isinstance(cfg, str):
        try:
            cfg = json.loads(cfg)
        except ValueError:
            cfg = {}
    return ((cfg.get("collection") or {}).get("topic_name")) or None


def profile_for(market: Dict[str, Any]) -> Optional[int]:
    """The organisational profile the reports are written for, from the
    market's config (``foresight.profile_id``). None means the tenant's
    default profile, which on this tenant is another customer's."""
    cfg = market.get("config") or {}
    if isinstance(cfg, str):
        try:
            cfg = json.loads(cfg)
        except ValueError:
            cfg = {}
    pid = (cfg.get("foresight") or {}).get("profile_id")
    return int(pid) if pid else None


def _raw(value: Any) -> Dict[str, Any]:
    """raw_output is JSON, sometimes JSON inside a JSON string."""
    for _ in range(2):
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                return {}
    return value if isinstance(value, dict) else {}


def runs(conn, kind: str, topic: str, limit: int = HISTORY_LIMIT) -> List[Dict[str, Any]]:
    """The stored runs for this topic, newest first: id, when, model, how
    many articles. No payloads."""
    model_col = "NULL" if kind == "consensus" else "model_used"
    rows = conn.execute(text(f"""
        SELECT id, created_at, {model_col} AS model_used, total_articles_analyzed
          FROM {_TABLES[kind]} WHERE topic = :t
         ORDER BY created_at DESC LIMIT :n
    """), {"t": topic, "n": limit}).mappings().all()
    return [dict(r) for r in rows]


def load_run(conn, kind: str, topic: str, run_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """One run with its payload: the newest, or the one asked for as long
    as it belongs to this topic."""
    where = "topic = :t" + (" AND id = :id" if run_id else "")
    row = conn.execute(text(f"""
        SELECT * FROM {_TABLES[kind]} WHERE {where}
         ORDER BY created_at DESC LIMIT 1
    """), {"t": topic, "id": run_id}).mappings().first()
    if not row:
        return None
    out = dict(row)
    out["raw"] = _raw(out.get("raw_output"))
    return out


def _horizons_articles(conn, run_id: str) -> List[Dict[str, Any]]:
    rows = conn.execute(text("""
        SELECT a.uri, a.title, a.news_source, a.publication_date
          FROM future_horizon_articles fha JOIN articles a ON a.uri = fha.article_uri
         WHERE fha.horizon_id = :r ORDER BY fha.id ASC
    """), {"r": run_id}).mappings().all()
    return [{"id": i, "uri": r["uri"], "url": r["uri"] if str(r["uri"]).startswith("http") else None,
             "title": r["title"], "source": r["news_source"],
             "published": r["publication_date"]} for i, r in enumerate(rows, 1)]


def _strip(market: Dict[str, Any], kind: str, run: Dict[str, Any],
           history: List[Dict[str, Any]], front_href: str) -> str:
    """The bar above the report: where it belongs, and the earlier runs."""
    when = run.get("created_at")
    when_txt = when.strftime("%d %B %Y") if hasattr(when, "strftime") else str(when)[:10]
    items = []
    for r in history:
        d = r["created_at"]
        label = d.strftime("%d %b %Y") if hasattr(d, "strftime") else str(d)[:10]
        if r["id"] == run["id"]:
            items.append(f"<strong>{esc(label)}</strong>")
        else:
            items.append(f'<a href="{esc(front_href)}&page={kind}&run={esc(str(r["id"]))}">{esc(label)}</a>')
    other = "horizons" if kind == "consensus" else "consensus"
    return (
        '<div style="font:14px/1.5 \'DM Sans\',system-ui,sans-serif;background:#211f26;color:#bcbac7;'
        'padding:10px 24px;display:flex;flex-wrap:wrap;gap:14px;align-items:center">'
        f'<a href="{esc(front_href)}" style="color:#fff;text-decoration:none;font-weight:600">'
        f'&larr; {esc(market["name"])} front page</a>'
        f'<span>{esc(_LABELS[kind])} · run of {esc(when_txt)}</span>'
        f'<a href="{esc(front_href)}&page={other}" style="color:#fff">{esc(_LABELS[other])}</a>'
        + (f'<span style="margin-left:auto">Earlier runs: {" · ".join(items)}</span>'
           if len(history) > 1 else "")
        + "</div>")


def render(conn, kind: str, market: Dict[str, Any], *, run_id: Optional[str] = None,
           front_href: str = "/?view=v2") -> Optional[bytes]:
    """The report as a self-contained page, or None when the topic has no
    run yet. Raises LookupError for a run id that is not this topic's."""
    if kind not in KINDS:
        raise ValueError(kind)
    topic = topic_for(market)
    if not topic:
        return None
    run = load_run(conn, kind, topic, run_id)
    if run is None:
        if run_id:
            raise LookupError(f"no {kind} run {run_id} for this market")
        return None
    raw = run["raw"]
    generated_at = run.get("created_at") or raw.get("generated_at")
    if hasattr(generated_at, "isoformat"):
        generated_at = generated_at.isoformat()
    model_used = run.get("model_used") or raw.get("model_used")
    if kind == "consensus":
        from app.services.consensus_html import build_consensus_html
        blob = build_consensus_html(market["name"], raw, generated_at=generated_at,
                                    model_used=model_used)
    else:
        from app.database import get_database_instance
        from app.services.horizons_html import build_horizons_html
        summaries: List[Any] = []
        try:
            payload = get_database_instance().facade.get_horizons_executive_summary(run["id"]) or {}
            summaries = payload.get("summaries") or []
        except Exception:  # noqa: BLE001 — the cards are optional
            logger.debug("no executive summary for horizons run %s", run["id"])
        blob = build_horizons_html(market["name"], raw.get("scenarios") or [], summaries,
                                   generated_at=generated_at, model_used=model_used,
                                   articles=_horizons_articles(conn, run["id"]))
    html = blob.decode("utf-8") if isinstance(blob, bytes) else str(blob)
    strip = _strip(market, kind, run, runs(conn, kind, topic), front_href)
    i = html.find("<body")
    if i >= 0:
        j = html.find(">", i)
        html = html[:j + 1] + strip + html[j + 1:]
    else:
        html = strip + html
    return html.encode("utf-8")


# ---------------------------------------------------------------------------
# Monthly refresh: the route, over loopback, as an operator
# ---------------------------------------------------------------------------

_RETRY_AFTER: Dict[int, datetime] = {}


def _session_cookie(user: str) -> str:
    import itsdangerous

    secret = os.getenv("FLASK_SECRET_KEY") or ""
    if not secret:
        raise RuntimeError("FLASK_SECRET_KEY unset; cannot mint a session")
    data = base64.b64encode(json.dumps({"user": user}).encode())
    return itsdangerous.TimestampSigner(secret).sign(data).decode()


def newest_run_at(conn, kind: str, topic: str) -> Optional[datetime]:
    return conn.execute(text(
        f"SELECT MAX(created_at) FROM {_TABLES[kind]} WHERE topic = :t"
    ), {"t": topic}).scalar()


async def refresh(conn, market: Dict[str, Any], now: datetime, *, force: bool = False) -> List[str]:
    """Make a new consensus run and a new horizons run when the newest is
    REFRESH_DAYS old. Returns the kinds refreshed. Failures back off a day
    so the 15-minute tick does not hammer a broken model."""
    import httpx

    market_id = int(market["id"])
    if not force and _RETRY_AFTER.get(market_id, now) > now:
        return []
    topic = topic_for(market)
    if not topic:
        return []
    due = []
    for kind in KINDS:
        last = newest_run_at(conn, kind, topic)
        if hasattr(last, "tzinfo") and last is not None and last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if force or last is None or (now - last) >= timedelta(days=REFRESH_DAYS):
            due.append(kind)
    conn.commit()
    if not due:
        return []

    port = os.getenv("PORT", "10004")
    from urllib.parse import quote
    base = f"http://127.0.0.1:{port}/api/trend-convergence/{quote(topic)}"
    params = {"model": DEFAULT_MODEL, "timeframe_days": TIMEFRAME_DAYS, "persona": "analyst",
              "enable_caching": "false"}
    profile = profile_for(market)
    if profile:
        params["profile_id"] = profile
    cookies = {"session": _session_cookie(SESSION_USER)}
    headers = {"X-Forwarded-Proto": "https"}
    done: List[str] = []
    async with httpx.AsyncClient(timeout=600) as client:
        for kind in due:
            try:
                r = await client.get(base, params={**params, "tab": kind},
                                     cookies=cookies, headers=headers)
                if r.status_code != 200:
                    raise RuntimeError(f"{kind}: HTTP {r.status_code} {r.text[:200]}")
                done.append(kind)
                logger.info("market %s: new %s run for %r (%s)", market_id, kind, topic,
                            (r.json() or {}).get("analysis_id"))
            except Exception as exc:  # noqa: BLE001
                logger.warning("market %s: %s refresh failed: %s", market_id, kind, exc)
                _RETRY_AFTER[market_id] = now + timedelta(days=1)
    return done
