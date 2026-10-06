# News Feed now shows only articles that passed the relevance check
_2026-10-05 · Explore → News Feed, on every brand-watch and market-monitor site_

## What shipped
- The News Feed leaves out articles the relevance check rejected. Until now it showed any
  article that had been through the AI analysis step, whether or not the check had passed it.
- On the Panaya site, the market topic's own approval bar was raised to match the rest of the
  product, and a followed social account that had nothing to do with the market was removed.

## Why it matters
**Before.** Every collected article goes through two steps: an AI analysis that adds a category
and a sentiment, and a relevance check that decides whether it belongs to the topic. The News
Feed only asked for the first. So an article the check had thrown out still appeared in the
feed, as long as it had been analysed. On the Panaya site this was most of what an analyst saw:
of the 70 articles in the 7-day feed, 12 were relevant, 32 were weak, and 26 had been rejected
outright. Those 26 included a story about Amazon delivery drivers' smart glasses and one about a
games publisher adopting AI. On our own test site the leak was about one article in eight.

**Now.** The News Feed applies the same relevance bar as the Brand Watcher, the social tab and
the daily briefing. The Panaya 7-day feed went from 70 articles to 12, all about enterprise
test automation. Analysts see less, and what they see is on topic.

**Who feels it.** Anyone reading the News Feed on a site with a broad topic. Narrow topics
leaked less because their relevance check rejected fewer analysed articles.

## Release notes (copy-ready)
- News Feed: articles that failed the relevance check no longer appear. The feed now uses the
  same relevance bar as the rest of Explore.
- Panaya site: the market topic's approval bar now matches the product-wide bar, and an
  unrelated followed account was removed from social collection.

## Demo / walkthrough
Explore → News Feed, "Last 7 days". On panaya.aunoo.ai the list is short and every item is about
test automation or a tracked vendor. The same view on 4 October showed general AI coverage
first.

## Positioning notes
This closes the gap between what the relevance check decides and what the feed shows. The
product's claim is that an analyst does not have to filter the feed by hand; a feed that showed
rejected articles undercut that claim on exactly the broad topics where it matters most.

## Limits and what's next
- The fix is live on panaya, bugfixing, wiley and wileytest. The other monolith sites (oviva,
  sunstar, abm, ibaset, pearson, bwtemplate) still show rejected articles until the same change
  reaches them.
- The relevance bar is one number, 0.4, for every topic. A weak-but-approved article at 0.40
  still shows. Raising the bar per topic is a separate decision.
- Articles that were approved and shown before this change are not re-examined, except on
  Panaya where 196 weak approvals were moved out by hand.
- On Panaya, 357 of the vendors' own LinkedIn posts have never been through the analysis step.
  They reach Market Monitor's owned-post panels but not Brand Watcher's news cards. Unchanged.
