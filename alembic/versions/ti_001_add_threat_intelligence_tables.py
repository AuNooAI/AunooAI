"""Add threat intelligence tables for cyber threat tracking and analysis

Revision ID: ti_001
Revises: gh_003
Create Date: 2026-01-26

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 'ti_001'
down_revision = 'gh_003'
branch_labels = None
depends_on = None


def upgrade():
    # ============================================================================
    # threat_intel_actors - Threat actor profiles (APT groups, criminal orgs, etc.)
    # ============================================================================
    op.create_table(
        'threat_intel_actors',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.Text(), nullable=False, unique=True),
        sa.Column('aliases', postgresql.ARRAY(sa.Text()), nullable=True),  # Alternative names
        sa.Column('actor_type', sa.Text(), nullable=False),  # nation_state, cybercrime, hacktivist, insider, script_kiddie, unknown
        sa.Column('attributed_country', sa.String(2), nullable=True),  # ISO 3166-1 alpha-2
        sa.Column('attributed_country_name', sa.Text(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('motivation', sa.Text(), nullable=True),  # espionage, financial, ideological, disruption
        sa.Column('sophistication_level', sa.Text(), nullable=True),  # advanced, intermediate, basic
        sa.Column('target_industries', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('target_regions', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('known_ttps', postgresql.ARRAY(sa.Text()), nullable=True),  # MITRE ATT&CK IDs
        sa.Column('associated_malware', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('first_observed', sa.Date(), nullable=True),
        sa.Column('last_active', sa.Date(), nullable=True),
        sa.Column('threat_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('article_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('metadata', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_index('idx_threat_intel_actors_name', 'threat_intel_actors', ['name'])
    op.create_index('idx_threat_intel_actors_type', 'threat_intel_actors', ['actor_type'])
    op.create_index('idx_threat_intel_actors_country', 'threat_intel_actors', ['attributed_country'])
    op.create_index('idx_threat_intel_actors_sophistication', 'threat_intel_actors', ['sophistication_level'])

    # ============================================================================
    # threat_intel_threats - Main threat entity table
    # ============================================================================
    op.create_table(
        'threat_intel_threats',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('threat_name', sa.Text(), nullable=False),
        sa.Column('threat_type', sa.Text(), nullable=False),  # malware, ransomware, apt, phishing, vulnerability, etc.
        sa.Column('threat_subtype', sa.Text(), nullable=True),  # More specific classification

        # Severity
        sa.Column('severity_level', sa.Text(), nullable=False, server_default="'medium'"),  # critical, high, medium, low, info
        sa.Column('severity_score', sa.Float(), nullable=False, server_default='50'),  # 0-100
        sa.Column('trend', sa.Text(), server_default="'stable'"),  # escalating, stable, declining

        # Attribution
        sa.Column('threat_actor_id', sa.Integer(), sa.ForeignKey('threat_intel_actors.id', ondelete='SET NULL'), nullable=True),
        sa.Column('threat_actor_name', sa.Text(), nullable=True),  # Denormalized for performance
        sa.Column('attributed_country', sa.String(2), nullable=True),
        sa.Column('attributed_country_name', sa.Text(), nullable=True),

        # Target information
        sa.Column('target_countries', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('target_latitude', sa.Float(), nullable=True),  # Primary target location
        sa.Column('target_longitude', sa.Float(), nullable=True),
        sa.Column('target_industries', postgresql.ARRAY(sa.Text()), nullable=True),

        # Technical indicators
        sa.Column('cve_ids', postgresql.ARRAY(sa.Text()), nullable=True),  # CVE-XXXX-XXXXX
        sa.Column('mitre_techniques', postgresql.ARRAY(sa.Text()), nullable=True),  # T1059, T1566, etc.
        sa.Column('malware_families', postgresql.ARRAY(sa.Text()), nullable=True),

        # Article/temporal tracking
        sa.Column('first_seen_date', sa.Date(), nullable=True),
        sa.Column('last_seen_date', sa.Date(), nullable=True),
        sa.Column('article_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('recent_article_count', sa.Integer(), nullable=False, server_default='0'),  # 7 days

        # Metadata
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('tags', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('metadata', postgresql.JSONB(), nullable=True),
        sa.Column('topic', sa.Text(), nullable=True),  # Optional topic filter

        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_index('idx_threat_intel_threats_name', 'threat_intel_threats', ['threat_name'])
    op.create_index('idx_threat_intel_threats_type', 'threat_intel_threats', ['threat_type'])
    op.create_index('idx_threat_intel_threats_severity', 'threat_intel_threats', ['severity_level'])
    op.create_index('idx_threat_intel_threats_score', 'threat_intel_threats', ['severity_score'])
    op.create_index('idx_threat_intel_threats_actor', 'threat_intel_threats', ['threat_actor_id'])
    op.create_index('idx_threat_intel_threats_country', 'threat_intel_threats', ['attributed_country'])
    op.create_index('idx_threat_intel_threats_topic', 'threat_intel_threats', ['topic'])
    op.create_index('idx_threat_intel_threats_coords', 'threat_intel_threats', ['target_latitude', 'target_longitude'])

    # ============================================================================
    # threat_intel_iocs - Indicators of Compromise
    # ============================================================================
    op.create_table(
        'threat_intel_iocs',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('indicator_type', sa.Text(), nullable=False),  # ip, domain, hash_md5, hash_sha256, url, email
        sa.Column('indicator_value', sa.Text(), nullable=False),
        sa.Column('threat_id', sa.Integer(), sa.ForeignKey('threat_intel_threats.id', ondelete='CASCADE'), nullable=True),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('threat_intel_actors.id', ondelete='SET NULL'), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),  # 0-100
        sa.Column('first_seen', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_seen', sa.DateTime(timezone=True), nullable=True),
        sa.Column('source_article_uri', sa.Text(), sa.ForeignKey('articles.uri', ondelete='SET NULL'), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('metadata', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.UniqueConstraint('indicator_type', 'indicator_value', name='uq_ioc_type_value')
    )
    op.create_index('idx_threat_intel_iocs_type', 'threat_intel_iocs', ['indicator_type'])
    op.create_index('idx_threat_intel_iocs_value', 'threat_intel_iocs', ['indicator_value'])
    op.create_index('idx_threat_intel_iocs_threat', 'threat_intel_iocs', ['threat_id'])
    op.create_index('idx_threat_intel_iocs_actor', 'threat_intel_iocs', ['actor_id'])

    # ============================================================================
    # threat_intel_campaigns - Campaign tracking
    # ============================================================================
    op.create_table(
        'threat_intel_campaigns',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('threat_actor_id', sa.Integer(), sa.ForeignKey('threat_intel_actors.id', ondelete='SET NULL'), nullable=True),
        sa.Column('threat_actor_name', sa.Text(), nullable=True),
        sa.Column('start_date', sa.Date(), nullable=True),
        sa.Column('end_date', sa.Date(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('target_countries', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('target_industries', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('techniques_used', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('malware_used', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('threat_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('article_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('metadata', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_index('idx_threat_intel_campaigns_name', 'threat_intel_campaigns', ['name'])
    op.create_index('idx_threat_intel_campaigns_actor', 'threat_intel_campaigns', ['threat_actor_id'])
    op.create_index('idx_threat_intel_campaigns_active', 'threat_intel_campaigns', ['is_active'])

    # ============================================================================
    # threat_articles - Junction table: threats <-> articles
    # ============================================================================
    op.create_table(
        'threat_articles',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('threat_id', sa.Integer(), sa.ForeignKey('threat_intel_threats.id', ondelete='CASCADE'), nullable=False),
        sa.Column('article_uri', sa.Text(), sa.ForeignKey('articles.uri', ondelete='CASCADE'), nullable=False),
        sa.Column('relevance_score', sa.Float(), nullable=True),  # 0-1
        sa.Column('mention_type', sa.Text(), nullable=True),  # primary, secondary, background
        sa.Column('extracted_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.UniqueConstraint('threat_id', 'article_uri', name='uq_threat_article')
    )
    op.create_index('idx_threat_articles_threat', 'threat_articles', ['threat_id'])
    op.create_index('idx_threat_articles_article', 'threat_articles', ['article_uri'])

    # ============================================================================
    # threat_daily_stats - Time series for trends
    # ============================================================================
    op.create_table(
        'threat_daily_stats',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('threat_id', sa.Integer(), sa.ForeignKey('threat_intel_threats.id', ondelete='CASCADE'), nullable=True),
        sa.Column('threat_type', sa.Text(), nullable=True),  # For aggregate stats by type
        sa.Column('article_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('avg_severity_score', sa.Float(), nullable=True),
        sa.Column('new_threats', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('escalating_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_index('idx_threat_daily_stats_date', 'threat_daily_stats', ['date'])
    op.create_index('idx_threat_daily_stats_threat', 'threat_daily_stats', ['threat_id'])
    op.create_index('idx_threat_daily_stats_type', 'threat_daily_stats', ['threat_type'])

    # ============================================================================
    # threat_intel_narratives - LLM-generated threat briefings
    # ============================================================================
    op.create_table(
        'threat_intel_narratives',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('narrative_text', sa.Text(), nullable=False),
        sa.Column('executive_summary', sa.Text(), nullable=True),
        sa.Column('threat_landscape', sa.Text(), nullable=True),
        sa.Column('emerging_threats', sa.Text(), nullable=True),
        sa.Column('recommendations', sa.Text(), nullable=True),
        sa.Column('threat_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('article_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('top_threat_types', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('top_actors', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('severity_breakdown', postgresql.JSONB(), nullable=True),
        sa.Column('model_used', sa.Text(), nullable=True),
        sa.Column('topic', sa.Text(), nullable=True),
        sa.Column('generated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_index('idx_threat_intel_narratives_topic', 'threat_intel_narratives', ['topic'])
    op.create_index('idx_threat_intel_narratives_generated', 'threat_intel_narratives', ['generated_at'])

    # ============================================================================
    # threat_intel_schedules - Processing schedules
    # ============================================================================
    op.create_table(
        'threat_intel_schedules',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('topic', sa.Text(), nullable=True),
        sa.Column('batch_size', sa.Integer(), nullable=False, server_default='50'),
        sa.Column('model', sa.Text(), nullable=False, server_default="'gpt-4o-mini'"),
        sa.Column('process_all', sa.Boolean(), nullable=False, server_default='false'),

        # Schedule configuration
        sa.Column('schedule_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('schedule_type', sa.Text(), nullable=True),  # 'interval' or 'daily'
        sa.Column('schedule_interval', sa.Integer(), nullable=True),
        sa.Column('schedule_unit', sa.Text(), nullable=True),  # 'minutes', 'hours', 'days'
        sa.Column('schedule_time', sa.Time(), nullable=True),  # For daily schedules

        # Notification settings
        sa.Column('notify_on_complete', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('notify_threshold', sa.Integer(), nullable=False, server_default='1'),

        # Run tracking
        sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_run_status', sa.Text(), nullable=True),  # success, error, running
        sa.Column('last_run_error', sa.Text(), nullable=True),
        sa.Column('last_run_articles_processed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_run_threats_created', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_run_threats_updated', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('run_count', sa.Integer(), nullable=False, server_default='0'),

        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_index('idx_threat_intel_schedules_enabled', 'threat_intel_schedules', ['schedule_enabled'])
    op.create_index('idx_threat_intel_schedules_next_run', 'threat_intel_schedules', ['next_run_at'])


def downgrade():
    op.drop_table('threat_intel_schedules')
    op.drop_table('threat_intel_narratives')
    op.drop_table('threat_daily_stats')
    op.drop_table('threat_articles')
    op.drop_table('threat_intel_campaigns')
    op.drop_table('threat_intel_iocs')
    op.drop_table('threat_intel_threats')
    op.drop_table('threat_intel_actors')
