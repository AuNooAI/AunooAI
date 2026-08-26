# A shared market report no longer names every company you monitor
_2026-08-26 · Market Monitor — shared reports and feeds_

## What shipped

- A shared market report now names the top 10 companies, not all 84.
- The same limit applies to the market's RSS feed.
- The report says on the page how many companies it covers and that the rest are excluded.
- A company you explicitly mark public is always included.
- Signed in, you still see the whole market. Nothing changes for your own screens.
- Full-market views are recorded in the log.

## Why it matters

**A shared report was disclosing your entire watchlist.** The market report can be opened three ways: a signed link you send someone, a normal session, or — if the market is flagged public — just the URL. All three produced the same file, and that file named **every one of the 84 companies** in the SOC Automation market.

Because the market was flagged public, no link and no login were needed at all. Anyone who knew the URL got the list.

Who feels it: whoever the report was sent to, and whoever they forward it to. The list of companies a customer watches is a competitive document in its own right — arguably more sensitive than any single figure in the report, because it shows what they think the market *is*.

The market's RSS feed had a smaller version of the same problem: 20 of the 84 names, reaching anyone subscribing anonymously, through article headlines rather than any list of companies.

**There was already a control for this, and nothing read it.** Each company in a market has a "public" flag, with a setting to change it. No part of the product ever consulted it — and zero of the 84 companies were marked public. So the one setting that was supposed to govern this was both switched off and ignored.

**A shared view now shows the top 10 and says so.** Ranked by observed activity, with any company you explicitly mark public always included. The report carries the line "It names 10 of 84 monitored vendors" so a recipient cannot mistake it for the whole market.

Signed in, you see everything, exactly as before.

**And the limit cannot be worked around by reloading.** The ten are chosen from the market itself, not from whatever period or sort the viewer happens to be using. Someone who changes the date range five times sees the same ten companies five times, so repeated requests cannot be used to piece the list together. We verified that: five different date ranges, the same ten names each time.

**The last line of defence refuses rather than patches.** A company's name can reach a page through an event headline or an article title, not only through a list. So after the report is built, it is checked for any name the viewer should not see — and if one is found, the report is not sent at all. Refusing is recoverable. Sending is not.

## Release notes (copy-ready)

- Shared market reports and public RSS feeds now name a limited set of companies (10 by default) instead of the full monitored list.
- Signed-in users are unaffected and continue to see the whole market.
- The limit applies to a signed share link and to a public market equally.
- Companies explicitly marked public are always included in a shared view.
- A shared report states how many companies it covers and that the remainder are excluded.
- The selection is fixed per market, so changing the period or sort cannot reveal additional companies.
- Full-market accesses are recorded.

## Demo / walkthrough

Market Monitor → SOC Automation → share the report. Open the link in a private window: the report names 10 companies and carries the line "This is a shared view. It names 10 of 84 monitored vendors."

Open the same market's report while signed in: all 84, as before.

## Positioning notes

This is a disclosure fix, and it is worth being straightforward about it: the shared report was showing more than it should have, we measured exactly how much, and the fix is enforced on the server rather than hidden in the page.

It also makes the share link usable for the first time in a sales context. Sending a prospect a market report previously meant sending them the full list of companies the account tracks.

## Limits and what's next

**There is no middle tier yet.** The limit is either "shared" (10) or "everything" (signed in). A named recipient who should see 25, or the whole market, cannot be granted that individually — there is no per-viewer setting, only signed-in or not.

**The default of 10 may be wrong for your market.** It is configurable per deployment but not per market.

**There is no restricted interactive view.** The limit covers the shared report and the feed. Every interactive screen requires a login, so those are correctly unrestricted — but if a restricted live view is ever added, each of its data endpoints needs the same gate.

**A company marked public is shown even if it would not make the top 10.** That is deliberate, and it means the visible set can exceed the ranking; it never exceeds the limit.
