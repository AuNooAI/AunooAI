# React Dashboards - Quick Reference Guide

## File Locations

| Component | Location |
|-----------|----------|
| **Trend Convergence** | `/ui/src/App.tsx` |
| **Operations HQ** | `/ui/src/pages/OperationsHQ.tsx` |
| **Shared Nav** | `/ui/src/components/SharedNavigation.tsx` |
| **API Client** | `/ui/src/services/api.ts` |
| **State Hook** | `/ui/src/hooks/useTrendConvergence.ts` |
| **Build Config** | `/ui/vite.config.mts` |
| **Dependencies** | `/ui/package.json` |

## Dashboard URLs & Entry Points

### Trend Convergence (Anticipate)
- **Route**: `/trend-convergence`
- **HTML**: `index.html`
- **Main Component**: `App.tsx`
- **Build Entry**: `main` (vite config)
- **Asset Base**: `/static/trend-convergence/`

### Operations HQ  
- **Route**: `/operations-hq` or `/health/dashboard`
- **HTML**: `index-operations.html`
- **Main Component**: `pages/OperationsHQ.tsx`
- **Build Entry**: `operations` (vite config)
- **Asset Base**: `/static/` (shared with Trend Convergence)

## Key Commands

```bash
# Development
cd /home/orochford/tenants/multi.aunoo.ai/ui
npm install           # Install dependencies
npm run dev          # Start Vite dev server (http://localhost:3000)

# Production Build
npm run build        # Output to /ui/build/ directory

# Deployment (from backend)
# FastAPI serves /ui/build/index.html and /ui/build/index-operations.html
```

## Five Analysis Tabs (Trend Convergence)

| Tab | API Param | Component | Purpose |
|-----|-----------|-----------|---------|
| Consensus | `consensus` | ConsensusCategoryCard | Sentiment distribution, decision windows |
| Strategic Recommendations | `strategic` | ConvergenceCard | Near/mid/long-term trends |
| Impact Timeline | `timeline` | ImpactTimelineCard | Visual timeline, key insights |
| Market Signals | `signals` | Market data table | Risks, opportunities, signals |
| Future Horizons | `horizons` | FutureHorizons | Long-term outlook |

## API Endpoints Summary

### Trend Convergence
```
GET /api/trend-convergence/{topic}
  ?tab=consensus|strategic|timeline|signals|horizons
  &model=gpt-4o-mini
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

### Supporting APIs
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

## Component Hierarchy

### Trend Convergence
```
App.tsx (main)
├── SharedNavigation
├── Tab Navigation
├── Configuration Dialog
├── Analysis Tabs
│   ├── Consensus Tab
│   │   └── ConsensusCategoryCard (repeated)
│   ├── Strategic Tab
│   │   └── ConvergenceCard (repeated)
│   ├── Timeline Tab
│   │   └── ImpactTimelineCard (repeated)
│   ├── Market Signals Tab
│   │   └── Signals Table
│   └── Future Horizons Tab
│       └── FutureHorizons
├── OrganizationalProfileModal
└── OnboardingWizard
```

### Operations HQ
```
OperationsHQ.tsx
├── SharedNavigation
├── Header with Stats
├── System Health Status Card
├── World Clock Section
│   └── WorldClockConfig Modal
└── Metrics Grid
    ├── CPU Card
    ├── Memory Card
    ├── Disk Card
    └── File Descriptors Card
```

## localStorage Keys

```
trendConvergence_config              # Analysis configuration
trendConvergence_topic               # Last selected topic
trendConvergence_data_consensus      # Tab cache
trendConvergence_data_strategic      # Tab cache
trendConvergence_data_timeline       # Tab cache
trendConvergence_data_signals        # Tab cache
trendConvergence_data_horizons       # Tab cache
worldClockTimezones                  # Clock settings
```

## Styling & Design

- **Framework**: Tailwind CSS v3.4.18
- **Components**: Radix UI (40+ primitives)
- **Icons**: Lucide React
- **Primary Color**: Pink (#ec4899)
- **Layout**: Flex-based responsive grid
- **Font**: Inter (Google Fonts)

## Configuration Defaults

```javascript
{
  topic: '',
  timeframe_days: 365,
  model: 'gpt-4o',
  analysis_depth: 'standard',
  sample_size_mode: 'auto',
  consistency_mode: 'balanced',
  enable_caching: true,
  cache_duration_hours: 24,
}
```

## Data Refresh Rates

- **Trend Convergence**: Manual trigger (button) or auto on tab change
- **Operations HQ Health**: Every 30 seconds
- **Operations HQ Clocks**: Every 1 second

## UI Components Available

Located in `/ui/src/components/ui/`:

**Forms**: Button, Input, Select, Checkbox, Switch, Textarea, Form
**Layout**: Card, Sidebar, Tabs, Accordion, Drawer
**Dialogs**: Dialog, AlertDialog, Popover, Sheet
**Navigation**: Navigation Menu, Breadcrumb, Menubar, Dropdown Menu
**Data**: Pagination, Table (custom), Progress, Slider
**Utility**: Badge, Avatar, Separator, Skeleton, Tooltip, Alert

## Key npm Dependencies

```json
{
  "react": "18.3.1",
  "tailwindcss": "3.4.18",
  "vite": "6.3.5",
  "@vitejs/plugin-react-swc": "3.10.2",
  "@radix-ui/react-*": "^1.x",
  "recharts": "2.15.2",
  "react-hook-form": "7.55.0",
  "lucide-react": "0.487.0",
  "sonner": "2.0.3",
  "react-resizable-panels": "2.1.7"
}
```

## Data Type Examples

### Topic
```typescript
{
  name: "Cloud Repatriation",
  display_name: "Cloud Repatriation Trends",
  article_count: 342
}
```

### Organizational Profile
```typescript
{
  id: 1,
  name: "Tech Corp",
  industry: "Cloud Infrastructure",
  organization_type: "Enterprise",
  region: "North America",
  risk_tolerance: "medium",
  innovation_appetite: "high"
}
```

### AI Model
```typescript
{
  id: "gpt-4.1-mini",
  name: "GPT-4.1 Mini (openai)",
  context_limit: 1000000
}
```

## Removed Features

- Community article editing (dashboard is read-only)
- Podcast script generation
- Topic map visualization
- Model-specific API keys (consolidated to provider-wide)

## Navigation Quick Links

| Link | URL |
|------|-----|
| Home | `/` |
| Trend Convergence | `/trend-convergence` |
| News Feed | `/news-feed-v2` |
| Keyword Alerts | `/keyword-alerts` |
| Config | `/config` |
| Create Topic | `/create_topic` |
| Prompt Manager | `/promptmanager` |
| Vector Analysis | `/vector-analysis-improved` |
| Database Editor | `/database-editor` |
| Analytics | `/analytics` |
| Health Dashboard | `/health/dashboard` |

## Build Output Structure

```
/ui/build/
├── index.html                    # Trend Convergence
├── index-operations.html         # Operations HQ
├── assets/
│   ├── main-*.js                # Main app JS
│   ├── operations-*.js           # Operations HQ JS
│   └── *.css                     # Compiled styles
└── static/
    └── trend-convergence/        # Asset base path
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Blank page | Check browser console, verify API responding at `/api/` |
| Styling missing | Run `npm run build` and verify CSS files in build/assets/ |
| Tab data not showing | Check localStorage quota, try force refresh |
| Clock not updating | Check browser's Intl support, verify timezone strings |
| Config not saving | Clear localStorage, check browser permissions |

