# iBASEt monitoring — update, 6 August 2026

Summary: we found and fixed the reason your own brand column was empty, and your feed now
leads with the TA Associates investment story about iBASEt. We also audited the search terms
behind all five monitoring groups and extended three of them, and we fixed a statistic on
the collection page that overstated relevance.

## Your own brand now collects news

The iBASEt group had collected nothing since the site went live, while the competitor groups
worked normally. The cause was in our news source: searches for rarely-mentioned names could
hang until the collector gave up, and because each attempt failed silently, the group looked
healthy while every search it ran was dying. We fixed this platform-wide — stalled searches
are now retried a different way within seconds — and verified the fix on your group first.

Two configuration changes followed. We widened the group's look-back window to a year, since
the existing iBASEt coverage predates the last 30 days. And we found that the press writes
your name as "iBase-t" with a hyphen, which the official spelling can never match in search;
the hyphenated form actually returns more coverage than the official one, including the TA
Associates investment announcement. That story is now the top item in your brand column.

We also added sector terms so the column carries industry context alongside direct mentions:
"manufacturing execution system", "digital thread", and "MRO software". After the first full
run the group holds 28 collected articles, of which 12 were approved as relevant — the
investment story, MES and digital-thread market coverage, and an Airbus manufacturing story
— and 16 were correctly rejected as noise.

One expectation to set: iBASEt's direct press coverage is genuinely thin — two industry
reports in the last ninety days. The platform now catches all of it, plus the sector
coverage, and new mentions will arrive as they are published.

## Competitor tracking tuned

We ran the same check on the search terms behind the four competitor groups.

- **Siemens** — coverage often says "Opcenter" without the word "Siemens", so the existing
  terms were missing most of it. Added the bare product name, which more than doubles the
  matchable coverage.
- **SAP** — two of the three terms ("SAP DM", "SAP DMC") matched nothing at all in the news
  source, which is why this group had collected only noise. Added "SAP MES" and
  "SAP S/4HANA manufacturing", which together match over a hundred articles.
- **Dassault Systèmes** — same finding as your own brand: the press writes the name with the
  accent, and the unaccented term misses that coverage, including their Q2 revenue release.
  Added the accented spelling.
- **Tulip Interfaces** — checked and healthy; no change.

The first collection runs with the new terms have completed. The SAP group picked up its
first genuinely relevant article straight away; the other additions take effect from today's
collection onward, catching new coverage as it is published rather than backfilling old
market reports.

## Relevance percentage on the collection page corrected

The per-group relevance statistic had been computed from a raw text-similarity number that
rates almost anything as a near-match, which is why every group displayed close to 100%
relevant. It now reflects the platform's actual relevance decisions, so the number responds
when a group's terms are tuned. Percentages will look lower than before because they were
inflated, not because collection got worse.

## AI model transparency

Model selectors across the platform now list only the AI models that actually run on your
deployment (Claude, Amazon Nova, and Kimi, all hosted on AWS). Previously the lists included
legacy third-party model names that were silently rerouted. The model named on screen, the
model recorded with each analysis, and the model that did the work are now always the same
— relevant if you need to answer "which AI produced this?" for compliance purposes.

## Afternoon update — same day

Work continued through the afternoon; the items below are live on your site now.

### The Brand Watcher is populated

The Brand Watcher tab was empty this morning because its classifier had never made a first
full pass over your articles. It has now classified the collected coverage for all five
brands — including your own: the TA Associates investment story leads the iBASEt column.
Ongoing classification runs every six hours automatically.

### The Timeline is populated

The Timeline tab now carries 17 dated events extracted from your coverage: the Dassault
Systèmes ArisGlobal acquisition and Q2 results, the Siemens shipbuilding and chip-design
deals, SAP warehouse-automation coverage, and the iBASEt investment announcement. New
events are extracted nightly as coverage arrives.

### The assistant now finds brands that articles mention only in passing

Asking Auspex about a niche brand — yours, or a competitor like Tulip Interfaces — used to
return "no articles found" even when coverage existed, because the mentions sit deep inside
sector reports rather than in headlines. Three changes fixed this end to end: every article
now carries the search term that found it as a visible tag; the meaning-based search index
includes those tags; and the assistant sees them when it reads articles. The assistant also
now works with the newest Claude models (Sonnet 5 and Opus 5), which are available in the
model selectors.

### The AI disclosure now names the models that run

The "AI Technology Disclosure" shown on dashboards and in exports previously named GPT-4 —
a model your deployment does not use. It now names the models actually serving your site.
Given your sector's compliance environment, this matters: the disclosure, the audit trail,
and the executing model can no longer disagree.

## What to look at

Explore → News Feed: the iBASEt topic now has current content at the default 7-day range;
the full backfill, including the investment story, is visible at 90 days. Gather: the iBASEt
group card shows the collected/approved split with the corrected statistic. Brand Watcher:
per-brand coverage including your own column. Timeline: the extracted events. Auspex: ask
"latest on Tulip Interfaces" with any topic scope.

We suggest reviewing the approved lists after a week of collection and tuning from there —
in particular whether the "MRO software" term earns its place, and whether the SAP terms
bring in the coverage you expect.
