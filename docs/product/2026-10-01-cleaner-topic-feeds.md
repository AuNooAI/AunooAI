# Topic feeds show each story once, and keep press releases out where they don't belong
_1 October 2026 · topic news feed, Explore, search, the research assistant and MCP; time-to-impact labels_

## What shipped
- When several outlets carry the same story, the feed shows it once instead of once per outlet.
- Paid press releases no longer appear as news in topics that don't want them.
- Each topic decides whether to show press releases. Market-watch topics keep them, because a
  vendor's own announcements are the point there.
- Time-to-impact labels are counted from today's date. Before, the AI could count from a year
  that had already passed.

## Why it matters
**Repeated stories.** Before, an AP or Reuters story picked up by several outlets appeared in a
topic's feed once per outlet. A copy of a page that differed only in its tracking code also
counted as a new article. On our demo site, 7% of the articles over 30 days repeated a story
already in the same topic, and on the Wiley site 11% did. Now the feed shows the first copy we
collected and keeps the others in the background. Analysts see fewer repeats, and the research
assistant no longer counts one story as several.

**Press releases.** Before, a market-research press release about batteries passed the same
relevance check as a news report, because it is about batteries. On the Wiley site, wire
releases made up 6.7% of readable articles over 30 days. Now every article is labelled as news or
a press release when we collect it. A topic that hides press releases doesn't show them in the
feed, in search, or to the research assistant.

**Dates.** Before, the AI writing the time-to-impact explanation did not know today's date.
It described a 2027 launch as "about three years away" in September 2026. Now it is told the
date, and the exact calendar dates for each option ("Short-term: April 2027 to April 2028").

## Release notes (copy-ready)
- Topic feeds now show a story once when several outlets carry it.
- Press releases are labelled as press releases. Each topic chooses whether to show them.
- Time-to-impact labels are now counted from today's date.

## Demo / walkthrough
On the demo site (bugfixing), open the news feed and choose the "European Battery Industry"
topic. The Volkswagen–Gotion story appeared three times and the Sagunto plant story twice; each
now appears once. The two market-report press releases are gone.

## Positioning notes
This matters for the "maintained, evidence-backed view of a market" pitch made to PowerCo today.
A feed that repeats one wire story five times looks like five sources agreeing. Showing each
story once makes agreement and disagreement between real sources easier to read.

## Limits and what's next
- **Same-story matching is title-based, so it isn't perfect.** We checked 50 random links by eye
  at a time. Early checks found wrong links, and each kind got its own rule. The final checks
  on each site found no clear errors and one borderline match: two different articles about the
  same wedding. Two reports about the same event with very different headlines stay as
  separate articles.
- **The feed does not yet say how many outlets carried a story.** The count is stored, but
  showing it needs a UI change.
- **The Wiley sites keep press releases in most topics for now.** M&A Updates and Patent Cliffs
  hide them. Every other topic there still shows them until someone decides topic by topic,
  because for deals and filings the press release is often the primary source.
- **Time-to-impact is better but not reliable.** In testing, the AI chose the right window in 2
  of 3 runs.
- **Rollout status:** live on the demo site and on both Wiley sites.
