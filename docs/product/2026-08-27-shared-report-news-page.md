# The shared market link now opens as a news page
_2026-08-27 · Market Monitor — the shareable report_

## What shipped

- The shared report opens on a scannable news page: four headline figures, the changes we observed, and a sidebar of movers and voices.
- Each story says what backs it — "the vendor announced it; no independent source" — rather than leaving a reader to assume.
- Each headline figure carries how much of the market it covers.
- Stories can be filtered by theme in the page itself, including from a saved copy with no internet connection.
- The detailed sections and the methodology notes are unchanged, below the new front page.

## Why it matters

**A shared report is read by someone who was not there when it was made.** They cannot ask what a number covers or where a claim came from, so the page has to say. The new front page leads with four figures, each carrying its own denominator — "80 of 84 measured" beside the headcount, "21 of 85 Crunchbase pages read" beside the funding figure — and then a list of what actually changed, each entry stating what backs it.

**Nothing is drawn that is not there.** The design calls for a small trend line under each figure. Staff headcount has two weekly readings so far, so it gets a sentence explaining that instead of a two-point line pretending to be a trend. Where a panel is empty, it says why: "No vendor has two readings yet, so no movement can be reported."

There is no generated summary paragraph. Everything else on the page traces back to a record, and a written-up market commentary would be the one thing that does not.

**We found a serious problem while building it.** The shared report has a final safety check: after the page is built, it is searched for the name of any company the recipient is not entitled to see, and refused rather than sent if one appears.

That check had been doing nothing. A variable holding the list of names to look for was accidentally reused further down the same function to hold a count, so by the time the check ran it had a number rather than a list — and a count of zero made it exit immediately, reporting success.

No company names were disclosed. Two other filters upstream were working correctly, which is exactly why nobody noticed: the pages they produced were clean, so the test that checked those pages passed while the guard behind them was dead. That is the real lesson — a test on the result does not test the safeguard protecting it. There is now a test that the safeguard actually runs, and it fails if the old mistake is reintroduced.

**Two smaller errors, both caught by reading the finished page.** The headline figures were labelled "last 30 days" while quoting all-time totals — 4 mentions against 2,088 posts, where the real 30-day figures are 2 and 531. And several stories printed the same sentence twice, as headline and again as summary, because these entries are extracted from posts whose opening line becomes the title.

## Release notes (copy-ready)

- The shared market report now opens on a news-style front page with four headline figures, the observed changes, and a movers and voices sidebar.
- Every figure shows how much of the market it covers; every change shows what evidence supports it.
- Stories can be filtered by theme within the page, including offline.
- Figures labelled with a period now use that period.
- Detailed sections and methodology notes are unchanged and still included.

## Demo / walkthrough

Market Monitor → any market → share the report. The link opens on the new front page. The links in the top bar jump to the detailed sections further down, which are unchanged.

## Positioning notes

The shared link is the artefact that leaves the building, and until now it looked like an internal report. It now reads like a market briefing while keeping every qualification that makes it trustworthy — the coverage denominators, the evidence state on each claim, and the methodology notes.

## Limits and what's next

**This market's figures are genuinely thin, and the page shows that.** Two earned mentions in thirty days, one company with a measurable staff change, nothing independently corroborated. The design holds up when the data is sparse because it says so, but it is not a showcase.

**No trend lines on most figures yet.** They need at least four weekly readings. Content volume has fourteen and gets one.

**The vendor-name prefix on story headlines is still there** — "Vendor: The infrastructure you trust..." — because it comes from the underlying post. It reads awkwardly next to the vendor name in the byline.
