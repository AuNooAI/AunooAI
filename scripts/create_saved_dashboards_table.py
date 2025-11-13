"""
Create saved_dashboards table in PostgreSQL database.
Includes PostgreSQL-specific features: JSONB, TEXT[], triggers, and indexes.

Database: PostgreSQL 16.10
Connection: multi_user@localhost:5432/multi
"""
from app.database import get_database_instance

SQL_CREATE_TABLE = """
-- Main table with PostgreSQL-specific types
CREATE TABLE IF NOT EXISTS saved_dashboards (
    id SERIAL PRIMARY KEY,
    topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,

    name VARCHAR(255) NOT NULL,
    description TEXT,

    config JSONB NOT NULL,
    article_uris TEXT[] NOT NULL,

    consensus_data JSONB,
    strategic_data JSONB,
    timeline_data JSONB,
    signals_data JSONB,
    horizons_data JSONB,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    last_accessed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,

    profile_snapshot JSONB,
    articles_analyzed INTEGER,
    model_used VARCHAR(100),

    CONSTRAINT uq_saved_dashboards_topic_user_name UNIQUE(topic_id, user_id, name)
);

-- Standard indexes
CREATE INDEX IF NOT EXISTS idx_saved_dashboards_topic ON saved_dashboards(topic_id);
CREATE INDEX IF NOT EXISTS idx_saved_dashboards_user ON saved_dashboards(user_id);
CREATE INDEX IF NOT EXISTS idx_saved_dashboards_created ON saved_dashboards(created_at DESC);

-- PostgreSQL-specific: GIN index on JSONB for fast JSON queries
CREATE INDEX IF NOT EXISTS idx_saved_dashboards_config_gin ON saved_dashboards USING GIN (config);

-- PostgreSQL-specific: Partial index for active dashboards (performance optimization)
CREATE INDEX IF NOT EXISTS idx_saved_dashboards_active
    ON saved_dashboards(topic_id, user_id, last_accessed_at DESC)
    WHERE last_accessed_at > NOW() - INTERVAL '90 days';

-- PostgreSQL-specific: Full-text search index on name and description
CREATE INDEX IF NOT EXISTS idx_saved_dashboards_search
    ON saved_dashboards USING GIN (to_tsvector('english', coalesce(name, '') || ' ' || coalesce(description, '')));

-- Auto-update updated_at trigger (PostgreSQL feature)
CREATE OR REPLACE FUNCTION update_saved_dashboards_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_saved_dashboards_updated_at ON saved_dashboards;
CREATE TRIGGER trigger_saved_dashboards_updated_at
    BEFORE UPDATE ON saved_dashboards
    FOR EACH ROW
    EXECUTE FUNCTION update_saved_dashboards_timestamp();
"""

def create_saved_dashboards_table():
    """Create saved_dashboards table with PostgreSQL-native features."""
    db = get_database_instance()

    # Check if table exists
    check_query = """
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name = 'saved_dashboards'
        );
    """

    result = db.execute_query(check_query)
    table_exists = result[0][0] if result else False

    if table_exists:
        print("✅ Table 'saved_dashboards' already exists")
        return

    print("Creating 'saved_dashboards' table with PostgreSQL features...")

    # Execute creation SQL
    db.execute_query(SQL_CREATE_TABLE)

    print("✅ Created 'saved_dashboards' table successfully!")
    print("   - JSONB columns for efficient JSON storage")
    print("   - TEXT[] array for article URIs")
    print("   - GIN indexes for fast JSON queries")
    print("   - Partial index for active dashboards (90 days)")
    print("   - Full-text search index on name/description")
    print("   - Auto-update trigger for updated_at timestamp")

if __name__ == "__main__":
    create_saved_dashboards_table()
