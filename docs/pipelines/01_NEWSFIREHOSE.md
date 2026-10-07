# NewsFirehose: the upstream news aggregator

Written 2026-10-07 from a read-only pass over `/opt/newsfirehose` on this box (5.9.100.178), git HEAD `4403b1b` (2026-10-04). No secret values appear here. Where a variable holds a secret, only its name is given.

## What it is

NewsFirehose pulls about 25-40k English (plus a small Swiss German/French/Italian) news articles a day from NewsData.io into one Postgres table. Celery workers then tag each article against 24 fixed topics. Tagging uses a DeBERTa embedding with a per-topic classifier, and an LLM checks a 15% sample. A FastAPI service exposes full-text search over the table.

Both Aunoo products use it, in different ways:

- **Monolith tenants** call the HTTP API (`/v1/search`) through `app/collectors/newsfirehose_collector.py`.
- **saas** reads the Postgres tables directly (`scripts/import_firehose_corpus.py`), because it needs the stored DeBERTa embeddings, and the API does not serve them.

## Where it runs (state on 2026-10-07)

The live firehose moved to **188.40.128.115** on 2026-09-10. On this box, everything except the shared encoder is stopped.

| Part | This box | Notes |
|---|---|---|
| `newsfirehose-api.service` (:8000) | inactive, disabled | Live API answers at `http://188.40.128.115:8000/health` → `{"status":"healthy","database":"connected"}` (checked today) |
| `newsfirehose-worker.service` (Celery worker) | inactive, disabled | |
| `newsfirehose-beat.service` (scheduler) | inactive, disabled | |
| `newsfirehose-encoder.service` (old encoder) | inactive, disabled | Replaced by `deberta-encoder.service`. Do not start it, because it would fight for :8001 |
| `newsfirehose-flower.service` (:5555) | enabled but dead | |
| `newsfirehose-daily-train.timer` | disabled | |
| ingestion-check and worker-watchdog timers | not installed here | Unit files exist in `systemd/` |
| Postgres `newsdb` | **running**, in docker container `aunooscraper_pg` (postgres 16.4), `127.0.0.1:5431` | Frozen: the last row is id **4511749**, created 2026-09-09 14:24 UTC |
| Redis | running on :6379 | Shared with other things on this box |
| `deberta-encoder.service` (:8001) | **running** (CUDA) | Shared by every Aunoo site, see Stage 5 |
| saas `saas-firehose-import.timer` (hourly) | running, imports **0 rows** every hour | Reads the frozen local DB, see Stage 8 |
| saas `saas-firehose-check.timer` (daily) | **failing** | Reports "newest firehose article is 640.6h old" (06 Oct) |

This box's code is current with git (HEAD 10-04), but its `.env` dates from 2026-09-08. The live host's `.env` may differ. Every config value below is from this box's copy.

`newsfirehose.service` at the repo root is an unused template (its paths are `/path/to/your/...`). `docker-compose.yml` says at the top that it is obsolete (Phase 1, no Celery). The real unit files are in `systemd/`.

---

## Stage 1: Fetch from NewsData.io

**What it does.** One daily bulk pull of "everything recent" in fixed slices. It does not search by keyword. Articles are kept whether or not they match a topic, and topic tagging happens after they are stored.

**Trigger.** Celery beat task `fetch-newsdata-daily` → `worker.tasks.scheduled_fetch_newsdata` (`worker/celery_app.py:131-136`). The time comes from `CELERY_BEAT_NEWSDATA_HOUR=6`, `CELERY_BEAT_NEWSDATA_MINUTE=0`, `CELERY_BEAT_TIMEZONE=UTC` (.env:81-90). That is **06:00 UTC**, which is 08:00 Berlin in summer and 07:00 in winter. Code defaults are 02:00 UTC (`celery_app.py:109`), and the README still says 2 AM.

The task runs `fetch_newsdata.py` as a subprocess (`worker/tasks.py:305-367`):
- A Redis lock `newsfirehose:fetch_lock:fetch_newsdata.py` with a 1 h TTL, refreshed every 20 min, stops two fetches running at once (`tasks.py:292-336`).
- The hard limit is 24 h. A failed run is retried up to 3 times, 1 h apart (`tasks.py:373-390`).

**Inputs.** `NEWSDATA_TOKEN` (secret). `NEWSDATA_ENDPOINT=latest`, which is `/api/1/news` (.env:171; validated at `fetch_newsdata.py:71-73`). `NEWSDATA_TIMEFRAME=25` hours (.env:182), passed straight through as `timeframe` on the latest endpoint (`fetch_newsdata.py:460-463`). Global `NEWSDATA_LANGUAGE=en` and `NEWSDATA_PRIORITY_DOMAIN=top` (.env:174-175). Slices override the priority domain.

**Slices.** `NEWSDATA_SLICES` and `NEWSDATA_SLICES_WE` are single-line JSON arrays (`fetch_newsdata.py:76-96`). python-dotenv cannot read multi-line values, so each must stay on one line. Each slice is an object:

- `max_articles` (required; a slice without it is skipped, `:656-658`)
- `prioritydomain` (`top`/`medium`/`low`; empty means every tier, `:662-665`)
- `category` (comma list; absent means all categories)
- optional `language`, `country`, `domain`, `excludedomain`, which override the global values (added 2026-09-08 for the Swiss feed, `:670-675`)

The weekend set is used when the UTC weekday is Monday or Sunday, because those runs cover Saturday and Sunday news (`:634-647`).

Current weekday slices (.env:203):

| # | prioritydomain | category | language/country | max_articles | requests at 50/page |
|---|---|---|---|---|---|
| 1 | top | politics,world,domestic,crime | en | 11,500 | 230 |
| 2 | medium | technology,science,environment,health,education | en | 12,500 | 250 |
| 3 | top | business | en | 7,000 | 140 |
| 4 | top | technology,science,education | en | 5,600 | 112 |
| 5 | top | entertainment,food | en | 2,000 | 40 |
| 6 | (all) | politics,world,domestic | de,fr,it / ch | 1,000 | 20 |
| | | | | **39,600** | **792** |

The weekend slices (.env:213) use the same shapes with caps of 6,600 / 7,700 / 4,300 / 3,000 / 1,500 / 600. That totals 23,700 articles, or 474 requests.

**Paging.** Each slice makes `ceil(max_articles / ARTICLES_PER_REQUEST)` requests, with `ARTICLES_PER_REQUEST=50` (.env:231; code at `fetch_newsdata.py:522`). It follows the `nextPage` token and stops early when there is no next page or a page comes back empty (`:544-587`). The token advances before the articles are processed, so a crash during processing does not cause the same page to be fetched and billed twice (`:548-556`). `REQUEST_DELAY=40` s between requests (.env:232). Slices run one after another.

**Budget.** The .env comment says "650-670 requests/day", with ~648 on weekdays and ~393 on weekends (.env comment block above line 203). **The current caps add up to more than that: 792 weekday and 474 weekend requests if every slice runs to its cap.** In practice slices often run out of pages before the cap. At 40 s per request, a full run takes up to about 8.8 hours. `NUM_REQUESTS` is ignored when slices are set (.env:230).

**Outputs.** Rows in `news_firehose` (Stage 2). Each insert or content change queues `classify_article_task.delay(article_id)` (`fetch_newsdata.py:561-571`).

**Gotchas.**
- Errors inside `_fetch_slice` are caught, followed by a 40 s sleep and `continue` (`:593-596`). If the daily credit runs out, the loop keeps burning its remaining iterations, 40 s each, without stopping.
- `NEWSDATA_PRIORITY_DOMAIN` is ignored while slices are set; the script prints a warning (`:650-651`).
- `fetch_newsdata.py:12` imports `check_article_relevance`, which is a Phase 1 leftover and is never used.
- The worker's own watchdog fixes are recent: `celery_app.py:23-31` describes a Redis restart on 2026-09-30/10-01 after which the worker never reconnected, and two daily fetches sat unconsumed for over 24 h.

### TheNewsAPI fetch (disabled)

`fetch_thenewsapi.py` calls `https://api.thenewsapi.com/v1/news/all` (`:42`) with `NEWSAPI_TOKEN`. The schedule is off: `CELERY_BEAT_THENEWSAPI_ENABLED=false` (.env:77), and `NEWSAPI_TOKEN` is only present as a comment. The script still carries Phase 1 search and LLM-filter variables (`:59-81`). The table has no `thenewsapi` rows among ids above 4.3M; all 211,749 of those rows are `newsdata`.

---

## Stage 2: Storage (`newsdb`)

**Database.** Postgres `newsdb` with user `user` (`DB_*`, .env:7-11; port 5431 here). The base schema is `database_schema.sql`, and migrations `migrations/001-005_*.sql` are plain SQL files, not Alembic.

**Main table: `news_firehose`** (`database_schema.sql:5-90`). Key columns:
- `id` serial: the id every consumer uses (saas stores it as `external_id='nf_<id>'`)
- `external_id` (NewsData `article_id`)
- `url TEXT UNIQUE NOT NULL` (`:9`)
- `title`, `description`, `content`, `snippet`, `keywords[]`
- `source_name` (NewsData `source_id`), `source_domain` (taken from the URL), `source_url`, `source_icon`, `source_priority`
- `creator[]`, `image_url`
- `language`: **full English names** such as `english`, `german`, `french`, `italian`, never ISO codes
- `country[]`, `categories[]`
- `published_at`, `fetched_at`, `created_at`, `updated_at`
- `sentiment`, `sentiment_stats`, `ai_tag`, `ai_summary`, `ai_content`, `ai_organizations[]`, `ai_region`: NewsData's own AI fields, filled only on paid tiers
- `mbfc_*` (8 columns, Stage 6)
- `duplicate bool` (always false in practice)
- legacy `use_case_name`/`use_case_description`, overwritten with the top topic slug (`worker/tasks.py:95-116`)
- `source_api`, `raw_payload jsonb`
- `search_vector tsvector`, kept current by a trigger (`database_schema.sql:154-191`; GIN index at `:157`)

The full-text search weights are title A, description B, keywords B, content C, snippet D, all with the `english` configuration, which stems words.

**Deduplication.** `check_duplicate_article` looks up `url = %s OR external_id = %s` (`fetch_newsdata.py:222-233`):
- On a match, the row is updated only if `content` changed (`:235-241`, `:341-385`). An updated row is re-queued for classification.
- Otherwise the article counts as a duplicate and is skipped.
- Rows missing a URL or `external_id` are dropped (`:334-336`).

The same story at two different URLs becomes two rows. Nothing deduplicates by content.

**Topic tables.**
- `topics`, `article_topics(article_id, topic_id, relevance_score, classification_method, classifier_model, classification_trigger, …)` (`migrations/001:9-56`, `002:116-130`)
- `classification_feedback` (`002:90-112`)
- `encoder_versions`, `article_deberta_embeddings`, `topic_classifiers` (`003:9-116`)
- `mbfc_sources` (`database_schema.sql:118`)

**Search role.** `nf_search` is a separate login with `CONNECTION LIMIT 2`, `statement_timeout=60s`, and `work_mem=32MB` (`migrations/005_search_hardening_roles.sql`). It came out of the 2026-08-04..10 search-overload incident, in which search load saturated the host.

---

## Stage 3: Topic classification

**Trigger.** One Celery task per new or changed article, `classify_article_task` (`worker/tasks.py:148-233`). The worker runs with concurrency 10 (`CELERY_WORKER_CONCURRENCY`, .env:26). A failed task retries 3 times with backoff; a rate-limited one retries 5 times, 10 s apart (`:139-145`, `:228-233`). If a worker crashes mid-task, that article stays untagged; `cli/topic_backfill.py` re-runs missed ones (`celery_app.py:78-87`).

**Topics.** 24 topics are defined in `topics.yaml` and synced into the `topics` table with `python cli/topic_sync.py`. Workers read the DB table, not the YAML (`worker/db_utils.py:55-58`).

Each topic has a slug, name, description, keyword list, `relevance_threshold` (0.7-0.85), `class_prior`, and `active`. Examples are `ai`, `geopolitics`, `cybersecurity`, `disinformation`, `eu_ai_regulation`, `business_finance`, and `indie_games` (`topics.yaml:7-1170`).

In the local DB, 23 topics have `classifier_status=active`, and `eu_ai_regulation` is still `cold_start` with no trained classifier. Only `geopolitics` has `llm_enabled: false` (`topics.yaml:85`), so it is tagged by DeBERTa alone.

**Step 3a: keyword pre-filter** (`api/topic_classifier.py:116-151`, called from `tasks.py:177`). The worker lowercases title + description + content and counts topic keywords that appear in it as **substrings**. If none appear, it skips the article and stores no tags and no embedding.

Gotcha: this filter passes almost everything. Short keywords such as `AI`, `war`, and `GPT` match inside ordinary words ("s**ai**d", "a**war**d"). Of the 111,749 local rows above id 4.4M, 103,850 (93%) went on to get an embedding.

`ENABLE_KEYWORD_PREFILTER`, `KEYWORD_PREFILTER_MIN_MATCHES`, and `CLASSIFICATION_MODE` in .env are **not read by any code**. The filter always runs, and its threshold is always 1.

**Step 3b: split topics into two groups** (`tasks.py:183-215`):
- Topics with `llm_enabled=false` and an active classifier go straight to `deberta_nnpu`.
- All other topics go through the default method, `SEMANTIC_DEFAULT_METHOD=pipeline` (.env:61).

**Step 3c: the pipeline** (`topic_classifier.py:275-335`). The order of methods comes from `config/semantic_config.yaml:135-138`: `deberta_nnpu` → `llm` → `llm_fallback`. **The first method that returns any topic wins**, and the later ones are not called.

1. **`deberta_nnpu`** (`api/deberta_classifier.py:290-389`):
   - It gets the article's 768-d embedding: first from the `article_deberta_embeddings` cache, otherwise by calling the encoder service and storing the result (`:190-221`). See Stage 4.
   - For each topic, it loads the active `topic_classifiers` row and checks that its encoder version matches (`:245-286`).
   - It scores with `predict_proba`, which is calibrated with Platt scaling if a calibrator file exists, and compares the score with that classifier's `threshold`. Thresholds default to 0.50 (`semantic_config.yaml:129`).
   - A topic with no classifier scores 0.0. The comment at `:337-341` explains why: centroid cosine similarity is useless here, because DeBERTa-base embeddings are anisotropic (any two news texts score about 0.9 cosine).
   - The classifier is an MLP (768 → 256 → 1) trained with the nnPU loss from Kiryo et al. 2017 (`ml/nnpu.py:48-92`). Topics with fewer than 30 positives get logistic regression instead (`NNPU_MIN_POSITIVES`, .env:262).
   - Exceptions are swallowed and returned as an empty result (`topic_classifier.py:217-230`). A DeBERTa failure therefore never counts as an "error", so it never triggers `llm_fallback`.
2. **`llm`**, which runs only if DeBERTa matched nothing, and then only on a random 15% sample (`LLM_SAMPLE_RATE=.15`, .env:149; `topic_classifier.py:313-319`):
   - The candidate topics are only those whose keywords appear in the text (`:418-433`).
   - One call covers all candidate topics. The prompt asks for strict JSON and caps content at 40k characters (`:450-455`).
   - The LLM's score must reach the topic's `relevance_threshold` (`topic_classifier.py:572`).
   - The call goes to `{LLM_BASE_URL}/v1/chat/completions` with a Bearer token (`api/llm_relevance.py:249-298`).
   - `LLM_BASE_URL` is `https://bedrock-runtime.us-east-1.amazonaws.com/openai`, Bedrock's OpenAI-compatible endpoint (.env:130).
   - Model `LLM_MODEL=qwen.qwen3-32b-v1:0`, temperature 0.2, `max_tokens` 300, timeout 60 s (.env:131-134).
   - The response cleaner strips `<think>` and other reasoning tags (`topic_classifier.py:75-113`).
   - HTTP 429 raises `LLMRateLimitError`, and Celery retries the task.
3. **`llm_fallback`** runs only if the `llm` step raised an exception. A clean "no match" does not trigger it (`:306-311`). It uses `LLM_FALLBACK_MODEL=moonshotai.kimi-k2.5` on the same Bedrock endpoint, with the same settings (.env:139-147).

**Outputs.**
- One `article_topics` row per matched topic, with `classification_method` set to the step that matched (`deberta_nnpu` or `llm`) and `classifier_model` set to `deberta_nnpu_v1` or the LLM id (`tasks.py:45-60`, `68-92`).
- The legacy `use_case_name` is set to the top topic.

Measured on the local copy (ids above 4.4M): 56,218 DeBERTa tags and 201 qwen tags.

**Retraining** (`cli/daily_train.py`, timer `newsfirehose-daily-train.timer` at 03:00 UTC, disabled here). It runs seed → embed → train for every topic:
- `seed_positives.py` copies high-scoring LLM tags into `classification_feedback` as confirmed positives (`SEED_MIN_SCORE=0.90`, .env:268). A regression guard keeps the old model if quality drops.
- Gotcha: the unit passes `--model gpt-4o claude-sonnet-4-6` (`systemd/newsfirehose-daily-train.service`), so only tags made by those two models count as positives. The live LLM is qwen, so **the current LLM's verdicts never feed retraining** unless the live host's unit differs.

**Unused config.** The `semantic_classification` block in `config/semantic_config.yaml:7-98` (BART-MNLI, MiniLM 384-d, ensemble weights) is switched off (`enabled: false`; `SEMANTIC_CLASSIFICATION_ENABLED=false`, .env:64). `systemd/vllm.service` (Phi-3-mini) is also unused.

---

## Stage 4: Embeddings

- **Model:** `microsoft/deberta-base`, encoder version 1, the only row in `encoder_versions` (`migrations/003:28-30`). It has had no domain-adaptive pretraining (DAPT).
- **Method** (`ml/encoder.py:53-192`):
  - The input text is `title [SEP] body`, where the body is `content` if non-empty, otherwise `description` (`:111-129`).
  - The vector is a mean pool of the last hidden layer over the tokens.
  - Text longer than 512 tokens is split into 512-token windows that overlap by 64 (`:27-28`), and the window vectors are averaged.
  - Vectors are **not L2-normalised**.
- **Dimension:** 768.
- **Where stored:** `article_deberta_embeddings.embedding_json` (JSONB), one row per `(article_id, encoder_version)`, plus a `content_hash` (SHA-256 of title+body) (`migrations/003:36-61`).
- **Write path:** `worker/db_utils.py:457-485`. It writes **only `embedding_json`**. The `embedding vector(768)` column exists but is never filled: 0 of 103,850 recent rows have it.
- **When:** only as a side effect of DeBERTa classification. Articles dropped by the keyword pre-filter have no embedding.

Gotcha: an article whose content changes keeps its old embedding. `get_deberta_embedding` returns the cached vector by `(article_id, version)` without checking `content_hash`, and the hash is only written, never compared.

---

## Stage 5: `deberta-encoder.service` (shared, :8001)

**What it does.** One process holds DeBERTa on the GPU and returns embeddings over HTTP, so that workers and tenants do not each load their own copy.

**Unit:** `/etc/systemd/system/deberta-encoder.service`.
- User/group `deberta`, tree `/opt/deberta-encoder`, own venv and HF cache.
- `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, `DEBERTA_MODEL=microsoft/deberta-base`, `DEBERTA_DEVICE=auto`.
- Runs `uvicorn ml.encoder_service:app --host 127.0.0.1 --port 8001 --workers 1`. The single worker is mandatory, because every extra worker would load its own copy of DeBERTa.
- `Restart=always`, hardened with `ProtectSystem=strict` and `ProtectHome`.
- Deliberately **not** part of `newsfirehose.target`, so it survives the firehose stack being stopped or moved.

Status today: active since 2026-10-01, `/health` returns `{"status":"ok","model":"microsoft/deberta-base","device":"cuda"}`, using about 745 MB of RAM.

**Code.** `/opt/deberta-encoder/ml/encoder.py` and `encoder_service.py` are byte-identical to the copies in `/opt/newsfirehose/ml/`.

**API** (`ml/encoder_service.py:64-89`):
- `GET /health`
- `POST /encode` with body `{title, description, content}` returns `{embedding: [768 floats]}`. A single-thread executor runs one encode at a time.

**Callers.**
- Monolith: `app/vector_store_pgvector.py:44` (`DEBERTA_ENCODER_URL`, default `http://localhost:8001`).
- saas: `saasmvp-app/app/core/config.py:210` and `app/ai/llm.py:36`.
- The firehose worker, when it runs on this box (`ENCODER_SERVICE_URL`, .env:256).

Because the model, pooling, and `title [SEP] body` input are the same everywhere, tenant-made vectors and firehose vectors live in the same space.

---

## Stage 6: MBFC enrichment (dormant)

**What it does.** It adds Media Bias/Fact Check ratings for each publisher to every article from that publisher.

**How it runs.** This is a manual two-step process with no scheduler; there is no cron, timer, or Celery task.

1. `run_mbfc_data_fetcher.py` → `mbfc_data_fetcher.py` downloads the whole MBFC list from RapidAPI (`media-bias-fact-check-ratings-api2.p.rapidapi.com/fetch-data`, `:58-61`) into `mbfc_sources` (9,632 rows locally). It needs `RAPIDAPI_KEY`, **which is not in this .env**. The `.env` has `MBFC_API_URL`/`MBFC_API_KEY`/`ENABLE_MBFC_ENRICHMENT` (.env:301-303), but no code reads them.
2. `run_mbfc_enrichment.py` → `mbfc_enrichment.py` matches each `news_firehose` source to an MBFC entry, in this order (`:152-215`):
   - normalised `source_domain`
   - then `source_url`
   - then exact `source_name`
   - then **substring name matching**, in either direction

   It then runs `UPDATE news_firehose SET mbfc_* … WHERE source_name = … OR source_domain = … OR source_url = …` (`:266-279`).

**Last run:** 2025-09-11 (`mbfc_enrichment.log`), which matched 1,706 of 3,086 sources. None of the 111,749 local rows above id 4.4M has `mbfc_bias`, so the saas importer's `mbfc_*` fields are NULL for current articles.

**Gotcha.** The substring name match can attach the wrong outlet's rating. For example, a short name like "times" matches many outlets.

---

## Stage 7: HTTP API (FastAPI, :8000)

The service starts from `start_api.py` / `main.py` and mounts its routers under `/v1` (`main.py:63-66`):
- **Auth:** an `X-API-Key` header checked against `API_KEYS` or `api_keys.json` (`api/auth.py:14-80`), with `ENFORCE_AUTH=true`.
- **Rate limits:** slowapi at 100 requests/min per IP on these routes; `RATE_LIMIT_PER_MINUTE=100`.
- **Health:** `/health` (`main.py:86`).

### `GET /v1/search` (`api/routers/search.py:94-303`)

**Parameters:**
- `q` (required, 1-500 characters)
- `sources` (comma list, matched against `source_name`)
- `categories` (comma list; array overlap)
- `language` (**exact string match**)
- `country` (comma list; array overlap)
- `from_date` and `to_date` (YYYY-MM-DD)
- `sentiment` (positive/negative/neutral)
- `sort_by` (`relevance` default, or `published_at`)
- `page_size` (1-100, default 20)
- `page`

**Query building** (`prepare_search_query`, `:519-574`):
- Uppercase ` AND `/` OR `/` NOT ` become `&`/`|`/`!`.
- `"a b"` becomes `a <-> b`, an adjacent-word phrase.
- In an OR query, each multi-word term becomes `(w1 & w2)`.
- With no operators at all, spaces become `&`.

So **plain words are ANDed**, and each OR branch is an AND of its words. Matching uses `search_vector @@ to_tsquery('english', $1)`, which stems words ("elections" matches "election"). Results are ranked by `ts_rank_cd`, and rows with `duplicate = TRUE` are always excluded.

**Cost limits**, added after the August 2026 search-overload incident (`:28-35`, `:166-201`):
- At most **8 OR terms**; more returns HTTP 400.
- With no `from_date`, the window defaults to the **last 14 days**.
- Any window is capped at **90 days**; the API silently moves `from_date` forward.
- No exact COUNT: the API fetches `page_size + 1` rows and returns `has_more` (`total_results` is only `offset + rows`).
- Queries run on the `nf_search` pool with a 2 s wait for a slot. When busy, it returns HTTP 429 with `Retry-After: 5`.
- If the client disconnects, the query is cancelled and the API returns 499.

**Language filter.** The stored values are `english`, `german`, `french`, `italian`. Passing `language=en` returns **nothing**, even though the docstring says ISO codes work (`:125`).

**Phrase inside OR.** A quoted phrase inside an OR query breaks: `"a b" OR c` becomes `(a & <-> & b) | c`, which is a tsquery syntax error.

Every result includes `topics` (slug, name, score) from `article_topics`, and `use_case_name` is set to the top topic (`articles.py:68-124`). **Embeddings are never returned.**

### `GET /v1/articles?ids=` (`api/routers/articles.py:547-627`)

- `ids` is a comma list of up to 50. Each entry can be an internal `id`, an `external_id`, or a URL.
- SQL: `WHERE id = ANY($1::bigint[]) OR external_id = ANY($2) OR url = ANY($2)`.
- Returns the same article shape with topics. No embeddings.

### Other routes

- `/v1/everything`, `/v1/top-headlines`, `/v1/search/keyword`, `/v1/article/{id}` (`articles.py`)
- `/v1/sources`, `/v1/categories`, `/v1/languages`, `/v1/countries` (`sources.py`)
- `/v1/topics`, `/v1/topics/{slug}/articles` (`topics.py`)
- `/v1/search/suggestions`, `/v1/search/trending` (`search.py:306`, `:402`)

---

## Stage 8: Consumers

### 8a. Monolith collector: `app/collectors/newsfirehose_collector.py` (bugfixing tree)

- **Endpoint:** `NEWSFIREHOSE_BASE_URL` (`:150`). The code default `http://5.9.100.178:8000` is the **dead old host**. Every running tenant's `.env` sets `http://188.40.128.115:8000`: abm, bugfixing, oviva, panaya, saas, sunstar, wbm, wiley, wileytest, and saasmvp-app.
- **Key:** `PROVIDER_NEWSFIREHOSE_API_KEY` or `NEWSFIREHOSE_API_KEY` (`:144`), sent as `X-API-Key`.
- **Language:** `LANGUAGE_MAP` converts ISO codes to the stored names (`en` → `english`, …) before calling (`:24-44`, `:211-213`). This is the workaround for the exact-match filter in Stage 7.

**Query rewriting** (`_normalize_query`, `:48-125`):
- A query that is **only** one quoted phrase is kept as a phrase (`:80-89`).
- Anything else is flattened: quotes and parentheses are removed, and `|`, `+`, `AND`, `and`, `or` all become ` OR `.
- `NOT x` is deleted, and `& ! : * \` are removed.

The result is a flat OR-chain. The server then turns each multi-word OR term into an AND of its words. The effective meaning is therefore "**any term matches, and each term is an AND of its words, anywhere in the document**". That leads to two problems:

- **The OR-flattening gotcha:** a tenant query `military AND coup` becomes `military OR coup`, which is much broader than the user asked for. Precision then has to come from relevance scoring further down the pipeline.
- **The AND-of-words gotcha:** an unquoted multi-word keyword like `Atlantis Press` matches any document that contains both words anywhere, for example a Tomb Raider page that uses "press". The docstring at `:68-74` gives that example.

**Splitting and dates.**
- `_split_query_terms` splits the OR-chain into groups of 8 terms to stay under the API's limit. It calls `/v1/search` once per group and merges the results, deduplicating by URL (`:127-141`, `:303-327`).
- `from_date` is always sent: the caller's start date, or now minus `timeframe` hours, or 30 days (`:224-247`).
- After the call, the collector filters by date itself, keeping a 30-day minimum window (`:329-376`).

`fetch_article_content` searches `/v1/search?q=<url>` (`:386-400`). That is a full-text search for the URL string, not an id lookup, so expect misses.

### 8b. saas importer: `scripts/import_firehose_corpus.py` (saasmvp-app and saas.aunoo.ai trees, identical)

**What it does.** It copies firehose articles **and their DeBERTa embeddings** into the saas `articles` and `article_embeddings` tables.
- It reads the firehose Postgres directly, because the API does not serve embeddings.
- It only takes rows that have an embedding: it `JOIN`s `article_deberta_embeddings` (`:441-446`).
- It also requires usable text: `content` of at least 200 characters, or `ai_summary` of at least 100 (`:447-458`).
- It stores the vector as `CAST(:emb AS vector)` with `model='deberta-base'` (`:256-262`, `:329-333`).

**Trigger.** `saas-firehose-import.timer`, hourly, runs `--auto-watermark --limit 3000` in the saas.aunoo.ai tree. The watermark is the highest `nf_<id>` already in saas (`:85-110`).

**Source.** `FIREHOSE_DSN`, which defaults to `postgresql://user:pass@localhost:5431/newsdb`, the old docker DB (`:51-57`). `check_firehose_watermark.py:55-56` reads the same variable.

**5432 access status (checked today).** The problem is still open:
- **`FIREHOSE_DSN` is not set** in `/home/orochford/tenants/saas.aunoo.ai/.env` or `saasmvp-app/.env`, so the importer reads the frozen local copy.
- Every hourly run logs `0 imported … watermark 4511749 → 4511749` (journal, 03:00-07:01 today).
- The daily lag check fails at 640 h stale.
- From this box, `188.40.128.115:5432` and `:6432` are both **closed or filtered**; only `:8000` answers.

To fix it:
1. Open tcp/5432 (or 6432 for pgbouncer) on the new host to 5.9.100.178, plus a `pg_hba` entry.
2. Add `FIREHOSE_DSN=postgresql://<user>:<pw>@188.40.128.115:5432/newsdb` to the saas `.env`.
3. Start the import service.

If the connection goes through pgbouncer on 6432, the script already turns off asyncpg's statement cache (`:61-82`). There is no SSH access from this box to the new host. Four ad-hoc backfill scripts still hard-code `localhost:5431`.

**Consequence.** saas has received no firehose articles since 2026-09-09 14:24 UTC, which is about four weeks.

---

## Rebuild checklist (short)

1. Postgres 16 + pgvector. Apply `database_schema.sql` (it creates the search trigger and GIN index), then `add_mbfc_columns.sql`, then `migrations/001`→`005`. Set the `nf_search` password by hand.
2. Run `python cli/topic_sync.py` to load `topics.yaml` into `topics`.
3. Redis. `deberta-encoder.service` on :8001 with the `microsoft/deberta-base` weights pre-cached (it runs offline).
4. Install `systemd/newsfirehose-{worker,beat,api}.service` and `newsfirehose.target`, plus the watchdog, ingestion-check, and daily-train timers. Do **not** install `newsfirehose-encoder.service` alongside `deberta-encoder`.
5. Set these in `.env`: `NEWSDATA_TOKEN`, `NEWSDATA_ENDPOINT=latest`, `NEWSDATA_TIMEFRAME=25`, the slice JSON on one line, `ARTICLES_PER_REQUEST=50`, `REQUEST_DELAY=40`, the `CELERY_BEAT_*` schedule, `LLM_*`/`LLM_FALLBACK_*` (Bedrock `/openai`, qwen3-32b / kimi-k2.5), `LLM_SAMPLE_RATE=.15`, `SEMANTIC_DEFAULT_METHOD=pipeline`, `ENCODER_SERVICE_URL`, `MODEL_DIR`, `API_KEYS`, `SEARCH_DB_USER`/`SEARCH_DB_PASSWORD`.
6. Copy the trained classifiers from `models/classifiers/{slug}/…` and the `topic_classifiers` rows. Without them, every topic scores 0 in DeBERTa and only the 15% LLM sample tags anything.
7. Open a Postgres port to the saas host if saas is to import directly.

## Smaller gotchas

- `.env` contains secrets in **commented-out** lines: an old OpenAI audit key and an old NewsData key. `FLOWER_BASIC_AUTH` is a plain-text password. Rotate them if this file is ever copied.
- `CELERY_VISIBILITY_TIMEOUT=43200` in .env, against a code default of 7200. Both values satisfy the constraint in `celery_app.py:37-45`.
- MBFC fields and NewsData `ai_summary`/`sentiment` are often NULL. Consumers must treat NULL as "unknown", not as a neutral rating.
- When you query the local copy with `docker exec aunooscraper_pg psql -U user -d newsdb`, a plain `count(*)` on `news_firehose` hits the 60 s `statement_timeout` for role `user`. Filter by `id > N` instead.
