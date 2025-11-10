# React Dashboards - Documentation Index

This directory contains comprehensive documentation of the React dashboards in the Aunoo AI application.

## Documentation Files

### 1. REACT_DASHBOARDS.md
**Comprehensive Technical Documentation** (718 lines, 22 KB)

Complete guide covering:
- Executive summary and architecture
- Full directory structure
- Trend Convergence Dashboard (Anticipate feature) - detailed features
- Operations HQ Dashboard - system monitoring
- Shared components and navigation
- Build configuration (Vite)
- API client layer
- State management
- Backend integration
- Browser storage schema
- Removed features from community
- Deployment details
- Design system specifications
- Performance considerations

**Best for:** Understanding complete architecture, deep dives into specific features, deployment planning

### 2. REACT_DASHBOARDS_QUICK_REFERENCE.md
**Quick Lookup Guide** (280 lines, 7.4 KB)

Quick reference tables for:
- File locations
- Dashboard URLs and entry points
- Common commands (dev/build)
- Five analysis tabs at a glance
- API endpoints summary
- Component hierarchy
- localStorage keys
- Styling framework details
- Configuration defaults
- Data refresh rates
- Available UI components
- Key dependencies
- Data type examples
- Removed features
- Navigation quick links
- Build output structure
- Troubleshooting

**Best for:** Quick lookups, rapid navigation, copy-paste commands, API endpoint reference

## Dashboard Overview

### Trend Convergence (Anticipate Feature)
Strategic analysis platform with AI-powered trend analysis

**Location:** `/ui/src/App.tsx`
**Route:** `/trend-convergence`
**Entry Points:** 
- HTML: `index.html`
- Component: `App.tsx`

**Five Analysis Tabs:**
1. **Consensus Analysis** - Sentiment distribution and decision windows
2. **Strategic Recommendations** - Near/mid/long-term trends (default tab)
3. **Impact Timeline** - Visual timelines and key insights
4. **Market Signals** - Risks, opportunities, future signals
5. **Future Horizons** - Long-term strategic outlook

**Key Features:**
- Configuration system (topic, timeframe, model, sample size, consistency)
- Organizational profile management
- Onboarding wizard
- Data export (PDF, images, raw JSON)
- Real-time AI-powered analysis
- Caching with 24-hour default TTL

### Operations HQ
System health monitoring and operational visibility dashboard

**Location:** `/ui/src/pages/OperationsHQ.tsx`
**Route:** `/operations-hq` or `/health/dashboard`
**Entry Points:**
- HTML: `index-operations.html`
- Component: `pages/OperationsHQ.tsx`

**Key Features:**
- System health status (healthy/degraded/critical)
- World clock with timezone configuration (8 defaults)
- Dashboard statistics (articles, keywords, topics)
- Real-time system metrics:
  - CPU (process, system, core count, load average)
  - Memory (process RSS, system usage with progress bars)
  - Disk (usage, free space with progress bars)
  - File descriptors (open, available, connections)
- 30-second health refresh, 1-second clock update

## Key File Locations

### Core Components
```
/ui/src/
├── App.tsx                              Trend Convergence main
├── operations-main.tsx                  Operations HQ entry
├── pages/OperationsHQ.tsx               Operations HQ component
├── components/SharedNavigation.tsx      Sidebar navigation
├── components/ConsensusCategoryCard.tsx Consensus display
├── components/ConvergenceCard.tsx       Convergence cards
├── components/ImpactTimelineCard.tsx    Timeline visualization
├── components/FutureHorizons.tsx        Future analysis
├── components/OrganizationalProfileModal.tsx Profile management
├── components/WorldClockConfig.tsx      Clock settings
├── components/onboarding/OnboardingWizard.tsx Setup wizard
├── services/api.ts                      FastAPI client
├── hooks/useTrendConvergence.ts         State management
└── components/ui/                       40+ Radix UI primitives
```

### Configuration
```
/ui/
├── vite.config.mts                      Build configuration
├── package.json                         Dependencies
├── index.html                           Trend Convergence entry
├── index-operations.html                Operations HQ entry
└── build/                               Production output
```

### Backend Routes
```
/app/routes/
├── trend_convergence_routes.py          Analysis endpoint
├── dashboard_routes.py                  Stats endpoint
├── health_routes.py                     Health monitoring
└── web_routes.py                        HTML page serving
```

## Technology Stack

### Frontend
- **Framework:** React 18.3.1
- **Language:** TypeScript
- **Build Tool:** Vite 6.3.5
- **Styling:** Tailwind CSS 3.4.18
- **Components:** Radix UI (40+ primitives)
- **Forms:** React Hook Form
- **Icons:** Lucide React
- **Data Viz:** Recharts
- **Layout:** React Resizable Panels

### Backend
- **Framework:** FastAPI
- **Database:** PostgreSQL with pgvector
- **Authentication:** Session-based cookies
- **AI Integration:** LiteLLM (OpenAI, Anthropic, Google)

## API Endpoints

### Trend Convergence
```
GET /api/trend-convergence/{topic}
  ?tab=consensus|strategic|timeline|signals|horizons
  &model=gpt-4o
  &timeframe_days=365
  &sample_size_mode=auto
  &consistency_mode=balanced
  &enable_caching=true
  &cache_duration_hours=24
  &profile_id=123
```

### Operations HQ
```
GET /api/dashboard/stats
GET /api/health
```

### Supporting
```
GET /api/topics
GET /api/available_models
GET /api/organizational-profiles
POST /api/organizational-profiles
PUT /api/organizational-profiles/{id}
DELETE /api/organizational-profiles/{id}
GET /api/onboarding/check-keys
POST /api/onboarding/validate-api-key
POST /api/onboarding/suggest-topic-attributes
POST /api/onboarding/save-topic
POST /api/onboarding/complete
```

## Build & Deployment

### Development
```bash
cd /home/orochford/tenants/multi.aunoo.ai/ui
npm install          # Install dependencies
npm run dev          # Start dev server on port 3000
```

### Production
```bash
cd /home/orochford/tenants/multi.aunoo.ai/ui
npm run build        # Build to /build/
```

### Serving
- **Vite Base:** `/static/trend-convergence/`
- **Output:** `/ui/build/index.html`, `/ui/build/index-operations.html`
- **Server:** FastAPI backend serves from `/trend-convergence` and `/health/dashboard`
- **Proxy:** NGINX reverse proxy configured

## Data Caching

### localStorage Keys
```
trendConvergence_config              Configuration
trendConvergence_topic               Last topic
trendConvergence_data_consensus      Tab cache
trendConvergence_data_strategic      Tab cache
trendConvergence_data_timeline       Tab cache
trendConvergence_data_signals        Tab cache
trendConvergence_data_horizons       Tab cache
worldClockTimezones                  Clock settings
```

### Cache Strategy
- Per-tab independent caching
- 24-hour default TTL (configurable)
- Force refresh available via UI
- Backwards compatible with legacy key

## Features Removed from Community

Based on git history:

1. **Community Article Editing** - Dashboard is now read-only for community
2. **Podcast Features** - Script generation, FFmpeg, diagram UI removed
3. **Topic Map Visualization** - Relationship mapping removed
4. **Model-Specific API Keys** - Consolidated to provider-wide
5. **Bugfixes Documentation** - Legacy documentation removed

## Navigation Structure

### Main Routes
- `/` - Home
- `/trend-convergence` - Trend Convergence Dashboard
- `/health/dashboard` - Operations HQ
- `/news-feed-v2` - News Feed
- `/keyword-alerts` - Keyword Alerts

### Configuration Routes
- `/config` - Configuration
- `/create_topic` - Topic Creator
- `/trend-convergence?onboarding=true` - Onboarding
- `/promptmanager` - Prompt Manager
- `/vector-analysis-improved` - Vector Analysis
- `/database-editor` - Database Editor
- `/analytics` - Analytics

## Design System

- **Primary Color:** Pink (#ec4899)
- **Font:** Inter (Google Fonts)
- **Grid:** 1-4 columns responsive
- **Sidebar Width:** 256px fixed
- **Status Colors:** Green (healthy), Yellow (degraded), Red (critical)
- **Card Style:** Rounded corners, shadows, hover transitions

## Support & Troubleshooting

See REACT_DASHBOARDS_QUICK_REFERENCE.md for:
- Troubleshooting table
- Common issues and solutions
- Configuration tips
- Development commands

## Document Statistics

| File | Lines | Size | Purpose |
|------|-------|------|---------|
| REACT_DASHBOARDS.md | 718 | 22 KB | Complete technical reference |
| REACT_DASHBOARDS_QUICK_REFERENCE.md | 280 | 7.4 KB | Quick lookup tables |
| **Total** | **998** | **29.4 KB** | Complete documentation |

---

**Last Updated:** November 10, 2025

For detailed information, refer to the specific documentation files:
- Start with REACT_DASHBOARDS_QUICK_REFERENCE.md for quick lookups
- Consult REACT_DASHBOARDS.md for comprehensive architecture and details
