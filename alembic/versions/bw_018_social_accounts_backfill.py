"""Backfill social_accounts (Account Profiles) on tenants whose alembic chain
skipped bw_007_social_accounts (bugfixing/bwtemplate lineage). Guarded with
IF NOT EXISTS so it is a no-op where bw_007 already created the table
(wileytest, wbm).

Revision ID: bw_018_social_accounts_backfill
Revises: bw_017_signals_xnet
"""

from alembic import op

revision = 'bw_018_social_accounts_backfill'
down_revision = 'bw_017_signals_xnet'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS social_accounts (
            id SERIAL PRIMARY KEY,
            platform TEXT NOT NULL,
            handle TEXT NOT NULL,
            handle_canonical TEXT NOT NULL,
            display_name TEXT,
            avatar_url TEXT,
            bio TEXT,
            profile_url TEXT,
            verified BOOLEAN,
            followers_count INTEGER,
            following_count INTEGER,
            posts_count INTEGER,
            account_created_at TEXT,
            topics JSONB,
            post_sentiment JSONB,
            summary TEXT,
            brand_context TEXT,
            sample_posts JSONB,
            tags JSONB,
            annotation JSONB,
            last_profiled_at TEXT,
            created_at TEXT
        )
    """)
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint
                           WHERE conname = 'uq_social_accounts_platform_handle') THEN
                ALTER TABLE social_accounts
                    ADD CONSTRAINT uq_social_accounts_platform_handle
                    UNIQUE (platform, handle_canonical);
            END IF;
        END $$;
    """)


def downgrade() -> None:
    # Deliberately a no-op: on bw_007-lineage tenants the table predates this
    # migration and must not be dropped.
    pass
