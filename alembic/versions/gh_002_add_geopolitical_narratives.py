"""Add geopolitical narratives table for strategic intelligence briefings

Revision ID: gh_002
Revises: gh_001
Create Date: 2026-01-25

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 'gh_002'
down_revision = 'gh_001'
branch_labels = None
depends_on = None


def upgrade():
    # Create geopolitical_narratives table - LLM-generated strategic briefings
    op.create_table(
        'geopolitical_narratives',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('narrative_text', sa.Text(), nullable=False),
        sa.Column('executive_summary', sa.Text(), nullable=True),
        sa.Column('regional_analysis', sa.Text(), nullable=True),
        sa.Column('emerging_threats', sa.Text(), nullable=True),
        sa.Column('outlook', sa.Text(), nullable=True),
        sa.Column('hotspot_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('article_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('top_regions', postgresql.JSONB(), nullable=True),
        sa.Column('top_categories', postgresql.JSONB(), nullable=True),
        sa.Column('risk_breakdown', postgresql.JSONB(), nullable=True),
        sa.Column('model_used', sa.String(100), nullable=True),
        sa.Column('topic', sa.Text(), nullable=True),
        sa.Column('generated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_index('idx_geopolitical_narratives_generated', 'geopolitical_narratives', ['generated_at'])
    op.create_index('idx_geopolitical_narratives_topic', 'geopolitical_narratives', ['topic'])


def downgrade():
    op.drop_table('geopolitical_narratives')
