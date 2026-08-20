# Market Monitor: an overview screen, category coverage, judged vendor posts, and all the data
_2026-08-20 · Explore → Market Monitor; public RSS feed_

## What shipped

- **An overview screen.** One page that says what state the market is in: how many vendors are
  watched, how much money is in them, who is active, how coverage runs week by week, and when
  each source last ran.
- **Coverage from our own archive.** The monitor now finds articles we already collected that
  are about the category, even when they name none of the tracked vendors.
- **Vendor posts get read and judged.** Every LinkedIn post a tracked vendor publishes is read
  once and marked as either stating a fact, offering commentary, or saying nothing.
- **A Data screen.** Every table the monitor writes to, with row counts and a spreadsheet
  download for each.
- **A working feed** that aggregates the market's coverage, with every item labelled by the kind
  of source it came from.

## Why it matters

**The overview.** Opening the market monitor used to show a brief — a list of what changed in
the last seven days. That is useful once you know the market. It is no use as a starting point,
because the reader had to reconstruct the standing picture from a list of recent events. The
first thing on screen is now the standing picture. An analyst can answer "how big is this market
and who is moving in it" without reading anything else.

One number on it is worth calling out. 62 of the 82 in-scope vendors currently produce no signal
at all — no posts, no job listings, no press coverage. That is a finding about the market, not a
gap in our collection, and it was invisible before.

**Coverage from our own archive.** The old behaviour: an article was linked to this market only
if it named one of the tracked companies. So an article about security teams adopting AI triage,
which named no vendor, was collected, stored, analysed — and then never appeared anywhere in the
market monitor. We were paying to collect context and throwing it away at the point of use.

The monitor now also matches on the language of the category itself: "SOC automation", "agentic
SOC", "security operations centre", "alert triage" and a dozen more. The first run found 348
relevant articles and **282 of them had been collected for entirely different topics**. That is
the answer to "are we searching our own news" — we are now, and four fifths of what it found was
already sitting in the database unused.

The word list is curated rather than broad, for a reason worth knowing. We tested widening it to
bare industry acronyms. "SOAR" matched "US Bible Sales Soar" and "Japan Bond Yields Soar To
Record". "MDR" matched papers on multidrug-resistant tuberculosis. Those two terms alone produced
about 240 wrong matches, so they are excluded. An overview built on noisy coverage is worse than
no overview.

**Judged vendor posts.** This is the change with the most in it. Tracked vendors had published
562 LinkedIn posts against 122 news articles about the whole market. Used as they were, they
buried everything, so we were leaving them out entirely — and losing the launches, funding
rounds, customer wins and senior hires that vendors announce on LinkedIn first and often nowhere
else.

No keyword rule separates the two. These two posts are the same shape:

> Dropzone AI is a 2025 IA40 winner, two years in a row.
>
> If you're at the Gartner Summit today, come meet the team at booth 4141.

So every post is now read once and given a verdict. Of the 562: **107 state a real fact**, 145
are commentary worth reading, and 310 are conference notices, employee spotlights and hype. The
107 include 42 product launches, 16 partnerships, 14 awards, 11 named customers, 9 hires, 2
funding rounds and 1 acquisition. Real examples it found: a partnership with Wiz, a partnership
with Anthropic, a named CISO at Virgin Money as a customer, a Black Hat competition win.

Only those 107 reach the feed, the timeline and the reporting agents. The other 455 stay out of
the way but remain visible on request, so nothing is deleted — it is filed.

**The Data screen.** The monitor writes to eight tables and the interface showed two. "Where can
we see all of the data" was a fair question with no answer. There is now a screen listing every
dataset with its row count and last-updated time — vendors, articles, posts, LinkedIn readings,
funding readings, job listings, watched web pages, collection runs, and open data questions —
each with a preview and a full spreadsheet download.

**The feed.** It had two problems. It required a browser login, which no feed reader has, so
anyone who subscribed got an error message instead of a feed. And it carried only timeline
summaries — four items in total — rather than the market's actual coverage.

It is now an aggregator. Every article and judged post the monitor finds appears in it, linked
to the original publication and sorted by date. Every item is labelled with the kind of source it
came from: third-party news, a vendor's own blog, a vendor's LinkedIn post, or academic research.

That labelling matters more than it sounds. Of the market's coverage, well over half is vendors
talking about themselves. A feed that mixed that in unlabelled would read as independent
corroboration of claims that have none.

## Release notes (copy-ready)

- New **Overview** screen for a tracked market: vendors watched, funding totals, largest raises,
  most active vendors, coverage by week, and the state of every collection source.
- New **Coverage** screen showing articles from across the whole archive that are about the
  market's subject, with the phrases that matched each one and filters by source kind.
- Market monitors now find relevant articles that name no tracked vendor. On the SOC Automation
  market this added 282 articles that were already collected but previously unused.
- Vendor LinkedIn posts are now read and sorted automatically. 107 of 562 posts were found to
  announce something real — launches, partnerships, customers, hires, funding — and only those
  reach reports and feeds.
- New **Data** screen: every dataset the monitor holds, with row counts and CSV download.
- The market RSS feed now works in a normal feed reader and carries the market's coverage, each
  item labelled news, vendor blog, vendor post or research. It previously required a browser
  login and held four items.

## Demo / walkthrough

Explore → Market Monitor. It opens on **Overview**.

- **Coverage** shows the matched articles. "Rescan corpus" re-runs the phrase match; "Review
  vendor posts" reads any posts that have not been judged yet. Both also run themselves daily.
  Filter by source kind, or tick "Include posts judged noise" to see everything.
- **Data** lists every dataset. Click one to preview it, or take the CSV.
- The **RSS feed** button on Brief and Coverage gives a subscribable URL that needs no login.

## Positioning notes

The distinction this closes is between brand monitoring and market monitoring, and it is a real
one. Brand monitoring answers "who was mentioned". Market monitoring answers "what is happening
in this category" — a question that has to include the articles that mention nobody. Most tools
in this space do only the first and describe it as the second.

The vendor-post judging is the part with no obvious equivalent elsewhere. Competitors either
ingest vendor social feeds raw, which produces a marketing firehose, or exclude them, which
loses the announcements. Reading each post once and filing it is a middle option, and it is
cheap because the judgement is stored rather than re-made on every query.

## Limits and what's next

- **The market produces little news.** Only 16 articles about it were published in the last 30
  days. The reporting agents see a small number of articles no matter how the search is written.
  This is the honest size of the market's public footprint, not a collection failure, and it is
  the reason vendor posts matter so much here.
- **The phrase list is hand-written per market.** It works because an analyst knows their
  category's vocabulary, but it will miss language that emerges after the list is written. There
  is no automatic term discovery.
- **Matching reads headlines and summaries, not full article bodies.** A category discussed only
  in the fifth paragraph is missed.
- **Post judgements are not reviewed by a person.** They were spot-checked and corrected once
  during this work, and the current results read well, but there is no way in the interface to
  overturn a verdict you disagree with. That is the obvious next addition.
- **76 relevant articles are still unanalysed.** They were collected for other topics and matched
  this market's phrases, but recovering them would reassign them away from the topics that
  collected them. That trade needs a decision before it is made.
- **The market's event list is still empty.** Scored, vendor-linked events — "this vendor raised",
  "this vendor was acquired" — were specified and never built. With 2 funding rounds and an
  acquisition now sitting in the post verdicts, there is finally real material to build it from.
