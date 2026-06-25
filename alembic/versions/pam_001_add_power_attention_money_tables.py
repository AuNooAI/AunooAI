"""Add Power, Attention & Money (PAM) dashboard tables

Revision ID: pam_001
Revises: sr_001
Create Date: 2025-12-13

This migration adds tables for tracking:
- PAM analysis runs (comprehensive analysis of power, attention, money flows)
- 2030 trend snapshots (daily tracking of 5 key trends)
- Tracked entities (publishers, tech companies, institutions)
- Metrics time series (historical tracking)
- Financial events (M&A, funding, partnerships)
- Regulatory events (legislation, rulings, enforcement)
- Saved PAM dashboards
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision = 'pam_001'
down_revision = 'sr_001'
branch_labels = None
depends_on = None


def upgrade():
    # PAM Analysis Runs - main analysis output storage
    op.create_table(
        'pam_analysis_runs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('username', sa.Text, sa.ForeignKey('users.username', ondelete='SET NULL'), nullable=True),
        sa.Column('topic', sa.String(255), nullable=True),
        sa.Column('topic_id', sa.Integer, nullable=True),

        # Analysis configuration
        sa.Column('analysis_type', sa.String(50), nullable=False),  # 'comprehensive', 'power', 'attention', 'money'
        sa.Column('entity_type', sa.String(50), default='publisher'),  # 'publisher', 'tech_company', etc
        sa.Column('time_horizon', sa.String(50), default='1_year'),
        sa.Column('trend_focus', postgresql.JSONB, default='["T1", "T2", "T3", "T4", "T5"]'),

        # Composite scores (0-100)
        sa.Column('power_score', sa.Float, nullable=True),
        sa.Column('attention_score', sa.Float, nullable=True),
        sa.Column('money_score', sa.Float, nullable=True),
        sa.Column('overall_score', sa.Float, nullable=True),
        sa.Column('threat_level', sa.String(20), nullable=True),  # 'low', 'moderate', 'elevated', 'high', 'critical'

        # Detailed breakdowns
        sa.Column('power_analysis', postgresql.JSONB, nullable=True),
        sa.Column('attention_analysis', postgresql.JSONB, nullable=True),
        sa.Column('money_analysis', postgresql.JSONB, nullable=True),
        sa.Column('trend_analysis', postgresql.JSONB, nullable=True),

        # Strategic output
        sa.Column('executive_summary', sa.Text, nullable=True),
        sa.Column('key_events', postgresql.JSONB, nullable=True),
        sa.Column('emerging_signals', postgresql.JSONB, nullable=True),
        sa.Column('strategic_recommendations', postgresql.JSONB, nullable=True),
        sa.Column('scenario_analysis', postgresql.JSONB, nullable=True),

        # Full raw output
        sa.Column('raw_output', postgresql.JSONB, nullable=True),

        # Sources
        sa.Column('articles_analyzed', sa.Integer, default=0),
        sa.Column('article_uris', postgresql.ARRAY(sa.Text), nullable=True),
        sa.Column('data_sources', postgresql.JSONB, nullable=True),

        # Processing metadata
        sa.Column('model_used', sa.String(100), nullable=True),
        sa.Column('analysis_duration_seconds', sa.Float, nullable=True),
        sa.Column('config', postgresql.JSONB, nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime, nullable=True),
    )
    op.create_index('ix_pam_analysis_runs_user', 'pam_analysis_runs', ['username'])
    op.create_index('ix_pam_analysis_runs_topic', 'pam_analysis_runs', ['topic'])
    op.create_index('ix_pam_analysis_runs_type', 'pam_analysis_runs', ['analysis_type'])
    op.create_index('ix_pam_analysis_runs_created', 'pam_analysis_runs', ['created_at'])
    op.create_index('ix_pam_analysis_runs_threat', 'pam_analysis_runs', ['threat_level'])

    # PAM Trend Snapshots - daily tracking of 2030 trends
    op.create_table(
        'pam_trend_snapshots',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('snapshot_date', sa.Date, nullable=False),
        sa.Column('topic', sa.String(255), nullable=True),  # NULL = global snapshot

        # Trend scores (0-100)
        sa.Column('t1_invisible_llm', sa.Float, nullable=True),
        sa.Column('t2_agentic_ai', sa.Float, nullable=True),
        sa.Column('t3_seo_geo_decline', sa.Float, nullable=True),
        sa.Column('t4_regulatory', sa.Float, nullable=True),
        sa.Column('t5_consolidation', sa.Float, nullable=True),

        # Trend velocities
        sa.Column('t1_velocity', sa.String(20), nullable=True),  # 'accelerating', 'stable', 'decelerating'
        sa.Column('t2_velocity', sa.String(20), nullable=True),
        sa.Column('t3_velocity', sa.String(20), nullable=True),
        sa.Column('t4_velocity', sa.String(20), nullable=True),
        sa.Column('t5_velocity', sa.String(20), nullable=True),

        # Detailed trend data
        sa.Column('trend_details', postgresql.JSONB, nullable=True),
        sa.Column('key_events', postgresql.JSONB, nullable=True),
        sa.Column('emerging_signals', postgresql.JSONB, nullable=True),

        # Sources
        sa.Column('articles_analyzed', sa.Integer, default=0),
        sa.Column('data_sources', postgresql.JSONB, nullable=True),

        # Metadata
        sa.Column('model_used', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index('ix_pam_trend_snapshots_date', 'pam_trend_snapshots', ['snapshot_date'])
    op.create_index('ix_pam_trend_snapshots_topic', 'pam_trend_snapshots', ['topic'])
    op.create_unique_constraint('uq_pam_trend_snapshot_date_topic', 'pam_trend_snapshots', ['snapshot_date', 'topic'])

    # PAM Entities - tracked publishers, tech companies, institutions
    op.create_table(
        'pam_entities',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('entity_name', sa.String(255), nullable=False),
        sa.Column('entity_type', sa.String(50), nullable=False),  # 'publisher', 'tech_company', 'research_institution', 'government'
        sa.Column('entity_subtype', sa.String(100), nullable=True),  # e.g., 'academic_publisher', 'big_tech', 'startup'

        # Core PAM scores (0-100)
        sa.Column('power_score', sa.Float, nullable=True),
        sa.Column('attention_score', sa.Float, nullable=True),
        sa.Column('money_score', sa.Float, nullable=True),
        sa.Column('overall_influence', sa.Float, nullable=True),

        # Publisher-specific: Three Pillars Assessment
        sa.Column('trust_pillar_score', sa.Float, nullable=True),
        sa.Column('infrastructure_pillar_score', sa.Float, nullable=True),
        sa.Column('connector_pillar_score', sa.Float, nullable=True),
        sa.Column('pillar_details', postgresql.JSONB, nullable=True),

        # Position assessment
        sa.Column('strategic_position', sa.String(50), nullable=True),  # 'trust_provider', 'infrastructure_provider', 'connector', 'commodity'
        sa.Column('threat_exposure', sa.Float, nullable=True),  # 0-100 vulnerability to AI disruption
        sa.Column('opportunity_score', sa.Float, nullable=True),  # 0-100 potential for positive adaptation

        # Detailed analysis
        sa.Column('strengths', postgresql.JSONB, nullable=True),
        sa.Column('vulnerabilities', postgresql.JSONB, nullable=True),
        sa.Column('strategic_recommendations', postgresql.JSONB, nullable=True),

        # Metadata
        sa.Column('metadata', postgresql.JSONB, nullable=True),
        sa.Column('data_sources', postgresql.JSONB, nullable=True),
        sa.Column('last_analyzed', sa.DateTime, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('ix_pam_entities_name', 'pam_entities', ['entity_name'])
    op.create_index('ix_pam_entities_type', 'pam_entities', ['entity_type'])
    op.create_index('ix_pam_entities_influence', 'pam_entities', ['overall_influence'])
    op.create_unique_constraint('uq_pam_entities_name_type', 'pam_entities', ['entity_name', 'entity_type'])

    # PAM Metrics Time Series - historical tracking of entity metrics
    op.create_table(
        'pam_metrics_timeseries',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('entity_id', sa.String(36), sa.ForeignKey('pam_entities.id', ondelete='CASCADE'), nullable=True),
        sa.Column('entity_name', sa.String(255), nullable=True),  # For ad-hoc metrics without entity
        sa.Column('metric_date', sa.Date, nullable=False),

        # Metric data
        sa.Column('metric_name', sa.String(100), nullable=False),
        sa.Column('metric_value', sa.Float, nullable=False),
        sa.Column('metric_category', sa.String(50), nullable=True),  # 'power', 'attention', 'money'
        sa.Column('metric_unit', sa.String(50), nullable=True),  # 'percent', 'count', 'usd', etc.

        # Context
        sa.Column('metadata', postgresql.JSONB, nullable=True),
        sa.Column('source', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index('ix_pam_metrics_entity', 'pam_metrics_timeseries', ['entity_id'])
    op.create_index('ix_pam_metrics_date', 'pam_metrics_timeseries', ['metric_date'])
    op.create_index('ix_pam_metrics_name', 'pam_metrics_timeseries', ['metric_name'])
    op.create_index('ix_pam_metrics_category', 'pam_metrics_timeseries', ['metric_category'])

    # PAM Financial Events - M&A, funding, partnerships
    op.create_table(
        'pam_financial_events',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('event_date', sa.Date, nullable=False),
        sa.Column('event_type', sa.String(50), nullable=False),  # 'acquisition', 'merger', 'funding', 'ipo', 'partnership', 'licensing_deal'

        # Parties involved
        sa.Column('acquirer', sa.String(255), nullable=True),
        sa.Column('acquirer_type', sa.String(50), nullable=True),
        sa.Column('target', sa.String(255), nullable=True),
        sa.Column('target_type', sa.String(50), nullable=True),
        sa.Column('parties', postgresql.JSONB, nullable=True),  # Full list of parties for complex deals

        # Financial details
        sa.Column('deal_value_usd', sa.BigInteger, nullable=True),
        sa.Column('funding_round', sa.String(50), nullable=True),  # 'seed', 'series_a', etc.
        sa.Column('valuation_usd', sa.BigInteger, nullable=True),
        sa.Column('financial_details', postgresql.JSONB, nullable=True),

        # Analysis
        sa.Column('headline', sa.Text, nullable=True),
        sa.Column('summary', sa.Text, nullable=True),
        sa.Column('strategic_significance', sa.Text, nullable=True),
        sa.Column('pam_implications', postgresql.JSONB, nullable=True),
        sa.Column('trend_relevance', postgresql.JSONB, nullable=True),  # Which T1-T5 trends this affects

        # Scores
        sa.Column('market_impact_score', sa.Float, nullable=True),  # 0-100
        sa.Column('consolidation_indicator', sa.Float, nullable=True),  # 0-100 contribution to T5

        # Sources
        sa.Column('source_articles', postgresql.JSONB, nullable=True),
        sa.Column('news_sources', postgresql.JSONB, nullable=True),

        # Metadata
        sa.Column('verified', sa.Boolean, default=False),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index('ix_pam_financial_events_date', 'pam_financial_events', ['event_date'])
    op.create_index('ix_pam_financial_events_type', 'pam_financial_events', ['event_type'])
    op.create_index('ix_pam_financial_events_acquirer', 'pam_financial_events', ['acquirer'])
    op.create_index('ix_pam_financial_events_target', 'pam_financial_events', ['target'])
    op.create_index('ix_pam_financial_events_value', 'pam_financial_events', ['deal_value_usd'])

    # PAM Regulatory Events - legislation, rulings, enforcement
    op.create_table(
        'pam_regulatory_events',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('event_date', sa.Date, nullable=False),

        # Event details
        sa.Column('jurisdiction', sa.String(100), nullable=False),  # 'EU', 'US', 'China', 'UK', 'Global'
        sa.Column('regulation_name', sa.String(255), nullable=True),
        sa.Column('regulation_type', sa.String(100), nullable=True),  # 'ai_governance', 'copyright', 'data_protection', 'antitrust'
        sa.Column('event_type', sa.String(50), nullable=False),  # 'enacted', 'proposed', 'amended', 'ruling', 'enforcement', 'guidance'

        # Content
        sa.Column('headline', sa.Text, nullable=True),
        sa.Column('summary', sa.Text, nullable=True),
        sa.Column('key_provisions', postgresql.JSONB, nullable=True),

        # Impact analysis
        sa.Column('publisher_implications', sa.Text, nullable=True),
        sa.Column('tech_implications', sa.Text, nullable=True),
        sa.Column('researcher_implications', sa.Text, nullable=True),
        sa.Column('compliance_requirements', postgresql.JSONB, nullable=True),

        # Trend relevance
        sa.Column('t4_impact_score', sa.Float, nullable=True),  # 0-100 impact on regulatory trend
        sa.Column('other_trend_impacts', postgresql.JSONB, nullable=True),

        # Status tracking
        sa.Column('status', sa.String(50), nullable=True),  # 'active', 'pending', 'draft', 'superseded'
        sa.Column('effective_date', sa.Date, nullable=True),
        sa.Column('deadline_date', sa.Date, nullable=True),

        # Sources
        sa.Column('source_articles', postgresql.JSONB, nullable=True),
        sa.Column('official_sources', postgresql.JSONB, nullable=True),

        # Metadata
        sa.Column('verified', sa.Boolean, default=False),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index('ix_pam_regulatory_events_date', 'pam_regulatory_events', ['event_date'])
    op.create_index('ix_pam_regulatory_events_jurisdiction', 'pam_regulatory_events', ['jurisdiction'])
    op.create_index('ix_pam_regulatory_events_type', 'pam_regulatory_events', ['regulation_type'])
    op.create_index('ix_pam_regulatory_events_status', 'pam_regulatory_events', ['status'])

    # PAM Saved Dashboards - user-saved PAM dashboard configurations
    op.create_table(
        'pam_saved_dashboards',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('username', sa.Text, sa.ForeignKey('users.username', ondelete='SET NULL'), nullable=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text, nullable=True),

        # Configuration
        sa.Column('topic', sa.String(255), nullable=True),
        sa.Column('config', postgresql.JSONB, nullable=True),
        sa.Column('entity_filters', postgresql.JSONB, nullable=True),
        sa.Column('trend_focus', postgresql.JSONB, nullable=True),
        sa.Column('time_range', sa.String(50), nullable=True),
        sa.Column('view_preferences', postgresql.JSONB, nullable=True),

        # Snapshot data
        sa.Column('power_analysis', postgresql.JSONB, nullable=True),
        sa.Column('attention_analysis', postgresql.JSONB, nullable=True),
        sa.Column('money_analysis', postgresql.JSONB, nullable=True),
        sa.Column('trend_analysis', postgresql.JSONB, nullable=True),
        sa.Column('scenario_analysis', postgresql.JSONB, nullable=True),
        sa.Column('entity_data', postgresql.JSONB, nullable=True),

        # Metadata
        sa.Column('articles_analyzed', sa.Integer, nullable=True),
        sa.Column('article_uris', postgresql.ARRAY(sa.Text), nullable=True),
        sa.Column('model_used', sa.String(100), nullable=True),

        # Auto-refresh settings
        sa.Column('auto_refresh', sa.Boolean, default=False),
        sa.Column('refresh_frequency', sa.String(50), nullable=True),  # 'daily', 'weekly', 'monthly'
        sa.Column('last_refreshed', sa.DateTime, nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('last_accessed', sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index('ix_pam_saved_dashboards_user', 'pam_saved_dashboards', ['username'])
    op.create_index('ix_pam_saved_dashboards_topic', 'pam_saved_dashboards', ['topic'])
    op.create_index('ix_pam_saved_dashboards_created', 'pam_saved_dashboards', ['created_at'])
    op.create_unique_constraint('uq_pam_saved_dashboards_user_name', 'pam_saved_dashboards', ['username', 'name'])


def downgrade():
    # Drop indexes and tables in reverse order

    # PAM Saved Dashboards
    op.drop_constraint('uq_pam_saved_dashboards_user_name', 'pam_saved_dashboards', type_='unique')
    op.drop_index('ix_pam_saved_dashboards_created', table_name='pam_saved_dashboards')
    op.drop_index('ix_pam_saved_dashboards_topic', table_name='pam_saved_dashboards')
    op.drop_index('ix_pam_saved_dashboards_user', table_name='pam_saved_dashboards')
    op.drop_table('pam_saved_dashboards')

    # PAM Regulatory Events
    op.drop_index('ix_pam_regulatory_events_status', table_name='pam_regulatory_events')
    op.drop_index('ix_pam_regulatory_events_type', table_name='pam_regulatory_events')
    op.drop_index('ix_pam_regulatory_events_jurisdiction', table_name='pam_regulatory_events')
    op.drop_index('ix_pam_regulatory_events_date', table_name='pam_regulatory_events')
    op.drop_table('pam_regulatory_events')

    # PAM Financial Events
    op.drop_index('ix_pam_financial_events_value', table_name='pam_financial_events')
    op.drop_index('ix_pam_financial_events_target', table_name='pam_financial_events')
    op.drop_index('ix_pam_financial_events_acquirer', table_name='pam_financial_events')
    op.drop_index('ix_pam_financial_events_type', table_name='pam_financial_events')
    op.drop_index('ix_pam_financial_events_date', table_name='pam_financial_events')
    op.drop_table('pam_financial_events')

    # PAM Metrics Time Series
    op.drop_index('ix_pam_metrics_category', table_name='pam_metrics_timeseries')
    op.drop_index('ix_pam_metrics_name', table_name='pam_metrics_timeseries')
    op.drop_index('ix_pam_metrics_date', table_name='pam_metrics_timeseries')
    op.drop_index('ix_pam_metrics_entity', table_name='pam_metrics_timeseries')
    op.drop_table('pam_metrics_timeseries')

    # PAM Entities
    op.drop_constraint('uq_pam_entities_name_type', 'pam_entities', type_='unique')
    op.drop_index('ix_pam_entities_influence', table_name='pam_entities')
    op.drop_index('ix_pam_entities_type', table_name='pam_entities')
    op.drop_index('ix_pam_entities_name', table_name='pam_entities')
    op.drop_table('pam_entities')

    # PAM Trend Snapshots
    op.drop_constraint('uq_pam_trend_snapshot_date_topic', 'pam_trend_snapshots', type_='unique')
    op.drop_index('ix_pam_trend_snapshots_topic', table_name='pam_trend_snapshots')
    op.drop_index('ix_pam_trend_snapshots_date', table_name='pam_trend_snapshots')
    op.drop_table('pam_trend_snapshots')

    # PAM Analysis Runs
    op.drop_index('ix_pam_analysis_runs_threat', table_name='pam_analysis_runs')
    op.drop_index('ix_pam_analysis_runs_created', table_name='pam_analysis_runs')
    op.drop_index('ix_pam_analysis_runs_type', table_name='pam_analysis_runs')
    op.drop_index('ix_pam_analysis_runs_topic', table_name='pam_analysis_runs')
    op.drop_index('ix_pam_analysis_runs_user', table_name='pam_analysis_runs')
    op.drop_table('pam_analysis_runs')
