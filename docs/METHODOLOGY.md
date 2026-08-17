# AunooAI: Intelligence Collection & Foresight Methodology

## Overview

AunooAI is a strategic intelligence platform that continuously collects, classifies, and synthesises open-source information to produce structured foresight analyses. The system combines automated multi-source collection with hybrid machine-learning and large-language-model enrichment, enabling analysts to move from raw information to actionable strategic insight.

This document describes the methodology at each stage of the intelligence lifecycle, with particular emphasis on the foresight analysis capabilities.

---

## 1. Collection

Articles are gathered from a configurable set of sources on a scheduled or on-demand basis. Each **monitoring topic** (e.g. "AI Governance", "Indo-Pacific Security", "Open Science Policy") defines its own keywords, source providers, and collection frequency.

### Sources

| Provider | Coverage | Authentication |
|----------|----------|----------------|
| NewsAPI | Global mainstream news | API key |
| TheNewsAPI | Global news, different index | API key |
| Newsdata.io | 70+ language coverage | API key |
| ArXiv | Pre-print scientific literature | Open |
| Semantic Scholar | Peer-reviewed academic papers | Open |
| Bluesky | Social signals & expert commentary | OAuth |
| NewsFirehose | High-volume aggregated feed | API key |

### Deduplication

When multiple providers return the same article, duplicates are resolved by prioritising the source with the richest metadata (e.g. full-text content, structured publication dates). URL normalisation ensures the same article from different syndication paths is recognised as one item.

---

## 2. Multi-Dimensional Article Enrichment

Every collected article passes through a structured enrichment pipeline that annotates it across eight analytical dimensions before it becomes available for analysis.

### 2.1 Relevance Filtering

Before investing in full enrichment, each article undergoes a lightweight relevance check against its monitoring topic:

1. **Embedding similarity** — The article's title and summary are encoded as a vector and compared to the topic's semantic profile (description + keywords). This works for any topic with zero training data.
2. **Fine-tuned classifier** — Where sufficient labelled data exists, a trained binary classifier provides a higher-precision relevance score.
3. **LLM adjudication** — When the first two methods produce ambiguous scores (the 0.3–0.7 range), a language model reads the article and makes an explicit relevance judgment.

Articles below the configurable relevance threshold are archived separately — they are never discarded, but they do not enter the enrichment pipeline or appear in analyses.

### 2.2 Content Acquisition

Articles that pass relevance filtering are scraped for their full text. A local cache ensures each URL is scraped at most once. Content is truncated to approximately 16,000 tokens to remain within language model context limits.

### 2.3 Classification Taxonomy

Each article is classified across four dimensions using a fine-tuned DeBERTa transformer model (345M parameters, trained on platform-specific labelled data):

**Sentiment** — The dominant framing of the article:
- Positive, Neutral, Negative, Concerned

**Time to Impact** — When the described development is likely to materialise:
- Immediate (0–6 months), Short-term (6–18 months), Mid-term (18–60 months), Long-term (60+ months)

**Driver Type** — The article's role in the trajectory of its topic:
- Accelerator, Catalyst, Initiator, Blocker, Inhibitor

**Future Signal** — Domain-specific forward-looking indicators. For geopolitical topics these include: Escalation, De-escalation, Peace agreements, New alliances form, Shifts in regional power balance, Economic collapse imminent, Frozen conflicts persist, among others. For technology topics: AI will accelerate, AI will evolve gradually, and others.

Each classification includes a confidence score. When confidence falls below 0.6, the system falls back to a large language model for that dimension, ensuring quality is maintained at the cost of slightly higher latency.

### 2.4 Source Credibility Assessment

Two complementary assessments of source reliability:

**Media Bias Profile** (automated lookup against Media Bias/Fact Check data):
- Political bias (Left through Right on a 6-point spectrum)
- Factual reporting rating (Very High → Very Low)
- Credibility rating
- Media type and press freedom context

**Factuality Assessment** (LLM-evaluated per article):
- Evidence of sourcing (named sources, data citations, expert quotes)
- Methodology transparency
- Separation of reporting from opinion
- Rated on a 5-point scale: Very High, High, Mixed, Low, Very Low

### 2.5 Summarisation & Tagging

A language model generates:
- A concise summary (typically 50 words) calibrated to a neutral, informative tone
- 3–5 keyword tags extracted via KeyBERT
- A topic-specific category drawn from a user-defined ontology (e.g. for a geopolitics topic: "Diplomacy", "Military", "Economic Sanctions", "Human Rights")
- Explanatory text for the time-to-impact and driver-type classifications, providing the reasoning behind each label

### 2.6 Vector Embedding

The enriched article (title + summary) is encoded as a vector and stored in PostgreSQL with pgvector. This enables semantic search — finding articles by meaning rather than keyword match — which underpins the research and foresight features described below.

The encoder is tenant-dependent, and the vector width must match the tenant's `articles.embedding` column exactly. Two configurations are in use (verified 2026-08-02):

- **Local DeBERTa encoder, 768 dimensions** — bugfixing, wileytest, wbm. The default. No external call, and no fallback: it raises rather than writing a fabricated vector.
- **OpenAI `text-embedding-3-small`, 1,536 dimensions** — wiley only, and the last tenant on this path. Article text is sent to OpenAI for this step. If the call fails, the store returns a random vector rather than raising; see the gotcha in `AI_DESIGN_PATTERNS.md` §3.1.

Vectors from the two encoders are not comparable. Cosine distance between a 768-d and a 1536-d space is meaningless, which is why the width is enforced at the column and a mismatch fails loudly rather than degrading.

---

## 3. Contextualisation: Profiles, Ontologies & Analysis Prompts

Three interrelated systems ensure that every analysis is both structurally rigorous and strategically relevant to the organisation consuming it: **organisational profiles** provide strategic context, **topic ontologies** provide classification structure, and **analysis prompts** wire them together into coherent analytical instructions.

### 3.1 Organisational Profiles

An organisational profile captures the strategic identity of the organisation consuming the intelligence. Rather than producing generic analysis, the platform uses the profile to frame all outputs — recommendations, risk assessments, scenario implications — in terms of what the organisation can realistically act on.

**Profile dimensions:**

| Dimension | Purpose | Example (Scientific Publisher) |
|-----------|---------|-------------------------------|
| Industry | Sector context | Academic Publishing |
| Organisation type | Determines action vocabulary | Publisher |
| Key concerns | Prioritises what matters | Research integrity, Open Access transition, AI-generated content |
| Strategic priorities | Anchors recommendations | Content quality, author trust, digital innovation |
| Risk tolerance | Calibrates urgency framing | Medium |
| Innovation appetite | Shapes technology recommendations | Moderate |
| Decision-making style | Adjusts recommendation format | Collaborative |
| Stakeholder focus | Determines whose interests are centred | Researchers, editors, institutions |
| Competitive landscape | Provides positioning context | Springer Nature, Elsevier, SAGE, Taylor & Francis |
| Regulatory environment | Surfaces compliance considerations | GDPR, Plan S, funder mandates |
| Custom context | Captures organisational philosophy | "Committed to balancing traditional publishing values with digital innovation" |

**How profiles shape analysis:**

The same corpus of articles about AI in research, analysed through different organisational profiles, produces fundamentally different outputs:

- **For a scientific publisher**: Recommendations focus on editorial standards for AI-generated content, author disclosure policies, and content platform strategy — actions an editorial board can take.
- **For a funding body**: Recommendations focus on grant conditions, integrity requirements for funded research, and monitoring frameworks — actions a programme officer can implement.
- **For a university**: Recommendations focus on research policy, academic integrity standards, and infrastructure investment — actions a provost or research VP can pursue.

The platform maintains a vocabulary of **organisation-appropriate actions** for each type. A publisher receives recommendations phrased in terms of "editorial board decisions" and "content strategy"; a government body receives "policy development" and "regulatory frameworks"; an NGO receives "advocacy campaigns" and "coalition-building". This prevents the common problem of generic AI analysis that recommends actions the reader has no authority to take.

### 3.2 Topic Ontologies

Each monitoring topic defines its own **classification ontology** — a structured vocabulary that articles are classified into during enrichment. This is not a flat tagging system; it is a multi-dimensional analytical framework specific to the domain being monitored.

**Ontology dimensions per topic:**

| Dimension | What it captures | Example: Geopolitical Hotspots |
|-----------|-----------------|-------------------------------|
| **Categories** | What type of development is this? | Diplomacy, Military Action, Economic Sanctions, Humanitarian Crisis, Arms Proliferation, Territorial Dispute |
| **Future signals** | What forward-looking indicator does this represent? | Escalation, De-escalation, New alliances form, Shifts in regional power balance, Frozen conflicts persist |
| **Sentiment** | What is the dominant framing? | Positive, Neutral, Negative, Concerned |
| **Time to impact** | When will consequences materialise? | Immediate (0–6 months), Short-term (6–18 months), Mid-term (18–60 months), Long-term (60+ months) |
| **Driver type** | How is this driving change? | Accelerator, Catalyst, Initiator, Blocker, Inhibitor |

Ontologies are topic-specific because useful categories differ fundamentally across domains. The categories that matter for "Patent Cliffs" (Generic Entry, Biosimilar Approval, Loss of Exclusivity) are entirely different from those for "Attacks on Expertise" (Paper Mills, Predatory Journals, Anti-Science Rhetoric, Retraction Events). A single generic taxonomy would either be too broad to be useful or too narrow to cover the range of monitored topics.

**Ontology-driven classification** means that when an article about a new biosimilar approval enters the system, it is not just tagged generically as "healthcare news" — it is classified as category: *Generic Entry*, driver type: *Catalyst*, time to impact: *Immediate*, future signal: *Loss of exclusivity accelerating*. This structured metadata is what enables the foresight lenses (Section 4) to weight and filter articles meaningfully.

### 3.3 Analysis Prompts

Analysis prompts are versioned templates that instruct the language model on how to synthesise articles into strategic intelligence. They are the mechanism through which organisational profiles and topic ontologies are combined into a coherent analytical frame.

**Prompt architecture:**

Each foresight analysis (Consensus, Strategic, Signals, Timeline, Horizons) has its own prompt template. At analysis time, the template is populated with:

1. **Topic ontology** — The valid categories, future signals, sentiment values, driver types, and time-to-impact categories for the topic being analysed. This constrains the model to classify and reference developments using the domain's own vocabulary.

2. **Organisational context** — The full profile injected as analytical framing: who the organisation is, what they care about, what actions are within their scope, and what regulatory constraints apply.

3. **Action vocabulary** — Organisation-type-appropriate language for recommendations (see Section 3.1).

4. **Article corpus** — The selected articles with their enrichment metadata (sentiment, category, driver type, source credibility, bias profile), formatted for the model to reference by citation number.

5. **Analytical instructions** — Lens-specific guidance (e.g., for Consensus: identify areas of broad agreement across independent sources; for Signals: surface emerging changes not yet reflected in consensus).

**Consistency control:**

Analysis prompts support four temperature settings that control the balance between reproducibility and analytical creativity:

| Mode | Temperature | Use case |
|------|-------------|----------|
| Deterministic | 0.0 | Audit-grade reproducibility; same inputs produce same outputs |
| Low variance | 0.2 | Consistent analysis with minimal variation between runs |
| Balanced | 0.4 | Default; good balance of consistency and analytical nuance |
| Creative | 0.7 | Exploratory analysis; surfaces more novel interpretations |

Lower temperatures are appropriate for compliance-sensitive contexts or when tracking how analysis changes over time. Higher temperatures are useful for brainstorming sessions or when seeking perspectives the analyst might not have considered.

### 3.4 How They Work Together

When an analyst requests a foresight analysis — say, Anticipate's Consensus lens for "Patent Cliffs" using the Wiley publisher profile — the system:

1. **Loads the topic ontology** for Patent Cliffs: categories like Generic Entry, Biosimilar Approval, Patent Term Extension; future signals like Loss of Exclusivity Accelerating; driver types like Catalyst, Blocker.

2. **Loads the organisational profile** for Wiley: a scientific publisher concerned with journal portfolio strategy, competitor positioning, and the impact of patent expirations on pharmaceutical research publishing volumes.

3. **Selects and weights articles** using the Consensus lens criteria (high credibility, 30–180 day recency, multi-source convergence), with each article carrying its ontology classifications as structured metadata.

4. **Assembles the analysis prompt** by injecting the ontology values (constraining what the model can classify), the organisational context (framing who the analysis serves), and the article corpus (providing the evidence base).

5. **Generates the analysis** with the language model operating within these constraints — producing consensus themes that use Patent Cliffs vocabulary, cite specific articles, and recommend actions appropriate for a publisher's strategic scope.

The result is analysis that is simultaneously **domain-specific** (using the right categories), **organisation-relevant** (framed for the right reader), and **evidence-based** (grounded in cited source material).

---

## 4. Foresight Analysis: Anticipate

The Anticipate module is the platform's primary foresight tool. It takes enriched articles for a given topic and time window and synthesises them through **five complementary analytical lenses**, each designed to answer a different strategic question.

### 4.1 The Five Lenses

**Consensus** — *"What is there broad agreement about?"*
Identifies themes where multiple independent sources converge on similar conclusions. Prioritises high-credibility sources and articles in the 30–180 day range (long enough for patterns to emerge, recent enough to be current). Useful for establishing baseline assumptions and identifying conventional wisdom.

**Strategic** — *"What are the most important long-term implications?"*
Surfaces authoritative, analytical content with high factual reporting scores. Emphasises in-depth, long-form analysis over breaking news. Weighted toward quality and credibility over recency. Useful for board-level briefings and strategic planning cycles.

**Signals** — *"What is changing right now that we should pay attention to?"*
Applies extreme recency bias (strongest weight to the last 30 days). Boosts articles tagged with future-signal classifications and immediate/short-term time-to-impact. Designed to surface early indicators before they enter mainstream consensus. Useful for horizon scanning and early warning.

**Timeline** — *"How is this situation evolving over time?"*
Weights articles for temporal diversity and time-to-impact metadata, reconstructing the causal sequence of developments. Favours articles in the 60–180 day sweet spot that provide enough historical depth. Useful for understanding trajectory and pace of change.

**Horizons** — *"What futures are becoming possible?"*
Prioritises speculative and forward-looking content, future-signal classifications, and long-term time horizons. Recency matters less than the article's orientation toward future states. Useful for scenario planning and identifying emerging possibilities.

### 4.2 Article Weighting & Selection

For each lens, the system scores every article in the corpus against lens-specific criteria (recency, credibility, signal type, time horizon, etc.) and selects the highest-scoring 75–150 articles. For models with extended context windows (1M+ tokens), the sample increases to 200–300 articles to provide richer evidence.

The language model receives the selected articles with structured metadata — source, date, sentiment, driver type, time-to-impact, future signal, bias profile, and credibility — enabling it to weight evidence appropriately in its synthesis.

### 4.3 Output

Each lens produces:
- Identified themes with supporting evidence
- Key insights and strategic implications
- Source attribution throughout

Results are cached and versioned, allowing analysts to compare how the picture changes over time as new articles enter the corpus.

---

## 5. Foresight Analysis: Extreme Outlier Detection

The Extreme Outlier module complements Anticipate's consensus-based analysis by specifically hunting for **tail risks, black swans, and contrarian scenarios** — the high-impact, low-probability events that standard trend analysis tends to filter out.

It operates through a four-stage pipeline with progressively increasing analytical creativity:

### Stage 1: Weak Signal Extraction (Low creativity)

The system scans existing trend analyses and article corpora for:
- Anomalies — data points that contradict the dominant narrative
- Contradictions — sources that disagree with each other on key facts
- Minority views — perspectives held by few but potentially credible sources
- Overlooked patterns — correlations or trends not surfaced in consensus analysis

### Stage 2: Amplification Pathway Modelling (Moderate creativity)

Each weak signal is examined for potential cascade effects: how could this faint signal be amplified into a major disruption? The system maps causal chains and identifies multiplier effects — feedback loops, contagion pathways, and tipping points that could transform a marginal development into a systemic event.

### Stage 3: Scenario Construction (Higher creativity)

Weak signals and amplification pathways are composed into detailed extreme scenarios across three categories:

- **Black Swans** — High-impact events with no historical precedent
- **Contrarian Scenarios** — Outcomes that contradict current expert consensus
- **Wild Cards** — Low-probability events that would reshape the strategic landscape

Each scenario includes: trigger events, impact rating (1–10), time horizon (near/mid/long-term), probability assessment, and source evidence.

### Stage 4: Strategic Implications & Early Warning (Focused creativity)

For each scenario, the system generates:
- **Early warning signs** — Observable indicators that would suggest the scenario is becoming more likely
- **Strategic implications** — What the scenario would mean for organisations operating in this space
- **Hedging recommendations** — Preparatory actions that make sense even if the scenario never materialises

The methodology deliberately varies analytical temperature across stages — constrained and evidence-close for signal detection, progressively more creative for scenario construction, then focused again for actionable recommendations.

---

## 6. Emerging Topics Detection

The platform continuously monitors for **genuinely new themes** that don't fit existing topic categories — topics that are forming but haven't yet been named or recognised.

### Detection Methodology

1. **Novelty scoring** — Article embeddings are compared against historical baselines. Articles scoring above 70% novelty (i.e., semantically distant from all prior content) are flagged as potential seeds of new themes.

2. **Theme proposal** — A language model analyses the high-novelty articles and proposes candidate themes, each with a label, description, key entities, and an explanation of why the theme appears to be emerging.

3. **Validation** — Semantic search assigns additional articles to proposed themes. Themes must meet minimum thresholds: at least 3 supporting articles, internal semantic coherence (maximum pairwise distance of 0.40), and distinctness from other themes (merge threshold 0.60).

4. **Deep analysis** — Validated themes receive full analysis across five dimensions: actors involved, events driving emergence, strategic implications, forward-looking signals, and a narrative synthesis.

5. **Trend scoring** — Each emerging topic is tracked over time with metrics for volume (article count), velocity (acceleration), diversity (source breadth), and novelty (distinctiveness). These produce a composite trend score and trajectory classification: rising, stable, declining, or volatile.

---

## 7. Observer Agents (Automated Signal Monitoring)

Analysts can define **custom detection rules** in natural language — essentially describing a specific threat, opportunity, or development they want to watch for. These rules are executed automatically on a configurable schedule.

### How It Works

1. **Signal definition** — The analyst writes a natural-language instruction describing what to watch for (e.g., *"Monitor for any indication that Country X is preparing economic sanctions against Country Y, including diplomatic rhetoric, trade data anomalies, or leaked policy documents"*).

2. **Scheduled execution** — The system searches recent articles using semantic search, then evaluates each article against the signal definition using a language model.

3. **Per-article assessment** — Each article receives:
   - Signal detected (yes/no)
   - Confidence score (0–1)
   - Threat level (low/medium/high)
   - Reasoning explaining why the article does or doesn't match
   - Recommended action

4. **Alerting** — Articles matching the signal above the confidence threshold generate alerts with full attribution. Notifications can be delivered via email or social channels.

5. **Reporting** — Each run can optionally produce an intelligence summary synthesising all matches into a briefing.

Observer agents provide a structured, repeatable approach to **threat hunting** across the article corpus — turning analyst intuition into automated, continuous monitoring.

---

## 8. Deep Research (Auspex)

Auspex is a conversational research interface that allows analysts to interrogate the enriched article corpus through natural-language dialogue.

### Capabilities

- **Multi-strategy search** — Queries are routed through semantic (meaning-based), keyword (term-based), and hybrid search strategies. A single analyst question may generate 3–5 related queries to ensure comprehensive retrieval.

- **Adaptive depth** — The system classifies each query as quick (2–4 sentence answer), standard (150–300 words), or deep (400–800 words with extensive citation), and adjusts the number of articles retrieved and the level of synthesis accordingly.

- **Citation discipline** — Every factual claim in a response must be attributed to a specific source article. Citation density scales with query depth: 1–2 sources for quick answers, up to 25 for deep research.

- **Conversation memory** — Multi-turn conversations maintain context. When conversations grow long, earlier turns are automatically summarised to preserve key facts while staying within model context limits.

- **Source credibility integration** — The bias and factuality metadata from enrichment is available to the language model, allowing it to weight evidence and flag when conclusions rest on lower-credibility sources.

---

## 9. Inference Architecture: Cost, Speed & Quality Trade-offs

The platform supports three inference modes that control the balance between local processing and cloud language model usage:

**Local mode** — All classification via DeBERTa; all generation via locally-hosted Qwen/Phi-3 models through vLLM. Zero cloud API cost. Best for privacy-sensitive deployments or high-volume processing where cost control is paramount.

**Hybrid mode** (default) — Classification via DeBERTa with cloud LLM fallback for low-confidence cases; generation via cloud models. Balances cost and quality — the local classifier handles the majority of articles, with the LLM stepping in only when needed.

**External mode** — All processing via cloud language models (GPT-4o-mini or configured alternative). Highest quality, highest cost. Best for low-volume, high-stakes analysis.

The platform tracks confidence statistics and cost metrics for each mode, allowing operators to monitor the proportion of articles handled locally versus via cloud API and adjust thresholds accordingly.

---

## 10. Domain-Specific Analysis Modules

The platform includes pluggable analysis modules that provide specialised intelligence for specific domains:

| Module | Domain | Analytical Focus |
|--------|--------|-----------------|
| **GeoHotSpots** | Geopolitics | Regional conflict dynamics, volatility mapping, destabilisation indicators |
| **US Crisis Tracker** | US Policy | Executive actions, agency responses, policy evolution timelines |
| **ScienceWatch** | Research & Innovation | Funding flows, R&D policy changes, research trend detection |
| **Brand Watcher** | Competitive Intelligence | Multi-brand sentiment tracking, competitive positioning, reputation monitoring |

Modules can be enabled or disabled per deployment without code changes, allowing each tenant to configure the platform for their domain focus.

---

## Summary: From Collection to Foresight

```
COLLECTION
  Multi-source scheduled gathering (7 providers, per-topic configuration)
       |
ENRICHMENT
  Relevance filtering -> Content acquisition -> Classification (8 dimensions)
  -> Source credibility assessment -> Summarisation -> Vector embedding
       |
ANALYSIS
  |
  |-- ANTICIPATE: Five-lens trend synthesis
  |     Consensus | Strategic | Signals | Timeline | Horizons
  |
  |-- EXTREME OUTLIER: Four-stage tail-risk analysis
  |     Weak signals -> Amplification -> Scenarios -> Early warning
  |
  |-- EMERGING TOPICS: Novelty detection & theme formation
  |     Novelty scoring -> Theme proposal -> Validation -> Trend tracking
  |
  |-- OBSERVER AGENTS: Custom automated threat hunting
  |     Signal definition -> Scheduled execution -> Per-article assessment -> Alerts
  |
  |-- AUSPEX: Conversational deep research
        Multi-strategy search -> Adaptive synthesis -> Cited analysis
```

The methodology is designed to surface both **convergent signals** (what most sources agree on) and **divergent signals** (weak signals, contrarian views, emerging themes) — recognising that strategic foresight requires attention to both the consensus view and the outliers that may reshape it.
