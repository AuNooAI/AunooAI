# AI SOC news: the front page moves on its own, even on a quiet week
_2026-09-15 · aisocnews.com public market page — the lead story and the "Influence and Influencers" card_

## What shipped
The front page no longer looks frozen when the market is quiet. The top story now changes every
day, and the influencers card leads with the people who actually posted rather than a list of
accounts that were silent.

## Why it matters
Two parts of the page were showing the same problem: a slow news week made them look dead.

The lead story used to pick the single most important development from the last week and hold it
there. When nothing bigger came along, the same story sat at the top for days — one launch led
for a full week. Now the page rotates through the five strongest recent developments, one per
day. A reader who checks back sees a different story each morning, so the page reads as live even
when the market is slow. The card is now labelled "Featured development" instead of "Top
development", because on a quiet week the rotation may surface the second or third story, and the
label should not overclaim.

The influencers card listed everyone we track in order of audience size, then noted whether each
had posted. On a quiet week the card opened on ten rows of "quiet this period" — the people who
had actually said something were buried further down. Now the voices who posted this period come
first, and the rest of the tracked list follows. Nobody is hidden; the active voices just lead.

## Release notes (copy-ready)
- The front-page lead story now rotates daily through the top recent developments, so the page
  changes on its own instead of holding one story for a week.
- The lead card is labelled "Featured development".
- The "Influence and Influencers" card now leads with the voices who posted this period; the
  full tracked list still appears behind them.

## Demo / walkthrough
Open https://aisocnews.com/?days=30&view=v2. The lead card near the top of the page reads
"Featured development"; come back tomorrow and it will be a different story. On the right, the
"Influence and Influencers" card opens with whoever posted about the market this period.

## Positioning notes
The public page is the shop window for the market data. A page that shows the same story for a
week reads as abandoned, whatever the quality of the data behind it. Rotating the lead and
leading with active voices keeps the window looking tended without inventing news that isn't
there — on a genuinely quiet week the page is still honest, it just cycles what it has.

## Limits and what's next
Rotation only produces variety when there is more than one recent development to rotate through.
On a market with a single recent story the pool is one item and the lead does not change until
new developments land — the fix removes the "stuck on one story while others exist" case, not the
"nothing happened this week" case. Likewise the influencers card can only lead with active voices
when someone posted; a week where nobody we track posts about the market still shows a quiet card.
