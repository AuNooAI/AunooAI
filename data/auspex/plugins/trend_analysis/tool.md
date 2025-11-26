---
name: "trend_analysis"
version: "1.0.0"
type: "tool"
category: "analysis"
description: "Analyze trends and patterns in article coverage over time, identifying emerging themes, sentiment shifts, and coverage intensity changes"

parameters:
  - name: topic
    type: string
    required: true
    description: "Topic to analyze trends for"
  - name: time_period
    type: string
    required: false
    default: "30d"
    description: "Time period to analyze (7d, 14d, 30d, 90d, 365d)"
    enum: ["7d", "14d", "30d", "90d", "365d"]
  - name: focus_area
    type: string
    required: false
    description: "Specific area to focus on (e.g., 'sentiment', 'categories', 'sources', 'all')"
    default: "all"
    enum: ["sentiment", "categories", "sources", "signals", "all"]
  - name: include_chart
    type: boolean
    required: false
    default: true
    description: "Whether to include chart data in the response"

output:
  type: object
  properties:
    trends:
      type: array
      description: "List of identified trends"
    time_series:
      type: object
      description: "Time series data for charting"
    summary:
      type: string
      description: "Natural language summary of trends"
    chart_data:
      type: object
      description: "Plotly-compatible chart configuration"

triggers:
  - patterns: ["trend", "trending", "over time", "change.*over", "evolution of"]
    priority: high
  - patterns: ["how.*changed", "what.*happening", "pattern", "shift.*in"]
    priority: medium
  - patterns: ["coverage", "volume", "frequency"]
    priority: low
---

# Trend Analysis Tool

## Purpose
Analyze temporal patterns in article coverage to identify emerging trends, sentiment shifts, and changes in media focus over time.

## When to Use
- User asks about trends or patterns over time
- User wants to understand how coverage has changed
- User asks "what's been happening with X lately"
- User wants to see evolution of sentiment or topics

## Analysis Dimensions

### 1. Coverage Volume
- Article count over time
- Publishing frequency changes
- Spike detection (unusual activity)

### 2. Sentiment Evolution
- Sentiment distribution shifts
- Positive/negative trend lines
- Sentiment volatility

### 3. Category Focus
- Category distribution changes
- Emerging vs declining topics
- Category crossover patterns

### 4. Source Diversity
- Source concentration changes
- New sources entering coverage
- Source sentiment correlation

### 5. Future Signals
- Signal type distribution over time
- Leading indicators identification
- Signal clustering

## Output Format

Returns structured data with:
- `trends`: Array of identified trend objects with description, direction, confidence
- `time_series`: Daily/weekly aggregated data points
- `summary`: Human-readable trend summary
- `chart_data`: Plotly-compatible configuration for visualization
