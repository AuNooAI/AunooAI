"""The monthly market briefing: assembled facts, model prose on top.

Two stages, and the split is the point. Stage one collects the period's
evidence from stored rows with no model involved. Stage two asks a model to
write narrative **around** that block, with no licence to introduce a fact that
is not in it. So no number in a briefing can be invented, and because the facts
are stored alongside the prose, that claim is checkable afterwards rather than
merely asserted.

Any calendar period — day, week, month or year — because the two-stage split
already made the length a non-issue: a thin period falls under
MIN_ITEMS_FOR_PROSE and gets the quiet fallback below instead of a model
padding out eight items to sound like sixty.

Almost none of the machinery here is new. The tone contract, the date
directive, the reader-organisation persona, the empty-response retry and the
outbound lint all already exist and are used by every other prose surface in
this codebase.
"""

import json
import os
import logging
import re
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from app.utils.timestamps import submission_stamp

logger = logging.getLogger(__name__)

# Below this the period did not contain enough to write about. The briefing
# says so instead of padding — 800 words about a quiet month is worse than one
# sentence saying the month was quiet.
MIN_ITEMS_FOR_PROSE = 6

# A day or a week rarely gets near this; a year can clear it by a hundredfold.
# Listing every item regardless of period length would make a year's prompt
# scale with the market's whole history instead of with what a reader can
# use, so each section is capped at the same rough size a normal month
# already produces — the model sees the most recent MAX_FACTS_PER_SECTION of
# each, and the facts block says so when the true count is bigger.
MAX_FACTS_PER_SECTION = 80

# Kimi K2.5 writes the briefing. The old default, gpt-5.4-mini, is a yaml
# alias that lands on Bedrock Haiku 4.5 on every tenant; kimi beat Haiku on
# the enrichment benchmark (07-20) at about half the price, and the project
# rule is to avoid Haiku unless nothing cheaper does the job. Override per
# tenant with MARKET_BRIEFING_MODEL.
DEFAULT_MODEL = os.getenv("MARKET_BRIEFING_MODEL", "bedrock-kimi-k2-5")


def month_bounds(year: int, month: int) -> Tuple[date, date, str]:
    """``(first, last, 'YYYY-MM')`` for a calendar month."""
    last = monthrange(year, month)[1]
    return (date(year, month, 1), date(year, month, last),
            f"{year:04d}-{month:02d}")


def previous_month(today: Optional[date] = None) -> Tuple[int, int]:
    """The last **complete** month.

    A briefing about the month in progress is a briefing that will be wrong by
    the end of it.
    """
    today = today or datetime.now(timezone.utc).date()
    return (today.year - 1, 12) if today.month == 1 else (today.year,
                                                          today.month - 1)


def period_bounds(kind: str, ref: date) -> Tuple[date, date, str]:
    """``(first, last, label)`` for the ``kind`` period containing ``ref``.

    ``ref`` picks *which* day/week/month/year — a UI picker already resolved
    that choice to one date before calling this. The label doubles as the
    row's dedup key (``bw_market_briefings`` is unique on
    ``(market_id, period_label)``), so it has to be stable for the same
    period and distinct across kinds: a day, its month and its year never
    collide because ``"2026-08-22"``, ``"2026-08"`` and ``"2026"`` are all
    different strings.
    """
    if kind == "day":
        return ref, ref, ref.isoformat()
    if kind == "week":
        start = ref - timedelta(days=ref.weekday())  # Monday
        end = start + timedelta(days=6)               # Sunday
        return start, end, f"Week of {start.isoformat()}"
    if kind == "year":
        return date(ref.year, 1, 1), date(ref.year, 12, 31), str(ref.year)
    if kind == "month":
        return month_bounds(ref.year, ref.month)
    raise ValueError(f"unknown period kind: {kind!r}")


def default_ref(kind: str, today: Optional[date] = None) -> date:
    """A date inside the last **complete** period of ``kind``.

    Used only when a caller does not name a specific period — the picker in
    the UI otherwise always sends one.
    """
    today = today or datetime.now(timezone.utc).date()
    if kind == "day":
        return today - timedelta(days=1)
    if kind == "week":
        this_monday = today - timedelta(days=today.weekday())
        return this_monday - timedelta(days=7)
    if kind == "year":
        return date(today.year - 1, 7, 1)
    year, month = previous_month(today)
    return date(year, month, 1)


# ---------------------------------------------------------------------------
# Stage 1 — the facts, from stored rows only
# ---------------------------------------------------------------------------

def build_facts(conn, market: Dict[str, Any], start: date, end: date
                ) -> Dict[str, Any]:
    """Everything the briefing is allowed to say, drawn from the database.

    ``build_brief()`` already assembles the standing parts — coverage, the
    timeline's events, headcount movement, open questions — so this adds the
    period-specific evidence rather than duplicating it.
    """
    from app.services import market_publish as mp

    market_id = market["id"]
    bounds = {"m": market_id, "d0": start.isoformat(),
              "d1": end.isoformat() + "T23:59:59"}

    # Announcements: vendor posts the review pass judged to state a fact.
    # DISTINCT ON the uri — bw_article_categories is keyed on category, so a
    # post filed under three categories would appear three times.
    announcements = [dict(r) for r in conn.execute(text("""
        SELECT * FROM (
            SELECT DISTINCT ON (a.uri)
                   a.uri, a.title, a.publication_date, b.display_name AS vendor,
                   ma.review_kind AS kind, ma.review_reason AS reason
            FROM bw_market_articles ma
            JOIN articles a ON a.uri = ma.article_uri
            JOIN bw_article_categories bac ON bac.article_uri = a.uri
            JOIN bw_brands b ON b.id = bac.brand_id
            JOIN bw_market_brands mb ON mb.brand_id = b.id
                                     AND mb.market_id = :m
            WHERE ma.market_id = :m AND ma.review_verdict = 'signal'
              AND a.publication_date >= :d0 AND a.publication_date <= :d1
            ORDER BY a.uri, a.publication_date DESC
        ) x ORDER BY x.publication_date DESC
    """), bounds).mappings().all()]

    # Third-party coverage: everything matched that is not a vendor's own post.
    coverage = [dict(r) for r in conn.execute(text("""
        SELECT DISTINCT ON (a.uri)
               a.uri, a.title, a.news_source, a.publication_date,
               ma.matched_terms
        FROM bw_market_articles ma
        JOIN articles a ON a.uri = ma.article_uri
        WHERE ma.market_id = :m
          AND COALESCE(a.bias_source, '') <> 'vendor:linkedin'
          AND a.publication_date >= :d0 AND a.publication_date <= :d1
        ORDER BY a.uri, a.publication_date DESC
    """), bounds).mappings().all()]

    brief = mp.build_brief(conn, market, days=max(
        1, (datetime.now(timezone.utc).date() - start).days))

    hiring = [dict(r) for r in conn.execute(text("""
        SELECT b.display_name AS vendor, COUNT(DISTINCT s.provider_item_id) AS openings
        FROM bw_vendor_snapshots s
        JOIN bw_market_brands mb ON mb.brand_id = s.brand_id
                                 AND mb.market_id = :m AND mb.role <> 'excluded'
        JOIN bw_brands b ON b.id = s.brand_id
        WHERE s.snapshot_type = 'job_posting'
        GROUP BY 1 ORDER BY 2 DESC
    """), {"m": market_id}).mappings().all()]

    entrants = [dict(r) for r in conn.execute(text("""
        SELECT b.display_name AS vendor,
               mb.baseline->>'founded_year' AS founded,
               mb.baseline->'funding_baseline'->>'total_musd' AS raised
        FROM bw_market_brands mb
        JOIN bw_brands b ON b.id = mb.brand_id
        WHERE mb.market_id = :m AND mb.role <> 'excluded'
          AND mb.created_at >= :d0 AND mb.created_at <= :d1
        ORDER BY b.display_name
    """), bounds).mappings().all()]

    by_kind: Dict[str, int] = {}
    for row in announcements:
        key = row.get("kind") or "other"
        by_kind[key] = by_kind.get(key, 0) + 1

    # The true counts, before either list is capped for the prompt — a year
    # can clear MAX_FACTS_PER_SECTION by a hundredfold, and "quiet" plus the
    # "N items" a reader sees must describe the whole period, not the sample
    # the model was shown.
    announcements_total = len(announcements)
    coverage_total = len(coverage)
    # Both queries already order newest-first, so keeping the first N keeps
    # the most recent — the ones a monthly-scale briefing would emphasise
    # anyway.
    announcements = announcements[:MAX_FACTS_PER_SECTION]
    coverage = coverage[:MAX_FACTS_PER_SECTION]

    # Stable citation IDs, one per fact, in the order the model will see
    # them. Scoped to announcements/coverage — the only sections that are
    # literally one article row each, so an ID resolves to exactly one URI.
    citation_index: Dict[str, Dict[str, Any]] = {}
    for i, a in enumerate(announcements, 1):
        a["cite_id"] = f"A{i}"
        citation_index[a["cite_id"]] = {
            "uri": a["uri"], "title": a["title"], "vendor": a["vendor"]}
    for i, c in enumerate(coverage, 1):
        c["cite_id"] = f"C{i}"
        citation_index[c["cite_id"]] = {
            "uri": c["uri"], "title": c["title"], "source": c.get("news_source")}

    return {
        "market": market["name"],
        "question": market.get("question"),
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "announcements": announcements,
        "announcements_total": announcements_total,
        "announcements_by_kind": by_kind,
        "coverage": coverage,
        "coverage_total": coverage_total,
        "hiring": hiring,
        "new_entrants": entrants,
        "headcount_movers": brief.get("headcount_movers", [])[:8],
        "events": brief.get("events", []),
        "registry": brief.get("coverage", {}),
        "open_questions": brief.get("open_questions", []),
        "standing_summary": brief.get("standing_summary"),
        "item_count": announcements_total + coverage_total,
        "citation_index": citation_index,
    }


# ---------------------------------------------------------------------------
# Stage 2 — prose, bounded by the facts
# ---------------------------------------------------------------------------

def _render_facts(facts: Dict[str, Any]) -> str:
    """The facts block as the model sees it."""
    lines: List[str] = []

    reg = facts.get("registry") or {}
    lines.append(
        f"REGISTRY: {reg.get('watching', '?')} of {reg.get('registry', '?')} "
        f"vendors are being collected for.")

    if facts["announcements"]:
        total = facts.get("announcements_total", len(facts["announcements"]))
        shown = (f"{len(facts['announcements'])} of {total}, most recent first"
                 if total > len(facts["announcements"]) else str(total))
        lines.append(f"\nVENDOR ANNOUNCEMENTS ({shown}). "
                     "Each is a claim the vendor made about itself on LinkedIn, "
                     "not an independently confirmed fact:")
        for a in facts["announcements"]:
            date_part = (a.get("publication_date") or "")[:10]
            lines.append(f"- [{a.get('cite_id')}] [{date_part}] {a['vendor']} "
                         f"({a.get('kind')}): {a['title']} — {a.get('reason') or ''}")

    if facts["coverage"]:
        total = facts.get("coverage_total", len(facts["coverage"]))
        shown = (f"{len(facts['coverage'])} of {total}, most recent first"
                 if total > len(facts["coverage"]) else str(total))
        lines.append(f"\nTHIRD-PARTY COVERAGE ({shown}):")
        for c in facts["coverage"]:
            date_part = (c.get("publication_date") or "")[:10]
            lines.append(f"- [{c.get('cite_id')}] [{date_part}] "
                         f"{c.get('news_source') or 'unknown'}: {c['title']}")

    if facts["new_entrants"]:
        lines.append("\nNEW TO THE REGISTRY THIS PERIOD:")
        for e in facts["new_entrants"]:
            lines.append(f"- {e['vendor']} (founded {e.get('founded') or '?'})")

    if facts["headcount_movers"]:
        # Two LinkedIn readings, each with its own date. The dates are given to
        # the model because a +1 over two days and a +1 over four months are
        # different facts and it cannot tell them apart otherwise.
        lines.append("\nHEADCOUNT MOVEMENT (LinkedIn headcount on two dates):")
        for m in facts["headcount_movers"]:
            lines.append(f"- {m['vendor']}: {m.get('previous')} on "
                         f"{str(m.get('previous_at'))[:10]} -> {m.get('latest')} on "
                         f"{str(m.get('latest_at'))[:10]} ({m.get('pct')}%)")

    if facts["hiring"]:
        top = ", ".join(f"{h['vendor']} {h['openings']}"
                        for h in facts["hiring"][:8])
        lines.append(f"\nOPEN JOB LISTINGS: {top}")

    if facts["open_questions"]:
        lines.append("\nOPEN DATA-QUALITY QUESTIONS: " + ", ".join(
            f"{q['n']} {q['kind']} ({q['severity']})"
            for q in facts["open_questions"]))

    return "\n".join(lines)


def build_prompt(facts: Dict[str, Any], period_label: str) -> str:
    """The instruction, with the tone and date policy the rest of the product uses."""
    from app.routes.vector_routes import _report_date_directive
    from app.services.report_style import CLINICAL_STYLE

    return f"""Write the market briefing for {facts['market']}, covering {period_label}.

The market's question: {facts.get('question') or facts['market']}

Use ONLY the facts below. Do not add companies, figures, funding rounds, dates
or events that are not in them. If something is not in the facts, it is not in
the briefing. Do not estimate, extrapolate or round a number into a different
number.

Say where each claim comes from and how well corroborated it is. A vendor's own
post is a vendor claim, not an established fact about the market — write "X
said it has..." rather than "X has...". A trade-press article is a single
source unless two sources say the same thing.

A vendor with no facts in a section was not observed doing that thing during
this period — it is not evidence the vendor did nothing. Write "no {{X}} was
observed for Y" rather than "Y did not {{X}}" or "Y has no {{X}}", and never
turn a missing observation into a claim about the vendor's actual state.

Only the VENDOR ANNOUNCEMENTS and THIRD-PARTY COVERAGE facts below carry a
citation ID, each in the exact form [A3] or [C7] — a single capital letter
followed by digits, nothing else inside the brackets. When a sentence you
write is supported by one specific fact from either of those two sections,
put its exact ID immediately after the sentence, copied verbatim from the
list. The ID follows the sentence's full stop, never leads the sentence —
the fact lines below start with their ID only so you can find it. Right:
"Arambh Labs launched Armor Detect, a detection engineering agent. [A2]"
Wrong: "[A2] Arambh Labs launched Armor Detect, a detection engineering
agent." Never invent an ID, never cite the same fact for an unrelated claim,
and never write a bracket for anything else — HEADCOUNT, OPEN JOB LISTINGS,
NEW TO THE REGISTRY and every other section have no IDs and get no brackets
at all, not even a descriptive one like [headcount data]. A sentence drawn
from one of those sections, or general framing not drawn from one specific
fact, needs no citation and no bracket of any kind.

Sections:
1. What happened — the period's substantive developments, grouped by what kind
   of thing they are, not vendor by vendor.
2. What it suggests about the market — only what these facts support.
3. What we still do not know — the gaps, including where our own coverage is
   thin.

Do not write an introduction explaining what a market briefing is. Do not end
with a summary of what you just said. If the period was quiet, say so in a
sentence and stop.
{CLINICAL_STYLE}{_report_date_directive()}

FACTS:
{_render_facts(facts)}
"""


def fallback_briefing(facts: Dict[str, Any], period_label: str) -> str:
    """A deterministic briefing, for when every model attempt came back empty.

    Bedrock returns an empty completion roughly one run in eight, and a monthly
    job that silently produced nothing would go unnoticed for a month. This is
    plainly the assembled facts rather than an imitation of written prose.
    """
    out = [f"# {facts['market']} — {period_label}", "",
           "_Assembled from stored records. The written briefing could not be "
           "generated, so this is the evidence without the narrative._", ""]

    if facts["announcements"]:
        total = facts.get("announcements_total", len(facts["announcements"]))
        out.append(f"## Vendor announcements ({total})")
        out.append("")
        out.append("Each is a claim the vendor made about itself."
                    + (f" Showing the most recent {len(facts['announcements'])}."
                       if total > len(facts["announcements"]) else ""))
        out.append("")
        for a in facts["announcements"]:
            out.append(f"- **{a['vendor']}** ({a.get('kind')}): {a['title']}")
        out.append("")

    if facts["coverage"]:
        total = facts.get("coverage_total", len(facts["coverage"]))
        out.append(f"## Third-party coverage ({total})")
        out.append("")
        for c in facts["coverage"]:
            out.append(f"- {c['title']} — {c.get('news_source') or 'unknown'}")
        out.append("")

    if facts["open_questions"]:
        out.append("## Open data-quality questions")
        out.append("")
        for q in facts["open_questions"]:
            out.append(f"- {q['n']} {q['kind']} ({q['severity']})")

    return "\n".join(out)


def quiet_briefing(facts: Dict[str, Any], period_label: str) -> str:
    """What a month with almost nothing in it gets."""
    def _plural(n: int, one: str, many: str) -> str:
        return f"{n} {one if n == 1 else many}"

    counts = (_plural(len(facts["announcements"]), "vendor announcement",
                      "vendor announcements")
              + " and "
              + _plural(len(facts["coverage"]), "article", "articles"))
    return (f"# {facts['market']} — {period_label}\n\n"
            f"The period was quiet: {counts}. That is too little to draw a "
            "conclusion from, so this briefing records the count and stops.\n")


# One citation ID, used to pull the IDs back out of a bracket that holds
# several.
_CITE_ID_RE = re.compile(r"[AC]\d+")

# A citation bracket: one ID, or several separated by commas. The prompt asks
# for one ID per bracket, but a model that has two facts for a sentence writes
# "[A5, A11]" anyway, and that used to fall through to _STRAY_BRACKET_RE and
# take both references down with it (three brackets, eight valid IDs, in the
# 2026-08-17 SOC automation weekly).
_CITATION_GROUP = r"[AC]\d+(?:\s*,\s*[AC]\d+)*"
_CITATION_RE = re.compile(r"\[\s*(" + _CITATION_GROUP + r")\s*\]")

# A bracket the model wrote that is not a real citation ID — e.g.
# "[headcount data]" instead of an [A3]/[C7] it was told those two sections
# alone carry. The negative lookahead excludes anything shaped like a real
# ID so this never touches a valid [A3] or [A5, A11]; the lookahead on "("
# excludes a markdown link, in case one is ever written even though this
# renderer doesn't support that syntax.
_STRAY_BRACKET_RE = re.compile(
    r"\[(?!\s*" + _CITATION_GROUP + r"\s*\])[^\[\]\n]{1,40}\](?!\()")


def _citation_garbage(content: str, facts: Dict[str, Any]) -> bool:
    """True when most bracket-shaped tokens in the prose are not real IDs.

    Two ways this fires: most [A3]-shaped tokens don't resolve (the model
    copied the ID pattern wrong), or the model invented its own
    descriptive-bracket habit instead of using IDs at all. Either way it
    invented the bracket *convention* rather than following the one it was
    given, which is worth falling back for rather than shipping brackets a
    reader cannot make sense of.
    """
    index = facts.get("citation_index") or {}
    tokens = [cid for group in _CITATION_RE.findall(content)
              for cid in _CITE_ID_RE.findall(group)]
    strays = _STRAY_BRACKET_RE.findall(content)
    if len(strays) >= 3 and len(strays) > len(tokens):
        return True
    if len(tokens) < 3:
        return False
    bad = sum(1 for t in tokens if t not in index)
    return bad / len(tokens) > 0.5


# One or more citation brackets at the start of a line, after any markdown
# bullet or heading marker. Only the line start is unambiguous: mid-paragraph,
# "X. [A3] Y." is the correct form (A3 cites X), so a bracket after a full
# stop is never touched.
_LEADING_CITES_RE = re.compile(
    r"(?P<lead>^[ \t]*(?:[-*#>]+[ \t]+)?)"
    r"(?P<cites>(?:\[\s*" + _CITATION_GROUP + r"\s*\][ \t]*)+)"
    r"(?=\S)",
    re.MULTILINE)
# Where the sentence those brackets belong to ends: a terminator followed by
# whitespace or the end of the line. A closing quote after the terminator
# stays with the sentence.
_SENTENCE_END_RE = re.compile(r"[.!?][\"'”’)]*(?=[ \t]|$)", re.MULTILINE)


def move_leading_citations(content: str) -> str:
    """Move a citation that leads its sentence to the end of that sentence.

    The prompt asks for the ID after the sentence, and the fact list shows
    each ID at the front of its line; Kimi copies the fact-list position
    ("[A2] Arambh Labs launched…") often enough that the report reads as a
    numbered list. Every ID still resolves either way, so this is a layout
    fix, and it only moves a bracket when the sentence has a visible end on
    the same line — a heading or a fragment is left alone. A bracket that
    opens a sentence mid-paragraph is left where it is, because from the
    text alone it is indistinguishable from one closing the sentence before.
    """
    out: List[str] = []
    pos = 0
    for m in _LEADING_CITES_RE.finditer(content):
        if m.start() < pos:
            continue
        line_end = content.find("\n", m.end())
        if line_end == -1:
            line_end = len(content)
        end = _SENTENCE_END_RE.search(content, m.end(), line_end)
        if not end:
            continue
        ids = [f"[{cid}]" for cid in _CITE_ID_RE.findall(m.group("cites"))]
        out.append(content[pos:m.start()])
        out.append(m.group("lead"))
        out.append(content[m.end():end.end()])
        out.append(" " + " ".join(ids))
        pos = end.end()
    out.append(content[pos:])
    return "".join(out)


def resolve_citations(content: str, facts: Dict[str, Any]
                      ) -> Tuple[str, List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Validate inline [A3]/[C7] citations and append a References section.

    Returns the content with any hallucinated ID stripped in place, the
    ordered list of resolved references (built straight from
    ``facts["citation_index"]`` — the same data the model was shown, so
    there's no second lookup to disagree with it), and a lint list of any
    hallucinated IDs that were dropped.
    """
    index = facts.get("citation_index") or {}
    seen: List[str] = []
    references: List[Dict[str, Any]] = []
    dropped: List[Dict[str, Any]] = []

    def _replace(match: "re.Match") -> str:
        cite_ids = _CITE_ID_RE.findall(match.group(1))
        kept: List[str] = []
        for cite_id in cite_ids:
            if cite_id not in index:
                logger.warning("dropped hallucinated citation %s", cite_id)
                dropped.append({"check": "citation",
                                "detail": f"dropped hallucinated citation [{cite_id}]"})
                continue
            kept.append(cite_id)
            if cite_id not in seen:
                seen.append(cite_id)
                references.append({"cite_id": cite_id, **index[cite_id]})
        # Every ID in the bracket was invented — drop the bracket with them.
        if not kept:
            return ""
        return "[" + ", ".join(kept) + "]"

    resolved = _CITATION_RE.sub(_replace, move_leading_citations(content))

    def _strip_stray(match: "re.Match") -> str:
        token = match.group(0)
        logger.warning("dropped non-citation bracket %s", token)
        dropped.append({"check": "citation",
                        "detail": f"dropped non-citation bracket {token}"})
        return ""

    resolved = _STRAY_BRACKET_RE.sub(_strip_stray, resolved)
    # A stripped bracket leaves "sentence ." behind when it sat right before
    # the period — tidy the space rather than ship a visible gap.
    resolved = re.sub(r" +([.,;:])", r"\1", resolved)

    if references:
        lines = ["", "## References", ""]
        for ref in references:
            byline = ref.get("vendor") or ref.get("source") or ""
            lines.append(f"[{ref['cite_id']}] {byline} — \"{ref['title']}\" "
                         f"— {ref['uri']}")
        resolved = resolved.rstrip() + "\n" + "\n".join(lines) + "\n"

    return resolved, references, dropped


async def generate(conn, market: Dict[str, Any], *, start: date, end: date,
                   period_label: str, model: Optional[str] = None,
                   store: bool = True) -> Dict[str, Any]:
    """Build the facts, write the prose, store both.

    Caller resolves the period first — ``period_bounds()`` for a named
    day/week/month/year, or any other ``(start, end, label)`` triple.
    """
    from app.routes.vector_routes import (
        _generate_report_with_retry, _org_persona_report_prefix,
    )
    from app.ai_models import LiteLLMModel

    facts = build_facts(conn, market, start, end)
    model = model or DEFAULT_MODEL

    generation = "generated"
    if facts["item_count"] < MIN_ITEMS_FOR_PROSE:
        content = quiet_briefing(facts, period_label)
        generation = "fallback"
    else:
        prompt = build_prompt(facts, period_label)
        try:
            from app.database import get_database_instance
            persona = _org_persona_report_prefix(get_database_instance())
        except Exception:  # noqa: BLE001 — a briefing without the persona is
            persona = ""    # still a briefing
        messages = [
            {"role": "system",
             "content": ("You write market briefings from supplied evidence. "
                         "You never introduce a fact that is not in the "
                         "evidence." + (persona or ""))},
            {"role": "user", "content": prompt},
        ]
        content = await _generate_report_with_retry(
            LiteLLMModel.get_instance(model), messages,
            label=f"market briefing {facts['market']} {period_label}")
        if not content or _citation_garbage(content, facts):
            content = fallback_briefing(facts, period_label)
            generation = "fallback"

    citation_lint: List[Dict[str, Any]] = []
    if generation == "generated":
        content, references, citation_lint = resolve_citations(content, facts)
        facts["references"] = references

    try:
        from app.services.report_lint import lint_outbound
        lint = lint_outbound(content, kind="html",
                             context=f"market briefing {period_label}") or []
    except Exception as exc:  # noqa: BLE001
        logger.debug("briefing lint failed: %s", exc)
        lint = []
    lint = citation_lint + lint

    uris = ([a["uri"] for a in facts["announcements"]]
            + [c["uri"] for c in facts["coverage"]])

    result = {
        "market_id": market["id"], "period_label": period_label,
        "period_start": start.isoformat(), "period_end": end.isoformat(),
        "title": f"{market['name']} — {period_label}",
        "content": content, "generation": generation, "model": model,
        "facts": facts, "lint": lint, "article_uris": uris,
        "item_count": facts["item_count"], "stored": False,
    }
    if not store:
        return result

    row = conn.execute(text("""
        INSERT INTO bw_market_briefings
            (market_id, period_start, period_end, period_label, title, facts,
             report_content, article_uris, model_used, generation, lint)
        VALUES (:m, :d0, :d1, :label, :title, CAST(:facts AS JSONB), :content,
                :uris, :model, :generation, CAST(:lint AS JSONB))
        ON CONFLICT (market_id, period_label) DO UPDATE SET
            facts = EXCLUDED.facts, report_content = EXCLUDED.report_content,
            article_uris = EXCLUDED.article_uris,
            model_used = EXCLUDED.model_used,
            generation = EXCLUDED.generation, lint = EXCLUDED.lint,
            -- A regenerated briefing goes back to draft: approval was given to
            -- the text somebody read, not to this one.
            status = 'draft', updated_at = NOW()
        RETURNING id
    """), {"m": market["id"], "d0": start, "d1": end, "label": period_label,
           "title": result["title"],
           "facts": json.dumps(facts, default=str),
           "content": content, "uris": uris, "model": model,
           "generation": generation,
           "lint": json.dumps(lint, default=str)}).scalar()
    # Back to draft means out of the feed until somebody approves this text.
    _withdraw_from_feed(conn, market["id"], row)
    conn.commit()
    result["id"] = row
    result["stored"] = True
    return result


KINDS = ("briefing", "analysis", "note")
KIND_LABELS = {"briefing": "Briefing", "analysis": "Analysis", "note": "Note"}


def listing(conn, market_id: int, limit: int = 24) -> List[Dict[str, Any]]:
    return [dict(r) for r in conn.execute(text("""
        SELECT id, period_label, period_start, period_end, title, status,
               generation, model_used, created_at, updated_at,
               kind, author, published_at,
               ARRAY_LENGTH(article_uris, 1) AS sources
        FROM bw_market_briefings WHERE market_id = :m
        ORDER BY period_start DESC, id DESC LIMIT :lim
    """), {"m": market_id, "lim": limit}).mappings().all()]


def create_piece(conn, market: Dict[str, Any], *, kind: str, title: str,
                 content: str, author: Optional[str] = None,
                 saved_by: Optional[str] = None) -> Dict[str, Any]:
    """A piece a person wrote — an analysis or a note — as a draft.

    Stored beside the briefings so it gets the same approval, revision and
    feed handling. ``generation = 'written'`` says no model drafted it; the
    period is the day it was written, and the period label carries the
    kind and the moment so the (market, label) uniqueness holds.
    """
    if kind not in ("analysis", "note"):
        raise ValueError(f"unknown kind: {kind}")
    title = (title or "").strip()[:300]
    content = (content or "").replace("\r\n", "\n").strip()
    if not title or not content:
        raise ValueError("A piece needs a title and its text")
    now = datetime.now(timezone.utc)
    label = f"{KIND_LABELS[kind]} · {now.strftime('%Y-%m-%d %H:%M:%S')}"
    row_id = conn.execute(text("""
        INSERT INTO bw_market_briefings
            (market_id, period_start, period_end, period_label, title, facts,
             report_content, article_uris, model_used, generation, lint,
             kind, author)
        VALUES (:m, :d, :d, :label, :t, '{}'::jsonb, :c, '{}'::text[], NULL,
                'written', '[]'::jsonb, :k, :a)
        RETURNING id
    """), {"m": market["id"], "d": now.date(), "label": label, "t": title,
           "c": content, "k": kind, "a": (author or saved_by or "").strip()[:120] or None}).scalar()
    conn.commit()
    return get(conn, market["id"], int(row_id))


def get(conn, market_id: int, briefing_id: int) -> Optional[Dict[str, Any]]:
    row = conn.execute(text("""
        SELECT * FROM bw_market_briefings
        WHERE market_id = :m AND id = :i
    """), {"m": market_id, "i": briefing_id}).mappings().first()
    return dict(row) if row else None


def set_status(conn, market_id: int, briefing_id: int, status: str) -> bool:
    if status not in ("draft", "approved", "rejected"):
        raise ValueError(f"unknown status: {status}")
    # The first approval is the publication; a later re-approval keeps it.
    updated = conn.execute(text("""
        UPDATE bw_market_briefings
           SET status = :s, updated_at = NOW(),
               published_at = CASE WHEN :s = 'approved'
                                   THEN COALESCE(published_at, NOW())
                                   ELSE published_at END
        WHERE market_id = :m AND id = :i
    """), {"s": status, "m": market_id, "i": briefing_id}).rowcount
    conn.commit()
    return bool(updated)


# ---------------------------------------------------------------------------
# Editing by hand
# ---------------------------------------------------------------------------
#
# The model writes the first draft; a person may rewrite it. The text that
# was there before each save goes to ``bw_market_briefing_revisions``, so the
# model's original and every edit survive and any of them can be restored.
# An edited briefing is marked ``generation = 'edited'`` — a reader can then
# tell a model's sentence from a person's — and if it is approved, its feed
# item is refreshed so the feed summary follows the new text.

def _snapshot(conn, briefing: Dict[str, Any], *, reason: str,
              saved_by: Optional[str]) -> int:
    return int(conn.execute(text("""
        INSERT INTO bw_market_briefing_revisions
            (briefing_id, market_id, title, report_content, generation, reason, saved_by)
        VALUES (:b, :m, :t, :c, :g, :r, :by)
        RETURNING id
    """), {"b": briefing["id"], "m": briefing["market_id"], "t": briefing.get("title"),
           "c": briefing.get("report_content") or "", "g": briefing.get("generation"),
           "r": reason, "by": saved_by}).scalar())


def save_edit(conn, market: Dict[str, Any], briefing_id: int, *, content: str,
              title: Optional[str] = None, saved_by: Optional[str] = None,
              reason: str = "edit", generation: str = "edited"
              ) -> Optional[Dict[str, Any]]:
    """Replace the briefing's text with a person's, keeping what was there.

    Returns the updated briefing, or None if it does not exist. The lint is
    rerun on the new text (advisory, never blocking); citations are left as
    written, because a person editing is the reviewer.
    """
    briefing = get(conn, market["id"], briefing_id)
    if not briefing:
        return None
    content = (content or "").replace("\r\n", "\n").strip()
    if not content:
        raise ValueError("The briefing text cannot be empty")
    if content == (briefing.get("report_content") or "").strip() and \
            (title is None or title == briefing.get("title")):
        return briefing
    _snapshot(conn, briefing, reason="before " + reason, saved_by=saved_by)
    try:
        from app.services.report_lint import lint_outbound
        lint = lint_outbound(content, kind="html", context="briefing edit") or []
    except Exception as exc:  # noqa: BLE001 — advisory
        logger.debug("briefing edit lint failed: %s", exc)
        lint = []
    conn.execute(text("""
        UPDATE bw_market_briefings
           SET report_content = :c, title = COALESCE(:t, title),
               generation = :g, lint = CAST(:l AS JSONB), updated_at = NOW()
         WHERE market_id = :m AND id = :i
    """), {"c": content, "t": (title or "").strip()[:300] or None,
           # A person's own piece stays "written" after a person's edit.
           "g": generation if generation in ("generated", "fallback", "edited", "written")
                else ("written" if briefing.get("generation") == "written" else "edited"),
           "l": json.dumps(lint), "m": market["id"], "i": briefing_id})
    conn.commit()
    if briefing.get("status") == "approved":
        sync_feed_entry(conn, market, briefing_id)
    return get(conn, market["id"], briefing_id)


def revisions(conn, market_id: int, briefing_id: int) -> List[Dict[str, Any]]:
    """Every previous text, newest first, without the text itself."""
    return [dict(r) for r in conn.execute(text("""
        SELECT id, title, generation, reason, saved_by, saved_at,
               LENGTH(report_content) AS length
          FROM bw_market_briefing_revisions
         WHERE market_id = :m AND briefing_id = :b
         ORDER BY saved_at DESC, id DESC
    """), {"m": market_id, "b": briefing_id}).mappings().all()]


def revision(conn, market_id: int, briefing_id: int, revision_id: int
             ) -> Optional[Dict[str, Any]]:
    row = conn.execute(text("""
        SELECT * FROM bw_market_briefing_revisions
         WHERE market_id = :m AND briefing_id = :b AND id = :r
    """), {"m": market_id, "b": briefing_id, "r": revision_id}).mappings().first()
    return dict(row) if row else None


def restore(conn, market: Dict[str, Any], briefing_id: int, revision_id: int,
            saved_by: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Put an earlier text back. The current text is kept as a revision."""
    rev = revision(conn, market["id"], briefing_id, revision_id)
    if not rev:
        return None
    # Putting the model's own text back makes it the model's text again.
    return save_edit(conn, market, briefing_id, content=rev["report_content"],
                     title=rev.get("title"), saved_by=saved_by, reason="restore",
                     generation=rev.get("generation") or "edited")


# ---------------------------------------------------------------------------
# The approved briefing as a news-feed item
# ---------------------------------------------------------------------------
#
# The shared news feed is a query over ``articles``: anything with a category
# and a sentiment inside the date range is a feed item. So an approved
# briefing joins the feed by becoming one row there, pointing at its own
# HTML page. Approval puts the row in; rejecting, or regenerating (which
# returns the briefing to draft), takes it out again. The row is marked
# ``article_origin = 'report'`` so any reader of ``articles`` that should not
# treat a briefing as one more article can tell it apart.

FEED_SOURCE = "Aunoo Market Monitor"
FEED_CATEGORY = "Market Briefing"
FEED_SENTIMENT = "Neutral"
FEED_ORIGIN = "report"
FEED_SUMMARY_LIMIT = 480


def briefing_page_path(market_id: int, briefing_id: int, kind: str = "briefing") -> str:
    if kind in ("analysis", "note"):
        # Our own pieces are public on the front page, whoever opens them.
        return f"/api/market-monitor/markets/{market_id}/report.html?view=v2&piece={briefing_id}"
    return f"/api/market-monitor/markets/{market_id}/briefings/{briefing_id}/report.html"


def briefing_page_url(market_id: int, briefing_id: int, kind: str = "briefing") -> str:
    """The absolute URL the feed row carries as its ``uri``.

    Absolute because the feed card opens it in a new tab and other readers
    of ``articles`` take the host out of the URI as the source name.
    """
    base = (os.getenv("APP_URL") or "").rstrip("/")
    return base + briefing_page_path(market_id, briefing_id, kind)


_MD_HEADING_RE = re.compile(r"^\s*(#{1,6}\s|[-*_]{3,}\s*$|\*\*[^*]+\*\*\s*$|>\s)")


def feed_summary(content: str, limit: int = FEED_SUMMARY_LIMIT) -> str:
    """The first real paragraph of the briefing, citations removed.

    The briefing opens with a byline, a bold title, a rule and a heading
    before it says anything, so the first prose paragraph is the one worth
    showing on a feed card. Cut on a sentence end where there is one.
    """
    for para in re.split(r"\n\s*\n", content or ""):
        lines = [ln for ln in para.splitlines() if ln.strip()]
        if not lines:
            continue
        prose = [ln for ln in lines if not _MD_HEADING_RE.match(ln)
                 and "|" not in ln]
        if not prose:
            continue
        joined = " ".join(ln.strip() for ln in prose)
        joined = _CITATION_RE.sub("", joined)
        joined = re.sub(r"\s+([.,;:!?])", r"\1", joined)
        joined = re.sub(r"\s{2,}", " ", joined).strip()
        # A subtitle written as plain text — "Week of 17–23 August 2026:
        # AI-SOC Market Briefing" — has no sentence end and is short. Skip it
        # the way a marked heading is skipped.
        if len(joined) < 120 and not re.search(r"[.!?]", joined):
            continue
        if len(joined) <= limit:
            return joined
        cut = joined[:limit]
        end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
        return (cut[:end + 1] if end > limit // 3 else cut.rstrip() + "…")
    return ""


def market_topic(market: Dict[str, Any]) -> str:
    """The topic name the market's own articles carry, so the briefing sits
    under the same topic filter as the news it summarises."""
    cfg = market.get("config") or {}
    if isinstance(cfg, str):
        try:
            cfg = json.loads(cfg)
        except ValueError:
            cfg = {}
    return ((cfg.get("collection") or {}).get("topic_name")
            or market.get("name") or "")


def feed_row(market: Dict[str, Any], briefing: Dict[str, Any],
             approved_at: Optional[datetime] = None) -> Dict[str, Any]:
    """The ``articles`` row for an approved briefing. Pure; no database."""
    stamp = (approved_at or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    kind = briefing.get("kind") or "briefing"
    return {
        "uri": briefing_page_url(market["id"], briefing["id"], kind),
        "title": briefing.get("title") or f"{market['name']} — {briefing.get('period_label', '')}",
        "summary": feed_summary(briefing.get("report_content") or ""),
        "news_source": FEED_SOURCE,
        "publication_date": stamp,
        "submission_date": submission_stamp(approved_at or stamp),
        "category": FEED_CATEGORY,
        "sentiment": FEED_SENTIMENT,
        "topic": market_topic(market),
        "tags": ", ".join(t for t in (f"market {kind}", market.get("name", "")) if t),
        "analyzed": True,
        "ingest_status": "approved",
        "article_origin": FEED_ORIGIN,
    }


def _withdraw_from_feed(conn, market_id: int, briefing_id: int) -> int:
    n = 0
    for kind in KINDS:
        n += conn.execute(text(
            "DELETE FROM articles WHERE uri = :u AND article_origin = :o"
        ), {"u": briefing_page_url(market_id, briefing_id, kind), "o": FEED_ORIGIN}).rowcount
    return n


def _publish_to_feed(conn, market: Dict[str, Any], briefing: Dict[str, Any]) -> None:
    row = feed_row(market, briefing)
    conn.execute(text("""
        INSERT INTO articles
            (uri, title, summary, news_source, publication_date, submission_date,
             category, sentiment, topic, tags, analyzed, ingest_status, article_origin)
        VALUES (:uri, :title, :summary, :news_source, :publication_date,
                :submission_date, :category, :sentiment, :topic, :tags,
                :analyzed, :ingest_status, :article_origin)
        ON CONFLICT (uri) DO UPDATE SET
            title = EXCLUDED.title, summary = EXCLUDED.summary,
            publication_date = EXCLUDED.publication_date,
            submission_date = EXCLUDED.submission_date,
            category = EXCLUDED.category, sentiment = EXCLUDED.sentiment,
            topic = EXCLUDED.topic, tags = EXCLUDED.tags,
            analyzed = EXCLUDED.analyzed, ingest_status = EXCLUDED.ingest_status,
            article_origin = EXCLUDED.article_origin
    """), row)


def sync_feed_entry(conn, market: Dict[str, Any], briefing_id: int,
                    commit: bool = True) -> Optional[str]:
    """Make the feed agree with the briefing's status.

    Approved: the briefing has a row in ``articles``. Anything else: it does
    not. Returns "published", "withdrawn", or None when the briefing does not
    exist. Safe to call repeatedly.
    """
    briefing = get(conn, market["id"], briefing_id)
    if not briefing:
        return None
    if briefing.get("status") == "approved":
        _publish_to_feed(conn, market, briefing)
        outcome = "published"
    else:
        _withdraw_from_feed(conn, market["id"], briefing_id)
        outcome = "withdrawn"
    if commit:
        conn.commit()
    return outcome


# ---------------------------------------------------------------------------
# The briefing as a page
# ---------------------------------------------------------------------------

def render_page(market: Dict[str, Any], briefing: Dict[str, Any]) -> str:
    """The briefing as one self-contained HTML page."""
    from app.services.html_report_common import esc, html_document

    status = briefing.get("status") or "draft"
    head = (f'<p class="eyebrow">{esc(market.get("name", ""))} · '
            f'{esc(briefing.get("period_label", ""))} · {esc(status)}</p>')
    return html_document(briefing.get("title") or market.get("name", "Briefing"),
                         head + render_body(briefing))


# ---------------------------------------------------------------------------
# The approved briefing on the shared market report
# ---------------------------------------------------------------------------
#
# The shared report (a public market, or a signed link) withholds most vendors
# and refuses to serve a page that names one of them — it raises rather than
# redacts (market_entitlements.assert_no_withheld). A briefing names every
# vendor, so the shared view gets a card: the title, the period, and only the
# summary sentences that name no withheld vendor. The text itself is for a
# reader with a session.

def approved_listing(conn, market_id: int, limit: int = 12,
                     kind: str = "briefing") -> List[Dict[str, Any]]:
    return [dict(r) for r in conn.execute(text("""
        SELECT id, period_label, period_start, period_end, title, updated_at,
               kind, author, published_at,
               (facts->>'item_count')::int AS item_count
        FROM bw_market_briefings
        WHERE market_id = :m AND status = 'approved' AND kind = :k
        ORDER BY period_start DESC LIMIT :lim
    """), {"m": market_id, "lim": limit, "k": kind}).mappings().all()]


def latest_approved(conn, market_id: int, kind: str = "briefing") -> Optional[Dict[str, Any]]:
    row = conn.execute(text("""
        SELECT * FROM bw_market_briefings
        WHERE market_id = :m AND status = 'approved' AND kind = :k
        ORDER BY period_start DESC LIMIT 1
    """), {"m": market_id, "k": kind}).mappings().first()
    return dict(row) if row else None


def approved_pieces(conn, market_id: int, limit: int = 24) -> List[Dict[str, Any]]:
    """Our own approved pieces — analysis and notes — newest published first,
    with their text, for the front page."""
    return [dict(r) for r in conn.execute(text("""
        SELECT * FROM bw_market_briefings
        WHERE market_id = :m AND status = 'approved' AND kind IN ('analysis', 'note')
        ORDER BY published_at DESC NULLS LAST, id DESC LIMIT :lim
    """), {"m": market_id, "lim": limit}).mappings().all()]


def piece(conn, market_id: int, piece_id: int) -> Optional[Dict[str, Any]]:
    """One approved piece by id, or None. A draft is never served."""
    row = get(conn, market_id, piece_id)
    if not row or row.get("status") != "approved" or row.get("kind") not in ("analysis", "note"):
        return None
    return row


def provenance_line(piece_row: Dict[str, Any]) -> str:
    """Who wrote it, honestly: a person, or a model with a person's edit."""
    author = (piece_row.get("author") or "the Cyberfuturists").strip()
    gen = piece_row.get("generation") or "written"
    if gen == "written":
        return f"By {author}"
    if gen == "edited":
        return f"Drafted with a model, edited by {author}"
    return f"Drafted by a model ({piece_row.get('model_used') or 'unnamed'}), reviewed by {author}"


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'“(])")


def safe_sentences(summary: str, withheld: List[str]) -> str:
    """The sentences of ``summary`` that name no withheld vendor.

    Dropped whole, never redacted, the way the shared news river drops a
    headline that names a withheld vendor. Matched on word boundaries, case
    folded, the same test the page-level check applies afterwards.
    """
    if not withheld:
        return summary
    patterns = [re.compile(rf"(?<!\w){re.escape(n)}(?!\w)", re.IGNORECASE)
                for n in withheld if n and n.strip()]
    kept = [s for s in _SENTENCE_SPLIT_RE.split(summary or "")
            if s.strip() and not any(p.search(s) for p in patterns)]
    return " ".join(kept)


def render_body(briefing: Dict[str, Any]) -> str:
    """The briefing text as HTML: markdown rendered, each citation linked to
    its source, and a References list of the IDs actually cited."""
    import markdown as _markdown
    from app.services.html_report_common import esc

    facts = briefing.get("facts") or {}
    if isinstance(facts, str):
        try:
            facts = json.loads(facts)
        except ValueError:
            facts = {}
    index = facts.get("citation_index") or {}

    body = _markdown.markdown(briefing.get("report_content") or "",
                              extensions=["tables"])
    seen: List[str] = []

    def _link(match: "re.Match[str]") -> str:
        parts = []
        for cid in _CITE_ID_RE.findall(match.group(1)):
            ref = index.get(cid)
            if ref and cid not in seen:
                seen.append(cid)
            if ref and ref.get("uri"):
                parts.append(f'<a href="{esc(ref["uri"])}" target="_blank" '
                             f'rel="noreferrer">{cid}</a>')
            else:
                parts.append(cid)
        return "[" + ", ".join(parts) + "]"

    body = _CITATION_RE.sub(_link, body)
    if not seen:
        return body
    items = []
    for cid in seen:
        ref = index[cid]
        label = " — ".join(p for p in (ref.get("vendor"), ref.get("title")) if p)
        uri = ref.get("uri") or ""
        items.append(
            f'<li><strong>{cid}</strong> {esc(label)}'
            + (f' <a href="{esc(uri)}" target="_blank" rel="noreferrer">'
               f'{esc(uri)}</a>' if uri else "") + "</li>")
    return body + '<h2>References</h2><ol class="refs">' + "".join(items) + "</ol>"
