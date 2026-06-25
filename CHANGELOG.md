# Changelog

Notable changes to AunooAI (bugfixing tenant). Loosely follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added — 2026-05-24

- **Wiley trend-discovery → topic-promotion pipeline.** A weekly
  background job runs the emerging-themes detector over the corpus,
  judges every new cluster against the Wiley organisational profile
  (`organizational_profiles`), and lands in-scope candidates in a new
  `topic_candidates` inbox. Off-scope candidates are auto-rejected.
  Analysts triage from a Candidates pill on the Topics dashboard —
  **Promote** kicks off Three Horizons + paired assessment + draft
  overlay, then drops the analyst into the wizard at the overlay-review
  step. Snooze / Reject / Merge are first-class. New files:
  `app/services/wiley_candidate_pipeline.py`,
  `app/tasks/wiley_candidate_scheduler.py`,
  `app/routes/wiley_candidates_routes.py`,
  `data/auspex/agents/wiley_relevance_judge.md`,
  `ui/src/components/CandidatesInbox.tsx`. Migration `fa_007` adds the
  `topic_candidates` table + `source_candidate_id` lineage column on
  `forecast_topic_metadata`. Gated by `WILEY_CANDIDATE_SCAN_ENABLED`
  (default on). [`fa_007`]
- **Topics dashboard + Add-topic wizard.** Single source of truth for
  what topics are tracked: one row per topic with health dot, owner,
  tags, last assessed, cadence, last delivered, overlay status, and
  status (`draft` / `active` / `archived`). The "+ Add topic" CTA opens
  a five-step wizard (name & framing → Three Horizons → first
  assessment → overlay review → delivery cadence) that's resumable via
  `localStorage`. The reviewer agent now warns when a topic with a
  missing overlay is included in a bundle. New files:
  `ui/src/components/TopicsDashboard.tsx`,
  `ui/src/components/AddTopicWizard.tsx`,
  `app/services/wiley_overlay_generator.py`,
  `data/auspex/agents/wiley_overlay_agent.md`. Migration `fa_006` adds
  the `forecast_topic_metadata` sidecar table.
- **Wiley multi-agent supervisor + bundle review.** Quarterly deck
  generation now runs through a supervisor that orchestrates
  briefing / recommendations / next steps / cross-cutting themes /
  executive-summary / surprises stages, with a separate
  `wiley_reviewer_agent` (LLM-as-judge) auditing every artefact
  against an explicit rubric before the deck ships. Reviewer findings
  are persisted in `forecast_bundle_review` and surfaced in the
  Deliverables panel. Migration `fa_005`.
- **LLM-named emerging-theme clusters.** Replaces the previous
  keyword-salad labels (`"ukraine, drug, generic"`) with Title Case
  names from `forecast_cluster_label_agent`. The same agent decides
  whether each cluster is genuinely topic-relevant; off-topic clusters
  are dropped and off-topic articles inside otherwise-relevant clusters
  are pruned. Reviewer's rubric extended to flag keyword-salad labels
  as `error` so any future regression gates the deck.
- **Markdown bundle export.** `wiley_delivery_service.generate_bundle_markdown`
  produces the same content as the PPTX path through a shared synthesis
  pipeline. Download button alongside "Download .pptx" in the
  Deliverables panel. Endpoint:
  `GET /api/forecast/deliverables/bundle.md`.
- **Headline Findings full-mode counts** in the bundle's opening slide
  now distinguish updates-only (status changes vs prior snapshot) from
  full review (off-baseline + inconclusive + total articles).
- **Strategic Domains card "no attribution" handling** — when zero
  articles support or contradict every scenario for a topic, the
  Strategic Domains slide drops the misleading "0% current consensus"
  chip and shows a "no attribution this window" note instead.

### Added
- **Cross-encoder reranker** (`app/retrieval/reranker.py`) — overfetch + rerank
  now runs on Auspex vector search, `/anticipate` Trend Convergence, and
  Market Signals. Default model `BAAI/bge-reranker-v2-m3` (multilingual,
  8K context, Apache 2.0). Enabled via `RERANK_ENABLED=true` on bugfixing.
  [`0d8e13df`, `6cc0c568`]
- **Cross-encoder tier in `HybridRelevanceService`** — optional intermediate
  between the hybrid classifier+embedding and the LLM fallback. Gated by
  `RELEVANCE_USE_CE_TIER` (currently off). `ce_score` column added to
  `relevance_confidence_readings` via Alembic migration `ce_001`.
  [`6cc0c568`]
- **Reranker eval harness** (`scripts/evaluate_ce_vs_llm_fallback.py`) —
  backtests a CE model against `user_relevance_feedback` labels and
  reports best-threshold accuracy, F1, and 85%-confident tails. Used to
  pick BGE-v2-m3 over ms-marco-MiniLM (83% vs 58% accuracy on n=12).
  [`0d8e13df`]

### Changed
- Trend Convergence (`/anticipate`) reranks the filtered article pool
  against a trend-framing query before heuristic weighting.
- Market Signals reranks the fetched pool before the 50-article
  token-budget truncation.
- Auspex `_direct_vector_search`, `_vector_search_topic`, and
  `enhanced_database_search` now overfetch (5× the requested `top_k`, capped
  at 200) and rerank back to `top_k`. The post-expansion merge in
  `_smart_vector_search` prefers `rerank_score` over cosine when present.
- `RERANK_MAX_TEXT_LEN` default bumped 1000 → 4000 chars so BGE's 8K-token
  window sees paragraph-level topical signal, not just headlines.

## 2026-04-17

### Fixed
- **Relevance pipeline — widen LLM fallback window** (`2403fb64`): bimodal
  classifier output (0.04 or 0.94) was landing outside the previous
  0.35/0.65 uncertainty band, making LLM fallback dead code. Window widened
  to 0.20/0.85. Topics like "Geopolitical Hotspots" were scoring 0–40%
  relevance quality; post-fix target is 60%.
- **Classifier/embedding disagreement** (`6cb1d803`): untrained-topic
  articles with high embedding (0.8+) but near-zero classifier score were
  being vetoed. Now detects a 0.35+ delta and forces LLM arbitration.
  Entity prefixes stripped before keyword collection.

### Added
- Data Quality Audit UI — per-topic pass rates with a 60% alert threshold.
- Nightly quality report (`scripts/nightly_quality_report.py`) samples the
  last 24h of approved articles and verifies via an independent LLM call.

## 2026-04-16 and earlier

- **Brand Intelligence Report** (`fcb5ad80`) — synthesized risk assessment
  with linked sources and export.
- **vLLM port fixes** (`ec0ab802`, `06fe24c3`) — standardized on 8765 and
  replaced hardcoded ports with `VLLM_BASE_URL` / `VLLM_PORT`.
- **Threat Intelligence module** (`aa589980`) — actor tracking, IOC
  management, campaign analysis.
- **Firecrawl billing incident fixes** (`068a4be0`, `a45c795a`,
  `33aa570d`) — stopped ~93k scrapes/day on opendemo; articles with
  collector content now skip Firecrawl. See
  `docs/FIRECRAWL_BILLING_INCIDENT_REPORT.md`.
- **Emerging topics auto-retirement fix** (`a6452929`) — SQL precedence bug
  was mass-retiring emerging topics.
