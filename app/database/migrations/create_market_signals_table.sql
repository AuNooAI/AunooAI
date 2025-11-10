-- Create market_signals_runs table for storing Market Signals analyses
-- Migration: create_market_signals_table.sql
-- Date: 2025-01-10

-- Create market_signals_runs table
CREATE TABLE IF NOT EXISTS market_signals_runs (
    id VARCHAR(36) PRIMARY KEY,
    user_id INTEGER,
    topic TEXT NOT NULL,
    model_used VARCHAR(100),
    raw_output JSON NOT NULL,
    total_articles_analyzed INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    analysis_duration_seconds FLOAT
);

-- Create index for efficient queries by user and creation time
CREATE INDEX IF NOT EXISTS idx_market_signals_user_created
ON market_signals_runs(user_id, created_at);

-- Create analysis_run_article_log table if it doesn't exist (for tracking articles used in analyses)
CREATE TABLE IF NOT EXISTS analysis_run_article_log (
    id SERIAL PRIMARY KEY,
    analysis_run_id VARCHAR(36) NOT NULL,
    article_id INTEGER NOT NULL,
    article_uri TEXT,
    logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT fk_analysis_run FOREIGN KEY (analysis_run_id)
        REFERENCES market_signals_runs(id) ON DELETE CASCADE
);

-- Create index for efficient article log queries
CREATE INDEX IF NOT EXISTS idx_analysis_run_article_log_run_id
ON analysis_run_article_log(analysis_run_id);

CREATE INDEX IF NOT EXISTS idx_analysis_run_article_log_article_id
ON analysis_run_article_log(article_id);
