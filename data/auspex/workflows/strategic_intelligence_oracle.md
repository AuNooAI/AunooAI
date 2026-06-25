---
name: "strategic_intelligence_oracle"
version: "1.0.0"
type: "workflow"
description: "BBC/Wiley-compliant strategic intelligence workflow for 24-hour news analysis"

stages:
  - name: discovery
    agent: sio_discovery_agent
    timeout: 120
    description: "Cast wide net - gather 300-500 articles from past 24 hours"
    outputs:
      - raw_articles
      - source_metadata
      - collection_stats

  - name: triage
    agent: sio_triage_agent
    timeout: 60
    description: "Quick filtering - credibility screen and event clustering"
    inputs:
      - raw_articles
    outputs:
      - screened_articles
      - event_clusters
      - cluster_rankings

  - name: deep_analysis
    agent: sio_deep_analysis_agent
    timeout: 300
    parallel: true
    max_concurrent: 5
    description: "Deep dive on top events using full article analysis"
    inputs:
      - event_clusters
      - cluster_rankings
    outputs:
      - event_analyses
      - verification_results
      - cross_references

  - name: synthesis
    agent: sio_synthesis_agent
    timeout: 120
    description: "Compile intelligence brief with quality gates"
    inputs:
      - event_analyses
      - verification_results
    outputs:
      - intelligence_brief
      - audit_trail

config:
  # Time window
  hours_back: 24

  # Article limits
  max_discovery_articles: 500
  min_discovery_articles: 100
  max_events_to_analyze: 30
  min_articles_per_cluster: 2

  # Quality thresholds (BBC/Wiley standards)
  credibility_threshold: 60
  min_factual_reporting: "Mostly Factual"
  min_cross_references: 2
  confidence_threshold: 0.7

  # Source diversity requirements
  min_unique_sources: 3
  max_single_source_percentage: 40
  require_geographic_diversity: true

  # Quality gates
  quality_gates:
    accuracy:
      enabled: true
      threshold: 0.95
      require_cross_verification: true
    context:
      enabled: true
      require_multiple_perspectives: true
      min_viewpoints: 2
    sourcing:
      enabled: true
      min_primary_sources: 1
      require_attribution: true
    foresight:
      enabled: true
      require_uncertainty_quantification: true
    ai_compliance:
      enabled: true
      require_disclosure: true
      require_human_review_flag: true

  # Total timeout
  total_timeout: 600

sampling:
  strategy: "comprehensive"
  articles_per_query: 50
  max_queries: 10
  recency_weight: 0.8
  diversity:
    category_diversity: true
    geographic_diversity: true
    source_diversity: true
    max_per_source: 10
    sentiment_balance: true

filtering:
  min_credibility: 60
  factual_reporting_whitelist:
    - "Very High"
    - "High"
    - "Mostly Factual"
  date_range:
    enabled: true
    hours_back: 24
    strict: true
  content_quality:
    min_content_length: 200
    require_url: true
    exclude_duplicates: true
    duplicate_threshold: 0.85
  source_blacklist: []

clustering:
  algorithm: "semantic"
  similarity_threshold: 0.75
  min_cluster_size: 2
  max_clusters: 50
  merge_threshold: 0.85

impact_scoring:
  dimensions:
    urgency:
      weight: 0.25
      factors:
        - recency
        - breaking_signals
        - time_sensitivity
    scale:
      weight: 0.25
      factors:
        - geographic_scope
        - affected_population
        - article_count
    consequence:
      weight: 0.30
      factors:
        - economic_impact
        - political_impact
        - social_impact
    credibility:
      weight: 0.20
      factors:
        - source_quality
        - cross_verification
        - factual_consistency

model_config:
  stages:
    discovery:
      model: "gpt-4.1-mini"
      temperature: 0.2
      max_tokens: 2000
    triage:
      model: "gpt-4.1-mini"
      temperature: 0.2
      max_tokens: 4000
    deep_analysis:
      model: "gpt-4o"
      temperature: 0.3
      max_tokens: 4000
    synthesis:
      model: "gpt-4o"
      temperature: 0.4
      max_tokens: 8000

output_format:
  type: "intelligence_brief"
  sections:
    - executive_summary
    - critical_events
    - emerging_signals
    - source_analysis
    - confidence_assessment
    - methodology
    - audit_trail
---

# Strategic Intelligence Oracle Workflow

## Overview

A four-phase workflow that produces BBC/Wiley-compliant strategic intelligence briefs by analyzing the past 24 hours of news coverage. Designed to sift through hundreds of articles, identify critical events, verify claims, and produce actionable intelligence.

## Phase Details

### Phase 1: Discovery (120s timeout)
**Agent:** sio_discovery_agent
**Goal:** Cast wide net to gather comprehensive news coverage

The discovery phase:
1. Executes multiple search queries in parallel
2. Gathers from internal database AND external APIs
3. Targets 300-500 articles from past 24 hours
4. Tracks source diversity and coverage gaps
5. Preserves full metadata for downstream filtering

**Quality Criteria:**
- Minimum 100 articles collected
- At least 10 unique news sources
- Coverage across multiple categories/topics

### Phase 2: Triage (60s timeout)
**Agent:** sio_triage_agent
**Goal:** Quick filtering and event identification

The triage phase:
1. Applies credibility screen (min score 60)
2. Filters by factual reporting quality
3. Clusters articles by semantic similarity
4. Identifies discrete "events" or "stories"
5. Ranks clusters by article count and source diversity
6. Selects top 30 events for deep analysis

**Quality Criteria:**
- All sources meet credibility threshold
- Events have minimum 2 articles
- Source diversity within each cluster

### Phase 3: Deep Analysis (300s timeout, parallel)
**Agent:** sio_deep_analysis_agent
**Goal:** Thorough analysis of each critical event

For each top event:
1. Fetch full content of representative article(s)
2. Cross-reference claims against cluster articles
3. Identify contradictions and verify facts
4. Assess strategic importance and impact
5. Calculate confidence levels
6. Apply quality gates (accuracy, context, sourcing)

**Quality Criteria:**
- Claims verified by 2+ sources
- Contradictions documented
- Confidence levels assigned
- Impact assessed on standard dimensions

### Phase 4: Synthesis (120s timeout)
**Agent:** sio_synthesis_agent
**Goal:** Produce final intelligence brief

The synthesis phase:
1. Compiles all event analyses
2. Ranks by strategic importance
3. Identifies cross-event connections
4. Generates executive summary
5. Creates audit trail for AI usage
6. Applies final quality gates

**Quality Criteria:**
- All critical events included
- Executive summary captures key insights
- Sources properly attributed
- Uncertainty quantified
- Audit trail complete

## Quality Gates (BBC/Wiley Standards)

### Gate 1: Accuracy Validation
- All factual claims cross-verified
- Quotes matched to sources
- Dates and entities verified
- Confidence scores assigned

### Gate 2: Context & Impartiality
- Multiple perspectives included
- Facts separated from opinion
- Appropriate detail level
- No material omissions

### Gate 3: Source Verification
- All sources accessible and verified
- Credibility scores meet threshold
- Source diversity requirements met
- Partisan affiliations disclosed

### Gate 4: Foresight Validation
- Forecasts include uncertainty ranges
- Assumptions documented
- Alternative scenarios noted
- Time horizons specified

### Gate 5: AI Compliance
- AI usage disclosed
- Human review flagged where needed
- Audit trail maintained
- Rights protected

## Error Handling

| Error Type | Handling Strategy |
|------------|-------------------|
| Discovery timeout | Return partial results, note coverage gaps |
| Low article count | Expand search queries, extend time window |
| Clustering failure | Fall back to category-based grouping |
| Deep analysis timeout | Skip event, note in report |
| Verification failure | Flag as unverified, lower confidence |
| Synthesis failure | Return structured event list |

## Output Format

Final output is a structured intelligence brief with:
- Executive Summary (top 5 critical items)
- Critical Events (ranked by importance)
- Emerging Signals (weak signals worth monitoring)
- Source Analysis (credibility and diversity)
- Confidence Assessment (per-event and overall)
- Methodology (transparent process documentation)
- Audit Trail (AI usage, human oversight needs)
