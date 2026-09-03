# Oviva brand-monitoring site, and three Brand Watcher fixes it exposed
_2026-09-03 · Brand Watcher (dedicated tenant), Market Monitor tab, Timeline tab_

## What shipped
- A dedicated brand-monitoring site for Oviva with six competitors, news in English and
  German, social across X, Reddit, Instagram, TikTok and Bluesky, Glassdoor reviews,
  LinkedIn company pages, a market maturity map, a timeline and a daily adverse-media agent.
- The Market Monitor tab now opens on a dedicated brand-monitoring site.
- The Timeline tab now shows a brand's timeline even when that brand is also tracked as a
  market vendor.
- The category chips above the Brand Watcher article list now count only articles the list
  will actually show.

## Why it matters
**Market Monitor on a brand site.** Before, a brand-only site hid the Market Monitor tab
even when the module was on, so the LinkedIn, website and hiring data collected for the
brand had no page. Now an analyst on a brand site can open the map and the vendor pages.

**Timeline.** Before, a brand that was also registered as a market vendor had no timeline,
and on a brand site that was every brand, so the tab was empty. Now each monitored brand
keeps its own timeline of developments, story emergences and source shifts.

**Category chips.** Before, a chip could say "Leadership (6)" and clicking it listed
nothing, because the count included the brand's own LinkedIn posts and Glassdoor reviews
that the list deliberately keeps off the news view. Now the chips and the list agree. The
posts and reviews are still there, on the Social tab, where a brand's own voice and its
staff reviews belong.

Who feels it: analysts and demo audiences on any brand-monitoring site. Operators setting
up a new brand site feel the difference most, because these three gaps together made a
fresh site look broken.

## Release notes (copy-ready)
- Market Monitor is available on dedicated brand-monitoring sites.
- Brands that are also tracked as market vendors now have a timeline.
- Brand Watcher category counts match the article list; a brand's own posts and its
  Glassdoor reviews are shown on the Social tab.

## Demo / walkthrough
On oviva.aunoo.ai, sign in and open Explore. Brand Watcher shows Oviva with the six
competitors; the Social tab holds the X, Reddit, Instagram and Glassdoor items; the Market
Monitor tab shows the map with five of seven vendors placed and a page per vendor with
headcount, funding, open roles and LinkedIn posts; the Timeline tab lists a scope per brand.
The Agents tab has the adverse-media agent, which emails its first report tomorrow at 08:00.

## Positioning notes
A brand site now offers the same company-level view (headcount, hiring, funding, owned
content) that the market product offers, without the customer having to buy or understand
the market product. That is the concrete answer to "what do you know about my competitors
beyond press coverage".

## Limits and what's next
- Oviva has had no earned press in the last 30 days on either news provider, so its news
  list today is its own site posts that name the brand. Coverage arrives as it is published.
- Two vendors are not yet on the map: Numan needs a second LinkedIn headcount reading
  (its page came back unchanged, and identical readings are not stored twice), and
  WeightWatchers is a listed company with no venture funding total, which the map requires.
- Funding totals are operator-entered from public sources; the Crunchbase feed does not
  carry a reliable total and is deliberately not trusted for it.
- The timeline runs one AI call per brand per day. On the SOC market site this fix adds
  13 brands' worth; watch the monthly model spend there.
- Setting up a brand site still needs several manual database steps (search-term seeding,
  social linking, a first full classification, first-day mementos). Folding those into the
  provisioning script is the obvious next job, about an hour of AI work.
