# Market pages now report incidents, check press stories, and count hiring honestly
_7 October 2026 · Market Monitor pages (customer sites such as Oviva, and aisocnews.com)_

## What shipped
- Data breaches, outages, lawsuits, regulator action and recalls now appear as developments, marked "Incident".
- News stories that only the press reported now appear on the page.
- Every press story is checked a second time before it can lead the page.
- Customer market pages carry the customer's own look, with no aisocnews branding or empty Analysis section.
- Private market pages show RSS and AI feed links that work in a feed reader.
- Hiring figures leave out the large incumbents and count each job once.
- Clinical jobs get their own group in the hiring breakdown.
- Several sentences on the page that were wrong now read correctly.

## Why it matters

**Incidents.** Before, a market page could only show launches, funding, customers, partnerships, acquisitions and hires. HelloBetter's data breach, covered by heise and other German press, never appeared on Oviva's page. Now it heads the "Market moves" section, marked as reported by multiple independent sources. Analysts tracking a competitor see the bad news as well as the announcements.

**Press-only stories.** Before, a story reported by the press but never announced by the vendor was silently dropped. That hid HelloBetter's breach and a Noom story in Adweek. Now these appear under the publisher's own headline.

**A second check on press stories.** Before, the first AI reading of a press article went straight to the page. Oviva's top story became Noom's new ad campaign, filed as a "product launch". Now a second model checks each press story's type. A story it does not clearly agree with can still be listed, but cannot lead the page. Readers get a top story they can trust.

**The customer's own page.** Oviva's page carried aisocnews's byline, its About page and an empty Analysis section. Those are gone. The page now reads as Oviva's market monitor.

**Feeds on private markets.** Before, the RSS and AI feed links only appeared on public markets. A customer could not subscribe to their own private market. Now signed-in viewers get feed links that work in a feed reader for a year.

**Honest hiring numbers.** Three things inflated or blurred the hiring panel:
- LinkedIn lists one job once per city, so Noom's open roles counted some jobs three times.
- Large companies such as WeightWatchers, Leidos and Torq sat in the top five, with hiring at a scale the specialists cannot match.
- Oviva's clinical roles all showed as "other".

Each job now counts once, the large incumbents are listed separately, and Oviva's breakdown reads "clinical 36" of 40 roles. On aisocnews the 30-day count went from 224 to 157, which is the specialists' real hiring.

**Correct sentences.** The acquisitions highlight on aisocnews read "Leidos acquired Leidos". It now reads "Leidos acquired Analogic". Smaller slips such as "1 vendors" and a summary printed twice are also fixed.

## Release notes (copy-ready)
- New: incidents (data breaches, outages, lawsuits, regulator action, recalls) appear as developments on market pages.
- New: stories reported only by the press now appear, under the publisher's headline.
- New: press stories get a second check; only well-supported stories can be the top story.
- New: RSS and AI feed links on private market pages.
- Changed: hiring counts list each job once and leave out large incumbents.
- Changed: clinical jobs have their own group in the hiring breakdown.
- Fixed: customer market pages no longer show aisocnews branding or an empty Analysis section.
- Fixed: the acquisitions highlight names the right buyer and target.
- Fixed: social posts from TikTok, Instagram, YouTube and Facebook name their platform.

## Demo / walkthrough
1. Open Oviva's market page: Market Monitor → Report (`/api/market-monitor/markets/1/report.html`).
2. Under "Market moves", see the HelloBetter data breach marked "Incident", with heise and stadt-bremerhaven as sources.
3. Under "Hiring", see 115 open roles, with Oviva's roles grouped as clinical. WeightWatchers is not in the top five.
4. In the top bar, use the RSS or AI feed link. It opens the feed without a login.
5. Open "Full map with names" from the Market Maturity Map. WeightWatchers is listed under "Large incumbents".

## Positioning notes
- Incident tracking answers the obvious buyer question, "would this have told me about a competitor's breach?". Before today the honest answer was no.
- The second check on press stories supports the claim that every item on the page has been checked, not just extracted.
- Feeds on private markets make the product usable in a customer's own reader or AI assistant, not only in our UI.

## Limits and what's next
- The second check agreed that Noom's ad campaign is a "product launch", though with low confidence. It is still listed under Product launches; it just cannot lead.
- Zanadio has no LinkedIn figures. Its parent company's page was linked by mistake and has been removed, and no Zanadio page of its own could be found.
- HelloBetter's, Voy's and Juniper's own websites block our reader, so their news comes only from the press and LinkedIn.
- Oviva's page fixes were patched into its copy by hand. Other customer sites (Sunstar, Panaya and others) do not have them yet.
- "Second Nature: other 8" in the hiring breakdown has not been looked into.
- Seven more queries share the bug that labelled news as social. They have not been checked yet.
