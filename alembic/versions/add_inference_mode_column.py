"""Add inference_mode column to keyword_monitor_settings

Revision ID: add_inference_mode
Revises:
Create Date: 2026-02-03

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_inference_mode'
down_revision = 'act_003'
branch_labels = None
depends_on = None


def upgrade():
    # Add inference_mode column with default 'hybrid'
    op.add_column(
        'keyword_monitor_settings',
        sa.Column('inference_mode', sa.Text(), nullable=False, server_default='hybrid')
    )


def downgrade():
    op.drop_column('keyword_monitor_settings', 'inference_mode')
