"""signal_alerts.review_status — alerts the referee holds back from email

Revision ID: ts_013
Revises: ts_012
Create Date: 2026-09-20

When TYPESAFE_DECIDE_REFEREE is on, an alert whose cited article the TypeSafe
Jev model scores under the match threshold is saved with review_status
'held': it appears in the alerts list (filter review_status=held) and is
left out of the alert email. NULL means the alert went out as before.
"""
from alembic import op
import sqlalchemy as sa

revision = 'ts_013'
down_revision = 'ts_012'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('signal_alerts', sa.Column('review_status', sa.String(16), nullable=True))
    op.create_index('ix_signal_alerts_review_status', 'signal_alerts', ['review_status'])


def downgrade() -> None:
    op.drop_index('ix_signal_alerts_review_status', table_name='signal_alerts')
    op.drop_column('signal_alerts', 'review_status')
