# Forecast Tracker and Topic Reports: the numbers now agree with each other
_2026-08-18 · Forecast Tracker tab, Topic Reports, Add-Topic wizard_

**Audience note.** The reliability work below is customer-facing and the release notes are
safe to send. **The first item is not.** It is a security fix on data that was publicly
reachable, and how it gets described to customers is Oliver's decision, not a copy
question. That section is marked internal only. Do not paste it into a changelog, a
customer email, or a release post.

## What shipped

- **(Internal only)** Closed a hole that left the Forecast Tracker, Topic Report and
  candidate-triage APIs readable and writable by anyone on the internet, with no login.
- The Forecast Tracker no longer mixes one forecast's scenarios with another forecast's
  results.
- Scenarios you promote from an emerging theme now show progress and finish on their own,
  instead of leaving a spinner that never stops.
- Marking a scenario "done" always marks the one you clicked.
- Topic Reports can now be re-run for topics whose display name differs from the name
  their articles are filed under.
- All five download formats of a report — slides, web page, Markdown and both Word
  documents — now describe the same forecast.
- Regenerating a report replaces the executive summary too, instead of pairing new slides
  with the previous letter.
- A newly generated forecast gets scored within hours rather than waiting up to a month.
- Corrections made in the Add-Topic wizard are saved instead of being silently dropped.
- Report generation requested while three jobs are already running is now queued and runs,
  instead of disappearing.

## Why it matters

### The access problem (internal only — not for external distribution)

Every Forecast Tracker, Topic Report and candidate endpoint could be called by anyone who
knew the address. No login, no session, nothing. That covered reading the tracked topic
list and the candidate queue, downloading generated reports in every format, and every
write action — starting a report, promoting a candidate, approving an overlay, changing
who receives reports by email, and sending a report out.

We confirmed it by requesting two of those addresses from outside with no credentials and
getting real data back, on every customer site including the live one. All 60 endpoints
now require a signed-in user, and four of the most sensitive — sending email, replacing a
production file, changing delivery recipients, approving content for release — require an
admin. Signed-in users notice no difference.

How long the gap was open, and whether anyone should be told, are open questions this
change does not answer.

### The Forecast Tracker was showing one forecast's results against another's scenarios

The tracker scores a stored forecast against news that arrived since. When you generated a
*new* forecast for a topic, the tracker had nothing to show for it yet, so it fell back to
the most recent scoring for that topic — from the *previous* forecast — and displayed it as
though it belonged to the new one. The two forecasts do not have the same scenarios in the
same order, so a result could appear under the wrong scenario's heading, and clicking
"done" could mark a different scenario than the one on screen.

Now an unscored forecast says so plainly. The older scoring is still available underneath,
clearly labelled as belonging to an earlier forecast, with both identities shown and every
edit control switched off.

The same confusion had a second source. Scenarios were identified by their position in a
list. Promote a new scenario, or resolve an existing one, and everything after it shifted
by one. Each scenario now carries an identifier of its own, so results and status stay
attached to the scenario they belong to no matter what moves around them. Anyone who works
in the tracker daily feels this one.

### Promoting a scenario looked like it had hung

Promoting an emerging theme into a tracked scenario starts a re-scoring run in the
background. The screen showed a progress spinner, but nothing was watching the job, so the
spinner never resolved and the new scenario's result only appeared after a manual page
reload. It now follows the job to completion and refreshes on its own, and reports a real
error if the job fails.

While fixing this we also found the assessment window control was not being sent. Changing
it from 8 weeks to 12 submitted the old value.

### Topics whose name differs from their articles could not be re-run

The Add-Topic wizard deliberately lets you name a topic "Quantum Advantage" while its
articles stay filed under "Quantum Computing". Report re-runs searched only for the
display name, found nothing, and stopped with "no articles". Those topics simply could not
be re-run from Topic Reports. Re-runs now search the source names the topic is actually
built from, and each forecast records which ones it used.

### The five download formats could disagree

A report pins itself to the exact forecast each of its topics was built from, so a later
re-run cannot change an existing report underneath you. Three of the five formats honoured
that pin. Markdown and the executive Word document ignored it and looked up the newest
scoring instead, so the same report could describe different analysis depending on which
button you pressed. All five now read the same pinned forecasts. If a pinned forecast has
genuinely been deleted, the download now says so and asks you to regenerate, rather than
quietly substituting a different one.

### Regenerating left half the old report in place

"Regenerate" deleted the cached slides and nothing else. The executive summary, the review
verdict and the record of which forecasts were used all survived, and the summary is only
written when it is missing — so the old executive letter was served against new slides
indefinitely. Regenerating now clears all of it. If it cannot, it says so and changes
nothing, rather than leaving a half-cleared report.

### New forecasts waited up to a month to be scored

Scoring was scheduled per topic: if a topic had been scored in the last 30 days, nothing
was scheduled, even if you had generated a brand-new forecast for it that morning. That
new forecast sat unscored. Scheduling now tracks each forecast separately, so a new one is
picked up on the next check. Only completed scorings count, so a failed run retries
instead of blocking the slot for a month.

### Wizard corrections were being thrown away

Going back a step in the Add-Topic wizard and correcting the name, description, owner,
tags or source topics did nothing — the wizard reported success and kept the original
values. Those edits now save. Separately, the final "activate" step never checked whether
it worked, so a failure there left the topic as a draft while the wizard closed and
deleted its own saved progress. It now reports the error and keeps your progress.

### Work could be silently dropped

Three background jobs run at once. A fourth request logged "queuing" and then did nothing
at all — the job was recorded as pending with nothing to run it, so it never started,
never failed, and never told anyone. A fourth report generation or scoring run simply
vanished. Requests beyond the limit are now genuinely queued and run when a slot frees.
Jobs interrupted by a restart are now marked failed instead of appearing to run forever;
65 such stuck records across the three sites were cleared on the first restart.

## Release notes (copy-ready)

Omit the first bullet unless Oliver has decided how the access issue is being communicated.

- The Forecast Tracker no longer shows an older forecast's results against a newer
  forecast's scenarios. An unscored forecast now says so, and the earlier scoring is shown
  separately and marked read-only.
- Marking a scenario done now always applies to the scenario you selected, including after
  scenarios have been promoted or resolved.
- Promoting an emerging theme to a scenario now shows real progress and refreshes when the
  re-scoring finishes, instead of leaving a spinner running.
- The assessment window setting is now applied — changing it from 8 to 12 weeks takes
  effect.
- Topic Reports can be re-run for topics whose display name differs from the name their
  articles are filed under.
- Slides, web page, Markdown and both Word exports of a report now all describe the same
  forecast.
- Regenerating a report now replaces the executive summary and review state as well as the
  slides.
- A newly generated forecast is scored on the next scheduled check instead of waiting for
  the topic's monthly cycle.
- Corrections made by stepping back in the Add-Topic wizard are now saved.
- Report and scoring jobs requested while others are running are queued and run, rather
  than being dropped.

## Demo / walkthrough

**Mixed forecasts.** Open **Explore → Forecast Tracker** for a topic, generate a new
Three Horizons forecast for it on the Future Horizons tab, then return. Before: the old
scoring appeared as if it were the new forecast's. Now: an amber banner names both the
forecast you are viewing and the earlier one the results belong to, and the edit controls
are off.

**Promotion.** In the Forecast Tracker, open an unanticipated development and promote it to
a scenario. The progress bar now advances and clears by itself, and the new scenario's
result appears without reloading.

**Report formats.** Generate a Topic Report, then download all five formats from the same
report. Every one names the same forecast.

## Positioning notes

This is a reliability release on two surfaces analysts use to make judgements, so the
argument is credibility rather than capability. The tracker showing one forecast's results
against another's scenarios, and two download formats describing different analysis, are
the kind of defects that make someone stop trusting the whole tool — including the parts
that were always correct. Worth raising proactively with anyone who has said the tracker
"looked off" or that a report "didn't match the deck".

Nothing here is a competitive differentiator. Do not lead with it.

## Known wobble during the rollout

A code review after deployment found that the scenario-identity change had, for about an
hour, broken "mark as done" for the five Wiley Horizons topics specifically. Those topics
group their scenarios into the named ones the customer's deck shows, and the new
identifier was being calculated from the ungrouped list on one side and the grouped list
on the other, so the two never matched and the button would have returned an error. It is
fixed and verified against the real data for those topics. If anyone reports that marking
a scenario done failed this afternoon, that was the cause and it is resolved.

The same review caught a report-regeneration problem before any customer hit it:
regenerating would have cleared the record of which topics a report contains, leaving its
downloads unusable until someone rebuilt it from memory. Also fixed.

## Limits and what's next

- The security fix closes anonymous access. It does not tell us whether anyone used it.
  Reviewing access logs for the exposure window is a separate piece of work and has not
  been done.
- Reports are still identified by a generated label rather than a durable ID, and
  regeneration still replaces the current report rather than creating a new version
  alongside it. Two reports covering the same period but different topics remain safe
  because the label includes a hash of the topic set, but the underlying design work is
  outstanding.
- Report files still live in a temporary directory. If that directory is cleared, the web
  page and full Word exports for existing reports stop working until the report is
  regenerated.
- Retrying a promotion after a network error can still create two scenarios; there is no
  duplicate-request protection yet.
- Anyone signed in can still read any background job's status by its ID. Job ownership is
  not yet checked.
- Roughly a third of the spec this work came from is not built, mostly around durable
  report identity and provenance. `docs/changes.md` lists exactly what remains.
