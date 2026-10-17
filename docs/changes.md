## 2026-10-17 (late afternoon) — Wiley Q4 bundle: links lost in the duplicate merge, put back with provenance; a build fails on a silent loss

### Goal
A question from the user ("did we find zero counter-evidence?") led to the finding that the
duplicate-merge step of 16 Oct had dropped scenario links: it carried wording, dates and
sources to the kept row and not the merged rows' ratings, and the link judge then rebuilt the
survivors' links from nothing. The audit of all 321 rows for the quarter found 74 lost links
(65 confirming, 9 countering) on 35 surviving rows. The deck's counts matched its lists all
week because both read the same thinned record.

### Link provenance (`wiley_event_extraction.py`)
Every entry in `scenario_relevance` is now one of: an active link (`judged`, `decided_by`,
`decided_at`, `rationale`), a candidate (`candidate`, `inherited_from`, `inherited_at`), a
rejected link (`rejected`, `rejected_by`, `rejected_at`, `rejected_reason`, kept as the record),
or a hand-set link (`locked`). `_normalize_scenario_relevance` and therefore every count ignore
candidates and rejections. `inherit_links` runs in the merge: the merged rows' active links go
onto the survivor as candidates (a link the survivor already holds records the twin in
`also_from`; a rejected link is not re-litigated). `links_to_decide` gives the link judge, per
row, this run's proposals, the row's candidates and the links a previous run kept; the judge
prompt (1.1.0) carries each link's `source` and returns a decision with a direction for every
link. `resolve_links` writes the keep or the rejection with the judge's reason, leaves a
candidate undecided when the judge gave no verdict, records a candidate on a hand-locked
scenario as rejected by the lock, and allows one active link per scenario (the lower-probability
one of two kept directions is recorded as superseded). `judge_event_links_for_bundle(row_ids=…)`
re-judges chosen rows only.

### Build gate (`audit_merged_links`, `wiley_bundle_supervisor.py`)
After the events stage, every active link on a merged-away row must be on its final survivor as
an active link with the same scenario and direction, or as a rejection with a reason. Otherwise
the build raises `BundleRequiresReviewError` with one finding per gap ("link never carried to
the survivor", "undecided candidate on the survivor", "direction changed on the survivor with no
recorded decision", "survivor row missing" when ratings would be lost). A locked re-export is
gated the same way.

### Review checks (`wiley_narrative_review.py`)
An actor with two events in one sentence ("Anthropic's Claude filing a false tip … in parallel
with Anthropic's OpenEvidence partnership") had the label near one mention held against the
other event. A label now counts only around the mention whose stretch of text up to the next mention
carries the event's own subject words. The event-count check reads "zero counters" and "no
counter-evidence". A repetition check flags a two-word phrase repeated within four words (a
repair twice produced "previously requiring tasks previously requiring"). `review_and_repair`
takes an `accepted` snapshot of the last sent bundle's text: a judge-only error on a segment
identical to it is advisory, because the judge is not deterministic and its fresh errors on
reviewed text sent the repair agent over sentences it then garbled. The What's Changed list
ranks events the letter names first and shows them in the letter's order.

### Repair on wileytest (data)
Links backed up to the session scratchpad (`links_backup_before_repair.json`). Inheritance
applied to 41 survivors (54 candidates), link judge run on those rows (111 s; per topic it
rejected 0, 13, 21, 13, 2 and 6 links with reasons), audit after: zero gaps. Of the nine
counter ratings on merged rows: four stand on their survivors (OpenAI's 722 papers against Open
Infrastructure Transformation; the dropped NIH veto order against Political Centralization,
twice; the train-American-scientists initiative against Collapse), four were rejected by the
judge with a reason (Meta's weights, the AstraZeneca–Summit deal, AbbVie's Juvmo approval, the
veto withdrawal against Collapse), one was superseded by the judge's confirming reading of the
same event (Biocon's Perjeta settlement). Ten scenarios changed count or status; see
`count_changes.json`, with each link marked restored or fresh. Three status changes rest mainly
on fresh ratings the judge made when it re-read those rows: NISQ Limitations and Proprietary
Inertia to crowd_wrong, Error Correction Unlocks Practical Applications to holding.

### Verification
`tests/test_wiley_event_links.py`: 10 tests on the pure functions (inheritance with a conflict
and a twin, decisions for proposals, candidates and previous links, keep/reject/unresolved,
superseded directions, lock rejection, no re-litigation of a rejection, repeated runs stable,
audit naming each gap kind, counts ignoring rejections and candidates); green on the bugfixing
venv against the wileytest tree and against bugfixing. Live audit on wileytest: 74 gaps before,
0 after. The first build after the repair stopped at the gate on two undecided candidates
(correct behaviour; resolved, then clean). Final build 16:54: reviewer approved_with_warnings with zero errors, narrative review clear with no repairs in its last pass, 26 slides differ from the 12:16 deck in text (counts, statuses, evidence lists, repaired sentences, the What's Changed order), HTML 66 confirming and 11 countering records with no gaps.

### Propagation
Code on bugfixing (canonical), wileytest and wiley by patch script; commit the commit titled "Wiley bundle: links lost in the duplicate merge, put back with provenance". Data repair on
wileytest only. Restart queued after the commit.

### Lessons
- NEVER let a step that rewrites a row drop fields it does not understand. The merge wrote
  wording and left the links behind; nothing downstream could tell.
- A count that matches its list proves nothing about what the list lost upstream. Audit the
  rows that leave the deck, not only the rows on it.
- "Zero counter-evidence" is a finding to check, not a result to report. The pipeline still
  does not search for evidence against a scenario; this repair restores what was found.

## 2026-10-17 (afternoon) — Wiley Q4 bundle: a fully locked bundle is a plain re-export

Once every bundle narrative key and every topic's narrative keys are locked, a build no longer
asks the planner or runs a writer: `_bundle_fully_locked` in `wiley_bundle_supervisor.py` sets an
empty plan, the humanizer and the narrative review have nothing to do, and the reviewed text goes
to the reviewer and the render. A build-only run on wileytest went from ten to twenty minutes to
95 seconds, with the deck text-identical to the sent one. The trade: a locked bundle does not
notice evidence edits on its own, so the runbook rule after a record change stays unlock, rerun
the review, lock.

## 2026-10-17 (early afternoon, twelfth review) — Wiley Q4 bundle: matrix cells on their rows; a parent lock covers its children everywhere

The twelfth review found the middle-row cells of the HTML matrix had no grid placement, so the low
cells sat beside the MIDDLE label. Fixed in the CSS (`#cell-mid-*` on row 3, `#cell-lo-*` on row 4)
and the build script now reads the grid rules back from the generated file.

The rebuild for that fix exposed a worse thing. The planner chose to regenerate the executive
letter on a plain rebuild, the lock on `exec_summary` was not honoured because the exec stage
looked only for `exec_summary.<field>`, and the in-pipeline narrative review then repaired the
fresh letter twice and rewrote six tension displays and a body. `_is_locked` and
`_exec_summary_locks` in `wiley_bundle_supervisor.py` now treat a locked parent as covering its
children at every lock check (overview, letter, expert commentary, the exec stage's restore). The
reviewed letter, lede, displays and body were restored by hand from the 10:51 files, and the sent
deck is text-identical to that one.

## 2026-10-17 (midday, eleventh review) — Wiley Q4 bundle: the HTML exports every judged record, three consensus bands, date bases on every row

The eleventh review read the HTML and the docx against the deck. The prose matched across the three
files; the HTML did not match its own totals. Four scenario ledgers listed six evidence rows
against declared totals of ten, ten, nine and eight (thirteen confirming records missing), the
calibration matrix read every basis under 60% as low consensus and so put a 58% scenario in the
outlier row, two records had no date basis, and inferred dates were shown bare.

- `forecast_bundle_html.py`: every confirming and countering record is exported (the `[:6]` cap is
  gone), so a drawer's "Confirming (10)" lists ten and the print ledgers expand the full lists. The
  matrix has three rows as the methodology defines them: high consensus at 60% or more, a middle
  band from 41% to 59% ("below the high-consensus threshold", leaning or undecided), low at 40% or
  less; only the low row carries the outlier reading, and an unknown basis goes to the middle row.
  Event lists label dates "reported" (article basis), "inferred", or "date basis unknown".
- `_sync_events_into_payload` and `_fmt_event_line`: "What's Changed" rows and evidence-slide lines
  say "inferred YYYY-MM-DD" for inferred dates, as the notes already did.
- The humanizer rewrote a locked, reviewed letter on a plain rebuild (an Oxford comma in the
  reviewer's sentence). `humanize_bundle_payload` matched locked paths exactly, so a lock on
  `exec_summary` did not cover `exec_summary.letter`; it now covers children and list items. The
  in-pipeline narrative review runs whenever the humanizer changed a field, not only after a writer
  stage (`wiley_bundle_supervisor.py`).
- wileytest records: 2248 (Sun Pharma) and 2250 (AI2 OlmoCore 3) had no date basis; the articles
  do not date the actions, so both are "reported" on the article date.

## 2026-10-17 (morning, tenth review) — Wiley Q4 bundle: where a development takes place, and whether it was announced before the window

One finding on slide 3. The letter's international sentence listed "WashU Medicine researchers'
prize-winning tool" under "non-U.S. research infrastructure". Washington University School of
Medicine is in St. Louis, and the university announced the award on 14 September 2026, a week
before the forecast; the 1 October article the extractor dated it by was later coverage. The
window judge could not see that, because the article never says when the award was made.

- `geography_findings` (`wiley_narrative_review.py`): a sentence framed as international ("Internationally",
  "non-U.S.", "outside the United States", "overseas", "in Europe") is read development by
  development. Each named event (actor words plus one of its own subject words in the sentence,
  so "IonQ's Cambridge centre" is one IonQ row, not all of them) goes to the new
  `wiley_geography_agent`, which says where the development takes place: `us`, `non_us`, `mixed`
  or `unknown`. The place is the development's, not the head office's, so IonQ's Cambridge centre
  and Google's access for 200 European researchers pass and the WashU prize is an error. Verdicts
  are cached per event for the run. "geography" is a preflight-owned category.
- `judge_event_precedence_for_bundle` (`wiley_event_extraction.py`, after the window judge): for
  each deck event, a Bright Data web search on the actor and the subject's distinctive words, then
  the new `wiley_precedence_judge_agent` reads the results and says whether the same action was
  announced before the window, citing the result and its date. A verdict is verified only when
  the cited result is one of the results the code sent, carries a date before the window that the
  code can read in its own title, snippet or URL, and names the actor, two subject words and the
  action word; the rest are unverified. The judge applies nothing on its own: both lists go into
  the synthesis payload under `precedence_review` for an analyst, and `WILEY_PRECEDENCE_APPLY=1`
  moves the verified rows to historical, dated by the announcement, out of the deck, with the
  "What's Changed" list re-synced. The
  search budget is the host's shared Bright Data allowance, so a run checks at most
  `WILEY_PRECEDENCE_SEARCHES` events (default 60): the ones the narrative names first, then the
  ones on an evidence slide, then the rest by confidence. `WILEY_SKIP_PRECEDENCE=1` skips the
  stage. The first dry run (17 Oct 2026, 60 events, 18 minutes, 20 searches without results) called two rows verified and both were precursors, not the action (CERN's 130 clusters in April for an October expansion to 139; an order being drafted on 20 September for its abandonment on the 23rd), and nine unverified, two of which were worth a hand edit: the 20,000-device Coathanger compromise cited in a 7 October Dutch warning was disclosed in 2024, so the record now says the warning is the development and the compromise its context, and CERN's expansion is "reported 15 October" because the article does not date it. So the judge applies nothing on its own: its proposals are stored in the synthesis payload under `precedence_review`, the verified tier also requires the action word, and `WILEY_PRECEDENCE_APPLY=1` is the only way it moves a row.
- `_sync_events_into_payload`: a "What's Changed" row whose date is the article's says "reported
  2026-10-02", as the evidence notes do; the HTML's ledger and event-explorer lists carry the same
  label (`forecast_bundle_html.py`).
- Prompts: judge 1.5.0 (geography), repair 1.5.0 (a U.S. development leaves the international
  list), exec summary 3.5.0 and cross-topic 1.4.0 (the place is the development's).
- wileytest records: 2608 (WashU prize) dated 2026-09-14, historical, out of the deck, hand note.
  Letter sentence replaced by hand with the reviewer's wording; the narrative review then ran
  clean over the whole bundle.

## 2026-10-16 (night, ninth review) — Wiley Q4 bundle: counts from the judged list, date provenance in the records

Two findings, both in the evidence records. A topic synthesis said "9 confirming events" for a
scenario whose evidence slide listed eight: the count had gone stale when a row left the ledger
and no deterministic check counted events per scenario. And the record for NSF's $1.4 billion
said "withheld on 2 October" when the report describes an amount accumulated over the preceding
year; the date-type check had let it through because a same-day event's subject words matched
the sentence.

- `_event_count_findings` (`wiley_narrative_review.py`): "N confirming/countering events" in a
  sentence that names a scenario (full name or its first two or three words; the looser
  two-word match read "partnership … biosimilar" as a scenario name) must equal that scenario's
  ledger count; a sentence naming none passes when any scenario has the count.
- `_date_basis_findings` narrows same-day events by actor first (initials count, matched in
  the date's own clause), then by subject words. Day-first dates ("2 October") were invisible
  to every date check, because the shared `_DATE_WORDS` pattern is month-first only; the
  review module now reads them too, in the date check, the date-type check and the figure
  stripping.
- `_historical_findings`: a sentence that restates a row the window audit holds as
  historical (three shared distinctive words, the actor named, no context marker) is a
  `window` error; the ledger now carries each topic's historical rows.
- Evidence-slide notes carry each row's date type ("reported", "dated", "inferred") and stage
  beside its source.
- Window judge 1.0.3: a season is its last month; a precursor's date (a tip, the cuts an
  initiative responds to, an amount accumulated over a year) is not the event's date. Its
  second pass on the Q4 set still over-reached on two rows and was not applied; the NIH record
  was dated by hand from the ACLU article (summer terminations, before the window) and left as
  context, and the $810 million rescission package was recorded from the White House PDF of
  25 September as a proposal across 11 accounts with $27.7 million for AHRQ research, judged
  confirming with a rationale that keeps it distinct from GAO's 7 October finding.

## 2026-10-16 (late night) — Wiley Q4 bundle after the eighth review

The eighth review read a deck whose overview, themes, decision framework and letter had been
regenerated one minute before it was sent. The round-seven review had run and passed; then a
rebuild for a one-line body edit let the planner rerun the cross-topic and letter stages, and
nothing reviewed what they wrote. The findings were the writers' usual classes on fresh text:
a causal link from pharmaceutical patent pressure to a publisher's portfolio review, rates and
capacity ("incidents are outpacing validation partnerships: ten events versus five") read off
scenario counts, a February 2025 contract cancellation dated 25 September 2026, article dates
written as occurrence dates, and theme bodies of five sentences shrunk and cut on the slide.

**The pipeline reviews what it writes** (`wiley_bundle_supervisor.py`). A new stage after the
bundle payload is saved runs `review_and_repair` whenever any writer stage ran in that build,
before the reviewer and the render, and reloads the repaired text. `WILEY_SKIP_NARRATIVE_REVIEW=1`
turns it off for a run. The hand-run scripts lock the bundle and topic narrative keys after
the review, so a planner regeneration restores the reviewed text.

**Window membership** (`judge_event_window_for_bundle`, `wiley_window_judge_agent` 1.0.1). The
extractor dates an event by its article; an in-window article that revisits an earlier action
became a new event. The judge reads each included event with its source article's title, date
and summary and classifies it in-window, historical (with the occurrence date the text gives)
or unknown. A statement made in the window (disclosed, apologised, reported) is in the window
whatever it describes. A historical row with an occurrence that ends before the window is dated
by it, marked `historical` and taken out of the deck; one without such a date stays as a report
(`date_basis` article). Year-only dates ("in 2026") place nothing before the window. It runs after
the link judge in `run_event_extraction`. On the Q4 2026 set it found the NCES row (set by hand
to 11 February 2025 from the AP report), the OpenAI scrape of UN data (April to June) and the
second-term climate cuts; five of its first verdicts over-reached and were reverted by hand.

**Three more checks** (`wiley_narrative_review.py`): `_rate_findings` (outpacing, faster than,
keeping pace, scale gap, can no longer absorb, is accelerating; passes when the sentence says the
counts do not measure it), `_bridge_findings` (two topics' terms in one sentence with a causal
connector, not marked separate; topic terms are the words unique to one topic's name, scenarios
and actors), `_length_findings` (theme body three sentences or 380 characters, overview seven or
1,000, framework body five or 720). The themes, overview and framework slides show whole
sentences and carry the full text in the notes, the themes with each named topic's judged events
and sources.

Prompts: judge 1.4.0, repair 1.4.0, cross-topic 1.3.0, letter 3.4.0, window judge 1.0.1.

## 2026-10-16 (late) — Wiley Q4 bundle after the seventh review

The seventh review was a targeted handoff: a wrong company on the expert view, breaches
placed at review platforms the ledger has no incident at, a causal link the events do not
state, an equity investment filed under licensing, a count of nine filings that included a
lawsuit, a swapped comparison baseline, and tension bodies cut mid-clause with an ellipsis
on the synthesis slides. Each is now a check in code, mirrored in the judge, repair and
writer prompts, and the slide shows a complete sentence. Commit below, same hunks on
wileytest and wiley.

**Who did it, where, and what kind** (`wiley_narrative_review.py`). Five deterministic
checks were added to the preflight. Actor attribution: a clause that shares three
distinctive words with a ledger event, one of them rare, and names another actor but not the
event's, is an identity error ("OpenAI models submitting false tips to police" for
Anthropic's Claude). Actor names include initials (NSF, GAO) and three-letter acronyms;
words shared by three or more actors (Quantum) name none; the check runs per clause so a
list of nine filings beside Samsung's deal does not become Samsung's. Transfer: a security
word and a peer-review or editorial-platform phrase in one sentence, with no ledger event at
such a platform and no analogy or hypothesis marker before the security word. Causal: "is
forcing", "accelerating demand for", "is prompting" between developments, unhedged. Deal
type: a transaction label (licensing, investment, acquisition, approval, settlement…) that
introduces a named event within 120 characters, or follows it within 40, must cover the
event's own kind; a colon list stays one clause. Comparison baseline: "once reserved for X"
keeps the event's X by head noun. The type-count check now allows adjectives between the
number and the type ("nine generic/biosimilar submissions") and compound types ("submissions
and approvals"); the Too-early progress check matches a scenario by its first two
distinctive words ("private research capital" for Private Capital Drives AI Innovation
Leadership) and counts "emergence" as a progress word. Judge errors in these categories on
a sentence the preflight passed are advisory.

**Display sentences** (`wiley_bundle_supervisor.py`, `forecast_pptx_export.py`,
`wiley_display_agent.md`). A tension body longer than the synthesis panel shows is
rendered as `display`: one complete sentence of at most 170 characters that the briefing
writer supplies, or that the new display agent writes from the body. `display_ok` checks it
in code (length, no ellipsis, a full stop, every figure and capitalised word from the
body; month names allowed). `finish_displays` then runs the preflight and the judge on the
displays, the judge seeing each display's body and flagging only what the display adds (a
changed actor or object, a gloss); a failing display is rewritten with the finding as
feedback, up to three passes, then dropped, and the slide falls back to the clause cut.
Sonnet 4.5 copied the body's first sentence until the agent was given a word budget (22)
and told not to copy. A repaired body drops its display; `review_and_repair` calls
`finish_displays` at the end. On the Q4 2026 bundle 17 of 18 displays passed; one was set
by hand after the judge rejected it on a scenario claim the sentence does not make. The
full body stays in the notes.

**Cross-topic writer sees the ledger.** `_cross_topic_payload` carried a headline, a
Strengthening/Stable/Cooling distribution and one theme label per topic, and no events;
that is where the review-platform breaches and the "emerging" reputation economy came from.
It now carries each topic's status sentence, scenarios with their judged events, the
reconciled events and the briefing lede, with the organisation and metric definitions.

Prompts: judge 1.3.0, repair 1.3.0, briefing 1.4.0 (`display`), cross-topic 1.2.0, recs
1.3.0, expert view 1.3.0, display agent 1.0.0.

## 2026-10-16 (night) — Wiley Q4 bundle after the sixth review

The sixth review confirmed the count, metric and transaction-state fixes and left findings
about meaning that survives a correct count. Commit below, same hunks on wileytest and wiley.

**Date type and statement dates.** The preflight now reads each date in a sentence against
the ledger: a date every matching event holds as an article date ("reported") cannot be
written as when the development happened, and a date whose event is a statement (apologised,
disclosed, warned) belongs to the statement, not to what it describes ("agents accessed
Medicare on 29 September" for an apology of that date about June). Ledger events carry
`date_basis`; the judge, repair and writer prompts carry the same rule.

**Event type and stage.** "Ten completed agreements" for a ledger of releases, platform
access and launches is an error: a count described by one type must match the actions of
that scenario's events. "Agreed to integrate" stays an agreement; "will host by summer 2027"
stays future.

**Hypothesis as fact.** An overview, theme, decision-framework or expert-view sentence that
describes a scenario with no judged events as emerging, accelerating or routing around
gatekeepers is an error unless it marks itself as a watch item or a hypothesis. The judge
also checks platform-breach claims against named incidents and recommendations against the
named tool's documented scope (a generation-time watermark on all published material).

**The expert view is reviewed.** Slide 4 was written from forecast-time sample headlines
and was never a review segment; it still said the administration was "asserting veto
authority". It is now written from the period's events (`named_events` per topic, with
state and date type) and reviewed with everything else.

**Synthesis slide layout.** Section positions come from the estimated height of the text
above them (about 60 characters per line at 9.5pt), bodies are cut at a sentence boundary
at 180 characters (120 if three still do not fit), and the full text sits in the notes.

## 2026-10-16 (evening) — Wiley Q4 bundle after the fifth review

The fifth outside review of the Q4 2026 deck found six P1 defects. Four of them had one
cause: the writers and the narrative judge saw each topic's events as one pool, so a
synthesis could credit a scenario with events its evidence slide never shows, count
statuses that matched no slide, and quote an event count as "10 points". Commit 6a8d85fb,
applied as the same hunks to wileytest and wiley (their writer prompts stay on Sonnet 4.5).

**Each scenario carries its own events.** `_topic_data_payload` lists, per scenario, the
events judged to bear on it with their direction, and a written-out tally
(`status_sentence`: "Of 5 scenarios: 2 holding, 3 too early."). The writers are told that
only a scenario's own `events` confirm or counter it. The narrative judge's ledger has the
same per-scenario lists, and a sentence crediting a scenario with any other event is
`absent`.

**Editor regeneration passed the writers no events.** `regenerate_single_stage` called
`_topic_data_payload(a)` without `named_events`, so every scenario read Too early to a
writer regenerated from the editor, and the round-seven ledes carried tallies from nowhere.
It now loads the same events the pipeline writers get.

**Article titles out of the writers' input, again.** The emerging-theme `sample_articles`
were forecast-time headlines; "Vought will reportedly be given veto power over all NIH
grants" (21 Sep) became a recommendation's present tense three weeks after the plan was
dropped. Themes are label and size only now.

**Four more deterministic checks in the narrative preflight.** Status counts in prose
("one holding, four too early") against the ledger tally; "no events" / "left no mark"
claims against the named scenario's counts (direction-aware: "no countering events" is only
wrong when there are some); "N points" against the article-share deltas and nothing else;
and every key signal must name an event from its scenario (or the topic) or start with
"Watch:". Judge `metric` findings block again, since the points check now owns the case
that made them advisory.

**Judge and repair prompts.** Event identity, "coverage is not behaviour" (an article-share
delta never shows investors pricing or analysts re-rating), "an enabling step is not the
outcome" (a review launched, a bond put on a 2028 ballot, an award), and a repair rule for
key signals.

**Hand-set links survive.** A scenario link with `"locked": true` is kept by the link judge.
The NIH abandonment event had lost its counter-link in the merge.

**Deck.** The briefing synthesis slide fits whole sentences at 9.5pt (tensions up to 300
characters, lede and view up to 1,050 together) and puts the full text in the notes instead
of shrinking to 8.5pt (and does not split a sentence at "U.S."). The Key Insights evidence count shows from one scenario, not two. The
methodology slide states the status thresholds (basis ≥60% high, ≤40% low) and the two
cutoffs (article-share assessment date; event window to export).

**Rows corrected by hand on wileytest** (`edited_by` says why): Informa / Taylor & Francis is
one record, 6 Oct, "announced plans to separate and launched an options review", outcome due
March 2027 (three duplicates merged, one of which said "separated to become independent");
the 23 Sep abandonment of the NIH veto order counters Political Centralization; planqc's
award is the Made in Europe Award 2026 of 16 Sep, out of window and unlinked (the article
summary had read "home and small business use" into a headline pun).

**Run scripts from the tenant tree.** Deck overlays live in `data/wiley_horizons` relative to
the working directory. A pipeline script started in the bugfixing tree against the wileytest
database used bugfixing's overlays, where Open Science has no display name, so that topic
dropped out of the narrative review and the regenerations.

## 2026-10-16 (late) — Wiley Q4 bundle after the round-four review

The fourth independent review found the narrative still out of step with the ledger in three
ways: a synthesis naming "supporting articles" the evidence slides never show, sweeping status
claims ("all five scenarios too early") that two ledgers contradicted, and event-to-scenario
links that accepted adjacent evidence (a novel-drug deal under a biosimilar scenario, an
error-correction milestone as a practical application). Commits f2166eda through 79eaf5b3,
live on bugfixing, wileytest and wiley.

**Writers and judge read events only.** The per-scenario `top_supports` / `top_contras` article
titles are no longer in the writers' input and the narrative judge's ledger, so a lede cannot
name "two supporting articles" that differ from its slide's two events.

**Wider review coverage.** The executive decision framework and every scenario's key signals and
strategic imperative (the text on the strategic-domain and scenario slides) are now review
segments, written back to `forecast_scenario_verdicts.synthesis` on repair.

**Two more deterministic checks.** A sweep over a topic's scenarios ("all five", "none of the")
must match every scenario's ledger status, or it is an error the judge cannot miss. A judge
error about a sentence that restates a ledger event almost word for word ("2,800 viruses" vs
"over 2,800 viruses") is wording, demoted in both the narrative review and the bundle reviewer.

**Links: Jev proposes, the judge decides.** Jev answers relevance only at 0.6; a second judge
(gpt-5.4, `wiley_link_judge_agent`) keeps or drops each proposed link with a one-line rationale
stored on the link, applying the rules about adjacent sectors, enabling milestones, single
instances and public funding. On Q4 it dropped 214 of Jev's proposals and kept 69. A first
attempt with those rules inside Jev's question left Quantum Advantage with no links at all;
that nuance belongs with the judge that reads the whole claim.

**Letter gate, again.** Titles carrying a banned word are quoted in three forms: the full title,
the shortest prefix that holds the word ("Credibility Crisis"), and any Title Case run of three
or more words (last quarter's tail risk, restated by the installment letter), case-insensitive.
The humanizer, the grounding check and the golden gate rewrite the letter after its gate; the
pipeline now re-quotes after them and keeps the gated letter if a rewrite reintroduces a word.

**Bundle reviewer sees the judged events.** Its per-topic data was built without events, so
every scenario read "Too early" and the reviewer called every correct lede an error.

**The loader that fed the writers (e882cc4d).** The pipeline's own event loader trimmed every
event to actor, action, subject and date, dropping the judged scenario links, so the writers
and the bundle reviewer saw every scenario as "Too early" while the exports, which use the
full rows, showed "Holding". That is why the writers kept producing "all five scenarios too
early" and the narrative review spent its repair rounds undoing it. The loader now returns the
full collapsed rows and the agents receive a trimmed copy with the links.

**Letter regeneration from the editor (28aa8d10, 7fb455e6).** The single-stage path had no
length or severity gate, and the humanizer and grounding check shortened a 420-word letter to
387 after the gate; both paths now gate, retry and keep the gated letter when a rewrite
breaks it. Grammar-only and self-approving reviewer findings are advisory.

**Extractor.** A retrospective account of earlier developments is `article`-dated, not
`stated`; the deck says "reported on" for those rows. A date later than the article is an
effective date (a licence "from April 2027"), so the article date stands in. The key-insights slide counts scenarios
without judged events, the same count the evidence slides show. Topic dividers label the
tracker date "Article-share assessment" next to the evidence window.

