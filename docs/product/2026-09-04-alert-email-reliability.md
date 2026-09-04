# Alert emails you can trust again
_2026-09-04 · Brand Watcher digests and signal alert emails, all customer sites_

## What shipped
- Alert digests no longer show internal error messages. When the AI summary of
  social posts fails, the email now ships the linked post list without a
  broken warning banner where the summary should be.
- The AI summary fails far less often. Every model the platform uses now has
  two backup models behind it, on different providers, so one provider's
  outage no longer takes the summaries down.
- The "download full report" link in alert emails works without logging in
  (rolling out — live on the canonical site, the customer sites follow once a
  one-line change is approved on each).
- The change-password and reset-password pages now match the product's look
  instead of rendering as unstyled forms.

## Why it matters
Before: a customer opening yesterday's brand digest saw "⚠️ gpt-5.4-mini is
currently unavailable. Please try a different model." above a raw list of
posts. That is an internal plumbing message in a customer's inbox, and it
happened because the summary model had no backup during a provider outage.
After: the summary appears when the model works, and the email degrades to a
clean post list when it does not. The reader never sees the machinery.

Separately, everyone who clicked "download report" in an alert email got an
error page, because the link demanded a login the email reader does not have.
The link carries its own signed, expiring pass; it now works as designed —
click from the inbox, get the report.

## Release notes (copy-ready)
- Fixed: alert digests could show an internal model-error message in place of
  the social post summary. Failures now fall back to the post list cleanly.
- Improved: AI summaries have automatic backup models, so a single provider
  outage no longer suppresses them.
- Fixed: "download full report" links in alert emails opened an error page
  unless you were already logged in. They now open the report directly; links
  remain private (signed, and they expire after 30 days).
- Improved: the change-password and reset-password pages use the product's
  design instead of an unstyled form.

## Demo / walkthrough
Open any Brand Watcher digest or signal alert email and click the report
link — it opens without a login prompt. The password pages are at
/change_password (when a password change is forced) and via any emailed
reset link.

## Positioning notes
None beyond trust: error text in a customer's inbox undoes the "always-on
analyst" story faster than any missed alert does. This closes that hole.

## Limits and what's next
The report-link fix reaches the customer sites only after a small approved
change on each; until then those links still require a login. Already-sent
emails start working the moment each site has the fix — the links stay valid
for 30 days, so nothing needs re-sending. The model backup chain covers the
outage case, not quality: which model should write these summaries in the
first place is being compared separately (the current default was chosen by
inertia, and our own benchmarks say a cheaper model writes better summaries).
