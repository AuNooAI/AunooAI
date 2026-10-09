# Claude can now show consensus, horizons and company records on Oviva and Panaya
_2026-10-09 · the Aunoo connector in Claude (Oviva, Panaya), and the consensus and horizons reports on those sites_

## What shipped
- Oviva's connector has the tools Panaya's already had: consensus, timelines, typed judgments,
  a tool picker, and source ratings (Trust Signals).
- On both sites, Claude can read a topic's Future Horizons scenarios and draw the S-curve chart
  with every scenario on its curve.
- When Claude shows a consensus or horizons analysis, it now gets layout rules: which cards,
  colours, bars and outlier markers to use, matching the site's own views.
- Claude can look up any tracked company and get its record: who it is, what it did and when,
  how often it is mentioned, and where each fact came from.
- Oviva's consensus and horizons reports for Oviva, Noom and WeightWatchers are now rebuilt
  every week, on Sunday night. Panaya's market reports are rebuilt every month.

## Why it matters
**Oviva's connector.** Before, an Oviva user asking Claude about consensus got nothing, because
the tool was missing. Now they get the same answers a Panaya user gets. They can also ask "what
changed with Noom?" and get the site's dated timeline instead of a fresh search.

**Horizons and display rules.** Before, Claude could describe a consensus analysis but drew it
however it liked, and it could not see the horizons analysis at all. Now it gets the scenarios
and the chart, plus instructions for laying out a report the way the site does. Analysts who build
reports in Claude get a result that looks like Aunoo's views, not a different design every time.

**Company records.** The site has been collecting company profiles, dated events and mentions for
weeks, but only its vendor pages showed them. Now an analyst can ask Claude "what has Voy done
this quarter?" and get the events with the articles behind each one. Every profile figure comes
with its source and date. When sources disagree, Claude is told so it can say so.

**Reports that stay current.** Before, a consensus or horizons report was only made when someone
pressed the button on the site. Oviva's reports were 35 days old, and Panaya's monthly refresh
had never run, because of a bug. Now Oviva's reports are rebuilt every Sunday night, ready for a
Monday report. Panaya's are rebuilt every 30 days. Fresh runs were made for both sites today.

## Release notes (copy-ready)
- Your Aunoo connector in Claude now reads consensus analyses, Future Horizons scenarios and the
  S-curve chart.
- Claude now follows Aunoo's layout when it shows a consensus or horizons view.
- New: ask Claude about any tracked company to get its profile, dated events, mentions and
  sources.
- Oviva: consensus and horizons reports for Oviva, Noom and WeightWatchers are refreshed every
  Sunday night.
- Panaya: the Enterprise Test Automation reports are refreshed monthly. Today's run is the
  first.

## Demo / walkthrough
In Claude, with the Oviva or Panaya connector switched on:
1. "Show the Future Horizons view for Brand Monitoring Oviva." Claude calls the horizons tools and
   draws the chart, then the scenarios in three columns.
2. "Show the consensus analysis for Brand Monitoring Noom as cards." Claude draws one card per
   theme, with the sentiment bar, agreement figure and outliers.
3. "What has Voy done in the last six months?" Claude returns Voy's dated events, the sources
   behind each one, and its profile.

On Oviva, the run dates on the Explore page's Consensus and Horizons tabs will move forward
every Sunday.

## Positioning notes
This answers the concern in this week's Oviva report that "the consensus runs only update when
someone starts a new run". It also brings the customer sites' connectors to the same level as
saas, which already sent display guidance for these views. The company records turn data we
already collect into answers a customer can get by asking.

## Limits and what's next
- **Drafts:** most company narratives are drafts that nobody has reviewed. Claude is told which
  are drafts, but the draft text still reaches the answer.
- **Horizons chart:** we have not looked at the chart drawn on these sites, because the server
  cannot render it. It is the same code saas uses, and its structure checks out.
- **No new analysis:** the connector reads saved runs and starts none. A topic with no saved run
  has no consensus or horizons until a run is made.
- **Other customer sites:** none got these tools. Wiley, Sunstar and the rest were not asked
  about.
- **Trust Signals on Panaya:** Panaya has no key for the source-rating service, so Claude cannot
  rate sources there.
- **abm:** abm's first automatic consensus and horizons runs finished today, but they read only
  25 articles, so expect thin reports there until more coverage builds up.
