# Three new vendors on the AI SOC list, and on-demand website collection
_2026-09-09 · aisocnews.com vendor registry; Market Monitor operator UI_

## What shipped
- BlinkOps, NextSOC and Securaa are now tracked vendors in the AI in the SOC market.
- An operator can now fetch one vendor's website on demand. Before, that button did nothing.
- Five reader-submitted news tips from 31 August are in the corpus.

## Why it matters
**Vendors who ask to be listed get listed.** Blink asked through a contact. NextSOC and
Securaa asked through the form on the site, and Securaa's two submissions from 7 September had
gone unanswered. All three are in, with their LinkedIn, website and (where it exists) Crunchbase
profiles wired up, so the collectors treat them like every other vendor. Whoever handles the
next request has a written four-step recipe instead of guesswork.

**A new vendor no longer waits a week for a rating.** The map rates a vendor once it has a
headcount, and headcount comes from the LinkedIn profile collector, which runs weekly. We forced
the runs today. BlinkOps shows 126 staff and Securaa 58 in the collected profiles. NextSOC has
no LinkedIn page anywhere we could find, so it stays unrated until its founder sends one, which
we have asked for.

**The per-vendor website fetch works.** The operator page has a "Fetch now" for a vendor's
website, but the scheduler only ever ran website collection for the whole market, so the
per-vendor request was accepted and then failed with an internal wiring error. It now runs for
that one vendor. Analysts adding a vendor between weekly sweeps can read its site the same hour.

**Reader tips reach the corpus.** The tip form stored submissions and nobody read them. The
five from 31 August (Simbian's benchmark, two Artemis case studies, a CrowdStrike release naming
Artemis, and Artemis's careers page) are now articles under the market topic and attributed to
their vendors. Two of them score below the relevance bar for public display, so they inform the
analysis without appearing on the site.

## Release notes (copy-ready)
- Added BlinkOps, NextSOC and Securaa to the AI in the SOC vendor registry.
- Fixed: "Fetch now" for a single vendor's website did nothing. It now collects that vendor's pages.
- Reader news tips submitted since 31 August have been reviewed and added.

## Demo / walkthrough
Market Monitor → AI in the SOC → Vendors → BlinkOps. The vendor page shows the LinkedIn
profile, 24 posts and 10 job listings collected today. The "Fetch now" control next to
"Site changes" queues a website read for that vendor alone; the run appears in the market's
run list within ten minutes.

## Positioning notes
None. This is registry upkeep and one operator-facing fix, not a story to tell buyers. The
useful line for a vendor conversation is that a listing request is turned around the same day
and the vendor's own channels are collected within hours.

## Limits and what's next
- Tips still have no accept or reject control. Each was pushed through by hand. A small
  operator action on the tip list would close that gap.
- NextSOC has no LinkedIn page on file, so its headcount, posts and hiring signals stay empty
  until one is found. The founder has been asked.
- The Crunchbase profile for BlinkOps was still being fetched at time of writing.
- The vendor request table records no status. We closed requests by adding the vendor, and
  found the missed one by comparing the table against the brand list. A status column would
  make the queue visible.
