# Future Horizons download fix, and news-feed narratives that stay cached for the day
_2026-09-03 · Foresight: Future Horizons tab download; Explore: news feed narratives_

## What shipped
- The Future Horizons tab no longer shows a download button for a topic that has never had a Future Horizons run. Before, it borrowed the most recent Consensus run and the download failed with "not found".
- When a topic has both kinds of run, the Future Horizons tab now always picks up its own most recent run, not whichever run was saved last.
- The narratives on the Explore news feed are now generated once per topic per day and reused for the rest of the day, instead of being rebuilt every time a new article arrives.

## Why it matters
An analyst on the sunstar site opened Future Horizons for "Oral-Systemic Health Research", saw a download button, and got a 404. The tab had been handed the Consensus analysis because that was the newest thing saved for the topic. Now the tab only shows cached results of its own kind, and offers Generate when there are none. The Consensus tab, Strategic tab and the others get the same rule.

The news feed narratives were being rebuilt on almost every visit on sites with a steady flow of social posts, because the saved copy was tied to whichever article was newest. Each rebuild is an AI call per topic, so opening the feed on a seven-topic site cost seven calls and a wait of ten to twenty seconds per topic. The saved copy is now tied to the topic and the date range instead. Opening the feed again the same day is instant. The regenerate button still forces a fresh build.

## Release notes (copy-ready)
- Fixed: the Future Horizons "Download interactive HTML" button no longer appears, and fails, on topics that have only a Consensus analysis.
- Fixed: each Foresight tab now loads its own most recent cached analysis rather than the most recent analysis of any tab.
- Improved: news feed narratives load from cache for the rest of the day after their first build. Use the regenerate button to rebuild early.

## Demo / walkthrough
Foresight, pick a topic that has a Consensus run but no Future Horizons run, open the Future Horizons tab. You see the Generate prompt, not a download button. Generate once and the download button appears and works.

Explore, news feed, open the narratives once and let them build. Reload the page: they appear immediately.

## Positioning notes
None. This is a correctness fix with no new capability.

## Limits and what's next
- Live on sunstar and bugfixing. Copied to oviva, wiley, wileytest, ibaset and pearson without a restart, so those sites pick it up when they next restart. The Future Horizons tab fix does not apply to wiley, wileytest, ibaset and pearson at all; they run older code with the same fault.
- Narratives now refresh once a day per topic. An article that arrives at noon is not in the narratives until the next day unless someone clicks regenerate. The highlights panel on the same page still uses the old newest-article rule and was not changed.
