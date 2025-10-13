# Dual Database Evidence - Critical Data Inconsistency

**Date**: 2025-10-13
**Status**: CONFIRMED - System Running in Dual-Database Mode

---

## Critical Findings

### Database Article Counts

| Database | Article Count | Difference |
|----------|---------------|------------|
| **PostgreSQL** (skunkworkx) | **32,617 articles** | +2,202 articles |
| **SQLite** (app/data/fnaapp.db) | **30,415 articles** | -2,202 articles |

**Conclusion**: PostgreSQL has 2,202 more articles than SQLite.

---

### Recent Articles Comparison

When querying for the 5 most recent articles:

**PostgreSQL (via `_temp_get_connection()`):**
```
1. None - Placeholder...
2. None - Placeholder Article...
3. None - Placeholder Article...
4. None - Placeholder Article...
5. None - Placeholder...
```

**SQLite (via `get_recent_articles()`):**
```
1. Figma partners with Google Cloud to expand AI-powe...
2. AI Now Has The Ability To Skirt Safeguards And Dev...
3. AI Creates Viruses That Kill Resistant Bacteria...
4. Perplexity AI Essentials...
5. EC Warns Parties Against AI Misuse in Bihar Polls...
```

**Result**: ✗ **0% overlap** - The 5 most recent articles in each database are completely different.

**Implication**: Users see different "recent articles" depending on which code path is used.

---

### Topics Comparison

**PostgreSQL Topics (6 topics):**
- AI and Machine Learning
- Climate Change
- Cloud repatriation
- Demographic Decline
- Right-wing Rise in Europe
- Tracking Mental health

**SQLite Topics (1 topic):**
- AI and Machine Learning

**Only in PostgreSQL**: 5 topics
- Cloud repatriation
- Tracking Mental health
- Demographic Decline
- Climate Change
- Right-wing Rise in Europe

**Result**: ✗ **Topics are completely out of sync**

**Implication**: The topic dropdown (which calls `get_topics()` → SQLite) shows only 1 topic, but PostgreSQL contains 6 topics. Users cannot filter articles by 5 of the 6 topics that actually exist in the database.

---

## What This Means

### User Experience Impact

#### Scenario 1: Dashboard View
1. User opens dashboard
2. Dashboard calls `get_recent_articles(limit=5)` → **Queries SQLite**
3. User sees: "Figma partners with Google Cloud...", "AI Now Has The Ability To Skirt Safeguards..."
4. User clicks on an article
5. Article details are loaded via migrated method → **Queries PostgreSQL**
6. Article might not exist in PostgreSQL, showing 404 error

#### Scenario 2: Topic Filtering
1. User wants to filter articles by topic
2. Topic dropdown calls `get_topics()` → **Queries SQLite**
3. Dropdown shows: "AI and Machine Learning" (only 1 topic)
4. User selects "AI and Machine Learning"
5. Article search calls migrated method → **Queries PostgreSQL**
6. PostgreSQL has 6 topics worth of articles, but user can't access 5 of them

#### Scenario 3: Article Search
1. User searches for recent articles via search interface
2. Search uses `facade.search_articles()` → **Queries PostgreSQL**
3. Returns articles from topics: "Climate Change", "Cloud repatriation", etc.
4. User tries to view recent articles via dashboard
5. Dashboard uses `get_recent_articles()` → **Queries SQLite**
6. Returns completely different set of articles
7. User is confused why search and dashboard show different data

---

## Code Path Analysis

### Path 1: Migrated Methods → PostgreSQL

**Example**: Article search in market signals dashboard
```python
# In templates/market_signals_dashboard.html or backend route
from app.database import Database
db = Database()

# This delegates to facade
articles = db.search_articles(query="AI", ...)

# Internally:
# → db.facade.search_articles()
# → Uses _temp_get_connection()
# → Queries PostgreSQL (32,617 articles)
```

### Path 2: Unmigrated Methods → SQLite

**Example**: Topic dropdown
```python
# In UI route for topic dropdown
from app.database import Database
db = Database()

# This uses get_connection() directly
topics = db.get_topics()

# Internally:
# → Uses get_connection()
# → Creates sqlite3.connect(app/data/fnaapp.db)
# → Queries SQLite (30,415 articles, 1 topic)
```

### Path 3: Direct Query → PostgreSQL

**Example**: Dashboard statistics
```python
# In analytics or dashboard route
from app.database import Database
db = Database()

conn = db._temp_get_connection()
result = conn.execute(text("SELECT COUNT(*) FROM articles"))
count = result.fetchone()[0]  # Returns 32,617
```

---

## Evidence of Dual Connection Pools

### Thread-Local Connection Storage

From `app/database.py`:

```python
class Database:
    def __init__(self):
        # SQLite connection pool (ALWAYS points to SQLite)
        self._connections: Dict[int, sqlite3.Connection] = {}

        # PostgreSQL connection pool (respects DB_TYPE)
        self._sqlalchemy_connections: Dict[int, sqlalchemy.engine.Connection] = {}
```

**Each thread maintains TWO separate connection pools:**

1. **`_connections`**: Dictionary of `thread_id → sqlite3.Connection`
   - Used by `get_connection()`
   - Always points to `app/data/fnaapp.db`
   - Ignores `DB_TYPE` environment variable

2. **`_sqlalchemy_connections`**: Dictionary of `thread_id → SQLAlchemy Connection`
   - Used by `_temp_get_connection()`
   - Respects `DB_TYPE` environment variable
   - Points to PostgreSQL when `DB_TYPE=postgresql`

**Result**: Every thread has connections open to **both databases simultaneously**.

---

## Database Logs Showing Dual Usage

From test run output:

```
2025-10-13 13:05:38,566 - app.database - INFO - Database initialized: /home/orochford/tenants/skunkworkx.aunoo.ai/app/data/fnaapp.db
2025-10-13 13:05:38,566 - app.database - INFO - Creating PostgreSQL connection: skunkworkx
2025-10-13 13:05:38,593 INFO sqlalchemy.engine.Engine select pg_catalog.version()
```

**Line 1**: SQLite database initialized (fnaapp.db)
**Line 2**: PostgreSQL connection created (skunkworkx)
**Line 3**: PostgreSQL version check query

**Both databases are initialized and connected in the same session.**

---

## Method-by-Method Database Routing

### Methods Querying PostgreSQL (40 methods)

**Via Facade Delegation (27 methods)**:
- `save_article()` → `facade.upsert_article()` → PostgreSQL
- `delete_article()` → `facade.delete_article_by_url()` → PostgreSQL
- `search_articles()` → `facade.search_articles()` → PostgreSQL
- All Auspex chat/message/prompt methods → PostgreSQL
- All feed management methods → PostgreSQL

**Direct PostgreSQL-Compatible (13 methods)**:
- `get_article()` → Uses `_temp_get_connection()` → PostgreSQL
- `fetch_one()` → Uses `_temp_get_connection()` → PostgreSQL
- `fetch_all()` → Uses `_temp_get_connection()` → PostgreSQL
- Async dashboard methods → PostgreSQL

### Methods Querying SQLite (41 methods)

**User Management (6 methods)**:
- `get_user()` → Uses `get_connection()` → SQLite
- `create_user()` → Uses `get_connection()` → SQLite
- `update_user_password()` → Uses `get_connection()` → SQLite

**Topic Management (7 methods)**:
- `get_topics()` → Uses `get_connection()` → SQLite ⚠️ **CRITICAL**
- `get_recent_articles_by_topic()` → Uses `get_connection()` → SQLite
- `delete_topic()` → Uses `get_connection()` → SQLite

**Article Operations (7 methods)**:
- `get_recent_articles()` → Uses `get_connection()` → SQLite ⚠️ **CRITICAL**
- `get_all_articles()` → Uses `get_connection()` → SQLite
- `get_articles_by_ids()` → Uses `get_connection()` → SQLite

**Configuration (9 methods)**:
- `get_config_item()` → Uses `get_connection()` → SQLite
- `get_newsletter_prompt()` → Uses `get_connection()` → SQLite
- `get_podcast_setting()` → Uses `get_connection()` → SQLite

**...and 12 more unmigrated methods**

---

## Data Consistency Risks

### Risk 1: Stale Dashboard Data

**Scenario**: New articles added via API
1. External system calls `/api/articles` POST endpoint
2. Backend uses `save_article()` → Saves to PostgreSQL
3. Article count in PostgreSQL: 32,618 (was 32,617)
4. User refreshes dashboard
5. Dashboard calls `get_recent_articles()` → Queries SQLite
6. SQLite still has 30,415 articles (unchanged)
7. User doesn't see the new article

### Risk 2: Orphaned Topics

**Scenario**: Topic created but not visible
1. Admin creates new topic "Quantum Computing" via UI
2. Backend might call `create_topic()` → Saves to SQLite
3. User tries to add articles to "Quantum Computing" topic
4. Articles saved via `save_article()` → PostgreSQL
5. Articles are tagged with topic="Quantum Computing"
6. User opens topic dropdown to filter
7. Dropdown calls `get_topics()` → Queries SQLite
8. "Quantum Computing" doesn't appear (it's only in PostgreSQL articles)
9. User can't filter by the topic they just created

### Risk 3: Authentication Confusion

**Scenario**: User created via different method
1. Admin uses OAuth to create user (might save to PostgreSQL)
2. User tries to log in via traditional login form
3. Login calls `get_user(username)` → Queries SQLite
4. User not found in SQLite
5. Login fails with "Invalid credentials"
6. User exists in database, but can't log in

### Risk 4: Data Loss on Migration

**Scenario**: SQLite database deleted prematurely
1. Developer sees "DB_TYPE=postgresql" in .env
2. Assumes migration is complete
3. Deletes or archives SQLite database file
4. Application starts failing on:
   - Topic dropdown (calls `get_topics()` → SQLite)
   - Recent articles dashboard (calls `get_recent_articles()` → SQLite)
   - Newsletter prompts (calls `get_newsletter_prompt()` → SQLite)
5. Users report: "Dashboard is blank", "Topics disappeared", etc.

---

## How This Went Undetected

### 1. No Immediate Errors

Both databases exist and contain data. Methods succeed, returning results from their respective databases. No exceptions are thrown.

### 2. Partial Migration Working Well

The most critical user-facing features (article search, save, delete) were migrated first and work correctly. This created a false sense of completion.

### 3. Low Traffic on Edge Features

Features like:
- Newsletter prompt management
- Podcast settings configuration
- Database admin operations

These are rarely used, so inconsistencies weren't noticed in normal operations.

### 4. Dashboard Appears to Work

The dashboard shows articles (from SQLite), so it "works" from a user perspective. They don't realize they're seeing stale data unless they specifically check for recently added articles.

### 5. Topic Filtering Still Functions

The topic dropdown shows 1 topic ("AI and Machine Learning"), and filtering by that topic returns results. Users don't know that 5 other topics exist in PostgreSQL that aren't visible.

---

## Recommended Immediate Actions

### 1. Verify Which Database Is Source of Truth

**Decision Required**: Which database contains the authoritative data?

**Option A**: PostgreSQL is source of truth (32,617 articles)
- SQLite data (30,415 articles) is outdated
- Action: Complete migration, then archive SQLite

**Option B**: SQLite is source of truth (30,415 articles)
- PostgreSQL data (32,617 articles) includes test/duplicate data
- Action: Re-sync PostgreSQL from SQLite, then complete migration

**Option C**: Both contain important data
- 2,202 articles in PostgreSQL not in SQLite are important
- 30,415 articles in SQLite must be preserved
- Action: Merge databases, resolve conflicts, then complete migration

### 2. Test Critical User Flows

**Test each workflow end-to-end**:

✓ **Article Submission**:
```python
# Add article via API
POST /api/articles → save_article() → PostgreSQL

# Verify it appears in dashboard
GET /dashboard → get_recent_articles() → SQLite (might not appear!)
```

✓ **Topic Management**:
```python
# Create topic
POST /api/topics → create_topic() → SQLite (?)

# Add article with topic
POST /api/articles {"topic": "new_topic"} → PostgreSQL

# View topic dropdown
GET /api/topics → get_topics() → SQLite (might not show!)
```

✓ **User Authentication**:
```python
# Create user via OAuth
oauth_callback → PostgreSQL (?)

# Try traditional login
POST /login → get_user() → SQLite (might fail!)
```

### 3. Run Data Consistency Check

```bash
# Run comparison script
.venv/bin/python3 /tmp/compare_databases.py

# Expected output:
# - Article count difference: 2,202
# - Topic count difference: 5 topics
# - Recent articles: 0% overlap
```

### 4. Document Current System State

**Create inventory of**:
- Which features use PostgreSQL (migrated methods)
- Which features use SQLite (unmigrated methods)
- Which features are actively used in production
- Which features can tolerate stale data temporarily

---

## Migration Priority Matrix

### 🔴 CRITICAL - Must Fix Immediately

**Topic Management (7 methods)**:
- `get_topics()` - Used by UI dropdown
- `create_topic()` - Used by admin
- `delete_topic()` - Used by admin

**Impact**: Topic filtering completely broken for 5 out of 6 topics.

**Estimated Effort**: 6-8 hours

### 🟠 HIGH - Fix This Week

**Article Operations (7 methods)**:
- `get_recent_articles()` - Used by dashboard
- `get_all_articles()` - Used by bulk operations

**Impact**: Dashboard shows stale data, missing 2,202 recent articles.

**Estimated Effort**: 8-10 hours

**User Management (6 methods)**:
- `get_user()` - Used by login
- `create_user()` - Used by registration

**Impact**: If OAuth fails, traditional login broken.

**Estimated Effort**: 4-6 hours

### 🟡 MEDIUM - Fix Next Sprint

**Configuration Methods (9 methods)**:
- Newsletter prompts
- Podcast settings
- Config items

**Impact**: Features may not persist settings correctly.

**Estimated Effort**: 6-8 hours

### 🟢 LOW - Fix As Needed

**Database Admin Methods (7 methods)**:
- Database info
- Create/switch database
- Schema operations

**Impact**: Admin tools don't work, but rarely used.

**Estimated Effort**: 4-6 hours

---

## Success Criteria

Migration is complete when:

✅ All 41 unmigrated methods use `_temp_get_connection()`
✅ Article counts match between PostgreSQL and test queries
✅ Topic dropdown shows all 6 topics
✅ Dashboard shows same recent articles as direct PostgreSQL query
✅ No methods call `self.get_connection()` except SQLite-specific utilities
✅ Full regression test suite passes with DB_TYPE=postgresql
✅ SQLite database can be archived without breaking functionality

---

## Test Commands

### Quick Verification

```bash
# Check if running dual-database
.venv/bin/python3 /tmp/test_dual_database.py

# Compare databases
.venv/bin/python3 /tmp/compare_databases.py

# Check article counts
echo "PostgreSQL:"
PGPASSWORD=WXF7o+XgkHfYYBIbLJuvfFg4psMFCNoP psql -U skunkworkx_user -d skunkworkx -h localhost -c "SELECT COUNT(*) FROM articles;"

echo "SQLite:"
sqlite3 app/data/fnaapp.db "SELECT COUNT(*) FROM articles;"
```

---

## Conclusion

The system is **definitively running in dual-database mode**. This is not a theoretical issue - the evidence shows:

- **2,202 article difference** between databases
- **0% overlap** in recent articles
- **5 missing topics** in SQLite (83% of topics invisible)
- **41 unmigrated methods** actively querying SQLite
- **Active connection pools** to both databases simultaneously

**Recommendation**: Prioritize completing the migration of all 41 unmigrated methods within the next sprint. Focus on Topic Management (7 methods) and Article Operations (7 methods) first, as these have the highest user-facing impact.

---

**Document Version**: 1.0
**Last Updated**: 2025-10-13
**Test Results**: CONFIRMED via `/tmp/compare_databases.py`
**Related Documents**:
- `COMPLETE_MIGRATION_AUDIT.md` - Full method analysis
- `WHY_SYSTEM_WORKS_DESPITE_INCOMPLETE_MIGRATION.md` - Technical explanation
- `DUAL_DATABASE_AUDIT.md` - Initial findings
