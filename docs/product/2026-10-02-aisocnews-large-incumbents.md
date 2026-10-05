# The AI SOC market map now includes the big platforms, without letting them distort it
_2 October 2026 · aisocnews.com (the AI in the SOC market page) and the Market Monitor in the app_

## What shipped
- **Large incumbents.** CrowdStrike, Palo Alto Networks, Microsoft, Splunk/Cisco and 13 other
  large companies now appear on aisocnews.com. They are named beside the market map, not ranked
  on it.
- **Three more AI SOC startups are tracked:** Tracecat, Binalyze and Stellar Cyber.
- **Every vendor has its own logo and colour,** where we could find one. Before, about half the
  vendors were drawn in plain grey.
- **The featured Binalyze guest post now carries Binalyze's logo,** like the other featured
  items.

## Why it matters

**Large incumbents.**
- **Before:** the map only covered AI SOC startups. Buyers ask about CrowdStrike Charlotte AI,
  Microsoft Security Copilot and Palo Alto Cortex XSIAM, and none of them was there.
- **The obstacle:** we couldn't simply add them. The map ranks vendors by size against each
  other. Microsoft's LinkedIn profile lists 231,728 staff. Every other vendor we measure adds
  up to 4,643 staff. Ranking them together would have pushed every startup to the bottom.
- **Now:** the large companies are tracked like any other vendor. Their news and posts appear
  on the page, and they count when we measure how loudly each vendor talks about AI in the SOC.
  On the map itself, they're listed under "Large incumbents" and left out of every size
  comparison.
- **Who feels it:**
  - Readers now see the whole competitive field.
  - Startups are still compared fairly with each other.

**Searching by product, not company name.** Each large company is followed through its AI SOC
product, for example "Charlotte AI" rather than "CrowdStrike". A plain company-name search
would pull in all of Microsoft's or CrowdStrike's news, almost none of it about the security
operations market.

**Vendor colours and logos.**
- **Before:** about half the vendors had no colour, so their bars and dots were drawn in grey,
  and 19 had no logo.
- **Now:** all but one have a colour taken from their own branding, and all but four have a
  logo. The ones left have no usable logo we could find, or a site that blocks us.

## Release notes (copy-ready)
- The AI in the SOC market page now covers the large security platforms. CrowdStrike, Palo Alto
  Networks, Microsoft, Google, Splunk (Cisco), IBM, ServiceNow, Fortinet, SentinelOne, Trellix,
  Rapid7, Arctic Wolf, Mandiant, Elastic, Exabeam, Torq and Leidos are listed beside the market
  map as large incumbents.
- Large incumbents are tracked through their AI SOC products and appear in the news on the page.
  They are left out of size comparisons, so the startups on the map are still ranked against
  companies of their own kind.
- Tracecat, Binalyze and Stellar Cyber are now tracked.
- Vendors are drawn in their own brand colours throughout the page.

## Demo / walkthrough
- **The list:** on aisocnews.com, open the Analyst View (`?view=report`). Under the market map,
  open "Who is where". The "Large incumbents" line lists all 17.
- **Changing a status in the app:** go to Market Monitor → Market Horizon tab → "Mark a vendor
  acquired, closed, pivoted or incumbent". Choose a vendor and "large incumbent". The map
  recomputes on save.

## Positioning notes
- **Answers a recurring buyer question:** "where do the big platforms sit?" The page now names
  them alongside the startups.
- **Doesn't pretend:** it doesn't put startups and giants on one size scale. Placing them
  together would make every startup look negligible.
- **Fits the method page:** the map measures size and growth from public data, and only
  compares companies where those numbers are comparable.

## Limits and what's next
- **Size, funding and hiring:** the page doesn't show any of these for incumbents. It also
  doesn't compare their open roles or funding with the startups'.
- **Microsoft and Google LinkedIn posts:** we read their main company pages, not the
  security-specific showcase pages. Our LinkedIn collector hasn't been tested on showcase pages.
  Most of those company posts won't be about security, and our review step should set them
  aside.
- **Incomplete readings:**
  - Arctic Wolf's LinkedIn profile came back, but the collector set it aside, so it has no
    headcount yet. That doesn't affect the map, because incumbents aren't placed.
  - Leidos's Crunchbase record was set aside the same way.
  - Neither has been looked into yet.
- **Other customer sites:** this only applies to the AI in the SOC market. The other Market
  Monitor sites (Oviva, Panaya, Sunstar) don't have the incumbent option yet.
- **Still missing data:** four vendors have no logo (Andesite, AquilaI, HTCD, SOCNova), and
  AquilaI has no colour. NextSOC and SOCAI are waiting on facts we don't hold: NextSOC's
  headquarters country, and a verified LinkedIn page for SOCAI.
