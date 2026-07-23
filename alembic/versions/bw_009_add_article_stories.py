"""Add Brand Watcher story dedup table (port of wileytest bw_006)

Story deduplication: near-duplicate / syndicated articles for a brand are
clustered into a single "story" (story_group_id = canonical earliest
article_uri). Ported to this tenant so /articles can LEFT JOIN it for
story_size ("×N sources") — the table stays empty until the story-clustering
service (assign_story_groups) is deployed here, and the join degrades to NULL.

Revision ID: bw_009_article_stories
Revises: bw_008_brand_relevance
Create Date: 2026-07-03
"""
from alembic import op
import sqlalchemy as sa

revision = 'bw_009_article_stories'
down_revision = 'bw_008_brand_relevance'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'bw_article_stories',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('brand_id', sa.Integer(), sa.ForeignKey('bw_brands.id', ondelete='CASCADE'), nullable=False),
        sa.Column('article_uri', sa.Text(), nullable=False),
        sa.Column('story_group_id', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.UniqueConstraint('brand_id', 'article_uri', name='uq_bw_story_brand_article'),
    )
    op.create_index('idx_bw_stories_brand', 'bw_article_stories', ['brand_id'])
    op.create_index('idx_bw_stories_group', 'bw_article_stories', ['brand_id', 'story_group_id'])


def downgrade():
    op.drop_table('bw_article_stories')
