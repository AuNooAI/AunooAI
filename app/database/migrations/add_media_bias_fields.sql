-- Migration script to add media bias fields to the articles table

-- Add columns only if they don't exist
-- SQLite doesn't have direct "ADD COLUMN IF NOT EXISTS" support, so we'll use a workaround
-- First, check if columns exist using pragma_table_info, then add them conditionally

-- bias column
SELECT CASE 
    WHEN NOT EXISTS(SELECT 1 FROM pragma_table_info('articles') WHERE name='bias') 
    THEN 'ALTER TABLE articles ADD COLUMN bias TEXT;' 
END AS sql_command;

-- factual_reporting column
SELECT CASE 
    WHEN NOT EXISTS(SELECT 1 FROM pragma_table_info('articles') WHERE name='factual_reporting') 
    THEN 'ALTER TABLE articles ADD COLUMN factual_reporting TEXT;' 
END AS sql_command;

-- mbfc_credibility_rating column
SELECT CASE 
    WHEN NOT EXISTS(SELECT 1 FROM pragma_table_info('articles') WHERE name='mbfc_credibility_rating') 
    THEN 'ALTER TABLE articles ADD COLUMN mbfc_credibility_rating TEXT;' 
END AS sql_command;

-- bias_source column
SELECT CASE 
    WHEN NOT EXISTS(SELECT 1 FROM pragma_table_info('articles') WHERE name='bias_source') 
    THEN 'ALTER TABLE articles ADD COLUMN bias_source TEXT;' 
END AS sql_command;

-- bias_country column
SELECT CASE 
    WHEN NOT EXISTS(SELECT 1 FROM pragma_table_info('articles') WHERE name='bias_country') 
    THEN 'ALTER TABLE articles ADD COLUMN bias_country TEXT;' 
END AS sql_command;

-- press_freedom column
SELECT CASE 
    WHEN NOT EXISTS(SELECT 1 FROM pragma_table_info('articles') WHERE name='press_freedom') 
    THEN 'ALTER TABLE articles ADD COLUMN press_freedom TEXT;' 
END AS sql_command;

-- media_type column
SELECT CASE 
    WHEN NOT EXISTS(SELECT 1 FROM pragma_table_info('articles') WHERE name='media_type') 
    THEN 'ALTER TABLE articles ADD COLUMN media_type TEXT;' 
END AS sql_command;

-- popularity column
SELECT CASE 
    WHEN NOT EXISTS(SELECT 1 FROM pragma_table_info('articles') WHERE name='popularity') 
    THEN 'ALTER TABLE articles ADD COLUMN popularity TEXT;' 
END AS sql_command;

-- Create indexes for faster lookups (IF NOT EXISTS so safe to run multiple times)
CREATE INDEX IF NOT EXISTS idx_articles_bias ON articles(bias);
CREATE INDEX IF NOT EXISTS idx_articles_factual_reporting ON articles(factual_reporting);

-- Update schema version (SQLite doesn't support arithmetic in PRAGMA)
PRAGMA user_version = 1; 