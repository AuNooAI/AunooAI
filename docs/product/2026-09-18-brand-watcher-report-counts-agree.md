# Brand report: the summary now counts the same articles as the overview
_2026-09-18 · Brand Watcher: the AI-written narrative, category spike alerts, the risk assessment, and the exported HTML report_

## What shipped
- The executive summary, the spike alerts and the risk assessment now count only earned press. A company's own LinkedIn posts and its own website articles no longer count as coverage anywhere in the brand report.
- The exported report no longer shows a row of zero stat cards when there was no press in the period. It says so in one line instead.

## Why it matters
Before today, the top of the Oviva 7-day report said 0 on-brand articles and the executive summary underneath said 17, with a "12.3x spike" in Media & Advertising. Both numbers came from the same database. The overview had already learned to ignore Oviva's own posts. The summary had not, so it described Oviva publishing on its own LinkedIn page as a surge in media attention.

Now every part of the report answers the same question: how much did other people write about this brand? For Oviva in that week the honest answer is none, and the report says so. The social side and the Glassdoor ratings are unaffected and still appear.

Who feels it: anyone reading or forwarding the exported report. A brand manager can no longer be told their own press releases are a coverage spike.

## Release notes (copy-ready)
- The brand narrative and spike alerts now count earned media only. A brand's own posts and articles are excluded, matching the overview counts.
- The risk assessment's attention readout uses the same rule. Where a brand has less than eight weeks of earned coverage history, it now says so instead of reporting a multiple.
- Exported brand reports hide the Overview stat cards when a period has no press coverage.

## Demo / walkthrough
Explore → Brand Watcher → pick Oviva → set the period to Last 7 days → Generate narrative. The summary opens with the article count for the window. Then Export report: with no coverage, the page opens on the Analysis section and the lead line reads "0 on-brand articles analyzed".

## Positioning notes
The distinction between earned and owned media is a basic promise of a media-monitoring product. This closes the last place in Brand Watcher where the two were still mixed.

## Limits and what's next
- The attention readout needs eight weeks of earned history before it will report a spike multiple. Oviva does not have that yet, so its risk block says "needs 56 days of prior coverage history" for now.
- The report still treats zero earned press as a plain fact. It does not yet suggest whether that is unusual for the brand.
- Wiley's two sites got the backend fix but not the exported-report change, which only shipped to Oviva.
