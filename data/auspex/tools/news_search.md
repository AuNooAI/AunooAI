---
name: "search_news"
version: "1.0.0"
type: "tool"
category: "search"
description: "Search external news APIs for recent articles not in the database"

parameters:
  - name: query
    type: string
    required: true
    description: "Search query"
  - name: max_results
    type: integer
    default: 20
    description: "Maximum number of results"
  - name: days_back
    type: integer
    default: 7
    description: "How many days back to search"
  - name: categories
    type: array
    required: false
    description: "Filter by categories (business, technology, etc.)"
  - name: language
    type: string
    default: "en"
    description: "Language filter"

output:
  type: object
  properties:
    articles:
      type: array
      description: "List of news articles"
    total_results:
      type: integer
      description: "Total results found"
    api_source:
      type: string
      description: "News API used"

triggers:
  - patterns: ["search.*web", "latest.*news", "breaking", "happening.*now"]
    priority: high
  - patterns: ["external.*sources", "online.*news", "news.*api", "google.*for"]
    priority: high
  - patterns: ["recent.*news", "today's.*news", "current.*events"]
    priority: medium
---

# External News Search Tool

## Purpose
Search external news APIs (TheNewsAPI, NewsAPI) for recent articles that may not be in the internal database.

## When to Use
- User asks about very recent events ("today", "just now", "breaking")
- User explicitly requests external search
- User asks about topics not well covered in database
- Real-time news is needed

## Execution Steps

1. **Prepare Query**
   - Sanitize and optimize query for news API
   - Set date range based on days_back parameter
   - Apply category filters if specified

2. **Execute Search**
   - Call TheNewsAPI (primary)
   - Fall back to NewsAPI if needed
   - Apply rate limiting as needed

3. **Process Results**
   - Normalize article format
   - Extract key metadata (title, summary, source, date, URL)
   - Calculate basic credibility score from source reputation

4. **Return Results**
   - Structured article list
   - API source attribution
   - Total results count

## Credibility Scoring
External articles receive credibility scores based on:
- Source reputation (known reliable sources score higher)
- Article completeness (has summary, date, author)
- Source diversity in results

## Rate Limits
- TheNewsAPI: 100 requests/day (free tier)
- NewsAPI: 100 requests/day (free tier)
- Cache results for 15 minutes to reduce API calls
