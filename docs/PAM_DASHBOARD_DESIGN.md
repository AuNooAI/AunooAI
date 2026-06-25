# Power, Attention & Money Flows (PAM) Dashboard

## Strategic Intelligence Platform for Scholarly Publishing in the AI Era

### Executive Summary

This dashboard tracks the three fundamental flows reshaping the knowledge economy:
- **Power**: Who controls infrastructure, standards, and regulatory frameworks
- **Attention**: Who captures mindshare, citations, and AI visibility
- **Money**: Where funding flows, who gets acquired, revenue concentration

Designed around the **5 Key Trends for 2030** from strategic planning sessions.

---

## 1. CORE ANALYTICAL FRAMEWORK

### 1.1 The 2030 Trends Tracking System

| Trend ID | Trend Name | PAM Dimension | Key Metrics |
|----------|------------|---------------|-------------|
| T1 | Invisible LLM Ecosystems | Attention | Brand visibility scores, zero-click rates, LLM citation tracking |
| T2 | Agentic AI Reshaping Workflows | Power | Workflow integration depth, API dependency mapping |
| T3 | Decline of SEO / Rise of GEO | Attention | AI-engine discoverability, metadata completeness, provenance signals |
| T4 | Regulatory & Provenance Pressures | Power | Compliance readiness, IP protection posture, licensing coverage |
| T5 | Market Consolidation | Money | M&A activity, funding concentration, vertical integration index |

### 1.2 Three-Axis Analysis Model

```
                    POWER
                      │
                      │     ┌─────────────────┐
                      │     │   PUBLISHERS    │
                      │     │  (Your Position)│
                      │     └─────────────────┘
                      │            ▲
                      │            │
    ─────────────────────────────────────────── ATTENTION
                      │            │
              ┌───────┴───────┐    │
              │  TECH GIANTS  │    │
              │  (Threat)     │    │
              └───────────────┘    │
                      │            │
                      │     ┌──────┴──────┐
                      │     │ GOVERNMENTS │
                      │     │ (Leverage)  │
                      │     └─────────────┘
                      │
                    MONEY
```

---

## 2. DATA SOURCES & COLLECTION

### 2.1 Primary Data Sources

| Source | Data Type | PAM Relevance | Update Frequency |
|--------|-----------|---------------|------------------|
| ArXiv | Preprints | Research attention, AI capability tracking | Daily |
| Semantic Scholar | Citations, Authors | Power networks, influence metrics | Weekly |
| NewsAPI | Industry news | Funding, M&A, regulatory announcements | Real-time |
| PubMed/Crossref | Published papers | Publisher market share, open access trends | Weekly |
| GitHub API | Code repositories | Tech integration, AI tool adoption | Daily |
| Funding databases (Crunchbase, PitchBook) | Investment data | Money flows, concentration | Weekly |
| Patent databases | IP filings | Power concentration, defensive moats | Monthly |

### 2.2 Derived Metrics Catalog

#### POWER Metrics
```yaml
power_metrics:
  regulatory_influence:
    - lobbying_spend_by_entity
    - policy_citation_count
    - standards_committee_representation

  infrastructure_control:
    - api_dependency_count
    - data_pipeline_ownership
    - model_training_data_contribution

  research_network_centrality:
    - author_collaboration_networks
    - institution_partnership_density
    - cross-sector_collaboration_index

  ip_positioning:
    - patent_portfolio_strength
    - licensing_revenue_streams
    - defensive_publication_rate
```

#### ATTENTION Metrics
```yaml
attention_metrics:
  academic_visibility:
    - citation_velocity  # citations per month
    - h_index_trajectory
    - altmetric_attention_score

  ai_engine_visibility:
    - llm_training_data_inclusion_estimate
    - metadata_completeness_score
    - structured_data_availability
    - provenance_signal_strength

  brand_visibility:
    - direct_traffic_trends
    - referral_source_diversity
    - social_media_mention_velocity

  content_synthesis_exposure:
    - clustering_frequency  # how often content appears in AI summaries
    - attribution_preservation_rate
    - zero_click_answer_rate
```

#### MONEY Metrics
```yaml
money_metrics:
  funding_flows:
    - venture_capital_by_sector
    - government_grant_distribution
    - corporate_rd_allocation

  revenue_concentration:
    - market_share_by_publisher
    - subscription_vs_oa_revenue_trends
    - licensing_deal_values

  ma_activity:
    - acquisition_volume_by_acquirer
    - vertical_integration_deals
    - content_asset_valuations

  cost_dynamics:
    - compute_cost_per_inference
    - publishing_cost_trends
    - ai_infrastructure_spend
```

---

## 3. DASHBOARD VIEWS

### 3.1 Executive Overview (Default View)

```
┌─────────────────────────────────────────────────────────────────────────┐
│  POWER, ATTENTION & MONEY FLOWS - Strategic Dashboard                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │ POWER INDEX │  │ ATTENTION   │  │ MONEY FLOW  │  │ THREAT      │    │
│  │    72/100   │  │   INDEX     │  │  $47.2B     │  │ LEVEL       │    │
│  │   ▲ +3.2%   │  │   58/100    │  │  ▲ +12.8%   │  │  ELEVATED   │    │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘    │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  2030 TRENDS RADAR                                                │  │
│  │                                                                   │  │
│  │        T1: Invisible LLMs ●━━━━━━━━━━━━━━━━━━━━━━ 78%            │  │
│  │     T2: Agentic Workflows ●━━━━━━━━━━━━━━━━━━━ 71%               │  │
│  │       T3: SEO→GEO Decline ●━━━━━━━━━━━━━━━━━━━━━━ 82%            │  │
│  │  T4: Regulatory Pressures ●━━━━━━━━━━━━━ 54%                     │  │
│  │  T5: Market Consolidation ●━━━━━━━━━━━━━━━━━━ 67%                │  │
│  │                                                                   │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  ┌────────────────────────────┐  ┌────────────────────────────────┐    │
│  │ KEY EVENTS THIS PERIOD    │  │ EMERGING SIGNALS               │    │
│  │ • OpenAI/Microsoft deal   │  │ • C2PA adoption accelerating   │    │
│  │ • EU AI Act enforcement   │  │ • Citation clustering detected │    │
│  │ • Elsevier acquires X     │  │ • New licensing models emerging│    │
│  │ • Nature AI layer launch  │  │ • GEO optimization patents     │    │
│  └────────────────────────────┘  └────────────────────────────────┘    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Power Flow Analysis View

```
┌─────────────────────────────────────────────────────────────────────────┐
│  POWER FLOW ANALYSIS                                           [Export]│
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                     POWER NETWORK GRAPH                          │   │
│  │                                                                  │   │
│  │              ┌─────────┐                                        │   │
│  │              │ OpenAI  │◄────────────┐                          │   │
│  │              └────┬────┘             │                          │   │
│  │                   │                  │                          │   │
│  │     ┌─────────────┼─────────────┐    │                          │   │
│  │     ▼             ▼             ▼    │                          │   │
│  │ ┌───────┐    ┌─────────┐    ┌──────┐│                          │   │
│  │ │Google │    │Microsoft│    │Meta  ││                          │   │
│  │ └───┬───┘    └────┬────┘    └──┬───┘│                          │   │
│  │     │             │            │     │                          │   │
│  │     └──────┬──────┴────────────┘     │                          │   │
│  │            ▼                         │                          │   │
│  │     ┌──────────────┐                 │                          │   │
│  │     │  PUBLISHERS  │─────────────────┘                          │   │
│  │     │  (Position)  │                                            │   │
│  │     └──────────────┘                                            │   │
│  │                                                                  │   │
│  │  Node Size = Revenue  |  Edge Width = Data/API Dependency       │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌─────────────────────────────┐  ┌─────────────────────────────┐      │
│  │ POWER CONCENTRATION        │  │ REGULATORY LANDSCAPE        │      │
│  │                            │  │                             │      │
│  │ Tech Giants:    ████████ 68%│ │ EU AI Act:        ■ Active  │      │
│  │ Publishers:     ████ 22%    │ │ US Copyright:     □ Pending │      │
│  │ Governments:    ██ 8%       │ │ China Model Gov:  ■ Active  │      │
│  │ Research Orgs:  █ 2%        │ │ C2PA Standards:   ◐ Emerging│      │
│  └─────────────────────────────┘  └─────────────────────────────┘      │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 3.3 Attention Economy View

```
┌─────────────────────────────────────────────────────────────────────────┐
│  ATTENTION ECONOMY ANALYSIS                                    [Export]│
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌────────────────────────────────────────────────────────────────┐    │
│  │ VISIBILITY TRENDS (12 Month)                                   │    │
│  │                                                                │    │
│  │  ▲                                                             │    │
│  │  │     Direct Traffic                                          │    │
│  │  │   ╲                                                         │    │
│  │  │    ╲_______________                                         │    │
│  │  │                    ╲                                        │    │
│  │  │                     ╲________                               │    │
│  │  │                              ╲                              │    │
│  │  │                               ╲___                          │    │
│  │  │                                                             │    │
│  │  │  AI-Mediated Discovery                                      │    │
│  │  │              __________                                     │    │
│  │  │       ______/          ╲_____                               │    │
│  │  │      /                       ╲_______                       │    │
│  │  │─────/────────────────────────────────►                      │    │
│  │      J  F  M  A  M  J  J  A  S  O  N  D                        │    │
│  └────────────────────────────────────────────────────────────────┘    │
│                                                                         │
│  ┌─────────────────────────────┐  ┌─────────────────────────────┐      │
│  │ CITATION VELOCITY RANKING  │  │ AI SYNTHESIS EXPOSURE       │      │
│  │                            │  │                             │      │
│  │ 1. Nature       ▲ +23%    │  │ LLM Training Data:          │      │
│  │ 2. Science      ▲ +18%    │  │ ██████████████████ 89%      │      │
│  │ 3. Cell         ▼ -3%     │  │                             │      │
│  │ 4. PNAS         ▲ +12%    │  │ AI Citation Rate:           │      │
│  │ 5. Elsevier     ▼ -8%     │  │ ██████████ 45%              │      │
│  │                            │  │                             │      │
│  │ [Your Position: 12th]     │  │ Attribution Preserved:      │      │
│  └─────────────────────────────┘  │ ████████ 38%               │      │
│                                    └─────────────────────────────┘      │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ GEO READINESS SCORECARD                                         │   │
│  │                                                                  │   │
│  │ Structured Metadata:     ████████████████████████ 92%  ✓        │   │
│  │ Machine-Readable Rights: ████████████ 48%               ⚠       │   │
│  │ Provenance Tagging:      ██████ 24%                     ✗       │   │
│  │ API Accessibility:       ██████████████████ 72%         ⚠       │   │
│  │ AI Training Licensing:   ████ 15%                       ✗       │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 3.4 Money Flows View

```
┌─────────────────────────────────────────────────────────────────────────┐
│  MONEY FLOWS ANALYSIS                                          [Export]│
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ FUNDING FLOW SANKEY DIAGRAM                                     │   │
│  │                                                                  │   │
│  │  ┌─────────┐                                    ┌──────────────┐│   │
│  │  │ VC/PE   │═══════════════════════════════════▶│ AI/ML        ││   │
│  │  │ $45B    │                                    │ Companies    ││   │
│  │  └─────────┘═══════════▶┌───────────────────────┤              ││   │
│  │                         │                       └──────────────┘│   │
│  │  ┌─────────┐            │                       ┌──────────────┐│   │
│  │  │ Govt    │════════════╪══════════════════════▶│ Research     ││   │
│  │  │ $28B    │            │                       │ Institutions ││   │
│  │  └─────────┘            │                       └──────────────┘│   │
│  │                         │                                       │   │
│  │  ┌─────────┐            │                       ┌──────────────┐│   │
│  │  │Corporate│════════════╧══════════════════════▶│ Publishers   ││   │
│  │  │ $12B    │                                    │ (Licensing)  ││   │
│  │  └─────────┘                                    └──────────────┘│   │
│  │                                                                  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌───────────────────────────────┐  ┌────────────────────────────┐     │
│  │ M&A ACTIVITY (LAST 90 DAYS)  │  │ MARKET CONCENTRATION       │     │
│  │                               │  │                            │     │
│  │ • Microsoft + Nuance ($19.7B)│  │ Top 5 Publishers:          │     │
│  │ • Google + Anthropic ($2B)   │  │ 2020: ████████ 42%         │     │
│  │ • Elsevier + Interfolio     │  │ 2024: ██████████████ 58%   │     │
│  │ • Wiley + Hindawi           │  │ 2030: ███████████████████ 72% (P)│
│  │ • RELX + ThreatMetrix       │  │                            │     │
│  │                               │  │ AI Infrastructure:        │     │
│  │ Total Deal Volume: $47.2B    │  │ Top 3: █████████████████ 87%│    │
│  └───────────────────────────────┘  └────────────────────────────┘     │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ LICENSING VALUE TRENDS                                          │   │
│  │                                                                  │   │
│  │  AI Training Rights:      $2.4B  ▲ +340% YoY                    │   │
│  │  Subscription Revenue:    $12.1B ▲ +4% YoY                      │   │
│  │  Open Access Fees:        $3.8B  ▲ +18% YoY                     │   │
│  │  Data Licensing:          $1.2B  ▲ +89% YoY                     │   │
│  │                                                                  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 3.5 Publisher Positioning View

```
┌─────────────────────────────────────────────────────────────────────────┐
│  PUBLISHER POSITIONING MATRIX                                  [Export]│
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ STRATEGIC ROLE ASSESSMENT                                       │   │
│  │                                                                  │   │
│  │  HIGH POWER                                                      │   │
│  │       │                                                          │   │
│  │       │    ┌────────────────┐        ┌────────────────┐          │   │
│  │       │    │ INFRASTRUCTURE │        │ TRUST          │          │   │
│  │       │    │ PROVIDER       │        │ PROVIDER       │          │   │
│  │       │    │ (RELX, Clarivate)      │ (Nature, Science)        │   │
│  │       │    └────────────────┘        └────────────────┘          │   │
│  │       │                                                          │   │
│  │       ├───────────────────────────────────────────────── HIGH    │   │
│  │       │                                                ATTENTION │   │
│  │       │    ┌────────────────┐        ┌────────────────┐          │   │
│  │       │    │ COMMODITY      │        │ RESEARCHER     │          │   │
│  │       │    │ CONTENT        │        │ CONNECTOR      │          │   │
│  │       │    │ (Risk Zone)    │        │ (Wiley, T&F)   │          │   │
│  │       │    └────────────────┘        └────────────────┘          │   │
│  │       │                                                          │   │
│  │  LOW POWER                                                       │   │
│  │                                                                  │   │
│  │  [Your Position: ●]  [Target Position: ○]                        │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ THREE PILLARS SCORECARD (Publisher Value Proposition)           │   │
│  │                                                                  │   │
│  │  TRUST PROVIDER                                                  │   │
│  │  ├─ Peer review integrity     ████████████████████ 95%          │   │
│  │  ├─ Retraction transparency   ████████████████ 78%              │   │
│  │  ├─ Data verification         ████████ 42%                      │   │
│  │  └─ AI content detection      ██████ 28%                        │   │
│  │                                                                  │   │
│  │  CONTENT INFRASTRUCTURE                                          │   │
│  │  ├─ API accessibility         ██████████████████ 85%            │   │
│  │  ├─ Metadata quality          ████████████████████ 92%          │   │
│  │  ├─ Rights management         ████████████ 56%                  │   │
│  │  └─ AI-ready pipelines        ██████ 31%                        │   │
│  │                                                                  │   │
│  │  RESEARCHER CONNECTOR                                            │   │
│  │  ├─ Author relationships      ██████████████████ 88%            │   │
│  │  ├─ Community engagement      ████████████████ 75%              │   │
│  │  ├─ Workflow integration      ████████████ 58%                  │   │
│  │  └─ Incentive alignment       ██████████████ 67%                │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 3.6 Scenario Planning View

```
┌─────────────────────────────────────────────────────────────────────────┐
│  SCENARIO PLANNING: 2030 FUTURES                               [Export]│
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ SCENARIO QUADRANT MAP                                           │   │
│  │                                                                  │   │
│  │  HIGH REGULATION                                                 │   │
│  │         │                                                        │   │
│  │         │  ┌───────────────────┐    ┌───────────────────┐       │   │
│  │         │  │ FRAGMENTED        │    │ TRUSTED ECOSYSTEM │       │   │
│  │         │  │ COMPLIANCE        │    │ (Best Case)       │       │   │
│  │         │  │ Multiple standards│    │ Publishers as     │       │   │
│  │         │  │ Regional silos    │    │ trusted custodians│       │   │
│  │         │  │ Prob: 25%         │    │ Prob: 30%         │       │   │
│  │         │  └───────────────────┘    └───────────────────┘       │   │
│  │         │                                                        │   │
│  │  ───────┼─────────────────────────────────────── HIGH           │   │
│  │  LOW    │                                        CONCENTRATION  │   │
│  │  CONC.  │  ┌───────────────────┐    ┌───────────────────┐       │   │
│  │         │  │ OPEN CHAOS        │    │ BEHEMOTH CONTROL  │       │   │
│  │         │  │ Wild west AI      │    │ (Worst Case)      │       │   │
│  │         │  │ No attribution    │    │ 3-5 giants own    │       │   │
│  │         │  │ Prob: 15%         │    │ everything        │       │   │
│  │         │  │                   │    │ Prob: 30%         │       │   │
│  │         │  └───────────────────┘    └───────────────────┘       │   │
│  │         │                                                        │   │
│  │  LOW REGULATION                                                  │   │
│  │                                                                  │   │
│  │  Current Trajectory: ─────▶ (Heading toward Behemoth Control)   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ STRATEGIC INTERVENTIONS TO REACH TRUSTED ECOSYSTEM              │   │
│  │                                                                  │   │
│  │ ■ Collective licensing agreements          (Urgency: HIGH)      │   │
│  │ ■ Multi-publisher data cooperatives        (Urgency: HIGH)      │   │
│  │ ■ Provenance/C2PA infrastructure           (Urgency: MEDIUM)    │   │
│  │ ■ AI-ready content pipelines               (Urgency: MEDIUM)    │   │
│  │ ■ Regulatory advocacy coordination         (Urgency: HIGH)      │   │
│  │ ■ GEO optimization standards               (Urgency: LOW)       │   │
│  │                                                                  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 4. ANALYSIS PLUGINS

### 4.1 Core PAM Analysis Plugin

```yaml
# /data/auspex/plugins/power_attention_money/tool.md

name: "power_attention_money"
version: "1.0.0"
type: "tool"
category: "analysis"
description: "Analyze power, attention, and money flows in knowledge economy"

parameters:
  - name: analysis_focus
    type: string
    required: true
    enum: ["power", "attention", "money", "comprehensive"]
    description: "Primary analysis dimension"

  - name: entity_type
    type: string
    required: false
    enum: ["publisher", "tech_company", "research_institution", "government"]
    default: "publisher"
    description: "Type of entities to analyze"

  - name: time_horizon
    type: string
    required: false
    enum: ["current", "6_months", "1_year", "5_years", "2030"]
    default: "1_year"
    description: "Analysis time frame"

  - name: trend_focus
    type: array
    required: false
    default: ["T1", "T2", "T3", "T4", "T5"]
    description: "Which 2030 trends to prioritize"

triggers:
  - patterns: ["power flow", "attention economy", "money flow", "market concentration"]
    priority: high
  - patterns: ["who controls", "who funds", "market share", "consolidation"]
    priority: medium
  - patterns: ["publisher strategy", "AI disruption", "SEO dying", "GEO"]
    priority: medium

actions:
  - vector_search
  - db_search
  - web_search

prompt: |
  You are analyzing POWER, ATTENTION, and MONEY flows in the scholarly publishing
  and knowledge economy space, with focus on the 5 key trends for 2030.

  **Analysis Focus:** {analysis_focus}
  **Entity Type:** {entity_type}
  **Time Horizon:** {time_horizon}
  **Active Trends:** {trend_focus}

  **THE 5 KEY TRENDS FOR 2030:**
  T1: Invisible LLM Ecosystems - AI intermediaries bypass direct access
  T2: Agentic AI Workflows - AI agents replace traditional research workflows
  T3: SEO→GEO Transition - Generative Engine Optimization replaces search
  T4: Regulatory Pressures - IP, provenance, and compliance requirements
  T5: Market Consolidation - Concentration around compute+data giants

  **CONTEXT DATA:**
  Topic: {topic}
  Articles Analyzed: {article_count}

  {articles}

  **ANALYSIS FRAMEWORK:**

  1. **POWER DYNAMICS**
     - Who holds infrastructure control?
     - What regulatory leverage exists?
     - How are research networks configured?
     - Where is IP positioning strongest?

  2. **ATTENTION FLOWS**
     - What is the citation velocity landscape?
     - How visible are entities to AI systems?
     - What is the GEO readiness posture?
     - How is content being synthesized/clustered?

  3. **MONEY MOVEMENTS**
     - Where is funding flowing?
     - What M&A activity is occurring?
     - How concentrated are revenues?
     - What are licensing value trends?

  4. **STRATEGIC IMPLICATIONS**
     - What does this mean for publishers?
     - What interventions could shift outcomes?
     - What is the trajectory toward 2030 scenarios?

  Provide your analysis with:
  - Specific metrics and data points from articles
  - Clear citations to source articles [Title](URL)
  - Actionable strategic recommendations
  - Confidence levels for projections
```

### 4.2 Trend Monitor Plugin

```yaml
# /data/auspex/plugins/trend_2030_monitor/tool.md

name: "trend_2030_monitor"
version: "1.0.0"
type: "tool"
category: "analysis"
description: "Track progress of 5 key 2030 trends for scholarly publishing"

parameters:
  - name: trend_id
    type: string
    required: true
    enum: ["T1", "T2", "T3", "T4", "T5", "all"]
    description: "Which trend to analyze"

  - name: signal_type
    type: string
    required: false
    enum: ["accelerating", "decelerating", "inflection", "emerging"]
    default: "all"
    description: "Type of signals to detect"

triggers:
  - patterns: ["trend status", "2030 progress", "invisible LLM", "agentic AI",
               "GEO optimization", "regulatory pressure", "consolidation trend"]
    priority: high

actions:
  - vector_search
  - db_search
  - web_search

prompt: |
  You are monitoring the progress of the 5 KEY TRENDS FOR 2030 in scholarly publishing.

  **TREND DEFINITIONS:**

  T1: INVISIBLE LLM ECOSYSTEMS
  - AI assistants become primary information gateway
  - Users no longer "go" to platforms
  - Brand visibility diminishes
  - Signals: Zero-click rates, direct traffic decline, AI mediation growth

  T2: AGENTIC AI RESHAPING WORKFLOWS
  - AI agents read literature, draft protocols, run simulations
  - Students rely on "AI cognition layers"
  - Signals: AI tool adoption, workflow automation metrics, research productivity

  T3: DECLINE OF SEO, RISE OF GEO
  - Traditional search discovery collapsing
  - LLMs collapse search→click→read→evaluate into single answer
  - Signals: Search traffic trends, AI answer extraction, metadata completeness

  T4: REGULATORY & PROVENANCE PRESSURES
  - EU AI Act, US rules, China governance, C2PA standards
  - Content provenance and licensing requirements
  - Signals: New legislation, court cases, standards adoption, opt-out rates

  T5: MARKET CONSOLIDATION
  - Vertical integration of compute+data+AI
  - Fewer, larger players control ecosystem
  - Signals: M&A activity, funding concentration, API dependencies

  **ANALYSIS FOR: {trend_id}**
  **Signal Type: {signal_type}**

  {articles}

  Provide:
  1. Current trend strength (0-100%)
  2. Velocity (accelerating/stable/decelerating)
  3. Key events driving the trend
  4. Early warning signals
  5. Publisher implications
  6. Recommended actions
```

### 4.3 Publisher Position Plugin

```yaml
# /data/auspex/plugins/publisher_position/tool.md

name: "publisher_position"
version: "1.0.0"
type: "tool"
category: "analysis"
description: "Assess publisher strategic positioning across three value pillars"

parameters:
  - name: publisher_name
    type: string
    required: false
    description: "Specific publisher to analyze (or 'industry' for sector-wide)"

  - name: pillar_focus
    type: string
    required: false
    enum: ["trust", "infrastructure", "connector", "all"]
    default: "all"
    description: "Which value pillar to analyze"

triggers:
  - patterns: ["publisher position", "trust provider", "content infrastructure",
               "researcher connector", "publisher value", "strategic role"]
    priority: high

prompt: |
  You are assessing publisher strategic positioning across the THREE VALUE PILLARS:

  **PILLAR 1: TRUST PROVIDER**
  Publishers maintain integrity and verification of knowledge:
  - Peer review processes
  - Retraction and correction transparency
  - AI content detection
  - Data verification capabilities
  - Combating misinformation

  **PILLAR 2: CONTENT INFRASTRUCTURE PROVIDER**
  Publishers provide technical backbone for knowledge:
  - API accessibility and machine-readability
  - Metadata quality and completeness
  - Rights management and licensing infrastructure
  - AI-ready content pipelines
  - Provenance and watermarking systems

  **PILLAR 3: RESEARCHER CONNECTOR**
  Publishers maintain relationships due to incentive structures:
  - Author career advancement alignment
  - Community building and engagement
  - Workflow integration with research process
  - Discovery and dissemination reach
  - Network effects in specific domains

  **ANALYSIS FOR: {publisher_name}**
  **Pillar Focus: {pillar_focus}**

  {articles}

  Provide:
  1. Scorecard for each pillar (0-100%)
  2. Strengths and vulnerabilities
  3. Comparison to competitors
  4. Threat vectors from AI intermediaries
  5. Strategic recommendations
```

---

## 5. DATABASE SCHEMA

### 5.1 Core Tables

```sql
-- Main analysis runs table
CREATE TABLE pam_analysis_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER REFERENCES users(id),
    topic_id INTEGER REFERENCES topics(id),
    analysis_type VARCHAR(50) NOT NULL,  -- 'comprehensive', 'power', 'attention', 'money'
    time_horizon VARCHAR(50),
    trend_focus JSONB DEFAULT '["T1", "T2", "T3", "T4", "T5"]',

    -- Scores
    power_score FLOAT,
    attention_score FLOAT,
    money_score FLOAT,
    threat_level VARCHAR(20),  -- 'low', 'moderate', 'elevated', 'high', 'critical'

    -- Full analysis
    raw_output JSONB,
    executive_summary TEXT,
    strategic_recommendations JSONB,

    -- Metadata
    articles_analyzed INTEGER,
    model_used VARCHAR(100),
    analysis_duration_seconds FLOAT,
    created_at TIMESTAMP DEFAULT NOW(),

    INDEX idx_pam_user_topic (user_id, topic_id),
    INDEX idx_pam_created (created_at DESC)
);

-- Trend tracking over time
CREATE TABLE pam_trend_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_date DATE NOT NULL,

    -- Trend scores (0-100)
    t1_invisible_llm FLOAT,
    t2_agentic_ai FLOAT,
    t3_seo_geo_decline FLOAT,
    t4_regulatory FLOAT,
    t5_consolidation FLOAT,

    -- Trend velocities
    t1_velocity VARCHAR(20),  -- 'accelerating', 'stable', 'decelerating'
    t2_velocity VARCHAR(20),
    t3_velocity VARCHAR(20),
    t4_velocity VARCHAR(20),
    t5_velocity VARCHAR(20),

    -- Key events
    key_events JSONB,

    -- Sources
    articles_analyzed INTEGER,
    data_sources JSONB,

    created_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(snapshot_date),
    INDEX idx_trend_date (snapshot_date DESC)
);

-- Entity tracking (publishers, tech companies, etc.)
CREATE TABLE pam_entities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_name VARCHAR(255) NOT NULL,
    entity_type VARCHAR(50) NOT NULL,  -- 'publisher', 'tech_company', 'research_institution', 'government'

    -- Scores
    power_score FLOAT,
    attention_score FLOAT,
    money_score FLOAT,
    overall_influence FLOAT,

    -- Publisher-specific pillars
    trust_pillar_score FLOAT,
    infrastructure_pillar_score FLOAT,
    connector_pillar_score FLOAT,

    -- Metadata
    metadata JSONB,
    last_updated TIMESTAMP DEFAULT NOW(),

    UNIQUE(entity_name, entity_type),
    INDEX idx_entity_type (entity_type),
    INDEX idx_entity_influence (overall_influence DESC)
);

-- Time series for tracking metrics
CREATE TABLE pam_metrics_timeseries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id UUID REFERENCES pam_entities(id),
    metric_date DATE NOT NULL,

    -- Metric data
    metric_name VARCHAR(100) NOT NULL,
    metric_value FLOAT NOT NULL,
    metric_category VARCHAR(50),  -- 'power', 'attention', 'money'

    -- Context
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(entity_id, metric_date, metric_name),
    INDEX idx_metric_date (metric_date DESC),
    INDEX idx_metric_name (metric_name)
);

-- M&A and funding events
CREATE TABLE pam_financial_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_date DATE NOT NULL,
    event_type VARCHAR(50) NOT NULL,  -- 'acquisition', 'merger', 'funding', 'ipo', 'partnership'

    -- Parties
    acquirer VARCHAR(255),
    target VARCHAR(255),

    -- Financial
    deal_value_usd BIGINT,
    funding_round VARCHAR(50),  -- 'seed', 'series_a', etc.

    -- Analysis
    strategic_significance TEXT,
    pam_implications JSONB,
    trend_relevance JSONB,  -- which T1-T5 trends this affects

    -- Sources
    source_articles JSONB,
    news_sources JSONB,

    created_at TIMESTAMP DEFAULT NOW(),

    INDEX idx_event_date (event_date DESC),
    INDEX idx_event_type (event_type)
);

-- Regulatory developments
CREATE TABLE pam_regulatory_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_date DATE NOT NULL,

    -- Event details
    jurisdiction VARCHAR(100),  -- 'EU', 'US', 'China', 'Global'
    regulation_name VARCHAR(255),
    event_type VARCHAR(50),  -- 'enacted', 'proposed', 'amended', 'ruling', 'enforcement'

    -- Analysis
    summary TEXT,
    publisher_implications TEXT,
    tech_implications TEXT,
    compliance_requirements JSONB,

    -- Trend relevance
    t4_impact_score FLOAT,  -- 0-100 impact on T4 (regulatory trend)

    -- Sources
    source_articles JSONB,

    created_at TIMESTAMP DEFAULT NOW(),

    INDEX idx_reg_date (event_date DESC),
    INDEX idx_jurisdiction (jurisdiction)
);

-- Saved dashboards for PAM
CREATE TABLE pam_saved_dashboards (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER REFERENCES users(id),
    name VARCHAR(255) NOT NULL,
    description TEXT,

    -- Configuration
    config JSONB,
    entity_filters JSONB,
    trend_focus JSONB,
    time_range VARCHAR(50),

    -- Snapshot data
    power_analysis JSONB,
    attention_analysis JSONB,
    money_analysis JSONB,
    scenario_analysis JSONB,

    -- Metadata
    auto_refresh BOOLEAN DEFAULT FALSE,
    refresh_frequency VARCHAR(50),
    last_refreshed TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    INDEX idx_pam_dash_user (user_id),
    INDEX idx_pam_dash_created (created_at DESC)
);
```

---

## 6. API ROUTES

### 6.1 Analysis Endpoints

```python
# /app/routes/pam_routes.py

from fastapi import APIRouter, Depends, Query
from typing import Optional, List

router = APIRouter(prefix="/api/pam", tags=["Power Attention Money"])

# Core Analysis
@router.post("/analyze")
async def run_pam_analysis(
    topic_id: int,
    analysis_type: str = "comprehensive",  # power, attention, money, comprehensive
    entity_type: str = "publisher",
    time_horizon: str = "1_year",
    trend_focus: List[str] = ["T1", "T2", "T3", "T4", "T5"],
    model: str = "gpt-4o",
    days_back: int = 90,
    article_limit: int = 100
):
    """Run comprehensive PAM analysis"""
    pass

@router.get("/executive-summary/{topic_id}")
async def get_executive_summary(topic_id: int, days_back: int = 30):
    """Get executive overview with KPIs"""
    pass

# Trend Monitoring
@router.get("/trends")
async def get_trend_status(
    trend_ids: List[str] = Query(default=["T1", "T2", "T3", "T4", "T5"]),
    include_history: bool = True,
    days_back: int = 90
):
    """Get current status of 2030 trends"""
    pass

@router.post("/trends/snapshot")
async def create_trend_snapshot():
    """Create daily trend snapshot (scheduled job)"""
    pass

# Entity Analysis
@router.get("/entities")
async def list_entities(
    entity_type: Optional[str] = None,
    sort_by: str = "overall_influence",
    limit: int = 50
):
    """List tracked entities with scores"""
    pass

@router.get("/entities/{entity_id}")
async def get_entity_detail(entity_id: str, include_timeseries: bool = True):
    """Get detailed entity analysis"""
    pass

@router.post("/entities/{entity_name}/analyze")
async def analyze_entity(
    entity_name: str,
    entity_type: str,
    pillar_focus: str = "all"
):
    """Run publisher positioning analysis"""
    pass

# Financial Events
@router.get("/events/financial")
async def get_financial_events(
    event_type: Optional[str] = None,
    days_back: int = 90,
    min_value: Optional[int] = None
):
    """Get M&A and funding events"""
    pass

@router.get("/events/regulatory")
async def get_regulatory_events(
    jurisdiction: Optional[str] = None,
    days_back: int = 90
):
    """Get regulatory developments"""
    pass

# Scenarios
@router.get("/scenarios")
async def get_scenario_analysis(topic_id: int):
    """Get 2030 scenario quadrant analysis"""
    pass

@router.post("/scenarios/simulate")
async def run_scenario_simulation(
    intervention: str,
    scenario_params: dict
):
    """Simulate impact of strategic interventions"""
    pass

# Dashboards
@router.get("/dashboards")
async def list_pam_dashboards(user_id: int):
    """List saved PAM dashboards"""
    pass

@router.post("/dashboards/save")
async def save_pam_dashboard(dashboard_data: dict):
    """Save PAM dashboard configuration and data"""
    pass

@router.get("/dashboards/{dashboard_id}")
async def load_pam_dashboard(dashboard_id: str):
    """Load saved PAM dashboard"""
    pass

# Metrics
@router.get("/metrics/power")
async def get_power_metrics(entity_id: Optional[str] = None, days_back: int = 365):
    """Get power-related metrics"""
    pass

@router.get("/metrics/attention")
async def get_attention_metrics(entity_id: Optional[str] = None, days_back: int = 365):
    """Get attention-related metrics"""
    pass

@router.get("/metrics/money")
async def get_money_metrics(entity_id: Optional[str] = None, days_back: int = 365):
    """Get money-related metrics"""
    pass
```

---

## 7. REACT COMPONENTS

### 7.1 Component Hierarchy

```
ui/src/components/pam/
├── PAMDashboard.tsx              # Main container
├── PAMExecutiveOverview.tsx      # KPI cards and radar
├── PAMTrendRadar.tsx             # 5 trends visualization
├── PAMPowerFlow.tsx              # Power network graph
├── PAMAttentionEconomy.tsx       # Attention metrics
├── PAMMoneyFlows.tsx             # Sankey + M&A
├── PAMPublisherPosition.tsx      # Positioning matrix
├── PAMScenarioPlanning.tsx       # 2030 scenarios
├── PAMEntityCard.tsx             # Individual entity display
├── PAMTrendCard.tsx              # Individual trend display
├── PAMEventTimeline.tsx          # Financial/regulatory events
├── PAMMetricsChart.tsx           # Time series charts
└── PAMTuneModal.tsx              # Configuration modal
```

### 7.2 Main Hook

```typescript
// ui/src/hooks/usePAM.ts

interface PAMConfig {
  analysisType: 'power' | 'attention' | 'money' | 'comprehensive';
  entityType: 'publisher' | 'tech_company' | 'research_institution' | 'government';
  timeHorizon: 'current' | '6_months' | '1_year' | '5_years' | '2030';
  trendFocus: ('T1' | 'T2' | 'T3' | 'T4' | 'T5')[];
  daysBack: number;
  articleLimit: number;
  model: string;
}

interface PAMData {
  executiveSummary: {
    powerIndex: number;
    attentionIndex: number;
    moneyFlow: number;
    threatLevel: 'low' | 'moderate' | 'elevated' | 'high' | 'critical';
    keyEvents: string[];
    emergingSignals: string[];
  };
  trends: TrendStatus[];
  powerAnalysis: PowerAnalysis;
  attentionAnalysis: AttentionAnalysis;
  moneyAnalysis: MoneyAnalysis;
  entities: Entity[];
  scenarios: ScenarioAnalysis;
  recommendations: Recommendation[];
}

interface TrendStatus {
  id: 'T1' | 'T2' | 'T3' | 'T4' | 'T5';
  name: string;
  score: number;
  velocity: 'accelerating' | 'stable' | 'decelerating';
  keyDrivers: string[];
  publisherImplications: string;
}

export const usePAM = () => {
  const [config, setConfig] = useState<PAMConfig>(defaultConfig);
  const [data, setData] = useState<PAMData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runAnalysis = async (topicId: number) => { /* ... */ };
  const saveDashboard = async (name: string, description: string) => { /* ... */ };
  const loadDashboard = async (dashboardId: string) => { /* ... */ };
  const refreshTrends = async () => { /* ... */ };

  return {
    config, setConfig,
    data, loading, error,
    runAnalysis, saveDashboard, loadDashboard, refreshTrends
  };
};
```

### 7.3 Main Dashboard Component Structure

```typescript
// ui/src/components/pam/PAMDashboard.tsx

const PAMDashboard: React.FC = () => {
  const [activeView, setActiveView] = useState<
    'executive' | 'power' | 'attention' | 'money' | 'publisher' | 'scenarios'
  >('executive');

  const {
    config, setConfig,
    data, loading, error,
    runAnalysis, saveDashboard
  } = usePAM();

  return (
    <div className="pam-dashboard">
      {/* Header with controls */}
      <PAMHeader
        config={config}
        onConfigChange={setConfig}
        onAnalyze={() => runAnalysis(topicId)}
        onSave={() => openSaveModal()}
      />

      {/* View tabs */}
      <PAMViewTabs activeView={activeView} onViewChange={setActiveView} />

      {/* Content area */}
      <div className="pam-content">
        {activeView === 'executive' && <PAMExecutiveOverview data={data} />}
        {activeView === 'power' && <PAMPowerFlow data={data?.powerAnalysis} />}
        {activeView === 'attention' && <PAMAttentionEconomy data={data?.attentionAnalysis} />}
        {activeView === 'money' && <PAMMoneyFlows data={data?.moneyAnalysis} />}
        {activeView === 'publisher' && <PAMPublisherPosition data={data} />}
        {activeView === 'scenarios' && <PAMScenarioPlanning data={data?.scenarios} />}
      </div>

      {/* Modals */}
      <PAMTuneModal isOpen={tuneOpen} config={config} onSave={setConfig} />
      <PAMSaveModal isOpen={saveOpen} onSave={saveDashboard} />
    </div>
  );
};
```

---

## 8. DATA COLLECTION STRATEGY

### 8.1 Article Collection Queries

```python
# Keywords for each trend
TREND_KEYWORDS = {
    "T1": [
        "AI assistant", "ChatGPT", "LLM", "zero-click", "AI intermediary",
        "brand visibility", "direct traffic decline", "AI gateway"
    ],
    "T2": [
        "AI agent", "autonomous research", "AI workflow", "research automation",
        "AI cognition", "scientific AI", "automated literature review"
    ],
    "T3": [
        "SEO decline", "generative engine", "GEO optimization", "AI discoverability",
        "machine-readable content", "structured data", "metadata standards"
    ],
    "T4": [
        "AI regulation", "EU AI Act", "content provenance", "C2PA", "copyright AI",
        "licensing AI", "AI training rights", "opt-out AI"
    ],
    "T5": [
        "AI acquisition", "tech consolidation", "publisher merger", "AI funding",
        "market concentration", "vertical integration", "AI monopoly"
    ]
}

# Power-specific keywords
POWER_KEYWORDS = [
    "regulatory influence", "standards committee", "AI governance",
    "data control", "API dependency", "infrastructure control"
]

# Attention-specific keywords
ATTENTION_KEYWORDS = [
    "citation impact", "research visibility", "AI training data",
    "content licensing", "academic influence", "brand recognition"
]

# Money-specific keywords
MONEY_KEYWORDS = [
    "acquisition", "merger", "funding round", "investment",
    "revenue", "market share", "deal value", "licensing deal"
]
```

### 8.2 Source Prioritization

| Priority | Source | Data Type | Refresh |
|----------|--------|-----------|---------|
| 1 | Semantic Scholar | Citations, authors | Weekly |
| 2 | NewsAPI | Industry news | Daily |
| 3 | ArXiv | Research trends | Daily |
| 4 | Web Search | Events, announcements | On-demand |
| 5 | Database articles | Analyzed content | Continuous |

---

## 9. IMPLEMENTATION PHASES

### Phase 1: Foundation (Core Infrastructure)
- [ ] Database schema creation
- [ ] Basic API routes
- [ ] Core analysis plugin
- [ ] React hook and main component shell

### Phase 2: Trend Tracking
- [ ] Trend monitor plugin
- [ ] Trend snapshot scheduler
- [ ] Trend radar visualization
- [ ] Historical trend charts

### Phase 3: Power Analysis
- [ ] Power network graph
- [ ] Entity tracking system
- [ ] Regulatory event tracking
- [ ] Power metrics dashboard

### Phase 4: Attention Analysis
- [ ] Citation velocity tracking
- [ ] GEO readiness scorecard
- [ ] AI visibility metrics
- [ ] Attention trends visualization

### Phase 5: Money Analysis
- [ ] Financial event tracking
- [ ] Sankey diagram for funding flows
- [ ] M&A activity dashboard
- [ ] Market concentration metrics

### Phase 6: Publisher Positioning
- [ ] Three pillars assessment
- [ ] Positioning matrix
- [ ] Competitor comparison
- [ ] Strategic recommendations engine

### Phase 7: Scenario Planning
- [ ] Scenario quadrant map
- [ ] Intervention simulation
- [ ] Trajectory visualization
- [ ] Action planning tools

### Phase 8: Integration & Polish
- [ ] Save/load dashboards
- [ ] Export functionality
- [ ] Scheduled reports
- [ ] Alert system for key events

---

## 10. SUCCESS METRICS

### Dashboard Usage
- Active users per week
- Average session duration
- Most-used views
- Save/export frequency

### Analysis Quality
- User satisfaction ratings
- Recommendation adoption rate
- Prediction accuracy (validated post-hoc)
- Citation/source quality

### Strategic Impact
- Decisions influenced by dashboard
- Early warning signals captured
- Strategic planning engagement
- Industry adoption of recommendations

---

## APPENDIX: Key Quotes from Strategic Brief

> "Our conversation centred on the flows of power, attention, and money, and how these forces will reshape research and publishing by 2030."

> "Intelligence will eventually be priced at the same cost as electricity—cheap, ubiquitous, and infrastructural. If that is true, the strategic battleground will be the control of content, data, and usage channels, not the intelligence layer itself."

> "Publishers collectively have the ability—and responsibility—to push a different future into existence. Our role is to put the infrastructure, policies, legislation, and standards in place that resist concentration and protect the integrity of the knowledge ecosystem."

> "This reinforces the value of publishers as: providers of trust, providers of content infrastructure, and collective purveyors of ground truth."

> "We collectively have a moral obligation to drive toward the better version of the future, where power, attention, and money are distributed fairly, where trust is maintained, and where the infrastructure of science continues to support global participation and human flourishing."
