"""add lock + edit_history columns for the Quarterly Brief Editor

Revision ID: fa_009
Revises: fa_008
Create Date: 2026-05-26 11:00:00.000000

The Quarterly Brief Editor lets the analyst edit, lock, and curate the
generated bundle before sending it to Wiley.

Locked sections survive supervisor re-runs (mirrors the
.proposed/.approved overlay pattern already used for deck overlays):
the supervisor wrapper `_apply_locks_after_call` restores any subtree
listed in `locked_keys` after the agent returns.

Schema choice: three JSONB columns, no new tables. Edits mutate the
existing `forecast_bundle_synthesis.payload` (or
`forecast_assessments.summary`) in place — renderers already read from
those JSONBs so no renderer change is needed for the override
mechanism itself.

- `locked_keys`        — list of dot-paths the supervisor must not
                         overwrite (e.g. "exec_summary.letter",
                         "cross_cutting_themes[2].body").
- `edit_history`       — append-only audit log:
                         [{key, prev_hash, next_hash, edited_by, edited_at}].
                         Hashes (not values) keep the column small.
- `summary_locked_keys`— per-topic equivalent on forecast_assessments,
                         scoped to that topic's summary JSONB.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'fa_009'
down_revision: Union[str, None] = 'fa_008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'forecast_bundle_synthesis',
        sa.Column(
            'locked_keys',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        'forecast_bundle_synthesis',
        sa.Column(
            'edit_history',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        'forecast_assessments',
        sa.Column(
            'summary_locked_keys',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column('forecast_assessments', 'summary_locked_keys')
    op.drop_column('forecast_bundle_synthesis', 'edit_history')
    op.drop_column('forecast_bundle_synthesis', 'locked_keys')
