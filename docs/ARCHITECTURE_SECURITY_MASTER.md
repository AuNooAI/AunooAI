# AunooAI — Master Architecture, Design Patterns & Security Document

| | |
|---|---|
| **Version** | 0.2 (correctness/comprehensiveness pass applied) |
| **Date** | 2026-07-16 |
| **Owner** | Oliver Rochford |
| **Review cadence** | Quarterly, and after any architecture-level change |
| **Audience** | ISO 27001 / SOC 2 auditors and assessors; AunooAI engineers |
| **Classification** | Internal. Annex A enumerates known weaknesses (several rated High) and must not be shared outside the audit/engineering context. |
| **v0.2 changes** | Corrected the host network-boundary claim (no firewall; public non-loopback listeners), reclassified NewsFirehose as in-boundary self-hosted, added the standalone LiteLLM proxy / vLLM / Docker estate and the remote LLM data path, corrected the tenant inventory and the "single OS user" framing, fixed router/migration counts, and added ~12 new Annex A items (A17–A28) plus new control subsections §8.9–§8.11. Figures verified against the running host on 2026-07-16. |

**Purpose.** This document is the authoritative system description for the AunooAI platform, written to serve two roles at once: (1) system-description evidence for ISO 27001 and SOC 2 audit work, and (2) the engineering architecture reference. Every material claim carries a file path (and where useful a line number) so it can be verified against the code. Where deeper documents exist, this document links them (Annex B) rather than duplicating them.

**How to read this document.** Sections 2–7 describe what the system is and how it is built. Section 8 describes the security controls that exist today — current state only, no aspirations. Annex A is the separated gaps/remediation backlog. Nothing in the body of the document is softened to look better for an audit; nothing in Annex A is a control claim.

---

## Table of contents

1. [Document control & purpose](#aunooai--master-architecture-design-patterns--security-document) (above)
2. [System overview & boundary](#2-system-overview--boundary)
3. [Monolith architecture](#3-monolith-architecture)
4. [SaaS MVP architecture](#4-saas-mvp-architecture)
5. [Design patterns catalog](#5-design-patterns-catalog)
6. [Data flows & external integrations (subprocessor inventory)](#6-data-flows--external-integrations-subprocessor-inventory)
7. [Deployment & operations](#7-deployment--operations)
8. [Security controls](#8-security-controls)
9. [Annex A: Known gaps & remediation candidates](#annex-a-known-gaps--remediation-candidates)
10. [Annex B: Source document index](#annex-b-source-document-index)

---

## 2. System overview & boundary

AunooAI is a strategic intelligence platform: it collects news and social-media content at scale, enriches it with AI (classification, relevance scoring, sentiment, entity extraction), and presents analysis surfaces (topic dashboards, brand monitoring, foresight/scenario tooling, research agents, reports and newsletters).

Two product lines exist inside the system boundary. They share domain concepts and one upstream article source, but are **separate codebases with separate databases**:

### 2.1 The monolith (tenant-per-deployment)

- Codebase: this repository (`/home/orochford/tenants/bugfixing.aunoo.ai` is the reference copy). FastAPI backend, React frontends built to static bundles, PostgreSQL 16 + pgvector.
- Multi-tenancy model: **one full deployment per customer/tenant**. Each tenant is a complete copy of the application in its own directory under `/home/orochford/tenants/<slug>.aunoo.ai`, with its own systemd service, its own loopback port, its own PostgreSQL database and DB role, and its own encrypted `.env`.
- **Tenant inventory is larger than a single reviewer usually expects and must be treated as authoritative only when reconciled against the host.** As of this revision, `ls /home/orochford/tenants/` plus `/etc/systemd/system/*.aunoo.ai.service` and `/etc/letsencrypt/live/` (~91 certificate directories) show roughly two dozen deployments. Named examples with live service units include `bugfixing` (dev/reference), `wiley` (production customer), `wileytest` (customer staging), `abbott`, `pearson`, `sage`, `wbm`, `abm`, `pbm`, and `bwtemplate` (golden template for Brand-Watcher-dedicated tenants). Additional directories/units exist (`community`, `helpnet`, `opendemo`, `skunkworkx`, `spiros`, `testbed`, `vc`, and service-only entries such as `oliver`, `quantum`, `secops`, `test`, `wiley1`), some active, some retired/failed. **A definitive, current asset register is a prerequisite for the audit and is not reproduced here — it must be generated from the host and kept as controlled evidence (see Annex A item A17).** Do not treat any list in this document as exhaustive.
- A tenant can run the full platform or a Brand-Watcher-dedicated subset (`BW_DEDICATED_MODE` flag; see §5.4).

### 2.2 The SaaS MVP (multi-tenant-from-day-one)

- Codebase: separate git repository (`github.com/AuNooAI/aunooai-saas`), checked out at `saasmvp-app/` inside this working tree (untracked here) and deployed independently. FastAPI (Python 3.12), SQLAlchemy 2.0 async, PostgreSQL 16 + pgvector, Redis 7, React/Vite SPAs.
- Multi-tenancy model: **shared application and database with PostgreSQL Row-Level Security** (RLS) scoping tenant data, plus a shared (non-tenant-scoped) article corpus.
- Deployments: production at `saas.aunoo.ai` (port 10017, `/home/orochford/tenants/saas.aunoo.ai`) and staging at `saasmvp.aunoo.ai` (port 10016, `saasmvp-app/` in this tree). Each deployment also runs worker and classifier services (§4.2, §7.2).
- Note: the `saasmvp/` directory (numbered markdown files `00-overview.md`…`10-infrastructure.md`) is the original design spec and has drifted materially from the implementation. Where they diverge, the code is authoritative (see Annex B).

### 2.3 Hosting model (both product lines)

Everything runs on a single Linux host (Ubuntu, kernel 6.8):

- **nginx** terminates TLS for every domain (Let's Encrypt/certbot, HTTP→HTTPS redirect) and reverse-proxies to loopback-bound uvicorn processes. The per-tenant application uvicorn processes do bind to `127.0.0.1` only.
- **systemd** supervises every application process (one or more units per tenant/deployment).
- **PostgreSQL 16** is a single shared instance hosting all tenant databases and the SaaS database; **pgbouncer** (port 6432) fronts it for some tenants (§7.4). pgvector provides vector storage in the same instance — there is no separate vector database. PostgreSQL, pgbouncer, and Redis are all verified loopback-bound.
- **The host is NOT firewalled and nginx is NOT the sole public ingress.** Verified state (`ufw status` = inactive; `iptables -L INPUT` policy = ACCEPT with no host rules; `ss -tlnp`): besides SSH (`:22`) and nginx (`:80`/`:443`), the following are bound to `0.0.0.0` and therefore internet-reachable — the standalone LiteLLM proxy (`:4000`, §3.6), the self-hosted NewsFirehose API (`:8000`, §2.4), and Docker-published containers on `:8080` and `:8443` (§2.4). A vLLM engine is additionally bound to the host's **public IPv6** address on high ports. This is a significant, currently-uncontrolled network boundary and is recorded as Annex A item A18; the transport section (§8.5) and this bullet must be read together — do not cite host-level network isolation as a control until a firewall is in place.
- Local ML services intended to be internal: a DeBERTa encoder on `:8001` and an SLM classifier on `:8012`. Note that the encoder service and some model endpoints are among the non-loopback listeners above, not on loopback as originally assumed.

### 2.4 Boundary summary

Inside the boundary: the host, nginx, all tenant deployments, the SaaS deployments, PostgreSQL/pgbouncer/Redis, local ML services, deployment/provisioning scripts, and monitoring crons. Outside the boundary but relied upon: the third-party APIs inventoried in §6 (subprocessors), GitHub (source hosting), Let's Encrypt (certificates), and AWS Bedrock/OpenAI (AI processing).

**Additional in-boundary systems co-resident on the host** (verified via `systemctl` / `docker ps` / `/opt`; these belong in the asset register and were under-described in earlier drafts):

- **NewsFirehose** — a **self-hosted** ingestion stack at `/opt/newsfirehose` (owner user `newsfirehose`) with its own systemd units (`newsfirehose-api` on `0.0.0.0:8000`, `-worker`, `-beat`, `-encoder`, `-flower`, a daily-train timer), its own Celery/Redis and database. It is **inside the boundary**, not a third-party subprocessor — the §6 entry is corrected accordingly. It is currently internet-bound on `:8000`.
- **Standalone LiteLLM proxy** — `litellm.service` (`User=laouad`, `--host 0.0.0.0 --port 4000`, own config/credentials). An internet-exposed LLM gateway owned by a non-Aunoo account (§3.6).
- **vLLM model servers** — `User=laouad` units; at least one binds the host's public IPv6 address (§2.3).
- **Docker estate** — a running Docker environment the application deployments do not use directly but which shares the host: `ciso-assistant` (a compliance tool; backend/frontend/huey/caddy, caddy publishes `:8443`), `langflow` + caddy (publishes `:8080`), `neo4j` (loopback), a `dask` cluster + Jupyter notebook, and a separate `postgres:16.4` scraper database (`:5431`). Two of these are internet-exposed.
- **The host is multi-user.** Service-relevant OS accounts include `orochford` (monolith tenants), `newsfirehose`, `laouad` (LiteLLM/vLLM), and `www-data` (a few legacy tenant units, §7.1) — not a single account as the isolation analysis originally framed it (see corrected Annex A item 10).

---

## 3. Monolith architecture

### 3.1 Application factory and lifecycle

- Entry point chain: `app/run.py` (dev) or `app/server_run.py` (systemd) → `app/main.py` → `app/core/app_factory.py::create_app()`.
- `create_app()` builds the FastAPI application, attaches state (`app.state.db`, `app.state.templates`, `app.state.dedicated_bw`), registers a `RequestValidationError` handler, wires middleware (`app/middleware/setup.py`), mounts `/static`, initializes OAuth providers (`app/security/oauth.py::setup_oauth_providers`), and registers routers.
- `app/main.py` is a large legacy module (~3,600 lines) still carrying page routes and topic CRUD; functionality is being progressively migrated to `app/routes/` + `app/core/routers.py`.
- **Lifespan management** (`app_factory.py`, async context manager): startup configures logging and an optional thread-pool executor override (`SERVICE_EXECUTOR_MAX_WORKERS`), initializes the async database (`initialize_async_db()`), and runs `initialize_application()` (`app/startup.py`); shutdown closes the async DB and the ingestion service's executor.

### 3.2 Router registration

`app/core/routers.py::register_routers()` performs 52 explicit `app.include_router()` calls, then iterates the module registry (`get_enabled_modules()`) and conditionally mounts pluggable module routers via `importlib`. Route files live one-per-feature in `app/routes/` (66 files); several separate page routers from API routers (e.g. `news_feed_routes.py` exposes both `router` and `page_router`).

### 3.3 Background tasks and schedulers

All background work is launched as fire-and-forget `asyncio.create_task()` calls inside lifespan, with staggered startup delays (5s–45s) so startup is never blocked. Implementations live in `app/tasks/`:

| Task | Delay | Gate |
|---|---|---|
| `keyword_monitor.py` (scheduled collection) | 5s | always |
| `emerging_topics_monitor.py` | 10s | always |
| `observer_agent_monitor.py` | 15s | always |
| `newsfeed_dashboard_monitor.py` | 20s | always |
| `rss_feed_monitor.py` | 25s | always |
| `timeline_task.py`, `forecast_tracker_monitor.py` | 30s | latter gated by `FORECAST_TRACKER_AUTO_RUN` |
| `wiley_candidate_scheduler.py` | 45s | `WILEY_CANDIDATE_SCAN_ENABLED` |
| `event_loop_monitor` (loop-lag health sampling) | 3s | always; surfaced at `GET /api/admin/event-loop-status` |
| Module monitors (`brand_watcher_monitor.py`, `policy_tracker_monitor.py`, `geopolitical_hotspots_monitor.py`, `science_funding_monitor.py`, `threat_intelligence_monitor.py`, `news_feed_scheduler.py`) | dynamic | per enabled module via `_schedule_module_task()` |

The ingestion engine is `app/services/automated_ingest_service.py`; long-running jobs are tracked by `app/services/background_task_manager.py` (`BackgroundTaskManager`, DB-persisted task records, max 3 concurrent).

### 3.4 Services layer

`app/services/` holds ~130 modules (101 at the top level, ~129 including subpackages), clustered by function:

- **Ingestion**: `automated_ingest_service.py`, `auto_ingest_service.py`.
- **Analysis/enrichment**: `article_intelligence_analyzer.py`, `ontology_aware_classifier.py`, `relevance_classifier_service.py`, `hybrid_relevance_service.py`, `hybrid_enrichment_service.py`.
- **Strategic intelligence (SIO)**: `strategic_intelligence_service.py` (4-stage pipeline; see `docs/sio_architecture_documentation.md`).
- **Brand Watcher**: `brand_*` / `bw_*` services, `opoint_brand_matcher.py`.
- **Forecast/foresight & reporting**: `forecast_*`, `topic_report_*`, per-format renderers (`*_docx.py`, `*_pptx.py`, `*_html.py`, `report_pdf.py`).
- **Research & agent surfaces**: Auspex research agent (`auspex_service.py`, `auspex_tools.py`, `mcp_server.py`, plugin loader `tool_plugin_base.py`/`tool_loader.py`); deep research (`deep_research_service.py`); PAM agents (`pam_service.py`, `pam_agents/`, `pam_event_extraction_service.py`).
- **Local ML / training**: `slm_integration.py`, `finetuning_service.py`, `preclassifier_training_service.py`, `training_bootstrap_service.py`.
- **Delivery**: `email_service.py`, `newsletter_service.py`, `daily_briefing_compose_service.py`; audio/podcast via ElevenLabs (`app/routes/podcast_routes.py`) and Dia TTS (`dia_client.py`).

Beyond the clusters above, several substantial user-facing subsystems have their own routers/services and are named here for asset-inventory completeness (they were omitted from earlier drafts): **executive briefings** (`executive_briefing_routes.py`), **focus groups** (`focus_group_routes.py`), **futures cone** (`futures_cone_routes.py`), **EOS** (`eos_routes.py`), **model bias arena** (`model_bias_arena_routes.py`), **market signals**, and **runtime prompt management** (`prompt_management_routes.py` — a change-control surface for LLM behavior). The `kissql/` package is a custom user-facing query DSL exposed through the vector routes that compiles user-supplied regex (`parser.py:116`) — a ReDoS surface flagged in Annex A item A24. The monolith also uses **Redis** (`localhost:6379`) as a search cache in `vector_routes_enhanced.py` (Redis is not SaaS-only).

### 3.5 Data collectors

- Abstract base: `app/collectors/base_collector.py` (`ArticleCollector` ABC — `search_articles()`, `fetch_article_content()`).
- Registry factory: `app/collectors/collector_factory.py` (`CollectorFactory._collectors` dict; `get_available_sources()` filters by which provider credentials are present in the environment).
- Implementations: `arxiv`, `newsapi`, `thenewsapi`, `newsdata`, `newsfirehose`, `opoint`, `rss`, `semantic_scholar`, `bluesky`, `reddit`, and `xpoz_collector.py` (cross-platform social: X, Reddit, Instagram, TikTok).

### 3.6 AI/LLM integration

- Every chat/completion LLM call funnels through **LiteLLM** (`app/ai_models.py` — `AIModel`, `LiteLLMModel`, `litellm.Router`; `litellm.drop_params = True`). Model routing config: `app/config/litellm_config.yaml` (plus `.local` override; path resolvable via `LITELLM_CONFIG_PATH`). The config file is re-read live, so config changes take effect without restart.
- **Effective LLM provider for the standard aliases is AWS Bedrock (Anthropic Claude).** Although the model aliases keep upstream names (`gpt-4o`, `gpt-5.4`, `claude-*`), every alias in `litellm_config.yaml` maps to a Bedrock Claude target (`bedrock/us.anthropic.claude-haiku-4-5-*` for the mini/nano tiers, `bedrock/us.anthropic.claude-sonnet-4-5-*` for the full tiers). One local entry (`ollama/gemma3:4b`) exists for on-host inference. Article text sent for LLM analysis via these aliases goes to AWS Bedrock, not OpenAI, regardless of the alias name.
- **Undisclosed remote LLM path (data-residency flag).** A sibling override file, `app/config/litellm_config.yaml.local`, is loaded and merged over the base config by `app/ai_models.py` (local settings win). It registers extra aliases (`mixtral`, `mixtral-instruct`, `qwen3:14b`, `gemma3:27b`) whose `api_base` points at a **remote off-host LiteLLM proxy and Ollama** (`http://5.9.100.178:4000` and `:11434`). Any feature selecting those aliases ships prompts/article text to that third-party host. This contradicts a naive "all LLM traffic is Bedrock / Ollama is local" reading and is recorded as Annex A item A19 (undisclosed subprocessor / data-residency).
- **A standalone LiteLLM proxy also runs as a host service** (`litellm.service`, `User=laouad`, `0.0.0.0:4000`; §2.4) — distinct from the in-process `litellm.Router` used by the app. It has its own config and credentials and is internet-bound. Treat it as a separate data-egress and access-control surface.
- **Embeddings no longer go to OpenAI, except on wiley**: `app/vector_store_pgvector.py` calls a local DeBERTa 768-d encoder (`DEBERTA_ENCODER_URL`, default `http://localhost:8001`) on **bugfixing**, **wileytest** and **wbm**, so no article text leaves the host for embedding on those tenants. **wiley** is the last tenant still calling OpenAI `text-embedding-3-small` directly (`OPENAI_API_KEY`), and article text for embedding does go to OpenAI there. Verified against code and the `articles.embedding` column type on each tenant, 2026-08-02. Check the tenant before relying on this in a data-residency answer.
- **History (resolved 2026-08-02).** wbm spent four weeks in a broken third state: 1536-d code against a `vector(768)` column, so every write raised `expected 768 dimensions, not 1536` and nothing was stored between 2026-07-05 and 2026-08-02. Fixed by moving wbm to the local encoder; the 26,348 stranded articles were backfilled. bugfixing was migrated the same day (alembic `emb_768_01`), which also ended its OpenAI embedding calls.
- Local ML models (fine-tuned DeBERTa 345M classifiers, KeyBERT, cross-encoder rerankers) run on-host under `models/` — that inference involves no external data transfer. Methodology, including the 3-tier relevance cascade, is documented in `docs/METHODOLOGY.md`.

### 3.7 Database layer

- `app/database.py` — `Database` class over a class-level shared SQLAlchemy engine (`_pg_engine_instance`, double-checked locking); module singleton `get_database_instance()`. Sync pool: `pool_size=20, max_overflow=10, pool_recycle=300, pool_pre_ping=True`. Dual-backend design (`DB_TYPE=postgresql|sqlite`); PostgreSQL is the only supported production backend.
- SQLite-style compatibility wrappers `PostgreSQLConnectionWrapper` / `PostgreSQLCursorWrapper` (`app/database.py:22-147`) present a `cursor/execute/fetchall` API over SQLAlchemy connections, rewriting `?` placeholders to bound parameters (§5.3).
- Async path: `app/database_async.py` + `app/services/async_db.py` (`AsyncDatabase`, asyncpg via `create_async_engine`, `async_sessionmaker`), opened/closed by lifespan.
- Table definitions: `app/database_models.py`. Query aggregation: `app/database_query_facade.py` (`DatabaseQueryFacade`, ~14,000 lines — see §5.2 and Annex A item 13).
- **Schema changes go through Alembic only** (106 migration versions in `alembic/versions/`); direct DDL is prohibited by project policy (`CLAUDE.md`). Tenants can sit at different migration heads; migrations copied between tenants need per-tenant `down_revision` review.
- Vector storage: `app/vector_store_pgvector.py` — cosine distance. The `articles.embedding` column width must match that tenant's encoder: `vector(768)` on bugfixing, wileytest and wbm, `vector(1536)` on wiley (verified 2026-08-02). A mismatch is not caught at startup; it surfaces as a per-article upsert error, which is how the wbm outage went unnoticed for four weeks (§3.6). `app/vector_store.py` is the public interface. ChromaDB was removed; `vector_store_chromadb_backup.py` and import stubs remain for compatibility.

### 3.8 Frontend

- Multiple independent React 18 + TypeScript + Vite apps in `ui/`, one HTML entry per surface (`index.html`, `index-operations.html`, `index-gather.html`, `index-newsfeed.html`, `index-pam.html`, `index-submit-articles.html`); Tailwind + Radix UI, Recharts, Leaflet/react-globe.gl.
- **Deployment model is build-then-copy, not a live SPA server**: `ui/deploy-react-ui.sh` runs the Vite build and copies `ui/build/` into `static/trend-convergence/`; `ui/update-template-assets.py` rewrites the hashed asset filenames into the Jinja2 templates. The server renders Jinja2 templates (`templates/`) that reference the pre-built bundles.
- `app/core/templates.py::AppInfoJinja2Templates` injects `app_info` and the session into every template response; templates read `app.state.dedicated_bw` to trim navigation for Brand-Watcher-dedicated tenants.

---

## 4. SaaS MVP architecture

### 4.1 Stack and entry point

- FastAPI (Python 3.12) + Starlette middleware; SQLAlchemy 2.0 async with asyncpg; PostgreSQL 16 + pgvector (one DB for relational and vector data); Redis 7 (`redis.asyncio`) for cache/queues; Alembic migrations.
- Entry: `saasmvp-app/app/main.py` → `app/core/app_factory.py::create_app()`. Middleware order (outer→inner): `SessionMiddleware` (OAuth state only) → `TenantContextMiddleware` (JWT) → CORS. CORS is `["*"]` only when `DEBUG`, otherwise locked to `APP_URL`.
- Lifespan: enforces secret configuration (§8.2), opens Redis, runs orphaned-run reapers (analyst pipeline, foresight, geohotspots), warms the prompt-injection guard model, and starts background loops only when the process role allows it.
- 191 SQLAlchemy models in `app/database/models.py`.

### 4.2 Process/role split

The same codebase runs in distinct process roles selected by the `WORKER_ROLE` env var:

- `web` — API only; systemd runs uvicorn with `--workers 4`.
- `pipeline` / `all` — runs ~28 background loops (`app/tasks/`): ingestion, embedding, novelty, emerging topics, geohotspots, threat intel, brand monitoring + digest, timeline, propagation detection, the analyst scheduler/executor family, bias/narrative loops, spectrum pre-generation, topic classification, author resolution, cleanup, and more.
- `skills` — `app/workers/pipeline_worker.py`, running only the validation/newsletter jobs loop (isolates long LLM jobs from CPU-bound ingestion).

Supporting ML service: `ml/classifier_service.py` (SLM sentiment/toxicity classifier) as its own systemd unit on :8012; a shared DeBERTa encoder service on :8001.

### 4.3 API surface

All application APIs live under `/api/v1/` (`app/core/routers.py`, 69 routers): auth, topics, dashboard, articles, agents, auspex, billing (Stripe Checkout + webhooks; 6 pricing tiers plus add-ons), notifications, search, settings, sharing, newsfeed, publishers, an RSS/"My News" reader family (RSS/arXiv/WebSub/Fever sync), onboarding, feature-gated modules (geohotspots, threatintel, brand-monitoring, social), a large `analyst/` family (MBFC, AI-tells, narratives, sentiment, editorial, propagation, state-media, entities, observability, …), `admin/` (platform-admin-gated), `marketing/` (separate role), and the Skills/MCP surface (`/api/v1/skills/`, `/mcp/<pack>`) with OAuth 2.1 dynamic client registration and `.well-known` discovery (`app/oauth/`). An SPA catch-all is registered last. **Note on DCR**: `POST /oauth/register` is an unauthenticated open client-registration endpoint (`app/oauth/routes.py:126` — RFC 7591 standard behavior, `redirect_uri` restricted to https/localhost). This is intentional for MCP interoperability but is an unauthenticated, unthrottled write surface that belongs in the threat model (Annex A item A23).

### 4.4 Tenant isolation (RLS)

Defense in depth across two layers:

1. **Application layer** — `TenantContextMiddleware` (`app/auth/middleware.py`) decodes the JWT cookie and sets `request.state.{user_id, tenant_id, role, is_impersonation}`; role dependencies (`require_platform_admin`, `require_marketing`, `require_tenant_admin`) gate privileged routers. **Impersonation caveat**: `is_impersonation` is defined and read but currently **dormant** — no code path sets it true, no endpoint mints an impersonation token, and there is no audit trail for admin-acting-as-tenant. If this capability is ever wired, an audit-log requirement must be added first (Annex A item A25).
2. **Database layer** — PostgreSQL Row-Level Security (`scripts/setup_rls.sql`; roles `aunoo_app` subject to RLS, `aunoo_admin` with BYPASSRLS). Three session dependencies in `app/database/session.py`: `get_db()` (no tenant scope, public data), `get_tenant_db()` (issues `SET LOCAL app.current_tenant_id = '<int>'` per transaction — the value is cast through `int()` before interpolation, a reviewed non-injectable pattern at `session.py:43,84`), and `get_admin_db()` (`SET LOCAL role = 'aunoo_admin'`). The router registry documents explicitly that `get_admin_db` only changes the PG role and does not authorize — every `/api/v1/admin` route is separately gated by `Depends(require_platform_admin)`.

The article corpus (articles, embeddings, topics) is deliberately shared — it carries no `tenant_id` and is readable platform-wide; tenant-owned data (agents, settings, findings, billing) is RLS-scoped.

### 4.5 Frontend

Three SPAs built from `ui/` (plus `aunoo-react/`): the user app (`static/app`), admin console (`static/admin`), and analyst panel (`static/analyst`). React 18 + TypeScript + Vite, Tailwind + Radix UI, Recharts, Leaflet. Deploy: `scripts/deploy-ui.sh` (build → copy → `systemctl restart`).

### 4.6 Relationship to the monolith

The two product lines do not share code or databases. They share: (a) the **NewsFirehose** upstream article source (§6), (b) the local DeBERTa encoder service, and (c) domain concepts — many SaaS pipelines are reimplementations of monolith features. Some capabilities intentionally remain monolith-only (e.g. disinformation network clustering). Selected monolith tenants embed SaaS-built UI surfaces (the Consensus/Horizons foresight pages were ported to the bugfixing tenant), but as static assets, not shared services.

---

## 5. Design patterns catalog

The patterns below recur across the codebase; new code should follow them rather than invent parallel mechanisms.

### 5.1 Factory / registry
- `CollectorFactory` (`app/collectors/collector_factory.py`): classmethod registry mapping source name → collector class; registration-based extension.
- Model factory in `app/ai_models.py` (`get_available_models()`, `resolve_litellm_call_params()`): alias → concrete provider resolution.
- Module registry in `app/core/modules.py` (§5.4).

### 5.2 Facade
- `DatabaseQueryFacade` (`app/database_query_facade.py`), lazily attached as `Database.facade` — a single aggregation point for query methods so routes/services don't hand-roll SQL. It is very large (~14,000 lines) and still carries `# TODO SQLAlchemy` markers from the SQLite era (Annex A item 13).

### 5.3 Adapter / wrapper
- `PostgreSQLConnectionWrapper` / `PostgreSQLCursorWrapper` (`app/database.py:22-147`): SQLite-style cursor API over SQLAlchemy PostgreSQL connections, including `?`→named-parameter rewriting (keeping legacy call sites parameterized) and PRAGMA no-op swallowing. `AutoClosingConnection` guards connection lifetime.
- `AppInfoJinja2Templates` (`app/core/templates.py`): template-engine subclass injecting standard context.
- `dia_client.py`: HTTP-service wrapper for TTS.

### 5.4 Module registry & feature gating
- `app/core/modules.py`: `AnalysisModule`/`ModuleTask` dataclasses in a `_MODULES` dict. `ENABLED_MODULES` env (`*`, `none`, or CSV) sets the startup default; the `module_config` DB table overrides at runtime (UI gear icon). Gating is enforced consistently in three places: router mounting, background-task scheduling, and frontend tab exposure (`/api/modules`). Spec: `docs/ANALYSIS_MODULE_PACKAGING_SPEC.md`.
- Tenant-level shape flag: `BW_DEDICATED_MODE` (`app.state.dedicated_bw`) trims a full deployment down to a Brand-Watcher-only product.
- SaaS equivalent: per-tenant feature gates on routers (geohotspots, threatintel, brand-monitoring, social).

### 5.5 Filesystem-discovered tool plugins
- `app/services/tool_plugin_base.py` (`ToolHandler`, `ToolResult`) + `tool_loader.py`: Auspex agent tools are dropped into `data/auspex/plugins/<tool>/{tool.md,config.json,handler.py}` and loaded via `importlib.util`. The monolith MCP server (`app/services/mcp_server.py`) exposes the same tools over **stdio only** (`run_stdio()`) — it is not network-bound and is not a remote-access surface. (This is distinct from the SaaS MCP surface in §4.3, which is HTTP-exposed and API-key-authenticated.)

### 5.6 SSE streaming pipelines
- Long-running analyses stream progress as `text/event-stream` via `StreamingResponse`; used in ≥13 routers (`sio_routes.py`, `auspex_routes.py`, `newsletter_routes.py`, `brand_watcher_routes.py`, `executive_briefing_routes.py`, …). The SIO service yields stage-progress events across its discovery→triage→deep-analysis→synthesis pipeline. nginx vhosts are configured SSE-friendly (`proxy_buffering off`, long read timeouts).

### 5.7 Job / queue
- `app/services/analysis_queue.py` (`AnalysisQueue`: `asyncio.Queue` + N workers, `max_concurrent=3`).
- `BackgroundTaskManager` (`app/services/background_task_manager.py`): DB-persisted `TaskInfo`/`TaskStatus` for restart-surviving job records.
- Route-level long-job endpoints (newsletter/validation/social-reach) return job IDs polled by the client; the SaaS runs these in the dedicated `skills` worker role.

### 5.8 Singletons & resource pooling
- Module singletons behind accessor functions: `get_database_instance()`, `_pg_engine_instance`, `_OPENAI_CLIENT`.
- `app/services/connection_manager.py` (`ConnectionManager`): actively monitors file descriptors and httpx clients (psutil; warning/critical thresholds at 70%/90% of the FD limit) to prevent leak-driven exhaustion.

### 5.9 Strategy cascade (cost-tiered AI)
- Relevance scoring runs a 3-tier cascade — embedding similarity → fine-tuned local classifier (DeBERTa) → LLM adjudication — so the expensive tier only sees ambiguous cases (`hybrid_relevance_service.py`, `relevance_classifier_service.py`; `docs/METHODOLOGY.md`). The same shape (local-first, LLM-fallback) is used for enrichment.

### 5.10 ABC base classes
- `ArticleCollector` (`app/collectors/base_collector.py`), `ToolHandler` (`tool_plugin_base.py`), `app/services/external_data/base_provider.py` — new integrations subclass the relevant ABC and register with the corresponding factory.

---

## 6. Data flows & external integrations (subprocessor inventory)

This table doubles as the vendor/subprocessor inventory SOC 2 vendor-management work requires. All credentials are environment-sourced (encrypted `.env`, §8.2); none are stored in `config.json`/`provider_config.json` (verified — `provider_config.json` holds provider metadata such as `api_key_name` only).

**Data sent outbound** falls into three classes: (A) search queries/keywords only; (B) public article/social content submitted for processing; (C) user or customer data.

| Service | Purpose | Data class | Where configured / used |
|---|---|---|---|
| AWS Bedrock (Anthropic Claude) | All standard-alias chat/completion LLM analysis (both product lines) | B (article text, prompts) | `app/config/litellm_config.yaml`, `AWS_BEDROCK_API_KEY`, `AWS_REGION_NAME`; SaaS `app/ai/llm.py`, `bedrock.key` |
| **Remote LiteLLM/Ollama proxy (`5.9.100.178`)** | Extra model aliases (mixtral/qwen/gemma) via off-host proxy — **undisclosed external subprocessor** | B (prompts, article text) | `app/config/litellm_config.yaml.local` (`:4000`, `:11434`); see §3.6 / Annex A item A19 |
| OpenAI | Embeddings only (`text-embedding-3-small`), and **only on wiley** since 2026-08-02. bugfixing, wileytest and wbm embed locally and send nothing (§3.6) | B | `app/vector_store_pgvector.py`, `OPENAI_API_KEY` |
| Ollama (local) | On-host small-model inference (base config `gemma3:4b`) | none (local) | `OLLAMA_BASE_URL` |
| NewsAPI / TheNewsAPI / Newsdata.io | News search/collection | A | `app/collectors/*_collector.py`, `PROVIDER_*` keys |
| Opoint | Licensed news content | A | `app/collectors/opoint_collector.py`, `OPOINT_BASE_URL` |
| xpoz | Cross-platform social data (X, Reddit, Instagram, TikTok) | A | `app/collectors/xpoz_collector.py`, `XPOZ_API_KEY`; SaaS `app/social/` via `XPOZ_SERVER_URL` |
| Bluesky | Social collection + notifications | A | `app/collectors/bluesky_collector.py` (`PROVIDER_BLUESKY_USERNAME/PASSWORD`) |
| Reddit | Social collection (RSS) | A | `app/collectors/reddit_collector.py` |
| ArXiv / Semantic Scholar | Academic paper collection (open APIs) | A | `app/collectors/`, `app/services/external_data/semantic_scholar.py` |
| Firecrawl | Article full-text scraping | A (URLs) | `app/startup.py`, `FIRECRAWL_API_KEY` |
| Google Custom Search / OpenWebNinja | Web search for research agents | A | `app/services/external_data/google_search.py` (`GOOGLE_API_KEY`, `GOOGLE_CSE_ID`, `OPENWEBNINJA_API_KEY`) |
| Wikidata | Entity verification (brand onboarding) | A | `app/services/wikidata_client.py` |
| CourtListener / SEC EDGAR (`efts.sec.gov`) / regulations.gov | Official-source enrichment (legal, filings, rulemaking) | A | `app/services/bw_official_sources.py`, `app/routes/policy_tracker_routes.py`, `app/tasks/brand_watcher_monitor.py` |
| OpenAlex / Crossref | Scholarly metadata enrichment | A | `app/services/bw_digest_service.py`, official-sources services |
| Glassdoor / trumpactiontracker.info | Ancillary reference sources | A | `app/services/bw_official_sources.py` |
| MBFC (Media Bias/Fact Check) | Source bias/credibility ratings | none (reference data in) | `app/routes/media_bias_routes.py`, `t_mediabias` tables |
| Resend (SMTP fallback) | Email delivery: alerts, digests, health-check notifications | C (recipient emails, report content) | `app/services/email_service.py` (`RESEND_API_KEY`, `SMTP_*`) |
| ElevenLabs / Dia TTS | Podcast/audio generation | B | `ELEVENLABS_API_KEY`; `app/services/dia_client.py` |
| Google / GitHub / Microsoft | OAuth login (both product lines) | C (identity claims) | `app/security/oauth.py`; SaaS `app/auth/routes.py` |
| Stripe | SaaS billing (Checkout + webhooks) | C (billing identity) | SaaS billing routes |
| Aunoo SaaS MCP | Hosted MCP tools consumed by the monolith | B | `AUNOO_SAAS_MCP_URL` / `AUNOO_SAAS_MCP_KEY` |

> **NewsFirehose is NOT in this table** — it was reclassified as an in-boundary self-hosted service (§2.4). It remains the shared upstream article source for both product lines (`app/collectors/newsfirehose_collector.py`; SaaS `NEWSFIREHOSE_BASE_URL` → the local `:8000` stack). This subprocessor inventory should be reconciled against the encrypted `.env` of each deployment before audit, since which providers are actually active is per-tenant.

**Primary internal data flow (monolith):** collectors fetch articles per topic keyword groups → dedup/URL normalization → enrichment (local DeBERTa classifiers, LLM fallback) → relevance cascade stamps `topic_alignment_score` → storage in PostgreSQL + pgvector embedding → analysis surfaces, agents, reports, and alerting read from the scored corpus. Full methodology: `docs/METHODOLOGY.md`.

**Primary internal data flow (SaaS):** NewsFirehose ingestion (~550k articles, `external_id = nf_<id>`) → analyst pipeline loops (embedding, classification, novelty, narratives) → shared corpus readable by all tenants; tenant-scoped artifacts (agents, findings, digests) written under RLS.

---

## 7. Deployment & operations

### 7.1 Process supervision (monolith tenants)

The **standard** tenant unit (`/etc/systemd/system/<slug>.aunoo.ai.service`) runs `app/server_run.py` under the unprivileged user `orochford`, bound to a unique loopback port (bugfixing: 10004; wiley: 10006; others in the 100xx range; provisioner allocates from 10018–10100 via `pick_port()`), and integrates the secrets lifecycle: `ExecStartPre` decrypts `.env`, `ExecStopPost` re-encrypts and deletes the plaintext (verified in `bugfixing.aunoo.ai.service:13,19,22`; see §8.2).

**Exceptions to this uniformity exist and must be remediated for the "consistent unprivileged user + uniform secrets lifecycle" control to hold.** A few legacy tenant units (`oliver.aunoo.ai.service`, `secops.aunoo.ai.service`, `wiley1.aunoo.ai.service`) run `User=www-data` with the system `/usr/bin/python3` and **no `ExecStartPre` env-decryption step**. These are currently inactive/disabled but exist as enabled configuration drift (`www-data` is a shared web account, weakening isolation). Recorded as Annex A item A21.

### 7.2 Process supervision (SaaS)

- `saas.aunoo.ai.service` (prod web, :10017) and `saasmvp.aunoo.ai.service` (staging web, :10016): `uvicorn app.main:app --host 127.0.0.1`, `EnvironmentFile=.env`. Effective worker count is 4 (the prod base unit's ExecStart is `--workers 1`, overridden to 4 by a `saas.aunoo.ai.service.d/*.conf` drop-in; the staging base unit is `--workers 4` directly). These currently run as `User=root` (Annex A item 10).
- Worker units: `saas-worker.service` / `saas-skills-worker.service` / `saasmvp-skills-worker.service` (`python -m app.workers.pipeline_worker`, `WORKER_ROLE=skills`).
- `saasmvp-classifier.service`: SLM classifier on :8012.

### 7.3 Ingress & TLS

nginx vhosts per domain (`/etc/nginx/sites-enabled/`), TLS via Let's Encrypt/certbot with 80→443 redirect, `proxy_pass` to the deployment's loopback port, `client_max_body_size 10M`, SSE-friendly proxy settings. ModSecurity is installed but commented out in the site configs (Annex A item 2); `setup_site.py` supports `--no-enable-modsec` because enabling it has broken `nginx -t` box-wide in the past.

**Certificate renewal is not evidenced as automated.** `certbot.timer` and `snap.certbot.renew.timer` are both `inactive`, and there is no `/etc/cron.d/certbot`. Certificates are renewed in practice (recent cert files exist), likely at provisioning time via `setup_site.py`, but there is no running renewer for the ~91 existing certificate directories — a realistic silent-expiry outage across live domains. Recorded as Annex A item A22 (availability).

### 7.4 Database operations

- Single PostgreSQL 16 instance; one database + one dedicated role per monolith tenant (`<slug>_user`, unique generated password), one database for SaaS with the `aunoo_app`/`aunoo_admin` RLS role pair.
- pgbouncer on :6432 fronts some tenants (session mode); the provisioning script wires new clones directly to :5432 (partial adoption — an operational inconsistency worth normalizing).
- Migrations: Alembic in both codebases. SaaS `alembic/env.py` rewrites the async URL to sync for migration runs. A known nuance (documented in SaaS `DEPLOY_NOTES.md`): migrations run via the postgres superuser left some tables postgres-owned, patched by `ALTER DEFAULT PRIVILEGES` grants in `setup_rls.sql`.

### 7.5 Tenant provisioning

`scripts/provision_brand_tenant.py` creates a tenant end-to-end: directory copy (with exclusion rules for key files), relocatable venv, database restore from the golden dump (`/var/tmp/bw_template.dump`), fresh per-tenant secrets (`FLASK_SECRET_KEY`/`NORN_SECRET_KEY` via `secrets.token_hex(32)`, DB password via `secrets.token_hex(24)`), bcrypt-hashed admin password, systemd unit, nginx vhost + certbot. Cloned tenants have alert delivery targets cleared (`bw_alert_config`) to prevent cross-tenant email/webhook delivery. Admin credentials are written to `/var/tmp/<slug>_credentials.txt` (`chmod 600`, root-only — flagged in Annex A item 8).

### 7.6 Monitoring & health

- A root cron runs `collector_health_check.sh` every 30 minutes across production tenants, checking a keyword-monitor heartbeat and a 12-hour article-ingest floor, alerting by email (Resend). This control exists because a hung third-party call (Firecrawl, no timeout) once silently froze a tenant's collection for two days; the ingest path now wraps collector calls in `asyncio.wait_for`.
- Other scheduled jobs on the host (for ops/change-inventory completeness): a root cron runs `saasmvp-app/scripts/daily_import.py` daily at 05:00 (a SaaS ingestion job); the `orochford` crontab runs `health_monitor.py` every 15 minutes, `monitor_pg_connections_24h.sh` every 5 minutes, and periodic CSV/JSON log-retention cleanups.
- In-process: the event-loop lag monitor (§3.3) and `ConnectionManager` FD monitoring (§5.8).
- SaaS: orphaned-run reapers at startup; an `analyst/observability` router.

### 7.7 Frontend deploys

Monolith: `./ui/deploy-react-ui.sh` (build → copy to `static/trend-convergence/` → template hash rewrite) then `systemctl restart <tenant>`. Cross-tenant static sync must use `rsync -av --delete` (hashed filenames make `cp -r` accumulate stale bundles). SaaS: `scripts/deploy-ui.sh`.

### 7.8 Backups

Current state: golden template dumps and per-tenant provisioning dumps under `/var/tmp` (`root:postgres`, `chmod 640`), plus dated directory backups of the SaaS prod deployment (`saas.aunoo.ai.bak-*`). There is no evidenced scheduled backup job with retention/restore testing — recorded as Annex A item 15.

---

## 8. Security controls

Current state only. Each control names its implementation so it can be audited against the code.

### 8.1 Authentication & session management

**Monolith**

- **Password storage**: bcrypt via passlib `CryptContext` — `bcrypt__default_rounds=12`, ident `2b` (`app/security/auth.py:35-38`). The tenant provisioner hashes generated admin passwords with the same context.
- **Primary auth is server-side session cookies** (Starlette `SessionMiddleware`, signed with `FLASK_SECRET_KEY`; `app/middleware/setup.py:12-14`). JWT support (python-jose, HS256, `NORN_SECRET_KEY`, 30-min expiry constant at `auth.py:16`) exists but is not the active path (`app/security/AUTH_PATTERNS.md`).
- **Per-request re-validation**: `verify_session` / `verify_session_api` (`app/security/session.py`) reload the user from the database on every request and enforce the `is_active` flag for both traditional and OAuth users — deactivating a user invalidates their live sessions immediately (they get a 307 to `/login` or a 401).
- **Login flow** (`app/routes/auth_routes.py`): form login with bcrypt verification, inactive-account check, and a bootstrap path — submitting `admin`/`admin` auto-creates the admin account (bcrypt-hashed, `force_password_change=True`) if it doesn't exist. Password verification still runs afterward (`auth_routes.py:80`), so this path cannot bypass a changed admin password; the residual issues are recorded in Annex A item 4.
- **Password reset**: HMAC-SHA256-signed reset links (24h TTL), bound to a prefix of the current password hash so a used link self-invalidates, compared with `hmac.compare_digest`.
- **OAuth**: Authlib (`app/security/oauth.py`) with Google, Microsoft (OIDC `openid email profile`) and GitHub (`user:email`), each enabled only when its client credentials exist. Access control: `ALLOWED_EMAIL_DOMAINS` domain allowlist plus a DB-backed `oauth_allowlist` table (`app/security/oauth_users.py`); denials are logged.
- **Authorization model**: coarse two-level roles — a `role` string on the users table, admin routes gated by `require_admin` → `check_user_is_admin` → 403 (~13 call sites across `app/routes/`). No fine-grained RBAC, no MFA (Annex A item 9).

**SaaS**

- **JWT in an httpOnly cookie** (`aunoo_session`; `app/auth/jwt.py`): HS256 signed with `JWT_SECRET`, payload `{sub, tenant_id, role, is_impersonation, iat, exp}`, default 24h expiry; no refresh tokens. OAuth login (Google/GitHub/Microsoft via Authlib).
- **Startup secret enforcement**: `_enforce_secret_config()` (`app/core/app_factory.py:20-47`) refuses to boot outside DEBUG if `JWT_SECRET` is empty or still the `CHANGE-ME-IN-PRODUCTION` placeholder — weak-secret deployments fail closed.
- **Middleware-enforced authn** (`app/auth/middleware.py`): 401 on protected routes without a valid token, 403 for `pending` users; public prefixes are an explicit allowlist (health, auth, public feeds, skills, OAuth discovery, legal reads, billing webhook).
- **Role dependencies**: `require_platform_admin`, `require_marketing`, `require_tenant_admin` (`app/auth/dependencies.py`) gate privileged routers; the entire `/api/v1/admin` surface is gated independently of the DB role switch (§4.4).
- **API-key auth for Skills/MCP** (`app/skills/dispatcher.py`, `rest.py`): Bearer tokens are **stored and matched as SHA-256 hashes** (`APIKey.key_hash`), carry `tenant_id` + scopes, and inject `allowed_topic_ids` into every tool call for per-topic data scoping. WebSub/Fever feed sync uses its own api-key/HMAC auth.

### 8.2 Secrets management

- **Encryption at rest for `.env`** (box-wide mechanism, `/home/orochford/bin/env_encryption.py`): AES-256-GCM authenticated encryption with per-file salt and PBKDF2-HMAC key derivation (100,000 iterations) from a master key at `/home/orochford/.env-master-key` (mode 400). systemd integrates the lifecycle — `ExecStartPre` decrypts, `ExecStopPost` re-encrypts and removes the plaintext — so plaintext `.env` exists only while a service runs. On disk: `.env.encrypted` mode 400, transient `.env` mode 600. Every encrypt/decrypt/verify operation is logged to `/var/log/aunoo-env-access.log`.
- **Loading**: `app/env_loader.py` (python-dotenv, `override=True`) with `sync_api_keys()` propagating keys across legacy/standardized names; debug logging masks values to first/last 4 characters.
- **No secrets in config files**: verified — `app/config/config.json` and `provider_config.json` contain no API keys; provider entries reference env-var names only.
- **Per-tenant uniqueness**: the provisioner generates fresh session secrets and DB passwords per tenant (§7.5), so no secret is shared between tenants.
- Known residue (plaintext key files and `.env` backups on disk) is recorded in Annex A item 8.

### 8.3 Injection defenses & input validation

- **SQL**: the query facade and route code use parameterized SQLAlchemy execution throughout — named bind parameters (`:brand_id`, `= ANY(:uris)`), no f-string SQL on user input (survey verified; the only f-string `execute()` calls in `app/database.py` interpolate schema-derived table names in SQLite `PRAGMA` calls and a `db_type` literal, none user-controlled). Legacy `?`-placeholder call sites remain parameterized through the cursor wrapper's placeholder rewriting (§5.3).
- **Request validation**: Pydantic models with field constraints on request bodies in both codebases; a custom 422 handler in each app factory. SaaS uses pydantic-settings for typed configuration.
- **Reviewed exception**: the SaaS RLS tenant setter interpolates `int(tenant_id)` into `SET LOCAL` (`app/database/session.py:43,84`) — non-injectable due to the integer cast; documented here as a reviewed pattern rather than a defect.

### 8.4 LLM safety (SaaS)

`app/security/prompt_guard.py`: a two-stage prompt-injection/jailbreak detector — regex heuristics plus the HuggingFace `protectai/deberta-v3-base-prompt-injection-v2` model — with `block`/`flag`/`allow` outcomes at 0.95/0.50 score thresholds (`prompt_guard.py:35-36`), a 2,000-character analysis cap, model warm-up at startup, and an audit recorder (`app/security/recorder.py`). The monolith has no equivalent inbound guard (its LLM inputs are collected articles rather than end-user free text, but Auspex chat is user-facing — see Annex A item 6 note).

### 8.5 Transport security

- TLS terminated at nginx for every domain (certbot; 80→443 redirect at the vhost level).
- App-level `HTTPSRedirectMiddleware` (`app/middleware/https_redirect.py`) is added when `ENVIRONMENT=production` (`app/main.py:207`), honoring `X-Forwarded-Proto`; uvicorn runs with `proxy_headers=True`.
- CORS: the monolith's systemd entrypoint (`app/server_run.py:32-33`) locks `allow_origins` to the tenant's own origin with `allow_credentials=True`. SaaS locks CORS to `APP_URL` outside DEBUG.
- **Per-tenant application uvicorn processes are loopback-bound.** However, **the host as a whole is not network-isolated**: there is no firewall (ufw inactive, iptables INPUT ACCEPT) and several *other* services on the box are bound to `0.0.0.0`/public IPv6 (§2.3: LiteLLM proxy `:4000`, NewsFirehose `:8000`, Docker containers `:8080`/`:8443`, vLLM). So while a tenant app port isn't directly reachable, the sentence "no app port is directly reachable from outside the host" is **not** true at the host level. Do not represent host-level network isolation as an implemented control (Annex A item A18).
- Gaps in this area (no security headers, unhardened session-cookie attributes, staging DEBUG, no firewall, SSH password auth) are Annex A items 2, 3, 11, A18, A26.

### 8.6 Tenant isolation

- **Monolith**: isolation by construction — separate process, port, database, DB role/password, and encrypted secrets per tenant. There is no shared query path between tenant databases. Residual shared-host risk (multiple tenants under one OS user `orochford`, a single shared PostgreSQL instance, a single master key, and *other* OS/service accounts on the same box — `newsfirehose`, `laouad`, `www-data`) is Annex A item 10 (corrected).
- **SaaS**: application-layer tenant context plus PostgreSQL RLS (§4.4), with the admin bypass role separately authorization-gated.

### 8.7 Audit & logging

- **Secrets access log**: `/var/log/aunoo-env-access.log` records every `.env` encrypt/decrypt/verify with timestamps (§8.2).
- **Review audit trail**: Brand Watcher finding reviews write an append-only transition log — `bw_finding_review_log` captures `old_status`, `new_status`, `actor`, `note` on every state change (`app/routes/brand_watcher_routes.py:4917`), alongside the current-state `bw_finding_reviews` table.
- **Auth events**: failed logins (user-not-found, bad password, inactive account) and OAuth allowlist changes/denials are logged through the application logger (`auth_routes.py`, `session.py`, `oauth_users.py`); `last_login` is tracked for OAuth users.
- **LLM guard audit**: SaaS prompt-guard decisions are recorded (`app/security/recorder.py`).
- Limitations (no dedicated auth-audit table, no centralized log store/SIEM, no failed-login counters) are Annex A item 12.

### 8.8 Data protection

- **Credentials**: DB credentials only in the encrypted `.env` (never in code); per-tenant unique DB passwords; OAuth client secrets env-only.
- **PII inventory**: primary PII is account email addresses (users, OAuth allowlist, alert recipients) plus OAuth identity claims and SaaS billing identity (held by Stripe). Stored in PostgreSQL without field-level encryption; protected in transit by TLS and at rest by filesystem permissions and DB access control.
- **Cross-tenant delivery prevention**: provisioning clears cloned alert recipients (§7.5).
- **Collected content** is public news/social data by nature; the sensitive assets are customer configurations (topics, brands, keywords — competitive intelligence about what customers watch), findings/reports, and account data.

### 8.9 Endpoint access-control exceptions

The session/JWT/OAuth model in §8.1 covers most routes, but several endpoints deviate and are called out here for the access-control control (least privilege / CC6.1):

- **Unauthenticated, secret-writing**: `POST /api/onboarding/validate-api-key` (`app/routes/onboarding_routes.py`) has no `verify_session` dependency yet writes caller-supplied API keys in plaintext to `.env` and `os.environ`, bypassing the encryption mechanism of §8.2 (Annex A item A20 — high).
- **Unauthenticated diagnostics**: `GET /api/admin/event-loop-status?dump=1` (`app/routes/admin_diagnostics_routes.py`) is unauthenticated "by design" and returns full thread stack dumps, which can leak query fragments, paths, and in-memory secrets (Annex A item A20).
- **Under-privileged DB endpoints**: `/api/databases/download/{db_name}` and `/api/databases/backup` (`app/routes/database.py`, the latter shells out to `pg_dump`) are gated by `verify_session` only, not `require_admin` — any authenticated user can dump/download the tenant database (Annex A item A20 — high).
- **Unauthenticated WebSockets**: `/ws/bulk-process/{job_id}` and `/ws/progress/{topic_id}` (`app/routes/websocket_routes.py`) call `accept()` with no token/session check (Annex A item A20).

### 8.10 Dependency & vulnerability management

There is currently **no evidenced dependency- or vulnerability-management process** — a standard ISO 27001 Annex A 8.8 (technical vulnerability management) expectation. `requirements.txt` pins only ~6 of ~60 dependencies exactly; auth-critical libraries under the JWT/OAuth path (`python-jose[cryptography]`, `authlib`, `PyJWT`, `cryptography`, `requests`) are unpinned; there is no lockfile (`poetry.lock`/`uv.lock`/`Pipfile.lock`) and no `dependabot.yml` / scheduled scan. Recorded as Annex A item A27.

### 8.11 Host / OS hardening

Auditable host facts (mixed):
- **SSH**: `PermitRootLogin no` (good), but `PasswordAuthentication yes` and no `fail2ban` (inactive) — combined with the absent firewall (§2.3), SSH is brute-forceable from the internet (Annex A item A26).
- **Patch management**: `unattended-upgrades` is **active** (a positive control worth citing).
- **Firewall**: none (§2.3 / Annex A item A18).
- **Config drift / dead units**: several failed or stuck aunoo units exist (`celery-aunoo-multi.service` failed — points at a nonexistent `multi.aunoo.ai` dir; `aunooai-flower.service` failed; `test.aunoo.ai` stuck activating), cluttering the asset baseline (Annex A item A28).

---

## Annex A: Known gaps & remediation candidates

This annex is the honest backlog. Items are stated factually with pointers; none are control claims. Ordering is roughly by risk-relevance for the compliance program, not strict severity. Estimated efforts are for AI-assisted implementation.

| # | Gap | Detail / pointer | Remediation candidate |
|---|---|---|---|
| 1 | No inbound rate limiting or brute-force protection | No limiter on `/login` or any endpoint, no account lockout or failed-attempt counters (monolith and SaaS web tier) | Add slowapi/nginx rate zones on auth + expensive endpoints; lockout with backoff. ~half-day |
| 2 | No security response headers; WAF disabled | No CSP/HSTS/X-Frame-Options/X-Content-Type-Options set by either app; live nginx vhosts don't add them; ModSecurity present but commented out (SaaS repo `nginx.conf` specs headers that the live vhost lacks) | Add a headers middleware or nginx `add_header` block per vhost; decide ModSecurity stance once. ~half-day |
| 3 | Session cookies not hardened (monolith) | `SessionMiddleware` gets only `secret_key` (`app/middleware/setup.py:12-14`): no `https_only=True`, no explicit `same_site`, default ~14-day lifetime | Pass `https_only=True, same_site="lax", max_age=<policy>`. ~1 hour |
| 4 | `admin/admin` bootstrap path | `auth_routes.py:49` — cannot bypass a changed password (bcrypt verify still runs, line 80), but any unauthenticated request can re-create a deleted admin account or flip `force_password_change` on the real one | Gate bootstrap behind first-run state or an env flag. ~1 hour |
| 5 | Weak hardcoded fallback secrets | `NORN_SECRET_KEY` → `'nornforever'` (`auth.py:14`), `FLASK_SECRET_KEY` → `'your-fallback-secret-key'` (`setup.py:13`), reset-token secret fallback. Provisioner sets strong values, so this bites only manual deployments — but it's a fail-open default | Fail closed like the SaaS `_enforce_secret_config()` pattern. ~1 hour |
| 6 | No SSRF protections on outbound fetch/scrape paths | Core scraping/collection paths (Firecrawl, collectors, feed fetchers) apply no scheme/private-IP/metadata-endpoint filtering to URLs, some of which are user-suppliable (RSS feed URLs, submitted articles) | Central URL validator (scheme allowlist, deny RFC1918/link-local/metadata IPs, resolve-then-check) on all outbound fetches. ~1 day |
| 7 | No CSRF tokens on form posts (monolith) | State-changing form endpoints rely on the session cookie; default SameSite=lax is partial mitigation only | CSRF middleware or per-form tokens; pairs with item 3. ~half-day |
| 8 | Plaintext secret residue on disk | `.env.backup`, `.env.pre_bedrock_*` copies; root-level key files `opointkeys`, `xpozkey`, `webninjakey`; `/var/tmp/<slug>_credentials.txt`; SaaS `.env.bak*` + `bedrock.key` (git-ignored but on disk) | Sweep and delete/encrypt; move key material into `.env`; provisioner already excludes some key files from clones. ~2 hours + policy. **See A16b for the more serious committed-secret case.** |
| 8b (A16b) | **Secrets committed to git** — worse than on-disk residue | `.env.hub` (and `aunooai-docker/.env.hub`) are **tracked in git** (`git ls-files`) with populated real values for `POSTGRES_PASSWORD` and `ADMIN_PASSWORD` (the API-key lines in that file are empty). Recoverable from history on every clone/GitHub, so **rotation is mandatory**, not optional | Rotate the committed DB and admin passwords now; `git rm` the files, add to `.gitignore`, and scrub history (BFG/filter-repo). ~half-day + rotation |
| 9 | Coarse authorization; no MFA/SSO enforcement | Binary admin/user role string (monolith); no MFA anywhere; SaaS has platform/tenant/marketing roles but no finer permissions. `AUTH_PATTERNS.md` lists RBAC/MFA as planned | Scope per compliance requirements; OAuth+allowlist partially compensates for workforce access |
| 10 | Shared-host blast radius; SaaS runs as root; multi-user box | All monolith tenants share one OS user (`orochford`) and one PostgreSQL instance; compromise of the user or the master key (`/home/orochford/.env-master-key`) exposes every tenant. SaaS web/worker units run `User=root` (`saas.aunoo.ai.service:7`, `saasmvp.aunoo.ai.service:7`). The host also carries *other* service accounts (`newsfirehose`, `laouad`) and a Docker estate (§2.4), widening the blast radius beyond the original "single OS user" framing | Dedicated unprivileged user per SaaS service (quick win, ~1 hour); longer-term per-tenant OS users or containerization; inventory and least-privilege the non-Aunoo accounts |
| 11 | `DEBUG=True` on SaaS staging | Widens CORS to `*` and relaxes the secret-enforcement gate on saasmvp.aunoo.ai | Run staging with `DEBUG=False` + explicit `APP_URL`. ~minutes |
| 12 | Audit logging is app-log based | No dedicated auth-audit table for traditional logins, no centralized/tamper-resistant log store, no log retention policy; `bw_finding_review_log` and the env-access log are the exceptions | Auth-events table + ship logs off-host (journald → remote); define retention. ~1 day |
| 13 | Query-facade technical debt | `app/database_query_facade.py` is ~14,000 lines / 548 KB with residual `# TODO SQLAlchemy` markers — a change-control and review-surface concern (not an active injection finding; §8.3) | Incremental decomposition; no urgent security action |
| 14 | Dead code & stale artifacts in the repo | Committed `.backup.*`/`.phase1` source copies, retired session/vector-store backups, binary artifacts (pptx/zip) in the working tree | Housekeeping sweep; add ignore rules. ~2 hours |
| 15 | No evidenced backup schedule or restore testing | Golden dumps and ad-hoc `.bak-*` directory copies exist (§7.8), but no scheduled DB backups with retention and tested restore — an availability-criteria gap for SOC 2 | Nightly `pg_dump` per DB + off-host copy + documented restore test. ~half-day |
| 16 | Single-host single-point-of-failure | All tenants, both product lines, DB, and ML services share one machine; no failover | Acknowledge in the risk register; mitigation is a roadmap decision, not a quick fix |
| A17 | No authoritative asset register | Tenant/deployment inventory is ~2× what earlier drafts listed (§2.1); ~91 certs and many systemd units, some failed/stale. An audit's foundation is a current, controlled asset list | Generate from the host (`ls`, `systemctl`, `/etc/letsencrypt/live`) and maintain as controlled evidence. ~half-day |
| A18 | **No host firewall; non-loopback public listeners** | ufw inactive, iptables INPUT ACCEPT; `0.0.0.0` listeners on `:4000` (LiteLLM), `:8000` (NewsFirehose), `:8080`/`:8443` (Docker), plus vLLM on public IPv6 (§2.3). Contradicts the network-isolation control narrative | Add ufw/nftables default-deny, allow only 80/443/22; bind internal services to loopback; re-verify with `ss`. ~half-day. **High.** |
| A19 | Undisclosed remote LLM subprocessor / data-residency | `litellm_config.yaml.local` routes extra aliases to off-host `5.9.100.178:4000`/`:11434` (§3.6); prompts/article text leave the boundary to an undocumented third party | Decide if the remote proxy is authorized; if not, remove the `.local` aliases; if yes, add a DPA and list it as a subprocessor. ~2 hours |
| A20 | **Endpoint access-control exceptions** | Unauthenticated secret-writing (`/api/onboarding/validate-api-key`), unauthenticated thread-dump diagnostics (`/api/admin/event-loop-status?dump=1`), non-admin DB download/backup (`/api/databases/*`), unauthenticated WebSockets (`/ws/*`) — see §8.9 | Add auth dependencies; make DB endpoints admin-only; authenticate WebSockets; gate the diagnostic dump. ~half-day. **High.** |
| A21 | Non-uniform tenant units (`www-data`, no secret decryption) | `oliver`/`secops`/`wiley1` units run `User=www-data` with system python and no `ExecStartPre` decrypt (§7.1); breaks the "uniform unprivileged user + secrets lifecycle" control | Normalize to the standard unit template or remove the dead units. ~1 hour |
| A22 | Certificate renewal not automated | `certbot.timer`/`snap.certbot.renew.timer` inactive, no cron (§7.3); silent-expiry risk across ~91 domains | Enable the certbot systemd timer and monitor expiry. ~1 hour. (Availability.) |
| A23 | Open OAuth 2.1 DCR endpoint | `POST /oauth/register` is unauthenticated, unthrottled client registration (§4.3); standard RFC 7591 but a public write surface | Add rate limiting (pairs with item 1) and monitoring; consider gating registration. ~2 hours |
| A24 | User-controlled regex in `kissql` DSL (ReDoS) | `app/kissql/parser.py:116` compiles query-derived regex; exposed via vector routes (§3.6) | Bound/timeout regex or use a safe matcher; also confirm whether the (ChromaDB-era) DSL is still needed. ~2 hours |
| A25 | Impersonation feature has no audit trail (latent) | `is_impersonation` is defined/read but dormant (§4.4); if wired later without an audit log it becomes an unlogged privileged action | Add an impersonation audit-log requirement before enabling the capability |
| A26 | SSH password auth; no fail2ban | `PasswordAuthentication yes`, `fail2ban` inactive; with no firewall (A18) SSH is internet-brute-forceable (§8.11). Positive: `unattended-upgrades` active | Disable SSH password auth (keys only), install fail2ban, restrict SSH via firewall. ~1 hour |
| A27 | No dependency/vulnerability management | ~6/60 deps pinned, auth libs (`python-jose`, `authlib`, `cryptography`) unpinned, no lockfile, no scanning (§8.10) — ISO A.8.8 gap | Pin + lockfile, add dependabot/scanning, patch cadence. ~half-day |
| A28 | Failed/stale systemd units | `celery-aunoo-multi` (missing dir), `aunooai-flower` failed, `test.aunoo.ai` stuck activating (§8.11); config drift masks real failures | Remove or fix dead units; clean the unit inventory. ~1 hour |

---

## Annex B: Source document index

Deeper documents this master doc links rather than duplicates. Trust ordering: code > this document > the linked docs where they conflict.

| Document | Covers | Currency note |
|---|---|---|
| `docs/METHODOLOGY.md` | End-to-end intelligence lifecycle: collection, dedup, enrichment dimensions, 3-tier relevance cascade, DeBERTa taxonomy, foresight synthesis | Good; provider list trails code (omits Opoint/xpoz/Reddit) |
| `docs/sio_architecture_documentation.md` (+ `SIO_QUICK_REFERENCE.md`) | Strategic Intelligence Oracle: 4-stage pipeline, quality gates, SSE streaming, audit trail | Content current; hard-coded paths reference another tenant |
| `docs/ANALYSIS_MODULE_PACKAGING_SPEC.md` | Module registry design (`app/core/modules.py`), `ENABLED_MODULES`, conditional mounting | Implemented, 2026-02-06 |
| `docs/MODULE_CONFIG_UI.md` | Runtime module toggles (DB schema, API, UI) | Current |
| `app/security/AUTH_PATTERNS.md` | Monolith auth patterns and planned enhancements | Current; "planned" items restated here as Annex A item 9 |
| `docs/README_Plugins.md`, `docs/PLUGIN_DATA_FILTERING.md` | Auspex tool-plugin system | Current |
| `docs/OBSERVER_AGENTS.md` | Observer agent (signal instructions) system | Current |
| `docs/SLM_PIPELINE_SUMMARY.md`, `docs/MODEL_DEPLOYMENT.md` | Local model training/deployment | Current |
| `docs/BRAND_WATCHER_TENANT_TEMPLATE.md` | BW-dedicated tenant provisioning playbook | Current |
| `docs/METHODOLOGY.md` §sources + `docs/opoint_evaluation.md` | Collector/source evaluation | Current |
| `saasmvp/00-overview.md` … `10-infrastructure.md` | Original SaaS MVP design spec | **Drifted**: spec says port 10015, Docker Compose, in-process tasks, ~30 tables; reality is systemd on 10016/10017, split web/worker roles, 191 models. Use for intent only |
| `saasmvp-app/CLAUDE.md`, `saasmvp-app/DEPLOY_NOTES.md` | SaaS codebase conventions and deploy nuances | Current |
| `saasmvp-app/docs/NEWSFIREHOSE_DATA_QUALITY_FINDINGS.md`, `DEBERTA_EMBEDDING_DIMS.md`, `SOCIAL_ANALYSIS_PORT_PLAN.md`, `BRAND_MONITORING_ENHANCEMENTS_SCOPE.md` | SaaS↔ecosystem integration points | Current |
| `docs/FIRECRAWL_BILLING_INCIDENT_REPORT.md` | Incident record (input to §7.6 health-check control) | Historical record |
| `AUNOO_SOLUTION_DATASHEET.md`, `docs/README.md` | Product-level descriptions / feature inventory | Marketing-oriented; low architectural depth |
