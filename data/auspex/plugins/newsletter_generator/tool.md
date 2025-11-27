---
name: "newsletter_generator"
version: "2.0.0"
type: "tool"
category: "content"
description: "Generate a professional weekly newsletter with curated headlines, deep analysis, market insights, and discoveries. Uses multi-step processing to ensure comprehensive coverage with proper article categorization."

parameters:
  - name: topic
    type: string
    required: false
    default: "AI"
    description: "Main topic focus for the newsletter"
  - name: days_back
    type: integer
    required: false
    default: 7
    description: "Number of days to look back for articles (1-30). Used when start_date/end_date not specified."
  - name: start_date
    type: string
    required: false
    description: "Start date for article range (format: YYYY-MM-DD). Overrides days_back."
  - name: end_date
    type: string
    required: false
    description: "End date for article range (format: YYYY-MM-DD). Defaults to today if not specified."
  - name: deep_dive_topic
    type: string
    required: false
    description: "Specific topic to focus on for the Deep Dive section (optional)"

output:
  type: object
  properties:
    newsletter:
      type: string
      description: "The complete formatted newsletter"
    article_count:
      type: integer
      description: "Total number of articles sourced"
    articles_used:
      type: integer
      description: "Number of articles actually used in the newsletter"
    section_counts:
      type: object
      description: "Breakdown of articles by section"

triggers:
  - patterns: ["newsletter", "weekly newsletter", "generate newsletter", "create newsletter"]
    priority: high
  - patterns: ["news roundup", "weekly roundup", "news digest", "weekly digest"]
    priority: medium
  - patterns: ["curate.*news", "summarize.*week", "compile.*news", "news summary"]
    priority: low
  - patterns: ["curious ai", "weekly ai", "ai roundup"]
    priority: high

# Note: This tool uses a custom handler.py for multi-step processing
# The handler fetches 100-200 articles, categorizes them, prioritizes by quality
# and recency, then generates the newsletter with proper section coverage.
---

# Newsletter Generator Tool (v2.0)

## Purpose
Generate a professional weekly newsletter with curated headlines, in-depth analysis, market insights, and notable discoveries for decision-makers and foresight professionals.

## Key Features (v2.0)

### Multi-Step Processing
Unlike simple prompt-based tools, this newsletter generator uses a sophisticated multi-step approach:

1. **Large Corpus Fetch**: Retrieves 100-200+ articles using multiple search strategies
2. **Smart Categorization**: Automatically categorizes articles into sections based on content analysis
3. **Quality Prioritization**: Scores articles by source quality, recency, and relevance
4. **Section Balancing**: Ensures each newsletter section has appropriate coverage
5. **Deduplication**: Prevents the same article from appearing in multiple sections

### Organizational Profile Integration
When an organizational profile is set in the chat:
- Newsletter content is tailored to the organization's industry
- Strategic insights prioritize their key concerns
- Risk assessments align with their risk tolerance
- Implications focus on their stakeholder priorities

## When to Use
- User asks for a "newsletter" or "news roundup"
- User wants a summary of the week's news
- User requests a "digest" or "weekly update"
- User mentions "Curious AI" newsletter

## Output Sections

### 1. THE NEWS (6-15 headlines)
Punchy headlines grouped by micro-themes:
- **Policy & Regulation**: Laws, regulations, government actions
- **Models & Research**: New models, papers, benchmarks
- **Enterprise & Adoption**: Business deployments, use cases
- **Risk & Trust**: Safety, security, ethics issues

### 2. THE DEEP DIVE (250-400 words)
In-depth analysis of the most significant development:
- What happened, why now
- Consensus vs outlier takes (call out hype)
- Strategic Insight bullets (4 implications)

### 3. WEIRD SH*T OF THE WEEK
Sharp, insightful commentary on bizarre or troubling events.
- Vice/Futurism vibes
- Evolutionary psychology or cyberpunk comparisons

### 4. MUST READS (8-12 articles)
Curated articles with summaries and why they matter.
- Unique data or credible methodology
- Contrarian but evidenced takes

### 5. MARKET UPDATES
- **M&A / Fundraising**: Deals, funding rounds, valuations
- **Releases / Models / Tooling**: New products, features
- **Partnerships / Enterprise Adoption**: Notable deployments

## Article Categorization

The tool uses keyword analysis to categorize articles:

| Section | Key Signals |
|---------|-------------|
| Policy & Regulation | regulation, law, congress, eu, compliance, ban |
| Models & Research | model, gpt, llm, paper, benchmark, training |
| Enterprise & Adoption | enterprise, deploy, implement, workflow, roi |
| Market & Funding | funding, series, investment, acquisition, ipo |
| Risk & Trust | risk, safety, bias, ethics, hallucination, fraud |
| Weird/Unusual | bizarre, viral, controversy, failure, unintended |

## Source Quality Tiers

**High Quality** (30 points): Reuters, FT, WSJ, Bloomberg, AP, MIT Tech Review, Nature, Wired, NYT
**Medium Quality** (15 points): Forbes, Fortune, CNBC, VentureBeat, ZDNet, IEEE Spectrum

## Style Notes
- Analytical, factual, direct voice
- Atlantic/Stratechery vibes with light wit
- Techno-realist: skeptical of hype
- Always cite with markdown links: **[Title](URL)** (Source, Date)
- No filler, no throat clearing
- Geographic diversity (not US-only)

## Example Trigger Messages
- "Generate a newsletter for AI"
- "Create a weekly news roundup"
- "Give me this week's AI digest"
- "Newsletter about the last 7 days"
- "Curious AI weekly update"
