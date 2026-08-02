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
index across ~193k UPDATEs.
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
    # Schema-reversible. Article vectors can be restored from
    # articles_embedding_1536_backup if it still exists; centroids are recomputed.
    op.execute("ALTER TABLE cluster_snapshots DROP COLUMN IF EXISTS centroid_embedding")
    op.execute("ALTER TABLE cluster_snapshots ADD COLUMN centroid_embedding vector(1536)")

    op.execute("ALTER TABLE emerging_topics DROP COLUMN IF EXISTS centroid_embedding")
    op.execute("ALTER TABLE emerging_topics ADD COLUMN centroid_embedding vector(1536)")

    op.execute("ALTER TABLE articles DROP COLUMN IF EXISTS embedding")
    op.execute("ALTER TABLE articles ADD COLUMN embedding vector(1536)")
    op.execute(
        "CREATE INDEX articles_embedding_hnsw_idx ON articles "
        "USING hnsw (embedding vector_cosine_ops) WITH (m='16', ef_construction='64')"
    )
