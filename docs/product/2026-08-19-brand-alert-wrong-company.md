# Brand alerts now check they are measuring the right company
_2026-08-19 · Brand Watcher — employer-rating alerts and the brand overview panel_

## What shipped

- Brand Watcher no longer mixes up a company with another company of a similar name.
- The company it tracks on Glassdoor is now locked in, so it stays the same from day to day.
- An alert about a falling rating is only sent when the ratings being compared belong to the
  same company.
- A wrong alert that had already gone out was withdrawn, and the affected customer view was
  corrected.

## Why it matters

**Before:** a customer received an email this morning saying Wiley's employer rating had dropped
from 3.7 to 3, and that the share of employees positive about the business outlook had fallen
from 44% to zero. None of that had happened. The real page still read 3.7 and 42%.

What actually happened is that Brand Watcher looked up "Wiley" on Glassdoor and got back a
different company — a 51-to-200-person Australian business with **three reviews**, rather than
the 2,435-review company it had been tracking every day since 7 August. It then compared the new
company's numbers against the old company's numbers and reported the difference as a decline.

Two things allowed it. Glassdoor's company search does not put the best match first — searching
"Wiley" returns the Australian business ahead of the real one — and Brand Watcher took the first
result whose name contained the brand name. It also never wrote down which company it had settled
on, so it looked the name up again every time the service restarted, and could land somewhere new.

**Now:** a company has to have at least 50 reviews before Brand Watcher will pick it automatically,
an exact name match is preferred, and the most-reviewed company wins otherwise. Once a company is
chosen it is recorded against the brand and reused. If a later lookup disagrees, the reading is
thrown away rather than saved. And the alert itself checks that the two ratings it is comparing
belong to the same company before it says anything.

Checking this against the live Glassdoor data for all five tracked brands turned up a second
quiet error nobody had reported. "Springer" was matching an 18-review German engineering firm
that happens to be named exactly "SPRINGER", not Springer Nature, the publisher the customer
actually tracks. That is now correct as well.

**Who feels the difference:** the person who receives brand alerts. A false alarm about employee
sentiment is the kind of thing that gets forwarded to an executive before anyone checks it, and
it costs more trust than a missed alert does.

## Release notes (copy-ready)

- Fixed: employer-rating alerts could compare two different companies with similar names and
  report the difference as a decline. Brand Watcher now locks on to a single company per brand
  and will not compare across a change.
- Fixed: brands could be matched to a small, unrelated company with a near-identical name. Company
  matching now requires a meaningful number of reviews and prefers an exact name match.
- When no confident match exists, Brand Watcher now reports no employer data instead of guessing.
  The company can be set manually.

## Demo / walkthrough

Brand Watcher → select a brand → the employer-ratings panel on the brand overview. The company
name shown there is the one being tracked, and it now stays put between visits.

To confirm the repair on the affected customer site, the Wiley panel reads 3.7 with a 42% business
outlook, matching Glassdoor. Before the fix it read 3.0 with 0%, because the panel was showing the
Australian company.

## Positioning notes

This is a trust fix, not a feature. Brand monitoring is bought on the promise that an alert means
something, and an alert that a rating "collapsed" when it did not is worse than no alert — the
customer has to check every future one by hand.

Worth being straightforward if it comes up with the affected customer: we sent one wrong alert,
we found why within the hour, and the rule now refuses to compare data from two different
companies. Do not describe this as an improvement to matching accuracy; it was a defect.

## Limits and what's next

**Company matching still cannot resolve every brand on its own.** Searching Glassdoor for
"Pearsons Education" returns no Pearson at all — only estate agents, lawyers, a florist and a
bakery. Brand Watcher now correctly refuses to guess and reports nothing until someone sets the
company by hand. Pearson was already set manually, so nobody sees a change, but any new brand with
an ambiguous name will need the same one-off step.

**Springer on the affected site has no employer data yet.** It has never fetched successfully, so
there is nothing recorded to lock on to. The next run will pick Springer Nature and lock that in.
If a different Springer entity is wanted, it should be set before then.

**The 50-review threshold could exclude a genuinely small employer.** A brand with fewer reviews
than that gets no automatic match. That is the deliberate trade — no data beats another company's
data — but it means small tracked brands may need the company set manually.

**Not on every customer site.** The fix is live on five sites. Others carry the same code but were
not updated in this pass.

---

_Also in this session, not covered above: an internal fix to the record of what our AI spending is
being used for. It has no customer-facing surface. Before the fix that record could say what was
spent but not what it was spent on — 99.86% of entries were filed as "unknown". It now attributes
99.76%. This matters for our own cost control and for deciding which features are worth their
model spend; it changes nothing a customer sees, and should not appear in customer-facing
material._
