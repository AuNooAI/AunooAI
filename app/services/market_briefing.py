"""The monthly market briefing: assembled facts, model prose on top.

Two stages, and the split is the point. Stage one collects the period's
evidence from stored rows with no model involved. Stage two asks a model to
write narrative **around** that block, with no licence to introduce a fact that
is not in it. So no number in a briefing can be invented, and because the facts
are stored alongside the prose, that claim is checkable afterwards rather than
merely asserted.

Monthly, not weekly. A week of this market carries eight to thirteen items; a
month carries thirty-five to sixty. A briefing generator run against a week
would spend most of its output padding.

Almost none of the machinery here is new. The tone contract, the date
directive, the reader-organisation persona, the empty-response retry and the
outbound lint all already exist and are used by every other prose surface in
this codebase.
"""

import json
import logging
from calendar import monthrange
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text

logger = logging.getLogger(__name__)

# Below this the month did not contain enough to write about. The briefing says
# so instead of padding — 800 words about a quiet month is worse than one
# sentence saying the month was quiet.
MIN_ITEMS_FOR_PROSE = 6

DEFAULT_MODEL = "gpt-5.4-mini"


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

    return {
        "market": market["name"],
        "question": market.get("question"),
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "announcements": announcements,
        "announcements_by_kind": by_kind,
        "coverage": coverage,
        "hiring": hiring,
        "new_entrants": entrants,
        "headcount_movers": brief.get("headcount_movers", [])[:8],
        "events": brief.get("events", []),
        "registry": brief.get("coverage", {}),
        "open_questions": brief.get("open_questions", []),
        "standing_summary": brief.get("standing_summary"),
        "item_count": len(announcements) + len(coverage),
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
        lines.append(f"\nVENDOR ANNOUNCEMENTS ({len(facts['announcements'])}). "
                     "Each is a claim the vendor made about itself on LinkedIn, "
                     "not an independently confirmed fact:")
        for a in facts["announcements"]:
            date_part = (a.get("publication_date") or "")[:10]
            lines.append(f"- [{date_part}] {a['vendor']} ({a.get('kind')}): "
                         f"{a['title']} — {a.get('reason') or ''}")

    if facts["coverage"]:
        lines.append(f"\nTHIRD-PARTY COVERAGE ({len(facts['coverage'])}):")
        for c in facts["coverage"]:
            date_part = (c.get("publication_date") or "")[:10]
            lines.append(f"- [{date_part}] {c.get('news_source') or 'unknown'}: "
                         f"{c['title']}")

    if facts["new_entrants"]:
        lines.append("\nNEW TO THE REGISTRY THIS PERIOD:")
        for e in facts["new_entrants"]:
            lines.append(f"- {e['vendor']} (founded {e.get('founded') or '?'})")

    if facts["headcount_movers"]:
        lines.append("\nHEADCOUNT AGAINST THE IMPORTED BASELINE:")
        for m in facts["headcount_movers"]:
            lines.append(f"- {m['vendor']}: {m.get('was')} -> "
                         f"{m.get('now_count')} ({m.get('pct')}%)")

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

    return f"""Write the monthly market briefing for {facts['market']}, covering {period_label}.

The market's question: {facts.get('question') or facts['market']}

Use ONLY the facts below. Do not add companies, figures, funding rounds, dates
or events that are not in them. If something is not in the facts, it is not in
the briefing. Do not estimate, extrapolate or round a number into a different
number.

Say where each claim comes from and how well corroborated it is. A vendor's own
post is a vendor claim, not an established fact about the market — write "X
said it has..." rather than "X has...". A trade-press article is a single
source unless two sources say the same thing.

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
        out.append(f"## Vendor announcements ({len(facts['announcements'])})")
        out.append("")
        out.append("Each is a claim the vendor made about itself.")
        out.append("")
        for a in facts["announcements"]:
            out.append(f"- **{a['vendor']}** ({a.get('kind')}): {a['title']}")
        out.append("")

    if facts["coverage"]:
        out.append(f"## Third-party coverage ({len(facts['coverage'])})")
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


async def generate(conn, market: Dict[str, Any], *, year: int, month: int,
                   model: Optional[str] = None, store: bool = True
                   ) -> Dict[str, Any]:
    """Build the facts, write the prose, store both."""
    from app.routes.vector_routes import (
        _generate_report_with_retry, _org_persona_report_prefix,
    )
    from app.ai_models import LiteLLMModel

    start, end, period_label = month_bounds(year, month)
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
        if not content:
            content = fallback_briefing(facts, period_label)
            generation = "fallback"

    try:
        from app.services.report_lint import lint_outbound
        lint = lint_outbound(content, kind="html",
                             context=f"market briefing {period_label}") or []
    except Exception as exc:  # noqa: BLE001
        logger.debug("briefing lint failed: %s", exc)
        lint = []

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
    conn.commit()
    result["id"] = row
    result["stored"] = True
    return result


def listing(conn, market_id: int, limit: int = 24) -> List[Dict[str, Any]]:
    return [dict(r) for r in conn.execute(text("""
        SELECT id, period_label, period_start, period_end, title, status,
               generation, model_used, created_at, updated_at,
               ARRAY_LENGTH(article_uris, 1) AS sources
        FROM bw_market_briefings WHERE market_id = :m
        ORDER BY period_start DESC LIMIT :lim
    """), {"m": market_id, "lim": limit}).mappings().all()]


def get(conn, market_id: int, briefing_id: int) -> Optional[Dict[str, Any]]:
    row = conn.execute(text("""
        SELECT * FROM bw_market_briefings
        WHERE market_id = :m AND id = :i
    """), {"m": market_id, "i": briefing_id}).mappings().first()
    return dict(row) if row else None


def set_status(conn, market_id: int, briefing_id: int, status: str) -> bool:
    if status not in ("draft", "approved", "rejected"):
        raise ValueError(f"unknown status: {status}")
    updated = conn.execute(text("""
        UPDATE bw_market_briefings SET status = :s, updated_at = NOW()
        WHERE market_id = :m AND id = :i
    """), {"s": status, "m": market_id, "i": briefing_id}).rowcount
    conn.commit()
    return bool(updated)
