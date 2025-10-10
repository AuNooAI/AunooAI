# Database Files

This directory contains the application's database files.

## Files

### `fnaapp.db`
The main application database. This file is **NOT** committed to git (excluded in `.gitignore`).

- Created automatically on first run by copying from `fnaapp.db.seed`
- Contains all application data (users, articles, keywords, settings, etc.)
- Each deployment has its own unique database

### `fnaapp.db.seed` ⭐
The seed database template that **IS** committed to git.

- Contains minimal essential defaults for new installations
- Includes:
  - Default admin user (username: `admin`, password: `admin`)
  - Default Auspex prompt
  - Default keyword monitoring settings
  - Default media bias settings
  - All required table schemas
- Copied to `fnaapp.db` during setup if no database exists

## For New Users

When you run `python scripts/setup.py` and choose SQLite:
1. The seed database (`fnaapp.db.seed`) is copied to `fnaapp.db`
2. You can log in with default credentials: `admin` / `admin`
3. You'll be required to change the password on first login

## For Developers

### Creating/Updating the Seed Database

To create or update the seed database:

```bash
python scripts/create_seed_database.py
```

This will:
1. Run Alembic migrations to create all tables
2. Insert default data (admin user, prompts, settings)
3. Create `app/data/fnaapp.db.seed`

**Important**: After creating a new seed database, test it thoroughly before committing!

```bash
# Test the seed database
rm app/data/fnaapp.db  # Remove existing database
cp app/data/fnaapp.db.seed app/data/fnaapp.db  # Copy seed
python app/run.py  # Test the app
# Try logging in with admin/admin
```

### When to Update the Seed Database

Update the seed database when:
- Database schema changes (new migrations added)
- Default settings need to be updated
- New required defaults are added

### Committing the Seed Database

The seed database **should be committed** to git because:
- It's small (~100KB) with minimal data
- New users need it to run the application
- It contains essential defaults

```bash
git add app/data/fnaapp.db.seed
git commit -m "Updated seed database with new defaults"
```

## Migrating from SQLite to PostgreSQL

If you start with SQLite and want to migrate to PostgreSQL:

```bash
# 1. Setup PostgreSQL
python scripts/setup_postgresql.py

# 2. Migrate all your data
python scripts/migrate_sqlite_to_postgres.py

# 3. Restart the app (now uses PostgreSQL)
```

See `scripts/MIGRATION_README.md` for detailed migration instructions.
