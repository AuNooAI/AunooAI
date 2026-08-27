"""What a reviewed customer post says about the customer.

The post review already reads every vendor post once and stores a verdict and
a kind. For a post of kind "customer" the report then needs three more things
that only a reader of the post can give: the customer's name (or that there is
none), whether the customer or the vendor is speaking, and whether the account
is a deployment, an evaluation or a case study. Asking for them in the same
model call costs nothing extra, and they are stored here so the report prints
what was read rather than what a regular expression guessed.

One JSON column rather than three typed ones: the shape belongs to the review
prompt, and a fourth field should not need a migration.

Revision ID: mm_012
Revises: mm_011
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'mm_012'
down_revision = 'mm_011'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'bw_market_articles',
        sa.Column('review_customer', postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column('bw_market_articles', 'review_customer')
