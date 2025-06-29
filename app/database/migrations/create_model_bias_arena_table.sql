-- Model Bias Arena Tables
CREATE TABLE IF NOT EXISTS model_bias_arena_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    benchmark_model TEXT NOT NULL,
    selected_models TEXT NOT NULL, -- JSON array of model names
    article_count INTEGER NOT NULL DEFAULT 25,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    status TEXT DEFAULT 'running' -- running, completed, failed
);

CREATE TABLE IF NOT EXISTS model_bias_arena_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    article_uri TEXT NOT NULL,
    model_name TEXT NOT NULL,
    response_text TEXT,
    bias_score REAL, -- 0-1 scale (legacy field)
    confidence_score REAL, -- 0-1 scale
    response_time_ms INTEGER,
    error_message TEXT,
    -- Ontological analysis fields with explanations
    sentiment TEXT,
    sentiment_explanation TEXT,
    future_signal TEXT,
    future_signal_explanation TEXT,
    time_to_impact TEXT,
    time_to_impact_explanation TEXT,
    driver_type TEXT,
    driver_type_explanation TEXT,
    category TEXT,
    category_explanation TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES model_bias_arena_runs(id) ON DELETE CASCADE,
    FOREIGN KEY (article_uri) REFERENCES articles(uri) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS model_bias_arena_articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    article_uri TEXT NOT NULL,
    article_title TEXT,
    article_summary TEXT,
    selected_for_benchmark BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES model_bias_arena_runs(id) ON DELETE CASCADE,
    FOREIGN KEY (article_uri) REFERENCES articles(uri) ON DELETE CASCADE,
    UNIQUE(run_id, article_uri)
);

-- Indexes for better performance
CREATE INDEX IF NOT EXISTS idx_bias_arena_results_run_id ON model_bias_arena_results(run_id);
CREATE INDEX IF NOT EXISTS idx_bias_arena_results_model ON model_bias_arena_results(model_name);
CREATE INDEX IF NOT EXISTS idx_bias_arena_articles_run_id ON model_bias_arena_articles(run_id);
CREATE INDEX IF NOT EXISTS idx_bias_arena_runs_status ON model_bias_arena_runs(status); 