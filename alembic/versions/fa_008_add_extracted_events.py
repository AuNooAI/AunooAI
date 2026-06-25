"""add extracted_events table for the event-extraction stage

Revision ID: fa_008
Revises: fa_007
Create Date: 2026-05-26 10:00:00.000000

The events stage runs between the supervisor's briefings and exec_summary
stages. Each call to the wiley_event_extractor_agent over a batch of
articles returns structured events (actor / action / subject / magnitude /
event_date) which we persist here so they can be edited / curated /
deduped / promoted to the deck by the analyst in the Quarterly Brief
Editor.

Dedupe key: (topic, actor_normalized, action, subject_normalized, event_date).
The runner aggregates source_urls[] across articles reporting the same
event rather than inserting duplicates.

`include_in_deck` is the analyst-curated toggle (default true).
`requires_review` is set by the extractor when confidence < 0.6 or
critical fields are missing; the editor surfaces these under a separate
header.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'fa_008'
down_revision: Union[str, None] = 'fa_007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'extracted_events',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        # Nullable so manual events added by the analyst (no source
        # assessment) can be persisted.
        sa.Column('assessment_id', sa.String(36), nullable=True),
        sa.Column('topic', sa.Text(), nullable=False),
        sa.Column('cadence', sa.String(16), nullable=True),
        sa.Column('period_label', sa.String(64), nullable=True),
        sa.Column('actor', sa.Text(), nullable=False),
        sa.Column('actor_normalized', sa.Text(), nullable=False),
        sa.Column('action', sa.Text(), nullable=False),
        sa.Column('subject', sa.Text(), nullable=False),
        sa.Column('subject_normalized', sa.Text(), nullable=False),
        sa.Column('magnitude_value', sa.Float(), nullable=True),
        sa.Column('magnitude_unit', sa.Text(), nullable=True),
        sa.Column('event_date', sa.Date(), nullable=True),
        sa.Column('source_urls', postgresql.JSONB(astext_type=sa.Text()),
                  nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('requires_review', sa.Boolean(), nullable=False,
                  server_default=sa.text('false')),
        sa.Column('include_in_deck', sa.Boolean(), nullable=False,
                  server_default=sa.text('true')),
        sa.Column('scenario_relevance', postgresql.JSONB(astext_type=sa.Text()),
                  nullable=True),
        # 'auto' (LLM extracted) | 'manual' (analyst added in editor)
        sa.Column('origin', sa.String(16), nullable=False,
                  server_default=sa.text("'auto'")),
        sa.Column('edited_by', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('NOW()'), nullable=False),
        sa.UniqueConstraint(
            'topic', 'actor_normalized', 'action',
            'subject_normalized', 'event_date',
            name='uq_extracted_events_dedupe',
        ),
    )
    op.create_index('idx_extracted_events_topic_period',
                    'extracted_events', ['topic', 'period_label'])
    op.create_index('idx_extracted_events_assessment',
                    'extracted_events', ['assessment_id'])
    op.create_index('idx_extracted_events_requires_review',
                    'extracted_events', ['requires_review'])


def downgrade() -> None:
    op.drop_index('idx_extracted_events_requires_review',
                  table_name='extracted_events')
    op.drop_index('idx_extracted_events_assessment',
                  table_name='extracted_events')
    op.drop_index('idx_extracted_events_topic_period',
                  table_name='extracted_events')
    op.drop_table('extracted_events')
