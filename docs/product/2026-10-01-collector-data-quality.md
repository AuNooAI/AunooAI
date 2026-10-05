# Collection that says what it did not get
_2026-10-01 · Article collection on the monolith sites and the SaaS platform; live on the bugfixing site only_

Audience note: most of this work is below the surface. A customer does not see a checkpoint
table or a quota ledger. What a customer does see, over the following weeks, is fewer missing
articles, fewer wrong dates, and a health page that says when a source has stopped delivering.
This writeup covers that visible part. The engineering detail is in `docs/changes.md` and
`docs/COLLECTOR_DATA_QUALITY_IMPLEMENTATION.md`.

## What shipped
- Every collection run now records whether it finished, how far it got, and why it stopped.
  A source that failed is retried from where it left off instead of being marked done.
- Articles with no publication date are stored as undated and shown by the date we found them,
  instead of being stamped with the current time.
- The same article arriving through two topics, two feeds or two providers is one article with
  both associations, instead of one copy kept and the other thrown away.
- Sites that share one provider key now share one request budget, so one site cannot spend the
  day's quota before the others poll.
- A feed that keeps failing is backed off and flagged for attention instead of being retried at
  full speed forever. A feed with thousands of entries is read 100 new entries an hour.
- A new health page lists failing sources, quota pauses, and topics whose configuration blocks
  analysis, with alerts the existing probe emails.
- SaaS: calendar feeds keep each occurrence as its own event with the right duration; push
  deliveries from feed hubs are stored before being acknowledged, so a hiccup does not lose
  them; short headlines are kept and marked rather than dropped.

## Why it matters
Before, a collector that hit a rate limit, a timeout or a broken feed returned nothing, and the
system treated nothing as "no news". The interval was marked collected and never revisited, so
the articles published in that hour were gone. In one week the logs showed 615 refused NewsAPI
requests, 710 refused NewsData requests and 920 refused Reddit fetches, each one a gap in
coverage that nobody could see. Now the run record says "failed, retry", the next poll replays
the same interval, and the health page shows the gap while it is open.

Before, an article whose feed gave no date was dated "now". A 2023 Bluesky post looked like
today's news; a party's press release looked like it was written when we fetched it. Now the
date is left empty and the article is sorted by when we first saw it, which is honest, and the
raw date text is kept for repair.

Before, when the same story was collected for a second topic it was dropped as a duplicate, so
the second topic never saw it. Now both topics do.

Who feels it: analysts, in fewer silent gaps and fewer articles misdated as new; operators, in a
page that names the broken source instead of a quiet log; the business, in provider spend that
is counted once per key.

## Release notes (copy-ready)
Internal only until the SaaS services are restarted and the other sites carry the change.
- Collection runs are recorded with their outcome; failed or partial intervals are retried from
  where they stopped.
- Articles without a publication date are stored as undated and ordered by discovery date.
- An article collected for several topics or feeds belongs to all of them.
- Provider request budgets are shared across sites that share a key.
- Failing feeds back off and are flagged for attention; large feeds are read in batches of 100.
- New collection health page and probe alerts.
- SaaS: calendar occurrences, hub push deliveries and short headlines are kept.

## Demo / walkthrough
On bugfixing: `GET /api/health/collection` shows the run summary per provider, the quota
ledger, flagged feeds and alerts. Tonight it shows the `rss` provider with one partial run (a
feed with a malformed character), three empty successes and no alerts. There is no page in the
UI for it yet; it is an API endpoint the probe reads.

## Positioning notes
None as a feature. This is reliability work. The one line worth saying to a buyer is that
coverage gaps are now visible and retried rather than silent, and that the system tells you
when a source is broken.

## Limits and what's next
- Live on the bugfixing site only. The SaaS services have not been restarted, and no customer
  site has the schema or the code. Each site's first poll after the change reads every feed's
  archive at 100 new entries an hour, which is paid scraping and analysis time.
- Time-windowed views still leave undated articles out; only the "newest first" orderings were
  fixed to put them last.
- The retry step cannot recover an article whose feed gave only a title, even though the full
  page text was fetched and stored: the analysis step reads the feed's summary, not the stored
  page. 31 such articles on bugfixing will be tried three times and left. Changing what the
  analysis reads is a separate decision.
- No Semantic Scholar API key exists; its requests stay on the shared unauthenticated budget.
- Two Noom feeds on the Oviva site and, until tonight, the Blink feed here returned 403 on every
  poll for a week. Blink is retired; Noom is an operator call.
- The wileytest site has a topic with an empty list that the analysis step requires, so every
  article routed to it fails. Filling the list is a customer configuration change.
- Six provider API parameters were written from documentation memory and need checking against
  the current docs before anyone relies on them; they are listed in the implementation notes.
