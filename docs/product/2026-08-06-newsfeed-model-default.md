# News Feed model picker now shows the model that actually runs
_2026-08-06 · Explore page News Feed header — all customer sites_

## What shipped
The News Feed's AI model selector defaulted to "gpt-4o", a name kept only for backward
compatibility — on Bedrock-based sites that selection actually ran a Claude model. The
default is now `bedrock-kimi-k2-5`, the same model the platform uses for article analysis,
so the name on screen matches the model doing the work. Browsers that had the old default
saved are upgraded automatically; a model someone deliberately chose is left alone.

## Why it matters
Before: an operator or customer looking at the header saw an OpenAI model name on a site
that runs entirely on AWS Bedrock. That undermined trust in the model controls and produced
support questions ("why does gpt-4o still show up?"). Now the default is a name that exists,
runs, and matches the backend's configured default.

## Release notes (copy-ready)
- The News Feed's default AI model now displays the model actually used for generation.
  Saved model choices you made yourself are unaffected.

## Demo / walkthrough
Explore → News Feed: the model dropdown in the header. On a fresh browser (or one that never
changed the model) it reads `bedrock-kimi-k2-5`.

## Positioning notes
Minor, but relevant for EU AI Act transparency conversations: the UI no longer names a model
other than the one generating the content.

## Limits and what's next
- Other pages still carry `gpt-4o-mini` as a last-resort fallback in their API wrappers; those
  only apply when no model is selected and were left unchanged.
- The dropdown still lists the legacy alias names (they keep old saved configs working). A
  later pass could label them with the model they resolve to.
