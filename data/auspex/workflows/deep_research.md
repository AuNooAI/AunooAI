---
name: "deep_research_workflow"
version: "1.0.0"
type: "workflow"
description: "Multi-step autonomous research with planning, searching, synthesis, and reporting"

stages:
  - name: planning
    agent: research_planner
    timeout: 30
    outputs:
      - research_objectives
      - search_queries
      - report_outline

  - name: searching
    agent: research_searcher
    timeout: 120
    parallel: true
    max_iterations: 5
    inputs:
      - search_queries
    tools:
      - enhanced_database_search
      - search_news
    outputs:
      - raw_results
      - source_metadata

  - name: synthesis
    agent: research_synthesizer
    timeout: 60
    inputs:
      - raw_results
      - research_objectives
    outputs:
      - synthesized_findings
      - credibility_assessment

  - name: writing
    agent: report_writer
    timeout: 90
    inputs:
      - synthesized_findings
      - report_outline
    outputs:
      - final_report

config:
  max_total_tokens: 100000
  credibility_threshold: 40
  source_diversity_min: 5
  allow_external_search: true
  total_timeout: 300

sampling:
  strategy: "balanced"
  articles_per_query: 20
  max_total_articles: 100
  recency_weight: 0.3
  diversity:
    category_diversity: true
    category_min_percentage: 10
    sentiment_diversity: true
    sentiment_distribution:
      positive: 30
      neutral: 40
      negative: 20
      mixed: 10
    source_diversity: true
    max_per_source: 5

filtering:
  min_credibility: 40
  date_range:
    enabled: true
    days_back: 30
    allow_override: true
  content_quality:
    min_summary_length: 50
    require_url: true
    exclude_duplicates: true
    duplicate_threshold: 0.85
  relevance:
    enabled: true
    min_score: 0.5
    use_semantic: true
    use_keyword: true
  source_blacklist: []
  source_whitelist: []

model_config:
  preset: "balanced"
  stages:
    planning:
      model: "gpt-4.1-mini"
      temperature: 0.3
      max_tokens: 2000
      top_p: 0.9
    searching:
      model: "gpt-4.1-mini"
      temperature: 0.2
      max_tokens: 2000
    synthesis:
      model: "gpt-4o"
      temperature: 0.4
      max_tokens: 4000
      top_p: 0.95
    writing:
      model: "gpt-4o"
      temperature: 0.5
      max_tokens: 8000
      top_p: 0.95
  presets:
    precise:
      temperature: 0.1
      top_p: 0.8
      frequency_penalty: 0.0
      presence_penalty: 0.0
      description: "High fidelity, factual output. Best for legal, financial, medical research."
    balanced:
      temperature: 0.4
      top_p: 0.9
      frequency_penalty: 0.1
      presence_penalty: 0.1
      description: "Good balance of accuracy and readability. Default for most research."
    creative:
      temperature: 0.7
      top_p: 0.95
      frequency_penalty: 0.3
      presence_penalty: 0.3
      description: "Exploratory, generates novel insights. Good for brainstorming, trends."
    analytical:
      temperature: 0.3
      top_p: 0.85
      frequency_penalty: 0.2
      presence_penalty: 0.1
      description: "Data-focused, systematic analysis. Good for quantitative research."
---

# Deep Research Workflow

## Overview
A four-stage autonomous research workflow that produces comprehensive, well-cited research reports on complex topics.

## Stage Details

### Stage 1: Planning (30s timeout)
**Agent:** research_planner
**Goal:** Develop a structured research plan

The planner:
1. Analyzes the user's research question
2. Identifies 3-5 specific research objectives
3. Creates targeted search queries for each objective
4. Designs report outline structure

**Quality Criteria:**
- Each objective is measurable and specific
- Queries cover different aspects of the topic
- Outline structure matches objectives

### Stage 2: Searching (120s timeout)
**Agent:** research_searcher
**Goal:** Gather diverse, high-quality sources

The searcher:
1. Executes search queries in parallel
2. Dynamically adapts strategy based on initial findings
3. Scores source credibility using mediabias data
4. Ensures source diversity (categories, sentiments, outlets)

**Quality Criteria:**
- Minimum 5 unique news sources
- Average credibility score >= 60
- Coverage of all research objectives

### Stage 3: Synthesis (60s timeout)
**Agent:** research_synthesizer
**Goal:** Analyze and synthesize findings

The synthesizer:
1. Filters low-credibility sources (below threshold)
2. Identifies patterns and themes across sources
3. Resolves contradictions using credibility hierarchy
4. Assesses overall confidence in findings

**Quality Criteria:**
- Key claims supported by multiple sources
- Contradictions explicitly noted
- Confidence levels assigned to findings

### Stage 4: Writing (90s timeout)
**Agent:** report_writer
**Goal:** Produce professional research report

The writer:
1. Follows the report outline from planning
2. Includes inline citations [Source Name]
3. Maintains consistent professional tone
4. Validates section completeness

**Quality Criteria:**
- All claims have citations
- Each section >= 500 characters
- Limitations section included
- References list complete

## Error Handling

| Error Type | Handling Strategy |
|------------|-------------------|
| Stage timeout | Return partial results with warning |
| Low source diversity | Expand search queries, retry |
| Contradictory findings | Note in report, show both sides |
| Synthesis failure | Fall back to structured summary |
| Writing failure | Return synthesis with basic formatting |

## Output Format
Final output is a Markdown report with:
- Executive Summary
- Methodology
- Findings (by objective)
- Analysis & Patterns
- Conclusions
- Limitations
- References
