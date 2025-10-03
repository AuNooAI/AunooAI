-- Create migration history tracking table
-- This tracks which migrations have been applied to the database

CREATE TABLE IF NOT EXISTS migration_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    migration_name TEXT NOT NULL UNIQUE,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT,
    checksum TEXT  -- Optional: SHA256 hash of migration file for integrity checking
);

-- Create index for fast lookup
CREATE INDEX IF NOT EXISTS idx_migration_name ON migration_history(migration_name);
CREATE INDEX IF NOT EXISTS idx_applied_at ON migration_history(applied_at DESC);

-- Mark this migration as applied
INSERT OR IGNORE INTO migration_history (migration_name, success)
VALUES ('create_migration_history_table.sql', TRUE);
