# Customer-defined escalation tiers

_2026-08-13 · Spec for sign-off, then v1 build. Origin: Pascal Hetzscholdt (Wiley), 12 Aug —
"unless a customer has told you that x posts = crisis or y statement = crisis, I would
recommend to be factual in a clinical way until instructed otherwise."_

## Problem

The clinical-register change (2026-08-13) stopped generated prose from calling routine
adverse coverage a "crisis" on the model's own judgment. That fixed the false-alarm
problem but removed the platform's only way of saying the word at all. Real escalations
(Pascal's examples: SOPA-PIPA, the Sony hack) deserve strong language — but the judgment
of what earns it belongs to the customer.

## Principle

Severity language in the platform's own voice comes only from a threshold the customer
defined in advance, with the label the customer chose, and every use cites the numbers
that triggered it. The LLM never decides a tier — a deterministic evaluator does, and the
model is only allowed to repeat its output. Unconfigured brands stay purely clinical, so
the default is exactly today's behavior.

## Configuration (v1: JSON on the brand, no UI)

`bw_brands.config['escalation_tiers']` — an ordered list, most severe last. Example:

```json
"escalation_tiers": [
  {"label": "elevated",
   "rules": {"volume_multiple": 3.0, "min_days": 2}},
  {"label": "crisis",
   "rules": {"volume_multiple": 10.0, "min_days": 2,
              "net_sentiment_below": -30, "requires_high_risk": true}}
]
```

Rules inside a tier are ANDed. The highest (last-listed) tier whose rules all pass is the
brand's current status; if none pass, the brand has no status and nothing changes
anywhere. Rule vocabulary, v1 — each reuses a metric the platform already computes:

| Rule | Meaning | Reuses |
|---|---|---|
| `volume_multiple` | mean daily on-brand article count over the last `min_days` days is ≥ N× the baseline (mean daily count over the prior 28 days, excluding the window) | brand volume queries (`bw_article_categories` join, `submission_date`) as in `timeline_events.py` |
| `min_days` | evaluation window length in days (default 2) — spikes must be sustained | — |
| `net_sentiment_below` | net sentiment over the window is ≤ N, where net = (positive − negative) / scored × 100, at least 3 scored articles | `bw_digest_service._POS/_NEG` definitions, same formula the digest emails show |
| `requires_high_risk` | at least one `bw_article_risks` row with severity 'high' detected inside the window | adverse-screening risk findings |

Labels are free text chosen by the customer ("elevated", "crisis", "code red"). Event-class
triggers ("no more funding for universities") are out of scope for v1 — the analyst-note
path covers them: a permanent timeline memento recording a human designation already flows
into every summary and is attributable prose.

## Evaluator

New `app/services/escalation_tiers.py`:

```
evaluate_brand_tier(conn, brand_id) -> Optional[dict]
# {"label": "crisis",
#   "triggered": ["coverage 8.2x baseline over 2 days (33/day vs 4.0/day)",
#                 "net sentiment -38 (>= 3 scored)",
#                 "1 high-severity risk finding (legal_regulatory)"],
#   "window_days": 2}
```

Pure SQL + arithmetic, no LLM. Returns None when the brand has no tiers configured or no
tier fires. Called at read/compose time — no state is stored, no schema change; a tier is
a fact about the current window, recomputed when needed.

## Where the status surfaces (v1)

1. **Prompt injection + style rule.** Wherever a brand's status fires, the composing code
   adds `CUSTOMER-DEFINED STATUS: "crisis" — triggered by: <the triggered list>` to the
   prompt input, and `CLINICAL_STYLE` gains one rule: if a customer-defined status is
   present in the input, state it using its exact label and cite the numbers that
   triggered it; never upgrade, downgrade, or invent a status that is not in the input.
2. **Adverse-media digest** (`bw_digest_service`): status line in the per-brand facts
   (so the prose lead may name it) and a badge in the brand's HTML card.
3. **Timeline state doc** (`timeline_rollup.refresh_state_doc`, brand scopes): status
   line injected into the prompt so the "State of X" paragraph opens with the customer's
   designation when one is active.
4. **Timeline tab chip** (`TimelineTab.tsx`): the summary API
   (`timeline_routes` summary endpoint) returns `escalation_tier` alongside the state
   doc; the UI renders a red badge with the customer's label next to the trend chip.
5. **Signal reports**: inherit it for free — they already receive the state-doc text via
   `build_timeline_context`, and the state doc now carries the designation.

## Explicitly not in v1

- No config UI (JSON on the brand via SQL/API; an editor is phase 2 if customers want
  self-service). No new pages, no new columns, no migrations.
- No tier-transition alerts/emails (phase 2 — "brand entered 'crisis'" is a natural
  `bw_alert_events` rule later).
- No topic-scoped tiers (brand scope only, where the adverse-media use case lives).
- No model involvement in evaluation.

## Acceptance checks

- Brand with no tiers: zero behavioral change on every surface (diff the digest facts and
  state-doc prompt before/after — identical).
- Test tier on a dev brand with thresholds set low enough to fire: digest facts carry the
  status line, digest lead names the label with numbers, state doc opens with it, summary
  API returns it, chip badge renders, and a signal report generated for a topic whose
  timeline includes that brand's state doc repeats the label with its trigger numbers.
- Set thresholds so none fire: all surfaces silent again.
- The label is echoed verbatim (a customer label like "code red" must not be normalized).

## Effort

Build + verify + all-tenant deploy: roughly 2 hours of AI work.
