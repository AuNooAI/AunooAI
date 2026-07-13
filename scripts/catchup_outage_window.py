#!/usr/bin/env python3
"""One-off catch-up collection for the 2026-07-11..12 keyword-monitor outage.

The monitor loop hung on a Firecrawl call from 07-11 08:00 to the 07-13 08:45
restart, so ~2 days of keyword-collected articles were never fetched. Routine
cycles won't recover them: providers return newest-first, so post-restart
results bury the outage window. This script pins start_date AND end_date to
the window and batches keywords into OR-queries (~6/query) so the whole run
fits inside the NewsAPI/TheNewsAPI 100-requests/day quotas.

Articles flow through the live AutomatedIngestService.process_articles_batch
(same relevance gate, enrichment, vector indexing), so backfilled articles are
indistinguishable from normally-collected ones. Safe to re-run: articles
upsert by URI.

Run from the tenant directory with its venv:
    .venv/bin/python scripts/catchup_outage_window.py --dry-run
    .venv/bin/python scripts/catchup_outage_window.py
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

WINDOW_START = datetime(2026, 7, 10)   # Jul 10 was already degraded late-day
WINDOW_END = datetime(2026, 7, 13)     # restart morning; overlap is deduped
CHUNK_SIZE = 6
# newsdata free tier ignores date filters; reddit/bluesky/firehose can't be
# back-searched this way — news APIs with real date windows only.
PROVIDERS = ("thenewsapi", "newsapi")
MAX_QUERIES_PER_PROVIDER = 85  # stay inside the 100/day quotas

OR_JOINER = {"newsapi": " OR ", "thenewsapi": " | "}

# Keywords that are already boolean expressions (TheNewsAPI |/+/() syntax)
# must go out verbatim, alone, and only to thenewsapi — quoting or OR-joining
# them builds garbage, and NewsAPI doesn't speak that syntax at all.
def _is_expression(kw: str) -> bool:
    return any(c in kw for c in '|()+"')


def _topic_priority(topic: str) -> int:
    t = topic.lower()
    if "brand" in t or any(b in t for b in ("wiley", "pearson", "sage", "elsevier")):
        return 0
    if any(w in t for w in ("publish", "licens", "peer review", "open science",
                            "expertise", "r&d")):
        return 1
    return 2


def _news_keywords_by_topic(db) -> dict:
    """topic -> list of keyword strings, news groups only (skip social-only)."""
    cur = db.get_connection().cursor()
    cur.execute(
        """
        SELECT mk.id, mk.keyword, kg.topic, COALESCE(kg.providers::text, '') AS providers
        FROM monitored_keywords mk
        LEFT JOIN keyword_groups kg ON mk.group_id = kg.id
        """
    )
    by_topic: dict = {}
    for kid, keyword, topic, providers in cur.fetchall():
        if not keyword or not topic:
            continue
        p = (providers or "").lower()
        if p and ("reddit" in p or "bluesky" in p) and "newsapi" not in p:
            continue  # social-only group
        by_topic.setdefault(topic, []).append((kid, keyword))
    return by_topic


def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def _in_window(article) -> bool:
    pub = article.get("published_date") or article.get("publication_date")
    try:
        pd = datetime.fromisoformat(str(pub)[:19].replace("Z", ""))
    except Exception:
        return True  # keep undated; relevance gate handles junk
    return WINDOW_START <= pd <= WINDOW_END


async def catchup(dry_run: bool = False) -> dict:
    from app.database import get_database_instance
    from app.tasks.keyword_monitor import KeywordMonitor, _strip_entity_prefix

    db = get_database_instance()
    km = KeywordMonitor(db)

    by_topic = _news_keywords_by_topic(db)
    n_kw = sum(len(v) for v in by_topic.values())
    n_queries = sum(-(-len(v) // CHUNK_SIZE) for v in by_topic.values())
    print(f"Topics: {len(by_topic)}, news keywords: {n_kw}, "
          f"queries per provider: {n_queries}, window: "
          f"{WINDOW_START.date()}..{WINDOW_END.date()}")

    collectors = {}
    for provider in PROVIDERS:
        try:
            collectors[provider] = km._create_collector(provider)
        except Exception as e:
            print(f"[{provider}] collector unavailable: {e}")
    collectors = {p: c for p, c in collectors.items() if c}

    summary = {"found": 0, "in_window": 0, "saved": 0, "by_provider": {},
               "by_topic": {}, "errors": []}
    queries_used = {p: 0 for p in collectors}

    for topic in sorted(by_topic, key=_topic_priority):
        kw_pairs = by_topic[topic]
        seen_urls = set()
        topic_articles = []   # raw collector dicts, tagged with _keyword_id

        plain, expressions = [], []
        for kid, kw in kw_pairs:
            term = _strip_entity_prefix(kw)
            (expressions if _is_expression(term) else plain).append((kid, term))

        # TheNewsAPI mishandles compound OR queries (returns 0 or unfiltered
        # junk — observed live 2026-07-13), so it gets one query per keyword,
        # exactly like the monitor's normal cycles. NewsAPI supports OR with
        # quotes, so it gets chunked queries to stretch its 100/day quota.
        planned = [([pair], ["thenewsapi"]) for pair in plain + expressions]
        planned += [(chunk, ["newsapi"]) for chunk in _chunks(plain, CHUNK_SIZE)]

        for pairs, providers in planned:
            keyword_id = pairs[0][0]
            terms = [t for _, t in pairs]
            for provider in providers:
                if provider not in collectors:
                    continue
                if queries_used[provider] >= MAX_QUERIES_PER_PROVIDER:
                    continue
                collector = collectors[provider]
                if len(terms) == 1:
                    query = terms[0]
                else:
                    query = OR_JOINER[provider].join(f'"{t}"' for t in terms)
                if dry_run:
                    print(f"  would query {provider} [{topic}]: {query}")
                    queries_used[provider] += 1
                    continue
                queries_used[provider] += 1
                try:
                    articles = await collector.search_articles(
                        query=query,
                        topic=topic,
                        max_results=100,
                        start_date=WINDOW_START,
                        end_date=WINDOW_END,
                        language="en",
                        sort_by="relevancy" if provider == "newsapi" else None,
                    )
                except Exception as e:
                    summary["errors"].append(f"{provider}/{topic}: {e}")
                    continue
                summary["found"] += len(articles or [])
                summary["by_provider"].setdefault(provider, 0)
                for a in articles or []:
                    url = (a.get("url") or "").strip()
                    if not url or url in seen_urls or not _in_window(a):
                        continue
                    seen_urls.add(url)
                    summary["by_provider"][provider] += 1
                    a["url"] = url
                    a["_keyword_id"] = keyword_id
                    topic_articles.append(a)
        if dry_run or not topic_articles:
            continue
        summary["in_window"] += len(topic_articles)

        # Step 1 — save raw articles to the DB exactly like check_keywords'
        # _save_articles_batch does. THIS is what lands them in `articles`;
        # the pipeline below only enriches/indexes them.
        inserted = 0
        for a in topic_articles:
            try:
                url = a["url"]
                exists = db.facade.article_exists((url,))
                new_a, alert_a, match_a = db.facade.create_article(
                    exists, url, a, topic, a["_keyword_id"])
                if new_a or alert_a or match_a:
                    inserted += 1
            except Exception as e:
                summary["errors"].append(f"save/{topic}/{a.get('url')}: {e}")
        summary["saved"] += inserted
        summary["by_topic"][topic] = inserted
        print(f"[{topic}] {len(topic_articles)} in-window, {inserted} saved → ingest pipeline")

        # Step 2 — enrichment/relevance/indexing via the monitor's own
        # pipeline (it maps url→uri etc. internally).
        try:
            topic_keywords = db.facade.get_monitored_keywords_for_topic((topic,))
            res = await km.auto_ingest_pipeline(
                topic_articles, topic, topic_keywords, suppress_notifications=True)
            print(f"[{topic}] pipeline: {res}")
        except Exception as e:
            summary["errors"].append(f"ingest/{topic}: {e}")
            print(f"[{topic}] ingest failed: {e}")

    summary["queries_used"] = queries_used
    print("\n=== catch-up summary ===")
    print(json.dumps(summary, indent=2, default=str))
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="Print planned queries without calling APIs.")
    args = ap.parse_args()
    asyncio.run(catchup(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
