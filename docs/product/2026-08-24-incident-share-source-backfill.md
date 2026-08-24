# Incident share emails: the "Unknown" outlet bug, actually finished

_2026-08-24 · News Feed: incident sharing by email (Highlights and Saved Incidents), wiley, wileytest, wbm_

## What shipped
- The fix for incident emails showing "Unknown" as the news outlet — shipped 2026-08-11, but
  only on bugfixing — is now live on wiley and wileytest too. It was never deployed there; a
  user submission today hit the exact bug the 08-11 fix was supposed to have already closed.
- A second, deeper fix: incident emails now look up the real outlet directly from the article
  database when an incident was saved with no outlet name recorded at all, not just when it
  was recorded under a different field name than the one being read.

## Why it matters
An incident email is an analyst vouching for a finding to someone who wasn't in the tool. The
outlet name is part of what lets the recipient judge the claim. Wiley and wileytest customers
were still seeing "Unknown" for two weeks after this was supposedly fixed, because the fix
never reached the servers that actually send their emails — it only reached the internal
development environment. Today's report of the bug is what caught that.

The second fix closes a case the first one couldn't reach: an incident built from a single,
manually-added article where the outlet name was never captured at save time, for reasons not
yet fully understood (see Limits, below). No amount of reading the saved incident's own data
differently fixes a value that was never written. The email now asks the article database
directly, which already has the real outlet name from when the article was analyzed.

## Release notes (copy-ready)
- Fixed: incident-share emails on wiley and wileytest still showed "Unknown" for the outlet
  name — the 2026-08-11 fix had not actually been deployed to those two sites.
- Fixed: an incident with no outlet name saved anywhere in its own data now has one filled in
  automatically from the article database when the email is sent.

## Demo / walkthrough
News Feed → Highlights or Saved Incidents → Share on an incident that has a source article →
send to yourself. The "Source Articles" section names the outlet under each title.

## Positioning notes
Same trust story as the original 08-11 fix — a finding is only as credible as the source
behind it, and the email is often the only part of the product a stakeholder outside the tool
ever sees.

## Limits and what's next
- We don't yet know why the manually-added article's outlet name wasn't captured when the
  incident was created, even though the article itself was already fully analyzed in the
  database at that point. The new lookup makes it recoverable at share time regardless, but
  the save-time gap is still open — worth a look if it recurs on a non-manually-added article.
- The 2026-08-11 fix's own verification said it had been confirmed "end-to-end on wileytest."
  On inspection, that check tested the backend's handling of a hand-built payload, not the
  actual deployed wileytest frontend — which is how a fix that looked fully verified sat
  undeployed on two live sites for two weeks. Future fixes spanning frontend and backend
  should confirm the fix is in the live bundle a browser will actually load, not only that the
  backend behaves correctly when fed the right input by hand.
