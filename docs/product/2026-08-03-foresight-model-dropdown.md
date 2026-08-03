# Every model picker shows the five real models
_2026-08-03 · Anticipate, Explore, Gather, Submit Articles, Auspex chat and the six tuning dialogs · Wiley and Wiley Test_

## What shipped
Every place in the product where you choose an AI model now lists the five models the platform
actually runs, under their real names. They had been listing 23 entries, most of them different
names for the same model.

## Why it matters
Before, opening any model picker gave you 23 options with names like "gpt-4.1-mini (bedrock)"
and "claude-3-5-sonnet-latest (bedrock)". Those names were misleading in two ways. They
suggested we run OpenAI and Google models, which we do not — everything goes through AWS
Bedrock. And most of them were the same model twice: seven of the entries all ran Claude Haiku
4.5, five more all ran Claude Sonnet 4.5.

The practical cost was a choice that could not be made well. Someone picking between two
options that were secretly identical got the same analysis and no way to know why. Someone
avoiding "Claude" by choosing a "gpt" entry got Claude anyway.

Now every list is Claude Sonnet 4.5, Claude Haiku 4.5, Nova Pro, Nova Lite and Kimi K2.5. Each
entry is a different model, and the name matches what runs.

One quieter fix came with it. The emerging-topics settings dialog used to replace a saved model
it did not recognise with the first one in the list, so opening the dialog could change a
setting you had chosen. Saved settings are now left alone, and a model that is no longer
offered still shows in the dropdown rather than appearing blank.

## Release notes (copy-ready)
- Model pickers across the product now show only the five distinct AI models available, named
  correctly. They previously listed 23 internal aliases, many of which pointed at the same model
  under a different vendor's name.
- Emerging-topics settings no longer replaces a saved model choice when you open the dialog.

## Demo / walkthrough
Open **Anticipate** and the model dropdown at the top of the analysis controls — five entries.
The same list now appears in the Explore header, the Add Agent dialog, emerging-topics settings,
the Gather group and auto-collect settings, Submit Articles, the Auspex chat bar, and the six
tuning dialogs (Executive Summary, Future Horizons, Editorial Board, Signals, Newsletter,
Focus Groups). If you still see the long list, hard-refresh (Ctrl+F5) — the old version is
cached in the browser.

## Positioning notes
Small fix, but it removes a credibility problem in screens we demo. A prospect who reads
"gpt-4o" in our dropdown and then hears "we run on AWS Bedrock" has spotted a contradiction we
then have to explain. Now the screens match the story.

## Limits and what's next
This changes what the pickers offer, not what any pipeline uses by default. Jobs and agents
already configured with an older alias keep running on it, and that alias still shows in its
dropdown so nothing silently changes underneath them. Repointing those defaults is a separate
decision with a cost implication, and it should go through a before/after comparison first.

The list of five is defined in one place in the backend. If a new model is added to the
platform, that list must be updated by hand — the pickers will not pick it up on their own.
