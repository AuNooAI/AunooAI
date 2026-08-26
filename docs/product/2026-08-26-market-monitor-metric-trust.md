# Every number on the market page now says whether it was measured
_2026-08-26 · Market Monitor — vendor figures, headcount, quiet vendors, downloadable report_

## What shipped

- Every figure carries a "what this means" panel: the definition, the period, who collected it, how much of the market was reached, and what it does not tell you.
- A zero now only appears when we actually checked and found nothing. Everything else that used to show as zero says what it really is: never collected, still collecting, failed, or only partly done.
- A company is no longer called quiet unless we successfully collected from it. Ones we never reached are listed separately.
- Quiet companies now show when they last posted at any time, not just inside the period you selected.
- The market's total staff headcount is shown for the first time, with the number of companies it covers.
- Headcount growth is now measured between two readings of the same kind. It used to compare a live reading against an imported spreadsheet from April.
- A "Signals" column that added two things that cannot be added has been removed.
- "Growth outlook" is now called "Crunchbase Growth vs Heat", because both numbers are Crunchbase's and neither is a forecast.
- The downloadable report now contains the definitions, the source list and the collection status. It had none of them.

## Why it matters

**A zero used to mean two opposite things.** A company with no posts and a company we had never collected from both rendered as `0`, and nothing on the page separated them. That is the same defect as last week's "no observed activity" count, one level up: it applied to every figure, not just that one tile.

Each figure now carries its own state. On the SOC Automation market today that reads: LinkedIn posts, profiles and jobs fully collected across 82 of 82 companies; funding data partly collected, 20 of 39; website monitoring partly collected, 19 of 82; Indeed not collecting at all, with the reason given. Before, all five of those looked the same from the outside.

Who feels it: anyone about to repeat one of our numbers to someone else. The honest answer to "how do you know?" is now on the page instead of in someone's head.

**"Quiet" was still an accusation we could not support.** Last week's work fixed the tile that counted quiet companies. The list itself was still built from the whole registry, so a company whose collection had never succeeded appeared on it by name. Being named as quiet is worse than being counted as quiet.

Quiet now requires a successful collection for that specific company. On this market that is 18 companies genuinely quiet in the last 30 days and 1 we have not managed to collect, listed on its own. And each quiet company now shows its real last-post date rather than nothing — Almanax last posted on 19 March, which the old panel had no way to say.

**Headcount growth was measuring the wrong thing entirely.** The chart compared each company's current LinkedIn staff count against the figure in the spreadsheet imported in April. Those are two different measurements taken four months apart, so almost every company looked like it had grown or shrunk, and the number told you as much about the spreadsheet as about the company.

Growth now needs two LinkedIn readings, each shown with its own date. That gives exactly **one** company today, because the first full sweep of all vendors only happened this week — 82 of 83 have a single reading so far. That is a much emptier chart and it is the truthful one; it fills as the next weekly sweep lands. The other 82 are listed as awaiting a second reading rather than shown as unchanged, which would have been a claim with nothing behind it.

The spreadsheet comparison is still there, under its own heading, labelled as a different source with a caution that it is a rough direction rather than observed growth.

What is new and available immediately: the market's **observed total headcount, 2,916 people across 80 companies**. That needs only one reading each, so it works today. The company count is shown beside it, because a market total without knowing how much of the market it covers is not interpretable.

**A column was adding two numbers that cannot be added.** "Signals" was a company's posts in the last 30 days plus its currently open job listings. One is a flow over a period, the other is a standing count right now. The sum changes if you change the period, or if a company freezes hiring, and it cannot be read as either thing. It was also deciding the table's sort order. Both are gone; posts, jobs and articles now stand on their own.

**"Growth outlook" implied a forecast we do not make.** Both scores are Crunchbase's own, we cannot reproduce how either is calculated, and "Heat" measures attention a company is getting now rather than predicting anything. The panel is now named after what it shows and says so in the help text.

**The downloadable report was the weakest link.** It had no definitions, no source labels and no collection status — so a report opened a month later gave figures with no way to tell what they had been measured against, and looked more authoritative than the live page. It now ends with a "How to read this report" section carrying the source list, the per-source collection state, every metric definition with its limitations, and the post-classification legend.

## Release notes (copy-ready)

- Every Market Monitor figure now has a "what this means" panel with its definition, period, source, collection coverage and limitations.
- A zero is only shown when collection succeeded and found nothing. Never-collected, in-progress, failed and partly-collected are each labelled as themselves.
- Companies are only listed as quiet when collection succeeded for them. Companies we could not reach appear in a separate "unmeasured" group.
- Quiet companies show their most recent post at any time, not only within the selected period.
- New: observed total market headcount, shown with the number of companies it covers.
- Headcount growth now compares two LinkedIn readings of the same company, each dated. The previous version compared a live reading against the April spreadsheet import.
- Companies with only one reading are listed as awaiting a second rather than shown as unchanged.
- The "Signals" column has been removed. It added 30-day post counts to currently-open job listings, which has no defensible meaning.
- "Growth outlook" is now "Crunchbase Growth vs Heat", with a note that both are Crunchbase's own scores and neither is a forecast.
- The downloadable HTML report now includes metric definitions, the platform and provider list, per-source collection status, and the post-classification legend.

## Demo / walkthrough

Market Monitor → SOC Automation → Collection → Sources & Health. The new "Can these numbers be believed?" table lists every source with its state and how many companies it reached. Below it, "Where coverage comes from" separates the platform something was published on from the provider we collected it through.

Then Analysis → the share-of-voice panel: "Quietest — collected, and said nothing" now shows last-post dates, with the unmeasured company below the dashed line. Any figure with a `?` beside it opens its definition.

Download the report from the market header and scroll to "How to read this report".

## Positioning notes

Last week's release could answer "how do you know these companies are quiet?" for one tile. This applies the same standard to every number on the page, and to the report we hand out.

That matters most for the report, which is the artefact that leaves the building. Until today it was the least qualified version of our data — no definitions, no coverage, no dates — while looking the most final. A customer could not audit it even if they wanted to.

## Limits and what's next

**Headcount growth is nearly empty and will look worse before it looks better.** One company has two readings. This is correct rather than broken, but anyone demoing the page should know why the chart is bare and should say the second sweep fills it.

**The market headcount total is a floor, not a total.** It counts the 80 companies with an exact reading. Three have no exact figure, and a company size band is deliberately never counted as a number.

**"No observed activity" is still not split into measured-and-empty versus never-measured.** The quiet list now makes that distinction; the tile on the vendor table does not yet.

**Most figures still lack the drill-down.** Clicking an aggregate should open the exact records behind it. That exists for some figures and not others, and the definition panel does not yet link to the records.

**Findings are still an evidence feed, not findings.** The page lists collected posts and articles rather than clustering several reports of one event into a single conclusion with its evidence attached.

**Restricted and public views do not yet limit which companies are named.** A shared market report shows the full roster. Limiting that per viewer is a separate piece of work and it is access control, not presentation.

**Employer-review matching is still wrong** — all four matches in this market are a different company with a similar name. Untouched, and the data should not be shown or cited.
