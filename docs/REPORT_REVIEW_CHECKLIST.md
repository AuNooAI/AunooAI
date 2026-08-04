# Customer report review checklist

Every check on this list caught (or would have caught) a real defect in the Q3 2026 Wiley
review (see `docs/changes.md`, 2026-08-03). Run it before any customer report ships.

Three layers enforce it:

| Layer | What it covers | Where |
|---|---|---|
| Release lint (deterministic, every build) | figures/orgs vs cited corpus, consensus patterns, internal leaks, dates, rendering | `app/services/report_lint.py`; findings on the period sidecar |
| LLM reviewer (every pipeline run) | grounding, framing, consistency, the judgment calls below | `data/auspex/agents/wiley_reviewer_agent.md` |
| Human (before send) | the last three sections | you |

## Figures
- Every figure appears in a cited source, in the source's unit. Unit traps: lakh/"L" =
  100,000; crore = 10,000,000; headline abbreviations bn/mn/m/k/tn. Never convert a count
  into a rate ("one in forty") unless the source states the rate.
- Contested figures: name both sources or prefer the peer-reviewed one; never present as
  settled.
- No figure that originates in a prompt's worked example — models copy example numbers
  into reports as findings (the 1.4-million failure).

## Names
- Every organisation named appears in a source. Special hazard: the customer's own former
  imprints or subsidiaries listed as third parties (the Hindawi failure).
- No name that originates in instructions or examples (`tests/test_prompt_hygiene.py`
  bans known offenders).

## Consensus and verdicts
- No "% consensus", "% of sources/scenarios", X%→Y% drift deltas, or
  Cooling/Stable/Strengthening vocabulary anywhere. A percentage is allowed only as a
  sourced event magnitude or a point-in-time forecast basis.

## Internal leaks
- No model names, persona settings, or internal field names (`events_by_topic`,
  `raw_output`, "scenario event file"…) in prose.
- Coverage/monitoring slides show only this customer's topics.
- No raw database timestamps; dates are day-precision.

## Cross-artifact consistency
- Deck, HTML and DOCX come from the same pinned analysis runs — the provenance run IDs
  printed on each must be identical.
- The letter's tail-risk statement agrees with the deck's cards: "no new tail-risk
  scenarios" only when the tracked count is truly zero; otherwise name the top card.
- Framing: tracked scenarios are "developing / evolving" — never "missing", "absent" or
  "unconfirmed" events, which reads as a coverage gap rather than the state of the world.
- Serial letters: confirm the prior letter actually resolved (non-empty `prior_letter` in
  the exec payload — check the generation log) and that the letter tracks the prior
  period's claims rather than opening a fresh inventory. For the topic report this fires
  for the first time in Q4 2026 (the hashed-label prior fix landed after Q3 shipped) —
  treat that run as the serial path's first live test and read the letter against Q3's.

## Dates
- No deadline, decision fork or action window in the past. The Three Horizons axis labels
  the current year as "Present".

## Rendering
- No em-dash fallback titles (a renderer reading keys the generator doesn't write —
  `tests/test_report_renderer_contracts.py` guards the shapes).
- Grouped citations ("[44, 52]") split and hyperlinked.
- The reference list is the full cited corpus, not a recency sample.

## Corpus
- No blocked publishers (`REPORT_SOURCE_BLOCKLIST`), no syndicated duplicates,
  relevance-screened (`app/services/report_corpus.py`).
- Spot-check inferences: an article must actually support the claim citing it (the
  Synthesia avatar-funding → fake-reviewer failure).

## Human-only, every time
- Read the letter as the customer would: tone, framing, and what a domain expert will
  push back on (e.g. a figure a peer-reviewed study contradicts, presented as settled).
- Team slide: credentials exactly as the named people state them; plain-noun section
  labels only.
- Disposition every lint finding explicitly: fixed, false positive (then improve the
  lint), or accepted with a written reason.
