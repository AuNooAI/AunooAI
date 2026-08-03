# Quarterly report gate: first live firing, and what it caught
_2026-08-03 · Internal note — no new product surface, not for external distribution_

**Audience note:** this documents an internal validation run and an internal data bug. The
customer-facing capability (the release gate) is described in
`2026-08-03-report-release-gate.md`; nothing here is sendable copy.

## What happened

We ran the real quarterly report pipeline to test the new quality gate under fire. The gate
refused to pass the report — and it was right, twice over:

- The letter scored 4 out of 10 against the customer-approved reference, and even the
  automatic rewrite couldn't lift it. The reason was not the writing: the report's inputs
  dated from May, and no rewrite can add this quarter's events to a letter whose source
  material doesn't contain them. The gate turned "the data underneath is stale" into a
  visible failing score.
- The independent AI reviewer blocked the report separately, catching a recommendation that
  told the customer to "request Wiley admin to supply required context" — internal plumbing
  language produced by a topic whose data feed was silently empty.

## The bug underneath

Chasing that empty topic found a real defect: two topics' scenario-mapping files were stale
(written against older analyses), which made their quarterly assessments complete "successfully"
in a fifth of a second with zero findings. Corrected mapping files had been prepared by an
earlier process and never activated. We activated them, and the assessment pipeline now
refuses to record success when its scenario mapping matches nothing — it falls back and
logs an error instead.

## Why it matters

Before tonight, a stale quarterly bundle would have rendered cleanly and read plausibly, and
the staleness would have been discoverable only by a careful reader comparing dates. Now two
independent gates catch it mechanically, and the failure mode that fed them bad data is
closed.

## Release notes
None — internal validation and internal fix; the customer-facing gate was released earlier
today.

## Positioning notes
None — no new external claim; this is evidence behind the existing "expert oversight,
mechanically enforced" story.

## Limits and what's next

- Outcome, claimed now that it exists: the six assessments completed on fresh data (one
  needed a second run after a database column proved too narrow for the newer scenario
  vocabulary — widened via migration on every site). The regenerated bundle passed: the
  letter scored 4 then 8 after the automatic rewrite, and the reviewer approved with no
  errors. The same letter pipeline that failed on May-vintage data passed on fresh data,
  which is the strongest evidence yet that the gate measures input quality, not just
  wording.
- The reviewer over-flags one mandated section header ("The bottom line.") as a bad opener —
  rubric tuning queued.
- The assessment pipeline's summary field is stored double-encoded (a known trap); untouched
  tonight, still worth normalising eventually.
