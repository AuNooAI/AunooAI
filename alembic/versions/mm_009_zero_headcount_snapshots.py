"""Clear a zero headcount out of stored profile snapshots.

Bright Data returned ``employee_count: 0`` for a vendor whose own size band
said "2-10 employees". ``entity_field_registry`` already refuses a zero for
this field, so the canonical column was never wrong — it fell back to the
workbook figure. But two readers go to the snapshot payload directly, and
neither guarded it: the published vendor row and the per-vendor headcount
chart. One vendor would have shown 0 staff and plotted a point on the floor.

The collector no longer stores a zero. This clears the ones already written,
so the chart does not carry the artefact for the seven days until that vendor
is next collected. The band stays where it is, which is where the information
actually lives.

Same shape as mm_008, which did this for the imported workbook baseline.

Revision ID: mm_009
Revises: mm_008
"""

from alembic import op
import sqlalchemy as sa

revision = 'mm_009'
down_revision = 'mm_008'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    if conn.execute(sa.text(
            "SELECT to_regclass('public.bw_vendor_snapshots')")).scalar() is None:
        # Market Monitor is not installed on this tenant.
        return

    result = conn.execute(sa.text("""
        UPDATE bw_vendor_snapshots
           SET data = jsonb_set(data, '{employee_count}', 'null'::jsonb)
         WHERE snapshot_type = 'profile'
           AND data ? 'employee_count'
           AND data->>'employee_count' IS NOT NULL
           AND (data->>'employee_count') ~ '^[0-9]+$'
           AND (data->>'employee_count')::numeric = 0
    """))
    print(f'mm_009: cleared {result.rowcount} zero headcount(s)')


def downgrade():
    # Deliberately empty. The zero carried no information — it was the shape of
    # a field the provider left unfilled — so there is nothing to restore, and
    # writing zeros back would reintroduce the artefact this removed.
    pass
