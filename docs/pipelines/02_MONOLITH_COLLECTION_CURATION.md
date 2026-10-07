# Monolith article pipeline: collection and curation

This document covers the bugfixing.aunoo.ai monolith, from "a keyword group exists" to "an article row is stored and marked kept or rejected". It was read from the canonical tree `/home/orochford/tenants/bugfixing.aunoo.ai` on 2026-10-07, at HEAD `d58ffa8c` plus whatever is uncommitted in the working tree. I read the `saasmvp-app/` subtree and the `*.bak*` files only to exclude them. Live figures come from the bugfixing database `test`, using SELECT only.

All file references are relative to the tree root unless they start with `/`. Line numbers are as of that date.

The pipeline has eight stages:

1. A scheduler decides that a keyword group is due.
2. Keyword groups, keywords and topic configuration define the search.
3. Collectors search providers inside a claimed time window.
4. The monitor merges, de-duplicates and filters the results.
5. `create_article` writes the row: identity, copy labels, translation and the group match.
6. The AI ingest pipeline scores relevance, runs the analysis and sets `ingest_status`.
7. The social path stores and scores social posts.
8. Readers apply the readable predicate. This is what "rejected" means in practice.

Then come other insert paths, live numbers, document discrepancies and the defects list.

---

## How the pieces fit, in one paragraph

A background loop wakes every 60 seconds and asks Postgres which keyword groups are due (`app/tasks/keyword_monitor.py:1700-1800`, `app/database_query_facade.py:4180-4219`). For each due group, `check_single_group` loads the group's providers, language and threshold (`keyword_monitor.py:1525-1647`) and calls `check_keywords` (`:579`). For each keyword, each provider claims a fixed time window from `collection_checkpoints` and is searched with a 120-second cap. All providers for a keyword run in parallel (`:749-779`).

The results are de-duplicated by exact URL. Each article is then inserted, or merged into its existing row, by `facade.create_article` (`database_query_facade.py:442-627`). That call also links the article to the group in `keyword_article_matches`. At this point the row has `ingest_status` NULL and `analyzed=false`.

Unless the group is social-only, the batch then goes to `AutomatedIngestService.process_articles_batch` (`app/services/automated_ingest_service.py:1682`). That step scrapes pages, scores relevance, runs the AI analysis and writes `ingest_status` plus the analysis columns onto the existing row. Social posts skip that step; the social evaluator scores them after the group run (`keyword_monitor.py:1598-1611`).

A "rejected" article is never deleted. It keeps its row, marked `ingest_status='filtered_relevance'` with a low `topic_alignment_score`. Readers hide it through `app/services/article_visibility.py`.

---

## Stage 1. Triggers and schedulers

**What it does.** It decides when each keyword group is collected.

### 1.1 The keyword monitor loop

This loop is the only scheduled news collection.

- **How it starts.** The `lifespan` function in `app/core/app_factory.py:21` schedules `app.tasks.keyword_monitor.run_keyword_monitor` with a 5-second delay. The schedule list is at `app_factory.py:138-148` and this entry at `:140`. `_schedule_background_task` (`:113-131`) wraps it in `asyncio.create_task` and registers it for graceful shutdown.
- **The loop** (`keyword_monitor.py:1700`):
  - It builds one `KeywordMonitor`, which loads `keyword_monitor_settings` row 1 once (`:183`, `_load_settings` `:186-224`) and builds an `AutomatedIngestService` (`:179-180`).
  - It wakes every `CHECK_INTERVAL_SECONDS = 60` (`:1711`, `:1800`) and logs a heartbeat every 30 minutes (`:1731-1738`). The cron health check greps for that heartbeat.
  - On each tick it reads `keyword_monitor_settings.is_enabled`, where NULL counts as on (`:1749`, facade `:638-645`). If it is on, it calls `check_due_groups()` (`:1649-1698`), which runs the due groups one after another.
  - A failing tick sleeps 30 seconds (`:1786-1793`).
- **Which groups are due** is decided in SQL by `get_due_keyword_groups` (`database_query_facade.py:4180-4219`). The group must be active, and one of these must hold:
  - `next_check_at <= NOW()`;
  - it was never checked;
  - `next_check_at` is NULL and `last_checked_at + interval` has passed.
  
  The oldest-checked group goes first. After a run, `update_keyword_group_check_status` (`:4221-4260`) sets `last_checked_at`, `next_check_at = NOW() + interval` and `last_error`. The interval is `check_interval × interval_unit` seconds, taking the group value and falling back to the global one (`keyword_monitor.py:1502-1503, 1521`).

### 1.2 Live global settings

These are in `keyword_monitor_settings`, id=1.

| Column | Value | Effect |
|---|---|---|
| check_interval × interval_unit | 12 × 3600 | Every group without its own value is collected every 12 hours |
| providers (JSON) | `["newsfirehose"]` | Default provider list. The legacy `provider` column says `thenewsapi` and is used only when `providers` is empty (`database_query_facade.py:258-268`) |
| search_date_range | 7 | First-run lookback in days, and the cap on later windows |
| page_size | 10 | `max_results` per provider call. Social providers get at least `SOCIAL_PAGE_SIZE`, default 25 (`keyword_monitor.py:81-86, 503-505`) |
| language | en | Default language |
| search_fields | title,description,content | Passed to collectors that support field selection |
| sort_by | publishedAt | Passed to collectors |
| auto_ingest_enabled | t | Turns the AI ingest pipeline on for the keyword route |
| min_relevance_threshold | 0.4 | Global relevance floor |
| default_llm_model | bedrock-kimi-k2-5 | Model for the AI analysis step and for the full-LLM relevance fallback |
| inference_mode | hybrid | Relevance scoring mode (see Stage 6) |
| daily_request_limit | 1000 | Loaded at `:198` but **never enforced** |
| quality_control_enabled, auto_save_approved_only | t, t | Read, but the quality check is a placeholder (Stage 6) |

### 1.3 Manual triggers

The routes are in `app/routes/keyword_monitor.py`, under the prefix `/api/keyword-monitor` (`:78`).

- **`POST /check-now`** (`:917-1037`) takes the body `{topic, group_id}`.
  - With a `group_id`, it goes through `check_single_group`, either inline when there are 3 keywords or fewer (`:983-993`) or as a background task (`app/services/background_task_manager.py:575-584`).
  - **With no `group_id`, it calls `check_keywords(None)`.** That run uses the global provider list for every group's keywords, social groups included, and sends everything through the news pipeline. This is the unguarded path that your memory note warns about: social posts get rewritten as news summaries.
- `POST /settings` (`:1612-1653`) writes the global settings. `POST /group/{id}/settings` (`:398-438`) writes the per-group settings. `POST /toggle-polling` (`:1779-1787`) flips `is_enabled`.
- `POST /auto-ingest/enable` (`:3017-3035`) writes the flag and then returns a 500, because `:3029` references an undefined name `toggle`. `POST /auto-ingest/trigger` (`:3101-3131`) is a stub.
- Scripts:
  - `scripts/catchup_outage_window.py` drives `KeywordMonitor` correctly and skips social-only groups (`:63-78`).
  - `scripts/backfill_collection_gap.py` is stale. It treats `_search_with_collector`'s `CollectionResult` as a list (`:105-112`) and skips `create_article`.

### 1.4 Other loops and whether they collect

| Loop | Collects? | Details |
|---|---|---|
| `app/tasks/rss_feed_monitor.py` | Yes | Started at 25 s (`app_factory.py:144`). Every 60 s it checks due feeds; each feed has its own interval and backs off 1x/2x/4x/8x on failure (`:93-134`). Inserts happen in `_store_article` (`:703-829`), then `process_articles_batch(route="rss")` always runs (`:878-940`). Live: 86 feeds, 65 active |
| Market Monitor (`app/tasks/market_monitor.py`) | Yes, vendor LinkedIn posts, web pages and jobs | Module task at 55 s (`app/core/modules.py:144-158`). Posts land through `market_collect.land_article` (`app/services/market_collect.py:219-290`) with topic `"<vendor> - Brand Watch"`, `topic_alignment_score=1.0`, `analyzed=false`, `ON CONFLICT DO NOTHING`. Cadence is 12 h fast and 24 h slow (`market_monitor.py:192-193`) |
| Brand Watcher (`app/tasks/brand_watcher_monitor.py`) | Official sources only | Every 5 cycles it calls `bw_official_sources.poll_official_sources` (`:1284-1291`), which inserts directly (`bw_official_sources.py:907-950`). It also runs the hourly `sweep_unevaluated_social` (`:1236-1245`) |
| `app/tasks/enrichment_retry_sweep.py` | No, re-runs ingest | Every 30 min; up to 50 `quarantined_config` / `enrichment_failed` rows per tick, at most 3 attempts (`:15-20, 189-190, 280`). `ENRICHMENT_RETRY_SWEEP_ENABLED` turns it off |
| `app/tasks/embedding_backfill.py` | No | Not wired; nothing calls it |
| `app/tasks/news_feed_scheduler.py` | No | Builds daily summaries; not started by the app and uses SQLite DDL |

`module_config` on bugfixing enables `brand_watcher`, `market_monitor` and `swiss_disinfo`. The database table overrides `ENABLED_MODULES` (`modules.py:276-285`).

### 1.5 Cron and systemd

Nothing in cron or systemd collects for bugfixing.

- `systemctl list-timers` shows only saas-* and OS timers.
- The root crontab runs monitors only:
  - `collector_health_check.sh` every 30 minutes, which checks the heartbeat and article volume;
  - `eval/relevance_regression/cron.sh` daily and weekly, which judges stored rows;
  - `embedding_health_check.sh`.
- `/etc/cron.d` holds market-quality, Jev-health and badaura entries, none of which collect.

**Gotchas.**

- Groups run one after another inside one loop, so a slow group delays every group behind it.
- The all-groups check-now path is the one way to push social posts through the news pipeline by hand.

---

## Stage 2. Topic and keyword configuration

**What it does.** It defines what to search for, where, and how strictly to judge it.

### 2.1 Three different things are called "topic"

A rebuild must keep them apart.

1. **`keyword_groups.topic`** is a free-text string. It is copied onto every article as `articles.topic`, and it is the join key for everything below.
2. **`app/config/config.json` → `topics[]`** has an entry per topic with name, description and the five label lists: `categories`, `future_signals`, `sentiment`, `time_to_impact`, `driver_types`. These are the topic's lists of allowed labels, which the AI analysis step needs. The entry also holds the optional `include_press_releases` and `enrichment_disabled`. The keys are read by `app/research.py:176-199` and `app/config/config.py:6-10`. A keyword group's topic must match a config.json name exactly, or ingest marks the article `skipped_unknown_topic` (Stage 6). Live: 8 config topics, all with non-empty lists.
3. **Forecast "Topics"** (`forecast_topic_metadata`) are the Topics tab's tracked topics. They read articles by their `topic` tag and are not part of collection. `docs/how_it_works_topics.md` describes only this third meaning (see the discrepancy list).

### 2.2 `keyword_groups` columns and what each one controls

A NULL value means "inherit the global setting". The merge happens in `_get_effective_group_settings` (`keyword_monitor.py:1487-1523`) and in the due-groups SQL.

| Column | Used in collection? | Where |
|---|---|---|
| `topic` | Yes, as the article topic | everywhere |
| `is_active` | Yes, in the due-groups SQL | facade `:4180` |
| `providers` (JSON text) | Yes. NULL means the global list; unparsable JSON means `['thenewsapi']` | `_get_group_collectors`, `keyword_monitor.py:1439-1485` (`:1462`) |
| `social_platforms` (JSON text) | Only xpoz uses it; NULL means env `XPOZ_PLATFORMS` | `:1466-1478` |
| `language`, `country` | Passed to collectors; `country` also turns on the publisher-country filter | `:1569-1575`, `:470-525` |
| `search_date_range` | Lookback for the checkpoint claim | `:755` |
| `check_interval`, `interval_unit` | Scheduling | `:1502-1503` |
| `min_relevance_threshold` | Relevance override at the quick gate only (see Stage 6, gotcha 1) | `:1578`, `:1400` |
| `default_llm_model` | Only the social evaluator uses it | `:1603-1604` |
| `auto_ingest_enabled`, `quality_control_enabled`, `auto_save_approved_only`, `llm_temperature`, `llm_max_tokens` | **Read but never applied.** Only the global auto-ingest flag counts | `:1511-1517` vs `:1306-1309` |
| `source` ('news', 'social', 'reddit', 'manual') | A label only; collection never reads it | |
| `last_checked_at`, `next_check_at`, `last_error` | Scheduler state | facade `:4221-4260` |

**`monitored_keywords`** has the columns id, group_id (FK, cascade), keyword, created_at and last_checked, with UNIQUE (group_id, keyword). Live: 434 rows. Before searching, the monitor strips the prefixes `tech:`, `company:`, `person:` and `location:` (`keyword_monitor.py:68-93`). `last_checked` is set after each keyword runs (`:995`).

### 2.3 Live groups

There are 20 groups, 17 of them active, with 434 keywords.

- **Default providers.** Groups 9 (AI and ML), 10 (Geopolitical), 16 (SOC Automation Market Watch, 131 keywords, threshold 0.25) and 34 (EV Battery Cells) inherit `["newsfirehose"]`.
- **Swiss elections.** Groups 21-27 use newsfirehose and thenewsapi with per-language settings (en, de, fr, it), plus Bluesky (26) and Telegram (27).
- **Social-only groups.** 17 (bluesky + xpoz, twitter+reddit), 18 and 19 (reddit + bluesky, threshold 0), 26, 27, 32 and 35 (bluesky).
- **Inactive groups.** 28-30, Enterprise Test Automation. Rows for that topic still arrive this week; see Stage 9.
- **Country.** No group sets `country`, so the country filter never runs on bugfixing.

**Gotchas.**

- An empty label list in config.json used to mean zero enrichment with no error. It is now caught and stored as `quarantined_config` (Stage 6).
- The `Brand Monitoring 7ai` and `Brand Monitoring Dropzone AI` topics are not in config.json. They survive only because their groups are social-only and never reach the ingest pipeline.

---

## Stage 3. Collectors

**What it does.** It turns a keyword plus a time window into a list of article dicts from one provider.

### 3.1 Contract and shared parts

- **`ArticleCollector`** (`app/collectors/base_collector.py`) has two entry points:
  - `search_articles(query, topic, max_results, start_date, end_date) -> list` (`:150-181`);
  - `collect(query, topic, interval_start, interval_end, continuation, **kw) -> CollectionResult` (`:233-267`).
  
  The default `collect` wraps `search_articles`. When the provider returns a full page, it sets `coverage_complete=False` and `truncated_reason=provider_limit` while leaving `status=success` (`:263-266`). This matters for checkpoints; see the defects list.
- **`stamp_items`** sets `content_kind` (one of full_text, abstract, excerpt, social_post, unknown) and `_collector_provider` on each item (`:36-40, 207-216`).
- **The page budget** is `PROVIDER_MAX_PAGES` (5) and `PROVIDER_PAGE_BUDGET_SECONDS` (60), overridable per provider, for example `NEWSAPI_MAX_PAGES` (`:55-78, 111-132`).
- **`CollectionResult`** (`app/collectors/contracts.py:98-131`) carries:
  - a status (success, partial or failed);
  - the items;
  - `interval_start`/`interval_end`, `coverage_complete` and a continuation cursor;
  - an error code from a fixed list (`:39-52`): timeout, connection, dns, http_4xx, http_5xx, parse, quota_exhausted, unsupported_query, transport_timeout, cancelled, auth, blocked, configuration, unknown;
  - a truncation reason (`:55-60`): provider_limit, time_budget, quota, retention_limit, provider_no_date_filter, parse_partial;
  - a `CollectionCounts` record (`:68-95`).
  
  `may_advance_checkpoint` is true only for status success with `coverage_complete` and no partial parse (`:190-194`). Statuses 406, 408, 425, 429, 500, 502, 503 and 504 count as transient (501 does not) (`:65`). `classify_exception` is at `:306-359`.
- **Dates.** `app/collectors/dates.py` returns a `ParsedDate` with precision, provenance and status (`:54-86, 110-213`). It never substitutes "now"; future dates are flagged, not clamped.
- **Query parsing.** `app/collectors/query_expression.py` parses phrases, AND, OR, NOT and brackets (`:16-22, 307-315`). It compiles them per provider into `exact` or `unsupported` (`:362-376`). **Only NewsData uses it.** Every other provider gets the raw keyword string.

### 3.2 How providers are chosen

- **The keyword monitor does not use `CollectorFactory`.** It has its own `_create_collector` chain, which covers xpoz and telegram (`keyword_monitor.py:226-283`). The per-group provider list comes from `_get_group_collectors` (`:1439-1485`).
- **`CollectorFactory`** (`app/collectors/collector_factory.py:19-120`) serves the manual collect route (`app/main.py:1395`) and research. Its key map leaves out xpoz. `get_available_sources()` decides "configured" from environment variables.
  - Mismatch: it accepts `NEWSAPI_KEY`, but `NewsAPICollector` reads only `PROVIDER_NEWSAPI_API_KEY` or `PROVIDER_NEWSAPI_KEY` (`newsapi_collector.py:65`).
- **`app/config/provider_config.json`** is UI metadata for the keys page. No collector reads it.

### 3.3 Per provider

The last two columns say whether a run on bugfixing is guarded by the shared quota ledger, and whether it ran in the last 7 days.

| Provider (key) | Credentials | Query handling | Window and paging | Ledger | Live 7 days |
|---|---|---|---|---|---|
| **newsfirehose** | `PROVIDER_NEWSFIREHOSE_API_KEY` / `NEWSFIREHOSE_API_KEY`; `NEWSFIREHOSE_BASE_URL` (the default `5.9.100.178` is dead; the live server is 188.40.128.115:8000) | `_normalize_query` (`newsfirehose_collector.py:49-124`). A single quoted phrase stays quoted. Otherwise quotes and brackets are dropped, `\|`, `+`, **AND** and **or** all become `OR`, `NOT x` is deleted, and bare multi-word text is ANDed by the server. Splits into chunks of 8 OR-terms because the server rejects more (`:127-141, 303-323`) | Sends `from_date`/`to_date`; the server defaults to 14 days and caps at 90; the client keeps at least 30 days (`:223-227, 331-375`). Language is sent as a full name ("english") | **No.** Swallows errors into `[]`, so a failure looks like an empty success (`:379-384`) | 2,880 runs, 7,941 items |
| **thenewsapi** | `PROVIDER_THENEWSAPI_API_KEY` / `_KEY` | Raw `search`; field names are mapped (content → `main_text`, plus `keywords`), because unmapped fields are silently ignored and non-English recall used to drop 5-14x (`thenewsapi_collector.py:101-121`) | `published_after/before`; pages until short or `found` reached (`:158-213`). `locale` does **not** filter by country (`keyword_monitor.py:467-487`). Body is a snippet only (`excerpt`) | Yes; budget unknown, so it only reacts to refusals | 693 runs, 741 items, 3 timeouts |
| **newsdata** | `PROVIDER_NEWSDATA_API_KEY` / `NEWSDATA_API_KEY` | `compile_for("newsdata")`; an expression it cannot express sends nothing and fails `unsupported_query` (`newsdata_collector.py:126-142`) | Date filter is sent only when `NEWSDATA_DATE_FILTER_SUPPORTED=1`; otherwise the run is marked `provider_no_date_filter` and filtered locally (`:164-236`). `test_connection` spends a credit | Yes, 200 a day shared across sites; the shared key hits its cap mid-day and then pauses for every site until UTC midnight | not used on bugfixing |
| **newsapi** | `PROVIDER_NEWSAPI_API_KEY` / `_KEY` | Raw `q` (`newsapi_collector.py:137-163`) | `from`/`to`; up to 5 pages; the 100-result developer cap narrows `to` in the continuation (`:287-356`) | Yes, 100 per rolling 24 h | not used |
| **bluesky** | `PROVIDER_BLUESKY_USERNAME` / `_PASSWORD` | Raw `q` to `app.bsky.feed.search_posts`, `sort=latest`, `since`/`until` (`bluesky_collector.py:148-166`) | Cursor paging; drops out-of-window posts; dedup by at:// URI (`:252-311`) | **No** | 515 runs, 1,061 posts |
| **xpoz** (not in the factory) | `XPOZ_API_KEY` | Raw term per platform; a strict term gate after the search: the first token must match, the rest per `XPOZ_TERM_MATCH` (root, majority or all); CJK text matches as substrings since 30 Sep (`xpoz_collector.py:205-287`) | ~60-day rolling window; `XPOZ_MAX_RESULTS` 25 per platform; per-platform timeout 25 s (`:83-93, 170-202`) | Yes, monthly, budget unknown | 40 runs, 484 items, 32 filtered |
| **reddit** (free RSS; no ThinkPol code in this tree) | none | Subreddit route plus search route; search hits must contain a whole-word term (`reddit_collector.py:155-309`) | `HostGuard("reddit.com")` allows 10 requests per 60 s for every site on the host | Host budget | 10 runs, all `quota_exhausted` (HTTP 429) |
| **telegram** | `TELEGRAM_CHANNELS` (comma list) | Scrapes `t.me/s/<channel>`; AND of words as substrings (`telegram_collector.py:67-134`) | Filters on start date only | No | 88 runs, 11 posts |
| **arxiv** | none | `submittedDate:[..]` AND `all:<kw>` or field prefixes (`arxiv_collector.py:121-143`) | Default 7 days; 3-second spacing per process only; retries 1/3/9 s (`:39-89, 231-263`) | The policy entry exists but is never consulted | not used |
| **semantic_scholar** | optional `SEMANTIC_SCHOLAR_API_KEY` | Raw query (`semantic_scholar_collector.py:109-117`) | Offset paging; stops at offset 1,000 (`:165-177`) | Yes, 100 per 5 min | not used |
| **opoint** | `PROVIDER_OPOINT_API_KEY` | Raw `searchterm` (`opoint_collector.py:58-119`) | Context-cursor paging | No | not used |
| **rss** | none | The "query" is the feed URL (`rss_collector.py:257-457`) | Conditional GET; BOM hygiene; partial-parse state; a guard against re-stamped dates via Wayback (`:21-194`) | No | 7,546 runs (Stage 9) |

Collectors that the keyword path does not call: `ats_collector.py` and `vendor_web_collector.py` (Market Monitor), and `app/services/brightdata_linkedin.py` (Market Monitor LinkedIn; it bills per record, and `MARKET_POSTS_PER_VENDOR=5`).

### 3.4 The shared quota ledger

**What it is.** `app/services/shared_ledger.py` writes `/home/orochford/tenants/_shared/collector_ledger.sqlite` (env `AUNOO_SHARED_LEDGER_PATH`, `:43-44, 186`). It exists because sites sharing one key each counted only their own requests.

- **Tables** (`:142-182`): `provider_quota` (keyed by provider and the first 12 hex characters of the key's sha256), `provider_quota_tenant`, `host_budget` and `quota_events`.
- **Built-in budgets** (`:50-66`): newsapi 100 a day, newsdata 200 a day, semantic_scholar 100 per 300 s, arxiv 1 per 3 s, reddit host 10 per 60 s. Thenewsapi, xpoz and firecrawl have no budget. `quota_policy.json` beside the ledger overrides this; the live file sets newsapi to `rolling:86400`.
- **`reserve()`** (`:285-333`) refuses a request when the key is paused, when the period budget is spent, or when this site has used its share and borrowing would eat into the other sites' share.
- **A provider refusal pauses the key for every site** (`:335-385`). The pause lasts until Retry-After (capped at 2 days), else the end of the period, else 15 minutes.
- **"Rolling" periods are fixed buckets** anchored on their first request, not true sliding windows (`:96-107`).
- **Directory permissions.** The directory is 0777 with no sticky bit on purpose, because of `fs.protected_regular` (`:218-242`).
- **Failure handling.** A broken ledger never blocks collection. It falls back to a temporary file, and `QuotaGuard` swallows its errors (`provider_quota.py:73-78`).
- `QuotaGuard` / `HostGuard` are in `app/services/provider_quota.py:55-147`.

**Gotchas.**

- Firehose and Bluesky have no rate limiting or circuit breaker.
- Firehose turns an explicit AND into OR, which widens a query instead of narrowing it.
- Collectors de-duplicate by their own key in memory; URL normalisation happens later, at insert.

---

## Stage 4. Per-keyword run in the monitor

**What it does.** For each keyword in the group, it claims a window per provider, searches, merges the results, filters, saves and commits the checkpoint (`keyword_monitor.py:579-1070`).

### 4.1 Steps

1. **Claim a window.** It calls `claim_interval(db, provider, "kw:<keyword_id>", lookback=search_date_range days)` (`:749-763`, `app/services/collection_runs.py:140-223`).
   - The claim takes a 30-minute lease (`:36`).
   - The first run covers `now - lookback` to `now`.
   - After a complete run, the next window is `coverage_through` to `now`, capped at the lookback.
   - An unfinished interval is returned again **as the same fixed window**, with its continuation (`:134-137, 189`).
   - If another worker holds the lease, the provider is skipped.
   - If the database fails, the claim returns a temporary window that is never committed.
2. **Search.** `_search_with_collector` (`:440-554`) calls `collector.collect(...)` under a hard 120-second timeout (`SEARCH_TIMEOUT_SECONDS`, `:78`). It passes language, `search_fields`, `sort_by` and `country`/`locale`, and stamps each item with `collector_source` and `_matched_keywords` (`:543-548`). A timeout or exception becomes a failed result.
3. **Summarise.** `summarize_outcomes` (`:96-139`) logs "No new articles" separately from "<provider> failed: <reason>".
4. **De-duplicate across providers.** `_deduplicate_articles` (`:385-438`) works by exact stripped URL. Priority is newsapi 5, thenewsapi 4, newsdata 3, semantic_scholar and bluesky 2, arxiv 1; everything else 0. The `_matched_keywords` of the copies are merged.
5. **Filter by country** (`_filter_by_source_country`, `:330-383`). This runs only when the group sets `country`. It resolves the publisher's country through `app/services/source_country.py`: a manual entry, then the TLD, then mediabias, then a model, cached in `news_source_countries`. Publishers it cannot place are dropped. The step is inactive on bugfixing.
6. **Save** in a worker thread (`_save_articles_batch`, `:834-881`):
   - `article_exists` checks for an exact uri (facade `:436-440`).
   - **CJK phantom guard** (`:22-57, 855-863`). For new thenewsapi items in ja, zh or ko groups, if the term is missing from the title and summary, it fetches the page once and drops the item if the term is not there. A failed fetch keeps the item. The reason, measured on sunstar: 111 of 181 Japanese results (61%) never contained the term.
   - `facade.create_article(...)` writes the row (Stage 5).
   - If any item fails to save, every provider result is downgraded to partial so the window is collected again (`:883-896`).
7. **Commit checkpoints and runs** (`_finish_runs`, `:788-804, 899`).
   - `commit_interval` (`collection_runs.py:226-291`) has three branches. A complete success advances `coverage_through` and clears the continuation. A partial run, or a retryable failure, stores the continuation and keeps the window. **Anything else** increments `consecutive_failures` and keeps the window.
   - `record_run` inserts a `collection_runs` row (`:52-118`).
8. **Hand to ingest** (`:906-938`).
   - `should_auto_ingest()` reads only the global flag (`:1306-1309`), and it is forced off for social-only groups (`:907-909`).
   - In mixed groups, rows whose source matches `is_social_source` are removed (`:912-925`).
   - `auto_ingest_pipeline` (`:1339-1430`) renames the fields (`url` to `uri`, `source` to `news_source`). It passes `topic_keywords`, which is every keyword of every group on the topic, social groups included (facade `:422-434`). It also passes the group threshold as `relevance_threshold_override` (`:1400`). It then calls `process_articles_batch(route="keyword")`.
9. **After ingest.**
   - `DataQualityService.audit_batch` samples 5 kept articles on nova-lite and **only logs** (`app/services/data_quality_service.py:85-141`).
   - `story_identity.label_unlabelled(limit=2000)` labels rows that other insert paths left unlabelled (`keyword_monitor.py:1620-1626`).
   - The group status is updated.

### 4.2 Tables written

| Table | Key columns |
|---|---|
| `collection_checkpoints` | provider, scope_key, coverage_through, continuation, version, lease_owner/lease_until, consecutive_failures, last_error_code, last_success_at |
| `collection_runs` | provider, scope_kind/scope_id, status, interval_start/end, coverage_complete, counts (jsonb), item_count, error_code, error_message, truncated_reason, diagnostics, duration_ms, started_at, finished_at |
| `monitored_keywords.last_checked` | |
| `keyword_groups.last_checked_at`, `next_check_at`, `last_error` | |

**Gotchas.**

- See defect 1 (the stuck window) in the last section.
- The `collection_runs.counts` for keyword providers show `received` but `inserted=0`. Insert outcomes are not fed back into the run record, so you cannot read insert rates per provider from it. Only RSS fills `inserted` and `duplicate`.

---

## Stage 5. Insert: `facade.create_article`

**What it does.** It turns a collector dict into an `articles` row, or merges it into the existing row, and links the row to the group (`app/database_query_facade.py:442-627`).

**Trigger.** It is called by the keyword monitor (`keyword_monitor.py:864`) and by some scripts. RSS, Market Monitor and Brand Watcher official sources use their own inserts (Stage 9).

### 5.1 Steps

1. **Resolve identity** (`:465-474`, `app/services/article_identity.py:216-306`). A match means the stored row's uri replaces the incoming URL and the article counts as existing.
   - **News** is matched by exact uri, then the observation key, then `article_url_aliases` (raw or canonical URL), then `articles.canonical_url` (same topic preferred), then `articles.url_key`.
   - **Social posts** are matched by exact uri, then the observation key, then `social_meta.platform` plus `external_id`. A post is never matched by URL (`:271-282`).
   - URL normalisation is `app/collectors/url_identity.normalize_url` (`:174-208`). It lower-cases the scheme and host, drops the default port and the fragment, and strips tracking parameters using the registry at `:45-75` (version `2026.10.01-1`), which `URL_TRACKING_REGISTRY_PATH` can extend. It keeps trailing slashes and does not merge http with https.
   - Identity priority (`choose_identity`, `:303-337`) is: calendar occurrence, then social `platform:post_id`, then DOI, then canonical URL, then feed GUID, then provider id, then content hash.
2. **Label copies and press releases** (`:475-490`, `app/services/story_identity.label_article` `:316-354`). This sets three things:
   - `url_key`, the URL with tracking parameters stripped. A hit on the same row counts as existing.
   - `source_type`, which is `press_release` when the host or source name is on the wire list (`is_wire_host`, prnewswire, globenewswire, openpr, menafn and others), else `news`.
   - `duplicate_of`, the uri of the earliest original in the same topic within ±3 days whose title matches. The match rules are in `docs/INGEST_DUPLICATES_AND_PRESS_RELEASES_SPEC.md` ("Matching limits"): at least 3 significant words for equal titles, 6 or more for near matches, numbers must agree, press releases link only on equal titles across different sites, and social posts link on URL only.
3. **Translate new rows only** (`:491-503`). `english_fields(article)` (`app/utils/title_translation.py:299-349`, model nova-lite at `:33`) translates the title and summary in place. It sets `original_title` and `original_summary` only when it actually translated.
4. **INSERT** (`:504-537`). It writes uri (the raw collector URL), title, original_title, news_source, publication_date (text), summary, original_summary, topic, `analyzed=false`, opoint_entities, social_meta, url_key, source_type, duplicate_of, canonical_url, identity_method, record_type, content_kind, first_seen_at, last_seen_at, published_at_raw, publication_date_precision and date_provenance. **`ingest_status` is left NULL.**
5. **`submission_date`** is not in the INSERT. The SQLAlchemy column default `text('CURRENT_TIMESTAMP')` fills it (`app/database_models.py:363`), giving Berlin-local text with an offset, the same shape as `app/utils/timestamps.submission_stamp()`. The database column has **no** default, so raw-SQL writers that leave it out store NULL. Live: 2,223 rows have NULL `submission_date`.
6. **Repeat sighting** (`:543-560`). `merge_fields` (`article_identity.py:416-492`) fills empty fields and lets full text replace an excerpt, never the reverse. It never overwrites a known date and moves `last_seen_at` forward. `PROTECTED_COLUMNS` (`:65-77`) are never touched.
7. **Observation and alias** (`:562-566`, `record_observation` `:317-384`). It writes `article_observations` and `article_url_aliases`.
8. **Group match** (`:568-594`). It upserts `keyword_article_matches(article_uri, keyword_ids CSV, group_id)`, unique on (article_uri, group_id).
9. It returns `(inserted, alert_inserted=False, match_updated)`. The full outcome is on `facade.last_create_outcome`.

### 5.2 Tables

| Table | Notes |
|---|---|
| `articles` | PK uri. See the list above. 242,689 rows |
| `keyword_article_matches` | Also carries below_threshold, topic_alignment_score, relevance_status and scored_at, plus brand_relation, source_relation, judge_version, decision_evidence and last_failure (brand decisions, unused on bugfixing). 99,230 rows |
| `keyword_alerts` | **Legacy, 0 rows.** `create_article` always returns `alert_inserted=False` |
| `article_observations`, `article_url_aliases` | 5,725 and 5,701 rows; they started on 2026-10-01 |

**Gotchas.**

- **The canonical-URL and url_key lookups are global with a same-topic preference.** A tracking variant collected for a second topic lands on the first topic's row, because `articles.topic` holds only one value.
- `article_observations.provider` stores the publisher domain, not the collector (`provider_of`, `article_identity.py:125-132`, never reads `collector_source`).
- `record_type` and `identity_method` are NULL on almost every row first seen before 2026-10-02. No backfill was run.

---

## Stage 6. Curation: the AI ingest pipeline and the relevance gate

**What it does.** It decides whether each stored article is kept (`approved`) or rejected (`filtered_relevance`), and it runs the AI analysis step on the kept ones.

**Trigger.** `process_articles_batch` (`app/services/automated_ingest_service.py:1682-1909`) runs from four places:

- the keyword route, when the global `auto_ingest_enabled` is on;
- the RSS route, always;
- the enrichment retry sweep;
- brand retry.

### 6.1 Batch stage

1. **Configuration check per topic** (`:1718-1720, 1911-1934`).
2. **Rejected-candidate ledger,** keyword route only (`:1722-1752`, `app/services/rejected_candidates.py`).
   - The key is `gate_version`, a hash of the keywords, the threshold and `relevance_route_signature()` (`rejected_candidates.py:48-58`, `hybrid_relevance_service.py:174-184`).
   - A hit skips scoring and counts as `already_rejected`.
   - `REJECTED_CANDIDATE_LEDGER` (default 1) turns it off, and `REJECTED_CANDIDATE_RETENTION_DAYS` defaults to 30.
   - RSS and manual routes never consult the ledger.
3. **Pre-scrape** (`:1771-1792`). Any article whose collector content is 200 characters or less is scraped **before** any relevance check, through `scrape_articles_batch` (`:2191-2303`). That step reads cached `raw_articles` first, then calls the Firecrawl batch API, then falls back per URL. It caches successes in `raw_articles`.
4. **Concurrency.** 5 articles at a time, with a 300-second cap per batch (`:1801, 1828-1864`).

### 6.2 Per article

This is `_process_single_article_async`, `:978-1526`. The steps run in order.

| # | Step | Lines | Result |
|---|---|---|---|
| 0 | Brand hook `pre_decide`; a no-op unless `BRAND_RELATION_DECISIONS` is set (unset on bugfixing) | `:1015`, `brand_ingest_hooks.py:91-188` | |
| 1 | Topic missing from config.json after one reload | `:1029-1064` | `skipped_unknown_topic`, scores 0.0, no model call |
| 2 | Configuration check: any of the five label lists empty, or `enrichment_disabled` | `:1066-1096`, `configuration_block_reason` `:72-103` | `quarantined_config` plus `enrichment_block_reason`, scores 0.0 |
| 3 | No text: uses the scraped page if it has 200+ characters, otherwise fails | `:1098-1147` | `enrichment_failed`, scores 0.0 |
| 4 | Ledger hit | `:1149-1165` | returns with no write |
| 5 | **Quick relevance check** with `score_article_relevance` (`:517-658`). Threshold = group override if passed, else the topic threshold | `:1167-1226` | below the threshold: `filtered_relevance` with its scores; marks the match `below_threshold`; `record_group_relevance`; records the rejection in the ledger |
| 5e | The scorer raised | `:1228-1247` | `relevance_check_failed`, scores 0.0, not recorded in the ledger |
| 6 | Bias lookup and scrape, run concurrently | `:1249-1305` | raw text goes to `raw_articles` |
| 7 | AI analysis step, 60-second cap (`_analyze_article_content_async`, `:1534-1639`) | `:1307-1327` | category, sentiment, labels, summary |
| 8 | **Second relevance score** on the enriched text (a second LLM call and a second Jev call) | `:1329-1345` | |
| 9 | **Final gate.** Threshold = `get_relevance_threshold(topic)`; the group override applies only to topics starting `"Brand Monitoring "` | `:1347-1362` | below the threshold: `filtered_relevance` (`:1492-1518`) |
| 10 | Quality check: **a placeholder that always approves with 0.8** | `:1363-1372, 1655-1662` | |
| 11 | `analyzed` not set: a configuration fault, or a silent analysis failure | `:1374-1431` | `quarantined_config` or `enrichment_failed` |
| 12 | Save | `:1433-1464` | `approved`, `auto_ingested=true`; `update_article_with_enrichment`, then `record_group_relevance`, then the embedding is written to the vector store (30-second cap) |

### 6.3 What the scores are

`score_article_relevance` (`automated_ingest_service.py:517-658`) works in this order:

1. Retail deal pages get 0.0 on every topic (`app/services/deal_listing.py`, `:535-552`).
2. The hybrid service, `HybridRelevanceService.score_relevance` (`app/services/hybrid_relevance_service.py:727-940`), runs.
3. The brand mention gate runs. It does nothing on bugfixing.

It then stores:

- **`keyword_relevance_score`**, which is the **embedding similarity** (`:609`), not a keyword score.
  - The model is `sentence-transformers/all-MiniLM-L6-v2` on the CPU (`hybrid_relevance_service.py:44, 222-241`).
  - The topic text is the topic name, its config.json description and up to 10 keywords (`:319-351`). The article text is `title. summary`, or the title plus the first 1,000 characters of full text when the summary is short (`:375-381`).
  - The score is `(cos+1)/2` (`:388`). Real articles therefore sit around 0.5 to 0.8 and almost never near 0.
- **`topic_alignment_score`**, which is the verdict score.

Inside `score_relevance`, the verdict score is built in these steps:

1. **Classifier.** A fine-tuned DeBERTa-base binary classifier at `models/relevance_classifier/final` (`:243-277`). Its input is `topic [SEP] title. summary`, at most 256 tokens; reported test AUC is 0.987. It runs only when there is text (`:796-805`).
2. **Combine.** `0.6 × classifier + 0.4 × embedding` when both exist (`:45-46, 811-818`).
3. **Confidence.** A score below 0.20 or above 0.85 counts as "high"; anything else is "medium" (`:837`). On theme topics, a classifier score of 0.90 or more forces "high" (`:850-853`).
4. **Cross-encoder tier.** Theme topics only, accept-only, and **off** (`RELEVANCE_USE_CE_TIER=false`; `:884-905`; model `BAAI/bge-reranker-base`). The reason it is theme-only: on brand topics it scored AUC 0.478, no better than a coin toss, against 0.885 on themes (`:52-88`).
5. **Jev accept tier** (`:908-920`). It applies when confidence is not high and Jev's `on_topic` is at least `TYPESAFE_DECIDE_RELEVANCE_MIN` (default 0.8). The article is accepted and the **score is set to `max(score, threshold)`**, so an accepted row stores exactly the threshold. **On** for bugfixing (`TYPESAFE_DECIDE_RELEVANCE_ACCEPT=1`, `TYPESAFE_MODEL=jev-1.13.0`). The Jev reading is stored in `relevance_confidence_readings`.
6. **LLM fallback** (`:922-930`). When confidence is still not high, the LLM's number **replaces** the score.
   - The model is `HYBRID_RELEVANCE_LLM_MODEL`, default **nova-lite** (unset on bugfixing), which maps to `bedrock/us.amazon.nova-lite-v1:0` with router fallbacks kimi-k2.5 and nova-pro (`app/config/litellm_config.yaml:236-238, 303-305`). It is called with `max_tokens=10` and `temperature=0` (`:592-627`).
   - There are three prompts in `_compute_llm_score`: market (`:478-495`), brand (`:497-516`) and theme (`:517-554`). The theme prompt is a strict auditor scoped by the config.json description.
   - The reply is parsed by `parse_unit_score` (`:148-161`). In inference mode `local` the LLM step is switched off entirely: `automated_ingest_service.py:573` sets `use_llm_fallback` only for `hybrid` and `external`, so the Qwen2.5-3B path in `hybrid_relevance_service.py` (`:561-590`) is never reached and uncertain cases keep the local score.
7. **Decision.** `relevant = score >= threshold`. If no engine answered, `status="unavailable"` and `relevant=None` (`:934-940`). The caller then writes `relevance_check_failed`.

**If the whole hybrid service raises,** ingest falls back to `RelevanceCalculator.analyze_relevance` (`app/relevance.py:163-243`). That runs the full LLM `keyword_monitor_settings.default_llm_model` (bedrock-kimi-k2-5) with the prompt template `relevance_analysis` (`app/analyzers/prompt_templates.py:92-127`). On that path the gate compares `(topic + keyword)/2`, and `keyword_relevance_score` holds the LLM's keyword score.

**Inference mode** comes from `keyword_monitor_settings.inference_mode`, which is `hybrid` (`automated_ingest_service.py:173-191`).

### 6.4 Thresholds and where they are set

| Threshold | bugfixing value | Where |
|---|---|---|
| Global ingest floor | 0.4 | `keyword_monitor_settings.min_relevance_threshold` (facade `:1073-1081`) |
| Topic threshold used at the final gate | the **lowest-id active group on the topic that sets one** | `get_group_relevance_threshold` (facade `:1083-1103`); falls back to the global, then 0.0 (`automated_ingest_service.py:1994-2017`) |
| Group override at the quick gate | `keyword_groups.min_relevance_threshold` | `keyword_monitor.py:1400`. RSS uses the feed's percentage divided by 100 (`rss_feed_monitor.py:925-939`) |
| Confidence band | below 0.20 or above 0.85 | `hybrid_relevance_service.py:837` |
| Jev accept | 0.8 | `TYPESAFE_DECIDE_RELEVANCE_MIN` |
| Readable floor for every reader | 0.4, hard-coded | `RELEVANCE_FLOOR`, `article_visibility.py:36` |
| Research re-scoring (Auspex deep research, not ingest) | 0.6 include, 0.8 high; model claude-haiku-4-5 | `app/services/relevance_scorer.py:54-55`, `RELEVANCE_MODEL` |

### 6.5 The AI analysis step

`_analyze_article_content_async` (`automated_ingest_service.py:1534-1639`) builds an `ArticleAnalyzer` on `default_llm_model` (bedrock-kimi-k2-5) and passes in the topic's five lists from config.json (`app/research.py:943` onward).

`ArticleAnalyzer.analyze_content` (`app/analyzers/article_analyzer.py:154-320`) does the following:

- It raises `ConfigurationFault` on an empty list (`:170-179`). The caller turns that into `quarantined_config`.
- It caches results for 24 hours by uri, model and categories hash (`:191-205, 299-307`).
- It snaps output to the allowed lists. An unknown category or future signal becomes `Other`; an unknown sentiment, time to impact or driver type becomes `""` (`:477-531`).
- It writes a 50-word neutral summary and translates non-English titles.
- It fires a Jev shadow check on the summary sentences (`TYPESAFE_SHADOW_EXTRACTION=1`, `:266-280`).

The DeBERTa multitask enrichment model (`models/enrichment_model/final`; 4/6/5/15 labels; `hybrid_enrichment_service.py`) runs **only** on the synchronous `analyze_article_content` path. That path is used by the manual enrichment route (`app/routes/keyword_monitor.py:651`) and by scripts. It never runs on the keyword or RSS ingest path.

### 6.6 How rejected and failed rows are saved

`save_below_threshold_article` (`app/services/async_db.py:420-499`) is an upsert. It updates the status and scores only when the row has the same topic or is not already approved (`:446-457`), so one topic's rejection cannot undo another topic's approval. It writes `analyzed=false` only on insert, which is why 19 `filtered_relevance` rows from this week still say `analyzed=true`.

Enrichment updates (`build_enrichment_update`, `:599-660`) move the topic, scores and labels only under `_REFILE` (`:581-582`): the row is not approved yet, or it has the same topic, or the new score is higher.

### 6.7 `ingest_status` values

| Value | Written at | Meaning |
|---|---|---|
| NULL | `create_article` | Stored, not yet processed. Social posts the evaluator has not reached, or news in a run where auto-ingest is off |
| `approved` | `automated_ingest_service.py:1436`; `brand_decision.py:110`; `market_briefing.py:969` | Kept: passed both gates and the analysis |
| `filtered_relevance` | `:1191, 1499`; `async_db.py:489`; `brand_decision.py:110` | Rejected on relevance. The row is kept as labelled data |
| `relevance_check_failed` | `:1233`; `brand_decision.py:107` | No evaluator answered. Not a rejection, yet the scores are 0.0. **No sweep retries it**; it is seen again only if a collector rediscovers the URL |
| `enrichment_failed` | `:1126, 1414` | No text, or the analysis failed; retried up to `ENRICHMENT_MAX_ATTEMPTS` (3) |
| `quarantined_config` | `:1077, 1384` | One of the topic's label lists is empty; retried once the configuration is fixed |
| `skipped_unknown_topic` | `:428, 1043` | Topic not in config.json. Terminal |
| `social_evaluated` | `social_eval_service.py:612, 642, 783` | A social post scored by the social evaluator |
| `deferred` | `brand_decision_store.article_verdict_sql` | Brand path only: identity or ownership unresolved |
| `auto`, `manual` | `auto_ingest_service.py:400`; `bulk_research.py:545` | Older services and manual saves |

`'rejected'` and `'failed'` are read in a few places (`auspex_service.py:1494`, facade `:5336`) but nothing writes them.

### 6.8 The brand decision path

This path is present in the code but off on bugfixing.

**Switch.** `BRAND_RELATION_DECISIONS` turns it on (`app/services/brand_decision.py:63-65`).

**Decision order** in `decide` (`:356-494`):

1. exclusions;
2. ownership;
3. mention detection (`brand_profile.detect_mention`);
4. reuse of an earlier decision with the same inputs;
5. without a verified mention, the topic scorer decides `sector` or `other`;
6. the LLM judge (`BRAND_JUDGE_MODEL`, else `HYBRID_RELEVANCE_LLM_MODEL`, else nova-lite; or Jev when `BRAND_JUDGE_ROUTE=jev`);
7. the headline rule, which since `brand-coverage-3` does not overrule a judge's `other`;
8. an earned label from an unknown publisher defers.

**Labels and grades:** subject 0.9, notable 0.7, sector 0.5, passing 0.2, other 0. A row is admitted when it is earned (subject or notable from an independent source), `sector`, or owned subject or notable.

**Storage.** Decisions are stored on the `keyword_article_matches` columns from migration `br_001`. Market vendor decisions go to `brand_article_decisions` behind `MARKET_VENDOR_DECISIONS`, also unset here. Readers use `app/services/brand_coverage.py`.

---

## Stage 7. The social path

**What it does.** It stores social posts and scores them cheaply, without ever passing them through the news analysis step.

**What counts as social:**

- **By provider:** reddit, bluesky, xpoz and telegram (`keyword_monitor.py:1559-1561`).
- **By source string:** `is_social_source` (`app/services/social_sources.py:21-26`), a substring test. It has a known false positive, `clsbluesky.law.columbia.edu`.
- **For identity:** any row with `social_meta` (`article_identity.py:114-122`).

**How the two paths stay apart:**

1. **Social-only groups.** `check_single_group` sets `_social_only_group`, and `check_keywords` then turns auto-ingest off (`:907-909`). Posts are stored only by `create_article`, with `social_meta`, `record_type='social_post'` and `ingest_status` NULL.
2. **Mixed groups.** Social rows are removed from the batch before the news pipeline (`:912-925`).
3. **After the group run,** if any social provider ran, `SocialEvalService.evaluate_and_store` (`social_eval_service.py:561-650`) runs.
   - It selects up to 500 social rows for the topic that are not yet `social_evaluated`, newest first. The `days_back` argument is accepted but not used.
   - Brand exclude terms set the score to 0 (`:600-615`).
   - A model scores relevance and sentiment and writes `ingest_status='social_evaluated'`, `analyzed=true`, both scores (`keyword_relevance_score` is a copy of the relevance), sentiment, author_role and author_role_reason (`:639-646`).
   - The model is the group's `default_llm_model`, then env `SOCIAL_EVAL_MODEL`, then `gemma3:4b` (`:26, 303-304`). On bugfixing that is **claude-haiku-4-5**, which your cost notes say to avoid.
   - The Jev prefilter and accept thresholds are `SOCIAL_JEV_PREFILTER_MIN=0.1` and `SOCIAL_JEV_ACCEPT_MIN=0.91` (`:1024-1038`).
4. **Hourly sweep.** Brand Watcher's `sweep_unevaluated_social` (`brand_watcher_monitor.py:1236-1245`) retries rows the evaluator missed.
5. **RSS** skips entries that link to social hosts (`rss_feed_monitor.py:724-731`).

**Gotcha.** The all-groups check-now (`check_keywords(None)`) breaks the separation. It is the only live path that does.

---

## Stage 8. What "kept" and "rejected" mean to readers

**What it does.** `app/services/article_visibility.py` is the single rule for whether a row is readable. The facade readers, both pgvector searches, Auspex and the MCP tools use it.

`readable_sql('a')` (`:90-98`) produces:

```sql
((a.topic_alignment_score IS NULL OR a.topic_alignment_score >= 0.4)
  AND (a.source_type IS DISTINCT FROM 'press_release' OR a.topic IN (<pr_topics>)))
AND (a.duplicate_of IS NULL OR NOT EXISTS (
  SELECT 1 FROM articles o WHERE o.uri = a.duplicate_of
    AND (o.topic_alignment_score IS NULL OR o.topic_alignment_score >= 0.4)
    AND (o.source_type IS DISTINCT FROM 'press_release' OR o.topic IN (<pr_topics>))))
```

- **Which topics show press releases.** `<pr_topics>` (`app/services/story_identity.py:217`) lists the topics that set `include_press_releases: true` in config.json, plus every Market Monitoring topic. With `STORY_PR_DEFAULT=show` (unset on bugfixing) it covers all topics.
- **A copy is hidden only when its original is readable,** so a story never disappears because the wrong copy arrived first.
- **The predicate does not look at `ingest_status` or `analyzed`.** "Rejected" in practice means "score below 0.4". A NULL score counts as readable, so unprocessed rows with a NULL score are visible.
- **Auspex vector search adds** `ingest_status != 'filtered_relevance'` (`auspex_service.py:54, 63`).
- **The news feed, Explore and the category lists** use `story_sql()` (`:125-161`), which hides copies and press releases but applies **no** score floor.
- **Gather** applies no filter. It is the view for checking everything that was collected.

**Gotcha.** The 0.4 floor is hard-coded, but group thresholds may be lower. In the last 7 days, 120 `approved` SOC Automation rows scored below 0.4 because group 16's threshold is 0.25. Every reader that uses the predicate hides them.

---

## Stage 9. Other insert paths

None of these goes through `create_article`. Fourteen code paths insert into `articles`, per the duplicates spec.

- **RSS** uses `_store_article` (`rss_feed_monitor.py:703-829`). It resolves identity, translates at insert, and inserts directly with `record_type='news'`, `content_kind='excerpt'`, `source_country` and `first_seen_at`. It then calls `process_articles_batch(route="rss")`. RSS is the only path that writes `articles.source_country`.
  - Failed entries queue in `pending_feed_entries` and replay on the next poll.
  - After 20 hard failures, or 10 partial parses, a feed becomes `needs_attention`. It is never deactivated.
- **Market Monitor** lands vendor LinkedIn posts with score 1.0 and `analyzed=false` (`market_collect.py:219-290`).
- **Brand Watcher official sources** use `bw_official_sources._land_and_attribute` (`:907-950`).
- `story_identity.label_unlabelled` runs after every group check, so rows from these paths still get `url_key`, `source_type` and `duplicate_of`.

---

## Stage 10. Live numbers

These are from the bugfixing database on 2026-10-07. "Last 7 days" means `first_seen_at` in the last 7 days.

### Overall volume

- **Total articles:** 242,689.
- **Last 7 days:** 5,767.
- **All time:** 177,456 `filtered_relevance`, 47,448 `approved`, 12,383 NULL, 5,050 `social_evaluated`.

### Last 7 days by status

| Status | Rows | With embedding | Mean topic_alignment_score |
|---|---|---|---|
| filtered_relevance | 2,898 | 19 | 0.16 |
| social_evaluated | 1,709 (all social) | 0 | 0.50 |
| approved | 1,057 | 1,057 | 0.61 |
| NULL | 64 (social, not yet evaluated) | 0 | 1.00 |
| enrichment_failed | 39 | 0 | 0.00 |

No `relevance_check_failed`, `quarantined_config` or `deferred` rows arrived this week. Copies: 148 rows. Press releases: 122 rows.

### How approved scores cluster

- 273 approved rows sit at exactly 0.400. That is the Jev accept tier writing the threshold.
- 118 sit at 0.300: nova-lite answers passing the SOC Automation 0.25 floor.
- 105 sit at 0.500.

The commonest methods behind approved rows are `hybrid+llm_fallback` (603) and `hybrid+jev_accept` (126).

### By topic, last 7 days

| Topic | Total | Approved | Filtered | Social |
|---|---|---|---|---|
| Market Monitoring SOC Automation | 1,528 | 377 | 189 | 935 |
| Market Monitoring Enterprise Test Automation | 1,237 | 297 | 940 | 0 |
| Swiss Federal Elections 2027 Disinfo Monitoring | 796 | 1 | 702 | 88 |
| Market Monitoring EV Battery Cells | 753 | 25 | 98 | 630 |
| EV Battery Industry | 527 | 43 | 480 | 0 |
| AI and Machine Learning | 394 | 90 | 302 | 0 |
| Geopolitical Hotspots | 393 | 222 | 170 | 0 |

Enterprise Test Automation's keyword groups are all inactive, so its rows must come from RSS or Market Monitor.

### Collection runs by provider, last 7 days (`collection_runs`)

| Provider | Runs | Received | Notes |
|---|---|---|---|
| rss | 7,546 | 248,364 | 1,091 inserted; 231,929 already stored |
| newsfirehose | 2,880 | 7,941 | |
| thenewsapi | 693 | 741 | 3 timeouts |
| bluesky | 515 | 1,061 | |
| telegram | 88 | 11 | |
| xpoz | 40 | 484 | 32 removed by the term gate |
| reddit | 10 | 0 | all `quota_exhausted` (HTTP 429) |
| enrichment_retry | 250 | | |

NewsAPI, NewsData, arXiv and Semantic Scholar did not run on bugfixing this week.

### Checkpoint state (`collection_checkpoints`)

| Provider | Never covered | Failing | Max consecutive failures | Oldest coverage_through |
|---|---|---|---|---|
| newsfirehose | 46 | 82 | 10 | 2026-10-02 |
| xpoz | 3 | 3 | 5 | |
| reddit | 2 | 2 | 5 | |
| thenewsapi | 0 | 0 | | 2026-10-02 |

### Daily new rows

Daily new rows ran at about 540-730 from 23 to 29 September. They spiked to 2,025 and 2,379 on 1-2 October, after the collector data-quality release. Since then they have been 76-488 a day.

---

## Stage 11. Where the documents disagree with the code

The code wins in every case.

### docs/COLLECTOR_DATA_QUALITY_IMPLEMENTATION.md

1. **"Nothing is committed, nothing is restarted."** This is stale. The work is committed as `6f8d4fbd`, and the bugfixing service has been running it since about 1 October, which the `collection_runs` rows show.
2. **"The keyword monitor should pass `group_id` explicitly"** is still listed as open. It is done: `auto_ingest_pipeline` passes `group_id` (`keyword_monitor.py:1404-1408`).
3. **"NewsAPI, NewsData, TheNewsAPI, Semantic Scholar … page under a budget … every collector sets `content_kind`."** NewsFirehose, Telegram and Opoint were never migrated to `collect()`. Firehose and Telegram set no `content_kind` (it is stamped `unknown`), and neither has a quota guard.
4. **"arXiv … three-second spacing"** is accurate, but the ledger's arxiv policy is never consulted. The spacing is per process only, which the doc does note under "Open".
5. **"The keyword monitor claims a fixed interval … commits it after saving."** True, but the doc does not say that a full page from a list-only collector, firehose being the default, never advances the checkpoint and is counted as a failure. That is defect 1 below.

### docs/COLLECTOR_DATA_QUALITY_SPEC.md

This is a proposal; the implementation doc records the as-built names. I found no other conflict beyond the points above.

### docs/INGEST_DUPLICATES_AND_PRESS_RELEASES_SPEC.md

1. **"Step 2 runs at insert, before the AI analysis step."** This matches the code (`create_article :475-490`), but only for `create_article`/`upsert_article`. Other paths are labelled afterwards by `label_unlabelled`, as the "As built" section says.
2. **It describes `create_article` at "line ~441" and `upsert_article` at "~5107".** `create_article` is now at `:442-627`. The line is close, but the function has grown identity and observation steps the spec does not describe.
3. **Readable rule.** It matches `article_visibility.py:90-98`.

### docs/how_it_works_topics.md

This document is about forecast topics (`forecast_topic_metadata`, candidates, horizons), not about collection topics or keyword groups. Nothing in it describes the collection pipeline. A reader looking for "how topics drive collection" will be misled; collection topics are `keyword_groups.topic` plus the config.json entry. It also says the Wiley judge uses `gpt-4.1-mini` and the theme proposer `gpt-5.4`. Those are aliases; per your memory notes the yaml repoints gpt-* aliases, so they are not the literal OpenAI models. I did not verify those two model settings, because they are outside collection.

### docs/RELEVANCE_INTEGRITY_PATCH_2026-10-05.md

1. **"One brand detector."** Two detectors still recognise only `"Brand Monitoring X"`: `brand_mention_gate._BRAND_TOPIC_RE` (`brand_mention_gate.py:42`) and the final-gate override (`automated_ingest_service.py:1359`). The comment at `hybrid_relevance_service.py:877-882`, which says `is_brand_topic` misses "X - Brand Watch", is itself out of date.
2. **"Missing evidence is not a reject" / no 0.0.** The verdict is no longer a reject, but `relevance_check_failed` rows still store 0.0 scores (`:1233-1237`). The brand path writes 0.0 for unavailable and deferred rows (`brand_decision_store.py:193`). A score of 0.0 fails the readable predicate, and `delete_unscored_article_matches` (facade `:3232-3249`) treats a keyword score of 0 as unscored.
3. **"Hybrid failure goes to the full LLM judge."** True, but that judge gates on `(topic + keyword)/2`, not on the topic score (`app/relevance.py:241-243`).
4. **It names `process_single_article`.** The function is `_process_single_article_async`.
5. **Confirmed accurate:** strict parsers, `method none` set to medium, the unavailable status, the threshold passed to the scorer (`:592`), the bulk endpoint returning 400, the route-keyed `gate_version`, and unscored research rows sorted last.

### docs/BRAND_RELEVANCE_SPEC.md

1. **The headline rule** "cannot demote it to passing or other". The code keeps a judge's `other` (`brand_decision.py:460-467`, `brand-coverage-3`). Only Appendix C records this change.
2. **Retail deals "excluded from brand press".** Single-brand deal listings go to the judge as possible `subject` with `evidence.promotional` (`:47-49, 384-389`). Again only Appendix C reflects this.
3. **Appendix B: duplicate profiles leave the article "undecided".** The code also writes the article row as `deferred` with score 0.0 (`brand_decision_store.py:186-210`).
4. **"An unavailable judgment is not a relevance score of zero."** The article row gets 0.0 in both scores (`:193, 208`).
5. **Judge model "the site's `HYBRID_RELEVANCE_LLM_MODEL`".** `BRAND_JUDGE_MODEL` takes precedence, and `BRAND_JUDGE_FALLBACK_MODEL` adds a second route (`brand_decision.py:316-327`).
6. **Appendix A: bugfixing "Mention gate: yes".** The code is present but has no effect: `BW_BRAND_MENTION_FLOOR` is unset, and no enabled brand has `mention_context`, `exclude_context` or `non_press_domains`.
7. **"Do not leave score-only queries such as `score >= 0.4`."** The shared readable predicate is exactly that.
8. **"Ingest approves on score ≥ threshold."** The final gate ignores per-group thresholds unless the topic starts `"Brand Monitoring "`.

### docs/BRAND_RELEVANCE_SAAS_VS_MONOLITH.md

1. **Step 1, "a missing profile defers".** A missing profile returns None and the old path runs. Only a duplicate profile defers (`brand_decision.py:368-373`).
2. **Step 7 judge model.** Same as point 5 of the previous document.
3. **Step 8 headline rule.** Same as point 1 of the previous document.
4. **"The brand decision is on at every running monolith site."** Bugfixing has it off; `BRAND_RELATION_DECISIONS` is unset in `.env`. This contradicts the doc's own table.
5. **Line numbers.** The `brand_profile.py` references are 8 lines short: `build_profile` is at 220, `detect_mention` 411, `source_relation` 488, `exclusion` 531, `fan_site_reason` 549 and `promotional_reason` 562.

### Memory-note corrections

- **The CJK page-check guard** is in `app/tasks/keyword_monitor.py:23-57, 855-863`, not in `app/collectors/page_compare.py`. `page_compare.py` diffs vendor pages for Market Monitor.
- **No ThinkPol code exists in the monolith tree.** `reddit_collector.py` is the free Reddit RSS route.

---

## Defects and risks found while tracing

These are ordered by severity. I changed nothing.

1. **Keyword checkpoints stick on a full page.**
   - **Cause.** The default `collect()` marks a full page `coverage_complete=False` while leaving `status=success` (`base_collector.py:263-266`). `commit_interval` takes neither the advance branch nor the partial branch, so it falls into the failure branch: it adds one to `consecutive_failures` and keeps the window (`collection_runs.py:264-272`). The next claim returns **the same old window** (`:134-137, 189`).
   - **Who it hits.** Every list-only collector: newsfirehose (the bugfixing default), Telegram and Opoint. With `page_size` 10, any keyword with more than 10 hits in a window is affected.
   - **Live.** Firehose has 82 failing scopes, up to 10 consecutive failures, and windows stuck since 2026-10-02. Daily new rows fell from about 600 to between 76 and 488 over the same period. The timing matches, but I have not proved the cause.
   - **The likely fix** is to return `partial` with an offset continuation, or to advance anyway as the old code did. That is a code decision for you.
2. **Pages are scraped before the cheap relevance check.** Every article with 200 characters of text or less is scraped (Firecrawl) before the quick gate (`automated_ingest_service.py:1771-1792`), even though about 3 in 4 stored rows end up `filtered_relevance`.
3. **The final gate ignores the group's own threshold.** It uses the topic's lowest-id group threshold (facade `:1083-1103`). SOC Automation's 0.45 social groups are judged at 0.25. Swiss FR (0.45) is judged at 0.4.
4. **Approved rows can be invisible.** They pass a 0.25 gate and then fail the hard-coded 0.4 readable floor: 120 rows this week.
5. **The all-groups check-now** sends social groups' keywords through firehose and the news analysis step.
6. **`relevance_check_failed` rows have no retry sweep,** and they store 0.0 scores, which looks like a hard reject to readers.
7. **The quality check is a placeholder** that always approves with 0.8. Per-group `auto_ingest_enabled`, `quality_control_enabled`, `auto_save_approved_only` and the LLM parameters are stored and never applied.
8. **Social evaluation runs on claude-haiku-4-5** through `SOCIAL_EVAL_MODEL`. Your cost notes say to avoid that model.
9. **Run records and provenance have gaps.**
   - Keyword-route `collection_runs.counts` never record inserts.
   - `article_observations.provider` holds the publisher domain, not the collector.
   - 2,223 rows have NULL `submission_date`, because the database column has no default and raw-SQL writers omit it.
10. **Smaller items:**
    - `_matched_keywords` is dropped by `auto_ingest_pipeline` (`keyword_monitor.py:1373-1391`), so matched-keyword tags never reach `_merge_matched_keyword_tags`. I found this by reading the code and did not check it against stored tags.
    - `/auto-ingest/enable` returns a 500 (a `NameError` at `routes/keyword_monitor.py:3029`).
    - `daily_request_limit` is never enforced.
    - The factory accepts `NEWSAPI_KEY`, which the collector does not read.
    - The cross-provider de-duplication priority leaves out newsfirehose, xpoz, reddit and telegram.
    - `keyword_alerts` is dead (0 rows).
    - `embedding_backfill` is never started.
