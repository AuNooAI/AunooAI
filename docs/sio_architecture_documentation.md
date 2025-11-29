# Strategic Intelligence Oracle (SIO) Architecture Documentation

## Executive Overview

The Strategic Intelligence Oracle is a multi-stage AI-powered system that analyzes 24 hours of news coverage, clusters articles into distinct events, performs deep verification, and generates executive intelligence briefs. The system is designed to meet BBC/Wiley editorial standards with emphasis on accuracy, sourcing, and confidence assessment.

### Key Characteristics
- **4-Stage Workflow**: Discovery → Triage → Deep Analysis → Synthesis
- **Quality Gates**: Source diversity, credibility filtering, contradiction detection
- **Real-Time Streaming**: SSE-based progress updates to frontend during scans
- **Configurable Agents**: Each stage uses customizable AI prompts and models
- **Audit Trail**: Complete documentation of processing and AI involvement

---

## Architecture Layers

### Layer 1: Backend Services (FastAPI)

#### 1.1 Strategic Intelligence Service
**File**: `/home/orochford/tenants/testbed.aunoo.ai/app/services/strategic_intelligence_service.py`

**Core Class**: `StrategicIntelligenceService`

**Responsibilities**:
- Orchestrates the complete 4-stage SIO workflow
- Manages state across pipeline stages
- Calls article analyzer for deep event analysis
- Generates final intelligence brief

**Key Methods**:

```python
async def run_scan(
    topic: Optional[str],
    hours_back: int = 24,
    max_events: int = 30,
    config: Optional[SIOConfig] = None
) -> AsyncGenerator[Dict, None]:
    """
    Main entry point for SIO scans.
    
    Yields progress updates at each stage:
    - stage: current stage name (discovery|triage|deep_analysis|synthesis|complete)
    - progress: 0.0-1.0 for current stage
    - status: operational status
    - And stage-specific data (articles_collected, events_identified, etc.)
    """
```

**State Management**:

`SIOState` dataclass tracks:
- `raw_articles`: All discovered articles (discovery output)
- `screened_articles`: Credibility-filtered articles (triage input)
- `event_clusters`: Identified events (triage output)
- `analyzed_events`: Deep-analyzed events (deep_analysis output)
- `intelligence_brief`: Final markdown brief (synthesis output)
- `stage_progress`: Per-stage progress tracking
- `audit_trail`: Complete processing record

**Configuration**:

`SIOConfig` dataclass with defaults:
- `hours_back`: 24 (time window)
- `max_discovery_articles`: 500
- `max_events_to_analyze`: 30
- `credibility_threshold`: 60 (MBFC score)
- `similarity_threshold`: 0.75 (for clustering)
- Model choices per stage (default: gpt-4.1-mini for discovery/triage, gpt-4o for analysis/synthesis)

#### 1.2 Stage 1: Discovery

**Method**: `_run_discovery(state, config)`

**Purpose**: Cast wide net to gather diverse news articles from past N hours

**Process**:
1. Generate 8-12 diverse search queries using discovery agent
2. Execute queries in parallel batches (internal database + external sources)
3. Deduplicate by URL
4. Collect statistics (sources, categories, time range)

**Discovery Agent Prompt**: `/home/orochford/tenants/testbed.aunoo.ai/data/auspex/agents/sio_discovery_agent.md`

**Outputs**:
- `state.raw_articles`: 50-500 articles
- `state.collection_stats`: Coverage metadata

**Example Query Output**:
```json
{
  "search_queries": [
    {
      "query": "breaking news major developments",
      "category": "general",
      "priority": "critical",
      "source_preference": "both"
    },
    {
      "query": "geopolitical conflict diplomatic",
      "category": "politics",
      "priority": "critical",
      "source_preference": "both"
    }
  ]
}
```

#### 1.3 Stage 2: Triage

**Method**: `_run_triage(state, config)`

**Purpose**: Screen articles for credibility and cluster into events

**Process**:
1. **Credibility Screening**:
   - Look up source in MediaBias database
   - Get MBFC credibility rating (Very High→95, High→85, Mostly Factual→70, etc.)
   - Filter: keep only articles with score ≥ credibility_threshold (default 60)
   - Unknown sources assigned score 50

2. **Event Clustering**:
   - Call triage agent with article summaries
   - Group articles covering the same event
   - Assign preliminary importance (critical/high/medium/low)
   - Calculate source diversity score per cluster
   - Select representative article (highest credibility)

**Triage Agent Prompt**: `/home/orochford/tenants/testbed.aunoo.ai/data/auspex/agents/sio_triage_agent.md`

**Clustering Example**:
```json
{
  "event_clusters": [
    {
      "cluster_id": "evt_001",
      "event_title": "Federal Reserve Announces 0.25% Rate Cut",
      "preliminary_importance": "critical",
      "article_count": 15,
      "source_diversity_score": 0.87,
      "keywords": ["federal reserve", "interest rates", "monetary policy"]
    }
  ]
}
```

**Outputs**:
- `state.screened_articles`: Credibility-filtered articles
- `state.event_clusters`: List of EventCluster objects

#### 1.4 Stage 3: Deep Analysis

**Method**: `_run_deep_analysis(state, config)` → `_analyze_event(cluster)`

**Purpose**: Perform rigorous verification and impact assessment on top events

**Process**:
1. Sort events by preliminary importance
2. Take top N events (default 30)
3. For each event, call `ArticleIntelligenceAnalyzer.analyze_cluster()`
4. Accumulate results with controlled parallelism (default 5 concurrent)

**Deep Analysis Agent Prompt**: `/home/orochford/tenants/testbed.aunoo.ai/data/auspex/agents/sio_deep_analysis_agent.md`

**Key Analysis Components**:
- **Key Facts Extraction**: Each fact marked with sources and confidence (0.5-1.0)
- **Verification Status**: 
  - Claims verified by 2+ sources
  - Contradictions found and resolved/flagged
  - Overall confidence score
- **Quality Gates**: 
  - Accuracy (facts cross-referenced?)
  - Context (multiple perspectives included?)
  - Sourcing (credible and attributed?)
- **Impact Assessment**:
  - Urgency score (0-1): How time-sensitive?
  - Scale score (0-1): How many affected?
  - Consequence score (0-1): What's the impact?
  - Overall importance: Weighted combination

**Outputs**:
- `state.analyzed_events`: List of EventCluster with ArticleAnalysis attached
- Events sorted by final_importance_score (highest first)

#### 1.5 Stage 4: Synthesis

**Method**: `_run_synthesis(state, config)`

**Purpose**: Generate final markdown intelligence brief for decision-makers

**Process**:
1. Prepare event summaries with analysis data
2. Call synthesis agent with markdown generation prompt
3. Stream response in real-time to frontend
4. Append audit trail footer
5. Return complete brief

**Synthesis Agent Prompt**: `/home/orochford/tenants/testbed.aunoo.ai/data/auspex/agents/sio_synthesis_agent.md`

**Brief Structure**:
1. Executive Summary (top 5 critical items)
2. Critical Events (detailed analysis with confidence markers)
3. Emerging Signals (weak signals worth monitoring)
4. Source Analysis (diversity, credibility distribution, gaps)
5. Confidence Assessment (per-event breakdown)
6. Methodology (time window, articles analyzed, approach)
7. Audit Trail (models used, AI disclosure)

**Confidence Indicators**:
- 🟢 HIGH CONFIDENCE (0.85+): Verified by 3+ credible sources
- 🟡 MEDIUM CONFIDENCE (0.70-0.84): Partially verified
- 🔴 LOW CONFIDENCE (<0.70): Unverified or conflicting

**Example Output**:
```markdown
# Strategic Intelligence Brief
## 24-Hour Analysis: [Date Range]

---

## Executive Summary

🔴 **CRITICAL ITEMS:**
1. **Federal Reserve cuts rates by 0.25%** - First cut since [date]
2. **Major cyberattack on [Entity]** - Millions of records potentially compromised
...

---

## Critical Events

### 🔴 Federal Reserve Announces Rate Cut
**Confidence:** 🟢 HIGH (0.95)

The US Federal Reserve reduced the federal funds rate by 25 basis points...

**Key Facts:**
- Rate cut: 0.25 percentage points 🟢
- Vote: Unanimous 🟡 (single source)

**Strategic Implications:**
- Lower borrowing costs likely to stimulate...

**Sources:** Reuters (High), Bloomberg (High), WSJ (High)

---

## Audit Trail
**AI Disclosure:** This intelligence brief was generated with AI assistance...
```

---

### Layer 2: API Routes (FastAPI)

**File**: `/home/orochford/tenants/testbed.aunoo.ai/app/routes/sio_routes.py`

**Base Path**: `/api/sio`

#### Endpoints

**POST `/scan`** - Start a scan
```python
class ScanRequest(BaseModel):
    topic: Optional[str] = None  # Focus filter
    hours_back: int = 24  # Time window
    max_events: int = 30  # Top N events to analyze
    credibility_threshold: int = 60  # Min credibility score
    stream: bool = True  # Enable SSE streaming

# Returns StreamingResponse with SSE (if stream=True)
# or waits for completion and returns full result (if stream=False)
```

**POST `/analyze-url`** - Single article analysis
```python
class AnalyzeUrlRequest(BaseModel):
    url: str  # Article URL
    topic: Optional[str] = None  # Context
    deep_verification: bool = True  # Cross-reference extensively
```

**GET `/scans`** - List recent scans
- Pagination support
- Filter by topic/status

**GET `/scan/{scan_id}`** - Get scan details
**GET `/scan/{scan_id}/brief`** - Get just the brief
**GET `/scan/{scan_id}/events`** - Get analyzed events
**DELETE `/scan/{scan_id}`** - Delete a scan

**GET `/prompts`** - List all SIO agent prompts
```json
{
  "success": true,
  "prompts": [
    {
      "id": "sio_discovery_agent",
      "name": "Discovery",
      "description": "Generates diverse search queries",
      "content": "...",
      "metadata": { "model_config": {...} }
    }
  ]
}
```

**PUT `/prompts/{agent_id}`** - Update agent prompt/config
```python
class UpdatePromptRequest(BaseModel):
    content: str  # New prompt markdown
    model: Optional[str] = None  # AI model
    temperature: Optional[float] = None  # 0.0-1.0
```

**GET `/prompts/{agent_id}` - Get specific prompt**

**GET `/health`** - Service health check

#### Streaming Response Format (Server-Sent Events)

```
data: {"stage": "discovery", "status": "started", "progress": 0.0, "scan_id": "..."}
data: {"stage": "discovery", "status": "completed", "progress": 1.0, "articles_collected": 342}
data: {"stage": "triage", "status": "started", "progress": 0.0}
data: {"stage": "triage", "status": "completed", "progress": 1.0, "events_identified": 47}
data: {"stage": "deep_analysis", "status": "analyzing", "progress": 0.2, "events_analyzed": 6}
...
data: {"stage": "synthesis", "status": "writing", "progress": 0.5, "chunk": "# Strategic Intelligence Brief\n"}
data: {"stage": "complete", "status": "success", "progress": 1.0, "brief": "...", "metadata": {...}}
```

---

### Layer 3: Frontend Components (React/TypeScript)

#### 3.1 useStrategicIntelligence Hook

**File**: `/home/orochford/tenants/testbed.aunoo.ai/ui/src/hooks/useStrategicIntelligence.ts`

**Purpose**: Manage SIO state and coordinate with backend

**State Managed**:
```typescript
interface UseStrategicIntelligenceReturn {
  // Scan control
  isScanning: boolean;
  startScan: (config: SIOConfig) => void;
  cancelScan: () => void;
  
  // Progress tracking
  currentStage: string;  // discovery|triage|deep_analysis|synthesis|complete
  stageProgress: number;  // 0.0-1.0
  overallProgress: number;  // 0.0-1.0 (weighted by stage importance)
  
  // Brief content
  briefContent: string;  // Markdown content being streamed
  briefChunks: string[];  // Individual chunks received
  scanResult: SIOBriefData | null;  // Final result
  
  // Statistics
  articlesCollected: number;
  articlesScreened: number;
  eventsIdentified: number;
  eventsAnalyzed: number;
  currentEvent: string;  // Current event being analyzed
  
  // Error handling
  error: string | null;
  clearError: () => void;
  
  // Cleanup
  clearResults: () => void;
}
```

**Key Features**:
- **Weighted Progress Calculation**:
  - Discovery: 20% (0.0-0.2)
  - Triage: 15% (0.2-0.35)
  - Deep Analysis: 45% (0.35-0.8)
  - Synthesis: 20% (0.8-1.0)

- **Local Storage Caching**:
  - Caches last brief on completion
  - Loads on mount
  - Can be cleared via `clearResults()`

- **Streaming Management**:
  - Accumulates brief chunks in real-time
  - Updates statistics as they arrive
  - Handles SSE connection cancellation

#### 3.2 IntelligenceBrief Component

**File**: `/home/orochford/tenants/testbed.aunoo.ai/ui/src/components/IntelligenceBrief.tsx`

**Purpose**: Display SIO scan UI and results

**Props**:
```typescript
interface IntelligenceBriefProps {
  // Scan control
  topic?: string;
  profileId?: number;
  
  // State from hook
  isScanning: boolean;
  currentStage: string;
  stageProgress: number;
  overallProgress: number;
  briefContent: string;
  scanResult: any;
  error: string | null;
  articlesCollected: number;
  articlesScreened: number;
  eventsIdentified: number;
  eventsAnalyzed: number;
  currentEvent: string;
  
  // Config (shown in expandable panel)
  hoursBack: number;
  maxEvents: number;
  credibilityThreshold: number;
  onHoursBackChange: (value: number) => void;
  onMaxEventsChange: (value: number) => void;
  onCredibilityThresholdChange: (value: number) => void;
  
  // Actions
  onClearError: () => void;
  onClearResults: () => void;
}
```

**Sub-Components**:

1. **StageIndicator**: Visual pipeline showing stage progression
   - Completed stages: green checkmark
   - Active stage: pink pulse animation
   - Pending stages: gray numbers
   - Connecting lines show progress

2. **ScanStats**: Grid showing real-time metrics
   - Articles Found (discovery output)
   - Passed Screening (triage output)
   - Events Identified (triage output)
   - Events Analyzed (deep_analysis output)
   - Current event being analyzed

3. **QualityGatesDisplay**: Visual quality checks
   - Source Diversity (passed/failed)
   - Credibility Check (passed/failed)
   - Freshness (passed/failed)
   - Geographic Diversity (passed/failed)
   - Contradiction Check (passed/failed)

4. **EventsSummary**: Expandable list of analyzed events
   - Importance badges (critical/high/medium)
   - Source count per event
   - Confidence scores
   - Expandable to show all events

5. **BriefDisplay**: Markdown rendering with custom styling
   - Confidence indicators (🟢🟡🔴)
   - Importance markers (emoji badges)
   - Custom heading styles
   - Source attribution
   - Quality gate badges
   - Metadata panel

#### 3.3 SIOTuneModal Component

**File**: `/home/orochford/tenants/testbed.aunoo.ai/ui/src/components/SIOTuneModal.tsx`

**Purpose**: Configure SIO workflow (prompts, models, parameters)

**Features**:

1. **Agent Selection**:
   - 4 agent tabs (Discovery, Triage, Deep Analysis, Synthesis)
   - Shows unsaved changes indicator
   - Fetches prompts on modal open

2. **Agent Configuration**:
   - **Model Selection**: Dropdown to choose AI model (gpt-4o, gpt-4.1-mini, etc.)
   - **Creativity/Temperature**: 4 presets
     - Precise (0.1): Deterministic, good for analysis
     - Balanced (0.3): Default, mix of precision and variety
     - Exploratory (0.5): More varied responses
     - Creative (0.7): High variety, less consistent

3. **Prompt Editor**:
   - Full textarea for markdown content
   - Syntax highlighting for markdown
   - Shows current agent description

4. **Global Settings**:
   - Credibility threshold slider
   - Visual indicator (Strict/Moderate/Relaxed/Minimal)

5. **State Management**:
   - Tracks unsaved changes per agent
   - Reset to original via "Reset" button
   - Save via "Save" button (updates backend)
   - Shows "Configuration saved" or "Unsaved changes" status

#### 3.4 App.tsx Integration

**File**: `/home/orochford/tenants/testbed.aunoo.ai/ui/src/App.tsx`

**Integration Pattern**:

```typescript
// In App component
const sio = useStrategicIntelligence();

// State lifted from hook
const [hoursBack, setHoursBack] = useState(24);
const [maxEvents, setMaxEvents] = useState(30);
const [credibilityThreshold, setCredibilityThreshold] = useState(60);

// Handlers
const handleStartScan = () => {
  sio.startScan({
    topic: currentTopic,
    hours_back: hoursBack,
    max_events: maxEvents,
    credibility_threshold: credibilityThreshold,
  });
};

// Render
<IntelligenceBrief
  isScanning={sio.isScanning}
  currentStage={sio.currentStage}
  // ... other props
  onHoursBackChange={setHoursBack}
  onMaxEventsChange={setMaxEvents}
  onCredibilityThresholdChange={setCredibilityThreshold}
/>

<SIOTuneModal
  open={showTuneModal}
  onOpenChange={setShowTuneModal}
  credibilityThreshold={credibilityThreshold}
  onCredibilityThresholdChange={setCredibilityThreshold}
/>
```

---

### Layer 4: API Service Layer

**File**: `/home/orochford/tenants/testbed.aunoo.ai/ui/src/services/api.ts`

**Type Definitions**:

```typescript
interface SIOScanRequest {
  topic?: string;
  hours_back?: number;
  max_events?: number;
  credibility_threshold?: number;
  stream?: boolean;
}

interface SIOScanProgress {
  stage: 'discovery' | 'triage' | 'deep_analysis' | 'synthesis' | 'complete' | 'error';
  status: string;
  progress: number;
  scan_id?: string;
  articles_collected?: number;
  articles_screened?: number;
  events_identified?: number;
  events_analyzed?: number;
  current_event?: string;
  chunk?: string;  // For synthesis streaming
  metadata?: { articles_collected, articles_screened, ... };
  audit_trail?: any;
  error?: string;
}

interface SIOBriefData {
  scan_id: string;
  brief: string;  // Complete markdown brief
  metadata: {
    articles_collected: number;
    articles_screened: number;
    events_identified: number;
    events_analyzed: number;
    duration_seconds: number;
  };
  audit_trail: any;
  events?: SIOEventCluster[];
}
```

**Key Functions**:

```typescript
// Start streaming scan
function startSIOScanStream(
  params: SIOScanRequest,
  onProgress: (data: SIOScanProgress) => void,
  onComplete: (data: SIOBriefData) => void,
  onError: (error: string) => void
): () => void  // Returns cleanup function
```

Implementation uses:
- Fetch API with AbortController for cancellation
- TextDecoder for streaming response
- SSE line parsing (lines starting with "data: ")
- JSON parsing of each event
- Returns cancel function for cleanup

```typescript
// Non-streaming scan (waits for completion)
async function startSIOScan(params: SIOScanRequest): Promise<SIOBriefData>

// Single URL analysis
async function analyzeSIOUrl(request: AnalyzeUrlRequest): Promise<ArticleAnalysis>

// Health check
async function getSIOServiceHealth(): Promise<HealthStatus>
```

---

## Data Flow Diagrams

### Scan Lifecycle

```
User clicks "Start Scan"
        ↓
App.tsx lifts state to hook: useStrategicIntelligence()
        ↓
Hook calls: startSIOScanStream() via API service
        ↓
API sends POST /api/sio/scan with ScanRequest
        ↓
Backend: StrategicIntelligenceService.run_scan()
        ↓
Stage 1: DISCOVERY
  - Generate queries (discovery agent)
  - Execute searches (parallel)
  - Collect 50-500 articles
  - Emit SSE: {"stage": "discovery", ...}
        ↓
Stage 2: TRIAGE
  - Credibility screening (MediaBias lookup)
  - Cluster articles (triage agent)
  - Assign importance
  - Emit SSE: {"stage": "triage", ...}
        ↓
Stage 3: DEEP ANALYSIS
  - Analyze top N events (ArticleIntelligenceAnalyzer)
  - Extract facts, entities, timeline
  - Verify claims cross-source
  - Apply quality gates
  - Assess impact
  - Emit SSE: {"stage": "deep_analysis", "progress": 0.X, ...}
        ↓
Stage 4: SYNTHESIS
  - Generate markdown brief (synthesis agent)
  - Stream chunks in real-time
  - Emit SSE: {"stage": "synthesis", "chunk": "...", ...}
  - Emit SSE: {"stage": "complete", "brief": "...", ...}
        ↓
Hook: handleComplete() called
  - Set scanResult = data
  - briefContent updated
  - Cache to localStorage
        ↓
Component: IntelligenceBrief re-renders
  - Shows completed brief
  - Displays metadata & stats
  - No longer pulsing "Scanning..."
```

### Event Analysis Drill-Down

```
EventCluster (from triage)
  - title: "Federal Reserve Rate Cut"
  - articles: [Article1, Article2, ... ArticleN]
  - preliminary_importance: "critical"
        ↓
ArticleIntelligenceAnalyzer.analyze_cluster()
  (from article_intelligence_analyzer.py)
        ↓
Returns ArticleAnalysis with:
  - key_facts: [Fact1, Fact2, ...] with sources & confidence
  - key_entities: [Entity1, Entity2, ...]
  - timeline: [Event1 at T1, Event2 at T2, ...]
  - verification_status: claims_verified, contradictions_found
  - quality_gates: accuracy_passed, context_passed, sourcing_passed
  - impact_assessment: urgency, scale, consequence, overall_importance
        ↓
EventCluster.analysis = ArticleAnalysis
EventCluster.final_importance_score = impact_assessment.overall_importance
        ↓
Used in synthesis for brief generation
```

---

## Agent Prompt Architecture

### Discovery Agent
**File**: `/home/orochford/tenants/testbed.aunoo.ai/data/auspex/agents/sio_discovery_agent.md`

**Input**: Topic (optional), time window

**Output**: List of 8-12 search queries with:
- Query string
- Category
- Priority (critical/high/medium)
- Source preference (internal/external/both)

**Model**: gpt-4.1-mini (fast, low-cost)

**Temperature**: 0.2 (deterministic)

**Purpose**: Generate diverse queries to maximize article coverage

---

### Triage Agent
**File**: `/home/orochford/tenants/testbed.aunoo.ai/data/auspex/agents/sio_triage_agent.md`

**Input**: Array of articles with:
- Index
- Title
- Summary (200 chars)
- Source
- Credibility score

**Output**: Event clusters with:
- cluster_id
- event_title
- article_indices (which articles belong)
- preliminary_importance
- source_diversity_score
- keywords

**Model**: gpt-4.1-mini (fast processing)

**Temperature**: 0.2 (consistent clustering)

**Importance Criteria**:
- Critical: Breaking news, major policy, security events, market-moving
- High: Significant developments, important discussions, notable incidents
- Medium: Noteworthy stories, ongoing developments
- Low: Routine updates, minor incidents, local stories

---

### Deep Analysis Agent
**File**: `/home/orochford/tenants/testbed.aunoo.ai/data/auspex/agents/sio_deep_analysis_agent.md`

**Input**: Event cluster with all articles

**Output**: Comprehensive analysis with:
- Detailed summary
- Key facts (each with sources and confidence: 0.5-1.0)
- Key entities (people, organizations, locations)
- Timeline of events
- Implications (economic, political, market, etc.)
- Verification status (verified, unverified, contradictions)
- Quality gates (accuracy, context, sourcing)
- Impact assessment (urgency, scale, consequence, overall importance)

**Model**: gpt-4o (more capable for deep analysis)

**Temperature**: 0.3 (some flexibility for synthesis, but deterministic)

**Editorial Standards**: BBC standards applied
- Accuracy: Facts verified by 2+ sources?
- Context: Multiple perspectives included?
- Sourcing: Credible sources properly attributed?

**Confidence Scoring**:
- 0.95-1.00: Verified by 3+ high-credibility sources
- 0.85-0.94: Verified by 2+ sources, minor discrepancies resolved
- 0.70-0.84: Single primary source with corroboration
- 0.50-0.69: Unverified but plausible
- Below 0.50: Unverified, contradicted, or questionable source

---

### Synthesis Agent
**File**: `/home/orochford/tenants/testbed.aunoo.ai/data/auspex/agents/sio_synthesis_agent.md`

**Input**: Array of analyzed events with:
- Title
- Category
- Key facts
- Verification status
- Quality gates
- Impact assessment
- Source information

**Output**: Markdown-formatted intelligence brief with:
1. Executive Summary (top 5 critical items)
2. Critical Events (ranked by importance)
3. Emerging Signals (weak signals for monitoring)
4. Source Analysis (diversity, credibility, gaps)
5. Confidence Assessment (per-event breakdown)
6. Methodology (time window, articles, approach)
7. Audit Trail (models used, AI disclosure)

**Model**: gpt-4o (high-quality prose generation)

**Temperature**: 0.4 (balanced creativity and consistency)

**Confidence Indicators**:
- 🟢 HIGH CONFIDENCE (0.85+)
- 🟡 MEDIUM CONFIDENCE (0.70-0.84)
- 🔴 LOW CONFIDENCE (<0.70)

**Importance Markers**:
- 🔴 CRITICAL (immediate strategic impact)
- 🟠 HIGH (significant development)
- 🟡 MEDIUM (noteworthy)
- ⚪ MONITORING (emerging signal)

---

## Configuration & Customization

### How to Configure

1. **Global Settings** (in app):
   - Hours back (1-168)
   - Max events to analyze (5-100)
   - Credibility threshold (0-100)

2. **Per-Stage Configuration** (in SIOTuneModal):
   - AI Model selection
   - Temperature/Creativity level
   - Prompt content (markdown)

3. **Stored In**:
   - Prompt files: YAML frontmatter with model_config
   - UI state: React component state in App.tsx

### Example Customization

**Change discovery model to be faster**:
1. Open SIO Tune Modal
2. Click "Discovery" tab
3. Select model: gpt-3.5-turbo
4. Keep temperature at 0.2
5. Click "Save"

**Make synthesis more creative**:
1. Open SIO Tune Modal
2. Click "Synthesis" tab
3. Set temperature to 0.7
4. Click "Save"

**Add custom triage instructions**:
1. Open SIO Tune Modal
2. Click "Triage" tab
3. Edit prompt in textarea
4. Click "Save"

---

## Database Tables (for future implementation)

These tables are referenced in routes but pending migration:

```sql
-- Core scan records
sio_scan_runs (
  scan_id UUID PRIMARY KEY,
  user_id INT,
  topic VARCHAR(255),
  hours_back INT,
  created_at TIMESTAMP,
  completed_at TIMESTAMP,
  status VARCHAR(50),
  brief_content TEXT
);

-- Event clusters per scan
sio_event_clusters (
  cluster_id UUID PRIMARY KEY,
  scan_id UUID FOREIGN KEY,
  title VARCHAR(500),
  summary TEXT,
  preliminary_importance VARCHAR(50),
  final_importance_score FLOAT,
  analysis_json JSONB
);

-- Single article analyses
sio_article_analyses (
  analysis_id UUID PRIMARY KEY,
  user_id INT,
  url TEXT UNIQUE,
  topic VARCHAR(255),
  analysis_json JSONB,
  created_at TIMESTAMP
);
```

---

## Error Handling

### Frontend Error Scenarios

1. **Network Error**: 
   - Displayed in Alert component
   - Error message from backend
   - "Dismiss" button to clear

2. **Scan Timeout**:
   - Partial results returned
   - Error message indicates which stage timed out
   - Can retry with adjusted parameters

3. **Missing API Endpoint**:
   - 404 error
   - Check backend routes are registered

### Backend Error Handling

**Graceful Degradation**:
- Discovery: Falls back to default queries if agent fails
- Triage: Falls back to simple word-overlap clustering if LLM fails
- Synthesis: Falls back to basic markdown brief if agent fails

**Logging**: All errors logged via Python logging module

---

## Performance Considerations

### Optimization Points

1. **Parallelism**:
   - Discovery: Run 3 search queries in parallel
   - Deep Analysis: Analyze up to 5 events concurrently
   - Controlled to avoid overwhelming backend/external APIs

2. **Timeouts**:
   - Discovery: 120 seconds
   - Triage: 60 seconds
   - Deep Analysis: 300 seconds (longest stage)
   - Synthesis: 120 seconds

3. **Caching**:
   - Last brief cached in localStorage
   - Avoids re-running scan if page reloaded
   - `clearResults()` to reset

4. **Cost Optimization**:
   - gpt-4.1-mini for discovery/triage (fast, cheap)
   - gpt-4o for deep analysis/synthesis (higher quality, strategic)
   - Temperature tuning (lower = faster response)

---

## Quality Assurance

### Built-in Quality Gates

1. **Source Credibility**:
   - MBFC database lookup
   - Numeric score threshold
   - Bias information captured

2. **Source Diversity**:
   - Per-cluster source diversity score
   - Computed as: unique_sources / cluster_size
   - High diversity = more trustworthy event assessment

3. **Verification**:
   - Claims cross-referenced across sources
   - Confidence scoring based on agreement
   - Contradictions explicitly noted

4. **BBC Editorial Standards**:
   - Accuracy gate: Facts verified by 2+ sources?
   - Context gate: Multiple perspectives included?
   - Sourcing gate: Sources credible and attributed?

### Audit Trail

Every brief includes:
- Scan ID (unique identifier)
- Time window analyzed
- Topic filter (if any)
- Article statistics (collected, screened, analyzed)
- AI models used
- Processing duration
- AI disclosure statement

---

## Extending for New Narrative Boards

To use SIO as a template for other narrative analysis boards:

### Step 1: Define Stages
- Identify your 3-4 processing stages
- Example: Collection → Filtering → Analysis → Synthesis

### Step 2: Create Agent Prompts
- Create YAML files in `/data/auspex/agents/`
- Define output JSON schema
- Include quality criteria

### Step 3: Implement Service
- Create `YourBoardService` in `/app/services/`
- Implement async generator for streaming
- Manage state across stages
- Call sub-analyzers for deep work

### Step 4: Add API Routes
- Create routes in `/app/routes/`
- POST endpoint to start scan
- GET endpoints for history
- PUT endpoint for prompt tuning

### Step 5: Build React Components
- Create hook for state management
- Create component for UI display
- Integrate with App.tsx
- Create tuning modal for prompts

### Step 6: Define Type System
- TypeScript interfaces in API service
- Request/Response models
- Progress update structure
- Final result structure

---

## Monitoring & Maintenance

### Health Checks
```
GET /api/sio/health
→ Returns { status: "healthy", components: { scan_service, article_analyzer } }
```

### Logging Points
- Each stage start/completion
- Search execution
- Clustering results
- Analysis per event
- Brief generation
- Errors and timeouts

### Model Metrics
- Average articles collected
- Clustering quality (% single-article vs multi-article clusters)
- Verification rate (% facts with 2+ sources)
- Synthesis completion time
- User scan frequency

---

## Summary Table

| Component | Location | Purpose | Key Methods |
|-----------|----------|---------|-------------|
| Service | `strategic_intelligence_service.py` | Orchestrate 4-stage workflow | `run_scan()`, `_run_discovery()`, `_run_triage()`, `_run_deep_analysis()`, `_run_synthesis()` |
| API Routes | `sio_routes.py` | HTTP endpoints | `/scan` (POST), `/analyze-url` (POST), `/prompts` (GET/PUT) |
| Hook | `useStrategicIntelligence.ts` | State management, streaming coordination | `startScan()`, `cancelScan()`, `clearResults()` |
| Component | `IntelligenceBrief.tsx` | UI for scan and display | Renders progress, brief, stats |
| Modal | `SIOTuneModal.tsx` | Configure prompts/models | Fetch/save agent configurations |
| API Service | `api.ts` | HTTP client | `startSIOScanStream()`, `startSIOScan()`, `analyzeSIOUrl()` |

---

## Conclusion

The Strategic Intelligence Oracle demonstrates a sophisticated multi-stage AI analysis system with:
- Clear architectural separation (service → routes → hooks → components)
- Real-time streaming feedback
- Quality gates and verification
- Audit trails and AI disclosure
- Customizable AI agents per stage
- Error handling and graceful degradation

This architecture can serve as a template for building similar multi-stage narrative analysis, consensus analysis, or intelligence synthesis systems with domain-specific modifications to agents, quality criteria, and output formats.

