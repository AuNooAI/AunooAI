"""Add Strategic Intelligence Oracle tables

Revision ID: sio_001
Revises: auspex_enhance_001
Create Date: 2025-11-29

This migration adds tables for:
- SIO scan runs (24-hour intelligence scans)
- Event clusters (grouped articles about the same event)
- Event analyses (deep analysis results)
- Audit trail records
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision = 'sio_001'
down_revision = 'auspex_enhance_001'
branch_labels = None
depends_on = None


def upgrade():
    # SIO Scan Runs - tracks each intelligence scan
    op.create_table(
        'sio_scan_runs',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('scan_id', sa.String(36), nullable=False, unique=True),
        sa.Column('username', sa.Text, sa.ForeignKey('users.username', ondelete='SET NULL'), nullable=True),
        sa.Column('topic', sa.String(255), nullable=True),  # NULL = all topics
        sa.Column('hours_back', sa.Integer, nullable=False, default=24),
        sa.Column('status', sa.String(50), server_default='running', nullable=False),
        # Collection stats
        sa.Column('articles_collected', sa.Integer, default=0),
        sa.Column('articles_screened', sa.Integer, default=0),
        sa.Column('events_identified', sa.Integer, default=0),
        sa.Column('events_analyzed', sa.Integer, default=0),
        # Quality metrics
        sa.Column('avg_credibility_score', sa.Float, nullable=True),
        sa.Column('source_diversity_score', sa.Float, nullable=True),
        # Output
        sa.Column('intelligence_brief', sa.Text, nullable=True),
        sa.Column('executive_summary', sa.Text, nullable=True),
        # Audit
        sa.Column('config', postgresql.JSONB, nullable=True),
        sa.Column('audit_trail', postgresql.JSONB, nullable=True),
        sa.Column('models_used', postgresql.ARRAY(sa.Text), nullable=True),
        # Timestamps
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime, nullable=True),
        sa.Column('duration_seconds', sa.Float, nullable=True),
        # Error handling
        sa.Column('error_message', sa.Text, nullable=True),
    )
    op.create_index('ix_sio_scan_runs_scan_id', 'sio_scan_runs', ['scan_id'])
    op.create_index('ix_sio_scan_runs_username', 'sio_scan_runs', ['username'])
    op.create_index('ix_sio_scan_runs_status', 'sio_scan_runs', ['status'])
    op.create_index('ix_sio_scan_runs_created_at', 'sio_scan_runs', ['created_at'])
    op.create_index('ix_sio_scan_runs_topic', 'sio_scan_runs', ['topic'])

    # SIO Event Clusters - groups of related articles
    op.create_table(
        'sio_event_clusters',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('cluster_id', sa.String(36), nullable=False),
        sa.Column('scan_id', sa.String(36), sa.ForeignKey('sio_scan_runs.scan_id', ondelete='CASCADE'), nullable=False),
        sa.Column('title', sa.Text, nullable=False),
        sa.Column('summary', sa.Text, nullable=True),
        sa.Column('category', sa.String(100), nullable=True),
        # Metrics
        sa.Column('article_count', sa.Integer, default=0),
        sa.Column('source_diversity_score', sa.Float, nullable=True),
        sa.Column('preliminary_importance', sa.String(20), nullable=True),
        sa.Column('final_importance_score', sa.Float, nullable=True),
        # Analysis results
        sa.Column('confidence_score', sa.Float, nullable=True),
        sa.Column('quality_gates_passed', sa.Boolean, nullable=True),
        sa.Column('quality_gates', postgresql.JSONB, nullable=True),
        # Content
        sa.Column('key_facts', postgresql.JSONB, nullable=True),
        sa.Column('key_entities', postgresql.JSONB, nullable=True),
        sa.Column('contradictions', postgresql.JSONB, nullable=True),
        sa.Column('impact_assessment', postgresql.JSONB, nullable=True),
        sa.Column('keywords', postgresql.ARRAY(sa.Text), nullable=True),
        # Timestamps
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('analyzed_at', sa.DateTime, nullable=True),
    )
    op.create_index('ix_sio_event_clusters_scan_id', 'sio_event_clusters', ['scan_id'])
    op.create_index('ix_sio_event_clusters_cluster_id', 'sio_event_clusters', ['cluster_id'])
    op.create_index('ix_sio_event_clusters_importance', 'sio_event_clusters', ['final_importance_score'])
    op.create_index('ix_sio_event_clusters_category', 'sio_event_clusters', ['category'])

    # SIO Cluster Articles - articles belonging to each cluster
    op.create_table(
        'sio_cluster_articles',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('cluster_id', sa.String(36), nullable=False),
        sa.Column('scan_id', sa.String(36), sa.ForeignKey('sio_scan_runs.scan_id', ondelete='CASCADE'), nullable=False),
        sa.Column('article_uri', sa.Text, nullable=True),  # FK to articles if exists
        sa.Column('article_url', sa.Text, nullable=True),  # For external articles
        sa.Column('article_title', sa.Text, nullable=True),
        sa.Column('article_source', sa.Text, nullable=True),
        sa.Column('article_summary', sa.Text, nullable=True),
        sa.Column('publication_date', sa.DateTime, nullable=True),
        # Scoring
        sa.Column('credibility_score', sa.Float, nullable=True),
        sa.Column('bias', sa.String(50), nullable=True),
        sa.Column('is_representative', sa.Boolean, default=False),
        # Verification
        sa.Column('verified_claims', sa.Integer, default=0),
        sa.Column('unverified_claims', sa.Integer, default=0),
        # Source tracking
        sa.Column('source_type', sa.String(20), nullable=True),  # 'internal' or 'external'
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index('ix_sio_cluster_articles_cluster_id', 'sio_cluster_articles', ['cluster_id'])
    op.create_index('ix_sio_cluster_articles_scan_id', 'sio_cluster_articles', ['scan_id'])
    op.create_index('ix_sio_cluster_articles_source', 'sio_cluster_articles', ['article_source'])

    # SIO Single Article Analyses - for Option A standalone analysis
    op.create_table(
        'sio_article_analyses',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('analysis_id', sa.String(36), nullable=False, unique=True),
        sa.Column('username', sa.Text, sa.ForeignKey('users.username', ondelete='SET NULL'), nullable=True),
        sa.Column('url', sa.Text, nullable=False),
        sa.Column('title', sa.Text, nullable=True),
        sa.Column('summary', sa.Text, nullable=True),
        # Source info
        sa.Column('source_domain', sa.String(255), nullable=True),
        sa.Column('credibility_score', sa.Float, nullable=True),
        sa.Column('bias', sa.String(50), nullable=True),
        sa.Column('factual_reporting', sa.String(50), nullable=True),
        # Analysis results
        sa.Column('confidence_score', sa.Float, nullable=True),
        sa.Column('key_facts', postgresql.JSONB, nullable=True),
        sa.Column('key_entities', postgresql.JSONB, nullable=True),
        sa.Column('verification_results', postgresql.JSONB, nullable=True),
        sa.Column('contradictions', postgresql.JSONB, nullable=True),
        sa.Column('impact_assessment', postgresql.JSONB, nullable=True),
        sa.Column('quality_gates', postgresql.JSONB, nullable=True),
        # Cross-references
        sa.Column('related_articles_count', sa.Integer, default=0),
        sa.Column('cross_references', postgresql.JSONB, nullable=True),
        # Timestamps
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime, nullable=True),
    )
    op.create_index('ix_sio_article_analyses_analysis_id', 'sio_article_analyses', ['analysis_id'])
    op.create_index('ix_sio_article_analyses_username', 'sio_article_analyses', ['username'])
    op.create_index('ix_sio_article_analyses_url', 'sio_article_analyses', ['url'])
    op.create_index('ix_sio_article_analyses_created_at', 'sio_article_analyses', ['created_at'])


def downgrade():
    # Drop indexes first
    op.drop_index('ix_sio_article_analyses_created_at', table_name='sio_article_analyses')
    op.drop_index('ix_sio_article_analyses_url', table_name='sio_article_analyses')
    op.drop_index('ix_sio_article_analyses_username', table_name='sio_article_analyses')
    op.drop_index('ix_sio_article_analyses_analysis_id', table_name='sio_article_analyses')

    op.drop_index('ix_sio_cluster_articles_source', table_name='sio_cluster_articles')
    op.drop_index('ix_sio_cluster_articles_scan_id', table_name='sio_cluster_articles')
    op.drop_index('ix_sio_cluster_articles_cluster_id', table_name='sio_cluster_articles')

    op.drop_index('ix_sio_event_clusters_category', table_name='sio_event_clusters')
    op.drop_index('ix_sio_event_clusters_importance', table_name='sio_event_clusters')
    op.drop_index('ix_sio_event_clusters_cluster_id', table_name='sio_event_clusters')
    op.drop_index('ix_sio_event_clusters_scan_id', table_name='sio_event_clusters')

    op.drop_index('ix_sio_scan_runs_topic', table_name='sio_scan_runs')
    op.drop_index('ix_sio_scan_runs_created_at', table_name='sio_scan_runs')
    op.drop_index('ix_sio_scan_runs_status', table_name='sio_scan_runs')
    op.drop_index('ix_sio_scan_runs_username', table_name='sio_scan_runs')
    op.drop_index('ix_sio_scan_runs_scan_id', table_name='sio_scan_runs')

    # Drop tables in reverse order of creation (due to foreign keys)
    op.drop_table('sio_article_analyses')
    op.drop_table('sio_cluster_articles')
    op.drop_table('sio_event_clusters')
    op.drop_table('sio_scan_runs')
