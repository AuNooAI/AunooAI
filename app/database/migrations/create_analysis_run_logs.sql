-- Create analysis run logs table to track all analyses and articles reviewed
CREATE TABLE IF NOT EXISTS analysis_run_logs (
    id SERIAL PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE, -- UUID for this analysis run
    analysis_type TEXT NOT NULL, -- 'trend_convergence', 'consensus_analysis', 'futures_cone', etc.
    topic TEXT NOT NULL,
    model_used TEXT,
    sample_size INT,
    articles_analyzed INT,
    timeframe_days INT,
    consistency_mode TEXT,
    profile_id INT,
    persona TEXT,
    customer_type TEXT,
    cache_key TEXT,
    cache_hit BOOLEAN DEFAULT 0,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    status TEXT DEFAULT 'running', -- 'running', 'completed', 'failed'
    error_message TEXT,
    metadata TEXT, -- JSON for additional parameters
    FOREIGN KEY (profile_id) REFERENCES organisational_profiles(id) ON DELETE SET NULL
);

-- Create table to track individual articles in each analysis run
CREATE TABLE IF NOT EXISTS analysis_run_articles (
    id SERIAL PRIMARY KEY,
    run_id TEXT NOT NULL,
    article_uri TEXT NOT NULL,
    article_title TEXT,
    article_source TEXT,
    published_date TIMESTAMP,
    sentiment TEXT,
    relevance_score REAL,
    included_in_prompt BOOLEAN DEFAULT 1,
    article_position INT, -- Order in which article was processed
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES analysis_run_logs(run_id) ON DELETE CASCADE,
    FOREIGN KEY (article_uri) REFERENCES articles(uri) ON DELETE CASCADE
);

-- Create indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_analysis_run_logs_type ON analysis_run_logs(analysis_type);
CREATE INDEX IF NOT EXISTS idx_analysis_run_logs_topic ON analysis_run_logs(topic);
CREATE INDEX IF NOT EXISTS idx_analysis_run_logs_started ON analysis_run_logs(started_at);
CREATE INDEX IF NOT EXISTS idx_analysis_run_logs_run_id ON analysis_run_logs(run_id);
CREATE INDEX IF NOT EXISTS idx_analysis_run_articles_run_id ON analysis_run_articles(run_id);
CREATE INDEX IF NOT EXISTS idx_analysis_run_articles_uri ON analysis_run_articles(article_uri);
CREATE INDEX IF NOT EXISTS idx_analysis_run_articles_created ON analysis_run_articles(created_at);
