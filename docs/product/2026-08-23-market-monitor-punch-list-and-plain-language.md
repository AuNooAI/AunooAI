# Market Monitor: the punch list, one period control, and words a brand manager can read

_2026-08-23 · Market Monitor (Explore tab), internal development tenant only_

## What shipped
- Events on the Pulse dashboard are now clickable and expand to show the articles behind them,
  the same way they already did on the Wire tab.
- A new "Top posts, articles & news" section on Pulse shows what's actually being read and
  shared about the market, ranked by engagement.
- An internal collector name (`xpoz:`) that was leaking into the visible source list is gone;
  readers see the outlet name only.
- Funding-round stages now list in order (seed, then Series A, B, C...) instead of sorted by
  how many vendors are in each one.
- A score that hadn't changed used to show a bare "0" — indistinguishable from a company whose
  actual score is zero. It now says "unchanged".
- One period selector (7/30/90/365 days) now controls the whole dashboard. Before, three
  different tabs quietly used three different, undisclosed time windows.
- Two lists — recent career moves and Crunchbase score changes — used to appear twice, once on
  Pulse and again on the Coverage tab, verbatim. They now live in one place, with a link from
  the other.
- A downloadable HTML report of the market can now be shared standalone and shows the same
  panels the live dashboard does. Before, several sections that were live in the app were
  missing from the file you'd actually hand someone.
- Share of voice can now be viewed as a pie chart as well as a bar chart. The two panels next to
  it — who posts the most, and who gets the most attention when they do — now rank every vendor
  top-to-bottom instead of just naming the top handful.

## Why it matters
This dashboard exists so someone tracking a competitive market — a product manager, an analyst,
a brand or marketing lead — can see who's moving and why, without reading raw Crunchbase exports
or LinkedIn scrapes themselves. Every item above was a place where the tool undercut that job:
an unclickable event hides the evidence behind a claim; two different silent time windows on the
same page make numbers look inconsistent when they're not comparable; a name like `xpoz:` in the
source list tells the reader "this is a tool, not a briefing." None of these are big ideas —
they're the difference between a dashboard someone trusts on first use and one they have to
learn to work around.

The plain-language pass, done separately after direct feedback that the rewritten copy still
read like one analyst briefing another, matters more. "Score changes during the reporting
period — consecutive Crunchbase readings that changed" tells a marketing manager nothing they
can act on. "Who's getting more attention or momentum" does. The Crunchbase mechanics (which
score, how it's measured, how often it updates) didn't disappear — they moved into a hover
tooltip, for the reader who wants to check the math, instead of sitting in the reader's way.

## Release notes (copy-ready)
- Pulse events are now clickable and show their source articles.
- New "Top posts, articles & news" panel on Pulse.
- Internal source-collector names no longer appear in the visible source list.
- Funding stages list in round order.
- A zero-change score now reads "unchanged" instead of a bare "0".
- One period selector (7/30/90/365 days) now controls Pulse, Analysis, and Coverage together.
- Career moves and score changes no longer appear twice across tabs.
- The downloadable HTML report now matches what the live dashboard shows.
- Share of voice has a pie-chart view; the "who shouts loudest" and "top voices" panels now
  rank every vendor, not just a handful.
- Panel names and captions rewritten in plain business language; Crunchbase-specific detail
  moved into tooltips.

## Demo / walkthrough
Explore → Market Monitor → Pulse. Click any event card to expand its source articles. The
period selector sits next to the tab bar and applies to Pulse, Analysis, and Coverage. The
Analysis tab's Share of voice panel has a bar/pie toggle in its top-right corner.

## Positioning notes
None of this is a new capability — it's the difference between a dashboard that demos well and
one a customer would actually adopt for daily use. The plain-language pass in particular is the
kind of detail that decides whether a non-technical buyer trusts the tool on a first look or
dismisses it as "built for analysts."

## Limits and what's next
- Market Monitor exists only on the internal development tenant (bugfixing.aunoo.ai) right now
  — it has not shipped to any customer-facing site. Everything here is pre-launch polish, not a
  live-customer fix.
- Formation and Funding panels stay all-time regardless of the period selector, by design —
  they describe the market's current makeup, not activity in a window — but this is a judgment
  call worth revisiting if a real customer finds it confusing rather than obvious.
- The pie-chart view for Share of voice is capped at 3 named vendors plus an "Other" bucket,
  because that's as many distinct colors as can be told apart reliably by a colorblind reader
  in a pie (checked against this team's accessibility validator). A market with many vendors a
  reader wants to compare individually is still better served by the bar view.
