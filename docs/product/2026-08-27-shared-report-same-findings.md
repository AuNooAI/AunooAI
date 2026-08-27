# The shared market report now says what the full one says
_27 August 2026 · Market Monitor — the shared report link and aisoc.aunoo.ai_

## What shipped

- The findings at the top of a shared report are computed from the whole market, not from
  the ten vendors the reader is allowed to see by name. Vendors outside that ten are counted
  and appear as "a vendor not shown in this view".
- The "Which sources we use" table names the social platforms we read (X, Reddit, TikTok and
  Instagram through Xpoz; Bluesky directly) and adds Glassdoor employee reviews.
- Each customer-evidence row now says whether the customer is named, whether the customer or
  the vendor is speaking, and whether it is a deployment, an evaluation or a case study.

## Why it matters

**Before**, a reader without a code could be told the opposite of what the data says. The
shared SOC Automation report said hiring was concentrated, with one vendor holding 58% of open
roles, and that only 5 of 84 vendors had job listings. The operator's own view of the same
market said hiring was spread, with the leader at 21% of 149 roles across 20 vendors. The
shared page had counted only its ten named vendors and compared that against all 84. The
same happened to the count of vendors that changed (8 against 25), the share of developments
held by the top three (53% against 24%), and the verdict on product news against customer
evidence.

**Now** every figure in the lead is the market's figure. What the shared reader does not get is
the names behind the withheld vendors. A buyer, analyst or investor reading the shared link
sees the same assessment the operator sees.

**Customer rows used to all say the same thing.** "A named customer or deployment, so far on
the vendor's word only" appeared under every one, including rows that named nobody and one
that described an evaluation. It now reads, for example, "Named customer: Virgin Money, in the
customer's own words, described in use" or "Unnamed customer: a published case study, in the
vendor's words". The "who else reported it" caveat is gone from customer rows: customer wins
are almost never reported by anyone but the vendor, so the caveat separated nothing.

## Release notes (copy-ready)

- Shared market reports state the same findings as the full report. Vendors not included in
  the shared view are counted but not named.
- The sources table lists the social platforms and Glassdoor.
- Customer-evidence rows say whether the customer is named, who is speaking, and whether it
  is in use, under evaluation or a case study.

## Demo / walkthrough

Open `https://aisoc.aunoo.ai/` (the shared view) and the same market signed in with `?full=1`.
The Concentration paragraph and the four findings read the same on both. Under "Where the
numbers come from", the legend lists X, Reddit, TikTok, Instagram, Bluesky and Glassdoor.

## Positioning notes

The shared link is the thing a prospect reads before they buy. It has to be right in the
same way the paid view is right, or the trial request that follows starts from a wrong
number.

## Limits and what's next

- The customer reading comes from the same AI pass that already reads every vendor post, and
  is stored with the post. Posts reviewed before this change get it on the next scheduled run;
  until then a rule-based fallback reads them. On the SOC Automation market all 29 customer
  posts were read and checked by hand.
- The reading is one model's judgement of one post. Where two posts about the same customer
  disagree (an evaluation write-up and a later "in use" post), the development carries one of
  them.

- The evidence lists under each finding still name only the shown vendors; withheld ones are
  collapsed into a single "N vendors not shown in this view" line.
- The developments table, records list and sidebar in the shared view remain the shown
  vendors' items only, since those are headlines and a headline names its subject.
- This market's social topic reads X and Reddit; TikTok and Instagram are supported by the
  collector but not turned on for it. Glassdoor has one review on this market so far.
