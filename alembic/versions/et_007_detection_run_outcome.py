"""Record why a detection run ended, and repair the runs that never ended

Revision ID: et_007
Revises: fa_012
Create Date: 2026-08-19

Two problems, one migration.

1. ``detection_runs`` had nowhere to record a failure. A run that hit an
   encoder outage or a database error simply stopped updating its row, so it
   sat at ``running`` forever and nobody could see why. This adds
   ``error_message`` and ``completed_at``.

2. About half of the existing rows are exactly that: runs that started and were
   never closed out. On the four tenants checked on 2026-08-19 the split was
   234/585 (bugfixing), 240/510 (wiley), 1472/2987 (wileytest), 1106/2240
   (wbm). They are all older than the deploy that fixes the lifecycle, so this
   marks any run still ``running`` after an hour as failed. Live runs are
   younger than that and are left alone.

Also repoints the notification filter default. ``["accelerating",
"new_cluster"]`` matched nothing the v2 pipeline writes: v2 detection types are
``llm_proposed`` and ``ongoing_topic``, and ``accelerating`` is a velocity, not
a detection type. Stored ``new_cluster``/``proto_cluster`` values are rewritten
to ``llm_proposed``; ``accelerating`` is kept and is now compared against the
topic's velocity. See app/services/emerging_topics/notification_filters.py.
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'et_007'
down_revision = 'fa_012'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Outcome columns on detection_runs
    op.execute("ALTER TABLE detection_runs ADD COLUMN IF NOT EXISTS error_message TEXT")
    op.execute("ALTER TABLE detection_runs ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP")

    # Historical completed runs have no recorded completion time; the run's own
    # duration is the best available answer, and NULL where we have neither.
    op.execute("""
        UPDATE detection_runs
        SET completed_at = run_date + (COALESCE(duration_seconds, 0) * INTERVAL '1 second')
        WHERE status = 'completed' AND completed_at IS NULL AND run_date IS NOT NULL
    """)

    # 2. Close out runs abandoned by the pre-fix pipeline.
    op.execute("""
        UPDATE detection_runs
        SET status = 'failed',
            completed_at = COALESCE(completed_at, NOW()),
            error_message = COALESCE(
                error_message,
                'Run never reached a terminal state; closed out by migration et_007'
            )
        WHERE status = 'running'
          AND run_date < NOW() - INTERVAL '1 hour'
    """)

    # 3. Notification filters: v2 vocabulary
    op.execute("""
        ALTER TABLE emerging_topics_settings
        ALTER COLUMN detection_type_filters
        SET DEFAULT '["llm_proposed", "accelerating"]'::jsonb
    """)
    op.execute("""
        UPDATE emerging_topics_settings
        SET detection_type_filters = (
            SELECT COALESCE(jsonb_agg(DISTINCT mapped), '[]'::jsonb)
            FROM (
                SELECT CASE value::text
                    WHEN '"new_cluster"' THEN 'llm_proposed'
                    WHEN '"proto_cluster"' THEN 'llm_proposed'
                    WHEN '"accelerating"' THEN 'accelerating'
                    WHEN '"llm_proposed"' THEN 'llm_proposed'
                    WHEN '"ongoing_topic"' THEN 'ongoing_topic'
                    ELSE NULL
                END AS mapped
                FROM jsonb_array_elements(detection_type_filters)
            ) m
            WHERE mapped IS NOT NULL
        )
        WHERE detection_type_filters IS NOT NULL
          AND jsonb_typeof(detection_type_filters) = 'array'
    """)
    # A settings row that mapped to nothing would notify on nothing at all.
    op.execute("""
        UPDATE emerging_topics_settings
        SET detection_type_filters = '["llm_proposed", "accelerating"]'::jsonb
        WHERE detection_type_filters IS NULL
           OR jsonb_typeof(detection_type_filters) <> 'array'
           OR jsonb_array_length(detection_type_filters) = 0
    """)


def downgrade() -> None:
    # The filter default goes back to the v1 vocabulary. Stored values are NOT
    # rewritten back: "llm_proposed" is the truthful description of what those
    # settings select, and re-introducing "new_cluster" would restore a filter
    # that matches nothing.
    op.execute("""
        ALTER TABLE emerging_topics_settings
        ALTER COLUMN detection_type_filters
        SET DEFAULT '["accelerating", "new_cluster"]'::jsonb
    """)

    # The closed-out runs stay closed out: they did fail, and re-opening them
    # would recreate the stuck rows this migration exists to clear.
    op.execute("ALTER TABLE detection_runs DROP COLUMN IF EXISTS completed_at")
    op.execute("ALTER TABLE detection_runs DROP COLUMN IF EXISTS error_message")
