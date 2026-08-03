# Foresight model picker shows the five real models again
_2026-08-03 · Anticipate page (foresight analysis), Wiley and Wiley Test_

## What shipped
The model picker on the Anticipate page now lists the five AI models the platform actually
runs, under their real names. It had been listing 23 entries, most of them different names for
the same model.

## Why it matters
Before, an analyst opening the Anticipate page saw a dropdown of 23 options with names like
"gpt-4.1-mini (bedrock)" and "claude-3-5-sonnet-latest (bedrock)". Those names were misleading
in two ways. They suggested we run OpenAI and Google models, which we do not — everything goes
through AWS Bedrock. And most of them were the same model twice: seven of the entries all ran
Claude Haiku 4.5, five more all ran Claude Sonnet 4.5.

The practical cost was a choice that could not be made well. Someone picking between two
options that were secretly identical got the same analysis and no way to know why. Someone
avoiding "Claude" by choosing a "gpt" entry got Claude anyway.

Now the list is Claude Sonnet 4.5, Claude Haiku 4.5, Nova Pro, Nova Lite and Kimi K2.5. Every
entry is a different model, and the name matches what runs.

## Release notes (copy-ready)
- The AI model picker on the Anticipate page now shows only the five distinct models available,
  named correctly. It previously listed 23 internal aliases, many of which pointed at the same
  model under a different vendor's name.

## Demo / walkthrough
Open **Anticipate**, then the model dropdown at the top of the analysis controls. It should
list five models. If you still see the long list, hard-refresh the page (Ctrl+F5) — the old
version is cached in the browser.

## Positioning notes
Small fix, but it removes a credibility problem in a screen we demo. A prospect who reads
"gpt-4o" in our dropdown and then hears "we run on AWS Bedrock" has spotted a contradiction we
have to explain. Now the screen matches the story.

## Limits and what's next
This fixes one dropdown. Four others still show the full 23-entry alias list: creating a news
feed agent, emerging topics settings, and the two gather settings dialogs (group settings and
auto-collect). They read a different, older endpoint. Worth doing the same cleanup there, and
the work is roughly an hour for an AI including the rebuild and deploy to each customer site.

The fix is deployed to Wiley and Wiley Test. It reaches a browser on the next hard refresh; no
service downtime was involved.
