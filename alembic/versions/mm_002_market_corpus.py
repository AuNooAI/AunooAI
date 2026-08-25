"""Market Monitor — market-term matches against the existing article corpus

Revision ID: mm_002
Revises: mm_001
Create Date: 2026-08-20

Brand Watcher answers "who was mentioned". It matches vendor names, so an
article about SOC automation that names no vendor can never attribute to one,
however wide the scan. That is the right answer to its own question and the
wrong one for a market monitor, which needs "what is relevant to this category"
— and nothing in the codebase asked that.

This table is where that second question's answers live. A row means an article
already in ``articles`` matched the market's own search language. The market is
the subject, not a vendor, so it does not belong in ``bw_article_categories``:
that table is keyed on ``brand_id`` and every row there is a claim about a
company.

``matched_terms`` is kept because a score with no evidence behind it cannot be
argued with. An operator who thinks a match is wrong can see which phrase
pulled it in and edit the market's terms.
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'mm_002'
down_revision = 'mm_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE IF NOT EXISTS bw_market_articles (
    id BIGSERIAL PRIMARY KEY,
    market_id INTEGER NOT NULL REFERENCES bw_markets(id) ON DELETE CASCADE,
    -- ``articles`` is keyed on uri in this codebase, not on an integer id.
    article_uri TEXT NOT NULL REFERENCES articles(uri) ON DELETE CASCADE,
    -- Which of the market's phrases matched, so a disputed row can be argued
    -- with rather than only overridden.
    matched_terms TEXT[] NOT NULL DEFAULT '{}',
    -- Split out because a phrase in the headline is a much stronger signal
    -- than the same phrase in the third paragraph.
    title_terms INTEGER NOT NULL DEFAULT 0,
    body_terms INTEGER NOT NULL DEFAULT 0,
    score REAL NOT NULL DEFAULT 0,
    -- term_match today. Leaves room for an embedding pass later without a
    -- second table.
    method VARCHAR(24) NOT NULL DEFAULT 'term_match',
    -- collected: the market's own collection topic already owned it.
    -- corpus:    it was collected for some other topic and matched here.
    origin VARCHAR(16) NOT NULL DEFAULT 'corpus',
    matched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_bw_market_articles UNIQUE (market_id, article_uri)
)""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_market_articles_rank
    ON bw_market_articles (market_id, score DESC, matched_at DESC)""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_market_articles_recent
    ON bw_market_articles (market_id, matched_at DESC)""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_market_articles_uri
    ON bw_market_articles (article_uri)""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS bw_market_articles CASCADE")
