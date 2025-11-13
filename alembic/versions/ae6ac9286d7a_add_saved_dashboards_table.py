"""add_saved_dashboards_table

Adds saved_dashboards table for storing Trend Convergence dashboard instances.
Includes PostgreSQL-specific features: JSONB, TEXT[], triggers, and indexes.

Revision ID: ae6ac9286d7a
Revises: tc_ref_articles_001
Create Date: 2025-11-13 09:46:01.198138

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'ae6ac9286d7a'
down_revision: Union[str, None] = 'tc_ref_articles_001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create saved_dashboards table
    op.create_table(
        'saved_dashboards',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('topic', sa.String(255), nullable=False),
        sa.Column('username', sa.Text(), nullable=True),

        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),

        # PostgreSQL JSONB for configuration
        sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=False),

        # PostgreSQL TEXT[] array for article URIs
        sa.Column('article_uris', postgresql.ARRAY(sa.Text()), nullable=False),

        # PostgreSQL JSONB for tab data caching
        sa.Column('consensus_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('strategic_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('timeline_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('signals_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('horizons_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),

        # Timestamps with timezone
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('last_accessed_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),

        # Additional metadata
        sa.Column('profile_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('articles_analyzed', sa.Integer(), nullable=True),
        sa.Column('model_used', sa.String(100), nullable=True),

        # Foreign key and constraints
        sa.ForeignKeyConstraint(['username'], ['users.username'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('topic', 'username', 'name', name='uq_saved_dashboards_topic_user_name')
    )

    # Standard indexes
    op.create_index('idx_saved_dashboards_topic', 'saved_dashboards', ['topic'])
    op.create_index('idx_saved_dashboards_user', 'saved_dashboards', ['username'])
    op.create_index('idx_saved_dashboards_created', 'saved_dashboards', ['created_at'], postgresql_ops={'created_at': 'DESC'})

    # PostgreSQL GIN index on JSONB config
    op.create_index(
        'idx_saved_dashboards_config_gin',
        'saved_dashboards',
        ['config'],
        postgresql_using='gin'
    )

    # PostgreSQL full-text search index
    op.execute("""
        CREATE INDEX idx_saved_dashboards_search
        ON saved_dashboards USING GIN (
            to_tsvector('english', coalesce(name, '') || ' ' || coalesce(description, ''))
        );
    """)

    # Create trigger function for auto-updating updated_at
    op.execute("""
        CREATE OR REPLACE FUNCTION update_saved_dashboards_timestamp()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Create trigger
    op.execute("""
        CREATE TRIGGER trigger_saved_dashboards_updated_at
        BEFORE UPDATE ON saved_dashboards
        FOR EACH ROW
        EXECUTE FUNCTION update_saved_dashboards_timestamp();
    """)


def downgrade() -> None:
    # Drop trigger and function
    op.execute("DROP TRIGGER IF EXISTS trigger_saved_dashboards_updated_at ON saved_dashboards;")
    op.execute("DROP FUNCTION IF EXISTS update_saved_dashboards_timestamp();")

    # Drop indexes
    op.drop_index('idx_saved_dashboards_search', 'saved_dashboards')
    op.drop_index('idx_saved_dashboards_config_gin', 'saved_dashboards')
    op.drop_index('idx_saved_dashboards_created', 'saved_dashboards')
    op.drop_index('idx_saved_dashboards_user', 'saved_dashboards')
    op.drop_index('idx_saved_dashboards_topic', 'saved_dashboards')

    # Drop table
    op.drop_table('saved_dashboards')
