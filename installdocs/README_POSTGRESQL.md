# PostgreSQL Setup - Quick Reference

## For New Users

**One-command setup:**
```bash
python scripts/setup.py
```

Choose option `2` when prompted for database type.

This will:
- ✅ Install PostgreSQL (if needed)
- ✅ Create database and user
- ✅ Configure credentials
- ✅ Run migrations
- ✅ Ready to use!

---

## For Existing Installations

**Migrate to PostgreSQL:**
```bash
python scripts/setup_postgresql.py
```

This preserves your existing `.env` and creates a backup.

---

## Manual PostgreSQL Setup

If you prefer to configure manually:

```bash
# Just setup database (PostgreSQL already installed)
python scripts/setup_postgresql.py --skip-install

# Force database recreation (destroys existing data!)
python scripts/setup_postgresql.py --force

# Custom database name/user
python scripts/setup_postgresql.py \
  --db-name my_db \
  --db-user my_user \
  --db-password my_password
```

---

## Startup Diagnostics

When you run `python app/run.py`, the application will:
1. ✅ Check database configuration
2. ✅ Verify PostgreSQL dependencies
3. ✅ Test database connection
4. ✅ Show helpful error messages if something is wrong

**Example startup output:**
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

---

## Switching Databases

### Switch to PostgreSQL
Edit `.env`:
```bash
DB_TYPE=postgresql
```

### Switch back to SQLite
Edit `.env`:
```bash
DB_TYPE=sqlite
```

**No code changes needed!** The application automatically adapts.

---

## What Was Added to `app/run.py`

The startup script now includes:

1. **Database Connection Check** (lines 30-88)
   - Detects PostgreSQL vs SQLite from `DB_TYPE`
   - Validates required environment variables
   - Tests database connection before server starts
   - Shows helpful error messages with fix suggestions

2. **Startup Diagnostics** (lines 110-121)
   - Logs database type and connection status
   - Exits with clear error if database is misconfigured
   - Prevents server startup with broken database

**Benefits:**
- ✅ Catch database issues before server starts
- ✅ Clear error messages guide users to fixes
- ✅ No more cryptic database errors during runtime
- ✅ New users get helpful setup instructions

---

## Automated PostgreSQL Setup Script

**Location:** `scripts/setup_postgresql.py`

**Features:**
- OS detection (Ubuntu, Debian, RedHat, CentOS, Fedora, macOS)
- Automatic PostgreSQL installation via package manager
- Secure random password generation
- Database and user creation
- `.env` configuration with backup
- Alembic migration execution
- Connection verification

**Supported Platforms:**
- ✅ Ubuntu/Debian (apt-get)
- ✅ RedHat/CentOS/Fedora (dnf)
- ✅ macOS (Homebrew)
- ⚠️ Windows (manual install, then --skip-install)

---

## Integration with Main Setup

**Location:** `scripts/setup.py`

**New database selection prompt:**
```
============================================================
Database Configuration
============================================================

AunooAI supports two database options:
1. SQLite (default) - Simple, file-based, good for development
2. PostgreSQL - Production-grade, better for concurrent users

Choose database (1 for SQLite, 2 for PostgreSQL) [1]:
```

**Workflow:**
1. Run `python scripts/setup.py`
2. Choose database type
3. If PostgreSQL selected, automatically runs `setup_postgresql.py`
4. If SQLite selected, configures `.env` with `DB_TYPE=sqlite`

---

## Documentation

**Comprehensive guide created:** `docs/POSTGRESQL_SETUP.md`

Includes:
- Quick start instructions
- Script options and flags
- Manual setup steps
- Troubleshooting guide
- Connection diagnostics
- Performance tuning
- Security best practices
- Migration from SQLite
- Benefits comparison

---

## Zero Code Changes Required

The PostgreSQL migration required **NO changes** to:
- ✅ Route files (38 files)
- ✅ Service files (16 files)
- ✅ Database query code
- ✅ Business logic

**Only changed:**
- `app/database.py` - Added PostgreSQL support via `DB_TYPE` check
- `app/config/settings.py` - Added `DatabaseSettings` class
- `app/database_async.py` - Fixed async pool
- `app/run.py` - Added startup diagnostics
- `.env` - Added PostgreSQL credentials

**Why it works:** The `Database` class abstraction allows switching databases by simply changing environment variables!

---

## For New AunooAI Deployments

**Recommended workflow:**
```bash
# 1. Clone repository
git clone <repo-url>
cd aunoo-ai

# 2. Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# or: .venv\Scripts\activate  # Windows

# 3. Run setup (includes database choice)
python scripts/setup.py

# 4. Start application
python app/run.py
```

**The setup script will:**
1. Install FFmpeg
2. Install Python dependencies
3. Create required directories
4. **Prompt for database type (NEW!)**
5. Setup chosen database automatically
6. Ready to run!

---

## Testing the Changes

To test the new PostgreSQL setup on a fresh system:

```bash
# Test automated PostgreSQL setup
python scripts/setup_postgresql.py

# Test startup diagnostics
python app/run.py

# Test with missing dependencies
pip uninstall asyncpg -y
python app/run.py  # Should show helpful error

# Test with wrong password
# Edit .env and change DB_PASSWORD to wrong value
python app/run.py  # Should show connection error

# Test SQLite fallback
# Edit .env: DB_TYPE=sqlite
python app/run.py  # Should work with SQLite
```

---

## Summary of Automation

### What's Automated:
✅ PostgreSQL installation (OS-specific)
✅ Database and user creation
✅ Secure password generation
✅ `.env` configuration
✅ Python dependency installation
✅ Database migration execution
✅ Connection verification
✅ Startup diagnostics
✅ Helpful error messages

### What Users Need to Do:
1. Run `python scripts/setup.py` (or `setup_postgresql.py`)
2. That's it!

**No manual PostgreSQL configuration needed for 90% of use cases.**

---

## Files Modified/Created

### Modified:
- `app/run.py` - Added database diagnostics (lines 16-21, 30-88, 110-121)
- `scripts/setup.py` - Added database selection prompt (lines 72-139)

### Created:
- `scripts/setup_postgresql.py` - Automated PostgreSQL setup (445 lines)
- `docs/POSTGRESQL_SETUP.md` - Comprehensive documentation (700+ lines)
- `README_POSTGRESQL.md` - This quick reference

---

## Next Steps

After PostgreSQL is working:

**Optional improvements** (see docs for details):
1. SQLAlchemy migration - Better code quality (15-20 hours)
2. Async migration - Maximum performance (9 hours)

**Both are optional.** Your application is production-ready now!

---

## Support

**Issues with setup:**
```bash
# Run with verbose output
python scripts/setup_postgresql.py 2>&1 | tee setup.log
```

**Issues with startup:**
```bash
# Run server and capture logs
python app/run.py 2>&1 | tee startup.log
```

Include these logs in bug reports.

**Database connection issues:**
Check PostgreSQL status:
```bash
sudo systemctl status postgresql
```

View PostgreSQL logs:
```bash
sudo journalctl -u postgresql -n 50
```

---

**Questions? See full documentation:** `docs/POSTGRESQL_SETUP.md`
