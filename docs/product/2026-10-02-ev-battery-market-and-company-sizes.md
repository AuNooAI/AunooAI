# A battery market for the PowerCo demo, and company sizes from annual reports
_2 October 2026 · demo site (bugfixing): Market Monitor, Brand Watcher, one news topic_

## What shipped
- A new market, "EV Battery Cells", tracks PowerCo and 13 battery makers it competes or
  partners with.
- The battery news topic is now called "EV Battery Industry" and keeps news about these
  companies from anywhere in the world.
- The new market shows who is posting about it on Bluesky.
- Each market now has its own list of followed accounts.
- The Market Maturity Map can size a company from its annual report instead of from LinkedIn.

## Why it matters
**The demo topic missed the prospect's own news.** Before, the topic was described as the
"European" battery industry. So the AI that judges relevance threw out PowerCo's two-year delay
at its Canadian plant, and LG Energy Solution's new cells with GM. Now the topic names PowerCo
and its competitors and covers them anywhere. A strategy reader at PowerCo would have noticed
the missing Ontario story straight away.

**There was no competitor view.** The companies were keywords in one topic, with nothing per
company. Now each one is a tracked company with its own page, timeline, brand colour and
coverage. The market's views include share of voice, a findings list and the Maturity Map.

**Top voices was empty.** That view is built from social posts, and this market collected
none. It now searches Bluesky every day, at no cost. The first run found 34 voices from 151
accounts, including InsideEVs, Electrek and Transport & Environment.

**One market showed another market's people.** The list of accounts we follow was shared
across the whole site. So the battery market showed a security analyst, and one of his posts
about security tools appeared in its coverage. Now each market keeps its own list.

**LinkedIn made the giants look small.** The map sized companies by how many people list the
company on LinkedIn. That is a small share of a large Chinese or Korean group: CATL showed
6,422 against 131,988 employees in its annual report. Now an analyst can enter the
annual-report figure with its source and date, and the map uses it for size. Growth over time
still compares LinkedIn readings, so like is compared with like.

## Release notes (copy-ready)
- New demo market "EV Battery Cells": PowerCo and 13 battery cell makers, with Bluesky voices.
- The Market Maturity Map can now use a company's published headcount, with its source shown.
- Followed accounts are now kept per market.
- The battery news topic is renamed "EV Battery Industry" and covers these companies worldwide.

## Demo / walkthrough
1. Open Explore, then Market Monitor.
2. Choose **EV Battery Cells** from the market menu beside the title.
3. Open **Market Maturity Map**. Thirteen companies are placed. CATL is the largest. PowerCo
   sits in the "established" tier with the fourth-highest momentum, after Gotion, CATL and Verkor.
4. Open **Top voices** to see who is posting about the market on Bluesky.
5. Open **Vendors** to see each company's page.

## Positioning notes
This is the pitch from the PowerCo briefing put into the product: a maintained view of a market
and the companies in it, not a news search. Two points matter for a strategy buyer. The map
says where every size figure comes from. And we leave a company unmeasured rather than size
it from the wrong number (BYD below).

## Limits and what's next
- **BYD is not on the map.** BYD does not publish a headcount for its battery business, and its
  group figure (869,600) includes cars. We chose to show it as unmeasured.
- **Some sizes are minimums or partial:**
  - PowerCo, Verkor and AESC publish only "over N" figures, and PowerCo's is out of date.
  - SK On's figure counts Korean staff only.
  - ACC's comes from April 2025 testimony, before its job cuts.
  - Lyten publishes no figure, so it is still sized from LinkedIn.
- **Four companies have no logo yet:** Samsung SDI, SK On, EVE Energy and AESC.
- **The topic's relevance check is still strict.** Some competitor stories, such as BMW's new
  battery plant, are still rejected by the topic. The market's own check keeps them.
- **The market is private and on the demo site only.** No customer site has it.
- **One slow company website can delay collection for every market for most of an hour.** This
  happened today and has not been fixed.
