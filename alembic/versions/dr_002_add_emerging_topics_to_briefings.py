"""Add emerging_topics column to desk_briefings

Revision ID: dr_002
Revises: dr_001_add_desk_briefings
Create Date: 2026-01-28

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = 'dr_002'
down_revision = 'dr_001'
branch_labels = None
depends_on = None


def upgrade():
    # Add emerging_topics column to desk_briefings
    op.add_column(
        'desk_briefings',
        sa.Column('emerging_topics', JSONB, nullable=False, server_default=sa.text("'[]'"))
    )
    op.add_column(
        'desk_briefings',
        sa.Column('emerging_topics_count', sa.Integer, nullable=False, server_default=sa.text('0'))
    )


def downgrade():
    op.drop_column('desk_briefings', 'emerging_topics_count')
    op.drop_column('desk_briefings', 'emerging_topics')
