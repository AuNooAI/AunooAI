# The Gather page no longer errors while the platform is busy collecting news
_2026-08-11 · Gather: keyword group summary cards_

## What shipped
- Fixed the error that made the Gather page fail with a technical message ("canceling
  statement due to statement timeout") on the busiest customer site. The statistics
  behind the keyword group cards now compute in about 1–2 seconds instead of 14 or more,
  so they finish well inside the safety limit even during heavy news collection.

## Why it matters
Gather is where an operator checks how each monitored keyword is performing. Before, on
a site ingesting thousands of articles a day, opening it during a collection run could
fail outright — the exact moment an operator most wants to look is the moment the page
broke. The computation was doing redundant de-duplication work over a million rows; the
data guarantees made that work unnecessary, and removing it made the page reliable
without loosening any safety limit.

## Release notes (copy-ready)
- Fixed: the Gather page could fail with a timeout error during heavy news collection.
  Keyword statistics now compute several times faster and load reliably.

## Demo / walkthrough
Open Gather. The keyword group cards with per-keyword relevance statistics load without
error, including while a collection run is in progress.

## Positioning notes
None. Reliability fix to an existing page; nothing new to position.

## Limits and what's next
- The group summary can still take ~20–30 seconds right after a service restart, while
  startup work competes for the database. It completes rather than erroring. The other
  queries in that page load are the follow-on candidate if it still feels slow.
- Emails or pages already showing the old error are transient; a reload gets the fix.
