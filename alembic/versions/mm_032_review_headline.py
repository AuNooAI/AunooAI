"""A reviewed post's headline and summary, written by the review, checked by Jev.

Until now every headline on the market report was a sentence lifted from the
vendor's own post by pattern rules. Vendor posts open with a hook and use "we"
and "they", so the page showed "When Your Insider Risk Program Is Put to the
Test" and "Since working with Spectrum, they've doubled…". The post review
already reads every post once; it now also writes a one-line headline and a
one-sentence summary in our words, and a second, independent model (Jev) checks
that each says only what the post says. ``review_check`` holds that check, so
the report can refuse a headline the post does not support.

Revision ID: mm_032
Revises: vp_001
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'mm_032'
down_revision = 'vp_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('bw_market_articles',
                  sa.Column('review_headline', sa.Text(), nullable=True))
    op.add_column('bw_market_articles',
                  sa.Column('review_summary', sa.Text(), nullable=True))
    op.add_column('bw_market_articles',
                  sa.Column('review_check', postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column('bw_market_articles', 'review_check')
    op.drop_column('bw_market_articles', 'review_summary')
    op.drop_column('bw_market_articles', 'review_headline')
