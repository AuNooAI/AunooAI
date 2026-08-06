# The local relevance model was being asked to judge headlines with no article attached
_2026-08-06 · article relevance scoring, all sites_

**Audience note.** Mostly internal. There is no new screen and nothing a customer clicks. It
matters commercially for one reason: it lowers the cost of deciding which articles are worth
keeping, and makes that decision better at the same time. Sales should not describe this as a
feature.

## What shipped
The small local model that judges whether an article belongs to a topic was only ever shown the
headline, never the article text. It was trained on headline-plus-summary, so with no summary
it returned "not relevant" for essentially everything. It now gets the article text whenever we
have it, and when we genuinely have nothing to show it, we skip it rather than treat its silence
as a rejection.

## Why it matters
Two things were happening, and the second is the expensive one.

The model's opinion counted for 60% of the local relevance score. Because it was answering
near-zero for every article, that 60% was pulling every score down by the same amount before
anything else got a say. The system compensated by sending far more articles to a paid AI model
for a second opinion, which is why the results still looked broadly right — we were paying to
work around a local model we had already trained.

Measured on the iBASEt site's 72 collected articles, the local model given the article text
agrees with the expensive AI's verdict almost perfectly. On a scale where 0.5 is a coin toss
and 1.0 is perfect, it scores 0.98. Given only headlines, it scores 0.68 — close to guessing.
Same model, same articles; the only difference is whether it could see the article.

For customers this shows up as fewer irrelevant articles in the feed and faster collection.
For us it should reduce spend on relevance checks, though I have not yet measured how much.

## Release notes (internal only)
- Article relevance scoring now gives the local model the article text, not just the headline.
- When no article text is available, the local model is skipped rather than counted as a
  rejection, so its silence no longer suppresses the score.
- Applied to all seven active customer and internal sites. No change to any screen.

## Demo / walkthrough
None. There is no user-facing surface. The effect is visible only as better filtering over the
next few collection runs.

## Positioning notes
Supports the "we run our own models where it makes sense" line rather than reselling somebody
else's AI for every decision. Worth knowing internally that this claim was, until today,
weaker in practice than on paper.

## Limits and what's next
- Measured on one site and 72 articles, 21 of which were relevant. That is a small sample and
  the comparison is against the paid AI's judgement, not a human's. Treat 0.98 as "clearly
  works", not as a precise figure.
- The saving in AI calls is expected but unmeasured. Worth checking the usage ledger in a week.
- The model is still the shared one trained on a different customer's subject area
  (academic publishing). It performs well on aerospace brand monitoring anyway, which was a
  genuine surprise, but a subject-specific model may do better again.
- Articles already collected keep their old scores. Only new collection benefits unless we
  deliberately rescore.
