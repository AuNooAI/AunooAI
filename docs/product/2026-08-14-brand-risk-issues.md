# Brand risk is now a list of real events, not a score
_2026-08-14 · Brand Watcher dashboard, generated reports, and exports on bugfixing, wileytest, and wbm_

## What shipped
- The 0–100 brand risk score and its Low/Elevated/High labels are gone. In their place,
  the dashboard shows the brand's **active issues**: each adverse event found in
  coverage, classified by type (legal/regulatory, fraud & integrity, data breach,
  product safety, and four more) and severity, with the article count, source count,
  first-seen date, and whether it is spreading, persisting, or fading.
- Coverage volume is reported separately as **attention** — "Product & Innovation
  running at 12.8× this brand's normal weekly volume" — and is explicitly labelled as
  visibility, not risk.
- When the same story also appears in tracked competitors' coverage, the issue is
  marked **sector-wide** and names the peers, so an industry-wide wave is not misread
  as brand-specific trouble.
- Issues expire on their own schedule — a high-severity event stays on the board for
  28 days after coverage stops, a minor one for 7 — and reopen with their history if
  coverage returns. Reports about past periods show the issues that were active then,
  not today's board.
- Strong words ("crisis", "elevated") appear in generated text only when a threshold
  the customer configured in advance has fired, quoted with its triggering numbers.
  Without one, the platform states its classifications as plain facts.

## Why it matters
The old score added up percentages and volume spikes. On the August Wiley report that
produced "Elevated (39/100)" where 30 of the 39 points came from *neutral* coverage —
Wiley publishing more research than usual — while the one article that actually
mattered, a peer-review bribery investigation, moved the number by less than two
points. An analyst reading that page had to reverse-engineer the arithmetic to find
out nothing was wrong.

Risk management rates events, not article counts: one regulatory investigation
outranks eighty neutral mentions, and forty mild complaints never add up to one fraud
case. The new board reads the way an analyst already thinks. The same Wiley month now
shows: high attention (a 12.8× volume spike in product coverage), and — as of
mid-August — no active issues, because the bribery story's coverage ended and the
issue expired. In late July, the same page showed that story as an active,
spreading, medium-severity integrity issue. Both statements are true, dated, and
checkable, which the 39/100 never was.

## Release notes (copy-ready)
- Brand risk is now shown as a list of active issues — concrete adverse events grouped
  from coverage, each with a type, severity, and coverage trail — instead of a
  composite 0–100 score.
- Coverage-volume surges are reported separately as "attention", so busy-but-neutral
  news weeks are no longer labelled as risk.
- Issues that also affect tracked competitors are marked sector-wide.
- Historical reports show the issues that were active in that period.
- Severity language (e.g. "crisis") appears only when a threshold your team defined in
  advance has fired, always with the numbers that triggered it.

## Demo / walkthrough
Brand Watcher → Dashboard: the "Brand Risk Assessment" card now lists active issues
with severity chips, and an "Attention — coverage volume, not risk" strip below.
Brand Watcher → Analysis: the verdict header leads with the issue count and top
severity. The markdown, PDF, and interactive HTML report exports carry the same issue
table. Generated insight reports reference the issues by name.

## Positioning notes
This aligns the product with how corporate risk and comms teams actually work (risk
registers: maximum of active risks, never a sum), and it operationalises the Wiley
feedback that severity judgment belongs to the customer. Against social-listening
competitors whose "risk scores" are volume-weighted sentiment blends, the pitch is
direct: we name the event, they give you a number.

## Limits and what's next
- Issue severity comes from an AI screening step (low/medium/high with a one-sentence
  basis). It is a clinical classification, not a customer-materiality judgment — the
  customer's escalation thresholds supply that layer, and unconfigured brands stay
  purely factual.
- Grouping articles into one event is decided by an AI check for borderline cases.
  Wrong merges or splits can be corrected and the correction sticks, but the analyst
  correction screen is not built yet — corrections are a database write today.
- Live on three sites (bugfixing, wileytest, wbm). The remaining Brand Watcher sites
  still show the old score until they are ported (~1 AI session).
- The planned calibration pass — checking every known past incident lands at a
  defensible type and severity, kept as a regression fixture — still needs
  ground-truth labels from Oliver (~1 session together).
