"""Convert pgvector columns from 1536d (OpenAI) to 768d (local DeBERTa)

Revision ID: emb_768_01
Revises: kg_social_01
Create Date: 2026-08-02

Brings canonical in line with the local-embeddings migration already completed on
wileytest (see that tenant's docs/LOCAL_EMBEDDINGS_MIGRATION_PLAN.md, and its
emb_001). This is the same DDL, re-parented onto canonical's head — canonical's
chain never carried emb_001, so this is a new revision rather than a cherry-pick.

The 1536d data is dropped, not converted. A 1536d vector cannot be cast to 768d,
and the values are OpenAI-space anyway, so they are meaningless once the encoder
changes. Before applying this, the existing vectors were copied to
`articles_embedding_1536_backup` (uri, embedding) so the downgrade path is not
purely theoretical.

  - articles.embedding: 51,526 of 193,202 rows populated. Re-embedded from
    scratch by the backfill task, newest-first.
  - emerging_topics / cluster_snapshots centroids are derived from article
    embeddings and are recomputed by the emerging-topics pipeline.

The HNSW index is intentionally NOT recreated here. It is rebuilt after the
backfill completes, because one bulk build is far cheaper than maintaining the
index across ~193k UPDATEs. Use scripts/embedding_768_postbackfill.py, which is
idempotent and verifies dimension, row counts, and index presence.

2026-08-19: upgrade() is unchanged and must stay unchanged — this revision has
been applied on bugfixing, wiley, wileytest, and wbm, so rewriting what it did
would make the recorded history a lie. Only downgrade() was corrected: it used
to add an empty vector(1536) column and call that a rollback, which looks like a
successful restore and is not one. It now restores from
articles_embedding_1536_backup, and refuses to run at all where that table does
not exist. See emb_768_02 for the forward repair and
docs/EMBEDDING_768_MIGRATION_RUNBOOK.md for the operator sequence.
"""
from alembic import op

# revision identifiers
revision = 'emb_768_01'
down_revision = 'kg_social_01'
branch_labels = None
depends_on = None


def upgrade():
    # articles.embedding: drop index + column, re-add at 768d (index rebuilt post-backfill)
    op.execute("DROP INDEX IF EXISTS articles_embedding_hnsw_idx")
    op.execute("ALTER TABLE articles DROP COLUMN IF EXISTS embedding")
    op.execute("ALTER TABLE articles ADD COLUMN embedding vector(768)")

    # Derived centroids — drop + re-add at 768d (pipeline recomputes)
    op.execute("ALTER TABLE emerging_topics DROP COLUMN IF EXISTS centroid_embedding")
    op.execute("ALTER TABLE emerging_topics ADD COLUMN centroid_embedding vector(768)")

    op.execute("ALTER TABLE cluster_snapshots DROP COLUMN IF EXISTS centroid_embedding")
    op.execute("ALTER TABLE cluster_snapshots ADD COLUMN centroid_embedding vector(768)")


def downgrade():
    """Restore the 1536d article vectors from the verified backup.

    Refuses to run without that backup. An empty vector(1536) column is not a
    rollback — it is the same outage as having no column at all, dressed as a
    valid schema, and it would be discovered only when search started returning
    nothing.
    """
    bind = op.get_bind()

    # The backup has to live beside the articles table being downgraded, not
    # merely somewhere on the search_path — otherwise a same-named table in
    # another schema would be mistaken for this one's backup.
    backup = bind.exec_driver_sql("""
        SELECT c.oid FROM pg_class c
        WHERE c.relname = 'articles_embedding_1536_backup'
          AND c.relnamespace = (
              SELECT relnamespace FROM pg_class WHERE oid = to_regclass('articles')
          )
    """).scalar()
    if backup is None:
        raise RuntimeError(
            "Cannot downgrade emb_768_01: articles_embedding_1536_backup does "
            "not exist in this database, so the original 1536d OpenAI vectors "
            "are unrecoverable. Restore that table from a database backup taken "
            "before emb_768_01 was applied, then re-run this downgrade. "
            "See docs/EMBEDDING_768_MIGRATION_RUNBOOK.md."
        )

    expected = bind.exec_driver_sql(
        "SELECT COUNT(*) FROM articles_embedding_1536_backup WHERE embedding IS NOT NULL"
    ).scalar()

    # Derived centroids are recomputed by the pipeline, so they only need the
    # right shape.
    op.execute("ALTER TABLE cluster_snapshots DROP COLUMN IF EXISTS centroid_embedding")
    op.execute("ALTER TABLE cluster_snapshots ADD COLUMN centroid_embedding vector(1536)")

    op.execute("ALTER TABLE emerging_topics DROP COLUMN IF EXISTS centroid_embedding")
    op.execute("ALTER TABLE emerging_topics ADD COLUMN centroid_embedding vector(1536)")

    # Drop the index that belongs to *this* articles table. A bare
    # "DROP INDEX IF EXISTS articles_embedding_hnsw_idx" resolves through the
    # search_path, so under a non-default search_path it can drop the index of
    # a same-named table in another schema. That is not hypothetical: it took
    # out the live index during a sandboxed test run on 2026-08-19.
    op.execute("""
        DO $$
        DECLARE target oid;
        BEGIN
            SELECT c.oid INTO target FROM pg_class c
            WHERE c.relname = 'articles_embedding_hnsw_idx'
              AND c.relnamespace = (
                  SELECT relnamespace FROM pg_class WHERE oid = to_regclass('articles')
              );
            IF target IS NOT NULL THEN
                EXECUTE 'DROP INDEX ' || target::regclass::text;
            END IF;
        END $$;
    """)
    op.execute("ALTER TABLE articles DROP COLUMN IF EXISTS embedding")
    op.execute("ALTER TABLE articles ADD COLUMN embedding vector(1536)")

    op.execute("""
        UPDATE articles a
        SET embedding = b.embedding
        FROM articles_embedding_1536_backup b
        WHERE a.uri = b.uri AND b.embedding IS NOT NULL
    """)

    restored = bind.exec_driver_sql(
        "SELECT COUNT(*) FROM articles WHERE embedding IS NOT NULL"
    ).scalar()
    if restored != expected:
        raise RuntimeError(
            f"Downgrade restored {restored} of {expected} backed-up vectors. "
            "Rolling back rather than leaving a partially restored index; the "
            "usual cause is articles deleted since the backup was taken. "
            "Reconcile articles_embedding_1536_backup against articles, then "
            "re-run."
        )

    op.execute(
        "CREATE INDEX articles_embedding_hnsw_idx ON articles "
        "USING hnsw (embedding vector_cosine_ops) WITH (m='16', ef_construction='64')"
    )
