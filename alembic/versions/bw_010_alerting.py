"""Brand Watcher push alerting: alert config + persisted alert events

bw_alert_config: per-tenant (optionally per-brand) adverse-alert rules, channels
and recipients. bw_alert_events: persisted rule-trigger events with dedup_key
(rule|brand|time-bucket) so re-evaluation is idempotent, plus delivery record
and acknowledgement.

Revision ID: bw_010_alerting
Revises: bw_009_article_stories
Create Date: 2026-07-03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'bw_010_alerting'
down_revision = "bw_009_article_stories"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'bw_alert_config',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('brand_id', sa.Integer(), sa.ForeignKey('bw_brands.id', ondelete='CASCADE'), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('rules', postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('channels', postgresql.JSONB(), nullable=False, server_default=sa.text('\'{"in_app": true, "email": false, "webhook": false}\'::jsonb')),
        sa.Column('email_recipients', postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('webhook_url', sa.Text(), nullable=True),
        sa.Column('cooldown_hours', sa.Integer(), nullable=False, server_default=sa.text('24')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_table(
        'bw_alert_events',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('brand_id', sa.Integer(), sa.ForeignKey('bw_brands.id', ondelete='CASCADE'), nullable=True),
        sa.Column('rule', sa.Text(), nullable=False),
        sa.Column('severity', sa.Text(), nullable=False, server_default=sa.text("'medium'")),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('body', sa.Text(), nullable=True),
        sa.Column('payload', postgresql.JSONB(), nullable=True),
        sa.Column('dedup_key', sa.Text(), nullable=False, unique=True),
        sa.Column('delivered', postgresql.JSONB(), nullable=True),
        sa.Column('acknowledged_by', sa.Text(), nullable=True),
        sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_index('idx_bw_alert_events_created', 'bw_alert_events', ['created_at'])
    op.create_index('idx_bw_alert_events_brand', 'bw_alert_events', ['brand_id'])


def downgrade():
    op.drop_table('bw_alert_events')
    op.drop_table('bw_alert_config')
