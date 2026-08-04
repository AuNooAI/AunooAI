# Changes

Running log of notable operational/code changes. Newest first.

## 2026-08-04 (topic report parity) — same gauntlet, one label fix, no regeneration

### Verified rather than re-rolled
"Apply the same fixes to the topic-report letter": the code fixes are already shared (one
supervisor pipeline), so the question was whether the EXISTING letter — generated before the
structure validator, quote-narration ban and golden gate — carries any of the defect
classes. Measured: 570 words, all five sections, no quote-narration, no meta-prose, and a
direct golden-gate judgment of **8/10 PASS** ("strong opening that names actors and actions
immediately; named-event density matches the exemplar's standard"). A clean artifact was
not regenerated — re-rolling a measured-clean letter is variance for zero gain.

### The one real gap: topic-report labels never resolved a prior
`_prior_period_label` couldn't parse "Q3_2026__<topic-hash>", so `prior_letter` lookup
always failed for topic reports and the serial remit degraded to self-contained (correct
for a first letter, wrong forever). New branch resolves the SAME topic set one quarter back
("Q3_2026__2cec74a7" → "Q2_2026__2cec74a7"), so from Q4 onward the topic-report letter is
written as an installment on its own thread, separate from the quarterly bundle's thread.
Verified on four label forms incl. year rollover; 12/12 tests; propagated.

## 2026-08-04 (morning close) — quote-narration banned; writer bake-off validates the status quo

### Quote-narration: the mandated quote manufactured its own tell
The delivered letter contained 'That line matters commercially because…' — the agent md
REQUIRES a verbatim briefing quote in paragraph 4, and the model narrated its own
compliance. Fix: the quote rule now shows the woven-in form and bans quote-narration
outright; `report_lint` `_META_PROSE_RE` catches the phrase class deterministically
("that/this line|quote|sentence|phrase|number matters|is important|captures") — verified on
the exact offending sentence. Regenerated: gate 8/10, 511 words, all sections,
quote-narration clean; package resent. The quarterly HTML was then rendered from the same
synthesis, verified sentence-for-sentence against the letter (25/25 present), and sent —
completing the matched deck+letter+HTML set.

### Writer bake-off against the golden gate
Five writers, one identical real Q3 payload (39,910 chars incl. the Q2 prior letter), first
drafts only, judged by the gate + structure validation + lint: **gpt-5.5 @none (current) 8
PASS · gpt-5.5 @low 8 PASS · gpt-5.4 4 fail · gpt-4.1 3 fail · claude-sonnet-4.5 wrote the
banned "80% of sources" construct** (its gate judgment glitched, score null — disqualified
by lint regardless). Two parse failures on the first pass were harness artifacts, re-run
with raw capture. Conclusions: keep gpt-5.5 @none (extra reasoning buys nothing); the
"gpt-4.1 wrote the good Q2 letter" theory is dead — on today's prompt it produced the worst
prose of the field, so the quality gain came from the remit + retry machinery, not the
model; the repoint away from Bedrock Claude is validated by its first draft reproducing the
original invented-consensus defect. Caveat recorded: n=1 per writer against observed 4↔8
first-draft variance; the ordering (8/8 vs 4/3) is wide enough to act on, and the harness
re-tests any candidate in minutes. Letters at `/tmp/bakeoff_*.txt`.

## 2026-08-04 (follow-up) — the installment letters were fragments; structure is now machine-validated

### Incident
The delivered serial letter was 102 words — the bottom line section only, four sections
missing. Every letter since the installment framing landed was a fragment: the writer
(openai-gpt-5.5, reasoning_effort none — no planning budget) latched onto "advance the
narrative, don't re-introduce the world" and dropped the inventory sections. Nothing
checked completeness: the golden gate scored a fragment 8/10 on prose form, and the send
audit checked defects-present, not sections-missing. Same failure shape as yesterday's
consensus bans, one level up: an instruction about what NOT to do, without re-affirming the
mandatory structure, and no deterministic backstop.

### Fix: validated, not requested
**`wiley_bundle_supervisor.py`**: `_letter_defects()` (five mandatory sections + 400-word
floor) validates the letter at generation; up to two retries with the defect list spelled
out in the payload (`structure_defects`); a still-incomplete letter raises — a fragment can
never ship again. Golden gate criterion 6a fails incomplete letters regardless of prose.
**`wiley_exec_summary_agent.md`**: "the installment framing changes what the five sections
SAY, never which sections exist" + the structure_defects contract. Live proof in one run:
fragment (112 words) → retry → fragment (121) → retry → **complete 549-word letter scoring
9/10 on the gate, the session's highest.**

### Reviewer false positive, third variant — overruled
The reviewer blocked the complete letter with one error: the AZ/BMS merger lede "does not
appear in the Patent Cliffs named_events" — the event ledger shows the event filed under
Patent Cliffs (verified by query), deck-included, exact wording. Third different rationale
against the same fully-grounded claim across three runs. Dispositioned per the checklist:
verified false positive, review status set to approved_with_warnings by analyst action,
findings retained. Final package (bundle deck + 576-word DOCX letter) emailed after an
audit that now asserts completeness (sections + word floor) alongside the defect checks.

### Lessons
- Structural requirements get VALIDATED in code, never merely requested in prose — a
  low-reasoning writer will satisfy the loudest instruction and drop the rest.
- Completeness is a first-class audit dimension: every future artifact audit asserts
  sections + length floor, not just absence of known defects.
- When a reviewer produces a third distinct rationale against the same verified claim,
  stop regenerating and overrule with the evidence documented.

## 2026-08-04 — the letter is an installment: serial remit, prior-letter payload, gate criterion

### Goal
The user compared the delivered Q3 quarterly letter to Q2's: Q3 read as an independent
quarter review; Q2 reads as an update ("remains", "was expected to advance, yet…"). Two
questions answered with evidence: what's unclear about the remit, and why Q2 worked.

### Diagnosis
Nothing in the agent remit said "installment", and `_exec_summary_payload` carried
`prior_period_label` + numeric deltas but NOT the prior letter — the model literally could
not write "the tail risk remains X" because it never saw last quarter's headline risk. And
the numeric deltas it did receive are exactly what the banned-phrasings list forbids. Q2
worked because it was written in May under the pre-ban instructions, which were built AROUND
baseline-diff framing; the 08-03 bans removed that vocabulary without specifying the
compliant replacement. We banned the bad way of being serial and never specified the good way.

### Fixes
**`wiley_bundle_supervisor.py`**: payload gains `prior_letter` (the prior period's letter
from `forecast_bundle_synthesis`, 8k cap, cadence-aware; degrades to empty for first
letters / topic-report labels). Golden gate gains criterion 6 — serial continuity, judged
against the Q2 exemplar's own register. **`wiley_exec_summary_agent.md`**: new "This letter
is an installment" section — track prior claims, state tail-risk continuity, frame new
developments as new against the standing picture; prior letter is narrative context only
(its facts are last quarter's); consensus-number bans unchanged.

### Live results and two briefing corrections
First serial run: draft scored 8, passed with NO retry (all prior first drafts scored 4 —
the missing remit was the binding constraint, not the model). Opener: "The Q2 concern about
declining trust has broadened from public confidence into the funding machinery." The
reviewer then blocked on two briefing ledes: "$400 billion deal" (a reviewer false positive
that persisted even after a qualifier rule was added to the rubric — resolved by aligning
the lede to the event record's own noun, "potential $400 billion pharmaceutical merger")
and "~300 grants in blue states" (half-real: 300 is event-supported, "blue states" was an
inference — corrected to the event's "political-consideration criteria"). Both edits in the
assessment rows (wileytest DB, this entry is the record). Writer variance observed across
rolls (8 / 4→4 / 8) — the gate absorbs it. Final run: **gate 8/10 passed, reviewer approved
with zero errors**; final package emailed with an eight-point audit asserted in the send
script (including "blue states" absence and serial-marker presence).

### Lessons
- When banning a bad framing, specify the compliant replacement in the same edit — a model
  stripped of its update vocabulary writes standalone reviews.
- A serial document's writer must SEE the prior document. Labels and deltas are not narrative.
- When a reviewer false-positive survives a rubric fix, align the artefact to the source
  record's exact wording instead of arguing with the judge — it's tighter grounding anyway.

## 2026-08-03 (quarterly live-fire) — the gate blocks a stale bundle; a silent-empty assessment incident underneath

### Goal
Live-test the golden gate on the real quarterly bundle, then produce a shippable Q3
quarterly bundle (assessments first, bundle second). The test worked better than intended:
it blocked the bundle for reasons that turned out to be real, and chasing them surfaced a
silent data-integrity bug in the assessment pipeline.

### The gate test: 4/10, retry 4/10, reviewer blocks — all correct
`generate_bundle("quarterly")` on wileytest (bundle rendered, 1,276,386 bytes, 6 topics).
Golden gate: draft 4/10, critique retry also 4/10, `{"score": 4, "passes": false}`
persisted. Unlike the topic-report letter (4→8), no rewrite could fix this one — the
letter's inputs were May 21–27 assessments on Jan–May runs, and event density can't be
written into prose the payload doesn't contain. The LLM reviewer independently returned
`revision_requested` with one genuine error: a Quantum Advantage recommendation reading
"Request Wiley admin to supply required context and scenario data" — internal plumbing in a
customer recommendation, produced by vacuum content from an empty topic. One reviewer false
positive for later rubric tuning: it flagged the mandated "**The bottom line.**" section
header as a meta-opener. Net: the two gates correctly refused to ship a stale bundle.

### Incident: assessments that "complete" in 0.2s with zero verdicts
Re-running the six Q3 assessments hit it immediately: "Attacks on Expertise & Peer Review"
assessed in 0.22s, status completed, verdicts empty (assessment `3158cefa`, summary shows
evidence_pool 2000, assigned 0, classified 0 — and the summary is double-encoded JSON, the
known wiley pitfall). Root cause chain: the topic's ACTIVE deck overlay
(`topic2_deck_overlay.json`) maps scenario titles from an older run — zero of the standing
run c30d7344's titles match — so `_build_deck_scenarios` returns an empty list,
`assign_exclusive([])` returns `[]` without ever loading the reranker, and the pipeline
persists a completed-empty assessment that the quarterly bundle would then read as the
topic's status. The corrected overlays existed as `.proposed` files (their title maps match
the standing runs exactly) — staged by the overlay-refresh flow and never activated. Two
topics affected: Attacks and Quantum Advantage.

### Fixes
**Overlay activation (uncommittable — wileytest data dir, this entry is the record):**
`attacks_on_expertise_peer_review_deck_overlay.json.proposed` and
`quantum_advantage_deck_overlay.json.proposed` promoted to active;
`topic2_deck_overlay.json` and the stale `quantum_advantage_deck_overlay.json` retired with
`.retired_20260803` suffixes. The in-flight assessment script loads overlays per topic, so
Quantum Advantage (queued behind the fix) assesses against the corrected overlay.
**Guard (`app/services/forecast_assessment_service.py`, this commit):** when the deck
overlay collapse yields zero scenarios, `assess_run` now logs an ERROR naming the
stale-overlay cause and falls back to db-level scenarios instead of silently persisting an
empty "completed" row. Propagated to wiley + wileytest after clean drift checks.

### Verification
Overlay title-map vs run-title comparison done per topic (0/13 match on the stale Attacks
overlay; 10/10 on the proposed). Syntax + 12/12 contract/hygiene tests green with the guard
in. The six Q3 assessments are IN FLIGHT at the time of this entry (topic 2 of 6 running);
the Attacks re-run (superseding the empty row) and the bundle regeneration follow — their
outcomes are NOT yet claimed here.

### Second failure under the first: verdicts computed, then lost to varchar(4)
The Attacks re-assessment with the fixed overlay did real work (398s, 32 articles
classified, five deck-level verdicts) and then lost ALL verdict rows to
``psycopg2.StringDataRightTruncation``: ``forecast_scenario_verdicts.horizon_type`` is
varchar(4), sized for "h1"/"h2"/"h3" — but the newer overlay generator emits likelihood
classes ("probable"/"plausible"/"possible") as deck-scenario horizons. Migration
``fsv_horizon_16`` widens ``horizon_type`` to varchar(16) on ``forecast_scenario_verdicts``
and ``forecast_user_scenarios`` (ORM synced in `database_models.py`). Applied on all three
tenants; wileytest's copy carries ``down_revision='kg_social_01'`` because its tree never
took ``emb_768_01`` (the known per-tenant alembic divergence — adapted copy, per practice).

### The fresh bundle: gate 4→8 passed, reviewer approves
Full sequence completed: six real Q3 assessments (530s/490s/432s/427s/484s/398s; Quantum
Advantage produced genuine verdicts through its activated overlay; Attacks superseded its
empty row on the second re-run after the column fix). Bundle regenerated on them:
**golden gate draft 4/10 → critique retry 8/10, passed; reviewer approved_with_warnings,
zero errors** (the "Request Wiley admin" vacuum error is gone). Letter opens with actor and
action. The controlled comparison against the stale run (same writer, same gate, retry
4→4 then vs 4→8 now) confirms the gate measures input freshness as much as prose:
1,366,055-byte bundle at `/tmp/q3_quarterly_bundle.pptx`.

### Delivered (2026-08-04 00:0x)
Quarterly package emailed: the 1,366,055-byte bundle deck plus the executive letter DOCX
rendered from the fresh synthesis via `generate_bundle_docx("quarterly")`. The send script
asserts a seven-point audit before emailing (internal keys, meta-openers, legacy defects,
tail-risk denial, consensus vocabulary, verdict vocabulary, the "Request Wiley admin"
string) — all clean. Home copies at
`/home/orochford/Wiley_Horizons_Quarterly_{Bundle,Letter}_Q3_2026.*`. Both Q3 products are
now delivered gate-passed: the topic report (fresh forecasts, six pinned runs) and the
quarterly bundle (standing forecasts tracked against Q3 events, six fresh assessments).

### Lessons
- A varchar sized for one vocabulary is a silent kill-switch for the next vocabulary; the
  write path must surface INSERT failures to the caller, not just the log (assess_run
  returned "success" while its verdict rows bounced).
- A "completed" status with zero verdicts in sub-second runtime is a data bug, not a fast
  run. Pipelines must refuse to persist success when a collapse stage returns empty.
- `.proposed` files are staged fixes awaiting activation — when debugging stale-config
  behaviour, check for them FIRST.

## 2026-08-03 (last) — golden-set gate: every letter judged against the Q2 exemplar

### Goal
The user compared Q3's letter to Q2's and asked why this quarter's was worse ("The most
decision-relevant read is…" — meta-commentary where Q2 opens with an actor and an action).
Three causes: the writer changed (gpt-4.1 → gpt-5.5) with no before/after — the exact
process the standing repoint rule exists to prevent, violated under incident pressure; the
framing scaffold supplied in yesterday's instruction got copied into the lede
(instruction-copying, in style form); and five sequential guard passes sand prose toward
abstraction, which a weaker lede-writer answers with meta-language instead of named events.

### Lede rules + meta-prose check
**`wiley_exec_summary_agent.md`**: the letter must OPEN with the quarter's sharpest named
development (actor, action, consequence); banned openers listed ("The most decision-relevant
read", "The key takeaway", "At a high level"…); illustrative phrasing in instructions
declared never-quotable. **`report_lint.py`** gains a `meta_prose` check (verified catching
the exact offending sentence); the reviewer rubric adds meta-opener = error.

### The golden-set gate
The Q2 letter (the customer-approved standard) is stored at
`data/auspex/golden/wiley_exec_summary_q2_2026.txt` — deliberately OUTSIDE the prompt dirs
the hygiene test scans, because it contains real facts. New `_golden_gate()` in
**`wiley_bundle_supervisor.py`**: after the letter's grounding passes, a gpt-5.4 judge
scores the candidate 0-10 against the exemplar on prose quality only (opening shape,
named-event density, forecast-vs-evidence contrast, concrete consequences, no abstraction),
pass = score ≥ 7 + compliant opening. On failure: ONE retry — the judge's critique
(qualities to fix, candidate quotes only, NEVER exemplar facts, so last quarter's events
cannot bleed into this quarter's letter) goes back to the exec agent as
`golden_gate_critique`, the rewrite is re-scrubbed (verdict/figures/entities) and re-judged,
best score ships. Verdict persisted in the synthesis payload. Fails open.

First live run proved the loop: **draft scored 4/10 → rejected → critique rewrite scored
8/10 → passed.** Final opener: "The Trump administration canceled federal research grants
using keyword filters, fired the National Science Board, and shut down ocean monitoring
systems; at forecast time…" — the Q2 shape. One import bug on the way (`os` missing in the
supervisor, caught by the contract tests + a crashed pipeline run, fixed).

### Delivery
Complete package emailed: golden-gated letter + deck + HTML re-rendered from the same six
pinned runs (run-ID match asserted in the send script itself — it refuses to email a
mismatched set). Home copies updated. All artifact audits clean; 12/12 tests green.

### Lessons
- NEVER change a shipping pipeline's writer model without judging output against the
  customer-approved exemplar — now enforced by machinery, not memory.
- Style scaffolds in instructions get copied like example facts do; supply shapes, mark
  them never-quotable, and lint for the tell-phrases anyway.

## 2026-08-03 (later) — the release gate covers Brand Watcher reports

### Goal
Close the gap the release-gate product doc named: Brand Watcher's customer-facing outputs
had none of the topic-report pipeline's checks.

### `lint_outbound` — the gate for any outbound customer text
**`app/services/report_lint.py`** gains `lint_outbound(text, kind, sources, context)`:
the artifact string checks (internal-name leaks, invented consensus, past deadlines,
fallback titles) plus figure/organisation grounding against the evidence text when
``sources`` is given. Advisory — logs findings with context and returns them, never raises,
never blocks. Verified: clean incident-style prose over its evidence → 0 findings; seeded
text trips config_leak, invented_consensus, past_deadline, unsourced_figure ($9B vs a
sourced $2B), unsourced_org.

### Four Brand Watcher surfaces wired
**`bw_digest_service.py`** (digest email, before send), **`brand_alert_service.py`**
(alert emails), and in **`brand_watcher_routes.py`** the incident "Situation" paragraph —
the one with real evidence to ground against: figures and org names checked against the
incident's evidence lines + agent brief + analyst description, findings returned in the
response as ``lint`` so the report UI can surface them — and the account-report email
(leak checks on the outbound HTML).

### Propagation — including the BW-dedicated tenants
bugfixing + wiley + wileytest: full copies. **wbm** and **bwtemplate** (not in the standard
copy rule, but they send these reports): drift-checked first — all three "drifted" files
matched ancestral canonical commits exactly (wbm/bwtemplate humanizer = `451bed56`
2026-06-18, bwtemplate routes = `c33b233a` 2026-07-13), i.e. staleness, not local edits.
wbm got full copies (its stale humanizer predates the grounding helpers `lint_outbound`
needs). bwtemplate's routes got the account-report hunk surgically (its July-13 version has
no `incident_report_summary` yet) plus the four service files. Smoke test on both BW venvs:
`lint_outbound` imports and flags seeded text (4 findings). All five services restarted and
active. 12/12 tests green.

## 2026-08-03 (close of session) — Q3 delivered clean; the generation workflow as it now stands

### Goal
Close out the report-integrity session: final team-slide copy, the four lint-flagged figures
resolved, and the Q3 deliverables sent for review. This entry also records the resulting
generation workflow in one place, since it changed in every stage today.

### Team slide, final form
Three iterations on feedback: the "WHAT TRANSFERS" consultant label went first, then the
aphorism subtitle; final copy is plain professional register (`925f8f05`, `c71ab823`). The
credential attributions are exact and confirmed by the user: **former Gartner Research
Director, authored Magic Quadrants for SIEM, named the SOAR market**; security research at
Securonix/Tenable, cybersecurity leadership at HP/Verizon. Saved to memory
(`user_oliver_credentials.md`) so future sessions keep them exact. The five-vendor cyber
advisory list stays off the slide.

### Q3 2026 delivered
Final artifacts (deck 237 slides / 2.6 MB, HTML 503 KB) emailed to the user with attachments
via Resend from the wileytest env (message `87b7493c`), copies at
`/home/orochford/Wiley_Horizons_Topic_Report_Q3_2026.{pptx,html}`, and the same builds serve
from the wileytest UI. Both artifacts render from the six pinned runs (identical provenance
IDs, verified), release lint reports zero findings.

### The exec letter — two more two-source bugs, then clean
The user asked "what about the exec?" — and the DOCX was the one artifact still rendering
from the stale 14:45 synthesis, which carried every review defect (14.5%, 4.8%, Hindawi,
"no new tail-risk"). Rebuilding it surfaced two live bugs:

1. **wileytest's letter model was silently Bedrock again.** OpenAI's gpt-5.5 dropped support
   for `reasoning_effort: minimal` (400: supported values none/low/…), so every
   `openai-gpt-5.5` call fell back to bedrock-claude-sonnet — the writer the 07-08 repoint
   exists to avoid. Fixed in wileytest's `wiley_exec_summary_agent.md`: `minimal` → `none`
   (uncommittable drift file; this entry is the record). `minimal_reasoning_effort()` in
   `ai_models.py` already handles this for code paths; the agent frontmatter bypassed it.
2. **The letter's tail-risk payload read a different EOS source than the deck.**
   `ensure_bundle_synthesis` built `eos_per_topic` from the assessment summary (empty on the
   topic-report path) while the deck loads `saved_eos` — so the agent saw count 0 and wrote
   "No new tail-risk scenarios surfaced this quarter" under a deck with 24 cards, the exact
   review defect, reproduced. Both `ensure_bundle_synthesis` and `_load_cached_state` now
   fall back to the deck's source (`_eos_scenarios` / `get_latest_saved_eos_for_topic`).

Rebuilt letter audit: all eleven checks clean, zero Bedrock fallbacks, and the tail-risk
section names the top scenario (Quantum arms-race, 2025-2028, one of 30 tracked) instead of
denying the deck's cards. DOCX emailed (Resend `ed647222`), copy at
`/home/orochford/Wiley_Horizons_Executive_Summary_Q3_2026.docx`. Note: the reviewer stage
skips when the period is already `approved_with_warnings`, so the attached review findings
are the OLD letter's — a re-review needs the review row reset.

### Fresh LLM-as-judge review of the rebuilt letter
The reviewer stage skips periods already approved, so the judge was invoked directly over
the SAVED synthesis (no regeneration): review row reset to under_review, reviewer payload
built from the cached payload + pinned items, gpt-5.4 at reasoning_effort=high, verdict
persisted. Result: **approved_with_warnings — 0 errors, 6 warnings, 10 findings** (30s).
Every warning was checked against the customer DOCX and none reaches it: the letter's only
percentage is "12% growth in OA publishing", a sourced event magnitude the rules allow (the
reviewer over-flags it), and the "no scenario-based data" text lives in the stored Quantum
Computing assessment briefing, not the document. That stale briefing (written by the
supervisor when the topic had no forecast assessment) was replaced in the assessment row
with the pinned run's real briefing so it cannot surface in future payloads. The four info
findings are stylistic (cross-cutting themes naming two topics).

### The letter narrated its own plumbing — final rebuild
Reading the sent letter as the customer would surfaced one more instruction-copying case:
"With no events_by_topic records supplied" and "the scenario event file has no confirming
events yet" — internal payload names in customer prose, there because the agent's own
instructions name the field. Fixes: a hard rule in `wiley_exec_summary_agent.md` (never name
an internal field or narrate missing inputs; phrase the events-gap in customer terms, with
the phrasing supplied), and the release lint now flags internal key names (`events_by_topic`,
`raw_output`, `per_topic_detail`, `briefing_lede`, `eos_per_topic`, "scenario event file")
in any artifact. Synthesis and review rows reset, pipeline re-run END TO END including a
fresh reviewer pass (not skipped this time): **approved_with_warnings, 0 errors, 9 warnings,
1 info**. Final letter audit clean on all axes — no internal keys, no orphan figures, no
Hindawi-class names, no consensus %, no verdict vocabulary, zero Bedrock fallbacks, and the
bottom line now reads "The quarter's pressure appears in reporting but has not yet produced
confirmed, named events in the scenarios we track." Final DOCX emailed (Resend `efec16d8`,
replacing `ed647222`), copy at `/home/orochford/Wiley_Horizons_Executive_Summary_Q3_2026.docx`.

### Framing correction: developing scenarios, not missing evidence
The user's read of the letter: "has not yet produced confirmed, named events" sounds like a
gap in our coverage. The agent rule now prescribes the opposite framing — scenarios "still
developing / continuing to evolve", with "missing / absent / unconfirmed events" phrasing
explicitly banned as reading like a coverage gap rather than the state of the world. Final
rebuild opens: "several high-consequence scenarios continue to develop while the pressures
around them intensify." Audit clean on all axes, fresh reviewer pass, zero fallbacks. Final
DOCX emailed — this replaces both earlier versions.

### Final matched delivery
Deck and HTML re-rendered from the pinned runs so all three artifacts form one package with
the final letter: identical six provenance run IDs deck<->HTML (verified), corrected figures,
final team-slide credentials, zero lint findings. Emailed as replacements for the 20:26
versions (which predated the credential and figure corrections); copies at
`/home/orochford/Wiley_Horizons_Topic_Report_Q3_2026.{pptx,html}` next to the letter.

### The review checklist is embedded in the solution
Three layers, one list (`docs/REPORT_REVIEW_CHECKLIST.md`, new): the release lint enforces
the deterministic items, the LLM reviewer's rubric gains rule 9 with the five judgment
checks it has the data for (internal names in prose = error; tail-risk denial while
`eos_per_topic` has cards = error; coverage-gap framing = warning; customer's own entities
listed as third parties = error; unsupported inference = error; past deadlines = warning),
and the doc records the human-only steps (read as the customer, credentials exactness,
disposition every lint finding). Also saved as a session memory for future work. Reviewer
agent verified drift-free on both tenants before copying.

### Docs pass: the hygiene test caught its own author
Running `/session-docs` re-verification surfaced a red test: embedding the checklist into
the reviewer rubric had written "Hindawi" into a prompt file, and
`test_prompt_hygiene.py::test_no_banned_names_in_prompts` failed exactly as designed — on
its author, twenty minutes after being written. Rule 9 reworded to "subsidiaries, retired
imprints … use your knowledge of the customer's corporate history" (the gpt-5.4 reviewer
knows the relationship without being handed the name). 12/12 tests green, propagated to
both tenants. Product writeup for the release-gate wave added:
`docs/product/2026-08-03-report-release-gate.md`.

### The generation workflow now
One topic, generate: corpus (alignment > 0.7) → blocklist + dedup + nova-lite relevance
screen (fails open, 35% floor) → Three Horizons on gpt-5.4 with a date-anchored,
figure-disciplined, example-fact-free prompt → humanize pass → run + numbered corpus
persisted → exec cards (prompt v3, no percentages). Deck renders from stored runs; the
period sidecar records topics + pinned run IDs; release lint runs over the artifact and the
run content, findings stored on the sidecar. HTML/DOCX/synthesis resolve the PINNED runs and
lint again. Analyst reviews lint findings, edits run data if needed, re-renders (seconds,
no LLM). CI: 12 renderer contract tests + prompt-hygiene tests (frozen figure baseline,
banned names). Caches and sidecars are tenant-scoped
(`/tmp/topic_report_render_cache_{DB_NAME}`). Tests run via `.venv/bin/python -m pytest`
(system pytest lacks pptx/docx).

## 2026-08-03 (late night) — hardening: release lint, contract tests, prompt hygiene, tenant-scoped caches

### Goal
Turn the manual Q3 review into machinery. Four measures, each keyed to a defect class the
review found.

### Release lint on every build
New **`app/services/report_lint.py`**, wired into the PPTX and HTML build paths (findings are
logged and stored on the period sidecar; they never block a render). Checks: config leaks
(model ids in config-shaped contexts, PERSONA, CORPUS SCANNED), invented-consensus patterns,
grouped citations, past-dated deadlines (built from the current year), em-dash fallback
titles, workspace-topic leaks, and a per-run content sweep — every figure and organisation the
prose asserts must appear in the cited corpus (reuses the humanizer's figure/org extractors,
findings only). Verified: zero findings on the shipped Q3 deck+HTML; a seeded defect string
trips all five artifact checks. One false positive fixed during testing: "business model:
AI-driven" tripped the model-id regex, which now requires a real model-id prefix.

### Renderer contract tests
**`tests/test_report_renderer_contracts.py`** (12 tests, all passing via `.venv/bin/python -m
pytest`): pushes the REAL generator shapes — `OutlierScenario.to_dict`, the prompt-v3 exec
card, the topic-report scenario schema — through the HTML/DOCX renderers and the exec-letter
payload builder, asserting content survives (no em-dash fallbacks, grouped cites split,
legacy percentage fields ignored, all EOS categories counted with `impact_rating`). These
would have caught three of the eleven review defects. pytest installed into the bugfixing
venv (`.venv/bin/python -m pip install pytest` — system pytest lacks pptx/docx).

### Prompt hygiene test — and it caught two more traps immediately
**`tests/test_prompt_hygiene.py`**: (1) freezes every number-with-unit currently in
`data/prompts/` + `data/auspex/agents/` as a reviewed baseline — any NEW figure fails until
reviewed; (2) bans names that have already been copied from a prompt into a customer artifact
(Hindawi, Novo Nordisk). First run flagged **`wiley_event_extractor_agent.md`** — whose worked
example was the very same fabricated event ("Springer Nature retracted 1,200 papers from
Hindawi journals") in a second file — and **`wiley_retrieval_agent.md`** (Novo Nordisk
example). Both replaced with placeholder shapes; `executive_summary.json` v3.0.1 likewise
swaps its Novo Nordisk/Lilly example for placeholders.

### First live lint run — tuning on real output
The first lint pass over the regenerated Q3 content produced 25 findings; three extractor
fixes brought it to 4 genuine ones. Fixed: the corpus loader now includes article summaries
(title-only grounding flagged legitimately sourced figures); the org extractor strips
possessives ("NIH's"), rejects compound adjectives ("AI-driven", "U.S.-origin"), and skips
nationality/geography words (China, Western, Latin America). The 4 survivors are real
analyst-review items in the fresh Q3 scenario prose: an Eliquis "$14 billion revenue
decline" and a "$1 trillion" science-funding figure in no cited source, a speculative
"10,000 logical qubits" H3 magnitude, and a "£162 million" figure cited to [1] but absent
from that article's stored summary. Stored on the period sidecar under ``lint``.

### The 4 flagged figures — resolved (2 corrected, 2 were lexicon gaps)
Chasing the lint's four unsourced-figure findings against the full sources settled them:
**two were lint false positives from unit abbreviations** — "$14 billion" is backed by a
headline writing "$14bn" (summary: "$14.2 billion over six years") and "£162 million" by a
headline writing "£162m". `_FIGURE_RE`/`_UNIT_SCALE` now understand bn/mn/m/k/tn, so
headline-abbreviated sources ground spelled-out claims. **Two were real** and were edited in
the wileytest DB (runs `b91c5797`, `3f125dd4`, `45a0af87` + their cached exec cards — data
edits, not in git; this entry is the record): Eliquis corrected to the source's exact
"$14.2 billion" (2 places + card); the invented "10,000 logical qubits" scaling removed from
a scenario title, description, key insight and card minority view (the sourced 1,500-qubit
target [30] stays); "a proposed $1 trillion attack on science funding" — unsourced figure,
charged phrasing — rewritten to "sweeping proposed cuts to science funding". Re-render:
**0 lint findings**, corrections verified in deck and HTML.

### Tenant-scoped render caches
`_render_cache_dir` in **`topic_report_service.py`** and **`wiley_delivery_service.py`** was
`$TMPDIR/…` shared by every tenant on the box and keyed only by period_label — two tenants
generating the same topic set for the same period would serve each other's decks and
sidecars. Both now scope by `DB_NAME`. No automatic migration (shared-dir files carry no
tenant marker); wileytest's Q3 sidecar+deck were placed into its scoped dir by hand.

### Team slide (professional register)
Copy rewritten twice on feedback: the "WHAT TRANSFERS" label and the aphorism subtitle are
gone. Plain professional bios — an unlabelled framing sentence (threat-intelligence /
large-scale-classification expertise stated directly), then BACKGROUND and SELECT WORK.
Also fixed in passing: a garbled role attribution and "synthetic-data integrity" where the
paper is about privacy.

### Propagation
Committed in bugfixing; backend + prompt + agent files copied to wiley + wileytest (both
agent files verified drift-free first); Q3 deck re-rendered from the pinned runs with the
final slide copy; services restarted.

## 2026-08-03 (night) — follow-ups: run pinning, honest convergence cards, reframed team slide

### Goal
Close the items left open by the evening's review pass: exports that can silently come from
different analysis runs, the trend-convergence card's fabricated fallback, and the team slide's
domain mismatch.

### Exports pinned to the runs the deck used
**`topic_report_service.py` / `topic_report_pptx.py`**: each export format resolved "latest
run per topic" at its own moment, so a horizons re-run between exports gave the deck and the
HTML different scenarios under the same cover. The PPTX build now records
{source topic → run id} in the period's state sidecar, and `resolve_items(topics, run_ids=…)`
pins the HTML, DOCX and synthesis paths to those exact runs. A pinned id that no longer
resolves falls back to latest with a warning; sidecars written before today have no mapping
and behave as before. Verified against the wiley DB: unpinned resolves the latest run,
pinning to an older run returns that run, a bogus id falls back to latest.

### Convergence card stops inventing "80% Consensus"
**`App.tsx` / `ConvergenceCard.tsx`**: the card rendered `consensus_percentage || 80` — a
fabricated badge whenever the pipeline supplied nothing. The prop is optional now; no value,
no badge, no "% of sources agree" tooltip, no "confidence level" line. Values the pipeline
does supply render unchanged.

### Team slide reframed (option C)
**`topic_report_pptx.py`** `_add_intro_team_slide`: same people, same true credentials, but
each bio now leads with a WHAT TRANSFERS row connecting the background to research integrity
(coordinated manipulation / large-scale classification), and the subtitle carries the frame:
"Integrity abuse is adversarial behaviour at scale — the discipline this team comes from."
The five-vendor cyber advisory list is gone. Copy needs the user's sign-off before the next
customer delivery.

### Post-regeneration fixes (found by auditing the fresh Q3 deck)
Two leaks survived the first pass, both caught by auditing the regenerated deck against the
review list. **`topic_report_pptx.py`**: the Key Supporting Articles slide loaded alignment-
ranked articles with no corpus hygiene, putting a naturalnews.com headline back on a customer
slide — it now takes the 7 freshest items of the SCREENED corpus the analysis used (fallback
to the old loader when no corpus is persisted). And the coverage slide scope is now the UNION
of the delivery config and the deck's topics — the config's stale "Quantum Advantage" name
had dropped Quantum Computing from its own deck's coverage slide.

### Verification
Regenerated Q3 2026 on wileytest (6 topics, ~13 min, label `Q3_2026__2cec74a7`): relevance
screen dropped 41/88, 43/89, 27/87, 8/85, 40/89, 36/72 per topic. Deck audit: 237 slides,
no "1.4 million" / "one in forty" / Hindawi / consensus-% / model / persona / naturalnews /
em-dash titles / grouped cites / past-dated forks; coverage slide "6 topics". HTML audit:
315 numbered references, timeline 2026–2041, same checks clean ("gpt-" hits are article
headlines about OpenAI, "lakh"/ASML are quoted source titles in reference lists). Deck and
HTML provenance tables carry the IDENTICAL six run IDs — the pinning works on the real
pipeline. Synthesia survived the screen into one corpus at [12] but is cited nowhere and no
avatar/identity claim exists in the run.

Team slide rendered standalone (all rows present); run pinning tested three ways (above);
`npm run typecheck` clean (246 known, 0 new); UI rebuilt.

### Propagation
Committed in bugfixing; copied to wiley + wileytest (surgical merge preserved wileytest's
`openai-gpt-5.5` agent repoint); UI bundle + templates synced; all three services restarted
and healthy. Q3 regeneration on wileytest is the remaining step.

## 2026-08-03 (evening) — the Q3 Wiley report review: eleven defects, one root pattern

### Goal
A line-by-line review of the Q3 deliverables (247-slide deck, HTML report, DOCX letter) found
errors that would have gone to the customer: a figure inflated tenfold, a consensus percentage
that is not a measurement, the customer's own retired imprint named as a third party, and a
set of rendering bugs. All fixed in commit `4ae2b324` (18 files, +985/−185). One pattern
explains the worst of it: **worked examples inside our own prompts carried real-looking facts,
and the model copied them into reports as findings.**

### The 1.4 million figure came from our prompt, not the sources
The reviewer traced "1.4 million phantom citations" to Times of India headlines saying "1.4L"
(1.4 lakh = 140,000) and assumed a unit misreading. The real origin is worse:
**`topic_report_service.py`** carried a style example reading *"1.4 million papers, about one
in forty published since 2020"* — the model writes about scientific publishing, so it lifted
the number AND the rate as content, and citations were attached to them afterwards. The same
trap existed twice in **`wiley_exec_summary_agent.md`**: an example event *"Springer Nature
retracted 1,200 Hindawi-linked papers in March"* and a voice line telling the model to "name
actors: Springer Nature, NIH, Max Planck, Hindawi, PubPeer". That is where the letter's
Hindawi came from. All three replaced with placeholder shapes and an explicit rule: these
instructions contain no citable facts. New prompt rules cover units ("1.4L" and "1.5 lakh"
mean 140,000/150,000, "crore" is 10 million), forbid converting a count into a rate, and
require naming both sources when they disagree on a figure.

**`wiley_humanizer.py`** backs this deterministically: `_FIGURE_RE` now matches lakh / `NL` /
crore and comma-grouped numbers, and `_figure_key` resolves scale units to absolute counts —
so a source saying "1.4L" supports a claim of "140,000" but not "1.4 million". Verified with
the review's exact strings. A new `ground_check_entities` pass extracts capitalised names from
the letter and deletes any organisation no source mentions; verified it flags Hindawi and
passes Springer Nature / Lancet / Elsevier. First extractor version glued "Hindawi and Taylor"
into one name and matched it against "Taylor" — names now split on "and", only "&"/"of" join.

### The consensus percentage was an instructed invention — removed everywhere
The exec-summary card prompt said *"Consensus percentage: Estimate based on how many scenarios
support this view (typically 70-90%)"* — and every cached card on wiley clusters exactly ONE
scenario, so there was never a prevalence to count. That is why the HTML said 82% and the deck
78% for the same topic. Fix in three layers: prompt v3 (**`executive_summary.json`**) asks for
no percentage at all; all six renderers (topic report HTML/DOCX/PPTX, shared HTML cards, React
card, React export — which had a hardcoded `|| 85` fallback) stop displaying the field; and a
new `scrub_invented_consensus()` in **`html_report_common.py`** rewrites cached-card prose
("with 80% of sources expecting" → "with most sources expecting"). Claims shaped like article
facts ("67% of hospitals") are deliberately left to the citation rules. The measured number —
`current_consensus_pct`, supports/total among confident verdicts — is untouched on the
assessment path.

### "No new tail-risk scenarios" while the deck showed 24 cards
**`wiley_bundle_supervisor.py`** `_exec_summary_payload` filtered EOS cards to
`category == "black_swan"` and read `impact_score`/`timeframe` — but the generator's default
category is `wild_card` and it writes `impact_rating`/`time_horizon`, so the letter's tail-risk
list was empty or impact-less while the deck rendered every card. Now all three categories
count, impact-sorted; the agent doc allows the "no new tail-risk scenarios" sentence only when
`black_swan_count` is 0. Verified: a 3-card mixed-category input that previously yielded
count 1 with `impact: None` now yields count 3 with the 9/10 card on top.

### Report corpus hygiene: dedup, blocklist, and a fails-open relevance screen
The topic corpus is selected by `topic_alignment_score > 0.7`, and the score saturates: 43
articles sit at exactly 1.00 on "Attacks on Expertise & Peer Review", including plain AI
business news, so no threshold can help. New **`app/services/report_corpus.py`** runs at
prompt-build time (so the numbered list the model sees, the persisted corpus, and every
export's references are the same list): a publisher blocklist (naturalnews.com and kin;
override via `REPORT_SOURCE_BLOCKLIST`), title-key dedup (kills the white paper that appeared
as [37][38][39][40][46]), and a batched nova-lite yes/no screen (`REPORT_CORPUS_SCREEN`,
default on). The screen fails open on any error, keeps unscored articles, and ignores itself
below a 35%-kept floor. Measured on the reviewed topic: 90 → 87 (blocklist+dedup) → 72
(screen), dropping Synthesia, Taktile, and Standard Chartered; one wrong drop (a Springer
Nature retraction story) — the error direction we want. A first, title-only prompt draft
rejected 63 of 87 including on-topic material; feeding summaries and instructing broad topic
reading fixed it.

### Rendering fixes (topic report)
**`topic_report_html.py` / `topic_report_docx.py`**: black-swan cards read `name` /
`trajectory` / `timeframe`; the generator writes `title` / `description` / `time_horizon` —
every card title rendered as an em dash. Fixed (0 in re-render). The HTML "Article References"
block rendered the 7 most recent articles instead of the cited corpus while inline citations
ran to [90]; it now renders the full numbered corpus (180 entries on the test topic).
`split_citation_groups()` in **`html_report_common.py`** turns "[44, 52]" into "[44][52]"
before linkification in all four renderers — 0 unlinked groups in re-render. The Three
Horizons axis was pinned to 2025–2040 in **`horizons_html.py`** and
**`wiley_three_horizons_viz.py`**; both now anchor on the render year (re-render shows
2026 "Present" → 2041). Both horizons prompts now carry today's date so decision forks cannot
predate the report.

### Run provenance on every artifact
The HTML renders from cached synthesis while the deck re-runs the pipeline, so two exports
hours apart can carry different analyses with nothing visible. Every topic-report HTML now
ends with an "Analysis Provenance" table and the deck with a matching slide: per-topic run ID
+ generated-at, with the instruction that artifacts whose IDs differ must not be read side by
side. The structural fix (one frozen snapshot per report build) is NOT built — divergence is
now visible, not impossible.

### Client-facing metadata cleaned
The "About this analysis" slide exposed `gpt-5.4` and the persona setting, and showed
"corpus scanned 90 / articles analysed 90" (both fields are set from the same variable, so the
pair always matches). Now: articles, distinct sources, actual coverage window, lookback,
framework, generated-at. The Future Horizons HTML cover also printed `model: gpt-5.4` —
removed. The "What We Monitor" slide queried ALL workspace topics, leaking ASML Watch and
Elsevier/SAGE/Pearson brand monitoring to the customer; it now scopes to
`forecast_topic_delivery` (on wileytest: the six quarterly Wiley topics), falling back to the
deck's own topics. Emerging-theme sample dates printed raw DB timestamps with microseconds and
mixed +01/+02 offsets; truncated to the day.

### Verification
Full three-format render against the wiley DB (2 topics): zero invented-consensus strings in
HTML/PPTX/DOCX, 0 em-dash titles, 0 unlinked citation groups, axis 2026–2041, provenance
present in HTML + deck, and a deck-text audit finds no "gpt-", "PERSONA", "CORPUS SCANNED",
"ASML", or peer-publisher brand strings. `npm run typecheck` clean (246 known, 0 new).

### Propagation
Committed in bugfixing (canonical) only, commit `4ae2b324`. NOT yet copied to wiley /
wileytest; UI not rebuilt (`./ui/deploy-react-ui.sh` + rsync still needed); no services
restarted. The cached Q3 artifacts remain wrong until the report is regenerated after deploy.
Open items: the per-build snapshot for format consistency, the team-slide credentials
question (business call), and the trend-convergence card's own `|| 80` fallback in
`App.tsx:2617` (different feature, same disease, untouched).

### Lessons
- NEVER put a real-looking fact — number, org name, event — in a prompt's worked example. The
  model will publish it. Use placeholder shapes ("<publisher> retracted <N> papers").
- NEVER render a model-estimated number in a UI element that reads as a measurement
  ("82% CONSENSUS"). If it isn't computed from data, it doesn't get a percent sign.
- When a letter contradicts its own deck, check the payload keys before the model: two of the
  three "hallucinations" here were key mismatches feeding the agent empty data.

## 2026-08-03 (later still) — a number changed meaning mid-pipeline; two wrong diagnoses on the way

### CORRECTION — the letter fabricates nothing, and the model is not the cause
Both first diagnoses were wrong, and the evidence that settled it is simple: **every figure in
that letter is present verbatim in the agent's own input payload.**

```
"14.5% drop in manuscript submissions"   ← verbatim in strategic_overview
"1.4 million … roughly one in forty"     ← verbatim in a briefing_lede
"$300 billion"                           ← verbatim in a briefing_lede
"4.8% faster than APC growth"            ← verbatim in strategic_overview
"99.9975% demonstrated [18]"             ← briefing_lede, with a citation
```

The exec-summary agent copies what it is given. Re-running the same stage on **GPT-5.5**
(direct OpenAI) produced the same figures plus more, all likewise from the payload — so the
2026-07-08 alias repoint to Bedrock Claude is not the cause either.

The earlier "four fabricated statistics" claim came from checking the letter against assessment
summaries and events only, which is not what the agent was given. Two of those "fabrications"
had citations attached upstream.

**What actually went wrong is subject drift at the cross-topic stage.** An assessment says
federal R&D funding ran "14.5% **below baseline expectations**"; the cross-topic agent's
strategic overview restated that as "a 14.5% drop in **manuscript submissions**"; the letter,
the cross-cutting themes and the DOCX then repeated it faithfully. One number, one wrong noun,
propagated to every downstream artefact.

### The guard, corrected
`ground_check_figures` was deployed briefly with the wrong source set — it would have deleted
sourced, cited figures. Fixed the same session:

- The exec-summary check now takes **the agent's own payload** as its first source, so it only
  removes a figure with no upstream origin at all. Verified: 0 unsourced against the real
  payload, and an injected "61.7%" is detected and removed.
- It **skips the model call entirely when nothing is orphaned** (`check_subjects=False`, the
  default). For a stage that copies its numbers, the "source sentence" is the output's own
  sentence, so the subject comparison is circular and can only churn good prose.
- `check_subjects=True` is set for the **cross-topic stage**, where prose is derived from
  different source text and drift is genuinely detectable. Measured on the real overview:

```
BEFORE:  triggering a 14.5% drop in manuscript submissions
AFTER:   triggering a 14.5% drop in federal R&D funding
```

Fixing it there fixes every downstream artefact; fixing it in the letter would not.

### The GPT-5.5 route — wileytest only, and it does not fix this
`gpt-5.5` on these tenants was an alias to Bedrock Claude Sonnet 4.5, so selecting it would have
changed nothing. Bedrock has no GPT-5.5 in this account — `foundation-models` in us-east-1,
us-west-2 and us-east-2 returns only `openai.gpt-oss-*`. The OpenAI key in `.env` is live and
does have `gpt-5.5`, so a **new** alias `openai-gpt-5.5` routes straight to OpenAI, with a
fallback to `bedrock-claude-sonnet`. The existing `gpt-5.5` alias is untouched — repointing an
alias in place is the failure this session started with.

`wiley_exec_summary_agent.md` now uses it, with `reasoning_effort: minimal` so the 5000-token
budget goes to the letter rather than reasoning. **Applied on wileytest only**, and it does not
address the drift, so whether wiley follows is a cost decision for the user.


### What the reader spotted
"Federal research funding faced disruption, triggering a 14.5% drop in manuscript submissions —
the single largest quarterly move in the portfolio." Five figures in that letter; four of them
were not in any source, and the fifth was real but pointed at the wrong subject.

| figure in the letter | what the sources actually contain |
|---|---|
| 14.5% drop in manuscript submissions | Federal R&D funding "14.5% **below baseline expectations**" — a consensus-vs-baseline metric, from the **21 May** assessment |
| $300 billion patent cliffs | only the string `300` in "canceled nearly 300 federal research grants" |
| 1.4 million phantom citations | only `1.4` in "below-baseline impact of -1.43%" (GLP-1 pricing) |
| 4.8% faster than APC growth | nothing |
| one in forty papers | nothing |

Plus "the single largest quarterly move in the portfolio", a superlative no source supports.

### The cause: the agent never changed, the model under it did
`data/auspex/agents/wiley_exec_summary_agent.md` still declares `model: gpt-4.1` and has not
been edited since **2026-05-27** (`b313fcc5`). On **2026-07-08**, `67cc5563` ("LLM routing:
Bedrock-primary yaml") repointed that alias:

```yaml
- model_name: gpt-4.1
  litellm_params:
    model: bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0
```

The Q2 document held up as the good one was generated 2026-05-27/28, when `gpt-4.1` still meant
OpenAI GPT-4.1. Same agent, same prompt, different writer.

The new writer is breaking an instruction in its own agent description, which reads: "NEVER
cites consensus percentages, 'Cooling/Stable/Strengthening' verdicts, or 'X% to Y%' deltas —
those measure article framing, not events, and the customer has said they're meaningless." The
14.5% is exactly that: a baseline-deviation percentage. It is not a misquote of a real
submissions figure; it is a category of number the agent is forbidden from citing at all.

The repeated JSON parse failures are most likely the same root cause — `c2596bd3` on the same
day was "Bedrock JSON mode: drop response_format + tolerant LLM JSON parsing", i.e. the
structured-output guarantee went away with the same migration.

**This is the case the standing rule exists for: never repoint a shipping pipeline's model
without a signed-off before/after.** The 07-08 repoint was a routing change, and it silently
swapped the model writing customer-facing prose.

### The guard: figures are grounded now, not just events
`ground_check_exec_summary` only ever checked *events* — actor, action, subject, date. A
statistic is not an event, so numbers passed untouched.

**`app/services/wiley_humanizer.py`** adds `ground_check_figures(text, sources)`:

- `_FIGURE_RE` extracts quantities ("14.5%", "1.4 million", "$300 billion", "one in forty").
  Note the absence of a trailing `\b` — after "%" the next character is a space, and `\b` would
  never match, which is the bug that made a first pass at this report only 3 of 5 figures.
- `_figure_key` normalises **number and unit together**, so "1.43%" cannot satisfy "1.4 million"
  and "300 grants" cannot satisfy "$300 billion". Digit-substring matching is what made two
  fabrications look sourced.
- `_figure_ledger` maps each sourced figure to the sentence it came from, so the model can be
  asked to check *subject*, not just presence.
- Unsupported figures are found deterministically and the model is told to delete those claims;
  sourced figures are checked against their source sentence and corrected; unsupported
  superlatives go too. Same half-length guard as the event check, so a revision can never gut
  the letter.

Wired into `wiley_bundle_supervisor.py` right after the event check, on the freshly-generated
letter only, emitting a `figures_grounded` stage with the unsourced list.

### Verification, on the real letter
```
unsourced figures detected: ['one in forty', '$300 billion', '4.8%', '1.4 million']
changed: True | length 3401 -> 3175
```
All four removed. Both occurrences of the 14.5% corrected to "14.5% drop below baseline
expectations", matching the source, and "the single largest quarterly move in the portfolio"
deleted. The prose survives intact.

### Propagation
`wiley_humanizer.py` and `wiley_bundle_supervisor.py` to wileytest and wiley, live jobs checked
(zero), all three restarted. **The stored Q3 letter still contains the bad figures** — the guard
applies to letters generated from now on. Correcting the stored one is a decision for the user.

## 2026-08-03 (later) — the topic-report DOCX was a transcript of the deck, not an executive summary

### What was wrong
The Word export for a topic report reproduced every slide: 339 paragraphs and 5,316 words for a
single topic, six topics to a report, including slide furniture like "CARD 3 OF 6", "YOUR
WINDOW" and "Based on scenarios". It was meant to be the emailable executive summary.

### How it regressed — two commits, neither of which says so
**2026-06-03, `c89e5018` ("Topic Reports tab + Future Horizons & Consensus interactive HTML
exports").** Created `topic_report_service.py` with a generation path that reads
`future_horizons_runs` directly — "No back-test, no supervisor pipeline, no reviewer gate", in
its own docstring. The supervisor is the only writer of `forecast_bundle_synthesis`
(`wiley_bundle_supervisor.py:1191`), which is what the executive-summary exports render. From
that day, no new period got one.

**2026-06-18, `451bed56` ("Daily Briefing auto-compose + monolith model repoint to gpt-5.4").**
With no synthesis row, the DOCX export was raising, so it was repointed from
`build_bundle_docx(..., updates_only=True, bundle_synthesis=…)` to a new renderer that walks the
deck. The commit message mentions this only as "Also bundles in-progress branch work (topic
report docx, etc.) for deploy integrity".

The same commit also trimmed `build_bundle_docx` itself from four sections (expert view,
cross-cutting themes, decision framework, topic summaries) down to the letter alone, citing
client feedback — "Per client feedback (Hetzscholdt, Jun 2026): the previous layered structure
… reads as cluttered for C-level". That trim was deliberate and has been left in place.

**The Markdown export was never repointed**, so it has been raising
`"No generated topic report for period_label=…"` for every period since 2026-06-03. Same root
cause, no symptom anyone noticed because nobody exports Markdown.

### The fix
**`app/services/topic_report_service.py`** gains `ensure_bundle_synthesis(period_label)`, which
runs `wiley_bundle_supervisor.run_pipeline` with `cadence="topic_report"` and the period's own
topics-hash label when no row exists. The supervisor persists as it goes, so a request that dies
at a proxy before it returns still leaves the row behind and the next call is instant.

`generate_topic_report_docx` is back to `_load_cached_state` + `build_bundle_docx(...,
updates_only=True)` — the same renderer and the same mode that produced the pre-June documents.
The deck transcript is not lost: it moved to `generate_topic_report_docx_full`, served from a new
`GET /api/topic-reports/{period_label}/download-full.docx`.

### Verification
Rendered the restored path against the surviving `topic_report / Q2_2026__64da6ed5` synthesis:
16 paragraphs, 606 words, titled "Wiley Horizons — Executive Summary" with the five-section
letter and the "— AunooAI Editorial Team" signoff. The transcript route returns 200 on
wileytest, and `download.docx` for a period with no synthesis correctly starts the pipeline.

**Provenance correction.** The Q2 document held up as the reference was not a topic-report
export at all. It came from `cadence='quarterly'`, `period_label='Q2 2026'` — the quarterly
bundle, whose five topics match it exactly and whose payload carries the `expert_commentary`
that the topic-report row lacks. The `topic_report / Q2_2026__64da6ed5` row covers only Quantum
Computing.

### Incident: a smoke test started a real pipeline run
Curling the restored `download.docx` for Q3 with no synthesis row did what the code now says it
does — it started the multi-agent supervisor run. The 25-second curl timeout did not stop it;
LLM calls kept flowing afterwards. It was left to finish, because it produces the Q3 executive
summary that was wanted anyway, but a smoke test should not have been the thing that triggered
it.

**Lesson: an endpoint that generates on demand is not safe to smoke-test.** Check for a
cheap read-only path first, or test against a period that already has its content.

### Two more defects the accidental run exposed
That run finished at 14:09:18 with `reviewer: approved_with_warnings`, and the document it
produced is 115 words. Two separate causes.

**The executive-summary agent's JSON failed to parse, and the pipeline called it a success.**
`wiley_exec_summary_agent JSON parse failed: Expecting ',' delimiter: line 2 column 2108`. The
parser in `_call_agent` already strips code fences and uses `strict=False` for literal newlines,
so this was a real syntax error mid-letter — an unescaped quote or backslash around character
2109. On failure it returned `{}`, the letter was dropped, and every other field persisted
normally, so nothing downstream noticed. `build_bundle_docx` fell back to `strategic_overview`,
which is 686 characters, and the whole executive summary came out as one paragraph.

**`app/services/wiley_bundle_supervisor.py`** now retries once on a parse failure, feeding the
model its own malformed reply and the parser's error and asking for valid JSON with quotes and
backslashes escaped. It only fires on failure, so it costs nothing on the normal path. Same
shape as the signal-report retry.

**The state sidecar stored display names, so one topic was silently dropped.**
`_write_state_sidecar` was written from `included_topics`, which have been through
`_apply_overlay_display_names`. So the sidecar held "Scientific Publishing" while
`future_horizons_runs` holds "Scientific Publishers - General Monitoring". `resolve_items` looks
up by the real name, missed, and logged one line — `Topic report: skipping Scientific Publishing
— no forecast run` — before carrying on with five topics. The synthesis row records
`topics` as those five.

Every export that reads the sidecar was affected: DOCX, Markdown and HTML. The deck was not,
because deck generation uses the input topic list rather than the sidecar. Fixed by writing the
source topic names; the Q3 sidecar file was corrected in place so the next export resolves all
six.

**Display fix:** the DOCX header and signoff printed the internal cache key
(`Q3_2026__2cec74a7 update`). They now use the human period from the sidecar, "Q3 2026".

### Reran it — the retry fired and the document is right
Regenerated the Q3 synthesis over all six topics at the user's go-ahead. The exec-summary agent
broke again, at a different offset (`char 1636` against `char 2109` the first time), so this is
not a one-off unlucky reply — the agent emits invalid JSON on this payload fairly reliably. The
retry recovered it in nine seconds:

```
14:44:34  wiley_exec_summary_agent JSON parse failed: Expecting ',' delimiter … — retrying once
14:44:43  exec_summary/completed 0.9
14:45:00  complete/approved_with_warnings 1.0
```

The letter is 3,401 characters and the rendered DOCX is 471 words across the five sections, with
"Q3 2026 update" in the header. Total pipeline time 14:43:32 → 14:45:00.

**One more display fix.** The signoff read "— AunooAI Editorial Team · Q3_2026__2cec74a7",
because `build_bundle_docx` prefers the agent's own `signoff` string and the agent echoes the
period it was handed. It now substitutes any `…__<hex>` token for the display period, so the
footer matches the header.

### The HTML and Markdown exports, closed out
`_load_cached_state` resolved items from the synthesis row's `topics`, which are post-overlay
display names, so it found 5 assessments for 6 topics. It now reads the state sidecar first —
that holds source names — and falls back to the row. For rows and sidecars written before
today, `source_topic_for_display_name()` in **`app/services/forecast_assessment_service.py`**
reverses the overlay (`"Scientific Publishing"` → `"Scientific Publishers - General
Monitoring"`), returning None when a string is not a display name so callers can distinguish
"no mapping" from "maps to itself". A topic that still resolves to nothing is now logged by
name instead of vanishing.

Markdown also gained the `ensure_bundle_synthesis` call the DOCX has, so it stops raising
"No generated topic report for period_label=…" on a period that has never had one.

**HTML needed no change beyond the sidecar fix.** It is a different product — the interactive
deck (`build_topic_report_html`), resolved through `resolve_items` from the sidecar, not the
bundle summary — so correcting the sidecar was enough. It was left as the deck rather than
repointed at the executive summary.

Verified on wileytest against Q3: all three resolve 6 of 6 topics, Markdown 33,010 bytes, HTML
390,566 bytes, DOCX 38,557 bytes. Against the running service after restart, all four export
routes return 200: `download.docx`, `download.md`, `download.html`, `download-full.docx`.

### State
Deployed to wileytest and wiley, all three services restarted, live jobs checked first (zero).

## 2026-08-03 (later still) — four defects found by reading the generated deck

### Goal
The Q3 2026 topic report was re-run and read end to end. Four problems in the output, none of
which any test would have caught, because they are all about what the slides claim rather than
whether they render.

### "What We Monitor" counted collected articles and called them analysed
**`app/services/topic_report_pptx.py`**, slide 8. The query was `COUNT(*)` per topic, labelled
"articles analysed". Those are collected counts, and the relevance gate rejects most of what the
collectors bring in before any AI analysis runs.

The overstatement was 4x overall — 623,027 claimed against 151,812 actually analysed — and far
worse per topic: Scientific Publishers – General Monitoring showed 37k against 1,207 analysed
(3.2%), Attacks on Expertise 32k against 2,374 (7.5%). Slide 8 also contradicted slide 12, which
reports the analysed figure for the same topic and read "90".

Now counts `category IS NOT NULL AND sentiment IS NOT NULL`, drops topics with none, and the
subtitle carries both numbers — "18 topics · 151,657 articles analysed of 622,532 collected" —
so the ratio is visible rather than something the reader has to take on trust. The ordering
changes as a result, honestly: Geopolitical Hotspots (72,367 analysed) now leads instead of AI
and Machine Learning, and Scientific Publishers drops from third to fifteenth.

### One syndicated story counted as fourteen articles
**`app/services/forecast_assessment_service.py`**, **`app/services/forecast_pptx_export.py`**.
An emerging theme read "Misinformation Impact On Cancer Vaccines · 14 articles" and its sample
list showed the same headline five times. All 14 rows were one Conversation piece republished by
13 US local papers plus The Hindu, twelve of them ingested inside the same second. Distinct URLs
and distinct sources, so they are legitimately distinct rows — and a single story.

The cluster builder now computes `distinct_stories` from normalised headlines, samples one
article per story, and ranks themes by distinct stories rather than row count, so a wire story
cannot outrank a theme with several independent sources. The renderer shows
"14 articles (1 story)" when the two differ, and dedupes the sample list itself as well, so
assessments stored before today display honestly without being regenerated. Themes with no
syndication read "9 articles" exactly as before.

### The topic divider showed February and May dates on an August deck
**`app/services/forecast_bundle_pptx.py`**. The divider read "Original forecast 2026-02-16 ·
Latest assessment 2026-05-22" with no mention that the Three Horizons analysis had been re-run
that morning. It now leads with the run the deck actually visualises and states how far behind
the assessment is:

```
This analysis 2026-08-03  ·  Original forecast 2026-02-16  ·  Latest assessment 2026-05-22 (73d earlier)
```

The staleness note appears only past 30 days. `_days_between` compares on the date alone, since
one side is usually timezone-aware and the other is not.

**Not a bug, checked and left alone:** the deck showing the 05-22 assessment when a 05-24 row
exists. `get_latest_forecast_assessment_by_topic` deliberately skips assessments with no scenario
verdicts (`database_query_facade.py:8269`), and the 05-24 rows have none.

**Two clocks, two slides apart.** Slide 12's "GENERATED 2026-08-03 10:16" was UTC while slide
11's dates were local, because `topic_report_service.py` stamped `generated_at` with
`datetime.utcnow()` — a naive UTC string. All three occurrences now use
`datetime.now().astimezone()`, so the stamp carries an offset and renders as local time.

### The humanizer had never run on this deck, and would not have caught it anyway
**`app/services/topic_report_service.py`**, **`app/services/wiley_humanizer.py`**. Two separate
gaps behind one symptom.

`wiley_humanizer` was imported in exactly one module, `wiley_bundle_supervisor.py`. The
topic-report path had no reference to it, so its prose went from the model's JSON onto a slide
unchecked. `WILEY_HUMANIZE` defaults to on and wileytest sets `HUMANIZE_MODEL`, so the
configuration looked live while being unreachable from this pipeline.

Even wired in it would have passed. Running the detector on the offending slide: the lede scored
**3 tells** (promotional "unprecedented", two em dashes) and the intelligence view scored **0**,
against a threshold that only rewrites *above* 3. The detector catches vocabulary and
punctuation; it does not catch "dual assault", "core value proposition", "the window for
publishers to act unilaterally is narrowing", the escalating "Critically, …" turn, or the
rule-of-three list of failing safeguards — which is what actually made it read as slop.

So both ends were fixed. `humanize_text` takes a `threshold` override; the topic-report pass uses
1 (`REPORT_TELL_THRESHOLD`), because slide prose is two or three sentences and the global default
of 3 is calibrated for long-form. And the generation prompt gained a Writing rules block that
bans the specific constructions by name, requires the finding before the explanation, and
requires every number to carry its meaning in the same sentence. The prompt is the real fix; the
humanizer is the backstop.

### Verification
The dedup and label helpers were exercised directly against the real syndication case: 14 rows →
2 distinct stories → 2 samples, `_theme_size_label` renders "14 articles (2 stories)" and plain
"9 articles" when nothing is syndicated, legacy rows without `distinct_stories` are unchanged,
ranking puts a 9-story theme above a 14-row 1-story one, and a 5-copy legacy sample list
collapses to 1. `_days_between` returns 73 for the real pair and None for missing or unparseable
input. The new coverage query was run against wileytest and returns the 18 topics above.

The prompt and humanizer changes are not verifiable without generating a deck, which is a
customer-facing re-run; they are exercised by the next report rather than proven here.

### Propagation
Six files copied to wileytest and wiley, both trees identical to each other beforehand and
differing from canonical only by these changes. `py_compile` clean under both venvs, all three
services restarted, clean startup. **Live jobs were checked first on both tenants** — zero
started since process boot — following this morning's incident.

The cached PPTX at `/tmp/topic_report_render_cache/topic_report_Q3_2026__2cec74a7.pptx` predates
all of this. A re-run with `rerun_forecast` invalidates it; a plain re-request returns the stale
deck from cache.

## 2026-08-03 (later) — Auspex was counting rejected articles as missing data

### Goal
An Auspex report on wileytest's ASML Watch topic opened with a "Sentiment Paradox": 80.2% of
articles unclassified for sentiment, and an inference about market bifurcation drawn from the
5.4% that were negative. The question was why sentiment coverage was so low. It isn't — the
denominator was wrong.

### What the numbers actually were
ASML Watch on wileytest holds 888 collected articles. 708 (79.7%) have no sentiment, which
matches the report. But 752 of those 888 have `ingest_status = 'filtered_relevance'`: the
collector's relevance gate rejected them before the AI analysis step ever ran, so they have no
category and no sentiment by design. 707 of the 708 unclassified articles are those rejects.

All 135 `approved` articles have sentiment. **Coverage among analysed articles is 100%, not
20%.** The gate is `keyword_monitor_settings.min_relevance_threshold = 0.5`, applied globally;
rejected articles average 0.188 topic alignment against 0.785 for approved ones.

### Auspex now excludes rejected articles from its corpus
Auspex retrieval had no `ingest_status` filter on any path, so it pulled approved and rejected
articles together and then reported the gap between them as missing data. Two mechanisms, both
additive, both defaulting to the old behaviour for every other caller:

- **`app/database_query_facade.py`** — `search_articles()` gains
  `exclude_ingest_status=None`. When set it adds
  `ingest_status IS NULL OR ingest_status NOT IN (...)`. NULL rows are kept, because NULL means
  the column was never written rather than "rejected".
- **`app/vector_store_pgvector.py`** — the metadata filter gains a `$ne` operator, compiled to
  `IS DISTINCT FROM` rather than `<>` for the same NULL reason. It had `$gte/$lte/$gt/$lt` and
  bare equality only.

**`app/services/auspex_service.py`** declares `REJECTED_INGEST_STATUSES` and a
`_exclude_rejected_filter()` helper, and applies the exclusion at all eleven retrieval sites —
seven `self.db.search_articles()` calls and four `vector_search_articles()` calls.

Measured against the live data, both filters keep 136 of 888 ASML articles (135 approved plus
one whose status was never written). The vector path returns 135 of those, because the
status-NULL article has no embedding. Sentiment coverage in the kept corpus is 135/136.

**Related, flagged and not changed:** five places in `auspex_service.py` (`:642`, `:1187`,
`:1300`, `:1560`, `:2880`) default a missing sentiment to `"Neutral"`. With rejects excluded
that default should almost never fire, but it is still a silent substitution in a sentiment
breakdown.

### ASML Watch gets its own relevance threshold — and manual runs now honour it
77 of the rejected ASML articles scored 0.4 or above, and spot-checking shows real losses:
"China's home-grown DUV progress not the biggest threat to ASML, analysts say" scored 0.40 and
was dropped. The group had no override, so it used the global 0.5.

`keyword_groups.min_relevance_threshold` for group 27 (ASML Watch) should be set to 0.4. **That
UPDATE has not been applied** — the tool call was blocked, so it is waiting on the user. On past
volume it moves roughly 77 articles from rejected to analysed, about a 57% increase on the 135
now approved, with the matching increase in analysis cost.

**`app/tasks/keyword_monitor.py` — the setting was only half-wired.** The scheduler
(`_run_group_check`) stores the group's threshold in `_group_relevance_threshold` before calling
`check_keywords`, but `/check-now` calls `check_keywords` directly, so a manual single-group run
left it unset and silently used the global threshold. `check_keywords` now reads the group's own
value when the scheduler has not already set one, and clears it on an all-groups run so a manual
run cannot leak its threshold into the next full pass.

It reads `get_keyword_group_with_settings()`, not `get_keyword_group_by_id()` — the latter
selects a fixed narrow column list that does not include `min_relevance_threshold`, and there are
two definitions of it in the facade (`:3501` and `:12973`), the later one winning.

### Deployed
All four files copied to wileytest and wiley, all three services restarted, clean startup on
each (`/api/trend-convergence/models` returns 200 on 10002, 10006 and 10004). The corpus the
deployed code now selects for ASML Watch:

| | articles |
|---|---|
| collected | 888 |
| Auspex SQL corpus | 136 |
| Auspex vector corpus | 135 |
| of the SQL corpus, with sentiment | **99.3%** |

**`database_query_facade.py` was patched surgically on wileytest, not copied.** That tenant
keeps `'social_meta'` in the saved-field list at `:4874` where canonical does not; a wholesale
copy would drop it and lose author and engagement data for social posts for good. The two hunks
were applied in place with an assertion that the local line survives, and the post-patch diff
against canonical is that one pre-existing difference and nothing else. wiley's copy had no
drift, so it was copied whole.

**Still not applied: the ASML threshold.** `UPDATE keyword_groups SET
min_relevance_threshold = 0.4 WHERE id = 27` on wileytest is with the user.

### INCIDENT: a restart killed a running topic report, and it kept reporting "running"
While verifying the 72h fix earlier the same day, wileytest was restarted at **10:23:58**. A
topic report (`45d7f2ff`, `topic_report:Q3_2026__2cec74a7`, six topics) had started at
**10:16:23**. The restart ended it 7.5 minutes in, after three of six topics.

**It went unnoticed for 100 minutes because the job kept reporting `running` at 35%.**
`BackgroundTaskManager` persists every progress update to the `background_tasks` table
(`background_task_manager.py:67`), but the `asyncio.Task` itself lives only in an in-memory
`_running_tasks` dict (`:55-56`). A restart drops the task and leaves the row untouched. There
is no `updated_at` column and no reaper, so a killed job is indistinguishable from a slow one
by looking at the row — which is exactly the mistake made here, twice, including an ETA of
14:00 extrapolated from a job that had been dead for over an hour.

**How it was actually diagnosed**, in the order that worked:
- `ps -o lstart` on the service: current process started 10:49:58, so anything with
  `started_at` before that cannot be executing.
- `llm_usage_log`: the job's six Sonnet calls run 10:17:38 → 10:23:12 in pairs (~75-95s
  scenarios, ~52-56s executive summary) and then stop dead. The later Sonnet burst at
  10:57–10:59 was `wiley_candidate_scheduler`, not this job.
- `future_horizons_runs`: exactly three rows from today — the three completed topics. Quantum
  Computing, the one the status line claimed to be working on, has none.
- `py-spy dump` on the service: every thread idle, nothing inside an LLM call.

**23 phantom `running` rows** were sitting in wileytest's `background_tasks`, the oldest from
June, every one of them predating the current process boot. `45d7f2ff` was marked `failed` with
the reason recorded; the other 22 were left alone.

**Lessons.**

**NEVER restart a monolith tenant without checking `background_tasks` for a job that started
after the current process boot.** `ps -o lstart -p $(systemctl show -p MainPID --value
{tenant}.aunoo.ai.service)` gives the boot time; anything younger is live work that a restart
destroys with no resume.

**A `running` row is not evidence that anything is running.** Cross-check against process start
time and `llm_usage_log`; both are cheap and both are conclusive.

**Do not extrapolate an ETA from a progress percentage.** In `topic_report_service.py:721-732`
the 5→65% band is split evenly across topics, so the bar measures topics completed, not time,
and it cannot distinguish "between steps" from "dead". Time the underlying work instead — here,
2.3 minutes per topic from the LLM ledger, against the 28 minutes/topic the percentage implied.

## 2026-08-03 — the foresight model dropdown was never fixed, only the endpoint nobody calls — `cbf5091a`

### Goal
wileytest's Anticipate page was still offering two dozen models in its dropdown, most of them
duplicates under the wrong vendor name. That was supposed to have been fixed on 30 July by
`1ddef137`. It looked like a regression.

### It was never a regression — the fix landed on an unused endpoint
`1ddef137` rewrote `GET /api/trend-convergence/models` to return the 5 distinct Bedrock models
instead of every litellm alias. That endpoint works, on every tenant:

```
curl http://127.0.0.1:10002/api/trend-convergence/models   # wileytest
→ 5 entries: Claude Sonnet 4.5, Claude Haiku 4.5, Nova Pro, Nova Lite, Kimi K2.5
```

Nothing calls it. The foresight page's React hook (`ui/src/hooks/useTrendConvergence.ts:176`)
gets its list from `getAvailableModels` in `ui/src/services/api.ts`, and that function fetched
`/api/available_models` — the raw litellm alias list. On wileytest that returns **23 entries**,
of which 7 are `gpt-*` names resolving to `claude-haiku-4-5` and 5 more resolving to
`claude-sonnet-4-5`.

The shipped bundle confirms it. `static/trend-convergence/assets/main-tSf9t5Zg.js` (the file
`templates/trend_convergence_react.html` loaded until today) contains 6 occurrences of
`api/available_models` and **zero** of `trend-convergence/models`. No deployed bundle anywhere
under `static/` on wileytest referenced the fixed endpoint.

So the July verification — curling the endpoint and counting 5 models — proved the endpoint,
not the dropdown. The dropdown had never changed.

### The fix — point the frontend at the endpoint that was already correct
**`ui/src/services/api.ts`**. `getAvailableModels` now fetches
`/api/trend-convergence/models`, whose response is already `{id, name, context_limit}`, so no
transform is needed. The old code's `contextLimits` lookup table and its OpenAI/Anthropic
fallback list both went away; the fallback is now the same 5 models, so a failed fetch cannot
put aliases back on screen.

Blast radius is one page. Only `useTrendConvergence` imports this function — the newsfeed,
gather and narrative-explorer services each have their own `getAvailableModels` hitting
`/api/available_models`, and those are untouched. Their dropdowns still show the full alias
list, which is a separate open item (see below).

### Verification
Built with `./ui/deploy-react-ui.sh`. The new chunk carrying `api.ts` is
`assets/index-BWmuoqcd.js`, and it is the only asset containing `trend-convergence/models`:

```
grep -rl "trend-convergence/models" static/trend-convergence/assets/
→ static/trend-convergence/assets/index-BWmuoqcd.js
```

`templates/trend_convergence_react.html` now loads `main-CNXurXiG.js` with
`index-BWmuoqcd.js` preloaded. Both wileytest (:10002) and wiley (:10006) serve the new chunk:
`GET /static/trend-convergence/assets/index-BWmuoqcd.js` → 200 on each.

### Propagation
Built in canonical (bugfixing), then `rsync -a static/trend-convergence/` plus a copy of the
six react templates to wileytest and wiley. Before copying, every template diff against
canonical was checked and contained nothing but asset-hash lines, so no tenant-local template
content was overwritten.

The type-checker is canonical-only on purpose. Frontend builds happen in bugfixing and the
result is rsynced, so wiley and wileytest need no `typescript` install; their `ui/` trees are
stale copies that nobody builds from.

The second pass added a backend change, so `app/routes/trend_convergence_routes.py` was copied
to both tenants as well. The diff beforehand was exactly the one hunk written today, nothing
tenant-local, and it compiles under each tenant's own venv. All three services were then
restarted. Users on the old bundle pick the new one up on a hard refresh.

wbm has no foresight page and was not touched. saasmvp-app has its own frontend and is
unaffected.

### Every other model picker in the UI, same day
The foresight fix left the alias list in every other dropdown, so the rest followed. There were
**twelve** of them, not the four the first pass counted — the earlier grep only looked for
imports of `getAvailableModels` and missed the components that `fetch('/api/available_models')`
inline.

Four service functions and eight components now read `/api/trend-convergence/models`:

- **`ui/src/services/newsFeedApi.ts`** — add-agent modal, emerging-topics config.
- **`ui/src/services/narrativeExplorerApi.ts`** — the model select in the Explore header. This
  one shares a dropdown with the newsfeed list and was missed in the first pass entirely.
- **`ui/src/services/gatherApi.ts`** — gather group settings, auto-collect. It read
  `/api/auto-ingest/models`, a different route serving the same raw list.
- **`ui/src/services/auspexService.ts`** — the Auspex chat model select, also on
  `/api/auto-ingest/models`.
- **`ui/src/SubmitArticlesApp.tsx`** and the six `*TuneModal.tsx` components (EOS, FH, EB, SIO,
  Newsletter, FG) fetched `/api/available_models` inline.

Two mechanical points made this more than a URL swap. The curated endpoint returns
`{id, name}` where `name` is a display label ("Claude Sonnet 4.5") and `id` is the alias that
must be stored (`bedrock-claude-sonnet`); several components used `model.name` as both the
label and the saved value, so they now carry a separate `label` field. And a config that
already holds an alias — `gpt-5.4-mini` on an existing agent — would render as a blank
dropdown now that the alias is not listed, so every one of these pickers keeps the saved value
as an extra entry. `EmergingTopicsConfigModal` previously did worse than blank: it silently
substituted the first option for an unrecognised saved model, which is how a saved setting
gets changed by opening a dialog. It now keeps the saved value.

**`app/routes/trend_convergence_routes.py`** gained one field: `provider`, taken from the same
`get_available_models()` scan the route already ran, so labels read "Claude Sonnet 4.5
(bedrock)" instead of a hardcoded vendor guess.

Stale fallback lists (used when the fetch fails) were replaced in `NewsFeedHeader.tsx`,
`EmergingTopicsConfigModal.tsx` and `api.ts`. They offered `gpt-5.4`, `gpt-5.4-nano` and
`claude-sonnet-4-20250514`.

### Verification, second pass
No file under `ui/src/` fetches `/api/available_models` or `/api/auto-ingest/models` any more
(two comment mentions remain). No built asset under `static/trend-convergence/assets/` contains
either path. All three tenants return the 5 models with the new `provider` field:

```
curl :10004 | :10002 | :10006 /api/trend-convergence/models
→ 5 entries each, every one "provider":"bedrock"
```

Every asset referenced by the six react templates returns 200 on wileytest and wiley, with one
exception noted below. Services restarted: bugfixing, wileytest, wiley — all `active`. The
TypeScript changes were verified by the build and by reading at the time, because the project
had no type-checker; one was added later the same day (below) and they check clean under it.

### The UI now has a type-checker — `npm run typecheck`
There was none. `ui/package.json` had `vite` and no `typescript`, no `tsconfig.json`, no
`@types/react`. `vite build` runs esbuild, which strips types without checking them, so a
misspelled property or a wrong argument built cleanly and failed in the browser.

Added `typescript@5.6.3`, `@types/react@18.3.12`, `@types/react-dom@18.3.1` as devDependencies,
plus `ui/tsconfig.json`. Its `paths` mirror the `resolve.alias` block in `vite.config.mts`,
including the five versioned imports the Figma export left behind (`sonner@2.0.3`,
`next-themes@0.4.6`, `input-otp@1.4.2`, `react-day-picker@8.10.1`,
`react-resizable-panels@2.1.7`). Keep the two in step — a path here that vite does not have
type-checks and then fails to build.

**247 pre-existing errors, so the check runs against a baseline.** A first run on this tree
reports 247 errors, and 173 of them are in two files: `App.tsx` (98) and `PAMDashboard.tsx`
(74), nearly all union-narrowing complaints like "Property 'scenarios' does not exist on type
'TrendConvergenceData | MarketSignalsData'" — code that works at runtime because the union
member is right in context. Failing on all 247 would mean nobody runs the check. So
`ui/typecheck.mjs` records the known set in `ui/tsconfig.baseline.txt` and fails only on errors
outside it. Baseline entries drop line and column numbers, so editing above an existing error
does not manufacture a failure, and the absolute checkout path is stripped from messages so the
file is portable between tenant trees.

`strict` is off, as are `noImplicitAny` and `strictNullChecks`. This catches the class of
mistake that breaks a page — a property that does not exist, a wrong argument, a misspelled
prop — without demanding a null-safety pass over 3,717 modules. Tighten one flag at a time.

`ui/deploy-react-ui.sh` runs the check before `npm run build` and stops the deploy on a new
error. `SKIP_TYPECHECK=1` overrides it.

Two commands: `npm run typecheck`, and `npm run typecheck:update` to re-record the baseline
(also the way to bank a fix, since it prints how many baseline errors are now gone).

**Verified two ways.** Clean run: `Type check clean: 247 errors, all 247 known`. Then twice
deliberately broken — `m.name` → `m.nmae` in `newsFeedApi.ts`, and a `const x: number =
"string"` appended to `api.ts` — and each time the check reported exactly one new error with
its file and line and exited 1. Both edits were reverted; `git status ui/src` is clean. A full
`./ui/deploy-react-ui.sh` then ran with the gate in place and produced byte-identical assets
(`main-CsIM0Gi4.js` unchanged), so no tenant needed re-syncing.

Today's model-picker changes type-check clean. The errors in files touched today
(`NewsFeedHeader.tsx`, `NewsletterTuneModal.tsx`, `api.ts`, `newsFeedApi.ts`,
`useNarrativeExplorer.ts`) are all pre-existing and all in the baseline.

### First baseline error paid off: `72h` was missing from `DateRange`
The new check's first finding. `NewsFeedHeader.tsx:46` offers "Last 72 hours" in the date-range
dropdown, but `DateRange` in **`ui/src/services/newsFeedApi.ts`** listed only
`24h | 7d | 30d | 3m | 1y | all`.

The option was not broken — it was untyped. The backend understands `72h`
(`news_feed_service.py:85` and `:196`, `news_feed_routes.py:1358`, `:1456`, `:2636`), and
`useArticleSearch.ts:44` already sends it. So the fix is to add `'72h'` to the union rather
than remove the option.

Baseline is now 246. The rebuild produced byte-identical assets, which is expected for a
type-only change and means no tenant needed re-syncing.

### The matching backend gap: `72h` silently meant 7 days on one endpoint
**`app/routes/news_feed_routes.py`**, `GET /api/news-feed/articles/list` — the flat
chronological list behind the Explore article view. Its date-range chain at `:329` had no
`72h` case, so the request fell through to `else: start_date = now - timedelta(days=7)`.
Picking "Last 72 hours" returned a week of articles, with no error and nothing in the logs.

Added the missing branch (`days=3`) and put `72h` in the `Query` description, which had also
omitted it. The `else` fallback stays, so a genuinely unknown value still degrades to 7 days.

A sweep of all six `date_range == "24h"` chains found this was the only one missing the case:
`news_feed_service.py:79` and `:190`, and `news_feed_routes.py:1355`, `:1453` and `:2633` all
handle it.

**Verified on all three tenants** — article counts for the same query, which must sit between
the 24h and 7d counts:

| tenant | 24h | 72h | 7d |
|---|---|---|---|
| bugfixing | 50 | 381 | 1102 |
| wileytest | 256 | 1845 | 5396 |
| wiley | 67 | 281 | 1562 |

Before the fix, `72h` returned the 7d number. A control request with `date_range=bogus` still
returns 1102 on bugfixing, confirming the fallback path is untouched. Copied to wileytest and
wiley (no drift in that file on either — the diff was exactly this hunk), compiled under each
tenant's venv, all three services restarted and `active`.

### Not fixed — a stale modulepreload in `pam_react.html`
`templates/pam_react.html:34` preloads `usePAM-zQ3fJmWy.js`, which does not exist; the built
chunk is `usePAM-DfZaKsti.js`. The deploy script rewrites `usePAM-*.css` but has no rule for
`usePAM-*.js`. This predates today — the same stale hash is in the file at `25812e69` — and is
harmless, because the PAM chunk imports the correct hash and a failed preload hint is ignored.
Left alone deliberately; it is a deploy-script gap, not part of this work.

### Lessons
**Verify the surface the user sees, not the endpoint you edited.** `1ddef137` was verified by
curling its own route, which will always agree with the code you just wrote. One `grep` of the
deployed bundle for the endpoint name would have caught this on 30 July, and instead the wrong
dropdown stayed up for four days across two prod tenants.

**`/api/available_models` and `/api/auto-ingest/models` are the raw alias list. Never point a
picker at either.** They return every `model_list` entry in `litellm_config.yaml` whose API key
is set — 23 on wileytest, collapsing onto 5 real models. `/api/trend-convergence/models` is the
curated one, and its docstring now says so.

**Grep for the URL, not for the helper function.** Counting importers of `getAvailableModels`
found 4 pickers. Grepping for `/api/available_models` found 12. Components here fetch inline as
often as they go through a service module.

**A `.tsx` edit is not verified by a green build.** `vite build` strips types without checking
them. Run `npm run typecheck` in `ui/` before deploying — the deploy script now does it for
you.

## 2026-08-02 — every monolith tenant moved to the local 768-d encoder (and a four-week wbm outage found on the way)

### Goal
None of this was planned. While fact-checking one line of `AI_DESIGN_PATTERNS.md` — the claim
that monolith retrieval embeddings are "OpenAI `text-embedding-3-small` (1536-d), silent
random-vector fallback" — the per-tenant check turned up a live failure on wbm. Fixing that
made the rest follow: bugfixing and wiley were the last tenants still embedding through OpenAI,
and leaving them there meant three different embedding spaces across four tenants.

### The wbm outage: four weeks with no embeddings at all
wbm's code embedded at 1536-d while its `articles.embedding` column was `vector(768)`. Every
upsert raised `expected 768 dimensions, not 1536`. The errors were arriving every few seconds
and had been since **2026-07-05**, so 26,348 articles were collected and none were vectorised.

The mismatch was somebody else's half-finished migration. wbm's `vector_store_pgvector.py` had
not been modified since 23 March and contains no 768-d code, so the 487,233 vectors already in
that database were never written by wbm's own application. The column and its data were
converted to 768-d on 5 July; the application was not.

**Why nobody noticed.** Brand alerts kept firing — 28, 17, 16 and 14 events in the weeks after
the break — because that path is SQL matching plus local classifiers and never touches
`articles.embedding`. What died was semantic: story clustering made its last assignment on 13
July, eight days after the break, which is how long the already-embedded backlog lasted. The
code says so plainly at `brand_watcher_stories.py:15` — "Articles without an embedding are
simply never written here." No error, no empty state, no warning. Stories stop growing and
searches return older articles that look plausible.

**Fix.** Copied wileytest's `vector_store_pgvector.py` onto wbm. The diff beforehand was 115
lines in exactly two hunks, both the encoder swap, with no wbm-local content elsewhere in 1,220
lines. Restarted, then backfilled the 26,348 stranded articles at ~36/s in 720s, zero failures.

### Proving the old vectors could stay
Before touching anything, the question was whether wbm's 487k existing vectors came from the
same encoder wileytest uses. If not, old and new vectors would sit in different spaces and
cosine distance across them would quietly return nonsense rather than erroring.

Re-encoded five sampled articles through wileytest's encoder and compared against their stored
vectors. **Three of five scored cosine 1.0000** on `title` + `summary`; the other two scored
0.91–0.93, consistent with summaries re-enriched after embedding. An exact 1.0000 cannot happen
across different models, so the corpus was already in the right space and no re-embed was needed
— only the 26k gap. The matching input convention is `{title, description: "", content: summary}`,
which is also what `embedding_backfill._doc_text` builds as `title\nsummary`.

### bugfixing and wiley migrated — `alembic emb_768_01`
New revision on each tenant, parented on their shared head `kg_social_01`. Canonical's chain
never carried wileytest's `emb_001`, so this is a new revision rather than a cherry-pick, with
identical DDL: `articles.embedding` plus the two derived centroid columns
(`emerging_topics`, `cluster_snapshots`) dropped and re-added at `vector(768)`, and the HNSW
index deliberately not recreated inside the migration — one bulk build after the backfill is far
cheaper than maintaining it across ~193k UPDATEs.

1536-d vectors cannot be cast to 768-d, so they are dropped rather than converted. Both tenants
got a `articles_embedding_1536_backup` table first (bugfixing 51,526 rows / 415 MB; wiley 80,982
/ 652 MB), which makes the migration's downgrade branch real rather than theoretical.

**Gotcha, wiley only — pgbouncer.** wiley's alembic resolves to `127.0.0.1:6432`, which is
pgbouncer running `pool_mode = transaction`, the mode that cannot carry this DDL. bugfixing
never hit it because its `.env` points at 5432. Ran the migration as
`DB_PORT=5432 DB_HOST=localhost .venv/bin/python -m alembic upgrade head`. **Check the port
before any future schema work on wiley.**

### Phase B (multilingual-e5, 1024-d) deliberately NOT ported
wileytest carries an `article_embeddings_ml` table with 520,249 E5 vectors, and the migration
plan treats it as part of the same work. It was skipped here after checking who reads it: within
the monolith, the only reference to `article_embeddings_ml` anywhere is `ml_embedding_task.py`,
which is the writer. No monolith service, route or task queries it. The actual consumers are all
on the saas side — `cascade_detect`, `cascade_directed`, `cascade_fingerprint`,
`cascade_retrieval`, `narratives`, `relevance/scorer`. Decision (user, 2026-08-02): if it isn't
used on wileytest, bugfixing doesn't need it.

### The backfill loops are not registered anywhere
`LOCAL_EMBEDDINGS_MIGRATION_PLAN.md` states both embedding loops were registered in the
`app_factory` lifespan with 60s/90s delays. They are not. Nothing imports `embedding_backfill` on
any tenant, neither loop is running on wileytest, and `app_factory.py` is byte-identical between
bugfixing and wileytest with no reference to either. **Backfill is operator-run in practice.**
New articles still embed inline through `upsert_article`, so the backlog does not creep back —
but a gap like wbm's will never self-heal.

### Verification
- **wbm, inline path — NOT yet verified end to end.** The backfill proves writes work, but new
  articles only reach `upsert_article` after the relevance and quality gates, and nothing has
  passed them since the 15:14 restart (`rss_feed_monitor`: `processed: 2, enriched: 2,
  relevant: 0, saved: 0, vector_indexed: 0`). 160 articles collected since the restart sit with
  `embedding IS NULL` as a result. That is the gate behaving normally, not a regression — but
  the live path stays unproven until an article qualifies. Re-check within a day.
- **wbm** — 26,348 embedded, 0 failed, 0 rows left NULL at the time of the backfill. `EXPLAIN` shows
  `Index Scan using articles_embedding_hnsw_idx`, and a probe vector from a 25 July article (i.e.
  inside the dead window) returns itself and sensible neighbours. Its index was already valid,
  1,943 MB over 513,581 rows; HNSW maintains on write, so backfilled rows folded in as written.
- **bugfixing** — 193,202 embedded in 9,573s (~20/s), 0 left NULL. HNSW rebuilt `CONCURRENTLY`
  in 342s, 740 MB, `indisvalid=t`, definition byte-identical to the pre-migration one
  (`m=16`, `ef_construction=64`). `EXPLAIN` confirms `Index Scan using articles_embedding_hnsw_idx`.
- **wiley** — complete. 265,062 articles embedded in 14,963s (~17.7/s), 100% coverage, 0 rows
  left NULL. HNSW rebuilt `CONCURRENTLY` in 469s, 1,026 MB, `indisvalid=t`, `indisready=t`.
  `EXPLAIN` confirms `Index Scan using articles_embedding_hnsw_idx`, and nearest neighbours for a
  probe vector are topically coherent (three fractional-SDE maths papers). Zero dimension errors
  since its restart. The build logged `hnsw graph no longer fits into maintenance_work_mem after
  16757 tuples` — a speed warning, not a correctness one; raising `maintenance_work_mem` would
  shorten future builds.
- Two concurrent backfills ran at 17/s and 21/s rather than halving each other, so the encoder
  service was not saturated by a single job.

**A verification that was wrong and had to be redone:** the bugfixing watcher's built-in
`EXPLAIN` check piped through `head -6` and showed only the subquery's `Seq Scan`, which reads
as "the index is not being used". The real plan is an `Index Scan`. Re-checked by hand with the
probe vector inlined. A truncated plan is worse than no check, because it looks like evidence.

### Ops — wbm added to the collector health check
`scripts/collector_health_check.sh` listed `TENANTS="bugfixing wileytest wiley"`. **wbm was never
in it**, so the one tenant nobody was watching is the one that then broke. The check would not
have caught *this* failure — it watches collection volume and the keyword-monitor heartbeat, both
healthy throughout — but wbm's absence meant it was uncovered for the failures it does catch: a
dead service, a hung collection loop, collection stopping outright.

Floor set to 20 articles per 12h from measurement, not a guess: wbm's 12h buckets over the 14 days
to 2026-08-02 have median 231 and p10 74, so 20 sits well under a normal weekend dip. Consistent
with wileytest at 30 and wiley at 10. Everything else is derived per tenant from the `.env` and the
systemd unit, which wbm already satisfies.

Verified by running the live script: `[wbm] OK: articles_12h=320`, no alert state files created.
Tracked copy and the deployed `/home/orochford/bin/` copy that root's `*/30` cron runs are
byte-identical again — they drifted once before (`7dd5d56c`).

A first measurement of wbm's volume showed 07-26 with 2 articles, which looked like an outage
worth alerting on. That was an artifact of a 7-day window cutting mid-day; the real figure is 322.
The floor would have been set wrong on it.

### Monitor built — `scripts/embedding_health_check.sh` (new) + INCIDENT (4 false alarms)
Checks A–D from the spec, in the same shape as `collector_health_check.sh`: Resend alerts,
6-hour repeat suppression cleared by a recovery, log at `/var/log/aunoo-embedding-health.log`,
state under `/var/tmp/embedding_health_state`. Root crontab at `15,45 * * * *`, offset from the
collector check at `:00/:30` so they do not hit the databases together. Covers all four tenants.

- **A** — the expected width is read from each tenant's own `EMBEDDING_DIM` (falling back to 1536
  if the file still names `text-embedding-3-small`) and compared against `articles.embedding`
  plus both centroid columns. This is the check that catches the wbm outage.
- **B** — probes `DEBERTA_ENCODER_URL/encode` and requires a vector of exactly that width.
  Skipped for any tenant still on the OpenAI path, which has no local encoder.
- **C** — counts `vector upsert failed|expected N dimensions|DeBERTa encoder unreachable` in the
  last 40 minutes of the journal.
- **D** — `articles_embedding_hnsw_idx` must exist and be `indisvalid`.

Deliberately absent: any "collected but not embedded" check. It fires on every quiet
relevance-gate spell — see the 160-article case in this entry's verification section, which
looked like a fault and was not.

**Verified by fault injection, not by assumption.** Each check was run against a sandboxed copy
(email disabled, own log and state dir) with a deliberate fault: code claiming 1024 against a
768 column, encoder URL pointed at a dead port, the journal pattern matched to live lines, and a
nonexistent index name. All four fired. The recovery path was tested too — the state file
appears on fault and is removed on the next clean run, logging `RECOVERED`.

**INCIDENT — the monitor's first live run sent 4 false alarms.** At 22:30 it emailed
`db_query_failed: Could not read index state (got: 'true')` for every tenant. Every index was
valid. `psql` renders `boolean::text` as `true` here, not `t`; the `case` matched only `t`, so
the healthy branch was unreachable and all four tenants fell through to the failure arm. It
would have fired every 30 minutes indefinitely.

Fixed by accepting both renderings (`t|true` / `f|false`), with a comment saying why. Stale
state files removed, and the deployed copy re-run to confirm: four `OK` lines, zero alert state
files, no Resend IDs in the log after 22:30:36. Checked the rest of the script for the same
fragility — `indisvalid` is the only boolean it compares.

**Lesson, and it is the point of the whole exercise:** the first version was run live against all
four tenants. The sandboxed copy that caught this class of bug in seconds was built minutes
later, for the fault-injection tests. Test a monitor in a sandbox first; letting it page you is
backwards, and a monitor that cries wolf on day one is the one people learn to ignore.

### Monitoring spec — `docs/EMBEDDING_HEALTH_MONITORING.md` (new, spec for A–I; A–D now built)
What to check so a repeat is caught in 30 minutes rather than four weeks. Checks A–D are
invariants with no baselines and no false positives: code-vs-column dimension, encoder reachable
at the right width, vector-write errors in the journal, HNSW index validity. **Check A alone
catches the wbm case.** Every query in the document was run against wbm before it was committed.
Checks E and H are specified but deliberately not implementable yet and say so — E needs the
gate-passed predicate pinned down or it fires whenever the relevance filter has a quiet spell,
and H needs an enrichment-cadence baseline.

### Propagation
All four monolith tenants now run the local DeBERTa 768-d encoder with no cloud fallback:
bugfixing, wileytest, wbm, wiley. **wiley was the last OpenAI embedding path on the platform**,
so no monolith tenant now sends article text to OpenAI for embedding — worth knowing for any
data-residency answer. Nothing was committed in wiley or wbm; both are deploy-copy trees.

Docs corrected to match, since several described the old world: `AI_DESIGN_PATTERNS.md` (§3.1
gotcha at 381, the 6.1 embeddings note at 810, Appendix B at 1083),
`ARCHITECTURE_SECURITY_MASTER.md` (§3.6 at 136–137, vector storage at 147, the third-party data
table at 254), and `METHODOLOGY.md` §2.6.

### Lessons
- **A column type is not proof the code agrees with it.** wbm's schema said 768 and its code said
  1536 for four weeks. Both bugfixing's "working" status and wbm's failure were initially inferred
  from code plus column type; only wbm's was checked against live write activity, and that
  inference is what hid the outage. Check that rows are actually landing.
- **Silent-skip is worse than a crash.** `bw_article_stories` skips articles with no embedding by
  design. That turned a hard write failure into an invisible four-week coverage hole, while the
  loud part of the system — alerts — kept working and made everything look fine.
- **Never assume alembic talks to postgres directly.** wiley routes through pgbouncer in
  transaction mode. Resolve the URL before running DDL.
- **A truncated `EXPLAIN` is misinformation.** Show the whole plan or don't claim the check ran.

## 2026-08-02 — session-doc tooling, and a technical reference for `/anticipate`

### Goal
Two separate pieces of documentation work on the same day.

First, this log had drifted: the newest entry was 2026-07-23 while commits ran through
2026-07-31 (`7dd5d56c`, 2026-07-31 22:56). The gap is a process problem, not a memory problem —
nothing prompted the write-up at the moment the work was fresh. Two artifacts to close it: a
skill that produces the documentation, and a hook that fires the reminder at commit time.

Second, the foresight stack behind the Anticipate tab had no code-level description anywhere.
`METHODOLOGY.md` covers it at the conceptual level and there were `how_it_works` pages for
Topics and the Forecast Tracker, but nothing wrote down the scoring formulas, the prompt
contracts, or which of the five subsystems share a pipeline. Writing that down also surfaced
four factual errors in the two existing pages.

### `session-docs` skill — `.claude/skills/session-docs/SKILL.md` (new)
A project-scoped skill, invoked as `/session-docs`. One evidence pass produces two deliverables:
this file's dated feature-by-feature entry, and a product write-up under `docs/product/`.

It defaults to **pre-commit mode**. Scope comes from `git diff HEAD` plus untracked files, not
from `git log`. There is no SHA yet in that mode, so the skill cites paths instead. It is told
never to invent one or leave a placeholder. Verification has to run *before* the commit: an entry
claiming verification that happens afterwards is a false claim.

The skill also carries this repo's own rules. Stage with `git add -u` plus an explicit add for
the new product doc, never `git add -A` — the 2026-07-23 secret-leak entry below is why. No
invented metrics. No `git checkout` of live UI-edited state. State propagation per tenant. Do not
fix code while documenting.

Two rules were added later the same day, after a dry run on the skill's own output. There is now
a third mode for work that cannot be committed at all, and the product doc must open with an
audience note when the work has no customer-facing surface. A plain-language rule was added after
that, on the same feedback.

### Pre-commit reminder — `.claude/settings.json` (new `hooks` block)
A `PreToolUse` hook on `Bash`. It reads the command with `python3` and exits silently unless the
command contains `git commit`. Then it checks whether `docs/changes.md` is staged or modified. If
it is, the hook says nothing. If it is not, it returns
`hookSpecificOutput.additionalContext` telling the model to run `/session-docs` first, with an
explicit escape hatch for trivial commits: typo, revert, WIP, docs-only.

It never blocks. It does not set `continue: false`, so a commit is never stopped.

Two details worth knowing. `jq` is **not installed** on this box; the first attempt used it and
failed, which is why the hook uses `python3`. And matching is a substring test on the raw command.
That is what makes `git commit -a`, `--amend`, and heredoc forms all match. The cost is that any
Bash command merely containing the text triggers the check.

`enabledPlugins` was preserved when the `hooks` block was merged in.

### `/anticipate` foresight reference — `docs/how_it_works_anticipate.md` (new) — `0dc0b00c`
1483 lines, written from source and cross-checked against live rows on wileytest. The framing
the page exists to record: **Consensus Analysis and Future Horizons are not separate pipelines**
— they are two of six *lenses* over one generation path (`GET /api/trend-convergence/{topic}`,
`trend_convergence_routes.py:564`), differing only in which articles get selected and which
prompt template is loaded. The tab is served at `/trend-convergence`; `/anticipate` is a nav
label and an nginx-side alias that appears in-repo only in outbound email links.

Documented end to end: the SHA-256 cache key and its `algorithm_version` bust lever
(`:2447-2487`); the corpus query; the per-lens weighting formulas quoted from
`weight_articles_for_dashboard()` (`:168-301`) — e.g. consensus scores `+5` for high
credibility and `+3` for the 30–180 day band, while horizons scores `+8` for `future_signal`
and only `+2` for recency; context-window-driven sample sizing (`:111-139`); the MD5-based
deterministic selector with its 60% category quota (`:1626-1700`); the four consistency modes
and their regex output-normalisation; prompt assembly from `data/prompts/*/current.json`; and
the shared output envelope. Then one section per subsystem, including the Forecast Tracker's
full A–F back-test with the aggregation formulas and verdict decision tree quoted from
`forecast_assessment_service.py:696-873`.

Two operational traps are called out because both are silent: `RERANK_ENABLED` defaults to
`"false"` (`reranker.py:42`), and with it unset every article falls into the ambiguous bucket
and every scenario returns Inconclusive; and `FORECAST_TRACKER_AUTO_RUN` is unset on most
tenants (`forecast_tracker_monitor.py:60`), so nothing re-assesses automatically and an amber
health dot means nobody pressed Reassess rather than a fault.

### Drift corrections in two existing pages — `0dc0b00c`
Writing the reference meant checking the older pages against code. Six errors in
**`docs/how_it_works_forecast_tracker.md`**, four of which would mislead someone debugging:

- Classifier default given as `gpt-4.1-mini`. That is the prompt template's advisory
  `model_recommendations` field; the runtime default is
  `DEFAULT_CLASSIFY_MODEL = "gpt-5.4-mini"` (`forecast_assessment_service.py:44`).
- Strengthening / Stable / Cooling presented as verdict labels. They are the customer-facing
  rendering of the *baseline-correction* axis (`forecast_narrative.py:34-38`); the verdicts are
  Accelerating / On-track / Stalled / Off-track / Inconclusive / Done. The page now documents
  both axes and why the header chip can read "Strengthening" while the card reads "On-track".
- A "fallback to corpus-wide retrieval if the topic is too narrow" that does not exist —
  `_fetch_window_articles()` (`:470-533`) is a single query with no widening branch. The actual
  mechanism is `source_topics`. Also corrected: the window cuts on `submission_date`, not
  `publication_date`, and `embedding IS NOT NULL` is a hard filter.
- Classifier described as returning three values; the enum has six, plus an evidence type and a
  confidence score, with a 0.5 confidence floor before anything counts.
- Surprise residual described as the ambiguous bucket only; it is ambiguous ∪ `unrelated`, with
  an 8-article floor below which the panel is skipped.
- "Re-runs overwrite the most recent assessment" — `save_forecast_assessment` is a plain
  `INSERT` (`database_query_facade.py:8011`). Nothing is overwritten; the tracker reads the
  latest row, which is what the trajectory heatmap is built from.

**`docs/how_it_works_topics.md`** carried the same corpus-wide-fallback and three-verdict errors
in §6.2, plus two stale model names: the theme proposer is `gpt-5.4`
(`theme_proposer.py:97`, now cited as the config attribute so a repoint does not re-stale the
doc) and the promotion-path Three Horizons call is `gpt-5.4`
(`wiley_candidate_pipeline.py:637`), both previously documented as `gpt-4o`.

Checked and deliberately left alone because they are correct: the relevance judge
(`gpt-4.1-mini`, temp 0.2, 600 tokens, matching `wiley_relevance_judge.md`) and the overlay
agent (`gpt-4.1` from the agent frontmatter plus `reasoning_effort='high'` injected by the
caller at `wiley_overlay_generator.py:193`).

### Verification — `/anticipate` reference
Documentation has no test suite; verification here means every non-obvious claim was re-checked
against code or live data before the commit, and again while writing this entry.

- Code facts re-grepped: `DEFAULT_CLASSIFY_MODEL = "gpt-5.4-mini"` (`:44`);
  `RERANK_ENABLED` default `"false"` (`reranker.py:42`); `FORECAST_TRACKER_AUTO_RUN` gate
  (`forecast_tracker_monitor.py:60`); `insert(t_forecast_assessments)` (`:8011`);
  `default_model: str = "gpt-5.4"` (`theme_proposer.py:97`); `get_ai_model("gpt-5.4")`
  (`wiley_candidate_pipeline.py:637`). `_fetch_window_articles()` re-read in full — no fallback
  branch present.
- Live data on wileytest (79 consensus runs, 80 horizons runs, 32 assessments): verdict labels
  in use are Inconclusive 102, On-track 15, Accelerating 6, Stalled 3 — confirming the label set
  and that Off-track and Done occur zero times in current data. Article verdicts across 573
  rows: `supports_trajectory` 251, `neutral_context` 126, `better_fits_other_scenario` 116,
  `unrelated` 48, `supports_state_contradicts_trajectory` 27, `contradicts` 3.
- Assessment `config` read from the newest row confirms the documented tunables:
  `{max_articles: 2000, stage_a_top_k: 150, stage_b_min_score: 0.5, stage_c_margin: 0.04,
  window_weeks: 8}`.
- Scenario-type distribution across `future_horizons_runs`: h1 368, h2 364, h3 251, plus
  probable/plausible/possible/preferable from the Futures Cone prompt — which is what confirmed
  two scenario vocabularies coexist in the same table.
- **Found while verifying, not fixed:** 2 of 573 `forecast_article_verdicts` rows carry an
  *evidence type* in the `verdict` column (`anecdote` 1, `leading_indicator` 1). The classifier
  parser accepts whatever string the LLM returns for `verdict` without validating it against the
  six-value enum. Low impact — `_aggregate_scenario()` counts by exact match, so these rows fall
  through every bucket and land in `neutral` — but it means a malformed response is silently
  miscounted rather than retried. Not touched, per documentation-only scope.
- **Not verified:** the `raw_output` double-encoding gotcha and the deck-overlay
  match-by-`topic`-field behaviour are documented from reading the code paths
  (`forecast_assessment_service.py:102-104`, `:1140-1155`), not from an executed test.

### Verification — hook and skill
- Hook, three cases piped as synthetic stdin: `git commit` with `docs/changes.md` untouched →
  emits the JSON; non-commit command (`ls -la`, `pytest -q`) → silent, exit 0; `git commit`
  with `docs/changes.md` modified → silent, exit 0.
- Round-trip: command re-extracted *from* `.claude/settings.json` and re-run — escaping
  survived, output parsed as valid JSON (459-char `additionalContext`), plugins intact.
- Hook proved live: it fired on a real Bash call in-session (that call's command text contained
  `git commit`) and the reminder arrived as a system-reminder.
- Skill proved discoverable: `/session-docs` loaded and this entry was written by following it.
- **Not verified**: behaviour on a genuine `git commit` — no commit was made this session.

### Propagation — docs
Committed to canonical (bugfixing) as `0dc0b00c` on branch `fix/enrichment-retry-empty` — note
that is a code branch, not a docs branch, so the three pages do not reach `main` until it
merges. Docs-only: no service restart, no UI rebuild, no tenant copy needed. The pages describe
canonical behaviour and are accurate for wiley / wileytest as long as those trees are not
drifted on the files cited; per-tenant `.env` differences (`RERANK_ENABLED`,
`FORECAST_TRACKER_AUTO_RUN`) are called out in the text rather than assumed.

The same commit also carried `docs/changes.md` backfill entries and the two `docs/product/`
writeups that an earlier session had left uncommitted — included because `changes.md`'s newest
entry references the product docs, so committing one without the other would leave a dangling
reference.

### Propagation — hook and skill: none, and it cannot propagate
`.gitignore:49` ignores `.claude/`, so **both files are untracked and uncommittable in this
repo**. They are local to this checkout only: not committed here, not carried to wiley /
wileytest / wbm / saasmvp-app, and not inherited by a tenant cloned from canonical. Any tenant
that wants them needs the two files copied in by hand. This entry is therefore the only
durable record that they exist.

### Lessons
- Don't assume `jq` — it is absent on this host, and every hook example in the wild uses it.
  `python3` is present and does the same job.
- A hook that nags unconditionally gets ignored. Gating the reminder on "is `docs/changes.md`
  actually absent from this commit" is what keeps it credible.
- **Never read a model name out of a prompt template or agent frontmatter and document it as
  what runs.** `data/prompts/*/current.json` carries `metadata.model`, and
  `forecast_assessment/current.json` carries `model_recommendations`; both are advisory. This
  was the single largest source of stale model names across the `how_it_works` pages — three of
  the six corrections traced to it. Cite the service constant or the `get_ai_model()` call site.
- When a doc says a pipeline has a fallback, check for the branch before repeating it. The
  "corpus-wide fallback" claim had propagated into two pages and describes code that has never
  existed; it makes an empty-pool assessment look like a retrieval bug rather than a missing
  `source_topics` mapping.

## 2026-07-31 — observer alerts mislabelled news as social; two ops monitors

Backfilled 2026-08-02. Detail below is from the commit messages except the propagation table,
which was measured on 2026-08-02.

### Observer alerts: news articles labelled "Social" — `00cb9683`
`social_ref()` had a catch-all branch. Anything that was not Bluesky, X, or Reddit came out as
`source · Social · view post`. Most observer matches are news URLs (nature.com, cnn.com,
arxiv.org), so most matches were labelled wrong, in both the alert email and the online report.

Non-social URLs now show their publisher domain, the word "News", and "read article", and link
to the site. Instagram and TikTok post URLs (xpoz platforms) are now recognised as social.
**`app/routes/vector_routes.py`**, **`app/services/email_service.py`**.

### Ops — saas email-delivery check — `9357f4f3`
A one-shot check on the three saas changes that shipped 2026-07-31, queued with `at` for 21:00
on 08-01. Each area gets its own verdict, so a green area cannot hide a red one in the subject
line. The three areas:

- **Correspondent email.** The Newsroom-tier gate came off and 19 agents were backfilled. The
  real signal is matched runs that produced *no* email.
- **Editor advisory-lock timeouts.** Reported as failures over ticks, with the 8.7% baseline
  printed next to it. A raw count means nothing without knowing how often the lock was tried.
- **Editorial `fabricated_claim` rejections**, against a baseline of 356 in 30 days.

The lock and editorial windows start at the 22:03 deploy rather than a rolling 24 hours, so
pre-fix hours do not dilute the numbers. The script reads the journal for both `saas-worker` and
`saas-skills-worker`. Two dry runs found psql column headers leaking into scalar values, which
had also broken the empty-result fallbacks.

**`scripts/saas_email_delivery_check.sh`**, deployed to `/home/orochford/bin/`, logging to
`/var/log/aunoo-saas-email-check.log`. It does not reschedule itself.

### Ops — collector health check, tracked copy resynced — `7dd5d56c`
The tracked copy had drifted from `/home/orochford/bin/collector_health_check.sh`, which is what
root's `*/30` cron actually runs. Version control did not hold what was live.

The gap was one comment line, recording that abbott left `TENANTS` when it shut down on 07-16.
Behaviour is the same either way. The sync went tracked ← live: live is what runs, and it held
the extra context.

### Propagation (measured 2026-08-02, md5 vs canonical)
`vector_routes.py` and `email_service.py` are identical on wiley and wileytest — the observer
labelling fix is on both.

## 2026-07-30 — post-Bedrock breakage sweep (11 fixes)

Backfilled 2026-08-02. Eleven fixes with one root cause. The Bedrock migration moved every tenant
off OpenAI. Code that still expected an OpenAI model, OpenAI-shaped JSON, or a `python` on PATH
then broke, and broke quietly. Detail is from the commit messages. Propagation was measured on
2026-08-02.

### Enrichment: retry on empty or unparseable response — `c6bb7a84`
Reasoning models on Bedrock (Kimi, Nova) sometimes return text the Key:Value field parser cannot
read. The commit message puts it at roughly 1 in 8. One miss was enough to mark the article
`enrichment_failed` (`Available fields: []`).

`generate_response` plus the parse now run inside a 3-attempt retry, so a bad response recovers
instead of failing the article. **`app/analyzers/article_analyzer.py`**.

### Event-loop watchdog was crashing the process — `7258071e`
The watchdog armed `faulthandler.dump_traceback_later(all_threads)` on every cycle. When the loop
blocked for more than 8 seconds, that walked every thread's `PyThreadState` from a timer thread.
It raced native-extension code and thread teardown, and segfaulted inside
`_Py_DumpTracebackThreads` (crash IP `0x4bb854`, `segfault at 0x70`). It took wileytest down twice
on 2026-07-30, during enrichment and hybrid relevance.

The C-level watchdog now sits behind `EVENT_LOOP_WATCHDOG=1` and is **off by default**. Diagnosis
survives without it: the async lag WARNING, the ring buffer, and the admin endpoint's GIL-safe
`dump_all_thread_stacks()`. **`app/utils/event_loop_monitor.py`**.

### Add-Topic wizard: keyword suggestion dead on Bedrock — `3f6302c2`
`/api/onboarding/suggest-topic-attributes` looked through `litellm_config` for the first
`openai/` model with an API key. After the Bedrock migration there is never one, so it raised
"No OpenAI model configured" and the wizard quietly stopped calling the LLM at all.

It now resolves a bare alias through `resolve_litellm_call_params`, and defaults to a Claude
alias because Nova's structured JSON is unreliable. **`app/routes/onboarding_routes.py`**.

### Foresight model dropdown: real models, not aliases — `1ddef137`
`litellm_config` exposes about two dozen aliases (`gpt-*`, `gemini-*`, `mixtral-*`,
`claude-*-latest`). They all collapse onto a few real models: Claude Sonnet 4.5, Claude Haiku 4.5,
Nova Pro, Nova Lite, Kimi.

The `/models` endpoint returned all of them. That mislabelled Claude as GPT and Gemini, showed
duplicates, and included a fallback that gave id `gpt-5.4` the labels "GPT-4.1" and "GPT-4o". It
now returns the 5 distinct models under honest names.
**`app/routes/trend_convergence_routes.py`**.

### Trend convergence: org profile never loaded, and JSON parsing was brittle — `f27e8bb8`
Two problems in one route.

`get_organisational_profile` returns a SQLAlchemy mapping keyed by column name. The route read it
positionally as `profile_row[0]`, which raised "Could not locate column in row for column '0'".
The profile silently never loaded. It is now read by name, and tolerates a value that arrives as
JSON text or as already-decoded JSONB.

The AI-response JSON extraction used a non-greedy regex and a first-`{`-to-last-`}` scan. Nested
objects or trailing prose returned a 500. It now goes through the shared `_preprocess_response`
and `json.raw_decode`, and only 500s when nothing parseable is left. The outer `except` also
stopped re-wrapping the `HTTPException`. **`app/routes/trend_convergence_routes.py`**,
**`requirements.txt`**.

### Collectors — `4bd1aa45`, `1c09aebf`
**NewsFirehose.** Publisher and keyword names containing `&`, such as "John Wiley & Sons" and
"Taylor & Francis", reached the `/v1/search` tsquery builder and raised `PostgresSyntaxError`
(500). `_normalize_query` now strips literal tsquery operators (`& ! : * \`), so those terms
degrade to plain words.

**TheNewsAPI.** `keyword_monitor` passes `search_fields` as a comma-separated string. Calling
`",".join()` on a string iterates its characters, which produced
`search_fields=t,i,t,l,e,,,d,…`. A string is now split into a list first, which is what
`newsapi_collector` already did.

### Ingest and services — `0bbbc7db`, `28fe09d2`, `0ab6a203`, `9876623c`
Four small failures, each of which stopped work silently.

- **Hybrid relevance scoring.** `article_data` can carry a content or summary key whose value is
  an explicit `None`, so `.get(k, '')` still returned `None` and `len()` raised. Now coerced with
  `or ''`.
- **Firecrawl batch scrape.** An empty or all-invalid URL list made the call 400 with "No valid
  URLs provided". The call is now skipped.
- **Data-quality check.** It parsed the LLM reply with `json.loads`, which throws "Extra data"
  when the model adds prose after the object. It now starts at the first `{` and uses
  `raw_decode`.
- **Brand-watcher auto-retrain.** It shelled out to `python`, which does not exist on these hosts
  — only `python3` and the venv — so it failed with Errno 2. Now uses `sys.executable`.
- **Analysis cache.** Long URLs, such as Google News RSS article IDs, produced filenames over the
  255-character limit (Errno 36, silent cache-write failures). The URL portion is now capped with
  a SHA1 of the full URL appended. Short URLs keep their old names, so no existing cache entry is
  invalidated.

### Briefing Desk: model pinned server-side — `e79b7aa3`
The daily briefing's draft, incident detection, and final synthesis now read the model from
`emerging_topics_settings.model`, which overrides the browser dropdown. Composed content and the
`model_used` byline are therefore the same for everyone on a tenant. If the setting is unset, it
falls back to the model the client passed. **`app/routes/daily_reports_routes.py`**,
**`app/services/daily_briefing_compose_service.py`**.

### Propagation (measured 2026-08-02, md5 plus marker grep against canonical)
Every file is identical on wileytest. On wiley, every file is identical except two.

**`trend_convergence_routes.py` — wiley was missing `1ddef137`.** Fixed on 2026-08-02, see below.
It still carried the old alias list: 2 hits of the `'GPT-4.1'` label, where canonical and
wileytest have 0, and 3869 lines against 3831. It did have `f27e8bb8`, both the by-name
`profile_row['id']` access and the `raw_decode` path. That dates wiley's copy to between 16:05
and 16:24 on 07-30 — taken 18 minutes before the dropdown fix landed. Wiley showed fictitious
GPT and Gemini entries in its foresight dropdown for three days.

The fix, 2026-08-02. `diff -u` against canonical showed exactly one hunk, confined to the
`/api/trend-convergence/models` endpoint. There was no wiley-local divergence anywhere else in
the file, so copying the whole file was safe and a surgical hunk apply was unnecessary. Steps:
backed up wiley's copy off-tree, copied canonical over it (both now md5 `30b0c46e`), ran
`py_compile` under wiley's own venv, restarted `wiley.aunoo.ai.service` (active 10:38:53 CEST).
Verified against the running service: `curl http://127.0.0.1:10006/api/trend-convergence/models`
returns the 5 real models, and the `'GPT-4.1'` label count is 0. Nothing was committed in wiley,
which is a deploy-copy tree.

**`automated_ingest_service.py` differs by 61 lines, but has the fix.** The `0bbbc7db` `or ''`
guard is present at line 447. That diff is unrelated tenant drift.

One thing flagged but not changed, and not a propagation gap: a positional `profile_row[0]`
survives in this file on all three tenants, canonical included. It is a different code path that
`f27e8bb8` did not touch.

## 2026-07-30 — EU AI Act Article 50: label AI-generated output — `25812e69`

Backfilled 2026-08-02.

`app/compliance/ai_disclosure.py` is now the single source for two things: the visible
"AI-generated" disclosure, and the machine-readable marker. One source means they cannot drift
apart between output formats.

It is wired into email (an opt-in `X-AI-Generated` header plus a footer), HTML, PPTX, DOCX and PDF
reports, dashboard exports, and the in-app React dashboards. UI copy that claimed more than we do
— "reviewed and validated" — was softened at the same time. The commit touches 18 service files
plus the React build and templates.

### Propagation
`ai_disclosure.py` identical on wiley and wileytest (measured 2026-08-02). Per
`project_euaiact_art50_compliance`, this also shipped to the saas side (canonical `saasmvp-app`,
commit `4ef4930`) — not re-verified here.

## 2026-07-29 — enrichment loss: parser, prompt, and the relevance gate

Backfilled 2026-08-02. The highest-impact day in this range. News articles were enriched, then
silently discarded, then made permanently invisible. The measurements below come from the commit
messages. Propagation was measured on 2026-08-02.

### Root cause: the parser threw away whole analyses over heading wording — `b266238c`
`parse_analysis()` checked the model's response by exact heading match across 14 required fields.
Several ordinary things broke that check:

- the model renamed a heading, for example "Driver Signal Explanation"
- it numbered the headings, "1. Category", which the prompt's own numbered list invited
- it wrapped them in markdown
- it merged the four rationales into one "Explanation" block
- it left out "Title"

Any one of those threw the **entire analysis** away, and the row kept a NULL `category` and
`sentiment`.

That is worse than it sounds. Every observer agent retrieves on
`sentiment IS NOT NULL AND category IS NOT NULL` (`vector_routes.py`). So the article vanished
from signal alerts, `/explore`, and reports — permanently, because nothing retries it. On
wileytest this hit about 227 news articles a day. Social posts enrich on a different path and
were fine, which is why agent output had drifted toward Bluesky.

The parser now:

- strips list markers and markdown from headings **and** values. A leading `**` on a value used
  to reach the ontology check as `** Widespread adoption` and get downgraded to "Other".
- maps known heading variants onto the canonical names
- reuses a merged "Explanation" block for the per-field rationales
- falls back to the caller's title when "Title" is missing
- hard-fails only on Title, Summary, Category and Sentiment. Descriptive fields now warn and
  store blank instead of voiding the whole record.

`scripts/reenrich_parse_failures.py` recovers the backlog. It checks each topic's ontology first
and skips any topic with an empty list, because `analyze_content()` rejects those before it ever
calls the model. Wileytest's "M&A Updates" has no `future_signals`, which blocks 3,003 articles.
That is a config problem, not a parsing one.

The commit also isolates `PromptManager` storage in tests.
`PromptTemplates.load_custom_templates()` calls `save_version()`, so running the suite had been
overwriting the live `data/prompts/current.json` with the test fixture's placeholder prompt.

### The prompt was inviting the drift — `8712c41c`, then `3f37ef27`
Six defects in the analysis prompt. Each one maps to a failure in the logs:

- Two competing "Format your response as follows:" blocks. The first listed only "Summary:", so
  a model that anchored on it emitted nothing else.
- Sections numbered 1–8, which came back as headings.
- Section 8 titled "Relevant tags" against a "Tags:" output label. Two names for one field.
- "Title" never requested in the instructions at all. This was the largest single missing field.
- "Provide a brief explanation" without naming the target field, which invited one merged block
  instead of four labelled ones.
- "regarding the future of AI" on every topic, including M&A Updates and Geopolitical Hotspots.

The replacement uses unnumbered sections keyed to the exact field labels, one output block, and
an explicit instruction against numbering, markdown, and renaming.

Measured A/B on the same 12 articles with `bedrock-kimi-k2.5`: the old prompt produced 10 clean
and 2 drifted, and both drifts were the exact failure modes dominating the production logs. The
new prompt produced 12 clean, 0 drifted.

Written with `PromptManager.save_version` (v1.0.3 → v1.0.4) on bugfixing, wileytest and wiley.
All three report template hash `ec7112190aee`. `get_template_hash` feeds the analysis cache key,
so analyses cached under the old prompt invalidate themselves.

`3f37ef27` then fixed the hardcoded default. `8712c41c` had rewritten
`data/prompts/content_analysis/current.json`, which is what existing tenants run, but
`PromptTemplates.DEFAULT_TEMPLATES` still carried every defect that rewrite removed.
`initialize_defaults()` only seeds when no stored version exists, so this changes nothing for an
existing tenant. It matters for a **newly cloned** one, which would otherwise start life with the
exact prompt that was causing analyses to be discarded — the bug reappearing silently, months
later, on a fresh deployment.

### Relevance gate: the CE tier was one flag away from an outage — `128d037a`, `540584d4`
`RELEVANCE_USE_CE_TIER` is off by default, and that default was the only thing preventing a
serious outage.

Measured against a 49-item hand-labelled gold set on wileytest, 20 genuinely relevant and 29 name
collisions:

| | min | median | max |
|---|---|---|---|
| relevant | 0.000018 | 0.0029 | 0.80 |
| collisions | 0.000016 | 0.000018 | 0.0049 |

The shipped `CE_LOW=0.10` sits above 90% of the *relevant* population. Turning the flag on would
have "confidently rejected" 18 of the 20 relevant articles, with no LLM review at all.

There is no honest reject threshold here. The widest cut that loses no positive is 0.000018, and
that is the lowest positive. A coincidence, not a margin.

So the tier is accept-only now. The risk is asymmetric: a wrong confident accept costs one
enrichment call, while a wrong confident reject drops the article for good. That is the same
failure mode that made news disappear from the observer agents. `CE_HIGH` dropped from 0.90 to
0.05, an order of magnitude above the worst collision — 0.0049, "Sage Group (OTCMKTS:SGPYY)", the
accounting software firm, not SAGE Publishing. On accept, the hybrid score is raised to the
threshold rather than overwritten with the CE value, whose scale is not comparable to the
embedding and classifier scale.

`540584d4` then corrected its own predecessor's measurement. `128d037a` justified the tier with
"AUC 0.907, better than any reworded query". That number scored **titles only**, while
`_compute_cross_encoder_score` builds `f"{title}. {summary}"`. Four of its 20 positives were
hand-written titles rather than real rows.

Re-measured on real articles, with real summaries, in the production document form:

- **theme topics, AUC 0.885** — 199 relevant, 114 not, weak-labelled from the pipeline's own
  confident extremes
- **brand topics, AUC 0.478** — 9 relevant, 86 not, hand-labelled. That is a coin toss.

Rewording the query does not rescue the brand case: bare entity 0.298, "news about X" 0.425,
question form 0.402, "X the company" 0.609, raw topic 0.478. The reason is that brand topics need
entity disambiguation — SAGE Publishing, Sage Group plc, sage the herb, and sage-agent-sdk on
PyPI. That is a named-entity problem, and a semantic reranker rates all four alike.

So the tier is theme-topics-only now. The flag still defaults off. This makes it safe to turn on;
it does not turn it on.

One thing `540584d4` flagged and left open. The gate uses its own brand predicate, because the
existing `is_brand_topic` only matches "Brand Monitoring X" and misses the live "X - Brand Watch"
topics (78 articles, most recent 2026-07-27). The narrower predicate was left alone rather than
silently changing which topics the classifier-confidence guard covers.

### Propagation (measured 2026-08-02)
`article_analyzer.py`, `prompt_templates.py` and `hybrid_relevance_service.py` are identical on
wiley and wileytest.

## 2026-07-23 — prod tenants under version control + INCIDENT (secret leak / file deletion)

### Goal
Get a restorable copy of the prod tenants into git. wileytest IS prod (despite the name);
wbm is prod. bugfixing is dev/canonical.

### What was done
- **wbm** — was not a git repo at all; `git init` (local, branch `master`, no remote). Hardened
  its `.gitignore` first; verified no secrets tracked.
- **wileytest** — pushed a **clean restore-point snapshot** to a dedicated private repo
  `AuNooAI/wileytest-prod` (branch `main`). Method: build a single orphan commit from the
  working tree in a THROWAWAY index (`GIT_INDEX_FILE=$(mktemp)` + `git add -A` + `commit-tree`),
  strip `.github/workflows/*` (so a `repo`-scoped token suffices, no `workflow` scope), and
  push that commit ref directly. This never switches branches on the live checkout and never
  drags git history — so the snapshot is ~43 MB, not the 980 MB (wileytest) / 19 GB (bugfixing)
  of legacy chromadb/sqlite blobs still in both repos' shared monolith history.

### Why the naive approaches don't work (for future reference)
- Pushing a branch (`training:main`) drags full history = ~980 MB of legacy `chromadb/chroma.sqlite3`
  (73 MB) + `fnaapp.db` (52–66 MB) blobs. `.gitignore` excludes these in the *working tree* but
  NOT in history. Only a history-free orphan snapshot (or a `filter-repo` purge) avoids it.
- Prod tenants are **deploy-copy targets**: files are rsync'd/copied in and never committed, so
  the working tree has UNTRACKED `.py` (19 on wileytest), `.env` backups, and a legacy `chromadb/`
  dir that git doesn't track. Dev (bugfixing) commits everything → 0 untracked app files.

### INCIDENT (my error) + recovery
While building the snapshot on the LIVE checkout with `git checkout --orphan … && git add -A &&
git checkout training`, two things went wrong:
1. **Deleted ~18 untracked deploy-copied files from prod's disk** — the branch-switch back to
   `training` removed files that `git add -A` had tracked in the orphan branch but `training`
   didn't. Prod stayed up (running from memory) but was one restart from breaking. **Recovered**
   by restoring the working tree from the snapshot commit (`git checkout <snap> -- .`).
2. **Pushed 47 live secrets** — `git add -A` swept in untracked `.env.pre_bedrock_*` (real keys:
   OPENAI/ANTHROPIC/AWS_BEDROCK/DB_PASSWORD/RESEND/FLASK_SECRET/…) that wileytest's `.gitignore`
   didn't cover, into a snapshot pushed to the (private) `wileytest-prod`. **Contained** by
   deleting+recreating the repo; owner rotated the exposed keys.

### Fix — hardened `wileytest/.gitignore`
Added broad exclusions so `git add -A` can never sweep these again: `.env.*` (keep
`*.example`/`*.template`), `**/.env.hub`, `*.pre_bedrock*`, `*.key`, `*.pem`, `bedrock.key`,
`opointkeys`, `*.bak_*`, `config.json.bak*`. Verified with `git check-ignore` (patterns hit) +
a mandatory pre-push secret scan on the built commit tree (`git ls-tree | grep -i secrets` →
must be empty, else abort). The safe orphan-snapshot method now bakes this scan in as a gate.

### Lessons
- NEVER `git checkout --orphan` / branch-switch on a live deploy-copy checkout (untracked files
  get deleted). Build snapshots via a temp `GIT_INDEX_FILE` + `commit-tree` instead.
- NEVER `git add -A` on prod without a hardened `.gitignore` AND a secret scan of the resulting
  tree BEFORE pushing.

## 2026-07-23 — back-port prod-only fixes into canonical (drift audit: PROD ahead)

A drift audit of bugfixing (canonical) vs wileytest (active prod) found several fixes that
were made in place on prod's `training` branch and never flowed back to canonical — so any
tenant cloned from canonical would be stale. Back-ported the three that matter:

- **`automated_ingest_service.py`** — unknown-topic guard (prod commit `6229dc9f`). If an
  article's topic isn't in the loaded config, mark it `skipped_unknown_topic` and make ZERO
  LLM calls, instead of never marking it done and re-selecting it forever (~5 LLM calls/pass).
  This loop is what drained the OpenAI account on 2026-06-18. Canonical (and clones) lacked it.
- **`geopolitical_service.py`** — bulk `GROUP BY … FILTER` aggregation (prod `9ee94a21` +
  `7d24219d`) replacing a per-hotspot loop that ran a full-table ILIKE seq-scan per unlinked
  hotspot (~6.7k scans/run); also drops the now-dead `sentiment_to_score` helper.
- **`geopolitical_hotspots_monitor.py`** — wrap `update_country_stats` / `update_hotspot_trends`
  in `asyncio.to_thread` on the `run_schedule` path (prod extended `9203117b`) so the scheduled
  stats run doesn't block the event loop.

Each was a confined change (verified: only diffs were the intended fix, no unrelated prod-local
content), so canonical adopted prod's version of the file wholesale. py_compile clean.

NOT touched: `vector_store_pgvector.py` (intentional per-tenant DeBERTa-768d vs OpenAI-1536d
split — schema-bound), `training_routes.py` (ce_score tied to the `ce_001` migration prod lacks),
`server_run.py`/CORS, `database_query_facade.py` (prod-local xpoz `social_meta`), the xpoz
collector registration, and the Threat-Intelligence module — all intentional divergence.

## 2026-07-23 — signal reports: inline account/post links + complete online report

### Ask
The alert email/report should link accounts and posts inline (click an @handle → the
profile, a post → the post), and the online "View full report" page was incomplete —
it showed only the narrative, not the matched source posts the email lists.

### Fix — `app/services/email_service.py` + `app/routes/vector_routes.py`
New shared helpers in `email_service.py`:
- `social_ref(uri)` → `{short, profile, post, platform}` parsed from a bsky/x/reddit post URL.
- `linkify_handles_md(md, matches)` → turns plain `@handle` in the report markdown into
  `[@handle](profile_url)` using the matched posts' URLs (deterministic — no LLM/hallucination).
- `render_matched_sources_html(matches)` → clean linked source cards (account link · platform ·
  view-post link · summary · threat/confidence).

Wired into both channels so they match:
- **Email** (`send_signal_alert_email`): linkify the narrative before render; the old
  raw-URL "Matched Articles" list replaced by `render_matched_sources_html` ("Matched posts").
- **Online report** (`/signal-reports/{id}/download`): now also SELECTs `alerts_data`, linkifies
  the narrative, and appends a **Sources** section (same cards) — so the loadable report is as
  complete as the email. Render-time, so already-saved reports gain it on next open.

Handles remain shortened (`@name`) as anchor text; no bare URLs in prose (strip still runs).

### Verification
Online report 647: 25 `@handle→profile` links in the narrative, Sources section with all 7
matched posts + "view post" links, 0 raw bare URLs, heading renders. Email sent through the new
path. Applied + py_compile + restart on all 4 tenants.

## 2026-07-23 — reports: render leading-space markdown headers (raw "# Title" in loadable report)

### Symptom
A signal report opened via the emailed "View full report" link (and the email's own
report section) showed a literal `# Negative Social Narrative Summary: Wiley…` instead of
a rendered heading, while `## Sub-headings` rendered fine.

### Root cause
`markdown_to_html` (shared by the email report section and the `/signal-reports/{id}/download`
HTML view) uses python-markdown, which renders an ATX header indented by **1–3 spaces** as a
paragraph, not a heading. The LLM emitted the top heading as `" # Title"` (one leading space),
so only that first heading failed.

### Fix — `app/services/email_service.py`
De-indent ATX headers before rendering: `re.sub(r'(?m)^[ \t]{1,3}(#{1,6}\s)', r'\1', text)`
in `markdown_to_html`, before `_md.markdown(...)`. 4-space indents (code blocks) are preserved.
Being a render-time fix, it also repairs already-saved reports on next open. The PDF renderer
(`report_pdf.py`) already `strip()`s each line before matching headers, so it was unaffected.

### Verification
Report 644 HTML download: raw `# Negative` paragraphs 0, summary now `<h1>…</h1>`; unit test
` # Foo`/`  # Foo`/`   # Foo` → H1, `    # x` (4-sp) → P. Restart on all 4 tenants.

## 2026-07-23 — signal reports: shorten social handles so email clients don't autolink them

### Symptom
In the alert email, account references rendered inconsistently — some as active
(broken) links, some as plain text — "especially for accounts". e.g.
`@rmounce.mastodon.social.ap.brid.gy` and `@x.bsky.social` became clickable while
`@jenom0urz` stayed text.

### Root cause
Our HTML has no `<a>` for these — the report body is link-free after `_strip_source_links`.
But email clients (Gmail etc.) **auto-linkify any bare hostname**, and ATProto/fediverse
handles carry a domain suffix (`.bsky.social`, `.eurosky.social`, `.mastodon.social.ap.brid.gy`),
so those get turned into links client-side while plain handles don't.

### Fix — `app/routes/vector_routes.py`
`_strip_source_links` now shortens social handles to a bare `@name` (drops the platform
domain suffix) for the common PDS/bridge suffixes (`bsky.social`, `eurosky.social`, `brid.gy`),
so nothing in the body looks like a hostname. `_NO_SOURCE_LINKS` directive reinforced to ask the
model for short `@handle` only. News domains (`reuters.com`, `example.org`) are untouched.
Applies to email + saved/loadable report (one strip feeds both). All 4 tenants, restart.

## 2026-07-23 — observer: only alert on social the product actually shows (on-brand ≥0.4, non-FP)

### Symptom
An observer alert (wbm instr 10) listed social posts that are **not visible in the Brand
Watcher Social tab** — e.g. two Indonesian journal-piracy "jasa unlock" X posts and a Reddit
archaeology post. The client sees an alert referencing posts they can't find/verify in the UI.

### Root cause
The Social tab gates on `topic_alignment_score >= 0.4` ("on-brand only", the platform-wide
brand-relevance standard) and hides analyst-flagged false positives. The prior social-inclusion
fix (`f2f962fb`) added social to the observer pool but applied **neither gate**, so the observer
alerted on off-brand noise (align 0.05/0.10) and on a post already flagged `false_positive`.
Measured on wbm/Wiley (14d): 444 sub-0.4 noise + 3 FP were eligible for alerting but hidden in
the tab; only 172 posts were both on-brand and shown.

### Fix — `app/routes/vector_routes.py` (all 4 observer retrieval queries)
Gate the **social branch only** (news `category IS NOT NULL` untouched) to match the tab:
`(social_meta present)` → `(social_meta present AND topic_alignment_score >= 0.4 AND NOT EXISTS
(false_positive review for this uri))`. Applied to all four observer queries (interactive,
background, entity, dedup). `bw_finding_reviews` exists on all four tenants.

### Verification
wbm observer social pool for *Brand Monitoring Wiley* (14d) now **172** (was 619) — exactly the
tab's on-brand, non-FP set. The three on-brand Bluesky posts (0.85, shown in Social) are kept;
the two X noise posts (0.05/0.10) and the FP-flagged Reddit post are dropped. py_compile clean +
restart on all four tenants.

## 2026-07-22 — signal reports: no raw source/post links (email + loadable report)

### Ask
Client-facing signal reports should not carry the raw source-post links (bsky/reddit/etc.)
— not in the emailed body and not in the downloadable/saved ("loadable") report.

### Fix — `app/routes/vector_routes.py`
Two layers, so links are suppressed at generation and stripped if any leak:
1. **Prompt directive.** `_apply_recommendations_pref` (the report-prompt finalizer both
   runners call) now also appends `_NO_SOURCE_LINKS`: *"Do NOT include any URLs, hyperlinks
   … refer to sources by @handle and platform only, never by URL"* — overrides a per-instruction
   prompt that says "link the URI" (e.g. wbm instr 10).
2. **Post-generation strip.** New `_strip_source_links(md)` removes `[text](url)`→`text`, bare
   URLs/autolinks, and the now-empty `- **URI:**`-style label lines. Applied to `report_content`
   before it is saved AND emailed, so both channels are covered from one value.
   - bugfixing/wiley/wileytest (retry variant): strip inside `_generate_report_with_retry`'s
     return; also removed the `article_uri` line from `_build_fallback_report`.
   - wbm (older, direct variant): strip at both direct `generate_response` report sites.
Our own "view full report" download link and podcast link are added during email assembly
(not part of `report_content`), so they are unaffected.

### Verification
Ran `_strip_source_links` on the real saved report 642: 5 bsky/reddit URLs → 0, empty URI
label lines → 0, Quote/Significance prose intact (5703→5338 chars). Directive append confirmed.
py_compile clean + restart on all 4 tenants. Note: already-sent report 642 keeps its links
(history); the next scheduled run generates clean.

## 2026-07-22 — observer agents: honor the instruction's configured model

### Symptom
Observer agents ran on `gpt-5.4-mini` (→ Bedrock Haiku via the yaml alias) regardless of
the model saved on the instruction. wbm's *Negative Social Sentinel — Wiley* has
`config.model = bedrock-kimi-k2-5` but every scheduled run used Haiku — pricier, and not what
the instruction was configured with.

### Root cause
`_run_signal_instruction_internal` (the scheduler's entry point) took `model: str =
"gpt-5.4-mini"` and never read `config['model']`. The scheduler
(`observer_agent_monitor.run_agent`) calls it without a `model` arg, so every scheduled run
silently used the hardcoded default.

### Fix — `app/routes/vector_routes.py`
Default the param to `None` and resolve from config:
`model: str = "gpt-5.4-mini"` → `model: Optional[str] = None`, then after loading config:
`model = model or config.get('model') or "gpt-5.4-mini"`.
Precedence: explicit caller arg > instruction's `config.model` > historic default. The
interactive runner (`_run_signals_background`) still passes `req.model` explicitly, so its
user-selected model continues to win — only the scheduler path (which passed nothing) changes.

### Verification
Stubbed `LiteLLMModel.get_instance` to capture the requested model without an LLM call: the
scheduler path (`instruction_id=10`, no model arg) now requests **bedrock-kimi-k2-5** (was
gpt-5.4-mini). Applied + py_compile clean + restart on all 4 tenants.

## 2026-07-22 — observer agents: stop excluding social posts from alerting

### Symptom
No alert emails from the wbm Observer (Explore tab). The one active agent (id 10,
*Negative Social Sentinel — Wiley*, `send_email=true → wiley@aunoo.ai`) ran daily and
succeeded but created 0 alerts since 07-13. Emails only fire when an agent creates alerts
meeting threshold (`vector_routes.py` `if config.get('send_email') and instruction_alerts
and meets_threshold`), so 0 alerts = 0 email — working as designed, but with an empty pool.

### Root cause
The observer article-retrieval queries require `category IS NOT NULL AND sentiment IS NOT
NULL`. On wbm, social posts never get a `category` (SocialEval sets `sentiment` only —
0 of 5,486 social rows have a category). So all 662 Wiley social posts in the 14-day window
were filtered out; the *Social* Sentinel was scanning only ~10 categorized news articles/day
and finding nothing negative. Long-standing (clause dates to `b4a604f6`, 2026-02), not caused
by today's collection change — re-enabling ig/tiktok just enlarged the pool being discarded.

### Fix — `app/routes/vector_routes.py` (all 4 observer retrieval queries)
Relax the requirement so social posts (which legitimately have no category) are included,
still requiring sentiment:
`AND category IS NOT NULL AND sentiment IS NOT NULL`
→ `AND sentiment IS NOT NULL AND (category IS NOT NULL OR (social_meta IS NOT NULL AND
social_meta::text <> 'null'))`
Applied to all four observer queries: interactive `run_signal_instructions`, background
`_run_signals_background`, and the entity + dedup queries in `_run_signal_instruction_internal`.
The four NON-observer queries (trend/summary/date-range stats) were left unchanged. Noise is
handled downstream as before — the LLM sentinel + threshold sift entity-collision posts
(e.g. *Maya Wiley* the politician, journal-piracy chatter).

### Verification
wbm observer pool for *Brand Monitoring Wiley* (14-day window): **10 → 672** articles, incl.
**28 Negative** candidate posts previously unseen. Applied + `py_compile` clean + service
restart on bugfixing (canonical), wbm, wiley, wileytest. `social_meta` confirmed jsonb on all
four (clause is safe). Not committed inside wiley/wileytest/wbm repos (deploy-copy model; wbm
is not a git repo). Next scheduled wbm run 2026-07-23 08:00 will scan social and email if
anything clears threshold.

## 2026-07-22 — xpoz social collection: ig/tiktok re-enable, reliability fixes, recall widening

### Summary
Instagram and TikTok social collection had silently stopped on wbm (~07-15/16); re-enabling
them exposed two collector bugs that discarded whole keyword results, plus a multi-word
query recall problem. Fixed all three in `app/collectors/xpoz_collector.py`, committed to the
canonical repo, and propagated to the other tenants. Also stood up cost monitoring and tuned
an editorial-failure monitor.

### Code — `app/collectors/xpoz_collector.py` (commit `34d8ddfd`, branch `fix/collection-reliability`)
1. **Per-platform timeout cap.** xpoz queries platforms sequentially inside one
   `keyword_monitor` call wrapped in `SEARCH_TIMEOUT_SECONDS=120`. Going from 2→4 platforms
   let a single hung platform (xpoz ig/tiktok `search_posts` can stall ~100s) push the whole
   keyword over 120s, so `asyncio.wait_for` discarded **every** platform's results — including
   posts already fetched. Fix: each `search_posts` runs via a `ThreadPoolExecutor` with
   `.result(timeout=_platform_timeout())`; a slow platform is skipped, the others' posts kept.
   - Env: `XPOZ_PLATFORM_TIMEOUT` (default `25` → worst case 4×25=100s, under the 120s wrapper).
2. **Non-blocking `client.close()`.** `close()` joins in-flight HTTP, so a still-hung platform
   thread blocked `_search_sync`'s return past 120s and the result was discarded even after the
   platform loop finished (~60s). This was the decisive bug. Fix: close in a daemon thread we
   never join (`_safe_close`). Hung platform threads are abandoned as daemons (harmless at this
   volume).
3. **Widened multi-word query recall.** Old gate required EVERY query token (AND), dropping
   ~every result for ambiguous multi-word product queries ("SAGE Publishing", "Pearson VUE").
   New gate requires only the brand **root** token; product tokens optional, leaning on the
   downstream `topic_alignment_score >= 0.4` filter to suppress the extra noise. Added
   plural/stem tolerance.
   - Env: `XPOZ_TERM_MATCH` = `root` (default, widest) / `majority` / `all` (original strict).

Note: the collection term-gate is a coarse brand-lane pre-filter; the real legit/noise
separator is the downstream 0.4 relevance filter (verified: real Elsevier/Google-lawsuit posts
score ~0.95; entity-collision noise scores <0.4 and is hidden).

### Config — wbm (`keyword_groups.social_platforms`)
Re-enabled ig+tiktok on all four `* - Social` groups:
`["twitter","reddit"]` → `["twitter","reddit","instagram","tiktok"]` (Wiley, Elsevier, SAGE,
Pearsons). Collector re-reads per-group platforms each cycle — no restart needed for this.

### Propagation
Collector fix committed in **bugfixing** (canonical). Copied file + service restart + venv
import verified on **wbm, wiley, wileytest** (all three had the file at the identical base, so
the copy = base + fixes, no divergence). Not committed inside wiley/wileytest repos (deploy-copy
model). Term-gate default is now `root` on all tenants; revert per-tenant with
`XPOZ_TERM_MATCH=all` (strict) or `=majority` (soft) in the tenant `.env` + restart.

### Verification
All four wbm groups confirmed landing ig/tiktok after the fix (Wiley +9ig/+2tiktok, Elsevier
+4, SAGE +5, Pearsons +21); zero `xpoz search timed out after 120s` in the SAGE/Pearsons run.

### Ops — wileytest social spend monitor (cost watch for `root` default)
`root` raises social volume → more Haiku social eval (`SOCIAL_EVAL_MODEL=bedrock-claude-haiku`)
+ nova-lite relevance. One-off report scheduled for the first full root day.
- Script: `/home/orochford/bin/wileytest_social_spend_report.sh 2026-07-23`
- Cron (root): `45 23 23 7 *` — emails oliver.rochford@gmail.com via Resend + logs
  `/var/log/aunoo-social-spend.log`. Compares 07-23 social volume + Haiku/nova/total spend vs
  prior-7d avg. Baseline pre-root: social ~11–44 posts/day, whole-tenant LLM ~$17–31/day.
- Revert if it spikes: `XPOZ_TERM_MATCH=all` in `wileytest/.env` + restart.

### Ops — editorial-failure monitor (saas `editorial_briefing_runs`)
Triaged an alert (run 2392, tenant 22 "Alvarovalera01"): the `fabricated_claim` verdict was a
**correct** rejection (draft over-specified an ambiguous source "two countries" into a
"US–Iran ceasefire") on a thin-signal briefing (1 correspondent). Not a bug — the LLM reviewer
worked as designed; do NOT loosen it.
Extended the regression monitor (v2→v3) to stop paging on this expected class. Added to the
WHERE clause: `AND NOT (error ILIKE '%fabricated_claim%' AND coalesce(correspondents_polled,0) <= 1)`.
Narrowly scoped — `ai_tells_above_threshold`, rich-signal (`polled>=2`) fabricated_claim, and all
other error classes still page. Session-scoped monitor (not durable).
