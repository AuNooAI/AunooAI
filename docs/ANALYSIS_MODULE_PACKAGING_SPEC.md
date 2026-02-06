# Analysis Module Packaging System - Specification

> **Status**: Draft
> **Date**: 2026-02-06
> **Scope**: Backend module registry, conditional routing/tasks, frontend dynamic tabs

## Goal

Package features like ScienceWatch and Policy Tracker as self-contained **analysis modules** that tenants can enable/disable via a single env var. When enabled: routes registered, migrations run, background monitor started, frontend tab appears, SLM loaded. When disabled: none of that happens.

## Approach: Lightweight Module Registry

A single Python registry file (`app/core/modules.py`) defines all available modules as dataclasses. An `ENABLED_MODULES` env var controls which are active. The app factory and router registration loop over enabled modules instead of hardcoding imports. The frontend queries `/api/modules` to know which tabs to render.

**Backwards compatible**: `ENABLED_MODULES` defaults to `*` (all enabled), so existing deployments need zero changes.

---

## Step 1: Create Module Registry

**New file**: `app/core/modules.py`

```python
@dataclass
class AnalysisModule:
    id: str                    # "science_funding"
    name: str                  # "ScienceWatch"
    description: str
    route_module: str          # "app.routes.science_funding_routes"
    route_attr: str = "router"
    task_module: str | None    # "app.tasks.science_funding_monitor"
    task_function: str | None  # "run_science_funding_monitor"
    task_delay: int = 45       # startup delay seconds
    extra_tasks: list[dict]    # additional background tasks
    model_path: str | None     # "models/science_funding_classifier/final"
    migration_prefix: str | None  # "sf_"
    frontend_tab_id: str | None   # "science"
    frontend_tab_label: str | None # "ScienceWatch"
    frontend_tab_icon: str | None  # "Microscope"
```

Register three modules:
- `policy_tracker` (US Crisis Tracker) - delay 40s
- `geopolitical_hotspots` (GeoHotSpots) - delay 30s, extra task: `run_hotspot_trend_updates` at 35s
- `science_funding` (ScienceWatch) - delay 45s, has SLM model

Functions:
- `get_enabled_module_ids()` - reads `ENABLED_MODULES` env var (default `*`)
- `get_enabled_modules()` - returns list of enabled `AnalysisModule` objects
- `is_module_enabled(id)` - check a single module

---

## Step 2: Module-Aware Router Registration

**Modify**: `app/core/routers.py`

Remove the 3 static imports + registrations (lines 55-57, 186-192):
```python
# REMOVE these:
from app.routes.policy_tracker_routes import router as policy_tracker_router
from app.routes.geopolitical_hotspots_routes import router as geopolitical_hotspots_router
from app.routes.science_funding_routes import router as science_funding_router
...
app.include_router(policy_tracker_router)
app.include_router(geopolitical_hotspots_router)
app.include_router(science_funding_router)
```

Replace with a dynamic loop at the end of `register_routers()`:
```python
import importlib
from app.core.modules import get_enabled_modules

for module in get_enabled_modules():
    try:
        mod = importlib.import_module(module.route_module)
        router = getattr(mod, module.route_attr)
        app.include_router(router)
        logger.info(f"Registered module: {module.name}")
    except Exception as e:
        logger.error(f"Failed to register module '{module.id}': {e}")
```

All other ~38 core routers remain unconditional.

---

## Step 3: Module-Aware Background Tasks

**Modify**: `app/core/app_factory.py`

Remove the 4 hardcoded monitor blocks (lines 144-202):
- `delayed_geopolitical_hotspots_monitor_start` (30s)
- `delayed_hotspot_trend_update_start` (35s)
- `delayed_policy_tracker_monitor_start` (40s)
- `delayed_science_funding_monitor_start` (45s)

Replace with a helper + loop:
```python
import importlib
from app.core.modules import get_enabled_modules

def _schedule_module_task(task_module, task_function, delay, label):
    async def delayed_start():
        await asyncio.sleep(delay)
        try:
            mod = importlib.import_module(task_module)
            func = getattr(mod, task_function)
            logger.info(f"Starting {label} background task...")
            asyncio.create_task(func())
        except Exception as e:
            logger.error(f"Failed to start {label}: {e}")
    asyncio.create_task(delayed_start())

for module in get_enabled_modules():
    if module.task_module and module.task_function:
        _schedule_module_task(module.task_module, module.task_function,
                             module.task_delay, module.name)
        for extra in module.extra_tasks:
            _schedule_module_task(extra["module"], extra["function"],
                                 extra["delay"], f"{module.name} extra")
```

The 5 core monitors (keyword, emerging_topics, observer_agent, newsfeed_dashboard, rss_feed) remain hardcoded — they are not optional analysis modules.

---

## Step 4: Modules API Endpoint

**New file**: `app/routes/module_routes.py`

```python
@router.get("/api/modules")
async def get_modules(session=Depends(verify_session)):
    return {"modules": [
        {"id": m.id, "name": m.name, "tab_id": m.frontend_tab_id,
         "tab_label": m.frontend_tab_label, "tab_icon": m.frontend_tab_icon,
         "has_model": m.model_path is not None,
         "model_available": os.path.isdir(m.model_path) if m.model_path else None}
        for m in get_enabled_modules()
    ]}
```

Register this route in `routers.py` (core, always-on).

---

## Step 5: Frontend Dynamic Tabs

**New file**: `ui/src/hooks/useModules.ts`
- Fetches `/api/modules` on mount
- Returns `{ modules, isEnabled(tabId) }`
- Fallback: if API fails, show all tabs (backwards compat)

**Modify**: `ui/src/pages/NewsFeedPage.tsx`

1. Replace static imports with `React.lazy()`:
```tsx
const PolicyTrackerTab = React.lazy(() =>
  import('../components/newsfeed/PolicyTrackerTab').then(m => ({ default: m.PolicyTrackerTab })));
const GeopoliticalHotspotsTab = React.lazy(() =>
  import('../components/newsfeed/GeopoliticalHotspotsTab').then(m => ({ default: m.GeopoliticalHotspotsTab })));
const ScienceFundingTab = React.lazy(() =>
  import('../components/newsfeed/ScienceFundingTab').then(m => ({ default: m.ScienceFundingTab })));
```

2. Use `useModules()` hook to dynamically render tab buttons and content
3. Wrap tab content in `<Suspense>` for lazy loading
4. Update the breadcrumb subtitle ternary to use modules array

Benefits: disabled modules add zero bundle size (Vite code-splits lazy imports automatically).

---

## Step 6: Environment Configuration

Add to `.env` on each tenant:
```bash
# Analysis modules: comma-separated IDs, '*' for all, 'none' for none
# Available: policy_tracker, geopolitical_hotspots, science_funding
ENABLED_MODULES=*
```

---

## Enable/Disable Flow

**Enable a module:**
1. Add module ID to `ENABLED_MODULES` in `.env`
2. Run `alembic upgrade head` (if first time — tables created, sit empty when disabled)
3. Copy SLM model if applicable (`rsync` the `models/` dir)
4. `sudo systemctl restart {tenant}.service`
5. Frontend auto-adjusts via `/api/modules`

**Disable a module:**
1. Remove module ID from `ENABLED_MODULES`
2. Restart service
3. Tables + data remain (harmless, re-enable later)

---

## Migrations: No Changes Needed

Keep current approach: all migrations always run via `alembic upgrade head`. Empty tables cost nothing. This avoids complex branch-based migration logic. The `sf_`, `pt_`, `gh_` prefixes already organize them by module.

---

## Files Summary

| # | File | Action |
|---|------|--------|
| 1 | `app/core/modules.py` | **Create** — module registry with 3 modules |
| 2 | `app/core/routers.py` | **Edit** — remove 3 static module imports, add dynamic loop |
| 3 | `app/core/app_factory.py` | **Edit** — replace 4 hardcoded monitor blocks with loop |
| 4 | `app/routes/module_routes.py` | **Create** — `/api/modules` endpoint |
| 5 | `ui/src/hooks/useModules.ts` | **Create** — frontend modules hook |
| 6 | `ui/src/pages/NewsFeedPage.tsx` | **Edit** — lazy imports + dynamic tab rendering |
| 7 | `.env` (all tenants) | **Edit** — add `ENABLED_MODULES=*` |

---

## Verification

1. **Default state**: Set `ENABLED_MODULES=*` (or omit). All 3 tabs appear, all monitors start. Identical to current behavior.
2. **Disable one**: Set `ENABLED_MODULES=policy_tracker,geopolitical_hotspots`. Restart. ScienceWatch tab disappears, `/api/science-funding/*` returns 404, science monitor doesn't start.
3. **Disable all**: Set `ENABLED_MODULES=none`. All 3 tracker tabs gone. Core features (feed, agents, emerging, briefing desk) unaffected.
4. **Re-enable**: Add module back, restart. Tab reappears, data intact.
5. **Frontend fallback**: If `/api/modules` fails (e.g., older backend), all tabs show (backwards compat).

---

## Module Anatomy (Reference: ScienceWatch)

A complete analysis module consists of:

| Layer | Files | Description |
|-------|-------|-------------|
| **Routes** | `app/routes/science_funding_routes.py` | API endpoints (prefix `/api/science-funding`) |
| **Services** | `app/services/science_funding_classifier_service.py` | SLM classifier (singleton, DeBERTa) |
| **Tasks** | `app/tasks/science_funding_monitor.py` | Background monitor (checks schedules every 60s) |
| **Migrations** | `alembic/versions/sf_001_*.py`, `sf_002_*.py` | 5 tables + indexes |
| **SLM Model** | `models/science_funding_classifier/final/` | 532MB DeBERTa model |
| **Training** | `scripts/train_science_funding_classifier.py` | Distills LLM classifications into SLM |
| **Export** | `scripts/export_science_funding_training_data.py` | Exports training data from DB |
| **Frontend** | `ui/src/components/newsfeed/Science*.tsx` (13 files) | Tab + sub-tabs + modals |
| **Hook** | `ui/src/hooks/useScienceFunding.ts` | State management + API calls |
| **API Service** | `ui/src/services/scienceFundingApi.ts` | TypeScript API client (40+ functions) |

### Creating a New Module

1. Create route file following the pattern in `science_funding_routes.py`
2. Create Alembic migration(s) with a unique prefix (e.g., `br_` for Branch IntelBoard)
3. Optionally create a background task monitor
4. Optionally train an SLM classifier
5. Create frontend tab component, hook, and API service
6. Add `_register(AnalysisModule(...))` call to `app/core/modules.py`
7. Add module ID to `ENABLED_MODULES` in tenant `.env`

## Estimated Implementation Time: ~1.5 hours (AI)
