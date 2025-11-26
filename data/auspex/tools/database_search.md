---
name: "enhanced_database_search"
version: "1.0.0"
type: "tool"
category: "search"
description: "Search the internal article database using hybrid vector/SQL search with intelligent query parsing"

parameters:
  - name: query
    type: string
    required: true
    description: "The search query or question"
  - name: topic
    type: string
    required: true
    description: "Topic to search within"
  - name: limit
    type: integer
    default: 50
    description: "Maximum number of articles to return"
  - name: filters
    type: object
    required: false
    description: "Optional filters (category, sentiment, date_range, news_source)"

output:
  type: object
  properties:
    articles:
      type: array
      description: "List of matching articles"
    total_count:
      type: integer
      description: "Total number of matches"
    search_method:
      type: string
      description: "Search method used (vector, sql, hybrid)"

triggers:
  - patterns: ["search.*database", "find.*articles", "look.*up", "from.*database"]
    priority: high
  - patterns: ["articles about", "news about", "coverage of", "what.*written"]
    priority: medium
  - patterns: ["search", "find", "look for"]
    priority: low
---

# Enhanced Database Search Tool

## Purpose
Search the internal article database using a hybrid approach combining vector similarity search and SQL filtering for optimal results.

## When to Use
- User asks about articles in the database
- User wants to find coverage on a specific topic
- User asks "what have we written about X"
- User requests article search with specific criteria

## Execution Steps

1. **Parse Query Intent**
   - Identify key entities and concepts
   - Determine if filters are needed (category, sentiment, date)
   - Extract any temporal references ("last week", "recent")

2. **Execute Hybrid Search**
   - Vector search: Semantic similarity to query
   - SQL search: Filter by topic, category, date range
   - Combine and deduplicate results

3. **Apply Diversity Selection**
   - Ensure category representation
   - Prevent single-source dominance
   - Balance recency vs relevance

4. **Return Results**
   - Include article metadata (title, summary, source, date)
   - Include relevance/similarity scores
   - Provide search method used

## Output Format
Returns structured JSON with articles array and metadata about the search.
