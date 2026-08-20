# Market Monitor — information architecture and the vendor dashboard

**Date:** 2026-08-20
**Status:** Draft for discussion. Nothing in this document is built yet.
**Scope:** The Market Monitor tab in Explore. Backend and collection are done and running; this
is about what a reader sees.

## Why this needs a redesign rather than another tab

The tab grew one view at a time, by request, and now has seven: Brief, Timeline, Vendors,
Collection, New entrants, Review, Source health. A per-vendor dashboard would make eight. They
sit in a flat strip, but they are three different kinds of thing serving three different moments:

| Kind | Views | Who, and when |
|---|---|---|
| Read | Brief, Timeline | An analyst who wants this week's answer |
| Curate | Vendors, New entrants, Review | Someone maintaining the registry, occasionally |
| Operate | Collection, Sources, Source health | Whoever answers for what it spends, rarely |

Today the person who wants the market brief tabs past keyword configuration to reach it. The
three groups also have completely different visit frequencies — daily, monthly, and almost never
— which is the clearest sign they do not belong in one row.

There is a second problem the flat strip hides. The vendor table is a terminus: 83 rows and no
way in. Everything we know about an individual vendor — four identifiers, a LinkedIn profile,
funding, five watched pages, 35 posts, 51 attributed articles — is collected and stored and
reachable only by SQL.

## What we actually hold per vendor

Measured on Dropzone AI, 2026-08-20, so the dashboard below is specified against real data rather
than intentions:

| Data | Count | Source |
|---|---|---|
| Identifiers (website, domain, LinkedIn, Crunchbase) | 4 | import + discovery |
| LinkedIn profile snapshots | 1 | Bright Data, weekly |
| Crunchbase record | 1 | Bright Data, weekly |
| Watched web pages | 5 | site discovery |
| Job postings | 0 | Bright Data, twice weekly — first run pending |
| Attributed articles | 51 | keyword group + classifier |
| LinkedIn posts | 35 | Bright Data, 12-hourly |
| Registered RSS feeds | 1 | site discovery |
| Review tasks | 0 | import |

The important caveat: **most series are one point long.** Profiles and funding have run once.
Charts that imply a trend from a single reading would be lying, and the spec below says what to
show instead until the second reading lands.

---

## Proposal A — Three surfaces, not seven tabs

**Market level keeps three:**

- **Brief** (default) — what changed, who moved, what is unresolved. Already built.
- **Wire** — the timeline, with the RSS link. Renames "Timeline" to say what it is for.
- **Vendors** — the registry table, and the way into a vendor.

**Operating moves behind one control.** A settings affordance on the market header opens
Collection terms, Sources and schedules, and Source health as panels in one place. These are
configuration, visited rarely, and they do not belong beside the report.

**Curation folds into where it is needed.** New entrants and Review both concern the registry,
so they belong with Vendors — either as a segmented control above the table or as a count badge
that filters it. A review task about one vendor should also appear on that vendor's page, which
is where somebody would act on it.

### Open question 1
Segmented control above the vendor table (`All · Needs review (27) · New entrants`) versus
keeping them as separate views. The control keeps one table and one mental model; separate views
are easier to link to.

---

## Proposal B — The vendor page

Reached by clicking a row in the Vendors table.

### Open question 2 — route or drawer
A **route** (`/explore/market/2/vendor/dropzone-ai`) is linkable, shareable, and survives a
refresh — you can send someone a vendor. A **drawer** over the table keeps the market context and
makes scanning several vendors quick, but cannot be linked to.

Recommendation: route, with the table's filter state preserved on return. Being able to send a
colleague "here is what we know about Conifers" is worth more than the scan-speed.

### Layout

**Header.** Display name, sub-category, country, founded year. Chips for role, whether it is
being watched, and whether it is published. The two verbs a reader needs are here: watch/unwatch,
and open the review queue for this vendor if it has one.

**Identity panel.** Every live identifier with its provenance and whether it was verified —
website, domain, LinkedIn, Crunchbase. Superseded identifiers are shown on demand, not hidden:
Crogl's crossed LinkedIn URL is part of how the registry got here. Guessed Crunchbase URLs are
marked unverified, because roughly one in three does not resolve.

**Where the numbers disagree.** Not a chart — a comparison. Workbook headcount against LinkedIn
headcount, with the date of each. These are different measurements taken at different times, and
the disagreement is the point. Dropzone AI: 75 at import, 77 on LinkedIn. Crogl showed 40 against
6 and that was the bug that exposed a crossed identifier.

**Funding.** Round count, last round type, named lead investors, IPO and operating status, and
Crunchbase's growth, heat and rank scores. State plainly that no dollar amount is available: this
source carries none, and 42 vendors are legitimately Undisclosed.

**Activity.** Three counts with a sparkline each once there is a series — LinkedIn posts, open
job postings, attributed articles. Until the second reading, a count and its date, no line.

**Recent posts.** The vendor's last ten LinkedIn posts with engagement, linking out.

**Site changes.** Which pages we watch, when each was last fetched, and the semantic diff for any
that changed. This is the highest-signal, least-visible thing we collect — a pricing page gaining
an Enterprise tier is a market event nobody announces.

**Coverage.** Attributed articles by category, and the most recent ones.

### Open question 3 — the headcount chart
Charting workbook-baseline-then-LinkedIn as a two-point line implies a trend between two numbers
that were measured differently. Options: (a) no line until two LinkedIn readings exist, showing
the comparison as a pair; (b) plot LinkedIn readings only, with the workbook value as an
annotated reference; (c) plot both and label the join.

Recommendation: (b). The workbook is provenance, not the start of our series.

---

## Proposal C — Charts, and where they are honest

Two exist on the Brief: headcount movement and posting volume. What else earns a chart, and when:

| Chart | Needs | Available |
|---|---|---|
| Headcount over time, per vendor | 2+ profile runs | after the second weekly run |
| Posting volume over time, market-wide | ~2 weeks of posts | ~2026-09-03 |
| Funding stage mix across the market | Crunchbase run | **now** — 19 vendors have rounds |
| Growth/heat scatter | Crunchbase run | **now** |
| Hiring by function and seniority | jobs run | after the first jobs run |
| Coverage by category over time | existing articles | **now** |

Three are buildable today. The rest should not be drawn until they have more than one point, and
the UI should say "one reading so far, next on <date>" rather than render a flat line.

---

## What this does not cover

- **Market events.** `bw_market_events` and `bw_event_vendors` exist and are empty. Scored,
  vendor-linked market events were Phase 3 of the original specification and were never built;
  the timeline currently does that job at topic level. Whether to build the event layer or keep
  leaning on the timeline is a separate decision from this redesign.
- **The public surface.** `is_public` exists on markets and vendors and nothing reads it. A
  public market page and feed would need its own pass, including the question of which event
  types are safe to publish about named companies.
- **Multi-market.** The selector works but there is one market. Anything that only makes sense
  with several — comparison, cross-market rollups — is out of scope here.

## Effort (AI)

| Piece | Estimate |
|---|---|
| Restructure to three surfaces plus a settings panel | 1.5–2 hours |
| Vendor page: route, header, identity, funding, activity | 2–3 hours |
| Site-change diffs and recent posts on the vendor page | 1 hour |
| The three chartable-now charts | 1 hour |
| Vendor detail API endpoint (one call, not six) | 45 min |

Roughly a day, dependent on the three open questions above.

## Decisions needed

1. Segmented control over the vendor table, or separate Curate views?
2. Vendor page as a route or a drawer?
3. Headcount chart: pair, LinkedIn-only with a reference line, or a joined line?
