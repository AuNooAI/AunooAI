# Brand monitoring search is working again, and article text no longer goes to OpenAI
_2 August 2026 · Brand Watcher search and story grouping · data handling_

This covers the customer-facing half of the day's work. The engineering half — the database
migrations, the index rebuilds, the site-by-site rollout — is in `docs/changes.md` under the
same date.

## What shipped

- **Search and story grouping work again on the Wiley brand monitoring site.** They had been
  broken since 5 July. Alerts kept arriving the whole time, which is why nobody spotted it.
- **The four weeks of missing coverage has been recovered.** 26,348 articles that the system
  collected but could not index are now searchable.
- **Article text is no longer sent to OpenAI to build the search index.** Three of the four sites
  moved to a model that runs on our own hardware. The fourth is in progress today.

## Why it matters

### Searches were quietly missing a month of coverage

To search by meaning rather than by keyword, we turn each article into a numeric fingerprint. On
the Wiley brand monitoring site, a configuration change on 5 July left the software writing
fingerprints in one format while the database expected another. Every attempt failed.

Nothing looked broken from the outside. Brand alerts kept firing every week, because alerts match
on keywords and classifiers and never touch the fingerprints. What stopped was everything that
answers "what else is connected to this story" or "find me coverage like this". Story grouping
made its last update on 13 July and then stopped. Searches still returned results, but never
anything published after 5 July.

That is the worst shape a failure can take. A visible error gets fixed the same day. This one
returned plausible older articles and looked healthy for four weeks.

Both are fixed. The 26,348 articles collected during the gap have been processed and are
searchable, and the software and database now agree on the format.

*Who noticed: anyone searching brand coverage, or looking at how stories cluster together.*

### Article text stops leaving our systems for indexing

Building those fingerprints was the last step that sent article text to OpenAI. Everything else
had already moved to AWS Bedrock or to models running on our own hardware.

Three of the four sites now build fingerprints locally, so no article text leaves the host for
that step. The fourth is being converted today and is roughly a fifth of the way through.

This is a straightforward answer to a question buyers ask: which third parties see the content
you process. One fewer name on the list, and the remaining ones are contracted infrastructure
rather than a general-purpose API.

*Who notices: anyone answering a security questionnaire or a data-residency question.*

## Release notes (copy-ready)

- Fixed: on the Wiley brand monitoring site, articles collected after 5 July were not being added
  to the search index. Searches and story grouping missed them. All affected articles have been
  reprocessed and are now searchable.
- Changed: article text is no longer sent to OpenAI to build the search index. This now runs on
  our own hardware. One remaining site is being converted.

## Demo

Search any brand for coverage from mid-July onwards — results from that window now appear, where
before the newest result was 5 July. Story groupings on the Brand Watcher tab will also start
growing again as new articles arrive.

## Positioning notes

Be precise about the failure rather than vague, because the precise version is more defensible.
Coverage was incomplete for a defined window on one site, the gap has been reprocessed, and no
data was lost — the articles were always collected and stored, they were just missing from the
search index.

The data-handling change is worth stating plainly in security reviews. "Article text is processed
on our own infrastructure and by contracted cloud providers, not sent to general-purpose AI APIs"
is now true of three sites and shortly all four.

## Limits and what's next

- **One site is still converting.** It is at 52,200 of 265,057 articles as this is written, at
  about 17 per second, so roughly three and a half hours. Its search results are thin until that
  finishes, newest articles first. Its search index is rebuilt automatically afterwards.
- **New articles have not yet been seen going into the index end to end.** The recovery of the
  26,348 backlog articles proves the write path works. But new articles are only indexed after
  they pass the relevance and quality filters, and on that site nothing has passed those filters
  since the fix went in at 15:14 — the pipeline log reads `processed: 2, enriched: 2, relevant: 0,
  saved: 0`. So 160 articles collected since then are sitting unindexed, which is the filters
  doing their job rather than a fault, but it means the live path is unproven until an article
  qualifies. Worth confirming tomorrow.
- **Nothing alerted us.** The failure ran for four weeks and was found by accident, while
  checking an unrelated line in a technical document. There is no monitor on "are articles still
  being added to the search index". Until there is, the same class of failure can recur and go
  unnoticed for just as long. This is the most important gap on this page, and it is not fixed.
- **Recovery is a manual job.** The background task that fills coverage gaps exists but is not
  switched on anywhere, despite internal documentation saying otherwise. New articles are indexed
  as they arrive, so a gap will not appear on its own — but if one does, somebody has to notice
  and run the recovery.
- **Story grouping has not been seen catching up yet.** It should resume by itself now that
  fingerprints exist, since it simply skips articles that lack one. That is expected behaviour,
  not verified behaviour, and it is worth checking in a day.
- **The figures here were measured today**, not estimated: the 26,348 recovered articles, the
  5 July and 13 July dates, and the weekly alert counts that show alerting never stopped.
