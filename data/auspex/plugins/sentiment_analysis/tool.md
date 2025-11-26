---
name: "sentiment_analysis"
version: "1.0.0"
type: "tool"
category: "analysis"
description: "Analyze sentiment distribution and patterns in media coverage"

parameters:
  - name: topic
    type: string
    required: true
    description: "Topic to analyze sentiment for"
  - name: limit
    type: integer
    default: 100
    description: "Maximum articles to analyze"

triggers:
  - patterns: ["sentiment", "positive", "negative", "opinion"]
    priority: high
  - patterns: ["how.*feel", "perception", "attitude", "tone"]
    priority: medium
  - patterns: ["coverage.*positive", "coverage.*negative", "media.*reaction"]
    priority: medium

actions:
  - vector_search
  - db_search
  - sentiment_analysis

prompt: |
  You are a media sentiment analyst. Analyze the sentiment patterns in {article_count} articles about "{topic}".

  SENTIMENT DATA:
  {sentiment}

  SAMPLE ARTICLES:
  {articles}

  Provide your analysis in the following format:

  ## Sentiment Analysis: {topic}

  ### Overall Sentiment Distribution
  - Summarize the sentiment breakdown with percentages
  - Identify the dominant sentiment and what's driving it

  ### Sentiment by Source Type
  - Note if certain types of sources lean more positive/negative
  - Identify any outliers in sentiment

  ### Key Themes by Sentiment
  **Positive Coverage:**
  - What aspects are covered positively?
  - What's driving optimism?

  **Negative Coverage:**
  - What concerns are being raised?
  - What's driving criticism?

  **Neutral/Mixed:**
  - What balanced perspectives exist?
  - What nuanced positions are represented?

  ### Sentiment Drivers
  - Identify the main factors influencing overall sentiment
  - Note any recent events affecting sentiment

  ### Notable Quotes/Perspectives
  - Highlight representative viewpoints from different sentiment categories

  Be specific and reference actual article content where possible.
---

# Sentiment Analysis Tool

## Purpose
Analyze the sentiment distribution and patterns in media coverage of a topic.

## When to Use
- User asks about sentiment or opinions
- User wants to understand how topic is being covered
- User asks "how is X being perceived"
- User wants positive vs negative breakdown

## Analysis Approach
1. Search for articles about the topic
2. Aggregate sentiment labels from articles
3. Analyze patterns by source, time, and content
4. Identify drivers of positive/negative sentiment
