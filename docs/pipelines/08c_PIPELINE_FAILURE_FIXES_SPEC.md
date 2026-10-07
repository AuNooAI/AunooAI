# Pipeline failure fixes

7 October 2026 · Implementation specification. Received from Oliver on 7 October 2026, after
08_INGEST_FIX_SPEC.md, and stored here verbatim. M1-M5 restate parts of 08_INGEST_FIX_SPEC.md (that
spec governs details); S1 and S2 are SaaS changes made in saasmvp-app on their own branch. The
implementation log is [08a_INGEST_FIX_LOG.md](08a_INGEST_FIX_LOG.md).

---

Repair the pipeline boundaries that can lose articles, approve unusable results, conceal failures or cause conflicting retries. Each fix must include the failure case that previously escaped detection, not only a successful-path test.

This specification covers the monolith and two independently identified SaaS defects. The full monolith design and related documentation/cost changes remain in the Monolith ingest pipeline fix spec (08_INGEST_FIX_SPEC.md). Where abbreviated here, that specification governs implementation details. SaaS fixes are separate changes and do not expand the monolith's scope.

## Baselines and scope

The reviewed monolith revision is `644ceec6503131472c3ea4d92895432c638b5619`; the reviewed SaaS revision is `fd102a2c98d0450b151f01e7521ab9e031aa159a`. The supplied traces refer to different canonical/deployed revisions. Record and reconcile the actual target checkout before editing, and repeat live configuration/database checks before rollout.

Preserve the five configured label lists and manual/arena behavior. Do not change brand decision logic. Do not remove the active relevance classifier or embedding encoder. No checkpoint reset, historical decision backfill or schema deletion may invent evidence that was never recorded.

## Priority and delivery

| Priority | Fix | Delivery |
|---|---|---|
| P1 | M1 Collection and coverage | First monolith change; deploy before catch-up |
| P1 | S1 SaaS importer failed-row recovery | Independent SaaS change; prevents permanent import holes |
| P2 | M2 Relevance policy and reader consistency | One coherent schema/gate/reader change |
| P2 | M3 Analysis parsing and prompt integrity | Coordinate prompt activation with mode/cache changes |
| P2 | M4 Timeouts, retry fairness and persistence | Bound calls and prevent late writes before increasing retries |
| P2 | M5 Missing embedding repair | Separate stage retries, without repeating analysis |
| P2 | S2 SaaS classification outcomes and attempt state | Distinguish errors before introducing durable skip state |

Health changes accompany each fix. Correct existing false customer documentation promptly; documentation work need not wait for every reliability fix. These priorities describe implementation urgency, not verified live severity on every tenant.

## M1 Collection and coverage

**Files:** `app/collectors/newsfirehose_collector.py`, `base_collector.py`, `contracts.py`, `app/services/collection_runs.py`, collection callers and health routes.

**Failure:** full pages repeatedly search the same interval; fetch failures can become empty successes; incomplete retrieval can falsely advance coverage.

Required changes:

1. Implement firehose traversal of every query chunk and page using validated `has_more` metadata. Bound pages and elapsed time and persist a resumable `{chunk, page}` continuation for the unchanged interval/query.
2. Preserve timezone-aware interval timestamps and verify boundary semantics. Do not determine completion from the filtered/deduplicated item count or widen every request to thirty days.
3. Classify HTTP, JSON, payload, connection, timeout, authentication and quota failures. Do not silently skip a failed chunk.
4. Preserve accumulated items on a later-page failure. Commit the continuation only after required item persistence succeeds. Failed persistence must leave a replayable position.
5. Advance proven `coverage_through` only after complete traversal and persistence, without unresolved parse loss. Partial results preserve coverage; only actual failed results increment the failure counter.
6. Report non-exhaustive provider limitations explicitly. Scheduling past a truncated interval, if later selected, must have a separate scheduling position and gap record; it must not certify full coverage.
7. Alert on failed runs and on coverage/cursors that stop progressing, even while `updated_at` refreshes. Do not skip windows after an arbitrary failure count.

Acceptance tests: multiple chunks/pages; a budget stop and resume; page-two failure after page-one success; persistence failure before cursor commit; 401/429/5xx and malformed responses; stopped server; same-day and cross-midnight bounds. No test may lose an eligible fixture item or advance proven coverage across an unresolved failure.

Recovery: preserve stuck checkpoints, deploy paging, finish the old interval and explicitly drive subsequent catch-up within budgets. Record per-scope target coverage and remaining gaps. Daily intake recovery is monitoring evidence, not proof of recovered coverage.

## M2 Relevance policy and reader consistency

**Files:** `app/services/automated_ingest_service.py`, `hybrid_relevance_service.py`, `article_visibility.py`, keyword-group callers/settings, reader routes/composers and migrations.

**Failure:** gates use different group thresholds; engine-specific acceptance fabricates threshold-valued scores; readers impose a different floor or admit failed NULL-score rows.

Required changes:

1. Carry group identity, keywords and the same threshold through quick and final scoring. Store approval-time threshold, measured scores/engine, decision outcome and policy version.
2. Keep decisions scoped to article/topic/group and the scored content. Do not combine one group's score with another group's lower threshold. Aggregate only compatible decision evidence.
3. Remove score clamping in both Jev and CE tiers. Preserve raw engine measurements. Recommended initial behavior preserves their existing accept-only criteria and records an explicit acceptance decision; numeric decisions still require the measured score to meet the group's threshold. Any stricter engine policy requires an explicit evaluated change.
4. Read new rows through valid persisted approval evidence. Retain the documented legacy/manual fallback where evidence is absent. Reject known failed/pending states independently of NULL-score handling.
5. Centralize user-facing relevance eligibility and retain intentional duplicate/press-release exclusions. Apply valid eligibility to duplicate-original checks. Audit readers using only story filters; keep audit/training exceptions explicit.
6. Use SQL for exact duplicate behavior unless the Python caller has original-readability context. Do not claim equivalent predicates when one lacks that information.

Acceptance tests: group thresholds below/equal/above the score; multiple groups on one topic; quick/final policy equality; Jev `on_topic=0.85` with group threshold `0.9`; enabled CE acceptance; NULL failure versus unscored manual row; readable and rejected originals; press-release opt-in. Count unexpected relevance exclusions separately from intentional story exclusions. No tier may manufacture a score equal to the threshold.

Decision before activation: retain valid thresholds below 0.4 or explicitly migrate to a global minimum. Do not silently raise existing settings or guess historical thresholds.

## M3 Analysis parsing and prompt integrity

**Files:** `app/analyzers/article_analyzer.py`, prompt templates/manager and mutation routes, live prompt versions, analysis consumers and cache implementation.

**Failure:** colons truncate summaries, invalid labels become empty strings, shared prompt changes affect unrelated consumers, and format locking exists only in presentation behavior.

Required changes:

1. Recognize only known field names/aliases in valid header positions. Preserve ordinary colons and multiline field content.
2. Validate required labels inside the bounded parse/retry loop. Empty/off-list required labels must retry, then produce an explicit failed analysis after exhaustion. Do not approve them merely because they are non-NULL.
3. Separate auto-ingest and manual/arena prompt contracts. Skip discarded factuality/bias output and date extraction only in auto mode; preserve manual date extraction and arena stored fields.
4. Include mode, date behavior, prompt/schema version, model, effective text and every output-affecting setting/list in cache validation. An auto cache entry must not satisfy a manual request requiring omitted fields.
5. Restore English instructions. Enforce the fixed output block server-side after effective prompt fields are merged, across save/restore/import and alternate mutation routes. Keeping `REQUIRED OUTPUT FORMAT:` while changing the block must still be rejected.
6. After the scrape-order fix, select usable cached page text before collector content/summary. Reject scrape error pages and apply a model-compatible input budget, initially evaluated at 6,000 article tokens with context/output space reserved.

Acceptance tests: colon-bearing and multiline summaries; aliases; invalid required labels; optional fields omitted in auto mode; manual/arena regression; cache crossing between modes; changed text/options/version; schema-edit attempts retaining the heading. Replay 300 approved articles before enabling page input, and check 50 non-English articles for English summaries. Record quality, token use, errors, latency and measured cost.

## M4 Timeouts, retry fairness and persistence

**Files:** ingest orchestration, analyzer/model router, cache writes, retry sweep, persistence/claim code and health.

**Failure:** a timed-out thread continues writing; overlapping retries compete; capped or newest-only rows prevent eligible failures from recovering.

Required changes:

1. Bound every provider call and fallback/retry with a finite timeout within an overall analysis deadline. Include translation and optional date calls. Stop starting new work when the remaining budget is exhausted.
2. Guard cache/database publication with attempt ownership or generation and coordinate the final write with that guard. Expired or superseded attempts cannot publish a usable late result. Merely increasing the outer `wait_for` timeout is insufficient.
3. Persist stage-appropriate attempts, errors and next-retry time. Filter eligibility/attempt caps before the SQL limit; claim due work fairly with a stable ordering and bounded concurrency.
4. Recollection of unchanged content respects the same cap. Content/configuration changes can reopen work only through an explicit version/reset policy.
5. Retry relevance failures with NULL scores and an unavailable decision, while keeping them excluded from user-facing eligibility. Expose exhausted attempts and configuration faults with a reason and next action.

Acceptance tests: blocked provider call; expiry followed by another attempt; old worker attempting a late cache/database write; overlapping sweeps; capped newest rows above an older eligible failure; repeated recollection; successful recovery after transient failure. No expired attempt overwrites a newer result; no retry-cap rows starve eligible work.

## M5 Approved articles without embeddings

**Files:** `app/vector_store_pgvector.py`, embedding backfill/sweep, approval persistence, health scripts and migrations.

**Failure:** swallowed encoder errors leave approved articles permanently absent from vector search.

Required changes:

1. Return and count meaningful vector-upsert outcomes. Record error/attempt/due-time evidence.
2. Run a dedicated repair sweep for up to 200 approved NULL-embedding rows per pass with fair ordering, claims, bounded encoder concurrency and backoff. Do not repeat successful analysis to repair a vector.
3. Restrict normal backfill to approved rows; keep broader manual repairs explicit.
4. Measure age from approval or embedding invalidation, not `first_seen_at`. Record an `embedding_due_at` or equivalent timestamp; retain a separate legacy backlog where approval time is unknown.
5. Monitor recent approvals and all-age overdue work. Verify tenant inventory, including the reported omissions abm, oviva, panaya and sunstar, against the deployed script and sync reviewed changes into the repository.

Acceptance tests: encoder unavailable/error/malformed dimensions; approval of an old collected article; concurrent repair claims; restoration after outage; rejected rows excluded. Under healthy dependencies no approved embedding remains missing more than one hour after it becomes due. During outages, overdue work remains visible and drains after restoration.

## S1 SaaS importer failed-row recovery

**File:** `scripts/import_firehose_corpus.py`, importer state migration/store and importer health.

**Failure:** row N fails, row N+1 imports, and a watermark derived from imported IDs skips N on restart. Eligibility-filtered rows can also be missed when source text/embeddings arrive later.

Required changes:

1. Separate source traversal position from the maximum ID found in destination articles. Define the eligibility/late-update contract before changing cursor behavior.
2. Before traversal moves past a failed eligible row, either successfully persist it or atomically record a durable retry entry for its source ID and error. A destination savepoint rollback must not also erase the retry record. Use bounded retries/backoff and expose exhausted entries; do not silently drop them.
3. Advance the durable traversal position only after every encountered eligible row has a persisted destination outcome or durable recovery obligation. Preserve idempotency and do not reconstruct traversal position solely from destination `nf_` IDs.
4. Track rows temporarily excluded for missing body/embedding and reconcile their later readiness through an update watermark, durable pending set or bounded periodic reconciliation. Discovery must examine source rows independently of the existing embedding inner join/body-eligibility filter, or the reconciliation must explicitly cover rows those filters omitted. Existing-row body backfill alone does not recover a source row that was never imported. Choose the mechanism according to available source metadata and prove its restart behavior.
5. Preserve source-ID association for URL-deduplicated imports so retries/reconciliation can find the correct destination without inserting duplicates or overwriting unrelated provenance.

Acceptance tests:

- Source row 100 fails while 101 succeeds; restart recovers 100 exactly once.
- Crash between destination outcome/retry recording and traversal commit replays safely.
- Deadlock retry exhaustion produces a durable, visible recovery obligation.
- A previously ineligible source row becomes usable later and imports once.
- Two source IDs sharing a destination URL retain recoverable source associations.

Health: traversal age, pending retry count/oldest age, exhausted retry count, deferred eligibility count and unassociated dedup outcomes. Throughput without zero-loss recovery is not acceptance.

## S2 SaaS classifier outcomes and durable attempt state

**Files:** `app/topics/classifier.py`, `app/tasks/topic_classifier_task.py`, classifier attempt-state migration/store and health.

**Failure:** model/parse failures and valid no-match answers both return an empty list. Skipping all empty results can suppress recoverable failures; reprocessing all no-matches can consume capacity until newer or older articles fall outside the seven-day window.

Required changes:

1. Return explicit `matched`, `no_match` and `failed` outcomes, with typed error/retryability details. Empty/unparseable responses are failures; a valid explicit no-match answer is a completed classification.
2. Persist attempts keyed by article identity, effective classifier-input hash, topic-catalogue version and prompt/model policy version. Successful matched/no-match attempts suppress duplicate unchanged work across restarts. Changed text, catalogue or policy reopens classification.
3. Retry transient failed outcomes with durable attempts, backoff and a cap. Expose exhausted/configuration faults. Never add failures to a permanent no-match skip set.
4. Select due work fairly so repeated recent no-matches cannot starve unattempted articles. Preserve a durable discovery/classification backlog; distinguish the new-input age policy from recovery of already-discovered failures. Do not let the seven-day query window silently erase pending obligations.
5. Measure intake and sustainable classifier throughput. The configured 50 articles per five minutes has an ideal ceiling of 14,400 attempts/day before latency, outages and retries; actual capacity must exceed eligible arrival rate or the backlog must remain durable and visible. Changing batch cadence requires model/rate-limit and cost checks.
6. Document and version the actual clipped classifier input, rather than describing it as full text. Ensure late body updates can change the input hash and trigger reclassification.

Acceptance tests:

- Valid no-match is skipped after restart for unchanged input/catalogue/policy.
- Timeout, empty response and malformed output remain retryable and never become no-match records.
- Topic addition, model/prompt change and later body availability reopen work.
- Repeated newest no-matches cannot block older unattempted articles.
- Pending work remains recoverable when its publication age passes seven days.
- A sustained-load run shows measured throughput and oldest pending age; overload produces a visible backlog rather than silent loss.

Health: unattempted/due/retrying/exhausted counts, oldest pending age, valid no-match rate, model/parse failure rates and measured completion throughput.

## Verification and rollout

Ship monolith and SaaS changes independently against their actual revisions. Run targeted boundary/failure tests and a representative replay, then deploy to the selected test tenant/environment before widening rollout. Capture before/after evidence with revision, configuration/prompt version, time and scope.

Monitor correctness directly: per-scope proven coverage, per-source recovery obligations, coherent approval decisions, parse failures, overdue retries and missing embeddings. Report deliberate story exclusions and valid no-match outcomes separately from failures. Intake, token savings and cost are secondary operational measures; verify pricing and show unpriced calls separately.

Retain previous code/prompt/configuration versions and compatible migrations for rollback. Do not delete retry/decision evidence during rollback or blindly reset cursors. Fix deployed documentation when behavior changes.

Before their respective activations, settle group-floor policy, Jev/CE acceptance policy, exact schema for approval/retry evidence, stage deadlines/caps, page-input cost budget and tenant rollout order. Those choices do not block firehose paging or correction of false documentation claims.

## Source references

- Monolith collection contract, firehose collector and checkpoint handling (`644ceec6`).
- Monolith relevance tiers, analysis and visibility (`644ceec6`).
- SaaS corpus importer, classifier and classifier task (`fd102a2c`).
