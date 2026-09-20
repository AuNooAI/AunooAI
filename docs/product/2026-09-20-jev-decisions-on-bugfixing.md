# Jev starts deciding, in four small places
_2026-09-20 · Auspex chat, observer alerts, relevance gate — bugfixing only_

**Audience note.** Internal. These are operator-facing behaviour changes on one internal site, each behind a flag, none on a customer site. Not for external distribution.

## What shipped
- Auspex on brand and market topics no longer hands the model articles that do not answer the question.
- Auspex answers greetings and simple questions briefly instead of in a report format.
- Observer alerts whose article does not match the instruction are held for review instead of emailed.
- Borderline articles that Jev is sure are on topic skip the paid language-model check.

## Why it matters
Before, a funding question on the SOC market gave the model forty articles, most of them vendor blogs; now it gets the few that answer. Before, an observer's email carried partner awards and trend pieces beside real signals; now those wait in a review list. Analysts on bugfixing feel the first two; the operator feels the third and fourth in the alert inbox and the bill.

## Release notes (internal only)
- Retrieval filter, router depth, referee hold and relevance accept-only tier live on bugfixing behind `TYPESAFE_DECIDE_*` flags.
- Held alerts: `GET /api/signal-alerts?review_status=held`.

## Demo / walkthrough
Auspex chat on the SOC Automation market: "hi there" answers in a line. Signals: held alerts appear in the alert list with the held filter after the next scheduled run.

## Positioning notes
None. Internal plumbing on one site.

## Limits and what's next
Each decision is measured against its shadow rows for two weeks before anything else moves. The relevance tier only accepts, never rejects. Auspex's individual queries were failing on every turn from an earlier change and are fixed today on all three monolith sites; the chat's own vector search on the SOC market topic still returns nothing with its filters, so the retrieval filter has had little to filter live.
