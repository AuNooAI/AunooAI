# The briefing safety check was too strict, and dropped good articles
_2026-08-19 · Explore tab → daily briefing_

**Audience note.** This is a follow-up to yesterday's briefing fix
([2026-08-18](2026-08-18-briefing-full-article-count.md)). The release notes below are
safe to send. If you already sent yesterday's note saying the briefing now always fills
up, this correction matters, because for one morning it did not.

## What shipped

The daily briefing on the Explore tab returns the full number of articles again. This
morning it returned five instead of six, and the cause was a check we added last night.

## Why it matters

Yesterday we fixed the briefing losing articles. The AI model picks the day's most
important stories out of a pool of about fifty, then has to hand each pick back to us by
copying the article's web address exactly. Some addresses differ by a single character,
the model would miscopy one, and we would quietly drop a good article.

Yesterday's fix gave the model a short reference number to copy as well, like `a7`, so a
miscopied address no longer loses the pick.

Last night a review pointed out the obvious follow-on risk. A two-character reference
number is itself easy to get wrong. If the model returns reference number `a46` but an
address that belongs to a different article, believing the number would attach today's
analysis to the wrong story with the wrong link — a worse outcome than the missing
article we were trying to prevent. So we added a tie-breaker: when the number and the
address disagree, the headline decides, and if the headline cannot decide, we drop the
pick rather than guess.

The tie-breaker was right in principle and wrong in practice. It compared headlines
character for character. But we ask the model to write each headline with its source and
date appended, like `... (Business Insider, 2026-08-18, Melia Robinson)`, so the headline
it returns is never character-for-character identical to ours. The tie-breaker therefore
failed every single time and threw the pick away.

This morning's briefing lost four picks that way. Every one of them named a real article
with the right address and the right headline. Only the two-character number was wrong,
which is exactly the case the tie-breaker was supposed to survive. The briefing asked the
model for replacements, got two back, lost a third to the same problem, and settled at
five.

The briefing now compares the part of the headline that is actually shared, which is what
the rest of the system already did. The protection against picking the wrong article is
unchanged: where two syndicated copies of a wire story share a headline, that headline
still identifies nothing, and the pick is still dropped rather than guessed.

**How we checked.** We replayed this morning's four dropped picks against a 400-article
pool taken from the live Wiley test site. All four now resolve, and none resolves to the
wrong article. Before the fix, all four were dropped.

## Release notes (copy-ready)

- Fixed a regression introduced on 18 August where the daily briefing could return fewer
  articles than requested. A safety check meant to prevent an article being attached to
  the wrong link was rejecting valid selections. The briefing returns the full count
  again, and the protection against wrong links is unchanged.

## Demo / walkthrough

Open **Explore** and look at the briefing. It should carry the number of articles set in
the briefing options, six by default. Today's briefing was generated before the fix and
still shows five; the next scheduled generation, or pressing regenerate, produces a
corrected one.

## Positioning notes

None. This corrects a defect we shipped ourselves, within a day. Nothing here is a
selling point. If a customer noticed the short briefing this morning, say what happened
plainly — a fix we shipped yesterday had a follow-on defect, we found it the same day and
corrected it.

## Limits and what's next

- Today's briefing on the Wiley test site was generated before the fix and still shows
  five articles. It is not rewritten automatically. Tomorrow's is the first one produced
  under the fix.
- The underlying reason any of this is needed has not changed. We still ask the model to
  copy identifiers by hand and then check its work, rather than having it choose from a
  list it cannot mistype. That redesign has not been scoped.
- Two of these defects in two days came from the same small piece of code. It now has
  seven tests covering the ways a pick can be lost or misattached, which is the guard
  against a third.
