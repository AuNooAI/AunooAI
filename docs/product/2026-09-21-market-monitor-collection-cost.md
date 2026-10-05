# Market Monitor collection costs a fifth of what it did
_2026-09-21 · Market Monitor — vendor LinkedIn collection_

**Audience note: internal.** Nothing here changes what a customer sees. It changes what we pay
to produce it. Worth writing down because it decides how many vendors a market can track, which
is a product limit customers do feel.

## What shipped
Market Monitor now asks its data provider for five recent posts per vendor per run instead of
twenty-five.

## Why it matters
We pay per record. The provider cannot filter by date, so we pay for whatever it hands back and
throw away what we already have.

The AI-in-the-SOC market was asking for the last 25 posts from each of 96 vendors, twice a day.
That is about 2,020 records a run, $3.03, $6.06 a day. Across September it paid for 60,858
records and kept 1,297 — one in forty-seven.

Those vendors do not post anything like that much. Over two weeks the whole list of 85 active
companies produced 480 posts: about one a day each, two for the busier ones, five on the single
busiest day any one company managed. Five per vendor per run covers that.

Measured on the first run under the new setting: 430 records for $0.645, against 2,020 for $3.03
that morning. That is $1.29 a day instead of $6.06 — roughly $39 a month rather than $186, for
more posts, not fewer. The same run collected 25 new posts where the previous one collected 3,
because it covered a working day rather than a weekend.

What this unblocks: the budget cap is per market and it applies to every paid source. When
LinkedIn posts ate the cap, company profiles, job postings and funding data stopped too. Those
three cost $1.56 a month between them, so we were losing the cheap signals to pay for a
redundant one.

## Release notes
Internal only — no customer-facing change.

## Demo / walkthrough
None. No UI surface.

## Positioning notes
None directly. Indirectly: how many vendors a market can cover is a cost question, and this
changes the answer. A market tracking 96 vendors now fits inside a $100 monthly budget with
room for the other sources, where before it did not fit at all.

## Limits and what's next
The bound is per run, and a post the provider does not hand over is not offered again. Slowing
collection below once a day would need the number raised to match, or posts get missed. The
setting is `MARKET_POSTS_PER_VENDOR` if that happens.

September could not be recovered by the saving alone — the month was already 93% spent — so the
cap for that market went from $100 to $150. Month to date is now 62% of the new cap and the nine
days left cost about $12.
