# Papers are no longer counted as product news
_2026-09-28 · Brand Watcher (Wiley sites): categories, alerts; Highlights cards_

## What shipped
- Journal papers, book chapters and datasets a publisher puts out now sit in their own
  "Publications" bucket in Brand Watcher, instead of being counted as product news.
- The "category coverage spike" alert is switched off on the Wiley sites.
- Highlights cards no longer show a made-up day when a story only gives a month.

## Why it matters

### Papers were product news
**Before.** Brand Watcher sorts every article about a brand into one of eleven news categories.
For a publisher, that included its own output. Every paper and chapter Wiley published landed in
"Product & Innovation", with the highest possible relevance. Last week that bucket held 46 items
for Wiley. 45 were papers: 33 chapters of one companion volume, a handful of index records, and
eight journal pages picked up through Google News. One was a press release.

The alert built on that bucket then told the reader that product coverage had doubled. Nothing
had happened at Wiley. The same alert had fired seven times since August for the same reason.

**Now.** Anything the brand published as scholarship goes to "Publications". The eleven news
categories hold coverage of the brand. Wiley's week now reads 45 Publications, 25 Financial
Performance and 9 Competitive Landscape, with nothing in Product & Innovation, which is what the
coverage actually was. Older items were moved as well, so the charts for past weeks are right
too.

**Who feels it.** Communications and brand teams reading the category charts, and anyone who
received the alert emails.

### The category spike alert is retired
**Before.** The alert compared how many articles landed in a category this week with the weekly
average over the last month, and fired when the count doubled. That number depends on what our
collectors fetched and where our classifier put it. It does not say what the articles are about,
and it cannot tell good news from bad.

**Now.** The alert is off on the Wiley sites. The alerts that describe a real event stay on: a
new adverse finding such as a retraction or a lawsuit, news sentiment turning net negative, a
burst of negative social posts, or a new critic gaining reach.

**Who feels it.** Anyone on the alert list. Fewer emails, and every one left describes something
that happened.

### Highlights dates
**Before.** When an article said an event happened "in June", the card showed 01.06.2026, a day
nobody stated. Two stories reported on 27 September about OpenAI's agents carried that date.

**Now.** A card shows a full date only when the articles give one. Otherwise it shows when the
story was reported. The three affected cards now read "reported 2026-09-27".

**Who feels it.** Readers of the Highlights view on wileytest, and anyone who sorts it by date.

## Release notes (copy-ready)
- Brand Watcher: papers, book chapters and datasets a brand publishes now appear under
  "Publications" rather than in the news categories.
- Brand Watcher: the "category coverage spike" alert is switched off on the Wiley sites. Alerts
  for adverse findings, sentiment turns and social activity are unchanged.
- Highlights: a card shows a full date only when its sources state one; otherwise it shows the
  date the story was reported.

## Demo / walkthrough
- Brand Watcher, Wiley, Categories: the bar for Publications appears in grey with its own name,
  and Product & Innovation holds only press and news items.
- Brand Watcher, Alerts: the last two "Product & Innovation coverage spike" entries (26 and 27
  September) are the final ones; nothing of that type will follow.
- Highlights on wileytest: the cards "OpenAI AI agents accessed US government websites" and
  "Autonomous OpenAI agent breached Australian federal health data portal" show
  "reported 2026-09-27".

## Positioning notes
A publisher's own output is not coverage of the publisher. Earned media tools that count a
company's own papers as news overstate product activity for every research-heavy customer, not
only publishers: pharma, device makers and universities all publish. Keeping owned scholarship in
its own bucket is the same principle as keeping a brand's own social posts out of its social
sentiment (24 September).

## Limits and what's next
- The Publications bucket is a category, not a report. There is no view yet that summarises what
  the brand published this week; the count is visible, the contents are not analysed.
- Detection is by source and by the platform name Google News appends to a title. A paper relayed
  through a news aggregator that strips that tail will still reach the news classifier.
- The category spike alert is off on the Wiley sites only. Other sites still have it, and it will
  keep producing the same kind of alert there until it is switched off or replaced.
- Highlights keeps the month the model extracted on the item, but nothing displays it yet. A card
  could say "June, reported 27 Sep" once the design allows a second date.
