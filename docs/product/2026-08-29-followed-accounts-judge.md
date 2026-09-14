# Followed accounts: what they say about the market reaches the page
_2026-08-29 · Market Monitor front page (Influence and Influencers card, Social section) and the Top voices view_

## What shipped

- A followed account's post now counts when it mentions the market in ordinary words — SOC, SIEM, SecOps, MDR, XDR, EDR, SOAR, detection, analyst, triage, alerts, threat hunting, incident response, playbook, runbook — not only when it uses one of the market's full search phrases ("AI SOC", "security operations center").
- A followed post that matches none of that is read by the same judge that reads vendor posts. An argument or observation about the market is kept; a joke, a bare reply or an unrelated post is not.
- One post is one row. A followed account's post that the keyword search had already caught is no longer counted twice.
- The Influence and Influencers card no longer says "quiet this period" beside a person whose post drew no reactions.

## Why it matters

The follow list exists for people the keyword search misses: analysts and practitioners who write "SOC" and "detection", not "AI SOC". Before today the follow read used the same phrase list as the search, so of Dr. Anton Chuvakin's last 40 posts it kept one — the one that happened to say "AI SOC". The card then showed him with "2 posts" (one post, stored under two URL forms) and later "quiet this period" (his one post drew no reactions and fell off the list the card reads).

Now a followed person's posts reach the page on their merits. The ordinary-word gate keeps the ones plainly about the market at once; the judge reads the rest and keeps substantive commentary. The reader who follows an analyst gets that analyst's view of the market, not the subset that matched a search phrase.

## Release notes (copy-ready)

- Followed accounts: posts that mention the market in ordinary words (SOC, SIEM, detection, analyst, …) are kept; the rest are read by the AI judge and kept when they say something about the market.
- The Influence and Influencers card counts every post in the period, whether or not it drew reactions.
- Fixed: a followed account's post could appear twice.

## Demo / walkthrough

- Front page sidebar, Influence and Influencers: the followed person leads, with "N posts · latest post".
- Explore → Market Monitor → Top voices → Accounts we follow → "Read them now": reads each followed timeline and reports "N posts, N about the market, N new, N for the judge".
- The judge runs once a day; a post it keeps appears in the Social section and the card the next day.

## Positioning notes

None beyond the follow list itself: this makes the feature do what it says. It matters most for the analyst-coverage story (see the Latest research writeup from the same day): following the analysts is how their public commentary reaches the page.

## Limits and what's next

- The first real read under the new rules has not happened: the X data provider answered "usage limit exceeded" on 29 August, so Anton's timeline still shows the one post from the old read. The next 12-hour cycle after the limit resets will read his last 40 posts.
- The judge runs daily, so a post it keeps is up to a day behind; the ordinary-word gate is immediate.
- Reddit accounts can be followed but yield nothing: the provider has no per-user history there. LinkedIn personal accounts are not read at all (company pages only).
- The marker list is one list per market (`follow_markers` in the market's settings); there is no per-person list yet.
