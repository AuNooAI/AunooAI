# Social posts for every monitored vendor, a cleaner coverage table, and a shared report that asks for a trial
_2026-08-27 · Brand Watcher Social tab; Market Monitor report (shared view and "How this was measured")_

## What shipped
- The shared market report (a link or a public market, no login) now shows the assessment, the headline figures and the first sections in full, blurs the detailed evidence, most of the vendor registry and the coverage tables, and asks the reader to request a trial.
- A trial-request form on that page takes a name, company email and title, and says what a trial includes: every vendor and figure, an RSS feed, an MCP server, CSV export and a weekly report by email.
- The Social tab now shows the public posts that mention a vendor, scored for relevance and sentiment, for every vendor with social monitoring switched on.
- The market report's "How much of the market we checked" table lists only the sources we actually read. Sources we do not run for this market are named in one sentence under the table.
- The table no longer says a source was "attempted 0" times while showing dozens of vendors collected from it.
- The row that read "Job boards read 20 / 84" now says what it counts: vendors with at least one open job listing we have seen.

## Why it matters
**Shared report as a sales surface.** Before, anyone with the link got the whole evidence pack for the ten most active vendors and had no reason to talk to us. Now they can read the assessment and see the shape of the evidence, but the figures under it are blurred and the numbers are removed from the page itself, so there is nothing to lift. The request form is on the same page, with the offer spelled out. Every request is stored, and emailed to the address in `MARKET_TRIAL_NOTIFY_EMAIL` once that is set.

**Social tab.** Before, a market customer site with ten vendors under social monitoring saw an empty tab, with "no social posts yet" and a prompt to add monitoring they had already added. The posts had been collected and scored, but the tab was reading a newer table that nothing was filling in or scoring. Now the posts appear, one entry per post and vendor, so a post naming two vendors is judged for each. An analyst can see what practitioners say about Dropzone AI, Radiant Security or 7ai without leaving the product. Volume is still modest: seventeen relevant posts across six vendors in the last thirty days, which is what the market says, not a gap.

**Coverage table.** A reader outside the team sees this table to judge how much of the market the figures cover. Three rows of zeros for Indeed, PitchBook and ZoomInfo read as three broken collectors. They are sources we chose not to run for this market, and that is now said once, in words, under the table. "Attempted 0" next to "Collected 69" read as a counting error, because it was one: a success was not being counted as an attempt. And "Job boards read 20 / 84" contradicted the row above it that said 82 boards were read; it now says what the 20 means.

Who feels it: analysts using the Social tab on market sites; anyone reading a shared market report's methods section.

## Release notes (copy-ready)
- Shared market reports show the assessment in full and blur the detailed evidence; readers can request a trial from the page.
- Social tab: posts that mention a monitored vendor now appear, scored per vendor.
- Market report: the coverage table lists only sources we read; unused sources are noted in a sentence.
- Market report: attempt counts now include successful checks; the hiring coverage row is labelled by what it counts.

## Demo / walkthrough
- Open the market report's plain URL (the one you would paste to someone) — logged in or not, it is the shared view. The app's own Report button opens the full one. Read the lead, then open "The evidence behind this": the first sections are readable, the rest blurred with a "Request a trial" card. The form sits just above the drawers.
- Brand Watcher → Social. Scope "selected brands" shows the brands chosen in the header; "+ competitors" shows every vendor. Leave "Min relevance" on ≥0.4 for on-brand posts.
- Market Monitor → open a market → Report (HTML) → expand "How this was measured" → "How much of the market we checked".

## Positioning notes
None that change the story. This closes a gap between what we collected and what we showed, on the customer site where the market layer runs.

## Limits and what's next
- The lead of the shared view (assessment, who moved, developments and their records) is still shown in full; only the evidence drawers, most of the registry and the coverage tables are blurred.
- The blur is a teaser, not a paywall: numbers are removed from the blurred text, but bar heights in the blurred charts and the prose still exist in the page source.
- Trial requests are stored in `market_trial_requests`. Nobody is emailed until `MARKET_TRIAL_NOTIFY_EMAIL` is set on the customer site.
- The form checks that the email looks like one; it does not reject personal mail domains.
- Which sections stay readable is fixed in code (scope, period comparison, snapshot, formation, headline cards, three registry rows). Changing the mix is a one-line edit each.
- Posts are linked and scored on an hourly sweep, so a post collected just now can take up to an hour to appear.
- Existing rows in the coverage table that show "attempted 0" correct themselves as each vendor is collected again; the one-line database backfill that would fix them at once has not been run yet.
- Only the market customer site has this. Classic brand sites read social posts the old way and were not affected.
- Social volume per vendor is small because only the vendors with their own social group are searched by name; the market-wide social group finds a vendor only when a post happens to name one.
