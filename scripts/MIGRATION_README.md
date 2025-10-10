# SQLite to PostgreSQL Migration Guide

This guide explains how to migrate your existing AuNoo AI SQLite database (`fnaapp.db`) to PostgreSQL.

## When to Use This Migration

This migration script is needed when:
- You have an existing AuNoo AI installation using SQLite
- You want to upgrade to PostgreSQL for better performance and scalability
- You want to preserve all your existing data (articles, keyword monitoring, organizational profiles, etc.)

## Prerequisites

1. **PostgreSQL must be installed and configured**
   - Run `scripts/setup_postgresql.py` first to set up PostgreSQL
   - Make sure your `.env` file has PostgreSQL connection details

2. **Backup your SQLite database**
   ```bash
   cp app/data/fnaapp.db app/data/fnaapp.db.backup
   ```

3. **Stop the application** (if running)
   ```bash
   # If using systemd service
   sudo systemctl stop yourinstance.aunoo.ai

   # Or kill the process if running directly
   pkill -f "python.*run.py"
   ```

## Migration Steps

### Step 1: Dry Run (Recommended)

First, run a dry run to see what will be migrated:

```bash
python scripts/migrate_sqlite_to_postgres.py --dry-run
```

This will show you:
- How many tables will be migrated
- How many records are in each table
- What would be migrated (without actually migrating)

### Step 2: Run the Migration

Once you've verified the dry run looks good:

```bash
python scripts/migrate_sqlite_to_postgres.py
```

The script will:
- Migrate all tables in the correct order (respecting foreign key dependencies)
- Convert data types appropriately (e.g., SQLite INTEGER booleans → PostgreSQL BOOLEAN)
- Skip records that already exist in PostgreSQL (by default)
- Show progress as it migrates
- Display a summary at the end

### Step 3: Verify Migration

After migration completes:

1. **Check the summary output** to ensure all tables were migrated successfully

2. **Start your application**:
   ```bash
   # If using systemd
   sudo systemctl start yourinstance.aunoo.ai

   # Or run directly
   python app/run.py
   ```

3. **Verify your data**:
   - Check that your articles are visible
   - Verify keyword monitoring settings and groups
   - Check organizational profiles
   - Test that media bias data loads correctly

## Advanced Options

### Custom SQLite Path

If your SQLite database is in a different location:

```bash
python scripts/migrate_sqlite_to_postgres.py --sqlite-path /path/to/custom.db
```

### Force Re-migration

By default, the script skips records that already exist in PostgreSQL. To force re-migration:

```bash
python scripts/migrate_sqlite_to_postgres.py --no-skip-existing
```

**Warning**: This will update existing records with data from SQLite.

## What Gets Migrated

The script migrates **all** tables including:

### Core Data
- `users` - User accounts
- `articles` - All articles and news data
- `raw_articles` - Raw article data

### Keyword Monitoring
- `keyword_groups` - Keyword groups and topics
- `monitored_keywords` - Individual keywords
- `keyword_alerts` - Keyword alerts
- `keyword_article_matches` - Article-keyword matches
- `keyword_monitor_settings` - Monitoring configuration
- `keyword_monitor_status` - Monitoring status

### Organizational Data
- `organizational_profiles` - Organizational profiles for research

### Media Bias
- `mediabias` - Media bias source data
- `mediabias_settings` - Media bias configuration

### Feed Management
- `shared_news_feeds` - Shared news feeds
- `feed_keyword_groups` - Feed keyword associations
- `feed_group_sources` - Feed source mappings
- `feed_items` - Feed items
- `user_feed_subscriptions` - User feed subscriptions

### Analysis & Research
- `scenarios` - Research scenarios
- `scenario_blocks` - Scenario building blocks
- `building_blocks` - Reusable building blocks
- `analysis_versions` - Analysis version history
- `article_analysis_cache` - Cached analysis results
- `article_annotations` - Article annotations

### Auspex Chat
- `auspex_prompts` - Chat prompts
- `auspex_chats` - Chat sessions
- `auspex_messages` - Chat messages

### Other Data
- `oauth_users`, `oauth_sessions`, `oauth_allowlist` - OAuth authentication
- `newsletter_prompts` - Newsletter prompts
- `podcasts` - Podcast data
- `signal_alerts`, `signal_instructions` - Signal monitoring
- `incident_status` - Incident tracking
- `trend_consistency_metrics` - Trend analysis
- `model_bias_arena_*` - Model bias testing
- And more...

## Troubleshooting

### Migration fails with foreign key errors

The script migrates tables in dependency order, but if you still see foreign key errors:

1. Make sure PostgreSQL is properly set up with all tables created
2. Run `alembic upgrade head` to ensure schema is up to date

### Some records are skipped

This is normal! The script skips records that already exist in PostgreSQL (based on primary key). To see exactly what was skipped, check the summary output.

### Out of memory errors

For very large databases (100k+ articles):

1. The script commits every 100 rows to avoid memory issues
2. If still problematic, you can migrate specific tables manually using the individual migration scripts

### PostgreSQL connection errors

Make sure:
- PostgreSQL is running: `sudo systemctl status postgresql`
- Your `.env` file has correct PostgreSQL credentials
- Database exists and is accessible

## Individual Migration Scripts (Legacy)

For reference, these individual scripts are also available but are not needed if using the comprehensive script:

- `migrate_org_profiles_to_postgres.py` - Organizational profiles only
- `migrate_keyword_monitoring.py` - Keyword monitoring only
- `migrate_keyword_articles.py` - Keyword-related articles only

## Support

If you encounter issues:

1. Check the migration output for specific error messages
2. Verify your PostgreSQL connection details in `.env`
3. Make sure you have proper permissions on both databases
4. Keep your SQLite backup safe until you've verified the migration

## Performance Notes

- Small databases (<10k articles): ~1-2 minutes
- Medium databases (10k-100k articles): ~5-15 minutes
- Large databases (>100k articles): ~30+ minutes

The script shows progress every 100 rows to keep you informed.
