---
name: "sio_triage"
version: "1.0.0"
type: "tool"
category: "analysis"
description: "Screen articles for credibility and cluster into events for strategic intelligence"

parameters:
  - name: articles
    type: array
    required: true
    description: "Articles to triage (from sio_discovery)"
  - name: credibility_threshold
    type: integer
    default: 60
    description: "Minimum credibility score (0-100)"
  - name: max_events
    type: integer
    default: 30
    description: "Maximum events to identify"

output:
  type: object
  properties:
    events:
      type: array
      description: "Identified event clusters"
    screened_count:
      type: integer
      description: "Articles passing credibility screen"
    rejected_count:
      type: integer
      description: "Articles failing credibility screen"
    event_categories:
      type: object
      description: "Events by category"

triggers:
  - patterns: ["triage.*articles", "cluster.*news", "screen.*credibility"]
    priority: medium
  - patterns: ["group.*events", "identify.*events"]
    priority: low
---

# SIO Triage Tool

## Purpose
Screen articles for minimum credibility and cluster related articles into distinct events for strategic analysis.

## Screening Process

1. **Credibility Check** - Filter articles below credibility threshold
2. **Source Validation** - Cross-reference with mediabias database
3. **Recency Filter** - Ensure articles are within time window

## Clustering Process

1. **Title Similarity** - Group articles with similar headlines
2. **Semantic Clustering** - Group by topic/content similarity
3. **Source Aggregation** - Track unique sources per cluster

## Event Ranking

Events are scored by:
- Source count (more sources = more significant)
- Average credibility of sources
- Recency of coverage
- Geographic diversity of sources

## Returns
- Event clusters with metadata
- Ranked by strategic importance
- Categorized by event type
