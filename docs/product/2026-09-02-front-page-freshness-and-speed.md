# The market front page now reads newest-first, loads fast, and can't be fooled by re-dated posts
_2026-09-02 · aisocnews.com — the public AI-in-the-SOC market page and its section pages_

## What shipped
- Every card on the front page lists its items newest first. Section pages open in date
  order too, with a "Ranked" toggle for the old importance order.
- The top story is now always recent: the page leads with the highest-ranked development
  from the last 7 days. In a quiet week it falls back to the best older story rather than
  showing nothing.
- The hiring card shows every qualifying recruiter. Vendors outside the public view appear
  as "a vendor not shown in this view" with their numbers kept, so the card's totals
  (157 open roles across 20 of 87 vendors) finally match its rows.
- The page loads in well under a second for almost every reader. Repeat views come from a
  90-second cache in 16–51 ms (measured 2 Sep); a cold build dropped from 3.3–5.1 s to
  about 2.3 s.
- A vendor re-dating its old blog posts can no longer plant them as news. When Dropzone
  re-served a January post with a 1 September date, it briefly led the page; the feed
  checker now catches batches as small as two re-dated posts and bounds their dates
  against the Internet Archive's first sighting.
- The full public report no longer errors when a vendor outside the public view has a
  headcount change (the 500 readers saw on 2 Sep, fixed the same day).
- The Market Maturity Map recomputes itself daily instead of waiting for someone to press
  the button.

## Why it matters
Readers kept meeting the same complaint in different clothes: the page looked stale or
wrong even when the data behind it was fresh. Cards opened with August items above
September ones because "important" outranked "new". The lead story could be a week old.
A re-dated vendor post could sit on top as if it broke yesterday. Each of these is now
fixed at the source, so the page earns the daily-read habit its traffic is starting to
show (1,230 distinct readers in the first 5 days, roughly 1 in 10 returning).

The hiring change also closes a trust gap: the card claimed 157 open roles but listed
three vendors. Now the list accounts for everyone, and the masked rows show honestly that
some names are withheld from the free view rather than pretending they don't exist.

## Release notes (copy-ready)
- Front page and section lists are ordered by date, newest first; sections keep a
  "Ranked" toggle.
- The top development is always from the last 7 days when the market has one.
- The hiring table lists all qualifying vendors; names outside the public view are masked,
  their numbers kept.
- Faster page loads: repeat views are served from cache in tens of milliseconds.
- Publication dates are verified against the Internet Archive when a feed re-dates its
  archive, so re-published old posts don't surface as news.

## Demo / walkthrough
Open https://aisocnews.com/ — the top story carries a date within the last week. Open
Market moves → the list starts with the newest item and the "Order" toggle sits above it.
The hiring card's "All 11 →" now matches its header numbers, with masked rows visible.

## Positioning notes
A market page that orders by editorial importance looks curated but stale; ordering by
date with a rank toggle keeps the daily-visit reason intact. Date verification against an
outside archive is something vendor-run news pages don't do — it protects the page from
the vendors it covers.

## Limits and what's next
- The date check only runs for pages we've never seen before and only when at least two
  items in a feed carry dates within 15 minutes of each other. A vendor re-dating a
  single post slips through; the Internet Archive must also have crawled the page for the
  check to bite.
- Cached pages mean a content change takes up to 90 seconds to reach readers.
- The two corrected Dropzone posts were fixed by hand in the database; the checker
  prevents recurrence, it does not re-audit the back catalogue.
