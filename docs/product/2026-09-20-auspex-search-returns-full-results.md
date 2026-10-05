# Auspex searches the whole topic again
_2026-09-20 · Auspex chat and research on bugfixing, wiley and wileytest_

## What shipped
- Auspex's semantic search returns a full set of matching articles for every topic. Before today it returned a handful, and for smaller topics none.
- Auspex's follow-up searches inside a research answer run again. They had been failing on every turn since an earlier change.

## Why it matters
Before, an analyst asking Auspex about a topic got answers built from the few articles the search happened to surface, sometimes none, so answers leaned on the model's general knowledge and cited little. A question about funding rounds in the SOC automation market found nothing at all. Now the same question returns thirty candidate articles and the answer cites the actual stories. The analyst using Auspex feels this on every question; the operator sees fewer "no results" turns in the logs.

The cause was in the database's vector index, which returns its nearest forty candidates first and applies the topic filter afterwards. A topic that is a small share of the whole article store was left with nothing. The search now checks how many articles the filter covers and scans them exactly when the set is small, which takes under a second for a typical topic and about two and a half seconds for the largest.

## Release notes (copy-ready)
- Auspex semantic search now returns the full result set for every topic, including small ones.
- Auspex follow-up searches during research answers work again.

## Demo / walkthrough
Open an Auspex chat on any market or brand topic and ask a specific question, for example which vendors announced funding this month. The answer cites articles from the corpus instead of stating it found nothing.

## Positioning notes
None. This restores expected behaviour; nothing to position.

## Limits and what's next
The largest topics take two to three seconds longer per search than before, because the exact scan replaces the index for them. Upgrading the database's vector extension from 0.6 to 0.8 removes that cost, since the newer version can keep searching the index until the filter is satisfied; that upgrade is pending. Only the three monolith sites have the fix; the SaaS side uses a different search path and was not affected.
