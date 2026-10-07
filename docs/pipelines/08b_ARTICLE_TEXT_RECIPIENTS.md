# Services that receive article text (monolith, bugfixing)

7 October 2026 · Work package WP2 of [08_INGEST_FIX_SPEC.md](08_INGEST_FIX_SPEC.md).

This lists every service that receives an article's text, or its URL so that it can fetch the text,
on the bugfixing tenant. It describes the code at commit `83fecd57` and the configuration and
database as read on 7 October 2026 between 10:45 and 11:00 CEST. It does not describe the fixes
planned in the spec.

## How to read it

Each entry separates two kinds of fact:

- **Configured** means the code and configuration send text there. The sources are the code, the
  `keyword_monitor_settings` row on `test`, `.env` (variable names and non-secret values only) and
  `app/config/litellm_config.yaml`.
- **Verified** means calls actually happened. For language models the evidence is the call log
  `llm_usage_log` on `test` for the 7 days from 30 September 10:48 to 7 October 10:48 (query at the
  end). For the other services it is the service journal or the health-check log, as stated.

A region appears only where configuration states one. Every Bedrock model in
`litellm_config.yaml` that this list names carries `aws_region_name: "us-east-1"`, and `.env` sets
`AWS_REGION_NAME=us-east-1`. Bedrock model IDs that start with `us.` are cross-region inference
profiles, and the configuration does not say which AWS regions Bedrock may route those calls to, so
this document claims only the configured region. No region is configured or documented for
TypeSafe or Firecrawl.

The call log records only calls made through LiteLLM and the TypeSafe client. Scraping and the
local encoder do not appear in it.

## Summary

| # | Service | What it receives | Provider and model, as configured | Configured region | Fallbacks | Status |
|---|---|---|---|---|---|---|
| 1 | Article analysis (labels, summary, tags) | title, source, URL, collector summary or content | Bedrock, alias `bedrock-kimi-k2-5` → `bedrock/moonshotai.kimi-k2.5` | us-east-1 | `bedrock-claude-haiku` → `nova-lite` | Verified: 2,970 calls, all Kimi K2.5 |
| 2 | Publication-date call | first 10,000 characters of the same text | same as 1 | us-east-1 | same as 1 | Verified: still running (see below) |
| 3 | Summary faithfulness shadow | summary sentences and the article text | TypeSafe API, `jev-1.13.0` | not stated | none | Verified: 1,493 calls |
| 4 | Relevance: local similarity and classifier | title + collector content or summary | in-process, `all-MiniLM-L6-v2` and the DeBERTa relevance classifier | on this server | none | Configured; runs in-process, not logged |
| 5 | Relevance: Jev accept tier and shadow | title + up to 4,000 characters of that text | TypeSafe API, `jev-1.13.0` | not stated | none | Verified: 14,310 calls |
| 6 | Relevance: LLM adjudicator | title + that text, untruncated | Bedrock, `nova-lite` → `bedrock/us.amazon.nova-lite-v1:0` | us-east-1 | `bedrock-kimi-k2-5` → `nova-pro` | Verified: 9,512 calls, all Nova Lite |
| 7 | Relevance: cross-encoder tier | title + summary | local `bge-reranker-base` | on this server | none | Configured off (`RELEVANCE_USE_CE_TIER=false`) |
| 8 | Relevance: LLM-only fallback | title + content | the analysis model (1) via `RelevanceCalculator` | us-east-1 | as 1 | Configured; no calls seen in the 7 days |
| 9 | Translation at first insert | non-English title and summary, up to 3,000 characters each | Bedrock, `nova-lite` | us-east-1 | `bedrock-kimi-k2-5` → `nova-pro` | Verified: 3,016 Nova Lite calls, 1 Kimi call |
| 10 | Page fetching | article URL; returns the page | Firecrawl SDK with `FIRECRAWL_API_KEY`, default endpoint | not stated | per-URL scrape when the batch call fails | Verified in the journal |
| 11 | Embedding | title, tags, page text or summary | local `deberta-encoder.service`, `127.0.0.1:8001` | on this server | none by design | Verified by the health check |
| 12 | Social post evaluation | post text | Bedrock, `SOCIAL_EVAL_MODEL=claude-haiku-4-5` → `bedrock/us.anthropic.claude-haiku-4-5-20251001-v1:0`; group 23 uses `bedrock-kimi-k2-5` | us-east-1 | `bedrock-kimi-k2-5` → `nova-lite` | Partly verified (see below) |
| 13 | Social Jev pre-screen | post text | TypeSafe API, `jev-1.13.0` | not stated | none | Verified: 141 calls |
| 14 | Author role (Brand Voices) | post text | TypeSafe API, `jev-1.13.0` (`VOICES_ROLE_MODEL=jev`) | not stated | none | Verified: 1,498 calls |
| 15 | Post-ingest data-quality spot check | title + summary of saved articles | Bedrock, `DATA_QUALITY_MODEL` default `nova-lite` | us-east-1 | as 9 | Verified: 734 calls |

MBFC media-bias lookup is a table lookup in the `mediabias` table and sends nothing outside.

## Details

### 1. Article analysis

- **Purpose.** One call per article that passed the quick relevance check. It returns the category,
  the four labels with explanations, a summary of about 50 words and 3–5 tags.
- **Model choice.** `AutomatedIngestService.get_llm_client()` reads
  `keyword_monitor_settings.default_llm_model` for id 1, which is `bedrock-kimi-k2-5` on `test`
  (`automated_ingest_service.py:211`). The alias resolves to `bedrock/moonshotai.kimi-k2.5` with
  `aws_region_name: "us-east-1"` (`litellm_config.yaml`, `model_name: bedrock-kimi-k2-5`).
- **Fallbacks.** `bedrock-kimi-k2-5` falls back to `bedrock-claude-haiku`
  (`bedrock/us.anthropic.claude-haiku-4-5-20251001-v1:0`, us-east-1), then `nova-lite`
  (`litellm_config.yaml`, `fallbacks:`).
- **Text sent.** Title, source, URL and the collector's summary, or its content when there is no
  summary (`automated_ingest_service.py:1545`). The scraped page is sent only when the collector sent
  no text at all (`:1098-1118`).
- **Verified.** 2,970 `analyzers.article_analyzer:analyze_content` calls, all
  `moonshotai.kimi-k2.5`, all `success`. No analysis call went to a fallback model in the window.

### 2. Publication-date call

The analyzer makes a second call with the first 10,000 characters to extract a publication date.
Commit `679ee413` (7 October 2026, 10:16) turned it off for auto-ingest
(`automated_ingest_service.py:1604`, `extract_date=False`). The running bugfixing process started at
10:03:50 that day, before the change reached the file on disk, so it still makes the call: the log
shows 2,462 `extract_publication_date_result` calls and 502 `extract_publication_date` calls on Kimi
K2.5 in the window, the latest at 10:46 on 7 October, and 4 more on Nova Lite. The change takes
effect at the next restart. Manual research keeps the call.

### 3. Summary faithfulness shadow

`TYPESAFE_SHADOW_EXTRACTION=1`. After each analysis, `app/services/extraction_check_shadow.py`
sends each summary sentence with the article text to TypeSafe's API
(`API_URL = "https://api.typesafe.ai/v1/systemone"`, `app/services/typesafe_client.py:32`) to check
it against the source. It records an answer and changes nothing. Verified: 1,493
`services.extraction_check_shadow:check` calls.

### 4–8. Relevance judges

The relevance check runs twice per article: once on arrival and once after the analysis. Tiers and
thresholds are described in `docs/AI_DESIGN_PATTERNS.md` section 2.1.

- **Local (4).** The similarity model and the relevance classifier load inside the app process
  (`hybrid_relevance_service.py:44`, `_load_classifier`). No text leaves the server.
- **Jev (5).** `TYPESAFE_DECIDE_RELEVANCE_ACCEPT=1` and `TYPESAFE_SHADOW_RELEVANCE=1` with
  `TYPESAFE_SHADOW_RATE=1.0`, so every scored article goes to TypeSafe once per scoring, whichever
  inference mode is set. The payload carries the title and the first 4,000 characters of the text,
  plus up to 20 topic keywords (`hybrid_relevance_service.py:629-726`). Verified: 14,310
  `_compute_jev_shadow` calls.
- **LLM adjudicator (6).** `HYBRID_RELEVANCE_LLM_MODEL` is not set, so the code default `nova-lite`
  applies (`hybrid_relevance_service.py:605-606`). The prompt carries the title and the full
  collector content or summary with no length cut. `nova-lite` falls back to `bedrock-kimi-k2-5`,
  then `nova-pro`. Verified: 9,512 `_compute_external_llm_score` calls, all
  `us.amazon.nova-lite-v1:0`.
- **Cross-encoder (7).** Configured off. If turned on it runs locally.
- **LLM-only fallback (8).** When the hybrid scorer raises or answers "unavailable", ingest runs
  `_score_article_relevance_llm_only` with the analysis model (`automated_ingest_service.py:655-690`),
  in any inference mode. No call under that path appears in the window.
- `RELEVANCE_MODEL` and `RELEVANCE_FALLBACK_MODEL` are both `claude-haiku-4-5` in `.env`. They
  configure `app/services/relevance_scorer.py`, which deep research uses, not the ingest gate.

### 9. Translation

`facade.create_article` translates a non-English title and summary before the first insert and keeps
the originals in `original_title` and `original_summary`. An offline check decides which text is
non-English; only that text goes to the model (`app/utils/title_translation.py`,
`TRANSLATION_MODEL = "nova-lite"` at `:33`, `TEXT_TRANSLATE_LIMIT = 3000` at `:75`). Verified: 1,731
`translate_title` and 1,285 `translate_text` calls on Nova Lite, and 1 `translate_text` call that
Kimi K2.5 served, which matches the configured `nova-lite` fallback.

### 10. Page fetching (Firecrawl)

Ingest sends article URLs to Firecrawl's batch API. Firecrawl fetches the page and returns its text,
which ingest stores in `raw_articles` (`automated_ingest_service.py`, `scrape_articles_batch` at
`:2193`). The client is the Firecrawl v2 SDK created with only an API key (`app/research.py`,
`Firecrawl(api_key=...)`), so it uses the SDK's default hosted endpoint; no URL or region is
configured. Every article whose collector content is 200 characters or less is sent before the
relevance check (`:1770-1794`). Verified: the service journal shows 84 "Sending N URLs to Firecrawl"
lines in the 24 hours to 7 October 10:53.

### 11. Embedding

The local `deberta-encoder.service` (`/opt/deberta-encoder`, uvicorn on `127.0.0.1:8001`) receives
the title, the tags and the page text or summary of each approved article
(`app/vector_store_pgvector.py`, `build_article_encoder_input`). `DEBERTA_ENCODER_URL` is not set in
`.env`, so the default `http://localhost:8001` applies. There is no cloud fallback. The 8,000-token
cut is counted with the tiktoken `text-embedding-3-small` tokenizer on this server; no text goes to
OpenAI. Verified: `/var/log/aunoo-embedding-health.log` at 10:45 on 7 October shows the encoder
answering at 768 dimensions; on `test`, 47,481 of 47,483 approved rows have an embedding.

### 12–14. Social posts

- **Evaluation (12).** The model is the group's `keyword_groups.default_llm_model`, else
  `SOCIAL_EVAL_MODEL`, else `gemma3:4b` (`app/services/social_eval_service.py:26`, `:304`).
  `SOCIAL_EVAL_MODEL=claude-haiku-4-5` resolves to
  `bedrock/us.anthropic.claude-haiku-4-5-20251001-v1:0`, us-east-1, with fallbacks
  `bedrock-kimi-k2-5` then `nova-lite`. Only group 23 sets its own model, `bedrock-kimi-k2-5`.
  **Not fully verified:** the log has 3,053 Haiku 4.5 calls with `use_case = 'unknown'`. Social
  evaluation is the busiest path configured for Haiku 4.5, so it is the likely caller, but deep
  research (`RELEVANCE_MODEL=claude-haiku-4-5`) is configured for it too, and the log does not name
  the caller. Treat the attribution as an inference.
- **Jev pre-screen (13).** `SOCIAL_JEV_PREFILTER_MIN=0.1`, `SOCIAL_JEV_ACCEPT_MIN=0.91`. Verified:
  141 `social_eval_service:jev_prefilter` calls.
- **Author role (14).** `VOICES_ROLE_MODEL=jev`. Verified: 1,498 `author_role_jev:read_role` calls.

### 15. Data-quality spot check

`DataQualityService` samples saved articles after a batch saves at least three and asks a model
whether each title and summary fits the topic (`app/services/data_quality_service.py:45`,
`DATA_QUALITY_MODEL` unset, so `nova-lite`). Verified: 734 `_check_single_article` calls.

## Other features that send stored article text

These read articles after ingest. Counts are from the same 7-day window.

| Feature | Use case in the log | Model served | Calls |
|---|---|---|---|
| Brand Watcher categorisation | `routes.brand_watcher_routes:_llm_categorize_article` | Kimi K2.5 | 13 |
| Brand Watcher adverse screening | `services.brand_screening:llm_detect_risks` | Kimi K2.5 4, Claude Haiku 4.5 63 | 67 |
| Emerging topics | `services.emerging_topics.*` | Claude Sonnet 4.5 534, Kimi K2.5 107 | 641 |
| Market post review | `services.market_post_review:*` | Jev, Kimi K2.5, Claude Sonnet 5 | 959 |
| Timeline and events | `services.timeline_rollup:_llm_json`, `services.timeline_events:_llm_extract_events` | Kimi K2.5 | 242 |
| News feed analysis | `services.news_feed_service:*` | Kimi K2.5 | 88 |
| Swiss elections monitor | `services.swiss_disinfo_service:*` | Kimi K2.5, Claude Sonnet 4.5 | 139 |
| Auspex chat | `services.auspex_service:_generate_streaming_response` | Kimi K2.5, Claude Sonnet 4.5, Claude Opus 5 | 6 |
| Observer referee, forecast, Auspex routing, MCP tool suggestion | various `jev` use cases | Jev | 564 |
| Publisher country | `services.source_country:_ask_model` | Nova Lite | 14 |

Adverse screening is configured for `bedrock-kimi-k2-5` (`app/services/brand_screening.py:25`). Its
63 Haiku calls on 3–5 October went to Haiku 4.5, which is the configured fallback for that alias;
the log does not record why the fallback was used.

The brand decision judge (`app/services/brand_decision.py`) is off on bugfixing because
`BRAND_RELATION_DECISIONS` is not set. Where it is on, its default route is `nova-lite`.

## Could not verify

- Which AWS regions Bedrock actually served the `us.` cross-region profiles from. The log does not
  record it.
- Where TypeSafe and Firecrawl process data. Neither configuration states a region.
- The caller of the 3,053 Haiku calls logged as `unknown` (see 12).
- Calls made outside LiteLLM and the TypeSafe client. A code search for direct provider SDK calls was
  not part of this check.

## Queries used

```sql
-- 7-day call log by use case and model (run 7 October 2026, 10:48 CEST)
SELECT use_case, model, resolved_model, count(*) AS calls, round(sum(cost_usd)::numeric, 2) AS usd
FROM llm_usage_log WHERE created_at > now() - interval '7 days'
GROUP BY 1, 2, 3 ORDER BY calls DESC;

-- the analysis model setting
SELECT default_llm_model, inference_mode FROM keyword_monitor_settings WHERE id = 1;

-- groups with their own model
SELECT id, name, default_llm_model FROM keyword_groups
WHERE default_llm_model IS NOT NULL AND default_llm_model <> '';
```
