# Aunoo brand monitoring in Claude: the full Brand Watcher, not just article search
_2026-09-28 · Brand Watcher over MCP on the Aunoo brand monitoring site (abm.aunoo.ai); an internal fix to run bookkeeping on all sites_

Audience note: the first part is a customer-facing capability, though today its only user is
our own team's Aunoo brand site. The second part (detection-run bookkeeping) has no product
surface and is recorded here for completeness only.

## What shipped
- The Aunoo brand monitoring site now answers the same questions in Claude as the Oviva site
  does: which brands are tracked, headline numbers per brand, classified articles, perception
  across media, social, community, employee and investor surfaces, who is talking and what each
  audience thinks, and recent alerts.
- Social posts about a brand can be pulled on their own, with platform, sentiment and
  engagement.
- Two ready-made playbooks, a brand briefing and a voices report, are available from the
  prompts list.
- Article results now honour the same relevance floor the site's own screens use, so a
  name-collision article the dashboard hides no longer reaches an assistant.

## Why it matters
Before, an assistant connected to the Aunoo brand site could only search articles by keyword or
topic. Any question the Brand Watcher screens answer, such as "how is Aunoo's coverage split by
category" or "what do journalists say about us versus what our own accounts post", had no tool
behind it, so the assistant either guessed or said it could not. Alvaro, who runs the use cases
on that site, asked for the gap to be closed on 25 September.

Now the numbers an assistant quotes are the numbers on screen, because the tools call the same
functions the pages do. The person who feels the difference is whoever runs a demo or an
analysis session against the Aunoo brand site in Claude: the same conversation that works on
Oviva now works there.

## Release notes (copy-ready)
- Brand Watcher tools are available over MCP on the Aunoo brand monitoring site: list brands,
  brand stats, brand articles, brand perception, brand voices and brand alerts.
- Social posts about a brand can be fetched directly, filtered by platform and sentiment.
- Two playbooks, brand briefing and voices report, are listed under prompts.
- Article results from the MCP now apply the site's relevance floor.

## Demo / walkthrough
In Claude, with the Aunoo connector active: ask "which brands does this site track", then
"give me a brand briefing for Aunoo over the last 30 days". The briefing playbook walks the
tools in order and writes up volume, sentiment, alerts, audiences and the competitor comparison.
For the audience view, ask "who is talking about Aunoo and what does each audience think".

Market tools appear in the catalogue but answer that Market Monitor is not enabled on this
site, which is correct: the Aunoo brand site has no market configured.

## Positioning notes
This is parity work, not a new capability. It closes the objection that the assistant
experience differs from one Aunoo site to the next.

## Limits and what's next
- The market tools are present but inert on this site, because it has no Market Monitor.
- Voices on the Aunoo brand site is thin: over 90 days the on-brand social posts resolve to 13
  brand-account posts and 1 journalist, so the "clinicians versus patients" style comparison
  has little to compare yet. That is the data, not the tool.
- Verification ran in-process rather than over a live MCP call with a token, because minting a
  key was refused by the permission system. Alvaro's client needs one `list_capabilities` call
  to pick up the new catalogue.
- The two adaptations that make this work on the Aunoo brand site exist only in that site's
  files. A future refresh of that site from canonical must carry them again.

## Internal only: detection runs that found nothing stayed open
On the Aunoo brand site, every daily emerging-topics run that found zero topics was left marked
as still running, 44 of them since July. Nothing was actually stuck, but our restart guard read
each as a job in flight, and the topic-retirement logic did not count them as runs. Both early
exits now close the run, and the 44 rows are closed. The other seven sites already had the
proper fix since 19 August; four runs there that a restart had cut short were closed by hand
as failed. No customer sees any of this.
