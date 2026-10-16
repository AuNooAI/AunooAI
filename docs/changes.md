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

