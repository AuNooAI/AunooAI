"""Add user relevance feedback table

Revision ID: act_002
Revises: act_001
Create Date: 2026-02-02

Tables:
- user_relevance_feedback: Stores user feedback on article relevance (more/less like this)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = 'act_002'
down_revision = 'act_001'
branch_labels = None
depends_on = None


def upgrade():
    # Create user_relevance_feedback table
    op.create_table(
        'user_relevance_feedback',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('article_uri', sa.Text, sa.ForeignKey('articles.uri', ondelete='CASCADE'), nullable=False),
        sa.Column('topic', sa.Text, nullable=False),
        sa.Column('user_id', sa.Text, nullable=True),  # null for anonymous users
        sa.Column('feedback_type', sa.Text, nullable=False),  # 'more_like_this', 'less_like_this'

        # Scores at time of feedback (for training/analysis)
        sa.Column('relevance_score', sa.Float),  # hybrid score when user gave feedback
        sa.Column('classifier_score', sa.Float),  # DeBERTa score if available
        sa.Column('embedding_score', sa.Float),  # Embedding similarity if available

        # Context for training
        sa.Column('article_metadata', JSONB),  # title, category, domain, etc for quick access

        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),

        # Prevent duplicate feedback from same user on same article
        sa.UniqueConstraint('article_uri', 'user_id', name='uq_relevance_feedback_article_user')
    )

    # Indices for efficient querying
    op.create_index('idx_relevance_feedback_topic', 'user_relevance_feedback', ['topic'])
    op.create_index('idx_relevance_feedback_type', 'user_relevance_feedback', ['feedback_type'])
    op.create_index('idx_relevance_feedback_created', 'user_relevance_feedback', ['created_at'])
    op.create_index('idx_relevance_feedback_topic_type', 'user_relevance_feedback', ['topic', 'feedback_type'])


def downgrade():
    op.drop_index('idx_relevance_feedback_topic_type', table_name='user_relevance_feedback')
    op.drop_index('idx_relevance_feedback_created', table_name='user_relevance_feedback')
    op.drop_index('idx_relevance_feedback_type', table_name='user_relevance_feedback')
    op.drop_index('idx_relevance_feedback_topic', table_name='user_relevance_feedback')
    op.drop_table('user_relevance_feedback')
