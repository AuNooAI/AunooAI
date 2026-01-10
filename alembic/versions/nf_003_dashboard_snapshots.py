"""Add newsfeed dashboard snapshots table for persisting auto-generated dashboards

Revision ID: nf_003
Revises: nf_002
Create Date: 2026-01-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers
revision = 'nf_003'
down_revision = 'nf_002'
branch_labels = None
depends_on = None


def upgrade():
    # Create table for storing auto-generated newsfeed dashboard snapshots
    op.create_table(
        'newsfeed_dashboard_snapshots',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('topic', sa.String(255), nullable=True),  # NULL = all topics
        sa.Column('generated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('persona', sa.String(100), nullable=False, server_default='CEO'),
        sa.Column('model', sa.String(100), nullable=False, server_default='gpt-4o-mini'),

        # Briefing data (six articles)
        sa.Column('briefing_articles', JSONB, nullable=True),
        sa.Column('briefing_generated', sa.Boolean, server_default=sa.text('false'), nullable=False),

        # Highlights data
        sa.Column('highlights_data', JSONB, nullable=True),
        sa.Column('highlights_generated', sa.Boolean, server_default=sa.text('false'), nullable=False),

        # Narratives data
        sa.Column('narratives_data', JSONB, nullable=True),
        sa.Column('narratives_generated', sa.Boolean, server_default=sa.text('false'), nullable=False),

        # Metadata
        sa.Column('articles_analyzed', sa.Integer, nullable=True),
        sa.Column('generation_duration_seconds', sa.Float, nullable=True),
        sa.Column('error_message', sa.Text, nullable=True),

        # Indexes
        sa.Index('idx_nf_snapshots_topic', 'topic'),
        sa.Index('idx_nf_snapshots_generated', 'generated_at'),
    )

    # Add constraint: only one snapshot per topic (most recent wins)
    # We'll handle this in code by deleting old snapshots when creating new ones


def downgrade():
    op.drop_table('newsfeed_dashboard_snapshots')
