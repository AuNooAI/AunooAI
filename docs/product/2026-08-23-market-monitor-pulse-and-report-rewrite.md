# Market Monitor gets a landing view, and the investor report reads like an analyst wrote it
_2026-08-23 · Market Monitor — bugfixing.aunoo.ai only_

## What shipped
Market Monitor now has a **Pulse** tab — one screen that answers "what is the state of this
market right now" without clicking through eight tabs to reconstruct it.

The **Coverage** tab can rank what it's showing you: most popular posts, coverage grouped by
what kind of thing it is (launches, partnerships, funding, acquisitions), and a new **career
moves** list of named hires read straight out of vendors' own "welcome to the team" posts.

Generated reports now cite their sources inline, can be downloaded, and no longer invent
placeholder citations like "[headcount data]".

The biggest piece: the **investor-facing HTML report** — the one that gets shared outside the
building — has been rewritten from a database status dashboard into something that reads like
an analyst wrote it. It leads with findings, not a wall of numbers, and it is honest everywhere
about what wasn't observed versus what was checked and came back empty.

## Why it matters
**Before**, the investor report opened with "83 vendors, 1,313 articles, 30 open jobs" and left
the reader to work out what any of that meant. Sentences like "Based on 81 of 83 vendors have a
founding year" read as machine output, because they were. "Vendors with no signal — 61" implied
61 companies did nothing, when it actually meant 61 companies weren't being watched closely
enough to know either way. Four separate news items about the same Cribl/Radiant acquisition
showed up as four separate "developments."

**Now** the report opens with "What changed" — three to six findings, each with the numbers
behind it: *"Hiring is concentrated: 7ai accounts for 20 of the 30 observed openings, with
Crogl accounting for another 6."* Every material development is deduplicated and shows whether
it's independently corroborated or resting on the vendor's own word. Every count that could
mean "checked, found none" versus "never checked" says which one it is. The report also now
compares this period against the one before it, and states the market's actual tracked scope
instead of leaving a reader to infer it from who's in the vendor list.

**On the dashboard side**, an investor or product person can open Pulse and get the state of the
market in one look — funding, sentiment, headcount trend, who's moving, what's still open —
instead of assembling that picture from separate Overview and Brief tabs that no longer exist
as separate things.

## Release notes (copy-ready)
- New Pulse tab: one landing view combining market state and this week's changes.
- Generated reports now cite their sources inline (click a `[A3]` marker to open the source
  article) and can be downloaded.
- Coverage tab: a "Most popular" ranking, sortable by newest or most-reactions, and groupable by
  what kind of announcement it is.
- New "Career moves" list — named hires and appointments, separate from open job listings.
- The investor HTML report leads with analytical findings, deduplicates coverage of the same
  event into one entry with a source count, states the market's tracked scope explicitly, and
  compares this period against the previous one.
- Fixed: several charts that looked broken (a single dot, a mostly-blank sentiment line) were
  actually correct — the market is young and doesn't have more history yet. They now say so
  instead of looking like a bug.

## Demo / walkthrough
Market Monitor → pick a market → **Pulse** is the default landing tab. Scroll for the sentiment
and headcount trend charts, the funding-moves list, and events.

**Coverage** tab → the "Most popular" panel and the "By network" rankings sit near the top,
above the filterable list; "Group by: Kind" is one of the grouping buttons above the list.

The investor report is the "Report (HTML)" link/download from the Pulse header, or the signed
share link from "Share link". Open it with no session (private/incognito window) to see exactly
what an external investor would see.

## Positioning notes
This is the artifact that goes outside the company. A report that reads as a database dump
undermines confidence in the underlying data even when the data is fine; a report that states
its own limitations plainly is more credible, not less, to anyone who's read a real analyst
report before. The corroboration labels ("vendor source only" vs. "independently corroborated")
are a small thing that signals real rigor — most competing "AI market monitor" tools don't
distinguish a vendor's own press release from independent reporting at all.

## Limits and what's next
**Market scope** has a field for it now (settable from the market's Settings → Scope drawer),
but no market has one filled in yet — every report currently shows "scope has not been defined
for this market." Worth setting for any market before its report goes to an external reader.

**Most-discussed / most-shared vendor rankings, per network, are usually empty.** This is a
real finding, not a bug: of this market's 180 non-vendor social posts, only 2 carry a formal
vendor tag today. Brand attribution barely reaches practitioner Twitter/Reddit/Bluesky posts —
it mostly runs on news articles and vendors' own posts. The "top post" ranking (which doesn't
need that tagging) works fine; the other two will fill in as attribution coverage improves, not
from anything in this release.

**Corroboration status is a real check, not a full fact-check.** It only knows a claim is
independently corroborated when this system has *also collected* a non-vendor article about the
same event — it can't tell you a claim is false, only whether outside reporting exists for it.

**Previous-period comparison** covers announcement counts, job postings and coverage volume —
not headcount or Crunchbase scores, which already have their own trend charts elsewhere and
weren't worth risking a second, possibly disagreeing, computation of the same thing.
