# Dual Database Usage Audit - SQLite & PostgreSQL

**Date**: 2025-10-13
**Issue**: Not all components have been migrated from SQLite to PostgreSQL, resulting in parallel database usage.

## Executive Summary

The codebase is currently using **both SQLite and PostgreSQL in parallel** across multiple subsystems. This creates data inconsistency risks, maintenance complexity, and potential synchronization issues.

### Critical Areas Identified

## 1. ✅ ChromaDB Vector Store (SEPARATE - OK)
**Location**: `app/vector_store.py`
**Status**: ✅ **Intentionally Separate** (This is correct)
- **Database**: Separate SQLite database (`chromadb/chroma.sqlite3`)
- **Purpose**: Stores embeddings for semantic search
- **Why Separate**: ChromaDB manages its own persistence layer
- **Action Required**: None - this is by design
- **Note**: ChromaDB must stay synchronized with PostgreSQL articles via `scripts/reindex_chromadb.py`

---

## 2. ⚠️ User Authentication System
**Location**: `app/security/oauth_users.py`, `app/database.py`
**Status**: ⚠️ **NEEDS REVIEW** - Likely using mixed databases

### Issues Found:
```python
# app/security/oauth_users.py line 57
conn.commit()  # Direct connection commit without .mappings()
```

### Tables Affected:
- `oauth_users` - OAuth user accounts
- `oauth_allowlist` - OAuth email allowlist
- `users` - Traditional user accounts (if still in use)

### Evidence of Mixed Usage:
1. `oauth_users.py` imports from `app.database.Database` which checks `DB_TYPE` environment variable
2. The code doesn't explicitly use `.mappings()` pattern for PostgreSQL compatibility in line 57
3. OAuth tables may not be properly migrated

### Required Actions:
- [ ] Verify OAuth tables exist in PostgreSQL schema
- [ ] Audit all OAuth user management queries for PostgreSQL compatibility
- [ ] Check if traditional `users` table is still in SQLite or migrated
- [ ] Review session management for database consistency

---

## 3. ⚠️ Session Management
**Location**: `app/security/session.py` (not read in detail)
**Status**: ⚠️ **NEEDS AUDIT**

### Concerns:
- Sessions may be stored in SQLite while other data is in PostgreSQL
- Session verification might query wrong database
- No clear evidence if sessions are database-backed or in-memory

### Required Actions:
- [ ] Determine session storage mechanism (database vs. in-memory)
- [ ] If database-backed, verify which database is used
- [ ] Ensure session data consistency with user authentication system

---

## 4. ⚠️ Keyword Monitoring System
**Location**: `app/routes/keyword_monitor.py`
**Status**: ⚠️ **MIXED USAGE DETECTED**

### Evidence:
```python
# Multiple try-except blocks catching sqlite3.OperationalError
except sqlite3.OperationalError as e:
```

### Issues:
- Catching `sqlite3.OperationalError` suggests SQLite-specific error handling
- No corresponding PostgreSQL error handling
- Keyword monitoring tables may be SQLite-only

### Tables Affected:
- `keyword_groups`
- `keyword_article_matches`
- `keyword_alerts`

### Required Actions:
- [ ] Check if keyword tables exist in PostgreSQL
- [ ] Update error handling to be database-agnostic
- [ ] Migrate keyword monitoring data if needed
- [ ] Test keyword monitoring with PostgreSQL

---

## 5. ⚠️ Health Check Routes
**Location**: `app/routes/health_routes.py`
**Status**: ⚠️ **SQLITE-SPECIFIC CODE**

### Evidence:
```python
# Line reference to sqlite_master
SELECT name FROM sqlite_master WHERE type='table'
```

### Issues:
- Hardcoded SQLite system table queries
- Health checks won't work correctly with PostgreSQL
- No PostgreSQL equivalent implemented

### Required Actions:
- [ ] Implement database-agnostic health checks
- [ ] Use `information_schema` for PostgreSQL
- [ ] Update health check logic to detect DB_TYPE

---

## 6. ⚠️ Database Management Utilities
**Locations**:
- `app/utils/create_new_db.py` - SQLite only
- `app/utils/db_manager.py` - SQLite only
- `app/utils/inspect_db.py` - SQLite only
- `app/utils/update_admin.py` - SQLite only

**Status**: ⚠️ **SQLITE-ONLY UTILITIES**

### Issues:
- All database management utilities are SQLite-specific
- Direct `sqlite3.connect()` calls throughout
- No PostgreSQL equivalents for database initialization/inspection

### Required Actions:
- [ ] Create PostgreSQL-compatible versions of utilities
- [ ] Update `create_new_db.py` for PostgreSQL schema creation
- [ ] Implement PostgreSQL-compatible database inspection
- [ ] Update admin user management for PostgreSQL

---

## 7. ⚠️ Media Bias Model
**Location**: `app/models/media_bias.py`
**Status**: ⚠️ **NEEDS REVIEW**

### Evidence:
```python
import sqlite3
```

### Required Actions:
- [ ] Review media_bias.py for direct SQLite usage
- [ ] Verify media bias data is in PostgreSQL
- [ ] Update any direct database calls

---

## 8. ⚠️ Database Routes
**Location**: `app/routes/database.py`
**Status**: ⚠️ **PARTIAL MIGRATION**

### Evidence:
```python
import sqlite3
# ...
if db_type == 'postgresql':
    # PostgreSQL-specific logic
else:
    # SQLite-specific logic (original code)
```

### Issues:
- Has dual-path logic for both databases
- Some routes may default to SQLite
- Database download endpoint serves SQLite file
- Re-index endpoint uses SQLite system tables

### Required Actions:
- [ ] Audit all database routes for correct DB_TYPE handling
- [ ] Update database download to support PostgreSQL dumps
- [ ] Fix re-index logic to work with PostgreSQL

---

## 9. ✅ Main Database Class (PROPERLY CONFIGURED)
**Location**: `app/database.py`
**Status**: ✅ **CORRECTLY HANDLES BOTH**

### Implementation:
```python
self.db_type = os.getenv('DB_TYPE', 'sqlite').lower()

if db_type == 'postgresql':
    # Use PostgreSQL connection
    database_url = db_settings.get_sync_database_url()
    engine = create_engine(database_url, ...)
else:
    # Use SQLite
    engine = create_engine(f"sqlite:///{self.db_path}", ...)
```

### Status:
- ✅ Properly checks `DB_TYPE` environment variable
- ✅ Uses appropriate connection strings
- ✅ Implements database-agnostic query facade

---

## 10. ⚠️ Analytics and Market Signals
**Location**: `templates/market_signals_dashboard.html`, `app/routes/executive_summary_routes.py`
**Status**: ⚠️ **REPORTED BY USER AS MIXED**

### Issues Reported:
- Market signals dashboard using both SQLite and PostgreSQL
- Inconsistent data retrieval

### Evidence from Code:
```python
# app/routes/executive_summary_routes.py
from app.database import Database
db = Database()  # Uses DB_TYPE from environment
```

### Potential Issues:
- If DB_TYPE is not set correctly, defaults to SQLite
- Analytics queries may not be using `.mappings()` pattern
- ChromaDB sync may be out of date

### Required Actions:
- [ ] Verify DB_TYPE environment variable is set
- [ ] Check all analytics queries use `.mappings()`
- [ ] Run ChromaDB reindex if needed
- [ ] Test market signals with PostgreSQL data

---

## Environment Variables Review

### Critical Environment Variables:
```bash
DB_TYPE=postgresql              # Main database type selector
DB_HOST=localhost               # PostgreSQL host
DB_PORT=5432                    # PostgreSQL port
DB_USER=skunkworkx_user         # PostgreSQL user
DB_PASSWORD=<password>          # PostgreSQL password
DB_NAME=skunkworkx              # PostgreSQL database name

# Connection Pool Settings
DB_POOL_SIZE=15                 # Max concurrent connections
DB_MAX_OVERFLOW=10              # Additional connections
DB_POOL_TIMEOUT=30              # Connection timeout (seconds)
DB_POOL_RECYCLE=3600            # Recycle connections (seconds)

# ChromaDB (separate)
CHROMA_DB_DIR=chromadb          # ChromaDB directory
```

### Verification Commands:
```bash
# Check if DB_TYPE is set
echo $DB_TYPE

# Verify PostgreSQL connection
PGPASSWORD=$DB_PASSWORD psql -U $DB_USER -d $DB_NAME -h $DB_HOST -c "SELECT COUNT(*) FROM articles;"

# Check ChromaDB sync status
python scripts/reindex_chromadb.py --limit 10
```

---

## Migration Status by Table

| Table Name | PostgreSQL | SQLite | Status | Notes |
|------------|-----------|--------|--------|-------|
| articles | ✅ | ❌ | Migrated | Main articles table |
| topics | ✅ | ❌ | Migrated | Topic configuration |
| mediabias | ✅ | ❌ | Migrated | Media bias data |
| keyword_groups | ❓ | ❓ | Unknown | Needs verification |
| keyword_article_matches | ❓ | ❓ | Unknown | Needs verification |
| oauth_users | ❓ | ❓ | Unknown | Needs verification |
| oauth_allowlist | ❓ | ❓ | Unknown | Needs verification |
| users (traditional) | ❓ | ❓ | Unknown | May be deprecated |
| sessions | ❓ | ❓ | Unknown | Storage mechanism unclear |
| feed_groups | ✅ | ❌ | Migrated | Feed system |
| organizational_profiles | ✅ | ❌ | Migrated | Org profiles |

---

## Recommended Action Plan

### Phase 1: Assessment (Immediate)
1. ✅ Document all dual-database usage locations (this document)
2. [ ] Run database connection tests with DB_TYPE=postgresql
3. [ ] Verify all critical tables exist in PostgreSQL
4. [ ] Check data counts match between databases (if both contain data)

### Phase 2: Authentication System (High Priority)
1. [ ] Audit OAuth user management code
2. [ ] Verify OAuth tables in PostgreSQL schema
3. [ ] Test OAuth login flow with PostgreSQL
4. [ ] Migrate any SQLite-only OAuth data
5. [ ] Update error handling for PostgreSQL

### Phase 3: Keyword Monitoring (Medium Priority)
1. [ ] Check if keyword tables exist in PostgreSQL
2. [ ] Migrate keyword monitoring data if needed
3. [ ] Update error handling in keyword_monitor.py
4. [ ] Test keyword monitoring functionality

### Phase 4: Utilities & Admin Tools (Medium Priority)
1. [ ] Create PostgreSQL versions of database utilities
2. [ ] Update admin user management tools
3. [ ] Implement PostgreSQL-compatible health checks
4. [ ] Update database inspection tools

### Phase 5: Data Consistency (High Priority)
1. [ ] Run ChromaDB reindex to sync with PostgreSQL
2. [ ] Verify market signals dashboard uses PostgreSQL
3. [ ] Test all analytics endpoints
4. [ ] Check data consistency across all tables

### Phase 6: Cleanup (Low Priority)
1. [ ] Remove SQLite-specific code where PostgreSQL is primary
2. [ ] Update error handling to be database-agnostic
3. [ ] Document remaining SQLite usage (if any)
4. [ ] Create migration rollback procedures

---

## Testing Checklist

### Database Connection Tests
```bash
# Test PostgreSQL connection
python -c "from app.database import Database; db = Database(); print('Connected')"

# Test article retrieval
python -c "from app.database import Database; db = Database(); articles = db.facade.get_recent_articles(limit=10); print(f'Found {len(articles)} articles')"

# Test OAuth user retrieval
python -c "from app.security.oauth_users import OAuthUserManager; from app.database import Database; mgr = OAuthUserManager(Database()); print('OAuth manager initialized')"
```

### Data Count Verification
```bash
# Articles count
PGPASSWORD=<pwd> psql -U skunkworkx_user -d skunkworkx -h localhost -c "SELECT COUNT(*) as total FROM articles;"

# Topics count
PGPASSWORD=<pwd> psql -U skunkworkx_user -d skunkworkx -h localhost -c "SELECT COUNT(*) as total FROM topics;"

# OAuth users count
PGPASSWORD=<pwd> psql -U skunkworkx_user -d skunkworkx -h localhost -c "SELECT COUNT(*) as total FROM oauth_users;"

# ChromaDB count
python check_chromadb_count.py
```

### Functional Tests
- [ ] Login via OAuth (Google/Microsoft)
- [ ] Create keyword monitoring group
- [ ] Trigger keyword alert
- [ ] View market signals dashboard
- [ ] Run analytics queries
- [ ] Test semantic search (ChromaDB)
- [ ] Check health endpoint

---

## Risk Assessment

### High Risk Areas:
1. **User Authentication** - Users may not be able to log in if OAuth data is in wrong database
2. **Data Inconsistency** - Articles in PostgreSQL but analytics querying SQLite
3. **Session Management** - Sessions may not persist correctly

### Medium Risk Areas:
1. **Keyword Monitoring** - May silently fail if tables don't exist
2. **Health Checks** - May report incorrect status
3. **Admin Tools** - May create/modify data in wrong database

### Low Risk Areas:
1. **ChromaDB Sync** - Can be re-indexed without data loss
2. **Database Utilities** - Only used in development/maintenance

---

## Files Requiring Immediate Attention

### Critical (Fix First):
1. `app/security/oauth_users.py` - Line 57 missing `.mappings()`
2. `app/routes/keyword_monitor.py` - SQLite error handling
3. `app/routes/health_routes.py` - SQLite system table queries
4. Environment variable verification on production server

### Important (Fix Soon):
1. `app/utils/create_new_db.py` - PostgreSQL version needed
2. `app/utils/update_admin.py` - PostgreSQL support
3. `app/routes/database.py` - Audit dual-path logic
4. `app/models/media_bias.py` - Review SQLite import

### Lower Priority (Fix Eventually):
1. `app/utils/inspect_db.py` - PostgreSQL inspection
2. `app/utils/db_manager.py` - PostgreSQL version
3. Database download endpoint updates

---

## PostgreSQL Query Patterns to Follow

### ✅ Correct Pattern:
```python
from app.database import Database
db = Database()
conn = db._temp_get_connection()

# ALWAYS use .mappings() for PostgreSQL compatibility
stmt = select(t_articles).where(t_articles.c.topic == topic)
result = conn.execute(stmt).mappings()  # ✅ REQUIRED
articles = [dict(row) for row in result]

# Access columns by name
for row in result:
    title = row['title']  # ✅ Works with PostgreSQL
    uri = row['uri']      # ✅ Column name access
```

### ❌ Incorrect Pattern:
```python
# DON'T DO THIS - Missing .mappings()
result = conn.execute(stmt)  # ❌ Won't work with PostgreSQL
articles = [dict(row) for row in result]  # ❌ Will fail

# DON'T DO THIS - Numeric index
title = row[0]  # ❌ Doesn't work with .mappings()
```

---

## Next Steps

1. **Immediate**: Verify DB_TYPE environment variable is set to `postgresql` on all environments
2. **Immediate**: Test OAuth login flow
3. **Today**: Run table existence verification queries
4. **This Week**: Fix critical files listed above
5. **Next Sprint**: Complete Phase 2-4 of action plan

---

## Conclusion

The codebase has **partially migrated** from SQLite to PostgreSQL, with several subsystems still using SQLite or having dual-path logic. The main `Database` class correctly handles both databases based on `DB_TYPE`, but not all code paths have been updated.

**Critical areas needing immediate attention:**
1. User authentication and OAuth system
2. Keyword monitoring error handling
3. Health check endpoints
4. Environment variable verification

**Recommended approach:**
- Focus on high-risk authentication system first
- Verify all tables exist in PostgreSQL
- Update error handling to be database-agnostic
- Test each subsystem individually
- Keep ChromaDB as separate (this is correct)

---

**Document Version**: 1.0
**Last Updated**: 2025-10-13
**Audit Performed By**: Claude Code Assistant
