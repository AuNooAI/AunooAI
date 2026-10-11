# The daily briefing fact-check now fixes what it finds, and shows its work
_2026-09-25 · Briefing Desk (daily briefings)_

## What shipped
- The automatic fact-check on daily briefings now fixes date wording itself, without a rewrite.
- Rewrites change only the sentences the check flagged. Nothing else in the briefing can move.
- A rewrite that makes the briefing worse ends the loop, and the best version ships.
- A serious finding stops a briefing only if the check upholds it on a second read.
- The review panel under each briefing shows how many correction passes ran and which one shipped.

## Why it matters

### Date wording, fixed in place
Most of what the fact-check flagged was one thing: a sentence that dated an event by the day it was
reported. "The White House reversed the directive on September 23" when the source only says the
story ran on September 23.

- **Before:** every such finding went back for a full rewrite, and the rewrite rarely settled. On
  Wiley's test site, the 25 September briefing went through three rewrites, from 14 warnings to 7,
  then 3, then 16, and shipped with 7. Six of those seven were on sentences that already said
  "reported on". The check was contradicting its own rule.
- **Now:** the check drops a date finding on a sentence that already gives its date as a reporting
  date, and it fixes a bare event date itself by writing "as reported on" into that one sentence.
  No rewrite, no other sentence touched.
- **Who notices:** the analyst who finalizes the briefing. The review panel stops listing the same
  non-problem seven times.

### Rewrites that cannot break the rest of the briefing
- **Before:** the rewrite was asked to change only the flagged sentence and return the whole
  briefing. It did not comply. On one run it dropped Elsevier's name from a sentence nobody had
  flagged, and every later rewrite added errors: on 15 September 1 error became 4, on 24 September 0
  became 3, on 25 September 2 became 3 and then 4.
- **Now:** the rewrite returns one replacement per flagged sentence, and we put each one in
  ourselves. Sentences the check did not flag stay exactly as they were. When a rewrite still adds
  errors, the loop stops and the best earlier version ships.
- **Who notices:** readers of the briefing. A correction cannot cost them a fact elsewhere.

### A second read before a briefing is held
The check sometimes raises a serious finding on text it had passed a minute earlier, with nothing
in that text changed. A serious finding holds the briefing until an analyst acts, so a false one
costs a morning.

- **Now:** when the check raises a serious finding, we ask it again about just that sentence and
  its sources, with doubt resolved against the finding. Only a finding that stands twice holds the
  briefing. A withdrawn one stays visible as a note.
- **Who notices:** the analyst, who is interrupted less often by findings that evaporate on a
  second look.

### The desk shows what happened
- **Before:** the correction passes were recorded but invisible. Seeing them meant a database query.
- **Now:** under the review line on a finalized briefing: "3 repair passes (1 date fix, 2 writer) ·
  kept pass 3 · judge errors: 3 confirmed, 0 withdrawn". It opens to a table of errors and warnings
  after each pass, with the version that shipped in bold.

### What the 25 September briefing looks like now
Regenerated from the same articles at the end of the day: 0 errors and 2 warnings, against the 7
warnings it shipped with in the morning. The two remaining warnings are an inference the check
considers unsupported and a piece of arithmetic on sourced figures. A separate test run of the same
briefing ended with no findings at all, in under five minutes.

## Release notes (copy-ready)
- Daily briefings: the fact-check now corrects date wording itself instead of sending the briefing
  for a rewrite.
- Daily briefings: rewrites change only the sentences the fact-check flagged.
- Daily briefings: a rewrite that adds errors ends the correction loop; the best version ships.
- Daily briefings: a serious finding stops a briefing only when the check confirms it on a second
  read.
- Briefing Desk: the review line on each finalized briefing shows the correction passes and which
  one shipped.

## Demo / walkthrough
1. Open **Briefing Desk** on the Wiley test site and select the 25 September briefing.
2. Under the executive summary, the review line reads "Reviewed: 2 warnings, no errors". Click it
   to see the two findings.
3. The line below it reads "6 repair passes (4 date fixes, 2 writer) · kept the first draft". Click
   it to open the table: errors and warnings after each pass, and the pass that stopped the loop
   marked "stopped: this pass added errors".
4. Finalize any draft briefing to watch the passes run live in the progress log. Date-fix passes
   are labelled as such.

## Positioning notes
We say every claim in a briefing traces to a source. Yesterday's work made the check act on what it
found; today's makes the corrections converge and keeps them from damaging anything else. For a
publisher like Wiley, the visible correction history is the part that sells: the reader can see the
briefing was checked, corrected, and checked again, rather than taking our word for it.

## Limits and what's next
- **The check itself is still the noisy part.** It raised 13 to 15 date findings per run on
  sentences that already said "reported on", even after we told it not to. We drop them, so the
  reader never sees them, but they cost review tokens. The second-read step is there because the
  check disagrees with itself on serious findings too. On the one run where it fired, it upheld all
  three findings and withdrew none, so we have not yet seen it catch a false one.
- **Warnings can still ship.** Only serious findings hold a briefing. The refinalized 25 September
  briefing shipped with two warnings the correction loop did not clear.
- **Only the Wiley sites and our own have this.** Sunstar, Oviva, abm, wbm and the smaller sites
  still run the old rewrite loop.
- **No "fix this one" button.** The question that started the day. The loop now does what such a
  button would do, and does it before the analyst sees the briefing. A per-finding button on a
  finalized briefing would need the source articles stored with it, which they are not.
