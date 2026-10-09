# MCP access on aisocnews.com now includes vendor benchmarks
_2026-10-09 · aisocnews.com subscribe page; the MCP key subscribers buy_

## What shipped
- Subscribers' AI tools can now benchmark any AI SOC vendor against the rest of the market.
- The subscribe page now says what the key adds, in terms of what a buyer can find out.
- A card at the foot of the page points readers who want other markets or topics to Aunoo for
  Agents.

## Why it matters
**The page undersold the subscription.** It told readers that everything was already on the
free pages and that the key only changed how they reached it. That was not true. The site
publishes findings, while the vendor benchmarks, each vendor's sourced profile and history,
the funding and hiring detail, and the full article collection sit underneath. A buyer reading
the old page had no reason to pay.

**The benchmark was not available to subscribers at all.** It lived only in the operator's
view. Now a subscriber can ask their assistant how a vendor compares, and get an answer for
each measure:
- **What it covers:** headcount, headcount change, hiring, funding, press coverage, the
  vendor's own posts, announcements and an activity index.
- **What each answer contains:** the vendor's rank, its percentile, the market median and the
  20 leading vendors by name.
- **An example:** asked about Exaforce, the tool showed 15 articles by others that named it in the last 30 days.
  That is the 97th percentile, where the typical vendor in the market had none.

**We rewrote the copy line by line.** We checked it against Wikipedia's list of signs of AI
writing and cut the patterns it names: a closing flourish, bold labels on every list item,
"not this, but that" contrasts, and a phrase repeated four times. We also cut two items that
described our own workings, which a buyer cannot use.

## Release notes (copy-ready)
- MCP access now includes vendor benchmarks. Ask how any vendor compares with the market on
  headcount, hiring, funding and press coverage, and get its rank and the market median.
- The subscribe page lists what the key adds: benchmarks, sourced vendor profiles and history,
  who funds the market and who is hiring, and every article and post we collected.
- New: a link to Aunoo for Agents, for news and forecasts on other markets and topics.

## Demo / walkthrough
- Open aisocnews.com/subscribe. The "What the key adds" list is under the intro, and the Aunoo
  for Agents card is at the foot of the page.
- With a subscriber key in an MCP client such as Claude, ask "How does Exaforce compare with
  the market on hiring and press coverage?". The assistant calls `get_vendor_benchmark`.

## Positioning notes
The free pages stay free, which keeps the site trusted as an independent source. The paid part
is the data a buyer would otherwise assemble by hand: a like-for-like comparison of a
shortlist, with the source and date of every figure, inside the buyer's own AI tools.

## Limits and what's next
- **It measures activity and scale, not quality.** A vendor above the median is busier or
  larger on that measure, which is all the benchmark says. The tool's own note says so.
- **Some measures are missing for some vendors.** Headcount, funding and job listings come
  from public sources. A vendor with no public job listings has no hiring figure, and the tool
  reports how many vendors were measured.
- **Only aisocnews.com has the benchmark tool.** The other customer sites' MCP servers do not.
- **The site access link adds nothing extra on a public market.** Subscribers are told the key
  is what they are paying for.
