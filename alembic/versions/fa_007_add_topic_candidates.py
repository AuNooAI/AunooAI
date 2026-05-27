"""add topic_candidates inbox table

Revision ID: fa_007
Revises: fa_006
Create Date: 2026-05-24 14:00:00.000000

Candidate-topics inbox sitting between EmergingTopicsService output and
the formal forecast_topic_metadata roster. Each candidate is a detected
emerging cluster paired with an LLM relevance verdict against an
organizational profile (Wiley). Analysts triage candidates via the
Topics dashboard.

Also adds source_candidate_id on forecast_topic_metadata so promoted
topics remember which candidate they originated from.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'fa_007'
down_revision: Union[str, None] = 'fa_006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'topic_candidates',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('emerging_topic_id', sa.Integer(), nullable=False),
        sa.Column('org_profile_id', sa.Integer(), nullable=False),
        # 'in_scope' / 'adjacent' / 'off_scope' — judge verdict against the
        # organizational profile's strategic priorities + key concerns.
        sa.Column('relevance_verdict', sa.String(16), nullable=False),
        sa.Column('relevance_score', sa.Float(), nullable=True),
        sa.Column('relevance_rationale', sa.Text(), nullable=True),
        sa.Column('proposed_topic_name', sa.Text(), nullable=True),
        sa.Column('proposed_description', sa.Text(), nullable=True),
        sa.Column('proposed_tags', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        # 'pending' (default) / 'snoozed' / 'rejected' / 'promoted' / 'merged'
        # off_scope candidates are auto-set to 'rejected' on insert so they
        # never appear in the inbox.
        sa.Column('triage_status', sa.String(16), nullable=False,
                  server_default=sa.text("'pending'")),
        sa.Column('snooze_until', sa.Date(), nullable=True),
        sa.Column('rejected_reason', sa.Text(), nullable=True),
        sa.Column('promoted_to_topic', sa.Text(), nullable=True),
        sa.Column('triaged_by', sa.Text(), nullable=True),
        sa.Column('triaged_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('NOW()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['emerging_topic_id'], ['emerging_topics.id'],
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['org_profile_id'], ['organizational_profiles.id'],
            ondelete='CASCADE',
        ),
        sa.UniqueConstraint('emerging_topic_id', 'org_profile_id',
                            name='uq_topic_candidates_topic_profile'),
    )
    op.create_index('idx_topic_candidates_triage_status',
                    'topic_candidates', ['triage_status'])
    op.create_index('idx_topic_candidates_verdict',
                    'topic_candidates', ['relevance_verdict'])
    op.create_index('idx_topic_candidates_snooze_until',
                    'topic_candidates', ['snooze_until'])

    # Promoted topics remember their origin candidate so the Topics
    # dashboard can show "promoted from candidate X on YYYY-MM-DD" and
    # so re-promotion is idempotent.
    op.add_column(
        'forecast_topic_metadata',
        sa.Column('source_candidate_id', sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        'fk_forecast_topic_metadata_source_candidate',
        'forecast_topic_metadata', 'topic_candidates',
        ['source_candidate_id'], ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint(
        'fk_forecast_topic_metadata_source_candidate',
        'forecast_topic_metadata', type_='foreignkey',
    )
    op.drop_column('forecast_topic_metadata', 'source_candidate_id')
    op.drop_index('idx_topic_candidates_snooze_until', table_name='topic_candidates')
    op.drop_index('idx_topic_candidates_verdict', table_name='topic_candidates')
    op.drop_index('idx_topic_candidates_triage_status', table_name='topic_candidates')
    op.drop_table('topic_candidates')
