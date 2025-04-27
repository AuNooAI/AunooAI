#!/usr/bin/env python
# flake8: noqa
"""Re-index all existing articles into ChromaDB.

Run with:
$ python scripts/reindex_chromadb.py

Optional arguments:
    --limit N   Only re-index first N rows (for testing).

The script fetches *articles* joined with *raw_articles* (if present) from the
SQLite database and calls *app.vector_store.upsert_article* for each row.
"""

import argparse
import logging
import sqlite3
from pathlib import Path
import sys

# Ensure .env variables are loaded *before* any application modules that may
# read from os.environ during import time (e.g. vector_store).
from dotenv import load_dotenv  # type: ignore

load_dotenv()

# Ensure project root (parent of scripts/) is on PYTHONPATH so that 'app'
# package is importable even when this script is executed directly.
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Now we can import application modules
from app.config.settings import DATABASE_DIR  # type: ignore
from app.vector_store import upsert_article, get_chroma_client
from app.database import Database

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def iter_articles(db: Database, limit: int | None = None):
    """Yield article dicts including *raw_markdown* when available."""
    query = (
        """
        SELECT a.*, r.raw_markdown AS raw
        FROM articles a
        LEFT JOIN raw_articles r ON a.uri = r.uri
        ORDER BY a.rowid
        """
    )
    if limit:
        query += " LIMIT ?"
        params = (limit,)
    else:
        params = ()

    with db.get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(query, params)
        for row in cur.fetchall():
            yield dict(row)


def main():
    parser = argparse.ArgumentParser(description="Re-index articles into ChromaDB")
    parser.add_argument("--limit", type=int, help="Re-index only first N articles")
    args = parser.parse_args()

    # Ensure database exists
    db_path = Path(DATABASE_DIR) / Database.get_active_database()
    if not db_path.exists():
        logger.error("Active database not found at %s", db_path)
        return 1

    db = Database()

    client = get_chroma_client()
    client.delete_collection("articles")       # drop current index

    total = 0
    for article in iter_articles(db, args.limit):
        try:
            upsert_article(article)
            total += 1
        except Exception as exc:  # pragma: no cover – keep going
            logger.warning(
                "Failed to index %s: %s",
                article.get("uri"),
                exc,
            )
    logger.info("Indexed %s article(s) into Chroma", total)
    return 0


if __name__ == "__main__":
    raise SystemExit(main()) 