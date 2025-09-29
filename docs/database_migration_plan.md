# Database Migration Plan: Hybrid Architecture

## Overview

This document outlines the plan for migrating from a single SQLite database to a hybrid architecture that separates system configuration data from analytics/content data.

**Current State**: Single SQLite database handling all data
**Target State**: SQLite for config + PostgreSQL for analytics/content

## Architecture Split

### SQLite Database (Keep - System/Config Data)
- User authentication & sessions
- Application configuration (`app_config`)
- System settings & preferences
- UI state & user preferences
- Small lookup tables
- OAuth tokens & security data
- Keyword monitoring settings
- User feed subscriptions

### PostgreSQL Database (New - Analytics/Content Data)
- `articles` table → Primary content storage
- `raw_articles` → Content cache
- `keyword_article_matches` → Alert data
- `article_analysis_cache` → AI results
- Vector embeddings & search data
- Bulk processing results
- Media bias data (large datasets)

## Migration Timeline: 2-3 Weeks

### Phase 1: Preparation (Week 1)

#### Days 1-2: Database Setup
- [ ] Set up PostgreSQL instance (local/cloud)
- [ ] Create PostgreSQL database and user
- [ ] Configure connection pooling (pgbouncer/pgpool)
- [ ] Set up backup strategy for PostgreSQL

#### Days 3-4: Schema Migration
- [ ] Extract article-related tables from SQLite schema
- [ ] Create PostgreSQL schema for analytics tables
- [ ] Add indexes for performance optimization
- [ ] Create migration validation scripts

#### Day 5: Database Abstraction Layer
- [ ] Create `HybridDatabase` class
- [ ] Implement dual-connection management
- [ ] Add connection pooling for PostgreSQL
- [ ] Create database router logic

### Phase 2: Data Migration (Week 2)

#### Days 1-2: Data Export/Import
- [ ] Export articles data from SQLite
- [ ] Transform data for PostgreSQL format
- [ ] Bulk import to PostgreSQL
- [ ] Validate data integrity and counts

#### Days 3-4: Code Updates
- [ ] Update `BulkResearch` class to use PostgreSQL
- [ ] Modify article routes to use analytics DB
- [ ] Update vector store integration
- [ ] Keep config routes using SQLite

#### Day 5: Testing
- [ ] Unit tests for dual-database operations
- [ ] Integration tests for bulk processing
- [ ] Performance testing
- [ ] Rollback procedure testing

### Phase 3: Deployment & Optimization (Week 3)

#### Days 1-2: Staging Deployment
- [ ] Deploy to staging environment
- [ ] Run parallel processing tests
- [ ] Validate no database blocking issues
- [ ] Performance benchmarking

#### Days 3-4: Production Migration
- [ ] Schedule maintenance window
- [ ] Run production migration
- [ ] Monitor performance metrics
- [ ] Validate all systems operational

#### Day 5: Optimization
- [ ] Fine-tune PostgreSQL configuration
- [ ] Optimize connection pool settings
- [ ] Monitor and adjust performance
- [ ] Documentation updates

## Technical Implementation

### Database Connection Management

```python
class HybridDatabase:
    def __init__(self):
        # System/config database (SQLite)
        self.config_db = sqlite3.connect('config.db')

        # Analytics database (PostgreSQL)
        self.analytics_pool = asyncpg.create_pool(
            host='localhost',
            database='analytics',
            user='aunoo_user',
            password='secure_password',
            min_size=5,
            max_size=20
        )

    # Config operations → SQLite
    async def save_config(self, key, value):
        return self.config_db.execute(
            "INSERT OR REPLACE INTO app_config (config_key, config_value) VALUES (?, ?)",
            (key, value)
        )

    # Article operations → PostgreSQL
    async def save_article(self, article):
        async with self.analytics_pool.acquire() as conn:
            return await conn.execute("""
                INSERT INTO articles (uri, title, news_source, ...)
                VALUES ($1, $2, $3, ...)
            """, article['uri'], article['title'], article['news_source'], ...)
```

### Migration Scripts

#### Data Export Script
```python
async def export_articles_from_sqlite():
    """Export articles from SQLite to JSON for PostgreSQL import"""
    sqlite_db = sqlite3.connect('app/data/fnaapp.db')

    # Export articles
    articles = sqlite_db.execute("SELECT * FROM articles").fetchall()

    # Export raw_articles
    raw_articles = sqlite_db.execute("SELECT * FROM raw_articles").fetchall()

    # Export keyword_article_matches
    keyword_matches = sqlite_db.execute("SELECT * FROM keyword_article_matches").fetchall()

    # Save to JSON files for import
    with open('migration_data/articles.json', 'w') as f:
        json.dump(articles, f)

    with open('migration_data/raw_articles.json', 'w') as f:
        json.dump(raw_articles, f)

    with open('migration_data/keyword_matches.json', 'w') as f:
        json.dump(keyword_matches, f)

    print(f"Exported {len(articles)} articles, {len(raw_articles)} raw articles, {len(keyword_matches)} keyword matches")
```

#### Data Import Script
```python
async def import_articles_to_postgresql():
    """Import articles from JSON to PostgreSQL"""

    # Connect to PostgreSQL
    conn = await asyncpg.connect(DATABASE_URL)

    # Import articles
    with open('migration_data/articles.json', 'r') as f:
        articles = json.load(f)

    await conn.executemany("""
        INSERT INTO articles (
            uri, title, news_source, publication_date, submission_date,
            summary, category, future_signal, future_signal_explanation,
            sentiment, sentiment_explanation, time_to_impact, time_to_impact_explanation,
            tags, driver_type, driver_type_explanation, topic, analyzed,
            bias, factual_reporting, mbfc_credibility_rating, auto_ingested
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22)
    """, articles)

    # Import raw_articles
    with open('migration_data/raw_articles.json', 'r') as f:
        raw_articles = json.load(f)

    await conn.executemany("""
        INSERT INTO raw_articles (uri, raw_markdown, topic, created_at)
        VALUES ($1, $2, $3, $4)
    """, raw_articles)

    # Import keyword_article_matches
    with open('migration_data/keyword_matches.json', 'r') as f:
        keyword_matches = json.load(f)

    await conn.executemany("""
        INSERT INTO keyword_article_matches (
            article_uri, keyword_ids, group_id, detected_at, is_read
        ) VALUES ($1, $2, $3, $4, $5)
    """, keyword_matches)

    await conn.close()
    print("Import completed successfully")
```

### PostgreSQL Schema

```sql
-- Articles table (main content)
CREATE TABLE articles (
    uri TEXT PRIMARY KEY,
    title TEXT,
    news_source TEXT,
    publication_date TIMESTAMP,
    submission_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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
    analyzed BOOLEAN DEFAULT FALSE,
    bias TEXT,
    factual_reporting TEXT,
    mbfc_credibility_rating TEXT,
    bias_source TEXT,
    bias_country TEXT,
    press_freedom TEXT,
    media_type TEXT,
    popularity TEXT,
    topic_alignment_score REAL,
    keyword_relevance_score REAL,
    confidence_score REAL,
    overall_match_explanation TEXT,
    extracted_article_topics TEXT,
    extracted_article_keywords TEXT,
    ingest_status TEXT DEFAULT 'manual',
    quality_score REAL,
    quality_issues TEXT,
    auto_ingested BOOLEAN DEFAULT FALSE
);

-- Raw articles table (content cache)
CREATE TABLE raw_articles (
    id SERIAL PRIMARY KEY,
    uri TEXT NOT NULL,
    raw_markdown TEXT,
    topic TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (uri) REFERENCES articles(uri) ON DELETE CASCADE
);

-- Keyword article matches (alerts)
CREATE TABLE keyword_article_matches (
    id SERIAL PRIMARY KEY,
    article_uri TEXT NOT NULL,
    keyword_ids TEXT NOT NULL,
    group_id INTEGER NOT NULL,
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_read INTEGER DEFAULT 0,
    FOREIGN KEY (article_uri) REFERENCES articles(uri) ON DELETE CASCADE
);

-- Indexes for performance
CREATE INDEX idx_articles_topic ON articles(topic);
CREATE INDEX idx_articles_submission_date ON articles(submission_date);
CREATE INDEX idx_articles_auto_ingested ON articles(auto_ingested);
CREATE INDEX idx_articles_analyzed ON articles(analyzed);
CREATE INDEX idx_raw_articles_uri ON raw_articles(uri);
CREATE INDEX idx_keyword_matches_group_id ON keyword_article_matches(group_id);
CREATE INDEX idx_keyword_matches_detected_at ON keyword_article_matches(detected_at);
```

## Code Changes Required

### File Updates

#### 1. `app/database.py`
- Add PostgreSQL connection management
- Keep SQLite connection for config data
- Implement routing logic for different data types

#### 2. `app/bulk_research.py`
- Update to use PostgreSQL for article operations
- Modify save_bulk_articles to use async PostgreSQL
- Keep vector operations async

#### 3. `app/routes/` (Various route files)
- Update article-related routes to use PostgreSQL
- Keep config routes using SQLite
- Update API responses to handle dual-database

#### 4. `app/vector_store.py`
- Update to work with PostgreSQL article data
- Maintain compatibility with existing vector operations

#### 5. `app/services/auto_ingest_service.py`
- Update to use hybrid database approach
- Ensure article operations use PostgreSQL

### Environment Configuration

```bash
# PostgreSQL connection
DATABASE_URL=postgresql://aunoo_user:password@localhost:5432/analytics
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=analytics
POSTGRES_USER=aunoo_user
POSTGRES_PASSWORD=secure_password

# Connection pool settings
POSTGRES_MIN_CONNECTIONS=5
POSTGRES_MAX_CONNECTIONS=20
POSTGRES_POOL_TIMEOUT=30

# SQLite config (keep existing)
SQLITE_DB_PATH=app/data/fnaapp.db
```

## Validation & Testing

### Data Integrity Checks
```python
async def validate_migration():
    """Validate migration data integrity"""

    # Count records in both databases
    sqlite_count = sqlite_db.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    pg_count = await pg_conn.fetchval("SELECT COUNT(*) FROM articles")

    assert sqlite_count == pg_count, f"Article count mismatch: {sqlite_count} vs {pg_count}"

    # Sample data validation
    sample_uris = sqlite_db.execute("SELECT uri FROM articles LIMIT 10").fetchall()
    for uri_tuple in sample_uris:
        uri = uri_tuple[0]

        sqlite_article = sqlite_db.execute("SELECT title FROM articles WHERE uri = ?", (uri,)).fetchone()
        pg_article = await pg_conn.fetchrow("SELECT title FROM articles WHERE uri = $1", uri)

        assert sqlite_article[0] == pg_article['title'], f"Title mismatch for {uri}"

    print("✅ Migration validation passed")
```

### Performance Testing
```python
async def performance_test():
    """Test bulk operations performance"""

    # Test bulk article save
    test_articles = [generate_test_article() for _ in range(100)]

    start_time = time.time()
    await bulk_research.save_bulk_articles(test_articles)
    end_time = time.time()

    print(f"Bulk save of 100 articles: {end_time - start_time:.2f} seconds")

    # Test concurrent operations
    tasks = []
    for i in range(10):
        task = asyncio.create_task(
            bulk_research.save_bulk_articles([generate_test_article()])
        )
        tasks.append(task)

    start_time = time.time()
    await asyncio.gather(*tasks)
    end_time = time.time()

    print(f"10 concurrent article saves: {end_time - start_time:.2f} seconds")
```

## Rollback Plan

### Emergency Rollback Procedure
1. **Stop application services**
2. **Switch database configuration back to SQLite**
3. **Import recent data from PostgreSQL back to SQLite**
4. **Restart application with original configuration**

### Rollback Script
```python
async def rollback_to_sqlite():
    """Emergency rollback to SQLite"""

    # Export recent data from PostgreSQL
    recent_articles = await pg_conn.fetch("""
        SELECT * FROM articles
        WHERE submission_date > $1
    """, rollback_timestamp)

    # Import to SQLite
    sqlite_db.executemany("""
        INSERT OR REPLACE INTO articles (...) VALUES (...)
    """, recent_articles)

    print(f"Rolled back {len(recent_articles)} recent articles to SQLite")
```

## Benefits Expected

### Performance Improvements
- **Eliminated database blocking** during bulk operations
- **Concurrent article processing** without locks
- **Better connection pooling** for high-throughput operations
- **Optimized queries** using PostgreSQL features

### Operational Benefits
- **Separate backup strategies** for config vs content
- **Independent scaling** of analytics database
- **Better monitoring** and maintenance capabilities
- **Future-proof architecture** for growth

### Development Benefits
- **Cleaner separation of concerns**
- **Easier testing** with isolated data types
- **Better debugging** with separate connection pools
- **Simplified maintenance** with clear boundaries

## Success Criteria

### Performance Metrics
- [ ] No database blocking during bulk operations
- [ ] Concurrent article saves complete without errors
- [ ] Bulk processing time improved by 50%+
- [ ] System remains responsive during large imports

### Functionality Validation
- [ ] All existing features work correctly
- [ ] Auto-ingest pipeline functions properly
- [ ] Vector search integration maintained
- [ ] User authentication/config unchanged

### Operational Readiness
- [ ] Monitoring setup for both databases
- [ ] Backup procedures tested and documented
- [ ] Rollback procedure validated
- [ ] Team trained on new architecture

## Risk Mitigation

### High Risk Items
1. **Data Loss During Migration**
   - Mitigation: Complete backup before migration
   - Validation: Comprehensive data integrity checks

2. **Application Downtime**
   - Mitigation: Staging environment testing
   - Validation: Parallel deployment strategy

3. **Performance Regression**
   - Mitigation: Extensive performance testing
   - Validation: Benchmark comparison pre/post migration

### Medium Risk Items
1. **Configuration Errors**
   - Mitigation: Infrastructure as code
   - Validation: Automated configuration testing

2. **Connection Pool Issues**
   - Mitigation: Gradual load increase
   - Validation: Load testing in staging

## Post-Migration Tasks

### Immediate (Week 4)
- [ ] Monitor performance metrics
- [ ] Tune PostgreSQL configuration
- [ ] Optimize connection pool settings
- [ ] Update documentation

### Medium-term (Month 2)
- [ ] Implement PostgreSQL-specific optimizations
- [ ] Add advanced monitoring and alerting
- [ ] Consider read replicas for analytics
- [ ] Plan for future scaling needs

### Long-term (Month 3+)
- [ ] Evaluate ClickHouse for heavy analytics
- [ ] Consider sharding strategies
- [ ] Implement data archiving policies
- [ ] Plan for multi-region deployment

---

**Document Version**: 1.0
**Last Updated**: 2024-09-29
**Author**: Database Migration Team
**Review Date**: Monthly