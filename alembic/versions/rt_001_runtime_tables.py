"""Tables the app used to create at request time

tracked_emerging_topics was created by GET /api/emerging-topics/tracked (and the track route)
on every call, outside Alembic, and the keyword monitor's settings read inserted the
keyword_monitor_status default row. Both now live here. Idempotent: on a site where the table
and row already exist (every current site), this changes nothing.

Revision ID: rt_001_runtime_tables
Revises: mm_035
Create Date: 2026-10-15
"""
from alembic import op

revision = "rt_001_runtime_tables"
down_revision = "mm_035"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS tracked_emerging_topics (
            id SERIAL PRIMARY KEY,
            user_id VARCHAR(255) NOT NULL,
            topic_id INTEGER NOT NULL REFERENCES emerging_topics(id) ON DELETE CASCADE,
            tracked_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(user_id, topic_id)
        )
    """)
    op.execute("""
        INSERT INTO keyword_monitor_status (id, requests_today)
        VALUES (1, 0)
        ON CONFLICT (id) DO NOTHING
    """)


def downgrade():
    # Deliberately empty: the table holds readers' tracked topics, and it existed on every site
    # before this migration, so undoing the migration must not drop it.
    pass
