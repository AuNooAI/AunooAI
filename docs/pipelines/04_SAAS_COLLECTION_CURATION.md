# SaaS article pipeline: collection, import and curation

Read from code and the live system on 7 October 2026. Code wins over docs wherever they disagree.

- Canonical tree: `/home/orochford/tenants/bugfixing.aunoo.ai/saasmvp-app` (HEAD `92a41b57`). All `file:line` references below are in this tree unless they say "prod".
- Production tree: `/home/orochford/tenants/saas.aunoo.ai`. Prod database: `aunoo_saas_prod`. The canonical tree's own `.env` points at the staging database `aunoo_saas`, not at prod.
- Every file in the curation path is byte-identical between the two trees: `app/analyst/pipeline/**`, `app/analyst/curation.py`, `app/analyst/publishing.py`, `app/relevance/**`, `app/collectors/pipeline.py`, `app/collectors/url_identity.py`, `app/topics/classifier.py`, `app/tasks/topic_classifier_task.py`, `app/tasks/relevance_backfill_task.py`, `scripts/import_firehose_corpus.py`. Section 9 lists the files that do differ.

---

## 0. The shape of the system in five sentences

1. Two separate article stores exist. `analyst_articles` holds the analyst ("curation") pipeline's output, one row per article per analyst topic. `articles` is the shared store that every reader (UI, newsfeed, newsletter, MCP, brand pages) reads.
2. Articles reach `articles` by five routes: the hourly NewsFirehose database import (bulk, no topic), the 15-minute RSS collector, the daily per-brand "official sources" poller (Bluesky, SEC EDGAR, Reddit, OpenAlex and others), the 4-hourly arXiv poller, and the analyst publish step, which copies confirmed `analyst_articles` rows into `articles`.
3. A topic is attached to an article by writing its id into `articles.topic_ids` (an `int[]`). Four things do that: analyst publish, RSS collection for a topic-bound feed, the official-sources poller (brand topic), and an LLM topic tagger for articles that arrived with no topic.
4. The keep/reject decision for topics happens only inside the analyst pipeline (`analyst_status` = confirmed / pending / rejected). For articles that arrive by any other route there is no reject: they get a `relevance_score` from a background sweep, and readers filter on that score.
5. Brands are a separate path: an hourly job matches brand keywords against headlines in `articles`, optionally runs an LLM relevance gate, and writes accepted links into `bm_article_categories`.

---

## 1. Schedulers: what runs, where and when

### 1.1 systemd units (prod)

| Unit | What it runs | Schedule |
|---|---|---|
| `saas.aunoo.ai.service` | uvicorn web, port 10017, 4 workers (drop-in `workers.conf`), `WORKER_ROLE=web` | always on |
| `saas-worker.service` | `python -m app.workers.pipeline_worker`, `WORKER_ROLE=worker`. Hosts every background loop, including the whole curation pipeline | always on |
| `saas-worker-restart.timer` | restarts `saas-worker` every 4 hours to cap libtorch memory growth | 4h |
| `saas-skills-worker.service` | same module with `WORKER_ROLE=skills`: only the MCP validation/newsletter job loop | always on |
| `saas-firehose-import.timer` → `.service` | `scripts/import_firehose_corpus.py --auto-watermark --limit 3000` | hourly, up to 5 min random delay |
| `saas-firehose-check.timer` | `scripts/check_firehose_watermark.py`, emails `FIREHOSE_ALERT_EMAIL` | daily 09:00 |
| `saas-firehose-cleanup.timer` | `scripts/run_firehose_cleanup_when_idle.sh` | hourly |
| `saas-classifier.service` | `ml.classifier_service` on :8013 (sentiment + toxicity heads) | always on |
| `saas-e5-encoder.service` | multilingual-e5-large encoder on :8002 (1024-d vectors) | always on |
| `saas-story-cluster-shadow.timer` | `scripts/story_cluster_shadow_run.py` from the canonical tree against the prod DB on port 5432; writes `story_cluster_*` only | daily 07:30 |
| `saasmvp.aunoo.ai.service`, `saasmvp-classifier`, `saasmvp-skills-worker` | staging (canonical tree, DB `aunoo_saas`) | always on |
| `saasmvp-worker.service` | staging worker | **disabled** (stopped after the 18 June incident) |

Worker drop-ins in `/etc/systemd/system/saas-worker.service.d/` switch on three loops that default to off: `TOPIC_CLASSIFIER_ENABLED=1`, `TOPIC_CLASSIFIER_INLINE=1`, `RELEVANCE_BACKFILL_ENABLED=1`. Prod `.env` adds `TYPESAFE_SHADOW_RELEVANCE=1`, `TYPESAFE_MODEL=jev-1.13.0`, `TYPESAFE_RELEVANCE_DAILY_USD=5`, `NEWSFIREHOSE_BASE_URL=http://188.40.128.115:8000`, `CLASSIFIER_URL=http://localhost:8013`, `E5_ENCODER_URL=http://localhost:8002`. `NEWSAPI_KEY` is empty, so the NewsAPI collector never runs. `FIREHOSE_DSN` is not set anywhere (see 2.1).

Root cron also runs `scripts/daily_import.py` at 05:00 from the canonical tree. It copies articles from the wileytest, opendemo and vc monolith tenants, but because it uses the canonical `.env` it writes to the **staging** database, not prod.

There is no Celery in SaaS. "Celery" in `docs/SAAS_LOG_MONITOR.md` refers to the NewsFirehose service's own workers on another host.

### 1.2 Process roles

- The web process skips all loops when `WORKER_ROLE=web` (`app/core/app_factory.py:54`). With the role unset, one process runs everything.
- `app/workers/pipeline_worker.py:329` reads the role. `skills` runs only `skills_jobs_loop` (`:355`). `worker` runs every loop listed at `:363-465` and hands skills jobs to the skills worker (`:468`).
- On boot the worker fails every `analyst_pipeline_runs` row still marked `running` and inserts a fresh `pending` row per topic with `trigger_type='auto_requeue'` (`pipeline_worker.py:116-200`). Because the worker restarts every 4 hours, auto-requeue is routine: 38 of 249 completed runs in the last 7 days were requeues.

### 1.3 Loops that matter for collection and curation (all in `saas-worker`)

| Loop | Registered | Cadence | Job |
|---|---|---|---|
| `analyst_scheduler_loop` | `pipeline_worker.py:375` | 60 s | turns due `analyst_schedules` rows into `pending` runs |
| `analyst_executor_loop` | `:376` | 5 s poll, max 2 concurrent runs | claims and executes runs |
| `analyst_stale_reaper_loop` | `:380` | 60 s | fails runs with no heartbeat for 15 min, requeues |
| `collector_loop` (RSS) | `:442` | 15 min | topic-bound and topic-less RSS feeds |
| `arxiv_poll_loop` | `:444` | 4 h | followed arXiv authors and categories |
| `official_sources_poll_loop` | `:445` | 24 h per (brand, source) | brand opt-in sources |
| `market_sources_poll_loop` | `:449` | per market | **canonical tree only**, not on prod |
| `websub_delivery_loop` | `:427` | queue | WebSub pushes through the same resolve path as RSS |
| `topic_classifier_loop` | `:429` | 5 min, 50 articles | LLM tags articles with empty `topic_ids` |
| `relevance_backfill_loop` | `:435` | 5 min, 200 articles | writes `articles.relevance_score` |
| `brand_monitoring_loop` | `:385` | 1 h | brand keyword match, relevance gate, `bm_article_categories` |
| `embedding_generation_loop` | `:400` | 5 min, batches of 50 | DeBERTa 768-d vectors into `article_embeddings` |
| `ml_embedding_backfill_loop` | `:421` | 5 min | E5 1024-d vectors into `article_embeddings_ml` |
| `rss_auto_tag_loop` | `:428` | tick | per-tenant tag vocabulary on `TenantArticleState`, not a gate |
| `relevance_label_loop` | `:387` | off unless `RELEVANCE_DISTILL_ENABLED=1` (not set on prod) | teacher labels for distillation |

---

## 2. Sources into `articles`

### 2.1 Stage A — NewsFirehose database import (hourly)

**What.** Copies rows from the NewsFirehose Postgres (`news_firehose` joined to `article_deberta_embeddings`) into `articles` and `article_embeddings`.

**Trigger.** `saas-firehose-import.timer`, hourly, `--auto-watermark --limit 3000`, batches of 500 (`scripts/import_firehose_corpus.py:59`).

**Source connection.** `FIREHOSE_DSN`, defaulting to `postgresql://user:pass@localhost:5431/newsdb` (`import_firehose_corpus.py:55-58`). The comment at `:51-54` says the firehose database moved off this box on 2026-09-10 and that `FIREHOSE_DSN` points at the new host.

**Inputs and filters** (`_SRC_QUERY`, `:419-454`):
- only rows that have a DeBERTa embedding (inner join on `article_deberta_embeddings`), so the DeBERTa vector is required;
- `url` and `title` not null;
- body text present: `content` of 200+ characters or `ai_summary` of 100+ characters;
- `nf.id > watermark`, walked forward in id order.

**Watermark.** `MAX(external_id)` over rows shaped `nf_<id>` (`_get_watermark`, `:85-110`).

**Dedup.** Exact match on `articles.url` (`:217-221`), with no URL normalisation. If the URL exists, the importer back-fills `content`, `image_url` and a missing embedding, and returns `skipped` or `emb_only`. Then `INSERT ... ON CONFLICT (source, external_id) DO NOTHING` (`:281-300`).

**Writes.**
- `articles`: `source` (publisher name, else domain), `external_id='nf_<id>'`, `url`, `title`, `content`, `summary` (from upstream `ai_summary`, dropped if degenerate, `:191-193`), `author` (first `creator`), `actor_id` (`get_or_create_actor`), `image_url`, `published_at`, `collected_at` (= upstream `fetched_at`), `categories`, `sentiment`, `sentiment_score`, `factual_reporting`, `credibility_rating`, `bias`, `ai_tag`, `keywords`.
- It does **not** write `topic_ids`, `relevance_score` or `content_hash`.
- `article_embeddings` (`model='deberta-base'`), `article_citations`, `article_creators`.
- Google News redirect rows get their real publisher recovered from the title (`recover_google_news_publisher`, `:132-159`).

**Gotchas.**
- **The import has been dead since 2026-09-09 16:24.** Prod `.env` has no `FIREHOSE_DSN`, so the importer still reads the old container on `localhost:5431`, which stopped receiving rows when the database moved. The hourly run reports "0 imported, watermark 4511749 → 4511749". The daily check fails with "newest firehose article is 640.6h old". Before the stall the import added 24-29k articles a day. Since then it adds none.
- The watermark is an id, not a time. A row whose body arrived after the walk passed its id is never imported ("Articles that never get content will simply not be synced", `:449-452`), except through the separate `_backfill_null_content` pass for rows already imported.
- Imported articles have no topic. In the six days 3-8 September, 139,064 firehose rows were imported and only 16,566 (12%) ever got a `topic_ids` value. The rest are invisible to every topic-scoped reader.
- `saas-firehose-cleanup.service` has failed every hour because the script sources `.env` and line 124 (`WORDPRESS_APP_PASSWORD`, unquoted with spaces) breaks the shell.

### 2.2 Stage B — RSS collector (15 minutes)

**What.** Polls every active `rss_feeds` row. Prod has 215 active feeds, 187 of them with no topic.

**Trigger.** `collector_loop`, `app/tasks/collector_task.py:29` (15 min). Per active topic it runs `_collect_for_topic` (`:273`), with a 24-hour cold-start window. It then runs `_collect_topicless_rss` (`:140`) with 8-way parallel fetch and a 240-second budget. The canonical tree skips topics that belong to a Market Monitor brand (`:64-96`); prod does not have that change.

**Collectors.** `app/collectors/factory.py`: NewsAPI only if `NEWSAPI_KEY` (empty on prod), plus RSS. So on prod this stage is RSS only.

**Store path.** `CollectionPipeline.resolve_and_store` (`app/collectors/pipeline.py:759-910`):
1. Prepare the title. A titleless item gets a generated display title with `title_provenance='generated'`.
2. Structural validity (`structural_rejection`, `:244`). Items with no identity or no meaningful body or title are quarantined with a reason, not stored.
3. URL normalisation (`app/collectors/url_identity.py:174-209`): lowercase scheme and host, drop default ports, strip tracking query parameters from a JSON registry (`URL_TRACKING_REGISTRY_PATH`), drop the fragment, keep the path.
4. Identity by record type (`identity_for`, `pipeline.py:276`): news, feed entry, social post, scholarly or calendar.
5. Lookup order (`_match_existing`): `(source, external_id)`, then the bare RSS GUID within the same feed, then URL alias table, then canonical URL, then exact URL, then `content_hash`. Social, scholarly and calendar records are never matched by URL.
6. An existing row gets the topic id appended to `topic_ids` (`_merge_existing`, `:983`). A new row is built with `topic_ids=[topic_id]` (`_build_new_row`, `:1032`).
7. With `TOPIC_CLASSIFIER_INLINE=1` (set on prod), new rows that still have no topic are tagged by the LLM topic classifier before commit (`_inline_topic_classification`, `:1125-1150`).
8. RSS rows are linked into dedup groups (`rss_article_dedup_groups`) by canonical URL or normalised title within a time window.

**Writes.** `articles` (`source='rss'`, `rss_feed_id`, `canonical_url`, `content_hash`, `quality_score`, collector data-quality columns, `topic_ids`), URL alias rows, observations, feed memberships, `rss_feeds` validators and `last_error`. No relevance score.

### 2.3 Stage C — official sources per brand (daily)

**What.** For each enabled brand that lists sources in `bm_brands.config['extra_sources']`, queries each source with the brand keywords and stores the results under the brand's monitoring topic (`app/tasks/official_sources_poll_task.py`, docstring `:1-26`).

**Sources.** `get_official_collectors` (`app/collectors/factory.py`): `sec_edgar`, `crossref`, `openalex`, `courtlistener`, `reddit` always; `regulations_gov` if its key is set; `bluesky` if the app handle and password are set (set on prod); `x`, `tiktok`, `instagram` via xpoz if `XPOZ_API_KEY` is set (set on prod).

**Cadence.** `POLL_INTERVAL = 24h` per (brand, source) (`:57`), with a weekly reconciliation window (`:59`) and a Redis leader lock.

**Writes.** Goes through the same `resolve_and_store` path with `topic_id = brand.topic_id`, then writes `bm_article_categories` directly with `classification_method='official'` (`:180-230`). There is **no relevance check** on this path; Bluesky, OpenAlex and Crossref need a brand term as a whole word, and Reddit trusts the brand's own subreddit.

### 2.4 Stage D — arXiv poll (4 hours)

`app/tasks/arxiv_poll_task.py`. Fetches papers for followed authors and categories across tenants. Identity is the arXiv id without its version suffix (`source='arxiv'`). Writes `articles`. Not topic-scoped unless a feed or topic binds it.

### 2.5 Social collectors outside `articles`

Bluesky also appears as an analyst sub-collector (`app/analyst/pipeline/steps/collect_bluesky.py`), but no prod analyst topic lists it. ThinkPol (Reddit archive) and xpoz reach/propagation code (`app/social/*`, `app/foresight/*`) write the `social_*` tables for propagation and reach work; they are not part of the article curation path.

### 2.6 Live volumes (prod, from `articles.collected_at`)

| Period | Firehose import (`nf_`) | Everything else |
|---|---|---|
| 2-9 Sept, daily | 15,400-28,900 | 500-1,000 |
| 10 Sept - 6 Oct, daily | 0 | 2,000-9,000 (about 4,000 on a typical day) |

Last 7 days by `source`: rss 5,737; arxiv 5,344; sec_edgar 1,292; bluesky 208; openalex 32; reddit 16; crossref 4; courtlistener 3. On top of those, about 16,300 rows came from analyst publish (their `external_id` is the article URL).

---

## 3. The analyst (curation) pipeline

This is the only place where an article is kept or rejected for a topic. It reads NewsFirehose over **HTTP**, not from the database import, so it kept working after the import died.

### 3.1 Configuration

- `analyst_topics` (model `app/database/models.py:5220`): `name`, `description`, `topic_id` (link to the production `topics` row), `categories`, `future_signals`, `sentiment_options`, `time_to_impact_options`, `driver_types`, `topic_alignment_threshold` (DB default 0.5), `keyword_relevance_threshold` (default 0.2), `publish_min_articles` (default 10), `collection_config` (JSONB), `pipeline_config` (JSONB).
- `collection_config` keys: `keywords`, `newsfirehose_topic_slug`, `newsfirehose_min_relevance` (0.5 on every prod topic), `max_articles` (1000 on prod), `language`, `collector_sources` (default `["newsfirehose"]`), `rss_feed_urls`, `arxiv_categories`, `semantic_scholar_fields`, `bluesky_sort`, `newsfirehose_sources`, `newsfirehose_categories`.
- `pipeline_config` keys: `steps` (list), `relevance_model`, `classify_model`, `summarize_model`, `ner_model` (all null on prod, so models come from `ai_model_configs`), `use_relevance_classifier`, `use_shared_relevance_scorer`, `evaluate_existing_summaries`.
- `analyst_schedules` (model `:5717`): `interval_hours`, `next_run_at`, `is_active`. Prod: topics 1, 3, 4 and 5 every 6 hours; the other 16 scheduled topics every 24 hours. Topic 23 has no schedule and no steps.
- `analyst_custom_steps`: optional per-topic LLM steps run after the main steps (`app/analyst/pipeline/steps/custom.py`).
- Models: `ai_model_configs` rows with `is_default=true`, keyed by `use_case` (`app/ai/llm.py:619-660`). A call with no `use_case` falls back to `article_analysis`.

Prod model rows: `analyst_relevance_score` and `analyst_classify` = Bedrock `us.amazon.nova-lite-v1:0`; `relevance_score` = nova-lite; `topic_classifier` = `us.meta.llama3-3-70b-instruct-v1:0`; `article_analysis` = `us.anthropic.claude-haiku-4-5-20251001-v1:0`; `fallback` = `mistral.mistral-large-3-675b-instruct`.

### 3.2 Stage 1 — schedule and claim

- `analyst_scheduler_loop` (`app/tasks/analyst_scheduler_task.py:54-105`) selects `analyst_schedules` with `is_active` and `next_run_at <= now`, inserts `analyst_pipeline_runs(status='pending', trigger_type='scheduled')` and moves `next_run_at` forward by `interval_hours`.
- `analyst_executor_loop` (`:108-136`) claims the oldest pending run with `UPDATE ... WHERE id = (SELECT ... FOR UPDATE SKIP LOCKED)` and sets `status='running'`, `started_at`, `last_heartbeat_at` (`:139-161`). It runs at most 2 runs at once (`MAX_CONCURRENT_RUNS`, `:37`).
- The stale reaper (`:220-304`) fails any running row whose heartbeat is older than 15 minutes and requeues it. Steps stamp the heartbeat between steps and inside long loops (`app/analyst/pipeline/base.py:64-79`).
- Runs can also be started by hand from the analyst UI (`trigger_type='manual'`).

### 3.3 Stage 2 — run the steps

`run_pipeline` (`app/analyst/pipeline/runner.py:64-387`) reads `pipeline_config.steps`, else `DEFAULT_PIPELINE_STEPS` (`base.py:126-134`): `collect`, `score_relevance`, `classify`, `summarize`, `extract_ner`, `resolve_mentions`, `enrich_mbfc`. **Every prod topic lists six steps and leaves out `resolve_mentions`**, so Wikidata entity resolution does not run on prod. Each step writes an `analyst_pipeline_step_logs` row (status, counts, model, tokens, cost, duration). A step with `status='failed'` or an exception stops the run (`runner.py:198-211`). Articles live in memory (`context.articles`) until the end of the run; nothing is written to `analyst_articles` until every step has finished.

#### Step `collect` (`app/analyst/pipeline/steps/collect.py:518-699`)

- **Incremental window:** `from_date = max(analyst_articles.published_at for this topic) − 1 day` (`:548-557`). A first run falls back to a 30-day cutoff.
- **Layer 1, topic slug:** `GET {NEWSFIREHOSE_BASE_URL}/v1/topics/{slug}/articles` with `min_relevance` (0.5), `sort_by=published_at`, pages of 100, up to `max_articles` (`_collect_by_topic`, `:330-379`). The NewsFirehose service's own topic classifier is therefore the first relevance gate.
- **Layer 3, keyword top-up:** if Layer 1 returned fewer than `max_articles`, `GET /v1/search` per keyword batch. `_build_query_batches` (`:435-471`) flattens every keyword into an OR-chain of at most 8 terms and 450 characters, because the API rejects more than 8 OR terms. `_normalize_query` (`:92-104`) strips quotes and parentheses, turns `and`, `|` and `+` into `OR`, and drops `NOT` terms, so boolean keywords lose their meaning.
- **Other sources** by `collector_sources`: `rss` (`collect_rss.py`, `rss_feed_urls`), `arxiv`, `semantic_scholar`, `bluesky` (`:591-627`). On prod only topics 5, 16, 21 and 24 add RSS, and 16 and 25 add Semantic Scholar.
- **Parsing** (`_parse_article`, `:190-295`): drops items with no title; drops items older than 30 days; replaces `publishedAt` with the date in the URL slug when the claimed date is more than 3 days newer (`:165-220`); drops placeholder sources ("AVAILABLE", "PROFESSIONAL", "CORPORATE", "UNKNOWN"); drops a body that is Google's consent-gate text but keeps the article; `content_hash = sha256(title|url)` (`:116-118`).
- **Dedup:** first by URL across the sources in this run (`:644-653`), then capped to `max_articles`, then against this topic's existing `analyst_articles` by `firehose_url` or `content_hash` (`_filter_already_seen`, `:474-515`). Dedup is per analyst topic only; the same article can be stored under several analyst topics.
- **Images:** og:image fetch for new articles with no image, 8 at a time, 90-second budget (`:34-82`).
- Fails only if every source errored and nothing was collected (`:689-691`).

#### Step `score_relevance` (`app/analyst/pipeline/steps/score_relevance.py:331-577`)

Inputs per article: title and `summary` (else `full_text`, else `content`). Topic context is `"{name}\nTopic Description: {description}"`.

- **DeBERTa classifier** (`_classifier_score`, `:134-159`): loaded from `models/relevance_classifier/final` under the install root, or `RELEVANCE_MODEL_DIR`. **This directory does not exist in the prod tree**, and 10 of 20 topics also set `use_relevance_classifier=false` (`:374`). So on prod the classifier never runs.
- **Embedding similarity** (`:162-183`): `sentence-transformers/all-MiniLM-L6-v2` on CPU, cosine of topic text and `title. summary`, clipped to 0-1.
- **Combination** (`:410-422`): both signals → `0.6·classifier + 0.4·embedding` ("hybrid"); one signal → that signal ("classifier_only" or "embedding_only").
- **When to skip the LLM** (`:436-462`): with two signals, skip when the score is ≤0.30 or ≥0.70 and the two signals differ by no more than 0.4. With one signal (always the case on prod), skip only when the score is ≤0.10 or ≥0.85. A skipped article gets `topic_alignment_score = classifier score, else embedding score` and `keyword_relevance_score = embedding score, else classifier score`.
- **LLM scoring** (`_llm_score`, `:226-269`): `use_case="analyst_relevance_score"` (Nova-lite), temperature 0.1, 512 max tokens, content cut to 6,000 characters. The prompt (`:195-223`) asks for `topic_alignment_score`, `keyword_relevance_score`, explanation, `confidence_score`, 1-3 topics and 3-5 keywords. Then `relevance_score = 0.6·alignment + 0.4·keyword` (`:512`).
- **Divergence cap:** if the two local signals differed by more than 0.4, confidence is capped at 0.5 and the method is `hybrid+llm_diverged` (`:501-516`).
- **LLM failure:** the hybrid score is kept with confidence halved and method `<method>_fallback` (`:526-542`). If there was no hybrid score either, the article stays unscored and lands in `pending`.
- **Optional shared scorer:** `pipeline_config.use_shared_relevance_scorer` routes through `app.relevance.score_batch` (cross-encoder plus LLM band) and writes the same score into all three fields (`:276-329`, `:361-365`). Off on every prod topic.
- This step does not drop articles; it only scores them.

Method naming gotcha: `classification_method='hybrid+llm'` means "a local score was uncertain and the LLM decided", even when the only local score was MiniLM. Last 7 days on prod: 40,333 `hybrid+llm`, 28,935 `embedding_only`, 1 `embedding_only_fallback`. So about 58% of articles went to Nova-lite.

#### Step `classify` (`app/analyst/pipeline/steps/classify.py:176-348`)

- Skipped entirely if the topic has no `categories` (`:200-204`).
- Skips articles that already have `category` and `time_to_impact`, and articles with `topic_alignment_score < threshold − 0.1`, because they will be auto-rejected (`:209-234`).
- Nova-lite via `use_case="analyst_classify"`, temperature 0.1, 1,024 max tokens, content cut to 5,000 characters, 8 concurrent calls, batches of 100 (`:21-30`, `:259-271`).
- Writes `category`, `future_signal`, `sentiment`, `time_to_impact`, `driver_type`, `political_bias`, `factuality` and an explanation for each except category (`:91-98`).
- Out-of-taxonomy values are replaced (`category` → "Other") or dropped (`_enforce_taxonomy`, `:111-151`). Political bias and factuality use fixed lists (`:104-108`).
- Defaults when the topic leaves a list empty: four future signals, four sentiments, four time-to-impact bands, five driver types (`:192-198`).

#### Step `summarize` (`app/analyst/pipeline/steps/summarize.py:117-215`)

- If the article already has an upstream `ai_summary` and `evaluate_existing_summaries` is true, a sufficiency check decides whether to keep it (`_evaluate_summary`; it tries vLLM, else the default LLM).
- Otherwise vLLM `microsoft/Phi-3-mini-4k-instruct` at `VLLM_BASE_URL` (default `http://localhost:8765/v1`, live) writes the summary; it is free.
- Fallback when vLLM is down: `get_completion` with no `use_case`, which resolves to `article_analysis` = **Haiku 4.5** (`:183-185`). 108 such calls in the last 7 days, $0.17.
- Writes `ai_summary`, `ai_summary_model`.

#### Step `extract_ner` (`app/analyst/pipeline/steps/extract_ner.py:199-343`)

KeyBERT keywords when missing, then entities (people, organisations, locations, tags) from KeyBERT candidates plus vLLM Phi-3; LLM fallback via `ner_model` (null, so `article_analysis`). Keeps upstream keywords and entities when present. Writes `extracted_keywords`, `entities`, `tags`.

#### Step `resolve_mentions` (`app/analyst/pipeline/steps/resolve_mentions.py`)

Resolves NER names to Wikidata QIDs and writes `entities_resolved`. **Not in any prod topic's step list.**

#### Step `enrich_mbfc` (`app/analyst/pipeline/steps/enrich_mbfc.py:44-93`)

Loads the MBFC source cache and the topic's `analyst_source_overrides`. A domain with override action `exclude` is **removed from the run and never stored**. Otherwise fills `mbfc_bias`, `mbfc_factual_reporting`, `mbfc_credibility`, `mbfc_country`, `mbfc_media_type` where empty, and applies credibility overrides.

#### Custom steps

Run after the main steps if the topic has active `analyst_custom_steps`; results go into `custom_enrichments`.

### 3.4 Stage 3 — persist and bucket (the keep/reject decision)

`runner.py:253-344` inserts one `analyst_articles` row per article left in the run, with `analyst_status` set by `_bucket` (`:263-273`) on `topic_alignment_score`:

| `topic_alignment_score` | `analyst_status` |
|---|---|
| `>= threshold + 0.1` | `confirmed` |
| `<= threshold − 0.1` | `rejected` (auto-reject; `analyst_reviewed_by` stays NULL) |
| between the two, or NULL | `pending` |

`threshold = analyst_topics.topic_alignment_threshold`, defaulting to 0.3 here if NULL. Prod values: 0.3 on topics 1, 3, 4, 5, 6, 7, 8, 10 and 11 (confirm at ≥0.4, reject at ≤0.2); 0.5 on topics 12-25 (confirm at ≥0.6, reject at ≤0.4). The margin 0.1 is hard-coded and duplicated in `classify.py:215-217`.

Note that the bucket uses `topic_alignment_score`, not `relevance_score`. On the local-only path that is the MiniLM cosine; on the LLM path it is Nova-lite's alignment answer.

Run totals go to `analyst_pipeline_runs`: `status`, `completed_at`, `articles_collected`, `articles_classified`, `total_tokens_used`, `estimated_cost_usd`, `error_log` (`:346-362`).

### 3.5 Stage 4 — human review

`PATCH` from the analyst UI → `review_article` (`app/analyst/service.py:419-450`) sets `analyst_status`, `analyst_reviewed_at`, `analyst_reviewed_by`, `analyst_notes`, and records the decision in `relevance_evaluations` / `relevance_decisions` via `app/relevance/human.py` (rubric `analyst_review_binary_v1`). The UI tells auto-rejects from human rejects by `analyst_reviewed_by IS NULL` (`app/analyst/routes.py:187`). Rejecting an article that was already published does **not** remove it from `articles.topic_ids`; nothing in the code un-publishes.

`app/analyst/curation.py` is not part of the gate. It holds two analyst-triggered LLM tools: `cluster_articles` (up to 200 articles, writes `custom_enrichments.cluster_label`) and `generate_narrative` (writes `analyst_narratives`). Both use the default model (`article_analysis` = Haiku).

### 3.6 Stage 5 — publish to `articles`

After a run that completed and stored at least one article, if `analyst_topics.topic_id` is set, the runner calls `publish_to_production` (`runner.py:364-385`; `app/analyst/publishing.py:59-579`).

Gates, in order:
1. **Eligible set:** `analyst_status='confirmed'` and `topic_alignment_score >= topic_alignment_threshold` (defaulting to 0.5 here if NULL) (`publishing.py:107-118`). With the 0.1 margin every confirmed row already passes this.
2. **Maturity floor:** at least `publish_min_articles` (10) eligible rows for the whole topic, or the publish raises `PublishGateError` (`:120-133`).
3. **Delta:** only rows with `published_to_production_at IS NULL`, ordered by id, at most `PUBLISH_MAX_PER_ACT` (5,000) per act (`:56`, `:138-145`).
4. **Run gate** (`validate_run`, `app/analyst/pipeline/evals.py:119-184`): zero error-level issues, warnings on at most 10% of articles, at least 95% relevance coverage (`evals.py:114-116`).
5. **Per-article validation** (`validate_article`, `evals.py:53`): missing title, out-of-range scores or malformed entities are errors; the article is skipped as `validation_rejected` (`publishing.py:226-235`).

Per article, inside its own savepoint, committed every 50 (`PUBLISH_COMMIT_BATCH`, `:44`):
- Mark `published_to_production_at` first (`:205-212`), so deterministic failures are not retried.
- **Exact URL match** against `articles.url` (`:269-275`). If found: append the production topic id to `topic_ids` (`:281-285`); fill `relevance_score` with **`topic_alignment_score`** if empty; fill sentiment, factual reporting, credibility, bias and image where empty; replace the summary only if the provenance policy prefers the analyst's. Outcome `topic_linked`.
- Else **insert** a new `articles` row with `external_id = firehose_url or url`, `source = source_name or 'analyst'`, `topic_ids=[topic_id]`, `relevance_score = relevance_score` (the 0.6/0.4 blend, not the alignment score), MBFC fields, `content_hash`, `ai_tag`, `keywords`, `actor_id`, `ON CONFLICT (source, external_id) DO NOTHING` (`:365-449`), plus `article_citations`.
- An `analyst_publications` row records the act.

Gotcha: the same analyst field lands in different `articles` columns depending on whether the URL already existed (`topic_alignment_score` on link, the blended `relevance_score` on insert).

### 3.7 Live numbers (prod, last 7 days)

- `analyst_articles` created per day: 6,400-14,300 (about 9,700 on average).
- Status of rows created in the last 7 days: rejected 47,968 (69%, mean alignment 0.06); confirmed 18,098 (26%, mean alignment 0.81); pending 3,203 (5%). None has been reviewed by a person, and every confirmed row is already marked published.
- Runs: 211 scheduled and 38 requeued runs completed; 27 scheduled and 16 requeued runs failed.

### 3.8 Cost per step (prod, last 7 days)

| Step | Model | Calls (ledger) | Tokens in / out | Real cost | What the run log records |
|---|---|---|---|---|---|
| `score_relevance` | Nova-lite | 55,328 | 72.3M / 9.4M | **$6.59** | nothing: `model_used` contains "deberta", which `_estimate_cost` treats as free (`runner.py:58-59`) |
| `classify` | Nova-lite | 28,080 | 34.6M / 9.1M | **$4.26** | $74.94: `model_used` is NULL, so the estimate falls back to Haiku prices (`runner.py:60-61`) |
| `summarize`, `extract_ner` | vLLM Phi-3 (free), Haiku fallback | 108 Haiku calls | 72k / 16k | $0.17 | none |
| `collect`, `enrich_mbfc` | none | | | $0 | |

Real costs come from `llm_usage_log`. The analyst pipeline costs about $11 a week. `analyst_pipeline_runs.estimated_cost_usd` is wrong in both directions and should not be used.

---

## 4. Topics: `topics` versus `analyst_topics`, and how `topic_ids` gets set

### 4.1 Two tables

- **`topics`** (`models.py:337`) is the production catalogue that readers, subscriptions and `articles.topic_ids` refer to. Columns that matter: `name`, `slug`, `description` (fed to every relevance prompt), `categories`, `collection_keywords`, `is_active`, `is_custom`, `custom_tenant_id`, `is_public`. Prod has 21 active curated topics (ids 1, 2, 4, 9-11, 13-26, 36), 11 active custom topics (27-44; these are brand monitoring topics), 6 inactive curated and 5 inactive custom.
- **`analyst_topics`** is the curation workspace: one per thing an analyst curates, with the collection and pipeline config, the ontology lists and the thresholds. `analyst_topics.topic_id` links it to the `topics` row it publishes into. Several analyst topics can feed one production topic (24 and 25 both feed topic 36). Analyst topic ids and production topic ids are different numbers (analyst 4 Geopolitics → topic 2; analyst 13 Business & Finance → topic 17).

### 4.2 Writers of `articles.topic_ids`

| Writer | When | Rule | Ref |
|---|---|---|---|
| Analyst publish | after each successful run | append the linked topic for confirmed articles | `publishing.py:281-285`, `:409-449` |
| RSS collection | 15 min | append the feed's topic | `pipeline.py:983-1045` |
| Official sources | daily per brand | brand topic id | `official_sources_poll_task.py:271-285` |
| Inline topic classifier | at RSS/official insert, `TOPIC_CLASSIFIER_INLINE=1` | LLM picks from the curated catalogue | `pipeline.py:1125-1150` |
| Topic classifier loop | every 5 min, 50 articles, last 7 days only | same LLM, for rows with empty `topic_ids` | `app/tasks/topic_classifier_task.py:46-94`, `app/topics/classifier.py:209-296` |
| One-off backfill | manual | `scripts/backfill_topic_classifier.py` | |

The firehose import writes no topic.

### 4.3 The LLM topic classifier

- Catalogue: active, non-custom `topics` (`classifier.py:130-147`), so brand topics are never assigned this way.
- Prompt: the catalogue (id, name, first sentence of the description), title and the first 2,000 characters of `full_text` or `content` (`:46`, `:73-95`). The model returns a JSON array of ids; unknown ids are dropped (`:102-127`).
- Model: `use_case="topic_classifier"` (`:48`) = **Llama 3.3 70B** on prod. Docstrings and the 18 June incident note call it Haiku 4.5; the code and DB say Llama. 8 concurrent calls.
- Selection: `topic_ids` empty, published in the last 7 days, newest first, limit 50 (`:253-262`).

**Gotcha, live now:** the loop does not pass a skip list (`topic_classifier_task.py:88-94`), so an article for which the model returns `[]` stays at the head of the queue. In the last 24 hours the loop logged "tagged 0/50" 195 times and "tagged 1/50" 3 times: it re-sends the same 50 articles every 5 minutes. The ledger shows 84,138 `topic_classifier` calls and 104M input tokens in the last 7 days. `ai_model_configs` carries Nova-lite prices for this row (`cost_per_1k_input = 6e-05`), so the ledger records $6.32; at Llama 3.3 70B's Bedrock list price (about $0.72 per million tokens, worth confirming) the real spend is about $75 a week. That makes it the most expensive step in the whole collection path, for almost no output.

### 4.4 Relevance score for non-analyst articles

`relevance_backfill_loop` (`app/tasks/relevance_backfill_task.py`, every 5 min, 200 rows, last 30 days by default) calls `score_unscored_articles` (`app/relevance/backfill.py:42-195`):
- Selects `relevance_score IS NULL` rows that have at least one topic.
- Scores each article against each of its topics with `score_batch(..., llm_only=True)`: Nova-lite via `use_case="relevance_score"`, prompt at `app/relevance/scorer.py:293-321`, 0-1 scale (1 = central, about 0.5 = secondary, 0 = off-topic or namesake).
- Writes one `relevance_evaluations` row per (article, topic) with `caller_site='corpus_backfill'` and no decision.
- Writes `articles.relevance_score = max over the article's topics`. This is a "relevant to at least one topic" number, not relevance to any particular topic.
- A low score removes nothing. There is no reject on this path.

Last 7 days: 3,123 corpus-backfill evaluations; `relevance_score` use_case total 25,500 calls, $0.96 (shared with the brand gate and foresight retrieval).

---

## 5. Brands

### 5.1 Tables

- `bm_brands`: `tenant_id`, `name`, `display_name`, `description`, `brand_keywords`, `product_keywords`, `people_keywords`, `competitor_keywords`, `topic_id` (its custom monitoring topic), `enabled`, `config` (JSONB with `relevance_*`, `e5_relevance_threshold`, `embedding_top_k`, `embedding_margin`, `exclude_keywords`, `required_keywords`, `extra_sources`, `source_state`).
- `bm_article_categories`: one row per (article, brand, category) with `classification_method` (`embedding`, `keyword` or `official`), `confidence`, `classified_at`. A row's existence is what makes an article belong to a brand.
- `bm_runs`, `bm_article_stories` (story dedup), `bm_competitor_categories`, `relevance_run_metrics` (gate histogram and counts).
- Decision service tables (migration `relevance_decisions_01` / `relevance_decisions_prod_01`, 5 Oct): `relevance_evaluations` (append-only, one per provider evaluation), `relevance_decisions` (action accept / reject / review with policy version), `relevance_latest` (current decision per pair, used for reuse). View `relevance_shadow_comparison`.

### 5.2 Hourly classification (`run_classification`, `app/features/brand_monitoring/service.py:487-765`)

Trigger: `brand_monitoring_loop`, hourly (`app/tasks/brand_monitoring_task.py:22`), for tenants with the brand monitoring feature. Per enabled brand:
1. **Candidates:** headline-only, case-insensitive whole-word regex on `articles.title` for the brand's name, slug and keywords; `required_keywords` must also appear, `exclude_keywords` veto (`_build_brand_sql_filter`, `:100-154`). Last 30 days, not yet linked to this brand, newest first, at most 2,000.
2. **E5 gate**, if `e5_relevance_threshold > 0` (`:591-596`). 0 on every prod brand.
3. **Relevance gate**, if `relevance_min_score > 0` (`:597-614`, `_relevance_gate` `:271-457`). Modes: `relevance_llm_gate=true` sends every candidate to Nova-lite (`llm_only`); otherwise cross-encoder plus E5, with an LLM band (0.35-0.70) only if `relevance_use_llm`. Decision `decide_legacy` (`app/relevance/decision.py:29-56`): accept if score ≥ min, reject if below, **review if the model failed, and review is kept** (fail open). If the whole gate throws, all candidates are kept. `relevance_observe_only` records without dropping.
4. **Decision reuse** (`relevance_reuse_decisions`, default true): an unchanged (article text, brand definition, model, rubric, threshold) pair reuses its stored accept or reject with no model call. Human decisions always win.
5. **Category:** nearest category prototypes on the article's DeBERTa embedding (`top_k=3`, `margin=0.02`), or keyword rules if there is no embedding. Writes `bm_article_categories` with method `embedding` or `keyword` (`:640-685`). Rejected candidates are not written anywhere in `bm_*`; they stay "not yet linked" and come back next hour, where reuse skips them.
6. Story groups (cosine distance 0.08 within 3 days) and competitor head-to-head rows, each in a savepoint.

Prod config: brands 1-5 (aunoo-ai, dataminr, inoreader, feedly, palantir; tenant 1) have `relevance_llm_gate=true`, `relevance_min_score=0.5`, `relevance_observe_only=false`. Brands 8, 10, 11, 15, 16 and 17 have no gate, so a headline keyword hit is enough.

Official-source records (section 2.3) are linked with `classification_method='official'` and no gate. Last 7 days on prod: 993 `official` rows (726 articles), 9 `embedding` rows.

### 5.3 What is live and what is shadow

| Piece | State on prod |
|---|---|
| Brand relevance gate, Nova-lite, min 0.5 | **Live** (enforcing) on brands 1-5 |
| Decision recording and reuse | **Live** since 5 Oct. Last 7 days: 52 brand-gate evaluations, all rejects. A typical sweep now reuses everything ("6 candidates, 0 scored, 6 reused") |
| Human brand accept / reject (`POST /api/v1/brand-monitoring/articles/{id}/relevance`) | Live: 30 human accepts, 49 human rejects recorded in 7 days |
| Jev shadow (`TYPESAFE_SHADOW_RELEVANCE=1`, `jev-1.13.0`, $5/day cap) | **On but idle.** It only judges freshly scored pairs; with everything reused there are none. Zero shadow log lines in 24 h. The only Jev rows in 7 days are 50 from `replay`. Record-only: never touches `relevance_latest` |
| Analyst runner using the decision service | Not wired (spec review, "Not yet wired") |
| Publish checking an accepted decision | Not wired |
| Distillation (`RELEVANCE_DISTILL_ENABLED`) | Off |
| Student cross-encoder (`RELEVANCE_CE_MODEL`) | Unset; stock ms-marco would be used, but the live gates run `llm_only` so the cross-encoder is not called |
| Market Monitor vendor collection | Canonical tree only, not on prod |

TypeSafe/Jev in this pipeline is used only by that shadow (`app/relevance/providers/jev.py`, `app/relevance/shadow.py`). Other Jev shadows (stance, reception, profiles, affiliation, honeypot) are outside this path.

---

## 6. Readers: what makes an article visible

| Surface | Predicate | Ref |
|---|---|---|
| Articles list API (`/api/v1/articles`) | `topic_id = ANY(topic_ids)` (if a topic is chosen), `summary` longer than 20 characters, sentiment in the canonical set. **No relevance filter** | `app/routes/articles.py:120-131` |
| Reader newsfeed | topic filter, `collected_at` window, `relevance_score >= 0.3`, `sentiment` not null or empty | `app/newsfeed/service.py:74-90` |
| Public topic pages | same as the newsfeed: `relevance_score >= 0.3` plus sentiment | `app/public/queries.py:69-80` |
| Newsletter (marketing and MCP newsletter job) | `relevance_score IS NOT NULL`, `published_at` in range, topic filter | `app/marketing/service.py:1020-1040` |
| MCP `get_topic_articles` | topic tag (or the tenant's subscribed topics), `collected_at` and `published_at` in the window. **No relevance filter** | `app/auspex/tools.py:57-116` |
| Dashboard counts | `topic_id = ANY(topic_ids)` and `collected_at` | `app/routes/dashboard.py:20-25`, `:73` |
| Brand pages, stats, sentiment, alerts, MCP `get_brand_articles` | a row in `bm_article_categories` | `service.py:1003-1999`; `app/auspex/brand_tools.py` |
| Competitive landscape, people mentions, articles-by-term | their own headline regex, **ungated** | `service.py:1245-1592` |
| Analyst UI | `analyst_articles` by `analyst_status` | `app/analyst/service.py:300-384` |

Consequence: the analyst `analyst_status` decision reaches readers only through publish. An RSS, arXiv or official-source article is visible on topic surfaces with no reject step; the newsfeed hides it until the backfill scores it at least 0.3, while the article list and MCP show it regardless.

---

## 7. Tables and key columns written at each stage

| Stage | Tables written | Key columns |
|---|---|---|
| A. Firehose import | `articles`, `article_embeddings`, `article_citations`, `article_creators`, `actors` | `external_id='nf_<id>'`, `url`, `summary`, MBFC fields, `ai_tag`, `keywords`; no `topic_ids`, no `relevance_score`, no `content_hash` |
| B. RSS collector | `articles`, URL aliases, observations, feed memberships, `rss_article_dedup_groups`, `rss_feeds` | `source='rss'`, `rss_feed_id`, `canonical_url`, `content_hash`, `topic_ids`, `quality_score` |
| C. Official sources | `articles`, `bm_article_categories`, `collection_checkpoints`, `bm_brands.config.source_state` | `topic_ids=[brand topic]`, `classification_method='official'` |
| D. arXiv | `articles` | `source='arxiv'`, base arXiv id |
| Embedding loops | `article_embeddings` (DeBERTa 768-d via `DEBERTA_ENCODER_URL`, default :8001), `article_embeddings_ml` (E5 1024-d via :8002) | |
| Topic classifier | `articles` | `topic_ids` |
| Relevance backfill | `articles`, `relevance_evaluations` | `relevance_score` (max over topics) |
| Analyst schedule/claim | `analyst_schedules`, `analyst_pipeline_runs` | `next_run_at`, `status`, `last_heartbeat_at` |
| Analyst steps | `analyst_pipeline_step_logs` | `model_used`, tokens, `cost_usd`, `duration_ms` |
| Analyst persist | `analyst_articles` | `analyst_status`, `relevance_score`, `topic_alignment_score`, `keyword_relevance_score`, `confidence_score`, `classification_method`, `relevance_explanation`, ontology fields, `ai_summary`, `entities`, MBFC fields, `content_hash`, `firehose_url` |
| Analyst review | `analyst_articles`, `relevance_evaluations`, `relevance_decisions`, `relevance_latest` | `analyst_reviewed_by`, `analyst_reviewed_at` |
| Analyst publish | `articles`, `article_citations`, `analyst_articles`, `analyst_publications` | `topic_ids`, `relevance_score`, `published_to_production_at` |
| Brand classification | `bm_runs`, `bm_article_categories`, `bm_article_stories`, `bm_competitor_categories`, `relevance_run_metrics`, `relevance_evaluations`, `relevance_decisions`, `relevance_latest` | `classification_method`, `confidence`, action, policy version |

---

## 8. Docs reconciled against code

| Doc | Claim | What the code and live system say |
|---|---|---|
| `docs/BRAND_RELEVANCE_SAAS_VS_MONOLITH.md` (monolith repo) | "Three mechanisms feed" topics: RSS collection, topic tagging, relevance score | Omits the two largest feeders: analyst publish (about 16k new rows a week now) and the firehose import (24-29k a day until 9 Sept, no topic). Its numbers on brands (gate on 1-5, Nova-lite 0.5, review kept) match the code |
| same | "Only confirmed articles are published" | Also needs alignment ≥ threshold, ≥10 eligible articles per topic, the run gate and per-article validation |
| same | Topic tagging "runs at ingest and as a background loop" | True, but the loop is currently stuck re-sending the same 50 articles (section 4.3) |
| `docs/BRIEF_2026-05-02_relevance_classifier.md` | DeBERTa toggled off on 7 topics; the rest still use it | The classifier directory does not exist in the prod tree, so no topic uses DeBERTa; every topic is MiniLM plus Nova-lite |
| same | Cost should show as Nova-lite in step logs | `model_used` is stored as `deberta+embedding+None` or NULL, so step-log costs are wrong (section 3.8) |
| `docs/RELEVANCE_ROLLBACK.md` | "Everything is opt-in / off by default"; Jev shadow off | Correct as defaults. On prod the brand gate is on for 5 brands and the Jev shadow flag is on |
| `docs/RELEVANCE_DECISION_SERVICE_SPEC_REVIEW.md` "Delivery status" | "Stages 2 to 4 are not on prod" | Superseded by its own later section "Prod deployment (2026-10-05, late)", which matches prod: decision tables and Jev shadow are live. Code in `app/relevance/` is identical in both trees |
| `docs/RELEVANCE_DECISION_SERVICE_SPEC.md` | Status: "implementation design", "no live flag changes" | Design doc; flags were since changed on prod (shadow on). Analyst runner and publish still not wired, as the spec says |
| `docs/INCIDENT_2026-06-18_pipeline_stall_load_spike.md` | Remediation 5: cap auto-requeue, dedup pending per topic | Boot reaper and stale reaper still requeue without an attempt cap; they only skip when a pending or running row already exists for the topic (`pipeline_worker.py:170-180`) |
| `docs/EMERGING_TOPICS_SYSTEM.md` "Operational topology" | Worker is `saasmvp-worker.service` with 36 loops | Prod worker is `saas-worker.service`; `saasmvp-worker` is disabled; the worker now starts about 60 loops |
| `docs/SAAS_LOG_MONITOR.md` BUG-16 | vLLM model has a 2,048-token context | The live vLLM reports Phi-3-mini-4k with `max_model_len` 4096 |
| `app/topics/classifier.py` and `topic_classifier_task.py` docstrings | Topic tagging uses Bedrock Haiku 4.5 | `ai_model_configs.topic_classifier` = Llama 3.3 70B |
| `app/tasks/relevance_backfill_task.py` docstring | Inflow about 640 articles a day | True only after the firehose stopped; before, 24k+ a day arrived but most had no topic and so were never scored |
| `scripts/import_firehose_corpus.py:51-54` | `FIREHOSE_DSN` points at the new host | It is not set; the default is the dead local container |
| saas `CLAUDE.md` | Collectors are "NewsAPI, RSS"; 5 background loops | NewsAPI key is empty on prod; the analyst pipeline, firehose import and official sources are the main paths; about 60 loops |

---

## 9. Where prod differs from canonical

- Canonical only: `market_sources_poll_loop` (`app/tasks/market_sources_poll_task.py`) and the matching exclusion of market topics from the 15-minute collector (`collector_task.py:64-96`).
- Files that differ: `app/collectors/xpoz.py`, `app/collectors/thinkpol.py`, `app/tasks/propagation_detection_task.py`, `app/analyst/affiliation_tracking.py`, `app/analyst/article_lookup_service.py`, `app/analyst/propagation_routes.py`, `app/analyst/social_*.py`, `app/analyst/subject_monitoring.py`, `app/database/models.py` (391 changed lines), `app/workers/pipeline_worker.py` (the market loop only). None of them is in the curation path.
- Prod-only runtime facts: worker drop-ins enabling the topic classifier, inline tagging and relevance backfill; `TYPESAFE_SHADOW_RELEVANCE=1`; no `models/relevance_classifier` directory.

---

## 10. Open problems, in order of cost to the product

1. **The firehose import has been dead since 9 September** because `FIREHOSE_DSN` is unset on prod. Topic surfaces now depend almost entirely on analyst publish, RSS, arXiv and official sources. The daily check has been failing and emailing for weeks. Restoring it needs the new DSN in prod `.env`; the importer will then walk from `nf_4511749` forward.
2. **The topic classifier loop is stuck** on the same 50 articles and burns about $75 a week (estimate) of Llama 3.3 70B for about 3 tags a day. A skip set, as `relevance_backfill` already uses, would stop it. Its cost row in `ai_model_configs` uses Nova-lite prices, so the ledger understates it about twelvefold.
3. **Most imported articles never get a topic.** Even when the import ran, 88% of firehose rows stayed untagged, so they reached no topic reader.
4. **No reject outside the analyst pipeline.** RSS, arXiv and official-source articles join topics and brands without a relevance decision; only the newsfeed and public pages filter on `relevance_score >= 0.3`, and the MCP topic tool does not.
5. **Analyst run costs are misreported** (`estimated_cost_usd`): relevance scoring shows $0, classify shows Haiku prices.
6. **Three different dedup rules:** the firehose import uses an exact URL, the collector uses a normalised canonical URL plus aliases and GUIDs, and analyst publish uses an exact URL. The same story can therefore land twice in `articles` when URLs differ by tracking parameters.
7. **`resolve_mentions` is not in any prod step list**, so `entities_resolved` stays empty on prod analyst articles.
8. **Rejecting a published article does not un-publish it.**
9. **The Jev shadow is effectively idle**, because decision reuse leaves it no fresh pairs to judge.
