# Brand Watcher now says when a brand's own posts are being left out
_2026-09-21 · Brand Watcher dashboard, Brand Watcher API, MCP server_

## What shipped
The Articles card on the Brand Watcher dashboard now shows how many items below it are the
company's own blog, press or LinkedIn posts. The API and the MCP tools report the same number
and explain the rule.

## Why it matters
Brand Watcher counts press coverage, and it does not count a company writing about itself. That
rule went in on 18 September and it is the right rule: a weight-loss company publishing twenty
recipe posts has not been covered twenty times. What was missing was any sign of it on screen.

On the Oviva site that produced a dashboard reading "0 articles" directly above a list of 19.
All 19 were Oviva's own oviva.com posts, so both numbers were correct. Nobody could tell that
from looking. The first person to hit it, working through the API, reported the stat cards as
broken.

Now the card reads "0" with "19 owned excluded" under it, and the tooltip says what owned means.
The API returns the same count, and anyone querying it through Claude gets a sentence saying
there was no press coverage in the window against 19 of the brand's own items.

Who feels it: anyone reading a brand dashboard or a brand report, and anyone querying Brand
Watcher through the MCP server. The difference is between "the tool is broken" and "this brand
has no press coverage" — which, for Oviva, is the single most useful finding in the window.

## Release notes (copy-ready)
- The Articles card now shows how many of the listed items are the company's own posts, which
  the counts and sentiment figures leave out.
- The Brand Watcher stats API returns that count as `owned_articles`.
- Asking Claude for brand stats now gets an explanation when a brand has no press coverage,
  rather than a bare zero.

## Demo / walkthrough
Brand Watcher → pick a brand with owned content (Oviva) → the Articles card in the header row
shows "0" with "19 owned excluded" beneath it. Hover it for the explanation. The list below
shows the same items with an "owned" badge on each.

## Positioning notes
This is the visible half of a measurement claim the product already makes: Brand Watcher reports
earned coverage, not a company's own publishing. Competitors that count blog posts as coverage
will show a healthier number for a brand with no press at all. Being able to point at the card
and say "nineteen of these are yours, none of them are coverage" is a stronger demo than a
number nobody can interrogate.

## Limits and what's next
The count covers the news side only. Owned social posts sit on the Social tab under their own
rules and are not in this figure. The number is also not a reconciliation: articles a reviewer
flagged as false positives are hidden from the list but are not subtracted here, so on a brand
with flagged items the earned count plus the owned count can run slightly above the list length.
The Wiley sites have the API change but not the dashboard label until their next UI deploy.
