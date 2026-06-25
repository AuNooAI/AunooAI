---
name: "sio_discovery"
version: "1.0.0"
type: "tool"
category: "search"
description: "Comprehensive news discovery for strategic intelligence - gathers articles using multiple search strategies"

parameters:
  - name: topic
    type: string
    required: true
    description: "Topic to search for"
  - name: hours_back
    type: integer
    default: 24
    description: "Hours to look back (1-72)"
  - name: max_articles
    type: integer
    default: 200
    description: "Maximum articles to collect"

output:
  type: object
  properties:
    articles:
      type: array
      description: "Discovered articles with metadata"
    total_count:
      type: integer
      description: "Total articles found"
    sources:
      type: array
      description: "Unique sources found"
    search_strategies_used:
      type: array
      description: "Search strategies that returned results"

triggers:
  - patterns: ["discover.*news", "find.*articles", "gather.*intelligence"]
    priority: medium
  - patterns: ["comprehensive.*search", "news.*discovery"]
    priority: low
---

# SIO Discovery Tool

## Purpose
Perform comprehensive news discovery for strategic intelligence analysis using multiple search strategies to ensure broad coverage.

## Search Strategies

1. **Database Search** - Query internal article database by topic
2. **Vector Search** - Semantic similarity search using embeddings
3. **Alternative Queries** - Generated variations of the main topic

## Usage
This tool is typically used as the first stage of the SIO workflow but can also be called independently for comprehensive article gathering.

## Returns
- Full article metadata including title, summary, source, date
- Credibility scores where available
- Deduplication across search strategies
