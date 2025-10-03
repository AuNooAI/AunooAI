# Database Migrations

This directory contains SQL migration files for the database schema.

## Migration System Features

- ✅ **Version Tracking**: Automatically tracks which migrations have been applied
- ✅ **Checksum Validation**: Stores SHA256 hash of each migration for integrity
- ✅ **Idempotent**: Safe to re-run, skips already-applied migrations
- ✅ **Rollback Support**: Can remove migrations from history
- ✅ **Batch Execution**: Run all pending migrations at once
- ✅ **History View**: See all applied migrations and their status

## Usage

### Run a Single Migration

```bash
python run_migration.py <migration_file>
```

Example:
```bash
python run_migration.py create_organizational_profiles_table.sql
```

### Run All Pending Migrations

```bash
python run_migration.py --all
```

This will run all `.sql` files in alphabetical order, skipping any that have already been applied.

### View Migration History

```bash
python run_migration.py --history
```

Shows:
- Migration name
- Applied timestamp
- Success/failure status
- Error messages (if any)

### Force Re-run a Migration

```bash
python run_migration.py <migration_file> --force
```

Useful for development/testing. Use with caution in production.

### Rollback a Migration

```bash
python run_migration.py <migration_file> --rollback
```

This removes the migration from the tracking history but **does not** reverse the database changes. You must manually write and run a down migration if needed.

### Specify Database Path

```bash
python run_migration.py <migration_file> --db-path /path/to/database.db
```

Or set environment variable:
```bash
export DB_PATH=/path/to/database.db
python run_migration.py --all
```

## Creating New Migrations

1. Create a new `.sql` file in this directory
2. Use descriptive names (e.g., `add_user_roles_table.sql`)
3. Make migrations idempotent using `IF NOT EXISTS` clauses
4. Test locally before deploying

### Example Migration Template

```sql
-- Migration: Add new feature
-- Description: What this migration does

-- Create new table
CREATE TABLE IF NOT EXISTS new_table (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Add column to existing table (idempotent)
SELECT CASE
    WHEN NOT EXISTS(
        SELECT 1 FROM pragma_table_info('existing_table')
        WHERE name='new_column'
    )
    THEN 'ALTER TABLE existing_table ADD COLUMN new_column TEXT;'
END AS sql_command;

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_new_table_name ON new_table(name);
```

## Migration Naming Convention

Use descriptive names that indicate the purpose:

- `create_<table_name>_table.sql` - Creating new tables
- `add_<field_name>_to_<table>.sql` - Adding columns
- `update_<feature>_<description>.sql` - Modifying existing structure
- `migrate_<old>_to_<new>.sql` - Data migrations

## Migration History Table

The system automatically creates a `migration_history` table:

```sql
CREATE TABLE migration_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    migration_name TEXT NOT NULL UNIQUE,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT,
    checksum TEXT
);
```

## Best Practices

1. ✅ **Always make migrations idempotent** - Use `IF NOT EXISTS`, `IF EXISTS`, etc.
2. ✅ **Test migrations locally first** - Never run untested migrations in production
3. ✅ **One logical change per migration** - Don't combine unrelated changes
4. ✅ **Never modify existing migrations** - Create new ones instead
5. ✅ **Back up database before running migrations** - Especially in production
6. ✅ **Review migration history** - Use `--history` to verify state

## Troubleshooting

### Migration shows as failed in history

Check the error message:
```bash
python run_migration.py --history
```

Then fix and re-run with `--force`:
```bash
python run_migration.py <migration_file> --force
```

### Migration won't run (already applied)

Use `--force` to override:
```bash
python run_migration.py <migration_file> --force
```

### Need to reset migration history

Connect to database and clear history:
```sql
DELETE FROM migration_history WHERE migration_name = 'problematic_migration.sql';
```

## Example Workflow

### Initial Setup (New Database)
```bash
# Run all migrations
python run_migration.py --all

# Verify
python run_migration.py --history
```

### Adding a New Migration
```bash
# Create migration file
vim app/database/migrations/add_new_feature.sql

# Test locally
python run_migration.py add_new_feature.sql

# Verify
python run_migration.py --history

# Deploy to production
ssh production
python run_migration.py --all
```

### Production Deployment
```bash
# 1. Backup database
cp app/data/fnaapp.db app/data/fnaapp.db.backup

# 2. Run migrations
python run_migration.py --all

# 3. Verify
python run_migration.py --history

# 4. Test application
python app/server_run.py
```
