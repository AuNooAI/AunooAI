-- Migration: Create Feed System Tables
-- Date: 2024-01-XX
-- Description: Add unified feed system for social media and academic journals
-- Note: This is separate from existing keyword_groups which handles news monitoring

-- Feed Keyword Groups (separate from existing keyword_groups for news)
CREATE TABLE IF NOT EXISTS feed_keyword_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    color TEXT DEFAULT '#FF69B4',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Feed Sources for each keyword group
CREATE TABLE IF NOT EXISTS feed_group_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN ('social_media', 'academic_journals')),
    keywords TEXT NOT NULL, -- JSON array of keywords
    enabled BOOLEAN DEFAULT TRUE,
    last_checked TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (group_id) REFERENCES feed_keyword_groups(id) ON DELETE CASCADE
);

-- Feed Items (unified storage for social media and academic content)
CREATE TABLE IF NOT EXISTS feed_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT NOT NULL CHECK (source_type IN ('bluesky', 'arxiv', 'mastodon', 'twitter')),
    source_id TEXT NOT NULL, -- unique ID from source
    group_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    content TEXT,
    author TEXT,
    author_handle TEXT,
    url TEXT NOT NULL,
    publication_date TIMESTAMP,
    engagement_metrics TEXT, -- JSON: likes, reposts, etc.
    tags TEXT, -- JSON array
    mentions TEXT, -- JSON array
    images TEXT, -- JSON array of image URLs
    is_hidden BOOLEAN DEFAULT FALSE,
    is_starred BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (group_id) REFERENCES feed_keyword_groups(id) ON DELETE CASCADE,
    UNIQUE(source_type, source_id, group_id)
);

-- User preferences for feed groups
CREATE TABLE IF NOT EXISTS user_feed_subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER DEFAULT 1, -- For now, single user system
    group_id INTEGER NOT NULL,
    notification_enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (group_id) REFERENCES feed_keyword_groups(id) ON DELETE CASCADE
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_feed_items_group_id ON feed_items(group_id);
CREATE INDEX IF NOT EXISTS idx_feed_items_source_type ON feed_items(source_type);
CREATE INDEX IF NOT EXISTS idx_feed_items_publication_date ON feed_items(publication_date);
CREATE INDEX IF NOT EXISTS idx_feed_items_is_hidden ON feed_items(is_hidden);
CREATE INDEX IF NOT EXISTS idx_feed_group_sources_group_id ON feed_group_sources(group_id);
CREATE INDEX IF NOT EXISTS idx_feed_group_sources_source_type ON feed_group_sources(source_type);
CREATE INDEX IF NOT EXISTS idx_user_feed_subscriptions_group_id ON user_feed_subscriptions(group_id); 