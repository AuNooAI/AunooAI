"""Reconcile missing tables from gh_002 through act_003 branch

Revision ID: pt_005
Revises: pt_004
Create Date: 2026-02-05

Some tenants advanced their alembic_version stamp to pt_004 without
actually running the intermediate migrations (gh_002 through act_003).
This migration uses CREATE TABLE IF NOT EXISTS / ALTER TABLE ... ADD COLUMN
IF NOT EXISTS so it is fully idempotent:
  - Tenants that already have the tables/columns: no-op
  - Tenants missing them: creates everything

Tables reconciled:
  - geopolitical_narratives        (gh_002)
  - geopolitical_schedules         (gh_003)
  - desk_briefings                 (dr_001 + dr_002 columns)
  - enrichment_training_samples    (act_001)
  - training_sample_counts         (act_001)
  - training_runs                  (act_001)
  - user_relevance_feedback        (act_002)
  - enrichment_confidence_readings (act_003)
  - relevance_confidence_readings  (act_003)
  - policy_tracker_schedules       (pt_004)

Columns reconciled:
  - keyword_groups: kwg_001 columns
  - articles: enrichment_sources   (act_001)
  - keyword_monitor_settings: inference_mode (add_inference_mode)
  - desk_briefings: emerging_topics, emerging_topics_count (dr_002)
"""
from alembic import op


revision = 'pt_005'
down_revision = 'pt_004'
branch_labels = None
depends_on = None


def upgrade():
    # ── gh_002: geopolitical_narratives ──────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS geopolitical_narratives (
            id              SERIAL PRIMARY KEY,
            narrative_text  TEXT NOT NULL,
            executive_summary TEXT,
            regional_analysis TEXT,
            emerging_threats TEXT,
            outlook         TEXT,
            hotspot_count   INTEGER NOT NULL DEFAULT 0,
            article_count   INTEGER NOT NULL DEFAULT 0,
            top_regions     JSONB,
            top_categories  JSONB,
            risk_breakdown  JSONB,
            model_used      VARCHAR(100),
            topic           TEXT,
            generated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_geopolitical_narratives_generated ON geopolitical_narratives (generated_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_geopolitical_narratives_topic ON geopolitical_narratives (topic)")

    # ── gh_003: geopolitical_schedules ───────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS geopolitical_schedules (
            id                          SERIAL PRIMARY KEY,
            name                        VARCHAR(255) NOT NULL,
            topic                       VARCHAR(255),
            batch_size                  INTEGER NOT NULL DEFAULT 50,
            model                       VARCHAR(100) NOT NULL DEFAULT 'gpt-4o-mini',
            process_all                 BOOLEAN NOT NULL DEFAULT FALSE,
            schedule_enabled            BOOLEAN NOT NULL DEFAULT FALSE,
            schedule_type               VARCHAR(20) DEFAULT 'interval',
            schedule_interval           INTEGER,
            schedule_unit               VARCHAR(20) DEFAULT 'hours',
            schedule_time               TIME,
            notify_on_complete          BOOLEAN NOT NULL DEFAULT TRUE,
            notify_threshold            INTEGER NOT NULL DEFAULT 1,
            last_run_at                 TIMESTAMPTZ,
            next_run_at                 TIMESTAMPTZ,
            last_run_status             VARCHAR(20),
            last_run_error              TEXT,
            last_run_articles_processed INTEGER NOT NULL DEFAULT 0,
            last_run_hotspots_created   INTEGER NOT NULL DEFAULT 0,
            last_run_hotspots_updated   INTEGER NOT NULL DEFAULT 0,
            run_count                   INTEGER NOT NULL DEFAULT 0,
            created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_geopolitical_schedules_next_run ON geopolitical_schedules (next_run_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_geopolitical_schedules_schedule_enabled ON geopolitical_schedules (schedule_enabled)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_geopolitical_schedules_topic ON geopolitical_schedules (topic)")

    # ── kwg_001: columns on keyword_groups ───────────────────────────
    op.execute("ALTER TABLE keyword_groups ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE")
    op.execute("ALTER TABLE keyword_groups ADD COLUMN IF NOT EXISTS check_interval INTEGER")
    op.execute("ALTER TABLE keyword_groups ADD COLUMN IF NOT EXISTS interval_unit INTEGER")
    op.execute("ALTER TABLE keyword_groups ADD COLUMN IF NOT EXISTS search_date_range INTEGER")
    op.execute("ALTER TABLE keyword_groups ADD COLUMN IF NOT EXISTS providers TEXT")
    op.execute("ALTER TABLE keyword_groups ADD COLUMN IF NOT EXISTS auto_ingest_enabled BOOLEAN")
    op.execute("ALTER TABLE keyword_groups ADD COLUMN IF NOT EXISTS min_relevance_threshold FLOAT")
    op.execute("ALTER TABLE keyword_groups ADD COLUMN IF NOT EXISTS quality_control_enabled BOOLEAN")
    op.execute("ALTER TABLE keyword_groups ADD COLUMN IF NOT EXISTS auto_save_approved_only BOOLEAN")
    op.execute("ALTER TABLE keyword_groups ADD COLUMN IF NOT EXISTS default_llm_model TEXT")
    op.execute("ALTER TABLE keyword_groups ADD COLUMN IF NOT EXISTS llm_temperature FLOAT")
    op.execute("ALTER TABLE keyword_groups ADD COLUMN IF NOT EXISTS llm_max_tokens INTEGER")
    op.execute("ALTER TABLE keyword_groups ADD COLUMN IF NOT EXISTS last_checked_at TIMESTAMPTZ")
    op.execute("ALTER TABLE keyword_groups ADD COLUMN IF NOT EXISTS next_check_at TIMESTAMPTZ")
    op.execute("ALTER TABLE keyword_groups ADD COLUMN IF NOT EXISTS last_error TEXT")
    op.execute("ALTER TABLE keyword_groups ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()")
    op.execute("CREATE INDEX IF NOT EXISTS idx_keyword_groups_next_check ON keyword_groups (is_active, next_check_at)")

    # ── dr_001: desk_briefings ───────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS desk_briefings (
            id                  SERIAL PRIMARY KEY,
            name                VARCHAR(255) NOT NULL,
            description         TEXT,
            topic               VARCHAR(255),
            username            TEXT REFERENCES users(username) ON DELETE SET NULL,
            articles            JSONB NOT NULL DEFAULT '[]',
            incidents           JSONB NOT NULL DEFAULT '[]',
            synthesis           TEXT,
            themes              JSONB,
            priority_actions    JSONB,
            metadata            JSONB,
            status              VARCHAR(50) NOT NULL DEFAULT 'draft',
            model_used          VARCHAR(100),
            articles_count      INTEGER NOT NULL DEFAULT 0,
            incidents_count     INTEGER NOT NULL DEFAULT 0,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            finalized_at        TIMESTAMPTZ,
            UNIQUE (name, username)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_desk_briefings_username ON desk_briefings (username)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_desk_briefings_status ON desk_briefings (status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_desk_briefings_created_at ON desk_briefings (created_at)")

    # ── dr_002: columns on desk_briefings ────────────────────────────
    op.execute("ALTER TABLE desk_briefings ADD COLUMN IF NOT EXISTS emerging_topics JSONB NOT NULL DEFAULT '[]'")
    op.execute("ALTER TABLE desk_briefings ADD COLUMN IF NOT EXISTS emerging_topics_count INTEGER NOT NULL DEFAULT 0")

    # ── act_001: enrichment_training_samples ─────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS enrichment_training_samples (
            id           SERIAL PRIMARY KEY,
            article_uri  TEXT NOT NULL REFERENCES articles(uri) ON DELETE CASCADE,
            topic        TEXT NOT NULL,
            field_name   TEXT NOT NULL,
            field_value  TEXT NOT NULL,
            source       TEXT NOT NULL,
            model_used   TEXT,
            confidence   FLOAT,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (article_uri, field_name)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_training_samples_topic ON enrichment_training_samples (topic)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_training_samples_field ON enrichment_training_samples (field_name)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_training_samples_source ON enrichment_training_samples (source)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_training_samples_topic_field ON enrichment_training_samples (topic, field_name)")

    # ── act_001: training_sample_counts ──────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS training_sample_counts (
            id           SERIAL PRIMARY KEY,
            topic        TEXT NOT NULL,
            field_name   TEXT NOT NULL,
            field_value  TEXT NOT NULL,
            sample_count INTEGER NOT NULL DEFAULT 0,
            last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (topic, field_name, field_value)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_sample_counts_topic ON training_sample_counts (topic)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_sample_counts_field ON training_sample_counts (field_name)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_sample_counts_topic_field ON training_sample_counts (topic, field_name)")

    # ── act_001: training_runs ───────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS training_runs (
            id            SERIAL PRIMARY KEY,
            run_id        TEXT NOT NULL UNIQUE,
            status        TEXT NOT NULL DEFAULT 'pending',
            topics_included JSONB,
            fields_included JSONB,
            sample_count  INTEGER,
            metrics       JSONB,
            started_at    TIMESTAMPTZ,
            completed_at  TIMESTAMPTZ,
            model_path    TEXT,
            error_message TEXT,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_training_runs_status ON training_runs (status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_training_runs_created ON training_runs (created_at)")

    # ── act_001: enrichment_sources column on articles ───────────────
    op.execute("ALTER TABLE articles ADD COLUMN IF NOT EXISTS enrichment_sources JSONB DEFAULT '{}'")

    # ── act_002: user_relevance_feedback ─────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_relevance_feedback (
            id               SERIAL PRIMARY KEY,
            article_uri      TEXT NOT NULL REFERENCES articles(uri) ON DELETE CASCADE,
            topic            TEXT NOT NULL,
            user_id          TEXT,
            feedback_type    TEXT NOT NULL,
            relevance_score  FLOAT,
            classifier_score FLOAT,
            embedding_score  FLOAT,
            article_metadata JSONB,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (article_uri, user_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_relevance_feedback_topic ON user_relevance_feedback (topic)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_relevance_feedback_type ON user_relevance_feedback (feedback_type)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_relevance_feedback_created ON user_relevance_feedback (created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_relevance_feedback_topic_type ON user_relevance_feedback (topic, feedback_type)")

    # ── act_003: enrichment_confidence_readings ──────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS enrichment_confidence_readings (
            id          SERIAL PRIMARY KEY,
            topic       TEXT NOT NULL,
            field_name  TEXT NOT NULL,
            confidence  FLOAT NOT NULL,
            recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_enrichment_confidence_topic_time ON enrichment_confidence_readings (topic, recorded_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_enrichment_confidence_time ON enrichment_confidence_readings (recorded_at)")

    # ── act_003: relevance_confidence_readings ───────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS relevance_confidence_readings (
            id               SERIAL PRIMARY KEY,
            topic            TEXT NOT NULL,
            score            FLOAT NOT NULL,
            classifier_score FLOAT,
            embedding_score  FLOAT,
            method           TEXT NOT NULL DEFAULT 'hybrid',
            relevant         BOOLEAN,
            recorded_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_relevance_confidence_topic_time ON relevance_confidence_readings (topic, recorded_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_relevance_confidence_time ON relevance_confidence_readings (recorded_at)")

    # ── add_inference_mode: column on keyword_monitor_settings ───────
    op.execute("ALTER TABLE keyword_monitor_settings ADD COLUMN IF NOT EXISTS inference_mode TEXT NOT NULL DEFAULT 'hybrid'")

    # ── pt_004: policy_tracker_schedules ─────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS policy_tracker_schedules (
            id                             SERIAL PRIMARY KEY,
            name                           VARCHAR(255) NOT NULL,
            topic                          VARCHAR(255),
            run_type                       VARCHAR(20) NOT NULL DEFAULT 'incremental',
            days_back                      INTEGER NOT NULL DEFAULT 30,
            schedule_enabled               BOOLEAN NOT NULL DEFAULT FALSE,
            schedule_type                  VARCHAR(20) DEFAULT 'interval',
            schedule_interval              INTEGER,
            schedule_unit                  VARCHAR(20) DEFAULT 'hours',
            schedule_time                  TIME,
            notify_on_complete             BOOLEAN NOT NULL DEFAULT TRUE,
            notify_threshold               INTEGER NOT NULL DEFAULT 10,
            last_run_at                    TIMESTAMPTZ,
            next_run_at                    TIMESTAMPTZ,
            last_run_status                VARCHAR(20),
            last_run_error                 TEXT,
            last_run_articles_processed    INTEGER NOT NULL DEFAULT 0,
            last_run_articles_categorized  INTEGER NOT NULL DEFAULT 0,
            run_count                      INTEGER NOT NULL DEFAULT 0,
            created_at                     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at                     TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_policy_tracker_schedules_next_run ON policy_tracker_schedules (next_run_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_policy_tracker_schedules_schedule_enabled ON policy_tracker_schedules (schedule_enabled)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_policy_tracker_schedules_topic ON policy_tracker_schedules (topic)")


def downgrade():
    # This is a reconciliation migration - downgrade only drops what it created.
    # Tables/columns that already existed before this migration are left alone.
    # In practice this migration should never be downgraded.
    pass
