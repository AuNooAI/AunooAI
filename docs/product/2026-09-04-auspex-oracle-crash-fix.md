# The research assistant's intelligence brief no longer fails without a topic
_2026-09-04 · Auspex research assistant, all customer sites_

## What shipped
- Fixed: the assistant's "Strategic Intelligence Oracle" — the button that
  builds an intelligence brief from the last day's coverage — failed with an
  error whenever it was clicked without a topic selected. It now runs, and
  builds the brief from recent coverage across all topics instead.
- We caught this by watching the Sunstar site live after its launch work: a
  real user clicked the button minutes after a restart and got "Intelligence
  brief generation failed". The fix reached every active customer site the
  same afternoon.

## Why it matters
The tool sits on the assistant's toolbar on every customer site, one click
away. Clicking it without first picking a topic is the natural first move for
a new user — exactly what happened on Sunstar. Before the fix that click
produced an error message; now it produces a brief. The people who feel it
are new users exploring the assistant, which is precisely the audience a
first impression is made on.

## Release notes (copy-ready)
- Fixed: the research assistant's intelligence brief tool returned an error
  when no topic was selected. It now generates a brief from recent coverage
  across all topics.

## Demo / walkthrough
Open the Auspex assistant, leave the topic unset, and click Strategic
Intelligence Oracle. It runs. Before the fix this returned "Intelligence
brief generation failed".

## Positioning notes
None. This is a defect fix; its value is that the failure a new user was most
likely to hit no longer exists.

## Limits and what's next
Without a topic the brief draws on everything collected in the time window,
so on a site with several topics it is broader than a topic-scoped brief —
that is the intended behaviour, not a limitation of the fix. Sites that are
dormant today (not running for any customer) get the fix when they are next
brought up.
