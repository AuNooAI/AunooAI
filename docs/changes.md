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

