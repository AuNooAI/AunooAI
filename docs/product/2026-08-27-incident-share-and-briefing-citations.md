# Sharing an incident by email works again, market briefings cite properly, and an approved briefing appears in the news feed
_2026-08-27 · Incident sharing (Explore), Market Monitor briefings, News Feed_

## What shipped
- Sharing an incident by email no longer fails when the AI wrote the timeline as a set of dated
  entries rather than a sentence.
- Market briefings keep every source when a sentence rests on two facts, and put the citation
  after the sentence rather than in front of it.
- Market briefings are now written by a different model (Kimi K2.5). Internal change; the reader
  sees a briefing in the same format.
- An approved market briefing appears in the shared news feed as an item of its own, and opens
  as a page with every citation linked to its source. The feed refreshes as soon as you approve.
- The shared market report (aisoc.aunoo.ai) shows the latest approved briefing: a card with its
  opening line for public readers, the whole text and earlier briefings for a logged-in reader.
  The RSS feed carries it too.
- Vendors whose jobs come from their own careers page (Greenhouse, Lever) now show which
  teams they are hiring for. Before, every one of those roles was "not stated".

## Why it matters
**Incident sharing.** Before, some incidents could not be shared at all. The analyst pressed
Send and got "Input should be a valid string; Input should be a valid list", with no way to tell
what was wrong. The cause was the shape the AI had written the incident's timeline in. Now every
incident shares, and a structured timeline arrives in the email as readable text. Felt by the
analyst sharing, and by the recipient who would otherwise not have got the email.

**Briefing citations.** A market briefing cites its sources inline as `[A5]` and lists them at
the end. When the writer supported one sentence with two sources — `[A5, A11]` — we threw the
whole bracket away, so the sentence stood with no evidence and both sources vanished from the
list. In the 2026-08-17 weekly that happened three times, taking eight sources with it. The
reader saw a bare warning line above the report. Now grouped citations survive, the References
list is complete, and the warning strip is gone. Felt by anyone reading a briefing as evidence.

**Citation placement.** The new writer's first briefing opened sentences with the citation, so
the report read like a numbered list. It now places the citation after the full stop, and a
deterministic pass catches any it still gets wrong at the start of a line.

**Briefing in the feed.** The weekly briefing lived only on the Reports tab, so a reader who
kept to the feed never saw it. Now, when an analyst approves a briefing, it appears in the news
feed for that day, under the market's topic, with the source "Aunoo Market Monitor" and the
briefing's opening paragraph as its summary. Clicking it opens the briefing as a page. Rejecting
the briefing, or regenerating it, takes it out of the feed again, so only text somebody has read
and approved is ever in there. Felt by everyone who reads the feed rather than the Reports tab.

**Briefing on the shared report.** The public report is a trial teaser: it names ten vendors
and deliberately keeps the rest back. A briefing names them all, so the public page shows a
card — the week, the approval date, and the summary sentences that name nobody held back —
with the trial button under it. A logged-in reader opens the full briefing from the same card.
Felt by prospects reading aisoc.aunoo.ai and by the analyst who no longer has to send the
briefing separately.

**Hiring charts.** Dropzone AI showed 11 open roles, all "not stated". Its postings come from
its Greenhouse careers page, which names the department differently from LinkedIn, and the
hiring analysis only read the LinkedIn field. Now both are read, so Dropzone shows 6
engineering, 3 sales and 2 marketing roles, and Qevlar's 15 roles classify too. Felt by anyone
reading the hiring section of a market report or a vendor page.

## Release notes (copy-ready)
- Fixed: sharing an incident by email failed with a validation message when the incident's
  timeline or leads were structured rather than plain text.
- Fixed: a market briefing sentence citing two sources at once lost both from the References
  list.
- Improved: market briefing citations follow the sentence they support.
- New: an approved market briefing appears in the news feed and opens as a page with linked
  sources. Rejecting or regenerating it removes it from the feed. The feed refreshes on approval.
- New: the shared market report and its RSS feed carry the latest approved briefing; public
  readers see a card, logged-in readers the whole text.
- Fixed: job postings collected from a vendor's own careers page showed as "not stated" on the
  hiring charts instead of their department.

## Demo / walkthrough
Incident sharing: Explore → an incident card → Share → enter an address → Send. Market
briefings: Market Monitor → Briefings → pick a week → Generate report; citations appear as
`[A5]` after sentences, and the References list at the end has one line per cited source.
Briefing in the feed: Reports tab → a briefing → Approve, then News Feed → today; the item is
there with source "Aunoo Market Monitor". Click it to open the page.

## Positioning notes
None that change the story. The briefing's claim is that every figure comes from a stored
record and every specific claim carries a citation; this restores that claim where it had
quietly stopped being true.

## Limits and what's next
- The share modal reports "Email Not Configured" for any failed status check, including a
  momentary outage during a restart. The message is wrong in that case; a retry works.
- A citation that opens a sentence in the middle of a paragraph is left where it is, because
  from the text alone it cannot be told apart from one closing the previous sentence. Only
  line-start cases are corrected automatically; the rest rely on the prompt.
- The 2026-08-17 weekly was regenerated three times today and is in draft. It still needs an
  approve or reject, and approving it is what puts the first briefing into the feed.
- On the public report the briefing is a card, not the text. That is the report's own rule
  (ten vendors in public, the rest in the trial), not a gap; a briefing sentence that names a
  held-back vendor is dropped from the card whole.
- The briefing page needs a login. A feed shared by link to someone outside the site will show
  the briefing item, but the link behind it lands on the login page.
- The feed item is stored like an article, so the AI agents that watch a topic can see it. One
  item a week per market; it is marked as a report, but nothing filters on that mark yet.
- Three internal customer sites (pbm, ibaset, bwtemplate) were stopped and disabled today.
  Their web addresses still answer with an error page rather than nothing, and their data is
  kept.
- The writer change was judged on one week of one market, by eye. A wider before/after across
  several periods is the sensible next step before treating it as settled.
