# Auto-Ingest Migration Implementation

## Overview
This document describes the implementation of automatic database migrations for the auto-ingest feature in AunooAI. The migration system ensures that all required database schema changes are applied automatically when the application starts up.

## Problem Solved
Previously, users needed to manually run migration scripts when deploying the auto-ingest feature or when checking out the codebase on new environments. This created deployment friction and potential errors when the required database columns were missing.

## Solution: Integrated Startup Migration

### Architecture
The auto-ingest migration is now integrated into the application's existing migration system in `app/database.py`. The migration runs automatically during application startup as part of the database initialization process.

### Migration Flow
1. **App Startup** → `app/main.py` startup event handler
2. **Initialize Application** → `app/startup.py` `initialize_application()`
3. **Database Init** → `app/database.py` `Database.init_db()`
4. **Run Migrations** → `Database.migrate_db()`
5. **Check Applied Migrations** → Query `migrations` table
6. **Apply New Migrations** → Execute `_add_auto_ingest_columns()` if not already applied
7. **Record Migration** → Insert migration record in `migrations` table

## Database Schema Changes

### Articles Table
The migration adds the following columns to the `articles` table:

```sql
ALTER TABLE articles ADD COLUMN auto_ingested BOOLEAN DEFAULT FALSE;
ALTER TABLE articles ADD COLUMN ingest_status TEXT;
ALTER TABLE articles ADD COLUMN quality_score REAL;
ALTER TABLE articles ADD COLUMN quality_issues TEXT;
```

**Purpose:**
- `auto_ingested`: Tracks whether article was processed by auto-ingest pipeline
- `ingest_status`: Status of auto-ingest processing (e.g., 'approved', 'rejected', 'pending')
- `quality_score`: Numerical quality assessment score (0.0-1.0)
- `quality_issues`: JSON string of quality control issues found

### Keyword Monitor Settings Table
The migration adds auto-ingest configuration columns to `keyword_monitor_settings`:

```sql
ALTER TABLE keyword_monitor_settings ADD COLUMN auto_ingest_enabled BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE keyword_monitor_settings ADD COLUMN min_relevance_threshold REAL NOT NULL DEFAULT 0.0;
ALTER TABLE keyword_monitor_settings ADD COLUMN quality_control_enabled BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE keyword_monitor_settings ADD COLUMN auto_save_approved_only BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE keyword_monitor_settings ADD COLUMN default_llm_model TEXT NOT NULL DEFAULT 'gpt-4o-mini';
ALTER TABLE keyword_monitor_settings ADD COLUMN llm_temperature REAL NOT NULL DEFAULT 0.1;
ALTER TABLE keyword_monitor_settings ADD COLUMN llm_max_tokens INTEGER NOT NULL DEFAULT 1000;
```

**Purpose:**
- `auto_ingest_enabled`: Master toggle for auto-ingest functionality
- `min_relevance_threshold`: Minimum relevance score required for auto-approval
- `quality_control_enabled`: Whether to run quality control checks
- `auto_save_approved_only`: Only save articles that pass quality control
- `default_llm_model`: Default AI model for article analysis
- `llm_temperature`: Temperature setting for LLM calls
- `llm_max_tokens`: Maximum tokens for LLM responses

### Performance Indexes
The migration creates indexes for optimal query performance:

```sql
CREATE INDEX IF NOT EXISTS idx_articles_auto_ingested ON articles(auto_ingested);
CREATE INDEX IF NOT EXISTS idx_articles_ingest_status ON articles(ingest_status);
CREATE INDEX IF NOT EXISTS idx_articles_quality_score ON articles(quality_score);
```

## Implementation Details

### Migration Method: `_add_auto_ingest_columns()`
Located in `app/database.py`, this method:

1. **Iterates through column definitions** for both tables
2. **Attempts to add each column** using `ALTER TABLE ADD COLUMN`
3. **Handles existing columns gracefully** via `sqlite3.OperationalError` exception handling
4. **Creates performance indexes** for auto-ingest related queries
5. **Logs progress** for debugging and monitoring

### Error Handling
- **Idempotent Design**: Migration can be run multiple times safely
- **Graceful Column Existence**: Skips columns that already exist
- **Exception Logging**: Logs any migration errors for debugging
- **Rollback Safety**: Uses database transactions for consistency

### Migration Tracking
- **Migrations Table**: All applied migrations are recorded in `migrations` table
- **Unique Constraint**: Migration names are unique to prevent duplicate applications
- **Timestamp Tracking**: `applied_at` timestamp records when migration was applied
- **Status Checking**: System checks applied migrations before running new ones

## Integration Points

### Startup Integration
The migration is integrated into the application startup sequence:

```python
# app/main.py - startup event handler
@app.on_event("startup")
async def startup_event():
    # ... existing startup code ...
    success = initialize_application()  # This triggers database init and migrations
```

### Database Initialization
The migration runs as part of database initialization:

```python
# app/database.py
def init_db(self):
    # ... create tables ...
    self.migrate_db()  # This runs all pending migrations including auto-ingest
```

### Migration Registry
The migration is registered in the migrations list:

```python
migrations = [
    # ... existing migrations ...
    ("add_auto_ingest_columns", self._add_auto_ingest_columns)
]
```

## Benefits

### For Developers
- **No Manual Steps**: Auto-ingest works immediately after code deployment
- **Environment Consistency**: All environments get the same schema automatically
- **Version Control**: Migration is tracked and versioned with the codebase

### For Users
- **Seamless Updates**: Database schema updates happen transparently
- **No Downtime**: Migration runs during normal application startup
- **Error Prevention**: Eliminates "column not found" errors

### For Operations
- **Deployment Safety**: Migrations are tested and idempotent
- **Rollback Friendly**: Changes are tracked and can be reversed if needed
- **Monitoring**: Migration status is logged for operational visibility

## Testing and Validation

### Pre-Migration State
- Articles table lacks auto-ingest columns
- Keyword monitor settings lacks auto-ingest configuration
- Auto-ingest features throw "column not found" errors

### Post-Migration State
- All required columns exist with proper defaults
- Indexes are created for performance
- Auto-ingest features work without errors
- Migration is recorded in migrations table

### Validation Commands
```python
# Check if migration was applied
cursor.execute("SELECT name FROM migrations WHERE name = 'add_auto_ingest_columns'")

# Verify articles table columns
cursor.execute("PRAGMA table_info(articles)")

# Verify keyword monitor settings columns  
cursor.execute("PRAGMA table_info(keyword_monitor_settings)")
```

## Future Considerations

### Schema Evolution
- Additional auto-ingest columns can be added via new migrations
- Migration system supports incremental schema changes
- Backwards compatibility maintained through proper defaults

### Performance Monitoring
- Monitor migration execution time during startup
- Track index usage for query optimization
- Consider partitioning strategies for large datasets

### Data Migration
- Current migration only adds columns (schema-only)
- Future migrations may need to migrate existing data
- Consider data transformation requirements for existing articles

## Troubleshooting

### Common Issues
1. **Migration Not Applied**: Check logs for migration errors
2. **Column Already Exists**: Normal behavior, migration skips existing columns
3. **Permission Errors**: Ensure database write permissions
4. **Lock Errors**: Check for concurrent database access during startup

### Debugging Steps
1. Check application startup logs for migration messages
2. Query `migrations` table to see applied migrations
3. Use `PRAGMA table_info()` to verify column existence
4. Test auto-ingest functionality to confirm schema integrity

## Related Files
- `app/database.py` - Migration implementation
- `app/main.py` - Startup integration
- `app/startup.py` - Application initialization
- `app/services/automated_ingest_service.py` - Uses migrated columns
- `app/routes/keyword_monitor_api.py` - Auto-ingest API endpoints

## Migration History
- **Initial Implementation** (2024): Added auto-ingest columns and settings
- **Performance Optimization** (2024): Added indexes for auto-ingest queries
- **Future**: Additional auto-ingest features may require schema updates

---

**Note**: This migration system ensures that the auto-ingest feature works out-of-the-box for all users without requiring manual database setup steps. The migration is safe, idempotent, and integrates seamlessly with the application's startup process. 