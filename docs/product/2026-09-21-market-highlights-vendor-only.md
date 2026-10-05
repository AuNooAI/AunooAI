# Two market report highlights that could only ever say one thing are gone
_2026-09-21 · Market Monitor — aisocnews.com report highlights, all Market Monitor customers_

## What shipped
The market report no longer prints a headline claim about the market unless it has read
something other than the vendors themselves.

Two of the five highlights on aisocnews.com were removed by that rule:

- "Vendors announce products far more often than customers."
- "For most developments the only source is the vendor."

A third highlight took the freed slot, naming the companies that actually announced customers.

## Why it matters
Oliver looked at the highlights and said two of them seemed worthless and always showed up. He
was right, and the reason is worse than the wording.

Both sentences were arithmetic over a list of events we build almost entirely from what vendors
publish about themselves — their LinkedIn posts, their own websites, their job adverts. Of the
940 events we have ever recorded, 938 rest on the vendor's own word. Told to report how many
developments have only the vendor behind them, the report could return one answer and no other.
It was describing our own reading and presenting it as a finding about the market.

The product comparison had the same defect. Vendors post launches more often than they post
customer wins, so counting only vendor posts guarantees that result whatever the market is
doing. The margin was also thinner than the words suggested: 72 product announcements against
34 customer ones in 30 days, where the rule fires above 68.

A reader cannot tell the difference between a finding and a tautology by looking at it. That is
what makes this worth fixing rather than rewording. Someone paying for this report was being
told something about the AI-in-the-SOC market that was really a fact about our collection, and
it appeared in every edition because it could not come out any other way.

The report's own front page already promises it reports what it observed. A claim that cannot
vary breaks that promise quietly.

## What we are not claiming
Collection is fine. We take in 4,000 to 6,000 articles a week, and this market's corpus held
1,478 articles in the last 30 days. Nothing upstream is broken. The gap is narrower than that:
trade-press articles sit in the corpus but never reach the event list the highlights are
computed from.

## Release notes (copy-ready)
- The market report now withholds a market-wide claim when it rests only on what vendors say
  about themselves.
- Two highlights were removed under that rule: the product-versus-customer comparison, and the
  line about developments resting on the vendor's own word.
- Highlights now name the companies announcing customer wins instead.
- No change to the developments list, the vendor table, or any other section.

## Demo / walkthrough
Open aisocnews.com. The highlights are the bulleted list at the top of the report. The page is
generated per request and cached for 90 seconds.

## Positioning notes
This is the "findings, not a feed" promise holding under pressure. The report's case against a
news feed is that it tells you what the data supports and stays quiet otherwise. A finding that
prints every period regardless of the data is the exact failure that argument is supposed to
rule out, so removing two of them strengthens the claim rather than weakening it.

It also gives a straight answer to the obvious buyer question, "how do you know this isn't just
vendor press releases?" Today the honest answer is that a lot of it is, and the report now says
less rather than dressing that up.

## Limits and what's next
**This is a suppression, not a repair.** The two findings are silent, not fixed. They come back
automatically once we read enough outside sources — the rule is a threshold, not a delete.

**The underlying gap is real and unclosed.** Of 243 trade-press articles in this market's
corpus, 236 have never been assessed and exactly one was ever marked as carrying a signal. Two
things block it: the step that reads and judges articles only looks at vendor LinkedIn posts,
and the step that turns judged articles into events only accepts vendor-owned channels. Both
need changing before earned coverage reaches a finding. Building the missing piece is a few
days of work for an AI.

**Outside sourcing is thinner than the numbers suggest.** When the report assembles evidence it
finds some outside sources — 12 of 101 developments in the last 30 days. But 19 of the 31
independent items behind those are social posts rather than journalism, because a tweet counts
as an independent voice. That classification was left alone here; it deserves its own look.

**Sales should not describe the report as independently corroborated.** It mostly is not, and
the product no longer claims otherwise.
