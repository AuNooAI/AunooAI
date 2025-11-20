-- Migration: Create LLM Retry State and Error Tracking Tables
-- Purpose: Enable circuit breaker pattern and comprehensive error tracking for LLM operations
-- Version: 1.0
-- Date: 2025-01-18

-- Create LLM retry state table for circuit breaker pattern
CREATE TABLE IF NOT EXISTS llm_retry_state (
    id SERIAL PRIMARY KEY,
    model_name VARCHAR(255) NOT NULL UNIQUE,
    consecutive_failures INTEGER DEFAULT 0,
    last_failure_time TIMESTAMP,
    last_success_time TIMESTAMP,
    circuit_state VARCHAR(50) DEFAULT 'closed',  -- 'closed', 'open', 'half_open'
    circuit_opened_at TIMESTAMP,
    failure_rate FLOAT DEFAULT 0.0,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB
);

CREATE INDEX IF NOT EXISTS idx_llm_retry_model_name ON llm_retry_state(model_name);
CREATE INDEX IF NOT EXISTS idx_llm_retry_circuit_state ON llm_retry_state(circuit_state);

-- Create LLM processing errors table for error logging and monitoring
CREATE TABLE IF NOT EXISTS llm_processing_errors (
    id SERIAL PRIMARY KEY,
    article_uri TEXT REFERENCES articles(uri) ON DELETE CASCADE,
    error_type VARCHAR(255) NOT NULL,
    error_message TEXT NOT NULL,
    severity VARCHAR(50) NOT NULL,  -- 'fatal', 'recoverable', 'skippable', 'degraded'
    model_name VARCHAR(255) NOT NULL,
    retry_count INTEGER DEFAULT 0,
    will_retry BOOLEAN DEFAULT FALSE,
    context JSONB,
    timestamp TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_llm_errors_article_uri ON llm_processing_errors(article_uri);
CREATE INDEX IF NOT EXISTS idx_llm_errors_model_name ON llm_processing_errors(model_name);
CREATE INDEX IF NOT EXISTS idx_llm_errors_severity ON llm_processing_errors(severity);
CREATE INDEX IF NOT EXISTS idx_llm_errors_timestamp ON llm_processing_errors(timestamp);

-- Add LLM status tracking columns to articles table
ALTER TABLE articles ADD COLUMN IF NOT EXISTS llm_status VARCHAR(50);
ALTER TABLE articles ADD COLUMN IF NOT EXISTS llm_status_updated_at TIMESTAMP;
ALTER TABLE articles ADD COLUMN IF NOT EXISTS llm_error_type VARCHAR(255);
ALTER TABLE articles ADD COLUMN IF NOT EXISTS llm_error_message TEXT;
ALTER TABLE articles ADD COLUMN IF NOT EXISTS llm_processing_metadata JSONB;

CREATE INDEX IF NOT EXISTS idx_articles_llm_status ON articles(llm_status);

-- Optional: Create processing jobs table for job tracking (if not exists)
CREATE TABLE IF NOT EXISTS processing_jobs (
    id SERIAL PRIMARY KEY,
    job_id VARCHAR(255) NOT NULL UNIQUE,
    job_type VARCHAR(50) NOT NULL,  -- 'batch_ingest', 'analysis', 'bulk_research'
    status VARCHAR(50) NOT NULL,     -- 'running', 'completed', 'error', 'partial'
    total_items INTEGER DEFAULT 0,
    processed_items INTEGER DEFAULT 0,
    failed_items INTEGER DEFAULT 0,
    error_summary JSONB,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    metadata JSONB
);

CREATE INDEX IF NOT EXISTS idx_processing_jobs_job_id ON processing_jobs(job_id);
CREATE INDEX IF NOT EXISTS idx_processing_jobs_status ON processing_jobs(status);
CREATE INDEX IF NOT EXISTS idx_processing_jobs_job_type ON processing_jobs(job_type);
