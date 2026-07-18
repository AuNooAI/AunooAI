# Relevance thresholds — tuning notes

Per-group relevance cutoff lives in `keyword_groups.min_relevance_threshold`
(tunable in the /gather group settings). The recurring test in this directory
(`run.py --golden`) checks the pipeline's keep/drop decision at each topic's real
threshold — `build_fixtures.py` resolves that per-group value automatically.

## How to pick a brand threshold (data-driven)

Score a sample of recent brand articles through `hybrid_relevance_service`
(embedding + classifier + nova-lite LLM fallback) and look at the split:

- **Relevant** brand/industry coverage scores **≥ 0.40**
  (e.g. "Book Publishers Sue Google Over AI Training" → 0.50).
- **Noise** — surname/word collisions ("Springer" the surname, mining/asteroid/
  quantum papers that merely contain the word) — scores **≤ 0.20**.
- There is a **clean gap between 0.20 and 0.40**, so **0.3** cleanly separates:
  cuts all observed noise, keeps all relevant, no recall loss.

## Change log

- **2026-07-18 — wbm**: brand-watch groups were inconsistent (Wiley 0.4,
  Elsevier/Pearson 0.2, SAGE 0.45, Springer unset → global 0.5). Set **all five to
  0.3** (`UPDATE keyword_groups SET min_relevance_threshold=0.3 WHERE name LIKE
  '%- Brand Watch'`). Read live per collection run — no restart. Golden-test
  precision **62% → 100%**, recall held **100%**. (wbm is not a git repo; this note
  is the record. Other tenants keep their own per-group thresholds.)
