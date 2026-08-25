"""Entity intelligence — observations, canonical fields, and collection policy

Revision ID: ei_001
Revises: mm_007
Create Date: 2026-08-24

The registry currently keeps one value per field and forgets where it came
from. The workbook wrote ``bw_market_brands.baseline`` in April, everything
reads that JSON, and a LinkedIn reading collected in August cannot displace it
no matter how much better it is. Worse, ``market_collect`` writes
``funding_crunchbase`` back into the same JSON, so an immutable import and a
mutable current value now share one column.

This migration separates the three things that column was doing.

**Observations** are append-only: one field assertion from one source at one
time. The workbook's 180 and LinkedIn's 296 are both true statements about
different moments, and neither erases the other.

**Canonical fields** point at whichever observation currently wins, and record
which policy chose it. Changing the answer means moving a pointer and writing a
log row, not overwriting a value.

**Profiles** denormalize the winners so vendor lists and filters stay fast.
That table is a cache; the canonical rows are the truth.

Two changes to existing tables need explaining.

``bw_review_tasks.market_id`` becomes nullable, because an identity dispute or
a canonical field conflict belongs to the entity and not to one market
membership. Its dedup index has to be split in two to survive that. PostgreSQL
treats null indexed values as distinct, so a single index containing a nullable
``market_id`` would let every entity-global task re-insert on each resolver
pass — verified on 16.15, where two rows with a null ``market_id`` and
otherwise identical values both insert.

``bw_vendor_snapshots.market_id`` and ``bw_collection_runs.market_id`` become
nullable because a company fact collected once is not owned by whichever market
happened to trigger the collection.

Nothing is dropped, and ``baseline`` keeps every key it has today.
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'ei_001'
down_revision = 'mm_007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Observations: one normalized field assertion from one source.
    # ------------------------------------------------------------------
    # value_json is authoritative; the typed columns exist so a filter or an
    # ORDER BY does not have to cast JSON. The field registry decides which
    # typed column a given field populates, and composite values (investors,
    # funding rounds) legitimately use none of them.
    op.execute("""CREATE TABLE IF NOT EXISTS bw_entity_observations (
        id                 BIGSERIAL PRIMARY KEY,
        brand_id           INTEGER NOT NULL REFERENCES bw_brands(id) ON DELETE CASCADE,
        market_id          INTEGER REFERENCES bw_markets(id) ON DELETE CASCADE,
        field_key          VARCHAR(64) NOT NULL,
        value_json         JSONB NOT NULL,
        value_text         TEXT,
        value_number       NUMERIC,
        value_date         DATE,
        unit               VARCHAR(32),
        source             VARCHAR(64) NOT NULL,
        source_record_id   TEXT NOT NULL,
        source_url         TEXT,
        snapshot_id        BIGINT REFERENCES bw_vendor_snapshots(id) ON DELETE SET NULL,
        article_uri        TEXT REFERENCES articles(uri) ON DELETE SET NULL,
        collection_run_id  BIGINT REFERENCES bw_collection_runs(id) ON DELETE SET NULL,
        observed_at        TIMESTAMPTZ NOT NULL,
        effective_at       TIMESTAMPTZ,
        expires_at         TIMESTAMPTZ,
        confidence         DOUBLE PRECISION,
        authority          SMALLINT NOT NULL DEFAULT 50,
        status             VARCHAR(16) NOT NULL DEFAULT 'active',
        normalizer_version VARCHAR(32) NOT NULL,
        content_hash       VARCHAR(64) NOT NULL,
        metadata           JSONB NOT NULL DEFAULT '{}'::jsonb,
        invalidated_at     TIMESTAMPTZ,
        invalidation_reason TEXT,
        created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT ck_bw_entity_obs_confidence
            CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
        CONSTRAINT ck_bw_entity_obs_authority
            CHECK (authority >= 0 AND authority <= 100),
        CONSTRAINT ck_bw_entity_obs_status
            CHECK (status IN ('active','retracted','rejected','superseded'))
    )""")

    # The same provider record arriving twice — a callback retry, a backfill
    # rerun, the same snapshot reached through two markets — must not become
    # two observations. Market-scoped fields keep the market inside
    # source_record_id (see entity_observations.mint_source_record_id) so two
    # markets asserting the same value from one source do not collide here.
    op.execute("""CREATE UNIQUE INDEX IF NOT EXISTS uq_bw_entity_obs
        ON bw_entity_observations
           (brand_id, field_key, source, source_record_id, content_hash)""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_entity_obs_field
        ON bw_entity_observations (brand_id, field_key, observed_at DESC)""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_entity_obs_market
        ON bw_entity_observations (market_id, brand_id, field_key)
        WHERE market_id IS NOT NULL""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_entity_obs_snapshot
        ON bw_entity_observations (snapshot_id) WHERE snapshot_id IS NOT NULL""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_entity_obs_article
        ON bw_entity_observations (article_uri) WHERE article_uri IS NOT NULL""")

    # ------------------------------------------------------------------
    # Canonical fields: which observation currently wins, and why.
    # ------------------------------------------------------------------
    # ON DELETE RESTRICT on observation_id is deliberate. A canonical row must
    # never be left pointing at nothing, and an observation that something
    # depends on should be retracted rather than deleted.
    op.execute("""CREATE TABLE IF NOT EXISTS bw_entity_canonical_fields (
        id                BIGSERIAL PRIMARY KEY,
        brand_id          INTEGER NOT NULL REFERENCES bw_brands(id) ON DELETE CASCADE,
        market_id         INTEGER REFERENCES bw_markets(id) ON DELETE CASCADE,
        field_key         VARCHAR(64) NOT NULL,
        observation_id    BIGINT NOT NULL
                          REFERENCES bw_entity_observations(id) ON DELETE RESTRICT,
        value_json        JSONB NOT NULL,
        value_text        TEXT,
        value_number      NUMERIC,
        value_date        DATE,
        unit              VARCHAR(32),
        status            VARCHAR(16) NOT NULL,
        confidence        DOUBLE PRECISION,
        policy_version    VARCHAR(32) NOT NULL,
        resolution_reason TEXT NOT NULL,
        resolved_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        stale_after       TIMESTAMPTZ,
        locked            BOOLEAN NOT NULL DEFAULT FALSE,
        locked_by         TEXT,
        lock_reason       TEXT,
        updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT ck_bw_entity_canon_status
            CHECK (status IN ('current','stale','conflict','manual_override'))
    )""")

    # Two partial uniques rather than one, for the same null-distinct reason
    # the review-task index is split below: a global field has no market.
    op.execute("""CREATE UNIQUE INDEX IF NOT EXISTS uq_bw_entity_canon_global
        ON bw_entity_canonical_fields (brand_id, field_key)
        WHERE market_id IS NULL""")
    op.execute("""CREATE UNIQUE INDEX IF NOT EXISTS uq_bw_entity_canon_market
        ON bw_entity_canonical_fields (market_id, brand_id, field_key)
        WHERE market_id IS NOT NULL""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_entity_canon_stale
        ON bw_entity_canonical_fields (status, stale_after)
        WHERE status IN ('stale','conflict')""")

    # ------------------------------------------------------------------
    # Resolution log: append-only. No update or delete path exists.
    # ------------------------------------------------------------------
    op.execute("""CREATE TABLE IF NOT EXISTS bw_entity_resolution_log (
        id                  BIGSERIAL PRIMARY KEY,
        brand_id            INTEGER NOT NULL REFERENCES bw_brands(id) ON DELETE CASCADE,
        market_id           INTEGER REFERENCES bw_markets(id) ON DELETE CASCADE,
        field_key           VARCHAR(64) NOT NULL,
        old_observation_id  BIGINT,
        new_observation_id  BIGINT,
        old_status          VARCHAR(16),
        new_status          VARCHAR(16),
        policy_version      VARCHAR(32) NOT NULL,
        reason              TEXT NOT NULL,
        trigger             VARCHAR(24) NOT NULL,
        actor               TEXT,
        created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT ck_bw_entity_reslog_trigger
            CHECK (trigger IN ('ingest','backfill','manual','policy_replay','retraction'))
    )""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_entity_reslog
        ON bw_entity_resolution_log (brand_id, field_key, created_at DESC)""")

    # ------------------------------------------------------------------
    # Profile projection: a cache of the winners, for lists and filters.
    # ------------------------------------------------------------------
    op.execute("""CREATE TABLE IF NOT EXISTS bw_entity_profiles (
        brand_id                   INTEGER PRIMARY KEY
                                   REFERENCES bw_brands(id) ON DELETE CASCADE,
        hq_country                 TEXT,
        founded_year               INTEGER,
        employee_count             INTEGER,
        employee_count_observed_at TIMESTAMPTZ,
        employee_count_source      VARCHAR(64),
        funding_total_musd         NUMERIC,
        funding_status             TEXT,
        last_funding_type          TEXT,
        operating_status           TEXT,
        industry                   TEXT,
        description                TEXT,
        followers_linkedin         INTEGER,
        canonical_updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_entity_prof_country
        ON bw_entity_profiles (hq_country)""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_entity_prof_founded
        ON bw_entity_profiles (founded_year)""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_entity_prof_employees
        ON bw_entity_profiles (employee_count)""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_entity_prof_funding
        ON bw_entity_profiles (funding_total_musd)""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_entity_prof_funding_status
        ON bw_entity_profiles (funding_status)""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_entity_prof_operating
        ON bw_entity_profiles (operating_status)""")

    # ------------------------------------------------------------------
    # Collection policy, per entity and source.
    # ------------------------------------------------------------------
    # derived_from records which memberships produced the effective policy, so
    # switching one market off cannot silently stop collection another market
    # still depends on.
    op.execute("""CREATE TABLE IF NOT EXISTS bw_entity_source_policies (
        id              BIGSERIAL PRIMARY KEY,
        brand_id        INTEGER NOT NULL REFERENCES bw_brands(id) ON DELETE CASCADE,
        source          VARCHAR(64) NOT NULL,
        enabled         BOOLEAN NOT NULL DEFAULT FALSE,
        cadence_seconds INTEGER,
        next_due_at     TIMESTAMPTZ,
        last_attempt_at TIMESTAMPTZ,
        last_success_at TIMESTAMPTZ,
        priority        SMALLINT NOT NULL DEFAULT 50,
        config          JSONB NOT NULL DEFAULT '{}'::jsonb,
        derived_from    JSONB NOT NULL DEFAULT '[]'::jsonb,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_bw_entity_source_policy UNIQUE (brand_id, source)
    )""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_entity_policy_due
        ON bw_entity_source_policies (source, next_due_at)
        WHERE enabled""")

    # ------------------------------------------------------------------
    # Query terms: entity-owned, separate from global bw_brands.brand_keywords.
    # ------------------------------------------------------------------
    # The importer currently rewrites brand_keywords, which is why a brand
    # already claimed by one market cannot join a second. Terms live here so a
    # market can add matching vocabulary without touching Brand Watcher's.
    op.execute("""CREATE TABLE IF NOT EXISTS bw_entity_query_terms (
        id                    BIGSERIAL PRIMARY KEY,
        brand_id              INTEGER NOT NULL REFERENCES bw_brands(id) ON DELETE CASCADE,
        term                  TEXT NOT NULL,
        normalized_term       TEXT NOT NULL,
        term_kind             VARCHAR(24) NOT NULL,
        qualification_required BOOLEAN NOT NULL DEFAULT FALSE,
        enabled               BOOLEAN NOT NULL DEFAULT TRUE,
        identifier_id         INTEGER REFERENCES bw_vendor_identifiers(id) ON DELETE SET NULL,
        social_account_id     INTEGER REFERENCES social_accounts(id) ON DELETE SET NULL,
        provenance            JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT ck_bw_entity_term_kind CHECK (term_kind IN
            ('name','alias','former_name','product','person','ticker',
             'handle','qualified_name'))
    )""")
    op.execute("""CREATE UNIQUE INDEX IF NOT EXISTS uq_bw_entity_term_active
        ON bw_entity_query_terms (brand_id, term_kind, normalized_term)
        WHERE enabled""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_entity_term_lookup
        ON bw_entity_query_terms (normalized_term) WHERE enabled""")

    # ------------------------------------------------------------------
    # Keyword monitor -> entity. Without this, the only way back to a company
    # from a matched post is the article's topic string, which is a label.
    # ------------------------------------------------------------------
    op.execute("""CREATE TABLE IF NOT EXISTS bw_keyword_entity_map (
        id                   BIGSERIAL PRIMARY KEY,
        monitored_keyword_id INTEGER NOT NULL
                             REFERENCES monitored_keywords(id) ON DELETE CASCADE,
        query_term_id        BIGINT NOT NULL
                             REFERENCES bw_entity_query_terms(id) ON DELETE CASCADE,
        brand_id             INTEGER NOT NULL REFERENCES bw_brands(id) ON DELETE CASCADE,
        created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_bw_keyword_entity UNIQUE (monitored_keyword_id, query_term_id)
    )""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_keyword_entity_kw
        ON bw_keyword_entity_map (monitored_keyword_id)""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_keyword_entity_brand
        ON bw_keyword_entity_map (brand_id)""")

    # ------------------------------------------------------------------
    # Backfill progress, in the database rather than a file beside the script.
    # ------------------------------------------------------------------
    op.execute("""CREATE TABLE IF NOT EXISTS bw_entity_backfill_state (
        subcommand   VARCHAR(32) PRIMARY KEY,
        cursor_value TEXT,
        rows_done    BIGINT NOT NULL DEFAULT 0,
        rows_skipped BIGINT NOT NULL DEFAULT 0,
        status       VARCHAR(16) NOT NULL DEFAULT 'pending',
        detail       JSONB NOT NULL DEFAULT '{}'::jsonb,
        started_at   TIMESTAMPTZ,
        updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT ck_bw_entity_backfill_status
            CHECK (status IN ('pending','running','done','failed'))
    )""")

    # ------------------------------------------------------------------
    # Existing tables.
    # ------------------------------------------------------------------
    # Typed taxonomy columns. The baseline keys stay exactly where they are —
    # these are populated from them, not moved out of them.
    op.execute("""ALTER TABLE bw_market_brands
        ADD COLUMN IF NOT EXISTS category TEXT,
        ADD COLUMN IF NOT EXISTS sub_category TEXT,
        ADD COLUMN IF NOT EXISTS category_observation_id BIGINT,
        ADD COLUMN IF NOT EXISTS sub_category_observation_id BIGINT,
        ADD COLUMN IF NOT EXISTS social_collection_enabled BOOLEAN NOT NULL DEFAULT FALSE,
        ADD COLUMN IF NOT EXISTS social_collection_config JSONB NOT NULL DEFAULT '{}'::jsonb""")

    op.execute("""DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'fk_bw_market_brands_cat_obs') THEN
        ALTER TABLE bw_market_brands
            ADD CONSTRAINT fk_bw_market_brands_cat_obs
            FOREIGN KEY (category_observation_id)
            REFERENCES bw_entity_observations(id) ON DELETE SET NULL;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'fk_bw_market_brands_subcat_obs') THEN
        ALTER TABLE bw_market_brands
            ADD CONSTRAINT fk_bw_market_brands_subcat_obs
            FOREIGN KEY (sub_category_observation_id)
            REFERENCES bw_entity_observations(id) ON DELETE SET NULL;
    END IF;
END $$""")

    # Taxonomy is {"category": ..., "sub_category": ...} on every membership
    # that has it. Rows without it stay null rather than being given a guess.
    op.execute("""UPDATE bw_market_brands
        SET category = NULLIF(baseline->'taxonomy'->>'category', ''),
            sub_category = NULLIF(baseline->'taxonomy'->>'sub_category', '')
        WHERE baseline ? 'taxonomy'
          AND category IS NULL AND sub_category IS NULL""")

    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_market_brands_category
        ON bw_market_brands (market_id, category, sub_category)""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_market_brands_social
        ON bw_market_brands (market_id) WHERE social_collection_enabled""")

    # A company fact is not owned by whichever market triggered its collection.
    op.execute("ALTER TABLE bw_vendor_snapshots ALTER COLUMN market_id DROP NOT NULL")
    op.execute("""ALTER TABLE bw_vendor_snapshots
        ADD COLUMN IF NOT EXISTS schema_version VARCHAR(32),
        ADD COLUMN IF NOT EXISTS normalization_status VARCHAR(16)
            NOT NULL DEFAULT 'pending',
        ADD COLUMN IF NOT EXISTS normalization_error TEXT""")
    op.execute("""DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'ck_bw_vendor_snapshots_norm') THEN
        ALTER TABLE bw_vendor_snapshots
            ADD CONSTRAINT ck_bw_vendor_snapshots_norm
            CHECK (normalization_status IN
                   ('pending','normalized','partial','failed','skipped'));
    END IF;
END $$""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_vendor_snapshots_norm
        ON bw_vendor_snapshots (normalization_status, id)""")

    op.execute("ALTER TABLE bw_collection_runs ALTER COLUMN market_id DROP NOT NULL")
    op.execute("""ALTER TABLE bw_collection_runs
        ADD COLUMN IF NOT EXISTS keyword_group_id INTEGER,
        ADD COLUMN IF NOT EXISTS trigger VARCHAR(16) NOT NULL DEFAULT 'schedule',
        ADD COLUMN IF NOT EXISTS window_start TIMESTAMPTZ,
        ADD COLUMN IF NOT EXISTS window_end TIMESTAMPTZ,
        ADD COLUMN IF NOT EXISTS records_evaluated INTEGER NOT NULL DEFAULT 0,
        ADD COLUMN IF NOT EXISTS records_unmatched INTEGER NOT NULL DEFAULT 0,
        ADD COLUMN IF NOT EXISTS error_code VARCHAR(64),
        ADD COLUMN IF NOT EXISTS metrics JSONB NOT NULL DEFAULT '{}'::jsonb""")
    op.execute("""DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'fk_bw_collection_runs_group') THEN
        ALTER TABLE bw_collection_runs
            ADD CONSTRAINT fk_bw_collection_runs_group
            FOREIGN KEY (keyword_group_id)
            REFERENCES keyword_groups(id) ON DELETE SET NULL;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'ck_bw_collection_runs_trigger') THEN
        ALTER TABLE bw_collection_runs
            ADD CONSTRAINT ck_bw_collection_runs_trigger
            CHECK (trigger IN ('schedule','manual','backfill','retry','webhook_reconcile'));
    END IF;
END $$""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_collection_runs_brand
        ON bw_collection_runs (brand_id, source, started_at DESC)""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_collection_runs_group
        ON bw_collection_runs (keyword_group_id, started_at DESC)""")

    # Review tasks. An identity dispute or a field conflict belongs to the
    # entity; only membership problems belong to a market. Splitting the dedup
    # index is not tidiness: with a nullable market_id inside one index,
    # PostgreSQL treats the nulls as distinct and every entity-global task
    # re-inserts on each resolver pass.
    op.execute("ALTER TABLE bw_review_tasks ALTER COLUMN market_id DROP NOT NULL")
    op.execute("DROP INDEX IF EXISTS uq_bw_review_tasks_dedup")
    op.execute("""CREATE UNIQUE INDEX IF NOT EXISTS uq_bw_review_tasks_market_dedup
        ON bw_review_tasks
           (market_id, kind, COALESCE(brand_id, 0), COALESCE(field, ''), md5(message))
        WHERE market_id IS NOT NULL""")
    op.execute("""CREATE UNIQUE INDEX IF NOT EXISTS uq_bw_review_tasks_global_dedup
        ON bw_review_tasks
           (kind, COALESCE(brand_id, 0), COALESCE(field, ''), md5(message))
        WHERE market_id IS NULL""")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_bw_review_tasks_global_dedup")
    op.execute("DROP INDEX IF EXISTS uq_bw_review_tasks_market_dedup")
    op.execute("""CREATE UNIQUE INDEX IF NOT EXISTS uq_bw_review_tasks_dedup
        ON bw_review_tasks
           (market_id, kind, COALESCE(brand_id, 0), COALESCE(field, ''), md5(message))""")

    op.execute("DROP TABLE IF EXISTS bw_entity_backfill_state")
    op.execute("DROP TABLE IF EXISTS bw_keyword_entity_map")
    op.execute("DROP TABLE IF EXISTS bw_entity_query_terms")
    op.execute("DROP TABLE IF EXISTS bw_entity_source_policies")
    op.execute("DROP TABLE IF EXISTS bw_entity_profiles")
    op.execute("DROP TABLE IF EXISTS bw_entity_resolution_log")
    op.execute("DROP TABLE IF EXISTS bw_entity_canonical_fields")

    op.execute("""ALTER TABLE bw_market_brands
        DROP CONSTRAINT IF EXISTS fk_bw_market_brands_cat_obs,
        DROP CONSTRAINT IF EXISTS fk_bw_market_brands_subcat_obs""")
    op.execute("DROP TABLE IF EXISTS bw_entity_observations")

    op.execute("""ALTER TABLE bw_market_brands
        DROP COLUMN IF EXISTS category,
        DROP COLUMN IF EXISTS sub_category,
        DROP COLUMN IF EXISTS category_observation_id,
        DROP COLUMN IF EXISTS sub_category_observation_id,
        DROP COLUMN IF EXISTS social_collection_enabled,
        DROP COLUMN IF EXISTS social_collection_config""")
    op.execute("""ALTER TABLE bw_vendor_snapshots
        DROP COLUMN IF EXISTS schema_version,
        DROP COLUMN IF EXISTS normalization_status,
        DROP COLUMN IF EXISTS normalization_error""")
    op.execute("""ALTER TABLE bw_collection_runs
        DROP COLUMN IF EXISTS keyword_group_id,
        DROP COLUMN IF EXISTS trigger,
        DROP COLUMN IF EXISTS window_start,
        DROP COLUMN IF EXISTS window_end,
        DROP COLUMN IF EXISTS records_evaluated,
        DROP COLUMN IF EXISTS records_unmatched,
        DROP COLUMN IF EXISTS error_code,
        DROP COLUMN IF EXISTS metrics""")
