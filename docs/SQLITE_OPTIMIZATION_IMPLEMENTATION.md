# SQLite Performance Optimization Implementation

## Overview

This document describes the comprehensive SQLite performance optimizations implemented to resolve file locking issues and improve concurrent database access performance.

## Problem Statement

The application was experiencing file locking issues during background collection tasks, causing users to be frozen out of the app. The main issues were:

1. **Single write process limitation** - SQLite only supports one write process at a time
2. **Blocking transactions** - `BEGIN IMMEDIATE` transactions were blocking other operations
3. **WAL mode not optimally configured** - WAL was enabled but not properly tuned
4. **Long-running background tasks** - Held database connections for extended periods
5. **Missing SQLite optimizations** - Not using performance tuning recommendations

## Implemented Optimizations

### 1. Enhanced SQLite Configuration

**File**: `app/database.py`

Applied all optimizations from the [SQLite performance tuning article](https://phiresky.github.io/blog/2020/sqlite-performance-tuning/):

```python
# Core WAL mode configuration
PRAGMA journal_mode = WAL
PRAGMA synchronous = NORMAL
PRAGMA temp_store = MEMORY

# Performance optimizations
PRAGMA mmap_size = 30000000000  # 30GB memory mapping
PRAGMA page_size = 32768        # Larger page size
PRAGMA cache_size = 50000       # 50MB cache (increased from 10MB)
PRAGMA busy_timeout = 30000     # 30 second timeout
PRAGMA wal_autocheckpoint = 1000 # More frequent checkpoints
PRAGMA optimize                 # Run query optimizer
```

**Benefits**:
- **Memory mapping**: Reduces syscalls and improves I/O performance
- **Larger page size**: Better performance for larger data operations
- **Increased cache**: More data kept in memory
- **Frequent checkpoints**: Prevents WAL file from growing indefinitely

### 2. Fixed Transaction Blocking

**File**: `app/database_query_facade.py`

**Change**: Replaced `BEGIN IMMEDIATE` with regular `BEGIN`

```python
# Before (blocking)
conn.execute("BEGIN IMMEDIATE")

# After (non-blocking)
conn.execute("BEGIN")
```

**Benefits**:
- **Non-blocking transactions**: Allows concurrent readers during writes
- **Better concurrency**: Multiple processes can access database simultaneously
- **Reduced lock contention**: Less aggressive locking behavior

### 3. Connection Pooling and Timeout Management

**File**: `app/database.py`

**Features Added**:
- **Connection pool limits**: Maximum 20 concurrent connections
- **Retry logic**: 3 attempts with 5-second timeout
- **Stale connection cleanup**: Automatic cleanup of dead thread connections
- **Connection timeout**: 5-second timeout for new connections

```python
# Connection pool settings
MAX_CONNECTIONS = 20
CONNECTION_TIMEOUT = 5  # seconds
RETRY_ATTEMPTS = 3

# Retry logic for locked database
if "database is locked" in str(e).lower() and attempt < self.RETRY_ATTEMPTS - 1:
    logger.warning(f"Database locked, retrying in {self.CONNECTION_TIMEOUT}s")
    time.sleep(self.CONNECTION_TIMEOUT)
    continue
```

**Benefits**:
- **Resource management**: Prevents connection exhaustion
- **Automatic recovery**: Handles temporary lock situations
- **Better error handling**: Graceful degradation under load

### 4. WAL Checkpoint Management

**File**: `app/database.py`

**Features Added**:
- **Periodic checkpoints**: Automatic WAL checkpointing
- **Multiple checkpoint modes**: PASSIVE, FULL, RESTART
- **WAL monitoring**: Track WAL file status
- **Final checkpoint**: Clean shutdown with FULL checkpoint

```python
def perform_wal_checkpoint(self, mode="PASSIVE"):
    """Perform WAL checkpoint to prevent WAL file from growing indefinitely"""
    cursor.execute(f"PRAGMA wal_checkpoint({mode})")
    return cursor.fetchone()
```

**Benefits**:
- **Prevents WAL growth**: Keeps WAL file size manageable
- **Better performance**: Regular checkpointing improves read performance
- **Data safety**: Ensures data is properly committed to main database

### 5. Background Task Optimization

**File**: `app/tasks/keyword_monitor.py`

**Features Added**:
- **Periodic WAL checkpoints**: Every 5 minutes during background tasks
- **Post-operation checkpoints**: After successful keyword checks
- **Shorter transactions**: Individual article processing
- **Better error handling**: Graceful handling of checkpoint failures

```python
# Track checkpoint intervals
last_checkpoint = datetime.now()
checkpoint_interval = 300  # 5 minutes

# Perform periodic WAL checkpoint
if (current_time - last_checkpoint).total_seconds() >= checkpoint_interval:
    db.perform_wal_checkpoint("PASSIVE")
    last_checkpoint = current_time
```

**Benefits**:
- **Reduced blocking**: Shorter transactions reduce lock time
- **Better resource usage**: Regular checkpoints prevent resource buildup
- **Improved reliability**: Better error handling and recovery

## Performance Improvements Expected

Based on the SQLite tuning article and optimizations implemented:

1. **Concurrent Access**: Multiple readers can access database during writes
2. **Reduced Locking**: Non-blocking transactions reduce contention
3. **Better I/O Performance**: Memory mapping reduces syscalls
4. **Improved Caching**: Larger cache keeps more data in memory
5. **WAL Management**: Prevents WAL file from growing indefinitely
6. **Connection Efficiency**: Better connection pooling and timeout handling

## Testing and Validation

### Test Scripts Created

1. **`scripts/test_sqlite_performance.py`**
   - Tests connection pooling
   - Validates WAL checkpoint functionality
   - Tests concurrent write operations
   - Tests database locking behavior
   - Verifies SQLite pragma settings

2. **`scripts/apply_sqlite_optimizations.py`**
   - Applies optimizations to existing databases
   - Creates backups before optimization
   - Runs VACUUM and ANALYZE
   - Verifies optimization settings

### Running Tests

```bash
# Apply optimizations to existing databases
python scripts/apply_sqlite_optimizations.py

# Test performance improvements
python scripts/test_sqlite_performance.py
```

## Deployment Instructions

### 1. Deploy Code Changes

The optimizations are automatically applied when the application starts. No additional configuration is required.

### 2. Apply to Existing Databases

Run the optimization script to apply settings to existing databases:

```bash
python scripts/apply_sqlite_optimizations.py
```

### 3. Restart Application

Restart the application to use the optimized database connections.

### 4. Monitor Performance

- Monitor application logs for reduced locking errors
- Check WAL file sizes (should remain manageable)
- Monitor user experience for reduced freezing

## Monitoring and Maintenance

### Key Metrics to Monitor

1. **Database Lock Errors**: Should be significantly reduced
2. **WAL File Size**: Should remain stable and not grow indefinitely
3. **Connection Pool Usage**: Should stay within limits
4. **User Experience**: Reduced freezing during background tasks

### Maintenance Tasks

1. **Regular VACUUM**: Run periodically to optimize database
2. **Monitor WAL Checkpoints**: Ensure they're running regularly
3. **Connection Pool Health**: Monitor for stale connections

## Troubleshooting

### Common Issues

1. **WAL File Growing Large**
   - Check if checkpoints are running
   - Verify no long-running transactions
   - Run manual checkpoint if needed

2. **Connection Pool Exhaustion**
   - Check for connection leaks
   - Verify stale connection cleanup
   - Consider increasing pool size if needed

3. **Performance Not Improved**
   - Verify all pragmas are set correctly
   - Check if optimizations were applied
   - Run performance test script

### Recovery Procedures

1. **Database Corruption**
   - Use backup created by optimization script
   - Run database repair script if available

2. **WAL Issues**
   - Run `PRAGMA wal_checkpoint(FULL)`
   - Consider restarting application

## Future Considerations

### PostgreSQL Migration

If SQLite optimizations are insufficient for future growth:

1. **Benefits of PostgreSQL**:
   - True concurrent writes
   - Better performance under high load
   - Advanced features (JSON, full-text search)
   - Better scalability

2. **Migration Effort**: 2-3 weeks
   - Schema migration
   - Code changes
   - Testing and deployment

### Additional Optimizations

1. **Query Optimization**: Review and optimize slow queries
2. **Index Optimization**: Add missing indexes
3. **Connection Pooling**: Consider external connection pooler
4. **Read Replicas**: For read-heavy workloads

## Conclusion

The implemented SQLite optimizations should significantly reduce file locking issues and improve concurrent database access. The changes are:

- **Low risk**: No data migration required
- **Immediate benefit**: Applied on next restart
- **Comprehensive**: Addresses all major performance bottlenecks
- **Well-tested**: Includes validation scripts

Monitor the application after deployment to validate the improvements and consider PostgreSQL migration if additional performance gains are needed.
