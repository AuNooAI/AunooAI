"""Record whether older coverage was actually found, and retire the false rule

Revision ID: et_008
Revises: emb_768_02
Create Date: 2026-08-19

The pipeline decided "new topic" versus "ongoing topic" by asking whether at
least three articles in the previous 60 days sat within cosine distance 0.85 of
the theme. Measured on 2026-08-19 against 5,000 bugfixing articles, distances
ran 0.072-0.455 with a median of 0.148 — so 0.85 matched **100%** of the corpus
and the test always answered "ongoing". Two invented themes, a fictional product
recall and a fictional licensing reform, were both labelled as having prior
coverage from around 40 sources.

The check is now gated on an approved embedding store and returns one of three
states instead of a boolean. Where there is no validated index — everywhere, at
the time of writing — the answer is ``unknown`` and the topic stays
``llm_proposed``. See app/services/emerging_topics/historical_backend.py.

Columns
    emerging_topics.historical_coverage_status — 'ongoing' | 'not_found' |
        'unknown'. Defaults to 'unknown', which is the truthful answer for every
        row that already exists.
    emerging_topics.historical_shadow — what a shadow classifier would have
        decided, so the labelled-set validation can query real production
        decisions rather than scraping logs.

Existing ``ongoing_topic`` rows are reset to ``llm_proposed``: 12 on bugfixing,
9 on wiley, 9 on wileytest, 0 on wbm. Those labels came from a test that could
not distinguish a real topic from gibberish, and leaving them in place keeps a
known-false claim on the screen and suppresses the topics from new-topic
alerts. The previous value is preserved in ``historical_shadow`` so nothing is
lost, and the downgrade puts it back.
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'et_008'
down_revision = 'emb_768_02'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE emerging_topics
        ADD COLUMN IF NOT EXISTS historical_coverage_status VARCHAR(16)
        DEFAULT 'unknown'
    """)
    op.execute("""
        ALTER TABLE emerging_topics
        ADD COLUMN IF NOT EXISTS historical_shadow JSONB
    """)

    # Every existing row was decided by the retired rule, or not decided at all.
    op.execute("""
        UPDATE emerging_topics
        SET historical_coverage_status = 'unknown'
        WHERE historical_coverage_status IS NULL
    """)

    # Keep what the old rule claimed, then stop claiming it.
    op.execute("""
        UPDATE emerging_topics
        SET historical_shadow = jsonb_build_object(
                'retired_rule', 'deberta_distance_0.85',
                'previous_detection_type', detection_type,
                'reset_by', 'et_008',
                'reason', 'the 0.85 cutoff matched 100% of the corpus and could '
                          'not separate a real topic from invented text'
            ),
            detection_type = 'llm_proposed'
        WHERE detection_type = 'ongoing_topic'
    """)


def downgrade() -> None:
    # Put back the labels this migration reset, for the rows it reset.
    op.execute("""
        UPDATE emerging_topics
        SET detection_type = historical_shadow->>'previous_detection_type'
        WHERE historical_shadow->>'reset_by' = 'et_008'
          AND historical_shadow->>'previous_detection_type' IS NOT NULL
    """)
    op.execute("ALTER TABLE emerging_topics DROP COLUMN IF EXISTS historical_shadow")
    op.execute(
        "ALTER TABLE emerging_topics DROP COLUMN IF EXISTS historical_coverage_status"
    )
