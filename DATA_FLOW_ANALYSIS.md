# Data Flow Analysis: Write Paths and Dual-Database Usage

**Date**: 2025-10-13
**Analysis**: Where does the application save data and is it always dual-reading/writing?

---

## Question 1: Where Do Templates Save Data?

### `templates/submit_article.html`

**JavaScript Save Functions**:
```javascript
// Line 760 - Single article save
async function saveAnalyzedArticle() {
    const saveResponse = await fetch('/api/save_article', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(articleData)
    });
}

// Line 1534 - Bulk article save
const response = await fetch('/api/save-bulk-articles', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ articles })
});
```

**Backend Handler** (`app/main.py:924`):
```python
@app.post("/api/save_article")
async def save_article(article: ArticleData):
    result = db.save_article(article.dict())
    return JSONResponse(content=result)
```

**Database Method** (`app/database.py:854`):
```python
def save_article(self, article_data):
    """Save article to database.
    Uses SQLAlchemy facade for PostgreSQL compatibility.
    """
    return self.facade.upsert_article(article_data)
```

**✅ Result**: `submit_article.html` saves to **PostgreSQL ONLY** (via migrated facade method)

---

### `templates/news_feed.html`

**No Direct Save Operations**: This template doesn't have article save functionality. It:
- Loads articles from database (read-only)
- Generates insights/analysis
- Creates podcasts
- Exports data

**Database Reads** (various API endpoints):
```javascript
// Line 1878+ - Fetches articles via API
fetch('/api/articles?topic=' + topic)
fetch('/api/topics')
```

These endpoints use **mixed database calls** (some migrated, some unmigrated).

**✅ Result**: `news_feed.html` does **NOT write article data**, only reads

---

## Question 2: Topic Management

### Topic Storage: Dual Location System

**Location 1: Database (Articles Table)**
- Topics are stored as a column in the `articles` table
- Each article has a `topic` field
- Topics discovered via `SELECT DISTINCT topic FROM articles`

**Location 2: Config File (`app/data/config.json`)**
```json
{
    "active_database": "fnaapp.db"
}
```

**⚠️ Observation**: The config.json does **NOT** store topics, only the active database name. Topics come entirely from the articles table.

### Topic API Endpoint (`app/main.py:1258`)

```python
@app.get("/api/topics")
async def get_topics(session=Depends(verify_session)):
    topics = db.get_topics()
    return JSONResponse(content=topics)
```

### Topic Database Method (`app/database.py:1718`) - **UNMIGRATED**

```python
def get_topics(self):
    with self.get_connection() as conn:  # ❌ SQLite-only
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT topic FROM articles ORDER BY topic")
        return [{"id": row['topic'], "name": row['topic']} for row in cursor.fetchall()]
```

**❌ Result**: Topic dropdown queries **SQLite ONLY** (unmigrated method)

---

## Question 3: Newsletter & Podcast Usage

### Newsletter Generator: **NOT USED**

**Evidence**:
```python
# app/main.py:94 - Comment confirms removal
# Newsletter routers - REMOVED

# app/main.py:68 - Import commented out
# Removed newsletter routes - no longer needed
```

**Confirmation**: Newsletter functionality has been **completely removed** from the application.

---

### Podcast Generation: **PARTIALLY USED**

**Used in `news_feed.html`**:
- Line 937-962: Podcast settings UI (voice, length)
- Line 982: "Generate Podcast" export option
- References to `/api/generate-podcast` endpoint

**Backend Podcast Routes** (`app/main.py:75`):
```python
# ElevenLabs SDK imports used in podcast endpoints
from elevenlabs import ElevenLabs, PodcastConversationModeData
```

**Podcast Routes** (`app/routes/podcast_routes.py`):
```python
from app.routes.podcast_routes import router as podcast_router
```

**✅ Result**: Podcast generation is **actively used** in `news_feed.html`, but only a subset of the full podcast functionality

---

## Question 4: Always Dual Reading/Writing?

### Write Operations: **NO DUAL WRITING**

**Article Saves (Primary Write Operation)**:

```python
# app/database.py:854 - save_article()
def save_article(self, article_data):
    return self.facade.upsert_article(article_data)
    # ✅ Writes to PostgreSQL ONLY
```

**Article Deletes**:
```python
# app/database.py:867 - delete_article()
def delete_article(self, uri):
    return self.facade.delete_article_by_url(uri)
    # ✅ Deletes from PostgreSQL ONLY
```

**Result**: **No dual writing** for article data. All writes go to PostgreSQL through migrated facade methods.

---

### Read Operations: **YES, DUAL READING**

Different features read from different databases depending on which methods they call:

#### PostgreSQL Reads (Migrated Methods)

**1. Article Search** (`submit_article.html`, `news_feed.html`):
```python
# app/database.py - search_articles()
def search_articles(self, ...):
    return self.facade.search_articles(...)  # ✅ PostgreSQL
```

**2. Article Retrieval**:
```python
# app/database.py:831 - get_article()
def get_article(self, uri):
    conn = self._temp_get_connection()  # ✅ PostgreSQL
    result = conn.execute(...).mappings()
```

**3. Article Save/Delete**:
```python
# All save/delete operations → facade → PostgreSQL
```

#### SQLite Reads (Unmigrated Methods)

**1. Topic Dropdown** (ALL templates with topic selector):
```python
# app/database.py:1718 - get_topics()
def get_topics(self):
    with self.get_connection() as conn:  # ❌ SQLite
        cursor.execute("SELECT DISTINCT topic FROM articles ORDER BY topic")
```

**Templates Affected**:
- `submit_article.html` (line 282: topic dropdown)
- `news_feed.html` (line 730: topic dropdown)
- All other templates with topic filters

**2. Recent Articles Dashboard**:
```python
# app/database.py:749 - get_recent_articles()
def get_recent_articles(self, limit: int = 10):
    with self.get_connection() as conn:  # ❌ SQLite
        cursor.execute("SELECT * FROM articles ORDER BY published DESC LIMIT ?")
```

**3. Configuration & Settings**:
```python
# app/database.py:736 - get_config_item()
def get_config_item(self, name):
    with self.get_connection() as conn:  # ❌ SQLite
```

---

## Dual Reading Impact Analysis

### Critical Data Flow Scenario

**User Workflow: Submit Article → View in Dashboard**

1. **User submits article** (`submit_article.html`):
   - Calls `/api/save_article`
   - Executes `db.save_article()` → `facade.upsert_article()`
   - **Writes to PostgreSQL** (32,617 articles)
   - Article now exists in PostgreSQL with topic = "AI and Machine Learning"

2. **User opens topic dropdown** (same template):
   - JavaScript calls `/api/topics`
   - Executes `db.get_topics()` → **Queries SQLite** (30,415 articles)
   - **Returns 1 topic**: "AI and Machine Learning"
   - **Missing 5 topics** that exist in PostgreSQL

3. **User selects topic and searches**:
   - Calls `/api/articles?topic=AI...`
   - Executes `db.search_articles()` → `facade.search_articles()`
   - **Queries PostgreSQL** (32,617 articles)
   - **Returns article just saved** (found in PostgreSQL)

4. **User views "Recent Articles" dashboard**:
   - Calls an endpoint using `db.get_recent_articles()`
   - **Queries SQLite** (30,415 articles)
   - **Article NOT shown** (doesn't exist in SQLite)

### Result: Inconsistent User Experience

- **Topic dropdown**: Shows 1 topic (from SQLite)
- **Search results**: Returns articles from 6 topics (from PostgreSQL)
- **Recent dashboard**: Shows old articles (from SQLite, missing 2,202 newest)
- **User confusion**: "I just saved an article, why don't I see it in Recent?"

---

## Read Operations Summary Table

| Operation | Method | Database | Migrated? | Used In |
|-----------|--------|----------|-----------|---------|
| Save Article | `save_article()` | **PostgreSQL** | ✅ Yes | submit_article.html |
| Delete Article | `delete_article()` | **PostgreSQL** | ✅ Yes | All templates |
| Search Articles | `search_articles()` | **PostgreSQL** | ✅ Yes | news_feed.html, submit_article.html |
| Get Article | `get_article()` | **PostgreSQL** | ✅ Yes | Article detail views |
| **Get Topics** | `get_topics()` | **SQLite** | ❌ No | ALL templates with topic dropdown |
| **Recent Articles** | `get_recent_articles()` | **SQLite** | ❌ No | Dashboard views |
| **All Articles** | `get_all_articles()` | **SQLite** | ❌ No | Bulk operations |
| **Config Items** | `get_config_item()` | **SQLite** | ❌ No | Settings pages |

---

## Key Findings

### 1. Article Writes: PostgreSQL ONLY ✅

All article creation/update/delete operations go through migrated facade methods:
- `save_article()` → `facade.upsert_article()` → PostgreSQL
- `delete_article()` → `facade.delete_article_by_url()` → PostgreSQL

**No dual writing occurs.**

---

### 2. Article Reads: MIXED (Dual Reading) ⚠️

Depending on which feature is used:
- **Search/Fetch** → PostgreSQL (migrated)
- **Topic Dropdown** → SQLite (unmigrated)
- **Recent Dashboard** → SQLite (unmigrated)
- **Config/Settings** → SQLite (unmigrated)

**Dual reading causes data inconsistency.**

---

### 3. Topic Management: Database-Driven ⚠️

Topics are **NOT stored in config.json**. They come from:
```sql
SELECT DISTINCT topic FROM articles
```

**Problem**: This query runs against **SQLite** (unmigrated method), so:
- PostgreSQL has 6 topics
- SQLite has 1 topic
- Users see only 1 topic in dropdown (83% missing)

---

### 4. Newsletter: Removed ✅

Newsletter functionality has been **completely removed** from the codebase. No newsletter routes, templates, or API endpoints remain active.

---

### 5. Podcast: Partially Used ✅

Podcast generation is **actively used** in `news_feed.html`:
- Voice selection
- Length configuration
- Export to podcast via ElevenLabs API
- Limited to "Six Articles" podcast feature

Full podcast director functionality appears unused.

---

## Recommended Immediate Actions

### 1. Migrate `get_topics()` Method - CRITICAL

**Current Code** (`app/database.py:1718`):
```python
def get_topics(self):
    with self.get_connection() as conn:  # ❌ SQLite
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT topic FROM articles ORDER BY topic")
        return [{"id": row['topic'], "name": row['topic']} for row in cursor.fetchall()]
```

**Migrated Code**:
```python
def get_topics(self):
    """Get distinct topics from articles table.
    Uses PostgreSQL-compatible connection.
    """
    from sqlalchemy import text
    from app.database_models import t_articles

    conn = self._temp_get_connection()  # ✅ PostgreSQL-compatible
    try:
        stmt = text("SELECT DISTINCT topic FROM articles WHERE topic IS NOT NULL ORDER BY topic")
        result = conn.execute(stmt).fetchall()
        return [{"id": row[0], "name": row[0]} for row in result]
    except Exception as e:
        logger.error(f"Error in get_topics: {e}")
        raise
```

**Impact**: This single change will fix topic dropdowns across **ALL templates**.

---

### 2. Migrate `get_recent_articles()` Method - HIGH PRIORITY

**Current Code** (`app/database.py:749`):
```python
def get_recent_articles(self, limit: int = 10):
    with self.get_connection() as conn:  # ❌ SQLite
        cursor.execute(...)
```

**Migrated Code**:
```python
def get_recent_articles(self, limit: int = 10):
    """Get recent articles from database.
    Uses PostgreSQL-compatible connection.
    """
    from sqlalchemy import select
    from app.database_models import t_articles

    conn = self._temp_get_connection()  # ✅ PostgreSQL-compatible
    try:
        stmt = select(t_articles).order_by(t_articles.c.publication_date.desc()).limit(limit)
        result = conn.execute(stmt).mappings()
        return [dict(row) for row in result]
    except Exception as e:
        logger.error(f"Error in get_recent_articles: {e}")
        raise
```

**Impact**: Dashboard "Recent Articles" will show current data from PostgreSQL.

---

### 3. Document Newsletter Removal

Add to documentation:
```markdown
## Removed Features

### Newsletter Generator (Removed 2025-10-XX)
The newsletter generation feature has been removed from the application.
- Removed routes: `/newsletter/*`
- Removed templates: `newsletter_*.html`
- Removed API endpoints: `/api/newsletter/*`

If newsletter functionality is needed, it must be re-implemented.
```

---

### 4. Document Podcast Scope

Add to documentation:
```markdown
## Podcast Generation

### Active Features
- "Six Articles" podcast generation (via news_feed.html)
- ElevenLabs integration
- Voice selection and length configuration

### Unused Features
- Podcast Director (full interface)
- Podcast episode management
- Podcast library

Current implementation focuses on one-off podcast generation from article summaries.
```

---

## Testing Checklist

### Verify Write Paths (Should Already Work)
```bash
# Test 1: Save article via submit_article.html
# - Submit URL
# - Verify article saved to PostgreSQL
PGPASSWORD=WXF7o+XgkHfYYBIbLJuvfFg4psMFCNoP psql -U skunkworkx_user -d skunkworkx -h localhost -c "SELECT uri FROM articles ORDER BY submission_date DESC LIMIT 1;"

# Test 2: Delete article
# - Delete via UI
# - Verify deleted from PostgreSQL
```

### Verify Read Inconsistencies (Will Show Problems)
```bash
# Test 3: Topic dropdown vs search results
# - Open submit_article.html
# - Count topics in dropdown (will show 1)
# - Search for articles (will return 6 topics worth)
# - Document discrepancy

# Test 4: Recent articles dashboard
# - Save new article via submit_article.html
# - Check "Recent Articles" panel
# - Article will NOT appear (it's in PostgreSQL, panel reads SQLite)
```

### After Migration (Verify Fixes)
```bash
# Test 5: After migrating get_topics()
# - Open topic dropdown
# - Should show all 6 topics from PostgreSQL

# Test 6: After migrating get_recent_articles()
# - Save new article
# - Check "Recent Articles" panel
# - Should immediately show newly saved article
```

---

## Conclusion

### Direct Answers to Your Questions

**Q1: Where do templates save data?**
- `submit_article.html`: Saves to **PostgreSQL ONLY** (via migrated `facade.upsert_article()`)
- `news_feed.html`: Does **NOT save article data**, only reads

**Q2: Topic management?**
- Topics stored in **database articles table** (NOT in config.json)
- Config.json only stores `active_database` setting
- `get_topics()` queries **SQLite** (unmigrated), causing inconsistency

**Q3: Newsletter and podcast usage?**
- **Newsletter**: Completely removed from codebase
- **Podcast**: Partially used (only "Six Articles" feature in news_feed.html)

**Q4: Always dual reading/writing?**
- **Writing**: **NO** - All writes go to PostgreSQL only (migrated)
- **Reading**: **YES** - Mixed reads from both databases depending on method:
  - Search/fetch → PostgreSQL
  - Topics/recent/config → SQLite
  - **Result**: Users see inconsistent data

---

**Priority Fix**: Migrate `get_topics()` method immediately. This single change fixes the most visible user-facing inconsistency (topic dropdown showing 1 topic when 6 exist).

---

**Document Version**: 1.0
**Last Updated**: 2025-10-13
**Related Documents**:
- `COMPLETE_MIGRATION_AUDIT.md` - Full list of unmigrated methods
- `DUAL_DATABASE_EVIDENCE.md` - Proof of dual-database operation
- `WHY_SYSTEM_WORKS_DESPITE_INCOMPLETE_MIGRATION.md` - Technical explanation
