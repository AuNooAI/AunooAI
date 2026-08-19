#!/usr/bin/env python3
"""Verify the 768d embedding column and build its HNSW index, safely and repeatedly.

Run this after the encoder backfill has populated articles.embedding. It is
idempotent: every step checks the current state first, so re-running it on a
healthy database changes nothing and exits 0.

What it checks and does:

1. articles.embedding is vector(768). Anything else is fatal — the encoder
   writes 768d and inserts against another width fail.
2. How many rows are populated, reported as a percentage so a half-finished
   backfill is obvious.
3. articles_embedding_hnsw_idx exists, with vector_cosine_ops. If it is
   missing, it is built with CREATE INDEX CONCURRENTLY on an autocommit
   connection, so writes to articles keep working during the build.
4. A representative nearest-neighbour query actually uses the index, checked
   with EXPLAIN under planner settings that make a sequential scan expensive
   enough to be rejected.

Usage:
    python scripts/embedding_768_postbackfill.py            # check and repair
    python scripts/embedding_768_postbackfill.py --check    # report only
"""

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from app.database import get_database_instance  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("embedding_768_postbackfill")

EXPECTED_DIM = 768
INDEX_NAME = "articles_embedding_hnsw_idx"
# Enough of the table populated that the index is worth having and the EXPLAIN
# check is meaningful.
MIN_POPULATED_FOR_PLAN_CHECK = 1000


def _connection():
    return get_database_instance()._temp_get_connection()


def check_dimension(conn) -> str:
    dimension = conn.execute(text("""
        SELECT format_type(a.atttypid, a.atttypmod)
        FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        WHERE c.relname = 'articles' AND a.attname = 'embedding'
    """)).scalar()

    if dimension is None:
        raise SystemExit(
            "FAIL articles.embedding does not exist. Run `alembic upgrade head`."
        )
    if dimension != f"vector({EXPECTED_DIM})":
        raise SystemExit(
            f"FAIL articles.embedding is {dimension}, expected vector({EXPECTED_DIM}). "
            "Do not backfill against this column — every insert would fail."
        )
    logger.info("OK   articles.embedding is %s", dimension)
    return dimension


def check_population(conn) -> int:
    total, populated = conn.execute(
        text("SELECT COUNT(*), COUNT(embedding) FROM articles")
    ).fetchone()
    if not total:
        logger.warning("WARN articles is empty; nothing to index")
        return 0
    pct = 100.0 * populated / total
    level = logger.info if pct >= 90 else logger.warning
    level(
        "%s %s of %s articles have an embedding (%.1f%%)",
        "OK  " if pct >= 90 else "WARN", populated, total, pct,
    )
    if pct < 90:
        logger.warning(
            "     The backfill has not finished. Semantic search only sees the "
            "populated rows until it does."
        )
    return populated


def index_present(conn) -> bool:
    definition = conn.execute(text("""
        SELECT indexdef FROM pg_indexes
        WHERE tablename = 'articles' AND indexname = :name
    """), {"name": INDEX_NAME}).scalar()

    if not definition:
        return False
    if "vector_cosine_ops" not in definition:
        raise SystemExit(
            f"FAIL {INDEX_NAME} exists but is not a cosine index:\n  {definition}\n"
            "The pipeline searches with the <=> cosine operator, which this "
            "index cannot serve. Drop it and re-run."
        )
    logger.info("OK   %s present (%s)", INDEX_NAME, "hnsw, vector_cosine_ops")
    return True


def build_index() -> None:
    """CREATE INDEX CONCURRENTLY on its own autocommit connection.

    CONCURRENTLY cannot run inside a transaction block, and SQLAlchemy opens one
    implicitly, hence the explicit autocommit isolation level.
    """
    logger.info("     building %s concurrently — this can take a while", INDEX_NAME)
    conn = _connection()
    try:
        raw = conn._connection.execution_options(isolation_level="AUTOCOMMIT")
        raw.execute(text(
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {INDEX_NAME} ON articles "
            "USING hnsw (embedding vector_cosine_ops) "
            "WITH (m='16', ef_construction='64')"
        ))
        logger.info("OK   %s built", INDEX_NAME)
    finally:
        conn.close()


def check_query_plan(conn, populated: int) -> None:
    """Prove a nearest-neighbour query uses the index, not a sequential scan."""
    if populated < MIN_POPULATED_FOR_PLAN_CHECK:
        logger.warning(
            "SKIP query-plan check: only %s rows populated; the planner will "
            "prefer a sequential scan on a table this small either way.",
            populated,
        )
        return

    probe = conn.execute(text(
        "SELECT embedding FROM articles WHERE embedding IS NOT NULL LIMIT 1"
    )).scalar()

    # A sequential scan is always *possible*; discourage it so the check
    # measures whether the index is usable rather than what the planner
    # happens to prefer today.
    conn.execute(text("SET LOCAL enable_seqscan = off"))
    plan = conn.execute(text("""
        EXPLAIN (FORMAT TEXT)
        SELECT uri FROM articles
        WHERE embedding IS NOT NULL
        ORDER BY embedding <=> CAST(:probe AS vector)
        LIMIT 10
    """), {"probe": str(probe)}).fetchall()

    plan_text = "\n".join(row[0] for row in plan)
    if INDEX_NAME in plan_text:
        logger.info("OK   nearest-neighbour query uses %s", INDEX_NAME)
    else:
        logger.warning(
            "WARN nearest-neighbour query did not use %s. Plan was:\n%s",
            INDEX_NAME, plan_text,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true",
        help="report only; do not build a missing index",
    )
    args = parser.parse_args()

    conn = _connection()
    try:
        check_dimension(conn)
        populated = check_population(conn)
        present = index_present(conn)
    finally:
        conn.close()

    if not present:
        if args.check:
            logger.warning(
                "WARN %s is missing. Re-run without --check to build it.",
                INDEX_NAME,
            )
            return 1
        build_index()

    conn = _connection()
    try:
        if not index_present(conn):
            logger.error("FAIL %s still missing after the build", INDEX_NAME)
            return 1
        check_query_plan(conn, populated)
    finally:
        conn.close()

    logger.info("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
