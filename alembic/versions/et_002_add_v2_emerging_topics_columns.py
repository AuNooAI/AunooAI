"""Add v2 LLM-driven columns to emerging_topics

Revision ID: et_002
Revises: et_001
Create Date: 2026-01-09

This migration adds new columns for v2 LLM-driven emerging topic detection:
- Deep analysis fields: actors, events, implications, signals, synthesis
- Trend scoring: volume_score, velocity_score, diversity_score, novelty_score, composite_score
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic
revision = 'et_002'
down_revision = 'et_001'
branch_labels = None
depends_on = None


def upgrade():
    # Add deep analysis JSONB columns
    op.add_column('emerging_topics', sa.Column('actors', postgresql.JSONB, nullable=True))
    op.add_column('emerging_topics', sa.Column('events', postgresql.JSONB, nullable=True))
    op.add_column('emerging_topics', sa.Column('implications', postgresql.JSONB, nullable=True))
    op.add_column('emerging_topics', sa.Column('signals', postgresql.JSONB, nullable=True))
    op.add_column('emerging_topics', sa.Column('synthesis', postgresql.JSONB, nullable=True))

    # Add trend scoring columns
    op.add_column('emerging_topics', sa.Column('volume_score', sa.Float, nullable=True))
    op.add_column('emerging_topics', sa.Column('velocity_score', sa.Float, nullable=True))
    op.add_column('emerging_topics', sa.Column('diversity_score', sa.Float, nullable=True))
    op.add_column('emerging_topics', sa.Column('novelty_score', sa.Float, nullable=True))
    op.add_column('emerging_topics', sa.Column('composite_score', sa.Float, nullable=True))

    # Add index for composite score for sorting
    op.create_index('ix_emerging_topics_composite_score', 'emerging_topics', ['composite_score'])


def downgrade():
    # Drop index
    op.drop_index('ix_emerging_topics_composite_score', table_name='emerging_topics')

    # Drop trend scoring columns
    op.drop_column('emerging_topics', 'composite_score')
    op.drop_column('emerging_topics', 'novelty_score')
    op.drop_column('emerging_topics', 'diversity_score')
    op.drop_column('emerging_topics', 'velocity_score')
    op.drop_column('emerging_topics', 'volume_score')

    # Drop deep analysis columns
    op.drop_column('emerging_topics', 'synthesis')
    op.drop_column('emerging_topics', 'signals')
    op.drop_column('emerging_topics', 'implications')
    op.drop_column('emerging_topics', 'events')
    op.drop_column('emerging_topics', 'actors')
