# The quarterly letter stops calling things a "crisis" — and now a backstop catches it if it tries

_2026-08-24 · Wiley quarterly foresight letter, scheduled signal-alert emails, Briefing Desk_

## What shipped
- The Wiley quarterly letter's Executive Summary — and the three writers that feed it (the
  per-topic briefing, the cross-topic strategic overview, and the expert commentary on emerging
  themes) — no longer write "crisis", "severe", "aggressive", "alarming", "catastrophic",
  "collapse", or "compromised" in their own voice. They name the actor, the action, and the
  count instead, and let the reader decide how serious it is.
- Scheduled signal-alert emails (the "Observer agent" reports customers get on a schedule) and
  Briefing Desk (the manually-curated briefing tool) got the same treatment. Briefing Desk had
  no such rule at all before today.
- New: a second, mechanical check behind the writing rule. If a draft still uses one of the
  banned words, the system now catches it, tells the model exactly which word slipped through,
  and has it rewrite that one sentence — instead of hoping a plain instruction is enough.

## Why it matters
On 2026-08-13, Wiley's Director of AI Strategy told us directly that a company that has been
publishing for a century or two treats a bad news cycle as business as usual, and that words
like "crisis" are a judgment he wants to make himself, not one we hand him pre-made. We fixed
that for the day-to-day reports on 2026-08-13 (see that entry). What we had not yet fixed was
the one document that started the conversation: the quarterly letter his own team reads first,
plus two other places customers see AI-written narrative — the scheduled alert emails and the
curated briefing tool.

Testing this fix surfaced something the 08-13 fix didn't have an answer for: telling the model
not to use a word doesn't make it stop 100% of the time. Fed deliberately provocative input
(paper-mill fraud, mass retractions — the kind of thing that tempts strong language), the
writers still used a banned word on roughly 1 attempt in 3 or 4, even with the rule in place.
That is why this round adds the second layer: a plain word-check on what the model actually
wrote, with an automatic one-sentence rewrite when it catches something. Tested on 12 more
generations after adding it, every one of the two that came back dirty was corrected before
being accepted.

## Release notes (copy-ready)
- The Wiley quarterly letter's Executive Summary, per-topic briefings, and expert commentary no
  longer use severity language ("crisis", "severe", "collapse", etc.) in their own voice.
- Scheduled signal-alert emails and the Briefing Desk briefing tool carry the same rule.
- A new automatic check catches the rare case where the writing rule alone doesn't hold, and
  rewrites just the affected sentence rather than shipping it as-is.

## Demo / walkthrough
Nothing to click through today — this changes what gets written the next time each of these
runs, not something already on screen. The next Wiley quarterly letter, the next scheduled
signal-alert email, and the next Briefing Desk synthesis will all reflect it.

## Positioning notes
This closes the same "why does every incident read like a catastrophe?" objection the 08-13 fix
addressed, but this time on the flagship deliverable — the letter a customer's own leadership
reads first — rather than the day-to-day reports underneath it. It also answers the open
question that fix left on the table: what happens when the writing rule doesn't hold. Now
something does.

## Limits and what's next
- The automatic word-check only exists for the quarterly letter and the scheduled alert emails,
  both of which already had a retry mechanism to build on. Briefing Desk got the writing rule
  but not the check — if it slips, nothing catches it yet.
- Everything here was tested against deliberately provocative made-up scenarios, not a real
  customer's data. The next actual Wiley quarterly letter is the real test.
- If the check runs out of retries and a report still has one leftover word, it ships anyway
  rather than falling back to a bare, unanalyzed list of matches — a stray adjective was judged
  the lesser problem. That trade-off hasn't been reviewed against a real incident yet.
