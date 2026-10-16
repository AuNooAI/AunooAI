# Auspex research reports keep their findings and their endings
_16 October 2026 · Auspex deep research (Explore page, "Research" mode) on wileytest and wiley_

## What shipped
- A research run now finishes on the server even if you close the tab, lose the connection or the site restarts mid-way; the report lands in the chat when it is done, and reopening the chat shows the run's progress.
- Hybrid research on wileytest reaches the open web again, through Bright Data instead of Google.
- Research reports no longer lose most of their findings part-way through the run.
- Reports no longer stop mid-sentence before the Limitations and References sections.
- If a report still runs over the length limit, the progress panel says so instead of ending quietly.

## Why it matters
**A run no longer dies with the browser connection.** Until today a research run only existed as long as the browser kept its connection open. Close the tab, lose Wi-Fi for a moment, or have the site restart, and ten minutes of work vanished with no message. The 12:43 and 14:40 runs on wileytest both went that way. Now the run is a job on the server. The page follows it, and if the page loses touch it catches up by asking the server; the finished report is saved into the chat either way, and opening that chat while the run is still going shows the progress panel again. The site also waits for a running research before it restarts.

**Web sources were missing.** You picked hybrid mode, and the report still said it used internal articles only. Google's search API had been refusing every request from wileytest, so the web half of hybrid returned nothing. Bugfixing switched to Bright Data for this on 14 October; wileytest now has the same.

Deep research works in stages. It plans the questions, pulls the articles, has the AI read them in batches of 50 and write down the findings from each batch, then writes the report from those findings.

Before today the reading step had a short answer limit. On wileytest the AI ran over that limit on 6 of the 8 batches it read today, and when it did we threw the whole batch away. The 12:43 run reached the writing step with one finding from four batches, so the report had almost nothing to say about the 199 articles it had read. The same happened on all three runs on 15 October.

The writing step had the same problem one stage later. Every report since 15 October ran into the writer's length limit, which is why they ended abruptly and never reached the References list.

Now the reading step keeps every finding that was completed before the limit, and both limits are higher. The analyst running a research question on ASML gets a report built from the batches that were read, with its last sections present.

Who feels it: the Wiley analysts who run deep research on wileytest. Nobody else has run deep research in the last 30 days.

## Release notes (copy-ready)
- Deep research runs finish on the server. Closing the tab or losing the connection no longer loses the run; the report is saved to the chat and the chat shows the run's progress when you come back.
- Hybrid research mode searches the open web again. Reports say how many web sources they used.
- Deep research reports now keep the findings from every article batch, including batches where the AI's answer ran long.
- Reports are allowed to be longer, so the Limitations and References sections are no longer cut off.
- If a report still hits the length limit, the progress panel tells you.

## Demo / walkthrough
Explore page on wileytest, switch Auspex to Research mode, pick a topic such as ASML Watch and ask a question. A full run takes about 10 minutes. The report should end with a References section.

## Positioning notes
None. This restores what the feature already promised.

## Limits and what's next
- Not yet exercised end to end. The first real run after the wileytest restart is the check. The run started at 13:35 today is still on the old code.
- wileytest still runs the old code until its next restart, which is waiting for article collection to finish.
- Web search is Bright Data now. A test search from wileytest returned 5 results in 4 seconds. Bright Data is uneven in practice: on bugfixing a query can take up to 90 seconds or come back empty, and then that query falls back to the site's own articles.
- The web budget is shared across all sites: 150 Bright Data calls a day, 25 per research run.
- A run interrupted by a site restart is not resumed. It is marked as interrupted and has to be started again; the page says so instead of waiting forever.
- The new behaviour has not yet been exercised with a real dropped connection. The check is to start a run, close the tab, and reopen the chat a few minutes later.
- Cost per run can go up to about $0.66 at list price when every stage uses its full limit, from about $0.36 for a run that lost most of its findings.
