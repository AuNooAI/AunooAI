# Market Monitor rebuild: dark mode, number-correctness, and a simpler navigation

_2026-08-24 · Market Monitor (Explore tab), internal development tenant only — no customer-facing
surface yet. Not for external distribution; this is a status note on work in progress. Covers all
five phases of the rebuild: dark mode, backend correctness, a shared "not enough data" gate, the
Pulse summary / Wire period-selector fixes, and a navigation rebuild replacing seven tabs with
four._

## What shipped
- Dark mode now works correctly across all of Market Monitor. Before this, switching to dark
  mode left KPI values, panel titles, tab labels, and most chart text rendering dark-on-dark —
  effectively invisible.
- Every chart (coverage, sentiment, headcount, funding, vendor activity) now recolors correctly
  in dark mode instead of keeping its light-mode colors on a dark background.
- The vendor count now agrees with itself everywhere on the page. Before, the same market could
  show 83 vendors in the header, 84 in the vendor list, and "39 of 84" in a different panel — all
  on the same screen, all technically defensible individually, but confusing side by side.
- A day with an unusually large amount of coverage no longer produces a next-day "average" that's
  lower than it should be — the count used for "today" and the count used for the trailing
  average now come from the same population of articles.
- The sentiment trend chart now actually responds to the date-range selector, instead of always
  showing a fixed six months regardless of what the reader picked.
- "Quietest vendors" now shows vendors that are genuinely quiet (no LinkedIn activity), instead
  of the bottom end of the "loudest vendors" list, which is a different thing.
- Share of voice no longer turns a handful of mentions into a misleading percentage — a market
  with too few total mentions to make a percentage meaningful now says so instead of drawing a
  bar chart out of single-digit counts.
- The "top voices" table is now ranked by actual reader engagement (likes, comments, reposts),
  not by how many times an account posted.
- "Most active vendors" now shows every vendor in the market, ranked by real audience coverage,
  instead of a fixed top 10 selected by a different, less meaningful measure.
- Long lists on the Pulse tab (most active vendors, events, top articles, source runs, largest
  raises) now scroll inside their own panel instead of stretching the whole page — table headers
  stay visible while a long table scrolls.
- Panels that don't have enough data to draw a trustworthy chart — a headcount trend with one
  reading, a funding-momentum chart with one month, an investor-overlap list of one — now collapse
  into a single labeled line in a shared "Not enough data yet" section, instead of each drawing
  its own empty or misleading chart at full size.
- Fixed a layout bug where three panels sharing a two-column grid always left an empty gap next
  to the third one, regardless of how much data it had.
- The Pulse summary paragraph now names the actual vendors and companies involved in a market
  shift, instead of sometimes saying the underlying data "does not specify" who was involved —
  even when the very events list on the same page names them.
- The Wire tab (raw event feed) now respects the same date-range selector as the rest of the
  dashboard, instead of always showing the 50 most recent events regardless of what range is
  selected.
- Navigation is now four tabs instead of seven: Findings, Collection, Reports, and Vendors.
  Findings is everything about the market itself — the old Pulse tab and the old Analysis tab,
  together in one place, since a reader had to visit both to get the full picture before.
  Collection is everything about the data pipeline — health, sources, the raw article and event
  feeds, dataset export — with its own sub-tabs, so a reader focused on the market never has to
  scroll past crawler status to get to it.
- The four counters that used to sit permanently at the top of the page regardless of which tab
  was open (vendor count, collecting, open reviews, no-LinkedIn) — mostly pipeline information —
  now live inside Collection, where they belong next to the rest of the pipeline detail.
- Added a count-reconciliation table inside Collection that shows, in one place, why the vendor
  count can legitimately differ across the app (some counts include vendors marked excluded,
  some don't) — instead of that being a silent discrepancy a reader had to notice and wonder about.

## Why it matters
This dashboard exists so someone tracking a competitive market can trust the numbers on the
screen without checking them against the raw data first. Every item above was a place where two
numbers that should have agreed didn't — which is the fastest way to make a reader stop trusting
the whole page, not just the one panel that looked wrong. None of these are new capabilities;
they're fixes to numbers and colors that were already supposed to be right.

## Release notes (copy-ready)
Internal only — not customer-facing yet.
- Fixed dark mode across Market Monitor (was unreadable).
- Fixed chart colors in dark mode.
- Fixed the vendor count disagreeing with itself across panels.
- Fixed a coverage-spike alert comparing inconsistent article counts.
- Fixed the sentiment trend chart ignoring the date-range selector.
- Fixed "Quietest vendors" showing the wrong vendors.
- Added a minimum-sample check to Share of Voice.
- Fixed "Top voices" sorting by post count instead of engagement.
- Fixed "Most active vendors" being capped at 10 and sorted by a mixed metric.
- Fixed long lists on Pulse running the page on indefinitely instead of scrolling.
- Added a shared "Not enough data yet" section for panels below their sample-size floor.
- Fixed a grid layout bug that always left an empty gap next to a third panel in a two-panel row.
- Fixed the Pulse summary sometimes claiming it couldn't identify which vendors were involved.
- Fixed the Wire tab ignoring the date-range selector.
- Rebuilt navigation: seven tabs (Pulse, Analysis, Reports, Wire, Coverage, Vendors, Data) are
  now four (Findings, Collection, Reports, Vendors), grouping by "is this a market finding or
  pipeline information" instead of by which team originally built each screen.
- Added a count-reconciliation view showing why the vendor count can differ across the app.

## Demo / walkthrough
Explore → Market Monitor, on bugfixing.aunoo.ai only. Toggle dark mode from the app's theme
switch to see the fix. The vendor-count fix is visible by comparing the Findings tab's "N of M
vendors monitored" line against Collection → Overview's count-reconciliation table. The new
navigation is the four tabs at the top: Findings, Collection, Reports, Vendors — Collection has
its own row of sub-tabs (Overview, Sources & Health, Coverage, Wire, Data) underneath.

## Positioning notes
None — this is a pre-launch dev-tenant fix, not a feature with a competitive or sales angle.

## Limits and what's next
- This covers all five phases of the rebuild driven by a design-review document (22 findings) and
  a static HTML mockup. The one mockup idea not built: a lead-finding paragraph with inline
  citations a reader can click to jump to the source record behind a figure. Findings' summary
  paragraph is the already-fixed standing summary, not a new citation-linked synthesis — that's a
  separate, larger piece of work.
- The navigation rebuild (phase 4) has not been clicked through in a real browser — no
  screenshot/browser tool was available this session. It's verified by a clean type-check (which
  would catch a broken tab or a wrong condition) and a careful re-read of the changed code, but
  that's a lower bar than actually using it. This is the one item in this whole rebuild worth
  checking by hand before treating it as done — click through all four tabs and Collection's five
  sub-tabs.
- The Pulse summary fix touches a function shared with Brand Watcher's own summaries (both
  features generate their "state of the market/brand" paragraph the same way). The change only
  restores data that was already being collected and dropped before it reached the prompt, so it
  should make Brand Watcher's summaries more specific too, never different in kind — but it's
  worth Brand Watcher's own team glancing at a summary or two after this ships everywhere.
- The Data tab's "last 30 days" label is deliberately not tied to the date-range selector — it's
  a pipeline-health question, not a market question, and already states its own window plainly.
- Two things the original review flagged as bugs turned out, on inspection, to be intentional:
  funding/investor data is deliberately not filtered by date range (it describes the market's
  current state, not a period), and the vendor list deliberately shows excluded vendors with a
  tag so they can be un-excluded later. Neither was changed.
- Dark mode and the chart color fixes were verified by code review and a successful build, not
  by viewing the page in a browser — no screenshot tool was available this session. Worth a
  quick look before considering this fully done.
- Market Monitor is still internal-only; nothing here has shipped to a customer tenant.
