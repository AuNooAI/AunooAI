# Relevance integrity patch, 5 October 2026

The focused first step from the relevance specification review: invalid evidence
cannot decide, and missing evidence is not a reject. No new tables, contracts or
model authority. Live on all eight sites since the evening of 5 October
(bugfixing, wiley, wileytest, panaya, sunstar, oviva, abm, wbm); every
restart came up with no tracebacks.

## What changed

**Parsers reject bad values instead of coercing them.**
`parse_unit_score` in `app/services/hybrid_relevance_service.py` reads "0.2",
".2", "1e-3" and "Score: 0.85" correctly and returns None for anything outside
0 to 1 or non-finite. The old pattern read "1e-3" as 1 and ".2" as 2, then
clamped both to 1.0. `unit_value` does the same for values already parsed, and
rejects booleans. The Jev parser now checks the Noul, the ordinal score (against
its rubric size) and the confidence; an out-of-range reply is ignored, so it can
never clear `TYPESAFE_DECIDE_RELEVANCE_MIN`. `app/relevance.py` raises on a
reply it cannot read instead of returning zeros, and `app/services/relevance_scorer.py`
rejects booleans and out-of-range numbers.

**No engine is no verdict.** When neither the embedding model nor the classifier
answers, the hybrid result used to be score 0.0 with "high" confidence, which
skipped every fallback and rejected the article. It is now "medium" so the Jev
and LLM fallbacks run, and if nothing answers the result carries
`status: "unavailable"` with `relevant: None`. The ingest step then tries the
full LLM judge; if that fails too it raises `RelevanceUnavailableError`, and
`process_single_article` files the row as `relevance_check_failed` without
writing `filtered_relevance` and without recording it in the rejected-candidate
ledger. Before this, a double failure became a 0.0, a rejection and a ledger
entry that stopped the URL being looked at again.

**One brand detector.** `brand_name_from_topic` recognises both "Brand Monitoring X"
and "X - Brand Watch". The classifier override, the cross-encoder gate, the LLM
prompt and the Jev question all use it. The LLM prompt used to give the second
form theme instructions.

**Research scoring keeps failures visible.** A failed or timed-out batch, or a
reply without a usable number, marks the article `relevance_status: "unavailable"`
with no score. Unscored articles stay in the result (sorted last) and are counted
in a warning. They used to get 0.5 and be removed by the 0.6 filter.

**Callers keep their target and settings.** The ingest scorer gets the topic's
own threshold (the same one the gates compare against). The bulk endpoint
passes `relevance_threshold_override` through and refuses
`quality_control_enabled=false` and `llm_model_override` with a 400 instead of
ignoring them. The manual rescore endpoint writes the verdict to the requested
topic's match row as well as the article row, skips articles the judge could
not answer, and lists them in the response.

**Jobs report what happened.** The keyword monitor's save batch counts failed
inserts; when any fail, every provider result for that keyword is downgraded to
partial so the checkpoint keeps the interval instead of advancing past rows that
never reached the database (only matters where the collector checkpoints exist:
canonical and abm). The brand scheduler reads the classification run's status
and raises on anything but completed, so a failed run is recorded as failed.

**The regression harness cannot pass on nothing.** Precision and recall with no
support are None, a run with no judged samples is inconclusive, and the script
exits 2. `cron.sh` labels that alert as inconclusive.

## Tests

`tests/test_relevance_integrity.py`: 64 cases, no models, no database. Run with
`.venv/bin/python -m pytest -q tests/test_relevance_integrity.py`. The golden
harness run after the change gives the same figures as before (79 / 71 / 83).
The eight failures in `tests/test_relevance_complete.py`,
`test_relevance_implementation.py` and `test_relevance_scores_persistence.py`
are pre-existing SQLite-era tests that send PRAGMA to PostgreSQL.

## Live impact measured before the patch

Jev accept runs on bugfixing and panaya only (about 520 and 187 accepts a week).
1,812 stored Jev readings since 4 October, none out of range. No engine load
failures in 7 days. One swallowed insert error. No failed brand runs in 30 days.
The patch closes paths that had not fired yet, with the research 0.5 default the
one exception that affects a live feature (Auspex deep research).

## Rolling out

Patches for each file are in `/var/tmp/integrity_patches/` as unified diffs
built from the pre-change canonical files, plus two appliers for files whose
site copies are older than canonical:

- `apply_hybrid.py <file>`: wiley, wileytest, sunstar, oviva and wbm carry
  older `hybrid_relevance_service.py` (no Jev tier; sunstar, oviva and wbm also
  lack the market-topic regex). The applier makes the same edits on that layout.
  panaya and abm match canonical, so the plain patch applies there.
- `apply_tasks_km.py <file>`: the checkpoint fix, for abm only. The other sites
  do not run the checkpointing collector code yet.
- `run.py.patch`: only where the regression cron runs (wiley, wileytest, wbm,
  oviva). The older `cron.sh` on those sites still alerts on exit 2, with the
  generic subject.

Applied on every site on 5 October (backups `*.bak-integrity-20261005` beside
each file), import-checked with each tree's interpreter, restarted with
`scripts/restart_when_quiet.sh`.

## Not done, on purpose

The ledger, run policies, target snapshots, job leases, the 2,000-pair human
benchmark and the fetch hardening from the specification. A trained-topic
manifest for the classifier override does not exist: the model takes the topic
as input text and `model_config.json` lists no topics, so the override is gated
on the brand and market detectors only.

## Round 2, same evening: regression fixtures and decision reuse

The spec author's revised plan withdrew the rebuild and asked for three
things: regression tests built from the real failing payloads, decision reuse
keyed on the model route, and a check that the hardening above is in place.

**Annotation gating.** The plan's first change, making an annotation screen
optional for model selection, does not apply here. The monolith's model
controls are the inference-mode endpoint and the group thresholds; neither
reads labels. Nothing to remove.

**Regression tests from real rows.**
`tests/test_deal_listing.py` carries twelve Sunstar deal pages and ten
approved brand news items. It failed first on "FREE Oral-B Toothbrush at
Walmart!" from moneysavingmom.com, which the rule had let through; the host is
now listed and a "free <product> at <retailer>" title form added.
`tests/test_phantom_guard.py` uses the periodontal-disease term and a page from
the 5 October sweep that the provider matched without carrying the term.
`tests/test_reddit_metadata.py` failed first because posts had no permalink or
timestamp in `social_meta`; the collector now records `permalink` and
`created_at`, and on the JSON route the score, comment count and upvote ratio
when Reddit returns them. A missing field stays missing.

**Decision reuse keyed on the route.** `gate_version` in
`app/services/rejected_candidates.py` takes the model route as part of the
hash, and the ingest passes inference mode plus `relevance_route_signature()`
from the hybrid service (embedding model, classifier weight, fallback model,
cross-encoder and Jev tiers). A changed setting re-evaluates saved rejections;
restoring the setting reuses them again. A failed evaluation never records a
rejection, so the next poll retries (test added). The ledger itself exists only
on bugfixing and abm.

**Rollout.** Applied to all eight sites on the evening of 5 October
(backups `*.bak-round2-20261005`), sunstar first, then the rest once its
restart came up clean. wiley, wileytest, abm and wbm also gained the
deal-listing hook in the ingest step, which they did not have before.
