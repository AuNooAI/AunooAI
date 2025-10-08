# AunooAI Database Schema Specification

## Database Configuration

**Database Engine**: SQLite 3.x
**Database Location**: `{DATABASE_DIR}/{instance}/fnaapp.db`
**Connection Mode**: WAL (Write-Ahead Logging) for concurrent access
**Connection Pooling**: Thread-local connections with 20 max connections
**Migration System**: SQL files in `app/database/migrations/`

## Core Tables

### table:articles
**Purpose**: Store collected and analyzed articles from various sources

**Primary Key**: `uri` (Text, unique identifier from source URL)

**Indexes**:
- `idx_topic` on `topic`
- `idx_analyzed` on `analyzed` 
- `idx_publication_date` on `publication_date`
- `idx_news_source` on `news_source`

**Fields**:
```sql
uri TEXT PRIMARY KEY,                    -- Article unique identifier (from source URL)
title TEXT,                              -- Article headline (max 500 chars)
news_source TEXT,                        -- Publication name (e.g., "TechCrunch", "arXiv")
publication_date TEXT,                   -- ISO 8601 timestamp
submission_date TEXT DEFAULT CURRENT_TIMESTAMP,  -- When article was processed
summary TEXT,                            -- AI-generated summary
category TEXT,                           -- Content category classification
future_signal TEXT,                      -- Future trend indicator
future_signal_explanation TEXT,          -- Explanation of future signal
sentiment TEXT,                          -- Sentiment analysis result
sentiment_explanation TEXT,              -- Explanation of sentiment
time_to_impact TEXT,                     -- Estimated impact timeline
time_to_impact_explanation TEXT,         -- Explanation of time to impact
tags TEXT,                               -- Content tags (JSON array)
driver_type TEXT,                        -- Driver type classification
driver_type_explanation TEXT,            -- Explanation of driver type
topic TEXT,                              -- Research topic classification
analyzed BOOLEAN DEFAULT FALSE,          -- Analysis completion flag
bias TEXT,                               -- Bias assessment
relevance_score REAL,                    -- Content relevance score (0.0-1.0)
created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
```

**Constraints**:
- `uri` must be unique across all articles
- `relevance_score` must be between 0.0 and 1.0
- `analyzed` defaults to FALSE until AI analysis completes

**Triggers**:
- Update `updated_at` timestamp on any field change

---

### table:users
**Purpose**: User authentication and profile management

**Primary Key**: `id` (Integer, auto-increment)

**Indexes**:
- `idx_username` on `username` (unique)
- `idx_email` on `email` (unique)

**Fields**:
```sql
id INTEGER PRIMARY KEY AUTOINCREMENT,
username TEXT UNIQUE NOT NULL,           -- Unique username
email TEXT UNIQUE NOT NULL,              -- User email address
hashed_password TEXT NOT NULL,           -- bcrypt password hash
is_active BOOLEAN DEFAULT TRUE,          -- Account status
is_admin BOOLEAN DEFAULT FALSE,          -- Admin privileges
created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
last_login TIMESTAMP,
login_attempts INTEGER DEFAULT 0,        -- Failed login counter
locked_until TIMESTAMP                   -- Account lockout timestamp
```

**Constraints**:
- `username` must be unique and not null
- `email` must be unique and valid email format
- `hashed_password` must be bcrypt hash
- `is_admin` can only be TRUE if `is_active` is TRUE

---

### table:topics
**Purpose**: Research topics and their configurations

**Primary Key**: `name` (Text, topic identifier)

**Indexes**:
- `idx_topic_active` on `name, is_active`
- `idx_updated_at` on `updated_at`

**Fields**:
```sql
name TEXT PRIMARY KEY,                   -- Topic identifier (e.g., "artificial_intelligence")
description TEXT,                        -- Topic description
keywords TEXT,                           -- Associated keywords (JSON array)
created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
is_active BOOLEAN DEFAULT TRUE,          -- Topic status
config_json TEXT,                        -- Topic configuration (JSON)
news_query TEXT,                         -- News collection query
paper_query TEXT,                        -- Academic paper query
created_by INTEGER,                      -- User ID who created topic
FOREIGN KEY (created_by) REFERENCES users(id)
```

**Constraints**:
- `name` must be unique and URL-safe
- `config_json` must be valid JSON
- `created_by` must reference valid user

**Configuration JSON Structure**:
```json
{
  "categories": ["Technology", "Business", "Science"],
  "sentiments": ["Positive", "Neutral", "Negative"],
  "futureSignals": ["Emerging", "Accelerating", "Disruptive"],
  "timeToImpacts": ["Immediate", "Short-term", "Mid-term", "Long-term"],
  "keywords": ["AI", "machine learning", "automation"],
  "sources": ["newsapi", "arxiv", "bluesky"]
}
```

---

### table:keyword_alerts
**Purpose**: Keyword monitoring and alerting system

**Primary Key**: `id` (Integer, auto-increment)

**Indexes**:
- `idx_user_keyword` on `user_id, keyword`
- `idx_topic_active` on `topic, is_active`
- `idx_created_at` on `created_at`

**Fields**:
```sql
id INTEGER PRIMARY KEY AUTOINCREMENT,
user_id INTEGER NOT NULL,                -- User who created alert
keyword TEXT NOT NULL,                   -- Monitored keyword
topic TEXT NOT NULL,                     -- Associated topic
threshold INTEGER DEFAULT 1,             -- Alert threshold (articles per day)
is_active BOOLEAN DEFAULT TRUE,          -- Alert status
created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
last_triggered TIMESTAMP,                -- Last alert timestamp
trigger_count INTEGER DEFAULT 0,         -- Total alerts sent
FOREIGN KEY (user_id) REFERENCES users(id),
FOREIGN KEY (topic) REFERENCES topics(name)
```

**Constraints**:
- `keyword` must be minimum 3 characters
- `threshold` must be positive integer
- `user_id` must reference valid user
- `topic` must reference valid topic

---

### table:auspex_chats
**Purpose**: AI chat session management

**Primary Key**: `id` (Integer, auto-increment)

**Indexes**:
- `idx_auspex_chats_topic` on `topic`
- `idx_auspex_chats_user_id` on `user_id`
- `idx_auspex_chats_profile_id` on `profile_id`
- `idx_auspex_chats_user_profile` on `user_id, profile_id`

**Fields**:
```sql
id INTEGER PRIMARY KEY AUTOINCREMENT,
topic TEXT NOT NULL,                     -- Topic for chat context
title TEXT,                              -- Chat session title
created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
user_id TEXT,                            -- Chat owner (username)
profile_id INTEGER,                      -- Optional organizational profile ID
metadata TEXT,                           -- Additional chat metadata (JSON)
FOREIGN KEY (user_id) REFERENCES users(username) ON DELETE SET NULL,
FOREIGN KEY (profile_id) REFERENCES organizational_profiles(id)
```

---

### table:auspex_messages
**Purpose**: Individual chat messages

**Primary Key**: `id` (Integer, auto-increment)

**Indexes**:
- `idx_chat_created` on `chat_id, created_at`
- `idx_role` on `role`

**Fields**:
```sql
id INTEGER PRIMARY KEY AUTOINCREMENT,
chat_id INTEGER NOT NULL,                -- Parent chat session
role TEXT NOT NULL,                      -- Message role (user/assistant/system)
content TEXT NOT NULL,                   -- Message content
model_used TEXT,                          -- AI model used for generation
created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
metadata TEXT,                           -- Additional message metadata (JSON)
tokens_used INTEGER,                      -- Token count for this message
FOREIGN KEY (chat_id) REFERENCES auspex_chats(id) ON DELETE CASCADE
```

**Constraints**:
- `role` must be one of: "user", "assistant", "system"
- `content` cannot be empty
- `chat_id` must reference valid chat

---

### table:auspex_prompts
**Purpose**: System prompt templates management

**Primary Key**: `id` (Integer, auto-increment)

**Indexes**:
- `idx_name` on `name` (unique)
- `idx_is_default` on `is_default`

**Fields**:
```sql
id INTEGER PRIMARY KEY AUTOINCREMENT,
name TEXT UNIQUE NOT NULL,               -- Prompt identifier
title TEXT NOT NULL,                     -- Human-readable title
content TEXT NOT NULL,                   -- Prompt template content
is_default BOOLEAN DEFAULT FALSE,        -- Default prompt flag
user_created BOOLEAN DEFAULT FALSE,      -- User-created vs system prompt
created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
created_by INTEGER,                      -- User who created prompt
FOREIGN KEY (created_by) REFERENCES users(id)
```

---

### table:keyword_alert_articles
**Purpose**: Articles that triggered keyword alerts

**Primary Key**: `id` (Integer, auto-increment)

**Indexes**:
- `idx_url` on `url` (unique)
- `idx_submission_date` on `submission_date`

**Fields**:
```sql
id INTEGER PRIMARY KEY AUTOINCREMENT,
url TEXT UNIQUE NOT NULL,                -- Article URL
title TEXT,                              -- Article title
summary TEXT,                            -- Article summary
source TEXT,                             -- Article source
submission_date DATETIME DEFAULT CURRENT_TIMESTAMP,
topic TEXT,                              -- Associated topic
keywords TEXT,                           -- Matched keywords (JSON array)
analyzed BOOLEAN DEFAULT FALSE,          -- Analysis completion flag
moved_to_articles BOOLEAN DEFAULT FALSE, -- Moved to main articles table
FOREIGN KEY (topic) REFERENCES topics(name)
```

---

### table:analysis_versions_v2
**Purpose**: AI analysis results caching

**Primary Key**: `id` (Integer, auto-increment)

**Indexes**:
- `idx_cache_key` on `cache_key` (unique)
- `idx_accessed_at` on `accessed_at`
- `idx_topic_created` on `topic, created_at`

**Fields**:
```sql
id INTEGER PRIMARY KEY AUTOINCREMENT,
cache_key TEXT UNIQUE NOT NULL,          -- Unique cache identifier
topic TEXT NOT NULL,                     -- Analysis topic
version_data TEXT NOT NULL,              -- Analysis results (JSON)
cache_metadata TEXT,                     -- Cache metadata (JSON)
created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
model_used TEXT,                          -- AI model used
analysis_depth TEXT                       -- Analysis depth level
```

**Constraints**:
- `cache_key` must be unique
- `version_data` must be valid JSON

---

### table:article_annotations
**Purpose**: User annotations on articles

**Primary Key**: `id` (Integer, auto-increment)

**Indexes**:
- `idx_article_uri` on `article_uri`
- `idx_author` on `author`

**Fields**:
```sql
id INTEGER PRIMARY KEY AUTOINCREMENT,
article_uri TEXT NOT NULL,               -- Reference to article
author TEXT NOT NULL,                    -- Annotation author
content TEXT NOT NULL,                   -- Annotation content
is_private BOOLEAN DEFAULT FALSE,        -- Private annotation flag
created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
FOREIGN KEY (article_uri) REFERENCES articles(uri) ON DELETE CASCADE
```

**Constraints**:
- `article_uri` must reference valid article
- `content` cannot be empty

---

## Database Relationships

### Primary Relationships
```
users (1) ←→ (N) topics (created_by)
users (1) ←→ (N) keyword_alerts (user_id)
users (1) ←→ (N) auspex_chats (user_id)
users (1) ←→ (N) auspex_prompts (created_by)

topics (1) ←→ (N) articles (topic)
topics (1) ←→ (N) keyword_alerts (topic)
topics (1) ←→ (N) auspex_chats (topic)
topics (1) ←→ (N) keyword_alert_articles (topic)

auspex_chats (1) ←→ (N) auspex_messages (chat_id)
articles (1) ←→ (N) article_annotations (article_uri)
```

### Foreign Key Constraints
- All foreign keys use `ON DELETE CASCADE` where appropriate
- Users cannot be deleted if they own topics, chats, or prompts
- Topics cannot be deleted if they have articles or alerts
- Chat sessions cannot be deleted if they have messages

## Database Operations

### Connection Management
```python
# Get database instance
db = Database()
conn = db._temp_get_connection()  # SQLAlchemy connection
```

### Query Patterns
```python
# Select articles by topic
stmt = select(t_articles).where(t_articles.c.topic == topic_name)
result = conn.execute(stmt)
articles = [dict(row) for row in result]

# Insert new article
stmt = insert(t_articles).values(
    uri=article_uri,
    title=title,
    topic=topic_name,
    analyzed=False
)
conn.execute(stmt)

# Update article analysis
stmt = update(t_articles).where(
    t_articles.c.uri == uri
).values(
    analyzed=True,
    sentiment=sentiment_result,
    category=category_result
)
conn.execute(stmt)
```

### Migration System
- Migrations stored in `app/database/migrations/`
- Each migration is a SQL file with version number
- Run migrations with: `python run_migration.py`
- Migrations are idempotent (safe to run multiple times)

### Performance Optimizations
- WAL mode enabled for concurrent access
- Connection pooling with thread-local connections
- Proper indexing on frequently queried fields
- Batch operations for bulk inserts
- Prepared statements for repeated queries

## Data Validation

### Article Data
- `uri`: Must be valid URL format
- `title`: Maximum 500 characters
- `publication_date`: Must be ISO 8601 format
- `relevance_score`: Must be between 0.0 and 1.0
- `analyzed`: Boolean flag, defaults to FALSE

### User Data
- `username`: Alphanumeric, 3-50 characters
- `email`: Valid email format
- `hashed_password`: bcrypt hash format

### Topic Data
- `name`: URL-safe identifier, 3-100 characters
- `config_json`: Valid JSON structure
- `keywords`: JSON array of strings

## Backup and Recovery

### Backup Strategy
```bash
# Create backup
cp app/data/{instance}/fnaapp.db app/data/{instance}/backup_{timestamp}.db

# Restore from backup
cp app/data/{instance}/backup_{timestamp}.db app/data/{instance}/fnaapp.db
```

### Data Export
- Articles can be exported to CSV format
- User data export includes all user-generated content
- Topic configurations can be exported as JSON

## Security Considerations

### Data Protection
- Passwords stored as bcrypt hashes
- Sensitive data encrypted at rest
- Database files have restricted permissions (600)
- Regular security updates for SQLite

### Access Control
- Database connections use connection pooling
- All queries use parameterized statements
- Foreign key constraints enforce referential integrity
- User data isolation through proper foreign keys

## Monitoring and Maintenance

### Performance Monitoring
- Query execution time logging
- Connection pool usage tracking
- Index usage statistics
- Database file size monitoring

### Maintenance Tasks
- Regular VACUUM operations
- Index rebuilding when needed
- Log file rotation
- Backup verification

### Health Checks
- Database connectivity test
- Foreign key constraint verification
- Index integrity checks
- Data consistency validation
