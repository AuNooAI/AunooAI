"""Finding attributes on entity events: materiality, review state, why it matters.

``bw_entity_events`` already carried most of the specification's finding model —
an occurrence date with its own precision, a first-observed date, corroboration,
evidence rows and affected entities. Four things were missing, and all four are
filterable, so they are columns rather than another corner of ``attributes``:

``materiality``    how much this change matters. The spec orders the Findings
                   page by it, so it has to be sortable.
``review_state``   whether a human, a model, or nobody has looked at it. A
                   reader is entitled to know which.
``why_it_matters`` bounded interpretation, kept in its own column so it can
                   never be confused with ``description``, which is facts.
``limitations``    what this finding does not establish.

Nullable throughout: the 194 existing events predate all four, and backfilling
a judgement about materiality onto them would be inventing one.

Revision ID: mm_010
Revises: mm_009
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'mm_010'
down_revision = 'mm_009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('bw_entity_events',
                  sa.Column('materiality', sa.String(8), nullable=True))
    op.add_column('bw_entity_events',
                  sa.Column('review_state', sa.String(20), nullable=False,
                            server_default='unreviewed'))
    op.add_column('bw_entity_events',
                  sa.Column('why_it_matters', sa.Text(), nullable=True))
    op.add_column('bw_entity_events',
                  sa.Column('limitations', postgresql.JSONB(),
                            nullable=False, server_default='[]'))

    # Constrained rather than free text: the Findings page orders by these, and
    # an unexpected value would sort in an undefined place instead of failing.
    op.create_check_constraint(
        'ck_bw_entity_events_materiality', 'bw_entity_events',
        "materiality IS NULL OR materiality IN ('high', 'medium', 'low')")
    op.create_check_constraint(
        'ck_bw_entity_events_review_state', 'bw_entity_events',
        "review_state IN ('unreviewed', 'machine_reviewed', "
        "'analyst_reviewed')")

    # The Findings page's default order is materiality, then evidence state,
    # then date. This index serves that read directly.
    op.create_index('ix_bw_entity_events_findings', 'bw_entity_events',
                    ['status', 'materiality', 'occurred_at'],
                    postgresql_where=sa.text("status = 'active'"))


def downgrade() -> None:
    op.drop_index('ix_bw_entity_events_findings',
                  table_name='bw_entity_events')
    op.drop_constraint('ck_bw_entity_events_review_state',
                       'bw_entity_events', type_='check')
    op.drop_constraint('ck_bw_entity_events_materiality',
                       'bw_entity_events', type_='check')
    op.drop_column('bw_entity_events', 'limitations')
    op.drop_column('bw_entity_events', 'why_it_matters')
    op.drop_column('bw_entity_events', 'review_state')
    op.drop_column('bw_entity_events', 'materiality')
