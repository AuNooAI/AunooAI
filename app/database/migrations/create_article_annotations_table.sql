CREATE TABLE IF NOT EXISTS article_annotations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_uri TEXT NOT NULL,
    author TEXT NOT NULL,
    content TEXT NOT NULL,
    is_private BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (article_uri) REFERENCES articles(uri) ON DELETE CASCADE
);

-- Remove any existing unique constraint if it exists
DROP INDEX IF EXISTS idx_article_author;

-- Trigger to update the updated_at timestamp
CREATE TRIGGER IF NOT EXISTS update_article_annotations_timestamp 
AFTER UPDATE ON article_annotations
BEGIN
    UPDATE article_annotations 
    SET updated_at = CURRENT_TIMESTAMP 
    WHERE id = NEW.id;
END; 