-- Migration script to add provider column to keyword_monitor_settings table

-- Add provider setting (for selecting newsapi, newsdata, etc.)
SELECT CASE
    WHEN NOT EXISTS(SELECT 1 FROM pragma_table_info('keyword_monitor_settings') WHERE name='provider')
    THEN 'ALTER TABLE keyword_monitor_settings ADD COLUMN provider TEXT DEFAULT ''newsapi'';'
END AS sql_command;
