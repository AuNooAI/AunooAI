---
name: "external_research"
version: "1.0.0"
type: "tool"
category: "research"
description: "Comprehensive external research combining web search with internal database analysis"

parameters:
  - name: query
    type: string
    required: true
    description: "Research query or topic to investigate"
  - name: topic
    type: string
    required: false
    description: "Topic context for the research"
  - name: limit
    type: integer
    default: 10
    description: "Maximum web results to return"
  - name: include_internal
    type: boolean
    default: true
    description: "Also search internal database for context"

triggers:
  - patterns: ["external research", "deep research", "comprehensive research"]
    priority: high
  - patterns: ["search.*web.*and", "combine.*internal.*external", "full research"]
    priority: high
  - patterns: ["what.*external.*sources", "outside.*perspective", "broader.*context"]
    priority: medium
  - patterns: ["compare.*internal.*external", "verify.*against.*web"]
    priority: medium

actions:
  - web_search
  - vector_search
  - db_search

prompt: |
  You are conducting comprehensive research that combines external web sources with internal database analysis.

  RESEARCH QUERY: {query}
  TOPIC CONTEXT: {topic}

  EXTERNAL WEB RESULTS:
  {web_search}

  INTERNAL DATABASE CONTEXT:
  {vector_search}

  Provide a comprehensive research synthesis in the following format:

  ## External Research: {query}

  ### External Sources Summary
  - Key findings from web search results
  - Notable sources and their credibility
  - Emerging trends or consensus from external sources

  ### Internal Database Context
  - Relevant articles from our monitored sources
  - How internal data aligns with or differs from external sources
  - Gaps in internal coverage

  ### Synthesis & Analysis
  - Combined insights from both internal and external sources
  - Areas of agreement and disagreement
  - Confidence level in findings

  ### Key Takeaways
  - Most important findings
  - Recommended follow-up research if needed

  Be thorough but concise. Prioritize actionable insights.

requires_api_key: GOOGLE_API_KEY
---

# External Research Tool

## Purpose
Conduct comprehensive research by combining Google Programmable Search Engine results with internal database analysis. This provides a fuller picture by comparing external web sources with your curated internal data.

## When to Use
- User wants comprehensive research on a topic
- User asks for external perspectives to compare with internal data
- User wants to verify internal findings against external sources
- User asks for "deep research" or "full analysis"
- User wants to identify gaps in internal coverage

## How It Works
1. Searches the web using Google PSE for external sources
2. Searches internal vector database for relevant articles
3. Combines and synthesizes findings from both sources
4. Identifies areas of agreement, disagreement, and coverage gaps

## Requirements
This tool requires:
- `GOOGLE_API_KEY`: Google Cloud API key with Custom Search API enabled
- `GOOGLE_CSE_ID`: Custom Search Engine ID

Configure these in Settings > Providers > Google Programmable Search.

## Rate Limits
Google Custom Search API has usage limits:
- Free tier: 100 queries/day
- Paid tier: $5 per 1000 queries

## Best Practices
- Use specific queries for better results
- Combine with topic context for more relevant internal matches
- Consider the credibility of external sources
- Use for verification and gap analysis
