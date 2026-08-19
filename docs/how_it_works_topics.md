# How the Topics tab works

The Topics tab manages the lifecycle of formally tracked intelligence
topics. It has three views, toggled by the pill row at the top —
**Tracked**, **Candidates**, and **How it works**. Most of the work
happens off-screen in scheduled jobs and background pipelines; this
page documents what those pieces actually do.

The rest of this page is the methodology — what each panel shows, what
the discovery pipeline computes, and what the promotion path does when
you click a button.

## 1. The data flow

```
articles + embeddings  ──►  emerging-themes detector (weekly)  ──►  emerging_topics rows
                                                                         │
                                                                         ▼
                                                Wiley relevance judge (LLM, per cluster)
                                                                         │
                                                          ┌──────────────┼──────────────┐
                                                          ▼              ▼              ▼
                                                       in_scope       adjacent       off_scope
                                                          │              │              │
                                                          └──────┬───────┘              ▼
                                                                 ▼                 auto-rejected
                                                       topic_candidates inbox
                                                                 │
                                  ┌──────────────────┬───────────┴──────────┬──────────────────┐
                                  ▼                  ▼                      ▼                  ▼
                              Promote           Snooze 7/14d              Merge             Reject
                                  │                  │                      │                  │
                                  ▼                  ▼                      ▼                  ▼
                     Three Horizons  →     re-surface after        articles fold into   audit-trail row
                     Paired assessment     window expires          existing topic's
                     Draft overlay                                 next assessment
                     `.proposed` JSON
                                  │
                                  ▼
                  forecast_topic_metadata row (status='draft')
                                  │
                                  ▼
                  Wizard opens at overlay-review step
                                  │
                                  ▼
                  Analyst approves overlay → topic 'active'
                                  │
                                  ▼
                  Topic ships in the next Wiley bundle
```

Each arrow corresponds to a discrete piece of code; the rest of this
page walks through each one.

## 2. The Tracked view

One row per formally tracked topic, drawn from a single SQL view that
joins `forecast_topic_metadata` (sidecar lifecycle data),
`forecast_topic_delivery` (cadence + recipient), and the most recent
`forecast_assessments` row for the topic.

### Health dot

Computed client-side from the joined row, in priority order:

1. **Red** if `status='archived'` (excluded from bundles).
2. **Red** if no assessment has been run.
3. **Red** if the most recent assessment is >90 days old.
4. **Red** if `overlay_status='missing'` (bundle delivery would warn).
5. **Amber** if the most recent assessment is 30–90 days old.
6. **Amber** if `overlay_status='auto_generated'` (pending human review).
7. **Amber** if no delivery cadence is set.
8. **Green** otherwise — fresh assessment, reviewed overlay, cadence
   configured.

Hover the dot for the specific reason.

### Status

Three values, stored as `status` on `forecast_topic_metadata`:

- `draft` — created but not yet activated. The Add-topic wizard sets
  this on step 1; the wizard's final step flips it to `active`.
- `active` — included in bundle generation, surfaced in the Wiley
  Deliverables panel.
- `archived` — kept for history but excluded from bundles and the
  default dashboard view.

### Overlay status

Three values, stored as `overlay_status` on `forecast_topic_metadata`:

- `missing` — no `_deck_overlay.json` file on disk. The bundle reviewer
  flags this as a warning before delivery.
- `auto_generated` — `.proposed` file exists but a human hasn't approved
  it yet. Surfaced as an amber chip with a "Review overlay" CTA.
- `human_reviewed` — production overlay file exists and the wizard's
  approve endpoint marked it reviewed.

## 3. The Candidates view — discovery methodology

This is where new topics are *proposed*, not chosen. A scheduled job
runs the emerging-themes detector across the corpus and the LLM judges
each cluster against the Wiley remit.

### 3.1 Sample selection

Each scan reads the last `WILEY_CANDIDATE_SCAN_DAYS_BACK` days of
articles (default 14; the detector's own default when called directly is
7). The window cuts on `publication_date` here — note that the forecast
assessment window cuts on `submission_date` instead, so the two are not
comparable. The detector doesn't cluster every article — it samples
high-novelty articles from each news source to ensure source diversity:

- Articles are LEFT JOINed to `article_novelty_scores` to pull
  pre-computed novelty scores.
- The SQL uses `DISTINCT ON (news_source, uri) ORDER BY news_source,
  uri, COALESCE(novelty_score, 50) DESC` so each source contributes its
  most-novel article before any source contributes a second one.
- The rows are then sorted by novelty and truncated to `max_articles`
  (default 250). That sort and cap happen in Python, not in the SQL.

The `COALESCE` matters: an article that has never been scored is treated
as novelty 50, the midpoint, rather than excluded. On a corpus where the
novelty job hasn't run, every article samples as equally novel and the
source-diversity ordering quietly stops doing anything.

This is `_fetch_sample_articles()` in
`app/services/emerging_topics/theme_proposer.py`.

### 3.2 Novelty scoring

`article_novelty_scores` is a composite of three independent signals
computed from article embeddings (see `novelty_scorer.py`):

| Signal | What it measures | Weight |
| --- | --- | --- |
| **knn_distance_score** | Average cosine distance to the article's k-nearest neighbours (`k_neighbors=10`). Articles in dense neighbourhoods score lower; isolated ones score higher. | 0.40 |
| **density_score** | Count of articles within `density_radius=0.3` cosine distance. Inverted, scaled 0–100. | 0.35 |
| **centroid_distance_score** | Distance to the *nearest cluster centroid* — how far the article sits from the closest known topic, not from the corpus as a whole. Falls back to an approximation when no centroids are available. | 0.25 |

`composite_novelty_score` is the weighted sum, so kNN distance carries
most of it. An article scoring above 75 is flagged an outlier. Scores are
written once per article per calculation date and cached.

### 3.3 LLM theme proposal

The high-novelty sample is fed to an LLM (`ThemeProposer.default_model`,
currently `gpt-5.4`) with a prompt that asks for
5–10 *specific* emerging themes. The prompt rejects broad categories
("AI Developments", "Tech News") and requires concrete framings
("DeepSeek R1 Release and Global Response", "EU AI Act Implementation
Deadlines"). Each proposed theme includes:

- `theme_label` — 3–7 word title
- `theme_description` — one-sentence framing
- `search_query` — used to semantically retrieve more articles for the
  theme
- `key_entities` — actors named
- `why_emerging` — what makes it new

Each theme then has its `search_query` run against the article embedding
index to enrich its article set beyond the original sample.

### 3.4 HDBSCAN clustering pass

In parallel, `app/services/emerging_topics/cluster_detector.py` runs
HDBSCAN on the recent article embeddings to surface emerging clusters
the LLM may have missed. Parameters (the defaults work well empirically):

| Parameter | Value | Purpose |
| --- | --- | --- |
| `min_cluster_size` | 5 | Minimum articles to form a cluster |
| `min_samples` | 3 | Stricter density required at cluster core |
| `cluster_selection_epsilon` | 0.0 | No flat distance threshold (HDBSCAN picks per cluster) |
| `metric` | `precomputed` | Pre-compute cosine distance matrix |

HDBSCAN is preferred over k-means because:

1. It automatically determines the number of clusters from data
   density.
2. It handles varying cluster densities — "AI policy" can be a tight
   cluster while "pharma generics" can be more diffuse.
3. It marks low-density articles as noise (`-1`) rather than forcing
   them into a cluster.
4. Hierarchical output makes parent/child cluster tracking possible
   (the splitting / merging detection types).

LLM-proposed themes and HDBSCAN clusters are merged and deduplicated
before persistence.

### 3.5 Historical coverage check

For each proposed theme, the service queries the last 60 days of
articles for matches against the theme's search query. If 3 or more
historical articles exist, the theme is marked `ongoing_topic` instead
of `llm_proposed` — the Candidates inbox filters those out by default
because they're not genuinely emerging.

### 3.6 Persistence to `emerging_topics`

Each surviving theme becomes a row in `emerging_topics`, with:

- `detection_date`, `detection_type` (`new_cluster`, `accelerating`,
  `splitting`, `proto_cluster`)
- `article_count`, `article_uris`, `sample_article_uris`
- `growth_rate`, `velocity`, `velocity_change_pct`
- `key_themes`, `representative_keywords`
- `volume_score`, `velocity_score`, `diversity_score`, `novelty_score`,
  `composite_score`
- `centroid_embedding` (1536-d vector)
- `actors`, `events`, `implications`, `signals`, `synthesis` (V2 fields
  added by a follow-on LLM enrichment pass)

## 4. The Wiley-fit judge

After detection persists fresh `emerging_topics` rows, the candidate
pipeline scans for rows that don't yet have a corresponding
`topic_candidates` row for the Wiley organisational profile. Each
unjudged cluster is fed to the `wiley_relevance_judge` agent.

### 4.1 What the judge sees

```json
{
  "cluster": {
    "label": "<HDBSCAN keyword-salad label, hint only>",
    "topic_description": "<LLM-generated theme description>",
    "key_themes": [...],
    "representative_keywords": [...],
    "article_titles": ["...", "..."],     // ≤12 titles
    "article_count": <int>,
    "growth_rate": <float>,
    "velocity": "<accelerating|stable|decelerating>"
  },
  "organization": {
    "name": "Wiley Scientific Publisher",
    "description": "...",
    "industry": "Academic Publishing",
    "key_concerns": [...],                // 8 concrete items
    "strategic_priorities": [...],        // 7 items
    "competitive_landscape": [...],
    "regulatory_environment": [...],
    "stakeholder_focus": [...],
    "custom_context": "...",
    "monitored_keywords": [...]
  }
}
```

The `organization` block is the row in `organizational_profiles` for
`Wiley Scientific Publisher` — the same one used elsewhere in the
trend-convergence app. Items there include "R&D funding sustainability",
"Open research initiatives", "Peer review system integrity", etc.

### 4.2 Decision criteria

The judge prompt is explicit about each verdict:

- **`in_scope`** — the cluster's content directly addresses ≥1 entry in
  `key_concerns` or `strategic_priorities` and would plausibly carry a
  standalone Wiley briefing.
- **`adjacent`** — relevant context (regulator, actor, or event that
  materially affects the remit) but the cluster's primary subject is
  not a Wiley concern. Surface, but flag.
- **`off_scope`** — no plausible bearing on the remit. Auto-rejected at
  insert; never appears in the inbox.

The prompt instructs the judge to "be conservative on `in_scope` —
better to mark borderline cases `adjacent` than to flood the analyst's
inbox." On the wileytest live run this produces roughly 1 in-scope,
14 adjacent, 13 off-scope out of 28 clusters — a 50% noise rate that
the inbox absorbs and the analyst triages in seconds.

### 4.3 What the judge returns

```json
{
  "verdict": "in_scope" | "adjacent" | "off_scope",
  "score": 0.0-1.0,
  "rationale": "one sentence naming the specific overlap (or absence)",
  "proposed_topic_name": "3-6 word Title Case name",
  "proposed_description": "1-2 sentence framing for an executive reader",
  "proposed_tags": ["lowercase-hyphenated-1", "lowercase-hyphenated-2"]
}
```

`proposed_topic_name` is what populates the candidate card and, on
promotion, becomes the `forecast_topic_metadata.display_name`.

Configuration: `gpt-4.1-mini` at temperature 0.2 with a 600-token cap.
Concurrency is capped by `WILEY_CANDIDATE_JUDGE_CONCURRENCY` (default 4)
so a 28-cluster scan saturates four LLM workers in parallel.

### 4.4 Persistence to `topic_candidates`

Each judged cluster becomes a row in `topic_candidates`, unique on
`(emerging_topic_id, org_profile_id)`. Off-scope verdicts are persisted
with `triage_status='rejected'` and `rejected_reason='off_scope (auto)'`
so the audit trail keeps them but the default inbox filter
(`triage_status='pending'`) hides them.

## 5. Triage actions in detail

### 5.1 Promote

Hitting Promote on a pending candidate kicks off a background task
that runs the same multi-stage pipeline the wizard's Build step uses,
seeded from the candidate's articles. Steps, in order:

1. **Create draft topic** — inserts a `forecast_topic_metadata` row
   with `status='draft'`, `display_name = proposed_topic_name`,
   `description = proposed_description`, `tags = proposed_tags`,
   `source_candidate_id = <this candidate>`.
2. **Three Horizons** — pulls full article rows for the candidate's
   first 50 URIs, builds the same `emerging_topic_driver` prompt the
   Future Horizons tab uses, calls `gpt-5.4`, parses out the 10–14
   scenarios, and writes to `future_horizons_runs`.
3. **Paired assessment** — calls `assess_run` for `mode='live'` and
   `mode='placebo'` against the new horizons run with
   `window_weeks=12`, then `apply_baseline_correction` so the per-pool
   support rates are placebo-corrected. See the Forecast Tracker's
   "How it works" page for the full methodology.
4. **Overlay draft** — calls `wiley_overlay_agent` with the new
   horizons run + the just-completed assessment, writes a `.proposed`
   JSON file to `data/wiley_horizons/{slug}_deck_overlay.json.proposed`,
   and flips the topic's `overlay_status` to `auto_generated`.
5. **Mark promoted** — updates the candidate row:
   `triage_status='promoted'`, `promoted_to_topic=<topic name>`,
   `triaged_at=NOW()`.

The wizard auto-opens at step 3 (overlay review) when the job finishes.
Runtime is typically 8–12 minutes per promotion — that is what operators
observe, not an instrumented measurement.

### 5.2 Snooze

Sets `triage_status='snoozed'` and `snooze_until = CURRENT_DATE + N
days`. The candidate disappears from the default inbox until the daily
sweeper picks it back up.

The sweeper runs once every 24h inside the scheduler loop. SQL:

```sql
UPDATE topic_candidates
SET triage_status = 'pending', snooze_until = NULL, updated_at = NOW()
WHERE triage_status = 'snoozed'
  AND snooze_until IS NOT NULL
  AND snooze_until <= CURRENT_DATE
```

### 5.3 Merge

Sets `triage_status='merged'` and `promoted_to_topic = <target topic
name>`. No automatic re-assessment is fired — the candidate's article
URIs are not pushed into the target topic's article set today. The next
scheduled assessment of the target topic will pick up the articles
naturally if they match the topic's keyword/topic-string filter.

### 5.4 Reject

Sets `triage_status='rejected'` with `rejected_reason = <free text>`.
Rows are kept forever as a fewshot delta — future improvements to the
judge prompt can be evaluated against the corpus of rejected
candidates.

## 6. Promotion pipeline — methodology details

This section dives deeper into what the promotion (or wizard Build)
pipeline does at each stage.

### 6.1 Three Horizons seed

The horizons LLM call receives:

- The candidate's first 50 articles, with `title`, `summary`,
  `publication_date`, `sentiment`, `category`, `future_signal`,
  `driver_type`, `time_to_impact`, and `quality_score`.
- A formatted article-references block (`[1] Title (date)` lines).
- An aggregated stats block (sentiment counts, category counts, driver
  counts).
- The `emerging_topic_driver.json` prompt template that asks for 10–14
  scenarios distributed across Probable / Plausible / Possible /
  Preferable.

The response is parsed; `raw_output.scenarios` is what later assessments
score against, and what the overlay agent collapses into deck scenarios.

### 6.2 Paired assessment

Each assessment runs in two passes — `live` and `placebo`:

- **Live**: articles from `[forecast_date, forecast_date + window_weeks]`.
- **Placebo**: articles from `[forecast_date - window_weeks,
  forecast_date]` (a temporal negative control).

For each pass:

1. Pull the article pool for the topic's tags — the tracked topic's
   `source_topics` when its deck name is decoupled from the corpus tag,
   else the topic name itself. There is **no corpus-wide fallback**; a
   topic with no matching, embedded articles yields an empty pool rather
   than a widened one. The window is cut on `submission_date`.
2. For each article, score against every scenario with the cross-encoder
   reranker. Articles where the top scenario's gap from the runner-up is
   below `margin` (default 0.04) are routed to the "ambiguous" bucket.
3. Surviving article–scenario pairs are sent to a classifier LLM
   (`gpt-5.4-mini` by default) which returns one of six verdicts —
   `supports_trajectory`, `supports_state_contradicts_trajectory`,
   `contradicts`, `better_fits_other_scenario`, `neutral_context`,
   `unrelated` — plus an evidence type and a confidence score.
4. Counts are aggregated per scenario into a verdict label
   (Accelerating / On-track / Stalled / Off-track / Inconclusive).

`apply_baseline_correction` subtracts the placebo's per-scenario
support rate from the live rate. The resulting `net_rate` is what the
deck reports as "Strengthening" / "Stable" / "Cooling" — a separate axis
from the per-scenario verdict labels above.

See the [Forecast Tracker methodology](how_it_works_forecast_tracker.md)
for the full pipeline, the scoring formulas and the two label axes.

### 6.3 Overlay agent

`wiley_overlay_agent` reads the new horizons run's raw scenarios plus
the just-completed assessment's per-scenario verdicts. It groups the
10–14 raw scenarios into 4–5 deck-level scenarios with the fields the
Strategic Domains slide needs:

- `deck_scenario_name`, `horizon` (`h1` / `h2` / `h3` / blends)
- `consensus_pct` — typically inherited from the assessment's
  per-scenario consensus, sometimes summarised across the grouped raws
- `primary_signal` — 1–2 sentence concrete-actor framing
- `minority_view` — counterpoint when supporting evidence is split
- `decision_fork` — what to do if the trend strengthens (`favorable`)
  vs cools (`adverse`)
- `action_windows` — `0_6_months` / `6_18_months` / `18_plus_months`
- `scenario_title_to_deck_key` — a complete mapping so every raw
  scenario routes to exactly one deck scenario

Model: `gpt-4.1` with `reasoning_effort='high'`. Output lands as a
`.proposed` file the human reviews in wizard step 3.

Two things about overlay files that are easy to get wrong:

- An overlay is matched to a topic by the `topic` field **inside** the
  JSON, not by its filename. Renaming the file changes nothing.
- `horizon` may span — `h1_h2`, `h2_h3`, `h1_h3` — and three of the five
  production overlays use spanning values. The deck builder treats them
  as display-only and takes the real horizon from the first raw scenario
  in the group, so anything validating overlays against a strict
  h1/h2/h3 enum will reject working files.

If an overlay's `scenario_title_to_deck_key` matches none of a run's
scenario titles, the assessment falls back to raw scenarios and logs an
error rather than producing an empty result.

## 7. The Add-topic wizard

For analyst-driven additions (no candidate), the wizard mirrors the
promotion path but uses the corpus as the article seed instead of a
candidate's URIs.

| Step | What happens | Backend |
| --- | --- | --- |
| 1. Framing | Creates `forecast_topic_metadata` (`status='draft'`) with name, display name, description, owner, tags. | `POST /api/forecast/topics` |
| 2. Build | Background task: pulls recent articles tagged with the topic name, runs Three Horizons + paired assessment + overlay draft. Wizard polls progress, auto-advances on completion. | `POST /api/forecast/topics/{topic}/wizard/build` |
| 3. Overlay | Structured editor on the `.proposed` overlay. Mini-preview shows how each card will look in the Strategic Domains slide. Approve writes the production overlay file and flips `overlay_status='human_reviewed'`. | `POST /api/forecast/topics/{topic}/overlay/approve` |
| 4. Delivery | Cadence + recipient email. Final step flips `status='active'`. | `PATCH /api/forecast/topics/{topic}/delivery` + metadata |

Wizard state is persisted in `localStorage` keyed by topic name —
closing the modal mid-build is safe; reopening for the same topic
resumes at the correct step and re-attaches to the running task.

The Build step requires articles tagged with the topic name in the
corpus. If none exist, the build fails with a clear message asking
either to add articles or to rename the topic to match existing
article tags. This is a deliberate trade-off: the analyst-driven path
trusts the corpus's existing tags rather than auto-tagging new
articles, which would risk silently widening the topic's article set.

## 8. Scheduling and tunables

The scheduler lives in `app/tasks/wiley_candidate_scheduler.py` and is
started in the FastAPI service's lifespan (45 second startup delay +
60–1800 second jitter to stagger multi-tenant restarts).

Tick logic, every 24 hours:

1. Run the snooze sweeper unconditionally.
2. If `WILEY_CANDIDATE_SCAN_INTERVAL_DAYS` (default 7) have elapsed
   since the last successful scan, run a full discovery + judging pass.
3. On scan failure, leave `last_scan_at` unchanged so the next tick
   retries.

Environment variables:

| Variable | Default | Effect |
| --- | --- | --- |
| `WILEY_CANDIDATE_SCAN_ENABLED` | `true` | Set to `false` to disable the scheduler entirely. |
| `WILEY_CANDIDATE_SCAN_DAYS_BACK` | `14` | Detection window for the emerging-themes scan. |
| `WILEY_CANDIDATE_SCAN_INTERVAL_DAYS` | `7` | Days between full scans. The sweeper still runs every 24h. |
| `WILEY_CANDIDATE_JUDGE_CONCURRENCY` | `4` | LLM workers for the relevance judge. |
| `WILEY_ORG_PROFILE_NAME` | `Wiley Scientific Publisher` | Row to load from `organizational_profiles`. |

The "Scan now" button in the Candidates inbox bypasses the cron — it
fires `POST /api/forecast/candidates/scan` immediately and the inbox
polls the resulting `task_id` for completion.

## 9. Data model

Three tables back this tab.

### `forecast_topic_metadata` (sidecar)

Keyed by `topic` (text PK). One row per tracked topic.

| Column | Purpose |
| --- | --- |
| `topic` | The universal join key. Matches `future_horizons_runs.topic`, `forecast_topic_delivery.topic`, and the `topic` field in the overlay JSON file. |
| `display_name` | Optional deck-friendly name when the canonical `topic` is internal. |
| `description` | 1–2 sentence framing shown in the Topics dashboard. |
| `owner` | Free-text username. Soft link to `users.username`. |
| `status` | `draft` / `active` / `archived`. |
| `tags` | JSONB string array. |
| `overlay_status` | `missing` / `auto_generated` / `human_reviewed`. |
| `source_candidate_id` | Optional FK to `topic_candidates.id` when the topic was promoted from a candidate. |
| `created_at`, `updated_at` | Timestamps. |

Migration: `fa_006_add_topic_metadata.py`. Source-candidate column
added in `fa_007_add_topic_candidates.py`.

### `topic_candidates` (inbox)

One row per `(emerging_topic, organisational_profile)` pair the judge
has evaluated.

| Column | Purpose |
| --- | --- |
| `id` | Serial PK. |
| `emerging_topic_id` | FK to `emerging_topics.id`, `ON DELETE CASCADE`. |
| `org_profile_id` | FK to `organizational_profiles.id`. |
| `relevance_verdict` | `in_scope` / `adjacent` / `off_scope`. |
| `relevance_score` | 0.0–1.0 judge confidence. |
| `relevance_rationale` | Judge's one-sentence reason. |
| `proposed_topic_name`, `proposed_description`, `proposed_tags` | Naming the analyst can adopt with one click. |
| `triage_status` | `pending` / `snoozed` / `rejected` / `promoted` / `merged`. |
| `snooze_until` | Date the sweeper unsnoozes on. |
| `rejected_reason` | When `triage_status='rejected'`. `'off_scope (auto)'` for auto-reject. |
| `promoted_to_topic` | The topic name on `forecast_topic_metadata`. |
| `triaged_by`, `triaged_at` | Audit. |

Unique constraint on `(emerging_topic_id, org_profile_id)` keeps the
upsert idempotent across repeated scans.

### `emerging_topics` (upstream source)

Owned by the emerging-themes service, not the Topics tab. The judge
reads this table; the inbox joins to it for display data (article
counts, growth rate, etc.).

Migration history: `et_001_add_emerging_topics_tables.py` and
`et_002_add_v2_emerging_topics_columns.py`.

## 10. Files to read for code-level detail

- `app/services/emerging_topics/emerging_topics_service.py` — top-level
  detection orchestration.
- `app/services/emerging_topics/cluster_detector.py` — HDBSCAN config.
- `app/services/emerging_topics/novelty_scorer.py` — three-component
  novelty.
- `app/services/emerging_topics/theme_proposer.py` — LLM theme
  proposal prompt + sampling.
- `app/services/wiley_candidate_pipeline.py` — judging, promotion,
  wizard-build helper.
- `app/tasks/wiley_candidate_scheduler.py` — cron loop + sweeper.
- `app/routes/wiley_candidates_routes.py` — inbox HTTP API.
- `app/routes/forecast_assessment_routes.py` — wizard build endpoint
  and overlay endpoints.
- `data/auspex/agents/wiley_relevance_judge.md` — the judge prompt.
- `data/auspex/agents/wiley_overlay_agent.md` — the overlay agent.
- `alembic/versions/fa_006_add_topic_metadata.py` — metadata sidecar
  table.
- `alembic/versions/fa_007_add_topic_candidates.py` — inbox table.
