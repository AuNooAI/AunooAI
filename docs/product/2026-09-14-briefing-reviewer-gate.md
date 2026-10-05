# Daily Briefing: a reviewer reads every briefing before it can be finalized
_2026-09-14 · Briefing Desk_

## What shipped

- Every daily briefing is now checked against its own sources before it can be
  finalized. A second model reads the generated summary, themes and decision points
  next to the articles and incidents they were written from, and lists every claim the
  sources do not support: a number that appears nowhere, a company attached to a story
  that never mentions it, an article date presented as the date something happened, a
  wrong institution, one wire report described as several outlets confirming.
- When the reviewer finds an error, the briefing stays a draft. The analyst sees the
  findings and the held text, and can regenerate or finalize anyway with a reason. The
  name and reason are stored on the briefing.
- When the reviewer finds only warnings, or nothing, the briefing finalizes as before and
  shows a short reviewer line under the model byline, with the findings one click away.
- If the reviewer cannot run, the briefing says so instead of looking approved.

## Why it matters

A briefing goes out by email. Until today nothing stood between the writing model and
the send button, and a reader checking one day's Sunstar briefing found three items
dated by the day we collected the article rather than the day the thing happened. The
reviewer is the same gate the Wiley quarterly bundle has had since May, applied to the
daily product.

## What to expect

The reviewer is strict on purpose. On the first Sunstar briefing it held the draft for
eleven findings, most of them right and a few of them paraphrases it should have let
through. The override exists for those cases, and every override is recorded.

## Later the same day: a clean report on the first try

The first version held every briefing, because the checking model was as fallible as the
writing model. Three changes fixed that. Dates, figures and monitored brand names are now
checked mechanically against the sources, which never guesses. The checking model must
quote the sentence it objects to, and objections about sentences that do not exist are
thrown away. And when the check finds a problem, the writer fixes the quoted sentences
and the check runs again, up to twice, before anything is held. Today's Sunstar briefing
went through with one correction and finalized on its own.

## Where it is live

bugfixing, sunstar, wiley and wileytest, deployed 14 September 2026.
