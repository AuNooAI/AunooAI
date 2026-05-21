"""add forecast assessment tables

Revision ID: fa_001
Revises: ce_001
Create Date: 2026-05-21 10:00:00.000000

Backs the Forecast Assessment feature: given a stored future_horizons_runs
row, score each scenario against post-forecast articles.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'fa_001'
down_revision: Union[str, None] = 'ce_001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'forecast_assessments',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('run_id', sa.String(36), nullable=False),
        sa.Column('topic', sa.Text(), nullable=False),
        sa.Column('assessed_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('evidence_count', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('scenarios_count', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('ambiguous_count', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('unrelated_count', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('surprises', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('summary', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('status', sa.String(32), nullable=False, server_default=sa.text("'completed'")),
        sa.Column('mode', sa.String(32), nullable=False, server_default=sa.text("'live'")),
        sa.Column('model_used', sa.String(100), nullable=True),
        sa.Column('runtime_seconds', sa.Float(), nullable=True),
        sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_index('ix_forecast_assessments_run_id', 'forecast_assessments', ['run_id'])
    op.create_index('ix_forecast_assessments_topic_assessed', 'forecast_assessments', ['topic', 'assessed_at'])

    op.create_table(
        'forecast_scenario_verdicts',
        sa.Column('id', sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column('assessment_id', sa.String(36), nullable=False),
        sa.Column('scenario_idx', sa.Integer(), nullable=False),
        sa.Column('horizon_type', sa.String(4), nullable=False),
        sa.Column('scenario_title', sa.Text(), nullable=False),
        sa.Column('verdict_label', sa.String(32), nullable=False),
        sa.Column('directional_rate', sa.Float(), nullable=True),
        sa.Column('velocity', sa.Float(), nullable=True),
        sa.Column('milestone_density', sa.Float(), nullable=True),
        sa.Column('coverage', sa.Float(), nullable=True),
        sa.Column('supports', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('contradicts', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('neutral', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('summary_md', sa.Text(), nullable=True),
        sa.Column('top_articles', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.UniqueConstraint('assessment_id', 'scenario_idx', name='uq_scenario_verdicts_assessment_scenario'),
    )
    op.create_index('ix_scenario_verdicts_assessment', 'forecast_scenario_verdicts', ['assessment_id'])

    op.create_table(
        'forecast_article_verdicts',
        sa.Column('id', sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column('assessment_id', sa.String(36), nullable=False),
        sa.Column('article_uri', sa.Text(), nullable=False),
        sa.Column('scenario_idx', sa.Integer(), nullable=True),
        sa.Column('verdict', sa.String(48), nullable=False),
        sa.Column('evidence_type', sa.String(24), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('rerank_score', sa.Float(), nullable=True),
        sa.Column('margin', sa.Float(), nullable=True),
        sa.Column('best_alt_scenario_idx', sa.Integer(), nullable=True),
        sa.Column('rationale', sa.Text(), nullable=True),
        sa.Column('article_date', sa.Text(), nullable=True),
        sa.Column('recorded_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_index('ix_article_verdicts_assessment_scenario', 'forecast_article_verdicts', ['assessment_id', 'scenario_idx'])
    op.create_index('ix_article_verdicts_assessment_uri', 'forecast_article_verdicts', ['assessment_id', 'article_uri'])


def downgrade() -> None:
    op.drop_index('ix_article_verdicts_assessment_uri', table_name='forecast_article_verdicts')
    op.drop_index('ix_article_verdicts_assessment_scenario', table_name='forecast_article_verdicts')
    op.drop_table('forecast_article_verdicts')

    op.drop_index('ix_scenario_verdicts_assessment', table_name='forecast_scenario_verdicts')
    op.drop_table('forecast_scenario_verdicts')

    op.drop_index('ix_forecast_assessments_topic_assessed', table_name='forecast_assessments')
    op.drop_index('ix_forecast_assessments_run_id', table_name='forecast_assessments')
    op.drop_table('forecast_assessments')
