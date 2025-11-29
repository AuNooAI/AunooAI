---
name: "strategic_intelligence_oracle"
version: "1.0.0"
type: "tool"
category: "analysis"
description: "Generate a BBC/Wiley-quality 24-hour strategic intelligence brief with comprehensive news discovery, credibility verification, event clustering, and actionable intelligence synthesis."

parameters:
  - name: topic
    type: string
    required: false
    description: "Topic focus for intelligence gathering (uses org profile topic if not specified)"
  - name: hours_back
    type: integer
    required: false
    default: 24
    description: "Hours to look back for news (1-72)"
  - name: max_events
    type: integer
    required: false
    default: 30
    description: "Maximum events to analyze in depth (10-50)"
  - name: credibility_threshold
    type: integer
    required: false
    default: 60
    description: "Minimum source credibility score (0-100)"
  - name: deep_analysis_count
    type: integer
    required: false
    default: 10
    description: "Number of top events to deep analyze (5-20)"

output:
  type: object
  properties:
    brief:
      type: string
      description: "Complete intelligence brief in markdown format"
    metadata:
      type: object
      description: "Processing statistics and audit trail"
    events:
      type: array
      description: "Analyzed event clusters with confidence scores"

triggers:
  - patterns: ["intelligence brief", "strategic intelligence", "sio scan", "24 hour scan"]
    priority: high
  - patterns: ["news intelligence", "intelligence oracle", "daily brief", "morning brief"]
    priority: high
  - patterns: ["comprehensive scan", "news scan", "full scan", "deep scan"]
    priority: medium
  - patterns: ["what happened", "critical developments", "important news"]
    priority: low

quality_gates:
  - name: "source_diversity"
    threshold: 3
    description: "Minimum unique sources per event"
  - name: "credibility_minimum"
    threshold: 60
    description: "Minimum average credibility score"
  - name: "temporal_freshness"
    threshold: 24
    description: "Maximum age in hours for lead articles"
  - name: "geographic_diversity"
    threshold: 2
    description: "Minimum regions represented"
  - name: "contradiction_check"
    threshold: true
    description: "Flag contradicting claims between sources"

workflow:
  stages:
    - name: discovery
      description: "Gather articles from past 24 hours using multiple search strategies"
      weight: 0.2
    - name: triage
      description: "Screen for credibility and cluster into events"
      weight: 0.15
    - name: deep_analysis
      description: "Analyze top events with cross-verification"
      weight: 0.45
    - name: synthesis
      description: "Generate intelligence brief with audit trail"
      weight: 0.2
---

# Strategic Intelligence Oracle (SIO)

## Purpose

Generate a comprehensive 24-hour strategic intelligence brief that meets BBC/Wiley editorial standards. Unlike simple news summaries, SIO performs multi-stage analysis including:

1. **Discovery**: Comprehensive news gathering across multiple sources
2. **Triage**: Credibility screening and event clustering
3. **Deep Analysis**: Fact verification and cross-referencing
4. **Synthesis**: Coherent brief with confidence assessments

## Key Features

### BBC/Wiley Quality Standards
- **Verification**: All factual claims cross-referenced against multiple credible sources
- **Attribution**: Every claim cites its source with credibility assessment
- **Balance**: Multiple perspectives presented where they exist
- **Transparency**: Clear distinction between facts, analysis, and speculation
- **Confidence Levels**: Explicit ratings on all assessments

### Multi-Stage Processing

#### Stage 1: Discovery (20% of processing)
- Generate search queries for comprehensive coverage
- Fetch articles from multiple APIs (TheNewsAPI, NewsAPI, database)
- Target: 200+ articles for thorough analysis
- Apply temporal filtering (configurable hours_back)

#### Stage 2: Triage (15% of processing)
- Screen articles for minimum credibility threshold
- Apply semantic clustering to group related articles into events
- Calculate event importance based on:
  - Number of sources covering event
  - Average source credibility
  - Recency of coverage
  - Geographic spread

#### Stage 3: Deep Analysis (45% of processing)
- Analyze top N events based on importance ranking
- For each event:
  - Extract key claims
  - Cross-reference between sources
  - Identify contradictions
  - Calculate confidence scores
  - Assess strategic implications

#### Stage 4: Synthesis (20% of processing)
- Generate executive summary (top 5 critical items)
- Structure critical events with confidence indicators
- Identify emerging signals worth monitoring
- Create audit trail with AI disclosure

## Organizational Profile Integration

When an organizational profile is set:
- Events are ranked by relevance to organization's industry
- Strategic implications tailored to organization type
- Risk assessments aligned with risk tolerance
- Recommendations appropriate to organization's capabilities

## Output Structure

### Executive Summary
- Top 5 critical items with importance markers
- Overall landscape assessment
- Key uncertainties and watch items

### Critical Events
For each high-importance event:
- Headline and summary
- Key facts with confidence indicators
- Strategic implications
- Source citations with credibility
- Confidence explanation

### Emerging Signals
- Weak signals worth monitoring
- Developing stories
- Potential future developments

### Confidence Assessment
- Overall brief confidence
- Per-event breakdown
- Verification gaps

### Audit Trail
- Processing statistics
- AI models used
- Human review requirements
- Disclosure statement

## Confidence Indicators

| Level | Score Range | Meaning |
|-------|-------------|---------|
| HIGH | 0.85+ | Verified by multiple credible sources |
| MEDIUM | 0.70-0.84 | Partially verified, some uncertainty |
| LOW | <0.70 | Unverified or conflicting reports |

## Importance Markers

| Marker | Level | Description |
|--------|-------|-------------|
| CRITICAL | Red | Immediate strategic impact |
| HIGH | Orange | Significant development |
| MEDIUM | Yellow | Noteworthy |
| MONITORING | White | Emerging signal |

## Example Triggers

- "Generate an intelligence brief for AI governance"
- "SIO scan for the past 24 hours"
- "What critical developments happened in tech today?"
- "Strategic intelligence on climate policy"
- "Morning brief on cybersecurity"

## Quality Gates

The SIO applies five quality gates before generating output:

1. **Source Diversity**: Minimum 3 unique sources per critical event
2. **Credibility Minimum**: Average credibility score >= 60
3. **Temporal Freshness**: Lead articles within 24 hours
4. **Geographic Diversity**: Minimum 2 regions represented
5. **Contradiction Check**: All contradicting claims flagged

Events failing quality gates are downgraded or flagged for human review.

## Technical Notes

- Uses custom handler.py for multi-step processing
- SSE streaming provides real-time progress updates
- Results cached in database for audit purposes
- Integrates with mediabias table for source credibility
