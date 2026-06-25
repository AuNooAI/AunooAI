"""Add daily_briefing_topics setting for auto-composed daily briefings

Revision ID: dbc_001
Revises: fa_011
Create Date: 2026-06-18

Adds:
- emerging_topics_settings.daily_briefing_topics (JSONB) — the configured set of
  topics the daily-briefing auto-compose job runs over when no explicit topic
  list is supplied.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'dbc_001'
down_revision = 'fa_011'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'emerging_topics_settings',
        sa.Column('daily_briefing_topics', postgresql.JSONB(), server_default='[]', nullable=True),
    )


def downgrade() -> None:
    op.drop_column('emerging_topics_settings', 'daily_briefing_topics')
