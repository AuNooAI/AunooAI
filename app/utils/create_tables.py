def create_articles_table(cursor):
    """Create the articles table with URI as primary key"""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            uri TEXT PRIMARY KEY,
            title TEXT,
            news_source TEXT,
            publication_date TEXT,
            submission_date TEXT DEFAULT CURRENT_TIMESTAMP,
            summary TEXT,
            category TEXT,
            future_signal TEXT,
            future_signal_explanation TEXT,
            sentiment TEXT,
            sentiment_explanation TEXT,
            time_to_impact TEXT,
            time_to_impact_explanation TEXT,
            tags TEXT,
            driver_type TEXT,
            driver_type_explanation TEXT,
            topic TEXT,
            analyzed BOOLEAN DEFAULT FALSE
        )
    """)
    
    # Create unique index on URI
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_articles_uri 
        ON articles(uri)
    """)

def create_keyword_alerts_table(cursor):
    """Create the keyword alerts table with proper foreign key constraint"""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS keyword_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword_id INTEGER NOT NULL,
            article_uri TEXT NOT NULL,
            detected_at TEXT DEFAULT CURRENT_TIMESTAMP,
            is_read INTEGER DEFAULT 0,
            FOREIGN KEY (keyword_id) REFERENCES monitored_keywords(id) ON DELETE CASCADE,
            FOREIGN KEY (article_uri) REFERENCES articles(uri) ON DELETE CASCADE,
            UNIQUE(keyword_id, article_uri)
        )
    """) 