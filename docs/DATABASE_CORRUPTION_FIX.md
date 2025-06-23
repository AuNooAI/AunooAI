# Database Corruption Fix Guide

## Problem Description

The application may encounter SQLite database corruption, typically manifesting as:

```
sqlite3.DatabaseError: database disk image is malformed
```

This error occurs when:
- The SQLite database file becomes corrupted
- File system issues affect the database
- Improper shutdowns or disk space issues
- Cross-platform file transfers that don't preserve file integrity

## Common Error Locations

1. **Database initialization** - When setting WAL (Write-Ahead Logging) mode
2. **Article queries** - When reading from corrupted tables
3. **User authentication** - When accessing user data

## Quick Fix

### Automated Recovery

Run the database corruption fix script:

```bash
# From the project root directory
python scripts/fix_database_corruption.py
```

The script will:
1. **Detect corruption** - Check database integrity
2. **Backup corrupted DB** - Create timestamped backup
3. **Attempt recovery** - Try to salvage existing data
4. **Create fresh DB** - Initialize clean database if recovery fails

### Manual Steps

If the automated script doesn't work:

1. **Stop the application**
2. **Backup the corrupted database**:
   ```bash
   cp app/data/fnaapp.db app/data/fnaapp.db.backup_$(date +%Y%m%d_%H%M%S)
   ```

3. **Remove corrupted database**:
   ```bash
   rm app/data/fnaapp.db
   ```

4. **Start the application** - A fresh database will be created automatically

## Recovery Options

### Option 1: Automatic Recovery (Recommended)

```bash
python scripts/fix_database_corruption.py
```

**What it does:**
- Checks database integrity
- Attempts SQLite backup/restore
- Tries table-by-table data recovery
- Creates fresh database if recovery fails
- Preserves corrupted database as backup

### Option 2: Manual Recovery

1. **Use SQLite recovery tools**:
   ```bash
   # Try to dump data from corrupted DB
   sqlite3 app/data/fnaapp.db ".dump" > recovery.sql
   
   # Create new database from dump
   sqlite3 app/data/fnaapp_new.db < recovery.sql
   
   # Replace corrupted database
   mv app/data/fnaapp.db app/data/fnaapp.db.corrupted
   mv app/data/fnaapp_new.db app/data/fnaapp.db
   ```

2. **Use external recovery tools**:
   - SQLite Repair Kit
   - DB Browser for SQLite repair function
   - sqlite3_analyzer

### Option 3: Fresh Start

If data recovery isn't critical:

```bash
# Remove corrupted database
rm app/data/fnaapp.db

# Remove WAL and SHM files if they exist
rm -f app/data/fnaapp.db-wal app/data/fnaapp.db-shm

# Start application - fresh database will be created
python app/server_run.py
```

## Prevention

### 1. Regular Backups

Add to your deployment script:

```bash
# Create daily backups
cp app/data/fnaapp.db app/data/backups/fnaapp_$(date +%Y%m%d).db

# Keep only last 7 days
find app/data/backups -name "fnaapp_*.db" -mtime +7 -delete
```

### 2. Proper Shutdown

Always shutdown the application gracefully:
- Use SIGTERM instead of SIGKILL
- Allow database connections to close properly
- Ensure sufficient disk space

### 3. File System Monitoring

Monitor for:
- Disk space warnings
- File system errors
- Hardware issues

### 4. Database Health Checks

Add to monitoring:

```python
def check_database_health():
    try:
        conn = sqlite3.connect('app/data/fnaapp.db')
        cursor = conn.cursor()
        cursor.execute("PRAGMA integrity_check")
        result = cursor.fetchone()
        return result[0] == 'ok'
    except Exception:
        return False
```

## Technical Details

### WAL Mode Issues

The error often occurs when enabling WAL (Write-Ahead Logging) mode:
```sql
PRAGMA journal_mode = WAL;
```

WAL mode benefits:
- Better concurrency
- Atomic commits
- Crash recovery

But requires:
- Intact database file
- Proper file permissions
- Sufficient disk space

### Database Structure

The application uses these key tables:
- `users` - User authentication
- `articles` - Article data and analysis
- `raw_articles` - Original article content
- `keyword_alerts` - Monitoring alerts
- `podcasts` - Generated podcasts

### Recovery Priorities

1. **Users table** - Critical for authentication
2. **Articles table** - Main application data
3. **Configuration tables** - Settings and preferences
4. **Temporary tables** - Can be recreated

## Error Messages and Solutions

### "database disk image is malformed"
- **Cause**: File corruption
- **Solution**: Run fix script or restore from backup

### "database is locked"
- **Cause**: Multiple connections or improper shutdown
- **Solution**: Kill all processes, remove lock files

### "no such table"
- **Cause**: Incomplete migration or corruption
- **Solution**: Run database initialization

### "UNIQUE constraint failed"
- **Cause**: Data integrity issues during recovery
- **Solution**: Clean duplicates before restore

## Testing Recovery

After fixing corruption:

1. **Check application startup**:
   ```bash
   python app/server_run.py
   ```

2. **Verify login**:
   - Username: `admin`
   - Password: `admin`
   - Should prompt for password change

3. **Test basic functionality**:
   - Add a test article
   - Run analytics
   - Check database queries

## Monitoring

Set up alerts for:
- Database connection failures
- WAL mode failures
- Disk space warnings
- File system errors

## Related Files

- `scripts/fix_database_corruption.py` - Automated fix script
- `app/database.py` - Database connection logic
- `app/config/settings.py` - Database configuration
- `app/data/` - Database directory 