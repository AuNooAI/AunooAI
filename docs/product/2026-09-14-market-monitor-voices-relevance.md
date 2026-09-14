# AI SOC news: the practitioner-voices section stays on topic
_2026-09-14 · aisocnews.com public market page, "What practitioners are saying" section_

## What shipped
The social section of the public market page no longer shows off-topic posts. Stock-market
spam and semiconductor chatter that had been slipping in are now filtered out, so the section
shows what people are actually saying about the AI SOC market.

## Why it matters
The section had two ways for junk to get in, and both are now closed.

The market tracks the phrase "AI SOC" as in Security Operations Center. But "AI SoC" also
means AI System-on-Chip — a computer chip. The matcher could not tell the two apart, so a
Korean stock post about a chip-test company's share price landed in a section about security
software. Anyone reading the public page saw it. We now recognise the chip and
stock-market vocabulary and leave that content out.

Separately, the social section was the one place on the page that showed posts without first
checking they were about the market. Every other section already does that check. Now the
social section does too: a post has to clear the same relevance bar as the news before it
appears. That protects the page against the next term that happens to collide, not just this
one.

## Release notes (copy-ready)
- The "What practitioners are saying" section now filters out off-topic posts, including
  stock-market and semiconductor content that shares wording with security terms.
- Social posts are held to the same relevance standard as the rest of the page.

## Demo / walkthrough
Open https://aisocnews.com/?days=30&view=v2&section=social. The list is practitioner posts
about the AI SOC market, newest first, with the most-shared posts alongside. The stock-spam
accounts that were there earlier today are gone.

## Positioning notes
The public page is the shop window for the market data. Off-topic posts in it undercut the
claim that this is a curated, analyst-grade view of the market, so keeping the section clean
is a credibility fix, not only a tidiness one.

## Limits and what's next
The relevance bar is a fixed score threshold (0.4), the same one used elsewhere. It filters
what is shown; it does not re-judge posts the model scored wrongly. A genuinely on-topic post
that the model scored low would also be held back — the trade favours a clean section over
full recall, matching how the news sections already behave.
