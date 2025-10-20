# pgvector HNSW Index - Automatic Deployment Guide

## 🎯 Summary

The HNSW vector index is now **automatically created on all new deployments** via Alembic migrations.

**Migration File:** `alembic/versions/e0aa2eb4fa0a_add_hnsw_vector_index.py`

---

## 📦 How It Works on New Deployments

### 1. **Docker Deployments** (Automatic)
**File:** `docker-entrypoint.sh` (lines 79-87)

```bash
echo "Running database migrations..."
if ! alembic upgrade head; then
  echo "❌ ERROR: Database migrations FAILED!"
  exit 1
fi
echo "✅ Database migrations completed successfully"
```

**Process:**
1. Container starts
2. Waits for PostgreSQL to be ready
3. **Automatically runs:** `alembic upgrade head`
4. Applies all pending migrations including HNSW index
5. Exits if migrations fail (safety)

**No manual intervention required** ✅

---

### 2. **Manual Deployments**

For non-Docker deployments, run migrations manually:

```bash
# Activate virtual environment
source .venv/bin/activate

# Run migrations
alembic upgrade head
```

Or use the wrapper script:
```bash
python run_migration.py
```

---

## 🔍 Migration Details

### What Gets Created
```sql
CREATE INDEX IF NOT EXISTS articles_embedding_hnsw_idx
ON articles
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
```

### Index Parameters
- **Type:** HNSW (Hierarchical Navigable Small World)
- **Distance Metric:** Cosine distance (`<=>` operator)
- **m=16:** Connections per layer (optimal for 1536-dim embeddings)
- **ef_construction=64:** Build quality (higher = better accuracy, slower build)

### Performance Impact
- **10-100x faster** vector searches at scale
- Automatic usage by PostgreSQL query planner
- Scales efficiently with growing datasets

---

## ✅ Verification

### Check if Migration Applied
```bash
# Method 1: Via Alembic
alembic current

# Should show: e0aa2eb4fa0a (head), add_hnsw_vector_index
```

### Check if Index Exists
```sql
-- Connect to database
psql -U <user> -d <database> -h <host>

-- List indexes
\di articles_embedding_hnsw_idx

-- Or via SQL
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'articles' AND indexname LIKE '%hnsw%';
```

**Expected output:**
```
indexname                    | indexdef
-----------------------------+------------------------------------------------
articles_embedding_hnsw_idx  | CREATE INDEX ... USING hnsw (embedding vector_cosine_ops) ...
```

---

## 🏗️ Existing Instances

### For Already Deployed Instances

The migration is **idempotent** (safe to run multiple times), so just run:

```bash
alembic upgrade head
```

If the index already exists (like on the current instance where we created it manually), it will skip creation with a harmless notice:

```
NOTICE: relation "articles_embedding_hnsw_idx" already exists, skipping
```

---

## 🔄 Rollback (If Needed)

If you need to remove the index:

```bash
# Via Alembic
alembic downgrade -1

# Or manually via SQL
DROP INDEX IF EXISTS articles_embedding_hnsw_idx;
```

**Warning:** Rolling back will cause **significant performance degradation** for vector searches.

---

## 📋 Deployment Checklist

### For New Tenants/Instances:
- [ ] Deploy application code with migration file
- [ ] Ensure PostgreSQL 14+ with pgvector extension
- [ ] Run `alembic upgrade head` (or start Docker container)
- [ ] Verify index exists (see Verification section)
- [ ] Monitor query performance logs

### For Existing Instances:
- [ ] Pull latest code with migration file
- [ ] Run `alembic upgrade head`
- [ ] Verify index created successfully
- [ ] No restart required (hot migration)

---

## 🐛 Troubleshooting

### Issue: "relation already exists"
**Status:** ✅ **Safe to ignore** - means index already created manually or in previous run.

### Issue: "extension 'vector' does not exist"
**Solution:**
```sql
-- Connect as superuser
psql -U postgres -d <database>

-- Enable extension
CREATE EXTENSION IF NOT EXISTS vector;
```

### Issue: Alembic migration fails
**Check:**
1. Database connection credentials in `.env`
2. PostgreSQL version (must be 14+)
3. pgvector extension installed
4. Migration file integrity

**Debug:**
```bash
# Check Alembic config
alembic history

# Verbose migration
alembic upgrade head --sql  # Shows SQL without executing
```

---

## 📊 Performance Monitoring

### Verify Index Usage
```sql
EXPLAIN ANALYZE
SELECT uri, (embedding <=> '[0.1,0.2,...]'::vector) as distance
FROM articles
WHERE embedding IS NOT NULL
ORDER BY embedding <=> '[0.1,0.2,...]'::vector
LIMIT 10;
```

**Look for:**
- ✅ `Index Scan using articles_embedding_hnsw_idx` (good!)
- ❌ `Seq Scan on articles` (bad - index not being used)

### Index Statistics
```sql
SELECT
    schemaname,
    tablename,
    indexname,
    idx_scan as index_scans,
    idx_tup_read as tuples_read,
    idx_tup_fetch as tuples_fetched
FROM pg_stat_user_indexes
WHERE indexname = 'articles_embedding_hnsw_idx';
```

---

## 🔗 Related Files

| File | Purpose |
|------|---------|
| `alembic/versions/e0aa2eb4fa0a_add_hnsw_vector_index.py` | Migration definition |
| `docker-entrypoint.sh` | Automatic migration execution |
| `alembic.ini` | Alembic configuration |
| `alembic/env.py` | Migration environment setup |
| `run_migration.py` | Manual migration wrapper |

---

## 🎓 Migration System Overview

### Migration Chain
```
d8d9cdcec340 (Initial PostgreSQL schema)
    ↓
1745b4f22f68 (Article analysis cache)
    ↓
8eadb2079747 (Add pgvector support)
    ↓
b6a5ff4214f5 (Add incident status table)
    ↓
e0aa2eb4fa0a (Add HNSW index) ← NEW
```

### How Alembic Tracks State
- Creates `alembic_version` table in database
- Stores current migration revision
- Applies only **new** migrations on `upgrade head`
- **Idempotent by design** - safe to run repeatedly

---

## ✅ Success Criteria

Your deployment is successful when:

1. ✅ `alembic current` shows `e0aa2eb4fa0a (head)`
2. ✅ Index exists in `\di` output
3. ✅ Vector queries use index (check with `EXPLAIN ANALYZE`)
4. ✅ No errors in application logs
5. ✅ Page loads are fast and non-blocking

---

## 📞 Support

If issues arise:

1. **Check migration status:** `alembic current`
2. **Check database logs:** `journalctl -u postgresql -n 100`
3. **Manual index creation:** Run SQL from migration file directly
4. **Verify pgvector:** `SELECT * FROM pg_extension WHERE extname = 'vector';`

---

**Last Updated:** 2025-10-20
**Migration Version:** e0aa2eb4fa0a
**Deployment Method:** Automatic via Alembic

