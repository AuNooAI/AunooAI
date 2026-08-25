"""Market Monitor — stored monthly briefings

Revision ID: mm_004
Revises: mm_003
Create Date: 2026-08-20

The market monitor had no report table at all: ``build_brief`` and
``build_overview`` recompute on every request, which is right for a live view
and wrong for a briefing. A briefing is a statement about a period, made at a
point in time, and it has to still say the same thing when someone opens it
next quarter.

Columns follow ``saved_signal_reports``, the house shape for a generated
report, with two market-specific additions:

``facts`` is the deterministic evidence block the prose was written from. It is
stored because it is the only way to check a briefing afterwards — any figure
in the prose that is not in the facts is a fabrication, and without the facts
that check cannot be made.

``status`` gates publication. A briefing is drafted, read, and only then
approved; a monthly job that publishes straight to a customer surface with
nobody in between is a monthly opportunity to publish something wrong.
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'mm_004'
down_revision = 'mm_003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE IF NOT EXISTS bw_market_briefings (
    id BIGSERIAL PRIMARY KEY,
    market_id INTEGER NOT NULL REFERENCES bw_markets(id) ON DELETE CASCADE,
    -- The period the briefing is about, not when it was generated. A briefing
    -- for July written in August is dated July.
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    period_label VARCHAR(32) NOT NULL,
    title VARCHAR(300),
    -- The evidence, assembled from stored rows with no model involved.
    facts JSONB NOT NULL DEFAULT '{}'::jsonb,
    report_content TEXT,
    -- Which articles and posts the facts were drawn from, so a briefing can be
    -- traced back to its sources after the corpus has moved on.
    article_uris TEXT[] NOT NULL DEFAULT '{}',
    model_used VARCHAR(64),
    -- generated | fallback — a fallback briefing is the deterministic summary
    -- written when every model attempt came back empty. It is still a real
    -- briefing and must be distinguishable from a written one.
    generation VARCHAR(16) NOT NULL DEFAULT 'generated',
    lint JSONB NOT NULL DEFAULT '[]'::jsonb,
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    status VARCHAR(16) NOT NULL DEFAULT 'draft',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_bw_market_briefings UNIQUE (market_id, period_label),
    CONSTRAINT ck_bw_market_briefings_status CHECK (
        status IN ('draft','approved','rejected')),
    CONSTRAINT ck_bw_market_briefings_generation CHECK (
        generation IN ('generated','fallback')),
    CONSTRAINT ck_bw_market_briefings_period CHECK (period_end >= period_start)
)""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_market_briefings_recent
    ON bw_market_briefings (market_id, period_start DESC)""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS bw_market_briefings CASCADE")
