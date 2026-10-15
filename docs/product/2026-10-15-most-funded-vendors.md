# Most funded vendors, compared like for like
_15 October 2026 · Market Monitor Analysis view, and the market tools on the Claude connector_

## What shipped
- A "Most funded vendors" card that ranks a market's vendors by disclosed total funding.
- Large incumbents are left out of the ranking, so startups are compared with startups.
- Claude, connected to a market site, now knows which vendors are incumbents and which funding figure to use.

## Why it matters

**Funding at a glance.** Before, the Analysis view showed funding stage and Crunchbase's scores, but not who had raised the most. Now the top 10 is a single card, with the market median beside it. In the AI in the SOC market, 7AI ($202M) and Exaforce ($201M) have each raised about 17 times the median of $12M. That gap is the kind of finding an analyst or a vendor's marketing team would want to quote.

**Like for like.** A company such as Arctic Wolf (about $900M raised) or Torq ($332M) would top any ranking it entered. Both are large incumbents, the same group as CrowdStrike and Palo Alto Networks: they are in the market, but they are not startups. The card leaves them out and says how many it left out (17 in this market), so the ranking stays a comparison between vendors of a similar kind.

**Honest gaps.** The card says how many vendors have a disclosed total: 50 of 98 in this market. It also says why the other 48 have none: every one has told the market it is undisclosed or bootstrapped. "Not disclosed" is a fact about the company. "Not found" would be a gap in our data, and there are none.

**Claude gives the same answer.** A Claude session asked for the top 10 by funding got the ranking right. But it said Torq and Arctic Wolf were "missing" and would probably rank near the top. That was wrong: both totals were on file, and both are incumbents. The data Claude reads now marks each vendor's status and names the funding figure to use, and the funding analysis it can call carries the same ranking as the card.

**The full funding list agrees with the card.** The vendor funding list in Market Monitor, and its CSV export, read an old copy of each total taken when the market was first imported. Nobody updates that copy, so the list showed 36 AI in the SOC vendors with a total when we have 53, and it called most of the others "unavailable". It now reads the same totals as the card. The vendors without a figure show as undisclosed or bootstrapped, which is what they told us. The same fix is on every market site; AI Security gained the most, with 41 of its 56 vendors' figures corrected.

## Release notes (copy-ready)
- New "Most funded vendors" card in Market Monitor → Analysis → Funding: the top 10 by disclosed total, with the market median.
- Large incumbents and acquired vendors are left out of the ranking, and the card says how many.
- Claude on a market site now sees each vendor's market status (active, incumbent, acquired) and its current funding total.
- The vendor funding list and its CSV export now show the current totals, and say "undisclosed" rather than "unavailable" for vendors that have not disclosed.

## Demo / walkthrough
1. Open Explore → Market Monitor on the new interface (/explore/next) and pick "AI in the SOC".
2. Go to Analysis and scroll to Funding. "Most funded vendors" is the first card.
3. In Claude, ask the AI SOC connector for the top 10 vendors by funding. Torq and Arctic Wolf now come back as incumbents with their totals, not as gaps.

## Positioning notes
Funding league tables are what most market maps lead with, and most of them mix incumbents and startups or hide what they don't know. Ours separates the two and shows its denominator. For a buyer that means a fair comparison; for a vendor it means a ranking it can check and quote.

## Limits and what's next
- Totals are kept by hand from announcements. A round announced in the last few days may not be in yet.
- A round with no amount, such as Prophet Security's 8 October strategic investment from Amex Ventures and Citi Ventures, cannot change a total.
- The card is on bugfixing (aisocnews.com's site) only. Other market sites get it if they ask for it.
- The old interface (/explore) does not show the card; only the new one does.
- The funding list fix was live on five market sites by 16:03. On aisocnews.com's own site it goes live at the next restart, which was waiting for a quiet moment at the time of writing.
