# Escalation status, defined by you
_2026-08-13 · Brand Watcher: digest email, timeline "State of" panel, reports_

## What shipped
- You can now define what counts as an escalation for each brand you monitor — your own
  labels ("elevated", "crisis", "code red") with your own thresholds: how many times above
  normal coverage volume, for how many days, how negative the sentiment, whether a
  high-severity risk finding is required.
- When a threshold you set is crossed, every summary states your label and the numbers
  that crossed it: "Wiley entered elevated status after news coverage doubled to 8
  articles per day over two days."
- When no threshold is crossed — or none are configured — nothing changes: summaries stay
  strictly factual, as introduced earlier today.

## Why it matters
Earlier today we stopped the platform from calling routine coverage a "crisis" on its own
judgment. This closes the loop on the obvious follow-up question: how is a real crisis
signified? The answer is that the judgment is yours, made in advance, as configuration.
The system checks your thresholds with plain arithmetic — the AI is only allowed to repeat
the result, word for word, with the evidence attached. Strong language becomes rare,
defined, and traceable, which is what makes it mean something when it appears.

## Release notes (copy-ready)
- New: per-brand escalation tiers. Define labels and thresholds (coverage multiple vs
  baseline, sustained days, net sentiment, high-severity findings); when crossed, digests,
  timeline summaries, and reports state your label with the triggering numbers.
- Default behavior is unchanged: with no tiers configured, all output remains strictly
  factual.

## Demo / walkthrough
Configure tiers on a brand (currently via brand configuration, no self-service editor
yet), then: the daily digest email shows a bold status line under the brand; Explore →
Timeline → the brand's "State of" panel opens with the designation and shows a red badge
next to the trend chip, with the trigger numbers on hover.

## Positioning notes
Turns the "why is everything a catastrophe?" objection into a differentiator: monitoring
tools generally either editorialize or stay mute. Here the customer owns the severity
vocabulary and the platform proves every use of it. Written to Pascal Hetzscholdt's
framing — "unless a customer has told you that x posts = crisis … be factual in a
clinical way until instructed otherwise."

## Limits and what's next
- Configuration is JSON on the brand record, set by us on request — no self-service
  editor yet. That is the natural phase 2 if customers want to tune thresholds themselves.
- Thresholds are numeric (volume, sentiment, risk findings). Event-class triggers ("no
  more funding for universities") are not automated; an analyst note on the brand's
  timeline covers those and flows into every summary.
- No alert fires yet when a brand enters or leaves a tier — summaries reflect it, but
  there is no "brand entered crisis" email. Also phase 2.
- Tiers are per-brand only (the adverse-media use case); topics have no tiers.
