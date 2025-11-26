---
name: "future_impact"
version: "1.0.0"
type: "tool"
category: "analysis"
description: "Analyze articles to predict future impacts, emerging opportunities, and potential risks"

parameters:
  - name: topic
    type: string
    required: true
    description: "Topic to analyze for future impacts"
  - name: limit
    type: integer
    default: 50
    description: "Maximum articles to analyze"

triggers:
  - patterns: ["future", "impact", "prediction", "forecast", "outlook"]
    priority: high
  - patterns: ["what.*happen", "expect", "anticipate", "upcoming"]
    priority: medium
  - patterns: ["risk", "opportunity", "potential", "emerging"]
    priority: medium

actions:
  - vector_search
  - db_search

prompt: |
  CRITICAL: All citations must include clickable markdown links: [Article Title](URL)
  Every article in ARTICLES has a URL field - USE IT in your citations!

  You are an expert futures analyst. Based on the following {article_count} articles about "{topic}", provide a comprehensive future impact analysis.

  ARTICLES:
  {articles}

  Provide your analysis in the following format (cite with markdown links throughout):

  ## Future Impact Analysis: {topic}

  ### Key Predictions (Next 6-12 months)
  - List 3-5 specific predictions based on current trends
  - Include confidence level (High/Medium/Low) for each

  ### Emerging Opportunities
  - Identify potential opportunities arising from current developments
  - Note which sectors or groups might benefit

  ### Potential Risks & Challenges
  - Identify risks and challenges that may emerge
  - Note mitigation strategies if apparent from coverage

  ### Signals to Watch
  - List early indicators that would confirm or contradict predictions
  - Identify what to monitor going forward

  ### Confidence Assessment
  - Overall confidence in predictions based on data quality and consensus
  - Note any significant uncertainties or conflicting signals

  Be specific and cite patterns from the articles using markdown links: [Title](URL). Avoid generic predictions.
---

# Future Impact Analysis Tool

## Purpose
Analyze current coverage to identify and predict future impacts, opportunities, and risks related to a topic.

## When to Use
- User asks about future outlook or predictions
- User wants to understand potential impacts
- User asks "what will happen with X"
- User wants risk/opportunity assessment

## Analysis Approach
1. Search for articles with forward-looking content
2. Identify signals and predictions already in coverage
3. Synthesize patterns into actionable predictions
4. Assess confidence based on source consensus
