# Every analyst citation now names a report you can go and find
_2026-09-22 · Market Monitor — the "Research firms" panel on the front page_

## What shipped
The panel listing analyst-firm coverage no longer prints rows that say only "Gartner research".
Every item now names an actual report — Emerging Tech Impact Radar, Innovation Insight, Magic
Quadrant for SSE and SASE, IDC MarketScape.

Two kinds of bad row are gone. A vendor that posted twice about one analyst mention used to
produce two entries, one properly titled and one blank; those are now merged. And a vendor simply
saying an analyst firm's name, with no report behind it, is no longer listed at all.

## Why it matters
The panel's job is to tell a reader which analyst reports have named which vendors, with a link
to each source. A row reading "Gartner research" does none of that. It asserts a report exists
and gives the reader no way to check, which is worse than leaving it out — and it sat directly
beside a correctly-titled entry describing the very same report.

Six of the sixteen rows were not citations of research at all. One was a vendor noting that "SAP
kept Splunk". One was an investor thread about revenue growth. One was a phishing story that had
drifted in by mistake. Those rows made the panel look fuller and made it worth less.

The panel now shows eight items, and all eight name a report.

**What we were careful not to break.** Some real recognitions never name the report — "Acme was
named a Leader by Forrester this week" is a genuine, checkable claim with no report series in it.
Those are kept. The rule drops a row only when it has no report, no title *and* no stated
position.

## Release notes (copy-ready)
- The Research firms panel now names an actual report for every item.
- Duplicate entries, where a vendor posted about one report twice, are merged into a single row.
- Vendor posts that mention an analyst firm without citing a report are no longer listed.
- Recognitions that state a position — "a Leader", "a Sample Vendor" — are still shown even when
  the post does not name the report.

## Demo / walkthrough
On the market report front page, the "Research firms" panel. Compare the item count before and
after: it drops from eighteen to ten, and nothing left in it is unattributable.

## Positioning notes
Small surface, same argument as the rest of this product: we would rather show less and have all
of it stand up. A panel padded with unverifiable rows is the thing a competitor's demo does.

## Limits and what's next
**The panel is smaller now, and that is the intended result.** If a customer asks why there is
less in it, the answer is that six of the rows were not analyst research.

**One recognised report type is missing on the other customer sites.** Oviva and Sunstar have
this fix but not the separate change that taught the parser to recognise Gartner's "AI Vendor
Race" format, so a citation of that report would still be unnamed there.

**The merge rule is conservative.** It requires two distinctive words in common and the same
analyst firm. Two posts about one report that share no specific wording will still appear
separately, which is the safer failure.
