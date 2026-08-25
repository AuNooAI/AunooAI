"""Entity intelligence — content links, per-entity mentions, social identity

Revision ID: ei_002
Revises: ei_001
Create Date: 2026-08-25

A post that names two vendors is one post. Today the relevance and sentiment it
gets are written onto the article row itself, so the second vendor inherits
whatever was decided about the first, and a post reused in two monitoring
topics carries one score for both. That is the defect these tables exist to
fix: the evaluation belongs to the pair of (post, company), not to the post.

``bw_entity_content_links`` says how an entity relates to an article — it owns
it, it is the subject of it, it is merely named in it — and which channel the
article arrived through. The channel is what keeps a vendor's own LinkedIn
announcement out of its reputation sentiment. A company praising itself is not
evidence that anyone else did.

``bw_entity_mentions`` holds the per-entity evaluation: relevance, sentiment,
and a stance that can say ``owned_claim`` rather than pretending a press
release is positive coverage.

``bw_entity_social_identities`` maps public accounts to companies. It is
deliberately hard to satisfy. An exact handle match may *propose* ownership and
can never confirm it, because handles collide and companies get impersonated;
only a stable platform id or a link from a verified company domain is allowed
to auto-verify. Two companies claiming the same account is a high-severity
review task, never a silent winner.

``social_accounts`` gains a stable platform id, so a company that changes its
handle stays one identity with its old handle kept in history rather than
becoming a second account nobody has mapped.

Nothing here copies an article body. ``articles`` remains the only document
store, and every table below points at it by uri.
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'ei_002'
down_revision = 'ei_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # How an entity relates to a piece of content.
    # ------------------------------------------------------------------
    # The uniqueness is (brand, article, relationship, channel) and not
    # (brand, article): a vendor can both own a post and be its subject, and
    # collapsing those would lose the distinction the channel exists for.
    # Note this does not multiply with bw_article_categories — a brand with
    # three category rows on one article still gets one link.
    op.execute("""CREATE TABLE IF NOT EXISTS bw_entity_content_links (
        id                    BIGSERIAL PRIMARY KEY,
        brand_id              INTEGER NOT NULL REFERENCES bw_brands(id) ON DELETE CASCADE,
        article_uri           TEXT NOT NULL REFERENCES articles(uri) ON DELETE CASCADE,
        relationship          VARCHAR(24) NOT NULL,
        channel               VARCHAR(24) NOT NULL,
        platform              VARCHAR(24),
        social_account_id     INTEGER REFERENCES social_accounts(id) ON DELETE SET NULL,
        attribution_method    VARCHAR(24) NOT NULL,
        matched_identifier_id INTEGER REFERENCES bw_vendor_identifiers(id) ON DELETE SET NULL,
        confidence            DOUBLE PRECISION,
        first_seen_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        last_seen_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        collection_run_id     BIGINT REFERENCES bw_collection_runs(id) ON DELETE SET NULL,
        metadata              JSONB NOT NULL DEFAULT '{}'::jsonb,
        CONSTRAINT uq_bw_entity_content_link
            UNIQUE (brand_id, article_uri, relationship, channel),
        CONSTRAINT ck_bw_entity_content_rel CHECK (relationship IN
            ('owned','mentions','about','authored_by_person','shared_by','cites')),
        CONSTRAINT ck_bw_entity_content_channel CHECK (channel IN
            ('owned_web','owned_social','earned_news','public_social',
             'community','employee','investor','research','official')),
        CONSTRAINT ck_bw_entity_content_method CHECK (attribution_method IN
            ('identifier','domain','handle','keyword','classifier','manual',
             'query_term','provider'))
    )""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_entity_content_brand
        ON bw_entity_content_links (brand_id, channel, last_seen_at DESC)""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_entity_content_article
        ON bw_entity_content_links (article_uri)""")

    # ------------------------------------------------------------------
    # What this specific entity was said to be, in this specific post.
    # ------------------------------------------------------------------
    # stance carries 'owned_claim' so a vendor's own announcement is never
    # counted as somebody else being positive about it.
    op.execute("""CREATE TABLE IF NOT EXISTS bw_entity_mentions (
        id                   BIGSERIAL PRIMARY KEY,
        brand_id             INTEGER NOT NULL REFERENCES bw_brands(id) ON DELETE CASCADE,
        article_uri          TEXT NOT NULL REFERENCES articles(uri) ON DELETE CASCADE,
        content_link_id      BIGINT REFERENCES bw_entity_content_links(id) ON DELETE SET NULL,
        mention_type         VARCHAR(24) NOT NULL,
        channel              VARCHAR(24) NOT NULL,
        platform             VARCHAR(24),
        excerpt              TEXT,
        matched_query_term_id BIGINT REFERENCES bw_entity_query_terms(id) ON DELETE SET NULL,
        matched_identifier_id INTEGER REFERENCES bw_vendor_identifiers(id) ON DELETE SET NULL,
        relevance            DOUBLE PRECISION,
        sentiment            VARCHAR(16),
        stance               VARCHAR(24),
        evaluation_method    VARCHAR(24),
        evaluation_model     VARCHAR(64),
        evaluation_version   VARCHAR(32),
        evaluated_at         TIMESTAMPTZ,
        status               VARCHAR(16) NOT NULL DEFAULT 'pending',
        dedupe_hash          VARCHAR(64) NOT NULL,
        metadata             JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_bw_entity_mention UNIQUE (brand_id, article_uri, dedupe_hash),
        CONSTRAINT ck_bw_entity_mention_type CHECK (mention_type IN
            ('explicit_name','alias','handle','product','person',
             'inferred_context','owned_attribution')),
        CONSTRAINT ck_bw_entity_mention_status CHECK (status IN
            ('pending','accepted','false_positive','disputed')),
        CONSTRAINT ck_bw_entity_mention_stance CHECK (stance IS NULL OR stance IN
            ('supportive','neutral','critical','mixed','owned_claim',
             'not_applicable')),
        CONSTRAINT ck_bw_entity_mention_relevance
            CHECK (relevance IS NULL OR (relevance >= 0 AND relevance <= 1)),
        CONSTRAINT ck_bw_entity_mention_excerpt CHECK (char_length(excerpt) <= 1000)
    )""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_entity_mentions_status
        ON bw_entity_mentions (brand_id, status)""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_entity_mentions_sentiment
        ON bw_entity_mentions (brand_id, sentiment)""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_entity_mentions_article
        ON bw_entity_mentions (article_uri)""")
    # The evaluation backlog: what has been found but not yet scored.
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_entity_mentions_pending
        ON bw_entity_mentions (created_at) WHERE evaluated_at IS NULL""")

    # ------------------------------------------------------------------
    # Which public accounts belong to, or talk about, an entity.
    # ------------------------------------------------------------------
    op.execute("""CREATE TABLE IF NOT EXISTS bw_entity_social_identities (
        id                  BIGSERIAL PRIMARY KEY,
        brand_id            INTEGER NOT NULL REFERENCES bw_brands(id) ON DELETE CASCADE,
        social_account_id   INTEGER NOT NULL REFERENCES social_accounts(id) ON DELETE CASCADE,
        relationship        VARCHAR(24) NOT NULL,
        verification_method VARCHAR(24) NOT NULL,
        confidence          DOUBLE PRECISION,
        status              VARCHAR(16) NOT NULL DEFAULT 'proposed',
        valid_from          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        valid_to            TIMESTAMPTZ,
        provenance          JSONB NOT NULL DEFAULT '{}'::jsonb,
        verified_by         TEXT,
        verified_at         TIMESTAMPTZ,
        created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT ck_bw_entity_identity_rel CHECK (relationship IN
            ('owned_company','product','executive','employee','community',
             'unofficial','critic','advocate')),
        CONSTRAINT ck_bw_entity_identity_method CHECK (verification_method IN
            ('manual','linked_from_domain','provider','content_inference')),
        CONSTRAINT ck_bw_entity_identity_status CHECK (status IN
            ('proposed','verified','rejected','retired'))
    )""")
    # Only live mappings are unique; a rejected mapping stays in history so the
    # same wrong guess is not proposed again on the next pass.
    op.execute("""CREATE UNIQUE INDEX IF NOT EXISTS uq_bw_entity_identity_active
        ON bw_entity_social_identities (brand_id, social_account_id, relationship)
        WHERE valid_to IS NULL""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_entity_identity_account
        ON bw_entity_social_identities (social_account_id, status)""")
    # Finding the second claimant on an account that is supposedly owned.
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_entity_identity_owned
        ON bw_entity_social_identities (social_account_id)
        WHERE relationship = 'owned_company' AND valid_to IS NULL""")

    # ------------------------------------------------------------------
    # Accounts keep their identity across a rename.
    # ------------------------------------------------------------------
    op.execute("""ALTER TABLE social_accounts
        ADD COLUMN IF NOT EXISTS platform_user_id TEXT,
        ADD COLUMN IF NOT EXISTS identity_status VARCHAR(16)
            NOT NULL DEFAULT 'provisional',
        ADD COLUMN IF NOT EXISTS first_seen_at TIMESTAMPTZ,
        ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ,
        ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb""")
    op.execute("""DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'ck_social_accounts_identity_status') THEN
        ALTER TABLE social_accounts
            ADD CONSTRAINT ck_social_accounts_identity_status
            CHECK (identity_status IN
                   ('provisional','verified','disputed','retired'));
    END IF;
END $$""")
    # The stable id wins where the provider gives one. The existing
    # (platform, handle_canonical) unique stays for the accounts where it
    # does not, which is most of them today.
    op.execute("""CREATE UNIQUE INDEX IF NOT EXISTS uq_social_accounts_platform_uid
        ON social_accounts (platform, platform_user_id)
        WHERE platform_user_id IS NOT NULL""")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_social_accounts_platform_uid")
    op.execute("""ALTER TABLE social_accounts
        DROP CONSTRAINT IF EXISTS ck_social_accounts_identity_status""")
    op.execute("""ALTER TABLE social_accounts
        DROP COLUMN IF EXISTS platform_user_id,
        DROP COLUMN IF EXISTS identity_status,
        DROP COLUMN IF EXISTS first_seen_at,
        DROP COLUMN IF EXISTS last_seen_at,
        DROP COLUMN IF EXISTS metadata""")
    op.execute("DROP TABLE IF EXISTS bw_entity_social_identities")
    op.execute("DROP TABLE IF EXISTS bw_entity_mentions")
    op.execute("DROP TABLE IF EXISTS bw_entity_content_links")
