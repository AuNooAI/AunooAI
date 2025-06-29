-- Migration: Update Feed Sources Types
-- Date: 2024-01-XX
-- Description: Update source_type constraint to support specific source types instead of generic ones

-- SQLite doesn't support altering CHECK constraints directly
-- So we need to recreate the table with the new constraint

-- Create new table with updated constraint
CREATE TABLE feed_group_sources_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN ('bluesky', 'arxiv')),
    keywords TEXT NOT NULL, -- JSON array of keywords
    enabled BOOLEAN DEFAULT TRUE,
    last_checked TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (group_id) REFERENCES feed_keyword_groups(id) ON DELETE CASCADE
);

-- Copy existing data (if any) with type mapping
INSERT INTO feed_group_sources_new (id, group_id, source_type, keywords, enabled, last_checked, created_at)
SELECT 
    id, 
    group_id, 
    CASE 
        WHEN source_type = 'social_media' THEN 'bluesky'
        WHEN source_type = 'academic_journals' THEN 'arxiv'
        ELSE source_type
    END as source_type,
    keywords, 
    enabled, 
    last_checked, 
    created_at
FROM feed_group_sources
WHERE source_type IN ('social_media', 'academic_journals', 'bluesky', 'arxiv');

-- Drop old table
DROP TABLE feed_group_sources;

-- Rename new table
ALTER TABLE feed_group_sources_new RENAME TO feed_group_sources;

-- Recreate index
CREATE INDEX IF NOT EXISTS idx_feed_group_sources_group_id ON feed_group_sources(group_id);
CREATE INDEX IF NOT EXISTS idx_feed_group_sources_source_type ON feed_group_sources(source_type);

-- Also update feed_items table constraint to match our supported types
CREATE TABLE feed_items_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT NOT NULL CHECK (source_type IN ('bluesky', 'arxiv')),
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

-- Copy existing data from feed_items
INSERT INTO feed_items_new SELECT * FROM feed_items WHERE source_type IN ('bluesky', 'arxiv');

-- Drop old table
DROP TABLE feed_items;

-- Rename new table
ALTER TABLE feed_items_new RENAME TO feed_items;

-- Recreate indexes
CREATE INDEX IF NOT EXISTS idx_feed_items_group_id ON feed_items(group_id);
CREATE INDEX IF NOT EXISTS idx_feed_items_source_type ON feed_items(source_type);
CREATE INDEX IF NOT EXISTS idx_feed_items_publication_date ON feed_items(publication_date);
CREATE INDEX IF NOT EXISTS idx_feed_items_is_hidden ON feed_items(is_hidden); 