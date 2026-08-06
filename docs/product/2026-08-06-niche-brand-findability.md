# Coverage of rarely-headlined brands now surfaces everywhere
_2026-08-06 · article tags, Auspex chat, Brand Watcher — all customer sites_

## What shipped
Three connected improvements for brands that get mentioned inside articles rather than in
headlines:

- Every collected article now carries the search term that found it as a visible tag. A
  sector report that names a customer's brand in its ninth paragraph is now labeled with
  that brand, so search, the AI assistant, and the Brand Watcher can all see the connection.
- The Auspex chat assistant no longer fails on the newest Claude models, and no longer
  leaks internal markers like "[/TOOLS]" into replies.
- The Brand Watcher on the ibaset site went from empty to populated: its classifier had
  never run a first full pass, and brand names spelled differently by the press
  ("iBase-t") were invisible to it. Both fixed, with the full backlog classified.

## Why it matters
Before: a customer whose brand rarely makes headlines could have real coverage in the
system that nothing displayed — the assistant said "no articles found", the Brand Watcher
showed nothing, and search came up empty, all while the articles sat in the database. The
platform's layers assumed the brand name appears in an article's title or summary, which
is true for famous brands and false for most mid-market ones.

Now: the reason an article was collected travels with it. If it was found because it
mentions the brand, that fact is visible and searchable everywhere, regardless of where in
the article the mention sits.

## Release notes (copy-ready)
- Articles now display the monitored keyword that matched them as a tag.
- Fixed: the AI assistant returned an error when used with the newest Claude models.
- Fixed: brand coverage mentioned only in article body text did not appear in the Brand
  Watcher or assistant answers.

## Demo / walkthrough
ibaset site: Brand Watcher tab now shows classified coverage per brand; open any Tulip
Interfaces article and the brand appears in its tags; ask Auspex about a brand with the
topic scope selected and the coverage is in context.

## Limits and what's next
- Tags make body-only mentions findable by exact term; the semantic search index is still
  built from titles and summaries, so meaning-based search for such brands remains weaker
  than term search. Rebuilding embeddings to include tags is the follow-on if needed.
- The tag stamp applies from today's collections onward; ibaset's history was backfilled,
  other sites' history was not (their brands appear in headlines, so nothing is missing in
  practice).
