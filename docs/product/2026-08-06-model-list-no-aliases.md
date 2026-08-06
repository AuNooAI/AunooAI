# Model selectors now list only the models that actually run
_2026-08-06 · every AI model dropdown (News Feed, Trend Convergence, Narratives, onboarding, settings) — all customer sites_

## What shipped
Model dropdowns across the platform previously listed legacy names — gpt-4o, gpt-5,
gemini-pro and a dozen others — kept for backward compatibility and silently rerouted to the
models we actually operate. Those names are gone from every list. On AWS-hosted sites the
selectable models are now exactly the ones that run: Claude Haiku 4.5, Claude Sonnet 4.5,
Amazon Nova Lite and Pro, and Kimi K2.5. Saved selections using the old names continue to
work unchanged.

## Why it matters
The model a user picks is stamped into the audit trail: analysis provenance, report footers,
and the AI-disclosure text the EU AI Act requires. Until now that trail could read "gpt-4o"
for output a Claude model generated — technically routed correctly, but wrong as a
disclosure. Now the name on screen, the name in the records, and the model doing the work are
the same thing. For anyone answering a customer's "which AI wrote this?", the UI answer is
now the true answer.

## Release notes (copy-ready)
- Model selectors now show only the models actually available on your deployment; legacy
  third-party model names have been removed from the lists.
- Existing saved model choices keep working; defaults were updated to current models.

## Demo / walkthrough
Any model dropdown — Explore → News Feed header, Trend Convergence settings, Narratives
config, onboarding. The list is short and every entry names a real deployed model.

## Positioning notes
Directly supports AI-transparency conversations (EU AI Act Article 50): model disclosure in
the product now cannot disagree with the model that ran.

## Limits and what's next
- The legacy names still exist internally as routing entries so nothing breaks; they are
  hidden, not deleted. A browser or saved configuration that explicitly selected one keeps it
  (and keeps being routed) until the user re-picks; migration only auto-upgrades defaults the
  user never chose.
- Historical records written before today may still name legacy models; this change fixes the
  trail going forward, it does not rewrite history.
