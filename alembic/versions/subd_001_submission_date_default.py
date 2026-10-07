"""articles/raw_articles.submission_date default to the insert time

Revision ID: subd_001
Revises: ip_003

Several raw-SQL writers (save_below_threshold_article, the brand decision
store, the science-funding and policy-tracker importers, the database route's
bulk insert) leave submission_date out, so those rows land NULL and drop out
of every date-window reader. A column default closes it for all of them at
once. ``CURRENT_TIMESTAMP::text`` prints the canonical shape the Python
writers produce via ``submission_stamp()``: local (Europe/Berlin session) time
with offset, e.g. ``2026-10-07 12:30:01.123456+02``.

Rows already NULL are back-filled from first_seen_at where it is known;
older rows without it stay NULL (their insert time is not known).
"""
from alembic import op
from sqlalchemy import inspect

revision = 'subd_001'
down_revision = 'ip_003'
branch_labels = None
depends_on = None


def _has(table, column):
    insp = inspect(op.get_bind())
    return table in insp.get_table_names() and column in {c["name"] for c in insp.get_columns(table)}


def upgrade():
    for table in ("articles", "raw_articles"):
        if _has(table, "submission_date"):
            op.execute(f"ALTER TABLE {table} ALTER COLUMN submission_date SET DEFAULT (CURRENT_TIMESTAMP)::text")
    if _has("articles", "first_seen_at"):
        op.execute("""
            UPDATE articles SET submission_date = first_seen_at::text
             WHERE submission_date IS NULL AND first_seen_at IS NOT NULL
        """)


def downgrade():
    for table in ("articles", "raw_articles"):
        if _has(table, "submission_date"):
            op.execute(f"ALTER TABLE {table} ALTER COLUMN submission_date DROP DEFAULT")
