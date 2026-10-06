# Cleaner brand feeds for the proof-of-value sites, and a relevance step that admits when it does not know
_2026-10-05 · Brand Watcher feeds, observers and the daily briefing on panaya, sunstar and oviva; the relevance step on every site_

## What shipped
- Retail price listings and coupon pages no longer appear in brand feeds, observer alerts or the daily briefing.
- Japanese news that only a search provider claims is about a topic is checked against the page before it enters the feed.
- Reddit posts on sunstar are filed as social posts again, with author, link, time and subreddit attached.
- Panaya, sunstar and oviva each have a daily observer set (adverse media, competitor moves, and one demand or policy watch) and the reviewed daily briefing, run the same way as the Wiley service.
- Oviva's site shows the Briefing Desk tab.
- When the relevance check cannot get an answer, the article is held for another look instead of being thrown away as irrelevant.
- Articles the research assistant could not score stay in its results, marked as unscored, instead of disappearing.

## Why it matters
**Deal listings.** On sunstar, two of every three approved Colgate press items in September were price listings such as "4-Pack Colgate Optic White, $6.34". The brand judge accepted them because they are about the brand's products. An analyst scanning the feed, and the observer writing the morning alert, saw a brand drowning in coupons. The listings are now stopped before any model looks at them, and the 37 that were already approved on sunstar and oviva were removed. Colgate's two-week approved count on sunstar fell from 16 to 4, which is the real volume.

**Phantom matches.** Sunstar's Japan topic approved nothing for weeks. The cause was not the scorer: 111 of 181 provider results did not contain the search term anywhere on the page. Those pages are now checked once and dropped when the term is missing, so what remains is real supply, which is thin (one to three usable items a week).

**Reddit posts.** 1,065 sunstar reddit posts were stored as if they were news articles, so they counted in the wrong places and carried no author or subreddit. They are social posts again, with the link and time the product needs for the Social tab and the observers.

**The three sites run like Wiley.** Each has observers on the cheap model at fixed morning times, the reviewed briefing on the standard model, and a runbook that says who forwards what to whom. An operator can run the three proof-of-value sites from one checklist.

**Relevance that admits uncertainty.** Before, if the local models were unavailable and the fallback also failed, the article scored zero and was rejected for good. Now it is held as "check failed" and looked at again on the next poll. A reply the model wrote badly, such as a score of 2.0 or a non-number, is no longer rounded into a perfect score. These paths had barely fired in production, measured over the last week, so this is insurance rather than a visible change today.

## Release notes (copy-ready)
- Brand feeds, observer alerts and the daily briefing exclude retail deal and coupon pages.
- Non-English search results are checked against the source page before they enter a feed.
- Reddit posts carry author, link, time and subreddit.
- Panaya, Sunstar and Oviva: daily observers and the reviewed daily briefing are live.
- Oviva: Briefing Desk tab added.
- An article whose relevance check could not run is retried rather than rejected.

## Demo / walkthrough
- Sunstar, Brand Watcher, Colgate: the News list no longer shows price listings. The weekly data quality check reports how many were rejected.
- Oviva, Explore: the Briefing Desk tab sits after Timeline; drafts carry a count badge.
- Any site, Explore, Agents: the observer list shows the morning schedule and the model.

## Positioning notes
Brand monitoring tools are judged on what they leave out. A feed that reports a coupon as press coverage, or a Japanese article that never mentions the brand, costs the analyst's trust faster than a missed story. This work is the noise-removal side of "signal, not volume". It also supports the claim that the service is run, not just hosted: the runbook, the checks and the observer schedule are the same for every proof-of-value site.

## Limits and what's next
- The deal rule is a list of hosts and title forms. A new deal site or a new phrasing gets through until it is added; the weekly check shows any that slipped.
- The page check for phantom matches runs for Japanese, Chinese and Korean groups only, and only on sunstar and canonical today.
- Sunstar's Japan topic remains thin because the supply is thin; the shared NewsData key still hits its daily cap by midday on four sites.
- Reddit author, link and time are recorded on the sites running the current collector (canonical, sunstar, abm). Engagement counts come only from Reddit's JSON route.
- Reuse of saved relevance decisions, which avoids paying twice for the same rejected link, exists on bugfixing and abm only; the other sites do not have that ledger yet.
- Sunstar and abm had not run a collection cycle by the time of writing, so their first live deal rejections and reddit links are unverified; bugfixing's first cycles rejected three listings and reused 23 saved decisions.
- The duplicates and press-release grouping build is written but not deployed; it wants its own session, tested on one site first.
