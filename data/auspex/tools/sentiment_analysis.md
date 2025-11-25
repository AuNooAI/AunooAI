---
name: "analyze_sentiment_trends"
version: "1.0.0"
type: "tool"
category: "analysis"
description: "Analyze sentiment distribution and trends over time for a topic"

parameters:
  - name: topic
    type: string
    required: true
    description: "Topic to analyze"
  - name: time_period
    type: string
    default: "month"
    enum: ["week", "month", "quarter", "year"]
    description: "Time period for trend analysis"
  - name: include_chart
    type: boolean
    default: true
    description: "Whether to generate a chart"

output:
  type: object
  properties:
    sentiment_distribution:
      type: object
      description: "Count of articles per sentiment category"
    sentiment_percentages:
      type: object
      description: "Percentage breakdown by sentiment"
    trend_data:
      type: array
      description: "Time series sentiment data"
    chart_data:
      type: object
      description: "Plotly chart configuration (if include_chart=true)"

triggers:
  - patterns: ["sentiment", "how.*feel", "opinion.*trend", "positive.*negative"]
    priority: high
  - patterns: ["mood", "perception", "attitude", "tone"]
    priority: medium
  - patterns: ["coverage.*positive", "coverage.*negative", "media.*reaction"]
    priority: medium
---

# Sentiment Analysis Tool

## Purpose
Analyze the sentiment distribution of articles within a topic over a specified time period.

## When to Use
- User asks about sentiment or opinion trends
- User wants to compare positive vs negative coverage
- User asks how media is covering a topic
- User wants to identify sentiment shifts over time

## Execution Steps

1. **Retrieve Articles**
   - Filter by topic and date range
   - Include all sentiment-tagged articles
   - Apply time period grouping

2. **Calculate Distribution**
   - Count articles per sentiment category (Positive, Neutral, Critical, Negative, Mixed)
   - Calculate percentage breakdown
   - Identify dominant sentiment

3. **Identify Trends**
   - Group by time period (daily for week, weekly for month, etc.)
   - Calculate rolling averages if applicable
   - Identify significant shifts

4. **Generate Chart** (if requested)
   - Create sentiment donut chart for distribution
   - Create timeline chart for trends
   - Return Plotly JSON configuration

## Output Interpretation

| Sentiment | Typical Range | Interpretation |
|-----------|---------------|----------------|
| Positive | 20-40% | Normal optimism |
| Neutral | 30-50% | Balanced coverage |
| Critical | 15-25% | Healthy skepticism |
| Negative | 5-15% | Concerning if higher |
| Mixed | 5-15% | Nuanced coverage |

## Chart Recommendation
When sentiment analysis is performed, generate:
- `sentiment_donut` for distribution overview
- `sentiment_timeline` for trends over time
