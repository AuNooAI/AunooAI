#!/usr/bin/env python3
"""Import articles from one SQLite DB to another.

Usage (from repo root):

    python scripts/import_articles.py --source fnaapp_new.db --target app/data/fnaapp.db

By default existing rows in *target* (matched on primary-key/unique columns) are
left untouched (INSERT OR IGNORE).  Pass ``--replace`` to overwrite them.
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
from pathlib import Path
from typing import List, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

BATCH_SIZE = 500  # tune for memory/perf trade-off


def _get_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    """Return column names for *table* using PRAGMA table_info."""
    cur = conn.execute(f"PRAGMA table_info({table})")
    return [row[1] for row in cur]  # type: ignore[index]


def _prepare_insert_statement(columns: List[str], replace: bool) -> str:
    placeholder = ", ".join(["?"] * len(columns))
    cols = ", ".join(columns)
    verb = "REPLACE" if replace else "IGNORE"
    return f"INSERT OR {verb} INTO articles ({cols}) VALUES ({placeholder})"


def copy_articles(source_db: Path, target_db: Path, replace: bool = False) -> None:
    if not source_db.exists():
        raise FileNotFoundError(f"Source DB not found: {source_db}")
    if not target_db.exists():
        raise FileNotFoundError(f"Target DB not found: {target_db}")

    with sqlite3.connect(source_db) as src_conn, sqlite3.connect(target_db) as tgt_conn:
        src_conn.row_factory = sqlite3.Row

        src_cols = _get_columns(src_conn, "articles")
        tgt_cols = _get_columns(tgt_conn, "articles")

        shared_cols = [c for c in tgt_cols if c in src_cols]
        extra_cols = [c for c in tgt_cols if c not in src_cols]

        logger.info("Source columns: %s", src_cols)
        logger.info("Target columns: %s", tgt_cols)
        logger.info("Shared columns: %s", shared_cols)
        logger.info("Extra target-only columns will be set to NULL: %s", extra_cols)

        insert_sql = _prepare_insert_statement(tgt_cols, replace)
        logger.debug("Insert statement: %s", insert_sql)

        # Fetch rows in iterable chunks
        total_inserted = 0
        offset = 0
        while True:
            rows = src_conn.execute(
                f"SELECT {', '.join(shared_cols)} FROM articles LIMIT {BATCH_SIZE} OFFSET {offset}"
            ).fetchall()
            if not rows:
                break

            records: List[Tuple] = []
            for row in rows:
                # build full row aligned to tgt_cols order
                record = []
                for col in tgt_cols:
                    if col in src_cols:
                        record.append(row[col])
                    else:
                        record.append(None)  # default for extra cols
                records.append(tuple(record))

            tgt_conn.executemany(insert_sql, records)
            tgt_conn.commit()

            inserted_batch = tgt_conn.total_changes - total_inserted
            total_inserted += inserted_batch
            logger.info("Processed %s rows (%s new/updated)", offset + len(rows), inserted_batch)

            offset += BATCH_SIZE

        logger.info("Finished. Total new/updated rows: %s", total_inserted)


def main() -> None:
    parser = argparse.ArgumentParser(description="Copy articles between SQLite DBs")
    parser.add_argument("--source", required=True, help="Path to source DB (fnaapp_new.db)")
    parser.add_argument("--target", required=True, help="Path to target DB (app/data/fnaapp.db)")
    parser.add_argument(
        "--replace",
        action="store_true",
        help="If set, replace existing rows in target (INSERT OR REPLACE). Otherwise ignore duplicates.",
    )
    args = parser.parse_args()

    copy_articles(Path(args.source), Path(args.target), replace=args.replace)


if __name__ == "__main__":
    main() 