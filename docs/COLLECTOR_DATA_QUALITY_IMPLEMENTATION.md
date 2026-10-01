# Collector data quality: implementation notes

Companion to `COLLECTOR_DATA_QUALITY_SPEC.md`. This records what was built on
1 October 2026, the schema decisions, the shared pieces, and what is still
open. Field names here are the ones that exist; the spec's names were
proposals.

Status: code written in both canonical trees (monolith `bugfixing.aunoo.ai`,
SaaS `bugfixing.aunoo.ai/saasmvp-app`), schema applied to the bugfixing
database (`test`) and the saasmvp database (`aunoo_saas`). Nothing is committed,
nothing is restarted, and no other tenant has the migration yet.

## Shared foundation (identical files in both trees)

| File | What it is | Packages |
| --- | --- | --- |
| `app/collectors/contracts.py` | `CollectionResult`, `CollectionCounts`, the status, error-code and truncation vocabularies, `classify_exception` | 1, 14, 28 |
| `app/collectors/url_identity.py` | Canonical URL under a versioned tracking-parameter registry; identity choice by record type | 4, 27, 30 |
| `app/collectors/dates.py` | One date parser with precision, provenance and status; never substitutes now() | 7 |
| `app/services/shared_ledger.py` | Host-wide SQLite quota ledger, circuit breaker, per-host budget | 20, 21 |
| `app/services/provider_quota.py` | `QuotaGuard` and `HostGuard`, the two calls a collector makes around a request | 20, 21 |
| `app/services/collection_runs.py` | Run records and interval checkpoints with lease and version (sync in the monolith, async in SaaS) | 1, 14 |
| `tests/test_collector_foundations.py` | 42 tests, run unchanged in both trees | |

The monolith also has `app/services/rejected_candidates.py` (package 19).

### The ledger file

`/home/orochford/tenants/_shared/collector_ledger.sqlite`, env
`AUNOO_SHARED_LEDGER_PATH`. Policy file `quota_policy.json` beside it
(sample provided). The directory is `0777` without the sticky bit on purpose:
the host sets `fs.protected_regular=2`, and with a sticky world-writable
directory SQLite cannot open another user's `-wal` and `-shm` files, which
the root-owned SaaS worker and the orochford-owned tenants would otherwise
hit as "attempt to write a readonly database".

Default budgets (`DEFAULT_POLICY`): NewsAPI 100 a day, NewsData 200 a day,
Semantic Scholar 100 per five minutes, arXiv one per three seconds; Xpoz,
TheNewsAPI and Firecrawl have no known budget, so the ledger only breaks the
circuit when the provider refuses. Site allocation defaults to equal shares
with borrowing of what other sites have not used.

### Error vocabulary

`timeout`, `connection`, `dns`, `http_4xx`, `http_5xx`, `parse`,
`quota_exhausted`, `unsupported_query`, `transport_timeout`, `cancelled`,
`auth`, `blocked`, `configuration`, `unknown`. Transient HTTP statuses:
406, 408, 425, 429, 500, 502, 503, 504.

## Schema

Monolith migration `cdq_001` (revises `si_001`). SaaS migration `cdq_01`
(revises `mirror_page_events_01`; that earlier revision was also missing on
the saasmvp database and was applied first). Both are additive. Both ORM
layers carry the new columns and tables.

Monolith `rss_feeds` gains: `consecutive_error_count`, `polling_status`,
`first_failed_at`, `last_failed_at`, `next_poll_at`, `last_attempt_at`,
`last_success_at`, `coverage_through`, `etag`, `last_modified`,
`parse_partial_count`, `pending_batch`, `needs_attention_reason`.
`last_checked_at` stays as the scheduling alias.

Monolith `articles` gains: `published_at_raw`, `publication_date_precision`,
`date_provenance`, `source_indexed_at`, `first_seen_at`, `last_seen_at`,
`future_date_flag`, `content_kind`, `extraction_status`, `identity_method`,
`canonical_url`, `record_type`, `enrichment_block_reason`,
`enrichment_attempts`. `publication_date` stays TEXT.

Monolith new tables: `collection_runs`, `collection_checkpoints`,
`rejected_candidates`, `article_observations`, `article_url_aliases`,
`pending_feed_entries`.

SaaS `rss_feeds` gains the attempt/success/coverage split, `last_error`,
`last_error_code`, `parse_partial_count`, `pending_batch`,
`needs_attention_reason`, `delivery_etag`, `delivery_last_modified`.
SaaS `articles` gains the same date and identity columns plus
`original_title`, `title_provenance`, `source_authenticity`, the calendar
fields (`event_start`, `event_end`, `all_day`, `event_timezone`,
`recurrence_key`, `event_sequence`, `event_cancelled`),
`content_input_version` and `quality_flags`. `rss_article_dedup_groups` gains
`method`, `version`, `evidence`. `paper_enrichment` gains `next_attempt_at`
and `last_status`. New tables: `collection_runs`, `collection_checkpoints`,
`article_observations`, `article_url_aliases`, `article_feed_memberships`,
`websub_deliveries`, `pending_feed_entries`.

Backfill done on bugfixing only: `first_seen_at = submission_date` for
existing rows, with `date_provenance = 'unknown_pre_cdq'` where it was null.
No attempt timestamp was copied into `last_success_at` or
`coverage_through`; they start empty and fill from real runs.

## Environment knobs introduced

| Variable | Default | Purpose |
| --- | --- | --- |
| `AUNOO_SHARED_LEDGER_PATH` | `/home/orochford/tenants/_shared/collector_ledger.sqlite` | Ledger file |
| `AUNOO_QUOTA_POLICY_JSON` | unset | Inline policy instead of the file |
| `AUNOO_TENANT_NAME` | directory basename | Site name in the ledger |
| `URL_TRACKING_REGISTRY_PATH` | unset | JSON file extending the tracking registry |
| `REJECTED_CANDIDATE_LEDGER` | `1` | Turn the early-gate ledger off |
| `REJECTED_CANDIDATE_RETENTION_DAYS` | `30` | Ledger retention |
| `NEWSDATA_DATE_FILTER_SUPPORTED` | `0` | Send from_date/to_date to NewsData |
| `NEWSAPI_MAX_PAGES`, `PROVIDER_PAGE_BUDGET_SECONDS` | 5, 60 | Pagination budget |
| `ARXIV_MAX_PAGES`, `ARXIV_PAGE_BUDGET_SECONDS` | 5, 60 | arXiv pagination budget |
| `ENRICHMENT_RETRY_SWEEP_ENABLED`, `_MINUTES`, `ENRICHMENT_RETRY_BUDGET`, `ENRICHMENT_MAX_ATTEMPTS` | 1, 30, 50, 3 | Package 22 sweep |
| `RSS_GROUP_WINDOW_HOURS` | 72 | Package 18 grouping window |
| `OFFICIAL_INDEX_CURSOR_ENABLED`, `OFFICIAL_ROLLING_DAYS`, `OFFICIAL_RECONCILE_DAYS` | 1, 30, 365 | Package 11 |
| `COLLECTION_EXPECTED_INTERVALS` | unset | Health alert thresholds (JSON) |
| `ICAL_DEFAULT_TIMEZONE` | unset | Floating calendar times |

## Running the tests

Monolith: `cd /home/orochford/tenants/bugfixing.aunoo.ai && .venv/bin/python -m pytest tests/test_collector_foundations.py tests/test_collection_runs_db.py -q`
(the second file needs `CDQ_DB_TESTS=1` and writes then deletes rows in the
tenant database under provider `pytest-cdq`).

SaaS: `cd /home/orochford/tenants/bugfixing.aunoo.ai/saasmvp-app && /usr/bin/python3 -m pytest tests/test_collector_foundations.py -q`
(system python, not the venv; SaaS tests never touch the database).

Per-package test files are listed in the package sections below.

## Packages

Filled in as each package landed. See the sections below.

### 13 Compare website content accurately (both trees)

`app/collectors/page_compare.py` (identical in both trees): `extract_blocks`
reflows wrapped paragraphs and keeps list items, table rows and headings as
their own blocks; `compare_blocks` uses multiset semantics, so a moved block
is not a change but a duplicated price row is; `validate_content` returns
`ok`, `blocked`, `extraction_failed` or `suspicious_drop`. `vendor_web`
(`vendor_web_collector.py` in the monolith, `vendor_web.py` in SaaS) runs the
validator in `fetch_page`, returns `changed=False` with the reason on anything
but `ok`, and `diff_pages` delegates to the block comparison. Both callers
treat `error` as no change, so a challenge page keeps the prior baseline.
Tests: `tests/test_page_compare.py` in both trees.

Open: reseeding baselines on a normalizer version change. Both trees store the
baseline in `*_vendor_snapshots.content_hash` as a hash of the whole snapshot
dict, not of the text, so `prior_hash` never matches and `diff_pages` is what
decides today. The reseed needs `blocks_hash` and `normalizer_version` stored
inside `data` and compared before diffing. Neither caller passes `prior_text`
yet, so `suspicious_drop` cannot fire until they do.

### 14 Collection quality monitoring (both trees)

Monolith `GET /api/health/collection` (unauthenticated like `/api/health`):
run summary, quota ledger status, rejected-candidate stats, failing feeds,
configuration-blocked and enrichment-failed counts by topic, and computed
alerts (no success in two expected intervals, continuation older than two
intervals, feed failing more than 24 hours, configuration-blocked articles).
Expected intervals from `COLLECTION_EXPECTED_INTERVALS` (minutes; rss 60,
others 720). `scripts/collector_health_check.sh` gained a third check that
reads the endpoint per tenant and routes its alerts through the existing
mail path; tenants without the endpoint are skipped.
SaaS `GET /api/v1/health/collection` (platform admin only): runs, quota,
flagged feeds, paper-enrichment deferrals, WebSub delivery queue, alerts.
Tests: `tests/test_collection_health_route.py` (monolith).

### 2, 16, 21, 29 Monolith RSS path

`RSSCollector.fetch_feed_result` returns a `CollectionResult`; `fetch_feed`
is the list-returning wrapper. The collector strips a BOM and leading
whitespace, retries once when a comment precedes the XML declaration, fails
with `parse` when nothing usable comes back, and returns a partial result
with `parse_partial=True` and no validators when feedparser recovered some
entries. The 50-entry cap is gone. `since` is advisory: older entries are
returned flagged, and the monitor deduplicates by URL. A 304 is a success
with no items. Dates come from `dates.parse_date` with feed provenance;
unknown dates are stored NULL with `first_seen_at` set.

`RSSFeedMonitor` schedules from `next_poll_at`, backs off 1x, 2x, 4x, 8x on
consecutive failures, moves a feed to `needs_attention` after 20 hard
failures (403, 404, 410, DNS, parse) or 10 parse-partial polls, and never
deactivates it. Reddit hosts go through the shared host budget. Storage
returns `inserted`, `existing` or `failed`; failed entries are queued in
`pending_feed_entries` and replayed at the start of the next poll; cache
validators and `coverage_through` are written only when nothing failed and
the parse was complete. Every attempt writes a run record.
Tests: `tests/test_rss_collector_outcomes.py`, `tests/test_rss_feed_monitor_backoff.py`.

Open:
- The manual "fetch now" route in `app/routes/rss_feeds_routes.py` still uses
  the old wrapper, writes no run record and no backoff state, and sets
  `last_article_date` to now when the feed has no dates. It needs the same
  treatment as the monitor (package 2's "manual route" rule).
- NULL publication dates and readers. The one reader that raised on a NULL
  (`news_feed_service.py`, `datetime.fromisoformat` on the value) now falls
  back to the discovery date. Every `ORDER BY ... publication_date DESC` in
  the monolith (88 sites in 31 files, SQL strings and SQLAlchemy `.desc()`
  forms, including the `feed_items` readers) now says `NULLS LAST`, so an
  undated row sorts last instead of first. About 300
  `publication_date >= :since` comparisons still exclude NULL rows from
  time-windowed views; the spec's "choose publication or discovery
  explicitly" sweep for those is not done. Watch the null-date rate on the
  health endpoint; the previous behaviour never produced a NULL because it
  substituted the current time.
- `rss_feeds.pending_batch` is unused; the queue lives in
  `pending_feed_entries`. Normalisation and enrichment are not yet split
  into separately bounded batches.
- `RSSCollector.test_feed_url` (add-feed validation) does not apply the
  BOM hygiene.

### 4, 8, 30, 31 Monolith identity, merging, registry, briefing selection

`app/services/article_identity.py`: `resolve_identity` chooses the identity
by record type (social by platform and post id, scholarly by DOI, news by
canonical URL) and looks for the existing row by exact uri, alias,
`canonical_url`, then `url_key`; `record_observation` writes the
observation and alias rows with the registry version; `merge_fields` never
replaces non-empty with empty, lets full text beat an excerpt and not the
reverse, and keeps a conflicting known date (the incoming one goes on the
observation). `create_article` in the facade now resolves first, writes
`canonical_url`, `identity_method`, `record_type`, `content_kind`,
`first_seen_at` and the date columns on insert, and merges plus records the
observation on an existing row; its return shape is unchanged and the full
outcome is on `facade.last_create_outcome`. `story_url_key` strips through
the registry, so the per-host list is the single source of truth.
`scripts/propose_tracking_params.py` proposes registry additions from URL
variant groups with shared titles and writes nothing.

Briefing selection: both six-articles prompts present candidates as `a{i}`
and ask for the id only; a pick whose id and uri or title disagree is a
`selection_mismatch`, retried once, then skipped and counted
(`selection_mismatches` in the cache metadata and in the executive
briefing run metadata). No pick is resolved from a title alone.
Tests: `tests/test_article_identity.py`, `tests/test_tracking_param_proposals.py`,
`tests/test_briefing_selection_identity.py`; `tests/test_briefing_resolver.py`
was rewritten where it encoded the old title-rescue rule.

Behaviour change to know about: the canonical-URL and url_key lookups are
global with a same-topic preference, so a tracking variant collected for a
second topic lands on the first topic's row. Exact-URL repeats already did
this; `articles.topic` is single-valued in the monolith.

Open: no backfill of `canonical_url`, aliases or observations for existing
rows (they resolve through `url_key` meanwhile); the proposal script has not
been run on wileytest, where the 118 variant groups are.

### 7, 19, 22, 27 Monolith ingest path

Package 19: the early relevance gate looks every batch up in the
rejected-candidate ledger (`gate_version(keywords, threshold)`) before
scoring; a hit skips the embedding and the row write and is counted as
`already_rejected`; a fresh rejection is recorded. RSS and manual routes
never consult the ledger, and an article they accept is forgotten from it.
Callers now pass `route="rss"` or `route="manual"`; the keyword route is
resolved to its group with one query when no `group_id` is passed.

Package 22: the topic configuration is checked before any model call
(`configuration_block_reason`); an empty required list stores the article as
`quarantined_config` with `enrichment_block_reason` naming the topic and
the list, counted under `configuration_blocked`. Article faults increment
`enrichment_attempts`. `app/tasks/enrichment_retry_sweep.py` runs every 30
minutes with a budget of 50, retries configuration faults once the topic is
fixed and article faults up to three times, and writes a run record under
provider `enrichment_retry`. Started from `app_factory` unless
`ENRICHMENT_RETRY_SWEEP_ENABLED` is off. The onboarding save-topic route
refuses an empty categories or future-signals list unless the payload sets
`enrichment_disabled: true`.

Package 27: the Firecrawl batch helper returns an outcome per URL, isolates
a rejecting URL by splitting the batch, resolves Google News redirect
wrappers before the provider call, and the per-URL fallback runs for the
URLs the provider did not deliver. `extraction_status` and `content_kind`
are written on the article.

Package 7 (analyzer): `extract_publication_date_result` returns a
`ParsedDate` with model provenance and day precision; the wrapper never
returns the current time. `research.py` prefers a provider date, calls the
model only when none exists, and returns the stored publication date for
cached content instead of the submission date. The date-extraction prompt
defaults now say to answer NONE when no date is found; the per-tenant live
prompt store (`data/prompts/date_extraction/current.json`) still carries the
old text and should be updated the same way.
Tests: `tests/test_rejected_candidate_gate.py`, `tests/test_enrichment_quarantine.py`,
`tests/test_fulltext_fallback.py`, `tests/test_publication_date_extraction.py`.

Open: the keyword monitor should pass `group_id` explicitly; the UI flag for
configuration-blocked topics is not wired (`health_counts` is the data
source, the health endpoint reports it); the wileytest repair (fill the
future-signals list on the interalogistics topic, then let the sweep run
over its 597 enrichment_failed rows from the last 14 days) is a customer
configuration change and has not been made.

### 3, 11, 12, 16, 20, 24 SaaS arXiv, official sources, NewsAPI, Semantic Scholar

arXiv: `search_result` returns a `CollectionResult`; 406, 429, 503 and
connection errors retry with backoff inside a 60-second budget and a
failed query is not cached; queries are spaced three seconds apart with
jitter; a full batch is partial with an offset continuation. Versions are
split off the id, so a v2 of a known paper merges into it. The poll task
claims a fixed interval per author or category, ingests through
`resolve_and_store` without the intermediate commit, writes markers and
tags, commits once per follow, and only moves `last_paper_at` when the
interval is proven complete. Query coverage lives in
`collection_checkpoints`, separate from the per-user follow rows.

Official sources: the fixed "very high / high / least biased" stamps are
gone; records carry `source_authenticity='official'` and a `record_type`
(filing, court_opinion, regulatory_submission, scholarly). Future dates
are flagged, not clamped. All five collectors page with a shared loop
(five pages or 60 seconds), freeze the interval end, and report a 429 as
quota. Crossref without an abstract stores the venue as metadata and no
body; OpenAlex marks its truncated abstract. Crossref and OpenAlex use
index and update date cursors by default (`OFFICIAL_INDEX_CURSOR_ENABLED`),
with the bounded 30-day daily plus 365-day weekly windows as the fallback,
recorded as `retention_limit`. The poll task attributes every matched
record, not only new ones, and writes a run record per brand and source.

NewsAPI pages up to five pages with a frozen `to`, dedups across pages,
and goes through the quota guard. Semantic Scholar goes through the guard,
stops a tick on the first 429, defers throttled rows with
`next_attempt_at`, and reports refreshed, missing, transient, quota-skipped
and deferred counts in a run record.
Tests: `tests/test_arxiv_outcomes.py`, `tests/test_official_sources_outcomes.py`,
`tests/test_semantic_scholar_quota.py`, `tests/test_newsapi_pagination.py`.

Provider parameters to verify against documentation before relying on them:
Crossref `until-index-date` and cursor paging combined with a sort; OpenAlex
`to_updated_date`; SEC full-text search `from` offset; regulations.gov
`meta.hasNextPage`; CourtListener v4 `filed_before`; NewsAPI 426 for the
developer-plan limit.

Open: `app/routes/arxiv.py` still bumps `last_paper_at` from the inline
initial fetch; arXiv spacing is per process, not through the shared
ledger; no dedicated alert for ten consecutive 406 cycles (the data is in
`collection_checkpoints.consecutive_failures`); a Semantic Scholar API key
still has to be obtained and set as `SEMANTIC_SCHOLAR_API_KEY`.

### 1, 3, 5, 8, 9, 10, 20, 24, 25, 26 Monolith provider collectors and keyword monitor

`ArticleCollector` gains a non-abstract `collect(query, topic, interval_start=,
interval_end=, continuation=)` returning a `CollectionResult`; every
provider collector overrides it and `search_articles` stays as the list
API. NewsAPI, TheNewsAPI, Semantic Scholar and NewsData page under a budget
of five pages or 60 seconds with the interval end frozen and URL dedup
across pages; the NewsAPI developer-plan cap narrows the window in the
continuation. NewsAPI, NewsData, TheNewsAPI, Semantic Scholar and Xpoz go
through the shared quota guard, and the per-tenant daily counters no longer
decide whether to send. `app/collectors/query_expression.py` parses
phrases, AND, OR, NOT and brackets and compiles them per provider; NewsData
never truncates to two words or substitutes "news", and an unsupported
expression sends nothing. NewsData declares its dropped date clause
(`provider_no_date_filter`) and filters locally unless
`NEWSDATA_DATE_FILTER_SUPPORTED=1`. Bluesky sends `since`, `until` and
`sort=latest`, pages by cursor, drops posts outside the interval, and uses
the record's `createdAt` with `indexedAt` kept separately. arXiv treats 406,
429, 503 and connection errors as transient with backoff and three-second
spacing. Reddit runs its two routes with separate budgets and the shared
host budget, newest-first search, and a failed route makes the run partial.
Xpoz keeps a post without a permalink as `xpoz://<platform>/<id>`, never a
profile URL. Every collector sets `content_kind`; NewsAPI exposes its
truncated `content` at top level.

The keyword monitor claims a fixed interval per provider and keyword from
`collection_checkpoints`, commits it after saving, writes a run record,
logs "No new articles" apart from "<provider> failed: <reason>", and passes
the keyword group to the ingest batch for the rejected-candidate ledger.
Behaviour change: collection is incremental from proven coverage rather
than always the last `search_date_range` days (the first run still looks
back that far).
Tests: `tests/test_provider_collectors_outcomes.py`, `tests/test_query_expression.py`,
`tests/test_keyword_monitor_outcomes.py`.

Open: no provider offers a quota endpoint, so the daily reconciliation in
package 20 is not implemented; NewsData's `from_date`/`to_date` on the
`/news` endpoint must be verified on a paid key before turning the flag on.

### 1, 2, 4, 6, 15, 16, 18, 28, 29 SaaS RSS, pipeline, WebSub, reader

`RSSCollector._fetch_feed_result` returns a `CollectionResult` and never
writes the feed row; the task applies validators and `coverage_through`
through `commit_feed_result` only when the run may advance. BOM hygiene,
parse-partial and the no-cutoff rule match the monolith. Feed entries are
identified as `feed:{id}|{guid}` so unrelated feeds can reuse a GUID.
`CollectionPipeline.resolve_and_store` resolves identity by record type,
upserts topic ids, feed memberships, aliases and observations, merges
fields, generates a display title for titleless items, flags short and
uppercase titles instead of dropping them, and quarantines only items with
no identity and no body. Grouping confirms a title bucket with full-title
equality within 72 hours or a shared canonical URL and stores the method
and evidence. The reader picks an in-scope representative per group and
counts in-scope members, so a story whose canonical is out of scope is no
longer hidden. WebSub stores the signed body in `websub_deliveries` before
answering, returns 503 when it cannot, and `websub_delivery_loop` (now
registered in the pipeline worker) ingests it with backoff and gives up at
eight attempts. Topic-less feed failures carry the exception class, status
and host.
Tests: `tests/test_rss_collector_outcomes.py`, `tests/test_pipeline_identity.py`,
`tests/test_websub_delivery.py`, `tests/test_title_quality.py`, `tests/test_reader_grouping.py`.

Expect per-poll candidate counts and short-title rows to rise on SaaS; that
is the intended effect of packages 2 and 6.

### 5, 7, 17, 23, 25 SaaS Xpoz, Bluesky, calendar

Package 23, the cancel-scope tracebacks. The cause, confirmed against a
worker traceback: `AsyncXpozClient.connect()` enters the MCP transport and
session contexts by hand; when the handshake fails (connect timeout or 429
from mcp.xpoz.ai) it raises before marking itself connected, the two
contexts leak, and Python's async-generator finaliser later closes the
transport from a garbage-collection task that never entered its cancel
scope. The old wrapper could not see it because it was raised in a task
nobody owned. Now one task owns each session, runs every SDK call
sequentially inside it, applies the timeout inside it, and exits the
entered contexts itself with a bounded close; failures become
`transport_timeout` or a classified failure, never an escaping
cancellation. A 429 goes through the quota guard and pauses the key for
every site. Story-reach sweeps record a per-platform outcome, mark the
sweep incomplete when a platform failed, and an incomplete sweep is not
written to the reach cache. The 24-hour soak with injected timeouts has
not been run.

Package 25 and 7: the Bluesky keyword collector sends `since`, `until` and
`sort=latest`, pages by cursor, drops posts outside the interval, uses the
record's `createdAt` as the publication date and keeps `indexedAt`
separately. Package 5: an Instagram post without `code_url` keeps its
platform and id with no permalink, never a profile URL or a fabricated
`/p/` link.

Package 17: `parse_calendar_body` expands RRULE and RDATE, applies EXDATE
and detached RECURRENCE-ID overrides, keeps cancellations as flagged
observations, computes each occurrence's end from the master duration,
honours TZID and all-day exclusive ends, and resolves floating times
through `X-WR-TIMEZONE`, then `ICAL_DEFAULT_TIMEZONE`, then UTC with the
assumption recorded. Each occurrence is a `calendar_event` with
`recurrence_key` as its identity and its own content hash; DTSTART is not
written as a publication time. The RSS collector now parses the body it
already fetched instead of fetching the calendar again.
`normalize_article` passes the calendar, social and date keys through and
keeps a collector-supplied `content_hash`; the pipeline drops anything
that is not an `articles` column before building the row.
Tests: `tests/test_xpoz_cancellation.py`, `tests/test_bluesky_window.py`,
`tests/test_ical_occurrences.py`.

## Rollout state and what is still open

Done on 1 October 2026: code in both canonical trees, schema on the
bugfixing and saasmvp databases, foundation and package tests green
(monolith 268 tests across the new files, SaaS 275). Nothing is committed
and no service has been restarted, so no running process has the new
behaviour yet. The spec's rollout order says to capture baselines and
compare in shadow mode before enabling; none of that has happened.

Before the first restart:
1. Monolith readers and NULL publication dates (see package 2 notes). The
   "newest" orderings carry `NULLS LAST`; time-windowed comparisons still
   leave undated rows out.
2. Check running jobs on the tenant (`scripts/restart_when_quiet.sh --check`)
   and remember the restart loads every other session's uncommitted code.
3. The SaaS worker and web units run from the canonical tree; the three
   live saasmvp units pick up the pipeline changes on their next restart.

Not done, by package:
- 1 and 3: NewsData archive date parameters unverified on a paid key;
  arXiv spacing is per process, not through the shared ledger.
- 2: the manual "fetch now" route in the monolith still uses the old path.
- 4 and 30: no backfill of `canonical_url`, aliases or observations for
  existing rows; the registry proposal script has not been run on wileytest.
- 7: the per-tenant live prompt store for date extraction still tells the
  model to return today's date when none is found; the code defaults now
  say NONE.
- 13: baseline reseed on a normalizer version change; `prior_text` is not
  passed by either caller, so `suspicious_drop` cannot fire yet.
- 14: no baseline metrics captured; alert thresholds are the defaults.
- 20: Semantic Scholar has no API key; no provider offers a quota endpoint
  to reconcile against; per-site shares are the equal-share default until
  `quota_policy.json` is written (sample provided).
- 21: Noom (oviva, feeds 4 and 5) and Blink (bugfixing, feed 57) return 403
  on every poll; the monitor will mark them `needs_attention` after 20 more
  failures. Whether to fix their URLs or retire them is an operator call.
- 22: the wileytest interalogistics topic still has no future-signals
  list; 597 enrichment_failed rows in 14 days on that tenant. Filling the
  list is a customer configuration change. No UI flag for blocked topics.
- 23: no 24-hour soak with injected timeouts.
- 24: no dedicated alert for ten consecutive 406 cycles.
- All repairs described in the spec (replaying quota-failed windows,
  re-extracting empty bodies, merging confirmed URL-variant groups) are
  not run. The migration has not been applied to wileytest, wbm, sunstar,
  oviva, abm, panaya or wiley, and the code has not been copied to them.
