"""Verify the 768d embedding migration and rebuild its index if missing

Revision ID: emb_768_02
Revises: et_007
Create Date: 2026-08-19

emb_768_01 has already been applied on every tenant (bugfixing, wiley,
wileytest, wbm as of 2026-08-19), so it cannot be rewritten. This is the forward
repair for the two things it left unfinished.

1. It dropped the HNSW index and left rebuilding it to a manual step. If that
   step is skipped, every semantic search falls back to a sequential scan over
   the whole articles table and simply gets slow — no error, no log line. This
   revision creates the index when it is missing.

2. It never verified anything. This revision checks that articles.embedding is
   vector(768) and reports how much of the table is populated, so a half-done
   backfill is visible at deploy time rather than as thin search results later.

It deliberately does NOT create an empty articles_embedding_1536_backup on
tenants that lack one. An empty backup table would make the emb_768_01 downgrade
look possible when the original vectors are gone. Where the backup is missing,
the downgrade path fails loudly instead — which is the honest answer.

The index build here is a plain CREATE INDEX inside the migration transaction,
which locks writes to articles for the duration. For a live tenant, build it
first with scripts/embedding_768_postbackfill.py (CREATE INDEX CONCURRENTLY, no
write lock) and this revision will find it already there and do nothing.
"""
import logging

from alembic import op

logger = logging.getLogger('alembic.runtime.migration')

# revision identifiers, used by Alembic.
revision = 'emb_768_02'
down_revision = 'et_007'
branch_labels = None
depends_on = None

EXPECTED_DIM = 768
INDEX_NAME = 'articles_embedding_hnsw_idx'


def upgrade() -> None:
    bind = op.get_bind()

    # Resolved through to_regclass so the check lands on the same articles
    # table the rest of this migration writes to, whatever the search_path is.
    dimension = bind.exec_driver_sql("""
        SELECT format_type(a.atttypid, a.atttypmod)
        FROM pg_attribute a
        WHERE a.attrelid = to_regclass('articles') AND a.attname = 'embedding'
    """).scalar()

    if dimension is None:
        raise RuntimeError(
            "articles.embedding does not exist. emb_768_01 should have created "
            "it; run that revision first."
        )
    if dimension != f"vector({EXPECTED_DIM})":
        raise RuntimeError(
            f"articles.embedding is {dimension}, expected vector({EXPECTED_DIM}). "
            "The encoder writes 768d vectors and inserts will fail against any "
            "other width. Fix the column before continuing — see "
            "docs/EMBEDDING_768_MIGRATION_RUNBOOK.md."
        )

    total, populated = bind.exec_driver_sql(
        "SELECT COUNT(*), COUNT(embedding) FROM articles"
    ).fetchone()
    logger.info(
        "emb_768_02: articles.embedding is vector(%s); %s of %s rows populated",
        EXPECTED_DIM, populated, total,
    )
    if total and populated == 0:
        logger.warning(
            "emb_768_02: no article has an embedding yet. Semantic search will "
            "return nothing until app/tasks/embedding_backfill.py has run."
        )

    index_exists = bind.exec_driver_sql(f"""
        SELECT c.oid FROM pg_class c
        WHERE c.relname = '{INDEX_NAME}'
          AND c.relnamespace = (
              SELECT relnamespace FROM pg_class WHERE oid = to_regclass('articles')
          )
    """).scalar()
    if index_exists:
        logger.info("emb_768_02: %s already present", INDEX_NAME)
        return

    logger.info(
        "emb_768_02: %s missing — building it now (writes to articles are "
        "blocked for the duration)", INDEX_NAME,
    )
    op.execute(
        f"CREATE INDEX {INDEX_NAME} ON articles "
        "USING hnsw (embedding vector_cosine_ops) WITH (m='16', ef_construction='64')"
    )


def downgrade() -> None:
    # Verification leaves nothing to undo. The index is not dropped: it is what
    # emb_768_01 was always supposed to end with, and dropping it would only
    # make searches slow.
    pass
