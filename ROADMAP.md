# Roadmap

Forward-looking work. Ordered by priority, not by dependency.

## Immediate (this week)

### Unblock retrieval quality
- [ ] **OpenAI embedding quota exhausted on bugfixing.** Vector search is
      falling back to random 1536-d vectors; every semantic path produces
      garbage before reranking. Top up the account or switch embeddings to
      a local provider. Reranker masks the impact but doesn't fix it.

### Validate reranker in production
- [ ] Exercise Auspex and `/anticipate` with `RERANK_ENABLED=true` and
      monitor retrieval latency (expect +30–100ms per call on CPU with
      BGE-v2-m3).
- [ ] Confirm `rerank_score` appears in Auspex citation payloads.
- [ ] Watch the first few Trend Convergence / Market Signals runs for
      qualitative shift in the LLM input.

## Short-term (next 1–2 weeks)

### Grow labeled feedback, then enable the CE tier
- [ ] Surface `ce_score` in the Data Quality Audit UI so reviewers can flag
      CE/LLM disagreements. Targets a growing `user_relevance_feedback`
      corpus (currently 12 labels — too sparse for stable thresholds).
- [ ] Re-run `scripts/evaluate_ce_vs_llm_fallback.py` once the corpus
      passes ~50 labels.
- [ ] If 85%-confident tails cover ≥25% of borderline cases at ≥85%
      accuracy, enable `RELEVANCE_USE_CE_TIER=true` in staging. The
      current 44% LLM-fallback rate could drop toward 20–25%.

### Multi-tenant deploy
- [ ] After bugfixing validates (1+ week live), copy backend files to
      `wiley.aunoo.ai` and `wileytest.aunoo.ai` and restart their
      systemd services. Sentence-transformers is already installed on all
      three. `.env` additions: `RERANK_ENABLED=true`.

## Medium-term (this month)

### Emerging Topics theme assignment — cross-encoder replacement
- [ ] Replace the 0.85 vector-distance threshold + AI validation sweep in
      `app/services/emerging_topics/emerging_topics_service.py:308` with
      cross-encoder theme-assignment scoring. Higher-value than the
      retrieval reranker but structurally larger — needs its own plan
      and backtest before shipping.

### Reranker model evaluation
- [ ] Benchmark `mixedbread-ai/mxbai-rerank-large-v2` against BGE-v2-m3 on
      a larger eval set (expect modest quality lift at ~3× compute).
- [ ] Consider a two-stage rerank when the candidate pool grows: cheap
      first-pass filter (`qnli-electra-base`) → BGE/mxbai on the
      survivors. Only worth it if retrieval latency becomes a complaint.

### Observability
- [ ] Dashboard card on Operations HQ showing rerank usage per endpoint,
      median rerank_score, and time spent in CE inference.
- [ ] Histogram of `ce_score` vs `classifier_score` on the training UI so
      model disagreements are visible.

## Deferred / investigative

### Fine-tune a domain-specific reranker
- Once `user_relevance_feedback` passes 500 labeled pairs, train a DeBERTa
  cross-encoder on the exact `(topic, title+summary)` distribution we care
  about. Training infra already exists for the relevance classifier.

### Retire MS-MARCO references
- Clean up the legacy reference to `ms-marco-MiniLM` in reranker comments
  once BGE-v2-m3 has been the default for a quarter without incident.

## Recently shipped (see CHANGELOG.md)
- Cross-encoder reranker for Auspex, `/anticipate`, and HybridRelevanceService
- Eval harness (`scripts/evaluate_ce_vs_llm_fallback.py`)
- Default model: `BAAI/bge-reranker-v2-m3`
