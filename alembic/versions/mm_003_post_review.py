"""Market Monitor — LLM review verdicts on vendor posts

Revision ID: mm_003
Revises: mm_002
Create Date: 2026-08-20

A market monitor cannot use vendor LinkedIn posts wholesale and cannot throw
them away either. Wholesale, they swamp everything — 562 posts against 122
news articles — and most are conference-booth notices. Thrown away, the market
loses the launches, funding notes, customer wins and hiring signals that
vendors announce there first and nowhere else.

No keyword rule separates the two. "Dropzone AI is a 2025 IA40 winner" and
"If you're at the Gartner Summit today, come meet the team at booth 4141" are
the same shape. So each post gets read once and judged, and the judgement is
stored next to it.

These columns go on ``bw_market_articles`` rather than into a new table because
the question is the same one that table already answers — is this article part
of what this market is about — arrived at a different way. A row can now carry
a phrase-match score, a review verdict, or both.
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'mm_003'
down_revision = 'mm_002'
branch_labels = None
depends_on = None

COLUMNS = (
    "review_verdict", "review_kind", "review_reason",
    "review_model", "reviewed_at",
)


def upgrade() -> None:
    # signal     — a fact about the company or the market: a launch, a raise,
    #              a customer, a partnership, an award, a hire, a finding.
    # commentary — substantive analysis of the market with no new fact in it.
    #              Worth reading, not worth reporting as a change.
    # noise      — conference presence, generic recruiting, content-free hype.
    op.execute("""ALTER TABLE bw_market_articles
        ADD COLUMN IF NOT EXISTS review_verdict VARCHAR(16),
        ADD COLUMN IF NOT EXISTS review_kind VARCHAR(24),
        ADD COLUMN IF NOT EXISTS review_reason TEXT,
        ADD COLUMN IF NOT EXISTS review_model VARCHAR(64),
        ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ""")

    op.execute("""DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'ck_bw_market_articles_verdict') THEN
        ALTER TABLE bw_market_articles
            ADD CONSTRAINT ck_bw_market_articles_verdict
            CHECK (review_verdict IS NULL
                   OR review_verdict IN ('signal','commentary','noise'));
    END IF;
END $$""")

    # The read path wants "posts worth showing", which is a verdict lookup
    # inside one market.
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_market_articles_verdict
    ON bw_market_articles (market_id, review_verdict)
    WHERE review_verdict IS NOT NULL""")

    # And the review path wants "what have I not read yet", which is the
    # complement. Partial so it stays small as the reviewed set grows.
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_market_articles_unreviewed
    ON bw_market_articles (market_id)
    WHERE review_verdict IS NULL""")

    # A reviewed post that matched no phrase still needs a row, so the phrase
    # score has to be allowed to mean "not scored" rather than "scored zero".
    op.execute("""ALTER TABLE bw_market_articles
        ALTER COLUMN score DROP NOT NULL""")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_bw_market_articles_verdict")
    op.execute("DROP INDEX IF EXISTS ix_bw_market_articles_unreviewed")
    op.execute("""ALTER TABLE bw_market_articles
        DROP CONSTRAINT IF EXISTS ck_bw_market_articles_verdict""")
    for column in COLUMNS:
        op.execute(f"ALTER TABLE bw_market_articles DROP COLUMN IF EXISTS {column}")
