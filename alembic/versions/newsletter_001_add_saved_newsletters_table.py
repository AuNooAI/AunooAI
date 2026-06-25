"""Add saved_newsletters table

Adds saved_newsletters table for storing generated newsletter instances.
Follows the same pattern as saved_dashboards.

Revision ID: newsletter_001
Revises: sio_001
Create Date: 2025-11-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'newsletter_001'
down_revision: Union[str, None] = 'sio_001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create saved_newsletters table
    op.create_table(
        'saved_newsletters',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('topic', sa.String(255), nullable=False),
        sa.Column('username', sa.Text(), nullable=True),

        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),

        # Configuration used to generate
        sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('days_back', sa.Integer(), nullable=True),
        sa.Column('deep_dive_topic', sa.String(255), nullable=True),

        # Generated content
        sa.Column('newsletter_content', sa.Text(), nullable=False),
        sa.Column('deep_dive_analysis', sa.Text(), nullable=True),

        # Metadata
        sa.Column('articles_used', sa.Integer(), nullable=True),
        sa.Column('article_uris', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('model_used', sa.String(100), nullable=True),

        # Timestamps with timezone
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),

        # Foreign key and constraints
        sa.ForeignKeyConstraint(['username'], ['users.username'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('topic', 'username', 'name', name='uq_saved_newsletters_topic_user_name')
    )

    # Standard indexes
    op.create_index('idx_saved_newsletters_topic', 'saved_newsletters', ['topic'])
    op.create_index('idx_saved_newsletters_user', 'saved_newsletters', ['username'])
    op.create_index('idx_saved_newsletters_created', 'saved_newsletters', ['created_at'], postgresql_ops={'created_at': 'DESC'})

    # PostgreSQL GIN index on JSONB config
    op.create_index(
        'idx_saved_newsletters_config_gin',
        'saved_newsletters',
        ['config'],
        postgresql_using='gin'
    )

    # PostgreSQL full-text search index
    op.execute("""
        CREATE INDEX idx_saved_newsletters_search
        ON saved_newsletters USING GIN (
            to_tsvector('english', coalesce(name, '') || ' ' || coalesce(description, ''))
        );
    """)

    # Create trigger function for auto-updating updated_at
    op.execute("""
        CREATE OR REPLACE FUNCTION update_saved_newsletters_timestamp()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Create trigger
    op.execute("""
        CREATE TRIGGER trigger_saved_newsletters_updated_at
        BEFORE UPDATE ON saved_newsletters
        FOR EACH ROW
        EXECUTE FUNCTION update_saved_newsletters_timestamp();
    """)


def downgrade() -> None:
    # Drop trigger and function
    op.execute("DROP TRIGGER IF EXISTS trigger_saved_newsletters_updated_at ON saved_newsletters;")
    op.execute("DROP FUNCTION IF EXISTS update_saved_newsletters_timestamp();")

    # Drop indexes
    op.drop_index('idx_saved_newsletters_search', 'saved_newsletters')
    op.drop_index('idx_saved_newsletters_config_gin', 'saved_newsletters')
    op.drop_index('idx_saved_newsletters_created', 'saved_newsletters')
    op.drop_index('idx_saved_newsletters_user', 'saved_newsletters')
    op.drop_index('idx_saved_newsletters_topic', 'saved_newsletters')

    # Drop table
    op.drop_table('saved_newsletters')
