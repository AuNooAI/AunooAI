---
name: "web_search"
version: "1.0.0"
type: "tool"
category: "search"
description: "Search the web using Google Programmable Search Engine for external sources"

parameters:
  - name: query
    type: string
    required: true
    description: "Search query"
  - name: topic
    type: string
    required: false
    description: "Topic context for the search"
  - name: limit
    type: integer
    default: 10
    description: "Maximum results to return"

triggers:
  - patterns: ["search.*web", "google", "internet", "online"]
    priority: high
  - patterns: ["external.*source", "outside", "find.*online", "look.*up"]
    priority: medium
  - patterns: ["what.*say", "according.*to", "news.*about"]
    priority: low

actions:
  - web_search

prompt: |
  CRITICAL: All citations must include clickable markdown links: [Title](URL)
  Each web search result includes a link - USE IT in your citations!

  Based on the following web search results for "{query}", provide a summary of what external sources are saying.

  WEB SEARCH RESULTS:
  {web_search}

  Provide your analysis in the following format (cite with markdown links throughout):

  ## Web Search Results: {query}

  ### Key Findings
  - Summarize the main points from the search results
  - Note any consensus or disagreement among sources

  ### Source Overview
  - List the main sources found and their perspectives
  - Note source credibility where apparent

  ### Relevant Links
  - Highlight the most relevant/useful links found

  Be concise and focus on the most relevant information. Format all links as: [Title](URL).

requires_api_key: GOOGLE_API_KEY
---

# Web Search Tool

## Purpose
Search the web using Google Programmable Search Engine to find external sources and information not in the internal database.

## When to Use
- User explicitly asks to search the web/Google
- User wants external sources or perspectives
- User asks "what are people saying about X"
- Information may not be in the internal database

## Requirements
This tool requires the following environment variables:
- `GOOGLE_API_KEY` or `GOOGLE_SEARCH_API_KEY`: Google API key
- `GOOGLE_CSE_ID` or `GOOGLE_SEARCH_ENGINE_ID`: Custom Search Engine ID

If these are not configured, the tool will not be available.

## Rate Limits
Google Custom Search API has usage limits:
- Free tier: 100 queries/day
- Paid tier: $5 per 1000 queries
