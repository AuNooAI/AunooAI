# React Dashboards Documentation - Aunoo AI

## Executive Summary

This codebase contains multiple React dashboards built with TypeScript and modern web technologies. The main dashboards are:

1. **Trend Convergence Dashboard** (Anticipate feature) - Strategic analysis platform
2. **Operations HQ** - System health monitoring and world clock

Both dashboards use Vite as the build tool, React 18, TypeScript, Tailwind CSS, and Radix UI components.

---

## Frontend Directory Structure

### Base Location
```
/home/orochford/tenants/multi.aunoo.ai/ui/
```

### Key Directories
```
ui/
├── src/
│   ├── App.tsx                          # Trend Convergence Dashboard (main)
│   ├── operations-main.tsx              # Operations HQ entry point
│   ├── pages/
│   │   └── OperationsHQ.tsx            # Operations HQ component
│   ├── components/                      # Shared React components
│   │   ├── SharedNavigation.tsx         # Navigation sidebar
│   │   ├── TabNavigation.tsx            # Tab switching
│   │   ├── ConsensusCategoryCard.tsx    # Consensus analysis cards
│   │   ├── ConvergenceCard.tsx          # Convergence trend cards
│   │   ├── ImpactTimelineCard.tsx       # Timeline visualization
│   │   ├── FutureHorizons.tsx           # Future prediction component
│   │   ├── OrganizationalProfileModal.tsx  # Profile management
│   │   ├── WorldClockConfig.tsx         # World clock settings
│   │   ├── onboarding/                  # Onboarding wizard
│   │   │   └── OnboardingWizard.tsx
│   │   └── ui/                          # Radix UI components (40+ primitives)
│   ├── hooks/
│   │   └── useTrendConvergence.ts       # Main state management hook
│   ├── services/
│   │   └── api.ts                       # FastAPI client layer
│   ├── utils/
│   │   └── contextCalculation.ts        # Context window calculations
│   ├── main.tsx                         # Trend Convergence entry point
│   ├── index.css                        # Tailwind styles
│   └── theme.ts                         # Design tokens
├── vite.config.mts                      # Build configuration
├── package.json                         # Dependencies
├── index.html                           # Trend Convergence HTML entry
├── index-operations.html                # Operations HQ HTML entry
└── build/                               # Production build output
    ├── index.html
    ├── index-operations.html
    └── assets/
```

---

## Dashboard 1: Trend Convergence (Anticipate)

### Purpose
Strategic trend analysis and decision-making platform that uses AI to analyze convergence patterns, market signals, and strategic recommendations.

### Entry Point
- **HTML**: `/home/orochford/tenants/multi.aunoo.ai/ui/index.html`
- **Component**: `/home/orochford/tenants/multi.aunoo.ai/ui/src/App.tsx`
- **Route**: `/trend-convergence`
- **Base URL**: `/static/trend-convergence/`

### Main Features

#### 1. Five Analysis Tabs
The dashboard provides five distinct analysis perspectives:

**a) Consensus Analysis Tab**
- Displays consensus categories from Auspex service
- Shows sentiment distribution (positive/neutral/critical)
- Includes timeline consensus and confidence levels
- Shows optimistic/pessimistic outliers
- Displays key decision windows
- Renders strategic implications

**b) Strategic Recommendations Tab** (Default)
- Near-term, mid-term, and long-term recommendations
- Rationale and description for each trend
- Executive decision framework with principles

**c) Impact Timeline Tab**
- Visual timeline cards for trend impact windows
- Key insights from evidence synthesis
- Impact categorization and significance

**d) Market Signals Tab**
- Future signals with confidence levels
- Risk cards with severity and mitigation strategies
- Opportunity cards with potential value
- Key quotes from analyzed articles

**e) Future Horizons Tab**
- Long-term strategic outlook
- Horizon analysis and emerging patterns
- Cross-cutting theme analysis

#### 2. Configuration System
Located in `/src/App.tsx` lines 183-290:
- Topic selection from available topics
- Analysis timeframe (30/90/180/365 days or all time)
- AI model selection with context limits
- Sample size mode (auto, focused, balanced, comprehensive, custom)
- Consistency mode (deterministic, low_variance, balanced, creative)
- Caching options (duration in hours)
- Organizational profile selection

#### 3. Organizational Profile Management
Modal component: `OrganizationalProfileModal.tsx`
- Create/edit organizational context
- Industry, region, organization type
- Risk tolerance and innovation appetite
- Decision-making style preferences
- Stakeholder focus and competitive landscape
- Custom context for personalized analysis

#### 4. Onboarding Wizard
Component: `components/onboarding/OnboardingWizard.tsx`
- Auto-triggered with `?onboarding=true` URL parameter
- API key validation for multiple providers
- Topic creation with AI-powered suggestions
- Category, sentiment, and signal suggestions
- Keyword auto-generation

#### 5. Data Export Features
Toolbar buttons (lines 400-430 in App.tsx):
- **Columns**: Customize displayed columns
- **Image**: Export visualization as image
- **PDF**: Generate PDF report
- **Raw**: View raw JSON analysis data (tab-specific)

### Tab to Backend API Mapping

| Tab | Backend Route | API Endpoint |
|-----|---------------|--------------|
| consensus | consensus | `/api/trend-convergence/{topic}?tab=consensus` |
| strategic-recommendations | strategic | `/api/trend-convergence/{topic}?tab=strategic` |
| impact-timeline | timeline | `/api/trend-convergence/{topic}?tab=timeline` |
| market-signals | signals | `/api/market-signals/analysis` |
| future-horizons | horizons | `/api/trend-convergence/{topic}?tab=horizons` |

### Data Caching Strategy
- **Per-tab localStorage keys**: `trendConvergence_data_{tab}`
- **Legacy key**: `trendConvergence_data` (backwards compatibility)
- **Config storage**: `trendConvergence_config`
- **Default cache duration**: 24 hours

### Key Type Definitions (from `api.ts`)

```typescript
// Main analysis data structure
interface TrendConvergenceData {
  topic?: string;
  categories?: AuspexConsensusCategory[];      // Consensus tab data
  convergences?: Convergence[];                // Legacy convergence data
  key_insights?: KeyInsight[];
  strategic_recommendations?: StrategicRecommendations;
  executive_decision_framework?: ExecutiveDecisionFramework;
  next_steps?: string[];
  model_used?: string;
  analysis_depth?: string;
  articles_analyzed?: number;
  timestamp?: string;
}

// Auspex Consensus Category (Consensus tab structure)
interface AuspexConsensusCategory {
  category_name: string;
  category_description: string;
  articles_analyzed: number;
  '1_consensus_type': AuspexConsensusType;
  '2_timeline_consensus': AuspexTimelineConsensus;
  '3_confidence_level': AuspexConfidenceLevel;
  '4_optimistic_outliers': AuspexOutlier[];
  '5_pessimistic_outliers': AuspexOutlier[];
  '6_key_articles': AuspexKeyArticle[];
  '7_strategic_implications': string;
  '8_key_decision_windows': AuspexDecisionWindow[];
  '9_timeframe_analysis': AuspexTimeframeAnalysis;
}
```

---

## Dashboard 2: Operations HQ

### Purpose
System monitoring and operational visibility dashboard showing system health metrics, world time zones, and quick navigation to key features.

### Entry Point
- **HTML**: `/home/orochford/tenants/multi.aunoo.ai/ui/index-operations.html`
- **Component**: `/home/orochford/tenants/multi.aunoo.ai/ui/src/pages/OperationsHQ.tsx`
- **Route**: `/operations-hq` (or root `/` depending on deployment)

### Main Features

#### 1. System Health Status
Displays overall system status with color-coded indicators:
- **Status Colors**: Green (healthy), Yellow (degraded), Red (critical)
- **Uptime Display**: Days, hours, minutes
- **Warning Section**: System-specific warnings if any

#### 2. World Clock
Interactive world clock configuration (lines 240-268):
- Default cities: San Francisco, New York, London, Berlin, Moscow, Dubai, Beijing, Tokyo
- Customizable timezone selection via `WorldClockConfig` modal
- Real-time updates every second using `Intl.DateTimeFormat`
- Persistent settings stored in localStorage
- Visual card display for each timezone

#### 3. Statistics Dashboard
Four stat cards (lines 271-315):
- **Total Articles**: Links to `/database-editor`
- **Articles Today**: Links to `/keyword-alerts`
- **Keyword Groups**: Links to `/keyword-monitor`
- **Topics**: Links to `/create_topic`

#### 4. Detailed Metrics Grid
Four metric cards with real-time data:

**a) CPU Metrics**
- Process CPU percentage
- System CPU percentage
- Core count
- Load average (1/5/15 minute)

**b) Memory Metrics**
- Process RSS (MB)
- Process memory percentage
- Thread count
- System memory usage with progress bar

**c) Disk Metrics**
- Used/Total disk space
- Free disk space
- Usage percentage with progress bar

**d) File Descriptors**
- Open descriptors
- Soft limit
- Available descriptors
- Connection and file counts
- Usage percentage

### API Endpoints

```
GET /api/dashboard/stats    - Returns: { total_articles, articles_today, keyword_groups, topics }
GET /api/health             - Returns: System health data (see structure below)
```

### Health Data Structure
```typescript
interface HealthData {
  status: string;  // 'healthy', 'degraded', 'critical'
  uptime: { days: number; hours: number; minutes: number };
  warnings: string[];
  cpu: {
    process_percent: number;
    system_percent: number;
    core_count: number;
    load_average?: number[];
  };
  memory: {
    process: { rss_mb: number; percent: number; num_threads: number };
    system: { used_gb: number; total_gb: number; percent: number };
  };
  disk: {
    root: { used_gb: number; total_gb: number; free_gb: number; percent: number };
  };
  file_descriptors: {
    open: number;
    soft_limit: number;
    available: number;
    connections: number;
    files: number;
    usage_percent: number;
  };
}
```

### Data Refresh
- Health data refreshes every 30 seconds
- Clocks update every 1 second

---

## Shared Components

### SharedNavigation (`components/SharedNavigation.tsx`)
Main sidebar navigation component used by all dashboards.

**Main Navigation Links:**
- `/` - Home
- `/trend-convergence` - Trend Convergence (Anticipate)
- `/news-feed-v2` - News Feed
- `/keyword-alerts` - Keyword Alerts

**Operational Links:**
- `/config` - Configuration
- `/trend-convergence?onboarding=true` - Setup Topic
- `/create_topic` - Create Topic
- `/promptmanager` - Prompt Manager
- `/model-bias-arena` - Model Bias Arena
- `/vector-analysis-improved` - Vector Analysis
- `/database-editor` - Database Editor
- `/analytics` - Analytics
- `/health/dashboard` - Health Dashboard

**External Links:**
- Gitbook KB
- Discord Community
- Chrome Extension

### UI Component Library
Located in `/src/components/ui/` using Radix UI primitives:
- Buttons, Cards, Tabs
- Dropdowns, Selects, Modals/Dialogs
- Inputs, Forms, Tooltips
- Navigation Menu, Breadcrumb
- Scroll Area, Separator
- Pagination, Skeleton
- Accordion, Calendar

---

## Build Configuration

### Vite Configuration (`vite.config.mts`)

```typescript
export default defineConfig({
  base: '/static/trend-convergence/',  // Base URL for Trend Convergence assets
  plugins: [react()],
  resolve: {
    extensions: ['.js', '.jsx', '.ts', '.tsx', '.json'],
    alias: {
      '@': path.resolve(__dirname, './src'),
      // Multiple Radix UI and third-party aliases
    },
  },
  build: {
    target: 'esnext',
    outDir: 'build',
    rollupOptions: {
      input: {
        main: path.resolve(__dirname, 'index.html'),         // Trend Convergence
        operations: path.resolve(__dirname, 'index-operations.html'),  // Operations HQ
      },
    },
  },
  server: {
    port: 3000,
    open: true,
  },
});
```

### Build Output
- **Main entry**: `build/index.html` + `build/assets/`
- **Operations entry**: `build/index-operations.html` + `build/assets/`
- Both entries share the same compiled asset bundles

### NPM Scripts
```json
{
  "dev": "vite",           // Start development server
  "build": "vite build"    // Build for production
}
```

### Dependencies

**Core Framework:**
- react@^18.3.1
- react-dom@^18.3.1

**UI Framework:**
- Radix UI components (40+ primitives)
- @radix-ui/react-*@^1.x.x

**Styling:**
- tailwindcss@^3.4.18
- postcss@^8.5.6
- autoprefixer@^10.4.21

**Forms & Validation:**
- react-hook-form@^7.55.0
- lucide-react@^0.487.0

**Utilities:**
- recharts@^2.15.2 (data visualization)
- react-resizable-panels@^2.1.7 (layout)
- react-day-picker@^8.10.1 (date picking)
- sonner@^2.0.3 (notifications)
- cmdk@^1.1.1 (command palette)
- next-themes@^0.4.6 (theme switching)

**Build Tools:**
- vite@6.3.5
- @vitejs/plugin-react-swc@^3.10.2

---

## API Client Layer (`services/api.ts`)

### Authentication
- Uses session cookies (`credentials: 'include'`)
- Redirects to `/login` on 401/403 errors
- All requests include `Content-Type: application/json`

### Main API Functions

```typescript
// Trend Convergence Analysis
generateTrendConvergence(params: {
  topic: string;
  model: string;
  timeframe_days?: number;
  analysis_depth?: string;
  sample_size_mode?: string;
  custom_limit?: number;
  consistency_mode?: string;
  enable_caching?: boolean;
  cache_duration_hours?: number;
  profile_id?: number;
  tab?: string;
}): Promise<TrendConvergenceData>

// Topics & Profiles
getTopics(): Promise<Topic[]>
getOrganizationalProfiles(): Promise<OrganizationalProfile[]>
createOrganizationalProfile(profile): Promise<{success, profile_id, message}>
updateOrganizationalProfile(profileId, profile): Promise<{success, message}>
deleteOrganizationalProfile(profileId): Promise<{success, message}>

// AI Models
getAvailableModels(): Promise<AIModel[]>

// Onboarding
validateApiKey(data): Promise<{status, configured, masked_key?}>
checkApiKeys(): Promise<{newsapi, openai, anthropic, ...}>
suggestTopicAttributes(data): Promise<{explanation, categories, ...}>
saveTopic(data): Promise<{status, success?, message, topic_id?}>
completeOnboarding(): Promise<{success, message}>

// Analysis Data Retrieval (Raw/Stored)
getMarketSignalsRaw(analysisId): Promise<any>
getImpactTimelineRaw(analysisId): Promise<any>
getStrategicRecommendationsRaw(analysisId): Promise<any>
getFutureHorizonsRaw(analysisId): Promise<any>
getConsensusAnalysisRaw(analysisId): Promise<any>
```

---

## State Management Hook (`useTrendConvergence.ts`)

### Purpose
Centralized state management for analysis configuration, data fetching, and UI state.

### State Structure
```typescript
interface UseTrendConvergenceReturn {
  // Data
  data: TrendConvergenceData | MarketSignalsData | null;
  topics: Topic[];
  profiles: OrganizationalProfile[];
  models: AIModel[];
  config: AnalysisConfig;
  
  // State
  loading: boolean;
  error: string | null;
  
  // Actions
  generateAnalysis(forceRefresh?: boolean): Promise<void>;
  updateConfig(updates: Partial<AnalysisConfig>): void;
  clearError(): void;
}
```

### Configuration Defaults
```typescript
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

### Features
- Auto-loads topics, profiles, and models on init
- Persists config to localStorage
- Per-tab data caching
- Auto-generates analysis when tab changes if no cached data
- Handles Market Signals with different API endpoint
- Force refresh support

---

## Backend Routes (`app/routes/`)

### Relevant Route Files

#### 1. `trend_convergence_routes.py`
Main endpoint for Trend Convergence analysis:
- `GET /api/trend-convergence/{topic}`
- Supports tabs: consensus, strategic, timeline, signals, horizons
- Handles caching, consistency modes, sample size calculation
- Integrates with Auspex service

**Context Limits Supported:**
- GPT-4.1 variants: 1,000,000 tokens
- Claude 3.5 Sonnet: 200,000 tokens
- GPT-4 Turbo: 128,000 tokens
- GPT-4o: 128,000 tokens
- Gemini 1.5 Pro: 2,097,152 tokens

#### 2. `dashboard_routes.py`
Dashboard statistics and data:
- `GET /api/dashboard/stats`
- Returns article counts, topic counts, keyword groups

#### 3. `health_routes.py`
System health monitoring:
- `GET /api/health`
- Returns CPU, memory, disk, file descriptor metrics

#### 4. `web_routes.py`
HTML page routing:
- `/config` - Configuration page
- `/promptmanager` - Prompt manager
- `/vector-analysis-improved` - Vector search UI
- `/topic-dashboard` - Per-topic dashboard

---

## Browser Storage Schema

### localStorage Keys
```
trendConvergence_config                     // Analysis config
trendConvergence_topic                      // Last selected topic
trendConvergence_data_consensus             // Tab-specific cache
trendConvergence_data_strategic
trendConvergence_data_timeline
trendConvergence_data_signals
trendConvergence_data_horizons
trendConvergence_data                       // Legacy key (all data)
worldClockTimezones                         // World clock settings
```

---

## Features Removed from Community Editing

Based on git history and codebase analysis:

### 1. Community Article Editing
- Removed article edit functionality for community users
- Dashboard now read-only for community contributions
- Admin-only editing retained

### 2. Podcast-Related Features
- Podcast script generation removed (`/podcast-director`)
- FFmpeg integration removed
- Podcast diagram UI removed (see commit `5b2f7bf0`)

### 3. Topic Map Visualization
- Topic relationship mapping removed (commit `ce6fbc9a`)
- Replaced with other analysis methods

### 4. Bugfixes Documentation
- Legacy bugfixes documentation removed during refactoring (commit `420c44c0`)

### 5. Model-Specific API Key Management
- Removed model-specific API keys
- Consolidated to provider-wide API keys (commit `fed76159`)

---

## Deployment & Serving

### Production Serving
The React dashboards are served from FastAPI backend:

```python
# In web_routes.py
GET /trend-convergence       → Serves Trend Convergence dashboard
GET /health/dashboard        → Serves Operations HQ
```

### Asset Serving
- Static assets served from `/static/trend-convergence/` path
- Built files in `build/` directory
- NGINX reverse proxy configured to serve static files

### Development
```bash
cd /home/orochford/tenants/multi.aunoo.ai/ui
npm run dev    # Runs on http://localhost:3000
```

### Production Build
```bash
cd /home/orochford/tenants/multi.aunoo.ai/ui
npm run build  # Output to build/
```

---

## Design System

### Color Palette
- **Primary**: Pink/Magenta (#ec4899, #fb7185)
- **Neutral**: Gray scale (#050f1c to #f9fafb)
- **Status**: Green (healthy), Yellow (degraded), Red (critical)
- **Data Viz**: Orange, Purple, Green, Blue, Pink, Lime

### Layout Grid
- Responsive grid system: 1-4 columns based on breakpoint
- Sidebar navigation: 256px fixed width
- Main content: flex-1 (remaining space)
- Horizontal padding: 24px (px-6)
- Vertical padding: 24px (py-6)

### Typography
- Font: Inter (300-700 weights)
- Source: Google Fonts CDN

### Components Style
- Card-based layout with shadows
- Rounded corners (8px - rounded-lg)
- Hover state transitions
- Modal dialogs with overlays
- Inline form validation

---

## Performance Considerations

### Caching Strategy
1. **Tab-based caching**: Each tab stores its data separately
2. **24-hour default TTL**: Configurable cache duration
3. **Force refresh**: UI supports bypassing cache
4. **localStorage limit**: Monitoring for quota exceeded

### API Rate Limiting
- Backend implements analysis caching
- Sample size optimization based on model context window
- Automatic model selection based on task requirements

### Bundle Size
- Code splitting by tab recommended
- Lazy loading for modals and heavy components
- Radix UI tree-shaking enabled

---

## Navigation Map

```
SharedNavigation (sidebar)
├── Main Section
│   ├── Home (/)
│   ├── Trend Convergence (/trend-convergence)
│   ├── News Feed (/news-feed-v2)
│   └── Keyword Alerts (/keyword-alerts)
├── Operational Section
│   ├── Configuration (/config)
│   ├── Setup Topic (/trend-convergence?onboarding=true)
│   ├── Create Topic (/create_topic)
│   ├── Prompt Manager (/promptmanager)
│   ├── Model Bias Arena (/model-bias-arena)
│   ├── Vector Analysis (/vector-analysis-improved)
│   ├── Database Editor (/database-editor)
│   ├── Analytics (/analytics)
│   └── Health Dashboard (/health/dashboard)
├── External Links
│   ├── Gitbook KB
│   ├── Discord
│   └── Chrome Extension
└── Logout (/logout)
```

---

## Summary

The Aunoo AI React dashboards represent a sophisticated modern web application with:

- **Multiple specialized dashboards** for different operational needs
- **Advanced Vite build configuration** supporting multiple entry points
- **Comprehensive TypeScript typing** for type safety
- **Session-based authentication** with secure API communication
- **Sophisticated state management** with localStorage caching
- **Accessible UI components** using Radix UI primitives
- **Responsive design** with Tailwind CSS
- **Real-time data updates** with configurable refresh intervals
- **Data export capabilities** (PDF, images, raw JSON)
- **Organizational context awareness** for multi-tenant scenarios

The dashboards are designed for enterprise use with focus on trend analysis, strategic decision-making, and operational visibility.
