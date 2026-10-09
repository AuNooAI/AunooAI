"""The weekly LinkedIn post: what the market's vendors did last week.

The post says what happened, not why. Its shape is the one the publisher
wrote by hand on 2 October 2026: a line naming the market and the week, a
handful of bullets that group the week's developments by kind (launches,
open-source releases, partnerships, integrations, analyst mentions), the
open-role count, the chart's movers, whether anything was acquired, one
sentence on the pattern, and the link.

The model writes only the development bullets and the pattern sentence, from
the same stored facts the market briefing uses (``market_briefing.
build_facts``), and it must cite a fact for every bullet. A bullet without a
valid citation is dropped. Everything with a number in it that the code can
state itself (open roles, the chart, acquisitions, vendor count) is written
by the code, so no figure in the post is the model's.

Nothing posts to LinkedIn. The post is stored and mailed to the editors,
with each bullet's sources under it, to check, tag the vendors and paste.
"""

import json
import logging
import os
import re
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text

logger = logging.getLogger(__name__)

# The standard tier, not the cheap one the briefing uses: one call a week,
# and on 9 Oct 2026 the cheap model put Exaforce's CrowdStrike Marketplace
# listing under Exabeam's name in a post that goes out under a person's name.
POST_MODEL = os.getenv("MARKET_WEEKLY_POST_MODEL", "")  # empty: the standard tier
MAX_BULLETS = 5
# Cited sentences per bullet, after an optional lead. The example's longest
# bullet has three.
MAX_SENTENCES = 3
# Facts shown to the model per section. A week has about a hundred vendor
# posts; the noise among them (job ads for one person, event photos) is the
# model's to skip, but the list has to stay readable.
MAX_FACTS = 80

# The publisher's own post of 2 October 2026, trimmed to the bullets. Given
# to the model for shape and register only; its facts are from another week.
EXAMPLE = """- The specialists shipped focused products. Strike48 launched an on-premises agentic SOC appliance that can run fully air-gapped, with local inference. AiStrike launched AiStrike for Insider Threat. Spectrum Security launched Detection Health, which checks every detection rule against the live environment, then generates and applies fixes with a human in the loop.
- Nebulock open-sourced its GATES Method, a framework for deciding when a threat hunt should become a detection.
- Specialists signed channel partners. Exaforce signed KDDI America and KDDI Europe to reach multinational companies across the US and EMEA, with KDDI Corporation adding managed services. At GISEC, Aquila I signed Ampcus Cyber as a global MSSP partner and Virus Rescuers for the Middle East.
- BlinkOps connected its agentic security operations to Microsoft Sentinel Data Lake.
- Tuskira says it is named in Gartner's 2026 Emerging Tech Impact Radar for preemptive cybersecurity, the report that also lists Kai Security and Backline AI as Sample Vendors.
SUMMARY: The specialists are shipping for specific settings, such as air-gapped sites, insider risk and broken detections, and signing partners to sell them."""

_CITE = re.compile(r"\[([AC]\d+)\]")


def _incumbents(conn, market_id: int) -> set:
    return {r[0] for r in conn.execute(text("""
        SELECT b.display_name FROM bw_market_vendor_controls vc
        JOIN bw_brands b ON b.id = vc.brand_id
        WHERE vc.market_id = :m AND vc.status = 'incumbent'
    """), {"m": market_id}).fetchall()}


def _vendor_names(conn, market_id: int) -> set:
    """Every tracked vendor's display name, for the name check."""
    return {r[0] for r in conn.execute(text("""
        SELECT b.display_name FROM bw_market_brands mb
        JOIN bw_brands b ON b.id = mb.brand_id
        WHERE mb.market_id = :m AND mb.role <> 'excluded'
    """), {"m": market_id}).fetchall() if r[0]}


def _facts_block(facts: Dict[str, Any], incumbents: set) -> str:
    from app.services.market_briefing import source_label

    lines = ["VENDOR POSTS (each is the vendor's own claim about itself):"]
    for a in facts["announcements"][:MAX_FACTS]:
        tag = " (large incumbent)" if a["vendor"] in incumbents else ""
        lines.append(f"[{a['cite_id']}] {(a.get('publication_date') or '')[:10]} "
                     f"{a['vendor']}{tag} ({a.get('kind')}): {a['title']}"
                     + (f" | {a['reason']}" if a.get("reason") else ""))
    lines.append("\nTHIRD-PARTY COVERAGE:")
    for c in facts["coverage"][:MAX_FACTS]:
        lines.append(f"[{c['cite_id']}] {(c.get('publication_date') or '')[:10]} "
                     f"{source_label(c.get('news_source')) or 'unknown'}: {c['title']}")
    return "\n".join(lines)


def build_prompt(market: Dict[str, Any], span: str, facts: Dict[str, Any],
                 incumbents: set) -> str:
    return f"""Write the bullets for this week's LinkedIn post about {market['name']}, covering {span}.

The post says WHAT the vendors did. It does not explain why, rank them,
predict anything or give advice.

Here is last week's post, for shape and tone only. Its facts are from another
week and must not appear in yours:

{EXAMPLE}

Rules:
- Use only the facts below. No company, product, figure, partner or date that
  is not in them.
- Write 3 to {MAX_BULLETS} bullets, each starting "- " and then the kind's
  number in brackets, such as "- (3) ". One bullet per kind, and only for
  the kinds the week has:
    1. product launches and new features
    2. open-source releases
    3. partnerships, channel deals, marketplace listings and integrations
    4. funding
    5. analyst reports and awards that name a vendor
  Every sentence in a bullet is that bullet's kind. Never mix kinds.
- A bullet covering several vendors may open with a short lead sentence
  naming what they did, as the example's "Specialists signed channel
  partners." does. A lead sentence needs no citation. After it, at most
  three sentences.
- Each bullet names the vendor and the concrete thing: the product, the
  partner, the report. One to three short sentences. Pick the most
  significant developments; the post is short, so leave the minor ones out.
- Write about the specialist vendors. Leave out the large incumbents (marked
  below) unless a specialist is part of the development, such as a
  specialist joining an incumbent's marketplace.
- Leave out: job adverts, event appearances, webinars, customer quotes and
  testimonials, threat research and vulnerability disclosures, general AI
  model releases, product teasers, marketing slogans and anything you
  cannot state as a concrete development.
- Name the vendor exactly as the fact you cite names it. Each sentence cites
  the facts it rests on; a sentence naming a vendor must cite that vendor's
  fact.
- A vendor's claim about outside recognition is written as a claim: "X says
  it is named in ...".
- After each sentence, put the IDs of the facts it rests on, such as [A3] [C7].
  Every sentence needs at least one. Copy IDs exactly.
- Do not mention hiring, job counts, acquisitions or rankings: those lines are
  added separately.
- No dashes of any kind as punctuation. Plain words, no hype.
- Finish with one line starting "SUMMARY:" and one sentence describing what
  the specialists did, in the style of the example's last line. It says what
  happened, never why, and never characterises anyone's motives. It uses
  only what your bullets say: no place, company, report or product that is
  not in them.
- Output only the bullets and the SUMMARY line.

FACTS:
{_facts_block(facts, incumbents)}
"""


def _sentences(text_: str) -> List[str]:
    # A sentence ends at its full stop, or after the citations that follow it.
    return [p for p in re.split(r"(?<=[.!?\]])\s+(?=[A-Z0-9@])", text_.strip()) if p]


def parse(content: str, citation_index: Dict[str, Any],
          vendors: Optional[set] = None
          ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """The model's bullets with their cited sources, and the summary line.

    Checked sentence by sentence. A sentence that cites nothing we gave it
    is dropped, and so is one that names a tracked vendor none of its cited
    facts is about or mentions in its title: that is the model attaching one
    vendor's news to another's name. A bullet left with no sentence goes.
    """
    vendors = vendors or set()
    bullets, summary = [], None
    for raw in (content or "").splitlines():
        line = raw.strip()
        if line.upper().startswith("SUMMARY:"):
            summary = _clean(_CITE.sub("", line.split(":", 1)[1]))
            continue
        if not line.startswith(("-", "*", "•")):
            continue
        line = line.lstrip("-*• ")
        kind_m = re.match(r"\((\d)\)\s*", line)
        kind = int(kind_m.group(1)) if kind_m else 9
        line = line[kind_m.end():] if kind_m else line
        kept, sources, lead = [], {}, None
        for n, sentence in enumerate(_sentences(line)):
            ids = [i for i in _CITE.findall(sentence) if i in citation_index]
            if not ids:
                # Only the opening sentence may go uncited, as a lead naming
                # what the bullet's vendors did; it may not name one.
                body = _clean(_CITE.sub("", sentence))
                if n == 0 and not any(re.search(
                        r"(?<![\w])" + re.escape(v.lower()) + r"(?![\w])", body.lower())
                        for v in vendors):
                    lead = body
                continue
            if len(kept) >= MAX_SENTENCES:
                break
            body = _clean(_CITE.sub("", sentence))
            cited = [citation_index[i] for i in ids]
            seen = " ".join(f"{c.get('vendor') or ''} {c.get('title') or ''}"
                            for c in cited).lower()
            named = [v for v in vendors if re.search(
                r"(?<![\w])" + re.escape(v.lower()) + r"(?![\w])", body.lower())]
            if any(v.lower() not in seen for v in named):
                logger.info("weekly post: dropped a sentence naming a vendor its "
                            "sources do not: %s", body[:120])
                continue
            kept.append(body)
            for i in ids:
                sources[i] = dict(citation_index[i], id=i)
        if kept:
            bullets.append({"text": " ".join(([lead] if lead else []) + kept),
                            "sources": list(sources.values()), "kind": kind})
    bullets.sort(key=lambda b: b["kind"])   # stable: the model's order within a kind
    bullets = bullets[:MAX_BULLETS]
    return bullets, _checked_summary(summary, bullets)


def _checked_summary(summary: Optional[str], bullets: List[Dict[str, Any]]
                     ) -> Optional[str]:
    """The summary cites nothing, so it may only name what the bullets name.
    Every capitalised word after its first must appear in a bullet; one that
    does not (a region, a company, a report) is the model adding a fact, and
    the sentence goes."""
    if not summary or not bullets:
        return None
    said = " ".join(b["text"] for b in bullets).lower()
    words = re.findall(r"[A-Za-z][\w&'.-]*", summary)[1:]
    for w in words:
        if w[0].isupper() and w.strip(".").lower() not in said:
            logger.info("weekly post: dropped the summary, %r is not in the bullets", w)
            return None
    return summary


def _clean(s: str) -> str:
    s = re.sub(r"\s*[—–]\s*", ", ", s)   # dashes read as machine-written
    s = re.sub(r"\s+([.,;:])", r"\1", s)
    return re.sub(r"\s{2,}", " ", s).strip()


def movers_line(market: Dict[str, Any], data: Dict[str, Any]) -> Optional[str]:
    """The chart's week in one bullet: who is #1, who climbed and fell
    furthest, who is new. What moved, not why."""
    from app.services import market_chart as mc

    rows = data.get("rows") or []
    if not rows:
        return None
    name = mc.title(market, len(rows))
    top = rows[0]
    if top["status"] in ("new", "reentry") or (top["last_week"] or 0) > 1:
        was = next((r for r in rows if r["last_week"] == 1), None)
        lead = f"{top['vendor']} took #1" + (f" from {was['vendor']}" if was else "")
    elif top["weeks_at_1"] > 1:
        lead = f"{top['vendor']} held #1 for a {mc._ordinal(top['weeks_at_1'])} week"
    else:
        lead = f"{top['vendor']} is #1"
    parts = [f"On the {name}, {lead}."]
    up = sorted((r for r in rows[1:] if r["status"] == "up"
                 and r["move"] >= mc.POST_MIN_MOVE),
                key=lambda r: (-r["move"], r["rank"]))[:3]
    if up:
        first = up[0]
        s = f"{first['vendor']} climbed {first['move']} places to #{first['rank']}"
        rest = [f"{r['vendor']} {r['move']} to #{r['rank']}" for r in up[1:]]
        parts.append(mc._names([s] + rest) + ".")
    down = sorted((r for r in rows if r["status"] == "down"
                   and -r["move"] >= mc.POST_MIN_MOVE),
                  key=lambda r: (r["move"], r["rank"]))[:1]
    if down:
        r = down[0]
        parts.append(f"{r['vendor']} fell {-r['move']} places to #{r['rank']}.")
    new = [r["vendor"] for r in rows if r["status"] == "new"]
    if new:
        parts.append(f"New this week: {mc._names(new)}.")
    return " ".join(parts)


def hiring_line(conn, market_id: int, previous: Optional[int]
                ) -> Tuple[Optional[str], Optional[int]]:
    """Open roles now, the three vendors with the most, and the change from
    the count the last post recorded."""
    from app.services import market_analysis as man

    h = man.hiring(conn, market_id)
    total = int(h.get("openings") or 0)
    if not total:
        return None, None
    top = [f"{v['vendor']} ({v['openings']})" for v in (h.get("by_vendor") or [])[:3]]
    from app.services.market_chart import _names
    trend = ""
    if previous:
        if total < previous:
            trend = f", down from {previous} a week earlier"
        elif total > previous:
            trend = f", up from {previous} a week earlier"
        else:
            trend = ", the same as a week earlier"
    line = (f"We count {total} open roles across the vendors we track{trend}"
            + (f", led by {_names(top)}." if top else "."))
    return line, total


async def compose(conn, market: Dict[str, Any], week_start: date) -> Dict[str, Any]:
    """The week's post and its sources. Raises nothing for a quiet week; the
    development bullets are then simply absent."""
    from app.ai_models import LiteLLMModel
    from app.routes.vector_routes import _generate_report_with_retry
    from app.services import market_briefing as mb
    from app.services import market_chart as mc

    end = week_start + timedelta(days=6)
    span = mc._span(week_start)
    facts = mb.build_facts(conn, market, week_start, end)
    incumbents = _incumbents(conn, market["id"])
    previous = conn.execute(text("""
        SELECT open_roles FROM bw_market_weekly_posts
        WHERE market_id = :m AND week_start < :w AND open_roles IS NOT NULL
        ORDER BY week_start DESC LIMIT 1
    """), {"m": market["id"], "w": week_start}).scalar()
    hiring, open_roles = hiring_line(conn, market["id"], previous)
    movers = movers_line(market, mc.chart(conn, market["id"]))
    acquisitions = int((facts.get("announcements_by_kind") or {}).get("acquisition", 0))
    registry = (facts.get("registry") or {}).get("watching")
    vendors = _vendor_names(conn, market["id"])
    conn.commit()  # the model call below can outlast an idle transaction

    from app.model_tiers import default_model
    model = POST_MODEL or default_model("standard")
    bullets: List[Dict[str, Any]] = []
    summary = None
    if facts["announcements"] or facts["coverage"]:
        messages = [
            {"role": "system",
             "content": "You write short factual LinkedIn posts from supplied "
                        "evidence. You never add a fact that is not in the evidence."},
            {"role": "user", "content": build_prompt(market, span, facts, incumbents)},
        ]
        content = await _generate_report_with_retry(
            LiteLLMModel.get_instance(model), messages,
            label=f"weekly post {market['name']} {week_start}")
        bullets, summary = parse(content, facts["citation_index"], vendors)

    cfg = market.get("config") or {}
    if isinstance(cfg, str):
        cfg = json.loads(cfg or "{}")
    url = ((cfg.get("chart") or {}).get("post_url") or "")
    site = re.sub(r"^https?://", "", url).rstrip("/")

    lines = [f"{market['name']}, last week:"]
    lines += [f"  - {b['text']}" for b in bullets]
    if movers:
        lines.append(f"  - {movers}")
    if hiring:
        lines.append(f"  - {hiring}")
    closing = []
    if acquisitions == 0:
        closing.append("No acquisitions this week.")
    if summary and bullets:
        closing.append(summary)
    if closing:
        lines.append("  " + " ".join(closing))
    lines.append("")
    lines.append((f"Tracking {registry} vendors based on scale and momentum. "
                  if registry else "") + "Full market report is free to read:"
                 + (f"\n{site}" if site else ""))
    return {"content": "\n".join(lines), "bullets": bullets, "summary": summary,
            "open_roles": open_roles, "model": model, "span": span,
            "week_start": week_start}


def store(conn, market_id: int, post: Dict[str, Any]) -> int:
    row = conn.execute(text("""
        INSERT INTO bw_market_weekly_posts
            (market_id, week_start, content, sources, open_roles, model_used)
        VALUES (:m, :w, :c, CAST(:s AS JSONB), :o, :model)
        ON CONFLICT (market_id, week_start) DO UPDATE SET
            content = EXCLUDED.content, sources = EXCLUDED.sources,
            open_roles = EXCLUDED.open_roles, model_used = EXCLUDED.model_used,
            created_at = NOW()
        RETURNING id
    """), {"m": market_id, "w": post["week_start"], "c": post["content"],
           "s": json.dumps(post["bullets"], default=str),
           "o": post["open_roles"], "model": post["model"]}).scalar()
    conn.commit()
    return row


def _editors() -> List[str]:
    return [a.strip() for a in (os.getenv("MARKET_TRIAL_NOTIFY_EMAIL") or "").split(",")
            if a.strip()]


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def mail(market: Dict[str, Any], post: Dict[str, Any]) -> bool:
    from app.services.email_service import EmailService

    to = _editors()
    svc = EmailService()
    if not to or not svc.is_available():
        logger.warning("market %s: weekly post not mailed (no editors or no mail)",
                       market["id"])
        return False
    src_lines, src_html = [], []
    for i, b in enumerate(post["bullets"], 1):
        src_lines.append(f"{i}. {b['text']}")
        src_html.append(f"<p><strong>{i}.</strong> {_esc(b['text'])}</p><ul>")
        for s in b["sources"]:
            label = s.get("vendor") or s.get("source") or ""
            src_lines.append(f"   [{s['id']}] {label}: {s.get('title')}\n   {s.get('uri')}")
            src_html.append(f'<li>{_esc(label)}: <a href="{_esc(s.get("uri"))}">'
                            f'{_esc(s.get("title"))}</a></li>')
        src_html.append("</ul>")
    note = ("This week's LinkedIn post, ready to paste. Tag the vendors by hand. "
            "The movers, open roles and acquisitions lines are written from the "
            "data; the other bullets were written by an AI model from the facts "
            "listed under the post.")
    text_body = (note + "\n\n---\n\n" + post["content"] + "\n\n---\nSources\n\n"
                 + "\n".join(src_lines))
    html_body = (f"<p>{_esc(note)}</p><hr><pre style=\"white-space:pre-wrap;"
                 f"font-family:inherit\">{_esc(post['content'])}</pre><hr>"
                 "<h3>Sources</h3>" + "".join(src_html))
    subject = f"LinkedIn post: {market['name']}, week of {post['span']}"
    return svc.send_email(to, subject, html_body, text_body, ai_generated=True)


async def send(conn, market: Dict[str, Any], week_start: date) -> bool:
    """Compose, store and mail the week's post once. A week already mailed
    is left alone."""
    sent = conn.execute(text("""
        SELECT sent_at FROM bw_market_weekly_posts
        WHERE market_id = :m AND week_start = :w
    """), {"m": market["id"], "w": week_start}).scalar()
    conn.commit()
    if sent is not None:
        return False
    post = await compose(conn, market, week_start)
    row = store(conn, market["id"], post)
    if not mail(market, post):
        return False
    conn.execute(text("UPDATE bw_market_weekly_posts SET sent_at = NOW() WHERE id = :i"),
                 {"i": row})
    conn.commit()
    return True
