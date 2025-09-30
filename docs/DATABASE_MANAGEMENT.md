# Database Management Features

## Overview

This document describes the database management features available in the application, including article data export/import, database reset operations, and database creation.

**Last Updated:** 2025-09-30

---

## Table of Contents

1. [Article Export/Import](#article-exportimport)
2. [Database Reset Operations](#database-reset-operations)
3. [Database Creation](#database-creation)
4. [Topic Configuration Export/Import](#topic-configuration-exportimport)
5. [Removed Features](#removed-features)

---

## Article Export/Import

### Export Features

#### Enriched Article Export
**Endpoint:** `GET /api/export-articles-enriched`

Exports articles with AI-enriched metadata (without raw markdown content).

**Exported Fields:**
- Article metadata (URI, title, news_source, publication_date, submission_date)
- AI enrichments (summary, category, future_signal, sentiment, driver_type)
- Relevance scores (topic_alignment_score, keyword_relevance_score, confidence_score)
- Source credibility (bias, factual_reporting, mbfc_credibility_rating, press_freedom)
- Quality metrics (quality_score, quality_issues)
- Analysis data (tags, extracted topics/keywords, explanations)

**Use Cases:**
- Lightweight backups
- Data analysis and reporting
- Sharing curated article collections
- Export for external tools

**Response Format:**
```json
{
  "export_timestamp": "2025-09-30T12:00:00",
  "export_type": "enriched",
  "version": "1.0",
  "total_articles": 150,
  "articles": [...]
}
```

#### Raw Article Export
**Endpoint:** `GET /api/export-articles-raw`

Exports complete article data including raw markdown content.

**Additional Fields:**
- `raw_markdown`: Full article content in markdown format
- `last_updated`: Last modification timestamp

**Use Cases:**
- Complete database backups
- Migration to new systems
- Content archival
- Full data recovery

### Import Features

#### Article Import
**Endpoint:** `POST /api/import-articles`

Imports article data with robust validation and conflict resolution.

**Query Parameters:**
- `merge_mode` (boolean, default: true): Keep existing articles (true) or replace all (false)
- `skip_duplicates` (boolean, default: true): Skip articles with duplicate URIs
- `update_existing` (boolean, default: false): Update existing articles with new data

**Validation Features:**
- **URI Validation**: Ensures required primary key is present
- **Duplicate Detection**: Identifies existing articles by URI
- **Field Validation**: Validates data types and constraints
- **Partial Success**: Processes all valid records even if some fail
- **Error Tracking**: Records detailed errors for problematic records

**Conflict Resolution Strategies:**

1. **Skip Duplicates** (`skip_duplicates=true`, `update_existing=false`)
   - Existing articles remain unchanged
   - New articles are added
   - Duplicates are counted as "skipped"

2. **Update Existing** (`update_existing=true`)
   - Updates existing articles with new data
   - Only updates non-null fields from import
   - Handles both `articles` and `raw_articles` tables

3. **Replace All** (`merge_mode=false`)
   - ⚠️ Deletes ALL existing articles
   - Imports all articles from file
   - Requires explicit user confirmation

**Response Format:**
```json
{
  "message": "Article import completed: imported 100, updated 20, skipped 10, failed 5 of 135 records",
  "statistics": {
    "total_records": 135,
    "imported": 100,
    "updated": 20,
    "skipped": 10,
    "failed": 5,
    "errors": [
      "Record 15 (URI: https://...): Missing required field 'uri'",
      "Record 42 (URI: https://...): Invalid date format"
    ]
  }
}
```

---

## Database Reset Operations

### Reset Articles Data

**Endpoint:** `POST /api/reset-articles-data`
**UI Location:** Configuration > Database > Database Content Reset > Reset Articles

Comprehensively resets all article-related data while preserving database structure.

**Tables Cleared (in order):**

1. **Dependent Tables:**
   - `keyword_article_matches` - Keyword-to-article relationships
   - `keyword_alerts` - Keyword alert notifications
   - `article_annotations` - User annotations on articles
   - `model_bias_arena_articles` - Bias evaluation data
   - `model_bias_arena_results` - Bias evaluation results
   - `model_bias_arena_runs` - Bias evaluation runs
   - `feed_items` - Feed item references
   - `feed_group_sources` - Feed source configurations
   - `signal_alerts` - Signal alert notifications
   - `incident_status` - Incident tracking
   - `article_analysis_cache` - Analysis cache
   - `analysis_versions_v2` - Analysis version history (v2)
   - `analysis_versions` - Analysis version history (v1)
   - `podcasts` - Generated podcasts
   - `raw_articles` - Raw article content

2. **Main Tables:**
   - `monitored_keywords` - Monitored keyword definitions
   - `keyword_groups` - Keyword group definitions
   - `articles` - Main article table

**Safety Features:**
- Two-stage confirmation dialog
- Foreign key constraint management
- Transaction-based deletion with rollback
- Continues on individual table failures
- Detailed deletion statistics

**Response Format:**
```json
{
  "message": "Successfully reset articles data. Deleted 1247 total rows.",
  "details": {
    "articles": 150,
    "raw_articles": 150,
    "article_annotations": 45,
    "keyword_alerts": 200
  }
}
```

### Reset Auspex Chats

**Endpoint:** `POST /api/reset-auspex-chats`
**UI Location:** Configuration > Database > Database Content Reset > Reset Auspex Chats

Deletes all Auspex chat history (conversations and messages).

**Tables Cleared:**
- `auspex_messages` - All chat messages
- `auspex_chats` - All chat conversations

**Response Format:**
```json
{
  "message": "Successfully reset Auspex chats. Deleted 8 chats and 156 messages.",
  "chats_deleted": 8,
  "messages_deleted": 156
}
```

---

## Database Creation

### Create New Database

**Endpoint:** `POST /api/databases`
**UI Location:** Configuration > Database > New Database

Creates a new SQLite database with full schema initialization.

**Request Body:**
```json
{
  "name": "database_name"
}
```

**Process:**
1. Sanitizes database name (removes/adds .db extension)
2. Checks for existing database with same name
3. Creates new database file in `DATABASE_DIR`
4. Initializes complete schema with `init_db()`
5. Copies user accounts from current database
6. Returns new database information

**Automatic User Migration:**
- User accounts are copied from the current database
- Includes username, password hash, and force_password_change flag
- Ensures access to new database without re-authentication

---

## Topic Configuration Export/Import

### Export Topic Configurations

**Endpoint:** `GET /api/export-topics`

Exports all topic monitoring configurations to JSON.

**Exported Data:**
- `keyword_groups` - Topic/keyword groups
- `monitored_keywords` - Keywords with group references
- `feed_keyword_groups` - Feed group definitions
- `feed_group_sources` - Feed source configurations
- `keyword_monitor_settings` - Global monitoring settings

### Import Topic Configurations

**Endpoint:** `POST /api/import-topics`

Imports topic configurations from JSON file.

**Query Parameters:**
- `merge_mode` (boolean): Merge (true) or replace (false) existing configurations

**Import Modes:**

1. **Replace Mode** (`merge_mode=false`)
   - Deletes ALL existing topic configurations
   - Imports all configurations from file
   - Cleans up related data (alerts, matches)

2. **Merge Mode** (`merge_mode=true`)
   - Keeps existing configurations
   - Adds new configurations
   - Skips duplicates based on name/topic

---

## Removed Features

### Merge from Backup (Deprecated)

**Removed:** 2025-09-30

The "Merge from Backup" feature has been superseded by the more robust Article Import functionality.

**Previous Endpoint:** `POST /api/merge_backup` (still exists in code but no longer accessible from UI)

**Replacement:**
Use the Article Export/Import feature which provides:
- Better validation and error handling
- Granular control over conflict resolution
- Detailed statistics and error reporting
- Support for partial imports
- Per-record error tracking

**Migration Path:**
1. Export articles from backup database using database download
2. Use Article Import with appropriate merge settings
3. Review import statistics for any issues

---

## UI Components

### Configuration Page Location

All database management features are accessible from:
**Configuration** → **Database Management** tab

### Sections:

1. **Active Database** - Switch between databases
2. **Available Databases** - List and manage databases
3. **New Database** - Create new databases
4. **Database Operations** - Backup, download, reset
5. **Database Content Reset** - Selective data cleanup (NEW)
6. **Database Hygiene** - Clean orphaned data
7. **Topic Configuration Export/Import** - Topic management
8. **Article Data Export/Import** - Article data management (NEW)

---

## Best Practices

### Before Reset Operations

1. **Create Backup**
   - Use "Backup" button before any destructive operation
   - Download backup for external storage
   - Verify backup file integrity

2. **Export Data**
   - Export articles if you might need them later
   - Export topic configurations separately
   - Store exports in version control or secure storage

### Import Operations

1. **Test with Merge Mode First**
   - Use merge mode to test imports without data loss
   - Review statistics before replacing data
   - Verify data quality in UI

2. **Handle Import Errors**
   - Review error messages in import results
   - Fix problematic records in source file
   - Re-import corrected records

---

## API Reference

### Quick Reference

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/export-articles-enriched` | GET | Export enriched article data |
| `/api/export-articles-raw` | GET | Export complete article data |
| `/api/import-articles` | POST | Import article data |
| `/api/reset-articles-data` | POST | Reset all article-related data |
| `/api/reset-auspex-chats` | POST | Reset Auspex chat history |
| `/api/export-topics` | GET | Export topic configurations |
| `/api/import-topics` | POST | Import topic configurations |
| `/api/databases` | GET | List databases |
| `/api/databases` | POST | Create database |
| `/api/databases/{name}` | DELETE | Delete database |
| `/api/databases/backup` | POST | Create backup |

---

## File Locations

### Backend Code

- **Export/Import Endpoints:** `app/routes/database.py:660-973`
- **Reset Endpoints:** `app/routes/database.py:290-423`
- **Database Creation:** `app/main.py:1123-1130`
- **Database Class:** `app/database.py:589-618`

### Frontend Code

- **UI Components:** `templates/config.html:117-158`
- **JavaScript Functions:** `templates/config.html:2460-2669`
- **Export Functions:** `templates/config.html:2460-2531`
- **Import Functions:** `templates/config.html:2533-2669`
- **Reset Functions:** `templates/config.html:1975-2063`

---

## Change Log

### 2025-09-30

**Added:**
- Article enriched export endpoint (`/api/export-articles-enriched`)
- Article raw export endpoint (`/api/export-articles-raw`)
- Article import endpoint with validation (`/api/import-articles`)
- Reset articles data endpoint (`/api/reset-articles-data`)
- Reset Auspex chats endpoint (`/api/reset-auspex-chats`)
- Article Import dialog with merge/replace modes
- Database Content Reset UI section
- Comprehensive validation and error handling
- Per-record error tracking for imports
- Detailed statistics for all operations

**Removed:**
- Merge from Backup button and UI
- Merge dialog template
- `showMergeDialog()` JavaScript function
- `mergeFromBackup()` JavaScript function

**Deprecated:**
- `/api/merge_backup` endpoint (still exists but no longer used)

**Enhanced:**
- Import/export now handles both enriched and raw article data
- Better error messages and user feedback
- Transaction safety with rollback capabilities
- Granular control over conflict resolution

---

**Document Version:** 1.0
**Last Updated:** 2025-09-30