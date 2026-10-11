# Market Monitor: better browsing, flexible briefings, and a themes view
_2026-08-22 · Market Monitor (bugfixing.aunoo.ai only — not yet on any other customer instance)_

## What shipped

- **Coverage reading three ways**: by vendor, by day, or as a visual timeline showing
  which vendor was active when. A story covered by five outlets now shows as one card
  with a source count, in whichever view you're using — not just in a separate mode that
  usually looked empty.
- **Briefings for any period.** A briefing used to mean one calendar month. Now it can be
  a day, a week, a month, or a year, picked from a dropdown instead of typed.
- **A new Themes view**: what the market is talking about, and separately, what your
  tracked competitors are posting about themselves — grouped automatically from the
  articles' meaning, not from keyword matches, with an optional AI summary of each group.
- **The Wire's events are now checkable.** Every event (a coverage spike, a sentiment
  swing, a named development) can be expanded to show the actual articles behind it, each
  with a button straight to the vendor it's about.
- **Add a competitor in one step.** If a company shows up in your market's coverage but
  isn't in your tracked list yet, there's now an "Add vendor" button instead of needing a
  full spreadsheet re-upload.
- **A market-wide headcount growth figure.** Alongside the existing "biggest movers" chart,
  the Brief now shows the average and median headcount change across every tracked vendor
  with enough data, not just the handful that moved the most. A "Fetched by source" panel
  on the Data tab shows how much each connected provider actually returned in the last 30
  days, and a "Fetch now" button on each vendor's page can pull fresh data for just that
  one vendor instead of waiting for the next scheduled run.
- **Groundwork for four new data providers** — PitchBook, ZoomInfo, Indeed job postings,
  and LinkedIn people profiles. See "Limits and what's next" below before expecting data
  from these — most of this is infrastructure, not yet a working data feed.

## Why it matters

**Coverage was a flat list that got harder to read as it grew.** An analyst scanning 300
matched articles had no way to see "what has Vendor X said this month" or "what happened
this week" without scrolling past everything else. Grouping by vendor or by day turns that
scroll into sections; the timeline view turns it into a chart, so a burst of coverage
around one vendor on one day is visible at a glance instead of found by accident.

**Briefings locked to a calendar month meant "what happened this week" had no answer** —
you'd wait until the month closed, then read a report covering four times more than you
asked about. Day/week/month/year removes that wait.

**Themes answers a question Coverage can't**: not "what matched," but "what is this
actually about." Two articles can use completely different words and still be about the
same underlying development — coverage lists them as two separate rows, Themes groups
them as one. Splitting "the market" from "competitors" separately means you can see market
narrative and vendor messaging side by side instead of guessing which is which from a
flat list.

**The Wire told you something happened without letting you check it.** A "coverage spike"
event with no way to see the actual articles is a claim, not evidence. Now it's checkable,
the same standard the briefings and reports already hold themselves to.

**A competitor missing from the tracked list is a blind spot you don't know you have**
until it shows up in coverage by accident — which is exactly what happened with Intezer
during this session. Fixing that gap took one form field instead of a spreadsheet.

**A "biggest movers" chart alone answers "who changed the most," not "is the market
growing overall."** The headcount average/median gives that second answer directly. "Fetch
now" and the Data-tab source panel exist for the same reason: waiting for the next
scheduled collection cycle, or trusting that a data connection is working without a way to
check its actual return volume, are both avoidable delays.

## Release notes (copy-ready)

- Coverage: browse by vendor, by day, or as a timeline, with duplicate coverage grouped
  automatically in all three.
- Briefings can now be generated for a day, a week, a month, or a year.
- New Themes view: what the market is talking about, and what competitors are posting
  about themselves, grouped by meaning with an optional AI summary.
- Wire events can be expanded to show their source articles, each linking to the vendor
  it's about.
- Added an "Add vendor" button so a new competitor can be tracked without a full registry
  re-upload.

## Demo / walkthrough

Market Monitor → pick a market → **Coverage** tab: the "Group by" control (Vendor / Day /
Timeline) sits above the article list. **Briefings** tab: the Day/Week/Month/Year toggle
and period dropdown sit next to "Write briefing." **Analysis** tab: scroll to the bottom
for the new **Themes** panel (The market / Competitors toggle, a day-range selector, and
"Narrate with AI"). **Wire** tab: any event with linked articles shows a "Show articles"
link. **Vendors** tab: "+ Add vendor" sits above the vendor table.

## Positioning notes

None specific to a competitor gap or sales objection — this is depth-of-use work on an
existing module (bugfixing.aunoo.ai only), not a new product surface being introduced to
the market.

## Limits and what's next

- **The new data sources are not live yet.** PitchBook, ZoomInfo, and Indeed job listings
  have the request plumbing built, but PitchBook and ZoomInfo need a vendor's profile URL
  entered by hand (there's no way to look it up automatically for these two), and none of
  the three run automatically — they only fire when someone clicks "Fetch now" on a
  specific vendor. LinkedIn people-profile tracking (executive changes) has no code
  written yet at all, only the provider's catalog ID identified.
- **Two of the three new mappers are unverified.** The code that turns a PitchBook or
  Indeed response into stored data was written from a sample request, not a sample
  response — nobody has confirmed the field names are exactly right against a real
  answer yet. The first real use of each should be checked by hand.
- **Themes recomputes every time you open it** — nothing is cached or scheduled, so it's
  fine for occasional use but would need work before it could be a recurring report.
- **The AI persona used in full reports was tried in Themes' summaries and made them
  worse** (it wrote unrelated commentary instead of naming the topics), so Themes
  summaries deliberately don't use it — a reminder that report tuning does not transfer
  between surfaces automatically.
- **Vendor backfill is one article deep.** Adding a vendor after the fact attributes the
  one article that prompted adding it; it does not re-scan historical coverage for other
  mentions of that vendor.
