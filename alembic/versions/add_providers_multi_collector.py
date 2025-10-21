"""add providers column for multi-collector support

Revision ID: multi_collector_001
Revises: d8d9cdcec340
Create Date: 2025-10-21 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'multi_collector_001'
down_revision = 'd8d9cdcec340'
branch_labels = None
depends_on = None


def upgrade():
    # Add providers column with default JSON array
    op.execute("""
        ALTER TABLE keyword_monitor_settings
        ADD COLUMN IF NOT EXISTS providers TEXT DEFAULT '["newsapi"]'
    """)

    # Migrate existing provider value to providers array (PostgreSQL syntax)
    op.execute("""
        UPDATE keyword_monitor_settings
        SET providers = json_build_array(provider)::text
        WHERE provider IS NOT NULL AND (providers IS NULL OR providers = '["newsapi"]')
    """)


def downgrade():
    # Remove providers column
    op.execute("""
        ALTER TABLE keyword_monitor_settings
        DROP COLUMN IF EXISTS providers
    """)
