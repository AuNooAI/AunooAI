# 16 October 2026 — The Wiley quarterly bundle now checks itself

## What changed

Three rounds of repair in two days, driven by an outside review of the Q4 2026 deck, left the
Wiley quarterly bundle with four stages it did not have on Monday.

**Evidence starts at the forecast.** Events are extracted from each topic's forecast date, not
a fixed look-back, so a "since the forecast" ledger contains only developments since the
forecast. On Q4 that removed 307 of 463 events that predated it.

**One record per real-world event.** Articles arrive one row each; a deal that four outlets
covered came in as four rows with three different amounts. A reconciliation stage now merges
them: Jev decides which rows report the same development, a writer produces one record with
the agreed figure, date and state (proposed, agreed, completed, withdrawn), and a judge a tier
above the writer accepts, corrects or rejects it. Nothing is deleted; merged rows stay in the
editor's Events tab pointing at the record.

**Evidence links are judged, not assumed.** Each event is judged against every scenario of its
topic. A link exists only where Jev is confident the event bears directly on that claim. The
ledgers got thinner, the off-topic analogies disappeared, and a scenario's status is the same
on its slide, in the letter and in the recommendations because all three read the same record.

**The narrative is read against its own ledger.** Every lede, tension, recommendation, next
step, theme, the overview and the letter go through a deterministic check on dates and
figures, a quoting judge for contradictions, states, metric misuse and audience, and a repair
step that may change only the quoted sentences, twice at most. The verdict is computed in code.
On Q4 this took the regenerated narrative from 31 contradicted or unsupported sentences to
none without a human edit.

## Why it matters

The bundle had shipped three quarters on the strength of an LLM reviewer that judged the text
against whatever events it was handed. It could not tell that the events were from the wrong
window, that one story was counted four times, or that a number had been invented. Each of
those is now caught by a stage that does not take the model's word for it.

## What a customer sees

A deck whose evidence slides, executive letter and recommendations agree with each other;
event records with a state and a figure the sources support; speaker notes with the source
links behind every ledger row; and a methodology slide that says what the numbers mean.

## Still to do

Announcement dates kept apart from article dates, a printed map from one quarter's scenarios
to the next, and the dense summary slides.

## Evening update: each scenario owns its evidence

The fifth outside review found the same deck still naming different events in its summaries
than on its evidence slides, counting scenario statuses that matched no slide, and quoting a
ten-event count as "10 points". All three had one cause: the writers and the judge saw a
topic's events as one pool.

Now every scenario hands the writers and the judge its own judged events, the rows its slide
lists, together with a written-out tally of statuses. The checks run in code: a count of
statuses in prose must equal the tally, "no events" must be true of the scenario named, a
figure in points must be the article-share delta and nothing else, and a key signal must
name an event or be marked as something to watch. The summary slides keep whole sentences
at a readable size and put the rest in the notes. A hand-set evidence link now survives the
next automatic pass, and a plan reported as "will be given veto power" three weeks before it
was dropped can no longer reach a recommendation, because the forecast-time headlines are
out of the writers' input.

On Q4 the first pass of the review found ten contradicted sentences instead of fifty-three,
and the repair cleared them.
