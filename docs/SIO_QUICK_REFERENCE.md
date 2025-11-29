# Strategic Intelligence Oracle (SIO) - Quick Reference Guide

## System Overview

The SIO is a 4-stage intelligent analysis pipeline that transforms raw news articles into executive intelligence briefs.

### Processing Pipeline
```
Discovery (20%)      Triage (15%)        Deep Analysis (45%)    Synthesis (20%)
├─ Generate queries  ├─ Credibility      ├─ Verify facts        ├─ Format brief
├─ Execute searches  ├─ Clustering       ├─ Cross-reference     ├─ Add confidence
└─ Collect articles  └─ Prioritize       ├─ Quality gates       └─ Audit trail
                                         └─ Impact assessment
```

---

## Key Components by Layer

### Backend Services

| File | Class | Purpose |
|------|-------|---------|
| `strategic_intelligence_service.py` | `StrategicIntelligenceService` | Orchestrate 4-stage workflow |
| `article_intelligence_analyzer.py` | `ArticleIntelligenceAnalyzer` | Deep analysis of event clusters |
| `media_bias.py` | `MediaBias` | MBFC credibility lookup |

### API Routes

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/sio/scan` | POST | Start a scan (streaming or batch) |
| `/api/sio/analyze-url` | POST | Single article deep analysis |
| `/api/sio/prompts` | GET | List all agent prompts |
| `/api/sio/prompts/{agent_id}` | PUT | Update agent configuration |
| `/api/sio/scans` | GET | List historical scans |
| `/api/sio/health` | GET | Service health check |

### Frontend Components

| Component | File | Purpose |
|-----------|------|---------|
| `useStrategicIntelligence` | Hook | State management + streaming |
| `IntelligenceBrief` | Component | Display UI + results |
| `SIOTuneModal` | Component | Configure prompts/models |

### Agent Prompts

| Agent | Purpose | Model | Temp |
|-------|---------|-------|------|
| `sio_discovery_agent` | Generate search queries | gpt-4.1-mini | 0.2 |
| `sio_triage_agent` | Cluster articles → events | gpt-4.1-mini | 0.2 |
| `sio_deep_analysis_agent` | Verify facts + impact | gpt-4o | 0.3 |
| `sio_synthesis_agent` | Generate markdown brief | gpt-4o | 0.4 |

---

## Data Types

### ScanRequest (Frontend → Backend)
```typescript
{
  topic?: string;                     // Filter by topic
  hours_back?: number;                // 1-168 hours
  max_events?: number;                // Top N events to analyze
  credibility_threshold?: number;     // 0-100 (MBFC score)
  stream?: boolean;                   // Enable SSE
}
```

### ScanProgress (Backend → Frontend, SSE)
```typescript
{
  stage: 'discovery' | 'triage' | 'deep_analysis' | 'synthesis' | 'complete';
  status: string;
  progress: number;                   // 0.0-1.0 per stage
  articles_collected?: number;
  articles_screened?: number;
  events_identified?: number;
  events_analyzed?: number;
  current_event?: string;
  chunk?: string;                     // Brief content chunk
  metadata?: {...};
  error?: string;
}
```

### SIOBriefData (Final Result)
```typescript
{
  scan_id: string;
  brief: string;                      // Complete markdown brief
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

---

## Configuration Parameters

### Global Scan Settings
- **Hours Back**: How far back to search (default: 24)
- **Max Events**: Top N events for deep analysis (default: 30)
- **Credibility Threshold**: Min MBFC score (default: 60)

### Per-Agent Settings
- **Model**: AI model to use (gpt-4o, gpt-4.1-mini, etc.)
- **Temperature**: 0.1-1.0 (lower = more deterministic)
- **Prompt**: Markdown instructions for agent

### Default Model Assignments
- Discovery: gpt-4.1-mini (fast, cheap)
- Triage: gpt-4.1-mini (fast, cheap)
- Deep Analysis: gpt-4o (capable, thorough)
- Synthesis: gpt-4o (high-quality writing)

---

## Stage Details

### Stage 1: Discovery (20%)
**Goal**: Cast wide net to gather diverse articles

- Generates 8-12 search queries with LLM
- Executes in parallel batches (3 at a time)
- Queries both internal database + external sources
- Deduplicates by URL
- Collects statistics: sources, categories, time range
- **Timeout**: 120 seconds
- **Output**: 50-500 articles

### Stage 2: Triage (15%)
**Goal**: Screen articles and cluster into events

- Looks up each source in MediaBias/MBFC database
- Assigns credibility score (0-100)
- Filters by `credibility_threshold` (default: 60)
- Clusters articles using LLM (groups same-story articles)
- Assigns preliminary importance: critical/high/medium/low
- Calculates source diversity per cluster
- **Timeout**: 60 seconds
- **Output**: Screened articles + event clusters

### Stage 3: Deep Analysis (45%)
**Goal**: Rigorous verification and impact assessment

- Analyzes top N events (sorted by importance)
- Uses ArticleIntelligenceAnalyzer for each event
- Extracts key facts with source attribution
- Verifies facts across multiple sources
- Detects contradictions
- Applies BBC editorial quality gates:
  - Accuracy: Facts verified by 2+ sources?
  - Context: Multiple perspectives?
  - Sourcing: Credible sources properly attributed?
- Scores impact: urgency (0-1), scale (0-1), consequence (0-1)
- Analyzes 5 events in parallel
- **Timeout**: 300 seconds
- **Output**: Analyzed events with confidence scores

### Stage 4: Synthesis (20%)
**Goal**: Generate executive intelligence brief

- Prepares event summaries with analysis data
- Calls synthesis agent for markdown generation
- Streams response in real-time (chunk by chunk)
- Appends audit trail with AI disclosure
- **Timeout**: 120 seconds
- **Output**: Complete markdown intelligence brief

---

## Confidence Indicators

### Confidence Levels
| Level | Range | Meaning |
|-------|-------|---------|
| HIGH | 0.85-1.00 | Verified by 3+ credible sources |
| MEDIUM | 0.70-0.84 | Partially verified, some uncertainty |
| LOW | <0.70 | Unverified, conflicting, or questionable |

### Importance Ratings
| Level | Meaning |
|-------|---------|
| 🔴 CRITICAL | Immediate strategic impact |
| 🟠 HIGH | Significant development |
| 🟡 MEDIUM | Noteworthy story |
| ⚪ MONITORING | Emerging signal to watch |

---

## Key Interfaces

### Frontend Hook
```typescript
const sio = useStrategicIntelligence();

// Available properties
sio.isScanning              // boolean
sio.currentStage            // 'discovery'|'triage'|'deep_analysis'|'synthesis'|'complete'
sio.overallProgress         // 0.0-1.0 (weighted)
sio.briefContent            // accumulated markdown
sio.error                   // error message

// Available methods
sio.startScan(config)       // (config: SIOConfig) => void
sio.cancelScan()            // () => void
sio.clearResults()          // () => void
sio.clearError()            // () => void
```

### API Service Functions
```typescript
// Streaming (real-time progress)
startSIOScanStream(
  params: SIOScanRequest,
  onProgress: (data: SIOScanProgress) => void,
  onComplete: (data: SIOBriefData) => void,
  onError: (error: string) => void
): () => void  // returns cancel function

// Non-streaming (waits for completion)
startSIOScan(params: SIOScanRequest): Promise<SIOBriefData>

// Single URL analysis
analyzeSIOUrl(request: AnalyzeUrlRequest): Promise<ArticleAnalysis>
```

---

## Common Tasks

### Start a Scan
```typescript
const sio = useStrategicIntelligence();

sio.startScan({
  topic: 'Federal Reserve',
  hours_back: 24,
  max_events: 30,
  credibility_threshold: 60
});

// Listen to progress
// sio.isScanning, sio.currentStage, sio.overallProgress updated in real-time
// When complete: sio.briefContent populated with markdown
```

### Cancel a Scan
```typescript
sio.cancelScan();
// Sets isScanning = false, displays "Scan cancelled" error
```

### Customize Agent Prompt
1. Open SIOTuneModal
2. Click agent tab (Discovery/Triage/Deep Analysis/Synthesis)
3. Edit prompt in textarea
4. Select model and temperature
5. Click "Save"

### Change Credibility Threshold
```typescript
// In component
<SIOTuneModal
  credibilityThreshold={60}
  onCredibilityThresholdChange={(value) => setCredibilityThreshold(value)}
/>

// Only articles from sources with MBFC score >= this are included
```

---

## Performance Metrics

### Expected Processing Times
- Discovery: 30-60 seconds (depends on query complexity)
- Triage: 10-30 seconds (depends on article count)
- Deep Analysis: 60-180 seconds (depends on event count)
- Synthesis: 20-60 seconds (depends on brief length)
- **Total**: 2-5 minutes for typical 24-hour scan

### Resource Efficiency
- Uses cheaper gpt-4.1-mini for discovery/triage
- Uses gpt-4o only for analysis/synthesis
- Controlled parallelism (5 concurrent deep analyses)
- Streaming response reduces time-to-first-word
- LocalStorage caching avoids re-runs

### Scalability
- Can handle 50-500 articles per scan
- Can analyze 5-100 events concurrently (configurable)
- Timeout protection prevents hanging
- Graceful degradation if agent fails

---

## Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| Scan hangs | Service timeout or network issue | Cancel and retry, check backend logs |
| No articles found | Query too specific or time window empty | Widen topic, extend hours_back |
| Low confidence scores | Credibility threshold too high | Lower threshold or change sources |
| Synthesis missing | Agent prompt failed | Check error log, verify prompt syntax |
| Slow analysis | Events too complex or models overloaded | Reduce max_events or change models |

---

## Files Summary

| Path | Purpose |
|------|---------|
| `/app/services/strategic_intelligence_service.py` | Main SIO orchestrator |
| `/app/routes/sio_routes.py` | API endpoints |
| `/ui/src/hooks/useStrategicIntelligence.ts` | Frontend state management |
| `/ui/src/components/IntelligenceBrief.tsx` | Main UI component |
| `/ui/src/components/SIOTuneModal.tsx` | Prompt editor |
| `/ui/src/services/api.ts` | API client layer |
| `/data/auspex/agents/sio_discovery_agent.md` | Discovery prompt |
| `/data/auspex/agents/sio_triage_agent.md` | Triage prompt |
| `/data/auspex/agents/sio_deep_analysis_agent.md` | Analysis prompt |
| `/data/auspex/agents/sio_synthesis_agent.md` | Synthesis prompt |

---

## Architecture for Template Use

To replicate SIO for a new narrative board:

1. **Define your stages** (e.g., Collection → Analysis → Synthesis)
2. **Create agent prompts** in `/data/auspex/agents/`
3. **Implement Service class** in `/app/services/` with async generator
4. **Add API routes** in `/app/routes/`
5. **Build React hook** with streaming SSE
6. **Create UI components** for display and tuning
7. **Define TypeScript types** for requests/responses

Example: `TrendConvergenceAnalysis` → `DecisionWindowAnalysis` → `NarrativeBoard` can all follow this pattern.
