# Employee reviews were another company's, and are no longer shown
_2026-08-26 · Brand Watcher / Market Monitor — employer ratings_

## What shipped

- Employee reviews are no longer shown for companies where we could not confirm the match.
- Every match is now checked against the company's known employee count. A match that disagrees by a wide margin is rejected as a different company.
- The four wrong matches on the SOC Automation market, and the seven reviews collected under them, have been removed.
- The check runs on every path a review can arrive through, including a manually pinned company.

## Why it matters

**We were showing other companies' employee reviews.** All four employer matches in the SOC Automation market were the wrong company, and each was contradicted twice by information we already held:

| We track | We matched | Their industry | Their size | Their actual size |
|---|---|---|---|---|
| Kenzo Security | Kenzo | Clothing & shoe stores | 201–500 | **3 people** |
| Secure.com | SECURE | Energy & utilities | 1001–5000 | **34** |
| Method Security | Method | Business consulting | 201–500 | **26** |
| Artemis Security | Artemis | — | 501–1000 | **55** |

Seven employee reviews had been collected under these and similar matches. One, filed against a six-person security startup, reads "I like being on the move."

Who feels it: anyone reading a company's employee sentiment, and — more seriously — anyone acting on it. An employer rating attributed to the wrong company is not a slightly-off number; it is a statement about a business that has nothing to do with the one on screen.

**The names could not settle it.** Matching was already careful, and already catches cases like "Radiant Security" being offered Radiant Waxing. The rule is that a candidate must be the same name, possibly extended. Every wrong match here was the name *shortened*: "Kenzo" is a subset of "Kenzo Security", so it passed.

That is not simply a stricter-rule problem, because shortening is sometimes right — one customer tracks "Pearsons Education" where the review site calls it "Pearson". Forbidding shortened names would break real matches. Names genuinely cannot separate the two cases.

**Company size can.** We now hold an exact employee count for 80 of the 84 companies in this market — which only became possible with this week's profile collection work. Comparing that against the review site's size band settles it without needing any list of industries or business types to maintain. A three-person company is not the one with 201 to 500 employees.

The tolerance is deliberately wide: those bands are self-reported and often years out of date, and companies grow. It takes a four-fold disagreement to reject a match, which is loose enough to absorb ordinary change and still catch the one-to-two-orders-of-magnitude errors above.

**Where we cannot check, we stay quiet rather than guess.** No employee count on file means the check has no opinion, so this does not switch employer ratings off for companies we have not measured.

## Release notes (copy-ready)

- Employer review matches are now verified against the company's known employee count, and rejected when the two disagree by a wide margin.
- Four incorrect company matches in the SOC Automation market, and the seven employee reviews collected under them, have been removed.
- The verification applies to automatic matches and to manually pinned companies alike.
- Where no employee count is on file, matching behaviour is unchanged.

## Demo / walkthrough

Market Monitor → SOC Automation → any of Kenzo Security, Method Security, Secure.com or Artemis Security. The employer rating and its reviews are gone rather than wrong.

## Positioning notes

Worth stating plainly: we were showing the wrong companies' employee reviews, we found all four, and the fix is a check against a fact we independently measure rather than a cleverer guess at the name.

The related figure also moved. Genuine third-party coverage of this market's 84 companies now reads **4 items** — down from 22, after removing vendors' own blogs this morning and these employer reviews now. That is a small number and it is the true one.

## Limits and what's next

**Four companies still cannot be checked.** They have no employee count on file, so a match for them would be accepted on the name alone as before.

**No employer ratings are shown for this market now.** Every match was wrong, so removing them leaves the section empty. A correct match needs either a company large enough to be unambiguous, or a company ID pinned by hand.

**This has not been copied to the other customer sites yet.** The matching code is shared across Brand Watcher. The check is safe where no employee count exists — it simply stays silent — but it has not been verified against those customers' companies, which are much larger.
