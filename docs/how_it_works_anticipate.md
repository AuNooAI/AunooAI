# How the Anticipate foresight stack works

`/anticipate` is the navigation label; the page itself is served from
`GET /trend-convergence` (`app/routes/trend_convergence_routes.py:2591`,
template `templates/trend_convergence_react.html`, React root `ui/src/App.tsx`).
The nav mapping lives in `templates/shared_navigation.html:19` and
`ui/src/components/SharedNavigation.tsx:104` (`currentPage === 'anticipate'`).
The literal `/anticipate` path appears in-repo only in outbound email links
(`app/routes/email_routes.py:1822,1884`) — the alias itself is nginx-side,
outside the repo.

Router registration: `app/core/routers.py:40-43` mounts
`futures_cone_router`, `trend_convergence_router`,
`forecast_assessment_router`, `topic_report_router`.

> **Not to be confused with** `saasmvp-app/`, which is a separate
> application with its own consensus/horizons implementation
> (`saasmvp-app/app/newsfeed/{consensus_service,horizons_service}.py`,
> `saasmvp-app/app/foresight/`). Nothing on this page describes that tree.

This page documents the foresight subsystems the tab exposes:

| Tab id | Label | Backing subsystem |
| --- | --- | --- |
| `consensus` | Consensus Analysis | Lens pipeline (`consensus_analysis` prompt) |
| `future-horizons` | Future Horizons | Lens pipeline (`future_horizons` prompt, Three Horizons) |
| `topics` | Topics | `forecast_topic_metadata` + candidate discovery |
| `forecast-tracker` | Forecast Tracker | `forecast_assessment_service` back-test |
| `topic-reports` | Topic Reports | `topic_report_service` → PPTX/MD/HTML/DOCX |

Tab registry: `ui/src/components/TabNavigation.tsx:23-104`.

Two neighbouring subsystems already have their own pages —
[Topics](how_it_works_topics.md) covers candidate discovery and the
Add-topic wizard in depth, [Forecast Tracker](how_it_works_forecast_tracker.md)
covers the assessment narrative. This page is the code-level view and the
single place where the lens pipeline (shared by Consensus and Horizons)
is written down.

---

## 1. The shared lens pipeline

Consensus Analysis and Future Horizons are not separate pipelines. They
are two of six **lenses** over one generation path, differing only in
(a) which articles get selected and (b) which prompt template is loaded.

The six lenses, and the prompt directory each maps to
(`app/routes/trend_convergence_routes.py:3135-3147`):

```
consensus            → consensus_analysis
strategic            → strategic_recommendations
signals              → market_signals
timeline             → impact_timeline
horizons             → future_horizons
intelligence-brief   → intelligence_brief
```

Entry point is a single endpoint:

```
GET /api/trend-convergence/{topic}
    ?model=&timeframe_days=&sample_size_mode=&custom_limit=
    &profile_id=&consistency_mode=&persona=&customer_type=&tab=
```
`app/routes/trend_convergence_routes.py:564`

Full query-parameter set (`trend_convergence_routes.py:566-582`):
`timeframe_days=365`, `model` (required), `source_quality`,
`sample_size_mode`, `custom_limit`, `persona=executive`,
`customer_type=general`, `consistency_mode`, `enable_caching=True`,
`cache_duration_hours=24`, `profile_id`, `tab`, `cache_only=False`.

### 1.1 Stage 0 — cache key

`generate_comprehensive_cache_key()` (`trend_convergence_routes.py:2447-2487`):

```python
cache_params = {..., 'tab': tab,
    'algorithm_version': '4.0',
    'article_selection_method': 'deterministic_v2'}
params_string = json.dumps(cache_params, sort_keys=True, default=str)
cache_hash = hashlib.sha256(params_string.encode()).hexdigest()[:16]
return f"trend_convergence_{cache_hash}"
```

Read at `:2489-2524` (hit iff `age_hours <= max_age_hours`), write at
`:2526-2562`, both into `analysis_versions_v2`. Bumping
`algorithm_version` is the global cache-bust lever.

### 1.2 Stage 1 — corpus pull

`get_articles_with_dynamic_limit()`
(`app/database_query_facade.py:550-610`) selects
`title, summary, uri, publication_date, sentiment, category,
future_signal, driver_type, time_to_impact` from `articles`
LEFT JOIN `raw_articles` (for `raw_markdown`), filtered
`analyzed = True`, `summary != ''`, date range, `topic == topic`
(skipped for the `__all__` pseudo-topic). In `deterministic` and
`low_variance` modes `fetch_multiplier = 2` so the deterministic selector
downstream has headroom (`:567`).

Optional source-quality gate (`trend_convergence_routes.py:141`): when
`source_quality='high_quality'`, an article survives only if
`factual_reporting ∈ {High, Very High}` **and**
`mbfc_credibility_rating ∈ {High, Very High}`.

Optional cross-encoder pre-filter (`:680-690`), when reranking is enabled:
```python
rerank_query = f"{topic} emerging trends convergence strategic signals"
top_k = min(len(filtered_articles), optimal_sample_size * 2)
```

### 1.3 Stage 2 — lens weighting

`weight_articles_for_dashboard(articles, dashboard_type)`
(`trend_convergence_routes.py:168-301`) assigns each article an additive
score, then sorts descending. These are the actual scoring rules:

**`consensus`** — favours corroborated, credible, settled material:
```python
score += float(quality_score) * 2
if mbfc_credibility_rating in ('high','very high'):  score += 5
if 30 <= days_old <= 180:                            score += 3
```
The 30–180 day band is deliberate: recent enough to be current, old
enough that multiple outlets have converged on a reading.

**`horizons`** — favours forward-looking, long-dated material:
```python
if future_signal:                                    score += 8
if 'long' in time_to_impact or 'mid' in time_to_impact: score += 6
if days_old <= 180:                                  score += 2
```
Note recency is worth 2 here versus 10 on the `signals` lens — for
horizons, an article's *orientation toward the future* outranks its age.

**`strategic`** — authority-weighted:
```python
if factual_reporting in ('high','very high'):        score += 5
if mbfc_credibility_rating in ('high','very high'):  score += 5
score += float(quality_score) * 3
if days_old <= 365:                                  score += 2
```

**`signals`** — extreme recency bias:
```python
days_old <= 30  → +10 ;  <= 90 → +7 ;  <= 180 → +3
if future_signal:                                    score += 5
if time_to_impact in ('immediate','short-term'):     score += 4
```

**`timeline`** — temporal spread:
```python
if time_to_impact:                                   score += 7
days_old <= 60 → +4 ; <= 180 → +5 ; <= 365 → +3      # 60–180 is the peak
score += float(quality_score) * 2
```

The scored list is written back as `dashboard_score` on each article.

### 1.4 Stage 3 — sample sizing

`calculate_optimal_sample_size(model, sample_size_mode, custom_limit)`
(`trend_convergence_routes.py:111-139`) sizes the sample off the model's
context window, read from `CONTEXT_LIMITS` (`:25-60` — gpt-5.5 and
gpt-4.1* at 1 000 000; gpt-5.4 at 400 000; claude-* at 200 000; default
16 385). `is_mega_context` is `context_limit >= 1_000_000`.

| mode | mega-context | normal |
| --- | --- | --- |
| `focused` | 50 | 25 |
| `balanced` | 100 | 50 |
| `comprehensive` | 200 | 100 |
| `auto` (default) | `150 × 1.2 = 180` | `75 × 1.2 = 90` |

Clamped to `[20, 1000]` for mega-context models and `[20, 400]`
otherwise.

### 1.5 Stage 4 — deterministic selection

`select_articles_deterministic(articles, limit, consistency_mode)`
(`trend_convergence_routes.py:1626-1700`) makes reruns reproducible:

1. Each article gets a stable MD5 over `title|publication_date|category`,
   truncated to 8 hex chars (`:1645`).
2. In `deterministic`/`low_variance`, the sort key is
   `(category, publication_date, hash)`. Otherwise
   `(recency_score, hash)` descending.
3. **60 % of the budget is category-quota'd**: `category_quota = int(limit * 0.6)`,
   `articles_per_category = max(1, category_quota // n_categories)`
   (`:1675-1676`). This is what prevents a single dominant category from
   swamping the sample.
4. The remaining 40 % is filled by `(recency_score, hash)` descending.

### 1.6 Stage 5 — consistency mode

`ConsistencyMode` (`trend_convergence_routes.py:63-67`):

| Mode | Temperature |
| --- | --- |
| `deterministic` | 0.0 |
| `low_variance` | 0.2 |
| `balanced` (default) | 0.4 |
| `creative` | 0.7 |

Beyond temperature, `enhance_prompt_for_consistency` (`:2381-2414`)
appends explicit CONSISTENCY REQUIREMENTS / GUIDELINES blocks for the two
strictest modes, and `apply_consistency_post_processing` (`:2416-2444`)
regex-normalises the output vocabulary for those same two modes — e.g.
`r'\b(very high|extremely high)\b' → 'High'`,
`r'\b(growing|rising|expanding)\b' → 'Increasing'`. This is what makes
`deterministic` reruns comparable at the string level, not just the
sampling level.

### 1.7 Stage 6 — prompt assembly

Prompt templates are versioned JSON on disk under `data/prompts/<feature>/`,
with `current.json` as the live version and content-hashed siblings as
history. Loader: `app/services/prompt_loader.py`; management API:
`app/analyzers/prompt_manager.py` (`:250` lists the editable set).

Editable through the UI:
* `GET  /api/trend-convergence/prompt-preview/{tab_name}` — renders the
  fully-substituted prompt (`:3058`)
* `POST /api/trend-convergence/prompts/{tab_name}` — save an override (`:3332`)
* `POST /api/trend-convergence/prompts/{tab_name}/restore-default` (`:3401`)

Each template substitutes: `{org_context}`, `{action_vocabulary}`,
`{topic}`, `{article_count}`, `{articles}` (metadata-annotated corpus),
`{article_references}` (numbered `[N]` citation list), `{prompt_focus}`,
`{org_name}`, `{org_type}`.

`{org_context}` and `{action_vocabulary}` come from the row in
`organizational_profiles` selected by `profile_id` — this is the
mechanism that keeps recommendations inside the reader's actual remit.
Context block assembled at `:795-811`; `get_action_vocabulary()`
(`:1957-2037`) carries distinct verb sets for NGO / Government /
Publisher-Academic / Think-tank / Manufacturing / Financial / General,
and `get_framework_section_name()` (`:1941-1954`) renames the framework
section to match. Profile CRUD:
`GET/POST/PUT/DELETE /api/organizational-profiles*`
(`:2604, :2640, :2680, :2728, :2755`).

Prompt builders per lens: consensus `:1891`, strategic `:2040`,
signals `:2092`, timeline `:2143`, horizons `:2196`,
intelligence brief `:2242`; dispatch at `:815-847`.

### 1.8 Stage 7 — generation and parsing

`generate_analysis_with_consistency()` (`:2348-2379`) routes the call
through Auspex with retrieval tools disabled — the corpus is already
fixed by stages 1–4, so the model must synthesise from what it was given:

```python
async for chunk in auspex_service.chat_with_tools(
    chat_id=chat_id, message=enhanced_prompt, model=model, limit=10,
    tools_config={"search_articles": False, "get_sentiment_analysis": False}):
```

JSON extraction (`:1142-1176`) is a three-stage ladder: fenced-block
regex → `_preprocess_response()` (`:510`) →
`json.JSONDecoder().raw_decode` → `json_repair.loads` fallback.

Post-processing:
* Three Horizons `type ∈ {h1,h2,h3}` validation (`:1244-1257`).
* Consensus sentiment-distribution normalisation (`:1259-1277`) — the
  model is asked for percentages but sometimes returns fractions or raw
  counts:
  ```python
  total = dist['positive'] + dist['neutral'] + dist['critical']
  if 0.9 < total <= 1.1:            dist[k] *= 100          # fractions
  elif 0 < total < 10:              factor = 100.0 / total  # raw counts
  ```
  The same rule is mirrored client-side and in the HTML exporter
  (`app/services/consensus_html.py:121-138`).
* Market-signals quote transformation (`:1279-1332`).

### 1.9 Stage 8 — persistence and cache

Every lens writes the same envelope shape, regardless of which sections
it populates. Top-level keys observed in production:

```
analysis_id, topic, timeframe_days, generated_at, version,
model_used, analysis_depth, consistency_mode, caching_enabled,
persona, customer_type, organizational_profile, source_quality,
articles_analyzed, total_articles_found,
key_insights, convergences, scenarios, impact_timeline,
strategic_recommendations, future_signals, disruption_scenarios,
opportunities, next_steps, executive_decision_framework,
topic_briefing, categories, article_list, metadata
```

A consensus run populates `categories` / `key_insights` / `convergences`;
a horizons run populates `scenarios`. Unpopulated sections are emitted as
empty containers rather than omitted.

Storage:

| Table | Holds |
| --- | --- |
| `consensus_analysis_runs` | id, user_id, topic, timeframe, selected_categories, raw_output, total_articles_analyzed, created_at, analysis_duration_seconds, article_list |
| `consensus_reference_articles` | consensus_id → article_uri join |
| `future_horizons_runs` | id, user_id, topic, model_used, raw_output, total_articles_analyzed, created_at, analysis_duration_seconds |
| `future_horizon_articles` | horizon_id → article_uri join |
| `analysis_versions_v2` | generic keyed cache (`cache_key`, `version_data`, `cache_metadata`, `accessed_at`) — holds both `trend_convergence_{hash}` results and `horizons_exec_summary_{run_id}` cards |
| `trend_consistency_metrics` | per-topic `consistency_score` across repeated runs |
| `saved_dashboards` | all five tab payloads together: `consensus_data`, `strategic_data`, `timeline_data`, `signals_data`, `horizons_data` (JSONB) + `article_uris` + `profile_snapshot` (`database_models.py:73-97`, routes in `app/routes/saved_dashboard_routes.py`) |

The other three lenses persist to `market_signals_runs`,
`impact_timeline_runs` and `strategic_recommendations_runs` with the same
shape (write path `trend_convergence_routes.py:1350-1480`,
`analysis_id = uuid4()`).

> **Gotcha:** `raw_output` is stored *double-encoded* — the column is
> `json`, but the value is a JSON **string** containing the JSON object.
> `jsonb_object_keys(raw_output::jsonb)` fails with
> `cannot call jsonb_object_keys on a scalar`. Use
> `(raw_output #>> '{}')::jsonb`. Application code handles this at
> `forecast_assessment_service.py:102-104`.

Raw-output and article-list read endpoints per lens:
```
GET /api/trend-convergence/{consensus|timeline|strategic|horizons}/{analysis_id}/raw       (:2797, :2835, :2873, :2911)
GET /api/trend-convergence/{consensus|strategic|market-signals|timeline|horizons}/{analysis_id}/articles  (:2953–:3039)
GET /api/trend-convergence/{topic}/previous                                                 (:2573)
GET /api/trend-convergence/models                                                           (:530)
```

---

## 2. Consensus Analysis

**Prompt:** `data/prompts/consensus_analysis/current.json` (v1.0.0)
**Metadata:** `model: gpt-4o`, `temperature: 0.7`, `max_tokens: 4000`,
`response_format: json` — note the *prompt-declared* temperature is
overridden by the request's `consistency_mode`.

**System prompt:**
> You are an expert strategic analyst specializing in evidence synthesis
> and consensus identification. Your role is to analyze multiple sources,
> identify patterns of agreement and disagreement, and quantify the
> strength of consensus across different perspectives.

Builder: `generate_consensus_analysis_prompt()`
(`trend_convergence_routes.py:1891-1937`).

**Mission line:** identify **3–4 major consensus categories** where
trends, forecasts and expert opinions align across sources. The prompt is
explicit that this is *not* a summary — "it's a cross-source analysis
revealing patterns of agreement and disagreement."

### 2.0 The quantification rules

These are the instructions that make the numbers on the cards mean
something rather than being LLM vibes. Verbatim from the user prompt:

```
2. QUANTIFY EVERYTHING ACCURATELY:
   - Consensus confidence = (# sources supporting view) / (total sources) * 100
   - Source percentages for outliers must be realistic (typically 5-25%)
   - Sentiment distribution must sum to 100%
   - Timeline distribution must sum to 100%
   - Count articles_analyzed for each category

5. IDENTIFY OUTLIERS PER CATEGORY (ONLY IF GENUINELY PRESENT):
   - ONLY include outliers if sources genuinely present dissenting views (>5% of sources)
   - May have 0-3 optimistic outliers and 0-3 pessimistic outliers per category
   - DO NOT fabricate outliers if sources show strong consensus

10. CONSENSUS TYPE (1_consensus_type):
   - CRITICAL: Distribution values MUST sum to 100
   - Confidence level should reflect strength of agreement (typically 60-95%)
```

The "DO NOT fabricate outliers" clause matters: without it the model
manufactures a dissenting view for every category because the schema has
a slot for one. Targets: 3–4 categories, 4–6 key insights, 3–5 decision
windows per category.

### 2.1 The nine-field category structure

Each category is emitted with numbered fields (the "Auspex numbered field
structure"), which is what lets the renderer lay them out positionally:

| Field | Contents |
| --- | --- |
| `category_name` | e.g. "AI Safety Consensus" |
| `category_description` | Synthesis with `[n]` citations |
| `1_consensus_type` | `summary` ∈ {Positive Growth, Mixed Consensus, Regulatory Response, Safety/Security, Societal Impact, Technical Advancement, Market Shift}; `distribution` {positive, neutral, critical} as percentages; `confidence_level` 0–100 |
| `2_timeline_consensus` | `distribution` across Immediate / Short-term / Mid-term / Long-term buckets; `consensus_window` {start_year, end_year, label} |
| `3_confidence_level` | `majority_agreement` %, `consensus_strength` ∈ {Strong, Moderate, Emerging}, `evidence_quality` ∈ {High, Medium, Low} |
| `4_optimistic_outliers` | list of {scenario, details, year, source_percentage, reference} |
| `5_pessimistic_outliers` | same shape |
| `6_key_articles` | {title, url, summary, sentiment, relevance_score} |
| `7_strategic_implications` | Framed for `{org_name}` as a `{org_type}` |
| `8_key_decision_windows` | {urgency, window, action, rationale, owner, dependencies, success_metrics} |
| `9_timeframe_analysis` | immediate / short_term / mid_term prose + `key_milestones[]` |

Fields 4 and 5 are the important ones analytically — the prompt forces the
model to name the dissent explicitly with a `source_percentage`, rather
than letting a majority reading present as unanimity.

### 2.2 Citation discipline

The prompt bans prose attributions:

> Use 3-5 citations per category_description to support key claims.
> Do NOT use plain text source names like "(The Hindu, Times of India)"

Every claim resolves to a `[n]` in the numbered `{article_references}`
block, which the renderers hyperlink back to article URLs.

### 2.3 Storage and rendering

`consensus_analysis_runs` (`app/database_models.py:7-20`) with index
`idx_consensus_analysis_user_created(user_id, created_at)`; migrations
`7166c8140b17_add_consensus_analysis_runs_table.py` and
`47bbb2e52c81_add_article_list_to_consensus_analysis_.py`.
`consensus_reference_articles` (`:948-957`) holds the numbered corpus.
Facade: `save_consensus_analysis` (`database_query_facade.py:7494`),
`get_consensus_analysis` (`:7548`),
`save_consensus_reference_articles` (`:10201`).

**Frontend:** `ui/src/components/foresight/ConsensusView.tsx` is the
current renderer (accordion, sentiment bars, timeline windows, filter
pills). `foresightAdapters.ts:19-69` (`flattenCategory()`) maps the
numbered-key schema onto the flat view shape and builds the citation map
— that adapter is why the numbered keys never leak into the components.
`ConsensusCategoryCard.tsx` and `templates/consensus_analysis.html` are
the legacy card and pre-React page respectively. Rendered at
`App.tsx:2550-2620`.

**HTML export:** `GET /api/trend-convergence/consensus/{analysis_id}/download.html`
(`trend_convergence_routes.py:3784-3831`) →
`app/services/consensus_html.py` (`build_consensus_html()` at `:421`).

---

## 3. Future Horizons (Three Horizons)

**Prompt:** `data/prompts/future_horizons/current.json` (v1.0.0)
**Metadata:** `model: gpt-4o`, `temperature: 0.7`, `max_tokens: 3500`.

**System prompt:**
> You are a strategic foresight expert specializing in the Three Horizons
> framework for scenario planning. Your role is to map the transition from
> current paradigms to future possibilities, identifying what's declining,
> what's emerging, and what's transforming.

### 3.1 Framework definitions (verbatim from the prompt)

* **H1 — Current Paradigm/Declining.** "The dominant paradigm today.
  Current established practices and systems that are gradually declining
  as new innovations emerge. Represents what's working now but won't
  sustain long-term."
* **H2 — Transition/Innovation.** "Emerging innovations and disruptions.
  Innovative initiatives, experimental approaches, and the transitional
  period where old and new systems coexist."
* **H3 — Future Vision/Emerging.** "Transformative visions becoming
  reality. The preferred future state where new paradigms are fully
  established. Represents radical departures from current norms."

### 3.2 Enforced distribution and timeframes

```
4-5 H1 scenarios   timeframes 2025-2032
4-5 H2 scenarios   timeframes 2027-2037 (peak 2030-2033)
3-4 H3 scenarios   timeframes 2033-2040
Total: 12-14 scenarios
```

The overlapping bands are intentional — they produce the H1→H2→H3
transition arc the chart renders rather than three disjoint blocks.

### 3.3 Scenario object

```json
{
  "type": "h1|h2|h3",
  "title": "max 12 words",
  "description": "2-3 sentences with inline [1] [2] citations",
  "timeframe": "2025-2040",
  "sentiment": "Positive|Negative|Mixed|Neutral|Mixed/Positive|Critical/Neutral|
                Negative/Disruptive|Trend/Evolution|Breakthrough|
                Disruption/Warning|Warning/Disruption"
}
```
Persisted scenarios also carry `probability`, `driver_connection` and
`icon` in some runs. Every description must cite 2–4 articles.

Production distribution across `future_horizons_runs` on wileytest:
368 h1 / 364 h2 / 251 h3. A second scenario vocabulary
(`probable` / `plausible` / `possible` / `preferable`) appears in runs
seeded by the Add-topic wizard's `emerging_topic_driver.json` prompt —
the futures-cone variant used for candidate promotion.

Builder `generate_future_horizons_prompt()`
(`trend_convergence_routes.py:2196-2239`) caps the article-reference block
at the first 50 articles (`:2220`).

A third prompt lives in the same directory —
`emerging_topic_driver.json` — which uses the **Futures Cone** vocabulary
(`probable | plausible | possible | preferable`, 10–14 scenarios, plus a
`driver_connection` field) instead of H1/H2/H3. It is invoked from
`app/routes/emerging_topics_routes.py:1750` and by the Add-topic wizard's
promotion path, which is why both scenario vocabularies show up in
`future_horizons_runs`.

### 3.4 Executive Summary cards

A second LLM round produces the "Strategic Consensus" cards shown on the
tab:

```
POST /api/trend-convergence/horizons/{analysis_id}/executive-summary   (:3458-3608)
GET  /api/trend-convergence/horizons/{analysis_id}/executive-summary   (:3611-3644)
```

Prompt: `data/prompts/future_horizons/executive_summary.json` — **v2.1.0**,
`temperature: 0.4`, `max_tokens: 4000`. Verbatim rules:

```
1. Identify 4-6 major thematic clusters across the H1, H2, and H3 scenarios
2. For each cluster, synthesize a consensus view with an estimated percentage
   based on scenario weight/prevalence
3. Identify the minority view (dissenting scenarios) with percentage range
4. Frame decision forks as conditional business outcomes ("If X happens → Y outcome")

- Consensus percentage: Estimate based on how many scenarios support this view
  (typically 70-90%)
- Minority view: The contrarian perspective with percentage range (e.g., "7-12%")
- Decision forks: Frame as "If [condition] →" NOT as "H1 persists" or "H2 executes"
```

That last line is the important one — it forces the cards into business
conditionals rather than framework jargon the reader has no use for.

Per-card output: `topic_title` (ALL CAPS), `primary_horizon`,
`horizon_label` ∈ {Declining System, Transition/Innovation, Future Vision},
`opening_statement`, `consensus_percentage`,
`minority_view{percentage_range, statement}`, `primary_signal`,
`decision_fork{condition_a, condition_b}`,
`action_window{assessment (0-6 months), positioning (6-18 months)}`,
`source_scenarios[]`.

Cached in `analysis_versions_v2` under `horizons_exec_summary_{analysis_id}`
(`database_query_facade.py:9830/:9879`) — **not** a dedicated table.
`generate_executive_summary_for_run()`
(`app/services/topic_report_service.py:347`) reuses the exact prompt and
cache key so the PPTX cards are byte-identical to the React tab's.
Default model `gpt-5.4`.

### 3.5 Storage and rendering

`future_horizons_runs` (`database_models.py:61-71`),
`future_horizon_articles` (`:992-1000` — the numbered corpus that
resolves `[N]`). Facade: `save_future_horizons_analysis` (`:7894`),
`get_future_horizons_analysis` (`:7928`),
`save_future_horizon_articles` (`:10474`).

**Frontend:** `ui/src/components/foresight/HorizonsView.tsx` is the
current renderer. The S-curve geometry is analytic, not data-fitted
(`:56-90`):

```ts
const VW=1000, VH=320, L=24, RR=976, TOP=24, BOT=290, NSEG=160;
function ss(x){ x=clamp01(x); return x*x*(3-2*x); }   // smoothstep
const CURVES = {
  current:    (t) => 0.06 + 0.74 * (1 - ss((t - 0.05) / 0.75)),
  transition: (t) => (t < 0.38 ? 0.42 + 0.2*ss(t/0.38)
                              : 0.62 - 0.48*ss((t-0.38)/0.62)),
  future:     (t) => 0.05 + 0.81 * ss((t - 0.28) / 0.78),
};
```

Scenario callouts are de-cluttered in two passes: `spread()` (`:131-153`,
min gap `Math.min(16, (hi-lo)/(n-1))`, clamped 6..94) then `decollide()`
(`:166-192`, `CARD_W=15, CARD_H=12`, 80 iterations).
`foresightAdapters.ts:73-152` parses timeframes with
`/(\d{4})\s*[-–—]\s*(\d{4})/` and folds
`decision_fork.condition_a/b` into
`[{branch:'positive'|'warning', if_clause, then_clause}]`.

Supporting components: `horizons/{ExecutiveSummaryCard,
ExecutiveSummarySection, DecisionForkVisual, HorizonsExportModal}.tsx`,
types in `ui/src/types/horizonsExecutiveSummary.ts`, tune modal
`FHTuneModal.tsx`. Legacy standalone: `FutureHorizons.tsx`.
Rendered at `App.tsx:2837-2916`; exec summary auto-fires at `App.tsx:920`.

**HTML export:** `GET /api/trend-convergence/horizons/{analysis_id}/download.html`
(`:3649-3781`) → `app/services/horizons_html.py`, which re-implements the
curves as fixed SVG paths (`:77-79`) and places markers with
(`_scenario_position()`, `:123-148`):

```python
avg_year = (start + end) / 2
base_x = 10 + ((avg_year - 2025) / 15) * 75
spread = ((type_index / (total_in_type - 1) - 0.5) * 55) if total_in_type > 1 else 0
x = max(8, min(92, base_x + spread))
y = _y_on_curve(x, scenario['type']) + ((type_index % 3) - 1) * 12
```

When `future_horizon_articles` has no rows for the run (older runs), the
route falls back to a `topic_alignment_score > 0.7` corpus query to
rebuild the numbered references (`:3737`).

Other chart renderers: `app/services/wiley_three_horizons_viz.py`,
`scripts/render_three_horizons.py`.

---

## 4. Topics

Full treatment in [how_it_works_topics.md](how_it_works_topics.md). The
Anticipate-relevant summary.

### 4.0 Two different things are called "topic"

**(a) Config-defined corpus topics** — the source of truth is
`config.json`'s `topics[]`, served by `GET /api/topics`
(`app/routes/topic_routes.py:27-134`). `with_articles` adds counts via
`facade.get_topics_with_article_counts()`; `include_tracked` merges in
wizard-created topics from `forecast_topic_metadata` (`:74-109`), summing
article counts across their `source_topics`. Dedicated Brand-Watcher
tenants filter to `Brand Monitoring*` (`:111-114`).

**(b) Tracked forecast topics** — rows in `forecast_topic_metadata`, what
the Topics tab actually lists. These are the ones that carry assessments,
overlays and delivery cadence.

The two are joined by string equality on the topic name, with
`source_topics` as the escape hatch when they differ.

### 4.1 The metadata sidecar

`forecast_topic_metadata` is the lifecycle table, keyed on
`topic` (text PK) — the universal join key that ties together
`future_horizons_runs.topic`, `forecast_topic_delivery.topic`,
`forecast_assessments.topic` and the `topic` field inside the deck
overlay JSON files.

Columns (`app/database_models.py:1213-1250`): `display_name`,
`description`, `owner`, `status` ∈ {draft, active, archived},
`tags` (JSONB), `overlay_status` ∈ {missing, auto_generated, human_reviewed},
`source_candidate_id` (FK → `topic_candidates.id`), `claim_statement`,
`basis_consensus_pct`, `formalized_at`, `last_evidence_cycle`,
`dormant_since`, `source_topics` (JSONB). Indexed on `status`, `owner`.
Migrations: `fa_006`, `fa_007`, `fa_010_add_consensus_topic_lifecycle.py`,
`fa_011_add_source_topics.py`.

Sibling table `forecast_topic_delivery` (`:1199-1206`, migration `fa_003`):
`topic PK, cadence ∈ {none, …}, recipient_email, last_delivered_at`.

**Decoupled naming.** The wizard persists `source_topics` when the deck
name differs from the corpus tag (e.g. deck topic "Quantum Advantage" →
article tag "Quantum Computing"). The assessment window resolves through
that mapping, falling back to the deck name
(`forecast_assessment_service.py:115-126`).

### 4.2 Topic alignment is the real relevance filter

`topic_alignment_score` is produced at ingest by
`RelevanceCalculator` (`app/relevance.py`). The LLM returns a JSON block
that is clamped and combined at `:207-228`:

```python
for score_field in ["topic_alignment_score","keyword_relevance_score","confidence_score"]:
    validated_result[score_field] = max(0.0, min(1.0, score))
validated_result["relevance_score"] = (topic_score + keyword_score) / 2.0
```
`calculate_confidence_score()` (`:107-110`) is
`(alignment_score + relevance_score) / 2.0`. Ingest-side gating against
`config.min_relevance_threshold` happens in
`app/services/auto_ingest_service.py:363` (fallback score `0.1` at
`:289,295`).

Downstream, **every customer-facing selection re-filters on
`topic_alignment_score > 0.7`** — a raw `topic = :topic` match admits
collection noise. Call sites: `topic_report_service.py:503`,
`topic_report_pptx.py:1389`, `trend_convergence_routes.py:3737`,
`daily_reports_routes.py:50`.

Keyword groups (`app/tasks/keyword_monitor.py`,
`app/services/keyword_suggestion_service.py`) feed *ingestion*; they do
not participate in the Anticipate analyses directly.

### 4.3 Endpoints

```
GET   /api/forecast/topics                          (:651)  list_topics_with_lifecycle
GET   /api/forecast/topics/available                (:661)  distinct articles.topic + counts
GET   /api/forecast/topics/suggest?q=               (:684)  freeform → ranked corpus topics
POST  /api/forecast/topics                          (:734)  creates status='draft', overlay_status='missing'
PATCH /api/forecast/topics/{topic}/metadata         (:759)
POST  /api/forecast/topics/{topic}/wizard/build     (:796)  → build_topic_pipeline(article_limit=60, days_back=90)
POST  /api/forecast/topics/{topic}/overlay/generate (:853)
GET   /api/forecast/topics/{topic}/overlay/proposed (:895)
POST  /api/forecast/topics/{topic}/overlay/approve  (:913)  writes production overlay, status='active'
GET   /api/forecast/topics/delivery                 (:602)
PATCH /api/forecast/topics/{topic}/delivery         (:616)
```

`suggest` is semantic, not string-matching: it runs
`search_articles_async(q, top_k=150)` and aggregates hits by `topic` into
`{match_count, best_score, total}` (`:684-731`).

Overlay filename slug (`:776-781`):
```python
re.sub(r"[^a-z0-9]+", "_", topic.lower()).strip("_") + "_deck_overlay"
```

### 4.4 Health dot

Computed client-side in `ui/src/components/TopicsDashboard.tsx:60-72`,
in priority order:

```ts
if (r.status === 'archived')               → amber
if (!r.assessment_id)                      → red   'No assessment yet'
if (r.overlay_status === 'missing')        → red
if (days_since_assessment > 90)            → red
if (days_since_assessment > 30)            → amber
if (r.overlay_status === 'auto_generated') → amber
if (!r.cadence || r.cadence === 'none')    → amber
else                                       → green
```

**Frontend:** `TopicsDashboard.tsx` (views: `tracked | candidates |
how-it-works`), `AddTopicWizard.tsx` (4 steps, step 3 = overlay review),
`CandidatesInbox.tsx`, `AllTopicsForecastView.tsx`. Wired at
`App.tsx:2918-2936`. The "How it works" view renders
`docs/how_it_works_topics.md` through `DocViewer`.

---

## 5. Forecast Tracker

Back-tests a stored Three Horizons run against articles published after
it. Service: `app/services/forecast_assessment_service.py`.
Narrative version: [how_it_works_forecast_tracker.md](how_it_works_forecast_tracker.md).

### 5.1 Tuning constants (`forecast_assessment_service.py:32-57`)

```python
STAGE_A_TOP_K                    = 150     # per scenario, from pgvector
STAGE_B_MIN_SCORE                = 0.5     # sigmoid'd reranker gate
STAGE_C_MARGIN                   = 0.04    # margin to runner-up scenario
STAGE_D_CONCURRENCY              = 8       # parallel LLM calls
DEFAULT_MAX_ARTICLES             = 2000
DEFAULT_CLASSIFY_MODEL           = "gpt-5.4-mini"
MIN_CONF_FOR_VERDICT_PROMOTION   = 0.5
DIRECTIONAL_RATE_ONTRACK         = 0.2
DIRECTIONAL_RATE_OFFTRACK        = -0.2
INCONCLUSIVE_MIN_ARTICLES        = 6
DECK_OVERLAY_DIR                 = Path("data/wiley_horizons")
```

Two of these carry their tuning history in comments and are worth
knowing:

* `STAGE_C_MARGIN` was 0.10. At that setting **97 % of articles landed in
  the ambiguous bucket** even at deck granularity, because the reranker
  returns tightly bunched scores for in-topic articles. 0.04 requires the
  top scenario to beat the runner-up by ~4 points — "still requires clear
  directional signal but doesn't penalise honest overlap between, e.g.,
  Public Trust and Peer Review Strain."
* `INCONCLUSIVE_MIN_ARTICLES` was 15, too high for ~3-month windows on
  small-topic corpora. 6 is "the smallest sample where a directional rate
  is interpretable."

Live config observed on a wileytest assessment:
`{"max_articles": 2000, "stage_c_margin": 0.04, "stage_b_min_score": 0.5,
"stage_a_top_k": 150, "granularity_requested": "auto",
"scenario_level_used": "db", "window_weeks": 8}`

### 5.2 Stage A — window recall

The module docstring describes Stage A as "pgvector recall per scenario
probe". In the current code path it is a **plain window query** —
`_fetch_window_articles()` (`:470-533`):

```sql
SELECT uri, title, summary, submission_date, publication_date,
       news_source, sentiment, future_signal, time_to_impact
FROM articles
WHERE topic = ANY(:topics) AND embedding IS NOT NULL
  -- live:    AND submission_date::timestamp > :cutoff [AND <= :upper]
  -- placebo: AND submission_date::timestamp < :cutoff [AND >= :lower]
ORDER BY submission_date::timestamp DESC
LIMIT :lim
```

The per-scenario pgvector variant `_ann_search()` (`:536-598`,
`embedding <=> CAST(:qv AS vector)`) exists and honours `STAGE_A_TOP_K`,
but is **not** called by the main path — the reranker in Stage B does the
scenario-level discrimination instead. `STAGE_A_TOP_K` is therefore
recorded in `config` but currently inert.

Two things worth knowing about the query:

* The window is cut on **`submission_date`** (when the article entered
  the corpus), not `publication_date`. Both are TEXT columns and need the
  `::timestamp` cast.
* `embedding IS NOT NULL` is a hard requirement — an article that never
  got embedded is invisible to the tracker regardless of relevance.

`:topics` resolves from `forecast_topic_metadata.source_topics`, falling
back to `[topic]` (`:120-126`). Addendum scenarios promoted by analysts
are appended at `:146-159`; scenarios marked "done" are overlaid at
`:166-177` and never dropped, because `scenario_idx` is positional.

### 5.3 Stage B — cross-encoder rerank

Reranker: `BAAI/bge-reranker-v2-m3` via `sentence_transformers.CrossEncoder`,
`max_length=512` (`app/retrieval/reranker.py:51,98`, override with
`RERANK_MODEL`). Raw scores are sigmoid'd to `[0,1]` "so `score_pair`
thresholds are interpretable without per-model calibration" (`:47-48`).
Gate is `≥ STAGE_B_MIN_SCORE` (0.5).

Scenario text = `f"{title}. {description}"`; article text = title-based
(`reranker.py:257-262`). Scenario probe `_scenario_probe()` at
`forecast_assessment_service.py:1120-1125`; article text capped at 4000
chars (`_article_text()`, `:1128-1130`).

> **Deployment gotcha:** `RERANK_ENABLED` defaults to **`"false"`**
> (`reranker.py:~45`). With it unset, `assign_exclusive()` returns
> `scenario_idx=None` for every article, every article lands in the
> ambiguous bucket, and every scenario comes back `Inconclusive` while
> the surprises panel fills up. If a tracker run produces all-Inconclusive
> verdicts, check this env var before anything else.

Other reranker settings: `RERANK_OVERFETCH_FACTOR = 5`,
`RERANK_MAX_CANDIDATES = 200`,
`overfetch_limit(k) = min(max(k*5, k), 200)` (`:53-78`).

### 5.4 Stage C — exclusive assignment

`assign_exclusive()` (`reranker.py:211`) scores every article against
every scenario and assigns each article to at most one scenario. Purpose,
verbatim:

> Used by Forecast Assessment to prevent overlapping scenarios (e.g., an
> H1 decline scenario and an H3 replacement scenario about the same
> system) from both claiming credit for the same article.

Returns per article: `scenario_idx` (None if ambiguous), sigmoid'd
`score`, `margin` to runner-up, `best_alt_scenario_idx`, and the full
`all_scores` row. Articles whose margin < 0.04 go to the **ambiguous**
bucket, which feeds Stage F. If reranking is disabled or the model fails
to load, every row returns `scenario_idx=None` so the caller degrades
gracefully rather than mis-assigning.

Bucketing (`forecast_assessment_service.py:222-243`): an article is
*assigned* iff `assigned_idx is not None and score >= STAGE_B_MIN_SCORE`;
otherwise ambiguous. Articles that land on a scenario marked "done" are
also routed to ambiguous (`:229-235`).

**Granularity.** `granularity='auto'` uses deck scenarios when a
`data/wiley_horizons/{slug}_deck_overlay.json` exists (4–5 well-separated
named scenarios), otherwise the raw DB scenarios (10–14). Margin gating
works better at deck level precisely because the scenarios are further
apart. `_build_deck_scenarios()` (`:1158-1204`) merges each deck
scenario's `primary_signal` with all its member descriptions, truncated
to 4000 chars, so the reranker sees the full evidence surface.

`_load_deck_overlay()` (`:1140-1155`) matches overlays by the **`topic`
field inside the JSON**, not by filename — renaming an overlay file does
nothing; editing its `topic` key repoints it.

### 5.5 Stage D — per-pair LLM classification

Prompt: `data/prompts/forecast_assessment/current.json` (v1.0.0).
Model recommendations in the template: primary `gpt-4.1-mini`, fallback
`claude-haiku-4-5-20251001`; the service default is now `gpt-5.4-mini`.
Concurrency 8.

**System prompt:**
> You are a careful research analyst grading whether a news article
> supports, contradicts, or is irrelevant to a specific previously-stated
> scenario from a strategic forecast. **Be conservative: generic topical
> overlap is NOT support — only direction-matching, dated evidence
> counts.** Return strict JSON, no prose.

The user prompt supplies the scenario (horizon, title, description,
timeframe, forecast sentiment = expected direction), a
`sibling_scenarios_digest` (used *only* to decide
`better_fits_other_scenario`), and the article (title, date, summary).

**Six verdicts:**

| Verdict | Meaning |
| --- | --- |
| `supports_trajectory` | Concrete dated evidence consistent with the predicted direction. "Not just 'related topic.'" |
| `supports_state_contradicts_trajectory` | Confirms the subject but the trajectory is stabilising / reversing / being mitigated |
| `contradicts` | Evidence running against the predicted direction |
| `better_fits_other_scenario` | On-topic but fits a sibling better; returns `best_alt_scenario_idx` |
| `neutral_context` | Background or commentary, no directional evidence |
| `unrelated` | Off-topic for this scenario |

**Four evidence types:** `milestone` (specific dated named event),
`leading_indicator` (early empirical signal), `commentary` (opinion, no
new evidence), `anecdote` (single case, not generalisable).

Also returns `confidence` (0–1) and a `rationale` capped at 30 words /
240 chars citing the specific fact that drove the verdict.

Input truncation before the call (`:635-641`): title 300 chars, summary
1500 chars, date 10 chars. The sibling digest is built as
`"{i}: [{type}] {title}"` per scenario (`:1133-1137`). Parsing is
tolerant — `_parse_classifier_json()` (`:659-681`) falls back to
`_neutral_verdict()` (`:684-691`) rather than failing the run, so a
malformed response degrades one article, not the assessment.

Rows land in `forecast_article_verdicts` (article_uri, scenario_idx,
verdict, evidence_type, confidence, rerank_score, margin,
best_alt_scenario_idx, rationale, article_date).

Production distribution (wileytest, 573 rows) shows the conservatism
working: 241 `supports_trajectory`, 116 `better_fits_other_scenario`,
118 `neutral_context`, 45 `unrelated`, ~29
`supports_state_contradicts_trajectory`.

### 5.6 Stage E — aggregation to a verdict

`_aggregate_scenario()` (`forecast_assessment_service.py:696-841`).
Only verdicts with `confidence >= 0.5` count ("confident" set, `n_total`).

```python
eff_contra       = contradicts + state_only         # state-only counts against
denom            = supports + eff_contra
directional_rate = (supports - eff_contra) / denom          if denom > 0 else 0.0

milestone_hits    = count(evidence_type ∈ {milestone, leading_indicator}
                          and verdict ∈ {supports_trajectory, contradicts})
milestone_density = milestone_hits / n_total

months_elapsed   = max(elapsed_days / 30.0, 0.5)
velocity         = (supports - eff_contra) / months_elapsed

expected_supports = 3.0 * months_elapsed            # ~3 supporting events/month
coverage          = supports / expected_supports

current_consensus_pct = 100.0 * supports / n_total
```

`expected_supports` is an explicit placeholder — the code comment says
"we don't have per-scenario priors yet, so anchor to: a healthy on-track
scenario should produce ≥ ~3 supporting events per month."

**Verdict decision tree** (`:844-873`), evaluated in order:

```python
if n_confident < 6:                       return "Inconclusive"
if directional_rate < -0.2:               return "Off-track"
if state_only >= 3 and state_only > supports:  return "Off-track"
if velocity > 0 and milestone_density > 0.15 and coverage > 1.0:
                                          return "Accelerating"
if directional_rate > 0.2 and velocity >= 0:   return "On-track"
if abs(directional_rate) <= 0.1 and abs(velocity) <= 1.0:
                                          return "Stalled"
return "Inconclusive"
```

The `milestone_density > 0.15` conjunct on Accelerating is the guard
against commentary inflation — a scenario cannot accelerate on op-eds
alone. `"Done"` is a sixth label, set by analyst action rather than
computed (`:312-316`); such scenarios short-circuit the reranker/LLM
stages entirely.

Per-scenario rows go to `forecast_scenario_verdicts` with
`summary_md`, `top_articles` (top 3 supports + top 2 contradicts, ranked
by `confidence × rerank_score`), and `current_consensus_pct` — which the
Wiley bundle prints next to the overlay's original `consensus_pct` so the
reader sees quarter-over-quarter drift.

### 5.7 Stage F — surprises

`_find_surprises()` (`:896-925`) takes the residual = ambiguous ∪
unrelated. Requires ≥ 8 residual articles, else returns empty.

Clustering on pgvector embeddings:
```python
hdbscan.HDBSCAN(min_cluster_size=5, metric="euclidean")
# ImportError fallback:
sklearn.cluster.DBSCAN(eps=0.35, min_samples=5, metric="cosine")
# no numeric libs at all → TF-IDF top-terms keyword fallback
```
Clustering runs in `asyncio.to_thread` (`:345-352`) because
`fit_predict` is synchronous and would otherwise block the event loop.
Noise (`label == -1`) is dropped; clusters below 5 articles are dropped.

Each surviving cluster gets a provisional keyword label from
`_keyword_label()` (`:1093-1115`) — top-3 tokens matching
`r"[A-Za-z][A-Za-z\-]+"` with `len(w) >= 4`, stop-word filtered — then
`_label_clusters_with_llm()` (`:1001-1075`) calls
`forecast_cluster_label_agent` with `{topic, fallback_label,
article_titles}`. The agent returns a human-readable name plus a
`topic_relevance` boolean and `off_topic_article_indices`. Clusters with
`topic_relevance is False` are dropped whole; listed articles inside
otherwise-relevant clusters are pruned and `size` decremented. This is
what keeps retrieval-noise clusters (articles sharing a keyword with the
topic but nothing else) out of the analyst's surprises panel.

Result shape, stored in `forecast_assessments.surprises` (jsonb):
`[{label, size, sample_articles: [{uri, title, date}]}]`.

An analyst can promote a cluster to an addendum scenario:
`POST /api/forecast/{run_id}/scenarios/draft-from-surprise` (`:396`),
persisting to `forecast_user_scenarios` with `source_assessment_id`,
`source_surprise_label`, `source_article_uris`.

### 5.8 Paired mode and baseline correction

`assess_run(mode=...)` supports `live`, `placebo` (pre-forecast window —
the temporal negative control, where "verdicts should be Inconclusive"),
and `shuffle` (live window, scenario titles swapped in from another
topic).

`apply_baseline_correction()` (`:1254-1315`):
```python
live_rate    = live.supports    / live_pool        # live_pool = evidence_count
placebo_rate = placebo.supports / placebo_pool
net_rate     = live_rate - placebo_rate

net_rate >  0.005  → "Above baseline"
net_rate < -0.005  → "Below baseline"
else               → "At baseline"
```

The rationale, verbatim from the docstring:

> Near-zero or negative net_rate ⇒ the article-level signal is no stronger
> than it was before the forecast existed — either the forecast was a
> pure trend extrapolation, or the classifier is responding to topical
> overlap rather than incremental evidence.

Written back into `forecast_assessments.summary["baseline_correction"]`
with `"method": "live_rate − placebo_rate (pool-normalised supports)"`.

The deck reports the baseline-corrected rate, never the raw rate.

**The two label axes are distinct and often confused:**

| Axis | Values | Source |
| --- | --- | --- |
| Per-scenario verdict (§5.6) | Accelerating / On-track / Stalled / Off-track / Inconclusive / Done | `_decide_verdict_label()` |
| Baseline correction (§5.8) | Above / At / Below baseline | `apply_baseline_correction()` |
| Customer-facing rendering of the baseline axis | Strengthening / Stable / Cooling | `CUSTOMER_LABEL` |

`CUSTOMER_LABEL` lives in `app/services/forecast_narrative.py:34-38` and
is mirrored in `ui/src/components/ForecastAssessment.tsx:64-88` and
`app/services/forecast_pptx_export.py`:

```python
CUSTOMER_LABEL = {"Above baseline": "Strengthening",
                  "At baseline":    "Stable",
                  "Below baseline": "Cooling"}
```

The UI headline chip prefers the baseline label whenever a paired
correction exists, falling back to the verdict label otherwise
(`ForecastAssessment.tsx:596-603`).

### 5.9 Narrative layer

Numbers alone don't ship. `app/services/forecast_narrative.py`
(1187 lines, `NARRATIVE_MODEL = "gpt-5.4-mini"`) turns verdict rows into
prose, one prompt per artefact:

| Prompt | Line | Produces |
| --- | --- | --- |
| `_SCENARIO_PROMPT` | `:62` | Per-scenario summary |
| `_EXEC_PROMPT` | `:83` | Assessment-level executive narrative |
| `_PROMOTE_PROMPT` | `:226` | Addendum scenario drafted from a surprise cluster (h1/h2/h3 selection rules at `:246-249`) |
| `_BRIEFING_PROMPT` | `:314` | Topic briefing |
| `_RECOMMENDATIONS_PROMPT` | `:350` | Strategic recommendations |
| `_SCENARIO_SIGNALS_PROMPT` | `:584` | Watch-for signals |
| `_NEXT_STEPS_PROMPT` | `:678` | Next steps |
| `_BUNDLE_OVERVIEW_PROMPT` / `_BUNDLE_THEMES_PROMPT` / `_BUNDLE_FRAMEWORK_PROMPT` | `:746` / `:763` / `:785` | Cross-topic bundle sections |

Entry points: `synthesize_scenario_narrative` (`:116`),
`synthesize_exec_narrative` (`:167`),
`synthesize_scenario_from_surprise` (`:254`),
`synthesize_topic_briefing` (`:458`),
`synthesize_strategic_recommendations` (`:508`),
`synthesize_scenario_signals` (`:615`), `synthesize_next_steps` (`:702`),
`ensure_bundle_synthesis` (`:885`),
`ensure_narratives_for_assessment` (`:912`). Output lands in
`forecast_scenario_verdicts.synthesis` (JSONB, migration `fa_004`).

### 5.10 Background monitor

`app/tasks/forecast_tracker_monitor.py` (302 lines), registered at
`app/core/app_factory.py:136` with a 30-second startup delay.

```python
CHECK_INTERVAL_SECONDS = FORECAST_TRACKER_CHECK_INTERVAL_SEC   default 21600  # 6h
STALENESS_DAYS         = FORECAST_TRACKER_STALENESS_DAYS       default 30
WINDOW_WEEKS           = FORECAST_TRACKER_WINDOW_WEEKS         default 8
MAX_ARTICLES           = FORECAST_TRACKER_MAX_ARTICLES         default 2000
```

**The loop is gated on `FORECAST_TRACKER_AUTO_RUN`** and exits
immediately when unset (`:60-62`) — so on most tenants nothing
re-assesses automatically and the Topics health dot goes amber at 30 days
because a human hasn't pressed Reassess.

Each tick does two things:
1. `_check_and_kick_off()` (`:157-229`) — for every topic with an overlay
   whose latest `mode='live'` assessment is older than `STALENESS_DAYS`,
   fires a paired job (`_build_paired_job()`, `:232-269`:
   `margin=0.04, granularity="auto", window_weeks=WINDOW_WEEKS`) followed
   by `apply_baseline_correction`.
2. `_check_delivery_cadences()` (`:82-130`) — fires on day-of-month 1;
   quarterly cadences additionally require month ∈ {1, 4, 7, 10}.

Overlay-topic discovery: `_load_overlay_topics()` (`:272-287`).
Status endpoint: `GET /api/forecast/tracker-monitor/status` (`:299`).

### 5.11 Endpoints and frontend

```
POST /api/forecast/{run_id}/assess                                  (:31)
POST /api/forecast/{run_id}/assess-paired                           (:95)
GET  /api/forecast/assessment/job/{task_id}                         (:194)
GET  /api/forecast/topics/{topic}/latest-run                        (:206)
GET  /api/forecast/{run_id}/assessment                              (:242)
GET  /api/forecast/{run_id}/assessment/{assessment_id}/articles     (:1367)
GET  /api/forecast/{run_id}/assessment/{assessment_id}/export.pptx  (:307)
GET  /api/forecast/snapshots/by-topic                               (:282)
GET  /api/forecast/tracker-monitor/status                           (:299)
POST /api/forecast/{run_id}/scenarios/draft-from-surprise           (:396)
GET/POST/PATCH /api/forecast/{run_id}/scenarios[/status]            (:453,:544,:566)
```

`assess` accepts `mode`, `max_articles` (10..5000), `classify_model`,
`margin` (0..0.5), `granularity`, `window_weeks` (1..104).
`assess-paired` takes `window_weeks=8` (1..52) and internally schedules
live → [0,48] % progress, placebo → [48,96] %, correction at 97 %.
`latest-run` exists because `analysis_id` goes stale whenever a topic is
re-forecast — the client re-resolves rather than trusting a cached id.

**Tables:** `forecast_assessments`, `forecast_scenario_verdicts`
(unique on `(assessment_id, scenario_idx)`, `current_consensus_pct` and
`synthesis` added in `fa_004`), `forecast_article_verdicts`,
`forecast_user_scenarios` (`fa_002`), `forecast_scenario_status`
(`fa_003`, polymorphic done-marking, unique on
`(run_id, scenario_idx, user_scenario_id)`),
`forecast_bundle_synthesis` (`fa_004`, PK `(cadence, period_label)`),
`forecast_bundle_review` (`fa_005`). Facade:
`save_forecast_assessment` (`database_query_facade.py:7984`),
`get_latest_forecast_assessment` (`:8107`),
`get_forecast_assessment_snapshots` (`:8176`),
`get_latest_forecast_assessment_by_topic` (`:8249`).

**Frontend:** `ui/src/components/ForecastAssessment.tsx` (1301 lines) —
`VERDICT_STYLES` (`:34-62`), `ScenarioGrid` (`:535`), `ScenarioCard`
(`:590`, net rate rendered as `(net_rate*100).toFixed(2)%` at `:678`),
snapshot trajectory heatmap (`:1159-1300`). The run-id resolution effect
(`:104-140`) always re-resolves through `latest-run` and clears on 404
rather than falling back to a stale prop.
`AllTopicsForecastView.tsx` renders when `config.topic === '__all__'`
(`App.tsx:2939`). Also `WileyDeliverablesPanel.tsx`,
`QuarterlyBriefEditor.tsx`; types in
`ui/src/types/forecastAssessment.ts`.

---

## 6. Topic Reports

On-demand long-form deck for any combination of tracked topics.
Route: `app/routes/topic_report_routes.py`.
Service: `app/services/topic_report_service.py`.
Renderer: `app/services/topic_report_pptx.py`.

Explicitly **not** the quarterly bundle path — the module docstring says
"No back-test, no supervisor pipeline, no reviewer gate"
(`topic_report_service.py:680-682`). It reads
`future_horizons_runs.raw_output` per topic and shapes it into the deck.

### 6.1 Endpoints

```
POST /api/topic-reports/start                          (:43)
GET  /api/topic-reports/{period_label}/download.pptx   (:105)
GET  /api/topic-reports/{period_label}/download.md     (:132)
GET  /api/topic-reports/{period_label}/download.html   (:154)
GET  /api/topic-reports/{period_label}/download.docx   (:172)
POST /api/topic-reports/{period_label}/regenerate      (:190)
GET  /api/topic-reports/recent                         (:200)
```

`start` takes `{topics[] (min 1), period?, rerun_forecast=False,
force_model?}` and returns a `task_id`; progress polls the shared
`GET /api/forecast/assessment/job/{task_id}` (same `BackgroundTaskManager`).
MD/HTML/DOCX are *views* of the same cached synthesis, resolved via a
state sidecar written at render time (`_write_state_sidecar`, `:210`).

### 6.1.1 Cache identity

`_topics_period_label()` (`:40-50`) — the topic set is order-insensitive:

```python
sorted_topics = sorted([(t or "").strip() for t in topics if t])
h = hashlib.sha1("|".join(sorted_topics).encode("utf-8")).hexdigest()[:8]
safe = (period or "").strip().replace(" ", "_") or "ondemand"
return f"{safe}__{h}"
```

Artefacts live at
`{tempdir}/topic_report_render_cache/topic_report_{period_label}.pptx`
plus a `.state.json` sidecar recording `{topics, period}` (`:160-227`).
`_load_cached_state()` (`:767-806`) reads the supervisor synthesis from
`forecast_bundle_synthesis` with `cadence='topic_report'`.

### 6.2 Optional forecast rerun

With `rerun_forecast=true`, `_rerun_future_horizons_for_topic()`
(`:462-665`) runs a fresh Three Horizons pass per topic before rendering.
Default model `gpt-5.4`; sample size from
`calculate_optimal_sample_size(model, 'auto')` — ~180 articles for
≥1M-context models, ~90 for smaller (gpt-5.4 at 400k falls in the
latter). Article query gates on `topic_alignment_score > 0.7` as in §4.2.

Model kwargs are branched because reasoning models take different
parameters (`:531-542`):

```python
call_kwargs = {**resolve_litellm_call_params(model),
               "messages": [...], "caching": False}
if model.startswith("gpt-5"):
    call_kwargs["reasoning_effort"] = minimal_reasoning_effort(model)
    call_kwargs["max_completion_tokens"] = 16000
else:
    call_kwargs["max_tokens"] = 8000
    call_kwargs["temperature"] = 0.7
```

The new run is persisted with `metadata.analysis_type =
"topic_report_rerun"` (`:588-626`), then
`save_future_horizon_articles(run_id, ordered_uris, topic)` (`:633-641`)
stores the corpus **in prompt order** so `[N]` markers resolve correctly.
`generate_executive_summary_for_run()` (`:347-459`) follows.

Progress budget: reruns occupy 5–65 %, with each topic's slot split in
half so the bar moves during exec-summary generation ("gpt-5.4 reasoning
latency on the exec summary can rival the scenario generation, so without
a mid-step ping the UI would freeze on the first percentage for ~10
minutes per topic", `:725-728`). Loading is 70 %, render 92 %.

### 6.3 The topic-report prompt

`_build_topic_report_prompt()` (`:230-344`) is a bespoke prompt that asks
for the **whole deck in one call** rather than just scenarios — the stock
`generate_future_horizons_prompt` only produces `scenarios`, and the deck
needs recommendations, insights, next steps and the decision framework to
come from the same forecast for internal consistency.

**Audience constraint, verbatim:**

> every strategic_recommendation, next_step, and
> executive_decision_framework principle must be an action a scientific
> publisher can actually take within its own remit (editorial,
> commissioning, portfolio, licensing, research-integrity, partnership,
> or communication decisions). Never recommend actions for governments,
> regulators, funders, health authorities, or other third parties the
> publisher does not control; if the topic involves a crisis the publisher
> cannot act on directly, frame the action as how the publisher should
> respond within its remit, not how the crisis itself should be managed.

**Enforced quantities:**
```
topic_briefing.tensions                      : EXACTLY 3-4
scenarios                                    : 12-14 (4-5 H1 / 4-5 H2 / 3-4 H3)
strategic_recommendations                    : EXACTLY 3 (one per horizon:
                                               0-6 / 6-18 / 18+ months)
key_insights                                 : 4-5
next_steps                                   : EXACTLY 3
executive_decision_framework.principles      : EXACTLY 3
```

**Citation rules:** every scenario description cites 2–4 articles; every
recommendation rationale 1–3; every key_insight ≥ 1.

`topic_briefing` adds `headline` (≤16 words), `lede` (2–3 sentences),
`tensions[]` ({UPPERCASE NAME, body}), and `intelligence_view` — a
2–3 sentence analytical synthesis of what the evidence actually shows.

### 6.4 Item resolution

`resolve_items()` (`topic_report_pptx.py:1518-1597`) — per topic: latest
`future_horizons_runs` row → `_assessment_view()` (`:296`) → merge any
stored `forecast_assessments.summary`, where **the fresh forecast wins
and the stored assessment only fills gaps** (`:1565-1579`). Then attaches
`_eos_scenarios` (saved Extreme Outliers), `_consensus_payload`,
`_supporting_articles`, `_exec_summary_cards`, `_articles_corpus`
(`:1586-1594`).

When a topic has a forecast but no evidence yet,
`_synthesize_verdicts_from_forecast()`
(`topic_report_service.py:53-97`) emits
`verdict_label='Pending evidence'` placeholders rather than blank cards.

### 6.5 Deck structure

`build_topic_report_pptx()` (`topic_report_pptx.py:1600-1734`).
Slide size 10.0 × 5.625 in (16:9).

Front matter — a branded 8-slide intro pack when no static template is
supplied (`_add_branded_intro_pack`): cover / platform / team /
methodology / pipeline / lenses / calibration / coverage, in Wiley navy +
pink. Then the bundle cover, and a Three Horizons overview when ≥ 2
topics are selected.

Per topic, in order:
1. Topic divider
2. Analysis metadata
3. Three Horizons chart
4. Briefing synthesis (`summary.topic_briefing`, skipped if absent)
5. Executive Summary cards (one slide each, from the
   `horizons_exec_summary_{run_id}` cache — byte-identical to the React tab)
6. Key insights
7. Strategic recommendations
8. Executive decision framework (`principles[]`)
9. Next steps
10. Black swans / wildcards, when saved Extreme Outlier scenarios exist
11. Surprise clusters (divider + up to 4 cluster slides), when the topic
    has an assessment with surprises
12. Supporting articles
13. Per-horizon walk: H1 divider + one card per scenario, then H2, then H3
14. Numbered article references — resolves every `[N]` on the body slides

Closes with a methodology appendix and `_ai_pptx_marker()`, the
EU AI Act Art. 50 machine-readable AI-generation marker.

Every builder returns silently when its data source is empty, so the deck
only carries slides it can actually fill.

### 6.6 The other output formats

* **HTML** — `app/services/topic_report_html.py` (649 lines),
  `build_topic_report_html()` at `:527`. `_esc_cites()` (`:180-209`)
  turns `[N]` markers into hyperlinks. Section renderers: `_render_briefing`
  (`:228`), `_render_executive_summary` (`:256`), `_render_strategic_recs`
  (`:364`), `_render_decision_framework` (`:384`), `_render_next_steps`
  (`:401`), `_render_black_swans` (`:417`), `_render_supporting_articles`
  (`:458`), `_render_scenarios` (`:492`). Inlines the horizons chart via
  `horizons_html.render_horizons_chart()`.
* **DOCX** — `app/services/topic_report_docx.py`.
* **Markdown** — reuses the bundle renderer:
  `forecast_bundle_markdown.build_bundle_markdown(..., cadence="topic_report")`
  (`topic_report_service.py:809-826`).

Slide builders are shared with the bundle path — `topic_report_pptx.py:45-51`
imports `_add_executive_decision_framework_slide`,
`_add_briefing_synthesis_slide`, `_add_key_insights_slide`,
`_add_strategic_recommendations_slide`, `_add_next_steps_slide`,
`_add_black_swans_slide`, `_add_surprise_cluster_slide` and
`_add_methodology_appendix_slide` from
`app/services/forecast_pptx_export.py` (2858 lines).

### 6.7 Relationship to the Wiley bundle

`forecast_bundle_pptx.py` / `_docx.py` / `_html.py` / `_markdown.py` and
`forecast_pptx_export.py` back the cadence-locked Wiley bundle
(`/api/forecast/deliverables/*`, `forecast_assessment_routes.py:951-1366`),
which *does* run the multi-agent supervisor
(`app/services/wiley_bundle_supervisor.py`) and the `wiley_reviewer_agent`
approval gate, with state in `forecast_bundle_synthesis` and
`forecast_bundle_review`, and an editable brief layer at
`:1499-1782` (field/lock/topic-field patching, regenerate-stage,
preview.pptx). Topic Reports is the lightweight sibling of that path:
same renderers, no supervisor, no review gate.

**Frontend:** `ui/src/components/TopicReportsPanel.tsx` (638 lines).
Default period is `Q{quarter} {year}` (`:59-63`); the topic picker filters
to `status !== 'archived' && assessment_id` (`:90-91`); a
`downloadTriggered` ref (`:82`) guards against double-firing the download.
Mounted at `App.tsx:2952`.
Eval harness: `eval/model_comparison/eval_topic_reports.py`.

---

## 7. How the pieces connect

```
articles (enriched: sentiment, category, future_signal,
          driver_type, time_to_impact, quality_score,
          topic_alignment_score, embedding, mbfc_*)
   │
   ├─ lens weighting (§1.2) ─ sample sizing (§1.3) ─ deterministic select (§1.4)
   │        │
   │        ├─► consensus_analysis prompt ──► consensus_analysis_runs
   │        │                                 (categories, outliers, decision windows)
   │        │
   │        └─► future_horizons prompt ─────► future_horizons_runs
   │                                          (12-14 H1/H2/H3 scenarios)
   │                                                  │
   │                                                  ├──────────────┐
   │                                                  ▼              ▼
   │                                       Forecast Tracker      Topic Reports
   │                                       (§5: A→F back-test)   (§6: deck render)
   │                                                  │
   │                                       forecast_assessments
   │                                       forecast_scenario_verdicts
   │                                       forecast_article_verdicts
   │                                                  │
   │                                       surprises ──► promote to
   │                                                     forecast_user_scenarios
   │
   └─ emerging-themes detector ──► emerging_topics ──► topic_candidates
                                                            │
                                                       promote (§4)
                                                            ▼
                                                  forecast_topic_metadata
```

The load-bearing join key throughout is the `topic` string on
`forecast_topic_metadata`, with `source_topics` handling the case where
the deck-facing name differs from the corpus tag.

---

## 8. Known documentation drift

Recorded here so the next reader doesn't have to re-derive it:

* `STAGE_A_TOP_K` is documented (and stored in assessment `config`) as a
  pgvector recall depth, but the main path uses a window query and never
  calls `_ann_search()`. See §5.2.
* `data/prompts/*/current.json` files carry a `metadata.model` field
  (usually `gpt-4o`) and `forecast_assessment/current.json` carries
  `model_recommendations`. Both are advisory — the runtime model is
  whatever the request's `model` parameter (or the service default) says.
  **This is the single largest source of stale model names in the docs**:
  reading a model out of a prompt template tells you what someone
  recommended, not what runs.

Drift corrected on 2026-08-02:

* `how_it_works_forecast_tracker.md` — classifier model, the
  verdict-vs-baseline label conflation, the non-existent corpus-wide
  fallback, the three-value verdict enum, the ambiguous-only surprise
  residual, and "re-runs overwrite the most recent assessment" (they
  insert).
* `how_it_works_topics.md` §6.2 — same corpus-wide fallback and verdict
  enum; §3.3 and §5.1 model names (`gpt-4o` → `gpt-5.4` in both the theme
  proposer and the promotion-path Three Horizons call).

---

## 9. Files to read for code-level detail

| Area | File |
| --- | --- |
| Lens pipeline, weighting, sampling, prompt admin | `app/routes/trend_convergence_routes.py` (3831 lines) |
| Narrative synthesis over verdicts | `app/services/forecast_narrative.py` |
| Tracker background monitor | `app/tasks/forecast_tracker_monitor.py` |
| Ingest-time relevance scoring | `app/relevance.py`, `app/services/auto_ingest_service.py` |
| Corpus-topic API (config-defined) | `app/routes/topic_routes.py` |
| Consensus / horizons HTML exports | `app/services/consensus_html.py`, `app/services/horizons_html.py` |
| Saved dashboards | `app/routes/saved_dashboard_routes.py` |
| Prompt templates on disk | `data/prompts/{consensus_analysis,future_horizons,forecast_assessment,market_signals,impact_timeline,strategic_recommendations,intelligence_brief}/current.json` |
| Prompt loading / versioning | `app/services/prompt_loader.py`, `app/analyzers/prompt_manager.py` |
| Forecast assessment engine | `app/services/forecast_assessment_service.py` |
| Cross-encoder reranker | `app/retrieval/reranker.py` |
| Assessment / topics / bundle HTTP API | `app/routes/forecast_assessment_routes.py` |
| Topic reports | `app/routes/topic_report_routes.py`, `app/services/topic_report_service.py`, `app/services/topic_report_pptx.py` |
| Wiley bundle (supervisor path) | `app/services/wiley_bundle_supervisor.py`, `app/services/forecast_bundle_*.py`, `app/services/forecast_pptx_export.py` |
| Candidate discovery + promotion | `app/services/wiley_candidate_pipeline.py`, `app/tasks/wiley_candidate_scheduler.py` |
| Agent prompts | `data/auspex/agents/{wiley_overlay_agent,wiley_relevance_judge,forecast_cluster_label_agent,wiley_reviewer_agent}.md` |
| Deck overlays | `data/wiley_horizons/*_deck_overlay.json` |
| React | `ui/src/App.tsx`, `ui/src/components/{TabNavigation,ConsensusCategoryCard,FutureHorizons,ForecastAssessment,TopicsDashboard,TopicReportsPanel}.tsx`, `ui/src/components/{foresight,horizons}/` |

---

*Companion pages: [Topics](how_it_works_topics.md) ·
[Forecast Tracker](how_it_works_forecast_tracker.md) ·
[Methodology overview](METHODOLOGY.md) ·
[Anticipate user guide](getting-started-anticipate.md)*
