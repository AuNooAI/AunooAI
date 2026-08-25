"""Entity intelligence — events, evidence, and versioned narratives

Revision ID: ei_003
Revises: ei_002
Create Date: 2026-08-25

An event is a claim that something happened. The difference between a useful
event layer and a misleading one is entirely in how that claim is qualified,
so the qualification is in the schema rather than in the prose.

``corroboration`` says who is asserting it. A company's own announcement starts
at ``vendor_claim`` and stays there until somebody unconnected says the same
thing. ``bw_entity_event_evidence`` carries a source independence key, and the
count that matters is the number of *distinct* keys — ten syndicated copies of
one wire story are one source, and counting rows instead of sources is how a
press release comes to look independently confirmed.

``occurred_at`` is nullable and ``date_precision`` says how well it is known.
An event whose date nobody stated gets a null date, not the date we happened to
extract it. ``bw_market_events.event_date`` loses its NOT NULL for the same
reason: it is now a projection of an entity event, and a projection must not
invent what the source lacks.

The narrative columns make generated prose auditable. ``facts`` holds the
deterministic pack the text was written from, ``bw_narrative_evidence`` holds
what it may cite, and ``lint`` holds what a check found wrong with it. A
narrative that cites something absent from both is a failure, not a style
problem. ``supersedes_id`` means a regenerated brief replaces its predecessor
by pointing at it rather than by overwriting it.

``bw_market_events`` and ``bw_event_vendors`` have never held a row and no code
writes them, so nothing here is protecting existing behavior; they become the
per-market projection of the new entity events.
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'ei_003'
down_revision = 'ei_002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Market-independent events.
    # ------------------------------------------------------------------
    op.execute("""CREATE TABLE IF NOT EXISTS bw_entity_events (
        id                 BIGSERIAL PRIMARY KEY,
        event_type         VARCHAR(48) NOT NULL,
        event_subtype      VARCHAR(64),
        title              VARCHAR(500) NOT NULL,
        description        TEXT NOT NULL,
        occurred_at        TIMESTAMPTZ,
        date_precision     VARCHAR(16) NOT NULL DEFAULT 'unknown',
        published_at       TIMESTAMPTZ,
        first_observed_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        last_observed_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        confidence         DOUBLE PRECISION,
        corroboration      VARCHAR(24) NOT NULL DEFAULT 'uncorroborated',
        status             VARCHAR(16) NOT NULL DEFAULT 'active',
        attributes         JSONB NOT NULL DEFAULT '{}'::jsonb,
        extraction_version VARCHAR(32),
        dedupe_hash        VARCHAR(64) NOT NULL UNIQUE,
        created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT ck_bw_entity_events_precision CHECK (date_precision IN
            ('minute','day','month','unknown')),
        CONSTRAINT ck_bw_entity_events_corroboration CHECK (corroboration IN
            ('uncorroborated','vendor_claim','single_source','corroborated',
             'primary_document')),
        CONSTRAINT ck_bw_entity_events_status CHECK (status IN
            ('active','superseded','rejected','pending_review')),
        CONSTRAINT ck_bw_entity_events_confidence
            CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
        -- A dated event must say how well the date is known; an undated one
        -- must not claim precision it does not have.
        CONSTRAINT ck_bw_entity_events_date_known CHECK (
            (occurred_at IS NULL AND date_precision = 'unknown')
            OR (occurred_at IS NOT NULL AND date_precision <> 'unknown'))
    )""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_entity_events_type
        ON bw_entity_events (event_type, occurred_at DESC NULLS LAST)""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_entity_events_recent
        ON bw_entity_events (last_observed_at DESC)""")

    op.execute("""CREATE TABLE IF NOT EXISTS bw_entity_event_entities (
        id         BIGSERIAL PRIMARY KEY,
        event_id   BIGINT NOT NULL REFERENCES bw_entity_events(id) ON DELETE CASCADE,
        brand_id   INTEGER NOT NULL REFERENCES bw_brands(id) ON DELETE CASCADE,
        relation   VARCHAR(24) NOT NULL DEFAULT 'subject',
        confidence DOUBLE PRECISION,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_bw_entity_event_entity UNIQUE (event_id, brand_id, relation),
        CONSTRAINT ck_bw_entity_event_relation CHECK (relation IN
            ('subject','acquirer','target','partner','customer','investor',
             'competitor'))
    )""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_entity_event_entities_brand
        ON bw_entity_event_entities (brand_id, relation)""")

    # Exactly one reference column is populated per row, and which one is
    # named by evidence_type, so a row cannot claim to be an article and point
    # at a snapshot.
    op.execute("""CREATE TABLE IF NOT EXISTS bw_entity_event_evidence (
        id              BIGSERIAL PRIMARY KEY,
        event_id        BIGINT NOT NULL REFERENCES bw_entity_events(id) ON DELETE CASCADE,
        evidence_type   VARCHAR(16) NOT NULL,
        article_uri     TEXT REFERENCES articles(uri) ON DELETE CASCADE,
        snapshot_id     BIGINT REFERENCES bw_vendor_snapshots(id) ON DELETE CASCADE,
        observation_id  BIGINT REFERENCES bw_entity_observations(id) ON DELETE CASCADE,
        mention_id      BIGINT REFERENCES bw_entity_mentions(id) ON DELETE CASCADE,
        relationship    VARCHAR(16) NOT NULL DEFAULT 'supports',
        independence_key TEXT NOT NULL,
        excerpt         TEXT,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT ck_bw_entity_evidence_type CHECK (evidence_type IN
            ('article','snapshot','observation','mention')),
        CONSTRAINT ck_bw_entity_evidence_rel CHECK (relationship IN
            ('supports','contradicts','originates','context')),
        CONSTRAINT ck_bw_entity_evidence_excerpt CHECK (char_length(excerpt) <= 1000),
        CONSTRAINT ck_bw_entity_evidence_one_ref CHECK (
            (CASE WHEN article_uri    IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN snapshot_id    IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN observation_id IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN mention_id     IS NOT NULL THEN 1 ELSE 0 END) = 1)
    )""")
    op.execute("""CREATE UNIQUE INDEX IF NOT EXISTS uq_bw_entity_evidence_article
        ON bw_entity_event_evidence (event_id, relationship, article_uri)
        WHERE article_uri IS NOT NULL""")
    op.execute("""CREATE UNIQUE INDEX IF NOT EXISTS uq_bw_entity_evidence_snapshot
        ON bw_entity_event_evidence (event_id, relationship, snapshot_id)
        WHERE snapshot_id IS NOT NULL""")
    op.execute("""CREATE UNIQUE INDEX IF NOT EXISTS uq_bw_entity_evidence_observation
        ON bw_entity_event_evidence (event_id, relationship, observation_id)
        WHERE observation_id IS NOT NULL""")
    op.execute("""CREATE UNIQUE INDEX IF NOT EXISTS uq_bw_entity_evidence_mention
        ON bw_entity_event_evidence (event_id, relationship, mention_id)
        WHERE mention_id IS NOT NULL""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_entity_evidence_independence
        ON bw_entity_event_evidence (event_id, independence_key)""")

    # ------------------------------------------------------------------
    # Narratives: what was generated, from what, and whether it checks out.
    # ------------------------------------------------------------------
    op.execute("""ALTER TABLE bw_tracker_narratives
        ADD COLUMN IF NOT EXISTS narrative_type VARCHAR(24)
            NOT NULL DEFAULT 'brand_brief',
        ADD COLUMN IF NOT EXISTS status VARCHAR(16) NOT NULL DEFAULT 'draft',
        ADD COLUMN IF NOT EXISTS facts JSONB NOT NULL DEFAULT '{}'::jsonb,
        ADD COLUMN IF NOT EXISTS model_used VARCHAR(64),
        ADD COLUMN IF NOT EXISTS prompt_version VARCHAR(32),
        ADD COLUMN IF NOT EXISTS generator_version VARCHAR(32),
        ADD COLUMN IF NOT EXISTS source_cutoff_at TIMESTAMPTZ,
        ADD COLUMN IF NOT EXISTS supersedes_id INTEGER,
        ADD COLUMN IF NOT EXISTS lint JSONB NOT NULL DEFAULT '[]'::jsonb""")
    op.execute("""DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'fk_bw_narratives_supersedes') THEN
        ALTER TABLE bw_tracker_narratives
            ADD CONSTRAINT fk_bw_narratives_supersedes
            FOREIGN KEY (supersedes_id)
            REFERENCES bw_tracker_narratives(id) ON DELETE SET NULL;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'ck_bw_narratives_type') THEN
        ALTER TABLE bw_tracker_narratives
            ADD CONSTRAINT ck_bw_narratives_type
            CHECK (narrative_type IN ('brand_brief','theme_cluster',
                                      'social_narrative','event_summary'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'ck_bw_narratives_status') THEN
        ALTER TABLE bw_tracker_narratives
            ADD CONSTRAINT ck_bw_narratives_status
            CHECK (status IN ('draft','approved','rejected','superseded'));
    END IF;
END $$""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_narratives_type
        ON bw_tracker_narratives (brand_id, narrative_type, generated_at DESC)""")

    # Existing rows are brand briefs. Nothing is inferred from the prose.
    op.execute("""UPDATE bw_tracker_narratives
        SET narrative_type = 'brand_brief', status = 'approved'
        WHERE narrative_type IS NULL OR narrative_type = 'brand_brief'""")

    op.execute("""CREATE TABLE IF NOT EXISTS bw_narrative_evidence (
        id             BIGSERIAL PRIMARY KEY,
        narrative_id   INTEGER NOT NULL
                       REFERENCES bw_tracker_narratives(id) ON DELETE CASCADE,
        evidence_type  VARCHAR(16) NOT NULL,
        article_uri    TEXT REFERENCES articles(uri) ON DELETE CASCADE,
        event_id       BIGINT REFERENCES bw_entity_events(id) ON DELETE CASCADE,
        mention_id     BIGINT REFERENCES bw_entity_mentions(id) ON DELETE CASCADE,
        observation_id BIGINT REFERENCES bw_entity_observations(id) ON DELETE CASCADE,
        snapshot_id    BIGINT REFERENCES bw_vendor_snapshots(id) ON DELETE CASCADE,
        relationship   VARCHAR(16) NOT NULL DEFAULT 'supports',
        rank           INTEGER NOT NULL DEFAULT 0,
        excerpt        TEXT,
        created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT ck_bw_narrative_evidence_type CHECK (evidence_type IN
            ('article','event','mention','observation','snapshot')),
        CONSTRAINT ck_bw_narrative_evidence_excerpt
            CHECK (char_length(excerpt) <= 1000),
        CONSTRAINT ck_bw_narrative_evidence_one_ref CHECK (
            (CASE WHEN article_uri    IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN event_id       IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN mention_id     IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN observation_id IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN snapshot_id    IS NOT NULL THEN 1 ELSE 0 END) = 1)
    )""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_narrative_evidence
        ON bw_narrative_evidence (narrative_id, rank)""")

    # ------------------------------------------------------------------
    # The market projection.
    # ------------------------------------------------------------------
    op.execute("""ALTER TABLE bw_market_events
        ADD COLUMN IF NOT EXISTS entity_event_id BIGINT""")
    op.execute("""DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'fk_bw_market_events_entity') THEN
        ALTER TABLE bw_market_events
            ADD CONSTRAINT fk_bw_market_events_entity
            FOREIGN KEY (entity_event_id)
            REFERENCES bw_entity_events(id) ON DELETE SET NULL;
    END IF;
END $$""")
    # An entity event with no reliable occurrence date projects with a null
    # date rather than a fabricated one.
    op.execute("ALTER TABLE bw_market_events ALTER COLUMN event_date DROP NOT NULL")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_market_events_entity
        ON bw_market_events (entity_event_id)
        WHERE entity_event_id IS NOT NULL""")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_bw_market_events_entity")
    op.execute("""ALTER TABLE bw_market_events
        DROP CONSTRAINT IF EXISTS fk_bw_market_events_entity""")
    op.execute("ALTER TABLE bw_market_events DROP COLUMN IF EXISTS entity_event_id")

    op.execute("DROP TABLE IF EXISTS bw_narrative_evidence")
    op.execute("""ALTER TABLE bw_tracker_narratives
        DROP CONSTRAINT IF EXISTS fk_bw_narratives_supersedes,
        DROP CONSTRAINT IF EXISTS ck_bw_narratives_type,
        DROP CONSTRAINT IF EXISTS ck_bw_narratives_status""")
    op.execute("""ALTER TABLE bw_tracker_narratives
        DROP COLUMN IF EXISTS narrative_type,
        DROP COLUMN IF EXISTS status,
        DROP COLUMN IF EXISTS facts,
        DROP COLUMN IF EXISTS model_used,
        DROP COLUMN IF EXISTS prompt_version,
        DROP COLUMN IF EXISTS generator_version,
        DROP COLUMN IF EXISTS source_cutoff_at,
        DROP COLUMN IF EXISTS supersedes_id,
        DROP COLUMN IF EXISTS lint""")

    op.execute("DROP TABLE IF EXISTS bw_entity_event_evidence")
    op.execute("DROP TABLE IF EXISTS bw_entity_event_entities")
    op.execute("DROP TABLE IF EXISTS bw_entity_events")
