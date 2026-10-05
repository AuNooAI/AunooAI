# Blind labels for the TypeSafe Jev shadow disagreements (2026-09-19)

One JSONL file per shadow. Each line is one row from the shadow table: the item as the labeller saw it
(`item`), what the pipeline and Jev said (`key`), and the blind label (`label`, with a one-line rationale).

The labels were produced by Claude (Fable 5.1) agents that saw only the item and the question, never the
pipeline's or Jev's answer. They are a third opinion, not ground truth. The honeypot gold set in
`eval/honeypot_tactics/` remains the only human-labelled set.

Sampling: every disagreement row where the item could be reconstructed, capped at about 50 per shadow
(reception stratified across its three sites; honeypot 34 disagreements plus 16 blind controls where both
sides agreed; relevance limited to the 28 rows that join back to exactly one article, since
`relevance_confidence_readings` stores no article reference). Re-create with the scratchpad scripts noted in
docs/changes.md.

## Consistency (2026-09-20)

`consistency.json`: every labelled row re-judged five times through the shadow's own judge function
(1,600 calls in all, no errors). Per set: items, runs, how many rows got the same label on all five runs, and
the rows that did not, with the decision probability from each run. Across all 320 rows the label was
unanimous on 302; the mean variance of the decision probability was 0.0003 (median standard deviation 0.009,
under one percentage point). Every non-unanimous row sat within a few points of the 0.5 boundary. Runner:
scratchpad `ts/labels/consistency_{common,mono,saas}.py`.
