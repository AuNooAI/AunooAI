# Daily briefings now say whether an earnings figure is adjusted or GAAP
_2026-09-04 · Briefing Desk (daily briefing synthesis and incident detection)_

## What shipped
- Daily briefings state whether an earnings figure is GAAP or adjusted, and report a GAAP loss even when the adjusted number looks good.
- When the sources in a briefing disagree (one headline says "beat", another says "miss"), the briefing says so and gives both readings instead of silently picking one.
- The words "beat", "miss" and "momentum" only appear when the source material states what the figure is being compared against.
- The incident detector applies the same rules, and marks auto-generated earnings wire stories as a single thin source rather than independent confirmation.

## Why it matters
Before: the 4 September briefing for a publishing customer opened with "Wiley beat Q1 2027 earnings expectations with EPS of $0.44 versus $0.40 consensus" and called it "earnings momentum". Wiley had in fact reported a GAAP loss of $0.23 per share. The $0.44 was adjusted EPS, and it was down 10% on the prior year. An analyst forwarding that paragraph would have been wrong in front of their board.

Now: the same briefing, regenerated with the new rules from the same articles, opens with "Wiley reported adjusted EPS of $0.44, exceeding the $0.40 consensus estimate, while carrying a GAAP net loss of $11.7 million due to restructuring and Emerald acquisition costs". The incident behind it is now titled "adjusted EPS $0.44 beats estimates; GAAP loss $11.7M" and carries a "conflicting reports" flag.

Who feels it: anyone who reads or forwards a daily briefing. The rules apply to every briefing, not only earnings stories, because the same discipline (name the basis, name the disagreement) matters for any number.

## Release notes (copy-ready)
- Daily briefings now distinguish GAAP from adjusted earnings and always report a GAAP loss when the source has one.
- When sources disagree on a fact, the briefing names the disagreement instead of choosing one side.
- "Beat" and "miss" language is only used when the comparison basis is stated in the source.

## Demo / walkthrough
Briefing Desk, open "Daily Briefing — 2026-09-04" on the wileytest site. The first sentence of the synthesis and the first incident card show the corrected wording. Any briefing finalized from now on uses the new rules.

## Positioning notes
None. This closes a correctness gap rather than adding a capability; the story is "the briefing does not overstate results", which is a trust point in a demo, not a feature bullet.

## Limits and what's next
- The briefing can only be as accurate as the article summaries we store. The summaries for all seven Wiley articles omitted both the word "adjusted" and the loss. The fix makes the model refuse to call a result a beat without a stated basis, but it cannot recover a fact the summary dropped. Making the summariser keep financial qualifiers is the obvious follow-on.
- The rules were only tested on this one briefing and this one model (Claude Haiku on Bedrock). Other briefings finalized today were not regenerated.
- Existing finalized briefings keep their old text. Only briefing 143 was regenerated.
