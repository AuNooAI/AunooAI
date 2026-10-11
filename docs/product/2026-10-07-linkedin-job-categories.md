# Hiring charts keep their job categories after a LinkedIn change
_2026-10-07 · Market Monitor: hiring by function, job lists, CSV export_

## What shipped
- LinkedIn job postings get a job category again, after our data provider stopped supplying one.

## Why it matters
**Before.** On 1 October LinkedIn stopped showing a job's category publicly. Our data provider,
Bright Data, stopped sending it, and every LinkedIn job we collected after that had no category.
The "hiring by function" chart showed most LinkedIn jobs as "not stated". An analyst could no
longer see whether a vendor was hiring engineers or salespeople. This affected every site with
Market Monitor: bugfixing, Panaya, Sunstar, Oviva and abm.

**Now.** A job we saw before 1 October keeps the category LinkedIn gave it. For a newer job, we
guess the category from its title. "Senior Account Executive" becomes Sales, for example. We
also repaired the jobs already stored. On Panaya, 4 of the 102 affected jobs are still without
a category. On bugfixing it is 141 of 442.

## Release notes (copy-ready)
- LinkedIn stopped publishing job categories on 1 October. Market Monitor now keeps the category
  for jobs it saw earlier and guesses it from the job title for new ones.
- Jobs collected since 1 October have been repaired, so the hiring-by-function chart no longer
  files most of them under "not stated".

## Demo / walkthrough
Open a market in Market Monitor and go to the hiring chart, which groups openings by function.
The "not stated" bar should be small again. A vendor's job list shows the category beside each
posting.

## Positioning notes
None. This restores what the chart showed before a supplier change, so it adds nothing to sell.

## Limits and what's next
- The category of a new job is a guess from its title, not LinkedIn's label.
- The title word list was written for tech and security vendors. It rarely matches dental or
  healthcare titles. On Sunstar, 40 of the 82 affected jobs still had no category after the repair, and 19 of the 41
  jobs from its first run on the new code got none. Sunstar and Oviva would need their own word
  list, or a model-based guess, to fix that.
- The guess and LinkedIn's own label appear the same way on the chart.
