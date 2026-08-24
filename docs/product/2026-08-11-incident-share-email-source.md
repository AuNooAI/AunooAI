# Incident alert emails now name their news sources
_2026-08-11 · News Feed: incident sharing by email (Highlights and Saved Incidents)_

## What shipped
- Incident emails shared from the news feed now show the news outlet (for example
  "bostonglobe.com") under each source article. Before, incidents that an analyst had
  promoted from a single article showed "Unknown" in that spot, even though the outlet
  was known.
- Emails shared from the Saved Incidents card now include the source-article list for
  promoted incidents. Before, those emails silently omitted the articles section.
- The fix applies to incidents saved in the past, not just new ones — re-sharing an old
  incident produces a corrected email.

## Why it matters
An incident email is an analyst vouching for a finding to someone who wasn't in the tool.
The source line is what lets the recipient judge the claim: "bostonglobe.com" and
"Unknown" read very differently under a headline about government policy. Analysts who
promoted an article into an incident — the most deliberate, hands-on path in the product —
were the ones whose emails looked least trustworthy. That's now fixed, and the recipient
sees the same source attribution the analyst saw in the app.

## Release notes (copy-ready)
- Fixed: incident emails showed "Unknown" as the news source for incidents created from a
  single article. The correct outlet now appears.
- Fixed: incidents shared from the Saved Incidents card were missing their source-article
  list. The articles and their outlets are now included.
- Re-sharing a previously saved incident sends a corrected email; emails already sent are
  not retroactively changed.

## Demo / walkthrough
News Feed → open an article → Promote to Incident → save it. Then, on the incident card
(Highlights or Saved Incidents), choose Share and send it to yourself. The email's
"Source Articles" section lists each article with its outlet named beneath the title.

## Positioning notes
Small trust fix rather than a feature. It supports the standing claim that every finding
in the product traces to a named source — the email is often the only part of the product
a stakeholder ever sees, so it has to carry that attribution too.

## Limits and what's next
- Emails sent before 2026-08-11 still say "Unknown"; only re-shares are corrected.
- The two internal code paths that record an article's outlet still store it under
  different field names; the email and app now read both, but a future reader of that data
  must do the same until the writers are unified.
- **Correction, 2026-08-24:** this fix was on bugfixing only for the two weeks after it
  shipped. wiley and wileytest were still running the pre-fix code the whole time — a
  wileytest user hit the original "Unknown" bug on 2026-08-24, which is how this was caught.
  The original verification tested the backend's handling of a hand-built payload, not the
  actual deployed frontend bundle, so the gap went unnoticed. Now deployed and confirmed
  present in the live bundle on all three tenants; see `docs/changes.md`, 2026-08-24.
