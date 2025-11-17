"""add auto_regenerate_reports column

Revision ID: auto_regenerate_001
Revises: multi_collector_001
Create Date: 2025-11-08 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'auto_regenerate_001'
down_revision = 'multi_collector_001'
branch_labels = None
depends_on = None


def upgrade():
    # Add auto_regenerate_reports column with default FALSE
    op.execute("""
        ALTER TABLE keyword_monitor_settings
        ADD COLUMN IF NOT EXISTS auto_regenerate_reports BOOLEAN DEFAULT FALSE
    """)


def downgrade():
    # Remove auto_regenerate_reports column
    op.execute("""
        ALTER TABLE keyword_monitor_settings
        DROP COLUMN IF EXISTS auto_regenerate_reports
    """)
