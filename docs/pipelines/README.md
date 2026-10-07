# Article pipelines: monolith and saas

This folder describes how both Aunoo products turn news into stored, labelled, readable articles: collection, curation (the keep-or-reject decision) and enrichment (the AI analysis step and the other labellers). It is written so that someone can rebuild either pipeline from it.

Everything here was read from the code and the live databases on 7 October 2026. The monolith notes come from the canonical tree (`bugfixing.aunoo.ai`, HEAD `d58ffa8c`). The saas notes come from the canonical tree (`saasmvp-app`, HEAD `92a41b57`) and the prod tree (`saas.aunoo.ai`); the curation code is byte-identical between the two. Where an older doc disagrees with the code, the code wins, and each detail file lists the disagreements.

## The files

| File | Covers |
|---|---|
| [01_NEWSFIREHOSE.md](01_NEWSFIREHOSE.md) | NewsFirehose, our upstream aggregator: NewsData fetch, storage, topic tagging, the shared DeBERTa encoder, the search API, and how each product consumes it |
| [02_MONOLITH_COLLECTION_CURATION.md](02_MONOLITH_COLLECTION_CURATION.md) | Monolith: scheduler, keyword groups, collectors, insert, relevance gate, `ingest_status`, the social path, what readers hide |
| [03_MONOLITH_ENRICHMENT.md](03_MONOLITH_ENRICHMENT.md) | Monolith: the 14-step per-article run, the Kimi analysis call, label lists, models and fallback, embeddings, the other labellers, failure handling |
| [04_SAAS_COLLECTION_CURATION.md](04_SAAS_COLLECTION_CURATION.md) | saas: systemd units and worker loops, the five routes into `articles`, the analyst (curation) pipeline, topics, brands, readers |
| [05_SAAS_ENRICHMENT.md](05_SAAS_ENRICHMENT.md) | saas: the two embedding stores, the classifier service, analyst steps, MBFC and ownership, Trust Signals, novelty, coordination, story clusters, model routing and the cost ledger |
| [06_FIREHOSE_CHECKPOINT_STALL.md](06_FIREHOSE_CHECKPOINT_STALL.md) | Investigation of the monolith firehose keywords stuck since 2 October: cause, impact per tenant, recommended fix |

Each detail file is organised as numbered stages. Each stage gives what it does, what triggers it, its inputs, the tables and columns it writes, its config, the models it uses, file:line references and known gotchas. Line numbers are as of 7 October 2026 and will drift.

## The two pipelines in brief

### Monolith (one tenant per site)

1. **Schedule.** One loop, `run_keyword_monitor` (`app/tasks/keyword_monitor.py:1700`), wakes every 60 seconds and runs each due keyword group, every 12 hours by default. Nothing in cron or systemd collects.
2. **Collect.** For each keyword, each of the group's providers claims a time window from `collection_checkpoints` and searches it. The global default provider is NewsFirehose over HTTP; others are TheNewsAPI, NewsData, Bluesky, xpoz, Telegram, Reddit, arXiv, Semantic Scholar and RSS.
3. **Insert.** `facade.create_article` (`app/database_query_facade.py:442`) resolves the article's identity, marks copies and press releases, translates non-English titles and summaries with nova-lite, and links the row to its group. The row starts with `ingest_status` NULL.
4. **Curate and enrich in one pass.** `process_articles_batch` (`app/services/automated_ingest_service.py:1682`) runs 14 steps per article. In short: guards for unknown topic, empty label lists and missing text; a quick relevance gate; one Kimi K2.5 analysis call; a second relevance gate; then one UPDATE and a 768-dimension DeBERTa embedding.
5. **Reject means hide.** A rejected article keeps its row as `filtered_relevance`. Readers hide anything below a relevance of 0.4 through `app/services/article_visibility.py`.
6. **Social posts take their own path.** They skip the analysis step and are scored by the social evaluator, which ends in `social_evaluated`.

### saas (one shared platform)

1. **Two article stores.** `analyst_articles` holds the curation pipeline's work, one row per article per analyst topic. `articles` is the store every reader uses.
2. **Five routes into `articles`.** These are the hourly NewsFirehose database import, the 15-minute RSS collector, the daily official-sources poller per brand, the 4-hourly arXiv poller, and analyst publish.
3. **Curation happens only in the analyst pipeline.** Each topic runs collect → score_relevance → classify → summarize → extract_ner → enrich_mbfc. The runner sorts each article into confirmed, pending or rejected on `topic_alignment_score`, using the topic's threshold ± 0.1. Confirmed rows are published into `articles`.
4. **Nothing else is ever rejected.** RSS, arXiv and official-source articles get a `relevance_score` from a background sweep, and only some readers filter on it.
5. **Enrichment depends on the route.** Firehose imports arrive with firehose's sentiment and MBFC fields. Analyst publishes carry a summary and labels. RSS rows get only MBFC, keyed on the feed's domain. Worker loops then add DeBERTa (768d) and E5 (1024d) embeddings, novelty, AI-authorship tells, coordination edges and story clusters.
6. **Brands are a separate hourly job.** It matches brand keywords against headlines, gates brands 1 to 5 with a Nova-lite relevance check, and writes `bm_article_categories`.

## Side by side

| | Monolith | saas |
|---|---|---|
| Unit of configuration | `keyword_groups` + `monitored_keywords`; label lists per topic in `config.json` | `analyst_topics` (with step lists and threshold), `topics`, `bm_brands`, RSS feeds |
| Scheduler | One in-process 60 s loop | `saas-worker` hosts about 15 loops; systemd timers for firehose import, story clusters, worker restart every 4 h |
| NewsFirehose access | HTTP `/v1/search`, per keyword | Two routes. The analyst `collect` step uses the HTTP API per topic, which works. The bulk import reads the database directly to copy embeddings, and has been **broken since 9 Sep** (see below) |
| Where keep/reject happens | Per article, two relevance gates in the ingest pass | Only in the analyst runner; other routes are never rejected |
| Relevance score | `topic_alignment_score`: DeBERTa classifier 60% + MiniLM similarity 40%, nova-lite in the uncertain band, Jev can accept | `topic_alignment_score` from MiniLM similarity, Nova-lite for 0.10–0.85 (the DeBERTa relevance model is not deployed) |
| Rejected rows | Kept, `ingest_status='filtered_relevance'`, hidden below 0.4 | Kept in `analyst_articles` as `rejected`; never reach `articles` |
| AI analysis model | Kimi K2.5 on Bedrock, one call, 16 labelled lines, about $0.0017 per article | Nova-lite classify; Phi-3 on vLLM for summary and entities, Haiku fallback |
| Where the labels end up | On `articles` itself | Mostly in `analyst_articles`; `articles` gets summary, sentiment label, MBFC |
| Model routing | LiteLLM aliases in `app/config/litellm_config.yaml`, model tiers | `ai_model_configs` row per use case, Haiku 4.5 default, no tiers |
| Embeddings | DeBERTa 768d in `articles.embedding` | DeBERTa 768d in `article_embeddings` and E5 1024d in `article_embeddings_ml` |
| Cost ledger | `llm_usage_log` per tenant DB | `llm_usage_log`, no tenant id on background spend |
| Reader rule | One predicate, `article_visibility.py` (observer readers use their own) | Differs per reader: newsfeed ≥ 0.3 + sentiment, newsletter any score, MCP topic tool none |
| Weekly volume (7 days to 7 Oct) | bugfixing: 5,767 new rows, 1,057 approved | about 9,700 analyst rows a day, 26% confirmed; firehose import 0 |

## Rebuild order

The detail files each end with a rebuild checklist. Here they are in one dependency order.

1. **Shared services.** Postgres 16 with pgvector, Redis, and `deberta-encoder.service` on :8001 with `microsoft/deberta-base` pre-cached. Every product's vectors come from this one encoder, which keeps them comparable. See 01, Stage 5.
2. **NewsFirehose.** Schema, topic sync, Celery worker and beat, API, NewsData slices in `.env`, and the trained per-topic classifiers. Without the classifiers, only the 15% LLM sample tags anything. See 01, rebuild checklist.
3. **Monolith tenant.** Alembic migrations, `.env` (including `NEWSFIREHOSE_BASE_URL`, because the code default points at a dead IP), keyword groups, and non-empty label lists per topic. Then the keyword monitor loop, the ingest pass and the embedding step. See 02 Stages 1–6 and 03 Section 10.
4. **saas.** The E5 encoder (:8002), the classifier service (:8013), vLLM Phi-3 (:8765), `mbfc_sources`, `ai_model_configs` rows per use case, and `saas-worker` with every loop registered in both `pipeline_worker.py` and `app_factory.py`. Then the firehose import (it needs a network path to the firehose database), the analyst topics with step lists and thresholds, and the brand loop. See 04 Sections 1–5 and 05 Section 15.
5. **Check it works.** Compare against the live numbers in 02 Stage 10, 03 Section 0, 04 Section 3.7 and 05.

## Problems found while mapping

We fixed none of these. They are ordered by how much they cost the product now.

1. **saas has lost about 90% of its daily intake since 9 September.** saas reads NewsFirehose in two ways, and only one of them broke.
   - **The analyst pipeline's `collect` step uses the HTTP API** (`app/analyst/pipeline/steps/collect.py`). It still works, so curated topics kept receiving articles.
   - **The hourly bulk import reads the firehose database directly** (`scripts/import_firehose_corpus.py`), because it copies the stored DeBERTa vectors and the API does not serve them. `FIREHOSE_DSN` is not set on prod, so it reads the frozen local copy and adds 0 rows. The new database at 188.40.128.115 has its Postgres ports closed to this server.
   - **The drop, from prod `articles`:** 25,000–30,000 new rows a day up to 9 September, about 95% of them from the import. Since 10 September it has been 2,000–5,000 a day, with no firehose rows at all.
   - **There are two ways to restore it.** One is to open a Postgres port on the new host and set `FIREHOSE_DSN`. The other is to change the importer to walk firehose ids through `/v1/articles?ids=` and let saas's own `embedding_generation_loop` compute the DeBERTa vectors on the same encoder. That route takes about 550 calls a day, 50 ids each, well inside the 100-requests-per-minute limit.
   - See 01 Stage 8b and 04 Section 2.1.
2. **82 monolith firehose keywords have searched the same window since 2 October, and the AI keyword group (group 9) has matched no new articles since 5 October.** The full investigation is in [06_FIREHOSE_CHECKPOINT_STALL.md](06_FIREHOSE_CHECKPOINT_STALL.md). **Fixed 7 Oct in `a7b3263d`** (bugfixing, abm, bwtemplate); the design below is what shipped, except that the overlap is 12 hours and pages holding only rows newer than the window do not count toward the cap.
   - **Cause:** commit `6f8d4fbd` (1 Oct) introduced fixed time windows. A full page of results counts as "incomplete", and `commit_interval` treats incomplete as a failure, so the window never moves (`app/collectors/base_collector.py:263`, `app/services/collection_runs.py:264-272`). That commit added paging to TheNewsAPI and the other collectors but not to the firehose collector. So every keyword with 10 or more hits re-finds the same 10 articles on every run. Nothing reads the failure counter, so there is no backoff and no alert.
   - **A second bug makes it worse:** the collector sends `to_date` as a bare date, which the API reads as midnight, so a same-day window searches a single instant.
   - **Impact on bugfixing:** daily new matches in `keyword_article_matches` before and after:

     | Group | Before (26–29 Sep) | Since 4 Oct |
     |---|---|---|
     | AI (group 9) | 90–188 | 0 since 5 Oct (10 on 4 Oct) |
     | Geopolitical (group 10) | 150–179 | 13–40 |
     | SOC Market Watch (group 16) | 35–74 | 0–1 |

     abm has 9 stuck firehose scopes and 5 stuck xpoz scopes. wiley and wileytest do not have this code yet; copying `6f8d4fbd` there as it stands would cause the same stall.
   - **Recommended fix:**
     - Page the firehose collector until the API's `has_more` is false (it takes `page_size` up to 100 and `page`), returning `partial` with a continuation when the time budget runs out.
     - Send `to_date` as the following day.
     - For collectors that cannot page, advance the window anyway and record the truncation.
     - Add a valve that advances after about 6 runs that make no progress, and show the stuck count on the health route.
   - **Timing:** no manual reset is needed. Once fixed, frozen windows complete on their next run and the 2 October gap back-fills. The keyword monitor only looks back 7 days, so this fix should land by about 9 October, or `search_date_range` should be widened for one cycle.
3. **The saas topic classifier asks the same question about the same 50 articles every 5 minutes.**
   - **What it is for:** articles that arrive with no topic, mostly from RSS feeds not tied to a topic. It asks an LLM which of the 21 curated topics each article belongs to.
   - **What goes wrong:** it picks the 50 newest untagged articles from the last 7 days. Most match no topic, so they stay untagged and are picked again on the next cycle. `classify_and_persist_unclassified` (`app/topics/classifier.py`) accepts a `skip_ids` set for exactly this case, but the loop in `app/tasks/topic_classifier_task.py` never passes one.
   - **Live:** in the last 24 hours the log shows "tagged 0/50" 195 times and "tagged 1/50" 3 times. That is about 84,000 Llama 3.3 70B calls a week, each sending the title and up to 2,000 characters of text, for about 3 new tags a day.
   - **Cost:** we estimate about $75 a week at Llama's list price. The ledger shows about $6, because the model's row in `ai_model_configs` carries Nova-lite prices.
   - **Fix:** keep a skip set in the loop, as `relevance_backfill` already does.
   - See 04 Section 4.3.
4. **The monolith pays to scrape before it decides relevance.** Firecrawl runs before the quick gate for every article with 200 characters or less of collector text. On bugfixing, 422 of about 490 pages scraped between 3 and 7 Oct (86%) belonged to articles the gate then rejected, and the gate never reads the scraped page anyway. See 03 Section 0.
5. **Readers disagree about what is visible.**
   - On the monolith, the final gate uses the topic's lowest-id group threshold, so some approved rows fall below the 0.4 reader floor: 120 this week.
   - On saas, the MCP topic tool applies no relevance filter at all.
   - See 02 Stage 8 and 04 Section 6.
6. **Work is paid for and then thrown away.**
   - The monolith makes a second Kimi call per article for the publication date and discards the answer.
   - The monolith never stores the model's bias and factuality answers. saas stores them in `analyst_articles`, but they never reach `articles`.
   - On saas, most classify labels never reach `articles`.
7. **Cost reports are wrong in places.**
   - saas `analyst_pipeline_runs.estimated_cost_usd` shows $0 for relevance scoring and Haiku prices for classify.
   - Monolith social evaluation runs on claude-haiku-4-5, which our cost rules say to avoid.
8. **saas failure handling has a gap.** Bedrock 500/503 errors and timeouts are neither retried nor sent to a fallback model. See 05 Section 13.
9. **The saas hourly cleanup timer fails on every run.** An unquoted password on line 124 of the prod `.env` breaks the shell that sources it.

## Older docs this folder supersedes

These documents disagree with the code. Treat them as historical where they conflict with this folder.

- `docs/SLM_PIPELINE_SUMMARY.md` describes an "LLM-free, $0.00 per article" pipeline. The live path makes one Kimi call per article, and the DeBERTa classifier has not run on it since February.
- `docs/METHODOLOGY.md` is customer-facing and makes three false claims. It says articles are classified by DeBERTa, that a per-article AI factuality rating is stored, and that wiley sends text to OpenAI at 1536 dimensions. It needs correcting before it is shown to anyone again.
- `docs/AI_DESIGN_PATTERNS.md` gives the wrong embedding model and model list.
- `docs/COLLECTOR_DATA_QUALITY_IMPLEMENTATION.md` says nothing is committed. The work is commit `6f8d4fbd` and has been live since about 1 October.
- `docs/BRAND_RELEVANCE_SAAS_VS_MONOLITH.md` leaves out the saas analyst publish and firehose import routes. It also says the brand decision is on at every monolith site, but it is off on bugfixing.
- `docs/how_it_works_topics.md` describes forecast topics, not collection.
- The CLAUDE.md command `scripts/reindex_chromadb.py` fails on a ChromaDB stub.
- saas `docs/EMERGING_TOPICS_SYSTEM.md` names the disabled `saasmvp-worker` unit and a 24-hour cadence. Prod runs `saas-worker` and repeats every 4 hours.
