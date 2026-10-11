# Social tab: a quiet week no longer looks like a setup problem
_2 October 2026 · Brand Watcher, Social tab · live on Oviva, abm and Sunstar_

## What shipped
- When a brand already has social monitoring and no posts arrived in the chosen period, the
  Social tab now says so, and shows when collection last ran.
- The "Add social monitoring" box now appears only for brands that are not monitored yet.

## Why it matters
Before this change, the Social tab showed the same box in two different situations:
- a brand that had never been set up for social monitoring;
- a monitored brand that simply had no posts in the chosen period.

On 2 October an Oviva user saw the setup box on the 7-day view, although Oviva has been
monitored for weeks. It looked as if monitoring had been switched off. In fact the week was
quiet: the last post naming Oviva was from 1 October.

Now a monitored brand with a quiet week shows a plain note, for example: "No posts about Oviva in
the last 7 days match the current filters. Social monitoring is on; the last collection ran …".
The person reading the dashboard can tell a quiet period from a broken setup without asking us.

## Release notes (copy-ready)
- Social tab: when a monitored brand has no posts in the selected period, the tab now says
  "Social monitoring is on" and shows the time of the last collection, instead of offering to
  set monitoring up again.

## Demo / walkthrough
1. Open Brand Watcher, then the Social tab.
2. Pick a monitored brand and a short period with no posts, such as 7 days.
3. A grey note under the tab header names the brand, the period and the last collection time.
4. Pick a brand with no social monitoring: the original "Add social monitoring" box appears.

## Positioning notes
None. This is a correction to an empty state, not a capability to sell.

## Limits and what's next
- **The note can't say why a period is empty.** That might be a quiet week, or a provider
  outage: on 29–30 September the social data provider refused searches because the quota was
  used up, and on 1 October an X search took too long and was cut off. The note shows the last
  collection time, but not whether that run succeeded on every platform.
- **Public social volume for Oviva is low.** A larger collection run on 2 October looked back 30
  days and fetched up to 100 posts per platform. It found 48 X posts naming "Oviva", most of
  them from an unrelated Japanese account, and no Bluesky posts after 20 September. A week with
  three posts is normal for this brand. It is not a sign of a fault.
- **Other sites:** Wiley, wileytest and the other brand-watch sites still show the old box.
