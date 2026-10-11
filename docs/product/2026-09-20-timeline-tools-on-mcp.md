# Your assistant can now ask Aunoo what happened
_2026-09-20 · MCP connector (the Aunoo tools an external AI assistant can call); bugfixing site only_

## What shipped
- Three new tools on the Aunoo connector let an AI assistant read the timeline we keep for each brand and topic.
- **List the timelines.** Which brands and topics have a timeline, how many events each holds, and when the latest was.
- **Get a timeline.** The current state summary and trend, any analyst notes, the monthly and weekly rollups, and the dated events for a period. Every event points at the articles it was built from.
- **What changed.** Everything since a date, split into new developments and stories that came back, with a count of how often each has resurfaced.

## Why it matters
Until today, the timelines only reached an assistant inside Aunoo's own chat and in the observer-agent reports. An assistant connected from outside, such as Claude or ChatGPT with the Aunoo connector, could search articles but could not ask "what has happened with this brand" and get our dated record. It had to re-read search results and guess at the order.

Now it can. An analyst who asks their assistant "catch me up on Torq since Monday" gets the events we already extracted, in date order, marked as new or ongoing, each with the articles behind it. That is the difference between a search summary and a record. The people who feel it:

- **Analysts and brand managers** get the catch-up answer with sources attached, ready to forward.
- **Anyone building their own agent** on the connector gets a probability-free, dated, cited feed of developments they can act on without a fresh search.
- **Buyers of the connector tier** get a reason to stay: the timeline deepens the longer the subscription runs, and a search cannot rebuild it.

## Release notes (copy-ready)
- The Aunoo connector now exposes the brand and topic timelines. Ask your assistant what has happened with a brand or topic and it can answer from Aunoo's dated record, with the articles behind each event.
- "What changed since" answers separate new developments from stories that have come back, and say how often each has resurfaced.
- Every event carries the articles it was computed from, so any claim can be checked.

## Demo / walkthrough
Connect an assistant to the site's connector and ask, in order: "what timelines does Aunoo keep", then "give me the timeline for the SOC Automation market for the last 60 days", then "what changed on the Swiss elections disinformation topic since 20 September". The third answer should list about ten new items and four ongoing ones, the ongoing ones being narrative spikes first seen on the 19th. There is no new screen in the web UI; the Timeline tab under Explore already shows the same data.

## Positioning notes
This is the first piece of the "assistant-first" direction written up in the positioning note of the same date. A general assistant with web search has no memory of how a story moved. This gives it one, and it is ours. It also answers the DIY objection from the same discussion: a person can build a nightly news pull in a weekend, but they cannot build months of dated history they did not collect.

## Limits and what's next
- **One site only.** Live on the bugfixing site. The six other sites with timelines and a connector (abm, oviva, sunstar, wbm, wiley, wileytest) do not have the tools yet. Each needs the same small copy and a restart.
- **Only scopes we already track.** A new brand or topic starts with an empty timeline and fills in after the first daily run. Backfilling a new scope from the articles we already hold is the obvious next step, and would make "day one" useful.
- **Some events cite no articles.** The Swiss elections narrative alerts and calendar entries are computed differently and carry no article list, so "show me the sources" returns nothing for them.
- **Long windows are trimmed.** A timeline answer is capped at 60 events and event descriptions are shortened, so a very busy topic over a long period comes back in slices. Ask for a shorter window or more than one call.
- **Not in the assistant's playbooks yet.** The connector's named prompts (brand briefing, deep dive, and so on) do not call the timeline tools. Adding a "catch me up" playbook would make the feature discoverable without the user knowing the tool names.
