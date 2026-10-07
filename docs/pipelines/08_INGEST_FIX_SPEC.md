# Monolith ingest pipeline fix spec

7 October 2026 · Revised specification. Received from Oliver on 7 October 2026 and stored here
verbatim below the reconciliation note. Implementation branch: `fix/ingest-pipeline-spec`.

## Reconciliation with the checkout (added by the implementing session)

The spec was written against `d58ffa8c` (bugfixing) and monolith main `644ceec6`. The
implementation branch starts from `83fecd57`, which already carries two commits that touch this
spec:

- `a7b3263d` gave firehose its own paging `collect()`, but capped each OR-chunk at 3 pages and let
  that cap **advance** the checkpoint (`TRUNC_PAGE_CAP`), plus a 72-hour stall valve that advances
  a stuck window (`stalled_advanced`). WP1 items 2, 6 and 8 forbid both. This branch replaces them.
- `679ee413` already removed the discarded publication-date call from auto-ingest (WP3b.1) and
  fixed `/auto-ingest/enable` (WP7).

`644ceec6` is not present in this clone, so the GitHub line links below are navigation only.

The implementation log, with what shipped per work package and what was deferred, is in
[08a_INGEST_FIX_LOG.md](08a_INGEST_FIX_LOG.md).

---

## Purpose and implementation baseline

Restore collection progress without silently skipping articles, correct customer documentation, reduce unnecessary scraping and model calls, and make approved articles and recoverable failures behave consistently across ingestion and readers.

The supplied traces describe `bugfixing.aunoo.ai`, branch `fix/market-monitor-voices-relevance`, revision `d58ffa8c`, and database `test`. Source verification for this revision of the spec used monolith main at `644ceec6503131472c3ea4d92895432c638b5619`. Before editing, record the actual checkout and deployed revisions and reconcile differences. File and line references in the supplied traces are navigation aids and must be checked against that checkout.

Counts, costs, model settings and tenant configuration quoted below are observations reported by the 7 October traces. Repeat the relevant read-only checks before rollout; they are not acceptance results for the fixes.

## Order and scope

| WP | Change | Result | Size |
|---|---|---|---|
| 1 | Page firehose, preserve coverage and surface collection failures | Recover intake and the missing interval | Medium |
| 2 | Correct customer methodology and stale internal documentation | Describe the deployed behavior accurately | Small |
| 3 | Scrape after the gate, simplify auto analysis and change social model routing | Reduce unnecessary calls | Medium |
| 4 | Carry group policy through both gates and persist approval evidence | Make approval and reader behavior consistent | Medium |
| 5 | Retry transient failures and missing embeddings, bound analysis work and extend health checks | Recover failures automatically or expose them | Medium |
| 6 | Analyse usable page text, restore English output and enforce the response schema | Improve labels and summaries | Medium |
| 7 | Remove verified unused code and fix smaller defects | Reduce maintenance and repair secondary paths | Medium |

Ship WP1 independently after its failure tests pass. Correct WP2's existing false claims promptly, then update it again when later behavior changes are deployed. WP6 input changes depend on WP3a. Coordinate WP3b and WP6 prompt changes into one activation per analysis mode. WP4 and WP5 share visibility and schema changes and must use the same decision contract.

Out of scope: SaaS, including any `saasmvp-app/` subtree; changes to the brand decision path; and changes to the five configured label lists. Correcting descriptions of brand behavior is in scope. Remove only the obsolete enrichment classifier and services identified by a call-site audit; retain the live relevance classifier and 768-dimensional embedding encoder.

## WP1 Collection checkpoints and firehose failures

### Problem and diagnosis

The generic collector reports a full page as `success` with incomplete coverage. The checkpoint code then counts that outcome as a failure and retains the same interval. Firehose uses this wrapper without implementing traversal of every page. Its fetch path also converts HTTP and JSON errors to `None`, skips failed query chunks, and turns outer exceptions into empty lists. An outage or incomplete query can therefore appear to be a complete empty success.

The trace reports 82 affected firehose scopes on bugfixing, nine on abm, up to ten consecutive failures and intervals stuck since 2 October. Compare run item counts, requested page sizes, truncation reasons and checkpoint bounds before attributing each scope to this defect. Distinguish quota and genuine provider failures from full-page truncation.

### Required changes

1. Give firehose its own `collect()` implementation. Traverse every OR-query chunk, with at most eight terms per chunk, using the API's `has_more` response. A short post-filtered or deduplicated list is not evidence of exhaustion. Validate the paging response; absent or malformed completion metadata must not silently imply a proven end.
2. Use a bounded page and elapsed-time budget. At a budget stop, return `status=partial`, `coverage_complete=False` and a continuation identifying the next unprocessed `{chunk, page}` in the same fixed interval. Retain the query/chunk definition and provider sort parameters across resumes. Verify stable page ordering and use replay overlap and deduplication where concurrent inserts can shift offsets.
3. Keep every item accumulated before a later-page failure. Return it with a classified error and the cursor for the failed page. Persist item outcomes before committing that cursor. If persistence fails, retain a replayable position. A retry may repeat saved items but must not skip unsaved items.
4. Send full, timezone-aware timestamps for interval bounds. Verify the API's inclusive/exclusive boundary convention with same-day and cross-midnight examples, and use overlap with deduplication if needed to avoid boundary losses. Fix the bare `to_date` behavior that can collapse a same-day interval to midnight. Client filtering must respect the requested interval, rather than widening every request to thirty days.
5. Surface non-2xx responses, JSON errors, malformed payloads, connection errors and timeouts through the collection result contract. Preserve the cause for `classify_exception`, including quota/authentication distinctions. No failed query chunk may be treated as exhausted or silently skipped.
6. Advance `coverage_through` only after every chunk/page in the interval has been processed and required persistence has succeeded, with no unresolved parse loss. Clear continuation and failure state on that complete result. Partial progress retains the interval and stores its continuation. Increment `consecutive_failures` only for failed results; do not count a successful full-page observation or a budget stop as a provider failure.
7. Normalize incomplete generic successes to an explicit incomplete outcome. Use provider-specific paging where it exists. For providers without exhaustive traversal, keep `coverage_complete=False` and expose the limitation. Do not manufacture an offset the provider cannot honor. If the product later chooses to move scheduling past a truncated interval, record that scheduling position separately from proven coverage and retain an explicit gap record. That loss policy is a separate decision and is not the firehose fix.
8. Do not skip an interval after a fixed number of failures. Back off failed or non-progressing runs and alert on stalled coverage, including repeated partial results whose cursor does not progress. Increasing page size alone does not establish coverage.

### Recovery

Preserve the existing checkpoint windows, last proven coverage and continuations. With paging fixed, the next claim can finish the stuck interval and subsequent claims can collect the gap. No blanket reset of `coverage_through` is required.

Capture affected checkpoints before catch-up. Check whether the normal lookback still covers the oldest gap. Where it does not, run an explicit bounded catch-up from the last proven coverage using the fixed collector. Inspect `scripts/catchup_outage_window.py` before use; the supplied trace identifies `scripts/backfill_collection_gap.py` as broken. Reuse normal persistence and deduplication. Bound concurrency and upstream/model budgets, and trigger follow-up runs rather than waiting for the normal twelve-hour cadence to finish a multi-run gap.

### Acceptance

- A multi-page fixture, including multiple OR chunks, returns all unique eligible items and completes only at the API's proven end.
- A page/time budget stop resumes at the correct position without losing or repeatedly skipping items.
- A failure on page two preserves page-one items; replay after an item-save or checkpoint-commit failure loses no items.
- HTTP 401, 429 and 5xx, malformed JSON, a stopped server, a timeout and parse loss do not advance proven coverage. Error classification and retry policy match the cause.
- Same-day, timezone and cross-midnight interval tests preserve boundary articles.
- Completed catch-up reaches the target timestamp for each affected scope. Record remaining gaps and non-exhaustive providers separately.
- Track daily new rows against the reported late-September range of about 540–730 on bugfixing. Recovery toward that range within three days is an operational target, not proof of complete collection.

## WP2 Documentation corrections

Correct `docs/METHODOLOGY.md` against the actual deployed path and configuration. Avoid turning one tenant's setting into a universal model or region claim.

| Current claim | Required description |
|---|---|
| Fine-tuned DeBERTa assigns enrichment labels with an LLM fallback below 0.6 | A configured LLM assigns labels from the topic's lists. Identify Kimi K2.5 on Bedrock where deployment configuration confirms it. Distinguish enrichment from local relevance scoring. |
| Per-article LLM factuality is stored | Stored outlet factuality comes from Media Bias/Fact Check. Give coverage only with a measured tenant, date range and denominator; the trace reports roughly 48% blank among recent approved rows. |
| Wiley uses OpenAI 1536-dimensional article embeddings | Describe the deployed self-hosted 768-dimensional DeBERTa article encoder after checking tenant configuration and column width. Distinguish it from other relevance encoders. |
| Local mode has zero cloud cost | Inference mode governs relevance scoring; analysis uses its configured model and can incur cloud charges. |
| Analysis reads the full scraped page | Before WP6, analysis selects the collector summary, then content. After WP6 deployment, describe page selection and its token budget. |
| LLM adjudication always occurs between 0.3 and 0.7 | Describe the actual relevance tiers, confident local band below 0.20 or above 0.85, Jev/CE exceptions and fallback configuration. Brand/market handling can differ. |
| Tags come from KeyBERT | Tags are generated by the analysis LLM. Describe matched search keywords only after WP7 passes them through, and state whether they are stored separately or merged into tags. |

Inventory every service receiving article text: analysis and fallback models, relevance judges, translation, enabled shadow checks, scrape services and embedding services. Record purpose, actual provider/model, configured region and fallback destinations. Separate configured destinations from verified deployment facts; do not infer a region from a model alias.

Internal documentation changes:

1. Mark `docs/SLM_PIPELINE_SUMMARY.md` historical at the top rather than rewriting its old design as current behavior.
2. Rewrite enrichment and embedding sections in `docs/AI_DESIGN_PATTERNS.md` from the checked implementation and section 11.2 of the enrichment trace.
3. Replace “nothing is committed” in `docs/COLLECTOR_DATA_QUALITY_IMPLEMENTATION.md` with verified commit IDs and deployment dates.
4. Update `docs/EMBEDDING_HEALTH_MONITORING.md` and the 768 runbook to describe current failure handling and manual backfill, then revise them when WP5 automation ships.
5. Replace the obsolete ChromaDB reindex instruction in `CLAUDE.md` with the inspected `app/tasks/embedding_backfill.py` and `scripts/embedding_768_postbackfill.py` procedures.
6. Correct the module description in `app/vector_store_pgvector.py`.
7. Correct brand documentation about the headline rule, judge order and per-site enablement without changing brand decisions.

Acceptance: every current-behavior claim has an implementation/configuration or dated database check. Historical OpenAI/1536-dimensional references are clearly labeled historical. No current customer claim describes a future fix as already deployed.

## WP3 Cost fixes

### WP3a Scrape after sufficient evidence passes the gate

Remove batch pre-scraping. Read the `raw_articles` cache first. For articles with enough collector/cache text to judge relevance, run the quick gate before scraping; scrape retained articles in the existing parallel work with the MBFC lookup.

Keep a per-article scrape for missing text. Define and test insufficient evidence for very short snippets as well: moving a scrape behind a gate can change approvals when that scrape previously supplied the only useful text. Do not confidently reject an article solely because the new input order removed its usable evidence. Record why a pre-gate scrape was needed.

Compare the same replay sample before and after the change, including empty/short summaries, non-English articles and provider mix. Measure calls per collected item as well as total calls so WP1's intake recovery does not obscure savings. Target at least a halving of scrape calls on the controlled sample and investigate an approval-share difference over two percentage points before activation.

### WP3b Remove discarded auto-ingest output

1. Add an explicit auto-ingest analysis mode that skips publication-date extraction. Preserve manual research date extraction and the collected date/provenance fields. The trace's approximately 2,900 date calls per week is a baseline to repeat, not a guaranteed saving.
2. Use a distinct prompt variant for auto-ingest that omits Political Bias, Factuality and their explanations. Preserve the manual/arena contract and fields stored by the model bias arena. Do not globally replace the shared prompt without routing consumers to the appropriate variant.
3. Activate the new prompt through the live disk-backed prompt/version mechanism. Updating bundled templates alone is insufficient where a live current version overrides them.
4. Include analysis mode, date-extraction behavior, effective prompt/schema version, model, content and all output-affecting topic/options settings in cache validation. An auto result must not satisfy a manual request that needs omitted fields or a publication date. Verify content-hash and prompt-hash invalidation.
5. Combine the English/schema changes in WP6 with this activation per mode. Monitor the expected initial cache misses and resulting load.

Acceptance: auto-ingest emits no date-extraction use-case calls; manual date extraction and arena field storage still work; auto/manual cache-crossing tests pass. Target roughly one-third lower mean completion tokens on matched auto-analysis inputs, with call volume, prompt version and model recorded.

### WP3c Social evaluation model routing

Compare Kimi and/or Nova Lite against existing Haiku results on 200 recent posts before selecting a replacement. Review relevance, sentiment, errors, latency and measured cost.

Inspect every effective route: `SOCIAL_EVAL_MODEL`, group `default_llm_model`, retry/sweep construction and fallback settings. Change overrides that would otherwise retain Haiku. The trace reports group 23 already uses Kimi; recheck it. Limit changes to social evaluation routing so shared model settings do not unintentionally change news analysis.

Acceptance: selected groups use the chosen route and produce no Haiku 4.5 social-evaluation calls, including retries/fallbacks. Retain the previous configuration for rollback.

## WP4 Group policy and durable approval evidence

Carry the matching group's threshold and context through quick scoring, final scoring, persistence and readers. Preserve the distinction between a measured score and an acceptance decision: local, Jev and CE values are not automatically interchangeable probability scales.

### Required changes

1. Thread `relevance_threshold_override` and group identity through both gates for all relevant topics. Remove the brand-prefix condition governing the final override. Validate thresholds in the settings endpoint.
2. Store the approval-time threshold in `articles.relevance_threshold_applied`. Also persist the measured score, scoring engine/method, decision outcome and policy version. Use an explicit acceptance field, such as nullable `relevance_accepted_applied`, so an engine-specific accept is not encoded by fabricating a score equal to the threshold. Final schema names must be settled in the migration design.
3. Retain raw Jev `on_topic` and CE measurements under their engine names. Remove threshold-clamping from both tiers. Do not blindly substitute their measurements into a comparison designed for the local score. Recommended initial policy: preserve existing accept-only behavior when Jev clears `JEV_ACCEPT_MIN` or the enabled CE tier clears its own criterion, record that acceptance explicitly, and retain the group threshold as context. For ordinary numeric decisions, acceptance requires the score to meet the group's threshold. A change requiring Jev/CE to meet the group threshold is a separate behavioral decision requiring sample evaluation.
4. Record approval evidence per article/topic/group when multiple groups are involved. A row-level lowest approving threshold is valid only for decisions sharing the same topic, scored content, engine/policy and measured score. Otherwise keep separate decision records rather than pairing one group's score with another group's threshold. Group-specific readers use that group's decision; topic readers use valid approval evidence for that topic.
5. Update the central readable predicates to honor a valid persisted decision for new rows. Ordinary score decisions use the stored threshold; engine-specific accepts use their recorded policy outcome. For legacy rows without decision evidence, retain the existing score rule with `COALESCE(relevance_threshold_applied, 0.4)` until a documented re-evaluation or reliable backfill. Do not guess historical group thresholds.
6. Reject known failed/pending ingest states even when scores are NULL. Preserve manual/legacy handling for genuinely unscored records and the existing press-release and duplicate rules. Apply the same base eligibility to duplicate-original checks so a failed original cannot hide a valid copy.
7. Replace private relevance floors in Brand Watcher routes, dashboard and briefing composer with the central policy. Audit all reader families, including paths that currently use only `story_sql`/`story_clause`, and state which legitimately serve audit/training data. Python checks need original-readability context for exact duplicate parity; use SQL where that context is unavailable.

Decision: allow group thresholds below 0.4, or enforce a product-wide minimum. Until that is resolved, preserve valid existing group settings and make readers respect the applied decision; do not silently raise group 16's reported 0.25 threshold. If a minimum is selected, migrate settings explicitly and record its effect on approvals.

Acceptance:

- Quick and final gates receive the same group policy, including multiple groups on one topic.
- Threshold boundaries, low-threshold groups, NULL scores, legacy rows and Jev/CE values on both sides of their criteria have meaningful tests. Include Jev `on_topic=0.85` with group threshold `0.9` to prove the selected policy.
- New approvals contain coherent decision evidence; no tier manufactures a score by clamping to the approval threshold.
- Zero unexpected relevance exclusions among approved eligible rows. Deliberately hidden press releases and story copies remain separately counted.
- SQL and Python predicates agree when supplied equivalent context.

## WP5 Failure handling and health

Every recoverable failure must be retried within a bounded policy. Configuration faults, exhausted attempts and unsupported provider coverage must be visible with a reason and next action; they must not retry indefinitely.

### WP5a Relevance failures

Write NULL scores for `relevance_check_failed`, retain error details and mark the decision unavailable. Exclude this state explicitly from user-facing eligibility, including reader paths and duplicate-original checks affected by NULL semantics. Retry it with a defined cap, backoff and durable attempt count. Successful retry replaces failed decision evidence atomically.

The brand decision path remains out of scope: do not change `brand_decision_store.py` or its deferred/unavailable score behavior in this work package. Track any equivalent brand defect separately.

### WP5b Missing embeddings

Return a meaningful success/failure result from `upsert_article_async` and count failures in batch results. Record when embedding became due—normally the latest transition to approval or invalidation of a previous embedding—so an old article approved today is not immediately treated as an hour overdue.

Add a sweep for up to 200 approved rows with NULL embeddings per pass. Select due retries fairly, use bounded encoder concurrency and backoff, and prevent duplicate workers from claiming the same work. Embedding retries must not repeat analysis. Restrict normal embedding backfill to approved rows; any broader manual/audit repair requires an explicit selector.

Implement check E for recently approved rows, plus an all-age overdue count so an outage older than 24 hours does not disappear from health. Every embedding failure or exhausted retry remains counted with its last error. Avoid starving old missing embeddings by always selecting only newest rows.

### WP5c Retry starvation and recollection

Filter eligible retry states and `enrichment_attempts < ENRICHMENT_MAX_ATTEMPTS` in SQL before applying the sweep limit. Increment attempts for every actual retry of the relevant stage. Use oldest due/next-retry ordering with a stable tie-breaker, stage-specific counters where required, and claims to avoid overlapping retries.

Recollection of unchanged content must respect the same attempt cap. Changed content or repaired topic configuration may reopen work through an explicit versioned/reset policy. Expose capped and configuration-blocked rows in health instead of silently hiding them or blindly retrying them. Keep deterministic relevance rejects and unknown-topic outcomes separately counted.

### WP5d Analysis deadlines and late results

An outer `asyncio.wait_for` cannot stop a blocking worker thread. Set finite timeouts on every provider call, including router fallbacks, parse retries, translation and optional date extraction. Pass an overall deadline through analysis and do not begin a call/retry beyond the remaining budget. The batch deadline must accommodate the selected per-article policy.

Prevent expired/superseded attempts from committing late cache or database writes. Use an attempt generation/ownership guard and serialize the final decision with persistence, or an execution design that waits for actual worker termination before releasing ownership. A deadline checked only between calls is insufficient. A longer outer timeout is not the acceptance condition.

Acceptance includes a deliberately blocked provider call: after the attempt expires and a new attempt starts, the old attempt cannot overwrite its result or publish a cache entry usable by the new request. Verify that timeout recovery does not create overlapping unbounded work.

### WP5e Tenant health

Reconcile the deployed tenant inventory with `scripts/embedding_health_check.sh`, including the reported omissions abm, oviva, panaya and sunstar. Sync reviewed deployed changes into the repository and confirm which tenants the revised job actually checks.

Alert on real `consecutive_failures >= 3` and on coverage/continuation that has made no progress. Use last proven coverage and cursor progress, not only `updated_at` or a successful-but-incomplete run timestamp: repeated retries refresh those fields. Clear alerts only after the monitored failure or stall is resolved.

Acceptance: every failure state has a documented retry or visible terminal disposition; retry-cap rows cannot starve eligible work; no approved row remains without an embedding for more than one hour after embedding became due under healthy dependencies. During an encoder outage, overdue work must remain visible and recover on restoration. All intended tenants report health.

## WP6 Analysis input and response format

### WP6a Page input

After WP3a, select usable, fresh scraped page text from `raw_articles`, then collector content when it contains more usable text than the summary, then summary. Reject scrape error pages/boilerplate as input and retain a fallback. Do not re-scrape solely because analysis chooses the page text already in cache.

Start the evaluation at a 6,000-token article-input budget. Reserve space for instructions, configured label lists and output within the model context limit. Use an appropriate tokenizer or a documented conservative bound. Record chosen source, content hash, original/used length and truncation without logging article bodies unnecessarily. Cache validation must include the effective selected text and options.

Replay 300 approved articles, stratified by provider, length and language, using unchanged label lists. Compare category, sentiment, summary quality, errors, latency and measured cost per call. Do not assume cost rises or quality improves in every case. Choose the budget and acceptable measured increase before enabling full-page analysis broadly.

### WP6b English output

Restore explicit English instructions for summaries, explanations and tags in the appropriate new prompt variants. Preserve source-language originals where the existing product stores them. Activate with WP3b once per mode, and verify manual and arena variants independently.

### WP6c Enforce the format on the server

Use the literal `REQUIRED OUTPUT FORMAT:` separator, but enforce the immutable output block/schema in the save service. Ordinary dashboard/API edits may change instructions; they must not alter, delete or rename required fields or bypass the rule by retaining only the heading. Validate effective prompt data after merging additional fields. Apply the same invariant to save, restore/import and every alternate mutation route.

Schema migrations may deliberately replace the fixed block through an explicit versioned migration. Preserve topic label substitution. The frontend split is presentation behavior and is not the enforcement boundary.

### WP6d Parser and validation

Start a new parsed field only when text before the colon matches a known field name/alias in a valid field-header position. Preserve colons within summaries and explanations. Handle aliases, multiline values and omitted optional auto-mode fields without inventing empty labels.

Run label validation inside the bounded parse/retry loop. A required sentiment that becomes blank after validation is a parse failure and must retry; apply equivalent checks to other required labels. After retry exhaustion, record an analysis failure rather than approving invalid empty labels. Existence checks must distinguish NULL from empty strings.

Acceptance: usable cached pages are selected and their source/hash recorded; truncation obeys the effective budget; 50 non-English sample articles produce English summaries; manual/arena outputs remain intact; colons and multiline fields parse correctly; invalid required labels retry; dashboard and direct API attempts to change the fixed schema are rejected. Test a changed block that retains the required heading.

## WP7 Cleanup and secondary defects

### Remove only after auditing consumers

- Repoint `/test-process-article` and the two identified scripts to the async path, then audit routes, tasks, tests, scripts and training tools before removing the obsolete enrichment classifier, `EnrichmentService`, `HybridEnrichmentService`, bootstrap service and sync analysis implementation. Keep live relevance and embedding dependencies.
- Remove `ArticleAnalyzer.get_cached_analysis` after confirming no callers rely on its interface.
- Stop writing the placeholder `quality_score=0.8`. Decide whether to remove the stage or implement a real quality check with defined semantics; do not fabricate a historical backfill.
- For per-group `auto_ingest_enabled`, `quality_control_enabled`, `auto_save_approved_only`, `llm_temperature` and `llm_max_tokens`, either honor the advertised setting or deprecate it explicitly in API/UI. Do not silently remove user controls.
- An empty recent column/table does not establish that it is unused. Audit `articles.enrichment_sources`, `keyword_alerts` and `news_feed_scheduler.py` across readers, writers and deployment before deprecation. Drop schema only after compatible application code is deployed and data retention/rollback requirements are settled.

### Repair smaller paths

| Defect | Required repair |
|---|---|
| All-groups check-now sends social keywords through the news path | Reuse `check_single_group` routing and preserve provider-specific outcomes, limits and error reporting. |
| Auto-ingest now stamps `topic='general'` | Carry each article's actual group/topic context. Preserve separate decisions when multiple groups matched. |
| `/auto-ingest/enable` references an undefined toggle | Resolve the toggle from validated request/state and test enable/disable behavior. |
| `_matched_keywords` is dropped | Carry it as `matched_keywords`; define separately stored search terms versus generated tags and preserve that contract. |
| Expired analysis cache files are not removed | Schedule `cleanup_expired()` daily without blocking the async retry loop or deleting in-flight cache writes. |
| MBFC lookup re-enables disabled sources | Make lookup read-only; keep source-enable changes in their explicit administrative path. |
| Keyword run records omit insert outcomes | Feed actual inserted, duplicate, updated and failed persistence outcomes into run counts. |
| Observation provider can become the publisher domain | Prefer normalized collector identity, with a defined legacy fallback. Provider participates in identity generation: test provider/external-ID collisions and old-row replay, and plan compatible migration/aliasing before changing existing observation keys. |
| Reported NULL `submission_date` values | Validate the column type/timezone, add the appropriate default for new rows and backfill from `first_seen_at` only where NULL. Do not change publication-date semantics. |
| Factory accepts `NEWSAPI_KEY` but collector does not | Accept both supported variable names with documented precedence; keep credentials out of logs. |
| `daily_request_limit` is not enforced | Implement shared accounting at the actual request boundary, including retries/chunks, or explicitly deprecate the control. |
| Dedup priority omits firehose, xpoz, reddit and telegram | Add deterministic priorities and verify body/source preservation and story/press-release rules. |
| Topic creation accepts empty label lists | Validate all five lists without changing their values; validate edits too if they can recreate the fault. |

## Verification evidence and queries

Run read-only checks before and after each package on `test`, then on the rollout tenant. Retain timestamps, tenant, checkout/deployed revision, configuration/prompt version and results with the change. Verify actual schema/column names before executing the queries below.

### Collection state and intake

```sql
SELECT provider,
       count(*) FILTER (WHERE consecutive_failures >= 3) AS repeatedly_failed,
       count(*) FILTER (WHERE continuation IS NOT NULL) AS resumable,
       max(consecutive_failures) AS max_failures,
       min(coverage_through) AS oldest_proven_coverage
FROM collection_checkpoints
GROUP BY provider;

SELECT provider, scope_key, coverage_through, continuation,
       consecutive_failures, last_error_code, updated_at
FROM collection_checkpoints
WHERE consecutive_failures >= 3 OR continuation IS NOT NULL
ORDER BY provider, scope_key;

SELECT date_trunc('day', first_seen_at) AS day, count(*) AS new_rows
FROM articles
WHERE first_seen_at > now() - interval '21 days'
GROUP BY 1 ORDER BY 1;
```

Compare per-scope coverage and cursors over time, including apparently successful scopes that have no continuation. These snapshots and daily totals cannot prove progress or complete recovery by themselves. Reconcile exhausted upstream fixtures/intervals with persistence outcomes and the catch-up target.

### Approval evidence and visibility

After WP4's migration, use the central predicate to audit actual reader exclusions. Count intentional press-release/duplicate exclusions separately. This diagnostic lists all scored approvals below their applied threshold and groups them by recorded acceptance. It includes intentional engine-specific accepts so their decision evidence can be checked; it is not the complete readability test:

```sql
SELECT topic, relevance_accepted_applied,
       count(*) AS scored_approval_below_threshold
FROM articles
WHERE ingest_status = 'approved'
  AND topic_alignment_score IS NOT NULL
  AND topic_alignment_score < COALESCE(relevance_threshold_applied, 0.4)
  AND first_seen_at > now() - interval '7 days'
GROUP BY topic, relevance_accepted_applied;
```

An ordinary numeric approval below its applied threshold is inconsistent even if its acceptance flag is TRUE. Check engine-specific accepts against their recorded engine criterion/policy version. Audit every new approval's decision evidence, including approvals of older collected articles; `first_seen_at` alone does not identify the post-rollout approval cohort. The audit implementation must use the finalized schema for per-group decisions and exclude no erroneous decision merely because its acceptance flag is set.

### Embedding backlog

The age SLA uses approval/embedding-due time, not collection time. Assuming the WP5 migration names that field `embedding_due_at`:

```sql
SELECT count(*) AS missing_total,
       count(*) FILTER (
         WHERE embedding_due_at < now() - interval '1 hour'
       ) AS missing_overdue,
       count(*) FILTER (WHERE embedding_due_at IS NULL) AS missing_due_timestamp
FROM articles
WHERE ingest_status = 'approved' AND embedding IS NULL;
```

Backfill due-time evidence conservatively for legacy rows and retain a separate legacy backlog count where approval time cannot be recovered. Include retry attempts, last error and next due time in health. A zero recent-row count must not hide an old backlog.

### Cost and call counts

```sql
SELECT use_case, model, count(*) AS calls,
       count(*) FILTER (WHERE cost_usd IS NULL) AS unpriced_calls,
       round(sum(cost_usd)::numeric, 2) AS recorded_cost_usd
FROM llm_usage_log
WHERE created_at > now() - interval '7 days'
GROUP BY 1, 2 ORDER BY recorded_cost_usd DESC NULLS LAST;
```

Compare matched inputs and calls/tokens per item as well as totals. Verify model price configuration before interpreting dollars; NULL pricing is unknown cost, not free usage. Separate auto analysis, manual/arena, social evaluation, translation and shadow calls.

## Rollout and remaining decisions

For each package, ship a reviewable code/migration change with the relevant fixture or replay results. Record the deployed revision and activate bugfixing first; evaluate tenant-specific configuration before widening rollout. Keep code, prompt and configuration rollback versions. Leave new migration columns compatible with the previous application where possible so a code rollback does not require dropping evidence.

WP1 is ready to proceed with paging and preserved windows; no decision to silently advance truncated firehose coverage remains open. The remaining choices are:

- [ ] Permit group thresholds below 0.4 or migrate to a product-wide minimum.
- [ ] Confirm the initial Jev/CE policy preserves existing engine-specific accepts, or explicitly select and evaluate a stricter policy before WP4 activation.
- [ ] Select the social replacement from the 200-post evaluation and update all effective overrides.
- [ ] Set the full-page token budget and acceptable measured cost increase after the 300-article replay.
- [ ] Remove the quality stage or implement a defined real check; placeholder scores stop in either case.
- [ ] Set stage retry caps, call deadlines and sweep budgets from measured throughput and outage behavior.
- [ ] Select tenant rollout order after bugfixing and any explicit loss policy for genuinely non-exhaustive providers.

These choices do not block the collection repair or corrections to existing false documentation claims.

## Implementation references

The supplied `01_NEWSFIREHOSE.md`, `02_MONOLITH_COLLECTION_CURATION.md`, `03_MONOLITH_ENRICHMENT.md` and `06_FIREHOSE_CHECKPOINT_STALL.md` provide the trace context and dated database observations. Checked monolith source references (commit `644ceec6`, not present in this clone):

- Collection completion contract `app/collectors/contracts.py#L100-L194` and checkpoint commit `app/services/collection_runs.py#L226-L277`.
- Generic full-page behavior `app/collectors/base_collector.py#L233-L267` and firehose fetch/filter behavior `app/collectors/newsfirehose_collector.py#L203-L384`.
- Jev and CE accept tiers `app/services/hybrid_relevance_service.py#L884-L940` and article visibility `app/services/article_visibility.py`.
- Analysis cache, retry and write behavior `app/analyzers/article_analyzer.py#L154-L309`.
- Prompt save endpoint `app/routes/prompt_routes.py#L115-L147` and prompt manager `app/analyzers/prompt_manager.py`.
- Social group override `app/services/social_eval_service.py#L1003-L1009` and provider identity resolution `app/services/article_identity.py#L125-L239`.
