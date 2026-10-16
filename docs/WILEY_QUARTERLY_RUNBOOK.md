# Wiley quarterly cycle — runbook

How the quarterly deliverables for Wiley get made on wileytest, in the order the steps
must happen, with what each step writes and what to check before anything is sent. Written
on 15 October 2026 after a day in which the steps were run out of order; the traps section
at the end records what went wrong and how it was undone.

The design reference is `docs/TOPICS_FORECAST_REPORTS_SPEC.md` (sections 4 to 6) and the
customer-facing explanation is `docs/how_it_works_forecast_tracker.md`. This file is the
operating procedure.

## The four things a quarter produces

| Object | Where it lives | Made by |
| --- | --- | --- |
| **Forecast** (Three Horizons run, 12 to 14 raw scenarios per topic) | `future_horizons_runs` | Future Horizons tab, or the Topic Reports "re-run" box |
| **Deck overlay** (collapses the raw scenarios into the 4 to 5 Wiley sees) | `data/wiley_horizons/*_deck_overlay.json` | "Generate overlay proposal" on the Forecast Tracker tab, then approve |
| **Assessment** (how the forecast is tracking against the articles since) | `forecast_assessments` + `forecast_scenario_verdicts` + `forecast_article_verdicts` | "Re-run assessment" on the Forecast Tracker tab, or the auto-run |
| **Deliverables**: the quarterly bundle and the topic report deck | `forecast_bundle_synthesis` / `forecast_bundle_review`; `$TMPDIR/topic_report_render_cache_<db>/` | Deliverables panel; Topic Reports panel |

Every assessment points at one forecast run, every overlay was written for one run's
scenario titles, and the bundle and the topic report each resolve "the run for this topic"
on their own. Keeping those four pointing at the same run per topic is the whole job.

## The cycle as it has actually been run

| Quarter | Forecasts | Assessments | Bundle |
| --- | --- | --- | --- |
| Q2 2026 | 24 to 27 May (gpt-4o) | late May | 27 to 28 May |
| Q3 2026 | 3 Aug (gpt-5.4) | 3 to 4 Aug | 4 Aug; topic report 3 Aug |
| Q4 2026 | 21 Sep (gpt-5.4), overlays approved the same evening | 6 Oct, 97 to 366 articles per topic | 8 Oct, approved with warnings |

So the pattern is: new forecasts at the end of a quarter, assess them about two weeks later
once there is evidence, then build and review the bundle. The forecasts made at the end of
Q3 are the "Q4 forecasts". Do not make new forecasts mid-quarter unless you intend to replace
the forecast of record (see the traps section for why).

## Order of operations

### 0. Before you start

- `scripts/restart_when_quiet.sh --check wileytest` if you will need a restart. An ingest is a
  hard wait.
- Decide which run per topic is the forecast of record for the quarter and write the run ids
  down. `SELECT topic, id, created_at, model_used FROM future_horizons_runs ORDER BY topic,
  created_at DESC` shows the history.
- Check the model the UI will ask for exists in the site's `litellm_config.yaml`. Since
  `d8074f8d` a bare Claude name the site lacks (the UI defaults to `claude-sonnet-5-5`)
  runs on the standard tier with a WARNING in the log, instead of going to Anthropic's own
  API and failing with "x-api-key header is required".

### 1. Forecasts (only at the start of a new cycle)

Future Horizons tab per topic, or the Topic Reports panel with "Re-run a fresh Three
Horizons analysis" ticked, which does all selected topics in one job. About two minutes a
topic. Cost on 15 Oct 2026: $1.08 for seven topics on Sonnet 4.5, including the executive
summary cards.

What it writes: one `future_horizons_runs` row per topic plus `analysis_run_articles`. The
new row is now "the latest run" for the tracker tab, the auto-run, the overlay generator
and any topic report built without pins.

### 2. Overlays (once per new forecast run)

Forecast Tracker tab → "Generate overlay proposal" → review the mapping → approve. The
generator (`wiley_overlay_agent`) reads the run's raw scenarios and the most recent live
assessment of that run, writes `data/wiley_horizons/<slug>_deck_overlay.json.proposed`, and
approve promotes it to the production name and backs up the old file as
`*.approved-backup-<stamp>`. Overlays match a topic by the `topic` field inside the JSON,
not the filename.

An overlay only maps the scenario titles it was written for. The log line `Deck overlay for
'<topic>' maps 0 of this run's N scenario titles (stale overlay)` means the run and the
overlay disagree; the assessment then falls back to the raw scenarios and the deck shows 13
scenarios instead of 5.

### 3. Assessments

Forecast Tracker tab → "Re-run assessment". Window defaults to 8 weeks. It runs live
(articles after the forecast date) and placebo (the same window before it), scores each
article against each deck scenario on Jev, and names the leftover clusters on the standard
model. Cost on 15 Oct 2026: $0.70 for six paired runs. The spec's "$3 to 8 per run" predates
Jev.

The auto-run (`app/tasks/forecast_tracker_monitor.py`, on where `FORECAST_TRACKER_AUTO_RUN`
is set, which includes wileytest) fires 30 seconds after every service start and then every
6 hours. It assesses the newest run of every topic that has an overlay when that run has
never had a completed live assessment, or its last one is older than 30 days. A forecast made
today therefore gets assessed within the hour, against a live window that has no articles
yet.

`get_latest_forecast_assessment_by_topic` is what the bundle, the exports, the editor and
event extraction all use. It takes the newest completed live assessment that has scenario
verdict rows, and since `7c668dcb` it resolves a deck display name ("Scientific Publishing")
to its source topic before looking.

### 4. Quarterly bundle

Deliverables panel → cadence `quarterly`, "updates only" on → generate. The supervisor runs
briefing, recommendations, next steps, event extraction, cross-topic themes and the
executive letter, then the reviewer. The result lands in `forecast_bundle_synthesis` and the
review verdict in `forecast_bundle_review` (`approved_with_warnings` or
`revision_requested`).

Gates that stop the whole bundle, not just a stage:

- Executive letter must carry all five bold sections and at least 400 words.
- The letter may not use crisis / severe / aggressive / alarming / catastrophic / collapse /
  compromised in its own voice. Wiley asked for this on 12 Aug 2026. Inside double quotes is
  allowed. The writer gets two retries; since `d8074f8d` the retry names the words and tells
  it to quote any title that contains one.

Two stages run inside the bundle since 16 Oct 2026 and have no button of their own:

- **Event reconciliation** runs after every extraction (`reconcile_events_for_bundle` in
  `wiley_event_extraction.py`): one record per real-world event, with a state (proposed,
  agreed, completed, withdrawn ...). Merged rows stay in the table with `include_in_deck`
  off and `merged_into` set, so the editor's Events tab still shows them. Re-running it only
  touches live rows.
- **Narrative review** (`review_and_repair` in `wiley_narrative_review.py`): preflight on
  every date and figure, a quoting judge, up to two targeted repairs. Run it after any
  regeneration and before the reviewer; its result sits on the payload as `narrative_review`.
  An error there means a sentence the ledger contradicts or does not contain; warnings are
  wording. Locks block repair, so unlock before a regeneration and lock after reading.

Then the Quarterly Brief Editor (`#brief` on the page) to correct and lock fields, re-run
single stages, preview, and approve. Approval unlocks the download. "Send to recipients"
emails each topic's configured recipients (`forecast_topic_delivery`) and stamps
`last_delivered_at`; the scheduler sends on the 1st of January, April, July and October to
any topic not yet delivered that quarter.

Regenerating a single stage from the editor does not clear the bundle's rendered deck.
`regenerate_single_stage` rewrites the stage in `forecast_bundle_synthesis`, and the editor's
own preview renders from that fresh state, but the Deliverables download
(`/api/forecast/deliverables/bundle.pptx`) is served from a PPTX cache keyed only on cadence
and period label, so it keeps handing out the old deck. Only "request revision" clears that
cache. After re-running stages by hand, call `invalidate_render_cache("quarterly", "Q4
2026")` from `app/services/wiley_delivery_service.py` (or re-run the full bundle, which
rebuilds it) before anyone downloads.

### 5. Topic report deck

Topic Reports panel → tick the topics, period label such as `Q4 2026` → generate, with the
re-run box off unless this is step 1. The build resolves the newest run per topic, renders
the PPTX, and writes `topic_report_<label>.state.json` next to it with the run id per topic.
Every other export of that report follows those pins, and a missing pinned run raises rather
than substituting the latest. Release lint and the reference check run afterwards and never
block.

### 6. Checks before anything is sent

1. The pins in the topic report's `state.json` match the run ids behind the bundle's
   assessments (`SELECT topic, run_id FROM forecast_assessments` for the assessment ids the
   bundle used).
2. Every bundle topic has an assessment: the log must not say `event-extraction: no assessment
   for <topic>` or `Wiley delivery: skipping <topic>`.
3. No `maps 0 of this run's N scenario titles` lines for the runs in play.
4. The reviewer verdict, the `narrative_review` result and the lint findings have been read, not just counted.
5. The deck opened, every topic present, scenario count per topic is the overlay's 4 to 5.

## Traps and how to get out of them

### Re-running forecasts mid-quarter (15 Oct 2026)

The topic report was regenerated with the re-run box on, which made seven new forecast runs.
Within the hour the auto-run assessed them (zero evidence, because the live window starts at
the forecast date), the overlays matched none of the new scenario titles, and for Quantum
Advantage the new zero-overlay assessment became the one the bundle would pick. The topic
report was now on today's forecasts while the approved Q4 bundle was on the 21 September
ones.

Undo, in this order, after a table dump of `future_horizons_runs`, `forecast_assessments`,
`forecast_article_verdicts`, `forecast_scenario_verdicts`, `analysis_run_articles`,
`extracted_events`:

```sql
BEGIN;
CREATE TEMP TABLE del_runs AS SELECT id FROM future_horizons_runs WHERE created_at::date = '<date>';
CREATE TEMP TABLE del_asm  AS SELECT id FROM forecast_assessments WHERE run_id IN (SELECT id FROM del_runs);
DELETE FROM forecast_article_verdicts  WHERE assessment_id IN (SELECT id FROM del_asm);
DELETE FROM forecast_scenario_verdicts WHERE assessment_id IN (SELECT id FROM del_asm);
DELETE FROM extracted_events           WHERE assessment_id IN (SELECT id FROM del_asm);
DELETE FROM forecast_assessments       WHERE id IN (SELECT id FROM del_asm);
DELETE FROM analysis_run_articles      WHERE run_id IN (SELECT id FROM del_runs);
DELETE FROM forecast_scenario_status   WHERE run_id IN (SELECT id FROM del_runs);
DELETE FROM forecast_user_scenarios    WHERE run_id IN (SELECT id FROM del_runs);
DELETE FROM future_horizons_runs       WHERE id IN (SELECT id FROM del_runs);
COMMIT;
```

Then clear the topic report's render cache (`invalidate_render_cache(label)` in
`topic_report_service`) and regenerate it with the re-run box off, so the pins return to the
forecast of record. Check the `state.json` run ids afterwards.

### The model the UI asks for is not on the site

Symptom: `rerun horizons failed for <topic>: claude-sonnet-5-5 call failed:
AuthenticationError ... x-api-key header is required`, and the report quietly falls back to
the stored forecasts. Fixed by `d8074f8d`; on a site without that commit, pick a model from
the dropdown that the site's `litellm_config.yaml` has.

### Bundle stops at the executive letter

Symptom: `Exec letter still structurally incomplete after retries: severity language in own
voice: "collapse"`. The writer had restated an EOS scenario title that contained the word.
`d8074f8d` makes the retry say which words to remove and to quote titles. If it still fails,
regenerate only the `exec_summary` stage from the editor.

### "No assessment" for a topic that has one

Symptom: `event-extraction: no assessment for Open Science Transition`, the editor's
per-topic tab empty, a topic missing from the deck. The bundle stores display names, the
assessments are filed under source topics. Fixed in the facade by `7c668dcb`.

### The download is the old deck after a stage was regenerated

Symptom: a stage was re-run from the editor, the preview shows the new text, the download
from the Deliverables panel does not. The render cache was not cleared; see the end of step 4.

### A restart assesses everything

Every service start runs the tracker monitor 30 seconds later. Nothing fires if every newest
run has a completed live assessment under 30 days old, so check that before restarting
wileytest during a cycle, or expect six paired runs in the log.

## Costs seen on 15 Oct 2026

| Step | Cost |
| --- | --- |
| Seven fresh forecasts with executive summary cards (Sonnet 4.5) | $1.08 |
| Six paired assessments (Jev + Sonnet 4.5 cluster naming) | $0.70 |
| One "all topics" bundle attempt that failed at the letter | $1.55 |

Source: `llm_usage_log` on wileytest, which records calls made through LiteLLM only.
