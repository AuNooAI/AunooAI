CREATE TABLE IF NOT EXISTS keyword_alert_articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT UNIQUE NOT NULL,
    title TEXT,
    summary TEXT,
    source TEXT,
    submission_date DATETIME DEFAULT CURRENT_TIMESTAMP,
    topic TEXT,
    keywords TEXT,  -- Store matched keywords
    analyzed BOOLEAN DEFAULT FALSE,  -- Track if article has been analyzed
    moved_to_articles BOOLEAN DEFAULT FALSE  -- Track if moved to main articles table
); 