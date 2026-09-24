# Daily briefings now correct what the fact-check finds
_2026-09-24 · Briefing Desk (daily briefings) and incident tracking_

## What shipped
- The daily briefing's fact-check now sends every problem it finds back to be rewritten, not only the serious ones.
- Incidents no longer carry a year that none of their sources state.

## Why it matters

### Corrections instead of a list of problems
Each daily briefing goes through an automatic fact-check before it is finalized. The check compares
every sentence with the articles it came from. It rates what it finds as errors or warnings.

- **Before:** only errors went back for a rewrite. Warnings were shown next to the briefing and the
  briefing went out with them unchanged. On Wiley's 24 September briefing the check found five
  warnings, and all five were published. One sentence named "Russel Vought" and "Russell Vought" as
  if they were two people. The check had also listed nine sentences just to say they were correct.
- **Now:** warnings go back for a rewrite too, with one extra rewrite round to fit them in. When a
  rewrite makes the briefing worse, we keep the better earlier version. Lines that only say a
  sentence is fine are gone from the review.
- **Who notices:** the analyst who publishes the briefing, and everyone who reads it. There are fewer
  wrong sentences to correct by hand, and the review panel lists only real problems.

On the regenerated 24 September briefing, the check took the draft from 4 errors to none. It kept
the version with 0 errors and 5 warnings, and threw away a later rewrite that brought 3 errors back.

### No made-up dates on incidents
- **Before:** a news headline said an AI agent broke into an Australian Medicare portal "in June".
  Our automatic article summary added "2023". The incident tracker copied that, and the briefing
  reported a three-year-old breach that no source described.
- **Now:** a year in an incident must appear in one of its source articles. When it doesn't, we drop
  the year and date the incident by when it was reported. The incident now reads "in June, reported
  on September 23".
- **Who notices:** readers of the briefing and the incident panel. Dates are what people act on,
  and a wrong year changes the story.

## Release notes (copy-ready)
- Daily briefings: the automatic fact-check now corrects warnings as well as errors before a
  briefing is finalized.
- Daily briefings: the fact-check no longer lists sentences that need no change.
- Incidents: a year that no source article states is removed, and the incident is dated by when it
  was reported.

## Demo / walkthrough
1. Open **Briefing Desk** and finalize a daily briefing.
2. Watch the progress log. After the review step it now shows repair rounds whenever there are
   warnings, not only errors, with the error and warning counts before and after each round.
3. Open the finished briefing's review panel. It lists only open problems.

## Positioning notes
We say briefings are checked against their sources. This makes that claim hold for smaller problems
too. The check used to find them and then leave them in. It supports the "every claim traces to a
source" story for publishers such as Wiley, where a wrong date or a doubled name in a briefing costs
trust quickly.

## Limits and what's next
- **Some warnings still get through.** On 24 September, 4 to 5 warnings remained after all rewrite
  rounds, mostly small wording points. Only errors stop a briefing from being finalized.
- **The check can miss a claim.** The regenerated briefing merged two separate reports into "an
  executive order to give Vought veto authority", and the check did not flag it. We fixed that
  sentence by hand.
- **Dates are only checked where we have the full article text.** That covers about three quarters of
  recent articles on Wiley's test site. For the rest, a year from our own summary is kept.
- **Changing the summary instructions is unproven.** The summaries were also told not to add years.
  We could not make the old instructions add a year in testing, so we don't know yet whether the
  new rule helps.
- **Only the sites that are running have this.** Stopped customer sites, and Pearson (currently
  down), will get it when they are brought back.
