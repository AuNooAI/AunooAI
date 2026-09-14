# Forecast Tracker delivery controls no longer name Wiley
_2026-09-08 · Forecast Tracker tab, Scheduled deliverables panel, Topic Reports tab_

## What shipped
- The per-topic scheduling control is now labelled "Delivery cadence for this topic".
- The deliverables panel is titled "Scheduled deliverables".
- Recipient fields show a neutral example address.
- Downloaded and emailed bundles are named forecast_bundle or foresight_bundle, followed by the cadence.

## Why it matters
The delivery feature was built for one customer and carried that customer's name in the interface. Every customer site inherited it, so an analyst on a demo site saw another company named in their own tool. That is a trust problem in a demo and a confidentiality problem with a paying customer. The wording is now generic, so an operator can show the Forecast Tracker to anyone without explaining it away.

## Release notes (copy-ready)
- Forecast Tracker: delivery scheduling controls use neutral wording.
- Forecast bundle downloads and email attachments are named forecast_bundle_{cadence} and foresight_bundle_{cadence}.

## Demo / walkthrough
Open a topic, go to the Forecast Tracker tab, and scroll below the surprises panel. The "Delivery cadence for this topic" row and the "Scheduled deliverables" panel sit at the bottom. Download a bundle from the panel to see the new filename.

## Positioning notes
None. This removes a defect rather than adding capability.

## Limits and what's next
Only the sunstar demo site and the canonical tree have the change. The other customer sites keep the old wording until their interface is rebuilt. Internal file and function names still say Wiley, which does not affect anyone using the product.
