"""Add geopolitical hotspots tables for global threat monitoring

Revision ID: gh_001
Revises: pt_003
Create Date: 2026-01-25

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 'gh_001'
down_revision = ('pt_003', 'rss_003')  # Merge multiple heads
branch_labels = None
depends_on = None


def upgrade():
    # Create geopolitical_hotspots table - core hotspot data
    op.create_table(
        'geopolitical_hotspots',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('location_name', sa.Text(), nullable=False),
        sa.Column('location_type', sa.Text(), nullable=False),  # city, region, country
        sa.Column('country_code', sa.String(2), nullable=True),  # ISO 3166-1 alpha-2
        sa.Column('country_name', sa.Text(), nullable=True),
        sa.Column('latitude', sa.Float(), nullable=False),
        sa.Column('longitude', sa.Float(), nullable=False),
        sa.Column('intensity_score', sa.Float(), nullable=False, server_default='0'),  # 0-100
        sa.Column('risk_level', sa.Text(), nullable=False, server_default="'low'"),  # critical, high, medium, low, info
        sa.Column('trend', sa.Text(), server_default="'stable'"),  # escalating, stable, de-escalating
        sa.Column('article_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('recent_article_count', sa.Integer(), nullable=False, server_default='0'),  # 7 days
        sa.Column('primary_category', sa.Text(), nullable=True),  # Main threat category
        sa.Column('tags', postgresql.JSONB(), nullable=True),  # Additional tags array
        sa.Column('topic', sa.Text(), nullable=True),  # Optional topic filter
        sa.Column('last_article_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_index('idx_geopolitical_hotspots_location', 'geopolitical_hotspots', ['location_name'])
    op.create_index('idx_geopolitical_hotspots_country', 'geopolitical_hotspots', ['country_code'])
    op.create_index('idx_geopolitical_hotspots_risk', 'geopolitical_hotspots', ['risk_level'])
    op.create_index('idx_geopolitical_hotspots_intensity', 'geopolitical_hotspots', ['intensity_score'])
    op.create_index('idx_geopolitical_hotspots_category', 'geopolitical_hotspots', ['primary_category'])
    op.create_index('idx_geopolitical_hotspots_topic', 'geopolitical_hotspots', ['topic'])
    op.create_index('idx_geopolitical_hotspots_coords', 'geopolitical_hotspots', ['latitude', 'longitude'])

    # Create hotspot_articles junction table - links articles to hotspots
    op.create_table(
        'hotspot_articles',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('hotspot_id', sa.Integer(), sa.ForeignKey('geopolitical_hotspots.id', ondelete='CASCADE'), nullable=False),
        sa.Column('article_uri', sa.Text(), sa.ForeignKey('articles.uri', ondelete='CASCADE'), nullable=False),
        sa.Column('relevance_score', sa.Float(), nullable=True),  # 0-1
        sa.Column('mention_type', sa.Text(), nullable=True),  # primary, secondary, background
        sa.Column('extracted_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.UniqueConstraint('hotspot_id', 'article_uri', name='uq_hotspot_article')
    )
    op.create_index('idx_hotspot_articles_hotspot', 'hotspot_articles', ['hotspot_id'])
    op.create_index('idx_hotspot_articles_article', 'hotspot_articles', ['article_uri'])

    # Create hotspot_daily_stats table - trend tracking
    op.create_table(
        'hotspot_daily_stats',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('hotspot_id', sa.Integer(), sa.ForeignKey('geopolitical_hotspots.id', ondelete='CASCADE'), nullable=False),
        sa.Column('article_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('intensity_score', sa.Float(), nullable=True),
        sa.Column('trend', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.UniqueConstraint('date', 'hotspot_id', name='uq_hotspot_daily_stats')
    )
    op.create_index('idx_hotspot_daily_stats_date', 'hotspot_daily_stats', ['date'])
    op.create_index('idx_hotspot_daily_stats_hotspot', 'hotspot_daily_stats', ['hotspot_id'])

    # Create country_hotspot_stats table - country aggregation for choropleth
    op.create_table(
        'country_hotspot_stats',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('country_code', sa.String(2), nullable=False, unique=True),
        sa.Column('country_name', sa.Text(), nullable=False),
        sa.Column('total_hotspots', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_articles', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('heat_value', sa.Float(), nullable=False, server_default='0'),  # 0-100 aggregated intensity
        sa.Column('max_risk_level', sa.Text(), nullable=True),  # Highest risk level in country
        sa.Column('primary_category', sa.Text(), nullable=True),  # Most common threat category
        sa.Column('topic', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_index('idx_country_hotspot_stats_code', 'country_hotspot_stats', ['country_code'])
    op.create_index('idx_country_hotspot_stats_heat', 'country_hotspot_stats', ['heat_value'])
    op.create_index('idx_country_hotspot_stats_topic', 'country_hotspot_stats', ['topic'])

    # Create geopolitical_insights table - LLM-generated analysis
    op.create_table(
        'geopolitical_insights',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('topic', sa.Text(), nullable=True),
        sa.Column('insight_type', sa.Text(), nullable=False),  # overview, regional, category, trend
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('metadata', postgresql.JSONB(), nullable=True),
        sa.Column('model_used', sa.Text(), nullable=True),
        sa.Column('hotspot_ids', postgresql.ARRAY(sa.Integer()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('idx_geopolitical_insights_type', 'geopolitical_insights', ['insight_type'])
    op.create_index('idx_geopolitical_insights_topic', 'geopolitical_insights', ['topic'])
    op.create_index('idx_geopolitical_insights_created', 'geopolitical_insights', ['created_at'])


def downgrade():
    op.drop_table('geopolitical_insights')
    op.drop_table('country_hotspot_stats')
    op.drop_table('hotspot_daily_stats')
    op.drop_table('hotspot_articles')
    op.drop_table('geopolitical_hotspots')
