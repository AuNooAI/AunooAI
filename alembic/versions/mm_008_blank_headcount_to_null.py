"""Blank workbook headcounts stored as 0 become unknown

Revision ID: mm_008
Revises: ei_004
Create Date: 2026-08-25

The market workbook uses 0 in the headcount column to mean "we did not have
this figure". The import stored that 0 verbatim, so seven vendors on the SOC
Automation roster claimed zero employees next to vendors showing a real count,
and every one of them had a LinkedIn page on file.

Two things went wrong downstream. The vendor tables showed a confident 0 where
every other missing value shows an em dash, and the headcount-movers query in
market_publish treated the 0 as a baseline, so the first real profile scrape
would have reported the vendor as having hired its entire staff that period.

market_import._as_headcount now keeps these out of the baseline on the way in,
and the read paths wrap the legacy baseline in NULLIF. This drops the zeros
that were already stored.

Not reversible: once the key is gone there is no way to tell a cell that said 0
from one that was blank, and both mean the same thing anyway.
"""
from alembic import op

revision = 'mm_008'
down_revision = 'ei_004'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    if conn.dialect.name != 'postgresql':
        return
    # bw_market_brands only exists on tenants that have the market monitor.
    exists = conn.exec_driver_sql(
        "SELECT to_regclass('public.bw_market_brands') IS NOT NULL"
    ).scalar()
    if not exists:
        return
    result = conn.exec_driver_sql("""
        UPDATE bw_market_brands
           SET baseline = jsonb_set(
                   baseline::jsonb, '{metrics,employee_count}', 'null'::jsonb)
         WHERE (baseline->'metrics'->>'employee_count') IS NOT NULL
           AND (baseline->'metrics'->>'employee_count')::numeric = 0
    """)
    print(f"mm_008: cleared {result.rowcount} blank-cell headcounts")


def downgrade():
    # Deliberately a no-op. Restoring the zeros would restore the bug, and the
    # original cell value is not recoverable from what is left.
    pass
