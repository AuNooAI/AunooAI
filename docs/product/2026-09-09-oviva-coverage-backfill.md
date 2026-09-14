# Oviva's press history is in the corpus, and body-text mentions are now found
_2026-09-09 · Brand Watcher on oviva.aunoo.ai: news collection_

Audience note: this covers one customer site. The setting change is worth
offering to the other Brand Watcher customers; the backfill itself was a
one-off.

## What shipped
- A 12-month catch-up of news coverage for Oviva and its seven tracked
  competitors, so the site no longer starts on 3 September.
- News search on the Oviva site now looks inside the article body, not only
  the headline and summary.

## Why it matters
Before today, a reporter could write three paragraphs about Oviva and the
site would miss the article unless "Oviva" appeared in the headline or the
one-line summary. That is how the €200M funding round, the Salesforce
Switzerland announcement and the sick-days study, all of which name Oviva in
the body, were absent. The pilot users who log in this week would have seen
a brand with no history.

Now the corpus holds those stories, and every future collection cycle
searches the full text. The people who feel this are the Oviva strategy
team doing their first pass through the site, and whoever runs the training
session: there is something to show.

One caveat for that demo. Most of the recovered stories mention Oviva in
passing, and the AI relevance check filed them as background rather than
approved brand coverage. They appear in search, not in the brand's headline
counts. The €200M round is the exception and shows as approved.

## Release notes (copy-ready)
- Oviva: news coverage from the last 12 months added for Oviva, Second
  Nature, Numan, Voy, Juniper, Noom and WeightWatchers.
- Oviva: news search now matches brand mentions anywhere in an article, not
  only in the headline or summary.
- Social monitoring is collecting again after the provider top-up.

## Demo / walkthrough
Log in to oviva.aunoo.ai, open Brand Watcher, pick Oviva, and search for
"200 Millionen" or "Salesforce". The German funding-round story from
deutsche-startups.de (22 January) shows as approved coverage. Switch the
date range to the full year to see the rest.

## Positioning notes
None. This closes a gap in our own configuration; it is not a capability
competitors lack.

## Limits and what's next
- The other four Brand Watcher sites (abm, wbm, wiley, wileytest) still
  search headline and summary only. Same one-line change and a restart each
  if we want body-text matching there.
- The relevance check treats a passing mention as not-about-the-brand. For
  a small brand like Oviva that is most of its coverage. Whether passing
  mentions should count as brand coverage is a product question, not a bug.
- The manual "check now" button on Oviva's German topic still searches in
  English until the 8 September fix reaches that site.
- Oviva's own social footprint is thin: of the posts the provider returns
  for "Oviva", almost all mention it only in a hashtag and are dropped.
