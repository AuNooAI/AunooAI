"""Market Monitor — a tracked vendor portfolio on top of Brand Watcher

Revision ID: mm_001
Revises: et_008
Create Date: 2026-08-19

A market is a set of ``bw_brands`` plus the question and ontology that make
them comparable. The first is SOC Automation: 83 vendors from an IT-Harvest
registry, 82 of them in scope.

What is deliberately different from the SaaS build of the same feature:

- **No tenant_id and no RLS.** A monolith deployment is one customer. Adding a
  tenant column here would be a column that is always the same value and a
  policy that never excludes anything.
- **No entitlement column.** ``max_market_entities`` exists in the SaaS build
  because an 82-vendor market would blow past a plan's brand cap. There are no
  plans here.
- **``article_uris TEXT[]``, not integer ids.** ``articles`` is keyed on ``uri``
  in this codebase, which is also why ``bw_article_categories`` carries
  ``article_uri``.
- **Vendors get no monitoring topic.** Brand Watcher classifies the shared
  article corpus by brand keywords, and collection is driven by
  ``keyword_groups``. So unlike the SaaS build, 82 vendors add no collection
  cost to the shared cycle — nothing needed excluding from it.

Market events get their own table rather than reusing ``topic_events``: they
carry a score, an analyst review state, and evidence pointers into vendor
snapshots, none of which a topic timeline models.

Raw provider payloads are not stored. There is no object store here either, so
``bm_vendor_snapshots.data`` keeps a bounded sanitized payload and ``raw_ref``
stays nullable against the day one exists.
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'mm_001'
down_revision = 'et_008'
branch_labels = None
depends_on = None

TABLES = (
    "bw_markets",
    "bw_market_brands",
    "bw_vendor_identifiers",
    "bw_collection_runs",
    "bw_vendor_snapshots",
    "bw_review_tasks",
    "bw_market_events",
    "bw_event_vendors",
)


def upgrade() -> None:
    op.execute("""CREATE TABLE IF NOT EXISTS bw_markets (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) NOT NULL UNIQUE,
    question TEXT,
    description TEXT,
    ontology JSONB NOT NULL DEFAULT '{}'::jsonb,
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    is_public BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)""")
    op.execute("""CREATE UNIQUE INDEX IF NOT EXISTS uq_bw_markets_public_slug
    ON bw_markets (slug) WHERE is_public""")

    op.execute("""CREATE TABLE IF NOT EXISTS bw_market_brands (
    id SERIAL PRIMARY KEY,
    market_id INTEGER NOT NULL REFERENCES bw_markets(id) ON DELETE CASCADE,
    brand_id INTEGER NOT NULL REFERENCES bw_brands(id) ON DELETE CASCADE,
    role VARCHAR(16) NOT NULL DEFAULT 'vendor',
    sort_order INTEGER NOT NULL DEFAULT 0,
    -- Three independent decisions, three flags. ``role`` is what the row is,
    -- ``collection_enabled`` is whether we spend anything watching it, and
    -- ``is_public`` is whether it reaches a public page. "Only collect for
    -- funded vendors" is the middle one.
    collection_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    is_public BOOLEAN NOT NULL DEFAULT FALSE,
    baseline JSONB NOT NULL DEFAULT '{}'::jsonb,
    review_status VARCHAR(16) NOT NULL DEFAULT 'unreviewed',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_bw_market_brands UNIQUE (market_id, brand_id),
    CONSTRAINT ck_bw_market_brands_role CHECK (role IN ('vendor','watch','excluded')),
    CONSTRAINT ck_bw_market_brands_review CHECK (
        review_status IN ('unreviewed','verified','disputed'))
)""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_market_brands_market
    ON bw_market_brands (market_id, sort_order)""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_market_brands_collect
    ON bw_market_brands (market_id, collection_enabled) WHERE collection_enabled""")

    op.execute("""CREATE TABLE IF NOT EXISTS bw_vendor_identifiers (
    id SERIAL PRIMARY KEY,
    brand_id INTEGER NOT NULL REFERENCES bw_brands(id) ON DELETE CASCADE,
    -- domain | website_url | linkedin_company_url | alias | former_name | rss_feed
    kind VARCHAR(32) NOT NULL,
    -- Comparison key: lowercased, tracking params stripped, locale hosts
    -- normalised. ``display_value`` keeps whatever the source supplied.
    normalized_value TEXT NOT NULL,
    display_value TEXT,
    external_id TEXT,
    valid_from TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_to TIMESTAMPTZ,
    provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
    verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_vendor_ident_brand
    ON bw_vendor_identifiers (brand_id, kind)""")
    op.execute("""CREATE UNIQUE INDEX IF NOT EXISTS uq_bw_vendor_ident_active
    ON bw_vendor_identifiers (kind, normalized_value) WHERE valid_to IS NULL""")

    op.execute("""CREATE TABLE IF NOT EXISTS bw_collection_runs (
    id BIGSERIAL PRIMARY KEY,
    market_id INTEGER NOT NULL REFERENCES bw_markets(id) ON DELETE CASCADE,
    brand_id INTEGER REFERENCES bw_brands(id) ON DELETE SET NULL,
    source VARCHAR(64) NOT NULL,
    provider VARCHAR(64) NOT NULL,
    -- Provider-side job handle (a Bright Data snapshot_id). The async callback
    -- carries no session, so this row is how it finds its market.
    job_id TEXT,
    status VARCHAR(16) NOT NULL DEFAULT 'queued',
    request_hash VARCHAR(64),
    records_received INTEGER NOT NULL DEFAULT 0,
    records_new INTEGER NOT NULL DEFAULT 0,
    records_skipped INTEGER NOT NULL DEFAULT 0,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    latency_ms INTEGER,
    cost_amount NUMERIC(12,4),
    cost_currency VARCHAR(3),
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_bw_collection_runs_status CHECK (
        status IN ('queued','running','succeeded','failed','cancelled','partial'))
)""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_collection_runs_market
    ON bw_collection_runs (market_id, source, started_at DESC)""")
    op.execute("""CREATE UNIQUE INDEX IF NOT EXISTS uq_bw_collection_runs_job
    ON bw_collection_runs (provider, job_id) WHERE job_id IS NOT NULL""")

    op.execute("""CREATE TABLE IF NOT EXISTS bw_vendor_snapshots (
    id BIGSERIAL PRIMARY KEY,
    market_id INTEGER NOT NULL REFERENCES bw_markets(id) ON DELETE CASCADE,
    brand_id INTEGER NOT NULL REFERENCES bw_brands(id) ON DELETE CASCADE,
    source VARCHAR(64) NOT NULL,
    -- profile | page_state | metric | job_posting
    snapshot_type VARCHAR(48) NOT NULL,
    -- Stable per-source key. For a page state with no provider id this is the
    -- canonical URL; NULL would defeat the dedup constraint below.
    provider_item_id TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at TIMESTAMPTZ,
    data JSONB NOT NULL DEFAULT '{}'::jsonb,
    content_hash VARCHAR(64) NOT NULL,
    raw_ref TEXT,
    collection_run_id BIGINT REFERENCES bw_collection_runs(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_bw_vendor_snapshots UNIQUE (source, provider_item_id, content_hash)
)""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_vendor_snapshots_brand
    ON bw_vendor_snapshots (brand_id, snapshot_type, observed_at DESC)""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_vendor_snapshots_market
    ON bw_vendor_snapshots (market_id, observed_at DESC)""")

    op.execute("""CREATE TABLE IF NOT EXISTS bw_review_tasks (
    id SERIAL PRIMARY KEY,
    market_id INTEGER NOT NULL REFERENCES bw_markets(id) ON DELETE CASCADE,
    brand_id INTEGER REFERENCES bw_brands(id) ON DELETE SET NULL,
    kind VARCHAR(32) NOT NULL,
    severity VARCHAR(8) NOT NULL DEFAULT 'low',
    status VARCHAR(12) NOT NULL DEFAULT 'open',
    field VARCHAR(64),
    message TEXT NOT NULL,
    source_ref JSONB NOT NULL DEFAULT '{}'::jsonb,
    resolution JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    CONSTRAINT ck_bw_review_tasks_severity CHECK (severity IN ('low','medium','high')),
    CONSTRAINT ck_bw_review_tasks_status CHECK (
        status IN ('open','in_progress','resolved','dismissed'))
)""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_review_tasks_market
    ON bw_review_tasks (market_id, status, severity)""")
    op.execute("""CREATE UNIQUE INDEX IF NOT EXISTS uq_bw_review_tasks_dedup
    ON bw_review_tasks (market_id, kind, COALESCE(brand_id, 0),
                        COALESCE(field, ''), md5(message))""")

    op.execute("""CREATE TABLE IF NOT EXISTS bw_market_events (
    id BIGSERIAL PRIMARY KEY,
    market_id INTEGER NOT NULL REFERENCES bw_markets(id) ON DELETE CASCADE,
    event_type VARCHAR(48) NOT NULL,
    event_subtype VARCHAR(64),
    title VARCHAR(500) NOT NULL,
    description TEXT NOT NULL,
    -- When it happened, when a source said so, and when we saw it. Keeping the
    -- three apart is what makes this a timeline rather than a publication log.
    event_date DATE NOT NULL,
    published_at TIMESTAMPTZ,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    score INTEGER NOT NULL DEFAULT 0,
    score_components JSONB NOT NULL DEFAULT '{}'::jsonb,
    confidence DOUBLE PRECISION,
    -- A vendor's own post proves the vendor said it, not that it is true.
    corroboration VARCHAR(24) NOT NULL DEFAULT 'uncorroborated',
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
    article_uris TEXT[] NOT NULL DEFAULT '{}',
    snapshot_ids BIGINT[] NOT NULL DEFAULT '{}',
    extraction_version VARCHAR(32),
    content_hash VARCHAR(64) NOT NULL,
    is_public BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_bw_market_events UNIQUE (market_id, content_hash),
    CONSTRAINT ck_bw_market_events_score CHECK (score BETWEEN 0 AND 100),
    CONSTRAINT ck_bw_market_events_corroboration CHECK (
        corroboration IN ('uncorroborated','vendor_claim','single_source',
                          'corroborated','primary_document')),
    CONSTRAINT ck_bw_market_events_status CHECK (
        status IN ('active','superseded','rejected','pending_review'))
)""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_market_events_wire
    ON bw_market_events (market_id, event_date DESC, score DESC)""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_market_events_type
    ON bw_market_events (event_type)""")

    op.execute("""CREATE TABLE IF NOT EXISTS bw_event_vendors (
    id BIGSERIAL PRIMARY KEY,
    event_id BIGINT NOT NULL REFERENCES bw_market_events(id) ON DELETE CASCADE,
    market_id INTEGER NOT NULL REFERENCES bw_markets(id) ON DELETE CASCADE,
    brand_id INTEGER NOT NULL REFERENCES bw_brands(id) ON DELETE CASCADE,
    -- subject | acquirer | target | partner | customer | investor | competitor
    relation VARCHAR(24) NOT NULL DEFAULT 'subject',
    confidence DOUBLE PRECISION,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_bw_event_vendors UNIQUE (event_id, brand_id, relation)
)""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_event_vendors_brand
    ON bw_event_vendors (brand_id, market_id)""")


def downgrade() -> None:
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
