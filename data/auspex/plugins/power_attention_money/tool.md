---
name: "power_attention_money"
version: "1.0.0"
type: "tool"
category: "analysis"
description: "Analyze power, attention, and money flows in the knowledge economy. Tracks the 5 key trends reshaping scholarly publishing by 2030."

parameters:
  - name: analysis_focus
    type: string
    required: false
    default: "comprehensive"
    enum: ["power", "attention", "money", "comprehensive"]
    description: "Primary analysis dimension to focus on"

  - name: entity_type
    type: string
    required: false
    default: "publisher"
    enum: ["publisher", "tech_company", "research_institution", "government", "all"]
    description: "Type of entities to analyze"

  - name: time_horizon
    type: string
    required: false
    default: "1_year"
    enum: ["current", "6_months", "1_year", "5_years", "2030"]
    description: "Analysis time frame and projection horizon"

  - name: trend_focus
    type: array
    required: false
    default: ["T1", "T2", "T3", "T4", "T5"]
    description: "Which 2030 trends to prioritize (T1-T5)"

  - name: include_scenarios
    type: boolean
    required: false
    default: true
    description: "Include 2030 scenario analysis and strategic recommendations"

output:
  type: object
  properties:
    executive_summary:
      type: object
      description: "KPIs and high-level overview"
    power_analysis:
      type: object
      description: "Power dynamics and concentration analysis"
    attention_analysis:
      type: object
      description: "Attention economy metrics and visibility trends"
    money_analysis:
      type: object
      description: "Funding flows, M&A, and market concentration"
    trend_status:
      type: array
      description: "Status of each 2030 trend (T1-T5)"
    strategic_recommendations:
      type: array
      description: "Actionable recommendations for publishers"

triggers:
  - patterns: ["power flow", "attention economy", "money flow", "PAM analysis"]
    priority: high
  - patterns: ["who controls", "who funds", "market share", "consolidation"]
    priority: high
  - patterns: ["2030 trends", "publishing future", "AI disruption scholarly"]
    priority: high
  - patterns: ["publisher strategy", "SEO dying", "GEO optimization", "invisible LLM"]
    priority: medium
  - patterns: ["tech giants publishing", "regulatory pressure AI", "content licensing"]
    priority: medium
  - patterns: ["funding research", "acquisition publishing", "market concentration"]
    priority: medium

actions:
  - vector_search
  - db_search
  - web_search

workflow:
  stages:
    - name: data_collection
      description: "Gather articles on power, attention, money themes"
      weight: 0.15
    - name: trend_analysis
      description: "Analyze status of 5 key 2030 trends"
      weight: 0.20
    - name: power_analysis
      description: "Map power dynamics and concentration"
      weight: 0.20
    - name: attention_analysis
      description: "Assess visibility and discoverability metrics"
      weight: 0.20
    - name: money_analysis
      description: "Track funding flows and market movements"
      weight: 0.15
    - name: synthesis
      description: "Generate strategic recommendations"
      weight: 0.10
---

# Power, Attention & Money Flows Analysis

## Purpose

Analyze the three fundamental flows reshaping the knowledge economy and scholarly publishing:

- **POWER**: Who controls infrastructure, standards, regulatory frameworks, and research networks
- **ATTENTION**: Who captures mindshare, citations, AI visibility, and brand recognition
- **MONEY**: Where funding flows, who gets acquired, how revenues concentrate

This analysis is structured around the **5 Key Trends for 2030** identified in strategic planning:

## The 5 Key Trends for 2030

### T1: Invisible LLM Ecosystems & Loss of Brand Visibility
AI assistants become the primary gateway for information retrieval. Users no longer "go" to platforms - platforms become background infrastructure. This removes brand-level visibility and shifts value capture from publishers to AI intermediaries.

**Key Metrics:**
- Zero-click rate (queries answered without visiting publisher)
- Direct traffic trends
- AI-mediated discovery share
- Brand mention in AI responses

### T2: Agentic AI Reshaping Research & Learning Workflows
By 2030, AI agents will read the literature, draft protocols, run simulations, detect anomalies, and prepare manuscripts. Students and researchers rely on "AI cognition layers" rather than content platforms.

**Key Metrics:**
- AI tool adoption in research workflows
- Workflow automation penetration
- Human vs. AI content creation ratio
- Research productivity multipliers

### T3: Decline of SEO and Rise of GEO (Generative Engine Optimization)
Traditional search-driven discovery is collapsing. LLMs collapse multiple steps ("search -> click -> read -> evaluate") into a single answer or agentic action.

**Key Metrics:**
- Search traffic trends
- GEO readiness scores (metadata, structured data, provenance)
- AI-engine discoverability
- Attribution preservation rates

### T4: Regulatory & Provenance Pressures
The EU AI Act, US sector-specific rules, China's model governance, and global provenance initiatives (C2PA, watermarking) create a fragmented compliance landscape.

**Key Metrics:**
- Regulatory development velocity
- Compliance readiness scores
- Licensing coverage
- IP protection posture

### T5: Market Consolidation Around "Compute + Data" Giants
Control of compute, model training pipelines, and data-access ecosystems will be concentrated in fewer vertically integrated players.

**Key Metrics:**
- M&A activity volume and value
- Funding concentration (top 5 players)
- Vertical integration deals
- Market share by segment

## Three Strategic Roles for Publishers

The analysis assesses positioning across three value pillars:

### 1. Trust Provider
- Peer review integrity
- Retraction transparency
- AI content detection
- Data verification capabilities

### 2. Content Infrastructure Provider
- API accessibility
- Metadata quality and completeness
- Rights management infrastructure
- AI-ready content pipelines

### 3. Researcher Connector
- Author relationship depth
- Community engagement
- Workflow integration
- Incentive alignment

## Scenario Planning: 2030 Futures

The analysis maps four possible scenarios based on regulation level and market concentration:

| Scenario | Regulation | Concentration | Probability |
|----------|------------|---------------|-------------|
| Trusted Ecosystem | High | Low | 30% (Best case) |
| Fragmented Compliance | High | High | 25% |
| Open Chaos | Low | Low | 15% |
| Behemoth Control | Low | High | 30% (Worst case) |

## Example Queries

- "Analyze power flows in scholarly publishing"
- "What's the status of the 2030 trends?"
- "How is attention shifting from publishers to AI?"
- "Track funding and acquisitions in publishing tech"
- "Assess publisher positioning against AI disruption"
- "Who controls the knowledge infrastructure?"
- "What regulatory pressures are emerging?"
- "Map market consolidation in academic publishing"

## Output Structure

### Executive Summary
- Power Index (0-100)
- Attention Index (0-100)
- Money Flow total
- Threat Level (low/moderate/elevated/high/critical)
- Key events this period
- Emerging signals

### Trend Radar
- Status of each T1-T5 trend (0-100%)
- Velocity (accelerating/stable/decelerating)
- Key drivers
- Publisher implications

### Detailed Analysis
- Power flow network and concentration
- Attention economy metrics
- Money flows and M&A activity
- Entity positioning matrix

### Strategic Recommendations
- Prioritized interventions
- Urgency levels
- Expected outcomes
