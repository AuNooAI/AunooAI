# The market report now answers the question it was asked
_27 August 2026 · Market Monitor — the shared report link_

## What shipped

- The report opens with three to six findings. Each one states what changed, shows the
  evidence, links to the events behind it, and says how much of the market it rests on.
- A table of the vendors that showed material change: the vendor, what happened, who
  reported it, and why it matters for the market.
- A short "What this says about the market" section on how young the vendor cohort is,
  whether activity is product news or customer evidence, and where activity is concentrated.
- One entry per event. Seven articles and posts about one acquisition are one development
  with seven sources listed underneath, not seven developments.
- Every development says whose word it rests on: "Vendor source only", "Also reported
  independently", or "Reported by multiple independent sources".
- "Vendors with no signal" is gone. In its place, each vendor is in one of four states: showed
  material change, monitored with no change observed, incompletely observed, or paused.
- "Funding and momentum" is now "Funding and investor activity". It leads with the funding
  and acquisition events of the period, disclosed totals, stage mix and shared investors.
  Crunchbase's own Growth and Attention scores are still shown, labelled as Crunchbase's
  scores, and never presented as market momentum.
- Practitioner chatter, job-seeker posts, course completions and market-size reports no
  longer appear in the main list. They stay reachable under "View underlying coverage".

## Why it matters

**The reader can stop after two screens and know what happened.** Before, the lead was a feed
of records and a strip of numbers, and the reader had to work out from charts what the
period meant. Now the first screen says, for this market: one acquisition brought an
established data company into the category; one vendor announced new capital; vendors made
20 product announcements against 7 customer announcements, none of the 7 reported by anyone
but the vendor; 25 of 84 vendors showed material change; 44 of 50 developments rest on the
vendor's own word. Each of those sentences links to the events and says what it covers.

**One event is counted once.** The old report listed the Cribl acquisition of Radiant
Security's AI SOC technology four times, once per article, and counted a passing tweet as
outside confirmation of an unrelated launch. Merging now needs the same vendor, the same kind
of event, two weeks or less apart, and a shared name or subject. The seven sources for that
acquisition sit under one entry, each named by the account or outlet that carried it.

**"We saw nothing" no longer masquerades as "nothing happened".** A count of 61 vendors "with
no signal" said we had watched all 61 and found nothing. We had not: for 11 of this market's
vendors the website collection has never succeeded. The report now says "monitored, no
material change observed" only for a vendor whose LinkedIn page and website were both read
during the period, and puts the rest under "incomplete observation" with nothing concluded
about them. A paused vendor is paused, never quiet.

**Claims and reporting are visibly different things.** A vendor announcing a customer is one
side of a story until somebody else says the same. The report now marks that on every
development and in a finding of its own, and it uses "reported independently" rather than
"corroborated", because another source carrying the same event is not a fact-check.

**Nothing is written for this market in particular.** Every finding comes from a rule with a
declared minimum coverage — a comparison across the market is not made when the vendors'
own channels were read for fewer than half of them — so the same report works for any
market, and a finding that the data cannot support does not appear.

**It is fast and repeatable.** The page builds in about a second from stored data, with no
AI call, so the same data always produces the same report and a shared link never waits on
a model.

## Release notes (copy-ready)

- The Market Monitor report now leads with an executive assessment: three to six evidence-backed
  findings, each with its coverage stated.
- A "Vendors showing material change" table lists who moved, on what evidence, and why it
  matters.
- Developments are deduplicated: one entry per event, with every source underneath.
- Every development states whether only the vendor has said it or others have reported it.
- Vendor silence is reported honestly: "no change observed" is claimed only where the
  vendor's expected sources were all read in the period.
- "Funding and investor activity" replaces "Funding and momentum"; Crunchbase scores are
  labelled as Crunchbase's and are not treated as momentum.
- Social chatter and job-seeker posts are out of the main list and behind "View underlying
  coverage".

## Demo / walkthrough

Open a market's report link (Market Monitor → Share, or
`/api/market-monitor/markets/{id}/report.html?days=30`). The first screen is the assessment;
scroll to the table, the synthesis, and the developments list. Click a finding's
"Developments" link to jump to the event; click a source name under it to open the record.
The "Evidence", "Vendors" and "Method" links in the top bar open the folded sections. Switch
7, 30 and 90 days at the top right.

## Positioning notes

This is the difference between a monitoring feed and an analyst's read. Coverage tools list
what was collected; this report says what the evidence shows and, as clearly, what it does
not. The observation states and provenance labels are the answer to "how do I know you did
not just miss it" — the report tells the reader which vendors it was in a position to see.

## Also shipped later the same day

- The report is signed "By the Cyberfuturists · made using Aunoo", with both marks, at the
  top and the bottom.
- A vendor blog that re-dates its whole archive no longer turns old posts into this month's
  news. Prophet Security's Series A page, re-dated 14 August 2026 by its site, is dated
  31 July 2025 again (the earliest public archive capture), and the funding finding it
  produced is gone. The feed collector now checks batches of same-minute dates the same way
  before storing.
- Coverage notes appear only where coverage is actually short, and say what the gap means.
  Findings quote the event in the record's own words.
- A second page, "News river", lists everything matched in the period the way Techmeme's
  river does: time, source, headline, and the other outlets carrying the same story.
- In the app, Top voices has its own tab beside Analysis.

## Limits and what's next

- A page's corrected date is "no later than" the archive's first capture, not the day it was
  published.
- "Reported independently" counts sources we collect. A vendor covered by outlets we do not
  read looks uncorroborated.
- Merging is a rule, not a model. Two posts by one vendor about two different product
  features can still merge if they share a product name, and a repost that names nothing in
  common with the original will not.
- Hiring developments rest on job boards read for 20 of 84 vendors, and say so.
- No comparison with the previous period yet: this market began collecting on 19 August, so
  the first true period-on-period comparison is available from 18 October.
- Next: fix the vendor-web publication date; add market entry and exit detection beyond
  keyword rules once any such event exists in the data to test against.
