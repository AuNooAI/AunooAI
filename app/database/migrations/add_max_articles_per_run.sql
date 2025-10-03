-- Migration script to add max_articles_per_run setting to keyword_monitor_settings table

-- Add max_articles_per_run setting
SELECT CASE
    WHEN NOT EXISTS(SELECT 1 FROM pragma_table_info('keyword_monitor_settings') WHERE name='max_articles_per_run')
    THEN 'ALTER TABLE keyword_monitor_settings ADD COLUMN max_articles_per_run INTEGER NOT NULL DEFAULT 50;'
END AS sql_command;
