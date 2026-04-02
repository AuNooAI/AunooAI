# AunooAI — End-to-End Workflow Validation Report

---

## Step 1: Workflow Map

### 1.1 Entrypoints

| Entrypoint | File | Mechanism |
|---|---|---|
| **Docker production** | `docker-entrypoint.sh` | Runs `alembic upgrade head`, then `python app/run.py` |
| **`run.py`** | `app/run.py` | Loads `.env`, checks DB, calls `from main import app`, starts Uvicorn on `main:app` |
| **`main.py` (module import)** | `app/main.py:99` | `app = create_app()` triggers the factory |
| **`create_app()`** | `app/core/app_factory.py:245-318` | Builds `FastAPI(lifespan=lifespan)`, calls `setup_middleware`, `register_routers`, `initialize_application` |
| **Lifespan (startup)** | `app/core/app_factory.py:23-207` | Initializes async DB pool, calls `initialize_application()` (2nd time), then spawns 7+ background monitors via `asyncio.create_task` |

**Startup call sequence:**
1. `run.py` → imports `main.py` → `create_app()` is called
2. `create_app()` → `setup_middleware(app)` → `register_routers(app)` → `initialize_application()` **(1st call)**
3. After `create_app()` returns to `main.py`, 29 additional `app.include_router()` calls execute **(duplicate registrations)**
4. Uvicorn starts → lifespan `startup` fires → `initialize_async_db()` → `initialize_application()` **(2nd call)** → spawns background monitors

### 1.2 Core User Workflows

#### WF-1: Login (Traditional)

| Aspect | Detail |
|---|---|
| **Routes** | `POST /login` — defined in **both** `app/main.py:301` and `app/routes/auth_routes.py:39` |
| **Dependencies** | `Database.get_user()` → SQLAlchemy query on `t_users`, `verify_password()` via bcrypt |
| **Inputs** | Form: `username`, `password` |
| **Outputs** | Session cookie set → redirect to `/`, `/change_password`, or `/onboarding` |
| **Side effects** | Auto-creates admin user if `admin/admin` creds used; sets `force_password_change` |
| **Error handling** | Catches all exceptions, returns login page with "Invalid username or password" |
| **Invariants** | `is_active` check exists in `auth_routes.py:96` but **missing** in `main.py:301` |

#### WF-2: Session Verification (all protected routes)

| Aspect | Detail |
|---|---|
| **Function** | `verify_session()` in `app/security/session.py:22` |
| **Dependencies** | `db.facade.get_user_by_username()` or `db.facade.get_user_by_email()` → `DatabaseQueryFacade._execute_with_rollback()` → `Database._temp_get_connection()` |
| **Inputs** | `request.session` (Starlette SessionMiddleware cookie) |
| **Outputs** | Enhanced session dict with `user` as a **dict** (not string), or raises `HTTPException(307)` |
| **Critical detail** | Returns `session["user"] = {"username": ..., "email": ..., "role": ..., "is_active": ...}` — callers expecting a string must handle this |

#### WF-3: Article Collection

| Aspect | Detail |
|---|---|
| **Route** | `GET /api/collect_articles` — `app/main.py:1345` |
| **Auth** | **None** — no `verify_session` dependency |
| **Dependencies** | `CollectorFactory.get_collector(source, db)` → 8 collector classes; requires API keys per source |
| **Inputs** | Query params: `source`, `query`, `topic`, `max_results`, dates, filters |
| **Outputs** | JSON: `{articles: [...], article_count, source, query, topic}` |
| **Side effects** | Enriches articles with `MediaBias` data from DB |
| **Error handling** | Catches all exceptions → `HTTPException(500)` with raw error detail |

#### WF-4: Article Research/Analysis

| Aspect | Detail |
|---|---|
| **Route** | `POST /research` — `app/main.py:384` |
| **Auth** | `Depends(verify_session)` |
| **Dependencies** | `Research` (via `get_research`) → `ArticleAnalyzer` → `get_ai_model()` (LiteLLM), `Firecrawl` (scraping) |
| **Inputs** | Form: `articleUrl`, `summaryLength`, `summaryVoice`, `summaryType`, `selectedTopic`, `modelName` |
| **Outputs** | JSON with analysis results (category, sentiment, future signal, etc.) |
| **Side effects** | Saves article + analysis to DB; scrapes article content via Firecrawl |
| **Error handling** | Falls back to basic article info if no AI model available |

#### WF-5: Article Search

| Aspect | Detail |
|---|---|
| **Route** | `GET /api/search_articles` — `app/main.py:867` |
| **Auth** | `Depends(verify_session)` |
| **Dependencies** | `db.search_articles()` — `app/database.py:1852` |
| **Inputs** | Query params: `topic`, `category[]`, `sentiment[]`, `keyword`, `dateRange`, `page`, `per_page` |
| **Outputs** | JSON: `{articles: [...], total_count, page, per_page}` |
| **Error handling** | No explicit try/catch — uncaught exceptions yield 500 |

#### WF-6: Auto-Ingest Pipeline (Background)

| Aspect | Detail |
|---|---|
| **Routes** | `app/routes/auto_ingest.py` — 9 endpoints under `/api/auto-ingest/` |
| **Auth** | Only 1 of 9 endpoints (`POST /api/auto-ingest/run`) uses `Depends(verify_session)` |
| **Dependencies** | `AutoIngestService` → `AsyncDatabase`, collectors, `ArticleAnalyzer`, LiteLLM |
| **Trigger** | Manual via `POST /api/auto-ingest/run`, or automatic via keyword monitors |

#### WF-7: Background Monitors (Lifespan-spawned)

| Aspect | Detail |
|---|---|
| **Monitors** | keyword, emerging_topics, observer_agent, newsfeed_dashboard, rss_feed, geopolitical_hotspots, threat_intelligence, + dynamic module monitors |
| **Startup** | `asyncio.create_task(delayed_xxx_start())` — staggered by 5s each |
| **Dependencies** | Each monitor uses `db._temp_get_connection()` for DB, various collectors for data |
| **Shutdown** | **None** — no task cancellation in lifespan shutdown; tasks are orphaned |
| **Error handling** | Each monitor catches exceptions in the outer delayed_start wrapper only |

#### WF-8: Health Check

| Aspect | Detail |
|---|---|
| **Route** | `GET /health` — `app/routes/health_routes.py:353` |
| **Auth** | None (correct for health probes) |
| **Dependencies** | None for basic; detailed checks use `psutil`, `Database()`, ChromaDB |
| **Problem** | `get_database_health()` creates a **new** `Database()` instance each call (`health_routes.py:32`) instead of using the singleton |

### 1.3 Dependency Graph (Simplified)

```
run.py → main.py → create_app()
          ├─ app_factory.py
          │   ├─ middleware/setup.py (SessionMiddleware)
          │   ├─ core/routers.py (register_routers → 50+ routers)
          │   ├─ startup.py (initialize_application)
          │   │   ├─ env_loader.py
          │   │   └─ ai_models.py (LiteLLM router)
          │   └─ database.py (Database singleton)
          │       ├─ SQLAlchemy engine (PG or SQLite)
          │       └─ database_query_facade.py
          ├─ [29 duplicate router registrations]
          └─ [inline route definitions: login, research, search, collect, etc.]

lifespan(startup):
  ├─ async_db.py (AsyncDatabase pool)
  ├─ initialize_application() [2nd call]
  └─ 7+ background monitors (asyncio.create_task)
       ├─ keyword_monitor → db, collectors, LiteLLM
       ├─ emerging_topics_monitor → db, LiteLLM
       ├─ rss_feed_monitor → db, RSSCollector
       ├─ geopolitical_hotspots_monitor → db, LiteLLM
       ├─ threat_intelligence_monitor → db, LiteLLM
       └─ [dynamic module monitors]
```

---

## Step 2: Blockers and Workflow-Breaking Issues

### B-1: Duplicate Route Registrations (HIGH)

**Evidence:** `app/core/routers.py:register_routers()` registers 50+ routers. Then `app/main.py:115-219` calls `app.include_router()` 29 more times after `create_app()` returns.

Duplicated routers include:

| Router | In `register_routers()` | In `main.py` |
|---|---|---|
| `dataset_router` | `routers.py:113` | `main.py:115` |
| `media_bias_routes.router` | `routers.py:116` | `main.py:118` |
| `auspex_router` | `routers.py:108` | `main.py:123` |
| `api_router` (prefix `/api`) | `routers.py:122` | `main.py:126` |
| `keyword_monitor_router` | `routers.py:125` | `main.py:129`, `main.py:210` (3x total) |
| `onboarding_router` | `routers.py:92` | `main.py:133` |
| `focus_group_router` | `routers.py:167` | `main.py:139` |
| `executive_briefing_router` | `routers.py:170` | `main.py:140` |
| `web_router` | `routers.py:129` | `main.py:208` |
| `topic_router` | `routers.py:89` | `main.py:209` |
| `vector_router` | `routers.py:98` | `main.py:215` |
| `saved_searches_router` | `routers.py:101` | `main.py:213` |

**Impact:** FastAPI registers all routes from each `include_router` call. Duplicate routes result in the **first** registered handler winning, but all duplicate routes show in OpenAPI docs and add overhead. The inline routes in `main.py` (lines 247-3700+) that define handlers directly on `app` are NOT duplicated by `register_routers` — they are unique.

**However:** The `POST /login` route **IS** duplicated: once in `main.py:301` (no `is_active` check) and once in `auth_routes.py:39` (has `is_active` check). Because `auth_routes.py` is registered first (via `register_routers`), the `auth_routes` version wins. The `main.py` version is dead code **but** could cause confusion during maintenance.

**Functional impact:** Low for correctness (first-registered wins), but maintenance and debugging are significantly harder.

### B-2: `verify_session` Returns Dict for `user` Key (MEDIUM)

**Evidence:** `app/security/session.py:61-67`:

```python
enhanced_session["user"] = {
    "username": user.get('username'),
    "email": user.get('email', ''),
    "role": user.get('role', 'user'),
    "is_active": user.get('is_active', True)
}
return enhanced_session
```

Then in `require_admin` (`session.py:197-198`):

```python
username = session.get("user")
# username is now a DICT, not a string
```

This is passed to `check_user_is_admin(username)` → `get_user_by_username(username)` which has a **workaround** at `database_query_facade.py:1370`:

```python
if isinstance(username, dict):
    username = username.get('username') or username.get('email')
```

**Impact:** Works today because of the workaround, but is fragile. Any new code calling `session.get("user")` expecting a string will break.

### B-3: `initialize_application()` Called Twice (LOW-MEDIUM)

**Evidence:**
- 1st call: `app/core/app_factory.py:312` — `initialize_application()` in `create_app()`
- 2nd call: `app/core/app_factory.py:62` — `initialize_application()` in `lifespan()`

**Impact:** `initialize_application()` in `app/startup.py` calls `load_environment()`, `ensure_model_env_vars()`, `verify_firecrawl_config()`, `initialize_firecrawl()`. All are idempotent (env vars overwrite, Firecrawl client re-created). Wasteful but not breaking.

### B-4: Background Tasks Never Cancelled on Shutdown (MEDIUM)

**Evidence:** `app/core/app_factory.py:209-241` — the shutdown section closes async DB pool and AutomatedIngestService but does **not** cancel any of the 7+ `asyncio.create_task()` tasks from startup (lines 81-201).

**Impact:** On graceful shutdown, background monitors continue running against a closed DB pool, producing error logs. On Uvicorn reload, orphaned tasks may duplicate.

### B-5: Missing Authentication on Critical Endpoints (HIGH)

**Evidence (from main.py inline routes, which are the first-registered versions in most cases):**

| Endpoint | Auth? | Risk |
|---|---|---|
| `GET /api/collect_articles` (`main.py:1345`) | **No** | Unauthenticated article collection using configured API keys |
| `POST /api/save_article` (`main.py:957`) | **No** | Anyone can write articles to DB |
| `GET /api/latest_articles` (`main.py:992`) | **No** | Data exfiltration |
| `GET /api/fetch_article_content` (`main.py:1212`) | **No** | SSRF — fetches arbitrary URLs via Firecrawl |
| `GET /fetch_article_content` (`main.py:1260`) | **No** | SSRF — same, different path |
| `POST /api/markdown_to_html` (`main.py:950`, `1750`) | **No** | XSS — raw HTML passthrough |
| `POST /api/save_report` (`main.py:943`) | **No** | Write arbitrary reports |
| `GET /api/debug_settings` (`main.py:1100`) | **No** | Exposes config |
| `GET /api/debug_articles` (`main.py:1109`) | **No** | Exposes article data |
| 8/9 auto-ingest endpoints (`auto_ingest.py:17-224`) | **No** | Config mutation, status exposure |

**Impact:** These endpoints are reachable without any session cookie. In the Docker deployment, CORS is `["*"]` in non-production, making exploitation trivial.

### B-6: `config.json` Must Exist Before Startup (MEDIUM)

**Evidence:** `app/config/settings.py:51` — `config = load_config()` runs at **module import time**. It calls `init_config()` which copies `config.json.sample` → `config.json` if missing. If neither exists, startup crashes.

The Docker entrypoint copies `config.docker.json` → `app/data/config.json` (Dockerfile:86), but `settings.py` reads from `app/config/config.json` (line 21).

**However**, `DATABASE_DIR` is defined as `os.path.join(os.path.dirname(os.path.dirname(...)), 'data')` which resolves to `app/data/`. And `config_path` in `init_config()` uses `os.path.dirname(os.path.abspath(__file__))` which resolves to `app/config/`. These are **different directories**.

**Impact:** If `app/config/config.json` is missing and `config.json.sample` is missing, startup crashes at import time. The Docker build places config in `app/data/config.json` which `Database.__init__` reads, but `settings.py` reads a different path.

### B-7: SQLite `sqlite_master` Queries in `AsyncDatabase` for PostgreSQL (MEDIUM)

**Evidence:** `app/services/async_db.py:301` — `get_topic_articles()` uses:

```python
check_query = "SELECT name FROM sqlite_master WHERE type='table' AND name='keyword_article_matches'"
```

This will fail on PostgreSQL since `sqlite_master` doesn't exist.

**Impact:** `get_topic_articles()` will throw an exception on PostgreSQL deployments.

### B-8: `health_routes.py` Creates New `Database()` Per Call (LOW)

**Evidence:** `app/routes/health_routes.py:32`:

```python
db_instance = Database()
```

Same at `health_routes.py:268`. Each call to `get_database_health()` or `get_autopolling_status()` creates a new `Database` instance with a new SQLAlchemy engine, rather than using the singleton `get_database_instance()`.

**Impact:** Connection pool leak on PostgreSQL; each `Database()` creates a new engine with `pool_size=20`.

### B-9: `vector_store_pgvector.py` Uses `logger` Before Definition (HIGH for startup)

**Evidence:** `app/vector_store_pgvector.py:35`:

```python
except ImportError:
    _async_db_available = False
    logger.warning("AsyncDatabase not available...")  # logger not yet defined!
```

`logger` is defined on line 37. If the `AsyncDatabase` import fails, this crashes at import time.

**Impact:** If `async_db` module has an import error, the vector store module crashes, which cascades to `vector_routes.py` import, which cascades to `register_routers()`, which crashes `create_app()`.

### B-10: `run.py` Imports From `main` (Not `app.main`) (MEDIUM)

**Evidence:** `app/run.py:94`:

```python
from main import app
```

This assumes the working directory is `app/`. The Docker entrypoint runs `cd /app && python app/run.py`, but `sys.path.append` at `run.py:5` adds the **parent** of `app/`, so `from main import app` would look for `/app/main.py` which is `/app/app/main.py` (since `main.py` is inside `app/`).

Actually, `run.py:94` uses `"main:app"` as a string for Uvicorn, not a direct import. And `configure_app()` at line 94 does `from main import app` — but `configure_app()` is never called in the `__main__` block. Uvicorn resolves `"main:app"` relative to CWD.

**Impact:** If CWD is not `app/`, Uvicorn won't find `main:app`. The entrypoint sets `cd /app` so Uvicorn looks for `/app/main.py` which doesn't exist (it's at `/app/app/main.py`). **However**, the Docker entrypoint runs `python app/run.py` from `/app`, and `run.py` adds parent to `sys.path` — so `"main:app"` resolves to `app/main.py` which is a valid module. This works but is fragile and relies on the path manipulation at `run.py:5`.

### B-11: Missing `conftest.py` — No Shared Test Fixtures (LOW)

**Evidence:** `Glob` search returned 0 `conftest.py` files. Tests use local fixtures with ad-hoc mocks.

**Impact:** Tests can't share DB fixtures, app client, or mock configurations. Each test file reinvents its own mocking strategy.

---

## Step 3: Minimal Executable Validation

### 3.1 Smoke Test Checklist (Manual)

These can be run against a local `docker-compose up` instance:

```bash
# 1. Start the stack
docker-compose up -d

# 2. Wait for healthy (uses /health endpoint)
until curl -sf http://localhost:10001/health; do sleep 2; done

# 3. Login smoke test (should return 302 redirect)
curl -v -X POST http://localhost:10001/login \
  -d "username=admin&password=admin123" \
  -c cookies.txt

# 4. Verify session (should return 200, not 307)
curl -v -b cookies.txt http://localhost:10001/

# 5. Health detailed endpoint
curl -s http://localhost:10001/health/detailed | python3 -m json.tool

# 6. Health readiness
curl -s http://localhost:10001/health/ready

# 7. Unauthenticated endpoint check (should work — currently no auth)
curl -s "http://localhost:10001/api/available_sources" | python3 -m json.tool

# 8. Search articles (requires session)
curl -s -b cookies.txt "http://localhost:10001/api/search_articles?page=1&per_page=5" \
  | python3 -m json.tool

# 9. API models (no auth required)
curl -s http://localhost:10001/api/ai_models | python3 -m json.tool

# 10. Logout
curl -v -b cookies.txt http://localhost:10001/logout
```

### 3.2 Proposed pytest Integration Tests

These tests use **FastAPI's `TestClient`** (synchronous, via `httpx`) and require **no external services** — they mock the database and external APIs. They should live in a new `tests/test_e2e_workflows.py` file with a shared `conftest.py`.

**Proposed `conftest.py`:**

```python
import pytest
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient


@pytest.fixture
def mock_db():
    """Mock Database singleton for all tests."""
    db = Mock()
    db.db_type = "postgresql"
    db.get_database_info.return_value = {"type": "postgresql", "name": "test"}
    db.facade = Mock()
    db.facade.get_user_by_username.return_value = {
        "username": "admin",
        "password": "$2b$12$...",  # bcrypt hash of "admin123"
        "role": "admin",
        "is_active": True,
        "email": "admin@test.com",
        "force_password_change": False,
        "completed_onboarding": True,
    }
    db.facade.get_topics_with_article_counts.return_value = {}
    db.facade.check_user_is_admin.return_value = True
    db.search_articles.return_value = ([], 0)
    db.get_user.return_value = db.facade.get_user_by_username.return_value
    return db


@pytest.fixture
def app_client(mock_db):
    """Create a TestClient with mocked dependencies."""
    with patch("app.database.get_database_instance", return_value=mock_db), \
         patch("app.database.Database", return_value=mock_db), \
         patch("app.services.async_db.initialize_async_db"), \
         patch("app.startup.initialize_application", return_value=True), \
         patch("app.security.oauth.setup_oauth_providers", return_value=[]):
        from app.main import app
        client = TestClient(app, raise_server_exceptions=False)
        yield client
```

**Proposed test cases (`tests/test_e2e_workflows.py`):**

```python
def test_health_endpoint_returns_200(app_client):
    """WF-8: Basic health check works."""
    resp = app_client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


def test_login_page_returns_200(app_client):
    """WF-1: Login page is accessible."""
    resp = app_client.get("/login")
    assert resp.status_code == 200


def test_unauthenticated_root_redirects_to_login(app_client):
    """WF-2: Protected routes redirect without session."""
    resp = app_client.get("/", follow_redirects=False)
    assert resp.status_code == 307
    assert "/login" in resp.headers.get("location", "")


def test_search_articles_requires_auth(app_client):
    """WF-5: Search requires session."""
    resp = app_client.get("/api/search_articles", follow_redirects=False)
    assert resp.status_code == 307


def test_collect_articles_no_auth_required(app_client):
    """B-5: Collect articles is unauthenticated (documents current behavior)."""
    resp = app_client.get(
        "/api/collect_articles",
        params={"source": "nonexistent", "query": "test", "topic": "test"},
    )
    # Should not be 307/401 — currently no auth
    assert resp.status_code != 307


def test_available_sources_returns_list(app_client):
    """Collector factory enumerates configured sources."""
    resp = app_client.get("/api/available_sources")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
```

### 3.3 Commands to Run Locally

```bash
# Install test dependencies (not in requirements.txt currently)
pip install pytest pytest-asyncio httpx

# Run existing tests (what CI runs)
pytest tests/ -v

# Run proposed smoke tests
pytest tests/test_e2e_workflows.py -v

# Run with coverage (not currently in CI)
pytest tests/ --cov=app --cov-report=term-missing -v
```

### 3.4 CI Gaps (from `.github/workflows/test-and-build.yml`)

| Gap | Evidence | Fix |
|---|---|---|
| `app/tests/` excluded from CI | `test-and-build.yml:68`: `pytest tests/ -v` (not `app/tests/`) | Add `pytest tests/ app/tests/ -v` |
| No `pytest-asyncio` in requirements.txt | CI installs it ad-hoc (`line 50`) | Add to `requirements.txt` |
| No `conftest.py` anywhere | `Glob` returned 0 results | Create `tests/conftest.py` with shared fixtures |
| `pytest` not in `requirements.txt` | Missing | Add as dev dependency |
| No type checking in CI | No `mypy` or `pyright` step | Add `mypy app/ --ignore-missing-imports` |

### 3.5 Docker-Compose Validation (Already in Repo)

The existing `docker-compose.yml` is well-structured for local validation:

```bash
# Full stack up (PostgreSQL + App)
docker-compose up --build

# Verify health after ~40s startup
curl http://localhost:10001/health
curl http://localhost:10001/health/ready
curl http://localhost:10001/health/detailed
```

No additional `docker-compose` changes needed — the existing file provides PostgreSQL with pgvector.

---

## Summary of Critical Blockers by Priority

| # | Severity | Blocker | Functional Impact |
|---|---|---|---|
| B-5 | **HIGH** | 10+ endpoints missing authentication | Security: unauthenticated SSRF, data write, config mutation |
| B-9 | **HIGH** | `vector_store_pgvector.py` `logger` before definition | Crash at import if `AsyncDatabase` import fails |
| B-1 | **MEDIUM** | 29 duplicate router registrations | First-registered wins; maintenance confusion |
| B-7 | **MEDIUM** | `sqlite_master` query in `AsyncDatabase` on PostgreSQL | `get_topic_articles()` crashes on PG |
| B-4 | **MEDIUM** | Background tasks never cancelled on shutdown | Orphaned tasks, error spam on shutdown |
| B-6 | **MEDIUM** | `config.json` path mismatch between settings.py and Docker | Potential startup crash if config not in expected location |
| B-2 | **MEDIUM** | `verify_session` returns dict for `user`, fragile contract | Works today via workaround; new code may break |
| B-8 | **LOW** | Health routes create new `Database()` per call | Connection pool leak on PG |
| B-3 | **LOW** | `initialize_application()` called twice | Wasteful but idempotent |
| B-11 | **LOW** | No `conftest.py` for shared test fixtures | Test isolation and DRY concerns |
