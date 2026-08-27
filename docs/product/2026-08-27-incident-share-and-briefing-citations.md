# Sharing an incident by email works again, and market briefings cite properly
_2026-08-27 · Incident sharing (Explore), Market Monitor briefings_

## What shipped
- Sharing an incident by email no longer fails when the AI wrote the timeline as a set of dated
  entries rather than a sentence.
- Market briefings keep every source when a sentence rests on two facts, and put the citation
  after the sentence rather than in front of it.
- Market briefings are now written by a different model (Kimi K2.5). Internal change; the reader
  sees a briefing in the same format.

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

## Release notes (copy-ready)
- Fixed: sharing an incident by email failed with a validation message when the incident's
  timeline or leads were structured rather than plain text.
- Fixed: a market briefing sentence citing two sources at once lost both from the References
  list.
- Improved: market briefing citations follow the sentence they support.

## Demo / walkthrough
Incident sharing: Explore → an incident card → Share → enter an address → Send. Market
briefings: Market Monitor → Briefings → pick a week → Generate report; citations appear as
`[A5]` after sentences, and the References list at the end has one line per cited source.

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
  approve or reject.
- Three internal customer sites (pbm, ibaset, bwtemplate) were stopped and disabled today.
  Their web addresses still answer with an error page rather than nothing, and their data is
  kept.
- The writer change was judged on one week of one market, by eye. A wider before/after across
  several periods is the sensible next step before treating it as settled.
