"""Entity intelligence — examined-article marker and durable policy claims

Revision ID: ei_004
Revises: ei_003
Create Date: 2026-08-25

Two scheduling defects, both of the same kind: work that never finishes because
nothing records that it was done.

**Articles examined and matched to nothing were re-examined forever.** The
ingest backlog asked for articles with no entity content link. An article that
genuinely names no vendor never gets one, so it stayed in the answer set and
was re-scanned on every collection run — 2,400 examinations to produce twelve
links, the same few hundred articles going round. ``bw_entity_link_attempts``
records that an article was looked at and by which matcher version, so a
routine run skips it and a matcher upgrade re-examines it deliberately.

**Vendor selection had no memory.** The collector took the first twenty vendors
by ``sort_order`` on every pass, so the same nineteen were refreshed
indefinitely and sixty-four were never collected at all. ``bw_entity_source_
policies`` already exists to hold per-vendor scheduling state; it needs a claim
column so two overlapping scheduler passes cannot select the same vendor, and
an attempt counter so a failing vendor backs off instead of hot-looping.
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'ei_004'
down_revision = 'ei_003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # "We looked at this article and it named nobody."
    # ------------------------------------------------------------------
    # Keyed by matcher version so that widening the query terms re-examines
    # the corpus on purpose, rather than the backlog being permanently sealed.
    op.execute("""CREATE TABLE IF NOT EXISTS bw_entity_link_attempts (
        article_uri     TEXT NOT NULL REFERENCES articles(uri) ON DELETE CASCADE,
        matcher_version VARCHAR(32) NOT NULL,
        examined_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        links_found     INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (article_uri, matcher_version)
    )""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_entity_link_attempts_at
        ON bw_entity_link_attempts (examined_at)""")

    # ------------------------------------------------------------------
    # Durable claims and backoff on the per-vendor scheduling state.
    # ------------------------------------------------------------------
    op.execute("""ALTER TABLE bw_entity_source_policies
        ADD COLUMN IF NOT EXISTS claimed_at TIMESTAMPTZ,
        ADD COLUMN IF NOT EXISTS claimed_by TEXT,
        ADD COLUMN IF NOT EXISTS consecutive_failures INTEGER NOT NULL DEFAULT 0,
        ADD COLUMN IF NOT EXISTS last_error TEXT,
        ADD COLUMN IF NOT EXISTS eligible BOOLEAN NOT NULL DEFAULT TRUE,
        ADD COLUMN IF NOT EXISTS ineligible_reason TEXT""")

    # The picker's ordering, as an index: due first, never-collected before
    # long-ago-collected, then priority, then a stable id.
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_entity_policy_pick
        ON bw_entity_source_policies
           (source, next_due_at NULLS FIRST, last_success_at NULLS FIRST,
            priority DESC, brand_id)
        WHERE enabled AND eligible""")
    # Finding claims that outlived their run.
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_entity_policy_claimed
        ON bw_entity_source_policies (claimed_at)
        WHERE claimed_at IS NOT NULL""")

    # ------------------------------------------------------------------
    # Which vendors a run asked the provider for.
    # ------------------------------------------------------------------
    # A batch that succeeds with zero records still means those vendors were
    # processed, and their policies must advance. Without this the run ledger
    # cannot say who was requested, so an empty-but-successful batch would
    # leave every vendor in it permanently due.
    op.execute("""ALTER TABLE bw_collection_runs
        ADD COLUMN IF NOT EXISTS requested_brand_ids INTEGER[]""")


def downgrade() -> None:
    op.execute("""ALTER TABLE bw_collection_runs
        DROP COLUMN IF EXISTS requested_brand_ids""")
    op.execute("DROP INDEX IF EXISTS ix_bw_entity_policy_claimed")
    op.execute("DROP INDEX IF EXISTS ix_bw_entity_policy_pick")
    op.execute("""ALTER TABLE bw_entity_source_policies
        DROP COLUMN IF EXISTS claimed_at,
        DROP COLUMN IF EXISTS claimed_by,
        DROP COLUMN IF EXISTS consecutive_failures,
        DROP COLUMN IF EXISTS last_error,
        DROP COLUMN IF EXISTS eligible,
        DROP COLUMN IF EXISTS ineligible_reason""")
    op.execute("DROP TABLE IF EXISTS bw_entity_link_attempts")
