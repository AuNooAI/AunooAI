-- Dashboard Cache Table Migration
-- Stores last generated dashboard for each configuration
-- Version: 1.0
-- Date: 2025-01-26

-- =============================================================================
-- TABLE: dashboard_cache
-- =============================================================================

CREATE TABLE IF NOT EXISTS dashboard_cache (
    id SERIAL PRIMARY KEY,

    -- Unique cache key for this dashboard configuration
    cache_key TEXT NOT NULL UNIQUE,

    -- Dashboard configuration
    dashboard_type TEXT NOT NULL,
    date_range TEXT NOT NULL,
    topic TEXT,
    profile_id INTEGER,
    persona TEXT,

    -- Content storage
    content_json TEXT NOT NULL,
    summary_text TEXT,

    -- Metadata
    article_count INTEGER DEFAULT 0,
    model_used TEXT,
    generation_time_seconds REAL,

    -- Timestamps
    generated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Foreign keys
    FOREIGN KEY (profile_id) REFERENCES organizational_profiles(id) ON DELETE SET NULL
);

-- =============================================================================
-- INDEXES
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_dashboard_cache_type
    ON dashboard_cache(dashboard_type, generated_at DESC);

CREATE INDEX IF NOT EXISTS idx_dashboard_cache_accessed
    ON dashboard_cache(accessed_at DESC);

CREATE INDEX IF NOT EXISTS idx_dashboard_cache_key
    ON dashboard_cache(cache_key);

CREATE INDEX IF NOT EXISTS idx_dashboard_cache_topic
    ON dashboard_cache(topic) WHERE topic IS NOT NULL;
