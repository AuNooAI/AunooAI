# Collector data quality implementation specifications

These specifications cover the SaaS repository, aunooai-saas, and the monolith repository, AunooAI. They turn both collector reviews into implementation work for collection completeness, identity, timestamps, metadata, relevance, and website changes.

Status: proposed implementation, revised after a third source review on 1 October 2026, and extended the same day with work packages 19 to 31 from a seven-day log and database review (see "Evidence from logs" at the end). Evidence for packages 1 to 18 comes from repository main branch inspection and isolated function probes, not a production corpus audit. Field names, defaults, and interfaces below are proposed unless explicitly described as existing. Resolve each repository to a commit before implementation and record that commit in its pull request.

An external operational review on 1 October 2026 checked packages 19 to 31 against source and consolidated them into a 26-package layout (error diagnostics folded into 14, Xpoz cancellation into 16, the tracking-parameter registry into 4, arXiv 406 merged with source backoff, and NewsData merged with Bluesky). This document keeps the 31-package numbering; the review's verified findings are folded into packages 7, 20, 21, 23, 27, and 31 below, and its limits on the evidence are recorded in "Evidence from logs".

## Delivery order

| Work package | Priority | Applies to | Delivery dependency |
| --- | --- | --- | --- |
| 1 Collection outcomes and checkpoints | P1 | Both | Foundation for 2 and 3 |
| 2 Complete and recover RSS collection | P1 | Both | 1 |
| 3 Complete provider collection | P2 | Both | 1 |
| 4 Article identity and association merging | P1 | Both | Independent of 1 |
| 5 Preserve social post identity | P1 | Monolith and SaaS | 4 |
| 6 Retain valid short and titleless content | P1 | SaaS | Independent |
| 7 Publication dates and discovery dates | P2 | Both | Additive schema first |
| 8 Merge content and provenance | P2 | Both | 4 and 7 |
| 9 Preserve query meaning | P2 | Monolith | Independent |
| 10 Balance Reddit collection routes | P2 | Both | 1 and 4 |
| 11 Recover late indexed scholarly records | P2 | SaaS | 1 and 7 |
| 12 Separate authenticity from credibility | P2 | SaaS | 7 and 8 |
| 13 Compare website content accurately | P2 | Both | Independent |
| 14 Collection quality monitoring and repair | P1 support | Both | Instrument throughout |
| 15 Reliable WebSub delivery | P1 | SaaS | 1 and 2 |
| 16 Isolate fetch state and database failures | P1 | Both | 1 and 2 |
| 17 Preserve calendar occurrences and changes | P1 | SaaS | 4 and 7 |
| 18 Conservative reader grouping | P1 | SaaS | 4 |
| 19 Remember rejected candidates | P1 | Monolith | Independent |
| 20 Shared provider quota ledger and circuit breaker | P1 | Both | 1 |
| 21 Back off failing sources and budget shared hosts | P1 | Monolith | 1 |
| 22 Quarantine and retry enrichment config gaps | P1 | Monolith | 14 |
| 23 Xpoz MCP client cancellation safety | P1 | SaaS | 16 |
| 24 Treat arXiv 406 as transient | P2 | Both | 1 and 3 |
| 25 Bluesky collection window | P2 | Monolith | 1 and 7 |
| 26 NewsData date filter as a declared limitation | P2 | Monolith | 3 and 9 |
| 27 Per-URL full-text fallback | P2 | Monolith | 8 |
| 28 Complete error diagnostics | P2 | SaaS | 14 |
| 29 Feed XML hygiene and partial-parse state | P2 | Both | 2 |
| 30 Publisher-specific tracking parameter registry | P2 | Both | 4 |
| 31 Briefing selection identity | P2 | Monolith | 4 |

P1 work should ship before expanding collector volume. P2 order can vary by provider usage. These are work packages, not a requirement for thirty-one separate pull requests. Packages 15 through 18 contain specific recovery and visibility requirements in addition to the shared contracts. Packages 19 through 31 come from production logs rather than code review; each names the measured count that motivated it.

## Shared design requirements

Collection must distinguish an empty successful response from failure and incomplete coverage. A retry must preserve enough state to recover the unfinished interval. A duplicate can contain a new topic, feed, brand relationship, or richer observation; finding the existing article must not discard those changes.

Adapters own provider parsing and supported query translation. Shared ingest owns validation, identity resolution, metadata merging, associations, and persistence. Both repositories should follow the same contract while retaining their existing database abstractions. This specification does not require moving the monolith onto the SaaS ORM.

Tenant access checks apply to every association write, including background tasks running with an administrative role. A globally shared article must not imply globally shared feed subscriptions, brand classifications, or private source data. Preserve current authorization boundaries and verify tenant isolation with integration tests.

## 1 Collection outcomes and checkpoints

**Problem.** SaaS official adapters catch HTTP errors and return an empty list. The poll task then marks the source polled. RSS attempt timestamps are also used as collection cutoffs. Scheduling and completeness become indistinguishable.

**Entry points.** SaaS: collectors/base.py, collectors/official_base.py, collectors/arxiv.py, tasks/collector_task.py, tasks/official_sources_poll_task.py, tasks/arxiv_poll_task.py, routes/arxiv.py, and routes/websub.py. Monolith: collectors/base_collector.py, tasks/keyword_monitor.py, tasks/rss_feed_monitor.py.

**Required behavior.**

Introduce an internal CollectionResult used by background callers, with these proposed fields:

| Field | Meaning |
| --- | --- |
| status | success, partial, or failed |
| items | Valid normalized records returned so far |
| interval_start and interval_end | Fixed query boundaries for this run |
| coverage_complete | Whether all retrievable pages or entries in those boundaries were processed |
| continuation | Opaque provider cursor or resumable local batch position |
| error_code and retryable | Stable failure category and retry advice |
| counts | Received, invalid, filtered, inserted, updated, and duplicate records |
| truncated_reason | Provider limit, time budget, quota, or retention limit |

Adapter counts describe observations received, parsed, rejected, and filtered. Ingest counts describe articles inserted or updated and associations created. Do not ask an adapter to report database insert counts. A failed source request must not be cached as a successful empty result. Cache entries include outcome, query boundaries, coverage state, and expiry; only genuinely successful empty results qualify as empty-result caching.

Separate last_attempt_at, last_success_at, and coverage_through. Keep an existing last_checked_at field as a scheduling alias where compatibility requires it; remove its use as evidence of collection coverage. For feed sources without a meaningful time cursor, use committed cache validators and entry identity rather than inventing a publication watermark.

Fix interval_end at run start. Persist valid partial items idempotently and retain a continuation without advancing the interval coverage checkpoint. Resume the same fixed interval before starting another one. A genuine successful empty interval can advance the checkpoint. A 429, timeout, invalid response, or exhausted budget cannot.

Store data, associations, continuation, and checkpoint changes atomically for each committed batch. Use a provider or feed lease and compare the expected checkpoint version at commit to prevent concurrent workers from overwriting newer state. Compatibility wrappers may still expose list-returning methods, but background tasks must consume the structured result.

**Acceptance tests.**

- A successful empty response advances coverage; an HTTP failure returning no items does not.
- Page one succeeds and page two fails: page one persists, status is partial, and retry resumes without losing or duplicating items.
- Failure before commit leaves the checkpoint unchanged; retry after commit is idempotent.
- Two workers claiming the same interval cannot regress or incorrectly advance its checkpoint.

**Migration and repair.** Add nullable checkpoint fields before switching callers. Existing attempt timestamps must not be copied into last_success_at without evidence. Initialize uncertain sources with a bounded replay window and mark their historical coverage unknown. Preserve raw error details in logs while excluding credentials.

Sources: [official poll caller](https://github.com/AuNooAI/aunooai-saas/blob/main/app/tasks/official_sources_poll_task.py#L262), [RSS collector](https://github.com/AuNooAI/aunooai-saas/blob/main/app/collectors/rss.py).

## 2 Complete and recover RSS collection

**Problem.** SaaS filters against last_checked_at, including timestamps recorded after errors. Monolith stops after 50 entries and advances last_article_date to the newest returned date. Both can miss entries that remain available in a feed.

**Required behavior.**

For SaaS XML and JSON feeds, inspect all entries present in a successful response and use stable entry identity for replay. Publication time alone must not exclude an unseen entry. Separate scheduling backoff from recovery state. Topic-bound, standalone, manual refresh, and WebSub ingestion must use the same identity and checkpoint rules.

For monolith, remove the collection-layer 50-entry truncation. Bound normalization and enrichment in separate batches. If a response exceeds the processing budget, retain a durable pending batch containing remaining entry identities and sufficient payload to finish processing. Commit the response ETag and Last-Modified only when all relevant entries have been persisted or durably queued. Otherwise the next conditional request could return 304 while unfinished content is lost.

A fetch or parse failure must not advance the data checkpoint or commit new cache validators. A malformed XML response that yields no valid feed structure must be an error, not a healthy empty feed. A valid empty feed and a valid 304 remain successful outcomes. Individual malformed entries should be quarantined with a reason while valid entries proceed.

Preserve existing restamped-date checks. Their output must retain date provenance and must not cause unseen records to be skipped solely because their corrected publication date is old.

**Acceptance tests.**

- A newest-first feed with 120 unseen entries stores all 120 across bounded batches.
- Failure between polls does not prevent recovery of entries published during the failed interval.
- A newly added entry with an old or equal publication timestamp is collected once.
- A changed response followed by a crash and a 304 cannot strand pending entries.
- Invalid XML is failed; a valid empty feed is successful.
- Standalone, topic-bound, manual, and push routes resolve the same record identity.

**Repair.** Replay current feed contents, then publisher archives or existing historical snapshots where available. A rolling feed cannot restore content it no longer exposes; report such gaps as unknown rather than claiming full recovery.

Sources: [SaaS cutoff and errors](https://github.com/AuNooAI/aunooai-saas/blob/main/app/collectors/rss.py), [monolith entry limit](https://github.com/AuNooAI/AunooAI/blob/main/app/collectors/rss_collector.py#L285), [monolith checkpoint](https://github.com/AuNooAI/AunooAI/blob/main/app/tasks/rss_feed_monitor.py#L104).

## 3 Complete provider collection

**Problem.** NewsAPI callers retrieve one page. SaaS official-source adapters also perform single requests with bounded result counts. High-volume queries can repeatedly return a leading subset.

**Required behavior.**

Implement provider-specific page or cursor traversal behind CollectionResult. Freeze the interval end, choose a stable ordering where supported, and deduplicate overlapping pages. Respect documented provider caps, quota, and retention restrictions. Verify current provider contracts against official documentation during implementation; page numbers and cursor semantics must not be inferred from another provider.

Include SaaS arXiv author follows, category follows, initial fetch, catch-up, and full sweeps. The current author limit is 50 and category limit is 100; neither proves complete coverage. Do not advance author last_paper_at or category coverage solely from a limited newest-first batch or from last_polled_at. Keep query coverage state distinct from per-user follow status. arXiv versions must be retained as observations of a base work with explicit version identity; replay and metadata updates must not silently merge versions or multiply the user-visible work count.

Initial proposed budget: five pages or sixty seconds per provider interval, configurable by provider. Reaching the budget produces partial status and a persisted continuation. Provider hard limits must produce an explicit coverage limitation; split time windows where supported. When records share the same timestamp, use a stable secondary ID or overlap plus dedup rather than a strict timestamp-only cursor.

**Acceptance tests.**

- A fixture with 230 records across three pages produces 230 unique records.
- Overlapping page results do not duplicate records.
- A full last page with no proven end is not labeled complete.
- Rate limits preserve the continuation and fixed interval.
- Providers that cannot offer exhaustive search report that limitation.
- An arXiv category interval containing 150 papers collects all papers or retains a continuation; its next query does not skip the unprocessed 50.
- A failed arXiv query is not cached as an empty success and does not mark a never-polled follow complete.

**Repair.** Replay known outage and high-volume windows within provider retention and budget constraints. Start with a dry-run count estimate.

Sources: [SaaS NewsAPI](https://github.com/AuNooAI/aunooai-saas/blob/main/app/collectors/newsapi.py), [monolith keyword caller](https://github.com/AuNooAI/AunooAI/blob/main/app/tasks/keyword_monitor.py#L294), [SaaS official adapters](https://github.com/AuNooAI/aunooai-saas/tree/main/app/collectors).

arXiv sources: [query cache and error conversion](https://github.com/AuNooAI/aunooai-saas/blob/main/app/collectors/arxiv.py#L315), [poll markers and limits](https://github.com/AuNooAI/aunooai-saas/blob/main/app/tasks/arxiv_poll_task.py#L168).

## 4 Article identity and association merging

**Problem.** SaaS discards candidates matching stored hashes, URLs, or provider IDs. New topic and feed membership disappears. Its official poll loop filters existing records before brand attribution. Monolith dedup selects a single provider copy.

**Required behavior.**

Replace skip-only dedup with identity resolution that returns the persisted article ID for both new and existing records. Always upsert authorized topic, feed, and brand associations. Run official-source attribution against every matched eligible article, not only newly inserted ones. Exclusion and required-term checks still apply.

Use provider and external ID as observation identity. Scope RSS GUID identity to its originating feed: unrelated feeds can legitimately reuse a GUID. Use canonical URL as an article identity candidate, with conservative normalization of host casing, default ports, and known tracking parameters. Preserve the original URL and alias history. Do not remove arbitrary query parameters or force HTTP and HTTPS equivalence.

Choose identity by record type before consulting URL or content hashes. Calendar occurrences and social posts can legitimately share one landing URL. RSS replicas may match by URL, but calendar URL equality must never override distinct occurrence keys. Do not add a global unique URL constraint as part of this migration.

Social posts use platform and stable post ID. Scholarly records should match normalized DOI where available. URL or content similarity must not merge distinct social posts or distinct documents that happen to share text. For news without a stable identifier, retain a deterministic fallback hash with an explicit identity method.

Proposed additive relations: article_observations, article_url_aliases, and article_feed_memberships. Reuse existing topic arrays and brand tables where appropriate. Membership uniqueness includes the tenant or owner scope required by the current access model. Keep rss_feed_id as a compatibility field while readers migrate to the membership relation.

Separate inserted, updated, and associated counts. Existing unique constraints must be reconciled with the identity resolver; use conflict-safe inserts and resolve concurrent winners inside the same transaction.

**Acceptance tests.**

- One story collected for two topics belongs to both while keeping one article.
- The same story in two subscribed feeds appears in both readers.
- A shared official record is attributed to two eligible brands.
- Replaying an item makes no duplicate associations.
- Two feeds using GUID 123 for different articles retain both.
- A functional URL query parameter keeps two resources distinct.
- A worker with administrative access cannot attach another tenant's private feed observation to the wrong tenant.

**Repair.** Recover associations from feed snapshots, provider observations, URLs, and logs with reliable ownership evidence. Produce a candidate report before merging existing rows. Preserve saved-item, analysis, and embedding references when applying confirmed merges.

Sources: [SaaS dedup](https://github.com/AuNooAI/aunooai-saas/blob/main/app/collectors/pipeline.py#L179), [official filter and attribution](https://github.com/AuNooAI/aunooai-saas/blob/main/app/tasks/official_sources_poll_task.py#L116), [monolith dedup](https://github.com/AuNooAI/AunooAI/blob/main/app/tasks/keyword_monitor.py#L239).

## 5 Preserve social post identity

**Problem.** Monolith Instagram uses the account profile URL when the post URL is absent. Distinct posts then collapse during URL dedup. SaaS constructs an Instagram /p/ URL from an ID when code_url is missing; that fallback needs verification because an internal numeric ID is not necessarily a public shortcode.

**Required behavior.**

Persist social identity as platform plus external post ID even when no public permalink is available. Store account_url separately from post_url. Use a supplied valid permalink or a provider-documented shortcode conversion; never use a profile URL as post identity or invent a public URL from an unverified ID.

Support nullable post URLs in downstream social storage and rendering. Preserve source and ID provenance for later permalink enrichment. If the existing monolith article schema requires a URI, migrate it or introduce an internal identity field rather than passing a fabricated fetchable URL to scraping.

**Acceptance tests.**

- Two Instagram posts from one account with missing code_url remain two records.
- A numeric ID without a documented shortcode produces no fabricated permalink.
- A later permalink updates the existing post rather than inserting another.
- Missing URLs do not trigger a profile-page scraper or erase engagement metadata.

**Repair.** Identify records whose URI is an Instagram profile URL, then recover individual post IDs and permalinks from retained payloads or bounded provider re-fetches. Lost posts cannot be reconstructed from the surviving profile record alone.

Sources: [monolith mapper](https://github.com/AuNooAI/AunooAI/blob/main/app/collectors/xpoz_collector.py#L429), [SaaS URL fallback](https://github.com/AuNooAI/aunooai-saas/blob/main/app/collectors/xpoz.py).

## 6 Retain valid short and titleless content

**Problem.** SaaS ingest rejects all titles shorter than 25 characters and many uppercase titles, regardless of useful content.

**Required behavior.**

Separate ingestion validity from clustering quality. Ingest validity requires a stable identity and meaningful title or body. Short length and uppercase ratio become quality flags rather than unconditional rejection. Reject exact known navigation placeholders only when the surrounding item provides no meaningful content.

Support titleless JSON Feed and social content. Preserve original_title as absent and generate a deterministic display title from the first meaningful body sentence, capped at 120 characters, with title_provenance set to generated. Display titles must not participate in stable identity. Do not silently truncate the stored body.

Keep the existing stricter clustering policy until its own regression evaluation supports a change; it must not cause database deletion. Quarantine structurally invalid items with a reason and aggregate count.

**Acceptance tests.**

- OpenAI launches GPT-7 and IBM reports Q3 earnings ingest with valid identities.
- A legitimate uppercase bulletin with useful body text ingests.
- A titleless JSON Feed item with body and ID ingests with a generated display title.
- An empty navigation item is rejected.
- A changed display title does not create a new identity.

**Repair.** Replay recent affected feeds and provider intervals. Previously dropped content requires source recovery because it was never stored.

Sources: [title filter](https://github.com/AuNooAI/aunooai-saas/blob/main/app/newsfeed/service.py#L270), [ingest use](https://github.com/AuNooAI/aunooai-saas/blob/main/app/collectors/pipeline.py#L194), [JSON Feed parser](https://github.com/AuNooAI/aunooai-saas/blob/main/app/collectors/json_feed.py).

## 7 Publication dates and discovery dates

**Problem.** Monolith substitutes the current time for missing or invalid RSS and NewsData dates. Both Bluesky collectors use indexing time as publication time. SaaS can replace future official publication dates with the current time.

**Required behavior.**

Introduce a common date parser with source-specific formats and explicit timezone policy. Persist proposed published_at_raw, published_at, publication_date_precision, date_provenance, source_indexed_at, first_seen_at, and last_seen_at. Keep first_seen_at immutable during replay.

Missing or unparseable publication time remains null. Preserve date-only, month-only, and year-only precision. If storage needs a representative instant for a coarse date, document it as such and retain precision; consumers must not treat it as an exact timestamp. Unknown timezone input can be assigned UTC only where provider documentation establishes that convention, with provenance recorded.

For Bluesky, prefer record.createdAt or the equivalent SDK field for publication and indexedAt for indexing. If creation time is missing, publication remains unknown. Preserve future publication values with a future-date flag; discovery views use first_seen_at instead of rewriting them. Calendar event dates remain event dates and must not be coerced into publication dates.

Update date-dependent analytics and readers to choose publication or discovery explicitly. Exclude unknown or coarse dates from analyses requiring exact time and report the exclusion count.

The monolith analyzer is a second entry point for the same defects and is in scope. `extract_publication_date` in analyzers/article_analyzer.py (line 603) parses model output as YYYY-MM-DD, returns it formatted as an exact midnight timestamp, and returns the current time when the output is empty, invalid, or the extraction fails. Replace it with a typed result (date value, precision, provenance model_extracted, or unknown) and never substitute the current time. Its callers in research.py (lines 390, 467, 567, 650, 997, 1111) must prefer a supported provider date and call the model only when none exists. Two of those callers pass the extraction as the default argument of dict.get (lines 388 and 995); Python evaluates that argument before the lookup, so the model runs even when published_date is present. Make the fallback lazy. research.py also returns submission_date under the publication_date key for cached content (lines 366 and 602); return the stored publication date with its provenance, or unknown.

**Acceptance tests.**

- An offset timestamp normalizes to the same UTC instant.
- Invalid input yields null plus raw value and parse status.
- A Bluesky post created yesterday and indexed today retains both dates.
- A forthcoming paper keeps its future date and appears in discovery views.
- A replay does not move first_seen_at.
- Month-only dates retain month precision.
- Analyzer extraction of "2026-09-30" yields date precision day with provenance model_extracted, not an exact midnight instant.
- Empty or invalid analyzer output yields unknown, not the current time.
- A research fetch with a provider published_date makes zero extraction calls.
- Cached content returns its publication date, not its submission date.

**Repair.** Recover dates from retained source payloads first. Do not identify fabricated timestamps merely because publication and insertion times are close. Without source evidence, mark provenance unknown instead of inventing a replacement.

Sources: [monolith RSS](https://github.com/AuNooAI/AunooAI/blob/main/app/collectors/rss_collector.py), [NewsData dates](https://github.com/AuNooAI/AunooAI/blob/main/app/collectors/newsdata_collector.py#L296), [SaaS Bluesky](https://github.com/AuNooAI/aunooai-saas/blob/main/app/collectors/bluesky.py#L109), [monolith Bluesky](https://github.com/AuNooAI/AunooAI/blob/main/app/collectors/bluesky_collector.py#L209), [future clamp](https://github.com/AuNooAI/aunooai-saas/blob/main/app/collectors/official_base.py).

## 8 Merge content and provenance

**Problem.** Monolith prefers providers by a fixed ranking. NewsAPI content lives under raw_data while auto-ingest reads top-level content. Abstracts, snippets, and full articles can also be treated alike.

**Required behavior.**

Normalize all available content before identity resolution, including monolith NewsAPI raw_data.content. Store content_kind as full_text, abstract, excerpt, social_post, or unknown, together with provider, extraction method, observation time, and truncation status. Preserve all authors where supplied.

Merge fields independently. Prefer a valid complete body over an explicitly truncated excerpt, regardless of provider ranking. Prefer a valid publication date over missing data; do not overwrite conflicting dates without retaining provenance. Nonempty values must not be replaced by empty ones. Later corrections and deletions require explicit source-aware handling rather than blind longest-text selection.

For Crossref, a journal name used when the abstract is absent must be stored as venue metadata, not substantive body content. OpenAlex's truncated abstract must be labeled truncated. Engagement updates apply only to the same stable social post and record the observation time.

Keep quality_score as a content-completeness heuristic, separate from credibility. Derive completeness using content kind and visible text; HTML markup length must not inflate it. Recompute dependent embeddings or analysis only when material input fields change, using an input version.

**Acceptance tests.**

- NewsAPI first, full-text provider second: one article gains the fuller body.
- Full text first, empty duplicate second: content remains intact.
- Abstracts and excerpts never become labeled full_text.
- Crossref without an abstract has venue metadata and no invented body.
- Repeated identical observations do not trigger repeated embedding work.

**Repair.** Re-normalize retained observations and selectively re-enrich deficient records. Preserve licensing and existing source retention restrictions.

Sources: [monolith provider ranking and ingest](https://github.com/AuNooAI/AunooAI/blob/main/app/tasks/keyword_monitor.py), [NewsAPI mapping](https://github.com/AuNooAI/AunooAI/blob/main/app/collectors/newsapi_collector.py), [Crossref](https://github.com/AuNooAI/aunooai-saas/blob/main/app/collectors/crossref.py), [OpenAlex](https://github.com/AuNooAI/aunooai-saas/blob/main/app/collectors/openalex.py).

## 9 Preserve query meaning

**Problem.** Monolith NewsData removes grouping and quotes, retains at most two words, and can substitute a generic news query.

**Required behavior.**

Represent input as a query expression with phrases, conjunctions, alternatives, and exclusions. Each adapter declares supported operations and compiles the expression into its provider syntax. Preserve Unicode and full brand names. Reject unsupported expressions with unsupported_query, or use a declared bounded expansion that preserves meaning.

Persist the original expression, compiled provider query, and translation status in collection diagnostics. Never silently substitute news or AI. If an expansion exceeds the request budget, report incomplete coverage. Any local relevance gate must use the original expression and the available full candidate text, not only a truncated display title.

**Acceptance tests.**

- An exact phrase remains a phrase.
- Three alternative brands do not silently become the first two words.
- Exclusions and nested grouping either preserve meaning or fail explicitly.
- Japanese and German terms remain intact.
- Empty input makes no provider request.

**Repair.** Replay high-value affected queries after translation is corrected; track reclassification of newly recovered results separately.

Source: [NewsData query simplification](https://github.com/AuNooAI/AunooAI/blob/main/app/collectors/newsdata_collector.py#L46).

## 10 Balance Reddit collection routes

**Problem.** Monolith places unrestricted subreddit items before search results and truncates the combined list. Existing subreddit posts can continually consume the allowance. Both builds infer a subreddit name from the brand term and search by relevance within a limited result set.

**Required behavior.**

Give configured subreddit and keyword-search routes independent budgets and identity sets. Resolve existing records before applying a final new-record allowance. Preserve metadata updates for existing posts outside that allowance.

Use an explicit verified subreddit mapping per brand; an inferred slug is a discovery candidate, not proof of ownership or relevance. A subreddit-only post can be attributed using verified community context even if the brand name is absent, subject to required and excluded terms. Confirm the downstream SaaS attribution gate honors that context.

For monitoring, request newest-first search where supported and page until the collection interval is covered or a budget is reached. Relevance-ranked historical retrieval is a separate mode with its own coverage semantics. Record route-level errors; failure of one route must not masquerade as a completely successful combined collection.

**Acceptance tests.**

- Twenty already-stored subreddit posts cannot suppress five new search hits.
- One failed route produces partial status while the other route's records persist.
- An unverified eponymous subreddit does not automatically establish brand attribution.
- A verified community post without the brand term is evaluated using its community context.
- The same post arriving through both routes remains one record.

Sources: [monolith Reddit](https://github.com/AuNooAI/AunooAI/blob/main/app/collectors/reddit_collector.py#L104), [SaaS Reddit](https://github.com/AuNooAI/aunooai-saas/blob/main/app/collectors/reddit.py), [SaaS attribution gate](https://github.com/AuNooAI/aunooai-saas/blob/main/app/tasks/official_sources_poll_task.py#L130).

## 11 Recover late indexed scholarly records

**Problem.** SaaS Crossref and OpenAlex filter publication dates against the previous poll time. Records published earlier but indexed later can be missed.

**Required behavior.**

Use provider indexing or update timestamps for incremental retrieval where the current API and plan support them. Store that cursor separately from publication time. An updated known work must pass through observation merging.

Fallback proposal when no usable update cursor exists: daily retrieval over a rolling 30-day publication window, plus a bounded 365-day reconciliation weekly. Make both configurable and record the bounded coverage limitation. Paginate under work package 3. Do not promise exhaustive recovery beyond the provider's searchable or licensed history.

**Acceptance tests.**

- A work published two weeks ago and first indexed today is collected.
- A metadata correction updates an existing DOI.
- Failure during reconciliation retains progress.
- Fallback windows are reported as bounded coverage, not exhaustive indexing.

Sources: [Crossref filter](https://github.com/AuNooAI/aunooai-saas/blob/main/app/collectors/crossref.py#L52), [OpenAlex filter](https://github.com/AuNooAI/aunooai-saas/blob/main/app/collectors/openalex.py#L53).

## 12 Separate authenticity from credibility

**Problem.** SaaS official records receive fixed very high factual reporting, high credibility, and least biased labels.

**Required behavior.**

Add source_authenticity and record_type provenance. An authentic SEC filing, court opinion, scholarly metadata record, or regulatory submission can carry authentic origin without receiving a claim-level truth judgment or a least-biased label.

Remove unconditional credibility and bias stamps from OfficialCollector. Keep factual_reporting and credibility_rating unknown unless a documented assessment supplies them. Separate authority weighting for official origin from claim validation and expose the distinction in analytics and badges. Absence of an assessment must remain visible.

**Acceptance tests.**

- An authentic filing retains official origin but no automatic truth verdict.
- Public submissions and court allegations do not inherit top factual-reporting labels.
- Independently validated claims retain their own assessment.
- Analytics distinguish unknown credibility from low credibility.

**Repair.** Reclassify only labels demonstrably originating from the fixed official stamp, retaining the previous value and migration reason. Do not overwrite independent assessments.

Source: [OfficialCollector labels](https://github.com/AuNooAI/aunooai-saas/blob/main/app/collectors/official_base.py).

## 13 Compare website content accurately

**Problem.** Both website collectors treat paragraph line reflow as material change. Successful HTTP responses containing login or challenge pages can also become page-state input because HTTP status alone determines fetch success; this is a risk inferred from the current fetch path.

**Required behavior.**

Preserve raw extracted text and a versioned semantic representation. Normalize whitespace and line wrapping within paragraphs. Preserve table cells, list item boundaries, numbers, currency, and units. Compare structured blocks and ignore pure block movement while retaining multiplicity; adding a duplicate price row is not automatically a move.

Validate content before replacing a baseline. Obvious challenge, login, blank, and extraction-error responses produce extraction_failed or blocked outcomes. A suspicious abrupt drop in content should retain the prior baseline pending confirmation. The validator must permit genuine concise pages and legitimate removals.

Store conditional-response validators independently from the last material-change snapshot, so nonmaterial changes can update HTTP cache state without creating a false timeline event. Version the normalizer and reseed baselines when that version changes; a software normalization upgrade must not appear as a vendor announcement.

**Acceptance tests.**

- Starter $10 followed by Pro $60 across two lines versus one produces no material change.
- Reordering unchanged blocks produces no material change.
- A price changing from $60 to $70 is material.
- A real removed tier and a duplicate added row are detected.
- A challenge page returned with HTTP 200 leaves the prior baseline intact.
- A normalizer version upgrade reseeds without a business event.

**Repair.** Recompute historical diffs where both original snapshots remain available. Flag confirmed reflow-only events for exclusion with an audit reason; preserve original snapshots.

Sources: [SaaS diff](https://github.com/AuNooAI/aunooai-saas/blob/main/app/collectors/vendor_web.py#L296), [monolith diff](https://github.com/AuNooAI/AunooAI/blob/main/app/collectors/vendor_web_collector.py#L327), [SaaS page caller](https://github.com/AuNooAI/aunooai-saas/blob/main/app/tasks/market_sources_poll_task.py#L409).

## 14 Collection quality monitoring and repair

**Required behavior.**

Emit a durable run record by provider and collection scope with status, interval, checkpoint movement, continuation, counts, duration, error category, and coverage limitation. Low-cardinality metrics should summarize provider and route; tenant, feed, and query identifiers belong in authorized run diagnostics rather than unbounded metric labels.

Expose successful empty, partial, failed, blocked, and quota-limited collection separately. A process heartbeat is not evidence of data completeness. Report age since last successful collection, backlog age, null and invalid date rates, content-kind distribution, rejection reasons, association updates, and source truncation.

Initial proposed alerts: no successful run after two expected polling intervals, pending continuation older than two intervals, and a sustained rejection or invalid-date increase against that provider's baseline. Quiet sources must not alert solely because they publish no new records. Capture baseline measurements before selecting production thresholds.

All repair jobs must support dry-run, fixed scope, bounded budget, resumable progress, audit output, and idempotent replay. Counts must distinguish fetched observations, inserted articles, updated articles, new associations, and unrecoverable gaps. Repairs must not reset source history or first discovery dates.

**Acceptance tests.**

- Successful empty runs do not trigger a missing-content alert; overdue unsuccessful runs do.
- A partial run reports its continuation and backlog age separately from liveness.
- Run counters reconcile valid observations with inserts, updates, duplicates, filtering, and quarantine using documented units.
- A repair dry-run performs no corpus or checkpoint writes. Interrupted apply mode resumes idempotently and preserves first_seen_at.
- Diagnostic queries and alerts do not expose another tenant's private collection details.

## 15 Reliable WebSub delivery

**Problem.** The SaaS WebSub callback invokes RSSCollector.collect_for_feed, but the inspected class and its base define no such method. The exception handler returns a JSON failure object with the endpoint's normal HTTP 200 status. The signed delivery body is discarded and a second network fetch is attempted instead.

**Required behavior.**

Create a supported parse-and-ingest entry point for a feed response body. After signature validation, persist a bounded delivery payload or durable ingestion job before acknowledging success. Prefer ingestion of the signed body over another fetch that can fail, return newer content, or omit delivered entries. Keep delivery validators separate from polling validators.

A persistence failure returns an appropriate retryable non-2xx response. A 2xx response means the items are committed or a durable retry job is committed. Processing failures after queue acceptance remain visible and retry with bounded backoff; a JSON ok=false body with HTTP 200 is not a recovery contract. Retain delivery identity and retry state so repeated hub deliveries are idempotent. Persist payloads under existing source retention and access restrictions.

Define behavior for inactive feeds, muted feeds, expired subscriptions, and pending unsubscribe deliveries consistently with existing product semantics. Do not let the public callback become a general unrestricted collector endpoint.

**Acceptance tests.**

- A valid signed body reaches a real supported ingest method and stores its records.
- The original publisher being unavailable does not prevent ingestion of an already delivered signed body.
- Failure before durable persistence returns a retryable failure status.
- Failure after durable queue acceptance is retried without needing another hub delivery.
- Duplicate delivery creates no duplicate article, association, or pending job.
- Invalid signatures create no records or jobs.

**Repair.** Poll affected subscribed feeds with a bounded replay and reconcile hub delivery logs where retained. Report deliveries whose content no longer exists in the feed as unrecoverable without another source.

Sources: [WebSub delivery](https://github.com/AuNooAI/aunooai-saas/blob/main/app/routes/websub.py#L93), [RSSCollector methods](https://github.com/AuNooAI/aunooai-saas/blob/main/app/collectors/rss.py), [collector base](https://github.com/AuNooAI/aunooai-saas/blob/main/app/collectors/base.py).

## 16 Isolate fetch state and database failures

**Problem.** SaaS concurrent standalone fetching mutates attached RSSFeed cache validators before an item result exists. A timeout cancels tasks, but the final transaction can still persist validators for an unfinished feed. SaaS auto-categorization can also roll back the outer transaction from a caught helper failure. Monolith RSS returns the same false value for an existing article and a failed insert, then advances the feed watermark using all fetched articles.

**Required behavior.**

Fetch and parse against immutable feed input. Return proposed validator and tracking changes in a result object; apply them only after successful ingestion or durable staging. A cancelled task must leave ORM objects unchanged. Do not share a mutable database session with parallel fetch tasks.

Give storage an explicit outcome: inserted, updated, existing, quarantined, or failed. Duplicate detection is a completed observation; a transient storage failure is incomplete work. Failed records must either prevent checkpoint advance or be durably queued with enough payload and retry state for recovery.

Each batch coordinator owns commit and rollback. Helpers use flush or an explicit savepoint for recoverable local conflicts; optional categorization cannot roll back required ingest. Network and model calls should happen outside long write transactions where practical. Re-establish transaction-local role and tenant context for every new transaction. Audit arXiv's _ingest, whose current store_articles call commits before follow markers and tags are written, and remove that intermediate commit or define a durable retry stage for the remaining writes.

Do not catch a database exception and continue using an aborted PostgreSQL transaction. Roll back the savepoint or batch, restore required scope, and replay deterministically.

**Acceptance tests.**

- Cancellation after response headers but before normalized items does not commit a new ETag.
- A later 304 cannot hide an uncommitted response.
- One monolith insert fails after other items succeed: the failed payload remains retryable and the coverage checkpoint does not claim completion.
- Duplicate and failed insert outcomes are distinct in counters.
- A duplicate category creation conflict does not remove earlier article or tracking writes.
- arXiv article storage, follow markers, and tags commit together or have durable independent retry states.
- A forced database constraint failure leaves the next batch able to run with the correct role and tenant scope.

**Repair.** Reset suspect cache validators only for feeds with supporting evidence of failed or cancelled ingestion, then replay their current content. Reconcile article persistence and arXiv follow or tag state separately; do not assume a committed article proves its user associations were committed.

Sources: [standalone fetch coordinator](https://github.com/AuNooAI/aunooai-saas/blob/main/app/tasks/collector_task.py#L181), [early validator mutation](https://github.com/AuNooAI/aunooai-saas/blob/main/app/collectors/rss.py#L268), [helper rollback](https://github.com/AuNooAI/aunooai-saas/blob/main/app/collectors/rss.py#L766), [monolith storage outcome](https://github.com/AuNooAI/AunooAI/blob/main/app/tasks/rss_feed_monitor.py#L208), [arXiv intermediate commit](https://github.com/AuNooAI/aunooai-saas/blob/main/app/tasks/arxiv_poll_task.py#L259).

## 17 Preserve calendar occurrences and changes

**Problem.** Calendar occurrences have distinct external IDs but share URL-based content hashes when they use the same event landing page. Recurrence expansion substitutes the occurrence start without shifting the original event end, so future occurrences can appear already ended. Expansion also reads RRULE alone and does not apply exception dates or detached recurrence overrides.

**Required behavior.**

Represent calendar data with record_type=calendar_event and separate event_start, event_end, all_day, timezone, recurrence identity, source modification time, sequence, and cancellation status. DTSTART must not be written as publication time.

Use calendar source identity plus UID and original RECURRENCE-ID as the occurrence key. A rescheduled occurrence retains its original recurrence key while event_start changes. URL and content hash are attributes, not occurrence identity. Validate UID handling for missing or malformed entries without dropping valid sibling events.

Expand RRULE and RDATE, apply EXDATE and detached RECURRENCE-ID overrides, and preserve cancellations and sequence ordering. Compute each occurrence end using event duration or the effective override, accounting for all-day exclusive DTEND and timezone transitions. Floating dates require an explicit feed timezone policy; do not silently pin local event times to UTC. Keep expansion bounded and state the visible horizon.

Parse the already fetched response body. Avoid the current second iCal fetch after RSS has captured validators, which can associate one response's ETag with another response's data. Use a tested recurrence library and verify its current supported semantics during implementation.

**Acceptance tests.**

- Three weekly occurrences sharing one URL remain three records.
- A one-hour recurring event has a one-hour duration on every occurrence.
- Two future occurrences survive a cutoff after the first occurrence ends.
- EXDATE removes one occurrence; a detached reschedule updates its original occurrence identity.
- Cancellation removes the occurrence from upcoming views while retaining an auditable observation.
- DST and all-day cases retain correct local time and end semantics.
- A second network fetch is not needed to parse a calendar response.
- A bad event is quarantined without losing valid siblings.

**Repair.** Re-expand retained calendars within the configured horizon. Update or create occurrences by the new identity and preserve saved references through an explicit migration mapping. Do not regenerate past events outside the stated repair scope.

Source: [iCal parser and recurrence expansion](https://github.com/AuNooAI/aunooai-saas/blob/main/app/collectors/ical.py), [RSS iCal handoff](https://github.com/AuNooAI/aunooai-saas/blob/main/app/collectors/rss.py#L276), [URL-based hash](https://github.com/AuNooAI/aunooai-saas/blob/main/app/collectors/base.py#L63).

## 18 Conservative reader grouping

**Problem.** SaaS RSS groups articles using only the first eight normalized title words, with no time bound or body confirmation. Distinct editions can join a permanent group. The reader globally suppresses noncanonical members even when the group's canonical article is outside the selected feed or date scope. Existing groups also retain their original canonical when richer members arrive.

**Required behavior.**

Treat title buckets as candidate retrieval keys rather than proof of equivalence. Require additional evidence such as normalized full-title equality with compatible publication timing, a known canonical URL relationship, or strong body agreement. Grouping must preserve distinct document and event identities. Proposed initial time window for ordinary news replicas is 72 hours, configurable by source; uncertain dates require stronger identity evidence rather than unlimited grouping.

Persist the grouping method, version, and evidence. Prefer an uncollapsed false negative to hiding an unconfirmed distinct story. Keep grouping separate from database identity merging so a bad group can be split without changing article IDs.

Select the visible representative from authorized members satisfying the current feed, date, search, tag, and unread filters. If the global canonical is outside that scope, show an eligible member instead of suppressing the whole story. Reconsider representative quality when a richer verified replica arrives. Member counts displayed to a user must use the same authorized scope.

**Acceptance tests.**

- Headlines sharing eight opening words but differing in month or subject remain separately visible.
- Different daily editions do not join a permanent group.
- Selecting feed B shows its eligible member even if feed A owns the global canonical.
- A filtered-out canonical does not hide matching members in search or unread views.
- A richer replica can become the representative while original article IDs remain stable.
- Splitting a mistaken group preserves saved state and associations.

**Repair.** Evaluate existing groups in shadow mode, starting with groups spanning long date ranges or divergent full titles. Split confirmed false groups and recompute representatives without deleting articles or read state.

Sources: [title buckets and group linking](https://github.com/AuNooAI/aunooai-saas/blob/main/app/collectors/pipeline.py#L470), [reader suppression](https://github.com/AuNooAI/aunooai-saas/blob/main/app/routes/rss.py#L1422).

## 19 Remember rejected candidates

**Problem.** The monolith early relevance gate in automated_ingest_service scores every candidate URL on every keyword poll and keeps no record of the result. In seven days across eight tenants it ran 112,332 times on 21,033 distinct URLs; 8,001 URLs were scored five or more times and the worst two 134 times each. wileytest alone accounts for 75,418 evaluations. Each evaluation embeds the candidate, so the waste is compute and log volume, and the inflated numbers hide real throughput.

**Entry points.** Monolith: services/automated_ingest_service.py (the "filtered early" branch), tasks/keyword_monitor.py.

**Required behavior.**

Keep a rejected-candidate ledger keyed by canonical URL, keyword group, and gate version, storing the score, threshold, and time of the last evaluation. Before scoring a candidate, look it up; a hit under the current gate version and unchanged group terms returns the stored outcome without embedding. A change to the group's terms, the threshold, or the gate implementation bumps the version and invalidates the entry. The ledger is per tenant and bounded by a retention window, proposed at 30 days, matching the longest provider look-back.

Count ledger hits separately from new rejections in the run record (work package 14). A ledger hit is neither a duplicate nor a filtered observation; it is "already rejected". The ledger must not block an article that a different route accepts: an RSS feed or manual submission that passes its own gate stores the article regardless of a keyword-route rejection.

**Acceptance tests.**

- A URL rejected by group G is not embedded again on the next poll of G.
- The same URL is scored again when G's terms change or the gate version bumps.
- A URL rejected by group G is still scored for group H.
- A URL rejected by the keyword route is still stored when it arrives through an RSS feed that accepts it.
- After the ledger is enabled, the per-poll count of early-filter evaluations on wileytest drops to roughly the count of new distinct candidates.

**Repair.** None needed. Seed the ledger from the last seven days of logs only if the gate version is unchanged; otherwise start empty.

## 20 Shared provider quota ledger and circuit breaker

**Problem.** Several tenants share one provider key but each tenant counts requests on its own. wbm and wileytest share a NewsAPI developer key limited to 100 requests per day; the guard at newsapi_collector.py line 78 compares a per-tenant counter against 100, so it never fires and the provider rejected 615 requests in seven days. NewsData shows the same pattern across wbm, wileytest, sunstar, and oviva on one key (710 "exceeded your assigned API credits" errors). Xpoz shows it across seven tenants (over 2,100 "Usage limit exceeded" warnings interleaved with successes, so the budget runs out part way through each period and the remaining polls fail until reset). The SaaS Semantic Scholar enrichment has no key at all and received 10,451 HTTP 429 responses in five days, about 200 per hour around the clock; its tick sleeps three seconds per 429 and moves to the next of 120 rows, so a rate-limited tick burns the whole budget to refresh 13 to 23 rows.

**Entry points.** Monolith: collectors/newsapi_collector.py, collectors/newsdata_collector.py, collectors/xpoz_collector.py, collectors/semantic_scholar_collector.py, services/social_profile_service.py, services/social_engagement_refresh.py. SaaS: services/semantic_scholar.py, tasks/paper_enrichment_task.py, collectors/xpoz.py, social/reach.py.

Source confirms the mechanism: the monolith NewsAPI collector keeps its daily count in the tenant database through the facade, NewsData keeps an instance counter, and the SaaS Semantic Scholar tick selects rows newest-first with no persisted per-row retry eligibility, so the same rows are retried on every throttled tick. Key sharing and the error totals are operational evidence from the host .env files and logs.

**Required behavior.**

Keep one quota ledger per provider key fingerprint on the host, shared by every tenant process that uses that key. Store the documented period, the budget, the count used, and quota_exhausted_until. The ledger lives in a shared store the tenants can reach, for example a table in a shared database or a file under a lock; a per-process counter is not acceptable. Each request reserves a unit before it is sent and records the provider's response. A 429, an "exceeded credits" body, or a "usage limit" body sets quota_exhausted_until from the provider's Retry-After or documented reset time, and every tenant stops polling that key until then.

A quota-exhausted collector returns a CollectionResult (work package 1) with status failed, error_code quota_exhausted, retryable true, and truncated_reason quota. It does not advance coverage. Where a provider offers a quota endpoint, reconcile the ledger against it daily.

For Semantic Scholar, obtain an API key, send it from every caller, and break the per-tick loop on the first 429: the remaining rows wait for the next tick. Honour Retry-After. Persist per-row next_attempt_at so a throttled row is not selected again before its cooldown and other due rows get their turn. Report rows refreshed, rows skipped for quota, rows deferred by cooldown, and rows skipped for missing record separately.

Allocate budget across tenants explicitly. Proposed default: equal shares with borrowing of unused share within the period. The allocation is configuration, not code, and the run record shows each tenant's share and use.

**Acceptance tests.**

- Two tenants on one 100-per-day key together send at most 100 requests in the period.
- The first 429 on a key stops every tenant's polling of that key until the reset time, and the run record for each skipped poll says quota_exhausted.
- A quota-exhausted interval keeps its continuation and is replayed after reset.
- A Semantic Scholar tick that receives a 429 on row 3 stops at row 3 and reports 117 rows deferred.
- The ledger survives a process restart.

**Repair.** Replay the intervals that failed with quota errors within provider retention, starting with wbm and wileytest NewsAPI windows.

## 21 Back off failing sources and budget shared hosts

**Problem.** The monolith feed monitor stores last_error but keeps no error count and applies no backoff, so a dead feed is retried at full cadence forever. The Noom feed returned 403 on all 188 polls in seven days and the Blink feed on 19. Reddit RSS returned 429 on 920 polls across tenants, because every tenant fetches reddit.com/search.rss and subreddit .rss from the same host IP with no shared rate budget. The SaaS standalone path already keeps error_count and a non-productive-poll multiplier; the monolith does not.

**Entry points.** Monolith: tasks/rss_feed_monitor.py (the error branch near line 200), collectors/reddit_collector.py, collectors/rss_collector.py. SaaS reference implementation: collectors/rss.py bump_empty_polls and tasks/collector_task.py lines 189 to 215.

Source confirms the monolith monitor schedules from last_checked_at and the configured interval only; it persists no consecutive-error count and no next-retry time, so backoff state has to be added, not tuned.

**Required behavior.**

Port the SaaS backoff to the monolith feed monitor: consecutive_error_count, polling_status, and a cadence multiplier that grows with consecutive failures and saturates, proposed at eight times the base interval. A 403, 404, 410, or DNS failure repeated for a configurable number of polls, proposed at 20, moves the feed to polling_status needs_attention and surfaces it in the collector health probe with the first and last failure times. The feed is not deleted and not silently disabled; a user or operator action clears the state. A success resets the count.

Keep a per-host request budget shared across tenants for hosts that rate-limit by client IP, starting with reddit.com. The budget lives in the same shared store as the quota ledger (work package 20). A 429 from the host sets a host-level pause from Retry-After, and every tenant's fetch of that host returns quota_exhausted until it passes.

Backoff is scheduling state, not coverage state. A feed in backoff keeps its checkpoint and continuation; when it is polled again, it resumes from the same interval.

**Acceptance tests.**

- A feed returning 403 twenty times in a row is polled at the maximum multiplier and appears in the health probe as needs_attention with its first failure time.
- A feed that recovers after five failures returns to base cadence on the next success and its checkpoint is unchanged.
- Two tenants fetching reddit.com together stay under the host budget, and one 429 pauses both.
- The health probe lists feeds that have failed for more than 24 hours by tenant and reason.

**Repair.** Review the feeds currently failing for more than seven days (Noom, Blink, and any the probe finds) and either fix their URLs or mark them needs_attention.

## 22 Quarantine and retry enrichment config gaps

**Problem.** The monolith analyzer validates the topic configuration before any model call and raises when a list is empty. On wileytest the topic "What are the technology trends in the interalogistics markets" has no future-signals list, so every article routed to it fails with "Future signals list cannot be empty": 592 failures and 249 articles marked enrichment_failed in seven days, plus 547 "analyzed flag is False" validation errors. bugfixing shows the same with "Categories list cannot be empty" (55). Nothing re-queues enrichment_failed rows; no retry sweep exists. This is one stage after collection, but the loss mechanism is the same as work package 6: a valid article is discarded because a rule, not the article, is broken.

**Entry points.** Monolith: analyzers/article_analyzer.py lines 150 to 162, services/automated_ingest_service.py (the enrichment_failed branches near lines 967 and 1202), services/async_db.py.

**Required behavior.**

Distinguish article faults from configuration faults. An empty categories, future-signals, or sentiment list is a configuration fault: the article is stored with ingest_status quarantined_config and an enrichment_block_reason naming the topic and the missing list, no model call is made, and the run record counts it under configuration_blocked. The topic is flagged in the UI and the health probe until the list is filled.

Add a retry sweep for enrichment_failed and quarantined_config rows. It runs on a timer, re-reads the topic configuration, and re-enriches rows whose block reason no longer applies, newest first, under a per-tick budget. It records the attempt count per article and stops after a configurable maximum, proposed at three, for article faults; configuration faults have no maximum because they retry only when the configuration changes.

The topic wizard and the topic configuration save path must refuse to save a topic with an empty list that enrichment requires, or must mark the topic enrichment-disabled explicitly with the consequence shown.

**Acceptance tests.**

- An article routed to a topic with an empty future-signals list is stored as quarantined_config with the topic named, and no model call is logged.
- Filling the list causes the sweep to enrich the quarantined articles without a manual command.
- An article that fails enrichment three times for an article fault stays enrichment_failed with its last error and is not retried again.
- Saving a topic with an empty categories list is refused or marks the topic enrichment-disabled.
- The health probe reports the count of configuration-blocked articles per topic.

**Repair.** Fill the wileytest topic's future-signals list, then run the sweep over the 249 enrichment_failed rows from the last seven days. Report how many were enriched and how many remain failed for article faults.

## 23 Xpoz MCP client cancellation safety

**Problem.** The SaaS Xpoz calls go through an MCP client over streamable HTTP. In seven days the worker logged 317 "Attempted to exit cancel scope in a different task than it was entered in" tracebacks, 284 HTTP 429 responses from mcp.xpoz.ai, 100 search_shares calls abandoned after their timeout, and story-reach sweeps failing with "xpoz call aborted by MCP client teardown". A timeout cancels the call from a different task than the one that opened the client's cancel scope, which raises inside the client teardown and leaves the sweep's partial state behind.

**Entry points.** SaaS: collectors/xpoz.py, social/reach.py, and the MCP client wrapper they share.

collectors/xpoz.py already has an `_isolate_cancellation` decorator (line 42) on two call sites and deliberately leaves a third unwrapped. The 317 tracebacks occurred with that guard in place, so this package is an audit of MCP session lifecycle and task ownership with regression tests, not another wrapper.

**Required behavior.**

Run each Xpoz MCP session in the task that owns it, and apply timeouts inside that task rather than cancelling it from outside. If a call must be abandoned, close the session from its own task and return a failed CollectionResult with error_code transport_timeout. Teardown errors must not propagate into the caller's transaction. A 429 from the MCP endpoint goes through the quota ledger (work package 20).

Story-reach and share sweeps record per-platform outcomes; a wedged transport on one platform does not mark the sweep complete for that platform. Apply work package 16's rule: cancellation leaves persisted state unchanged.

**Acceptance tests.**

- A search_shares call that exceeds its timeout returns transport_timeout without a cancel-scope traceback.
- A 429 from the MCP endpoint pauses Xpoz calls until Retry-After and is counted as quota_exhausted.
- A sweep where reddit wedges and x succeeds records x complete and reddit incomplete.
- The worker log contains no "exit cancel scope" errors over a 24-hour soak with injected timeouts.

## 24 Treat arXiv 406 as transient

**Problem.** arXiv returns HTTP 406 to both repositories in bursts: 68 monolith and 90 SaaS failures in seven days. On SaaS the five category queries fail together in the same minute and succeed on a later cycle; the identical URL returned 200 from curl at review time. Only 7 of roughly 300 SaaS page requests produced a first page. Neither repository classifies 406 as retryable, so each burst is treated as a query failure and the day window is lost until a later cycle happens to succeed.

**Entry points.** SaaS: collectors/arxiv.py, tasks/arxiv_poll_task.py. Monolith: collectors/arxiv_collector.py, tasks/keyword_monitor.py.

**Required behavior.**

Classify 406, 429, 503, and connection errors from the arXiv API as retryable transient failures. Space consecutive category and author queries by at least the documented arXiv interval, proposed three seconds, with jitter, and do not launch all categories in the same second. Retry with exponential backoff within the run budget; on exhaustion, return status failed with the continuation for the fixed day window (work package 3) so the next cycle replays the same window rather than a new one. Record the status code in error_code so a persistent 406 for a specific query is visible as a query fault after a configurable number of cycles.

**Acceptance tests.**

- A 406 on the first attempt followed by 200 on retry yields a complete interval.
- Five category queries are not sent in the same second.
- A 406 on every attempt leaves the day window's continuation in place; the next cycle replays it.
- A query that returns 406 for ten consecutive cycles is reported as a probable query fault.

**Repair.** Replay the arXiv day windows that failed in the last 30 days on both repositories, under the pagination budget.

## 25 Bluesky collection window

**Problem.** The monolith Bluesky collector accepts a start_date argument but never sends it to the API; no since or until parameter exists in the collector. On bugfixing, 668 of the 4,468 articles collected in the last seven days are Bluesky posts dated before 1 September 2026, some from August 2023. Work package 7 fixes which date the collector stores; it does not fix which posts it requests.

**Entry points.** Monolith: collectors/bluesky_collector.py (search at line 114 and the post mapping at lines 209 and 335). Check the SaaS collector for the same omission.

**Required behavior.**

Send the collection interval to the Bluesky search endpoint using its since and until parameters, with the interval fixed at run start (work package 1). Sort by latest for monitoring. Page with the API cursor until the interval is covered or the budget is reached, and keep the continuation. Records outside the interval that the API still returns are dropped at the adapter with a filtered count, not stored.

Apply the same rule to reply and thread fetches: a thread fetched for context is an observation of the parent post, not a new collection of its replies' dates.

**Acceptance tests.**

- A search for the last 24 hours sends since and until and returns no post created before the interval.
- A post the API returns outside the interval is counted as filtered and not stored.
- A rate limit on page two keeps the continuation for the same interval.
- After deployment, the weekly count of Bluesky posts stored with a publication date older than 30 days on bugfixing is near zero.

**Repair.** Review the 668 old-dated Bluesky rows on bugfixing. They are genuine posts, so keep them, but mark their discovery date (work package 7) so discovery views do not show them as new.

## 26 NewsData date filter as a declared limitation

**Problem.** The monolith NewsData collector logs "Date filtering requested but skipped (free tier limitation)" and sends an undated query: 1,514 times in seven days. Every request returns whatever the provider ranks first regardless of the collection interval, and credits are spent on results outside it. The interval is silently dropped, which work packages 3 and 9 forbid in general but do not name here.

**Entry points.** Monolith: collectors/newsdata_collector.py line 181 and the request construction above it.

**Required behavior.**

Decide the plan. If the plan does not support date filtering, the adapter declares it: the CollectionResult carries truncated_reason provider_no_date_filter and coverage_complete false, the translation status (work package 9) records that the date clause was dropped, and the adapter filters returned records to the interval locally with a filtered count. If the plan does support it, send the from_date and to_date parameters. Either way, the behaviour is declared in the run record, not in an INFO log line.

**Acceptance tests.**

- With date filtering unsupported, the run record says provider_no_date_filter and records outside the interval are counted as filtered, not stored.
- With date filtering supported, the request includes the interval and the run record says coverage bounded by provider retention.
- No NewsData run reports coverage_complete true while the date clause was dropped.

## 27 Per-URL full-text fallback

**Problem.** The monolith sends batches of URLs to Firecrawl. When Firecrawl rejects the batch with "No valid URLs provided", the inner helper `_firecrawl_batch_scrape` catches the error and returns an empty mapping (line 2006). The caller `scrape_articles_batch` only falls back to `_fallback_individual_scraping` when an exception reaches it (line 1892), so the swallowed rejection bypasses the per-URL fallback that already exists. 59 batches were rejected in seven days; every URL in each lost its full text with no retry. The batch count does not translate into an article-loss total because batch sizes vary and some URLs are later re-fetched through other routes.

**Entry points.** Monolith: services/automated_ingest_service.py lines 1862 to 1893 and 1894 to 2010.

**Required behavior.**

The batch helper returns per-URL outcomes, never a bare empty mapping for a rejected batch. On a batch rejection, retry the URLs individually or in halves until the rejecting URL is isolated. Record the isolated URL with content_kind unknown and extraction_status rejected_by_provider (work package 8), and fetch the others. Resolve known redirect wrappers, such as Google News RSS links, before sending to the provider, since those are the documented cause of the rejection. Per-URL extraction outcomes go into the run record so a provider that rejects many URLs is visible.

**Acceptance tests.**

- A batch of ten URLs with one Google News redirect yields nine full texts and one rejected_by_provider record.
- A Google News redirect is resolved to its target before the provider call.
- Extraction outcomes reconcile with the batch size in the run record.

**Repair.** Re-run full-text extraction for articles stored in the last 30 days whose body is empty and whose source batch was rejected.

## 28 Complete error diagnostics

**Problem.** 210 of the 293 topic-less feed failures in the SaaS worker log read "failed:" followed by nothing, because httpx timeout exceptions stringify to an empty string. The feed's last_error and the run record carry no reason. Work package 14 asks for error categories; this names the gap.

**Entry points.** SaaS: tasks/collector_task.py line 191, collectors/rss.py error path. Check the monolith feed monitor's last_error for the same.

**Required behavior.**

Every failure message and error_code includes the exception class name and, for HTTP errors, the status code and host. Map exception classes to the stable error_code set from work package 1: timeout, connection, dns, http_4xx, http_5xx, parse, quota. An empty message is a test failure.

**Acceptance tests.**

- A read timeout records error_code timeout and a message naming ReadTimeout and the host.
- No run record or last_error in a 24-hour sample has an empty reason.

## 29 Feed XML hygiene and partial-parse state

**Problem.** The monolith logged 139 "not well-formed (invalid token)" and 47 "XML or text declaration not at start of entity" parse warnings in seven days. The second is leading whitespace or a byte-order mark before the XML declaration, which feedparser then treats as malformed. In both cases feedparser recovers some entries and the collector accepts them without recording that the parse was partial, so entries lost to the parse error are never replayed. Work package 2 makes a parse that yields nothing an error; it does not cover a parse that yields some entries.

**Entry points.** Monolith: collectors/rss_collector.py lines 276 to 290. SaaS: collectors/rss.py parse path.

**Required behavior.**

Strip a byte-order mark and leading whitespace before parsing, and retry a declaration-position failure once after stripping. When the parser reports a recoverable error and still yields entries, record parse_partial true with the error and the entry count on the run record and the feed, and do not commit cache validators (work package 2) so the next poll re-fetches the full response. A feed that is parse_partial for a configurable number of consecutive polls is surfaced like a failing feed (work package 21).

**Acceptance tests.**

- A feed with a byte-order mark before the declaration parses cleanly with no warning.
- A feed with one invalid token yields its valid entries, records parse_partial, and does not commit an ETag.
- A feed that stays parse_partial for ten polls appears in the health probe.

## 30 Publisher-specific tracking parameter registry

**Problem.** wileytest holds 118 groups of URL variants (696 surplus rows) collected in the last 30 days. The real cases are seekingalpha links with and without feed_item_type=news and BBC links with and without at_medium=RSS&at_campaign=rss, neither of which is a utm parameter. A naive strip of all query parameters would also merge two streamingmedia articles that differ only in ArticleID, which are different articles. Work package 4's "known tracking parameters" must therefore be a per-publisher list, not a fixed global one.

**Entry points.** Both: the URL normalizer introduced by work package 4.

**Required behavior.**

Keep a tracking-parameter registry with a global list (utm_*, fbclid, gclid, and similar) and per-host additions (seekingalpha.com feed_item_type; bbc.co.uk at_medium, at_campaign). The registry is data, versioned, and applied by the normalizer with the version recorded in article_url_aliases. Parameters not in the registry are kept. A repair script proposes registry additions from URL-variant groups whose members share title and publication time, for review before they are added.

**Acceptance tests.**

- The two seekingalpha variants resolve to one article with both URLs in the alias table.
- The two streamingmedia ArticleID URLs remain two articles.
- A registry change bumps the normalizer version and is visible on the alias rows written after it.
- The proposal script lists the wileytest groups with their shared title evidence and writes nothing without review.

**Repair.** Run the proposal script on wileytest and bugfixing, review, then merge confirmed groups under work package 4's merge procedure, preserving saved items and analysis.

## 31 Briefing selection identity

**Problem.** The monolith logs "Selected article disagrees with itself" when the model's chosen id, uri, and title resolve to three different articles; 12 cases in seven days, resolved by a title heuristic at news_feed_service.py line 2055. All 12 come from the six-articles newsletter report pipelines (`_generate_six_articles_report` at line 469 and `_generate_six_articles_with_political_analysis` at line 813), which call `_resolve_selected_articles`. The daily briefing compose service already presents candidates by id and hydrates picks through its own id map, and the executive briefing service accepts model-produced indices with copied metadata; neither logged a mismatch, but the executive path has the same exposure. This is downstream of collection, but it is the same identity problem: a positional id the model can mismatch.

**Entry points.** Monolith: services/news_feed_service.py lines 469 to 700, 813 to 1000, and 1994 to 2070; services/executive_briefing_service.py selection parsing. Reference: services/daily_briefing_compose_service.py id map at line 1166.

**Required behavior.**

Present candidates to the model with one stable identifier, the article id, and require the model to return only that identifier. Validate the returned id against the candidate set; a mismatch between id and any echoed uri or title is a rejected selection that is retried once, then logged as selection_mismatch and skipped. Do not resolve conflicts by guessing from the title. Count mismatches in the briefing run record.

**Acceptance tests.**

- A response whose id and uri point to different candidates is rejected and retried.
- A second mismatch skips the slot and records selection_mismatch.
- No selection is made from a title match alone.

## Verification and rollout

Use fixture-based adapter tests and database integration tests. Isolated review probes established short-title rejection, Instagram profile-URL collision, reflow false positives, calendar end-time and hash collisions, and title-prefix group collisions. Static class inspection confirmed the missing WebSub method. A small cancellation model demonstrated the validator mutation hazard; that model is not a full collector or database test. Turn these triggers into regressions against the implemented paths.

Before coding, inventory every call site, current database constraint, scheduler lock, WebSub route, and reader query touched by a work package. Confirm provider pagination and date contracts from current official documentation. Recheck the monolith's existing restamped-date recovery path to preserve its behavior.

Roll out in this order:

1. Add nullable fields, association relations, indexes, and compatibility readers. Capture baseline metrics.
2. Implement structured outcomes, identity resolution, and merge behavior with fixture and integration tests.
3. Compare old and new decisions in shadow mode using the same captured responses. Avoid doubling paid API requests.
4. Enable a small provider and feed cohort. Observe at least two scheduled cycles, plus injected outage and retry fixtures.
5. Expand the cohort, then run bounded historical repairs after live collection is stable.
6. Remove compatibility paths only after callers and readers have migrated.

Release gates are zero checkpoint movement on failed or incomplete intervals, complete fixture recovery after retries, preservation of topic and feed associations, valid short-content retention, and stable post identity. Investigate increased counts as possible recovered coverage rather than automatically interpreting them as duplicates.

Also require a valid signed WebSub delivery to reach durable ingestion, cancellation to leave feed validators unchanged, per-record failures to remain retryable, calendar occurrences to retain distinct identities and correct duration, and reader grouping to retain at least one eligible representative in every requested scope. Run these checks before backfills; recovery through a still-broken route can recreate the defects.

For packages 19 to 31, the release gates are measured against the baseline in "Evidence from logs": early-filter evaluations per distinct candidate near one, zero provider quota errors on shared keys within a period, no feed failing for more than 24 hours without a needs_attention state, zero configuration-blocked articles without a named topic, and zero cancel-scope tracebacks in a 24-hour soak.

On rollback, keep additive schema and persisted checkpoints, pending batches, observations, and associations. If an older collector cannot respect the new checkpoint semantics, pause that collector or deploy the compatible reader first; do not roll it back into advancing attempt timestamps as coverage. Stop repair jobs independently without deleting their progress.

## Implementation completion criteria

Each work package is complete when its acceptance cases pass, all relevant background and manual routes use the intended contract, migrations are reversible or documented as additive, run diagnostics expose failures and incomplete coverage, and its repair command produces a reviewed dry-run report.

No production recovery rate or timeline is asserted here. Historical recovery depends on retained payloads, feed archives, provider retention, licensing, and quota. Work package pull requests should record the verified commit, actual schema decisions, tests run, and any provider limitation that leaves bounded rather than exhaustive coverage.

## Evidence from logs

Source: journald output from 25 September to 1 October 2026 for the eight running monolith tenants (abm, bugfixing, oviva, panaya, sunstar, wbm, wiley, wileytest) and the SaaS worker and web services, plus the articles table on bugfixing and wileytest. Counts are for that window.

Limits. Log events count attempts, not unique lost articles: 59 rejected scrape batches and 139 malformed-feed parses cannot be converted into an article-loss total. Seven arXiv first pages out of roughly 300 page requests is not a success rate, because the library's retries inflate the denominator. The curl 200 on the same arXiv URL shows the query is well formed; it does not establish why the earlier responses were 406. Zero null publication dates confirms the substitution path is live but does not quantify it, and neither the midnight nor the near-submission pattern proves which rows were fabricated; repairs must use raw source values and provenance (work package 7).

| Signal | Count | Work package |
| --- | --- | --- |
| Early relevance-gate evaluations / distinct URLs (monolith) | 112,332 / 21,033 | 19 |
| URLs evaluated five or more times | 8,001 | 19 |
| NewsAPI rate-limit errors (wbm + wileytest, one shared key) | 615 | 20 |
| NewsData credits-exceeded errors (four tenants, one key) | 710 | 20 |
| Xpoz usage-limit warnings (seven tenants) | 2,100+ | 20 |
| Semantic Scholar 429 (SaaS, five days, no key) | 10,451 | 20 |
| Noom feed 403 / Blink feed 403 | 188 / 19 | 21 |
| Reddit RSS 429 | 920 | 21 |
| "Future signals list cannot be empty" (wileytest) | 592 | 22 |
| enrichment_failed rows written (wileytest) | 249 | 22 |
| "Categories list cannot be empty" (bugfixing) | 55 | 22 |
| Cancel-scope tracebacks (SaaS) | 317 | 23 |
| mcp.xpoz.ai 429 / search_shares abandoned | 284 / 100 | 23 |
| arXiv 406 (monolith / SaaS) | 68 / 90 | 24 |
| arXiv first pages succeeded of ~300 requests (SaaS) | 7 | 24 |
| Bluesky posts stored on bugfixing with dates before 1 Sep | 668 of 4,468 | 25 |
| NewsData "date filtering skipped" | 1,514 | 26 |
| Firecrawl batches rejected | 59 | 27 |
| Topic-less feed failures with an empty reason (SaaS) | 210 of 293 | 28 |
| Feed parse "not well-formed" / "declaration not at start" | 139 / 47 | 29 |
| URL-variant groups / surplus rows (wileytest, 30 days) | 118 / 696 | 30 |
| "Selected article disagrees with itself" | 12 | 31 |

Observations that confirm earlier packages:

- Work package 1: the monolith keyword monitor logs one message, "No articles found or error occurred", for both outcomes.
- Work package 7: zero null publication dates on either tenant, which confirms the now() substitution is live. 140 rows on bugfixing and 103 on wileytest sit at exactly midnight UTC, so date-only sources are stored as exact timestamps. Only 8 and 5 rows have a publication time within two minutes of submission, so wholesale fabrication was rare in this window; precision loss is the common case.
- Work package 2: the re-stamp recovery path stopped after failed lookups 30 times.
- Work package 8: trafilatura returned nothing 2,918 times on SaaS. The result is None, so nothing is overwritten, but no extraction_failed state is recorded for targeted retry.
