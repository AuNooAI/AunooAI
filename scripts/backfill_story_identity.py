"""Label existing articles as copies and press releases.

Fills url_key, source_type and duplicate_of on rows that have none, oldest
first, so the first copy we saw stays the original. Safe to stop and rerun:
it only touches rows with no source_type. The keyword monitor runs the same
sweep after each check, so this is only needed once per site.

    .venv/bin/python scripts/backfill_story_identity.py [--topic NAME] [--dry-run]
    .venv/bin/python scripts/backfill_story_identity.py --sample 50   # links to check by eye
    .venv/bin/python scripts/backfill_story_identity.py --recheck     # after tightening the rule

Spec: docs/INGEST_DUPLICATES_AND_PRESS_RELEASES_SPEC.md
"""
import argparse
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from sqlalchemy import text  # noqa: E402

from app.database import Database  # noqa: E402
from app.services.story_identity import label_unlabelled, recheck_links  # noqa: E402


def sample(facade, n):
    rows = facade._fetchall_with_rollback(text(
        "SELECT c.topic, o.title, o.news_source, c.title, c.news_source "
        "FROM articles c JOIN articles o ON o.uri = c.duplicate_of "
        "WHERE c.url_key IS DISTINCT FROM o.url_key"), {})
    rows = list(rows or [])
    random.seed(int(os.getenv("SAMPLE_SEED", "1")))
    for r in random.sample(rows, min(n, len(rows))):
        print(f"[{r[0]}]\n  original: {r[1]}  ({r[2]})\n  copy:     {r[3]}  ({r[4]})")
    print(f"\n{len(rows)} title-matched links in total; showed {min(n, len(rows))}")


class OneConnection:
    """The three facade calls label_unlabelled makes, on one connection.

    The facade opens a pooled connection and commits for every statement,
    which ran the backfill at ~15 rows a second (four hours on bugfixing).
    One connection, committed once per batch, labels the same way.
    """

    def __init__(self, engine):
        self.conn = engine.connect()

    def _fetchone_with_rollback(self, stmt, params=None):
        return self.conn.execute(stmt, params or {}).fetchone()

    def _fetchall_with_rollback(self, stmt, params=None):
        return self.conn.execute(stmt, params or {}).fetchall()

    def _execute_with_rollback(self, stmt, params=None):
        return self.conn.execute(stmt, params or {})

    def commit(self):
        self.conn.commit()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic")
    ap.add_argument("--batch", type=int, default=2000)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sample", type=int, help="print N title-matched links and exit")
    ap.add_argument("--recheck", action="store_true",
                    help="clear title links the current rule no longer makes, then exit")
    args = ap.parse_args()

    facade = Database().facade
    if args.sample:
        sample(facade, args.sample)
        return

    if args.recheck:
        db = OneConnection(Database._pg_engine_instance or facade.db._temp_get_connection().engine)
        after, checked, cleared = "", 0, 0
        while True:
            st = recheck_links(db, limit=args.batch, after_uri=after)
            db.commit()
            checked += st["checked"]
            cleared += st["cleared"]
            print(f"{checked} links checked, {cleared} cleared", flush=True)
            if st["checked"] < args.batch:
                return
            after = st["last"]

    batch_db = OneConnection(Database._pg_engine_instance or facade.db._temp_get_connection().engine)
    totals = {"labelled": 0, "copies": 0, "press_releases": 0}
    start = time.time()
    while True:
        stats = label_unlabelled(batch_db, limit=args.batch, topic=args.topic, dry_run=args.dry_run)
        batch_db.commit()
        for k in totals:
            totals[k] += stats[k]
        print(f"{totals['labelled']} rows, {totals['copies']} copies, "
              f"{totals['press_releases']} press releases, {time.time() - start:.0f}s", flush=True)
        if args.dry_run:
            for uri, title, dup in stats["links"][:20]:
                print(f"  {title[:80]!r}\n    copy of {dup}")
            break
        if stats["labelled"] < args.batch:
            break


if __name__ == "__main__":
    main()
