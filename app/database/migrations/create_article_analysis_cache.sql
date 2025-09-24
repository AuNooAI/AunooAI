-- Create article analysis cache table
CREATE TABLE IF NOT EXISTS article_analysis_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_uri TEXT NOT NULL,
    analysis_type TEXT NOT NULL, -- 'summary', 'themes', 'deep_dive', 'consensus', 'timeline'
    content TEXT NOT NULL,
    model_used TEXT NOT NULL,
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    metadata TEXT, -- JSON for additional data like structured themes
    FOREIGN KEY (article_uri) REFERENCES articles(uri) ON DELETE CASCADE,
    UNIQUE(article_uri, analysis_type, model_used)
);

-- Create indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_article_analysis_cache_uri ON article_analysis_cache(article_uri);
CREATE INDEX IF NOT EXISTS idx_article_analysis_cache_type ON article_analysis_cache(analysis_type);
CREATE INDEX IF NOT EXISTS idx_article_analysis_cache_expires ON article_analysis_cache(expires_at);
