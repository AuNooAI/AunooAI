"""Timeline mementos: per-brand/per-topic event timeline (monolith port of saas /timeline)

timeline_events: one row per "memento" — a structured, dated development for a
scope (a Brand Watcher brand or a keyword-group topic). Daily events are
extracted from that day's articles (SQL detectors + one LLM pass); weekly and
monthly LLM rollups absorb them (superseded_by_id / is_stale), so the timeline
compacts instead of repeating.

Dedup design (differs from saas deliberately): content_hash does NOT include
the event date for story-type events, so the same real-world story recurring
across days bumps occurrence_count / last_seen_date on ONE memento instead of
minting a duplicate every day.

Revision ID: tl_001_timeline_mementos
Revises: bw_019_account_watchlist
Create Date: 2026-07-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'tl_001_timeline_mementos'
down_revision = 'bw_019_account_watchlist'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'timeline_events',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('scope_type', sa.Text(), nullable=False),   # 'topic' | 'brand'
        sa.Column('scope_id', sa.Text(), nullable=False),     # topic name / bw_brands.id::text
        sa.Column('event_type', sa.Text(), nullable=False),
        sa.Column('event_subtype', sa.Text(), nullable=True),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('significance', sa.Text(), nullable=False, server_default=sa.text("'medium'")),
        sa.Column('event_data', postgresql.JSONB(), nullable=True),
        sa.Column('entities', postgresql.JSONB(), nullable=True),
        sa.Column('article_uris', postgresql.JSONB(), nullable=True),
        sa.Column('article_count', sa.Integer(), nullable=False, server_default=sa.text('1')),
        sa.Column('content_hash', sa.Text(), nullable=False),
        sa.Column('event_date', sa.Date(), nullable=False),
        sa.Column('last_seen_date', sa.Date(), nullable=True),
        sa.Column('occurrence_count', sa.Integer(), nullable=False, server_default=sa.text('1')),
        sa.Column('granularity', sa.Text(), nullable=False, server_default=sa.text("'daily'")),
        sa.Column('is_stale', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('superseded_by_id', sa.Integer(),
                  sa.ForeignKey('timeline_events.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.UniqueConstraint('scope_type', 'scope_id', 'content_hash', name='uq_timeline_event_hash'),
    )
    op.create_index('idx_timeline_events_scope_date', 'timeline_events',
                    ['scope_type', 'scope_id', 'event_date'])
    op.create_index('idx_timeline_events_scope_gran', 'timeline_events',
                    ['scope_type', 'scope_id', 'granularity'])

    op.create_table(
        'timeline_runs',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('scope_type', sa.Text(), nullable=False),
        sa.Column('scope_id', sa.Text(), nullable=False),
        sa.Column('run_type', sa.Text(), nullable=False),  # daily_extraction | weekly_rollup | monthly_rollup | state_doc
        sa.Column('run_date', sa.Date(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False, server_default=sa.text("'completed'")),
        sa.Column('articles_processed', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('events_created', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('events_deduplicated', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('duration_seconds', sa.Float(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.UniqueConstraint('scope_type', 'scope_id', 'run_type', 'run_date', name='uq_timeline_run'),
    )

    op.create_table(
        'timeline_state_docs',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('scope_type', sa.Text(), nullable=False),
        sa.Column('scope_id', sa.Text(), nullable=False),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('key_entities', postgresql.JSONB(), nullable=True),
        sa.Column('current_trend', sa.Text(), nullable=True),
        sa.Column('event_count_at_refresh', sa.Integer(), nullable=True),
        sa.Column('generated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.UniqueConstraint('scope_type', 'scope_id', name='uq_timeline_state_doc'),
    )


def downgrade():
    op.drop_table('timeline_state_docs')
    op.drop_table('timeline_runs')
    op.drop_table('timeline_events')
