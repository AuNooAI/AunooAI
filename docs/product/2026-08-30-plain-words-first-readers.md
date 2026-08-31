# The page in plain words, and its first hundred readers
_2026-08-30 · aisocnews.com and aisoc.aunoo.ai: the front page, its section pages and the Analyst View_

## What shipped

- **Plain words everywhere.** The page no longer says "readings", "shape", "observed",
  "material change" or "the tracked cohort". It says what was counted and when: "LinkedIn
  headcount changed +12% between the two dates we collected it", "42 of 85 vendors had a
  development", "For most developments the only source is the vendor", "Most of the market
  is new: 64 of the 84 vendors with a known founding year were founded in 2023 or later."
- **One event, one entry.** A vendor's own post and a news story about the same launch are one
  entry with both sources under it, even when the story's summary runs long. Intezer's
  Workflows launch was listed twice on 19 August; it is one row now, with four sources.
- **Two things that read wrong are fixed.** The map's stage headings printed a placeholder
  ("scale of {c3} and over") instead of the number; they read "scale of 75 and over". A
  Forrester blog post about a Forrester report was listed as if Forrester were a vendor citing
  it ("Cited by forrester.com"); firms' own posts now appear only under the firm.
- **Scanner probes stop costing page renders.** Requests for `/.env`, `/.git/config` and the
  like get a plain 404 on both names.

## Why it matters

The page had its first real audience today: a LinkedIn post at about nine in the morning
brought a hundred readers by early afternoon, half of them on phones, and a tenth of them
went on to the Analyst View. What they read was written in the vocabulary of the people who
built it. A "reading" is a row we collected; a reader does not know that, and should not
have to. "42 of 85 vendors showed material observed change" tells an analyst nothing that
"42 of 85 vendors had a development" does not, and the second one is English.

The same read found the page contradicting itself. Two entries for one Intezer launch make
the vendor look twice as active as it was and put a "Product expansion" and a "Product
launch" side by side for the same thing. A stage heading with `{c3}` in it says the page is
generated and nobody looked. Those are the things a first-time reader judges a source by.

The change is guarded. The test that renders the real report now rejects every phrase that
was removed today, so the wording cannot drift back with the next feature.

## Release notes (copy-ready)

- The page is written in plain words throughout: what was counted, from where, and when.
- A launch reported by the vendor and by the press is one entry with both sources.
- Fixed: the map's stage headings showed a placeholder instead of the score.
- Fixed: an analyst firm's own blog post was listed as a vendor citing a report.

## Demo / walkthrough

- https://aisocnews.com/ — Highlights: "42 of 85 vendors had a development", "For most
  developments the only source is the vendor".
- https://aisocnews.com/?days=30&view=v2&section=launches — one Intezer row for 19 August,
  "4 sources · Reported by multiple independent sources".
- Analyst View (link in the top bar) — "Vendors with a development", "Developments",
  the map's stage list with its scores written in.

## Positioning notes

The public page is the first thing a prospect sees, before any trial. It has to read like a
publication, not like a database. Today's pass is what makes the "market news page" claim
true at the level of the sentence; the earlier work made it true at the level of the layout.

## Limits and what's next

- The market question in the masthead ("How is AI-led SOC automation evolving, and which
  vendors show material change in…") is the market's own configured text and still uses
  the old words. It is one line to change per market.
- The provenance labels ("Vendor sources only", "Also reported independently", "Reported by
  multiple independent sources") were kept; they are plain, but a reader has to work out that
  "independently" means "by someone other than the vendor".
- The merge rule now joins two records that name the same product in both headlines. It
  cannot join a story whose headline paraphrases the product name without using it; those
  still show as two entries until the daily review pass judges them.
- The readership figures above are from the web server log, not analytics; there is no
  country breakdown, and link-preview fetchers from cloud ranges were removed by a rule of
  thumb, so "102 people" is an estimate to within about ten.
