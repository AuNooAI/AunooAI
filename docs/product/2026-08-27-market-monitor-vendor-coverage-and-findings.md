# Market Monitor: outside coverage per vendor, and a Findings tab that lists findings
_2026-08-27 · Market Monitor (bugfixing tenant): Findings, Analysis, Collection and vendor pages_

## What shipped
- Every article in the corpus that names a tracked vendor is now credited to that vendor. Before today only 28 articles in the whole database were, across 84 vendors.
- The Findings tab lists the findings: what changed, who said it, how much it matters, with the evidence one click away. The dashboard it used to show is now the Analysis tab.
- A strip at the top of Findings says what the period recorded: posts the vendors published, articles about them by somebody else, open roles, headcount moves, vendors that went quiet.
- A vendor's own blog is now counted as the vendor's own voice, not as outside coverage.
- Charts that had nothing to show no longer draw: a one-bar chart, a two-point trend, a benchmark of zeros.
- The vendor map works again, vendor-page events stop warning on every row, and the Wire says which companies in a story are ones we track.

## Why it matters
**Outside coverage was missing, not zero.** The market question is whether anyone other than the vendor is talking about it. The system had no step that connected a news article to the vendor it named, so every "earned mentions" figure, the mentions third of the Activity Index, and the vendor page's "External mentions" read 0 for almost every company. An analyst reading that would conclude the market is quiet. It is not: over the last 30 days, 21 articles by outsiders name 9 of these vendors, against 3 articles and 2 vendors the day before. Prophet Security's page went from 51 "external mentions" — all of them its own blog — to 1 real one. Who feels it: the analyst using the index to rank vendors, and anyone reading a vendor page.

**The Findings tab now answers the question it is named for.** The tab showed a twenty-panel dashboard and a paragraph of AI prose that named AWS and Anthropic as this market's key actors. Neither is a tracked vendor. The findings themselves — 46 in the last 30 days, deduplicated and tied to evidence — were being produced and never shown. Now they are the page. Each row says whether it is the vendor's own claim or something an outside source reported, which is the first thing a reader needs to weigh it. Who feels it: the buyer or analyst who opens the tab to find out what changed.

**Charts no longer invent confidence.** A bar chart with one bar, a trend line through two points its own caption called untrustworthy, a benchmark reading "0 against a market median of 0 (+0%)" — each looked like a measurement. They now collapse to a sentence saying what is known and what would be needed to say more. Who feels it: anyone who would otherwise have quoted the chart.

## Release notes (copy-ready)
- Market Monitor now credits news and social posts to the vendors they name. Outside coverage per vendor, the earned-mentions benchmark and the Activity Index all use it.
- The Findings tab lists the market's findings, grouped by theme, each marked as the vendor's own claim or independently reported. The previous dashboard is the Analysis tab.
- A vendor's own website is counted as its own voice, not as outside coverage.
- Panels with too little data show a plain statement of what is missing instead of a chart.
- Vendor map restored; vendor-page events show a warning only where a source is actually missing.

## Demo / walkthrough
Explore → Market Monitor → **Findings**. The count line reads "46 findings in the last 30 days · 1 reported by someone other than the vendor". Tick "Only findings someone other than the vendor reported" to see that one. Expand any row for the body and the strongest-evidence link. Switch to **Analysis** for the leaderboard; sort by "earned mentions" to see the vendors outsiders wrote about. Open **Radiant Security** from the leaderboard: the Coverage panel shows own posts apart from external mentions, and the Benchmark's "Earned mentions" row plots it against the market. Collection → **Wire**: each event names the tracked vendor as a chip and any other company as plain text.

## Positioning notes
This closes the gap between "we collect what the vendor says" and "we know what the market says about the vendor". Until today the product could only truthfully claim the first. The corroboration marker on each finding ("the vendor's own claim" vs "reported by N outside sources") is the honest version of a claim competitors make loosely: it shows the reader the evidence class rather than asserting a verdict.

## Limits and what's next
- Matching is by reviewed keyword, so a post that says "the Dropzone thing" without the name is not credited. Two keywords collided today (a hashtag, a Korean given name) and were fixed by editing the keywords, which is the intended maintenance path.
- Every finding in this period is still the vendor's own claim: findings are synthesised from evidence, and the outside coverage attributed today has not yet been synthesised into findings. The list will change as that runs.
- The vendor page's Coverage panel is all-time; the market overview follows the period selector. The panel now says so, but the two numbers will differ.
- Not built: the activity-map scatter, activity change versus the prior period and "fastest rising", because there is one period of data so far and those would be invented metrics.
- LinkedIn jobs returned listings for 16 of 83 vendors on its first successful run. Treat "no open roles" for the rest as unconfirmed until a second run agrees.
