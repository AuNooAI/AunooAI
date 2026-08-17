# How the Forecast Tracker works

The Forecast Tracker back-tests a stored Three Horizons forecast against
fresh evidence. Given a forecast that says "five plausible H1 scenarios,
six H2, three H3" and a window of articles published after that forecast
was generated, it answers: which scenarios are tracking, which are off,
which are inconclusive, and what is happening that the forecast didn't
anticipate?

The output is a per-scenario verdict grid plus a "surprises" panel for
emerging themes that fall outside every scenario.

## What an assessment does

The assessment pipeline runs in five stages.

### Stage A — pool the article window

Fetches every article that entered the corpus between the forecast date
and `today` (or `forecast_date + window_weeks` weeks for a paired run).
Cap is `max_articles` (default 2000).

Two details that matter when a pool comes back smaller than expected:

- The window is cut on **`submission_date`** — when the article was
  collected — not `publication_date`. A backfill of older articles lands
  in the window by collection date, not by when it was written.
- Articles are filtered to those tagged with this topic, and
  `embedding IS NOT NULL` is a hard requirement. There is **no
  corpus-wide fallback** — a topic whose articles were never embedded
  yields an empty pool rather than a widened one.

Which topic tags are drawn from comes from the tracked topic's persisted
`source_topics` when its deck name is decoupled from the corpus tag
(e.g. deck topic "Quantum Advantage" → article tag "Quantum Computing"),
else just the deck name itself.

### Stage B — match each article to scenarios

For each article in the pool, the system computes a relevance score
against every scenario in the forecast. Two modes:

- **DB granularity** — score against the raw scenarios as the forecast
  produced them (~10–14 per run).
- **Deck granularity** (default for topics with a deck overlay) —
  collapse overlapping raw scenarios into the 4–5 named deck scenarios
  the customer actually sees in the PPTX. Margin-based gating works
  better because deck scenarios are well-separated.

Articles whose top-score gap from the second-best is below the margin
(default 0.04) are routed to an "ambiguous" bucket and shown in the
surprises panel. Scoring is a cross-encoder reranker, gated at a
sigmoid'd score of 0.5.

> Reranking is behind `RERANK_ENABLED`, which defaults to `false`. With
> it unset every article falls into the ambiguous bucket and every
> scenario returns Inconclusive. If a whole assessment comes back
> Inconclusive with a full surprises panel, check this first.

### Stage C — classify direction

Each article–scenario pair that survives stage B is sent to an LLM
classifier. The model defaults to `gpt-5.4-mini`. (The prompt template
at `data/prompts/forecast_assessment/current.json` carries a
`model_recommendations` block naming `gpt-4.1-mini` as primary — that
field is advisory and does not set the runtime model.)

The classifier is deliberately conservative — its system prompt states
that "generic topical overlap is NOT support — only direction-matching,
dated evidence counts." It returns one of **six** verdicts:

| Verdict | Meaning |
| --- | --- |
| `supports_trajectory` | Concrete dated evidence consistent with the predicted direction |
| `supports_state_contradicts_trajectory` | Confirms the subject, but the trajectory is stabilising or reversing |
| `contradicts` | Evidence running against the predicted direction |
| `better_fits_other_scenario` | On-topic but fits a sibling scenario better |
| `neutral_context` | Background or commentary, no directional evidence |
| `unrelated` | Off-topic for this scenario |

plus an evidence type — `milestone`, `leading_indicator`, `commentary`
or `anecdote` — and a confidence score. Only verdicts with confidence
≥ 0.5 count toward the aggregates.

Aggregation treats `supports_state_contradicts_trajectory` as a
contradiction: `eff_contra = contradicts + state_only`. The remaining
categories (`neutral_context`, `unrelated`, `better_fits_other_scenario`)
are pooled into the `neutral` column.

### Stage D — render verdicts

For each scenario the counts are reduced to four metrics, then a label.

```
eff_contra        = contradicts + state_only
directional_rate  = (supports − eff_contra) / (supports + eff_contra)
velocity          = (supports − eff_contra) / months_elapsed
milestone_density = milestone-or-leading-indicator hits / confident verdicts
coverage          = supports / (3.0 × months_elapsed)
```

`coverage` anchors to an assumed baseline of ~3 supporting events per
month; there are no per-scenario priors yet.

The label is a decision tree, evaluated in order:

- **Inconclusive** — fewer than 6 confident verdicts. Note this is a
  count of *classified articles*, not of supporting ones: a scenario with
  6 confident verdicts that are all contradictions is not Inconclusive.
- **Off-track** — `directional_rate < −0.2`, or ≥ 3
  `supports_state_contradicts_trajectory` verdicts outnumbering supports.
- **Accelerating** — `velocity > 0` **and** `milestone_density > 0.15`
  **and** `coverage > 1.0`. The milestone requirement is the guard
  against a scenario "accelerating" on op-eds alone.
- **On-track** — `directional_rate > 0.2` and `velocity >= 0`.
- **Stalled** — `|directional_rate| <= 0.1` and `|velocity| <= 1.0`.
- **Inconclusive** — anything left over.
- **Done** — set by analyst action rather than computed. These scenarios
  skip the reranker and classifier stages entirely.

### Two label axes, not one

Strengthening / Stable / Cooling are **not** verdict labels. They belong
to a separate axis — the paired-baseline correction described below — and
the two are reported side by side:

| Axis | Values | Answers |
| --- | --- | --- |
| Per-scenario verdict | Accelerating · On-track · Stalled · Off-track · Inconclusive · Done | How is the evidence for this scenario behaving? |
| Baseline correction | Above baseline · At baseline · Below baseline | Is that stronger than it was *before* the forecast existed? |
| Customer rendering of the baseline axis | Strengthening · Stable · Cooling | (the same thing, in the deck's language) |

The UI headline chip prefers the baseline label whenever a paired
correction exists, and falls back to the verdict label otherwise — which
is why a scenario can read "Strengthening" in the header while its card
shows "On-track".

### Stage E — find surprises

The residual is the union of the **ambiguous** bucket (stage B) and
articles classified **`unrelated`** (stage C). If fewer than 8 articles
land there, the panel is skipped entirely.

The residual is clustered with HDBSCAN (`min_cluster_size=5`, falling
back to DBSCAN at `eps=0.35, min_samples=5, cosine` where hdbscan isn't
installed); noise points and clusters under 5 articles are dropped.
Each surviving cluster is then run through `forecast_cluster_label_agent` which
gives it a human-readable name and decides whether the cluster is
genuinely on-topic. Off-topic clusters (e.g. retrieval-noise articles
about unrelated subjects that share a keyword with the forecast topic)
are dropped. Off-topic articles inside otherwise-relevant clusters are
pruned.

The surface result is the "Emerging themes" panel: clusters of
recent articles the forecast didn't anticipate. Analysts can promote
any cluster to a new addendum scenario from this panel.

## Paired (live + placebo) baseline

Running just "live" mode tells you the raw support rate of each scenario
in the post-forecast window. But that rate is inflated by the natural
base rate at which articles in the corpus drift toward any plausible
trajectory. To correct, a paired run also assesses the same forecast
against the `window_weeks` BEFORE the forecast was generated — a
temporal placebo. The pre-forecast support rate is subtracted from the
post-forecast rate, isolating the incremental support attributable to
the post-forecast window.

Concretely, per scenario:

```
live_rate    = live.supports    / live_pool        # pool = evidence_count
placebo_rate = placebo.supports / placebo_pool
net_rate     = live_rate − placebo_rate

net_rate >  0.005  → Above baseline  → "Strengthening"
net_rate < −0.005  → Below baseline  → "Cooling"
otherwise          → At baseline     → "Stable"
```

Both windows are bounded to the same number of weeks, which is what makes
the placebo a fair control — it removes pool-size asymmetries from
collection gaps or differing elapsed durations.

The deck always reports the baseline-corrected rate, not the raw rate.
This is what "Strengthening" actually means — net support above the
placebo baseline. It is independent of the per-scenario verdict in
stage D: a scenario can be On-track and At baseline at the same time,
meaning the evidence is directionally positive but no more so than
before the forecast was written.

## How it fits with the rest of the system

- **Three Horizons** (Future Horizons tab) generates the forecast. The
  output is stored in `future_horizons_runs` with a UUID `run_id`.
- **Forecast Tracker** (this tab) runs assessments against a `run_id`,
  one row per assessment in `forecast_assessments`. Per-scenario verdict
  data lands in `forecast_scenario_verdicts`.
- **Wiley deck overlay** (`data/wiley_horizons/*_deck_overlay.json`)
  maps raw scenarios to the 4–5 deck scenarios. Generated by the
  `wiley_overlay_agent` and reviewed by an analyst before any deck ships.
  Overlays are matched to a topic by the `topic` field *inside* the JSON,
  not by filename — renaming the file changes nothing.
- **Wiley bundle** (Deliverables panel) packages the latest assessment
  for one or more topics into a PPTX deck via the multi-agent supervisor.
  Briefing, recommendations, next steps, cross-cutting themes, and the
  executive summary letter are produced by separate agents and reviewed
  by `wiley_reviewer_agent` before the bundle ships.

## Re-running an assessment

The "Reassess" button at the top of the tracker fires a paired run
against the current `run_id`. Window defaults to 8 weeks but is
configurable in the modal.

Each re-run **inserts a new row** in `forecast_assessments` rather than
overwriting the previous one; the tracker simply reads the most recent
row per topic. Nothing is lost, and the history is what the trajectory
heatmap and `GET /api/forecast/snapshots/by-topic` are built from.

A background monitor (`app/tasks/forecast_tracker_monitor.py`) can do
this automatically — every 6 hours it looks for topics with an overlay
whose latest live assessment is older than 30 days and fires a paired
run. **The loop is gated on `FORECAST_TRACKER_AUTO_RUN` and exits
immediately when that is unset**, which is the case on most tenants. So
in practice re-assessment is a manual action.

The Topics dashboard's health dot turns amber after 30 days without a
re-assessment and red after 90 — on a tenant without auto-run, an amber
dot means nobody has pressed Reassess, not that anything is broken.
