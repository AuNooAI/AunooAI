# Real-time Signals Date Query Fix - Technical Notes

**Date**: 2025-10-10
**Issue**: Real-time signals returning 0 results due to date format mismatch
**Fixed in**: `/app/routes/vector_routes.py` line 2742

---

## Problem Summary

The `run_signal_instructions` endpoint at `/api/run-signals` was returning 0 articles because the date comparison in the SQL query was failing due to format mismatch between Python's `.isoformat()` output and the database TEXT field format.

### Database Schema Issue

The `articles` table has `publication_date` as **TEXT** (not TIMESTAMP/DATE):

```sql
Column: publication_date | Type: text | Nullable: yes
```

**Current Data Formats in Database**:
- Date only: `2025-10-07`
- DateTime: `2025-10-07 22:40:43` (space separator)
- Empty/NULL: 887 articles have NULL publication_date

**Total Articles with Required Fields**: 18,012 articles have publication_date, category, and sentiment populated.

---

## Solution Implemented (Option 1)

### Change Made
**File**: `/app/routes/vector_routes.py`
**Line**: 2742 (previously 2739)

**Before**:
```python
params = [start_date_dt.isoformat(), end_date_dt.isoformat()]
# Produces: ['2025-10-03T00:00:00', '2025-10-10T13:53:04.123456']
```

**After**:
```python
params = [start_date_dt.strftime('%Y-%m-%d'), end_date_dt.strftime('%Y-%m-%d %H:%M:%S')]
# Produces: ['2025-10-03', '2025-10-10 13:53:04']
```

### Why This Works

PostgreSQL TEXT comparison with `>=` and `<=` operators performs **lexicographical** (alphabetical) comparison:

- ✅ `'2025-10-07'` >= `'2025-10-03'` → TRUE
- ✅ `'2025-10-07 22:40:43'` <= `'2025-10-10 13:53:04'` → TRUE
- ❌ `'2025-10-07'` >= `'2025-10-03T00:00:00'` → FALSE (space sorts before 'T')

The 'T' character (ASCII 84) sorts **after** space (ASCII 32) and digits (ASCII 48-57), causing all database dates to fail the comparison.

---

## Alternative Solution (Option 2 - NOT Implemented)

### Option 2A: Cast to TIMESTAMP in Query

**Approach**: Cast the TEXT field to TIMESTAMP for proper date comparison.

**Implementation** (PostgreSQL-specific):
```python
query = """
SELECT uri, title, summary, news_source, publication_date, category, sentiment
FROM articles
WHERE CAST(publication_date AS TIMESTAMP) >= CAST(:start_date AS TIMESTAMP)
  AND CAST(publication_date AS TIMESTAMP) <= CAST(:end_date AS TIMESTAMP)
AND category IS NOT NULL AND sentiment IS NOT NULL
"""

params = {
    'start_date': start_date_dt.strftime('%Y-%m-%d %H:%M:%S'),
    'end_date': end_date_dt.strftime('%Y-%m-%d %H:%M:%S')
}
```

**Challenges**:
1. Requires changing from positional (`?`) to named (`:param`) placeholders
2. The `db.fetch_all()` method uses SQLite-style `?` placeholders that get converted to PostgreSQL `$1, $2` format
3. CAST will fail on NULL or empty string values (887 articles have NULL publication_date)
4. Requires error handling for invalid date strings

**Modified Query with NULL Handling**:
```sql
WHERE (publication_date IS NOT NULL
       AND publication_date != ''
       AND CAST(publication_date AS TIMESTAMP) >= CAST(:start_date AS TIMESTAMP)
       AND CAST(publication_date AS TIMESTAMP) <= CAST(:end_date AS TIMESTAMP))
```

### Option 2B: Create Database Migration

**Long-term Solution**: Alter the table to use proper TIMESTAMP type.

**Migration Script** (Alembic):
```python
"""Convert publication_date to TIMESTAMP

Revision ID: convert_publication_date_timestamp
"""
from alembic import op
import sqlalchemy as sa

def upgrade():
    # Add new column
    op.add_column('articles', sa.Column('publication_date_ts', sa.DateTime(), nullable=True))

    # Migrate data with error handling
    op.execute("""
        UPDATE articles
        SET publication_date_ts = CAST(publication_date AS TIMESTAMP)
        WHERE publication_date IS NOT NULL
          AND publication_date != ''
          AND publication_date ~ '^\d{4}-\d{2}-\d{2}'
    """)

    # Drop old column and rename new one
    op.drop_column('articles', 'publication_date')
    op.alter_column('articles', 'publication_date_ts', new_column_name='publication_date')

    # Create index for performance
    op.create_index('idx_articles_publication_date', 'articles', ['publication_date'])

def downgrade():
    op.alter_column('articles', 'publication_date', type_=sa.Text())
```

**Impact Analysis**:
- **Affected Records**: 18,012 articles with valid dates
- **NULL Records**: 887 articles remain NULL (acceptable)
- **Performance**: Index on TIMESTAMP column improves query performance
- **Breaking Changes**: Any code using TEXT comparison must be updated

**Other Affected Queries** (requires audit):
```bash
grep -r "publication_date.*>=" /home/orochford/tenants/skunkworkx.aunoo.ai/app/
grep -r "publication_date.*<=" /home/orochford/tenants/skunkworkx.aunoo.ai/app/
grep -r "ORDER BY publication_date" /home/orochford/tenants/skunkworkx.aunoo.ai/app/
```

---

## Testing the Fix

### Test Query (PostgreSQL)
```sql
-- Should return 1048 articles for last 7 days
SELECT COUNT(*)
FROM articles
WHERE publication_date >= '2025-10-03'
  AND publication_date <= '2025-10-10 23:59:59'
  AND category IS NOT NULL
  AND sentiment IS NOT NULL;
```

### Test Signal Instruction via API
```bash
# 1. Create a test signal instruction
curl -X POST http://localhost:PORT/api/signal-instructions \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Signal",
    "description": "Test description",
    "instruction": "Flag any articles mentioning AI or technology",
    "topic": "",
    "is_active": true
  }'

# 2. Run the signal
curl -X POST http://localhost:PORT/api/run-signals \
  -H "Content-Type: application/json" \
  -d '{
    "instruction_ids": [1],
    "topic": null,
    "days_back": 7,
    "max_articles": 100,
    "model": "gpt-4o-mini",
    "tag_flagged_articles": true
  }'

# Expected: Should return matches instead of 0 results
```

### Frontend Test
1. Navigate to News Feed → Narrative Explorer → Real-time Signals
2. Click "Add Signal" and create a test instruction
3. Set "Days Back" to 7
4. Click "Run All" button
5. Verify alerts are generated and displayed

---

## Related Issues

### Empty publication_date Values
**Count**: 887 articles have NULL publication_date

**Query to Identify**:
```sql
SELECT uri, title, news_source, submission_date
FROM articles
WHERE publication_date IS NULL OR publication_date = ''
LIMIT 10;
```

**Recommendation**: Implement a data cleanup job to:
1. Use `submission_date` as fallback if available
2. Parse dates from article metadata
3. Mark articles without dates for manual review

### Other Date Comparisons
Search for similar issues in other routes:
```bash
grep -n "\.isoformat()" /home/orochford/tenants/skunkworkx.aunoo.ai/app/routes/*.py
```

**Potentially Affected Routes**:
- Article filtering in `/api/articles`
- Feed generation in `/api/news-feed`
- Analytics date ranges
- Incident tracking time windows

---

## Performance Considerations

### Current Approach (Option 1)
- **Query Performance**: TEXT comparison with `>=`/`<=` is **slower** than TIMESTAMP comparison
- **Index Usage**: No index on `publication_date` (TEXT column)
- **Impact**: Minimal for queries under 100K rows

### With TIMESTAMP Migration (Option 2B)
- **Query Performance**: Native TIMESTAMP comparison is faster
- **Index Usage**: B-tree index on TIMESTAMP enables efficient range scans
- **Impact**: 10-100x faster for large date range queries

### Benchmark (Estimated)
```
TEXT comparison (current):     ~50-100ms for 20K rows
TIMESTAMP comparison:          ~5-10ms for 20K rows
With index:                    ~1-2ms for 20K rows
```

---

## Recommendations

### Immediate (Completed)
- ✅ Fix date format in signal query (Option 1 implemented)

### Short-term (Next Sprint)
1. Audit all date comparisons across codebase
2. Add data validation for publication_date on article ingestion
3. Create cleanup job for NULL publication_dates

### Long-term (Technical Debt)
1. Migrate `publication_date` column to TIMESTAMP type
2. Add database constraints for date validity
3. Create composite index on (publication_date, category, sentiment)
4. Update ORM models to use proper DateTime types

---

## References

- PostgreSQL TEXT comparison: https://www.postgresql.org/docs/current/functions-comparison.html
- Python datetime.isoformat(): https://docs.python.org/3/library/datetime.html#datetime.datetime.isoformat
- SQLAlchemy type casting: https://docs.sqlalchemy.org/en/20/core/type_api.html
- Alembic migrations: https://alembic.sqlalchemy.org/en/latest/tutorial.html

---

## Change Log

| Date | Change | Author | Notes |
|------|--------|--------|-------|
| 2025-10-10 | Fixed date format in run_signals endpoint | Claude Code | Option 1 implementation |
