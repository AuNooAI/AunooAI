"""Weekly error rate for one market page: 20 random items, graded against
their sources by a model that is neither the checker nor the corrector.

The daily lint catches faults of form. This measures the one number that
matters to a reader: how often an item on the page states something its
source does not support. The target is fewer than 1 wrong item in 50; a
rolling four-week rate (about 80 items) is what to act on, not one week.

Graded: the developments and the "Wider market" strip. Not graded: Social,
which quotes posts word for word.

Prints one JSON object (the last line of stdout). The weekly wrapper appends
it to /var/log/aunoo-market-quality-samples.jsonl and emails the result.

    .venv/bin/python scripts/market_quality_sample.py --market 2
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from sqlalchemy import text  # noqa: E402

from app.database import get_database_instance  # noqa: E402

SAMPLE = 20
#: Opus 5: not Jev (the checker) and not Sonnet 5 (the corrector), so it
#: does not grade its own work.
GRADER = "claude-opus-5"

PROMPT = """You check items on a market-intelligence news page against their sources.

The item says:
  TYPE: {type}
  COMPANY: {company}
  THE COMPANY ALSO PUBLISHES AS: {aliases}
  HEADLINE: {headline}
  SUMMARY: {summary}

The sources it was built from:
{sources}

Is the item right? It is WRONG if any of these hold:
- the headline or summary states something the sources do not support
  (a figure, a name, a claim, a detail);
- it names the wrong company as the one that acted;
- the TYPE is wrong for what happened (for example a marketplace listing
  shown as a customer, a milestone shown as a launch, a junior hire shown
  as an executive appointment);
- the sources do not describe a real development at all.
Wording, tone and what was left out do not make it wrong.

Answer with JSON only: {{"verdict": "right" | "wrong", "why": "<one sentence if wrong, else empty>"}}"""


def _aliases(conn, dev) -> str:
    """The vendor's other names and pages: System Two Security posts as
    detections.ai, and the grader marked its launch wrong for that."""
    ids = [v.get("brand_id") for v in dev.get("vendors") or [] if v.get("brand_id")]
    if not ids:
        return "(not known)"
    rows = conn.execute(text("""
        SELECT DISTINCT coalesce(display_value, normalized_value) FROM bw_vendor_identifiers
         WHERE brand_id = ANY(:b) AND valid_to IS NULL
           AND kind IN ('alias', 'former_name', 'linkedin_company_url', 'website_url',
                        'domain', 'social_account')
    """), {"b": ids}).scalars().all()
    return ", ".join(sorted(r for r in rows if r)) or "(not known)"


def _sources(conn, dev) -> str:
    uris = [e.get("uri") for e in dev.get("evidence") or [] if e.get("uri")][:3]
    if not uris:
        return "(none)"
    rows = conn.execute(text("""
        SELECT uri, title, summary FROM articles WHERE uri = ANY(:u)
    """), {"u": uris}).mappings().all()
    return "\n\n".join(f"[{r['uri']}]\n{r['title'] or ''}\n{(r['summary'] or '')[:2500]}"
                       for r in rows) or "(none)"


async def _grade(item) -> dict:
    import litellm

    from app.ai_models import extract_json_response, resolve_litellm_call_params

    response = await litellm.acompletion(
        **resolve_litellm_call_params(GRADER),
        messages=[{"role": "user", "content": PROMPT.format(**item["prompt"])}],
        max_tokens=300,
    )
    parsed = extract_json_response((response.choices[0].message.content or "").strip())
    return parsed if isinstance(parsed, dict) else {"verdict": "unanswered"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", type=int, required=True)
    ap.add_argument("--size", type=int, default=SAMPLE)
    args = ap.parse_args()
    from app.services import market_assessment as ma

    week = date.today().isocalendar()
    with get_database_instance()._temp_get_connection() as conn:
        result = ma.material_developments(conn, args.market, 30)
        pool = [d for d in result["developments"] + result.get("wider", [])
                if d.get("event_type") not in ("significant_hiring", "headcount_change")]
        # Same sample for a re-run in the same week.
        items = random.Random(f"{args.market}-{week[0]}-{week[1]}").sample(
            pool, min(args.size, len(pool)))
        for d in items:
            d["prompt"] = {
                "type": d.get("event_type_label") or d.get("event_type"),
                "company": ", ".join(v.get("vendor") or "" for v in d.get("vendors") or []),
                "headline": d.get("headline") or "",
                "summary": d.get("dek") or "",
                "aliases": _aliases(conn, d),
                "sources": _sources(conn, d)}

    async def run():
        gate = asyncio.Semaphore(4)

        async def one(d):
            async with gate:
                try:
                    d["grade"] = await _grade(d)
                except Exception as exc:  # noqa: BLE001
                    d["grade"] = {"verdict": "unanswered", "why": str(exc)[:200]}
        await asyncio.gather(*(one(d) for d in items))

    asyncio.run(run())
    wrong = [d for d in items if d["grade"].get("verdict") == "wrong"]
    graded = [d for d in items if d["grade"].get("verdict") in ("right", "wrong")]
    print(json.dumps({
        "market_id": args.market, "week": f"{week[0]}-W{week[1]:02d}",
        "grader": GRADER, "sampled": len(items), "graded": len(graded),
        "wrong": len(wrong),
        "wrong_items": [{"headline": d.get("headline"), "type": d["prompt"]["type"],
                         "company": d["prompt"]["company"],
                         "why": d["grade"].get("why"),
                         "uri": ((d.get("evidence") or [{}])[0]).get("uri")}
                        for d in wrong],
    }, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
