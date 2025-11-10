"""Add reference article tables for all trend convergence dashboards

Revision ID: tc_ref_articles_001
Revises:
Create Date: 2025-01-10

This migration adds junction tables to store reference articles for all five
Trend Convergence dashboard types:
- Consensus Analysis
- Strategic Recommendations
- Market Signals & Strategic Risks
- Impact Timeline
- Future Horizons
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'tc_ref_articles_001'
down_revision = ('2def6319d8d6', 'auto_regenerate_001')  # Merge from both heads
branch_labels = None
depends_on = None


def upgrade():
    # Create consensus_reference_articles
    op.create_table(
        'consensus_reference_articles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('consensus_id', sa.String(36), nullable=False),
        sa.Column('article_uri', sa.String(), nullable=True),
        sa.Column('topic', sa.String(), nullable=False),
        sa.Column('retrieved_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['article_uri'], ['articles.uri'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_consensus_ref_articles_consensus_id', 'consensus_reference_articles', ['consensus_id'])
    op.create_index('ix_consensus_ref_articles_topic', 'consensus_reference_articles', ['topic'])

    # Create strategic_recommendation_articles
    op.create_table(
        'strategic_recommendation_articles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('recommendation_id', sa.String(36), nullable=False),
        sa.Column('article_uri', sa.String(), nullable=True),
        sa.Column('topic', sa.String(), nullable=False),
        sa.Column('retrieved_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['article_uri'], ['articles.uri'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_strategic_rec_articles_recommendation_id', 'strategic_recommendation_articles', ['recommendation_id'])
    op.create_index('ix_strategic_rec_articles_topic', 'strategic_recommendation_articles', ['topic'])

    # Create market_signal_articles
    op.create_table(
        'market_signal_articles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('signal_id', sa.String(36), nullable=False),
        sa.Column('article_uri', sa.String(), nullable=True),
        sa.Column('topic', sa.String(), nullable=False),
        sa.Column('retrieved_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['article_uri'], ['articles.uri'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_market_signal_articles_signal_id', 'market_signal_articles', ['signal_id'])
    op.create_index('ix_market_signal_articles_topic', 'market_signal_articles', ['topic'])

    # Create impact_timeline_articles
    op.create_table(
        'impact_timeline_articles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('timeline_id', sa.String(36), nullable=False),
        sa.Column('article_uri', sa.String(), nullable=True),
        sa.Column('topic', sa.String(), nullable=False),
        sa.Column('retrieved_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['article_uri'], ['articles.uri'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_impact_timeline_articles_timeline_id', 'impact_timeline_articles', ['timeline_id'])
    op.create_index('ix_impact_timeline_articles_topic', 'impact_timeline_articles', ['topic'])

    # Create future_horizon_articles
    op.create_table(
        'future_horizon_articles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('horizon_id', sa.String(36), nullable=False),
        sa.Column('article_uri', sa.String(), nullable=True),
        sa.Column('topic', sa.String(), nullable=False),
        sa.Column('retrieved_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['article_uri'], ['articles.uri'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_future_horizon_articles_horizon_id', 'future_horizon_articles', ['horizon_id'])
    op.create_index('ix_future_horizon_articles_topic', 'future_horizon_articles', ['topic'])


def downgrade():
    # Drop tables in reverse order
    op.drop_table('future_horizon_articles')
    op.drop_table('impact_timeline_articles')
    op.drop_table('market_signal_articles')
    op.drop_table('strategic_recommendation_articles')
    op.drop_table('consensus_reference_articles')
