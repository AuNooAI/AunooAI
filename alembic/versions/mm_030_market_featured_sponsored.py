"""Featured items: say when one is sponsored.

A featured link a vendor paid for, or published as its own marketing, must
read as such: the badge says "Sponsored", the byline says who by. The flag
is per row; a talk we gave or a report we wrote stays "Featured".

Revision ID: mm_030
Revises: mm_029
"""

from alembic import op
import sqlalchemy as sa

revision = 'mm_030'
down_revision = 'mm_029'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('market_featured',
                  sa.Column('sponsored', sa.Boolean(), nullable=False,
                            server_default=sa.false()))


def downgrade() -> None:
    op.drop_column('market_featured', 'sponsored')
