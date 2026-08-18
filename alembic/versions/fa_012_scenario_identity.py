"""stable identity for scenarios, and a scenario-status key that actually holds

Revision ID: fa_012
Revises: bwr_001
Create Date: 2026-08-18 22:40:00.000000

Scenario identity was positional. A verdict's ``scenario_idx`` is only its
place in the list ``assess_run`` builds — the run's original scenarios followed
by any promoted ones — so it shifts whenever that list changes, and it means
different things in different runs. Two consequences:

* Promoted scenarios had no recorded identity at all, so the UI inferred the
  pairing by arithmetic: the i-th addendum was assumed to be the (N-K+i)-th
  verdict. Adding a promoted scenario between assessments, or skipping one
  because it was marked done, shifts every pairing after it — showing one
  scenario's verdict under another's title, and writing "mark done" to the
  wrong scenario.
* Original scenarios were keyed by index too, so a reordered payload moved
  status onto a different scenario.

This migration is additive. Existing rows keep working: the new columns are
nullable, ``scenario_idx`` is retained for display ordering and legacy reads,
and no historical ``raw_output`` is rewritten. Keys for legacy runs are derived
on read instead (see ``app/services/scenario_identity.py``).

Columns
    forecast_scenario_verdicts.user_scenario_id — which promoted scenario this
        verdict scored; NULL for originals.
    forecast_scenario_verdicts.scenario_key — stable key of the original
        scenario this verdict scored; NULL for promoted ones and for verdicts
        written before this migration.
    forecast_scenario_status.scenario_key — same, for status rows.

No foreign keys: ``forecast_user_scenarios`` rows are deletable and verdict
history is meant to survive that, matching the existing absence of an FK on
``run_id`` in these tables.

Constraints on forecast_scenario_status
    The previous ``UNIQUE (run_id, scenario_idx, user_scenario_id)`` could
    never fire — one of those columns is always NULL and Postgres treats NULLs
    as distinct, so it has enforced nothing since fa_003. The facade knows and
    hand-rolls a SELECT-then-INSERT, which is a race with no database backstop.

    Replaced with a CHECK that a row names exactly one kind of scenario, plus
    three partial unique indexes that do fire: keyed originals, legacy
    index-only originals, and addendums. Verified before writing that no tenant
    has duplicate or malformed rows.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'fa_012'
down_revision: Union[str, None] = 'bwr_001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── verdicts: record which scenario a verdict actually scored ──────────
    op.add_column(
        'forecast_scenario_verdicts',
        sa.Column('user_scenario_id', sa.String(36), nullable=True),
    )
    op.add_column(
        'forecast_scenario_verdicts',
        sa.Column('scenario_key', sa.String(64), nullable=True),
    )
    op.create_index(
        'ix_scenario_verdicts_user_scenario',
        'forecast_scenario_verdicts', ['user_scenario_id'],
    )
    op.create_index(
        'ix_scenario_verdicts_scenario_key',
        'forecast_scenario_verdicts', ['scenario_key'],
    )

    # ── status: add the key, then constraints that can actually fire ───────
    op.add_column(
        'forecast_scenario_status',
        sa.Column('scenario_key', sa.String(64), nullable=True),
    )

    op.execute(
        "ALTER TABLE forecast_scenario_status "
        "DROP CONSTRAINT IF EXISTS uq_scenario_status_run_keys"
    )
    # A row names exactly one scenario: a keyed original, a legacy index-only
    # original, or an addendum. scenario_idx may accompany scenario_key as
    # display ordering, so it is not counted as an identity of its own when a
    # key is present.
    op.create_check_constraint(
        'ck_scenario_status_one_identity',
        'forecast_scenario_status',
        '(CASE WHEN scenario_key IS NOT NULL THEN 1 ELSE 0 END '
        ' + CASE WHEN user_scenario_id IS NOT NULL THEN 1 ELSE 0 END) <= 1 '
        'AND (scenario_key IS NOT NULL OR user_scenario_id IS NOT NULL '
        '     OR scenario_idx IS NOT NULL)',
    )
    op.create_index(
        'uq_scenario_status_key',
        'forecast_scenario_status', ['run_id', 'scenario_key'],
        unique=True, postgresql_where=sa.text('scenario_key IS NOT NULL'),
    )
    op.create_index(
        'uq_scenario_status_addendum',
        'forecast_scenario_status', ['run_id', 'user_scenario_id'],
        unique=True, postgresql_where=sa.text('user_scenario_id IS NOT NULL'),
    )
    # Legacy rows that predate scenario_key: still one per (run, index).
    op.create_index(
        'uq_scenario_status_legacy_idx',
        'forecast_scenario_status', ['run_id', 'scenario_idx'],
        unique=True,
        postgresql_where=sa.text(
            'scenario_key IS NULL AND user_scenario_id IS NULL '
            'AND scenario_idx IS NOT NULL'
        ),
    )
    op.create_index(
        'ix_forecast_scenario_status_key', 'forecast_scenario_status', ['scenario_key'],
    )


def downgrade() -> None:
    op.drop_index('ix_forecast_scenario_status_key', table_name='forecast_scenario_status')
    op.drop_index('uq_scenario_status_legacy_idx', table_name='forecast_scenario_status')
    op.drop_index('uq_scenario_status_addendum', table_name='forecast_scenario_status')
    op.drop_index('uq_scenario_status_key', table_name='forecast_scenario_status')
    op.drop_constraint(
        'ck_scenario_status_one_identity', 'forecast_scenario_status', type_='check',
    )
    op.drop_column('forecast_scenario_status', 'scenario_key')

    op.create_unique_constraint(
        'uq_scenario_status_run_keys',
        'forecast_scenario_status',
        ['run_id', 'scenario_idx', 'user_scenario_id'],
    )

    op.drop_index('ix_scenario_verdicts_scenario_key', table_name='forecast_scenario_verdicts')
    op.drop_index('ix_scenario_verdicts_user_scenario', table_name='forecast_scenario_verdicts')
    op.drop_column('forecast_scenario_verdicts', 'scenario_key')
    op.drop_column('forecast_scenario_verdicts', 'user_scenario_id')
