# Monolith article enrichment pipeline (rebuild-grade notes)

Canonical tree: `/home/orochford/tenants/bugfixing.aunoo.ai` (the `saasmvp-app/` subdirectory and every `*.bak*` file are out of scope). Database: `test` on bugfixing. Written 7 October 2026 from the code as it stands on branch `fix/market-monitor-voices-relevance` (HEAD `d58ffa8c`), plus read-only SQL. Where a doc disagrees with the code, the code wins; the doc discrepancies are collected in section 11.

All line numbers are from that tree on that date.

---

## 0. The pipeline in one page

When the keyword monitor, the RSS monitor or the retry sweep hands a batch of collected articles to `AutomatedIngestService.process_articles_batch`, each article goes through these steps in order. Every step can end the article's run with a terminal `ingest_status`, which is why the status column, not `analyzed`, is the thing to read.

Before any of the per-article steps, the batch itself pre-scrapes (paid Firecrawl) every article with 200 characters or less of collector text, so scraping happens **before** the relevance gate, not after it (`automated_ingest_service.py:1774-1793`). Only ledger hits and articles of configuration-blocked topics are spared.

| # | Step | Ends with (if it stops here) | Model |
|---|------|-----------------------------|-------|
| 1 | First insert of the collected row, with English translation of non-English title/summary | row exists, `analyzed=false`, `ingest_status` NULL | `nova-lite` (translation only) |
| 2 | Brand pre-decision hook (brand topics only) | brand outcome | see section 6 |
| 3 | Unknown-topic guard | `skipped_unknown_topic` | none |
| 4 | Configuration guard (topic's label lists must be non-empty) | `quarantined_config` | none |
| 5 | No-text guard | `enrichment_failed` | none |
| 6 | Rejected-candidate ledger (keyword route only) | nothing written, skipped | none |
| 7 | Quick relevance gate on title + collector summary | `filtered_relevance` or `relevance_check_failed` | DeBERTa embedding + `nova-lite` (hybrid relevance) |
| 8 | MBFC bias lookup, plus a scrape for any article the batch pre-scrape did not cover | (never stops) | none (table lookup; Firecrawl for scraping) |
| 9 | **AI analysis step** (`ArticleAnalyzer.analyze_content`) | sets `analyzed=true`, or records an error | `bedrock-kimi-k2-5` (Kimi K2.5 on Bedrock) |
| 10 | Final relevance re-score | `filtered_relevance` | same as step 7 |
| 11 | Quality check | (placeholder: always approves) | none |
| 12 | "Was it analysed?" check | `enrichment_failed` or `quarantined_config` | none |
| 13 | Save: one UPDATE writes labels, verdict, MBFC fields | `approved` | none |
| 14 | Embedding into `articles.embedding` (768 dimensions) | (failure is logged, not stored) | DeBERTa encoder service on :8001 |

Live volume on bugfixing, articles first seen in the 7 days to 7 Oct 2026:

| ingest_status | analyzed | rows | category NULL | sentiment NULL/empty | embedding NULL |
|---|---|---|---|---|---|
| filtered_relevance | false | 2,879 | 2,879 | 2,879 | 2,879 |
| social_evaluated | true | 1,709 | 1,659 | 0 | 1,709 |
| approved | true | 1,057 | 0 | 0 | 0 |
| (NULL) | false | 64 | 0 | 64 | 64 |
| enrichment_failed | false | 39 | 39 | 39 | 39 |
| filtered_relevance | true | 19 | 0 | 0 | 0 |

So about 1,076 of 5,767 rows (19%) went through the AI analysis step this week. Most of the rest are rejects the relevance gate kept on purpose as labelled data, and social posts that took the cheaper social evaluator instead. The 64 NULL-status rows are LinkedIn posts from the Market Monitor BrightData collector, written with a category already set and never passed through this pipeline. All 39 failures are "no summary or body text" (no-text guard). No row is in `quarantined_config` today.

The LLM cost ledger (`llm_usage_log`) shows 2,903 analysis calls costing $4.94 this week (about $0.0017 per article) and 2,896 separate publication-date calls costing $0.71, all on `moonshotai.kimi-k2.5`. No analysis call failed at the provider, and the largest reply was 492 output tokens, so truncation is not happening on this path.

---

## 1. Triggers, concurrency and caching

### 1.1 What starts enrichment

Enrichment is not a separate queue. It is the second half of ingestion and runs inline, in the same task that collected the batch. Every production path funnels into `AutomatedIngestService.process_articles_batch` (`app/services/automated_ingest_service.py:1682`).

| Trigger | Caller | Route tag | Notes |
|---|---|---|---|
| Keyword monitor (main path) | `app/tasks/keyword_monitor.py:934` → `auto_ingest_pipeline` (`:1339`) → `process_articles_batch` (`:1404`) | `keyword` | Runs only when `keyword_monitor_settings.auto_ingest_enabled` is true (`:1303-1309`). Social-only groups skip it (`:906-908`), and social posts inside mixed groups are split off to the social evaluator (`:914-922`). Started 5 s after boot (`app/core/app_factory.py:139`). |
| RSS feed monitor | `app/tasks/rss_feed_monitor.py:935` | `rss` | Translates on insert first (`:875-876`). |
| RSS route (manual run) | `app/routes/rss_feeds_routes.py:480` | (none) | |
| Enrichment retry sweep | `app/tasks/enrichment_retry_sweep.py:189` | `enrichment_retry` | Every 30 min, see 8.3. Scheduled at boot +60 s unless `ENRICHMENT_RETRY_SWEEP_ENABLED=0` (`app/core/app_factory.py:150-153`). |
| Brand judgment retry | `app/services/brand_retry.py:165` | varies | Called from the sweep (`enrichment_retry_sweep.py:209-210`). |
| "Auto-ingest now" button | `app/routes/auto_ingest.py:92-134` → `run_auto_ingest_task` (`app/services/background_task_manager.py:454`) → `process_articles_batch(..., topic=None, route="manual")` (`:497`) | `manual` | **Bug:** it stamps every article with `topic='general'` (`:491`), which is not a configured topic, so every article ends as `skipped_unknown_topic`. |
| Progressive (WebSocket) processing | `app/routes/keyword_monitor.py:3247` → `process_articles_progressive` (`automated_ingest_service.py:777`) | | Calls `_process_single_article_async` without the configuration guard map or ledger. Batches of 5, 300 s timeout. |
| Bulk topic re-process | `bulk_process_topic_articles` (`automated_ingest_service.py:2068`, calls batch at `:2156`) | | |
| Scripts | `scripts/reenrich_parse_failures.py:230`, `scripts/reenrich_filtered_articles.py:244`, `scripts/backfill_collection_gap.py:145`, `scripts/catchup_outage_window.py`, `scripts/brand_rollout/reenrich_no_text.py:76` | | All reuse `process_articles_batch`, so they behave exactly like ingest. |
| Debug endpoint | `POST /test-process-article` (`app/routes/keyword_monitor.py:446`, calls sync `analyze_article_content` at `:651`) | | The only live caller of the DeBERTa hybrid path (section 4). |

There is a second, older family of analysis entry points for **manual research** (the user pastes URLs, or the "bulk research" screen):

- `BulkResearch.analyze_bulk_urls` (`app/bulk_research.py:77`, analysis at `:237`), `analyze_bulk_urls_stream` (`:984`, analysis at `:1115`), `analyze_single_article` (`:1211`).
- `Research` (`app/research.py:400, 665, 1261, 1335`) builds its own `ArticleAnalyzer`.
- `AnalysisQueue` (`app/services/analysis_queue.py`, 3 workers, queue of 100) runs `analyze_bulk_urls` with `default_model("standard")`, which is `claude-sonnet-4-5` (`analysis_queue.py:110-117`, `app/model_tiers.py:33-37`).

These manual paths differ from auto-ingest in three ways that matter for a rebuild. They analyse the **full scraped page** (`article_content["content"]`, `bulk_research.py:237-250`), where auto-ingest analyses the collector summary. They use the summary length, voice and type the user chose, where auto-ingest hard-codes 50 words, "neutral", "informative". And they keep the model-extracted publication date (`bulk_research.py:230-234`), which auto-ingest throws away (see 2.6).

### 1.2 Concurrency

- `process_articles_batch` runs articles in slices of `MAX_CONCURRENT = 5` with `asyncio.gather`, each slice under a 300 s timeout (`automated_ingest_service.py:1801-1866`).
- Inside one article, the MBFC lookup and the scrape run in parallel (`:1249-1290`). The AI analysis step is wrapped in a 60 s `asyncio.wait_for` (`:1307-1313`). The embedding write has its own 30 s timeout (`:1454-1464`).
- The analyzer itself is synchronous. `_analyze_article_content_async` pushes it to the default thread pool with `run_in_executor` (`:1586-1602`).
- Scraping (Firecrawl) uses a dedicated 3-worker `ThreadPoolExecutor` (`:143-147`). Articles that arrive with more than 200 characters of collector `content` are not scraped (`:1774-1784`). A URL whose raw page is already in `raw_articles` is reused and marked `extraction_status='cached'` (`:2215-2218`).
- LiteLLM is called through a Router with `routing_strategy: least-busy` (`app/config/litellm_config.yaml:375`), `max_retries` 0 and a 30 s timeout default (`app/ai_models.py:869-890`).

**Gotcha: the 60 s timeout cannot cancel the thread.** `wait_for` gives up on the coroutine, but the analyzer thread keeps running its up to three model calls, the date call and a possible translation call, and then writes the 24 h cache. The article is meanwhile marked `analysis_error = "LLM analysis timed out"` and ends as `enrichment_failed`. The retry sweep 30 minutes later usually gets a cache hit and fixes it for free.

### 1.3 The 24-hour analysis cache

- Class: `AnalysisCache` (`app/analyzers/cache.py:14`). Directory `cache/` relative to the working directory, which for the systemd unit is the tenant root, so `/home/orochford/tenants/bugfixing.aunoo.ai/cache/` (144 MB, about 34,000 JSON files today, 185 written in the last 24 h).
- TTL 24 h (`cache.py:15`, default from `ArticleAnalyzer.__init__`, `article_analyzer.py:115`). Every production analyzer is built with `use_cache=True` (`automated_ingest_service.py:408, 1541`; `research.py:400, 665, 1261, 1335`). The model bias arena turns it off (`model_bias_arena_service.py:234`).
- Key: `"{uri}_{model_name}_{md5(sorted categories)[:8]}"` plus `sha256(article_text)[:16]` (`article_analyzer.py:194-199`). The category hash stops one topic's labels being served to another topic. The file path is `cache/<content_hash[:2]>/<safe_uri>_<content_hash>.json`, with long URIs shortened and hashed (`cache.py:31-48`).
- A hit is rejected (and the file deleted) when it is older than 24 h, when the model name or provider differs, or when the prompt template hash differs (`cache.py:64-84`). The template hash covers the `title_extraction` and `content_analysis` prompts (`prompt_templates.py:220-236`), so editing the analysis prompt invalidates the whole cache.
- A cache hit returns before the publication-date call and before title translation (`article_analyzer.py:201-204`), so the cached result is exactly what was stored at first analysis.
- Expired files are deleted only when read. `cleanup_expired()` exists (`article_analyzer.py:599-604`) but nothing calls it, so the directory only grows.
- `ArticleAnalyzer.get_cached_analysis` (`article_analyzer.py:653-678`) calls `cache.get(key)` with one argument and a different key format; it can never hit. Nothing in the pipeline calls it.

---

## 2. The AI analysis step

### 2.1 Entry: `_analyze_article_content_async`

File `app/services/automated_ingest_service.py:1534-1639`. Reached through the brand hook `analyze_or_skip` (`app/services/brand_ingest_hooks.py:218-250`), which skips the analysis for a headline-only brand item (it sets `analyzed=True` with no labels, `:226-228`) and, for an admitted brand item with no summary, analyses the scraped page from `raw_articles` instead (`:229-249`).

What it does:

1. Builds one `ArticleAnalyzer` per service instance on first use, with the model from `get_llm_client()` (`:1538-1541`, see 3.1).
2. Picks the text to analyse: **`summary` if present, else `content`** (`:1544`). This is the collector's summary, not the scraped page. Scraped text is saved to `raw_articles` (`:1299-1305`) but never analysed on this path, except when the article has no summary or content at all and the no-text guard substitutes the scraped page (`:1098-1118`). A collector that sends both a short `summary` and a full `content` (NewsFirehose, NewsData) therefore gets its summary analysed.
3. Returns the article unchanged, with no error recorded, when text or title is missing (`:1549-1551`). That later becomes `enrichment_failed` at step 12.
4. Fetches the topic's five label lists through the shared `Research` object (`:1562-1577`), see 2.4.
5. Runs `analyze_content` in a worker thread with `summary_length=50`, `summary_voice="neutral"`, `summary_type="informative"` (`:1586-1602`).
6. Writes these keys onto the article dict (`:1605-1626`): `summary` (the AI précis replaces the collector summary), `category`, `sentiment`, `future_signal`, `future_signal_explanation`, `sentiment_explanation`, `time_to_impact`, `time_to_impact_explanation`, `driver_type`, `driver_type_explanation`, `tags`, `analyzed=True`, and, for a non-English headline, `title` (English) plus `original_title`.
7. Tags are the model's tags with the collection-time matched keywords appended when missing, joined with commas (`_merge_matched_keyword_tags`, `:31-45`). This keeps a niche brand's name findable after the model rewrites the tags.
8. A `ConfigurationFault` from the analyzer is stored as `_configuration_fault` (`:1631-1635`); any other exception as `analysis_error` (`:1636-1639`). Neither raises.

### 2.2 `ArticleAnalyzer.analyze_content`

File `app/analyzers/article_analyzer.py:154-320`.

1. **Input checks** (`:160-179`). Empty text, title, source or URI raises `ArticleAnalyzerError`. An empty categories, future signals, sentiment, time-to-impact or driver-types list raises `ConfigurationFault` (a subclass, `:73-78`), before any model call.
2. **Cache lookup** (`:191-206`), section 1.3.
3. **Prompt build** (`prompt_templates.py:190-210`). The five lists are joined with ", ". Today's UTC date is injected as `{current_date}` ("7 October 2026"). For time-to-impact labels that contain a month range ("Short-term (6-18 months)") the code computes calendar windows ("from April 2027 up to April 2028") and injects them as `{time_to_impact_windows}` (`prompt_templates.py:22-45`), because the models miscounted months.
4. **Model call with parse retry** (`:228-247`). Up to 3 attempts. An empty reply or a reply missing a critical field triggers another attempt. After three misses it raises `ArticleAnalyzerError("Failed to generate parseable analysis after retries: …")`.
5. **Validation against the topic's lists** (`_validate_analysis_fields`, `:477-531`), section 2.5.
6. **Summary trim** to `int(summary_length * 1.2)` words, cut back to the last sentence end past the halfway mark (`:259-263`, `:567-583`). With the auto-ingest setting of 50 words, the stored précis is at most 60 words.
7. **Jev shadow on the summary** (`:265-280`). Each summary sentence is scheduled for a TypeSafe Jev faithfulness check against the article text by `app/services/extraction_check_shadow.py`, only when the text is at least `MIN_SOURCE_CHARS` long. Shadow only: it records and never changes the result.
8. **Publication date** (`:285`): a second model call, see 2.6.
9. **English headline** (`:291-294`): `english_title()` from `app/utils/title_translation.py:285-296` translates the title with `nova-lite` when the cheap offline detector says it is not English.
10. **Cache write** (`:299-307`).

### 2.3 Output fields and the parser

The prompt asks for 16 labelled lines in this exact order (`data/prompts/content_analysis/current.json`, mirrored in `prompt_templates.py:75`):

```
Title / Summary / Category / Future Signal / Future Signal Explanation /
Sentiment / Sentiment Explanation / Time to Impact / Time to Impact Explanation /
Driver Type / Driver Type Explanation / Political Bias / Political Bias Explanation /
Factuality / Factuality Explanation / Tags
```

Political Bias must be one of Left-leaning, Center-left, Center, Center-right, Right-leaning, Neutral, Mixed. Factuality must be one of Very High, High, Mixed, Low, Very Low. Both lists are fixed in the prompt, not per topic. Tags are 3 to 5 plain English phrases.

The parser (`parse_analysis`, `:337-475`) is a line-based "Key: value" reader:

- A line containing a colon starts a new field; other lines continue the previous one (`:350-368`). **Gotcha:** any summary sentence containing a colon ("Revenue: $3bn") starts a bogus field and truncates the summary there. The bogus key is kept as an extra field and dropped at the end.
- Headings are normalised: markdown, list numbers and stray punctuation are stripped (`:20-22`, `:52-57`), values lose surrounding asterisks (`:60-66`), and 20 heading variants are aliased onto canonical names (`_FIELD_ALIASES`, `:28-49`), e.g. "Relevant tags" → "tags", "Time horizon" → "time to impact".
- A single "Explanation"/"Rationale" block is copied into all four per-field explanations when they are missing (`:401-406`).
- Title fallback: parsed title → separately extracted title → the caller's title (`:410-415`).
- **Critical fields** Title, Summary, Category, Sentiment must be non-empty or the attempt fails (`:326`, `:417-423`). The comment at `:322-325` gives the reason: a row without them would still pass the observer agents' `category IS NOT NULL AND sentiment IS NOT NULL` gate.
- **Optional fields** (the other ten) are filled with "" and a warning (`:331-335`, `:425-432`).
- Keys are mapped to snake_case (`:435-466`). Tags become a list (`format_tags`, `:543-565`).

What the result dict holds: `title, summary, category, future_signal, future_signal_explanation, sentiment, sentiment_explanation, time_to_impact, time_to_impact_explanation, driver_type, driver_type_explanation, political_bias, political_bias_explanation, factuality, factuality_explanation, tags (list), uri, publication_date`, and optionally `original_title`.

**What is thrown away.** The model's `political_bias`, `factuality` and their explanations are never written to `articles` by any path; the `bias`/`factual_reporting` columns come from the MBFC table instead (step 8). The only place they are stored is the model-comparison tool's `model_bias_arena_results` table (`app/services/model_bias_arena_service.py:280-282`). The model's `publication_date` is also dropped on the auto-ingest path (2.6). So roughly a third of the output tokens per call buy nothing.

### 2.4 The topic's label lists ("ontology")

- Source: the `topics` array in `app/config/config.json`, read by `app/config/config.py:6-10` and indexed by normalised name in `Research.load_config` (`app/research.py:176-199`). The keys are `categories`, `future_signals`, `sentiment`, `time_to_impact`, `driver_types` (`automated_ingest_service.py:61-67`). Nothing reads them from the database; the DB `keyword_groups` table only maps groups to topic names.
- `Research.get_categories(topic)` and its four siblings (`research.py:943-…`) call `set_topic(topic)` and return the list from `topic_configs`. On any exception they return `[]`.
- Bugfixing has 8 topics in `config.json`, all with all five lists filled. Example, "AI and Machine Learning": 23 categories, 4 future signals, sentiment Positive/Negative/Neutral, time to impact Immediate (0-6 months) / Short-term (6-18 months) / Mid-term (18-60 months) / Long-term (60+ months), driver types Initiator/Accelerator/Catalyst/Inhibitor/Blocker.
- The ~40 "X - Brand Watch" topics and the "Brand Monitoring …" topics are not in `config.json`. Their news goes through the brand hooks or the Market Monitor collectors, and their social posts through the social evaluator.
- The `Research` object is cached per model name and shared by every article of the service (`automated_ingest_service.py:161-171`). `set_topic` mutates `current_topic`; on the async path this is safe because the five getters contain no `await`, but on the sync hybrid path they run on five threads at once (`:432-446`).
- The shared `Research` re-reads `config.json` only when a topic is missing (`:1027-1036`). A list edited in the UI for an existing topic is picked up by the retry sweep (which re-reads `config.json` every tick, `enrichment_retry_sweep.py:72-84`) but not by the long-lived keyword-monitor service until restart. The configuration guard uses the same cached `topic_configs`, so it agrees with the analyzer.

**Empty list behaviour.** The memory note "empty ontology ⇒ enriches zero silently" is out of date. Since work package 22 (1 Oct 2026) an empty list is caught twice:

1. Before any model call, per batch: `configuration_block_reason()` (`automated_ingest_service.py:72-94`) returns a reason when the topic config is missing, `enrichment_disabled` is set, or any of the five lists is empty or blank. `process_articles_batch` computes it once per topic (`:1718-1720`, `_configuration_block_reasons` `:1911-1934`, one warning per topic) and skips scraping for those URLs (`:1760-1764`). `_process_single_article_async` then stores the article as `ingest_status='quarantined_config'` with `enrichment_block_reason`, scores 0.0 and no model call (`:1066-1097`), and the batch counts it as `configuration_blocked`.
2. As a backstop inside the analyzer: `ConfigurationFault` (`article_analyzer.py:169-179`) → `_configuration_fault` → quarantined at step 12 (`automated_ingest_service.py:1376-1399`).

It is still silent in one sense: quarantined rows have `topic_alignment_score = 0.0`, so they are invisible to every reader (section 7), and no alert fires. `enrichment_retry_sweep.health_counts` (`:250-…`) is the only counter.

### 2.5 Validation against the lists

`_validate_analysis_fields` (`article_analyzer.py:477-531`) uses exact, case-sensitive string matching:

| Field | Value not in the topic's list |
|---|---|
| category | becomes "Other" ("Other" is always allowed) |
| future_signal | becomes "Other"; the original goes into the explanation if that is empty |
| sentiment | becomes "" |
| time_to_impact | becomes "" |
| driver_type | becomes "" |

**Gotcha:** an off-list sentiment becomes the empty string after the parser has already accepted it as present. The row is then stored with `sentiment = ''`, which passes `sentiment IS NOT NULL` gates although it carries no label. This week: 20 approved rows have category "Other", 23 have an empty time to impact, 1 an empty driver type, 0 an empty sentiment.

### 2.6 The publication-date call

`extract_publication_date` (`article_analyzer.py:618-651`) makes a second model call per analysed article with the `date_extraction` prompt on the first 10,000 characters (`prompt_templates.py:257-264`). It returns a day-precision ISO date or None, and never substitutes today's date (work package 7).

On the auto-ingest path the value is computed and then discarded: `_analyze_article_content_async` does not copy `publication_date` from the result (`automated_ingest_service.py:1605-1622`), and the step-13 UPDATE does not write it. That is about 2,900 Kimi calls and $0.71 a week on bugfixing that change nothing. The manual research paths do keep it.

### 2.7 Prompt storage and versions

- `PromptManager` (`app/analyzers/prompt_manager.py:28-36`) stores prompts on disk under `data/prompts/<type>/`, one JSON per version plus `current.json`.
- The code defaults in `PromptTemplates.DEFAULT_TEMPLATES` (`prompt_templates.py:52-124`) are written only when a prompt type has no version yet (`prompt_manager.py:276-294`). After that, **the file on disk is what runs**, and editing the Python default changes nothing on an existing site.
- On bugfixing, `data/prompts/content_analysis/current.json` is version 1.0.8 (created 1 Oct 2026); the code default is 1.0.6. The live prompt adds a rule to keep dates as precise as the article states them, and **drops the instruction to write the summary, explanations and tags in English**. The English output still mostly happens because the model follows the English prompt, but nothing asks for it. Two version files and a `.bak` in that directory are untracked in git.
- The prompt can be edited from the UI's prompt manager, which writes a new version and `current.json`.

---

## 3. Models, routing, fallback and cost

### 3.1 Which model enriches

`AutomatedIngestService.get_llm_client()` (`automated_ingest_service.py:193-221`) picks, in order:

1. an explicit override (none of the ingest callers pass one);
2. `keyword_monitor_settings.default_llm_model` for `id = 1` (`database_query_facade.py:999-1015`);
3. the first model in `get_available_models()`;
4. the literal `"bedrock-kimi-k2-5"`.

On bugfixing the settings row says `bedrock-kimi-k2-5`, temperature 0.2, max tokens 4096, inference mode `hybrid`, auto-ingest on, relevance floor 0.4. The alias resolves to `bedrock/moonshotai.kimi-k2.5` in `us-east-1` with `reasoning_effort`, `response_format` and `thinking` dropped (`app/config/litellm_config.yaml:252-257`).

The model is chosen once per service instance (the analyzer is cached), so a settings change needs a restart to reach the keyword monitor.

`model_tiers.py` (`fast = bedrock-kimi-k2-5`, `standard = premium = claude-sonnet-4-5`, overridable with `MODEL_TIER_FAST/STANDARD/PREMIUM`, `app/model_tiers.py:33-43`) is **not** consulted by auto-ingest. It decides the manual `AnalysisQueue` model (standard tier) and many other features.

The temperature and max-tokens values in the settings row are read by `get_llm_parameters()` (`automated_ingest_service.py:223-240`) but not passed to the analyzer. `LiteLLMModel.generate_response` calls `router.completion(model, messages, metadata, caching=False)` with no temperature or max tokens (`app/ai_models.py:1067-1073`), so the provider's defaults and whatever the yaml pins apply. The yaml pins neither for Kimi.

Title translation and English text use `nova-lite` (`app/utils/title_translation.py:33`).

### 3.2 Model capabilities ("caps")

`model_caps(name)` (`app/ai_models.py:56-117`) reads the yaml target behind a name and looks it up in `_CAPS_TABLE` (`:79-90`): family, context window, max output, whether it is a reasoning model, and whether it accepts temperature. Kimi K2 is listed as a reasoning model with a 256k window and 64k output. `is_reasoning_model` (`:120-125`) and `minimal_reasoning_effort` (`:35-53`) use it; for a real OpenAI gpt-5 the code adds `reasoning_effort` = "minimal" or "none" when the caller passes none (`:1061-1065`). For Kimi on Bedrock the yaml drops `reasoning_effort`, so nothing changes.

### 3.3 Fallback chain and circuit breaker

- Fallbacks are listed under `fallbacks:` in `litellm_config.yaml:299-…` and merged with `litellm_config.yaml.local`. For enrichment: `bedrock-kimi-k2-5` → `bedrock-claude-haiku` (a legacy alias for `bedrock/us.anthropic.claude-haiku-4-5-20251001-v1:0` with thinking disabled, `:203-211`) → `nova-lite` (`:306-308`). `nova-lite` itself falls back to Kimi then `nova-pro` (`:303-305`).
- The Router receives the fallbacks (`ai_models.py:880-891`), and `LiteLLMModel._try_fallback_model` (`:943-1002`) also walks them by hand after a circuit-breaker trip, rate limit, network error, context overflow or service error (`:1036-1050`, `:1145-1153`, `:1181-1189`, `:1201-1211`, `:1238-1248`).
- The circuit breaker (`app/utils/circuit_breaker.py:56-59`) opens after 5 consecutive failures for 300 s, and allows 3 trial calls half-open. Its state lives in the `llm_retry_state` table (`database_query_facade.py:11714`), so it is shared across processes on one site.
- **Gotcha:** when the breaker is open and no fallback succeeds, `generate_response` returns a warning string ("⚠️ … temporarily unavailable …", `ai_models.py:1049`) instead of raising. The analyzer treats it as a reply, finds no fields, retries twice more and fails with "Missing required fields". The article ends as `enrichment_failed` with that message.
- Authentication and budget errors raise `PipelineError(FATAL)` (`ai_models.py:1089-1115`). The analyzer re-raises it (`article_analyzer.py:313-316`), but `_analyze_article_content_async` catches every exception (`automated_ingest_service.py:1636-1639`), so a fatal error does not stop the batch. Every article in the batch fails individually.

### 3.4 The LLM cost ledger

`app/services/llm_usage_logger.py` installs global LiteLLM success and failure callbacks at startup (`app/core/app_factory.py:78-81`), plus an async `CustomLogger` (`llm_usage_logger.py:353-375`; before 28 Sep 2026 async calls were missed). It wraps `litellm.completion/acompletion` to record the calling function as `use_case` (`:155-214`), queues rows and inserts them from a daemon thread (`:277-350`) into `llm_usage_log` (columns `use_case, model, resolved_model, provider, prompt_tokens, completion_tokens, total_tokens, cost_usd, latency_ms, status, error_message, created_at`). A fallback price table covers models LiteLLM cannot price (`:73-…`, `_estimate_cost` `:229`).

Use cases that belong to this pipeline: `analyzers.article_analyzer:analyze_content`, `analyzers.article_analyzer:extract_publication_date_result` (and the older `extract_publication_date`), `services.hybrid_relevance_service:_compute_external_llm_score` (nova-lite, 9,219 calls, $0.86 a week), `services.hybrid_relevance_service:_compute_jev_shadow` (Jev, 13,871 calls, $0.77). Translation calls go through `AIModelFactory` and show up under the translation module's name.

---

## 4. The DeBERTa classifier path (local small model)

There are two different DeBERTa things on this server, and the docs mix them up.

1. **The classifier** (`models/enrichment_model/final/`, base `microsoft/deberta-base`, max length 256, four heads with 4 / 6 / 5 / 15 labels for sentiment / time to impact / driver type / future signal, `model_config.json`). Loaded in-process by `EnrichmentService` (`app/services/enrichment_service.py:37-38`, `:124-211`), never over HTTP.
2. **The encoder service** on `127.0.0.1:8001` (`deberta-encoder.service`, `/opt/deberta-encoder`, `ml.encoder_service:app`, one uvicorn worker). It only produces 768-dimension embeddings (section 5). It does no classification.

### 4.1 How the classifier was meant to be used

`HybridEnrichmentService.enrich_article` (`app/services/hybrid_enrichment_service.py:119-236`) routes each of the four fields separately. A field with at least `DEBERTA_THRESHOLD = 500` training samples for the topic (`:54`, counts from `training_bootstrap_service`, cached) goes to DeBERTa; the rest go to an LLM "bootstrap" call that also stores the answer as a training sample, or to a local Qwen model when `inference_mode = 'local'`. The sync `analyze_article_content` (`automated_ingest_service.py:285-515`) then runs the full LLM analysis anyway and overrides the four fields with the small model's answers (`:490-498`), recording `enrichment_sources` and a confidence tracker entry. With `use_adaptive_enrichment=False` it would use `EnrichmentService` directly with a 0.6 confidence floor (`:367-398`).

### 4.2 What actually runs

None of that is on the live path. `_process_single_article_async` calls `_analyze_article_content_async`, which is LLM-only. The sync `analyze_article_content` is called only from the `/test-process-article` debug route (`app/routes/keyword_monitor.py:651`) and two scripts (`scripts/cleanup_ontology_artifacts.py:349`, `scripts/test_auto_ingest_summary.py:53`). The database agrees: all 12,752 approved articles of the last 90 days have `enrichment_sources = '{}'`, and `enrichment_training_samples` (104,923 rows) last grew on 3 Feb 2026. The `inference_mode` setting (`hybrid`) still matters, but only for the relevance gate.

A rebuild can drop the classifier, the hybrid service, the bootstrap service and the `enrichment_sources` column without changing any stored output.

---

## 5. Embeddings

- **Model and service:** `microsoft/deberta-base` served by `deberta-encoder.service` on `127.0.0.1:8001` (`systemctl cat deberta-encoder.service`; `DEBERTA_ENCODER_URL` default in `app/vector_store_pgvector.py:44`). The client posts `{"title", "description": "", "content"}` to `/encode` with a 30 s timeout and requires a 768-element list back (`:48-91`). There is deliberately no OpenAI fallback: a 1536-dimension or random vector would corrupt every search (`:40-43`).
- **Column:** `articles.embedding vector(768)`, index `articles_embedding_hnsw_idx` HNSW `vector_cosine_ops` (m 16, ef_construction 64). `articles.embedding_model` exists but the writers do not set it.
- **Input:** `build_article_encoder_input` (`:106-139`): title = real title; content = `"Tags: …"` first (so the matched keywords survive truncation), then the raw scraped page if there is one, else the summary, truncated to 8,000 tokens (`:170-…`).
- **When written:** only at step 14, after the save succeeded for an approved article (`automated_ingest_service.py:1454-1464`, `_upsert_to_vector_db_async` `:1664-1680`, `upsert_article_async` `vector_store_pgvector.py:299-337`). The manual research path indexes in a batch after saving (`bulk_research.py:634-676`). Rejected, quarantined, failed and social rows are never embedded. Today 47,446 of 47,448 approved rows have an embedding.
- **Failure handling:** `upsert_article_async` catches its own exceptions and only logs ("Async vector upsert failed …", `:336-337`), so the "fail loud" comment is true for the sync path and the reindex scripts but not for ingest. The article stays approved with a NULL embedding, and nothing retries it. The cron health check `embedding_health_check.sh` (every 30 min at :15 and :45, `/home/orochford/bin/`, source `scripts/embedding_health_check.sh`) catches a dimension mismatch, a dead encoder, vector-write errors in the journal and an invalid HNSW index. It deliberately does not count unembedded approved rows.
- **Search side:** HNSW post-filter starvation on pgvector 0.6.0 is handled by switching to an exact scan below `PGVECTOR_EXACT_SCAN_MAX` (40,000) matching rows (`vector_store_pgvector.py:340-363`).
- **Reindex / repair:** `scripts/embedding_768_postbackfill.py` checks the column width, fill rate and index and builds the index concurrently if missing. `scripts/reindex_chromadb.py` (still named in CLAUDE.md) is a ChromaDB-era script; see section 11 for whether it still works.
- **Stale doc in code:** the module docstring of `vector_store_pgvector.py:1-14` still says `vector(1536)` and OpenAI `text-embedding-3-small`.

---

## 6. Other enrichers

These labellers write to an article outside the AI analysis step. Counts in this section use `submission_date` within 7 days (a text comparison, because the column is TEXT), so they differ slightly from the `first_seen_at` counts in section 0.

### 6.1 English translation (at first insert)

- **What:** translates a non-English title and summary at the first insert, keeping the originals in `original_title` / `original_summary`. Detection is offline (non-Latin script, accents, English function words); only doubtful text goes to the model (`app/utils/title_translation.py:1-23`). A social post's title is taken from its translated body instead of a second call (`:299-…`).
- **Trigger:** `facade.create_article` before the INSERT (`app/database_query_facade.py:495-502`); the RSS monitor (`app/tasks/rss_feed_monitor.py:875-876`); market collection (`app/services/market_collect.py:269-300`). The analysis step translates the headline again only if it is still not English (`article_analyzer.py:291-294`).
- **Model:** `nova-lite` (`title_translation.py:33`), limit 3,000 characters per text (`:75`).
- **Columns:** `title`, `summary`, `original_title`, `original_summary`. This week 85 of 1,057 approved rows carry an `original_title`.
- **Gotcha:** the live analysis prompt no longer tells the model to write in English (section 2.7), so the précis of a non-English article depends on the model's habit.

### 6.2 MBFC media bias

- **What:** looks up the outlet in the `mediabias` table (4,435 rows) by exact domain, then fuzzy domain, then the same on disabled rows (`app/models/media_bias.py:325-402`).
- **Trigger:** step 8 of the pipeline, only for articles that passed the quick relevance gate (`automated_ingest_service.py:242-282`, `:1253-1255`). Saved by `build_enrichment_update` (`app/services/async_db.py:645-647`). A second writer, the Brand Watcher classification run, fills the same fields with COALESCE (`app/routes/brand_watcher_routes.py:2630-2645`). Manual research does its own lookup by URL then source name (`app/bulk_research.py:260-280`).
- **Model:** none.
- **Columns:** `bias`, `factual_reporting`, `mbfc_credibility_rating`, `bias_source`, `bias_country`, `press_freedom`, `media_type`, `popularity`. Coverage: about 23% of approved articles this week.
- **Gotchas:** a lookup that matches a disabled source re-enables it (`media_bias.py:368-399`), so reads change the table. `bias_source` holds three kinds of value: the MBFC outlet, `owned:<domain>` (`app/services/bw_owned.py:66`, `app/services/market_corpus.py:1036`) and `official:<domain>` (`app/services/bw_official_sources.py:27-29`); 1,709 of 2,566 non-null values this week are `owned:*`. The ingest code used to read the wrong keys and leave `bias_source`/`bias_country` NULL; fixed at `automated_ingest_service.py:263-265`.

### 6.3 Social post evaluation (instead of the AI analysis step)

- **What:** one cheap model call per Reddit, Bluesky, xpoz or Telegram post returns relevance 0-1, sentiment and author role (`app/services/social_eval_service.py:1-15`). Posts matching the brand's exclude terms or never naming the brand score 0 with no call (`:330-347`, `:611-612`). A negative verdict with relevance ≥ 0.4 gets a second "supervisor" call checking target and spam (`:435-466`).
- **Jev pre-screen:** with `SOCIAL_JEV_PREFILTER_MIN=0.1` and `SOCIAL_JEV_ACCEPT_MIN=0.91` (set here), Jev rejects clear misses and accepts clear non-negative hits without a model call (`:367-382`, `_JEV_NEGATIVE_TO_MODEL = 0.3` at `:1032`).
- **Trigger:** inline after a group's collection when it uses a social provider (`app/tasks/keyword_monitor.py:1597-1609`); hourly retry `sweep_unevaluated_social` from the Brand Watcher monitor (`social_eval_service.py:976-1020`, `app/tasks/brand_watcher_monitor.py:1239-1244`); per-company mention scoring `evaluate_mentions_for_group` (`social_eval_service.py:654-793`, `brand_watcher_monitor.py:1250-1273`). The keyword monitor keeps social posts out of the news pipeline (`keyword_monitor.py:906-922`).
- **Model:** group's `keyword_groups.default_llm_model`, else `SOCIAL_EVAL_MODEL`, else `gemma3:4b` (`social_eval_service.py:26`, `:304`; `keyword_monitor.py:1603-1604`). **On bugfixing `SOCIAL_EVAL_MODEL=claude-haiku-4-5`**, against the "avoid Haiku 4.5" cost rule; one group (23) uses `bedrock-kimi-k2-5`.
- **Columns:** `topic_alignment_score` and `keyword_relevance_score` (both = relevance), `sentiment`, `ingest_status='social_evaluated'`, `analyzed=true`, `author_role`, `author_role_reason` (`:641-646`). No category, summary, embedding or MBFC data. Mention scoring writes `bw_entity_mentions` (`:761-766`).
- **Gotchas:** `keyword_relevance_score` means embedding similarity for news but the model's relevance for social posts. A post settled by Jev gets no role from this path (`:374-382`). If the model is unreachable posts stay unscored and are retried by the sweep (`:575-576`).

### 6.4 Author role (Brand Voices)

- **What:** who wrote a social post, from 14 roles (`AUTHOR_ROLES`, `social_eval_service.py:39-54`).
- **Trigger and model:** with `VOICES_ROLE_MODEL=jev` (set here) TypeSafe Jev decides the role, with a deterministic rule that #ad/#sponsored posts are `brand` (`app/services/author_role_jev.py:1-19`, `:96-100`, `:144`). Called from the social evaluator (`social_eval_service.py:627-638`, `:749-757`, `:505-508`). Re-read after persona changes by `app/services/voices_reread.py:123` (route `app/routes/voices_personas_routes.py:119-124`). Backfill `scripts/backfill_author_roles.py` (dry run unless `--apply`).
- **Columns:** `articles.author_role`, `author_role_reason`. `app/services/audience_voices.py` only reads and relabels at read time (glassdoor → employee, bare paper shares → paper_share, registry accounts take their registry role, `:445`, `:479-482`, `:584-608`).
- **Live:** journalist 752, unknown 412, brand 95, professional 54, others under 25 each; 455 of 1,832 social rows this week have no role.

### 6.5 Publisher country

- **What:** country of the publisher per domain, by `manual` → `tld` → `mediabias` → `model` → `model+` (model with two headlines), else `unresolved`; cached in `news_source_countries` (`app/services/source_country.py:20-41`, `:210-216`, `:381`).
- **Model:** `SOURCE_COUNTRY_MODEL`, default `nova-lite` (`:56`, `:289-291`); unset here.
- **Trigger and columns:** only the RSS monitor stamps `articles.source_country` and `source_country_method`, at insert (`app/tasks/rss_feed_monitor.py:660-689`, `:803-804`). The keyword monitor resolves countries only to filter market groups and never stamps the row (`keyword_monitor.py:330-385`). About 51% of approved rows have a country.

### 6.6 Publications bucket (scholarly items)

- **What:** papers and chapters are put in a `Publications` category, never a news category. Rule `is_scholarly_article` (journal domain, `doi.org/`, Crossref/OpenAlex/Semantic Scholar/PubMed source, or a Google News title ending in a journal platform), `app/services/opoint_brand_matcher.py:73-90`.
- **Trigger:** the Brand Watcher classification run (`brand_watcher_routes.py:2655-2663`, scheduled from `brand_watcher_monitor.py:186-221`), and official-source polling for Crossref/OpenAlex (`bw_official_sources.py:84-98`, `:949`; about every 5 monitor cycles, `brand_watcher_monitor.py:1287-1292`).
- **Model:** none. **Table:** `bw_article_categories` (method `scholarly`, confidence 1.0), not `articles.category`. Alerts exclude the category (`brand_watcher_monitor.py:787`).

### 6.7 Brand Watcher classification and adverse screening

- **What:** per-brand categories for articles in brand scope. Methods in order: scholarly → DeBERTa BW classifier → LLM → keywords (`brand_watcher_routes.py:2655-2700`). The classifier directory `models/brand_watcher_classifier/final` **does not exist on bugfixing**, so it never loads (`app/services/brand_watcher_classifier_service.py:19-20`, `:107-108`).
- **Model:** `_llm_categorize_article` uses `bedrock-kimi-k2-5` (`brand_watcher_routes.py:2927-2943`).
- **Table:** `bw_article_categories` (`:2719-2728`). Methods this week: market_name_match 991, market 560, owned_domain 399, llm_semantic 21.
- **Adverse screening:** `app/services/brand_screening.py`, model `bedrock-kimi-k2-5` (`:26`) with a keyword fallback (`:169-172`), run per categorized article (`brand_watcher_routes.py:2735-2740`); writes `bw_article_risks` and `bw_screening_verdicts` (4 verdicts this week, no risks).
- **Brand relation decisions** (`app/services/brand_decision.py`, store `brand_decision_store.py`, the `pre_decide`/`save_enriched` hooks): gated by `BRAND_RELATION_DECISIONS` (`brand_decision.py:62-64`), **not set on bugfixing, so off**. Judge model `BRAND_JUDGE_MODEL` → `HYBRID_RELEVANCE_LLM_MODEL` → `nova-lite` (`:316-327`); verdicts on `keyword_article_matches`.
- **Brand mention gate** (`app/services/brand_mention_gate.py:11-55`): changes the relevance result in memory during ingest (`automated_ingest_service.py:644-647`) and social evaluation (`social_eval_service.py:342`); no table.
- **Language recovery:** `app/services/bw_language_recovery.py` re-judges recent low-scored non-English articles with `bedrock-kimi-k2-5` (`:55`) and rewrites `topic_alignment_score` and `llm_processing_metadata.lang_recovery` (`:96-110`), about hourly, 20 per run (`brand_watcher_monitor.py:1302-1305`). It can therefore make a rejected row readable after the fact.

### 6.8 Entity extraction (Entity Intelligence)

- **What:** deterministic term matching finds company mentions; no model is called during extraction (`app/services/entity_ingest.py:1-16`; event extractors `app/services/entity_event_extractors/__init__.py:1-24`).
- **Trigger:** after a market collection run (`market_collect.py:175` → `entity_ingest.on_run_closed`, `entity_ingest.py:665-700`); `process_pending` in the BW monitor (`brand_watcher_monitor.py:1266`); events via `market_monitor` when events are enabled (`app/tasks/market_monitor.py:1046-1053`).
- **Tables:** `bw_entity_content_links`, `bw_entity_mentions`, `bw_entity_social_identities`, `bw_entity_link_attempts`, `bw_entity_events`, `bw_entity_event_entities`, `bw_entity_event_evidence`, `bw_market_events`, `bw_event_vendors`. Mention relevance/sentiment comes from 6.3.
- **Flags:** `app/services/entity_flags.py:26-33`; on bugfixing all of `ENTITY_INTELLIGENCE_ENABLED`, `_CANONICAL_READ`, `_MENTION_READ`, `_SOCIAL_ENABLED`, `_EVENTS_ENABLED` are true. 2,571 mentions and 225 events this week.
- Earned trade-press review: `market_post_review.review_earned` (`app/services/market_post_review.py:1376`), model `MARKET_POST_REVIEW_MODEL` → `KEYWORD_MONITOR_DEFAULT_MODEL` → `bedrock-kimi-k2-5` (`:270-272`), writes `articles.social_meta.follow_verdict` (`:938-941`).

### 6.9 Story identity and duplicates

- **`app/services/story_identity.py`:** records `url_key` (URL without tracking parameters), `duplicate_of` (first copy of the same story in the topic, by title similarity in a date window; URL only for social, `:316-354`) and `source_type` (`news` / `press_release`). Blocks nothing. Runs at insert (`database_query_facade.py:484`, `:5251`), as a sweep after every group check (`keyword_monitor.py:1617-1623`) and from `scripts/backfill_story_identity.py`. Readers apply it through `article_visibility` (section 7.2); `STORY_PR_DEFAULT` (default `hide`) sets press-release visibility (`:238`).
- **`app/services/article_identity.py`:** at insert, `resolve_identity` (`:216`) picks the identity (platform post id, DOI, or canonical URL) so a repeat lands on the existing row; `record_observation` (`:317`) writes `article_observations` and `article_url_aliases` and sets `canonical_url`, `identity_method`, `record_type`, `last_seen_at` with COALESCE (`:349-376`).
- **Live:** `url_key` on 100% of rows; 148 copies and 126 press releases this week.

### 6.10 Jev (TypeSafe) shadows and decide flags

Client `app/services/typesafe_client.py`, model `TYPESAFE_MODEL=jev-1.13.0` here (`:48-49`), spend logged to the ledger (`:98-100`).

Shadows record an answer and change nothing:

| Shadow | Flag | Table | Touches articles? |
|---|---|---|---|
| Relevance (`_compute_jev_shadow`) | `TYPESAFE_SHADOW_RELEVANCE=1`, rate 1.0 (`hybrid_relevance_service.py:102-103`, `:942-960`) | `relevance_confidence_readings` | every scored article |
| Summary faithfulness (enrichment) | `TYPESAFE_SHADOW_EXTRACTION` (`article_analyzer.py:265-280`) | `extraction_check_shadow` (1,853 enrichment rows) | every analysed article with enough text |
| Briefing candidates / citations, issue merge, identity, Auspex compaction | `TYPESAFE_SHADOW_*` | `briefing_candidate_shadow`, `briefing_claim_shadow`, `issue_merge_shadow`, `entity_identity_shadow`, `auspex_compaction_shadow` | no |

Decide flags change output:

| Feature | Flag (on here) | Effect |
|---|---|---|
| Relevance accept tier | `TYPESAFE_DECIDE_RELEVANCE_ACCEPT=1`, min 0.8 (`hybrid_relevance_service.py:108-109`, `:907-919`) | accepts borderline articles without the nova-lite call; never rejects. 184 of 1,136 readings this week. |
| Social pre-screen | `SOCIAL_JEV_*` | skips the social model (6.3) |
| Author role | `VOICES_ROLE_MODEL=jev` | sets `author_role` (6.4) |
| Observer referee | `TYPESAFE_DECIDE_REFEREE=1` (`signal_referee_shadow.py:115-145`) | holds alerts out of email |
| Auspex rerank / route | `TYPESAFE_DECIDE_RERANK`, `_ROUTE` | retrieval order, chat routing |
| Alert narration check | `TYPESAFE_VALIDATE_NARRATION=1` (`brand_alert_service.py:144-193`) | validates alert text |

### 6.11 Credibility and trust signals

The monolith has no per-article trust labeller that writes to the database. `app/mcp_access/trust_tools.py:1-17` forwards URLs to the saas Trust Signals API and caches answers in memory for an hour. The stored credibility-like fields are MBFC's `mbfc_credibility_rating` and `factual_reporting`, and `quality_score` (always 0.8 from the placeholder, section 8.5).

### 6.12 The relevance gate, for reference

`app/services/hybrid_relevance_service.py` scores before and after the analysis step. Tiers: embedding similarity with `all-MiniLM-L6-v2` plus a DeBERTa relevance classifier, combined 0.6 / 0.4 (`:44-46`, `:812-830`); confident only below 0.20 or above 0.85 (`:837-840`); Jev accept tier; then the LLM fallback, `HYBRID_RELEVANCE_LLM_MODEL` default `nova-lite` (`:605-606`, unset here). `inference_mode` (`hybrid` here) allows the fallback (`automated_ingest_service.py:573-581`). `topic_alignment_score` is the verdict; `keyword_relevance_score` is the raw embedding similarity, not a keyword score (`:612-615`). Threshold = group `min_relevance_threshold`, else the settings row (0.4) (`:1994-2013`). No engine answering gives `unavailable`, not a reject (`hybrid_relevance_service.py:933-937`; `automated_ingest_service.py:600-604`).

### 6.13 Other writers to `articles` after insert

| Writer | Columns | Trigger |
|---|---|---|
| `tasks/embedding_backfill.py:85` | `embedding` | backfill task |
| `vector_store_pgvector.py:1333`; `routes/vector_routes.py:1081` | `embedding = NULL` | delete / reset |
| `social_engagement_refresh.py:296`, `:305` | `social_meta` engagement | BW monitor (`brand_watcher_monitor.py:1229-1232`) |
| `market_collect.py:257`, `:300` | `social_meta`; translated `title`/`summary` + originals | market collection |
| `database.py:1701` (`add_article_tag`) | `tags` | observer-agent matches (`vector_routes.py:4752-4756`) |
| `routes/vector_routes.py:3267`, `:3278` | `user_preference`, `preference_date` | user thumbs |
| facade `update_article_fields` (`:5190`), `update_article_by_url` (`:5176`), `update_feed_article_data` (`:1961`), `update_article_llm_status` (`:11660`) | hand-edited fields | routes |
| facade `save_approved_article` (`:1029`), `update_ingested_article` (`:1120`), `create_article` merge (`:556`) | enrichment and quality fields | older pipeline / insert merge |
| scripts `backfill_enrichment`, `backfill_english_text`/`_titles`, `restore_social_text`, `normalize_publication_dates`, … | as named | manual |

---

## 7. What "analysed" means, and who can read the row

### 7.1 Columns

There is no single "enriched" flag that readers agree on. These are the facts a rebuild needs:

- `analyzed` is set true by the step-13 UPDATE (`async_db.py`, `build_enrichment_update`, `plain("analyzed", …True)`) and by the social evaluator. It is set false by every terminal-reject write (`save_below_threshold_article`, `async_db.py:420-…`, literal `False`). It is also set true with **no labels** for headline-only brand items (`brand_ingest_hooks.py:226-228`, `:239-241`).
- `ingest_status` is the reliable discriminator: `approved` (fully enriched), `filtered_relevance`, `relevance_check_failed`, `enrichment_failed`, `quarantined_config`, `skipped_unknown_topic`, `social_evaluated`, `manual` (manual research), or NULL (inserted but never processed).
- The AI analysis step guarantees non-empty `title`, `summary`, `category`, `sentiment` at parse time (`article_analyzer.py:326`), but validation can blank `sentiment` afterwards (2.5).
- The "observer" readers (the signal runner behind Observer Agents) require `category IS NOT NULL AND sentiment IS NOT NULL`, or, since the social fix, `category IS NOT NULL OR social_meta is a real object`: `app/routes/vector_routes.py:4461` (`run_signal_instructions`), `:5386` (`_run_signals_background`), `:5624`, `:5658` (`_run_signal_instruction_internal`). The strict category-and-sentiment form is in `analyze_incidents` (`:1962`), `analyze_real_time_signals` (`:3846`), `debug_articles` (`:4067`, `:4081`), and in `threat_intelligence_service.py:1759-1868`, `geopolitical_service.py:1348-1805` and `topic_report_pptx.py:835-842`. Social posts have sentiment but no category (1,659 of 1,709 this week), so the strict form excludes them.

### 7.2 The readable-articles predicate

`app/services/article_visibility.py` is the one shared rule for "may a reader show this row?" It ignores `analyzed` and labels entirely and looks at three things:

1. `topic_alignment_score IS NULL OR topic_alignment_score >= 0.4` (`RELEVANCE_FLOOR`, `:38`, `:55-61`). A NULL score is readable because it means the gate never ran.
2. A press release (`source_type = 'press_release'`) is readable only in topics that accept press releases (`press_release_topics()` from `story_identity.py`, `:50-61`).
3. A copy (`duplicate_of` set) is hidden when its original is readable (`:64-80`).

Three forms: `readable_clause(table)` for SQLAlchemy, `readable_sql(alias)` for raw SQL, `is_readable(row)` for rows in hand (which treats every copy as unreadable, `:101-121`). A narrower `story_clause`/`story_sql` (`:132-161`) applies only rules 2 and 3, for readers that never used the relevance floor.

Because every terminal reject writes a score of 0.0 (quarantined, failed, unknown topic, relevance-check failed), the predicate hides all of them. An `enrichment_failed` row from the post-quality check path keeps the real relevance score, which is above the floor, so it **is** readable, with NULL labels and the collector summary.

Readers that use it (code search for the module name):

- `app/database_query_facade.py`: `get_articles_with_dynamic_limit` (story, `:809`), `get_articles_by_topic` (`:1304-1327`), `search_articles` (`:5650`, optional with `readable_only`), `get_recent_articles_by_topic` (`:5744`), `get_articles_with_bias_data` (`:5814`), `get_articles_with_future_signals` (`:5870`), the news-feed date-range and chronological readers and their counts (`:5967-6419`, readable for the main list, story for the rest).
- `app/vector_store_pgvector.py` (semantic search, 4 uses).
- `app/routes/news_feed_routes.py` (3 uses), `app/tasks/keyword_monitor.py` (1), `app/mcp_access/judgment_tools.py` (1), `app/services/story_identity.py` (itself).

Readers that do not use it write their own filter; the many raw-SQL services in 7.1 are examples. The Brand Watcher routes, dashboard and briefing composer keep their own copies of the 0.4 floor (`article_visibility.py:10-15`, `:37`).

---

## 8. Failure handling

### 8.1 Statuses and where they are written

| Status | Written at | Score written | Counts an attempt | Retried by the sweep |
|---|---|---|---|---|
| `skipped_unknown_topic` | `automated_ingest_service.py:1020-1064` (also `:419-428` sync) | 0.0 | no | no |
| `quarantined_config` | `:1066-1097` (pre-check) and `:1376-1399` (analyzer refused) | 0.0 / unchanged | no | yes, once the topic's lists are filled, no cap |
| `enrichment_failed` (no text) | `:1119-1147` | 0.0 | yes (+1) | yes, up to the cap |
| `relevance_check_failed` | `:1226-1247` | 0.0 | no | no |
| `enrichment_failed` (analysed=false after quality) | `:1400-1431` | real score | yes (+1) | yes, up to the cap |
| `filtered_relevance` | `:1180-1225`, `:1492-1517` | real score | no | no (separate script `reenrich_filtered_articles.py`) |

All of these go through `AsyncDatabase.save_below_threshold_article` (`app/services/async_db.py:420-…`). It upserts on `uri`, sets `analyzed = false`, stores `enrichment_block_reason`, adds the attempt count to `enrichment_attempts`, and sets `first_seen_at` only on insert. Its `ON CONFLICT … WHERE articles.topic = EXCLUDED.topic OR articles.ingest_status IS DISTINCT FROM 'approved'` stops one topic's rejection from demoting a row another topic approved. Before 8 Sep 2026 the function overwrote every status with `filtered_relevance`.

The error text ends up in `overall_match_explanation` ("Enrichment failed: …"). The older `llm_status`, `llm_error_type`, `llm_error_message` columns and the `llm_processing_errors` table are not written by this path.

### 8.2 The approved write

`build_enrichment_update` (`app/services/async_db.py:599-…`) builds one UPDATE. The title, original title, summary and original summary use `COALESCE(new, old)`, so a NULL never wipes them; a placeholder title starting "Article from" is replaced by NULL first (`:219-225`). It always sets `auto_ingested = TRUE`, `ingest_status`, `enrichment_block_reason` (cleared), extraction provenance, quality and MBFC columns.

The **verdict** columns (`topic`, `topic_alignment_score`, `keyword_relevance_score`, `confidence_score`, `overall_match_explanation`) and the **label** columns (`category, sentiment, future_signal, future_signal_explanation, sentiment_explanation, time_to_impact, time_to_impact_explanation, driver_type, driver_type_explanation, tags`, `_LABEL_COLUMNS` `:594-596`) move only when `_REFILE` holds (`:581-582`): the row is not yet approved, or it is already filed under this topic, or this topic's score beats the stored one. An article matched by two topics therefore keeps the labels of the topic it is filed under. Before 1 Oct 2026 the labels were written unconditionally; on wileytest 190 of 9,035 approved rows carried another topic's category.

After a successful save, `record_group_relevance` writes the verdict onto the `keyword_article_matches` row for each group of that topic (`async_db.py`, called at `automated_ingest_service.py:1443-1445`).

### 8.3 The retry sweep

`app/tasks/enrichment_retry_sweep.py`:

- Every `ENRICHMENT_RETRY_SWEEP_MINUTES` (30) minutes, first tick one interval after boot (`:274-…`).
- Reads up to `max(budget*4, 50)` rows in `quarantined_config` or `enrichment_failed`, newest `submission_date` first (`:95-116`, `:167`).
- Picks at most `ENRICHMENT_RETRY_BUDGET` (50) of them (`select_candidates`, `:119-133`). A quarantined row retries only when its topic's lists are now filled; a failed row retries while `enrichment_attempts < ENRICHMENT_MAX_ATTEMPTS` (3), and never while its topic is blocked (`should_retry`, `:50-69`). The topic config is re-read from `config.json` each tick (`:72-84`).
- Re-runs them through `process_articles_batch(route="enrichment_retry")` grouped by topic, with the topic's monitored keywords (`:176-198`). The retry article carries only the stored collector summary (`_article_dict`, `:136-146`), so it gets the same text as the first attempt, plus whatever the scrape adds.
- Then retries unavailable brand judgments (`app/services/brand_retry.py`, `:209-213`) and writes a `collection_runs` record with provider `enrichment_retry` (`:237-243`).

**Gotchas.** Rows that have used up their attempts stay in the candidate window forever, because the query does not filter on the attempt count. With enough of them among the newest 200 rows, older retryable rows are never reached. Today the table holds 61 rows at 3 attempts and 5 rows at 10 to 20 attempts. Counts above 3 mean some route other than the sweep re-ran those rows (every failure write adds one attempt, `async_db.py` `save_below_threshold_article`), so the cap limits only the sweep, not re-collection.

### 8.4 Parse failures and reasoning-model truncation

- The analyzer retries an empty or unparseable reply up to 3 times (2.2, step 4). The comment cites Kimi/Nova on Bedrock returning unreadable content about 1 call in 8.
- `scripts/reenrich_parse_failures.py` re-runs articles that failed parsing before the retry existed.
- Truncation of reasoning models (hidden reasoning tokens eating `max_tokens`) is handled for JSON stages by `parse_stage_reply` and `salvage_json_array` (`app/ai_models.py:190-270`), which detect `finish_reason = length` and salvage complete items. The analysis step does not use them because it passes no `max_tokens` and reads plain "Key: value" text. The ledger shows no truncation risk for it today (largest reply 492 tokens).
- An article that ends with `analyzed = false` but passed relevance and quality is the "silent failure" case. It is now written as `enrichment_failed` with the analysis error in the explanation (`automated_ingest_service.py:1400-1431`); before 8 Sep 2026 the row stayed NULL and the ingest loop re-selected it every cycle.

### 8.5 The quality check

`_quality_check_article_async` (`automated_ingest_service.py:1655-1662`) is a placeholder that always returns `quality_score 0.8, approved True`. The real `quality_check_article` (`:691-730`) is never called by the async path. So `quality_score = 0.8` on an approved row means "not checked". A separate post-ingest spot check, `DataQualityService`, samples saved articles when a batch saves at least 3 (`app/tasks/keyword_monitor.py:942-960`); it records findings and does not change the rows.

---

## 9. Configuration reference

| Setting | Where | Effect on enrichment |
|---|---|---|
| `keyword_monitor_settings.default_llm_model` | DB, id 1 | Analysis model (bugfixing: `bedrock-kimi-k2-5`) |
| `keyword_monitor_settings.auto_ingest_enabled` | DB | Turns the keyword-route pipeline on |
| `keyword_monitor_settings.inference_mode` | DB | `local` / `hybrid` / `external`; affects the relevance gate only on the live path |
| `keyword_monitor_settings.min_relevance_threshold` and per-group thresholds | DB | Relevance gate (`get_relevance_threshold`, `automated_ingest_service.py:1994-2017`) |
| `config.json` topics: `categories`, `future_signals`, `sentiment`, `time_to_impact`, `driver_types`, `enrichment_disabled` | file | Label lists; empty list or flag ⇒ quarantine |
| `use_adaptive_enrichment` | `config.json` top level, default true | Only affects the unused sync path |
| `data/prompts/content_analysis/current.json` | file | The live analysis prompt |
| `app/config/litellm_config.yaml` (+ `.local`) | file | Aliases, fallbacks, Router strategy |
| `MODEL_TIER_FAST/STANDARD/PREMIUM` | `.env` | Manual research model; not auto-ingest |
| `ENRICHMENT_RETRY_SWEEP_ENABLED/_MINUTES/_BUDGET`, `ENRICHMENT_MAX_ATTEMPTS` | `.env` | Retry sweep |
| `DEBERTA_ENCODER_URL` | `.env` | Embedding service (default `http://localhost:8001`) |
| `PGVECTOR_EXACT_SCAN_MAX(_ITERATIVE)` | `.env` | Search strategy |

---

## 10. Rebuild checklist (minimum faithful copy)

1. Insert the collected row, translating non-English title/summary with a cheap model and keeping `original_*`.
2. Per batch: compute the configuration block per topic; skip scraping for blocked topics.
3. Per article: unknown-topic guard, configuration guard, no-text guard, ledger, quick relevance on title + collector summary.
4. Pre-scrape (before relevance, per batch) articles with 200 characters or less of collector content; after the gate, look up MBFC by source and save the page to `raw_articles`.
5. Analyse **the collector summary (or content)**, not the scraped page, with the 16-line prompt, the topic's five lists, today's date and computed time windows; retry parse failures 3 times; validate to the lists ("Other" for category and future signal, blank for the rest); trim the précis to 60 words; append matched keywords to tags; translate a non-English headline.
6. Re-score relevance; approve (quality is a stub); fail with `enrichment_failed` if `analyzed` is still false.
7. One UPDATE with the topic-guarded verdict and labels; then embed title + tags + page/summary at 768 d through the encoder; log, do not raise, on embedding failure.
8. Every 30 minutes, retry quarantined and failed rows under the rules in 8.3.

Things a rebuild can leave out without changing stored output: the DeBERTa classifier and hybrid service, the publication-date call on the auto path, the model's political-bias and factuality fields, `get_cached_analysis`, the sync `analyze_article_content`, the quality-check stub. A rebuild should probably also move the scrape after the relevance gate, which changes cost but not output.

---

## 11. Docs versus code

The code wins in every row below. "Matters" means a reader acting on the doc would get a wrong result.

### 11.1 Facts none of the docs cover

1. **Firecrawl is paid before the relevance check.** `process_articles_batch` pre-scrapes every article with 200 characters or less of collector text (`automated_ingest_service.py:1774-1793`); the quick relevance check runs later, per article (`:1167`). Firecrawl here is the hosted API (`FIRECRAWL_API_KEY`), so rejected articles cost a scrape. Only ledger hits and configuration-blocked topics are spared.
2. **The model reads the collector's snippet, not the scraped page** (section 2.1).
3. **A second Kimi call per article extracts a publication date that is thrown away** (section 2.6).
4. **The model's political bias and factuality are generated and thrown away** (section 2.3).
5. **Embedding failures are swallowed** inside `upsert_article_async`, so the "Vector indexing failed" branch (`automated_ingest_service.py:1462-1464`) never fires and the batch counter `vector_indexed` counts every saved article (`:1866-1868`). `app/tasks/embedding_backfill.py` is not scheduled anywhere (commit 930f539c says it is operator-run), and it selects `WHERE embedding IS NULL` with no status filter, which likely explains about 1,140 non-approved rows that carry embeddings.
6. **The quality check is a constant 0.8 approval** (section 8.5).
7. **The analysis prompt's output format can be edited from the dashboard.** `PromptManager.split_user_prompt` locks only text below the literal `REQUIRED OUTPUT FORMAT:` (`app/analyzers/prompt_manager.py:216-226`); neither v1.0.8 nor v1.0.6 contains it (both say "OUTPUT FORMAT"), so an edit can break the parser.
8. **`inference_mode` does not affect analysis**, only relevance scoring. "local" mode still calls the cloud model for analysis.
9. `app/vector_store_pgvector.py:1-14` still says OpenAI 1536.
10. Other analysis paths exist outside the docs: `research.py:905`, `bulk_research.py:653`, `news_feed_service._analyze_article_deeply`.

### 11.2 docs/AI_DESIGN_PATTERNS.md

Claims a cost-ordered funnel (cheap relevance → scrape → LLM analysis → re-check → save → pgvector), DeBERTa classification with LLM fallback, a bootstrap/retrain loop and OpenAI 1536-d retrieval.

| Doc line | Doc says | Code does | Matters? |
|---|---|---|---|
| 86 | "Scrape + enrich: DeBERTa + LLM fallback" | LLM only; `enrichment_sources = '{}'` on all 12,752 approved rows in 90 days | yes, headline claim |
| 181-183 | quick check on title + summary, "Step 2: Firecrawl scrape" after it | scrape runs before the check (11.1 #1) | yes, cost |
| 184 | analysis implied to read the scrape | reads collector summary/content (`automated_ingest_service.py:1544`) | yes |
| 186-188 | "threshold + quality re-check" | quality is a stub (`:1655-1662`) | medium |
| 1.4 | — | omits the four guards (`:1020`, `:1066`, `:1098`, `:1149`), the `analyzed=false` → failed/quarantined step (`:1375-1431`) and the retry sweep | medium |
| 196 | line refs `:1265`, `:821`, `:847`, `:1440` | now `:1682`, `:978`, `:1167`, `:1994` | low |
| 208 | "free local models decide the confident majority" | nova-lite settled 567 of 1,136 scorings in 24 h | medium |
| 210-241 | CE tier resolves < 0.10 or > 0.90 | CE is accept-only, theme-only, `CE_HIGH=0.05` (`hybrid_relevance_service.py:89-93`), off here; doc omits Jev accept tier, classifier ≥ 0.90 guard, `unavailable` status, deal pre-filter (`automated_ingest_service.py:534`) | medium |
| 271-296 | sample-count bootstrap routing, gpt-5.4-mini | only in the training dashboard (`training_routes.py:643`, `:1180`, `:1209`); default `bedrock-kimi-k2-5` (`training_bootstrap_service.py:57`); no samples since 3 Feb 2026 | yes |
| 300-308 | confidence-gated merge is "the live gate" at `:298` | gate at `:377`, sync path, reached only by `/test-process-article` | yes |
| 337 | bad value preserved into explanation | only when the explanation is empty (`article_analyzer.py:495-497`) | low |
| 347 | checks 14 required fields | 4 required, 10 blank-filled, 3 retries | low-medium |
| 353 | output contract "locked" | not locked (11.1 #7) | medium |
| 360-362 | enrichment confidence telemetry recorded from ingest | sync path only; last row 23 Mar 2026 | low-medium |
| 376-385 | `text-embedding-3-small`, 1536-d, IVFFlat, text raw → summary → title; wiley on random fallback; three embedding spaces | DeBERTa encoder 768-d, HNSW cosine, title separate with tags first; wiley is 768-d; one space | yes |
| 1087-1090 | SLM gate 0.6 row; 1536-d embedding row | unused path; stale | medium |
| 1115-1124 | model inventory | missing `bedrock-kimi-k2-5` and its fallbacks, missing Jev; CE is `bge-reranker-base` not v2-m3; Qwen unit is dead; wiley 1536 row stale | yes |

### 11.3 docs/SLM_PIPELINE_SUMMARY.md

Written Feb 2026; describes a "100% LLM-free", "$0.00/article" pipeline (Phi-3 summaries, DeBERTa classes, KeyBERT tags, Qwen explanations and category). Almost all of it is wrong today and it should be marked historical rather than patched.

| Doc line | Doc says | Code does |
|---|---|---|
| 21-31, 113-215, 310-325, 970-1027, 1262-1294 | LLM-free, $0.00 per article | one Kimi analysis call + one Kimi date call per article; nova-lite on about half the relevance scorings; Jev |
| 1044-1162 | "LLM skip optimization", `_check_slm_services_available` | does not exist (grep finds nothing) |
| 433-443 | summarization/explanation/category/KeyBERT services "Running"; Qwen :8766 | never called by ingest (only `training_routes.py:2269`, `:2306` status endpoint); Qwen down |
| 93 | Firecrawl "FREE (self-hosted)" | hosted, paid |
| 106 | scrape feeds the model | saved to `raw_markdown`, not analysed |
| 156-157 | label counts 9/13/15/80 | 4/6/5/15 |
| 361-371, 465 | accuracies 82/72.5/70.5/67.5, eval loss 0.711 | deployed model 0.797/0.762/0.689/0.511, eval loss 0.789 |
| 236-237 | `article_embeddings` table | `articles.embedding vector(768)` |
| 231 | statuses approved/filtered | seven statuses (section 8.1) |
| 1166-1196, 1181, 1190 | adaptive training active, GPT-4o-mini bootstrap | dormant since Feb/Mar 2026; default Kimi |
| 471-502 | dual vLLM | only `vllm-phi3` (:8765) up, unused by ingest |
| 445, 1305 | relevance uses `relevance_classifier_service.py` | loads the model itself (`hybrid_relevance_service.py:243-277`) |

### 11.4 docs/METHODOLOGY.md (customer-facing)

Claims relevance filtering, full-text scrape, DeBERTa classification with LLM fallback below 0.6, MBFC plus per-article LLM factuality, LLM summary with KeyBERT tags, embedding, and three inference modes.

| Doc line | Doc says | Code does | Matters? |
|---|---|---|---|
| 43 | LLM adjudicates 0.3-0.7 | confident band < 0.20 or > 0.85, Jev accept tier first | low-medium |
| 49 | full text scraped for the model, ~16k tokens | model reads the collector snippet; scrape precedes relevance | yes |
| 53, 66 | fine-tuned DeBERTa (345M) with LLM fallback < 0.6 | Kimi K2.5 alone; DeBERTa is deberta-base (~139M) and off the live path | yes, customer-facing |
| 56, 149 | sentiment Positive/Neutral/Negative/Concerned | per topic; all 8 topics here use Positive/Negative/Neutral | low |
| 78-82 | per-article LLM factuality assessment stored | thrown away; only MBFC `factual_reporting`, blank on ~48% of recent approved rows | yes |
| 88 | tags via KeyBERT | LLM tags + matched keywords (`automated_ingest_service.py:31-45`) | medium |
| 90 | explanations only for time-to-impact and driver | all four classifications | low |
| 94 | embedding = title + summary | title + tags + scraped page, else summary | low-medium |
| 96-101 | wiley on OpenAI 1536-d | wiley is 768-d | yes, tells customers text goes to OpenAI |
| 348-352 | local mode = zero cloud cost; hybrid = DeBERTa + LLM; external = GPT-4o-mini | analysis always uses the configured cloud model (Kimi); modes only change relevance | yes |
| 35, 380 | "eight dimensions" | stored set is category, sentiment, time to impact, driver, future signal, tags, MBFC bias, MBFC factual | low |

### 11.5 docs/EMBEDDING_HEALTH_MONITORING.md

Written 2 Aug 2026 after wbm's four-week outage; specifies checks A-I, of which A-D run from root cron at :15 and :45. Checks A-D exist and pass on four tenants at 768-d; lines 75-76 correctly say 768-d everywhere, contradicting the two docs above.

| Doc line | Doc says | Reality | Matters? |
|---|---|---|---|
| 50-53, 202 | cover every tenant; `TENANTS="bugfixing wileytest wiley wbm"` | still four; abm, oviva, panaya, sunstar run the same encoder unchecked | yes, the gap that hid wbm |
| 196 | keep tracked and deployed scripts in sync | deployed `/home/orochford/bin/embedding_health_check.sh` (2 Oct, Discord notify) differs from `scripts/` (9 Aug) | low |
| 39 | indexed after relevance and quality filters | quality always approves | low |
| 92-94 | code raises, so an outage leaves rows unindexed | error caught inside `upsert_article_async`, counter still counts it, no automatic re-embed; check C's grep still matches the log line | medium |
| 137-139 | check E not implementable | predicate exists (`ingest_status='approved'`); 2 of 4,892 approved rows in 30 days lack an embedding | medium, E can be built |
| 120-121 | 193k embedded rows | 217,404 of 242,689 | low |

### 11.6 docs/EMBEDDING_768_MIGRATION_RUNBOOK.md

| Doc line | Doc says | Reality | Matters? |
|---|---|---|---|
| 86 | backfill task runs inside the app | registered nowhere (commit 930f539c) | yes |
| 171-172 | restart encoder, backfill picks up skipped rows | someone must run `run_embedding_backfill()` by hand; it also embeds rejected rows | medium |
| 15 | bugfixing alembic head `fa_012` | `bm_001` | low |
| 13-18 | four tenants | abm, oviva, panaya, sunstar not listed | low-medium |
| 125-133 | 90-day backup retention | `articles_embedding_1536_backup` still has 51,526 rows; drop date about 31 Oct 2026 | note |

### 11.7 docs/COLLECTOR_DATA_QUALITY_SPEC.md §22 (lines 597-619) and the implementation note

Package 22 is built, committed (6f8d4fbd, later c87849d3 and cea85466) and live: pre-check (`automated_ingest_service.py:1066-1097`), mid-analysis catch (`:1376-1399`), sweep every 30 min (251 successful runs, latest 7 Oct 08:14), health endpoint counts (`app/routes/health_routes.py:964`), 12 tests in `tests/test_enrichment_quarantine.py`.

| Spec / doc line | Says | Code does | Matters? |
|---|---|---|---|
| spec 605 | three lists checked | five lists plus `enrichment_disabled` (`:72-94`) | fine, goes further |
| spec 605 | topic flagged in the UI | not built (implementation doc admits it, lines 279-280, 475) | medium |
| spec 605 | run record counts `configuration_blocked` | in the batch dict; sweep files it under `quarantined`; keyword route writes no run record for it | low |
| spec 607, 615 | 3-attempt cap, row "not retried again" | cap limits only the sweep; re-collection keeps adding attempts (rows at 10-20) with no model call | low-medium |
| spec 609 | all topic save paths refuse empty lists | onboarding checks only categories and future_signals (`app/routes/onboarding_routes.py:1037-1050`); `POST /api/create_topic` (`app/main.py:1780-1806`) writes anything | medium |
| impl 8-11 | "nothing is committed, nothing is restarted" | committed and live | medium, misleading status |
| impl 280 | `health_counts` feeds the health endpoint | endpoint uses its own `_count_by_topic`; `health_counts` (`enrichment_retry_sweep.py:250`) is never called | low |
| spec 601 | entry-point line numbers | stale | low |

### 11.8 CLAUDE.md "Reindex vector store"

`scripts/reindex_chromadb.py` does not work. It calls `get_chroma_client()`, which is a stub raising `NotImplementedError` (`app/vector_store.py:38-43`), so it dies before indexing. It also refuses to run unless the user is `orochford`, would walk every article including rejects, and its failure stop never triggers because `upsert_article` catches its own errors (`vector_store_pgvector.py:291-297`). The working tools are `app/tasks/embedding_backfill.py` (run by hand) and `scripts/embedding_768_postbackfill.py` (check and index build).
