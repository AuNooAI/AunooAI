# Swiss Election Watch: a dashboard for disinformation aimed at Swiss voters
_2026-09-15 · Explore tab "Swiss Election Watch" on bugfixing_

## What shipped
- A new Explore tab that reads every article the Swiss election disinformation topic collects and answers: which storylines are circulating, who carries them, what they are aimed at, in which language, and what was done about it.
- Nine views: Overview, Narratives, Sources, Targets, Languages, Calendar, Responses, Insights, Articles.
- A weekly brief written from the data, one click, saved for sharing.
- Alerts when a new storyline appears on two outlets within two days, when one triples in a week, when it crosses from German into French or Italian, or when a deepfake targets a named person.
- The topic's sources were rebuilt the same day: twenty specialised feeds added, five general news feeds removed.

## Why it matters
Before, an analyst had a list of approved articles and a relevance score. Reading twenty of them to work out that three alternative outlets pushed the same claim about the neutrality initiative in the same week was manual work. Now the Narratives view shows the claim as one row with the outlets, the languages and the trend, and the Sources view shows the same thing as a grid of outlet by storyline.

Switzerland has a border that matters more than any canton line: language. A storyline that starts in German-language alternative media and turns up in French a week later is being carried across by someone. The Languages view shows exactly that, with the lag in days. Nothing else in the product does this.

The Calendar view plots storyline volume against the federal vote dates, so "activity rises three weeks before a vote" is a chart rather than a hunch. The next vote, 27 September with the neutrality initiative, is twelve days away as of today.

Silence is legible. A quiet week says how many sources were scanned and how many articles were gated, so an empty board reads as coverage rather than an outage.

## Release notes (copy-ready)
- New: Swiss Election Watch tab under Explore, with narratives, sources, targets, techniques, languages, calendar, responses and a weekly brief.
- New: alerts for new coordinated storylines, volume spikes, language-border crossings and synthetic media aimed at people.
- Changed: the Swiss election topic now draws on Swiss alternative and quality press, party press feeds, Swiss and European fact-checkers and disinformation trackers.

## Demo / walkthrough
Explore, then the "Swiss Election Watch" tab. Overview shows the week. Click Narratives, then any row, to see its articles and its language timeline. Sources shows the outlets and the who-carries-what grid. Languages shows crossings. Calendar shows the vote countdown, the daily chart with vote dates marked, and alerts. Insights has "Generate weekly brief". The "Analyse new" button at the top runs the extraction on any approved articles not yet analysed; the scheduler does the same every two hours.

## Positioning notes
This is the first module built for an election rather than a market or a brand, and the first with a language-crossing view. It is the concrete form of the narrative-intelligence story: storylines, carriers and targets as first-class objects, not article lists.

## Limits and what's next
- Attribution is what the articles say. The tool does not attribute operations itself, and every screen says so.
- The storyline grouping is done by a language model over a shortlist. It will sometimes merge two claims or split one. The article list under each narrative is there to check it.
- Volume is low today, a handful of on-topic articles a day. The design is for campaign volume in 2027; until then the value is baseline and early warning.
- Italian coverage arrives only through the firehose, with no dedicated keyword group. Social sources are off for this topic.
- RT DE's own feed blocks our collector; its Swiss items still arrive through the news API.
- Built on bugfixing only. Moving it to another site is a registry entry, a migration and a UI build.

Elapsed for an AI: about five hours end to end, including the source rebuild, the design spec and the verification passes.
