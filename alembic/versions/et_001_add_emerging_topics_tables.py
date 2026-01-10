"""Add Emerging Topics detection tables

Revision ID: et_001
Revises: pam_002
Create Date: 2026-01-09

This migration adds tables for:
- emerging_topics: Detected emerging topics with LLM-generated summaries
- article_novelty_scores: Per-article novelty scores for outlier detection
- cluster_snapshots: Daily cluster snapshots for temporal evolution tracking
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision = 'et_001'
down_revision = '15c1b856de49'
branch_labels = None
depends_on = None


def upgrade():
    # Emerging Topics - detected new/growing topic clusters
    op.create_table(
        'emerging_topics',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('topic_label', sa.String(255), nullable=False),
        sa.Column('topic_description', sa.Text, nullable=True),
        sa.Column('detection_date', sa.Date, nullable=False),
        sa.Column('detection_type', sa.String(50), nullable=False),  # 'new_cluster', 'splitting', 'accelerating', 'proto_cluster'

        # Cluster identification
        sa.Column('cluster_id', sa.String(100), nullable=True),
        sa.Column('parent_cluster_id', sa.Integer, sa.ForeignKey('emerging_topics.id', ondelete='SET NULL'), nullable=True),

        # Cluster metrics
        sa.Column('article_count', sa.Integer, default=0),
        # centroid_embedding added via raw SQL below
        sa.Column('avg_novelty_score', sa.Float, nullable=True),
        sa.Column('cluster_density', sa.Float, nullable=True),
        sa.Column('cluster_radius', sa.Float, nullable=True),

        # Velocity/growth metrics
        sa.Column('growth_rate', sa.Float, nullable=True),  # Articles per day
        sa.Column('velocity', sa.String(20), nullable=True),  # 'accelerating', 'stable', 'decelerating'
        sa.Column('velocity_change_pct', sa.Float, nullable=True),

        # LLM-generated analysis
        sa.Column('key_themes', postgresql.JSONB, nullable=True),
        sa.Column('representative_keywords', postgresql.JSONB, nullable=True),
        sa.Column('related_existing_topics', postgresql.JSONB, nullable=True),
        sa.Column('emergence_rationale', sa.Text, nullable=True),

        # Status and confidence
        sa.Column('status', sa.String(20), default='active'),  # 'active', 'merged', 'declined', 'confirmed'
        sa.Column('confidence_score', sa.Float, nullable=True),

        # Article references
        sa.Column('article_uris', postgresql.ARRAY(sa.Text), nullable=True),
        sa.Column('sample_article_uris', postgresql.ARRAY(sa.Text), nullable=True),

        # Optional topic filter
        sa.Column('topic_filter', sa.String(255), nullable=True),  # Topic used during detection

        # Processing metadata
        sa.Column('model_used', sa.String(100), nullable=True),
        sa.Column('config', postgresql.JSONB, nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Add vector column via raw SQL (pgvector)
    op.execute('ALTER TABLE emerging_topics ADD COLUMN centroid_embedding vector(1536)')

    op.create_index('ix_emerging_topics_date', 'emerging_topics', ['detection_date'])
    op.create_index('ix_emerging_topics_type', 'emerging_topics', ['detection_type'])
    op.create_index('ix_emerging_topics_status', 'emerging_topics', ['status'])
    op.create_index('ix_emerging_topics_confidence', 'emerging_topics', ['confidence_score'])
    op.create_index('ix_emerging_topics_topic_filter', 'emerging_topics', ['topic_filter'])

    # Article Novelty Scores - per-article novelty metrics
    op.create_table(
        'article_novelty_scores',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('article_uri', sa.Text, sa.ForeignKey('articles.uri', ondelete='CASCADE'), nullable=False),
        sa.Column('calculation_date', sa.Date, nullable=False),

        # Component scores (0-100)
        sa.Column('knn_distance_score', sa.Float, nullable=False),
        sa.Column('density_score', sa.Float, nullable=False),
        sa.Column('centroid_distance_score', sa.Float, nullable=False),
        sa.Column('composite_novelty_score', sa.Float, nullable=False),

        # KNN calculation details
        sa.Column('k_neighbors', sa.Integer, default=10),
        sa.Column('avg_knn_distance', sa.Float, nullable=True),
        sa.Column('min_knn_distance', sa.Float, nullable=True),
        sa.Column('max_knn_distance', sa.Float, nullable=True),

        # Density calculation details
        sa.Column('local_density', sa.Float, nullable=True),
        sa.Column('density_radius', sa.Float, nullable=True),

        # Cluster assignment
        sa.Column('nearest_cluster_id', sa.String(100), nullable=True),
        sa.Column('distance_to_nearest_cluster', sa.Float, nullable=True),
        sa.Column('is_outlier', sa.Boolean, default=False),

        # Link to emerging topic if assigned
        sa.Column('emerging_topic_id', sa.Integer, sa.ForeignKey('emerging_topics.id', ondelete='SET NULL'), nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index('ix_novelty_scores_article', 'article_novelty_scores', ['article_uri'])
    op.create_index('ix_novelty_scores_date', 'article_novelty_scores', ['calculation_date'])
    op.create_index('ix_novelty_scores_composite', 'article_novelty_scores', ['composite_novelty_score'])
    op.create_index('ix_novelty_scores_outlier', 'article_novelty_scores', ['is_outlier', 'calculation_date'])
    op.create_unique_constraint('uq_novelty_scores_article_date', 'article_novelty_scores', ['article_uri', 'calculation_date'])

    # Cluster Snapshots - daily snapshots for temporal evolution tracking
    op.create_table(
        'cluster_snapshots',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('snapshot_date', sa.Date, nullable=False),
        sa.Column('cluster_id', sa.String(100), nullable=False),

        # Cluster state
        sa.Column('article_count', sa.Integer, nullable=True),
        # centroid_embedding added via raw SQL below
        sa.Column('avg_internal_distance', sa.Float, nullable=True),
        sa.Column('cluster_radius', sa.Float, nullable=True),

        # Evolution metrics (compared to previous snapshot)
        sa.Column('centroid_drift', sa.Float, nullable=True),
        sa.Column('size_change', sa.Integer, nullable=True),
        sa.Column('composition_similarity', sa.Float, nullable=True),  # Jaccard similarity

        # Cluster status flags
        sa.Column('is_new', sa.Boolean, default=False),
        sa.Column('is_splitting', sa.Boolean, default=False),
        sa.Column('is_merging', sa.Boolean, default=False),

        # Parent/child tracking for splits/merges
        sa.Column('parent_cluster_ids', postgresql.JSONB, nullable=True),
        sa.Column('child_cluster_ids', postgresql.JSONB, nullable=True),

        # Article membership
        sa.Column('article_uris', postgresql.ARRAY(sa.Text), nullable=True),

        # Optional topic filter
        sa.Column('topic_filter', sa.String(255), nullable=True),

        # LLM-generated label (if available)
        sa.Column('cluster_label', sa.String(255), nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
    )

    # Add vector column via raw SQL (pgvector)
    op.execute('ALTER TABLE cluster_snapshots ADD COLUMN centroid_embedding vector(1536)')

    op.create_index('ix_cluster_snapshots_date', 'cluster_snapshots', ['snapshot_date'])
    op.create_index('ix_cluster_snapshots_cluster', 'cluster_snapshots', ['cluster_id'])
    op.create_index('ix_cluster_snapshots_topic', 'cluster_snapshots', ['topic_filter'])
    op.create_unique_constraint('uq_cluster_snapshots_date_cluster', 'cluster_snapshots', ['snapshot_date', 'cluster_id', 'topic_filter'])


def downgrade():
    # Drop cluster_snapshots
    op.drop_constraint('uq_cluster_snapshots_date_cluster', 'cluster_snapshots', type_='unique')
    op.drop_index('ix_cluster_snapshots_topic', table_name='cluster_snapshots')
    op.drop_index('ix_cluster_snapshots_cluster', table_name='cluster_snapshots')
    op.drop_index('ix_cluster_snapshots_date', table_name='cluster_snapshots')
    op.drop_table('cluster_snapshots')

    # Drop article_novelty_scores
    op.drop_constraint('uq_novelty_scores_article_date', 'article_novelty_scores', type_='unique')
    op.drop_index('ix_novelty_scores_outlier', table_name='article_novelty_scores')
    op.drop_index('ix_novelty_scores_composite', table_name='article_novelty_scores')
    op.drop_index('ix_novelty_scores_date', table_name='article_novelty_scores')
    op.drop_index('ix_novelty_scores_article', table_name='article_novelty_scores')
    op.drop_table('article_novelty_scores')

    # Drop emerging_topics
    op.drop_index('ix_emerging_topics_topic_filter', table_name='emerging_topics')
    op.drop_index('ix_emerging_topics_confidence', table_name='emerging_topics')
    op.drop_index('ix_emerging_topics_status', table_name='emerging_topics')
    op.drop_index('ix_emerging_topics_type', table_name='emerging_topics')
    op.drop_index('ix_emerging_topics_date', table_name='emerging_topics')
    op.drop_table('emerging_topics')
