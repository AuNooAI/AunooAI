#!/usr/bin/env python3
"""Name the author role on social posts scored before roles existed.

The social evaluation step now returns who wrote each post (patient,
clinician, customer, employee, journalist ...) in the same model call that
scores relevance and sentiment, so new posts need nothing. This script
covers the backlog: on-brand social and community posts with no
``author_role`` yet get one role-only model call each, using the same
taxonomy and the tenant's social evaluation model (SOCIAL_EVAL_MODEL).

Usage (from the tenant tree, its venv):
    .venv/bin/python scripts/backfill_author_roles.py            # dry run: counts only
    .venv/bin/python scripts/backfill_author_roles.py --apply    # classify and write
    .venv/bin/python scripts/backfill_author_roles.py --apply --days 180 --limit 500
    .venv/bin/python scripts/backfill_author_roles.py --apply --brand Oviva

Glassdoor rows are skipped: the read path treats them as employees without
a model verdict. Posts below the 0.4 relevance floor are skipped too; the
views never show them, so a role for them would be spend for nothing.
"""
import argparse
import asyncio
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from sqlalchemy import text  # noqa: E402

from app.database import get_database_instance  # noqa: E402
from app.services.social_eval_service import (  # noqa: E402
    SOCIAL_SOURCES, SocialEvalService, _brand_context_for_topic)


def _candidates(conn, days: int, limit: int, brand: str | None, redo: bool = False):
    """On-brand social posts that need a role.

    Two ways a post is on-brand: the topic read (score on the article row,
    every tenant) and the per-mention read (score on the (post, company)
    pair, Entity Intelligence tenants). Both are checked; a post found
    either way is classified once, under its brand topic.
    """
    src = " OR ".join(f"LOWER(a.news_source) LIKE :s{i}" for i in range(len(SOCIAL_SOURCES)))
    role_clause = "" if redo else "AND a.author_role IS NULL"
    params = {"lim": limit, "cutoff": f"{days}"}
    for i, s in enumerate(SOCIAL_SOURCES):
        params[f"s{i}"] = f"%{s}%"
    brand_clause = ""
    if brand:
        brand_clause = "AND a.topic = :topic"
        params["topic"] = f"Brand Monitoring {brand}"
    rows = conn.execute(text(f"""
        SELECT a.uri, a.title, a.summary, COALESCE(a.social_meta->>'author', '') AS author,
               a.topic
          FROM articles a
         WHERE ({src})
           AND a.news_source <> 'Glassdoor'
           {role_clause}
           AND a.analyzed = true
           AND a.topic_alignment_score >= 0.4
           AND a.topic LIKE 'Brand Monitoring %'
           AND a.publication_date >= to_char(NOW() - CAST(:cutoff || ' days' AS INTERVAL), 'YYYY-MM-DD')
           {brand_clause}
         ORDER BY a.publication_date DESC
         LIMIT :lim
    """), params).fetchall()
    found = {r[0]: dict(uri=r[0], title=r[1], summary=r[2], author=r[3], topic=r[4]) for r in rows}

    has_mentions = conn.execute(text(
        "SELECT to_regclass('bw_entity_mentions') IS NOT NULL")).scalar()
    if has_mentions:
        mparams = {"lim": limit, "cutoff": f"{days}"}
        mbrand = ""
        if brand:
            mbrand = "AND b.display_name = :brand"
            mparams["brand"] = brand
        mrows = conn.execute(text(f"""
            SELECT a.uri, a.title, a.summary, COALESCE(a.social_meta->>'author', ''),
                   'Brand Monitoring ' || b.display_name
              FROM bw_entity_mentions m
              JOIN articles a ON a.uri = m.article_uri
              JOIN bw_brands b ON b.id = m.brand_id
             WHERE m.channel IN ('public_social', 'community')
               AND m.status <> 'false_positive'
               AND m.relevance >= 0.4
               {role_clause}
               AND a.publication_date >= to_char(NOW() - CAST(:cutoff || ' days' AS INTERVAL), 'YYYY-MM-DD')
               {mbrand}
             ORDER BY a.publication_date DESC
             LIMIT :lim
        """), mparams).fetchall()
        for r in mrows:
            found.setdefault(r[0], dict(uri=r[0], title=r[1], summary=r[2], author=r[3], topic=r[4]))
    return list(found.values())[:limit]


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="classify and write; default is a dry run")
    ap.add_argument("--days", type=int, default=180, help="publication window (default 180)")
    ap.add_argument("--limit", type=int, default=1000, help="max posts this run (default 1000)")
    ap.add_argument("--brand", help="only this brand's topic (display name)")
    ap.add_argument("--model", help="override SOCIAL_EVAL_MODEL for this run")
    ap.add_argument("--redo", action="store_true",
                    help="classify posts that already have a role too, and overwrite it (after a model or prompt change)")
    args = ap.parse_args()

    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        posts = _candidates(conn, args.days, args.limit, args.brand, redo=args.redo)
        by_topic = Counter(p["topic"] for p in posts)
        print(f"{len(posts)} on-brand social post(s) "
              f"{'to reclassify' if args.redo else 'without an author role'} "
              f"(last {args.days} days):")
        for topic, n in by_topic.most_common():
            print(f"  {n:5d}  {topic}")
        if not args.apply or not posts:
            if not args.apply:
                print("dry run; pass --apply to classify")
            return 0

        svc = SocialEvalService(args.model) if args.model else SocialEvalService()
        if not svc._get_model():
            print(f"model {svc.model_name!r} unavailable", file=sys.stderr)
            return 2
        print(f"classifying with {svc.model_name}")
        written = 0
        roles = Counter()
        for topic in by_topic:
            batch = [p for p in posts if p["topic"] == topic]
            ctx = _brand_context_for_topic(db, topic)
            brand = topic.replace("Brand Monitoring ", "", 1)
            scored = await svc.classify_roles(batch, brand, brand_context=ctx["description"])
            for s in scored:
                conn.execute(text(f"""
                    UPDATE articles SET author_role = :role, author_role_reason = :why
                     WHERE uri = :uri {'' if args.redo else 'AND author_role IS NULL'}
                """), {"role": s["author_role"], "why": s.get("author_role_reason"), "uri": s["uri"]})
                roles[s["author_role"]] += 1
                written += 1
            conn.commit()
            print(f"  {topic}: {len(scored)}/{len(batch)} classified")
        print(f"wrote {written} role(s):")
        for role, n in roles.most_common():
            print(f"  {n:5d}  {role}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
