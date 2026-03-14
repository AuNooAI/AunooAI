# Module Config Modal — Runtime Toggle for Analysis Modules

> **Status**: Implemented
> **Date**: 2026-02-06
> **Depends on**: [Analysis Module Packaging Spec](ANALYSIS_MODULE_PACKAGING_SPEC.md)

## Summary

Adds a settings gear button to the Explore tab bar that opens a modal for enabling/disabling analysis modules at runtime. Changes persist to a `module_config` database table and take effect immediately for tab visibility. Background route registration and tasks still require a service restart.

## How It Works

### Data flow

```
┌──────────────┐     GET /api/modules      ┌───────────────────┐
│  Frontend    │ ◄──────────────────────── │  module_routes.py  │
│  useModules  │                           │                    │
│  hook        │ PUT /api/modules/:id/toggle│                    │
│              │ ──────────────────────────►│  set_module_enabled│
└──────────────┘                           └────────┬───────────┘
                                                    │
                                           ┌────────▼───────────┐
                                           │   module_config    │
                                           │   (DB table)       │
                                           └────────────────────┘
```

### DB → env var fallback

The `module_config` table is the source of truth when it contains rows. When empty (fresh deploy or pre-migration), the system falls back to the `ENABLED_MODULES` env var. The first toggle from the UI seeds the table from the current env var state.

## Files Changed

| File | Change |
|------|--------|
| `alembic/versions/mc_001_add_module_config.py` | Migration creating `module_config` table |
| `app/core/modules.py` | Added DB read/write helpers; `get_enabled_module_ids()` now checks DB first |
| `app/routes/module_routes.py` | `GET /api/modules` returns all modules with `enabled` flag; new `PUT /api/modules/{id}/toggle` |
| `ui/src/components/newsfeed/ModuleConfigModal.tsx` | Dialog with Switch toggles per module |
| `ui/src/hooks/useModules.ts` | Added `toggleModule()`, `enabled` field on `ModuleInfo` |
| `ui/src/pages/NewsFeedPage.tsx` | Gear icon on tab bar, wired to modal |

## Database Schema

```sql
CREATE TABLE module_config (
    module_id   VARCHAR(100) PRIMARY KEY,
    enabled     BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at  TIMESTAMP DEFAULT NOW(),
    updated_by  VARCHAR(255)
);
```

Migration: `mc_001`, depends on `sf_002`.

## API

### GET /api/modules

Returns all registered modules with their current enabled state.

```json
{
  "modules": [
    {
      "id": "geopolitical_hotspots",
      "name": "GeoHotSpots",
      "description": "Geopolitical hotspot monitoring...",
      "tab_id": "geopolitical",
      "tab_label": "GeoHotSpots",
      "tab_icon": "Globe",
      "has_model": false,
      "model_available": null,
      "enabled": true
    }
  ]
}
```

### PUT /api/modules/{module_id}/toggle

```json
{ "enabled": false }
```

Returns the same shape as GET (full updated module list).

## What Updates Immediately vs. On Restart

| Aspect | Immediate | Requires restart |
|--------|-----------|-----------------|
| Tab visibility in UI | Yes | - |
| `/api/modules` response | Yes | - |
| Route registration | - | Yes |
| Background monitor tasks | - | Yes |

This is by design — routes and background tasks are registered once at startup in `app/core/routers.py` and `app/core/app_factory.py`. The modal includes an info banner explaining this to the user.
