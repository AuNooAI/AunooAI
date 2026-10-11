# Brand Watcher: competitor-brand reports were running on missing data — now repaired, and social coverage completed
_2026-08-07 · Brand Watcher on three customer sites (wileytest, wbm, ibaset)_

## What shipped
- Competitor-brand news classification restarted on two sites where it had silently stopped
  in early July. All monitored brands are now processed every six hours.
- The missing month was backfilled and the affected risk reports regenerated.
- Social media coverage extended: X, Reddit, Instagram, and TikTok collection turned on for
  all monitored brands on wileytest; Springer added on wbm; the ibaset site went from no
  social monitoring at all to full coverage of its five brands.

## Why it matters
**Before:** the Pearson risk report on wileytest said "Low risk, 0/100" with a single
article captured in a month. The platform had actually collected 585 Pearson-mentioning
articles in that window — but the step that assigns articles to a brand had only been
running for the site's own brand since July 4, so every competitor report was built on an
empty month. An empty month reads as a quiet month; nobody gets an error. The same gap
existed on wbm, hidden further by run history inherited from the site it was cloned from.

**After:** the backfill classified the missing weeks and the regenerated Pearson report
tells the real story: High risk — 71/100 on wileytest, 88/100 on wbm — driven by a quarterly
earnings miss, downgrades from three major banks, a 6.3% one-day stock drop, and a
copyright-bot incident that hit an author's own code repository. That is the difference
between a reassuring report and an actionable one, and the people who feel it are the
analysts and account owners who read these reports.

**Social:** competitor perception increasingly moves on X, TikTok, Instagram, and Reddit
before it reaches the press. wileytest was only listening to Bluesky; ibaset was listening
to nothing. Both now collect across all platforms, with search terms chosen to survive
social noise (no bare "SAP", "Tulip", or "Springer" — those return direct messages, flowers,
and Jerry Springer).

## Release notes (copy-ready)
- Fixed: competitor-brand classification had stopped on two sites; all monitored brands are
  now processed on the same six-hour schedule, and the missing period was backfilled.
- Fixed: Pearson risk reports regenerated on the corrected data (Low 0/100 → High 71/100 and
  88/100 on the two affected sites).
- New: X, Reddit, Instagram, and TikTok collection enabled for all monitored brands on
  wileytest; Springer social monitoring added on wbm; full social monitoring stood up for
  all five ibaset brands.

## Demo / walkthrough
Brand Watcher → pick a competitor brand (e.g. Pearson) → the dashboard and the generated
narrative now show a populated month with category breakdowns and the High-risk drivers.
On ibaset, the Social tab now carries posts for all five brands (first X/Reddit/Instagram/
TikTok posts landed today; Bluesky joins from tomorrow's cycle).

## Positioning notes
The pitch for Brand Watcher is "you'll know when a competitor's month turns bad". This
session is what makes that claim true for every monitored brand, not just the customer's
own — the Pearson swing from 0/100 to 88/100 on the same underlying news is a concrete
before/after for that story.

## Limits and what's next
- The report generator has an unfixed defect: when generation takes long, the finished
  report can fail to save while still displaying once — the UI then keeps showing the older
  saved version. We worked around it manually this session; a code fix is queued.
- wiley prod was checked and is not affected: Brand Watcher is not in use on that site
  (no brands configured), so there was nothing to go stale.
- ibaset's Bluesky collection starts with tomorrow's daily cycle; today's first pass was
  X/Reddit/Instagram/TikTok only.
- Social volumes for niche industrial brands are legitimately small (iBASEt: 3 posts,
  Tulip: 2 on the first pass). Set expectations accordingly — the value there is early
  warning, not volume.
