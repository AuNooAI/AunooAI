"""Backfill the image of each vendor LinkedIn post already collected.

Until 2026-08-29 the collector dropped the post's image URL
(``market_collect._post_social_meta``). Bright Data keeps a finished snapshot
for a while and the snapshot ids are on ``bw_collection_runs.job_id``, so the
earlier runs can be downloaded again — no new collection, no new charge — and
the image put on the row that was made from the same post.

Dry by default: prints how many posts would get an image. ``--apply`` writes
``social_meta.image_url`` on rows that have none.

    .venv/bin/python scripts/backfill_post_images.py --market 2 [--apply]
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402


def _load_env() -> None:
    """The DB and Bright Data settings, from .env, without sourcing it."""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if not os.path.exists(path):
        return
    for line in open(path):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", type=int, required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    _load_env()

    from app.database import get_database_instance
    from app.services.brightdata_linkedin import (LinkedInDatasetClient, api_key,
                                                  map_company_post)

    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        snapshots = [r[0] for r in conn.execute(text("""
            SELECT DISTINCT job_id FROM bw_collection_runs
             WHERE market_id = :m AND source = 'linkedin_company_post'
               AND status = 'succeeded' AND job_id IS NOT NULL
        """), {"m": args.market}).fetchall()]
    finally:
        # The downloads take minutes; an idle connection is dropped meanwhile.
        conn.close()
    print(f"snapshots on record: {len(snapshots)}")
    client = LinkedInDatasetClient(api_key())
    images = {}
    raw_total = 0
    for sid in snapshots:
        try:
            records = asyncio.run(client.fetch_snapshot(sid))
        except Exception as exc:  # noqa: BLE001 — an expired snapshot is expected
            print(f"  {sid}: not available ({str(exc)[:80]})")
            continue
        raw_total += len(records)
        with_image = 0
        for raw in records:
            m = map_company_post(raw)
            if m and m.get("url") and m.get("image_url"):
                images.setdefault(m["url"], m["image_url"])
                with_image += 1
        print(f"  {sid}: {len(records)} posts, {with_image} with an image")
    print(f"raw posts: {raw_total}; distinct posts with an image: {len(images)}")
    if not images:
        return 0
    conn = db._temp_get_connection()
    try:
        rows = conn.execute(text("""
            SELECT uri FROM articles
             WHERE uri = ANY(:uris)
               AND (social_meta IS NULL OR jsonb_typeof(social_meta) <> 'object'
                    OR social_meta->>'image_url' IS NULL)
        """), {"uris": list(images)}).fetchall()
        targets = [r[0] for r in rows]
        print(f"stored posts matching, without an image yet: {len(targets)}")
        if not args.apply:
            print("dry run; add --apply to write")
            return 0
        n = 0
        for uri in targets:
            conn.execute(text("""
                UPDATE articles
                   SET social_meta = COALESCE(CASE WHEN jsonb_typeof(social_meta) = 'object'
                                                   THEN social_meta END, '{}'::jsonb)
                                     || jsonb_build_object('image_url', :img)
                 WHERE uri = :uri
            """), {"img": images[uri], "uri": uri})
            n += 1
        conn.commit()
        print(f"updated: {n}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
