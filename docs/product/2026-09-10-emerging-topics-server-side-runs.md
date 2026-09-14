# Emerging Topics scans keep running when you leave the page
_2026-09-10 · Explore › Emerging Topics, all sites except abm_

## What shipped
- A scan now runs on the server. Reloading the page, switching tabs, or
  closing the browser no longer cancels it. Come back and the progress
  panel picks up where the scan is.
- The progress panel shows which topic it is on ("Topic 4 of 11: Haleon"),
  a bar for that topic next to the overall bar, the step it is in, and a
  running clock.

## Why it matters
An all-topics scan on a site with eleven topics takes about 45 minutes. Until
today it lived inside your browser tab: the bar crept a few percent per
topic, the deep-analysis step showed nothing for minutes at a time, and the
natural reaction, a reload, threw away the topic in progress. On sunstar
this morning that cost the Haleon scan after seven minutes of work.

Now the scan is a job the server owns. The page only listens. An analyst
can start a scan, go to a meeting, and find the results waiting; an operator
watching it can see "Topic 4 of 11, Deep analysis, 23m 10s" and know it is
alive.

## Release notes (copy-ready)
- Emerging Topics: scans continue on the server if you leave or reload the
  page, and the page re-attaches to a running scan automatically.
- Emerging Topics: the progress panel shows the current topic, per-topic
  and overall progress, the current step and elapsed time.

## Demo / walkthrough
Explore › Emerging Topics, clear the topic filter, press the play button.
Watch the panel, reload the page: it comes back on the same scan with the
button greyed out. Wait for "Batch detection complete".

## Positioning notes
None. This is table stakes for a long-running job; it removes a reason to
distrust the feature rather than adding a selling point.

## Limits and what's next
- A service restart still ends a running scan; the topics already finished
  are kept, the one in flight is marked failed.
- abm is not on this yet. Its Emerging Topics code is a version behind and
  needs the August update first.
- Only one scan per topic can run at a time; starting a second gets a clear
  "already in progress" message.
