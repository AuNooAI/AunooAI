# AI SOC news: the public page shows real launches, and no internal labels
_2026-09-16 · aisocnews.com public market page — the Product launches section, the Analyst View coverage table, and vendor voices_

## What shipped
Two credibility fixes to the public market page. Vendor opinion posts no longer
show up as product launches, and an internal source code we use behind the
scenes no longer leaks onto the page.

## Why it matters

**Opinion posts were being shown as product launches.** The page has a "Product
launches" section. It was picking up posts that are not launches at all —
a vendor's think-piece on compliance, a threat-news comment about a software
bug, a podcast interview, a company anniversary, a published playbook. A reader
scanning the launches saw marketing and opinion mixed in with real product
news, which undercuts the section. Two things were done. The posts already
mislabelled were cleared out, so the section is clean now. And the step that
reads each vendor post and decides what it is was tightened, so it reserves
"launch" for a post that actually says a specific product or capability is now
available. On a re-check of the posts that had been mislabelled, 12 of 13 now
read as opinion, commentary or research instead of launch, while real launches
("Announcing Nightwatch", "now available on Google Cloud Marketplace") stay as
launches.

**An internal source name was showing on the page.** We pull some social posts
through a paid data feed we refer to internally as "xpoz". That internal name
was printing on the public Analyst View — in the coverage table and in the
weekly briefing's sources — instead of the platform name a reader expects.
Anywhere a source is now shown to a reader, an internal code like "xpoz:twitter"
is mapped to its public name ("X"). A check of the public page, the news view,
the social section and the current briefing draft found zero occurrences of the
internal name afterwards.

## Release notes (copy-ready)
- The "Product launches" section now shows real product and capability launches.
  Opinion posts, threat-news comments, interviews, podcasts and anniversaries no
  longer appear there.
- Post sources are shown by their public platform name everywhere on the page.

## Demo / walkthrough
Open https://aisocnews.com/?days=30&view=v2&section=launches — the list is
launches and capability releases. On the Analyst View
(https://aisocnews.com/?view=report), the coverage table and the weekly
briefing name each source as "X", "Bluesky", "LinkedIn" and so on.

## Positioning notes
The public page is the shop window for the market data. A launches list padded
with marketing, or an internal codename on the page, both read as "this is not
really curated." These are credibility fixes: the page should look like an
analyst put it together, because one did.

## Limits and what's next
The launches cleanup was conservative. Borderline posts that name a shipped
feature were left as launches rather than risk hiding a real one, so a few
marketing-heavy posts may still appear. The reviewer tightening only changes how
new posts are read from now on; it does not re-judge the whole back catalogue.
One interview post that describes a product's capability still reads as a launch,
because it genuinely sits on the line. If the launches section drifts again, the
next lever is re-reviewing the existing corpus with the tightened rule, not more
hand-editing.
