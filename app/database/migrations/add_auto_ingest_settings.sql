-- Migration script to add auto-ingest settings and status tracking
-- Default values for new users:
-- - auto_ingest_enabled: TRUE (Auto-processing ON)
-- - quality_control_enabled: TRUE
-- - auto_save_approved_only: TRUE (Save Approved Only ON)
-- - default_llm_model: NULL (use first available model)
-- - llm_temperature: 0.2
-- - auto_regenerate_reports: TRUE

-- Add auto-ingest settings to keyword_monitor_settings table
SELECT CASE
    WHEN NOT EXISTS(SELECT 1 FROM pragma_table_info('keyword_monitor_settings') WHERE name='auto_ingest_enabled')
    THEN 'ALTER TABLE keyword_monitor_settings ADD COLUMN auto_ingest_enabled BOOLEAN NOT NULL DEFAULT TRUE;'
END AS sql_command;

SELECT CASE
    WHEN NOT EXISTS(SELECT 1 FROM pragma_table_info('keyword_monitor_settings') WHERE name='min_relevance_threshold')
    THEN 'ALTER TABLE keyword_monitor_settings ADD COLUMN min_relevance_threshold REAL NOT NULL DEFAULT 0.0;'
END AS sql_command;

SELECT CASE
    WHEN NOT EXISTS(SELECT 1 FROM pragma_table_info('keyword_monitor_settings') WHERE name='quality_control_enabled')
    THEN 'ALTER TABLE keyword_monitor_settings ADD COLUMN quality_control_enabled BOOLEAN NOT NULL DEFAULT TRUE;'
END AS sql_command;

SELECT CASE
    WHEN NOT EXISTS(SELECT 1 FROM pragma_table_info('keyword_monitor_settings') WHERE name='auto_save_approved_only')
    THEN 'ALTER TABLE keyword_monitor_settings ADD COLUMN auto_save_approved_only BOOLEAN NOT NULL DEFAULT TRUE;'
END AS sql_command;

SELECT CASE
    WHEN NOT EXISTS(SELECT 1 FROM pragma_table_info('keyword_monitor_settings') WHERE name='default_llm_model')
    THEN 'ALTER TABLE keyword_monitor_settings ADD COLUMN default_llm_model TEXT DEFAULT NULL;'
END AS sql_command;

SELECT CASE
    WHEN NOT EXISTS(SELECT 1 FROM pragma_table_info('keyword_monitor_settings') WHERE name='llm_temperature')
    THEN 'ALTER TABLE keyword_monitor_settings ADD COLUMN llm_temperature REAL NOT NULL DEFAULT 0.2;'
END AS sql_command;

SELECT CASE 
    WHEN NOT EXISTS(SELECT 1 FROM pragma_table_info('keyword_monitor_settings') WHERE name='llm_max_tokens') 
    THEN 'ALTER TABLE keyword_monitor_settings ADD COLUMN llm_max_tokens INTEGER NOT NULL DEFAULT 1000;' 
END AS sql_command;

-- Add status tracking fields to articles table
SELECT CASE 
    WHEN NOT EXISTS(SELECT 1 FROM pragma_table_info('articles') WHERE name='ingest_status') 
    THEN 'ALTER TABLE articles ADD COLUMN ingest_status TEXT DEFAULT "manual";' 
END AS sql_command;

SELECT CASE 
    WHEN NOT EXISTS(SELECT 1 FROM pragma_table_info('articles') WHERE name='quality_score') 
    THEN 'ALTER TABLE articles ADD COLUMN quality_score REAL;' 
END AS sql_command;

SELECT CASE 
    WHEN NOT EXISTS(SELECT 1 FROM pragma_table_info('articles') WHERE name='quality_issues') 
    THEN 'ALTER TABLE articles ADD COLUMN quality_issues TEXT;' 
END AS sql_command;

SELECT CASE 
    WHEN NOT EXISTS(SELECT 1 FROM pragma_table_info('articles') WHERE name='auto_ingested') 
    THEN 'ALTER TABLE articles ADD COLUMN auto_ingested BOOLEAN DEFAULT FALSE;' 
END AS sql_command;

-- Create indexes for new fields for faster queries
CREATE INDEX IF NOT EXISTS idx_articles_ingest_status ON articles(ingest_status);
CREATE INDEX IF NOT EXISTS idx_articles_auto_ingested ON articles(auto_ingested);
CREATE INDEX IF NOT EXISTS idx_articles_quality_score ON articles(quality_score);

-- Update schema version
PRAGMA user_version = 2; 