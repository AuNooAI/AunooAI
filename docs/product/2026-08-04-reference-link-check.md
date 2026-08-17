# Every link in a report is now checked before delivery
_2026-08-04 · Topic reports (deck, web report); review checklist_

## What shipped

- Every report build now tests every source link it cites. Each link is fetched and
  sorted into one of five outcomes: it loads; it loads behind a paywall; the site blocked
  our automated check (a human in a browser may still get through); it now redirects to
  the site's homepage, which usually means the article was taken down; or it is dead.
- The results are stored with the report build, and the reviewer's checklist now says
  what to do with each outcome: replace or drop dead links, spot-check blocked ones by
  hand, and leave paywalled ones alone — the customer sees the publisher's own gate,
  which is normal.
- A command-line version of the same check lets an analyst test any report file or any
  list of links on demand, and can be wired to refuse a send while dead links remain.
- The check proved itself on the delivered Q3 report the day it was built. Of 315 cited
  links, one was confirmed dead. It turned out the publisher had re-dated the article,
  which changed its address. We repointed the citation to the live address and rebuilt
  the deck and web report from the same analysis, so the numbering and content are
  untouched.

## Why it matters

A report's credibility dies fastest at a dead link: the customer clicks a citation, gets
a 404, and starts doubting the claims that cite everything else. Until now nobody
checked the links; the reference lists were built from articles collected weeks or
months earlier, and the web moves underneath them.

Now the check runs on every build, takes about a minute for a 300-link report, and the
reviewer sees exactly which links need attention before the report goes out. The Q3
sweep gives the baseline: 315 links, 219 clean, 20 paywalled, 69 refusing automated
checks, 1 truly dead — found and fixed the same day.

## Release notes (copy-ready)

- Every source link in a report is now verified before delivery: live, paywalled,
  or dead.
- Link-check results are stored with each report build and covered by the reviewer's
  sign-off checklist.
- The one dead link found in the Q3 report was traced to a publisher moving the
  article, and the citation now points at the live page.

## Demo / walkthrough

Generate any topic report. The build log shows "Checking N reference link(s)" near the
end; the stored results list every link that needs attention. There is no separate UI
surface.

## Positioning notes

Extends the "expert human oversight on every output" story from the release gate shipped
2026-08-03: the gate proved every claim traces to a source, and this proves the customer
can actually open the source. Small on its own, but it closes the most visible failure a
customer can hit in a delivered report.

## Limits and what's next

- The check is advisory. It flags; a human decides. Nothing yet physically blocks
  sending a report with dead links, though the command-line tool can be wired to do so.
- About a fifth of links (69 of 315 in the Q3 sweep) sit on sites that refuse automated
  checks outright. For these the check can only say "unverified" — a human spot-check in
  a real browser is still the honest answer.
- A link that dies after delivery stays dead in the sent copy. The check runs at build
  time; it is not a monitor.
- Paywall detection reads the page's own markers, so a publisher that hides its paywall
  from crawlers may be counted as clean.
