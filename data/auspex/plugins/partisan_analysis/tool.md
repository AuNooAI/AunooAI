---
name: "partisan_analysis"
version: "1.0.0"
type: "tool"
category: "analysis"
description: "Analyze political bias and partisan framing in media coverage"

parameters:
  - name: topic
    type: string
    required: true
    description: "Topic to analyze for political bias"
  - name: limit
    type: integer
    default: 100
    description: "Maximum articles to analyze"

triggers:
  - patterns: ["bias", "partisan", "political", "left.*right"]
    priority: high
  - patterns: ["liberal", "conservative", "slant", "leaning"]
    priority: high
  - patterns: ["objectiv", "balanced", "fair", "one-sided"]
    priority: medium

actions:
  - vector_search
  - db_search
  - bias_analysis

prompt: |
  You are a media bias analyst. Analyze the political/partisan distribution in {article_count} articles about "{topic}".

  BIAS DATA:
  {bias}

  SAMPLE ARTICLES:
  {articles}

  Provide your analysis in the following format:

  ## Partisan Analysis: {topic}

  ### Source Bias Distribution
  - Breakdown of sources by political leaning (Left, Center-Left, Center, Center-Right, Right)
  - Percentage from each bias category
  - Note if coverage is balanced or skewed

  ### Framing Differences by Political Leaning

  **Left-Leaning Sources:**
  - How do they frame this topic?
  - What aspects do they emphasize?
  - What language/terminology do they use?

  **Center Sources:**
  - How do they frame this topic?
  - What balanced perspectives do they offer?

  **Right-Leaning Sources:**
  - How do they frame this topic?
  - What aspects do they emphasize?
  - What language/terminology do they use?

  ### Key Narrative Differences
  - Identify major points where left/right coverage diverges
  - Note any consensus across political spectrum
  - Highlight misleading or one-sided framings

  ### Factual vs Opinion Content
  - Assess ratio of factual reporting to opinion pieces
  - Note which claims are disputed vs accepted

  ### Recommendations for Balanced Understanding
  - What sources provide most balanced coverage?
  - What perspectives are underrepresented?
  - What questions remain contested?

  Be objective in your analysis. Identify bias without exhibiting bias.
---

# Partisan/Political Bias Analysis Tool

## Purpose
Analyze the political bias distribution and partisan framing differences in media coverage.

## When to Use
- User asks about media bias on a topic
- User wants to understand political framing differences
- User asks "how do left/right cover X"
- User wants balanced source recommendations

## Analysis Approach
1. Search for articles from diverse sources
2. Categorize sources by known political bias ratings
3. Compare framing, language, and emphasis across spectrum
4. Identify consensus and divergence points
