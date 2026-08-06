# Gather page relevance counts now tell the truth
_2026-08-06 · Gather page, keyword/brand group statistics — all customer sites_

## What shipped
The "relevant" count and percentage shown for each monitored group on the Gather page now
reflect the platform's actual relevance decisions. Since early February they had been computed
from a raw text-similarity number that rates almost any article as a near-match, which is why
groups showed 90–100% relevance regardless of how noisy their collection really was.

## Why it matters
Before: an operator tuning a group's keywords had no usable feedback. A group collecting
mostly noise and a well-tuned group both displayed ~100% relevant, so the number could not
tell you whether a keyword change helped. On one new customer site the counter read 100% on
day one, which looked like a scoring failure and cost an investigation.

Now: the counter uses the same judgement the pipeline itself uses to approve or reject
articles. On our largest site, one group's displayed relevance moved from 81% to 4.6% — the
honest figure for a deliberately wide net — and a well-performing group settled at 49%. Groups
now differ from each other, and the number moves when tuning changes.

Who feels it: operators and analysts who tune keyword and brand groups, and anyone reading the
Gather page to judge collection quality. The articles themselves are unaffected — collection,
AI analysis, and what appears in feeds and reports never used the broken number.

## Release notes (copy-ready)
- Fixed: the per-group relevance count on the Gather page overstated relevance (often showing
  ~100%). It now reflects the platform's real relevance decisions.
- Expect displayed relevance percentages to drop after this update. The articles you see in
  feeds and reports are unchanged — only the statistic was wrong.

## Demo / walkthrough
Open the Gather page and look at any group's card: the relevant/irrelevant split and the
relevance percentage. Broad groups now show visibly lower percentages than tightly tuned ones,
and the number responds when a group's keywords or threshold change.

## Positioning notes
None specific — this is a correctness fix to an existing statistic, not a new capability. It
does remove a demo liability: a page where every group reads 100% invites the question of
whether the scoring works at all.

## Limits and what's next
- Percentages will look worse than before because they were inflated, not because collection
  got worse. Expect that conversation with anyone who watched the old numbers.
- Articles collected before February 2026 are counted from the older scoring format. That
  format was also a real relevance judgement, so mixed-age groups remain comparable.
- The fix changes the statistic only; it does not retro-score any article or change what is
  collected, analyzed, or shown in feeds.
