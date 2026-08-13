# Generated reports now state facts and counts, not verdicts
_2026-08-13 · Timeline summaries, observer agent reports and alert emails, adverse-media digest_

## What shipped
- Every AI-written summary now attributes criticism to its source — "articles alleged", "posts
  on social media said" — instead of declaring the company itself to be in a "severe crisis".
- Coverage changes are reported as numbers: "64 to 114 articles per week against a baseline of
  1.3–1.9 per day", not "escalating dramatically".
- The trend label on timeline summaries now means coverage volume direction and displays as
  "coverage rising" or "coverage falling" instead of "escalating".
- Alert emails and reports say "Priority" where they said "Threat".
- The daily digest orders brands by how much their coverage changed and states the change; it no
  longer nominates a brand as "requiring immediate attention".
- All existing timeline summaries on the three customer sites were regenerated under the new
  rules, so the change is visible now, not after next week's refresh cycle.

## Why it matters
A Wiley stakeholder made the case directly: for a company that has been publishing for two
centuries, a week of critical articles is business as usual, and calling it a "severe
reputational crisis" is a judgment the customer wants to make themselves. Before this change,
a comms team could not forward our summaries upward without rewriting them — the language would
have read as alarmist to their leadership. Now the same summary gives them what they actually
need: what was published, who said it, how much of it there was, and how that compares to
baseline. The judgment stays with the reader.

The before/after on the customer's own brand: "Wiley is experiencing a severe reputational
crisis marked by escalating legal and editorial controversies" became "Wiley experienced
sustained elevated media coverage … 114 articles focused on accusations that the company
altered author work". Same facts, no verdict.

## Release notes (copy-ready)
- Report language: AI-generated summaries, reports, and digests now attribute claims to their
  sources and quantify coverage changes with counts rather than characterizing them.
- Timeline trend labels now describe coverage volume ("coverage rising") rather than severity
  ("escalating").
- Alert emails now label match importance as "Priority" instead of "Threat".

## Demo / walkthrough
Explore → Timeline tab → pick a brand or topic → the "State of …" panel. The paragraph is
attributed and quantified, and the chip next to the title reads "coverage rising" rather than
"escalating". The next observer agent email and daily digest will show the same register.

## Positioning notes
This closes the "why is every incident a catastrophe?" objection that comes up with large,
media-hardened customers. Severity judgments are now the customer's to make; we supply the
evidence. It also differentiates against monitoring tools whose summaries are tuned for drama.

## Limits and what's next
- The model can still occasionally reach for a strong adjective; the rules constrain it but do
  not guarantee zero slips, especially on the small model that writes these summaries.
- Severity thresholds are not yet customer-configurable. Pascal's "until instructed otherwise"
  suggests a per-customer setting for what earns strong language; today the clinical register
  is the only mode.
- Second pass (same day) extended the rules to executive briefings and topic reports, and
  rolled everything out to the two additional Brand Watcher sites. Incident reports still do
  not carry the rules.
- On the two Brand Watcher sites the timeline trend chip still shows the old wording
  ("escalating") — their interface bundle was not rebuilt; the summaries themselves are
  already clinical.
- Internal severity labels (used for sorting and alert routing) are unchanged; only the
  language shown to readers changed.
