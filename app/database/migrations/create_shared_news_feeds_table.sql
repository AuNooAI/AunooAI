-- Create shared news feeds table for sharing functionality
-- Migration: create_shared_news_feeds_table
-- Description: Adds table to store shared news feed data with expiration and access tracking

CREATE TABLE IF NOT EXISTS shared_news_feeds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    share_token TEXT UNIQUE NOT NULL,
    feed_type TEXT NOT NULL,
    feed_data TEXT NOT NULL,
    date_filter TEXT,
    topic_filter TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    access_count INTEGER DEFAULT 0
);

-- Create index for efficient token lookups
CREATE INDEX IF NOT EXISTS idx_shared_feeds_token 
ON shared_news_feeds(share_token);

-- Create index for cleanup operations (expired feeds)
CREATE INDEX IF NOT EXISTS idx_shared_feeds_expires 
ON shared_news_feeds(expires_at);
