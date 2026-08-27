"""An operator verdict, 'excluded', on a market's matched articles.

The reviewer's verdicts are signal, commentary and noise, and the feed and
the news river show all three. When an operator wants a matched page out of
the market for good — a university course page that matched on "security
operations" — deleting the link does not hold: the next term scan matches it
again and the upsert puts it back. The upsert never touches the verdict, so
a verdict is where an exclusion survives. market_corpus.articles skips it.

Revision ID: mm_019
Revises: mm_018
"""

from alembic import op

revision = 'mm_019'
down_revision = 'mm_018'
branch_labels = None
depends_on = None

_VERDICTS = ('signal', 'commentary', 'noise', 'excluded')


def upgrade() -> None:
    op.execute("""
        ALTER TABLE bw_market_articles
        DROP CONSTRAINT IF EXISTS ck_bw_market_articles_verdict""")
    op.execute(f"""
        ALTER TABLE bw_market_articles
        ADD CONSTRAINT ck_bw_market_articles_verdict
        CHECK (review_verdict IS NULL OR review_verdict IN
               ({', '.join(repr(v) for v in _VERDICTS)}))""")


def downgrade() -> None:
    op.execute("""
        UPDATE bw_market_articles SET review_verdict = 'noise'
        WHERE review_verdict = 'excluded'""")
    op.execute("""
        ALTER TABLE bw_market_articles
        DROP CONSTRAINT IF EXISTS ck_bw_market_articles_verdict""")
    op.execute("""
        ALTER TABLE bw_market_articles
        ADD CONSTRAINT ck_bw_market_articles_verdict
        CHECK (review_verdict IS NULL OR review_verdict IN
               ('signal', 'commentary', 'noise'))""")
