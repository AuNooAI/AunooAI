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
- The market is now called "AI in the SOC".
- An "Is your company missing?" button on the vendor list lets a vendor we do not track ask
  to be looked at: company, website and a contact address.
- Top voices now says who each account is. Every account links to its page on X, Bluesky or
  Reddit and to its latest post about the market. One click builds the same account profile
  Brand Watcher uses (who they are, reach, what they post about, and their part in this market),
  and one button profiles the whole list.
- The report's list of accounts that keep posting about the market no longer misses the ones
  with few reactions.
- Market Horizon marks the vendors doing the most product work as "innovating" — a ring on
  the dot, across every tier — from launches, confirmed launches, research posts and
  engineering hiring. Acquired vendors are listed with the acquirer, not placed on the map.
  On each vendor's page an analyst can weight the inputs for that vendor, mark it acquired or
  closed, and leave a note; every adjustment is shown beside the vendor.
- Market Horizon: a map of every rated vendor by scale (headcount, funding, followers,
  customer evidence) against momentum (headcount change, hiring, launches, coverage), in four
  tiers — Executing, Accelerating, Establishing, Emerging. A vendor is on the map only when every
  reading behind it was collected; the rest are listed with what is missing. The weights are
  printed under the chart. It is in Market Monitor and in the report.
- A vendor seen posting about the market that we do not yet track is filed automatically in
  the "Is your company missing?" queue, with its account and what it posts about, for the
  same review a reader's request gets.
- Vendors' own social accounts, and their staff, stay in Top voices but carry a "vendor" tag
  with the company name, and the list can be grouped by role (vendor, vendor staff,
  practitioner, analyst or press, reseller, promoter or bot).

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

**Top voices.** Before, the tab was a list of handles ranked by reactions. The account at
the top of the AI in the SOC market had one post and 28 reactions; the profile shows it is a
founder promoting their own AI tools with no part in the market. An analyst had to leave the
product to learn that. Now the profile sits on the row, with links to the account and its
latest post, and the tab tells the reader that 122 accounts posted in the month and only 10
posted more than once, so a table of single posts reads as what the market is, not as a
broken table.

**Market Horizon.** Buyers ask for "the quadrant". What we can build from collected data is
a map of size against movement, and that is what this is, said plainly on the page: it does
not rate product quality or strategy. The honesty is in the gate — a vendor without a
disclosed funding total or a second headcount reading is not plotted at zero, it is listed as
not yet rated with the reason — and in the weights being visible. On AI in the SOC today that
gate passes one vendor; the second weekly headcount reading, due within a week, will pass most
of the rest that have disclosed funding.

## Release notes (copy-ready)

- Shared market reports state the same findings as the full report. Vendors not included in
  the shared view are counted but not named.
- The sources table lists the social platforms and Glassdoor.
- "SOC Automation" is now "AI in the SOC".
- Vendors not on the list can ask to be added from the report itself.
- Customer-evidence rows say whether the customer is named, who is speaking, and whether it
  is in use, under evaluation or a case study.

- Top voices: each account links to its platform page and its latest post; a "Profile" button
  (or "Profile the N unprofiled") builds the account profile, with a "Who they are" column and
  a detail panel.
- The report's "Accounts posting repeatedly" table now includes accounts with few reactions,
  and links each one.

- Market Horizon: a scale-against-momentum map of rated vendors in four tiers, with the
  weights shown and the unrated vendors listed with the reading each one lacks.

## Demo / walkthrough

Open `https://aisoc.aunoo.ai/` (the shared view) and the same market signed in with `?full=1`.
The Concentration paragraph and the four findings read the same on both. Under "Where the
numbers come from", the legend lists X, Reddit, TikTok, Instagram, Bluesky and Glassdoor.

Top voices: Explore → Market Monitor → Top voices. Click "Profile the N unprofiled" and
watch the progress line; click a row's "Who they are" text for the full profile; the @handle
and the latest-post date open the platform in a new tab.

Market Horizon: Explore → Market Monitor → Market Horizon → "Recompute from today's
readings". Hover a dot for every input behind it; click a name for the vendor page. In the
report it is the "Market Horizon" drawer above the vendor registry.

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
- Profiles are built on request, never on a schedule. Each costs two xpoz calls and one short
  model call, and xpoz rate-limits the shared key, so the bulk button works through the list
  one account at a time (about ten seconds each).
- A vendor's own X account (SentinelOne appears on market 2) stays on the list, now tagged
  "vendor · SentinelOne". The tag comes from the profile's reading; an account with no profile
  is tagged only if its handle matches a vendor we track. Untracked ones are queued for review
  (11 on AI in the SOC on the first run); nothing is added to the vendor list without a person
  deciding.
- Most accounts have a single post because the social pull is capped per platform per run
  (`XPOZ_MAX_RESULTS`, default 25). Raising it costs money; not changed.
- Market Horizon rates only vendors with every input measured. On a market three weeks into
  collection that is one vendor; the map fills as readings accumulate. Names are ours, not
  Gartner's or Forrester's, and the page never calls itself a quadrant or a wave.
