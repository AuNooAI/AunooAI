# Brand monitoring now respects how sensitive you asked it to be
_2026-08-06 · Brand Watcher collection, all sites_

## What shipped
- When you tell a brand's monitoring to keep marginal mentions, it now actually keeps them.
  Before, that setting was applied early and then overruled, so the articles were collected,
  analyzed, and quietly filed out of sight.
- A one-off catch-up on a brand's older coverage now works. The news search was capped at the
  last 30 days no matter what date range you asked for.

## Why it matters
This is the difference between monitoring a big competitor and monitoring a small one.

A large vendor publishes constantly, so a strict filter still leaves plenty. A small competitor
might be mentioned six times a year, in passing, inside somebody else's market report — and a
strict filter removes all six. Customers who track small, fast-moving rivals were getting an
empty dashboard that looked identical to "nothing is happening".

Our first customer for this is a manufacturing software vendor whose single most important
question is why one small competitor keeps beating them to contracts. Their brand's dashboard
showed nothing at all. It now shows six real mentions going back a year, including a funding
story about an adjacent startup that names the competitor, and two industry roundups that place
them among the top manufacturing software tools. That is exactly the kind of evidence their
analyst was asking for and could not get anywhere else, because this competitor publishes
almost no product documentation.

The catch-up fix matters for every new customer site. A brand's coverage does not start on the
day we switch monitoring on, and until now the first month looked emptier than reality.

## Release notes (copy-ready)
- A brand's relevance setting is now applied consistently through the whole collection process.
  Brands tuned to keep marginal mentions will see more articles.
- Monitoring can now reach back further than 30 days when catching up on a brand's history.
- No change to how ordinary topics collect — this affects brand monitoring only.

## Demo / walkthrough
Brand Watcher → pick a brand with little coverage → Articles. Sensitivity lives on the brand's
monitoring settings. Worth showing alongside the Perception tab, because more articles is what
makes the sentiment comparison meaningful for a small competitor.

## Positioning notes
Answers the objection "your tool only works for companies that are already in the news".
Tracking a quiet competitor is the harder problem and the one buyers care about, since they
already read the big vendors' press releases.

## Limits and what's next
- Sensitivity is a real trade-off, not a free win. Set it too low and unrelated articles reach
  the feed — on our first site, a setting of 0.1 let through market commentary about the 17th
  century Dutch tulip bubble alongside genuine coverage of a company called Tulip. We tuned it
  to 0.25. New brands with generic names need this checked, not assumed.
- The manual "check now" button still uses the site-wide date range rather than the brand's
  own, so a deliberate catch-up needs an operator to change one setting temporarily. The
  scheduled collection is unaffected.
- Rolled out to the first site only so far; the remaining sites get it as part of the normal
  propagation, roughly ten minutes of work.
