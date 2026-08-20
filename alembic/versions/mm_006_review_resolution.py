"""Market Monitor — review tasks that can be answered, not just cleared

Revision ID: mm_006
Revises: mm_005
Create Date: 2026-08-20

The review queue raised good questions and offered no way to answer one. A task
saying "headcount recorded as zero" had a Resolve button that set a status and
left the headcount at zero, so resolving meant "I looked at this", not "this is
now correct". A queue that trains an operator to clear it rather than act on it
is worse than no queue.

Three columns close that gap.

``target_field`` is the baseline key a task is about — ``employee_count``,
``founded_year`` — so a fix can be applied from the queue rather than by hand
in the database. It is backfilled from the message text, which uses a stable
vocabulary; 25 of 26 open tasks carried no field at all before this.

``outcome`` distinguishes answers that are not the same thing. "Growth without
a baseline, founded 2026" cannot be fixed — the figure genuinely cannot exist —
and accepting that is a different act from correcting a wrong headcount or
dismissing a flag that was mistaken. All three used to look identical.

``auto_closed_at`` marks a task closed because the data arrived rather than
because a person acted. Ten of these say a headcount is zero, and LinkedIn
readings have since been collected for nineteen vendors.
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'mm_006'
down_revision = 'mm_005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""ALTER TABLE bw_review_tasks
        ADD COLUMN IF NOT EXISTS target_field VARCHAR(64),
        ADD COLUMN IF NOT EXISTS outcome VARCHAR(24),
        ADD COLUMN IF NOT EXISTS auto_closed_at TIMESTAMPTZ""")

    op.execute("""DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'ck_bw_review_tasks_outcome') THEN
        ALTER TABLE bw_review_tasks
            ADD CONSTRAINT ck_bw_review_tasks_outcome
            CHECK (outcome IS NULL OR outcome IN
                   ('fixed','accepted','dismissed','superseded'));
    END IF;
END $$""")

    # Backfill target_field from the message. The importer writes a fixed set
    # of opening phrases, so this is a lookup rather than a guess, and anything
    # that does not match is left NULL rather than assigned a likely field.
    op.execute("""UPDATE bw_review_tasks SET target_field = CASE
        WHEN message LIKE 'Headcount recorded as zero%' THEN 'employee_count'
        WHEN message LIKE 'Growth without a baseline%' THEN 'employee_growth_ytd'
        WHEN message LIKE 'Steep YTD decline%' THEN 'employee_growth_ytd'
        WHEN message LIKE 'Missing field(s). Founding Year%' THEN 'founded_year'
        WHEN message LIKE 'Missing field(s). Country%' THEN 'hq_country'
        WHEN message LIKE '%has no LinkedIn company URL%' THEN 'linkedin'
        ELSE target_field END
        WHERE target_field IS NULL""")

    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_review_tasks_open
        ON bw_review_tasks (market_id, status) WHERE status = 'open'""")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_bw_review_tasks_open")
    op.execute("""ALTER TABLE bw_review_tasks
        DROP CONSTRAINT IF EXISTS ck_bw_review_tasks_outcome""")
    for column in ("target_field", "outcome", "auto_closed_at"):
        op.execute(f"ALTER TABLE bw_review_tasks DROP COLUMN IF EXISTS {column}")
