# Wiley quarterly update — situation, diagnosis, plan

Status: pending implementation. Captured so the conversation can be compacted
and the work re-entered with full context.

## The situation we're in

* Wiley was sold a **strategic foresight service** in February 2026. The
  founding sales deck is `Wiley Horizons Final  (2).pptx` at the repo root.
  What was sold: continuous collection + AI enrichment + structured
  foresight analysis using Three Horizons + Five Strategic Domains +
  Black Swans + Decision Framework + Briefing Synthesis.
* A quarterly update is now due.
* Wiley want a **"what's changed since February"** view as part of that
  update.
* We have a **~30-day article-collection gap** in the run-up window.

## What works and what doesn't

| Component | Status |
|---|---|
| Article ingestion, embeddings, HDBSCAN clustering | Works |
| Emerging-themes discovery + Wiley-fit relevance judge + Candidates inbox | Works |
| Three Horizons generation | Works (exploratory, as intended) |
| Per-topic Briefing Synthesis agent | Works |
| Strategic Overview, Cross-cutting Themes, Decision Framework, Recommendations, Next Steps | Works |
| Black Swans / Wild Cards / Outlier scans (EOS) | Works |
| PPTX / DOCX / Markdown bundle rendering | Works |
| Multi-agent supervisor + LLM-as-judge reviewer | Works (sanitizer in place to stop loops) |
| Topics dashboard + Add-topic wizard + multi-tenant deploy | Works |
| **Forecast Tracker / `current_consensus_pct` / Strengthening-Cooling verdicts** | **Does not work as advertised** — see diagnosis |

## The diagnosis (the part that's BS)

The Forecast Tracker overlay I built after the original sale takes the
Three Horizons output and "back-tests" it against post-forecast articles.
Two layered problems:

1. **Conceptual**: Three Horizons is exploration, not prediction. The
   Probable / Plausible / Possible / Preferable scenarios are not
   forecasts you can score. Back-testing them is a category error.
2. **Measurement**: even if we wanted to score them, the metric
   (`current_consensus_pct = supports / total` over article framing
   classifications) measures **press attention to a narrative**, not
   **whether the predicted events happened**. Ten op-eds saying the
   same thing count as 10 supports; one investigative piece documenting
   a 1,200-paper retraction counts as 1.

The exec-summary agent built on top of this confidently emits prose like
"conditions deteriorated", "consensus dropped 78% → 21%", "the forecast is
playing out" — none of which the underlying measurement supports.

**The Forecast Tracker is not in the original sales deck.** Wiley didn't
buy it. It was something I added. The plan below removes its overclaim
layer and reverts to delivering what was actually sold, plus an honest
"what's changed" view.

## Plan to ship the quarterly update credibly

### 1. Backfill the 30-day collection gap

ArXiv and Semantic Scholar support full date-range backfill via their
APIs. NewsAPI / NewsData / TheNewsAPI / NewsFirehose support partial
backfill (depends on tier and whether the gap window is still in the
~30-day API access range). Bluesky paginates backward with rate limits.
RSS is mostly lost — RSS feeds only expose current items.

**Step 1 — detect the precise gap.** Before backfilling we need to know
*which* window. Query `articles.publication_date` distribution per
collector (`articles.source` or `articles.collector_name`), find the
longest contiguous null span ≥ 7 days, and write:

```json
{
  "start": "2026-04-21",
  "end":   "2026-05-20",
  "days":  29,
  "sources_affected": ["NewsAPI", "Bluesky", "RSS:Nature", "RSS:Science"],
  "n_recovered_per_source": null
}
```

to `data/wiley_horizons/collection_gap.json`. This file is the single
source of truth for the backfill script *and* the disclosure footnote
(§5) — they must agree on the same dates.

**Step 2 — backfill.** `scripts/backfill_collection_gap.py` reads
`collection_gap.json` and walks each tracked Wiley topic, calling every
collector with explicit `since=GAP_START` / `until=GAP_END` bounds.
Updates `n_recovered_per_source` in the JSON file as it goes.
Estimated ~2-3 hours of compute. Expected recovery: 60–75% of the
missing articles (API sources mostly recoverable; RSS lost).

Files:
- `scripts/detect_collection_gap.py` (NEW) — outputs the JSON above.
- `scripts/backfill_collection_gap.py` (NEW)
- `data/wiley_horizons/collection_gap.json` (NEW — generated artifact)

### 2. Event extraction stage (the single biggest credibility lift)

Add a per-article LLM extraction pass that pulls structured *events*
from each article in the quarter window, per topic:

```
{
  "actor": "Springer Nature",
  "actor_normalized": "springer-nature",
  "action": "retracted",
  "subject": "1,200 papers from Hindawi journals",
  "subject_normalized": "hindawi-retraction-1200-papers",
  "magnitude": {"value": 1200, "unit": "papers"},   // OPTIONAL — many events have no numeric magnitude
  "event_date": "2026-03-14",
  "source_urls": ["...", "..."],                     // aggregated across N source articles
  "confidence": 0.87,                                // LLM self-confidence 0-1
  "requires_review": false,                          // true when confidence < 0.6 or critical fields missing
  "scenario_relevance": ["Attacks on Expertise & Peer Review.peer_review_breakdown"]
}
```

**Dedupe rule (critical).** Multiple articles reporting the same event
must collapse to ONE row keyed by `(actor_normalized, action, subject_normalized, event_date)`.
Aggregate `source_urls[]` rather than duplicating. Otherwise the
"what's changed" slide reads like an article count, not an event count
— exactly the bug we're fixing.

**Confidence + review surface.** Events with `confidence < 0.6` or
missing critical fields (no actor / no date) are flagged
`requires_review=true`. They still persist but the editor (§6) shows
them under a separate "Needs review" header so the analyst can promote
or drop each one.

**`magnitude` is optional.** Many events have no numeric magnitude
(Springer announces new policy, NIH publishes guidance, Max Planck
adopts diamond OA). Don't force the model to invent numbers.

Events aggregate per topic + per scenario. The bundle then has actual
facts to cite under "what's changed" — not article counts.

**Sync vs batch — resolved.** Run extraction **synchronously** as a
new supervisor stage between `briefings` and `exec_summary`. Quarterly
bundle runs 4×/year; nightly batch wastes compute on articles that
won't be cited. Sync gives fresher facts and one fewer cron to babysit.

Files:
- `data/auspex/agents/wiley_event_extractor_agent.md` (NEW)
- `app/services/wiley_event_extraction.py` (NEW) — extraction runner,
  batches articles, dedupes per the rule above, caches results.
- Migration `fa_008_add_extracted_events` — table:
  `extracted_events(id, assessment_id, topic, actor, actor_normalized,
  action, subject, subject_normalized, magnitude_value, magnitude_unit,
  event_date, source_urls JSONB, confidence REAL, requires_review BOOL,
  include_in_deck BOOL DEFAULT true, scenario_relevance JSONB,
  created_at, updated_at)`. Unique key on
  `(topic, actor_normalized, action, subject_normalized, event_date)`.
- Wire into the bundle supervisor as a new `events` stage between
  `briefings` and `exec_summary`. Output feeds the exec-summary + the
  What's Changed slide.

Estimated: ~1 day.

### 3. Strip the Forecast Tracker overclaim layer

Reframe the bundle as a **Quarterly Foresight Refresh + What's Changed**
deliverable. The synthesis pipeline underneath doesn't change; only the
*claim layer* does.

Specific changes:

* **Rename — be precise about the surfaces.**
  * Deck cover: *"Wiley Quarterly Foresight Update — Q2 2026"*.
  * App top-level dashboard tab: "Forecast Tracker" → **"Quarterly
    Brief"**.
  * Per-topic Forecast Tracker tab inside a topic: **keep the name**
    (internal-only, used for diagnostic drill-down, has deep links
    we don't want to break).
  * `docs/how_it_works_forecast_tracker.md` → renamed
    `docs/how_it_works_quarterly_brief.md`, content rewritten.
* **Drop verdict language from the deck**: no "Strengthening / Stable /
  Cooling" chips, no "consensus 78% → 21%" deltas, no "the forecast is
  playing out" prose. The per-scenario data lives on in the
  per-topic-tab; the **bundle headlines** stop using it.
* **Keep the data.** `forecast_assessments` and
  `forecast_scenario_verdicts` rows continue to be written by the
  assessment pipeline — useful for internal analysis, longitudinal
  curiosity, future research. Only the *bundle's claim layer*
  changes. Don't drop tables or stop running assessments.
* **Exec summary agent** — third rewrite (v3.0.0). Prose centres on:
  (a) named events from the new extraction stage,
  (b) new emerging themes from discovery,
  (c) Three Horizons scenario-set drift (the scenario set itself
      changed quarter-over-quarter),
  (d) press-attention shifts labelled **as press attention**, not as
      forecast accuracy.
  Drop "Q-over-Q baseline" framing entirely.
  **Hard rule: every percentage in the letter must be traceable to
  either `events[*].magnitude` (factual) or `coverage_shifts[*]`
  (labelled as press attention). No `vs_prior_assessment` deltas as
  headline numbers — ever.**
* **What's-changed slide section** built from those four signals (see
  §4 below).

Files:
- `app/services/forecast_pptx_export.py` — drop the flip-detail slide,
  the verdict chips on Strategic Domains cards, the "consensus X → Y"
  drift line, and the "Status changed" slides.
- `app/services/forecast_bundle_pptx.py` — drop the
  `_add_no_prior_stub_slide`, the gap-analysis matrix slide, and the
  reviewer's pre-existing "first snapshot" path. Restructure per-topic
  section to: briefing → events this quarter → scenarios → surprises →
  recommendations → next steps.
- `data/auspex/agents/wiley_exec_summary_agent.md` — third rewrite,
  centred on events + emerging themes + scenario drift + press
  attention (labelled).
- `data/auspex/agents/wiley_reviewer_agent.md` — relax rubric items
  that gated on Tracker-style claims.

Estimated: ~half day for the deck changes, ~half day for the exec
summary rewrite and reviewer adjustment.

### 4. The "What's changed since February" section

Built honestly from four signals. **Priority order** (the slide drops
items from the bottom when budget is tight):

1. **Named events that happened** (from the event extraction stage).
   *Always shown.* Cite actor, action, magnitude (if present), date,
   source. This is what a director wants under "what's changed".
2. **Three Horizons scenario-set drift**. Re-run produces a slightly
   different scenario set; the diff is meaningful ("Last quarter
   'AI-fraud detection lag' was Plausible; this quarter the evidence
   pushed it to Probable").
3. **New emerging themes** the discovery pipeline surfaced since the
   last bundle. The Candidates inbox already has this — surface
   in-scope candidates that didn't exist last quarter.
4. **Press-attention shifts**, labelled as such ("the China R&D
   narrative quieted, peer-review delegitimization grew"). NOT as
   forecast-tracking. Dropped first if the slide overflows.

**Empty-state behaviour.** If a topic has zero named events in the
quarter, render *"No new headline events this quarter for this
topic"* — not a blank section, not "no data" (which reads as a system
failure). The other three signals can still appear underneath.

Slide section format:

```
What's changed since February
─────────────────────────────
NAMED EVENTS THIS QUARTER
  • Springer Nature retracted 1,200 papers from Hindawi journals (2026-03-14)
  • NIH announced 18% reduction in extramural grants (2026-04-02)
  • Max Planck network adopted Diamond OA (2026-04-30)
  …

SCENARIOS THAT MOVED IN OUR FRAMING
  • 'AI-fraud detection lag': Plausible → Probable
  • …

NEW ON THE WATCH
  • Two emerging clusters surfaced this quarter: <name>, <name>
  …

WHERE PRESS ATTENTION SHIFTED  (share of coverage by scenario)
  • Peer-review delegitimization: rose +X%
  • US-China R&D decoupling: fell -Y%
```

Files:
- `app/services/forecast_pptx_export.py` — new `_add_whats_changed_slide`
  rendering the above.
- `app/services/forecast_bundle_pptx.py` — wire into front-of-deck
  position (between Strategic Overview and Five Domains).

Estimated: ~half day.

### 5. Collection-gap disclosure footnote + methodology appendix

A single line on slide 2 (Executive Summary), populated from
`collection_gap.json`:

> *"Note: a {days}-day collection interruption between {start} and
> {end} reduced article volume for this period. API-based sources
> (ArXiv, Semantic Scholar, NewsAPI, TheNewsAPI) were backfilled to
> ~{recovery_pct}% of expected volume; RSS-only material from that
> window is unrecoverable. See methodology appendix on the final
> slide."*

And a full **methodology appendix slide** at the back of the deck —
not a footnote — covering:
- The gap window and which sources were affected.
- Backfill methodology (per-source: which API was queried, what
  window).
- What's NOT in this quarter: RSS items between {start} and {end}.
- Recovery percentage estimate per source from
  `collection_gap.json.n_recovered_per_source`.
- Methodology note on event extraction: deduplication rule, confidence
  threshold, analyst review surface.

Files:
- `app/services/forecast_pptx_export.py` — exec summary slide accepts
  optional `data_quality_note`; new `_add_methodology_appendix_slide`.
- `app/services/wiley_delivery_service.py` — load `collection_gap.json`,
  compute recovery percentages, pass through to renderer.

Estimated: ~half hour after the gap-detection script lands.

### 6. Quarterly Brief Editor page (new — Wiley pays for this)

Wiley pays for the brief; today the analyst has no curation surface.
When the exec summary fabricates a number or a per-topic briefing reads
off, the only recovery is to regenerate everything and hope. We need a
dedicated editor page where the analyst can review, edit, lock, and
ship the bundle.

**Scope (this quarter, MVP):**

- Inline edit on the exec summary letter, cross-cutting themes,
  decision framework, per-topic briefings, and the new "what's
  changed" entries.
- **Lock** mechanism — when a section is locked, supervisor re-runs
  do NOT overwrite it. Mirrors the existing `.proposed/.approved`
  overlay pattern.
- **Regenerate this section** — re-run a single supervisor stage
  with locks respected. Polls progress via the existing
  BackgroundTaskManager pattern.
- **Events curation** — CRUD on `extracted_events` for the period;
  toggle `include_in_deck` per row; promote `requires_review=true`
  events into the deck after analyst sanity check.
- **Preview** — `/api/forecast/brief/{cadence}/{period}/preview.pptx`
  renders the current state (overrides applied, locks respected) and
  opens in a new tab.
- **Single-analyst approval** — "Approve & ship" stamps
  `forecast_bundle_review.approved_by/approved_at`; PPTX download
  endpoint then returns 200 (not 202 waiting-on-approval).

**Schema** (migration `fa_009_add_brief_overrides`): three JSONB
columns, no new tables:

```sql
ALTER TABLE forecast_bundle_synthesis
  ADD COLUMN locked_keys  JSONB DEFAULT '[]'::jsonb,
  ADD COLUMN edit_history JSONB DEFAULT '[]'::jsonb;

ALTER TABLE forecast_assessments
  ADD COLUMN summary_locked_keys JSONB DEFAULT '[]'::jsonb;
```

`locked_keys` = list of dot-paths (e.g. `"exec_summary.letter"`,
`"cross_cutting_themes[2].name"`). `edit_history` = append-only
audit log with hashes (not values, to keep the column small).

**Merge model.** Renderers already read from
`forecast_bundle_synthesis.payload`. Overrides simply mutate that
JSONB in place — renderers are unchanged. A
`_apply_locks_after_call(prior, new, locked_paths)` wrapper in
`wiley_bundle_supervisor.py` restores locked subtrees after every
agent re-run.

**Endpoints** (extend `app/routes/forecast_assessment_routes.py`):

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/forecast/brief/{cadence}/{period_label}` | GET | Full payload + locked_keys + review state |
| `/api/forecast/brief/{cadence}/{period_label}/field` | PATCH | Update one field by JSON path |
| `/api/forecast/brief/{cadence}/{period_label}/lock` | PATCH | Toggle lock on a path |
| `/api/forecast/brief/{cadence}/{period_label}/regenerate-stage` | POST | Re-run one stage; returns task_id |
| `/api/forecast/brief/{cadence}/{period_label}/preview.pptx` | GET | Render current state |
| `/api/forecast/brief/{cadence}/{period_label}/approve` | POST | Single-analyst self-approve |
| `/api/forecast/brief/{cadence}/{period_label}/events` | CRUD | Event curation |

**Frontend.** New route `/forecast/brief/:cadence/:periodLabel`, new
page `ui/src/pages/QuarterlyBriefEditor.tsx`, seven tabs:
ExecSummary | CrossCuttingThemes | DecisionFramework | WhatsChanged |
PerTopic (sub-tabs) | Events | Approval. Lifts the existing
`MarkdownEditor` from `saasmvp-app/`. Reuses the progress modal +
polling pattern from `WileyDeliverablesPanel.tsx`. "Edit & curate"
button on the deliverables panel routes here.

**Estimated: ~1.5 days** (0.5d backend, 1d frontend).

**Behind a feature flag.** `WILEY_BRIEF_EDITOR` env var, default off
on wiley (production) until end-to-end review passes on wileytest.

## Effort summary

| Task | Effort |
|---|---|
| Gap detection + backfill script | 2–3 hrs compute + 1.5 hr script |
| Event extraction agent + service + migration | 1 day |
| Strip Tracker overclaim from deck + exec summary v3 | 1 day |
| Build "What's changed" slide from the 4 honest signals | half day |
| Collection-gap disclosure + methodology appendix slide | half hour |
| **Editor backend** (migration, facade, lock wrapper, 7 endpoints) | half day |
| **Editor frontend** (page, 7 tabs, MarkdownEditor lift, wire-in) | 1 day |
| Multi-tenant rollout (bugfixing → wileytest → wiley) + end-to-end review | half day |
| **Total** | **~4 working days** |

## Order of operations

1. **Kick off the backfill script in background** — longest-running
   and most uncertain (some collectors may rate-limit or fail to find
   the historical window). Run detect-gap first to produce
   `collection_gap.json`, then start backfill.
2. **While backfill runs, land the editor backend**: migration
   `fa_009_add_brief_overrides`, facade helpers,
   `_apply_locks_after_call` wrapper, 7 new endpoints. This is the
   foundation for everything else — once locks work, agent re-runs
   become safe.
3. **Event extraction stage**: agent prompt, runner, migration
   `fa_008_add_extracted_events`, wire into supervisor between
   `briefings` and `exec_summary`. Test on one already-collected topic.
4. **Strip Tracker overclaim**: remove verdict chips / drift deltas /
   status-changed slides from deck; rewrite exec summary agent v3.
5. **Build the "What's changed" slide** using events + scenario drift
   + emerging themes + coverage shifts (in that priority order).
6. **Build the editor UI**: page + 7 tabs + wire-in button on
   deliverables panel.
7. **Add collection-gap disclosure + methodology appendix slide**.
8. **End-to-end review**: regenerate bundle on bugfixing → edit a few
   sections in the editor → lock → regenerate → preview → approve →
   ship. Rsync to wileytest, repeat. Rsync to wiley (behind
   `WILEY_BRIEF_EDITOR=true` flag), do final review, hand to Wiley.

## What we are NOT doing

* Not rebuilding Three Horizons. It works for what it's for.
* Not deleting the Tracker's `forecast_assessments` /
  `forecast_scenario_verdicts` data. It's archived but no longer
  drives the deck headlines.
* Not promising back-testing. Wiley didn't buy it and we can't deliver
  it on Three Horizons output.
* Not promising event extraction is "predictive" — it's factual
  ground-truth, useful in its own right.

## Related context from prior memory

* `feedback_no_ai_slop` — generated text must be plain data narration,
  not "intelligence briefings". Doubly important here since the
  Tracker prose was the worst offender.
* `feedback_troubleshoot_dont_redesign` — when a user reports a bug,
  diagnose the pipeline; don't propose new columns. **Exception
  here**: the user explicitly identified a methodology flaw at the
  measurement layer, not a bug.
* `feedback_just_do_the_work` — execute the plan, don't ask the user
  to run SQL.

## Open questions

1. **Exact gap window dates** per tenant — output of step 1
   (`detect_collection_gap.py` → `collection_gap.json`). Will reveal
   per-source impact; until then we don't know whether to budget 2 or
   4 hours for backfill.
2. **Editor feature-flag rollout.** Default plan: behind
   `WILEY_BRIEF_EDITOR=true` env flag on wiley (production); on by
   default on wileytest and bugfixing. Re-evaluate before quarterly
   handoff — if confident, flip default to on.
3. **Historical Tracker data retention.** Plan: keep
   `forecast_assessments`, `forecast_scenario_verdicts`, and
   `forecast_bundle_synthesis` history indefinitely (cheap storage,
   useful for longitudinal research, the per-topic Forecast Tracker
   tab still reads it). Do NOT migrate or drop.
