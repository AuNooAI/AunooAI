# A market tracker built for one prospect, on its own site
_23 September 2026 · Market Monitor and Brand Watcher, on a dedicated customer site_

**Audience note.** This describes a sales demo built for one named prospect, Panaya. It is not a
product release. Nothing here is new capability: every screen already existed, and the work was
configuration, data and judgement. It is written up because the setup decisions are reusable for
the next prospect and the mistakes are worth not repeating.

## What shipped
- A private site for the prospect, carrying only the two tabs the demo needs.
- Their market: seven competitors, verified by hand, with who owns them and what they sell.
- Roughly 1,800 articles and social posts going back to December 2024, filtered to that market.
- Headcount, follower counts, funding momentum and open jobs for all seven.
- Dated events: product launches, customer wins, hiring spikes, geographic moves, webinars.
- Every voice in the market labelled as a practitioner, a journalist, a competitor or unrelated.
- Two standing agents that email a brief each morning, one on bad news, one on competitor moves.
- A before-and-after read on the prospect's 9 September rebrand.

## Why it matters

**The prospect asked to see his own market, not a demo.** He said so on the first call: that is how
he will judge whether the data is real. He now opens on his own competitor list. That is the whole
reason for a separate site rather than showing him ours with a filter applied.

**The honest empty cells are the strongest part.** Two rows on the comparison panel carry no number
and say why in words: headcount movement needs a second reading, and disclosed funding reads as
"acquired" because Infosys owns the company. He spent five years at HP with an industry tracker
where every competitor filed real figures. A tool that invents a number where it has none is a tool
he will stop trusting in the first five minutes.

**The agents found things nobody went looking for.** The bad-news agent's first run surfaced a
string of outages at the prospect's largest competitor, including one lasting five days and
twenty-two hours. The competitor agent found a rival launching an autonomous testing product, and a
Gartner Leader placement, inside a seven-day window. That is the difference between a dashboard and
something worth paying for.

**The market has an asymmetry the prospect can act on.** Two vendors take almost all the press
coverage; everyone else is mostly talking to themselves. The prospect sits third. That single fact
is what his rebrand exists to move, and it is measured the same way for every competitor.

## Release notes (copy-ready)
**Internal only.** No customer-facing change. Do not send.

- Built a private Market Monitor and Brand Watcher site for a named prospect.
- Seven competitors tracked, all identifiers verified against company sources.
- Two daily agents configured: adverse coverage, and competitor activity.

## Demo / walkthrough
Forty-five minutes, planned minute by minute in `docs/PANAYA_DEMO_RUNBOOK.md` inside the prospect's
site directory. The short version: open on the vendor list, move to share of voice, then the
comparison panel including its empty rows, then the rebrand read, then events and voices, then ask
the assistant a question against the market live.

The last one matters most for this prospect specifically, because Claude and Claude Code reach
their whole company by the end of October.

## Positioning notes
The prospect already runs a homegrown competitive-intelligence chatbot with battle cards and
objection handling. The line that works is that this is the rigorous data layer underneath it, not a
replacement for it. He has the interface; he does not have the measured, dated, attributed inputs.

His market is almost entirely privately held, so disclosed funding describes very little of it. That
is the argument for reading several weak signals together — hiring, partner pickup, coverage,
events, headcount movement — rather than waiting for a funding announcement that may never come.

## Limits and what's next

**Known gaps, all told to the prospect rather than hidden.** PitchBook is not connected, because its
profile URLs end in a number that cannot be derived from a company name, so somebody with access
must paste one per vendor. Two of the competitors' websites, including the prospect's own, refuse
automated fetches, so there is no site-change detection on those two. Headcount movement needs its
second reading, which was requested today.

**The benchmark sits close to its floor.** It needs five comparable companies before it will show a
median, and this market has seven. It works today. If one company's reading fails on the day of the
demo, the panels say there are not enough peers rather than showing a smaller sample. Check before
the call, not during it.

**One competitor is unconfirmed.** We track Nova Intelligence of San Francisco, which sells agentic
SAP change work. There is an unrelated company called Nova AI selling AI testing agents. The
prospect named "Nova Intelligence" and we matched the SAP one; worth confirming with him in the
first five minutes.

**A bug found while documenting, not fixed.** Removing a company from a market leaves its
auto-discovered news feeds running. Three kept collecting for hours after the company was dropped.
Not customer-visible here because we caught it, but it will bite a real customer who prunes a
market. Logged in `docs/changes.md`.
