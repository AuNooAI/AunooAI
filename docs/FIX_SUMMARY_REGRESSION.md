# Fix: AI Summary Regression Issue

## Problem
Articles on mariam.aunoo.ai instance were displaying NewsAPI descriptions instead of AI-generated summaries, despite having correct AI-generated metadata (sentiment, time_to_impact, etc.).

## Root Cause
Bug in `app/services/automated_ingest_service.py` at two locations:
- Line 241: `analyze_article_content()` method
- Line 661: `_analyze_article_content_async()` method

Both methods were extracting analysis results from ArticleAnalyzer but **omitted the 'summary' field**. They extracted all other AI metadata (sentiment, category, time_to_impact, driver_type, tags) but discarded the AI-generated summary, leaving articles with their original NewsAPI descriptions.

## Fix Applied
Added `'summary': analysis_result.get('summary')` to both update calls in `automated_ingest_service.py`:

**Lines 241-251** (sync version):
```python
article_data.update({
    'summary': analysis_result.get('summary'),  # ✅ CRITICAL: Include AI-generated summary
    'category': analysis_result.get('category'),
    'sentiment': analysis_result.get('sentiment'),
    'future_signal': analysis_result.get('future_signal'),
    'future_signal_explanation': analysis_result.get('future_signal_explanation'),
    'sentiment_explanation': analysis_result.get('sentiment_explanation'),
    'time_to_impact': analysis_result.get('time_to_impact'),
    'driver_type': analysis_result.get('driver_type'),
    'tags': tags_str,
    'analyzed': True
})
```

**Lines 661-671** (async version - same fix)

Also added `summary_length` to debug logging at both locations for easier troubleshooting.

## Testing
Both article ingestion pathways verified working:

### 1. bulk_research.py pathway (manual analysis)
```bash
source .venv/bin/activate
python scripts/test_summary_update.py
```
**Result**: ✅ SUCCESS - Summary updated from 316 → 294 chars

### 2. automated_ingest_service.py pathway (auto-ingest)
```bash
source .venv/bin/activate
python scripts/test_auto_ingest_summary.py
```
**Result**: ✅ SUCCESS - Summary extracted from 90 → 311 chars

## Deployment to mariam.aunoo.ai

### Step 1: Deploy Fixed Code
```bash
# On mariam.aunoo.ai instance
cd /home/orochford/tenants/mariam.aunoo.ai
git pull origin postgres_final_candidate_1
sudo systemctl restart aunooai-mariam
```

### Step 2: Verify Service is Running
```bash
sudo systemctl status aunooai-mariam
sudo journalctl -u aunooai-mariam -f
```

### Step 3: Repair Existing Articles (Optional)
Run the repair script to fix articles that were analyzed before the fix:

```bash
cd /home/orochford/tenants/mariam.aunoo.ai
source .venv/bin/activate

# Dry run first to see what will be fixed
python scripts/fix_missing_summaries.py --days 30 --limit 100

# Actually fix the articles
python scripts/fix_missing_summaries.py --days 30 --limit 100 --fix --yes
```

**Script parameters**:
- `--days N`: Check articles from last N days (default: 7)
- `--limit N`: Maximum articles to fix (default: 100)
- `--fix`: Actually fix articles (without this, it's a dry run)
- `--yes`: Skip confirmation prompt

### Step 4: Verify Fix
1. Check that new articles ingested through keyword monitoring have AI-generated summaries
2. Check that repaired articles show proper summaries in the UI
3. Monitor logs for "summary_length=" in analysis debug logs

## Technical Details

### Two Article Ingestion Pathways
The system has two pathways for ingesting articles:

1. **Manual/Bulk Analysis** (`bulk_research.py`)
   - Used by repair scripts and manual bulk analysis
   - Was working correctly (not affected by bug)
   - Calls `ArticleAnalyzer.analyze_content()` and correctly extracts all fields

2. **Automated Keyword Monitoring** (`automated_ingest_service.py`)
   - Used by keyword monitoring → auto-ingest pipeline
   - Had the bug (fixed in this commit)
   - Calls `ArticleAnalyzer.analyze_content()` but was not extracting summary field

### Why Some Articles Appeared Fixed
- Articles analyzed through bulk_research.py (repair scripts) had correct summaries
- Articles analyzed through automated_ingest_service.py (keyword monitoring) had NewsAPI descriptions
- This is why skunkworkx appeared fixed (repair scripts run) but mariam showed the problem (new deployment, auto-ingest active, no repairs run)

## Files Changed
- `app/services/automated_ingest_service.py`: Added summary field extraction at 2 locations
- `scripts/test_auto_ingest_summary.py`: New test script to verify the fix

## Commit Information
- Branch: `postgres_final_candidate_1`
- Fix commit: [This commit]
- Original issue commit: 19e603b (only added topic field, missed summary)

## Prevention
- Added test script `scripts/test_auto_ingest_summary.py` to verify summary extraction
- Added summary_length to debug logs for easier monitoring
- Both ingestion pathways now tested and verified

## Related Issues
- Commit 19e603b: Added `result["topic"] = topic` but missed summary field
- The repair scripts (fix_missing_summaries.py, clear_bad_cache.py) were treating symptoms, not root cause
