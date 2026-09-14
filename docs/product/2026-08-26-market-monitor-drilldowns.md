# Every number on the market page now opens the records behind it
_2026-08-26 · Market Monitor — posts, coverage, hiring, funding, investors, voices_

## What shipped

- Click any figure and you get the exact records it counted, with paging, and the count on the list always matches the count on the card.
- Every list downloads as a spreadsheet, using the same filters you were looking at.
- Job listings now say what changed: currently observed, newly observed, or no longer observed — and a failed collection can never mark a role as gone.
- The "Open roles" column is now "Open roles on LinkedIn", because that is the only place we look.
- Funding is broken out per company with each field labelled by where it came from, and companies that never disclosed a figure are no longer lumped in with companies we have not read.
- Investors show which companies they back, with a link to the evidence for each.
- Each account in Top Voices links to every post it made about the market.
- "Largest disclosed raises" is now "Largest disclosed total funding", because those are cumulative totals and not single rounds.

## Why it matters

**A number you cannot open is a claim you cannot check.** Every figure on this page used to be a dead end. The most useful one on the overview was "62 vendors with no signal" and there was no way to see which 62. Now every count opens its records, and the list shows the filters the server actually applied so you can see it is the list the card opened rather than a similar one.

If a list and the card ever disagree, the page says so in an amber banner rather than leaving you to notice. That mattered immediately — see below.

**Three ways the records quietly disagreed with the figure.** All three were real, all three were found by building the lists and comparing, and none of them looked like a bug.

The first: a card said 533 posts and its list held 532. The cause was the date boundary being written two slightly different ways — one with a timezone suffix, one without — compared as text. One post sat between the two spellings.

The second: clicking an account in Top Voices returned *nothing* for an account the list ranked. Two different definitions of "posts about this market" were in play: one counted everything matching the market, the other only counted posts naming a company we track. A practitioner can discuss the market without naming any of our vendors.

The third: adding paging to the job listings quietly cut the hiring panel from 91 roles to 50, because that panel had always received the complete list.

Who feels it: anyone about to repeat one of our numbers. A figure that cannot be opened has to be taken on trust; these three cases are why that trust was not warranted.

**Job listings now distinguish "gone" from "we could not look".** A listing is only marked as no longer observed when two consecutive *successful, uncomplete-free* collections did not see it. A failed run, or one that came back at the provider's limit, is never used as evidence a role closed. Otherwise a provider outage reads as the whole market cancelling its hiring.

Where a company has only one collection on file there is nothing to compare against, so those roles are marked "first observation" rather than "new" — and the panel states how many are in that position. Today that is 89 of 91.

**"0 open roles" was true and read as "not hiring".** A customer pointed at Dropzone AI: we showed 0, and their careers page lists 11 roles. We checked — the company's LinkedIn page genuinely says "There are no jobs right now." Their hiring runs through Greenhouse and their own site.

The number was right. The label was wrong, and not by a little: **67 of the 83 companies in this market list no roles on LinkedIn**. So an unqualified "Open roles: 0" was being read as "not hiring" for four out of five companies on the page.

The column now says "Open roles on LinkedIn", and the explanation names the gap: roles posted to a careers page or a hiring system are not counted. The count still shows 0 rather than a dash, because we did look at LinkedIn and there was nothing there — a dash would claim we had not.

Who feels it: anyone using hiring as a signal of how a company is doing. Reading "0" as a slowdown, when the company has eleven roles open, is the kind of wrong conclusion that gets repeated in a meeting.

**Funding said Crunchbase for figures that were not Crunchbase's.** The disclosed total comes from the imported spreadsheet; the stage, investors and scores come from Crunchbase, read on a different date. Shown side by side with no labels, a reader attributes all of it to Crunchbase. Every field now carries its own source.

And three states replace two: **disclosed**, **undisclosed** (the company chose not to say) and **unavailable** (we have not read it). 37, 0 and 46 respectively. Neither of the last two is shown as zero, which used to put a bootstrapped company and an unread one in the same place at the bottom of a chart.

**The shared-investor figure now admits when it cannot answer.** No investor in this market currently appears against two companies — but that is because we have read 20 of the 39 Crunchbase pages, not because the market has no common backers. The list reports that it is partly collected rather than reporting a confident zero, and says so as its first caveat. Names are matched on spelling only; two firms with similar names are never merged, because guessing would invent exactly the overlap the figure exists to measure.

## Release notes (copy-ready)

- Every Market Monitor figure now opens the records behind it, with paging and a CSV download that uses the same filters.
- Drill-down totals are checked against the figure that opened them, and any disagreement is shown rather than hidden.
- Job listings are labelled currently observed, newly observed, no longer observed, or first observation. A failed or capped collection can never mark a role as no longer observed.
- Where a company has only one collection on file, its roles are marked "first observation" and the panel states how many.
- "Open roles" is now "Open roles on LinkedIn". 67 of 83 companies in the SOC Automation market list no roles there, so a zero means none on LinkedIn rather than none at all.
- Funding is listed per company with each field labelled by source. Undisclosed and unavailable are now distinct, and neither is shown as zero.
- Investors list the companies they back with a link to the evidence for each, and state how much of the market has been read.
- Top Voices handles link to every post that account made about the market.
- "Largest disclosed raises" renamed to "Largest disclosed total funding" — these are cumulative totals, not single rounds.

## Demo / walkthrough

Market Monitor → SOC Automation. On the Findings view, click a bar in **LinkedIn post volume** for one company's posts, or "All posts" for the market. Click a bar in **Content observed by week** for that week's articles. In the vendor table, click a number under **Open roles on LinkedIn**.

Each opens a list showing the record count, the filters applied, and a `?` for the definition. The CSV link exports the same rows.

For the hiring statuses, open Analysis → Observed hiring, then any company's role count. For funding provenance, Findings → Largest disclosed total funding → "All vendors".

## Positioning notes

This is the half of "can I trust this number" that last week's work did not cover. Labelling a figure's state told a customer whether it was measured; this lets them check it. Together they answer the auditor's question — where does this come from — without a call.

The Dropzone case is worth telling in a sales conversation rather than hiding. A customer found a number that was technically correct and practically misleading, and the fix was to name the source in the label rather than to change the figure or quietly drop the column.

## Limits and what's next

**We still only read LinkedIn for hiring.** We already fetch 16 companies' careers pages, including Dropzone's, so the pages are in hand — but nothing yet extracts job listings from them. That is the single biggest gap in hiring data and it is the obvious next piece of work.

**Shared investors is empty for a reason we should fix.** Reading the remaining 19 Crunchbase pages would likely surface real overlap. 45 of 85 companies have no Crunchbase link on file, and the link has to be guessed from the company name.

**Findings is still an evidence feed.** Several articles about one event are still several rows, not one finding with its evidence attached.

**Restricted and public views still name every company.** Limiting which companies a shared report can name is a separate piece of work.

**Currency is not converted on funding totals**, so totals are only comparable where the source currency matches.

**Employer-review matching is still wrong** — every match in this market is a different company with a similar name. Untouched, and it should not be shown or cited.
