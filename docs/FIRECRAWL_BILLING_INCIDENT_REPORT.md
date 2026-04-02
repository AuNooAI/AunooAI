# Firecrawl Billing Incident Report

**Date:** 2026-03-23
**Severity:** High (cost impact)
**Affected Key:** `fc-bdda86e2178242ccb47c050cc4b5f69d`
**Status:** Partially remediated (test scrapes eliminated; batch volume issue outstanding)

---

## Summary

Firecrawl reported hundreds of thousands of scrapes on the above API key. Investigation traced the root cause to **opendemo.aunoo.ai**, which was generating approximately **93,000 Firecrawl API calls per day**. Three compounding issues were identified: wasted test scrapes (~23k/day), uncached Research instances creating redundant inits, and a keyword monitor running in a tight loop that re-scrapes the same article pool repeatedly (~70k/day).

## Timeline

- **March 18:** ~356 articles ingested on opendemo (normal baseline)
- **March 19:** ~4,235 articles ingested on opendemo (10x spike)
- **March 20–23:** Sustained elevated ingestion (900–1,500 articles/day)
- **March 23:** Issue identified and remediated

## Affected Tenants

Five tenants share the affected API key:

| Tenant | Firecrawl calls (last 24h) | Severity |
|---|---|---|
| **opendemo.aunoo.ai** | ~93,000 | Critical |
| helpnet.aunoo.ai | ~860 | Low |
| vc.aunoo.ai | ~494 | Low |
| community.aunoo.ai | ~122 | Minimal |
| bugfixing.aunoo.ai | ~55 | Minimal |

The remaining tenants (wiley, wileytest, skunkworkx) use a different Firecrawl key. spiros and testbed have no Firecrawl key configured.

## Root Cause

Three compounding bugs:

### 1. Per-keyword batch scraping causes massive redundant Firecrawl calls (PRIMARY CAUSE)

The keyword monitor on opendemo uses per-group scheduling (checks every 60s for groups where `next_check_at <= NOW()`). The outer scheduling loop is correct — groups run on their configured 15-minute interval. However, **inside each group check**, the design causes an explosion of Firecrawl calls:

**The multiplier effect:**

Each keyword group (e.g. "Geopolitical Hotspots") contains multiple keywords (22 in this case). When a group is checked, `check_keywords()` iterates over every keyword and for **each keyword independently**:

1. Searches the news API → returns ~100-200 articles
2. Saves articles to database
3. Runs `auto_ingest_pipeline()` → calls `process_articles_batch()` → triggers a **Firecrawl batch scrape** for all articles

```
08:04:03 - Starting auto-ingest for 181 articles (keyword 1/22) → batch scrape 181 URLs
08:07:08 - Starting auto-ingest for 200 articles (keyword 2/22) → batch scrape 200 URLs
08:12:11 - Starting auto-ingest for 200 articles (keyword 3/22) → batch scrape 200 URLs
...continues for all 22 keywords...
08:38:34 - Per-group collection complete (35 minutes for one group)
```

**Result per group check:** 22 keywords × ~150 articles = **~3,300 Firecrawl batch scrape URLs per group run**. Over a day with 4 active groups checking every 15 minutes, that's:

- 4 groups × 96 checks/day × ~150 URLs/keyword × ~15 keywords avg = **~864,000 potential scrape URLs/day**
- Actual observed: **~70,000 URLs/day** (some batches are smaller due to deduplication at the article-exists level, and not all groups have as many keywords)

**Critical flaw:** Keywords within the same topic return heavily overlapping article sets from the news API. The same article gets batch-scraped once per keyword that returns it, rather than once per group check. The `batch_scrape_articles()` method does check `raw_articles` for existing content, but this only filters articles scraped in *prior* group checks — not articles already scraped by a different keyword within the *same* check cycle.

**No circuit breaker on Firecrawl errors:** When Firecrawl credits were exhausted, batch scrapes fail with `402 Payment Required`, but the error is caught and execution continues to the next keyword's batch scrape. There is no backoff or disabling mechanism, so the remaining keywords in the group each attempt (and fail) their own batch scrape.

```
08:27:43 - Starting Firecrawl batch scrape for 69 URLs
08:27:44 - ❌ Error: Payment Required: Insufficient credits
08:28:34 - Starting Firecrawl batch scrape for 89 URLs  ← next keyword, same error
```

### 2. New `Research()` instance created per article (opendemo only)

The `automated_ingest_service.py` on **opendemo, helpnet, community, and vc** was running an older version of the code that lacked the `_get_research()` caching mechanism. Instead of reusing a single `Research()` instance, it created a brand new one for every article processed:

```python
# OLD code on opendemo (no caching)
from app.research import Research
research = Research(self.db, model_name=model_name)  # called per article
```

The bugfixing tenant had already been updated with a cache:

```python
# FIXED code (cached)
def _get_research(self, model_name=None):
    cache_key = model_name or '_default'
    if cache_key not in self._research_cache:
        self._research_cache[cache_key] = Research(self.db, model_name=model_name)
    return self._research_cache[cache_key]
```

This older code existed at four call sites in `automated_ingest_service.py` (lines 326, 609, 1283, 2029 on opendemo).

### 3. Firecrawl test scrape on every initialization (all tenants)

Every time `Research.__init__()` ran, it called `initialize_firecrawl()`, which performed a **billable test scrape** of `https://example.com` to verify the SDK was working:

```python
# research.py - initialize_firecrawl()
test_result = firecrawl_instance.scrape(
    "https://example.com",
    formats=["markdown"]
)
```

This test scrape was unnecessary — the Firecrawl SDK validates the API key on construction. The test scrape was a leftover from early integration debugging.

### Combined impact on opendemo

All three bugs compound on each other:

| Source | Calls/day | Type |
|---|---|---|
| Keyword monitor tight loop batch scrapes | ~70,000 | Re-scraping same articles repeatedly |
| Research() re-init test scrapes | ~23,000 | Wasted (scraping example.com) |
| **Total** | **~93,000** | |

The keyword monitor loop is the primary volume driver. Even with bugs #2 and #3 fixed, the ~70k batch scrapes/day from the tight loop remain.

## Why March 19th

Before March 19th, only one keyword group was active on opendemo ("Geopolitical Hotspots"), ingesting ~350 articles/day. On March 19th, **four additional groups began ingesting simultaneously**:

| Topic | Mar 18 | Mar 19 | Change |
|---|---|---|---|
| Geopolitical Hotspots | 347 | 628 | +81% |
| LLM Progress and Scaling | 0 | 2,025 | new |
| AI Development and Design Research | 0 | 1,089 | new |
| Cloud Repatriation | 0 | 263 | new |
| Brand Monitoring Aunoo AI | 0 | 224 | new |
| **Total** | **356** | **4,229** | **~12x** |

Journal logs only go back to March 20th (server reboot), so the exact trigger is unknown. Likely causes: the additional keyword groups were enabled, auto-ingest was turned on, or the service was restarted with updated configuration.

The per-keyword batch scraping bug existed before March 19th, but with only one active group it produced a manageable ~350 articles/day. Five active groups with the same bug produced ~4,200 articles/day — and the Firecrawl batch calls scaled even worse due to the keyword multiplier effect across all groups.

## Why the raw_articles cache doesn't prevent re-scraping

The `scrape_articles_batch()` method does check `raw_articles` before sending URLs to Firecrawl:

```python
existing_raw = await self.async_db.get_raw_article_async(uri)
if existing_raw and existing_raw.get('raw_markdown'):
    existing_articles[uri] = existing_raw['raw_markdown']
```

However, raw content is only saved to `raw_articles` for articles that **pass the relevance check** (inside `_process_single_article_async`, after line 936). Articles that fail relevance are returned early and their scraped content is discarded — never saved to the cache.

**Impact:** Across all keywords in a group check, the same article gets batch-scraped by every keyword that returns it. Since most articles fail relevance (typical: 200 processed → 79 saved), the cache misses on ~60% of articles every time.

**Evidence:** On March 23rd, opendemo had **0 raw_articles added today** and **0 cache hits** despite sending 3,922 URLs to Firecrawl in one hour across 38 batch jobs.

## Remediation

Applied 2026-03-23:

1. **Removed the test scrape** from `initialize_firecrawl()` in `research.py` — eliminates ~23k wasted calls/day
2. **Copied the cached `automated_ingest_service.py`** from bugfixing to opendemo, helpnet, community, and vc — ensures `Research()` instances are reused rather than recreated per article
3. **Restarted all 4 affected tenant services**

Verified post-restart: opendemo logs show `"Successfully created Firecrawl v2 instance"` with no subsequent `"Testing Firecrawl instance"` log.

## Outstanding Issues

### Per-keyword batch scraping (NOT YET FIXED)

The ~70k batch scrapes/day from per-keyword Firecrawl calls have **not been resolved**. The fix should be one of:

1. **Collect first, scrape once:** Aggregate all article URLs across all keywords in a group check, deduplicate, then batch-scrape once at the end
2. **Track already-scraped within a cycle:** Pass a shared set of already-scraped URLs between keyword iterations so the same article is not re-scraped by multiple keywords
3. **Move scraping to article save time:** Only scrape articles that are newly inserted into the database (not already existing), rather than scraping all articles returned by the news API

### No circuit breaker on Firecrawl quota errors (NOT YET FIXED)

When Firecrawl returns `402 Payment Required`, the batch scrape fails but execution continues to the next keyword. Each subsequent keyword also fails. A circuit breaker should:
- Detect `402`/`429` errors and disable Firecrawl for the remainder of the group check
- Optionally disable for a cooldown period (e.g. 1 hour) to avoid burning API calls on repeated failures

### Code drift between tenants

The bugfixing tenant had the `_get_research()` cache fix. Opendemo, helpnet, community, and vc were running an older version without it. Manual file copying for deployments is error-prone and caused this class of bug to persist on production tenants while appearing fixed on the development tenant.

### Opendemo runs a different (newer) version of keyword_monitor.py

Opendemo has a per-group scheduling system (`check_due_groups()`, `check_single_group()`, `get_due_keyword_groups()`) that does not exist in the bugfixing codebase. This newer code also exists in `database_query_facade.py` (new methods: `get_due_keyword_groups`, `update_keyword_group_check_status`). These tenants are not running the same codebase, making cross-tenant bug analysis and fixes significantly more complex.
