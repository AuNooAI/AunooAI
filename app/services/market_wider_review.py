"""The review for the "Wider market" strip: deals and launches by companies
the market does not track.

The strip used to print the news item's own text as its headline: Splunk's
first-person ".conf" post cut off mid-word, Cisco's with "&amp;" in it. The
vendor review never saw these items, because they are not the tracked
vendors' posts. This runs the same loop over them: a drafter writes a
headline and one-sentence summary, Jev checks both against the article, the
corrector fixes what Jev disputes, and Jev checks again. The strip shows only
items that passed (``market_assessment._wider_candidate``).

The reading is stored in ``bw_market_articles.review_check`` under the key
``wider``, beside whatever else the row carries:

    {"headline", "summary", "company", "kind", "check", "passed",
     "corrected", "model", "checked_at"}
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

#: Items per model call.
BATCH = 15

_KIND_WORDS = {
    "acquisition": "an acquisition", "market_exit": "a market exit or shutdown",
    "funding": "a funding round", "product_launch": "a product launch",
    "product_expansion": "a product expansion", "partnership": "a partnership",
}

DRAFT_PROMPT = """You write short news items for a market-intelligence page about {market}.

Each item below is a news report or post about a company. For each, write:
- "headline": at most 90 characters, third person, present tense, with the
  company named as the one acting. Only facts the text states. No hype words,
  no emoji, no hashtags, no handles, no links.
- "summary": one sentence, at most 200 characters, adding detail about the
  same development. Only facts the text states. Leave it empty rather than
  pad it.
If the text does not report that the company did what the item says, set
"headline" to null.

Return JSON: {{"results": [{{"id": <id>, "headline": ..., "summary": ...}}]}}

ITEMS:
{items}"""

CORRECT_PROMPT = """You correct short news items for a market-intelligence page about {market}.
A checker disputed each item below against its source. Rewrite the headline
and summary so the source supports every word: third person, the right company
as the actor, no detail the source lacks. Headline at most 90 characters,
summary one sentence of at most 200 characters, or empty. If the source does
not report the development at all, set "headline" to null.

Return JSON: {{"results": [{{"id": <id>, "headline": ..., "summary": ...}}]}}

ITEMS:
{items}"""


def _source(row: Dict[str, Any]) -> str:
    return f"{row.get('title') or ''}\n\n{row.get('summary') or ''}".strip()


def _render(items: List[Dict[str, Any]], with_objections: bool = False) -> str:
    blocks = []
    for i, it in enumerate(items):
        block = (f"[{i}] COMPANY: {it['company']}\n"
                 f"    DEVELOPMENT: {_KIND_WORDS.get(it['kind'], it['kind'])}\n"
                 f"    SOURCE: {_source(it)[:1500]}")
        if with_objections:
            block += (f"\n    FIRST HEADLINE: {it.get('headline')}"
                      f"\n    FIRST SUMMARY: {it.get('summary')}"
                      f"\n    CHECKER DISPUTES: {'; '.join(it.get('objections') or [])}")
        blocks.append(block)
    return "\n\n".join(blocks)


async def _write(model: str, prompt: str, n: int) -> Dict[int, Dict[str, Any]]:
    import litellm

    from app.ai_models import extract_json_response, resolve_litellm_call_params

    response = await litellm.acompletion(
        **resolve_litellm_call_params(model),
        messages=[{"role": "user", "content": prompt}],
        max_tokens=min(8192, 160 * n + 400),
        temperature=0,
    )
    parsed = extract_json_response((response.choices[0].message.content or "").strip())
    if isinstance(parsed, dict):
        parsed = parsed.get("results") or []
    out: Dict[int, Dict[str, Any]] = {}
    for item in parsed if isinstance(parsed, list) else []:
        try:
            out[int(item.get("id"))] = item
        except (TypeError, ValueError, AttributeError):
            continue
    return out


def _clean(value: Any, limit: int) -> Optional[str]:
    if not isinstance(value, str):
        return None
    value = " ".join(value.split()).strip().strip('"')
    if not value or value.lower() in ("null", "none"):
        return None
    return value[:limit]


def _questions(has_summary: bool) -> Dict[str, Dict[str, Any]]:
    from app.services.market_post_review import _CHECK_CRITERIA

    q: Dict[str, Dict[str, Any]] = {
        "is_news": {
            "type": "noul",
            "instructions": ("Does `post` report that `company` has done "
                             "`development`, as something that has happened?"),
            "criteria": {
                "true": "It reports the development as done or announced by the company",
                "false": "It is opinion, a preview, a rumour, a list, or about "
                         "another company"},
        },
        "headline": {
            "type": "choice",
            "instructions": ("How does `post` relate to `headline`? Judge only what "
                             "the post states. A headline that names the wrong "
                             "company as the actor or adds a detail the post lacks "
                             "is not supported."),
            "criteria": _CHECK_CRITERIA,
        },
        "actor": {
            "type": "noul",
            "instructions": "Does `headline` name `company` as the one that acted?",
            "criteria": {"true": "Yes", "false": "It makes another company the actor"},
        },
    }
    if has_summary:
        q["summary"] = {**q["headline"], "instructions": (
            "How does `post` relate to `summary`? Judge only what the post states. "
            "A summary that adds a detail the post lacks is not supported.")}
        q["summary_on_event"] = {
            "type": "noul",
            "instructions": "Is `summary` about the same development as `headline`?",
            "criteria": {"true": "It adds detail about that development",
                         "false": "It reports a different fact, event or topic"},
        }
    return q


def check(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Jev's reading of one written item, with the exact checks, or None when
    Jev did not answer."""
    from app.services import typesafe_client
    from app.services.market_post_review import CHECK_SOURCE_CHARS
    from app.services.review_exact_checks import exact_objections

    if not typesafe_client.is_configured() or not item.get("headline"):
        return None
    state = {"post": _source(item)[:CHECK_SOURCE_CHARS], "company": item["company"],
             "development": _KIND_WORDS.get(item["kind"], item["kind"]),
             "headline": item["headline"]}
    if item.get("summary"):
        state["summary"] = item["summary"]
    out = typesafe_client.system_one(state, _questions(bool(item.get("summary"))),
                                     use_case="services.market_wider_review:validate")
    if not out:
        return None
    answers = out.get("answers") or {}
    result: Dict[str, Any] = {"model": out.get("model")}
    for field in ("headline", "summary"):
        if field in answers:
            a = answers[field] or {}
            result[field] = {"verdict": a.get("choice"), "p_supports": round(float(
                (a.get("probabilities") or {}).get("supports", 0.0)), 3)}
    for key in ("is_news", "actor", "summary_on_event"):
        if key in answers:
            result[key] = round(float((answers[key] or {}).get("noul", 0.0)), 3)
    exact = exact_objections(item["headline"], item.get("summary"), _source(item),
                             [item["company"]])
    if exact:
        result["exact"] = exact
    return result


def objections(item: Dict[str, Any], result: Optional[Dict[str, Any]]) -> List[str]:
    from app.services.market_post_review import CHECK_MIN_SUPPORT, NEWS_MIN, ROLE_MIN

    if not result:
        return ["the checker did not answer"]
    out: List[str] = []
    if float(result.get("is_news", 1.0)) < NEWS_MIN:
        out.append(f"the source does not report that {item['company']} did this")
    if float(result.get("actor", 1.0)) < ROLE_MIN:
        out.append(f"the headline does not make {item['company']} the actor")
    if item.get("summary") and float(result.get("summary_on_event", 1.0)) < ROLE_MIN:
        out.append("the summary is about a different fact from the headline")
    out.extend(result.get("exact") or [])
    for field in ("headline", "summary"):
        reading = result.get(field) or {}
        if item.get(field) and not (reading.get("verdict") == "supports"
                                    and reading.get("p_supports", 0) >= CHECK_MIN_SUPPORT):
            out.append(f"the {field} is not supported by the source "
                       f"({reading.get('verdict') or 'no answer'})")
    return out


def _passed(item: Dict[str, Any], result: Optional[Dict[str, Any]]) -> bool:
    """The headline must pass. A summary that fails is dropped, not fatal."""
    if not item.get("headline") or not result:
        return False
    return not [o for o in objections({**item, "summary": None}, result)]


async def _check_all(items: List[Dict[str, Any]]) -> None:
    from app.services.market_post_review import _CHECK_CONCURRENCY

    gate = asyncio.Semaphore(_CHECK_CONCURRENCY)

    async def one(it):
        async with gate:
            it["check"] = await asyncio.to_thread(check, it)

    await asyncio.gather(*(one(it) for it in items if it.get("headline")))


def pending(conn, market_id: int, days: int = 30) -> List[Dict[str, Any]]:
    """Strip candidates with no stored reading, as the page would pick them."""
    from app.services import market_assessment as ma

    result = ma.material_developments(conn, market_id, days)
    return result.get("wider_unchecked") or []


async def review(conn, market_id: int, *, days: int = 30,
                 limit: int = 60) -> Dict[str, int]:
    """Write, check and correct the strip's items that have no reading yet."""
    from app.services.market_post_review import _corrector_model, _model

    market = conn.execute(text("SELECT name FROM bw_markets WHERE id = :m"),
                          {"m": market_id}).scalar() or ""
    items = pending(conn, market_id, days)[:limit]
    stats = {"candidates": len(items), "passed": 0, "corrected": 0, "failed": 0}
    drafter, corrector = _model(), _corrector_model()
    for start in range(0, len(items), BATCH):
        chunk = items[start:start + BATCH]
        try:
            drafts = await _write(drafter, DRAFT_PROMPT.format(
                market=market, items=_render(chunk)), len(chunk))
        except Exception as exc:  # noqa: BLE001 — one bad batch is not a failed run
            logger.warning("wider review draft failed (%d items): %s", len(chunk), exc)
            continue
        for i, it in enumerate(chunk):
            d = drafts.get(i) or {}
            it["headline"] = _clean(d.get("headline"), 120)
            it["summary"] = _clean(d.get("summary"), 260)
            it["model"] = drafter
        await _check_all(chunk)
        disputed = []
        for it in chunk:
            if it.get("headline"):
                it["objections"] = objections(it, it.get("check"))
                if it["objections"]:
                    disputed.append(it)
        if disputed:
            try:
                fixes = await _write(corrector, CORRECT_PROMPT.format(
                    market=market, items=_render(disputed, with_objections=True)),
                    len(disputed))
            except Exception as exc:  # noqa: BLE001
                logger.warning("wider review correction failed: %s", exc)
                fixes = {}
            recheck = []
            for i, it in enumerate(disputed):
                f = fixes.get(i)
                if f is None:
                    continue
                it["first_draft"] = {"headline": it["headline"], "summary": it["summary"]}
                it["headline"] = _clean(f.get("headline"), 120)
                it["summary"] = _clean(f.get("summary"), 260)
                it["model"] = corrector
                recheck.append(it)
            await _check_all(recheck)
        for it in chunk:
            ok = _passed(it, it.get("check"))
            summary_ok = ok and it.get("summary") and not objections(it, it.get("check"))
            reading = {
                "headline": it.get("headline") if ok else None,
                "summary": it.get("summary") if summary_ok else None,
                "company": it["company"], "kind": it["kind"],
                "check": it.get("check"), "passed": bool(ok),
                "corrected": bool(it.get("first_draft")),
                "first_draft": it.get("first_draft"),
                "objections": it.get("objections") or [],
                "model": it.get("model"),
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
            conn.execute(text("""
                UPDATE bw_market_articles
                   SET review_check = COALESCE(review_check, '{}'::jsonb)
                                      || jsonb_build_object('wider', CAST(:r AS jsonb))
                 WHERE market_id = :m AND article_uri = :u
            """), {"r": json.dumps(reading, default=str), "m": market_id,
                   "u": it["uri"]})
            stats["passed" if ok else "failed"] += 1
            stats["corrected"] += int(reading["corrected"])
        conn.commit()
    return stats
