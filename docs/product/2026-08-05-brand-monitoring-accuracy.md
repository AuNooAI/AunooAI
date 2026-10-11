# Brand monitoring stops reporting things that are not about the brand
_2026-08-05 · Brand Watcher: the adverse-media digest email, brand keyword setup, and topic filing_

## What shipped

- The daily adverse-media email now checks whether an article is actually adverse before
  reporting it. Previously it reported any category whose article count doubled, whatever those
  articles said.
- Brand keywords now search for the brand name as a phrase. Previously a two-word keyword matched
  any article containing both words anywhere, so "Signal AI" matched 51,175 articles.
- The keyword suggestion tool produces phrase keywords, so new brands set up from now on do not
  inherit the problem.
- Articles are analysed under the topic they belong to. One topic had been analysed under a
  different topic's settings for months.
- Saved reports record which AI model actually wrote them, and carry the correct date.

## Why it matters

**The digest reported research papers as reputational risk.** A customer received an
"Adverse-media digest" whose headline finding was a spike in Wiley coverage. The articles behind
it were a hemodialysis meta-analysis, a protein-ligand study and a swallowing-disorder protocol —
papers Wiley had published. Nothing adverse, and not coverage of Wiley at all. The email's own
summary paragraph even said the spike "reflects legitimate scholarly output rather than
reputational risk", and sent it anyway, because the alert and the summary were produced by
different steps. The alert step measured how many articles arrived, never what they said. It now
screens them first, and this specific email would not have been sent.

**Keyword setup produced searches far wider than the brand.** The setup tool asked an AI to
suggest keywords and never told it to write them as phrases, so they came back as loose words.
The effect compounds: a brand watch for a company called Signal AI was reading essentially the
whole AI news stream. Across the five customer sites we measured, one topic's keywords reached
92,057 articles and now reach 593. The analyst sees the difference immediately — fewer items in
the queue, and the ones there are about the brand.

**One publisher's coverage was being analysed as a different publisher's.** A topic named
"Brand Monitoring Springer" had a trailing space in its name. The lookup that selects a topic
tidies the name it is given but the stored name was never tidied, so the two never matched. When
that happens the system silently keeps whatever topic was already selected — the logs show it
falling back to Wiley 1,523 times in a single day. Springer's articles were scored against
Wiley's categories and signals. 9,209 stored records were corrected along with the name.

**Reports named a model that never ran.** Model names in our configuration are aliases, and most
point at a different vendor: a report generated with "gpt-5.4-mini" is written by Claude Haiku
4.5. Saved reports recorded the alias. Under EU record-keeping obligations that is a compliance
problem, not a cosmetic one. Reports now store the model that actually ran alongside the name
that was requested. Separately, reports were dating themselves from the model's training data —
one generated in August 2026 came out headed "August 2025".

## Release notes (copy-ready)

- Adverse-media alerts are now screened for adverse content before they are sent. Coverage
  volume alone no longer triggers an alert.
- Brand keywords search for the brand name as a phrase rather than as separate words, sharply
  reducing unrelated articles in brand queues.
- The keyword suggestion tool now generates phrase keywords.
- A topic-name fault that caused one topic's articles to be analysed under another topic's
  settings has been fixed, and the affected records corrected.
- Saved reports now record which AI model produced them, and use the correct date.

## Demo / walkthrough

Brand Watcher → any brand → the daily digest email. Compare an email from before 5 August with
one after: the "coverage spike" alerts and their article lists are gone unless the articles
carry an adverse finding.

Keyword setup: Brand Watcher → brand → Keywords. Suggested keywords now appear wrapped in
quotes. Existing keywords on the five configured sites have already been converted.

## Positioning notes

This closes the most obvious objection a buyer would raise in a first demo: an adverse-media
product that sends alerts about things that are not adverse is not usable, and the fault is
visible in the first email they receive. It does not yet close the harder question of whether we
find the adverse events that exist — see below.

## Limits and what's next

**This makes the product quieter, not more complete.** Everything above removes false alerts. It
adds nothing to detection. The honest position for a sales conversation is that we have fixed
precision and not yet demonstrated recall.

**The sources that carry genuine adverse events are not producing.** CourtListener, which would
supply litigation, has never returned a single record for any brand. SEC EDGAR has returned
nothing since 9 July. Those are where lawsuits and filings live. Until they work, a brand could
be sued and the system would not know.

**Twelve articles in three weeks.** That is how many genuinely brand-relevant articles one
monitored publisher produced. Whether that reflects a quiet period or a coverage gap is not yet
established, and it should be before the product is sold on coverage.

**Some keywords were deliberately silenced.** At the customer's instruction, 61 keywords whose
phrase form returns nothing were quoted anyway. Terms like "Pearson digital learning" now match
nothing rather than casting a broad net. This trades recall for precision on purpose; if
coverage of a business line disappears, this is why.

**Ten collection sources on stopped customer sites still point at topics that do not exist**, and
one site is running an entirely different customer's topic configuration. Those are dormant while
the services are stopped and will misbehave on restart.

**Not yet proven in production.** The digest fix has been verified by recomposing today's email
(it produces no alerts and no article links). The keyword changes take effect at each group's
next scheduled run — the earliest is 21:50 on 5 August — so the reduction in queue noise has been
measured against the search index, not yet observed end to end.
