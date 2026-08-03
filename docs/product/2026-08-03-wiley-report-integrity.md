# Every number in a customer report now has to earn its place
_2026-08-03 · Wiley Horizons quarterly deliverables: deck, HTML report, Word letter_

## What shipped

- Reports can no longer state a figure that none of their sources contain. The checks now
  understand Indian-English units (a "lakh" is 100,000), so a headline saying "1.4L" can never
  become "1.4 million" in a report.
- Organisation names get the same treatment: if no source behind the report mentions a company,
  the report cannot name it. This is the guard that would have caught a letter naming the
  customer's own retired imprint as a struggling competitor.
- The "82% consensus" badges are gone. That number was an estimate the AI was asked to invent,
  not a measurement, and two runs of the same analysis gave different values. Consensus is now
  described in words ("most scenarios expect…"), and the only percentages left are ones
  computed from data.
- The article list behind each topic is cleaned before analysis: known misinformation sites are
  excluded, syndicated copies of the same story count once, and a cheap AI pass drops articles
  that merely share a buzzword with the topic. On the reviewed topic this removed 18 of 90
  articles, including a corporate-video funding story that had been cited as evidence about
  fake peer reviewers.
- Every report now states which analysis run it came from. If a deck and an HTML report were
  built from different runs, the mismatch is visible on the page instead of discoverable only
  by a careful reader.
- Reader-facing polish: the 24 "black swan" cards show their titles again (they all rendered
  as a dash), every inline citation up to [90] now resolves to a numbered reference list,
  grouped citations like [44, 52] are clickable, and the timeline says 2026 is the present —
  not 2025.
- Internal configuration no longer leaks into the deliverable: no AI model names, no settings,
  and the coverage slide lists only the topics this customer pays for instead of the whole
  workspace.

## Why it matters

Before: a research-integrity report went to a scholarly publisher with a headline figure
inflated tenfold, a percentage presented as a measurement that changed between runs, and their
own former imprint listed as a third party in trouble. Any one of these, spotted by the
customer, undermines the entire deliverable — this customer employs people whose job is
spotting exactly this.

Now: figures, names, and percentages are checked against the sources before the document
renders, and the evidence list behind each topic is actually about the topic. The person who
feels the difference is the analyst who signs the report — and the customer contact who no
longer has to.

## Release notes (copy-ready)

- Fact-checking now covers numbers and organisation names against the report's own sources,
  including non-Western number units.
- Consensus is described qualitatively; invented percentage badges removed.
- Source lists are screened for relevance, duplicates, and low-credibility publishers before
  analysis.
- Full clickable reference lists in the HTML report; scenario cards, timelines, and dates
  corrected.
- Each report states the analysis run it was built from.

## Demo / walkthrough

Forecast Tracker → Topic Reports → generate a report, then download the HTML and the deck.
The "Article References" section now lists the full numbered corpus; the "Analysis
Provenance" section at the bottom (and the matching slide at the end of the deck) shows the
run IDs.

## Positioning notes

The pitch line this protects is "expert human oversight on every output". The review showed
the corpus contradicting that line; the screening and grounding steps close the gap between
the claim and the artifact. No new competitor claim — this is credibility defence.

## Limits and what's next

- The grounding checks run on the executive letter; scenario prose in the topic reports relies
  on prompt rules plus the cleaned corpus, without a deterministic per-sentence check.
- Closed later the same day: exports are now pinned to the analysis runs the deck was built
  from, so a deck and an HTML report of the same period always describe the same analysis.
  Reports generated before today fall back to the old behaviour, with the run IDs printed so
  a mismatch is visible.
- The relevance screen errs toward keeping borderline articles and can wrongly drop an
  occasional relevant one (one of 15 drops in testing).
- The existing Q3 files were generated before these fixes and stay wrong until regenerated.
- The team slide's cybersecurity-heavy credentials are a content decision, not a code fix.
