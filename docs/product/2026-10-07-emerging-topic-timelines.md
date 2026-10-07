# Emerging topics now show the story they are named after
_2026-10-07 · Emerging Topics (topic cards, events timeline, current status) on bugfixing, wiley and wileytest_

## What shipped
- Each emerging topic is now built only from articles about that story.
- Timelines list events from that story, not from unrelated news that happened to be nearby.
- Topics name a specific company, product, person, law or event.
- Stories that only one or two articles cover no longer appear as emerging topics.
- A story whose name changes between runs stays as one topic.

## Why it matters
**Before:** a topic's timeline could be mostly unrelated news. "Meta's Free AI Agent vs Google
Paywall Strategy" listed an FTC investigation, an IBM product and two security-vendor launches.
None of its 30 articles mentioned Meta or Google. On wileytest, topics appeared under the wrong
subject entirely, such as a court ruling on a shooting under Patent Cliffs.

**Why:**
- Topics read articles that the platform had already rejected as off-subject.
- The search that collects a topic's articles could not find stories by name.
- The step meant to remove off-topic articles only checked half of them.

**Now:** each topic is collected by the names it is about, and every article is checked
before it counts. On wileytest, the Gemini 4 Argon launch went from 0 matching articles to 30.

**Who notices:** analysts reading topic cards, and anyone forwarding a topic's timeline or
status to a client. A timeline that cites unrelated events cannot be trusted or sent on.

## Release notes (copy-ready)
- Emerging-topic timelines now only include events from the topic's own story.
- Topics are built only from articles that passed the site's relevance check.
- Topic names now name a specific company, product, person, law or event.
- A story reported under a slightly different name no longer appears twice.

## Demo / walkthrough
Open Emerging Topics on wileytest and pick any topic. Expand Events Timeline, then click
through to the articles. Every timeline entry should match one of the listed articles, and every
article should be about the topic's named story. Good examples to open: "AMD Acquires World
Labs for $8.2B" and "FlyDubai Flight FZ1073 Cockpit Attack".

## Positioning notes
This supports the claim that every item we surface traces to its sources. A timeline whose
events don't match its own article list would have undercut that claim in front of a customer.

## Limits and what's next
- **Fewer topics.** Each run now keeps the themes that have at least 3 checked articles. A run
  on bugfixing's SOC topic kept 1 of 9 proposed themes. Brand-monitoring topics on wileytest
  produced none, because their candidate stories each had 1-4 supporting articles. That is
  thin coverage, not a fault, but a sparse page may look like one.
- **Only three sites.** bugfixing, wiley and wileytest have the fix. The other customer sites
  still run the old code, and their existing topics still carry the old timelines.
- **Old topics.** We retired all 330 old topics on wileytest and 6 on bugfixing. Topics on
  other sites will age out on their own.
- **Broad labels can still slip through.** "Physical AI Era in Warehouse Robotics" was created
  before the prompt change and is still active on wileytest, with two loosely related entries
  in its timeline.
- **The underlying search is still weak for short queries.** We worked around it by matching
  on names. A better search model would help Auspex and the other search features too.
