"""Regression set for the market post review: every mistake that reached
aisocnews.com, with the right outcome written down.

Each case is a real post. The runner takes it through the review as it runs
in production — the drafter, Jev's checks, the corrector, the hold rules —
without storing anything, then applies the page's own rules to decide what a
reader would see, and compares that with the case's expectation.

Run it after any change to the review prompt, the checks, the page rules or
the models. A failing case means the change brought an old mistake back.

    .venv/bin/python eval/market_review_regression/run.py
    .venv/bin/python eval/market_review_regression/run.py --drafter bedrock-kimi-k3
    .venv/bin/python eval/market_review_regression/run.py --only spectrum_sep2
    .venv/bin/python eval/market_review_regression/run.py --repeat 3   # the gate

Exit code 0 when every case passes, 1 otherwise.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from sqlalchemy import text  # noqa: E402

from app.database import get_database_instance  # noqa: E402
from app.services import market_assessment as ma  # noqa: E402
from app.services import market_post_review as mpr  # noqa: E402

CASES = Path(__file__).with_name("cases.json")


def _post(conn, market_id: int, uri: str):
    return conn.execute(text("""
        SELECT a.uri, a.title, a.summary, a.bias_source,
               b.display_name AS vendor, b.id AS brand_id
          FROM articles a
          JOIN bw_article_categories bac ON bac.article_uri = a.uri
          JOIN bw_market_brands mb ON mb.brand_id = bac.brand_id
                                   AND mb.market_id = :m
          JOIN bw_brands b ON b.id = bac.brand_id
         WHERE a.uri = :u
         LIMIT 1
    """), {"m": market_id, "u": uri}).mappings().first()


def _shown(post, v) -> dict:
    """What the page would show for this reading: whether it is an item, and
    the headline, summary and customer a reader would see."""
    article_class = "social" if post["bias_source"] == "vendor:linkedin" else "vendor"
    row = {
        "uri": post["uri"], "title": post["title"], "summary": post["summary"],
        "article_class": article_class,
        "vendors": [{"vendor": post["vendor"], "brand_id": post["brand_id"]}],
        "review_verdict": v.get("verdict"), "review_kind": v.get("kind"),
        "review_headline": v.get("headline"), "review_summary": v.get("summary"),
        "review_check": v.get("check"), "review_customer": v.get("customer"),
        "social_meta": {},
    }
    kind = ma.classify_record(row)
    headline, dek = ma.checked_writing(row)
    # The two guards the corpus path adds for a vendor's own web page.
    if kind in ma.THIRD_PARTY_KINDS and article_class == "vendor" \
            and not ma.speaks_for_vendor(headline or post["title"] or "", row):
        kind = None
    if kind == "customer" and article_class == "vendor" \
            and not (v.get("customer") or {}).get("name"):
        kind = None
    customer = None
    if v.get("customer"):
        customer = ma.reading_from_review(
            v["customer"], text_value=f"{post['title']} {post['summary']}").get("name")
    return {"shown": kind is not None, "kind": kind, "headline": headline,
            "summary": dek, "customer": customer}


def _judge_case(case, seen) -> list:
    exp, problems = case["expect"], []
    if "shown" in exp and seen["shown"] != exp["shown"]:
        problems.append(f"shown={seen['shown']}, expected {exp['shown']}")
    if "kind_in" in exp and seen["shown"] and seen["kind"] not in exp["kind_in"]:
        problems.append(f"kind={seen['kind']}, expected one of {exp['kind_in']}")
    if "customer_name" in exp and seen["customer"] != exp["customer_name"]:
        problems.append(f"customer={seen['customer']!r}, expected {exp['customer_name']!r}")
    if "customer_not" in exp and (seen["customer"] or "") == exp["customer_not"]:
        problems.append(f"customer is {exp['customer_not']!r}")
    for field, key in (("headline", "headline_excludes"), ("summary", "summary_excludes")):
        for bad in exp.get(key, []):
            if bad.lower() in (seen[field] or "").lower():
                problems.append(f"{field} contains {bad!r}: {seen[field]!r}")
    for good in exp.get("text_includes", []):
        blob = f"{seen['headline'] or ''} {seen['summary'] or ''}".lower()
        if good.lower() not in blob:
            problems.append(f"headline/summary lacks {good!r}")
    return problems


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--drafter", help="model alias for the drafting review")
    ap.add_argument("--corrector", help="model alias for the corrector")
    ap.add_argument("--only", help="run one case id")
    ap.add_argument("--repeat", type=int, default=1,
                    help="runs; a case fails only when it fails in most of them")
    args = ap.parse_args()
    if args.corrector:
        os.environ["MARKET_REVIEW_CORRECTOR_MODEL"] = args.corrector
    drafter = args.drafter or mpr._model()

    cases = json.loads(CASES.read_text())
    if args.only:
        cases = [c for c in cases if c["id"] == args.only]
    db = get_database_instance()
    with db._temp_get_connection() as conn:
        name = conn.execute(text("SELECT name FROM bw_markets WHERE id = 2")).scalar()
        posts = {c["id"]: _post(conn, c["market_id"], c["uri"]) for c in cases}

    started = time.monotonic()
    todo = [dict(p) for p in posts.values() if p]
    # The models vary between runs (Sonnet 5 takes no temperature, and the
    # drafter's reading depends on which posts share its batch), so one run
    # is a noisy measure: a case fails only when it fails in most runs.
    misses: dict = {c["id"]: [] for c in cases}
    for run_no in range(args.repeat):
        by_uri = {}
        for i in range(0, len(todo), 20):
            verdicts = await mpr._judge(name, todo[i:i + 20], drafter)
            await mpr.validate_and_correct(name, verdicts)
            by_uri.update({v["uri"]: v for v in verdicts})
        for case in cases:
            post = posts[case["id"]]
            if post is None:
                continue
            v = by_uri.get(case["uri"])
            problems = (["the drafter returned no reading"] if v is None
                        else _judge_case(case, _shown(post, v)))
            if problems:
                misses[case["id"]].append("; ".join(problems))

    failed = 0
    for case in cases:
        if posts[case["id"]] is None:
            print(f"SKIP  {case['id']}: post not found")
            continue
        n = len(misses[case["id"]])
        tally = f" ({n} of {args.repeat} runs)" if args.repeat > 1 else ""
        if n * 2 > args.repeat:
            failed += 1
            print(f"FAIL  {case['id']}{tally}: {misses[case['id']][0]}\n      why: {case['why']}")
        elif n:
            print(f"flaky {case['id']}{tally}: {misses[case['id']][0]}")
        else:
            print(f"pass  {case['id']}")
    print(f"\n{len(cases) - failed} of {len(cases)} passed with drafter {drafter}, "
          f"corrector {mpr._corrector_model()}, {args.repeat} run(s), "
          f"in {time.monotonic() - started:.0f}s")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
