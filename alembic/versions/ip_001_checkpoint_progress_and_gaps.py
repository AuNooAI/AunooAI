"""collection_checkpoints progress, backoff and gap records

docs/pipelines/08_INGEST_FIX_SPEC.md, work package 1. Proven coverage
(``coverage_through``) now moves only when every page of an interval was
read and saved. Four new checkpoint columns keep the rest apart from it:

``scheduled_through``  how far the schedule moved past windows a provider
                       could not page through (a list API's full page).
                       Never proof of coverage; each such move writes a
                       ``collection_gaps`` row.
``progress_at``        when coverage, the schedule or the continuation
                       cursor last moved. Every run touches ``updated_at``,
                       so it cannot say whether a scope is stuck.
``no_progress_runs``   runs in a row that moved nothing.
``next_attempt_at``    backoff: the scope is not claimed before this.

``collection_gaps`` holds one row per window the schedule moved past
without reading all of it, so the loss is on record and can be refilled.

Every step checks first, so the migration is safe to run again. The old
application ignores the new columns, so a code rollback needs no downgrade.

Revision ID: ip_001
Revises: bm_001
Create Date: 2026-10-07
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = 'ip_001'
down_revision = 'bm_001'
branch_labels = None
depends_on = None


def upgrade():
    insp = inspect(op.get_bind())
    cols = {c['name'] for c in insp.get_columns('collection_checkpoints')}
    if 'scheduled_through' not in cols:
        op.add_column('collection_checkpoints', sa.Column('scheduled_through', sa.DateTime(timezone=True)))
    if 'progress_at' not in cols:
        op.add_column('collection_checkpoints', sa.Column('progress_at', sa.DateTime(timezone=True)))
    if 'no_progress_runs' not in cols:
        op.add_column('collection_checkpoints', sa.Column(
            'no_progress_runs', sa.Integer(), nullable=False, server_default=sa.text('0')))
    if 'next_attempt_at' not in cols:
        op.add_column('collection_checkpoints', sa.Column('next_attempt_at', sa.DateTime(timezone=True)))

    if 'collection_gaps' not in insp.get_table_names():
        op.create_table(
            'collection_gaps',
            sa.Column('id', sa.BigInteger(), primary_key=True),
            sa.Column('provider', sa.String(40), nullable=False),
            sa.Column('scope_key', sa.Text(), nullable=False),
            sa.Column('interval_start', sa.DateTime(timezone=True)),
            sa.Column('interval_end', sa.DateTime(timezone=True)),
            sa.Column('reason', sa.String(32), nullable=False),
            sa.Column('items', sa.Integer()),
            sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
            sa.Column('resolved_at', sa.DateTime(timezone=True)),
        )
        op.create_index('ix_collection_gaps_scope', 'collection_gaps', ['provider', 'scope_key'])


def downgrade():
    insp = inspect(op.get_bind())
    if 'collection_gaps' in insp.get_table_names():
        op.drop_index('ix_collection_gaps_scope', table_name='collection_gaps')
        op.drop_table('collection_gaps')
    cols = {c['name'] for c in insp.get_columns('collection_checkpoints')}
    for name in ('next_attempt_at', 'no_progress_runs', 'progress_at', 'scheduled_through'):
        if name in cols:
            op.drop_column('collection_checkpoints', name)
