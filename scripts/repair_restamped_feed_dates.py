"""Repair publication dates that a vendor's feed re-stamped.

The RSS collector now checks a same-minute batch of feed dates against the
Wayback Machine's first capture before storing (see
``app/collectors/rss_collector.bound_restamped_dates``). This applies the same
rule to rows stored before that check existed.

Scope: articles on the domains of vendors tracked by the Market Monitor
(``bw_vendor_identifiers.kind = 'domain'``), whose publication date is shared
to the minute by at least ``RSS_RESTAMP_MIN_ITEMS`` other articles from the
same source. Each is looked up once. Where the first capture is earlier than
the stored date by more than the tolerance, ``articles.publication_date`` is
set to the capture and the change is logged to a CSV. Nothing else is
touched.

Usage:
    .venv/bin/python scripts/repair_restamped_feed_dates.py            # dry run
    .venv/bin/python scripts/repair_restamped_feed_dates.py --apply
    .venv/bin/python scripts/repair_restamped_feed_dates.py --apply --csv out.csv
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.collectors import rss_collector as rc  # noqa: E402
from app.database import get_database_instance  # noqa: E402


def candidates(conn):
    return [dict(r) for r in conn.execute(text("""
        WITH domains AS (
            SELECT DISTINCT lower(normalized_value) AS domain
              FROM bw_vendor_identifiers
             WHERE kind = 'domain' AND valid_to IS NULL
        ),
        rows AS (
            SELECT a.uri, a.news_source, a.publication_date,
                   date_trunc('minute', a.publication_date::timestamptz) AS minute
              FROM articles a
             WHERE a.publication_date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T'
               AND EXISTS (
                   SELECT 1 FROM domains d
                    WHERE lower(regexp_replace(a.uri, '^https?://(www\\.)?([^/]+).*$', '\\2'))
                          IN (d.domain, 'www.' || d.domain))
        ),
        clusters AS (
            SELECT news_source, minute, COUNT(*) AS n
              FROM rows GROUP BY 1, 2 HAVING COUNT(*) >= :min_items
        )
        SELECT r.uri, r.news_source, r.publication_date, c.n AS batch_size
          FROM rows r JOIN clusters c
            ON c.news_source = r.news_source AND c.minute = r.minute
         ORDER BY r.news_source, r.publication_date, r.uri
    """), {"min_items": rc.RESTAMP_MIN_ITEMS}).mappings().all()]


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write the corrections")
    ap.add_argument("--csv", default="restamped_feed_dates.csv")
    ap.add_argument("--from-csv", help="apply the corrections in this CSV, "
                    "written by an earlier run, without looking anything up")
    args = ap.parse_args()

    if args.from_csv:
        with open(args.from_csv, newline="") as fh:
            changes = list(csv.DictReader(fh))
        print(f"{len(changes)} corrections read from {args.from_csv}")
        return _apply(changes) if args.apply else 0

    conn = get_database_instance()._temp_get_connection()
    try:
        rows = candidates(conn)
        # The lookups take an hour across a big batch. Release the read
        # transaction first, or the idle-in-transaction timeout closes the
        # connection long before the UPDATE runs.
        conn.commit()
        print(f"{len(rows)} articles in same-minute batches on tracked vendor domains")
        changes = []
        checked = 0
        for row in rows:
            feed_date = rc._to_datetime(row["publication_date"])
            try:
                capture = await rc.first_capture(row["uri"])
            except rc.LookupFailed:
                print(f"  lookup failed, skipped: {row['uri']}")
                continue
            checked += 1
            if capture is None:
                continue
            if capture <= feed_date - timedelta(days=rc.RESTAMP_TOLERANCE_DAYS):
                changes.append({
                    "uri": row["uri"], "news_source": row["news_source"],
                    "feed_date": row["publication_date"],
                    "first_capture": capture.isoformat(),
                    "batch_size": row["batch_size"],
                })
                print(f"  {row['news_source']}: {row['uri']}\n"
                      f"      feed {feed_date.date()} -> first captured {capture.date()}")
            await asyncio.sleep(0.2)
        print(f"checked {checked}, {len(changes)} dates to correct")

        with open(args.csv, "w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=[
                "uri", "news_source", "feed_date", "first_capture", "batch_size"])
            writer.writeheader()
            writer.writerows(changes)
        print(f"log written to {args.csv}")

        if args.apply and changes:
            return _apply(changes)
        elif changes:
            print("dry run: nothing written (use --apply)")
        return 0
    finally:
        conn.close()


def _apply(changes) -> int:
    """Write the corrections on a fresh connection, one short transaction."""
    conn = get_database_instance()._temp_get_connection()
    try:
        for ch in changes:
            conn.execute(text("""
                UPDATE articles SET publication_date = :d WHERE uri = :u
            """), {"d": ch["first_capture"], "u": ch["uri"]})
        conn.commit()
        print(f"applied {len(changes)} corrections")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
