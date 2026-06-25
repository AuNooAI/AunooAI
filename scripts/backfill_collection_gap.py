#!/usr/bin/env python3
"""Backfill the article-collection gap detected by detect_collection_gap.py.

Reads ``data/wiley_horizons/collection_gap.json`` and re-runs collection for
that window, reusing the live ``KeywordMonitor`` machinery (same collectors,
same relevance + enrichment + save path via auto_ingest) so backfilled
articles are indistinguishable from normally-collected ones.

Best-effort by source: ArXiv / Semantic Scholar support full historical
ranges; news APIs only reach back ~30 days (so a 2–4-week-old gap is
borderline); RSS exposes only current items and is unrecoverable. The script
records how many it recovered back into collection_gap.json.

Run from a tenant directory:
    python scripts/backfill_collection_gap.py --dry-run      # plan only
    python scripts/backfill_collection_gap.py                # execute

Safe to re-run: articles upsert by URI, so duplicates are ignored.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

GAP_PATH = "data/wiley_horizons/collection_gap.json"


def _load_gap() -> dict:
    with open(GAP_PATH) as f:
        return json.load(f)


def _parse(d: str) -> datetime:
    return datetime.fromisoformat(str(d)[:10])


async def backfill(*, dry_run: bool = False, max_per_keyword: int = 50) -> dict:
    from app.database import get_database_instance
    from app.tasks.keyword_monitor import KeywordMonitor

    gap = _load_gap()
    if not gap.get("detected"):
        print("No gap detected in collection_gap.json — nothing to backfill.")
        return {"recovered": 0}

    start = _parse(gap["start"])
    end = _parse(gap["end"])
    print(f"Backfill window: {start.date()} → {end.date()} ({gap.get('days')} days)")

    db = get_database_instance()
    km = KeywordMonitor(db)
    km.page_size = max(km.page_size, max_per_keyword)

    raw_providers = db.facade.get_keyword_monitoring_providers()
    if isinstance(raw_providers, str):
        try:
            providers = json.loads(raw_providers)
        except Exception:
            providers = [raw_providers]
    else:
        providers = list(raw_providers or [])
    print(f"Providers: {providers}")

    keywords = db.facade.get_monitored_keywords() or []
    print(f"Monitored keywords: {len(keywords)}")

    def _f(row, key, default=""):
        # SQLAlchemy Row supports mapping access by key; dict does too.
        try:
            return row[key]
        except Exception:
            try:
                return row._mapping.get(key, default)
            except Exception:
                return default

    recovered_by_source: dict = {p: 0 for p in providers}
    total_saved = 0

    for kw in keywords:
        keyword_text = _f(kw, "keyword")
        topic = _f(kw, "topic") or ""
        if not keyword_text:
            continue
        for provider in providers:
            try:
                collector = km._create_collector(provider)
            except Exception as e:
                print(f"  [{provider}] collector unavailable: {e}")
                continue
            if collector is None:
                continue
            if dry_run:
                print(f"  would search {provider} · '{keyword_text}' · {topic} "
                      f"[{start.date()}..{end.date()}]")
                continue
            try:
                # signature: _search_with_collector(provider, collector, keyword, topic, start_date)
                articles = await km._search_with_collector(
                    provider, collector, keyword_text, topic, start)
            except Exception as e:
                print(f"  [{provider}] '{keyword_text}' search failed: {e}")
                continue
            # Bound to the gap window's upper edge.
            in_window = []
            for a in articles or []:
                pub = a.get("published_date") or a.get("publication_date")
                try:
                    pd = datetime.fromisoformat(str(pub)[:19].replace("Z", ""))
                except Exception:
                    pd = None
                if pd is None or (start <= pd <= end):
                    in_window.append(a)
            if not in_window:
                continue
            # auto_ingest.process_articles_batch expects the AUTO-INGEST keys
            # (uri / news_source), not the raw collector keys (url / source).
            # Mirror keyword_monitor's own formatting exactly. Skip articles
            # the collector returned without a usable URL — they'd fail the
            # raw_articles FK with uri='unknown'.
            formatted = []
            for a in in_window:
                uri = a.get("url") or a.get("uri") or ""
                if not uri:
                    continue
                formatted.append({
                    "uri": uri,
                    "title": a.get("title", ""),
                    "news_source": a.get("source") or provider,
                    "publication_date": a.get("published_date", a.get("publication_date", "")),
                    "summary": a.get("summary", ""),
                    "content": a.get("content", ""),
                    "topic": topic,
                    "analyzed": False,
                })
            if not formatted:
                continue
            try:
                res = await km.auto_ingest_service.process_articles_batch(
                    formatted, topic, [keyword_text])
                saved = (res or {}).get("saved", 0)
                recovered_by_source[provider] = recovered_by_source.get(provider, 0) + saved
                total_saved += saved
                if saved:
                    print(f"  [{provider}] '{keyword_text}' → {saved} saved")
            except Exception as e:
                print(f"  [{provider}] ingest failed for '{keyword_text}': {e}")

    print(f"\nTotal recovered: {total_saved}")
    if not dry_run:
        gap["n_recovered"] = total_saved
        gap["n_recovered_by_source"] = recovered_by_source
        gap["backfilled_at"] = datetime.utcnow().isoformat()
        with open(GAP_PATH, "w") as f:
            json.dump(gap, f, indent=2)
        print(f"Updated {GAP_PATH}")
    return {"recovered": total_saved, "by_source": recovered_by_source}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="List what would be searched without collecting.")
    ap.add_argument("--max-per-keyword", type=int, default=50)
    args = ap.parse_args()
    asyncio.run(backfill(dry_run=args.dry_run, max_per_keyword=args.max_per_keyword))


if __name__ == "__main__":
    main()
