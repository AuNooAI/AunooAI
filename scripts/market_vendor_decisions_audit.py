#!/usr/bin/env python3
"""Dry-run report: what the brand decision would do to a market's existing
vendor links (docs/BRAND_RELEVANCE_MARKET_VENDORS.md, section 6).

Reads the market's existing name-match links (bw_article_categories,
method market_name_match) and decides each (article, vendor) pair. Writes
nothing: no decision is stored and no link is removed. Removing or
relabelling old links is a separate decision made from this report.

    cd /home/orochford/tenants/<site>.aunoo.ai
    .venv/bin/python scripts/market_vendor_decisions_audit.py --market 1312             # rules only, no model calls
    .venv/bin/python scripts/market_vendor_decisions_audit.py --market 1312 --judge     # also call the judge
    ... --days 30 --samples 5 --json out.json

Rules only: pairs that need the judge (the vendor is named and nothing else
settles it) are reported as "needs judge".
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--market", type=int, required=True)
    ap.add_argument("--days", type=int, default=None, help="only links to articles from the last N days")
    ap.add_argument("--judge", action="store_true", help="call the judge where the rules do not settle a pair")
    ap.add_argument("--samples", type=int, default=5, help="sample titles per vendor and result")
    ap.add_argument("--json", help="write the full per-pair result here")
    a = ap.parse_args()

    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
    import logging
    logging.disable(logging.WARNING)
    from sqlalchemy import text
    from app.database import get_database_instance
    from app.services import brand_decision as bd
    from app.services import brand_profile as bp
    from app.services import market_vendor_decisions as mvd

    conn = get_database_instance()._temp_get_connection()
    try:
        where = ["bac.classification_method = 'market_name_match'",
                 # Social posts keep today's rule (spec section 4).
                 "(a.social_meta IS NULL OR a.social_meta::text = 'null')",
                 "bac.brand_id IN (SELECT brand_id FROM bw_market_brands WHERE market_id = :m)"]
        params = {"m": a.market}
        if a.days:
            where.append("COALESCE(a.publication_date, a.submission_date) >= :since")
            from app.services.market_corpus import _iso_days_ago
            params["since"] = _iso_days_ago(a.days)
        rows = conn.execute(text(f"""
            SELECT DISTINCT bac.brand_id, a.uri, a.title, a.summary, a.original_title, a.original_summary,
                   a.news_source, a.bias_source, a.topic
              FROM bw_article_categories bac JOIN articles a ON a.uri = bac.article_uri
             WHERE {' AND '.join(where)}
        """), params).mappings().all()
        profiles = mvd.profiles_by_id(conn, [r["brand_id"] for r in rows])

        def needs_judge(*_a):
            raise bd.JudgeUnavailable("rules-only audit")
        needs_judge.route = "audit"
        judges = bd.configured_judges() if a.judge else (needs_judge,)

        per = defaultdict(Counter)
        samples = defaultdict(list)
        full = []
        for r in rows:
            p = profiles.get(int(r["brand_id"]))
            name = p.display_name if p else f"brand {r['brand_id']}"
            if p is None:
                d = bd.Decision("deferred", reason="no brand profile")
            elif a.judge:
                d = mvd.decide(conn, p, dict(r), judges=judges)
            else:
                d = bd.decide(bp.ProfileResolution(p, brand_topic=False), dict(r), judges=judges,
                              topic_scorer=None, reuse=mvd.reuse_lookup(conn, r["uri"]))
            if d.outcome == "decided":
                result = "keep (earned)" if d.earned else f"drop ({d.brand_relation}, {d.source_relation})"
            elif d.outcome == "unavailable":
                result = "needs judge" if not a.judge else "unavailable"
            else:
                result = "deferred"
            per[name][result] += 1
            if len(samples[(name, result)]) < a.samples:
                samples[(name, result)].append((r["title"] or "")[:100])
            full.append({"vendor": name, "uri": r["uri"], "title": r["title"], "result": result,
                         "relation": d.brand_relation, "source": d.source_relation,
                         "mention": (d.evidence or {}).get("mention"), "reason": d.reason})
        conn.rollback()
    finally:
        conn.close()

    total = Counter()
    print(f"Market {a.market}: {len(rows)} existing name-match links on news (social posts keep today's rule)"
          f"{' (last %d days)' % a.days if a.days else ''}; {'judge called' if a.judge else 'rules only'}.\n")
    for vendor in sorted(per):
        print(f"{vendor}: " + ", ".join(f"{k} {v}" for k, v in per[vendor].most_common()))
        for result in per[vendor]:
            total[result] += per[vendor][result]
            for t in samples[(vendor, result)]:
                print(f"    [{result}] {t}")
    print("\nAll vendors: " + ", ".join(f"{k} {v}" for k, v in total.most_common()))
    print("Nothing was written.")
    if a.json:
        json.dump(full, open(a.json, "w"), ensure_ascii=False, indent=1, default=str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
