# Market Monitor: the coverage panel now reports what was actually measured
_2026-08-26 · Market Monitor and Brand Watcher (bugfixing.aunoo.ai only — Market Monitor does not exist on any other customer instance)_

## What shipped

- **Simbian is now tracked** in the SOC Automation market and in Brand Watcher, with its
  website, LinkedIn page and funding history on file.
- **"How much of the market was measured" now counts work that was done.** Three of the
  panel's data sources were reporting reading they had already finished as never
  finished. One said it had read nothing when it had just read 82 companies' websites.
- **Company websites are read for 69 companies instead of 19.** The reading was always
  happening; almost none of it was being counted.
- **44 companies became visible to funding data.** They had been quietly unreachable, and
  the panel had been hiding them by shrinking the total rather than showing a gap.
- **A remaining gap now tells you why it's there.** "No pages found for this company" and
  "this company's site would not load" are reported as different things, and neither is
  reported as a measurement.

## Why it matters

**A panel that under-reports is worse than one that says nothing.** The whole point of
"how much of the market was measured" is to stop a zero being mistaken for an answer. A
customer looking at `0 of 83` for company websites would reasonably conclude the feature
was broken and stop trusting the numbers next to it. The reading had in fact been done —
the system simply never wrote down that it had. Who feels it: the analyst deciding whether
a quiet market is genuinely quiet, and the buyer deciding whether to believe the coverage
claim at all.

**Company website coverage went from 19 companies to 69.** Before, a company was only
counted once something on its website *changed*. A company with a stable site looked
identical to one nobody had ever visited. So the number tracked "how many competitors
redesigned a page recently", not "how many competitors we are watching" — and it drifted
down over time as sites settled. Now it counts having read the site, which is the question
being asked.

**44 of 84 companies could never receive funding data, and nothing said so.** Reaching a
company's funding record needs a link to it, and that link is worked out from the company's
own name. The step that works it out sat behind a check that could only pass for companies
that already had one. So a company added to the market could never get a link, and could
never be collected. Worse, the panel reported this as `20 of 40` — it shrank the total to
the companies it could reach, so half the market's absence looked like a smaller market.
It now reads `20 of 84`. That looks worse and is the honest figure. Who feels it: anyone
who added a competitor after the market was first set up and wondered why its funding stayed
blank.

**Simbian was added end to end, not just to a list.** Its funding status matters mechanically
as well as informationally — a company recorded without a disclosed raise is tracked but
never searched for by name, so it would have sat in the registry collecting nothing. That is
now recorded, along with the source it came from.

## Release notes (copy-ready)

- Added Simbian to the SOC Automation market and to Brand Watcher.
- Fixed the market coverage panel, which was reporting completed data collection as never
  started for three sources. Company website coverage was the worst affected and now shows
  69 companies where it previously showed 19.
- Fixed a bug that made 44 tracked companies permanently unreachable for funding data. The
  coverage total now shows the full market rather than only the reachable part.
- Company website reading no longer stops partway through when one site is slow to respond.
- Gaps in coverage now say why: no pages found, or the site could not be reached.

## Demo / walkthrough

Market Monitor → Data tab → "How much of the market was measured". Compare the Collected
column against the Notes column. Every source row is now one of: measured, partly collected
with a stated reason, or no source configured — and the Collected figure counts vendors the
source actually read.

Simbian: Market Monitor → Vendors, or Brand Watcher → brand list. Both list it as active.

## Positioning notes

This is the metric-honesty story we already tell about this product, applied to itself. The
existing promise is that a zero on the market page has to be a measurement and not a blank —
the 2026-08-26 metric-contract work made the panel capable of saying "unmeasured", and this
session found three sources that were wrongly claiming exactly that. It closes the obvious
objection to any coverage claim: *how do you know you looked?* The answer is now per-source
and per-company, with the reason attached when the answer is "we didn't".

The `20 of 84` figure is worth leading with rather than hiding. A vendor that corrects its own
denominator upward, making its numbers look worse, is making a credibility argument that a
polished dashboard cannot.

## Limits and what's next

- **Funding coverage is still 20 of 84 today.** The fix makes the other 64 reachable; it does
  not fetch them. That happens on the next scheduled funding run, around 31 August.
- **The funding links are guesses.** All 85 are worked out from company names and marked
  unverified. The internal estimate is roughly two in three land on a real page, so expect
  around a third of the newly-reachable companies to come back empty on the first attempt and
  need a correction. Check the review queue after the 31 August run rather than assuming full
  coverage.
- **13 companies have no website pages to read**, because the page-discovery step found none
  on their sites. They are deliberately shown as a gap rather than counted, so website
  coverage will read 69 of 83 and not 83 of 83 until discovery finds pages for them.
- **Three sources show 82 of 83 because Simbian is new** and has not had its first LinkedIn
  reading yet. That clears on the next scheduled run, within 12 hours.
- **The 230 website snapshots recorded today are starting points, not news.** A page read for
  the first time counts as changed. If a vendor timeline surfaces these, today will show a
  burst of activity that is not real activity. The next run is the first whose change count
  means movement.
- **Provider spend tracking is internal and new.** Bright Data usage is now costed per record
  so the monthly spend limit works — it previously read a value nothing ever wrote, so setting
  it had no effect. This has no customer-facing surface; it is noted here only because it
  changes what an operator can rely on. A limit of $50/month is set on this instance against
  measured usage of about $11 for August.
