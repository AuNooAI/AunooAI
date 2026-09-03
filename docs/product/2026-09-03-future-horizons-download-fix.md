# Future Horizons download works again on topics that only have a Consensus run
_2026-09-03 · Foresight: Future Horizons tab, interactive HTML download_

## What shipped
- The Future Horizons tab no longer shows a download button for a topic that has never had a Future Horizons run. Before, it borrowed the most recent Consensus run and the download failed with "not found".
- When a topic has both kinds of run, the Future Horizons tab now always picks up its own most recent run, not whichever run was saved last.

## Why it matters
An analyst on the sunstar site opened Future Horizons for "Oral-Systemic Health Research", saw a download button, and got a 404. The tab had been handed the Consensus analysis because that was the newest thing saved for the topic. Now the tab only shows cached results of its own kind, and offers Generate when there are none. The Consensus tab, Strategic tab and the others get the same rule.

## Release notes (copy-ready)
- Fixed: the Future Horizons "Download interactive HTML" button no longer appears, and fails, on topics that have only a Consensus analysis.
- Fixed: each Foresight tab now loads its own most recent cached analysis rather than the most recent analysis of any tab.

## Demo / walkthrough
Foresight, pick a topic that has a Consensus run but no Future Horizons run, open the Future Horizons tab. You see the Generate prompt, not a download button. Generate once and the download button appears and works.

## Positioning notes
None. This is a correctness fix with no new capability.

## Limits and what's next
- Live on sunstar and bugfixing. Copied to oviva but that service was not restarted. wiley, wileytest, ibaset and pearson run older code that has the same fault and cannot take this patch as a plain file copy.
- Separate finding, not changed: the narratives on the Explore news feed regenerate whenever a new article arrives in the topic's window, because the cache is keyed to the newest article. On a site with steady social ingest that means an AI call per topic on nearly every visit. Whether to cache by topic and date window instead is a product decision about how fresh narratives must be.
