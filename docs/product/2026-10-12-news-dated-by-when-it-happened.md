# Market moves are dated by when they happened
_2026-10-12 · Market Monitor market page: Market moves and the vendor timelines_

## What shipped
- A deal, launch or funding round we find in the news now carries the date it happened, not the
  date the article ran.
- When an article gives no date for the news, we use the publication date, as before.

## Why it matters
**Before, old news looked new.** Trade press often recalls a past event in a fresh article. On
8 October an article mentioned that Cisco had closed its purchase of Astrix Security on 29 June.
We dated the deal 8 October, so a three-month-old acquisition appeared among the month's market
moves on the AI security page.

**Now the date is the event's own.** After our AI step reads a news article and decides it reports
real news, a second short step reads when that news happened. The Cisco deal is now dated 29 June
and appears in the 90-day view, not in the last 30 days.

**Most articles are same-day news, and they keep their date.** On the AI security site, 4 of the
40 news items we checked gave a separate date. Only the Cisco deal was far from its article's
date; the other three were within a day.

Who feels it:
- **Readers of the market page** see each month's moves as the moves of that month.
- **Analysts** can trust a vendor's timeline order, because an event recalled later no longer jumps
  to the date it was mentioned.

## Release notes (copy-ready)
- Market moves found in the news are now dated by when they happened, not when they were reported.
  An older deal mentioned in a recent article no longer shows up as recent news.
- Articles that give no date keep their publication date.

## Demo / walkthrough
1. Open the AI security market page and go to Market moves.
2. On the 30-day view, the Cisco–Astrix acquisition is absent.
3. Switch to the 90-day view: it is there, dated 29 June 2026.

## Positioning notes
A news feed that sorts by publication date repeats old deals as new ones whenever the press
recalls them. Dating by the event keeps the page a record of what happened when, which is the
claim a market page makes.

## Limits and what's next
- **News only.** A vendor's own LinkedIn post is still dated by the day it was posted. Vendors
  rarely announce old news, and the page already handles "looking back" posts.
- **It depends on the article stating the date.** When the article doesn't say, we can't know,
  and the publication date stands.
- **Live on the AI security site.** aisocnews.com gets it at its next restart. The other market
  sites need the change copied.
- **Headlines.** Items found in news still use the article's own title as their headline. The
  Cisco item had a listicle title ("5 Astrix and Aembit Alternatives…") until we fixed it by
  hand.
