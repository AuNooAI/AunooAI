# Market Monitor: pull a vendor's data on demand, plus three new sources
_2026-08-23 · Market Monitor — bugfixing.aunoo.ai only_

## What shipped
Every vendor page in Market Monitor now has a **Fetch now** button. It queues a fresh pull for
that one vendor — LinkedIn posts, profile, funding, jobs — right away, instead of waiting for
the next scheduled collection cycle.

Two vendor data sources that had no way to attach a profile now do: paste a PitchBook or
ZoomInfo URL directly on the vendor page. A third source, Indeed job listings, is wired in
behind the scenes and pools with LinkedIn's job postings.

## Why it matters
Previously, adding a vendor meant waiting for its next scheduled poll — hours, sometimes longer
— before any data showed up. If you'd just added a company and wanted to see what Market
Monitor could find on it, there was nothing to do but wait. Fetch now closes that gap: click it,
and that vendor's data starts arriving within minutes.

PitchBook and ZoomInfo can't be found automatically the way Crunchbase can — their profile URLs
end in an opaque number a company name can't predict. Until now there was no way to give Market
Monitor one at all for those two sources.

## Release notes (copy-ready)
- New "Fetch now" button on every vendor page — queues an immediate data pull for that vendor.
- PitchBook and ZoomInfo URLs can now be added directly on a vendor's page.
- Indeed job listings are now collected alongside LinkedIn's, on request.

## Demo / walkthrough
Market Monitor → a market → Vendors → open any vendor → "Fetch now" near the top of the page.
Missing a PitchBook or ZoomInfo URL for that vendor? Scroll to the identifiers section and
"Add PitchBook URL" / "Add ZoomInfo URL" appears there.

## Positioning notes
None specific — this is an operator/analyst workflow improvement inside Market Monitor, not
something shown to an external reader (the investor-facing report is covered separately, in the
same day's other changelog entry).

## Limits and what's next
PitchBook, ZoomInfo and Indeed are **manual-only** right now — none run on the market's regular
schedule, only from Fetch now or an added identifier. That's deliberate, not a gap to close
casually: Indeed's employer-matching field is inferred from a sample request, not yet confirmed
against a real response, and the PitchBook/ZoomInfo field mappings were built from a schema or a
partial sample. Moving any of the three onto the scheduled cadence should wait until a real
response has been read and the mapped fields checked against it.
