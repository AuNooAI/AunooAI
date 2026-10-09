# Fewer site freezes, fewer lost labels, and audience counts you can put in a report
_9 October 2026 · all customer sites; the Voices page and the market's Top voices list_

## What shipped
- The test site stopped freezing for minutes at a time. Freezes dropped from about 26 an hour to about 3.
- The AI analysis step no longer loses category labels whose names contain commas, such as "AI Copyright, Regulation, and Antitrust".
- It no longer leaves time to impact empty when the model shortens "Immediate (0-6 months)" to "Immediate".
- Top voices shows patients, clinicians and customers instead of the catch-all "practitioner".
- The Voices page no longer counts a competitor's own marketing as a voice about your brand.
- Every account in the top 40 voices on Oviva and abm now has a profile, and every profile on every site has a market role.

## Why it matters
**Site freezes.** While a freeze lasts, nobody can load a page, and background collection stops too. On 8 October the test site froze 129 times in 6 hours, once for over 4 minutes. Three pieces of slow work were running where they blocked everything else:
- a scan for posts from a brand's own website, which ran four times a day;
- downloading and reading news feeds and article pages;
- the market's scan of the article archive.

Each now runs in the background. Over 6 hours on 9 October the site froze about 3 times an hour, mostly for under 12 seconds. A recording that evening caught one more freeze of 69 seconds, from the market's archive scan, which we then moved to the background too. The cause of a 36-second freeze at 13:40 is not yet known.

**Lost labels.** When a topic's category name contains commas, the AI read it as several names and answered with a fragment, which the site rejected and filed under "Other". On the AI topic that happened about 110 times every 6 hours. Time to impact went empty about 97 times a day for a similar reason. Analysts filtering by category or time to impact were missing those articles.

**Audience counts.** An analyst preparing an Oviva report found three problems:
- The site labelled most patients "practitioner".
- It listed Zanadio, Noom and HelloBetter's own Instagram posts as competitor voices about Oviva, though none mentioned Oviva.
- Several top accounts had no profile.

Each would have put wrong numbers in a client-facing report. All three are fixed, and the fixes apply on every customer site that has these pages.

## Release notes (copy-ready)
- Sites respond faster and no longer freeze for minutes while background work runs.
- Articles keep their category when the category name contains commas.
- Articles keep their time to impact when the AI shortens the label.
- Top voices names each account's audience: patient, clinician, customer, journalist, investor and so on.
- The Competitors group on the Voices page shows only rivals' posts that mention your brand. A site can switch back to showing all rival posts.
- A journal account run by the market's publisher is shown as that publisher's own voice.

## Demo / walkthrough
- **Top voices:** Market Monitor → the market → Voices. The role column now reads "patient", "clinician", "investor" and so on, where it used to read "practitioner".
- **Competitors:** Brand Watcher → a brand → Voices. The Competitors group is empty on Oviva because no rival post names Oviva. On Sunstar and abm the group still lists rivals' posts, because those sites use the "show all rival posts" setting.

## Positioning notes
Audience breakdowns are what a client quotes from a report. A label that mixes patients and doctors, or a count that includes a rival's adverts, would fail the first time a client checked a single account. These fixes make the counts hold up to that check.

## Limits and what's next
- Articles already filed as "Other" or with no time to impact keep those values. Fixing them means running the AI analysis again, which costs money; we have not done it.
- One freeze of 36 seconds (13:40 on 9 October) has no identified cause, and short freezes of a few seconds remain.
- Profiles show what the AI read from an account's bio and posts. A borderline account can still be placed wrongly. Respiratory Case Reports, published by Wiley for a medical society, reads as the society's, not Wiley's.
- On a site with a "show all rival posts" setting, the Competitors group still includes rivals' own marketing, by design.
