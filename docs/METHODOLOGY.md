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

Every collected article passes through a structured enrichment pipeline before it becomes available for analysis. The pipeline checks the article's relevance, then gives it a topic category, four forward-looking classifications, a summary, tags, and the credibility profile of its source.

### 2.1 Relevance Filtering

Before investing in full enrichment, each article undergoes a lightweight relevance check against its monitoring topic:

1. **Embedding similarity** — The article's title and summary are encoded as a vector and compared to the topic's semantic profile (description + keywords). This works for any topic with zero training data.
2. **Fine-tuned classifier** — Where a trained relevance classifier is available, it scores the article against the topic and is combined with the similarity score.
3. **Adjudication of unclear cases** — A combined score below 0.20 or above 0.85 is treated as a confident answer. Anything in between goes to a further check. Where enabled, a compact judgment model first accepts articles that are clearly on topic. Otherwise a language model reads the article and gives an explicit relevance score, which replaces the uncertain one.

Articles below the configurable relevance threshold are archived separately — they are never discarded, but they do not enter the enrichment pipeline or appear in analyses. A second relevance check runs after enrichment, on the enriched summary, and can still set an article aside.

### 2.2 Content Acquisition

When a source supplies only a headline or a very short snippet, the platform fetches the full article page. This happens as the article arrives, before relevance filtering. A local cache ensures each URL is fetched at most once.

The classification step (Section 2.3) reads the summary or text supplied by the source. The fetched page is used in two places: as the input to classification when the source supplied no text at all, and as the input to the vector embedding (Section 2.6).

### 2.3 Classification Taxonomy

Each article is read by a large language model, which classifies it across four dimensions in a single pass. The model is given the topic's own list of allowed values for each dimension (see Section 3.2) and must choose from it:

**Sentiment** — The dominant framing of the article. The values are set per topic; most topics use:
- Positive, Neutral, Negative

**Time to Impact** — When the described development is likely to materialise:
- Immediate (0–6 months), Short-term (6–18 months), Mid-term (18–60 months), Long-term (60+ months)

**Driver Type** — The article's role in the trajectory of its topic:
- Accelerator, Catalyst, Initiator, Blocker, Inhibitor

**Future Signal** — Domain-specific forward-looking indicators. For geopolitical topics these include: Escalation, De-escalation, Peace agreements, New alliances form, Shifts in regional power balance, Economic collapse imminent, Frozen conflicts persist, among others. For technology topics: AI will accelerate, AI will evolve gradually, and others.

Every answer is checked against the topic's list. A category or future signal outside the list is recorded as "Other". A sentiment, time to impact or driver type outside the list is left blank rather than guessed. If the model's reply cannot be read, the platform tries again, making up to three attempts in all, before marking the article as failed.

### 2.4 Source Credibility Assessment

Source reliability is assessed at the level of the outlet, not the individual article.

**Media Bias Profile** (automated lookup against Media Bias/Fact Check data):
- Political bias (Left through Right on a 6-point spectrum)
- Factual reporting rating (Very High → Very Low)
- Credibility rating
- Media type and press freedom context

The lookup matches the article's domain against the dataset. Outlets that the dataset does not cover carry no profile, so a blank rating means "not rated" rather than "low". The platform does not store a separate per-article factuality rating.

### 2.5 Summarisation & Tagging

The same language model pass that classifies the article (Section 2.3) also generates:
- A concise summary (about 50 words) in a neutral, informative tone
- 3–5 tags describing the article's main themes, to which the platform adds the monitoring keywords that matched the article at collection, so an article stays findable by the terms that brought it in
- A topic-specific category drawn from a user-defined ontology (e.g. for a geopolitics topic: "Diplomacy", "Military", "Economic Sanctions", "Human Rights")
- A one- or two-sentence explanation for each of the four classifications (sentiment, time to impact, driver type and future signal), giving the reasoning behind each label

Headlines in other languages are translated into English, and the original headline is kept alongside.

### 2.6 Vector Embedding

Each article that passes enrichment is encoded as a vector and stored in PostgreSQL with pgvector. This enables semantic search — finding articles by meaning rather than keyword match — which underpins the research and foresight features described below.

The encoder input is the article's title, its tags, and the full fetched page where one exists (otherwise the summary). Putting the tags first means the matched keywords still count when a long article has to be shortened to fit the encoder.

The encoder is a transformer model hosted on the platform's own servers, producing 768-dimension vectors. Article text is not sent to an outside service for this step. If the encoder is unavailable, the platform writes no vector rather than a substitute one, because a substitute vector would distort every search that touched it.

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
| **Sentiment** | What is the dominant framing? | Positive, Neutral, Negative |
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

- **Source credibility integration** — The outlet-level bias and factual-reporting ratings from enrichment are available to the language model, allowing it to weight evidence and flag when conclusions rest on lower-credibility sources.

---

## 9. Inference Architecture: Cost, Speed & Quality Trade-offs

The platform splits its work between models that run on its own servers and language models hosted by a managed cloud AI service:

- **On the platform's own servers:** the vector encoder (Section 2.6), the similarity model and the trained relevance classifier (Section 2.1).
- **Cloud-hosted language models:** classification, summarisation and tagging (Sections 2.3–2.5), the adjudication of unclear relevance cases, and the analysis and research features described in Sections 4–8.

An inference mode setting controls how much of the **relevance check** uses a cloud language model. It does not change the classification and summarisation step, which always uses the configured cloud model.

**Local mode** — The relevance check uses only the local similarity model and classifier. Unclear cases are decided on the local score alone.

**Hybrid mode** (default) — The local models decide the confident cases, and a cloud language model adjudicates the unclear ones (Section 2.1).

**External mode** — A cloud language model scores the relevance of every article. This costs the most and is mainly useful for comparing against the hybrid results.

The platform logs every language model call with its token usage and cost, so operators can see where model spend goes.

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
  Content acquisition -> Relevance filtering -> Source credibility lookup
  -> Classification, summary & tags (one language model pass)
  -> Second relevance check -> Vector embedding
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
