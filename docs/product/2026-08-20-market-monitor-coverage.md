# Market Monitor: the overview screen, category coverage, and a working feed
_2026-08-20 · Explore → Market Monitor; public RSS feed_

## What shipped

- **An overview screen.** One page that says what state the market is in: how many vendors are
  being watched, how much money is in them, who is active, what the coverage looks like week by
  week, and when each source last ran.
- **Coverage from our own archive.** The monitor now finds articles we already collected that
  are about the category, even when they name none of the tracked vendors.
- **A working feed that aggregates the market's news**, with every item labelled by
  what kind of source it came from.

## Why it matters

**The overview.** Before, opening the market monitor showed a brief — a list of what changed in
the last seven days. That is useful once you know the market. It is no use at all as a starting
point, because a reader had to reconstruct the standing picture from a list of recent events.
Now the first thing on screen is the standing picture. An analyst can answer "how big is this
market and who is moving in it" without reading anything else.

One number on it is worth calling out: 62 of the 82 in-scope vendors currently produce no signal
at all — no posts, no job listings, no press coverage. That is a finding about the market, not a
gap in our collection, and it was invisible before.

**Coverage from our own archive.** The old behaviour: an article was only linked to this market
if it named one of the tracked companies. So an article about how security teams are adopting AI
triage, which named no vendor, was collected, stored, analysed — and then never appeared
anywhere in the market monitor. We were paying to collect context and then throwing it away at
the point of use.

The monitor now also matches on the language of the category itself: "SOC automation", "agentic
SOC", "security operations centre", "alert triage" and a dozen more. On the first run this found
348 relevant articles, and 282 of them had been collected for entirely different topics. That is
the answer to "are we searching our own news" — we are now, and four fifths of what it found was
already sitting in the database unused.

The word list is curated rather than broad, for a reason worth knowing. We tested widening it to
bare industry acronyms. "SOAR" matched "US Bible Sales Soar" and "Japan Bond Yields Soar To
Record". "MDR" matched papers on multidrug-resistant tuberculosis. Those two terms alone
produced about 240 wrong matches, so they are excluded. Precision here is deliberate: an
overview built on noisy coverage is worse than no overview.

**The feed.** Two problems. It required a browser login, which no feed reader has, so anyone who
subscribed got an error message instead of a feed. And it only carried timeline summaries — four
items in total — rather than the market's actual coverage.

It is now an aggregator. Every article the monitor finds appears in the feed, linked to the
original publication, merged with the timeline events and sorted by date. It works without a
login for markets marked public, and SOC Automation is marked public.

Every item is labelled with the kind of source it came from: third-party news, a vendor's own
blog, a vendor's LinkedIn post, or academic research. This matters more than it sounds. Of the
348 articles found, 152 are vendor LinkedIn posts and 58 are vendor blog posts — so 60% of the
market's "coverage" is the vendors talking about themselves. A feed that mixed those in
unlabelled would read as independent corroboration of claims that have none. Vendor LinkedIn
posts are left out of the feed by default for the same reason; they can be switched back on.

## Release notes (copy-ready)

- New **Overview** screen for a tracked market: vendors watched, funding totals, largest raises,
  most active vendors, coverage by week, and the state of every collection source.
- New **Coverage** screen showing articles from across the whole archive that are about the
  market's subject, with the phrases that matched each one and filters by source kind.
- The market RSS feed is now an aggregator: it carries every article the monitor finds, linked
  to the original publication, with each item labelled news, vendor blog, vendor post or
  research.
- Market monitors now find relevant articles that do not name any tracked vendor. On the SOC
  Automation market this added 282 articles that were already collected but previously unused.
- The market RSS feed now works in a normal feed reader. It previously required a browser login.

## Demo / walkthrough

Explore → Market Monitor. It opens on **Overview**. Click **Coverage** for the matched articles;
the **Rescan corpus** button re-runs the match on demand, though it also runs itself once a day.
The **RSS feed** button on the Brief view now produces a subscribable URL.

## Positioning notes

The distinction this closes is between brand monitoring and market monitoring, and it is a real
one. Brand monitoring answers "who was mentioned". Market monitoring answers "what is happening
in this category" — a question that has to include the articles that mention nobody. Most tools
in this space only do the first and describe it as the second.

## Limits and what's next

- The phrase list is hand-written per market. It works because a market analyst knows their
  category's vocabulary, but it will miss language that emerges after the list is written. There
  is no automatic term discovery.
- Matching reads the headline and summary, not the full article body. A category discussed only
  in the fifth paragraph is missed.
- Scoring is a weighted count of matched phrases. It ranks reliably but it is not a relevance
  model, and it cannot tell a substantial article from a passing reference that happens to use
  the right words twice.
- The market's event table (`bw_market_events`) is still empty. Scored, vendor-linked events —
  "this vendor raised", "this vendor was acquired" — were specified and have not been built, so
  the Wire currently shows timeline summaries rather than discrete market events.
- 27 articles in the market's collection topic have never been assessed for relevance. Unrelated
  to this work, and still unexplained.
