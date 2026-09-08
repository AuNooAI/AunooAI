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
import re
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


# The report renderers carry the operator deliverables' look (system font,
# slate greys, the Wiley eyebrow by default). On the market site the page
# takes the site's chrome and palette instead: the same top bar and footer
# as the front page, DM Sans, and the site's tokens swapped for the
# report's colours inside its style blocks. The renderers stay untouched
# because the Wiley bundles depend on them.
# The site's tokens (aunoo-aisocnews-design-system.md); the report's own
# stylesheet is static, so its literals become the variables and the theme
# toggle reaches the report body too.
_PALETTE = (
    ("#d6346c", "var(--accent)"),         # accent
    ("#111827", "var(--nav-bg)"),         # dark ground
    ("#1f2937", "var(--text-secondary)"), # body text
    ("#f8fafc", "var(--area-bg)"),        # page background
    ("#f9fafb", "var(--wrap-2)"),         # subtle panel
    ("#e5e7eb", "var(--sidebar-border)"), # lines
    ("#6b7280", "var(--text-muted)"),     # muted text
    ("#fbcfe4", "var(--text-on-dark)"),   # cover subtitle
    ("background: #fff;", "background: var(--wrap);"),  # cards
    ("-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
     "var(--font-sans)"),
)
_STYLE_RE = re.compile(r"<style>.*?</style>", re.S)
_BRAND_SWAPS = (
    ("WILEY HORIZONS", "CYBERFUTURISTS"),
    ("Wiley Horizons", "Cyberfuturists"),
    ("Produced by AunooAI", "By the Cyberfuturists, made using Aunoo"),
    ("AunooAI", "Aunoo"),
    ("model: bedrock-kimi-k2-5", "model: Kimi K2.5"),
    ("model: gpt-5.4", "model: Claude Sonnet"),
)
_REPORT_CSS = """
.mm-report { border-radius:0; margin:0; border:0; box-shadow:none; }
.mm-report .container { max-width:1040px; padding-top:1.4rem; }
.mm-report .cover { border-radius:var(--r-card); }
/* The cover is a dark band in both themes; its type stays light. */
.mm-report .cover h1, .mm-report .cover h2, .mm-report .topic-divider h2 { color:#fff; font-size:clamp(26px,3.2vw,36px);
  letter-spacing:-.03em; }
.mm-report .cover .subtitle { color:var(--text-on-dark); }
.mm-report .cover .eyebrow, .mm-report .topic-divider .eyebrow { color:var(--accent-text-active); }
.mm-report .card, .mm-report .es-card, .mm-report .scenario-card { border-radius:var(--r-card); }
.mm-report .card h3, .mm-report .card h4, .mm-report .es-card h3, .mm-report .scenario-card h4,
.mm-report .section h2, .mm-report .es-signal { color:var(--text-primary); }
.mm-report .section-eyebrow, .mm-report .es-signal-label, .mm-report .es-window .tf,
.mm-report .cat-eyebrow { color:var(--accent-ink); }
.mm-report .n-jump { align-items:center; }
.mm-report .n-jump .n-jump-label { color:#bcbac7; font-size:.8rem; padding:6px 4px 6px 0; }
.mm-report .n-jump a[aria-current="page"] { background:var(--n-accent); color:#fff; border-color:var(--n-accent); }
.mm-report .n-pages a, .mm-report .n-jump a, .mm-report .n-foot a, .mm-report .n-brand a { text-decoration:none; }
/* Consensus categories fold: header and badge stay, the body opens on click. */
.mm-report .cat-card .cat-header { cursor:pointer; position:relative; padding-right:2.2rem; }
.mm-report .cat-card .cat-header::after { content:""; position:absolute; right:.6rem; top:1.1rem; width:.6rem; height:.6rem;
  border-right:2px solid #65636d; border-bottom:2px solid #65636d; transform:rotate(45deg); transition:transform .15s; }
.mm-report .cat-card.collapsed .cat-header::after { transform:rotate(-45deg); }
.mm-report .cat-card.collapsed .cat-body, .mm-report .cat-card.collapsed .cat-header .lhs p { display:none; }
.mm-report .cat-card .cat-header:focus-visible { outline:2px solid var(--n-accent); outline-offset:2px; }
.mm-report .cat-fold, .mm-report .cat-all { font:inherit; font-size:.82rem; font-weight:600; color:var(--n-accent);
  background:none; border:1px solid var(--n-line); border-radius:7px; padding:.35rem .7rem; cursor:pointer; margin:.6rem 0 .2rem; }
.mm-report .cat-fold:hover, .mm-report .cat-all:hover { border-color:var(--n-accent); }
.mm-report .cat-all { margin:0 0 .8rem; }
"""

# The download is static. On the site each category folds to its header,
# all closed on load, and the key-article list inside folds behind a count,
# so a reader scans four headlines rather than four screens. No library.
_FOLD_JS = """
(function(){
  var cards=document.querySelectorAll('.cat-card'); if(!cards.length) return;
  cards.forEach(function(card,i){
    var h=card.querySelector('.cat-header'); if(!h) return;
    var body=document.createElement('div'); body.className='cat-body';
    var n=h.nextSibling; while(n){var nx=n.nextSibling; body.appendChild(n); n=nx;}
    card.appendChild(body);
    card.classList.add('collapsed');
    h.setAttribute('role','button'); h.tabIndex=0;
    h.setAttribute('aria-expanded', 'false');
    // The renderer numbers categories ("CATEGORY 2"), which says nothing.
    // The eyebrow takes the consensus type and its strength from the
    // card's own metric boxes instead: "MARKET SHIFT · MODERATE CONSENSUS".
    var eyebrow=h.querySelector('.cat-eyebrow'), type='', strength='';
    body.querySelectorAll('.metric-box').forEach(function(m){
      var l=(m.querySelector('.label')||{}).textContent||'', v=(m.querySelector('.value')||{}).textContent||'';
      l=l.trim().toUpperCase(); v=v.trim();
      if(l==='CONSENSUS TYPE') type=v; else if(l==='STRENGTH') strength=v;
    });
    if(eyebrow && type){ eyebrow.textContent=type+(strength?' · '+strength+' consensus':''); }
    function toggle(){ card.classList.toggle('collapsed'); h.setAttribute('aria-expanded', String(!card.classList.contains('collapsed'))); }
    h.addEventListener('click',function(e){ if(e.target.closest('a')) return; toggle(); });
    h.addEventListener('keydown',function(e){ if(e.key==='Enter'||e.key===' '){ e.preventDefault(); toggle(); } });
    var list=body.querySelector('.cat-articles-list');
    if(list && list.children.length>3){
      var count=list.children.length, btn=document.createElement('button');
      btn.type='button'; btn.className='cat-fold'; list.hidden=true;
      btn.textContent='Show '+count+' key articles';
      list.parentNode.insertBefore(btn,list);
      btn.addEventListener('click',function(){ list.hidden=!list.hidden; btn.textContent=(list.hidden?'Show ':'Hide ')+count+' key articles'; });
    }
  });
  var all=document.createElement('button'); all.type='button'; all.className='cat-all';
  var open=false; function label(){ all.textContent=open?'Collapse all categories':'Expand all categories'; } label();
  all.addEventListener('click',function(){ open=!open; cards.forEach(function(c){ c.classList.toggle('collapsed',!open); var h=c.querySelector('.cat-header'); if(h) h.setAttribute('aria-expanded',String(open)); }); label(); });
  cards[0].parentNode.insertBefore(all, cards[0]);
})();
"""


def _restyle(html: str) -> str:
    """The report's own style blocks, in the site's colours and type; the
    Wiley eyebrow and the product name as the site writes them."""
    def _swap(m: "re.Match[str]") -> str:
        block = m.group(0)
        for old, new in _PALETTE:
            block = block.replace(old, new)
        return block
    html = _STYLE_RE.sub(_swap, html)
    for old, new in _BRAND_SWAPS:
        html = html.replace(old, new)
    return html


def _chrome(market: Dict[str, Any], kind: str, run: Dict[str, Any],
            history: List[Dict[str, Any]], front_href: str) -> tuple:
    """The site's top bar (with the run list as the jump row) and footer,
    plus the style blocks they need, as (head_extra, top, foot)."""
    from app.services.market_report_html import (
        _brand_line, _theme_toggle, _FONT_LINK_V2, _THEME_JS, NEWS_CSS, DARK_CSS, V2_CSS, EXTRA_CSS)

    other = "horizons" if kind == "consensus" else "consensus"
    pages = (f'<a href="{esc(front_href)}">Front page</a>'
             f'<a href="{esc(front_href)}&view=report">Analyst View</a>'
             f'<a href="{esc(front_href)}&view=news">News river</a>'
             f'<a href="{esc(front_href)}&page={other}">{esc(_LABELS[other])}</a>')
    runs_html = ""
    if len(history) > 1:
        # Two runs on one day are told apart by their time.
        days = [str(r["created_at"])[:10] for r in history]
        items = []
        for r in history:
            d = r["created_at"]
            same_day = days.count(str(d)[:10]) > 1
            fmt = "%d %b %Y %H:%M" if same_day else "%d %b %Y"
            label = d.strftime(fmt) if hasattr(d, "strftime") else str(d)[:16 if same_day else 10]
            cur = ' aria-current="page"' if r["id"] == run["id"] else ""
            items.append(f'<a href="{esc(front_href)}&page={kind}&run={esc(str(r["id"]))}"{cur}>'
                         f'{esc(label)}</a>')
        runs_html = ('<nav class="n-jump" aria-label="Runs">'
                     f'<span class="n-jump-label">{esc(_LABELS[kind])} runs</span>'
                     + "".join(items) + "</nav>")
    about = f"{front_href}&page=about"
    head_extra = (f"{_FONT_LINK_V2}<style>{EXTRA_CSS}{NEWS_CSS}{DARK_CSS}{V2_CSS}{_REPORT_CSS}</style>")
    # The theme script goes first in the body so a stored dark choice applies
    # before anything paints; the light theme itself is declared on <html>.
    top = (f"<script>{_THEME_JS}</script>"
           '<div class="mm-news mm-v2 mm-report"><div class="n-top">' + _brand_line()
           + f'<nav class="n-pages" aria-label="Pages">{pages}{_theme_toggle()}</nav>'
           + runs_html
           + f'<span class="n-market">{esc(market["name"])}</span></div>')
    foot = ('<div class="n-foot">' + _brand_line()
            + f'<span>{esc(market["name"])} · {esc(_LABELS[kind])} · '
            f'<a href="{esc(about)}">About</a> · <a href="{esc(about)}#privacy">Privacy</a> · '
            f'<a href="{esc(front_href)}&page={other}">{esc(_LABELS[other])}</a></span></div></div>'
            + (f"<script>{_FOLD_JS}</script>" if kind == "consensus" else ""))
    return head_extra, top, foot


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
    html = _restyle(html)
    head_extra, top, foot = _chrome(market, kind, run, runs(conn, kind, topic), front_href)
    html = html.replace("</head>", head_extra + "</head>", 1)
    html = html.replace('<html lang="en">', '<html lang="en" data-theme="light">', 1)
    i = html.find("<body")
    j = html.find(">", i) if i >= 0 else -1
    if j >= 0:
        html = html[:j + 1] + top + html[j + 1:]
        html = html.replace("</body>", foot + "</body>", 1)
    else:
        html = top + html + foot
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
                payload = r.json() or {}
                done.append(kind)
                logger.info("market %s: new %s run for %r (%s)", market_id, kind, topic,
                            payload.get("analysis_id"))
                if kind == "horizons":
                    # The executive-summary cards are a second generation
                    # step in the app; the page shows them when they exist.
                    await _executive_summary(client, payload, topic, profile, cookies, headers)
            except Exception as exc:  # noqa: BLE001
                logger.warning("market %s: %s refresh failed: %s", market_id, kind, exc)
                _RETRY_AFTER[market_id] = now + timedelta(days=1)
    return done


async def _executive_summary(client, payload: Dict[str, Any], topic: str,
                             profile: Optional[int], cookies: Dict[str, str],
                             headers: Dict[str, str]) -> None:
    run_id = payload.get("analysis_id")
    scenarios = payload.get("scenarios") or []
    if not run_id or not scenarios:
        return
    port = os.getenv("PORT", "10004")
    body: Dict[str, Any] = {"scenarios": scenarios, "topic": topic, "model": DEFAULT_MODEL}
    if profile:
        body["profile_id"] = profile
    r = await client.post(
        f"http://127.0.0.1:{port}/api/trend-convergence/horizons/{run_id}/executive-summary",
        json=body, cookies=cookies, headers=headers)
    if r.status_code != 200:
        raise RuntimeError(f"executive summary: HTTP {r.status_code} {r.text[:200]}")
    cards = ((r.json() or {}).get("executive_summary") or {}).get("summaries") or []
    logger.info("horizons run %s: %d executive-summary cards", run_id, len(cards))
