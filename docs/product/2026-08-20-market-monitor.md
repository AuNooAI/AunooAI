# Market Monitor: track a whole vendor market, not one brand at a time
_2026-08-20 · Explore → Market Monitor (new tab), API, RSS_

## What shipped

**Tracked markets.** You can now point the platform at a whole competitive market rather than at
individual brands. The first is SOC automation: 83 vendors imported from an analyst spreadsheet,
82 of them in scope.

**A registry that questions its own data.** The import flags what it cannot safely decide instead
of guessing — a name that might be a former name, a funding figure that is missing rather than
zero, two companies that share one LinkedIn page. Those become review tasks with the source row
attached.

**Continuous collection.** The market gathers news about the category, the vendors' own blogs and
websites, their LinkedIn posts and company profiles, their funding records and their job
listings. Each source runs on its own schedule, from twice a day to monthly.

**New entrants found automatically.** The system reads the funding coverage it already collected
and proposes companies that are not yet in the registry, with the article that named them.

**Three outputs.** A downloadable spreadsheet of the whole market, an RSS feed of what changed,
and a brief with charts.

## Why it matters

**Before, tracking a market meant configuring 80 brands by hand.** Each one needed its own
keywords, its own collection setup, and its own dashboard. Nobody does that for a market of 80
companies, so markets went untracked. Now it is one spreadsheet import and one question.

**A registry goes stale the day it is built.** Vendors raise money, get acquired, rebrand and
appear from nowhere. The system watches the funding coverage and tells you who is missing, so the
list stays current without someone re-doing the research each quarter.

**Bad data used to become a confident wrong answer.** Two companies in this registry shared a
LinkedIn page. Left alone, that would have reported one of them shrinking by 85% — a number that
looks precise and is fiction. The import caught the clash at load time and named both companies,
and the correction took minutes rather than being discovered by a customer.

**Cost is bounded on purpose.** You choose which vendors are worth paying to follow — all of
them, only the funded ones, or a hand-picked set. The market currently watches 38 of 83.

Who feels it: the analyst who wants a market brief without a fortnight of desk research, and the
operator who has to answer for what the platform spends.

## Release notes (copy-ready)

- New **Market Monitor** tab: track a whole vendor market from one imported registry.
- Import a vendor spreadsheet; anything ambiguous becomes a review task instead of a silent guess.
- Collect category news, vendor blogs, website changes, LinkedIn posts and profiles, funding
  records and job listings — each on its own schedule.
- New entrants are proposed automatically from funding coverage, with sources attached.
- Download the market as a spreadsheet, subscribe to it as an RSS feed, or read the brief.
- Choose which vendors are watched — all, funded only, or your own selection.

## Demo / walkthrough

Explore → **Market Monitor**. Three tabs.

1. **Brief** opens first: what changed, headcount movement, who is posting most, and what is
   still unresolved. "Download dataset" and "RSS feed" are top right.
2. **Wire** is the running timeline of market developments.
3. **Vendors** is the registry. Three segments: all of them, the ones needing review, and new
   entrants found in funding coverage. Click any vendor to open its own page — identity and where
   each fact came from, funding and backers, headcount against the imported figure, the pages we
   watch and what changed on them, its recent posts, and its coverage. The vendor page has its own
   link, so you can send someone a company.
4. **Settings** (top right) holds what the market searches for, which sources run and how often,
   and whether each one is healthy.

## Positioning notes

This moves the product from "monitor your brand" to "monitor your market", which is a different
buyer conversation — competitive intelligence and analyst teams rather than communications.

The honest differentiator is not coverage, it is refusal to guess. Every competitor can scrape a
vendor list. The review queue, the funding states kept distinct from zero, and the identifier
clash that got caught before it became a chart are what make the output defensible in front of
someone who knows the market.

## Limits and what's next

**Per-vendor pages are new and thin in places.** Clicking a vendor opens everything we hold about
it — identity, funding, headcount, the pages we watch, its posts and its coverage. Some panels are
still empty for most vendors because the sources behind them have only run once, or not yet.

**Most charts need a second reading before they mean anything.** Headcount is collected weekly, so
a vendor has one data point until the next run. The page shows the number and the date rather than
drawing a line through a single point, and says when the next reading is due.

**Funding amounts are not filled in.** The funding source we added gives round counts, investor
names and momentum scores but carries no dollar figures. 42 vendors still show "Undisclosed",
which is the truthful answer, not a gap we can close from this source.

**Crunchbase links are guessed.** Roughly two in three vendor pages resolve from the company
name. Misses are recorded as unverified rather than retried blindly, but they need correcting by
hand.

**The market brief is assembled, not written.** It reports what changed and who moved. An
observer agent has been set up against the market to produce a written brief on a schedule, but
it is not switched on yet.

**Hiring data is not available.** Job listings were part of the plan and the provider's dataset
does not support collecting them per company in any form we could get working. Every other source
— news, vendor websites, LinkedIn posts and profiles, funding — is running.

**Relevance tuning now works per market.** Each market can set how strict its own relevance
filter is, rather than inheriting one platform-wide setting. Loosening it for the SOC automation
market recovered the general AI SOC and security-operations coverage that was being discarded.
Other markets and topics are unaffected unless they set their own.

**One market so far.** The design is meant to be reusable by importing a different registry, but
that has not been tried.
