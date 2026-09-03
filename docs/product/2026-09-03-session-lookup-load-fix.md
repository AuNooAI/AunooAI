# Pages no longer fail intermittently when a site is busy
_2026-09-03 · All monolith customer sites; fixed live on sunstar, staged on wiley and wileytest_

## What shipped
We fixed a bug that made pages fail at random when a customer site was under load.
The Future Horizons and Consensus tabs on the Sunstar site returned about 90
"Internal Server Error" responses in a 15-minute burst on 3 September; any page on
any busy site could have done the same.

## Why it matters
Before: every page request checks who the logged-in user is with a small database
read. Under heavy traffic — the Foresight tabs poll the server frequently while a
report is open — that read could grab a database connection that was being taken
away at the same moment, and the page failed with a server error. The failures came
in bursts, looked random, and cleared on their own, which is the worst kind of bug
to be shown in front of a customer. After: the read holds its connection until it
has its answer, so traffic level no longer affects it. Analysts feel the
difference as tabs that load reliably during exactly the busy moments (demos,
report generation) when they used to fail.

## Release notes (copy-ready)
- Fixed intermittent "Internal Server Error" responses on busy sites, seen on the
  Future Horizons and Consensus tabs. The login check behind every page could lose
  its database connection mid-read under load; it now holds the connection until
  the read completes.

## Demo / walkthrough
None. The fix removes a failure — there is nothing new to show. The check is that
the Foresight tabs stay error-free while a report generates.

## Positioning notes
None beyond reliability: this closes an "it broke during the demo" class of
failure, which matters most for prospect-facing sites like Sunstar.

## Limits and what's next
Done the same evening: all 162 single-row queries in the shared database layer now
use the safe read pattern, not just the login check — so the whole class of
"random error under load" is closed for single-row reads, verified with a
550-request load test against the live Sunstar site (every request succeeded).
Queries that read many rows at once still use the old pattern; they carry the same
theoretical race and are the natural next batch. Wiley and wileytest have the fix
on disk but keep running the old code until their next restart, and the other
customer sites pick it up at their next sync with canonical.
