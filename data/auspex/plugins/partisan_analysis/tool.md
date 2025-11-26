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
  CRITICAL: All citations must include clickable markdown links: [Article Title](URL)
  Every article in SAMPLE ARTICLES has a URL field - USE IT in your citations throughout!

  You are a media bias analyst. Analyze the political/partisan distribution in {article_count} articles about "{topic}".

  BIAS DATA:
  {bias}

  SAMPLE ARTICLES:
  {articles}

  Provide your analysis in the following format (cite with markdown links throughout):

  ## Partisan Analysis: {topic}

  ### Source Bias Distribution Table

  | Bias Category | Count | % | Example Sources |
  |---------------|-------|---|-----------------|
  | Left | X | X% | Source1, Source2 |
  | Center-Left | X | X% | Source1, Source2 |
  | Center | X | X% | Source1, Source2 |
  | Center-Right | X | X% | Source1, Source2 |
  | Right | X | X% | Source1, Source2 |

  **Coverage Balance:** [Balanced/Left-Skewed/Right-Skewed] - brief explanation

  ### Comparative Framing Table

  | Aspect | Left-Leaning View | Center View | Right-Leaning View |
  |--------|-------------------|-------------|-------------------|
  | Main Narrative | [summary] | [summary] | [summary] |
  | Key Concerns | [concerns] | [concerns] | [concerns] |
  | Proposed Solutions | [solutions] | [solutions] | [solutions] |
  | Tone | [tone] | [tone] | [tone] |

  ### Detailed Framing Analysis

  **Left-Leaning Sources:**
  - Key narrative and framing - cite: [Article Title](URL)
  - Language and terminology used
  - What they emphasize/de-emphasize

  **Center Sources:**
  - Balanced perspectives offered - cite: [Article Title](URL)
  - How they present multiple viewpoints

  **Right-Leaning Sources:**
  - Key narrative and framing - cite: [Article Title](URL)
  - Language and terminology used
  - What they emphasize/de-emphasize

  ### Key Divergence Points
  - Where left/right coverage diverges most sharply
  - Any consensus across the political spectrum
  - Potentially misleading or one-sided framings

  ### Sample Articles by Political Leaning

  Present 3-4 representative articles from each political perspective:

  | Right Wing | Center | Left Wing |
  |------------|--------|-----------|
  | **[Article Title](URL)** (Source) - Brief 1-line summary of their take | **[Article Title](URL)** (Source) - Brief 1-line summary | **[Article Title](URL)** (Source) - Brief 1-line summary of their take |
  | **[Article Title](URL)** (Source) - Brief summary | **[Article Title](URL)** (Source) - Brief summary | **[Article Title](URL)** (Source) - Brief summary |
  | **[Article Title](URL)** (Source) - Brief summary | **[Article Title](URL)** (Source) - Brief summary | **[Article Title](URL)** (Source) - Brief summary |

  ### Recommendations
  - Most balanced sources for this topic
  - Underrepresented perspectives
  - Contested claims requiring further research

  Be objective. Identify bias without exhibiting bias. Every claim needs a source citation with markdown link.
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
