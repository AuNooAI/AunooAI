# Perception scores for every brand, and charts you can read
_2026-08-27 · Brand Watcher: Perception and Comparison tabs_

## What shipped
- Perception scores now appear for brands whose coverage comes through a market watch, not only for brands with their own monitoring topic.
- The perception radar and the comparison charts show the primary brand plus the top five by volume by default, with the number adjustable and any brand one click away.
- Share of Voice folds the smaller brands into one "Others" slice instead of drawing thirty thin ones.
- Brand Watcher reopens on the tab you were using.

## Why it matters
**Scores where there were none.** A site that tracks a market of vendors rather than one house brand had a perception table that read "no data" for almost every vendor. The vendors' news was there, linked to each vendor by the article classifier, but the perception view was only looking in one place for it. It now looks everywhere the rest of Brand Watcher does. On the SOC-automation site, nine vendors score instead of two; on a publisher site each brand picked up about forty more articles behind its media score. Analysts feel this first; it is the difference between a table and a blank.

**Charts that can be read.** Overlaying thirty-four brands on one radar gives a grey disc. Defaulting to the brands that matter, and letting the analyst add one more, gives a chart that says something at a glance.

**A vendor's own posts are not perception of it.** A company's LinkedIn posts now sit outside every perception dimension. Sentiment about a brand should come from other people.

## Release notes (copy-ready)
- Perception scores now include articles linked to a brand by the classifier, not only those under the brand's own monitoring topic.
- A brand's own social posts no longer count toward its perception scores.
- The perception radar and comparison charts default to the primary brand plus the top five by volume; choose 3, 5, 8, 10 or all.
- Share of Voice groups the remaining brands into "Others".
- Brand Watcher remembers which tab you had open.

## Demo / walkthrough
Brand Watcher → Perception. The row of brand chips starts with "Show top 5 by volume"; change the number, or click a chip to add or remove a brand; "reset" returns to the default. Hover any score for the item counts behind it. Brand Watcher → Comparison has the same selector above Share of Voice.

## Positioning notes
Brand Watcher now works on top of a Market Monitor site without separate per-vendor monitoring being set up first. That is the setup a competitive-intelligence buyer has, and the one a single-brand tool cannot serve.

## Limits and what's next
- Scores are only as deep as the coverage. On the SOC-automation site, 31 scored items across all vendors in 90 days means most cells still read "no data", and a +100 from one item is one item. The grey number next to each score is the count; read it.
- Social perception on a market site stays empty until vendor-level social collection exists. Today 26 public posts across 80 vendors mention one by name, and none is scored yet.
- Employee scores need Glassdoor enabled on the brand.
- Setting a primary brand pins it in every default view; no brand is primary on the SOC-automation site yet.
