# The daily digest now says whether a number actually moved
_2026-09-23 · Brand Watcher — the adverse-media digest email_

## What shipped
The opening paragraph of the daily digest email no longer describes changes that did not happen,
and the employee-signal line now shows what a rating or outlook figure was before, or how long it
has held steady.

## Why it matters
The digest opens with a short written summary above the per-brand detail. That summary is written
from the figures in the email and nothing else.

Until today those figures were all single snapshots — today's Glassdoor rating, today's employee
outlook, with no earlier value to compare against. The summary was still asked to lead with what
had changed most. With no before-value available, this morning's oviva digest reported that one
tracked competitor's employee outlook had dropped "to 14% from an unspecified higher level". That
figure had been unchanged for twenty days. A different brand in the same email had genuinely
moved on both its rating and its outlook, and the summary said nothing about it.

Two things changed. The email now carries the before-value itself, so a line reads "outlook 28%
(was 29% on 09-13)" or "outlook 14% (unchanged 20d)". And the summary is now written only from
changes that are actually stated, so a steady number is reported as steady.

Anyone reading the digest as a morning signal was the one affected. A fabricated drop is worse
than no drop at all, because it is the kind of thing a comms lead repeats in a meeting.

## Release notes (copy-ready)
- The daily digest now shows what an employee rating or outlook figure was previously, and the
  date it changed — or says how long it has been unchanged.
- The digest's opening summary now only describes movement that the underlying figures support.
  Steady numbers are reported as steady.

## Demo / walkthrough
Visible in the digest email itself, under each brand's "Employee signal" line. No dashboard
change. The next digest goes out at the configured hour on each site, 06:00 UTC by default.

## Positioning notes
This is the accuracy line we sell on. The product's claim is that a customer can act on what the
digest says without going and checking it, and a hedge like "an unspecified higher level" is the
opposite of that. Worth knowing about, rather than announcing.

## Limits and what's next
The "unchanged" figure only counts the history we hold. A site whose daily records start twenty
days ago will say "unchanged 20d" even if the number has been flat far longer, and one with a
single day of history says nothing at all. Panaya has one day; Wiley tracks no brands with
employer data, so the line does not appear there.

The fix covers the employee figures, which is where the fabrication came from. News-sentiment
figures in the same email are still compared against the peer average rather than against last
week, so the summary cannot say whether a brand's coverage is improving or worsening over time —
only how it sits against its peers today. That is the obvious next one.

The new summary wording has not yet been seen on a real send. Today's digests had already gone
out when the fix landed, so the first one written the new way is tomorrow morning.
