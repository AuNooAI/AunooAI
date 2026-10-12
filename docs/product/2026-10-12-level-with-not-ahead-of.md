# A zero is level with the market, not ahead of it
_2026-10-12 · Market Monitor vendor pages, all sites with a market_

## What shipped
- A vendor with no open roles in a market where most vendors have none now reads "level with 77 other vendors at none" instead of "ahead of 39% of the vendors measured".
- Yesterday's collection fixes (every vendor read on every run, job boards found from the site's own careers link, undisclosed rounds labelled as such, press coverage scored, look-back posts dated when the news happened) are now on every customer site with a market: abm, aisecurity, Oviva, Panaya and Sunstar.

## Why it matters
A percentile is a position in a ranking, and a tie sits in the middle of the group it shares. That is correct arithmetic and the wrong sentence: a reader comparing two vendors with no hiring saw one "ahead of" the other. The page now says what the number means, that the vendor shares the floor with most of the market. Analysts comparing early-stage vendors on hiring see the comparison they would make themselves.

The second item is reach. The scheduler and discovery fixes went live on aisocnews.com last night. The other sites run the same code and had the same gaps in a smaller form, so each now reads its whole vendor list on every run and finds job boards wherever the company links to them.

## Release notes (copy-ready)
- Vendors with no listings are described as level with the others at zero, not ranked ahead of them.
- Every market site now collects every vendor on every run and finds job boards from the company's own careers link.

## Demo / walkthrough
Market Monitor, any market, open a vendor with no open roles. "Observed active job listings" reads 0 and the line under it says how many other vendors share that.

## Positioning notes
None beyond yesterday's note: the page says what its numbers mean.

## Limits and what's next
- A careers board that cannot be read no longer stalls the whole daily job-board sweep into a ten-minute loop; the board is skipped and retried later, and the other boards' listings count as before.
- Only a zero gets the "level with" wording. A tie at any other value still reads as a percentile, which is acceptable because ties above zero are rare and small.
- The other sites' internal vendor page keeps the old labels ("Series Unknown", "import said", "ahead of") until their interface is next rebuilt; their public report page already says "Undisclosed round".
- Sunstar's restart was still waiting for a quiet moment when this was written.
