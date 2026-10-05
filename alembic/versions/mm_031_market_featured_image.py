"""Featured items: a picture.

The cover of a paper, the card of a talk: one image URL per row, shown on
the Featured card and strip. The lead development drops a picture that is
the same URL, so the cover is not printed twice on one screen.

Revision ID: mm_031
Revises: mm_030
"""

from alembic import op
import sqlalchemy as sa

revision = 'mm_031'
down_revision = 'mm_030'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('market_featured',
                  sa.Column('image_url', sa.String(1000), nullable=True))


def downgrade() -> None:
    op.drop_column('market_featured', 'image_url')
