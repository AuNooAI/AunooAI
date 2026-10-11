# A dedicated intelligence site for Pearson's language-testing question
_2026-08-11 · pearson.aunoo.ai (customer-pitch site) + dashboard proposals_

**Audience note.** This documents pitch preparation for Pearson, not a customer release.
The site is not yet shared with Pearson, two open items block a demo (below), and nothing
here should be sent externally as-is.

## What shipped

- A dedicated monitoring site for the Pearson opportunity, revived from the mothballed
  June installation, with its Wiley-era content switched off.
- Six news topics built around one thesis: English-test sales fall when immigration rules
  tighten, and demand shifts to wherever rules open up. The topics track visa policy in
  the US/UK/Australia/Canada, Germany's opening to skilled workers, German cities and
  sectors short of staff, the language-testing market itself, the countries people
  migrate from, and international student flows.
- Competitor tracking for the language-testing market: Duolingo, IDP Education (IELTS),
  and ETS (TOEFL) are now monitored alongside Pearson, whose profile finally includes its
  own test products (PTE Academic, PTE Express).
- A three-part dashboard proposal for the team to discuss, published as a shareable page:
  a per-country immigration policy tracker, a city-level labour demand view built from
  official German job-market data, and a corridor view that joins policy, demand, and news
  per origin→destination pair.

## Why it matters

Pearson's own view (Kátia Oliveira) is that the market blames Duolingo for a decline that
immigration policy actually caused, and that Pearson only tracks demand to country level.
Before today we had no vehicle to test or demonstrate that thesis. Now a site is
collecting evidence on both sides of it — 566 immigration-policy articles arrived in the
first collection pass alone — and the proposal document turns her three asks (non-English
destinations, city-level targeting, mid-career professionals) into three concrete
buildable dashboards with effort estimates and open questions. The differentiated piece is
city-level: news pinned to named cities plus official vacancy statistics, which is the
level Pearson says nobody in their industry reaches today.

## Release notes (internal only)

- pearson.aunoo.ai is live again with a migration-corridor topic set (10 active topics, 88
  search terms) and language-testing competitor tracking.
- Wiley-era topics, brands, alert agents, and user accounts on that site are switched off,
  not deleted.
- Dashboard proposals: docs/PEARSON_MOBILITY_DASHBOARDS_SPEC.md, also published at
  https://claude.ai/code/artifact/a53d6971-8804-4c5b-8ea5-053bfc2aa986

## Demo / walkthrough

Not yet demo-able — see blockers. When unblocked: the Explore tab shows the six topics
collecting; Brand Watcher shows Pearson primary with Duolingo/IDP/ETS as peers.

## Positioning notes

This is the same play that won the Wiley work — "US pullback → compensatory investment
abroad" — applied to people instead of research money. If the corridor dashboards get
built, the pitch to Dan Doyle (head of PTE) is: policy signals arrive the day they are
announced, visa statistics confirm them quarters later, and test purchases follow; we sit
at the early end of that chain, at city level, which Pearson currently cannot see.

## Limits and what's next

- **The site cannot analyze articles yet.** Its AI key is the stale pre-rotation one, so
  collected articles are saved but unclassified and invisible in the UI until the operator
  runs the staged key fix. This is the first blocker for any demo.
- **The site is currently stopped on purpose.** It was shut down this evening to shed load
  from the shared embedding encoder while that separate problem is worked; it needs a
  restart once the encoder work allows.
- Only one of the six topics has completed a collection pass; the rest fill in on the
  scheduler once the site is back up.
- The three dashboards are proposals, not features. None are built. City-level labour
  demand needs new data feeds (German federal employment agency, Adzuna) that the platform
  does not ingest today.
- German-language collection has not been validated end to end — we do not yet know if the
  AI analysis step holds up on German text.
