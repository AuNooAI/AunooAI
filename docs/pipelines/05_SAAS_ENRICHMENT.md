# SaaS enrichment pipeline: what gets computed on articles after they arrive

Written 2026-10-07 from a read-only pass over the canonical tree
`/home/orochford/tenants/bugfixing.aunoo.ai/saasmvp-app` (all file:line refs are relative to it),
checked against the prod tree `/home/orochford/tenants/saas.aunoo.ai` and the prod database
`aunoo_saas_prod`. Where docs and code disagree, this file follows the code.

**Prod vs canonical.** The enrichment files are byte-identical between the two trees:
the analyst pipeline runner and steps, `publishing.py`, the embedding, E5, ai_tells and novelty
tasks, the validation supervisor, trust signals, the collector pipeline and `app/ai/llm.py`.
Four files differ:
- `pipeline_worker.py`: canonical adds `market_sources_poll_loop`.
- `novelty_scorer.py`: canonical uses the B3 diversified sampler for theme proposal; prod uses a plain `DISTINCT ON` query.
- `propagation_detection_task.py`: only the docstring differs. Both trees use the 0.99 copy floor.
- `ml/classifier_service.py`: canonical adds the voice head; prod serves only sentiment and toxicity.

**Scope.** This file covers enrichment. Collection (the collectors, the NewsFirehose import, RSS) and
analyst curation (the `score_relevance` step, topic alignment, the topic classifier, relevance
backfill) belong to the other agent's notes. The hand-off points are marked **[HAND-OFF]**.

---

## 0. The shape of the whole thing

Articles reach the production `articles` table by three roads. Each road gets different enrichment,
and that difference explains most of the coverage gaps further down.

| Road | Writer | Enrichment it carries on arrival |
|---|---|---|
| A. NewsFirehose bulk import | `scripts/import_firehose_corpus.py` (hourly timer `saas-firehose-import.timer`, `--auto-watermark --limit 3000`) | DeBERTa vector copied from the firehose DB (`article_deberta_embeddings`), plus firehose's own `sentiment`, `sentiment_score`, `categories`, MBFC bias/factual/credibility, `ai_tag`, citations and creators. Only articles that already have a DeBERTa vector are imported (script docstring :1-5, query :434-450). |
| B. Collector pipeline (RSS, arXiv, SEC, official and market sources) | `app/collectors/pipeline.py` `CollectionPipeline` | MBFC by **feed** domain (:380-399, :1032-1041), `quality_score` heuristic (:136-169), `actor_id`, inline topic classification (:1125-1150, **[HAND-OFF]**). No sentiment, no summary, no citations. |
| C. Analyst pipeline publish | `app/analyst/publishing.py` `publish_to_production` | Copies the analyst-curated row: summary, sentiment label, categories, tags, MBFC fields, keywords, actor; extracts citations (:400-488). |

After arrival, worker loops add embeddings, novelty, AI-tell scans, coordination edges, story
clusters and the like. Readers (trust signals, foresight, highlights, briefings) then consume all of it.

### 0.1 Process topology

| Unit | Tree | Role | What runs |
|---|---|---|---|
| `saas.aunoo.ai.service` | prod | `WORKER_ROLE=web`, uvicorn 4 workers, :10017 | HTTP only. No loops (`app/core/app_factory.py:206-217`). |
| `saas-worker.service` | prod | `WORKER_ROLE=worker` | Every background loop (`app/workers/pipeline_worker.py:365-463`) except the skills jobs. Restarted every 4 h by `saas-worker-restart.timer` (00,04,…,20:17) to cap libtorch memory growth. |
| `saas-skills-worker.service` | prod | `WORKER_ROLE=skills` | Only `skills_jobs_loop`: validation and newsletter jobs (`pipeline_worker.py:355-363`). |
| `deberta-encoder.service` | `/opt/deberta-encoder` | shared by every Aunoo site | DeBERTa 768d encoder on :8001. |
| `saas-e5-encoder.service` | prod | | multilingual-E5 1024d encoder on :8002. |
| `saas-classifier.service` | prod | | Sentiment and toxicity heads on **:8013** (prod `.env` `CLASSIFIER_URL`). The staging copy `saasmvp-classifier` runs on :8012. |
| vLLM | host | | `microsoft/Phi-3-mini-4k-instruct` on :8765 (`VLLM_BASE_URL`). It was up when I checked. |
| `saas-story-cluster-shadow.timer` | **canonical tree script, prod DB** | | Daily 07:30, story clusters (Stage 12). |

Prod worker drop-ins set `TOPIC_CLASSIFIER_ENABLED=1`, `TOPIC_CLASSIFIER_INLINE=1` and
`RELEVANCE_BACKFILL_ENABLED=1`. Prod `.env` sets `RETRIEVAL_EMBEDDING=e5`,
`NTI_NARRATIVES_DISABLED=1`, `CASCADE_SWEEP_DISABLED=1`, `PROPAGATION_WATCH_DISABLED=1`,
`STORY_CLUSTERS_UI_ENABLED=1` and `TYPESAFE_SHADOW_RELEVANCE=1`.

**Rule for adding a loop:** register it in `pipeline_worker.py` AND in `app_factory.py`'s non-web
branch (`pipeline_worker.py:25-28`). The two lists have drifted. `app_factory` is missing about 20
loops, including `editorial_briefing_loop`, so single-process "all" mode never makes briefings.
`story_cluster_loop` exists only in `app_factory`, so in the deployed split it never runs
in-process, which is why the systemd timer exists.

---

## 1. Embeddings

There are two vector stores. They coexist on purpose and must never be mixed, because the
dimensions and the vector spaces differ.

### 1.1 DeBERTa 768d: `article_embeddings`

- **What it is.** Raw `microsoft/deberta-base`, not fine-tuned: the last hidden layer mean-pooled over
  non-padding tokens. Long text is chunked at 512 tokens and the chunk vectors are averaged
  (`/opt/deberta-encoder/ml/encoder.py:36-192`). The vectors are **not normalised** (norms around 19-20)
  and are strongly anisotropic: two random unrelated articles have a mean cosine of 0.903
  (`docs/EMBEDDING_ANISOTROPY_PLAN.md`). Every threshold below that uses DeBERTa is tuned to that
  skewed distribution. A global re-centring would break them.
- **Service.** `deberta-encoder.service`, `POST :8001/encode {title, description, content}` →
  `{embedding: [768]}`. HF offline mode, GPU.
- **Table.** `article_embeddings(id, article_id, embedding vector(768), model, created_at)`
  (`app/database/models.py:731-741`). `model` = `'deberta-base'`.
- **Writers.**
  1. The firehose import copies the vector that firehose already computed (Road A). This is the
     bulk of the corpus.
  2. `embedding_generation_loop` (`app/tasks/embedding_task.py:30-114`) catches everything else.
     - Timing: starts after 30 s; batches of 50 every 2 s while work exists, otherwise every 5 min.
     - Selection: the newest articles with no row, ordered by `collected_at DESC`, title required.
     - Text: `title + "\n" + LEFT(COALESCE(full_text, content), 4000)`, falling back to `summary`.
     - Call: `get_embedding()` (`app/ai/llm.py:1089-1133`). It splits on the first newline into
       title and content and POSTs to the encoder. **It raises if the encoder is down** and there is
       no OpenAI fallback, because every vector column is 768d. Each call is logged to
       `llm_usage_log` with use_case `embedding`, model `deberta-base`.
- **Who reads it.** Propagation copy detection (Stage 11), novelty scoring (Stage 9), emerging-topic
  assignment, spectrum and bias/sentiment narrative clustering (greedy, distance 0.03), brand
  monitoring, inferred source bias, polarization, the corroboration fallback, and
  `article_validator` (emerging-theme membership).
- **Live numbers.** About 2.19 M rows, 17 GB. Of the 28,264 articles collected in the last 7 days,
  every one has a DeBERTa row; 13 from the last 2 days were still pending.

### 1.2 multilingual-E5 1024d: `article_embeddings_ml`

- **What it is.** `intfloat/multilingual-e5-large`, L2-normalised, so cosine equals the dot product.
  E5 is asymmetric. Documents are stored with the `passage: ` prefix; searches must encode with
  `query: `. Using the wrong prefix degrades ranking quietly instead of failing.
- **Service.** `saas-e5-encoder.service`: `POST :8002/encode {texts, kind}`. Text is truncated at
  4,256 characters (`ml/e5_encoder_service.py`).
- **Table.** `article_embeddings_ml(article_id, embedding vector(1024), model_version, embedded_at)`
  (`models.py:764-789`). `model_version` = `intfloat/multilingual-e5-large`.
- **Writer.** `ml_embedding_backfill_loop` (`app/tasks/ml_embedding_task.py`).
  - Timing: starts after 45 s; batches of 16 (`ML_EMBED_SERVICE_BATCH`) every 1 s while work
    exists, otherwise every 5 min.
  - Order: the last 7 days first (`ML_EMBED_RECENT_WINDOW_DAYS`), then the older backlog with no
    `ORDER BY`, because sorting forced full materialisation.
  - Text: title plus body up to 4,000 characters, sent RAW. The service adds the prefix itself, so
    adding one here would double it.
  - `ML_EMBED_LOCAL_FALLBACK=1` reloads the model in-process. That path landed on CPU at about
    0.8 docs/s because vLLM holds about 17.4 GB of the 20 GB card. Through the service it runs
    about 26 docs/s (`ml_embedding_task.py:52-66`).
- **Query side.** `get_ml_embedding(text, kind="query")` (`llm.py:1171-1217`) checks for 1024d and
  raises otherwise. `embed_e5()` (`ml_embedding_task.py:147`) is the batch form.
- **Who reads it.** Semantic search when `RETRIEVAL_EMBEDDING=e5` (prod), validation corroboration,
  the NTI E5 gate (0.88), story clusters (0.88), cascade retrieval (0.84 article floor),
  cascade fingerprint (0.88), the relevance scorer (E5 weight 0.3) and the brand-monitoring centroid.
- **Live numbers.** About 2.19 M rows, 28 GB. 7-day coverage matches DeBERTa exactly.

### 1.3 The "E5 migration"

There was no swap. E5 was added beside DeBERTa as a second channel ("v2 Channel C") to catch
cross-language paraphrases and to work as a paraphrase gate on DeBERTa copy edges. Today:
- **DeBERTa** still produces near-copy candidates (cosine ≥ 0.99) and drives novelty, emerging topics, spectrum and brand monitoring.
- **E5** drives retrieval, corroboration, story clusters and cascade.

The memory note "gate on precision-of-delta, not volume" is about the copy channel; see Stage 11.

### 1.4 In-process vectors (never stored)

`sentence-transformers/all-MiniLM-L6-v2` (384d, CPU) runs inside the worker for KeyBERT (Stage 3c)
and for the relevance step **[HAND-OFF]**. These vectors are never written to pgvector
(`docs/DEBERTA_EMBEDDING_DIMS.md`).

---

## 2. The SLM classifier service (sentiment and toxicity heads)

- **What it is.** A small FastAPI service (`ml/classifier_service.py`) that serves two fine-tuned
  RoBERTa classifiers with calibrated probabilities:
  - Sentiment: `cardiffnlp/twitter-roberta-base-sentiment-latest`, returning positive, neutral and negative.
  - Toxicity: `cardiffnlp/twitter-roberta-base-offensive`, returning P(offensive).
  - Canonical only: a "voice" percentile head that compares a text against a precomputed reference set of replies in `models/voice_reference.json`.
- **Contract.** `POST /classify/sentiment {texts}` → `[{label, scores}]`; `POST /classify/toxicity`
  → `[{label, score}]`. Inputs are truncated at 512 characters. It runs on CPU with 2 threads
  (`CLASSIFIER_NUM_THREADS`). The OpenMP pins at :59-69 came from the 2026-07-22 incident where
  an idle torch service starved everyone else's inference.
- **What it classifies.** **Social posts, not news articles.** The callers are:
  - `app/social/slm_signals.py:26-57` `compute_slm_signals`. It samples 60 posts per account and
    aggregates them into mean sentiment probabilities plus toxicity mean and p90. The p90 feeds
    the account's hostility signal in the stance score.
  - `app/social/service.py:290-297`, the social profile.
  - `app/social/reddit_archive.py:375,750`, the Reddit discourse work.
- **Failure mode.** It degrades gracefully. `_classify` (`llm.py:1136-1168`) returns `None` and logs
  `status='error'` to `llm_usage_log` (use_cases `social_sentiment` / `social_toxicity`). The caller
  then falls back to the LLM's reading and tags the result with its source.
- **Gotcha.** Article `sentiment` does NOT come from this service. It comes from the LLM classify
  step or from firehose (Stage 3).

---

## 3. Per-article AI analysis: the analyst pipeline

This is where article-level LLM enrichment happens. It runs per **analyst topic**, not per article.

### 3.0 Trigger and orchestration

- `analyst_scheduler_loop` (`app/tasks/analyst_scheduler_task.py:54-67`) checks every 60 s for due
  schedules and inserts `analyst_pipeline_runs` rows with status `pending`.
- `analyst_executor_loop` (:108-136) claims pending runs every 5 s and runs at most
  `MAX_CONCURRENT_RUNS = 2` at once.
- `run_pipeline` (`app/analyst/pipeline/runner.py:63-387`) loads `analyst_topics.pipeline_config.steps`
  (default `DEFAULT_PIPELINE_STEPS`, `app/analyst/pipeline/base.py:126-134`). It runs each step in
  order and writes one `analyst_pipeline_step_logs` row per step (status, in/out counts, model,
  tokens, cost estimate, duration). It stamps a heartbeat between steps and calls `gc.collect()`.
- **Prod configuration.** All 22 active topics use
  `["collect","score_relevance","classify","summarize","extract_ner","enrich_mbfc"]`.
  **`resolve_mentions` is not in any prod topic's list**, so `analyst_articles.entities_resolved`
  is JSON `null` on all 69,267 rows from the last week.
- **Data flow.** Steps mutate a list of article dicts in memory (`PipelineContext.articles`). Only at
  the end does the runner insert every article into `analyst_articles` (:258-320), bucketed by topic
  alignment: ≥ threshold+0.1 is `confirmed`, ≤ threshold−0.1 is `rejected`, anything between (or
  unscored) is `pending`. The default threshold is 0.3 (:241-254). **[HAND-OFF]** to curation.
  If the run completed and the analyst topic is linked to a production topic, the runner then calls
  `publish_to_production` (:362-385; Stage 3.6).
- **Last 7 days on prod:** 292 runs (249 completed, 43 failed; 54 were auto-requeues).
  `collect` produced 100,838 articles. After curation, `analyst_articles` holds 18,098 confirmed,
  3,203 pending and 47,968 rejected rows.

### 3.1 Step `classify`: the ontology labels

- **File.** `app/analyst/pipeline/steps/classify.py`.
- **What it assigns.** One value each for `category`, `future_signal`, `sentiment`, `time_to_impact`,
  `driver_type`, `political_bias` and `factuality`, each with an `*_explanation` text field.
- **Allowed values.**
  - The first five come from the topic (`analyst_topics.categories`, `future_signals`,
    `sentiment_options`, `time_to_impact_options`, `driver_types`), with defaults at :191-198.
  - `political_bias` is one of Left-leaning, Center-left, Center, Center-right, Right-leaning, Mixed.
  - `factuality` is one of Very High, High, Mixed, Low, Very Low.
- **Prompt.** `SYSTEM_PROMPT` and `USER_PROMPT` at :34-89. Content is capped at 5,000 characters,
  taken from `content`, else `summary`, else `ai_summary`.
- **Model.** `get_completion(use_case="analyst_classify", temperature=0.1, max_tokens=1024)`. Prod
  `ai_model_configs` resolves that to **`bedrock/us.amazon.nova-lite-v1:0`**. A topic can override it
  with `pipeline_config.classify_model`.
- **Concurrency.** A semaphore of 8 over batches of 100, with a heartbeat per batch (:23-30, :307-319).
- **Skips.**
  - Articles already carrying `category` and `time_to_impact`.
  - Articles whose alignment is below `threshold − 0.1`, which are about to be auto-rejected.
    This saves tokens: 274 of 47,968 rejected rows have a category.
  - The whole step is skipped if the topic has no categories.
- **Validation.**
  - `_parse_json` strips code fences and finds the outermost `{…}`.
  - `_enforce_taxonomy` (:111-151) replaces an out-of-list `category` with "Other". Any other
    out-of-list field is dropped (left NULL) and logged.
  - A parse failure leaves the article unclassified. There is no retry beyond what `llm.py` does.
- **Output.** These columns exist on `analyst_articles` only. On publish, only `sentiment` (the label)
  reaches `articles`. **`political_bias`, `factuality`, `future_signal`, `time_to_impact` and
  `driver_type` never reach the production `articles` table.** `articles.bias` and
  `factual_reporting` come from MBFC instead (Stage 4).
- **Cost gotcha.** The step returns `model_used=None` because the model is resolved inside
  `get_completion`. The runner then prices its tokens at Haiku rates (`runner.py:52-60`): the step
  logs estimate **$74.94** for 7 days, while `llm_usage_log` shows the true Nova Lite cost of
  **$4.26** (28,080 calls).

### 3.2 Step `summarize`: topic-focused summary

- **File.** `app/analyst/pipeline/steps/summarize.py`.
- **Logic, per article** (sequential, heartbeat every 10):
  1. If an `ai_summary` already exists (usually firehose's) and `evaluate_existing_summaries` is on
     (the default), ask Phi-3 "sufficient or insufficient?" (`EVALUATE_PROMPT` :106-113). **If vLLM
     is down, it keeps the existing summary** (:246-248).
  2. Otherwise summarise with vLLM Phi-3-mini in 2-3 sentences focused on the topic (content up to
     3,000 characters, max_tokens 200; :64-93).
  3. If Phi-3 fails, fall back to `get_completion(model=summarize_model)` with **no `use_case`**,
     which means the default `article_analysis` use_case → Haiku 4.5 (content up to 4,000
     characters, max_tokens 256).
- **vLLM health.** Checked with a 60 s TTL cache (:33-61).
- **Output.** `ai_summary` and `ai_summary_model` (`vllm:microsoft/Phi-3-mini-4k-instruct`, or the
  model string).
- **Live.** Of the last week's analyst rows, 3,224 got a Phi-3 summary; the other ~66 k kept the
  existing summary. `article_analysis` logged 108 Haiku calls in 7 days, which are mostly these
  fallbacks and the NER fallbacks.
- **Publish handling.** `publishing.py:253-267` normalises the summary and drops degenerate ones
  (repetition loops from small models) before writing `articles.summary` with
  `summary_provenance='ai'`. The 7-day split on `articles` is 15,161 `ai`, 11,664 `feed`, 1,447 NULL.

### 3.3 Step `extract_ner`: keywords and entities

- **File.** `app/analyst/pipeline/steps/extract_ner.py`.
- **Per article:**
  1. If the article already has keywords AND entities (from firehose), skip it.
  2. If keywords are missing, run KeyBERT with MiniLM: n-grams of 1-3, MMR diversity 0.7, top 10,
     score ≥ 0.2 (:91-111).
  3. If entities are missing, run a "hybrid" Phi-3 call that takes the KeyBERT candidates and returns
     tags, people, organisations and locations (:142-183).
  4. If that fails, fall back to `get_completion(model=ner_model)` with the NER prompt (people,
     organisations, locations, events), again under the default use_case (Haiku).
- **Output.** `entities` JSONB `{people, organizations, locations[, events]}` and
  `extracted_keywords` (top 10).
- **Gotcha: event-loop blocking.** The hybrid path calls the **synchronous**
  `litellm.completion` inside async code (:167), which blocks the worker's event loop for each call.
  This is the slowest step: about 1,045 s average per run.
- **Gotcha: in-flight runs.** The step logs show 7 `extract_ner` rows stuck in `running`. Those are
  runs killed by the 4-hourly restart and then reaped.

### 3.4 Step `resolve_mentions` (built, not enabled on prod)

- **File.** `app/analyst/pipeline/steps/resolve_mentions.py`.
- **What it does.** Resolves each NER surface form to a Wikidata QID with
  `app.entities.service.resolve_mention_name`. It uses an in-run cache plus the Wikidata client's
  Redis cache (30-day TTL, 0.2 s between requests).
- **Output.** It writes `entities_resolved` as a flat JSONB list, which has a GIN index for `@>`
  queries. It also auto-creates shallow rows in the global `entities` table as `aunoo_admin`.
- **Prod status.** Not in any prod topic's step list (see 3.0), so none of this runs on prod.

### 3.5 Step `enrich_mbfc`

- **File.** `app/analyst/pipeline/steps/enrich_mbfc.py`.
- **Logic, by article URL domain:**
  1. Apply `analyst_source_overrides` for the topic. An `exclude` override removes the article from
     the run; a `credibility_override` replaces credibility.
  2. Keep MBFC fields if the article already has them (firehose pre-enriches most).
  3. Otherwise fill them from `load_mbfc_cache` (`app/services/mbfc_lookup.py:79`), which reads
     `mbfc_sources` and has NO inferred-bias fallback.
- **Output.** `mbfc_bias`, `mbfc_factual_reporting`, `mbfc_credibility`, `mbfc_country`, `mbfc_media_type`.

### 3.6 Custom steps

Analysts can define per-topic prompt steps in `analyst_custom_steps`
(`app/analyst/pipeline/steps/custom.py`). Each one formats a prompt template with the article's
fields, calls the LLM with the step's own model, and stores the parsed JSON in
`custom_enrichments[step_name]`. Custom steps run after the standard steps and only if none of
those failed.

### 3.7 Publish to production (`app/analyst/publishing.py`)

- **What gets published.** Only `confirmed` rows. Each article is handled in its own savepoint, and
  the code commits every `PUBLISH_COMMIT_BATCH` articles so it does not hold long row locks on
  `articles`. On 2026-08 those locks lasted over an hour.
- **Validation.** `validate_article` (`app/analyst/pipeline/evals.py`) can reject an article
  deterministically.
- **If the URL already exists in `articles`.** The topic id is appended, and these columns are filled
  only where they are NULL or empty: `sentiment_score`, `sentiment`, `factual_reporting`,
  `credibility_rating` and `bias` (:283-330). The summary is replaced only if
  `should_replace_summary` ranks the analyst summary higher (an `ai` summary outranks a `feed` one).
- **New article.** `INSERT INTO articles (…)` (:409-448) with this mapping:

  | `articles` column | Comes from |
  |---|---|
  | `bias` | `mbfc_bias` |
  | `factual_reporting` | `mbfc_factual_reporting` |
  | `credibility_rating` | `mbfc_credibility` |
  | `sentiment` | the classify label |
  | `sentiment_score` | the firehose score; classify does not produce one |
  | `categories` | the upstream list; classify's single `category` is NOT copied |
  | `tags` and `ai_tag` | `tags` (first element) |
  | `keywords` | extracted keywords |
  | `actor_id` | `attach_actor_from_ingest` |

- **After insert.** Citation extraction (`app/detection/citations.py` `extract_citations`) runs and
  writes to `article_citations`.

**Gotcha: sentiment scores.** `articles.sentiment_score` was NULL on all 28,264 articles collected in
the last 7 days. The classify step does not produce a score, and recent firehose rows carry none.
Consumers that need a number fall back to mapping the label (`app/foresight/series.py:37-134`
uses positive=1, negative=−1, neutral and mixed=0).

**Live 7-day coverage on `articles`.**

| Field | Articles with it (of 28,264) |
|---|---|
| sentiment label | 15,806 |
| bias | 14,211 |
| factual_reporting | 11,903 |
| ai_tells | 10,367 |
| actor_id | 28,244 |
| topic_ids | 27,811 |
| relevance_score | 25,694 |

**Gotcha: bias labels are not normalised.** The values include both `least biased` (2,140) and
`least-biased` (1,391), alongside `left-center`, `right-center`, `center`, `questionable` and
`right`. Any reader that groups by `bias` needs to normalise first.

### 3.8 The dead analyzer

`app/analyzers/article_analyzer.py` (`analyze_article` / `batch_analyze`, use_case
`article_analysis`, returning sentiment, sentiment_score, categories, tags and summary) has **no
callers** in `app/`. It is a leftover from the monolith port. Do not rebuild from it.
`app/analyzers/sentiment_filter.py` is live: it is a SQL helper that overlays the curated
`analyst_articles` sentiment label onto readers by URL (`sentiment_canonical_sql_filter`).

---

## 4. Source credibility: MBFC, inferred bias and ownership

### 4.1 MBFC data (`mbfc_sources`, 8,211 rows)

- **Columns.** `normalized_domain` (unique), `mbfc_*`, `idiap_*`, `canonical_bias`,
  `canonical_factual_reporting`, `canonical_credibility`, `canonical_source`, `rationale`,
  `needs_review`, `media_type`, `country`, `deleted_at` (`models.py:5831`). Every change is written
  to `mbfc_source_audit_log`.
- **Loaded by hand-run scripts.**
  - `scripts/import_mbfc_csv.py` reads `data/mbfc_raw.csv`.
  - `scripts/import_idiap_dataset.py` and `sync_idiap.sh` load the Idiap dataset and set
    `needs_review` when the left/right reading disagrees with MBFC.
  - `seed_satire_sources.py` and `merge_mbfc_sources.py`.
  - Analysts can also edit rows at `/api/v1/analyst/mbfc` (`app/analyst/mbfc_routes.py`).
- **`lookup_mbfc`** (`app/services/mbfc_lookup.py:38-76`) returns the canonical value, else the MBFC
  value, per field. It then falls back to `source_bias_inferred`, which supplies bias only.
  - **Gotcha:** a row that has factuality but no bias value is skipped entirely.

### 4.2 When bias is attached to an article

| Road | When | Keyed on |
|---|---|---|
| A, firehose | at import | firehose's own MBFC |
| B, collector | at insert, new rows only | **the RSS feed's domain**, not the article's. An aggregator feed such as Google News stamps its own rating on every article it carries. |
| C, analyst | at publish, from `enrich_mbfc` | the article URL's domain |
| read time | when the column is NULL | `app/public/queries.py:276-307` (`resolve_mbfc`) and the newsfeed routes fill gaps |

The article columns are a snapshot. A later MBFC edit does not update rows that already have a
value, and the stored column wins over a fresher `mbfc_sources` value.

### 4.3 Inferred bias (`source_bias_inferred`)

- **Loop.** `source_bias_inference_loop` (`app/tasks/source_bias_inference_task.py`) wraps
  `scripts/infer_source_bias.py`. It runs once 60 s after start if it has never run, then every
  7 days. `POST /analyst/mbfc/inference/run` triggers it manually through a Redis key.
- **Algorithm `knn-v1` (no LLM).**
  - Candidates: domains with ≥ 5 articles in 90 days and no canonical bias.
  - For up to 30 recent articles per domain, take the 10 nearest DeBERTa neighbours among articles
    from rated sources.
  - Vote across five buckets (left, left-center, center, right-center, right).
  - Confidence = winning votes ÷ total votes.
- **Gotchas.**
  - `inferred_factual_reporting` is never written.
  - The kNN is an unindexed cross-join over all rated articles from 90 days.
  - There is no leader lock. If the web role were not `web`, this loop would run twice.

### 4.4 Ownership and entity graph (computed when read, not stored per article)

- **Domain to entity.** `app/entities/resolver.py` searches Wikidata from the MBFC display name and
  scores candidates: name 0.40, official website (P856) 0.25, type 0.15, country 0.10,
  prominence 0.10.
  - An exact P856 match, or a score ≥ 0.85, gives `auto`.
  - 0.60-0.85 gives `ambiguous` if there are rival candidates, otherwise `auto`.
  - Below 0.60 gives `unresolved`.
- **Persistence.** `app/entities/service.py:464-558` writes `entities`, `source_entity_map` and the
  ownership edges in `entity_relationships`, seeded from Wikidata properties P127, P749, P1830, P488,
  P169, P112, P463 and P1019.
- **No loop resolves domains.** Resolution runs only through
  `POST /analyst/entities/source-entity-map/{domain}/reenrich` or the
  `scripts/resolve_all_domains.py` and `resolve_propagation_domains.py` scripts.
- **Actor sync.** `author_resolver_loop` (`app/actors/resolver_job.py`, every 6 h) copies
  `source_entity_map.entity_id` to `actors.entity_id` and resolves person authors.
  `actors.ultimate_parent_entity_id` is set only by `scripts/backfill_ultimate_parent.py`, so it goes
  stale. That column is the independence key that corroboration uses (Stage 6).
- **Ownership walk at read time.** Two implementations exist and they can disagree on the ultimate owner:
  - `app/newsfeed/ownership.py:307` `resolve_ownership` ranks parent edges by source
    (analyst_confirmed > wikidata_p127 > analyst), then confidence; walks to depth < 4.
  - `app/entities/ownership.py:29-92` uses no source rank and walks to depth < 5.
- **State media and syndicators.** `state_affiliated_domains` and `syndicator_domains` are curated
  lists with a 5-minute in-process cache.
- **Domain intel.** `domain_intel_refresh_loop` (every 24 h) refreshes the newly-registered-domain
  feed into `nrd_observations`. It then scores unresolved or ambiguous domains for typosquatting, a
  random-looking-name (DGA) score and TLD risk, and writes `domain_intel`. Only the analyst entity
  console reads it. It is not per article.

---

## 5. AI-authorship tells (`articles.ai_tells`)

- **Loop.** `ai_tells_loop` (`app/tasks/ai_tells_task.py`). Starts after 45 s; batches of 50 every
  5 s while work exists, otherwise every 600 s.
- **Selection.** `source IN ('rss','arxiv') AND ai_tells IS NULL` with a body present (:92-105). Most
  firehose rows have a domain as their `source`, so **the loop covers only collector rows**: 10,367 of
  28,264 articles in the last 7 days.
- **Stage A, heuristics (no LLM).** `scan_text` (`app/services/ai_tells/detector.py:773-801`) applies
  regex rules from the `ai_tell_detectors` and `ai_tell_patterns` tables to the first 12 k characters.
  It produces counts per 100 words, a severity-weighted rate, the number of distinct structural
  tells, readability and an em-dash count.
- **Stage B, LLM verdict.** It runs when the weighted rate is ≥ 1.5 per 100 words or there are ≥ 3
  structural tells; thresholds live in `module_configs.ai_tells_detection`. The call is
  `use_case="ai_tells_verdict"` (Haiku 4.5), temperature 0, max_tokens 100, on a 500-character excerpt.
  Labels are `ai`, `likely ai`, `unclear`, `likely human` and `human`, each with a confidence and a
  reason. 194 calls in 7 days.
- **Output.** `articles.ai_tells` = `{tells, stats, verdict, scanned_at, rules_version}`.
- **On demand.** `POST /articles/{id}/ai-tells` runs the heuristics only. Once a row is stored the
  loop never revisits it, so on-demand rows never get an LLM verdict.
- **Doc vs code.** `docs/TRUST_SIGNALS.md` uses the label `ambiguous` and says 3+ structural tells
  short-circuit to "likely ai". The code uses `unclear` and sends those articles to the LLM instead.

---

## 6. Trust Signals and validation

### 6.1 Trust Signals: five "stations", computed when read

- **Code.** The renderer is `app/public/trust_signals.py`. The MCP tools are `get_trust_signals` and
  `get_trust_signals_for_urls` (`app/auspex/trust_tools.py:88,264`, at most 25 items per call, window
  1-720 h, default 72). They are also embedded in `get_article_full` with a 5 s budget.
- **Nothing is stored as a trust-signal row, and nothing combines the stations into one score.**

| Station | Input | Stored or live | Rule |
|---|---|---|---|
| ① Source | `articles.factual_reporting` / `credibility_rating`, else `resolve_mbfc` | stored column, read-time fill for gaps | High → pass; mixed or medium → warn; low → fail; else Unrated |
| ② Claims | newest completed `validation_runs` row | stored run | `non_independent` → Syndicated. Otherwise any contested claim → fail, all supported → pass, a mix → warn. With no run, use the provenance count: ≥ 2 → Corroborated, 1 → Single source. |
| ③ Origin | `articles.ai_tells` | stored | verdict label; with no verdict, ≥ 5 tells per 100 words or ≥ 3 structural → warn |
| ④ Spread | `coordination_events` partners within the window (`app/newsfeed/provenance.py:423-483`) | live | ≥ 4 partners with ≥ 50 % under one owner → warn "Concentrated" |
| ⑤ Owner | `resolve_ownership` | live | owner known → pass, else Unmapped |

- **Doc vs code.**
  - The doc gives a 0.92 copy floor; the code uses `MIN_COPY_SIMILARITY = 0.99` (`app/detection/__init__.py:31`).
  - The doc describes a combined verdict ladder that does not exist.
  - The Spread window filters on detection time, not on publish time.

### 6.2 Article validation and corroboration: on demand only

- **Triggers.**
  - The analyst UI: `POST /api/v1/analyst/article-validation/validate`. It is gated by
    `ARTICLE_VALIDATION_ENABLED` (default False) and returns 404 when off.
  - The MCP tools `validate_article` (inline, about a 25 s budget) and `start_validation_job`
    (queues a `skills_jobs` row that the skills worker polls every 5 s; up to 3 jobs at once,
    20-minute timeout).
  - Nothing validates articles on a schedule. The Monday 08:00 UTC weekly digest only emails a
    summary of past runs.
- **Pipeline** (`app/services/article_validation/supervisor.py:356-830`):
  1. **Coordination context.** Resolve the article from the corpus or fetch it live, then roll up its
     `coordination_events`. An unresolved article ends as `unverifiable_input`.
  2. **Cache check.** The key is a SHA-256 of the normalised title and body plus the prompt versions
     (claim extraction v2.0, verify v1.2). The cache is global across tenants.
  3. **Monthly quota.** Per tenant, from the plan features. Going over returns HTTP 402.
  4. **Source reputation, then corroboration** (these run one after the other, not in parallel).
     - Reputation: the MBFC factual score plus a credibility bump.
     - Corroboration: an E5 k-nearest-neighbour search over ±30 days of publish date. It
       over-fetches 4 × 8 candidates, drops known copies and near-identical text (pg_trgm ≥ 0.85),
       dedupes by the ultimate parent owner, then reranks with a cross-encoder. **There is no
       minimum similarity.** The DeBERTa table is a fallback only when the pool is short.
  5. **Claim extraction and verification** with Haiku 4.5, **hardcoded** at
     `agents/claim_verification.py:65` rather than routed through `ai_model_configs`. At most
     8 claims; body capped at 4,000 characters.
  6. **External fact-check adapters**: Google Fact Check, ClaimBuster, FullFact, Wikipedia,
     Wikidata, Semantic Scholar, SEC, CourtListener, Regulations.gov, Crossref, OpenAlex, Firecrawl,
     BrightData and Tavily. Their keys live Fernet-encrypted in `PlatformValidatorKey`.
  7. **Web evidence grader**, only when the tenant has `module_web_verification`.
  8. **Rule-based verdict** (`_synthesise_verdict` :182-295, first match wins): `unverifiable_input`,
     `satire`, `contested`, `non_independent`, `single_source`, `corroborated`,
     `no_verifiable_claims`, `partial`.
- **Writes.** `validation_runs` (global, no tenant id), `validation_claims`, `validation_run_requests`
  (tenant-scoped audit), `skills_jobs`, plus a notification.
- **Gotchas.**
  - A cache hit recomputes the verdict for the response but does not update `verdict` and
    `confidence` on the stored row. Station ② therefore shows the original verdict.
  - `_VERDICT_VALUES` omits `satire` and `no_verifiable_claims`.
- **Doc vs code.** `ARTICLE_VALIDATION_AGENT_PLAN.md` is stale on the verdict names (it still says
  `likely_coordinated`), on the parallel agents, on the lexical threshold (0.45 in the doc, 0.85 in
  code) and on the window (7 days in the doc, ±30 in code).

### 6.3 Citations (`article_citations`, about 3.2 M rows)

- **What it extracts.** Regex only (`app/detection/citations.py:282-363`): `url`, `cited_domain`,
  `quote` (≥ 8 words) and `wire_credit` (agency credits in the dateline or footer). Caps: 50 URLs,
  20 quotes. Unique on (article_id, kind, value).
- **Writers.** The firehose import (Road A) and analyst publish (Road C).
  **The collector pipeline (Road B) never extracts citations.** RSS-ingested articles are therefore
  invisible to the shared-citation coordination channel and, through it, to Spread.

### 6.4 Paper enrichment (arXiv rows)

- **Loop.** `paper_enrichment_loop` (`app/tasks/paper_enrichment_task.py`; leader lock; every 30 min,
  at most 120 rows per tick).
- **Source.** The Semantic Scholar Graph API: citation counts, TLDR, open-access PDF, references and
  citations. Requests go through a shared host-wide quota ledger, and a 429 pauses the key.
- **Writes.** `paper_enrichment`, refreshed after 7 days (3 days for a paper not found).

---

## 7. Novelty and emerging topics

### 7.1 Novelty scores (per article, daily)

- **Loop.** `novelty_scoring_loop` (`app/tasks/novelty_task.py`). Starts after 60 s; batches of 100
  every 5 s while work exists, otherwise every 6 h.
- **Selection.** Articles from the last 14 days that have a DeBERTa row and no score for today. An
  article is therefore re-scored once a day for 14 days. 93,028 scores were written across today and
  yesterday.
- **Scorer.** `app/emerging/novelty_scorer.py`. Three signals, combined with weights:

  | Signal | Weight |
  |---|---|
  | k-nearest-neighbour distance (k = 10) on DeBERTa | 0.6154 |
  | local density | 0.0, zeroed 2026-08-10 |
  | distance to active emerging-topic centroids | 0.3846 |

  The baseline is 500 sampled articles from 30 days, cached for 6 h. An article scoring ≥ 75 is
  flagged as an outlier.
- **Writes.** `article_novelty_scores`. A shadow v2 score (percentiles within source-type and
  language strata) goes to `article_novelty_scores_v2`, which nothing reads.

### 7.2 Emerging topics (over the corpus, not per article)

- **Loop.** `emerging_topics_loop` wakes every 60 s and reads `emerging_topics_settings`. On prod
  that row has `schedule_enabled=true`, a full run every 4 h, trend refresh every 120 min and alerts
  every 60 min. A stage-3 refresh also runs every 60 min.
- **Seven stages** (`app/emerging/service.py:45-128`):
  1. Novelty baseline.
  2. Theme proposal by LLM: use_case `emerging_topics`, Sonnet 4.5, over up to 1,500 high-novelty articles.
  3. pgvector assignment of articles to themes on DeBERTa (threshold 0.15).
  4. Coherence checks and dedup. (Stage 3.5, `article_validator`, sits between assignment and this step.)
  5. Deep analysis: use_case `deep_analysis`, Sonnet 4.5.
  6. Trend scoring.
  7. Save, urgency, anomaly z-score, and the mature/retire/re-emerge lifecycle.
- **Writes.** `emerging_topics` (with a 768d centroid), `topic_history`, `detection_runs`.
- **`ingest_spike_loop`** (every 30 min) runs a detection scoped to one topic when the topic's 24 h
  count is ≥ 5 and ≥ 1.5 × its prior daily average. Cooldown is 2 h after an empty run and 24 h after
  a productive one.
- **Cost.** $22.04 for 47 calls in the last 7 days.
- **Doc vs code** (`docs/EMERGING_TOPICS_SYSTEM.md`):
  - The doc says the full run is every 24 h; the code default and prod setting are 4 h.
  - The doc's novelty weights (0.40 / 0.35 / 0.25, 100-article baseline) are stale.
  - The doc gives the spike cooldown as a flat 2 h.
  - The doc omits the stage-3 refresh.
  - The doc names `saasmvp-worker.service` as the host; the prod host is `saas-worker.service`.

---

## 8. Topic tagging and related per-article taggers [HAND-OFF to curation notes]

These write per-article fields but belong to curation. They are listed so the two notes connect.

| Loop | Writes | Model and cost (7 days) |
|---|---|---|
| `topic_classifier_loop`, every 5 min, articles ≤ 7 days old with no `topic_ids` | `articles.topic_ids` | `topic_classifier` = Llama 3.3 70B on Bedrock; 84,139 calls, $6.32 |
| `relevance_backfill_loop` | `articles.relevance_score` | `relevance_score` = Nova Lite |
| `rss_auto_tag_loop`, every 5 min, at most 100 calls per tick | `tenant_article_state.tags`, chosen from the tenant's own tag list | `rss_autocategorize` = Haiku 4.5; **43,875 calls, $40.32**, the second-largest line in the ledger |
| `threatintel_processing_loop`, hourly | `threat_intel_threats`, `threat_intel_articles` | `threat_extraction` = Haiku |
| `geohotspots_processing_loop`, every 30 min | `hotspot_articles`, `geopolitical_hotspots` | a local DeBERTa classifier for category and risk, plus `geohotspots` = Haiku for the location |
| `brand_monitoring_loop`, hourly | `bm_article_categories` and related tables | no LLM: keywords plus DeBERTa similarity, with an optional E5 gate |
| `agent_monitor_loop`, every 30 s | `agent_results`, `agent_briefs`, and a `SIGNAL_<name>` entry appended to `articles.tags` | `agent_execution` = Haiku |

---

## 9. Coordination, propagation and affiliation

### 9.1 Coordination edges (`coordination_events`), daily

- **Loop.** `propagation_detection_loop` (`app/tasks/propagation_detection_task.py`). Starts after
  90 s, runs every 24 h, looks back 25 h. Gate: `PROPAGATION_DETECTION_DISABLED`.
- **Stage 1, copies.** A DeBERTa self-join with these conditions:
  - cosine ≥ 0.99 (`COPY_DISTANCE_MAX` = 0.01; it was 0.92 until 2026-08-04)
  - published ≤ 24 h apart
  - different actors AND different outlet domains
  - at least 2 shared title tokens of 4+ characters
- **Stage 2, shared citations.** At least 2 shared `article_citations` tuples within 24 h,
  excluding `wire_credit`.
- **Writes.** `coordination_events(coordination_style ∈ {copy, shared_citation}, source_a, source_b, similarity, detected_at, …)`,
  capped at 50 k new rows per stage. No LLM.
- **Live.** 11,813 copy and 7,661 shared-citation events in 7 days; the minimum copy similarity is 0.990.
- **Dependency.** An article with no `actor_id` is invisible to detection. `actor_backfill_loop`
  repairs missing actors.

### 9.2 Built on top of the edges

- **Affiliation** (`app/analyst/affiliation_tracking.py`, daily, first run after 30 min). Louvain
  clustering over outlet pairs → `outlet_affiliation` and `affiliation_runs`. Then an LLM review
  (`affiliation_report`, Sonnet), alerts, and a TypeSafe/Jev shadow (`affiliation_path_shadow`).
- **Social tracking and amplification** (daily). `social_account_edges`, `social_amplification`,
  booster pairs.
- **Propagation watch.** Disabled on prod (`PROPAGATION_WATCH_DISABLED=1`).
- **Read time.** `propagation_clusters.py` and `propagation_summary.py` compute over the edges when
  read and store nothing.

---

## 10. Narratives (NTI), story clusters, cascade

### 10.1 NTI narrative clustering: retired, code still present

`nti_narratives_loop` uses `coordination_events` edges that pass an E5 ≥ 0.88 gate, Louvain
clustering (resolution 8, communities of ≥ 4 articles from ≥ 3 sources), and Nova Lite labels. It
writes `nti_narratives` and `nti_narrative_articles`. **Prod disables it** with
`NTI_NARRATIVES_DISABLED=1`, and the UI shows a "retired" notice. Step R4 of the retirement plan
(removing the code) has not happened. `cascade_sweep_loop` depends on NTI rows and is also disabled.

`docs/NTI_NARRATIVE_CLUSTERING_SPEC.md` approach B (ride the coordination edges and verify with E5)
matches what was built.

### 10.2 Story clusters (the NTI replacement), daily 07:30

- **Trigger.** `saas-story-cluster-shadow.timer` runs the **canonical tree's**
  `scripts/story_cluster_shadow_run.py` against the **prod DB** over port 5432. The in-process
  `story_cluster_loop` is never started in the deployed split.
- **Algorithm** (`app/tasks/story_cluster_task.py`, "louvain-e5-v1", no LLM):
  - Edges: coordination edges from the last 7 days (copies only at ≥ 0.99) that also pass E5 ≥ 0.88.
  - Louvain clustering; keep clusters of ≥ 4 members across ≥ 3 domains.
  - Pairwise evidence for clusters of ≤ 20 members, classified as owner, wire, state, syndication or residual.
  - Lineage: Jaccard ≥ 0.5 against the previous run counts as a continuation.
- **Writes.** `story_cluster_runs`, `story_clusters`, `story_cluster_memberships`,
  `story_cluster_pair_evidence`, `story_cluster_lineage`. It keeps the latest 45 runs. The last run
  was 2026-10-07 07:30.
- **Read surface.** `story_cluster_routes.py`, behind `STORY_CLUSTERS_UI_ENABLED`.

### 10.3 Cascade scan: analyst-triggered

`POST /analyst/propagation/cascade-detect/stream` runs:
- E5 k-nearest-neighbour retrieval (article floor 0.84)
- a cross-encoder rerank
- Nova Lite stance and verdict calls (`influence_cascade_stance` / `_verdict`)
- Sonnet 4 for the claim gate and the claim queries

Results persist to `influence_cascade_scans`. `docs/CASCADE_SCAN_HOW_IT_WORKS.md` matches the code.
The stance shadow (`TYPESAFE_SHADOW_STANCE`) writes `stance_shadow`, which nothing reads.

### 10.4 Spectrum and narrative drafts (over the corpus, cached)

| Loop | Cadence | What it does | Writes |
|---|---|---|---|
| `spectrum_pregenerate_loop` and `sentiment_spectrum_pregenerate_loop` | every 6 h, leader-locked | Greedy DeBERTa clustering (distance 0.03), bucketed by MBFC or inferred bias, or by sentiment. Haiku for themes and rerank, Sonnet for the summary. | `analysis_cache` `story_spectrum:v7:…` |
| `bias_narratives_loop` | daily | Sides left, center, right, smart and fringe; LLM `bias_narrative` | a draft into `narrative_drafts` |
| `sentiment_narratives_loop` | daily | Sides positive, negative and polarized; LLM `sentiment_narrative` | a draft into `narrative_drafts` |
| `bias_cluster` drafts (from spectrum) | with spectrum | per-cluster editorial draft | a draft into `narrative_drafts` |
| `editor_review_loop` | every 5 s | Reviews pending drafts with `editor_review` (Sonnet, max_tokens 400) | publishes into `bias_narratives`, `sentiment_narratives`, `bias_cluster_narratives` or `editorial_briefings` |

---

## 11. Products that consume enriched articles

All of these run in `saas-worker`. Most write to `analysis_cache` (JSON with a TTL).

| Product | Trigger | Model (use_case) | Reads | Writes |
|---|---|---|---|---|
| Highlights / incidents (`app/newsfeed/highlights_service.py`) | `newsfeed_generation_loop`, every 30 min, generation hour 04 UTC, per tenant | `incident_tracking` = Haiku, max_tokens 8192; **$30.93 for 7 days** | articles with sentiment and categories, credibility, bias, summary, a timeline block | `incidents_v2_{tenant}_{topic}_{days}`, 24 h |
| Narratives (themes) (`narratives_service.py`) | same loop, shared across tenants | `narrative_insights` = Sonnet 4.5 | 30 articles plus the sentiment overlay | `narratives_{topic}_{days}`, 24 h |
| Consensus (`consensus_service.py`) | `foresight_generation_loop`, every 30 min with daily/weekly/monthly guards | `consensus` = Sonnet 4.5, max_tokens 6000 | up to 75 articles, ≥ 5 required; sentiment, source, bias | `consensus_v3_…`; `foresight_runs` |
| Horizons (`horizons_service.py`) | same | `horizons` = Sonnet 4.5, max_tokens 6500 | articles, categories, timeline | `horizons_v2_…` |
| Timeline (`app/tasks/timeline_task.py`) | every 30 min; daily extraction 05 UTC, weekly Monday 06, monthly on the 1st at 07 | extraction uses no LLM; rollups, entity wikis and state docs use `summarization` = Nova Pro | articles, incidents cache | `topic_events`, `topic_event_runs`, `entity_wiki_pages`, `topic_state_docs` |
| Editorial briefings (`app/briefings/editor_service.py`) | `editorial_briefing_loop`, 60 s tick, 900 s per tenant; also after each agent brief | `editorial_synthesis` / `_correction` = Sonnet 4.5; **the largest spend, $57.62 + $27.68 for 7 days** | latest `agent_briefs`, articles (600 characters each), world-state block | `editorial_briefing_runs`, a draft, then `editorial_briefings` |
| Trajectory, series, sentiment, polarization (`app/foresight/*`) | on demand from Auspex/MCP | none | `articles`, DeBERTa | nothing |

**Gotcha: timeline cache key.** The timeline extractor reads `incidents_{topic}_7`, a key nothing
writes any more. It falls back to a `LIKE 'incidents_%_{topic}_7'` query with no `ORDER BY`. That
query picks an arbitrary tenant's incidents, and because `_` is a LIKE wildcard it can also match
another topic id.

`app/world_state/builder.py` is not an article consumer: it renders curated `world_state_facts`.

---

## 12. LLM routing, model tiers and the cost ledger

### 12.1 Routing (`app/ai/llm.py`)

- **No proxy.** There is no litellm proxy, YAML config or alias list in the saas tree. Each call goes
  directly to `litellm.acompletion` with the model string `f"{provider}/{model_name}"`.
- **Resolution.** `get_completion(prompt, model=None, use_case="article_analysis", …)` (:616) looks
  up the `ai_model_configs` row where `use_case=?` and `is_default=true` (:120-159).
  - The lookup has no `ORDER BY`, so if a use_case has two defaults the pick is arbitrary.
  - Results are cached in-process for 60 s, including "no row" results.
  - The row's `parameters.temperature` and `max_tokens` override the caller's values.
  - With no row, the call uses `DEFAULT_CHAT_MODEL` = Haiku 4.5. The `.env` value for that setting
    is **ignored** because `Settings` does not declare the field.
- **Tiers.** There is no tier column. The admin display derives a "tier" from the model name:
  Sonnet or Opus → reasoning, Haiku or Nova → bulk, local → local. "Plan tiers" control features,
  not models. The one tenant-level swap is `sonnet_upgrade`: Haiku → a configured model when the
  tenant has the `sonnet_model` feature. It needs a request context, so it **never applies to
  background loops**. Prod has no `sonnet_upgrade` row.
- **Prod model map for enrichment** (from `ai_model_configs`):

  | use_case | Model |
  |---|---|
  | `analyst_classify`, `analyst_relevance_score`, `relevance_score`, cascade stance/verdict | Nova Lite |
  | `summarization`, `relevance_label_teacher` | Nova Pro |
  | `article_analysis` (the default use_case), `ai_tells_verdict`, `rss_autocategorize`, `incident_tracking`, `geohotspots`, `threat_extraction`, `agent_execution` | Haiku 4.5 |
  | `topic_classifier` | Llama 3.3 70B |
  | `emerging_topics`, `deep_analysis`, `consensus`, `horizons`, `editorial_synthesis`, `editor_review`, narratives, spectrum summary | Sonnet 4.5 |
  | cascade claim gate and queries, newsletter | Sonnet 4 (EOL on Bedrock 2026-10-14) |
  | `fallback` | `mistral.mistral-large-3-675b-instruct` |
  | `embedding` | `local/deberta-base` |

- **Hardcoded models that bypass the table.**
  - Validation claims: Haiku 4.5.
  - NTI labels: Nova Lite.
  - Summarize and NER: Phi-3 on vLLM.
  - KeyBERT: MiniLM.

### 12.2 Cost ledger: `llm_usage_log` (about 6.2 M rows)

- **Columns.** `tenant_id`, `user_id`, `use_case`, `model`, `provider`, prompt/completion/total
  tokens, `cost_usd` (NULL means no price was found), `latency_ms`, `status`, `error_message`,
  `created_at`.
- **Writer.** `_log_usage` (`llm.py:504-582`) is awaited inline after every call; there is no
  litellm callback. Price comes from the `ai_model_configs` row for that model name (cached 300 s).
  Embedding and classifier calls are logged too, with token counts estimated as length ÷ 4.
  TypeSafe/Jev calls are logged by `app/ai/typesafe_client.py` at $0.042 per million input tokens.
- **Status values.** `success`, `fallback_triggered`, `fallback_suppressed`, `fallback_unavailable`,
  `rejected_content_filter`, `rejected_degenerate`, `success_cloud_rescue`, `error`.
- **Gotcha: no tenant id.** `tenant_id` is NULL for all background spend, because the tenant
  contextvar is set only by the HTTP middleware.
- **Gotcha: two cost numbers.** `analyst_pipeline_step_logs.cost_usd` is an estimate that falls back
  to Haiku prices; treat the ledger as the truth.
- **Top 7-day spend.**

  | use_case | Cost |
  |---|---|
  | editorial_synthesis | $57.62 |
  | rss_autocategorize | $40.32 |
  | incident_tracking | $30.93 |
  | editorial_synthesis_correction | $27.68 |
  | emerging_topics | $22.04 |
  | editor_review | $19.70 |
  | consensus | $14.51 |
  | summarization | $10.40 |
  | horizons | $10.04 |
  | agent_execution | $9.68 |

  The bulk article-level LLM work is cheap: `analyst_relevance_score` $6.59, `topic_classifier`
  $6.32 and `analyst_classify` $4.26.

---

## 13. Failure handling and retries

### 13.1 LLM calls (`llm.py`)

- **Rate limits.** A Bedrock 429 is retried on the same model after 5, 15 and 30 s (4 attempts,
  :323-365).
- **Fallback.** Only on `RateLimitError`, `AuthenticationError` or `APIConnectionError` does the call
  switch to the `fallback` use_case's model, once (:368-501).
- **Server errors and timeouts.** Bedrock 500/503 and timeouts get **no retry and no fallback**,
  because those exceptions are not subclasses of the three above (BUG-24 in
  `docs/SAAS_LOG_MONITOR.md`). The note in that doc saying a config entry would fix it is wrong;
  the fix needs code.
- **Timeouts.** No timeout is passed to litellm, so its default applies (6,000 s). The encoders and
  classifier use 30 s httpx timeouts.
- **Output gates.**
  - A content-filter refusal raises `ValueError`.
  - Degenerate repetition in a non-JSON reply is retried once at temperature + 0.3.
  - A reply cut off at `finish_reason="length"` only logs a warning.

### 13.2 Per step and per loop

- **Analyst steps.** An exception in any standard step marks the run failed and stops the remaining
  steps. Inside a step, one article's LLM failure is caught and that article is left unenriched.
  Parse failures are not retried.
- **Encoders.** `get_embedding` raises when the encoder is down. The embedding loop logs per article
  and moves on; the article stays without a row and is picked up on the next pass.
- **Classifier.** Social SLM calls degrade to `None` and fall back to the LLM's reading.
- **vLLM.** Steps re-check its health every 60 s and fall back to Bedrock (Haiku) when it is down.
  The summary sufficiency check defaults to "keep" when vLLM cannot answer.

### 13.3 Hung or orphaned work

- **Boot reaper** (`pipeline_worker.py:98-235`, scoped by role).
  - Analyst runs left `running` are failed, and a fresh `pending` run is queued with
    `trigger_type='auto_requeue'`.
  - Threat-intel runs left running are failed.
  - Skills jobs are failed and **not** requeued, because they are user-initiated and Bedrock-expensive.
- **Stale-heartbeat reaper** (`analyst_scheduler_task.py:220-303`). Every 60 s it fails any run whose
  `last_heartbeat_at` is more than 15 min old, then requeues it.
- **Threat-intel reaper.** Every 60 s it fails runs whose `processed` counter has not moved for 10 min.
- **Restarts.** The 4-hourly worker restart produces most of the reaped runs: 29 `(orphaned)` and
  5 `(stale heartbeat)` step failures in 7 days, all requeued.
- **Foresight.** Runs older than 6 h are reaped. The editorial loop reaps runs older than 1,200 s.
- **Leader locks** (`app/tasks/leader_lock.py`, Redis `SET NX EX`, default TTL 900 s) protect the
  spectrum, narrative, digest, paper and arXiv loops.
  - Foresight, newsfeed, timeline, editor review and the agent monitor have no lock and rely on
    there being one worker process.
  - The lock refresh does not check ownership, so two processes can both believe they lead after a
    lease lapses.
- **Write isolation.** Publish uses a savepoint per article and commits in batches. The embedding
  tasks commit every 10 rows.

---

## 14. Discrepancy list (code wins)

1. `docs/TRUST_SIGNALS.md`: the copy floor is 0.99, not 0.92. The AI labels are `unclear`/`ai`, not
   `ambiguous`. There is no structural short-circuit. There is no combined verdict.
2. `docs/ARTICLE_VALIDATION_AGENT_PLAN.md`: the verdict names (`non_independent`, `satire`,
   `no_verifiable_claims`), the serial agents, the 0.85 lexical floor and the ±30-day window all
   differ from the doc. Reflection is not built.
3. `docs/EMERGING_TOPICS_SYSTEM.md`: the cadence is 4 h, not 24 h. The stage-3 refresh is missing
   from the doc. The novelty weights, the spike cooldown and the host unit name are all stale.
4. `docs/NTI_NARRATIVE_CLUSTERING_SPEC.md` and the retirement preflight: NTI is disabled by env
   flags only, and its code and loop registrations remain.
5. `docs/CASCADE_SCAN_HOW_IT_WORKS.md`: matches the code.
6. `docs/SAAS_LOG_MONITOR.md`: this is a hand-kept bug log for the prod units; no script implements
   it. BUG-6 is fixed (900 s timeout). BUG-24 and BUG-34 still stand, and the "one config entry"
   note on BUG-34 is wrong. BUG-37 (timeline rollup truncation) is unfixed.
7. `CLAUDE.md` (saas): it says the lifespan starts 5 loops. The deployed web role starts none, and
   the worker starts about 60.
8. `docs/DEBERTA_EMBEDDING_DIMS.md` says "all surfaces 768d". That predates E5; the E5 store is 1024d.
9. `summarize.py` and `extract_ner.py` docstrings call the fallback "Configured LLM". In practice
   it is Haiku through the default use_case.
10. Internal comments in `llm.py` still mention an Ollama fallback and Sonnet 4.6. The real fallback
    is the DB row (Mistral Large 3 on prod).

---

## 15. Rebuild checklist (minimum set, in dependency order)

1. Run the DeBERTa encoder (768d, mean-pooled, not normalised) and the E5 encoder (1024d,
   `passage:`/`query:` prefixes). Create `article_embeddings` and `article_embeddings_ml` with HNSW
   indexes. Run both backfill loops.
2. Load `mbfc_sources` (MBFC CSV plus Idiap). Stamp MBFC fields at every ingest road, keyed on the
   article domain; do NOT key on the feed domain.
3. Run the analyst pipeline per topic: classify (Nova Lite, closed taxonomies), summarize (Phi-3,
   then a cheap LLM), extract_ner (KeyBERT plus Phi-3), enrich_mbfc, and optionally
   resolve_mentions. Publish confirmed rows to `articles`, extracting citations.
4. Run the per-article loops: ai_tells (heuristics, with a Haiku verdict above a threshold), novelty
   (daily for 14 days), coordination detection (DeBERTa ≥ 0.99 plus shared citations), and actor
   and author resolution.
5. Run the corpus-level jobs: story clusters (E5 ≥ 0.88 Louvain), emerging topics, affiliation,
   spectrum and the narrative drafts with editor review.
6. Run the readers: Trust Signals (five stations, live), on-demand validation, highlights,
   consensus, horizons, timeline and editorial briefings.
7. Route every LLM call through `ai_model_configs` by use_case, log every call to `llm_usage_log`,
   and add 5xx and timeout handling, which the current code lacks.
