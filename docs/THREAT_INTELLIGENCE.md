# Threat Intelligence Module

## Overview

The Threat Intelligence module adds cyber threat tracking to the Explore page. It monitors news articles for cybersecurity threats and provides:

- **Threat actor tracking** — APT groups, cybercrime orgs, hacktivists with country attribution
- **IOC management** — Indicators of Compromise (IPs, domains, hashes, URLs) extracted via `iocextract`
- **Campaign analysis** — Group related threats into named campaigns with timelines
- **MITRE ATT&CK mapping** — Techniques and tactics classification
- **Severity scoring** — Critical/High/Medium/Low threat categorization
- **Threat map** — Geographic visualization of threat origins and targets
- **Scheduled monitoring** — Background task auto-processes curated articles for threats

## Architecture

### Module Registration

Registered in `app/core/modules.py` as `threat_intel`. This auto-wires:
- Route registration at `/api/threat-intelligence/` (via `app/core/routers.py`)
- Background task scheduling with 55s startup delay (via `app/core/app_factory.py`)
- Frontend tab toggle via the gear icon on the Explore tab bar

### Backend

| File | Lines | Purpose |
|---|---|---|
| `app/services/threat_intelligence_service.py` | ~2,700 | Core service — threat extraction, actor management, campaign logic |
| `app/routes/threat_intelligence_routes.py` | ~1,500 | 36 API endpoints under `/api/threat-intelligence/` |
| `app/tasks/threat_intelligence_monitor.py` | ~500 | Background task — scheduled article processing |
| `alembic/versions/ti_001_add_threat_intelligence_tables.py` | ~265 | Migration creating 8 database tables |

### Frontend

| File | Purpose |
|---|---|
| `ui/src/services/threatIntelligenceApi.ts` | API client with TypeScript types for all endpoints |
| `ui/src/hooks/useThreatIntelligence.ts` | React hook for state management |
| `ui/src/components/newsfeed/ThreatIntelligenceTab.tsx` | Main tab container with sub-tab navigation |
| `ui/src/components/newsfeed/ThreatOverviewTab.tsx` | Dashboard overview with stats cards |
| `ui/src/components/newsfeed/ThreatActorsTab.tsx` | Threat actor profiles and filtering |
| `ui/src/components/newsfeed/ThreatArticlesTab.tsx` | Processed articles with threat annotations |
| `ui/src/components/newsfeed/ThreatInsightsTab.tsx` | AI-generated threat intelligence insights |
| `ui/src/components/newsfeed/ThreatCategoriesTab.tsx` | Threat categories breakdown |
| `ui/src/components/newsfeed/ThreatAnalysisTab.tsx` | MITRE ATT&CK and campaign analysis |
| `ui/src/components/newsfeed/ThreatTimelineTab.tsx` | Temporal trends and campaign timeline |
| `ui/src/components/newsfeed/ThreatMapTab.tsx` | Map view wrapper |
| `ui/src/components/newsfeed/map/ThreatMap.tsx` | Leaflet map with threat origin visualization |
| `ui/src/components/newsfeed/map/ThreatMapLegend.tsx` | Map legend component |
| `ui/src/components/newsfeed/ThreatArticleDetailPanel.tsx` | Article detail with threat metadata |
| `ui/src/components/newsfeed/ThreatImportModal.tsx` | Bulk article import for threat processing |
| `ui/src/components/newsfeed/ThreatScheduleModal.tsx` | Configure scheduled monitoring |
| `ui/src/components/newsfeed/CampaignDetailModal.tsx` | Campaign detail overlay |
| `ui/src/components/newsfeed/CampaignTimelineChart.tsx` | Gantt-style campaign timeline chart |
| `ui/src/components/newsfeed/ThreatIntelligenceTabs.tsx` | Tab navigation definitions |

### Database Tables (8)

| Table | Purpose |
|---|---|
| `threat_intel_actors` | Threat actor profiles (APT groups, criminal orgs, etc.) |
| `threat_intel_threats` | Individual threat records extracted from articles |
| `threat_intel_iocs` | Indicators of Compromise (IPs, domains, hashes, URLs) |
| `threat_intel_campaigns` | Named campaigns grouping related threats |
| `threat_articles` | Articles processed for threat intelligence |
| `threat_daily_stats` | Aggregated daily threat statistics |
| `threat_intel_narratives` | AI-generated threat narratives and summaries |
| `threat_intel_schedules` | Scheduled monitoring configurations |

Migration: `ti_001` (chains off `bw_005` in the Alembic history).

## API Endpoints

36 endpoints under `/api/threat-intelligence/`, including:

- `GET /overview` — Dashboard stats summary
- `GET /threats` — Paginated threat listing with filters
- `GET /actors` — Threat actor profiles
- `GET /actor/{id}/threats` — Threats attributed to a specific actor
- `GET /campaigns` — Campaign listing with timeline data
- `GET /iocs` — Indicators of Compromise
- `GET /categories` — Threat category breakdown
- `GET /timeline` — Temporal trend data
- `GET /map-data` — Geographic threat data for map visualization
- `POST /process` — Trigger threat extraction on articles
- `POST /import` — Bulk import articles for processing
- `GET /schedules` / `POST /schedules` — Manage scheduled monitoring

## Dependencies

- `iocextract>=1.16.1` — IOC extraction from article text (added to `requirements.txt`)

## Graceful Degradation

Two optional imports in the background monitor are wrapped in try/except:

- `app.utils.ner_extractor` — NER extraction; skipped with warning if unavailable
- `scripts.calculate_threat_trends` — Trend calculation; skipped with warning if unavailable

Both are non-critical. Core threat extraction and storage works without them.

## Toggling the Module

The module can be enabled/disabled at runtime:
- **UI**: Gear icon on the Explore tab bar > toggle "Threat Intelligence"
- **Env var**: `ENABLED_MODULES=threat_intel,...` (defaults to `*` = all enabled)
- **API**: `PUT /api/modules/{module_id}` with `{"enabled": true/false}`

When disabled, the tab disappears from the Explore page and the background monitor does not run. The routes remain registered but return empty results.
