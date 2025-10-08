# PostgreSQL Setup Guide

This guide covers PostgreSQL setup for AunooAI, including automated installation and manual configuration options.

---

## Quick Start (Automated Setup)

For new installations, run the automated setup script:

```bash
python scripts/setup_postgresql.py
```

This script will:
1. ✅ Detect and install PostgreSQL (if needed)
2. ✅ Install Python dependencies (asyncpg, psycopg2, alembic)
3. ✅ Create database and user with secure password
4. ✅ Update `.env` configuration
5. ✅ Run database migrations
6. ✅ Verify connection

**Your application is ready to use PostgreSQL!**

---

## Script Options

### Skip PostgreSQL Installation
If PostgreSQL is already installed:
```bash
python scripts/setup_postgresql.py --skip-install
```

### Force Database Recreation
**⚠️ WARNING: Destroys existing data!**
```bash
python scripts/setup_postgresql.py --force
```

### Custom Database Credentials
```bash
python scripts/setup_postgresql.py \
  --db-name my_database \
  --db-user my_user \
  --db-password my_secure_password
```

---

## Supported Operating Systems

### ✅ Ubuntu/Debian
Automatically installs via `apt-get`:
- postgresql
- postgresql-contrib

### ✅ RedHat/CentOS/Fedora
Automatically installs via `dnf`:
- postgresql-server
- postgresql-contrib

### ✅ macOS
Automatically installs via Homebrew:
- postgresql@14

**Note:** Requires Homebrew to be installed: https://brew.sh

### ⚠️ Windows
Manual installation required.

Download from: https://www.postgresql.org/download/windows/

After installing PostgreSQL manually:
```bash
python scripts/setup_postgresql.py --skip-install
```

---

## Manual Setup (Advanced)

If you prefer manual configuration:

### 1. Install PostgreSQL

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install postgresql postgresql-contrib
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

**RedHat/CentOS/Fedora:**
```bash
sudo dnf install postgresql-server postgresql-contrib
sudo postgresql-setup --initdb
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

**macOS:**
```bash
brew install postgresql@14
brew services start postgresql@14
```

### 2. Create Database and User

```bash
sudo -u postgres psql
```

In PostgreSQL shell:
```sql
CREATE USER aunoo_user WITH PASSWORD 'your_secure_password';
CREATE DATABASE aunoo_db OWNER aunoo_user;
GRANT ALL PRIVILEGES ON DATABASE aunoo_db TO aunoo_user;
\q
```

### 3. Install Python Dependencies

```bash
pip install asyncpg psycopg2-binary alembic sqlalchemy[asyncio]
```

### 4. Update `.env` Configuration

Add these lines to your `.env` file:

```bash
# Database Configuration
DB_TYPE=postgresql
DB_HOST=localhost
DB_PORT=5432
DB_NAME=aunoo_db
DB_USER=aunoo_user
DB_PASSWORD=your_secure_password

# Connection URLs
DATABASE_URL=postgresql+asyncpg://aunoo_user:your_secure_password@localhost:5432/aunoo_db
SYNC_DATABASE_URL=postgresql+psycopg2://aunoo_user:your_secure_password@localhost:5432/aunoo_db

# Connection Pool Settings
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=10
DB_POOL_TIMEOUT=30
DB_POOL_RECYCLE=3600
```

### 5. Run Migrations

```bash
alembic upgrade head
```

---

## Database Connection Diagnostics

The application now includes automatic database connection checking on startup.

When you run `python app/run.py`, you'll see:

### ✅ Successful PostgreSQL Connection
```
============================================================
AunooAI Server Startup
============================================================
PostgreSQL database configured
✅ PostgreSQL dependencies installed
✅ Connected to PostgreSQL database: aunoo_db
============================================================
Starting server on port 10015
```

### ❌ Missing Configuration
```
PostgreSQL database configured
❌ Missing required PostgreSQL environment variables: DB_PASSWORD
Run 'python scripts/setup_postgresql.py' to configure PostgreSQL
```

### ❌ Missing Dependencies
```
PostgreSQL database configured
❌ Missing PostgreSQL dependencies: No module named 'asyncpg'
Run 'pip install asyncpg psycopg2-binary' or 'python scripts/setup_postgresql.py'
```

### ❌ Connection Failed
```
PostgreSQL database configured
✅ PostgreSQL dependencies installed
❌ Failed to connect to PostgreSQL: connection refused
Check your database configuration or run 'python scripts/setup_postgresql.py'
```

---

## Switching Between SQLite and PostgreSQL

### Switch to PostgreSQL
Edit `.env`:
```bash
DB_TYPE=postgresql
```

### Switch to SQLite
Edit `.env`:
```bash
DB_TYPE=sqlite
```

**No code changes required!** The application automatically detects and uses the configured database type.

---

## Migrating Existing SQLite Data to PostgreSQL

If you have existing data in SQLite that you want to migrate:

```bash
cd /home/orochford/bin/sqlplan
python phase2/01_install_postgresql.py
python phase2/02_install_dependencies.py
python phase2/03_configure_database.py
python phase2/04_init_alembic.py
python phase2/05_export_sqlite_data.py
python phase2/06_create_migrations.py
python phase2/07_import_data.py
```

Or use the automated script:
```bash
python /home/orochford/bin/sqlplan/run_migration.py
```

---

## Troubleshooting

### PostgreSQL Not Starting

**Check status:**
```bash
sudo systemctl status postgresql
```

**View logs:**
```bash
sudo journalctl -u postgresql -n 50
```

**Restart service:**
```bash
sudo systemctl restart postgresql
```

### Connection Refused

Check if PostgreSQL is listening:
```bash
sudo netstat -plnt | grep 5432
```

Check `pg_hba.conf` for connection permissions:
```bash
sudo nano /etc/postgresql/*/main/pg_hba.conf
```

Add this line for local development:
```
host    all             all             127.0.0.1/32            md5
```

Restart PostgreSQL:
```bash
sudo systemctl restart postgresql
```

### Authentication Failed

Reset user password:
```bash
sudo -u postgres psql
ALTER USER aunoo_user WITH PASSWORD 'new_password';
\q
```

Update `.env` with new password.

### Port Already in Use

Check what's using port 5432:
```bash
sudo lsof -i :5432
```

Kill the process or change PostgreSQL port in `postgresql.conf`.

---

## Performance Tuning

### Connection Pool Settings

Adjust in `.env` based on your load:

```bash
# Light load (<10 concurrent users)
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=5

# Medium load (10-50 concurrent users)
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=10

# Heavy load (50+ concurrent users)
DB_POOL_SIZE=50
DB_MAX_OVERFLOW=20
```

### PostgreSQL Configuration

Edit `/etc/postgresql/*/main/postgresql.conf`:

```conf
# Memory settings (adjust based on available RAM)
shared_buffers = 256MB           # 25% of RAM for dedicated server
effective_cache_size = 1GB       # 50-75% of RAM
work_mem = 10MB                  # RAM / max_connections / 4

# Connection settings
max_connections = 100            # Should be >= pool_size + max_overflow

# Query optimization
random_page_cost = 1.1           # For SSD storage
effective_io_concurrency = 200   # For SSD storage
```

Restart after changes:
```bash
sudo systemctl restart postgresql
```

---

## Security Best Practices

### 1. Strong Passwords
The setup script generates 32-character random passwords. Keep these secure!

### 2. Restrict Network Access
For production, limit PostgreSQL to local connections only:

`pg_hba.conf`:
```
# Local connections only
local   all             all                                     md5
host    all             all             127.0.0.1/32            md5
host    all             all             ::1/128                 md5
```

### 3. Regular Backups

**Automated daily backup:**
```bash
# Add to crontab: crontab -e
0 2 * * * pg_dump -U aunoo_user aunoo_db > /backups/aunoo_db_$(date +\%Y\%m\%d).sql
```

**Manual backup:**
```bash
pg_dump -U aunoo_user aunoo_db > backup.sql
```

**Restore from backup:**
```bash
psql -U aunoo_user aunoo_db < backup.sql
```

### 4. Encrypt Connections

For production, enable SSL in `postgresql.conf`:
```conf
ssl = on
ssl_cert_file = '/path/to/server.crt'
ssl_key_file = '/path/to/server.key'
```

Update `.env`:
```bash
DATABASE_URL=postgresql+asyncpg://aunoo_user:password@localhost:5432/aunoo_db?ssl=require
```

---

## What Changed in the Migration

### Code Changes
- **`app/database.py`** (lines 75-104): Added PostgreSQL support via `DB_TYPE` environment variable
- **`app/config/settings.py`**: Added `DatabaseSettings` class for PostgreSQL configuration
- **`app/database_async.py`**: Fixed async pool for PostgreSQL
- **`app/run.py`**: Added database connection diagnostics

### Configuration
- **`.env`**: Added PostgreSQL credentials and connection URLs

### No Changes Required
- ✅ All 38 route files work without modification
- ✅ All service files work without modification
- ✅ All database queries work without modification

**The Database class abstraction allows zero application code changes!**

---

## Benefits of PostgreSQL

### 1. Concurrent Writes
- **SQLite:** Serial writes, 1 at a time (locked)
- **PostgreSQL:** Parallel writes, no lock contention

### 2. Scalability
- **SQLite:** ~10 concurrent users max
- **PostgreSQL:** 50+ concurrent users supported

### 3. Advanced Features
- Full-text search (FTS)
- Advanced indexing (GIN, GIST, BRIN)
- Point-in-time recovery
- Streaming replication
- Better query optimization
- JSON/JSONB support
- Array types
- Custom functions and triggers

### 4. Production-Grade
- ACID compliance
- Multi-version concurrency control (MVCC)
- Hot backups
- Professional tooling ecosystem

---

## Next Steps

After PostgreSQL is set up and working:

### Optional: SQLAlchemy Migration
For better code quality and database-agnostic queries, consider migrating to SQLAlchemy:

See: `/home/orochford/bin/sqlplan/DATABASE_QUERY_FACADE_PROGRESS.md`

**Effort:** 15-20 hours
**Benefit:** Database-agnostic code, better testing, easier maintenance

### Optional: Async Migration
For maximum performance with high concurrent load:

See: `/home/orochford/bin/sqlplan/FUTURE_ASYNC_MIGRATION.md`

**Effort:** 9 hours (incremental over 4 weeks)
**Benefit:** True async I/O, 25-50x faster under heavy load

**Note:** Both are optional improvements. Your application is production-ready now!

---

## Support

### Script Issues
If the automated setup script fails, check:
1. Operating system is supported (run `uname -a`)
2. You have sudo permissions
3. Internet connection is available
4. Disk space is sufficient (run `df -h`)

### Database Issues
Check logs:
```bash
# Application logs
tail -f /tmp/skunkworkx_postgresql.log

# PostgreSQL logs
sudo journalctl -u postgresql -f
```

### Getting Help
Run diagnostics and include output in bug reports:
```bash
python app/run.py 2>&1 | tee startup.log
```

---

## Summary

**New Users:**
```bash
python scripts/setup_postgresql.py
python app/run.py
```

**Existing Users:**
```bash
python scripts/setup_postgresql.py
# Review .env changes
python app/run.py
```

That's it! Your application now uses PostgreSQL with production-grade performance and scalability.

---

## Migrating Existing Article Data

For existing tenants with SQLite data, use the migration script to transfer articles to PostgreSQL.

### Article Migration Script

**Location:** `/home/orochford/bin/migrate_articles_to_postgres.py`

**What it migrates:**
- `articles` - Main article data
- `raw_articles` - Raw article content
- `keyword_article_matches` - Keyword monitoring matches

### Usage

**From tenant directory:**
```bash
cd /home/orochford/tenants/<tenant-name>
python /home/orochford/bin/migrate_articles_to_postgres.py
```

**Test first with dry run:**
```bash
python /home/orochford/bin/migrate_articles_to_postgres.py --dry-run
```

### Complete Migration Workflow

**Step-by-step migration for existing tenants:**

```bash
# 1. Navigate to tenant directory
cd /home/orochford/tenants/skunkworkx.aunoo.ai

# 2. Backup SQLite database
cp app/data/fnaapp.db app/data/fnaapp.db.backup
cp .env .env.backup

# 3. Deploy PostgreSQL (creates database and schema)
python /home/orochford/bin/deploy_postgres.py

# 4. Test migration with dry run
python /home/orochford/bin/migrate_articles_to_postgres.py --dry-run

# 5. Run actual migration
python /home/orochford/bin/migrate_articles_to_postgres.py

# 6. Verify data was migrated
psql -U skunkworkx_aunoo_ai_user -d skunkworkx_aunoo_ai << EOF
SELECT 'articles:', COUNT(*) FROM articles;
SELECT 'raw_articles:', COUNT(*) FROM raw_articles;
SELECT 'keyword_article_matches:', COUNT(*) FROM keyword_article_matches;
