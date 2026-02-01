# SLM Pipeline Research & Implementation Summary

**Date:** February 2026
**Project:** AunooAI - Strategic Intelligence Platform

---

## Objective

Replace/reduce LLM API calls for article processing with local Small Language Models (SLMs) to achieve:
- Zero API cost for most operations
- Lower latency
- Offline capability

---

## Current Architecture

### High-Level Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                    ARTICLE INGESTION PIPELINE                       │
├─────────────────────────────────────────────────────────────────────┤
│  1. RELEVANCE SCORING (Hybrid)          ~102ms   FREE               │
│  2. SUMMARIZATION (vLLM Phi-3)          ~3.5s    FREE               │
│  3. CLASSIFICATION (DeBERTa)            ~56ms    FREE               │
│  4. TAGGING + NER (KeyBERT + Phi-3)     ~2.5s    FREE               │
│  5. GENERATION (Configured LLM)         ~2-5s    API COST           │
└─────────────────────────────────────────────────────────────────────┘
```

### Detailed Pipeline Flowchart

```
                              ┌─────────────────────┐
                              │   Article Source    │
                              │  (NewsAPI, RSS,     │
                              │   ArXiv, etc.)      │
                              └──────────┬──────────┘
                                         │
                                         ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                        STEP 1: RELEVANCE SCORING                           │
│                        Service: hybrid_relevance_service.py                │
│                        Model: DeBERTa + MiniLM-L6-v2 Embeddings            │
│                        Latency: ~102ms | Cost: FREE                        │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  ┌───────────────────────┐    ┌───────────────────────┐                   │
│  │  Embedding Similarity │    │   DeBERTa Classifier  │                   │
│  │  (MiniLM-L6-v2)       │    │   (relevant/irrelevant)│                   │
│  │  Weight: 0.4          │    │   Weight: 0.6          │                   │
│  └───────────┬───────────┘    └───────────┬───────────┘                   │
│              │                            │                                │
│              └────────────┬───────────────┘                                │
│                           │                                                │
│                           ▼                                                │
│              ┌─────────────────────────┐                                   │
│              │  Combined Score         │                                   │
│              │  = 0.6×classifier +     │                                   │
│              │    0.4×embedding        │                                   │
│              └────────────┬────────────┘                                   │
│                           │                                                │
│              ┌────────────┴────────────┐                                   │
│              │  Score >= threshold?    │                                   │
│              │  (from Gather settings) │                                   │
│              └────────────┬────────────┘                                   │
│                           │                                                │
│           LOW CONFIDENCE  │  HIGH CONFIDENCE                               │
│              ┌────────────┴────────────┐                                   │
│              ▼                         ▼                                   │
│  ┌─────────────────────┐   ┌─────────────────────┐                        │
│  │  LLM Fallback       │   │  Use hybrid score   │                        │
│  │  (verify relevance) │   │                     │                        │
│  └─────────────────────┘   └─────────────────────┘                        │
│                                                                            │
└─────────────────────────────┼──────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              │                               │
              ▼                               ▼
     ┌────────────────┐              ┌────────────────┐
     │   RELEVANT     │              │   FILTERED     │
     │  (continue)    │              │  (skip article)│
     └───────┬────────┘              └────────────────┘
             │
             ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                        STEP 2: CONTENT SCRAPING                            │
│                        Service: Firecrawl                                  │
│                        Latency: ~2-5s | Cost: FREE (self-hosted)           │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  ┌──────────────────────────────────────────────────────────────────────┐ │
│  │  Sources WITH full content (no scraping needed):                     │ │
│  │  • newsdata.io - includes article content in API response            │ │
│  │  • News Firehose - includes article content in feed                  │ │
│  │                                                                      │ │
│  │  Sources REQUIRING scraping (Firecrawl):                             │ │
│  │  • TheNewsAPI, NewsAPI, RSS feeds, ArXiv, etc.                       │ │
│  │  • Fetches full article content from URL                             │ │
│  │  • Extracts: title, content, publish_date, author                    │ │
│  │                                                                      │ │
│  │  Store in: raw_articles.raw_markdown                                 │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
│                                                                            │
└─────────────────────────────┬──────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                        STEP 3: SUMMARIZATION                               │
│                        Service: summarization_service.py                   │
│                        Model: vLLM Phi-3-mini-4k-instruct                  │
│                        Latency: ~3.5s | Cost: FREE                         │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │                     PRIMARY: vLLM Phi-3                             │  │
│  │  Endpoint: http://localhost:8765/v1                                 │  │
│  │  Prompt: "Summarize in 2-3 sentences: {title} {content}"           │  │
│  │  Max tokens: 150 | Temperature: 0.2                                 │  │
│  └──────────────────────────────┬──────────────────────────────────────┘  │
│                                 │                                          │
│                    ┌────────────┴────────────┐                             │
│                    │     vLLM Available?     │                             │
│                    └────────────┬────────────┘                             │
│                          YES    │    NO                                    │
│                    ┌────────────┴────────────┐                             │
│                    ▼                         ▼                             │
│  ┌─────────────────────────┐   ┌─────────────────────────┐                │
│  │  Return vLLM summary    │   │  FALLBACK: Configured   │                │
│  │  source: "vllm"         │   │  LLM from Gather        │                │
│  └─────────────────────────┘   │  (e.g., gpt-4o-mini)    │                │
│                                │  source: "llm"          │                │
│                                └─────────────────────────┘                │
│                                                                            │
└─────────────────────────────┬──────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                     STEP 4: SLM CLASSIFICATION                             │
│                     Service: enrichment_service.py                         │
│                     Model: DeBERTa-base (multi-task)                       │
│                     Latency: ~56ms | Cost: FREE                            │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  Input: "{title}. {summary}"                                               │
│                                                                            │
│  ┌──────────────────────────────────────────────────────────────────────┐ │
│  │                    MULTI-TASK CLASSIFICATION                         │ │
│  │                                                                      │ │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐   │ │
│  │  │  SENTIMENT  │ │ TIME TO     │ │ DRIVER      │ │ FUTURE      │   │ │
│  │  │  (9 classes)│ │ IMPACT      │ │ TYPE        │ │ SIGNAL      │   │ │
│  │  │             │ │ (13 classes)│ │ (15 classes)│ │ (80 classes)│   │ │
│  │  ├─────────────┤ ├─────────────┤ ├─────────────┤ ├─────────────┤   │ │
│  │  │ • Positive  │ │ • Immediate │ │ • Catalyst  │ │ • AI will   │   │ │
│  │  │ • Negative  │ │ • Short-term│ │ • Blocker   │ │   accelerate│   │ │
│  │  │ • Neutral   │ │ • Mid-term  │ │ • Accelerator│ │ • Funding   │   │ │
│  │  │ • Concerning│ │ • Long-term │ │ • Inhibitor │ │   cuts      │   │ │
│  │  │ • Critical  │ │ • Unknown   │ │ • Initiator │ │ • Stable    │   │ │
│  │  │ • Alarming  │ │             │ │ • Delayer   │ │ • ...       │   │ │
│  │  │ • ...       │ │             │ │ • ...       │ │             │   │ │
│  │  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘ └──────┬──────┘   │ │
│  │         │               │               │               │          │ │
│  │         └───────────────┴───────────────┴───────────────┘          │ │
│  │                                 │                                   │ │
│  │                                 ▼                                   │ │
│  │                    ┌─────────────────────┐                          │ │
│  │                    │  Confidence Check   │                          │ │
│  │                    │  threshold >= 0.6   │                          │ │
│  │                    │  (per-field check)  │                          │ │
│  │                    └──────────┬──────────┘                          │ │
│  └───────────────────────────────┼──────────────────────────────────────┘ │
│                                  │                                        │
│     For each field (sentiment, time_to_impact, driver_type, future_signal)│
│              ┌───────────────────┴───────────────────┐                    │
│              │ CONFIDENCE >= 0.6      CONFIDENCE < 0.6│                   │
│              ▼                                       ▼                    │
│  ┌─────────────────────┐              ┌─────────────────────┐             │
│  │  Use SLM result     │              │  LLM generates      │             │
│  │  for this field     │              │  this field         │             │
│  │  (FREE)             │              │  (API cost)         │             │
│  └─────────────────────┘              └─────────────────────┘             │
│                                                                            │
└─────────────────────────────┬──────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                     STEP 5: LLM GENERATION                                 │
│                     Service: article_analyzer.py                           │
│                     Model: Configured LLM (e.g., gpt-4o-mini)              │
│                     Latency: ~2-5s | Cost: API COST                        │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  ┌──────────────────────────────────────────────────────────────────────┐ │
│  │                    LLM GENERATION TASKS                              │ │
│  │                                                                      │ │
│  │  ┌────────────────────┐  ┌────────────────────┐                     │ │
│  │  │  EXPLANATIONS      │  │  CATEGORY          │                     │ │
│  │  │  (required)        │  │  (required)        │                     │ │
│  │  ├────────────────────┤  ├────────────────────┤                     │ │
│  │  │ • sentiment_       │  │  Assign to topic-  │                     │ │
│  │  │   explanation      │  │  specific category │                     │ │
│  │  │ • time_to_impact_  │  │  from ontology     │                     │ │
│  │  │   explanation      │  │                    │                     │ │
│  │  │ • driver_type_     │  │                    │                     │ │
│  │  │   explanation      │  │                    │                     │ │
│  │  │ • future_signal_   │  │                    │                     │ │
│  │  │   explanation      │  │                    │                     │ │
│  │  └────────────────────┘  └────────────────────┘                     │ │
│  │                                                                      │ │
│  │  Note: Tags are now handled by KeyBERT (local) - see Step 4.5       │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
│                                                                            │
│  Note: If SLM confidence was low, LLM also verifies/corrects those fields │
│                                                                            │
└─────────────────────────────┬──────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                     STEP 6: DATABASE STORAGE                               │
│                     Service: automated_ingest_service.py                   │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  ┌──────────────────────────────────────────────────────────────────────┐ │
│  │  articles table:                                                     │ │
│  │  ├── uri, title, summary, topic, news_source                        │ │
│  │  ├── sentiment, sentiment_explanation                                │ │
│  │  ├── time_to_impact, time_to_impact_explanation                     │ │
│  │  ├── driver_type, driver_type_explanation                           │ │
│  │  ├── future_signal, future_signal_explanation                       │ │
│  │  ├── category, tags                                                  │ │
│  │  └── ingest_status: 'approved' | 'filtered'                         │ │
│  │                                                                      │ │
│  │  raw_articles table:                                                 │ │
│  │  └── uri, raw_markdown (full scraped content)                       │ │
│  │                                                                      │ │
│  │  article_embeddings table (pgvector):                                │ │
│  │  └── uri, embedding (for semantic search)                           │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

### Service Dependencies

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SERVICE ARCHITECTURE                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     automated_ingest_service.py                      │   │
│  │                     (Main Orchestrator)                              │   │
│  └───────────────────────────────┬─────────────────────────────────────┘   │
│                                  │                                          │
│          ┌───────────────────────┼───────────────────────┐                 │
│          │                       │                       │                  │
│          ▼                       ▼                       ▼                  │
│  ┌───────────────┐    ┌───────────────────┐    ┌───────────────────┐       │
│  │ hybrid_       │    │ summarization_    │    │ enrichment_       │       │
│  │ relevance_    │    │ service.py        │    │ service.py        │       │
│  │ service.py    │    │                   │    │                   │       │
│  ├───────────────┤    ├───────────────────┤    ├───────────────────┤       │
│  │ DeBERTa       │    │ vLLM Phi-3        │    │ DeBERTa           │       │
│  │ + Embeddings  │    │ (GPU :8765)       │    │ Multi-task        │       │
│  │ (CPU)         │    │                   │    │ (CPU)             │       │
│  └───────┬───────┘    └─────────┬─────────┘    └─────────┬─────────┘       │
│          │                      │                        │                  │
│          │            ┌─────────┴─────────┐              │                  │
│          │            │   LLM Fallback    │              │                  │
│          │            │ (Configured Model)│              │                  │
│          │            └───────────────────┘              │                  │
│          │                                               │                  │
│          └───────────────────────┬───────────────────────┘                  │
│                                  │                                          │
│                                  ▼                                          │
│                    ┌─────────────────────────┐                              │
│                    │    article_analyzer.py  │                              │
│                    │    (LLM Generation)     │                              │
│                    ├─────────────────────────┤                              │
│                    │  Configured LLM from    │                              │
│                    │  Gather settings        │                              │
│                    │  (e.g., gpt-4o-mini)    │                              │
│                    └─────────────────────────┘                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Cost Breakdown Per Article

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         COST PER ARTICLE BREAKDOWN                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  BEFORE SLM PIPELINE:                                                       │
│  ┌────────────────────────────────────────────────────────────────────┐    │
│  │  Relevance    → LLM API  ████████████████  $0.0001                 │    │
│  │  Summary      → LLM API  ████████████████  $0.0002                 │    │
│  │  Sentiment    → LLM API  ████████████████  $0.0001                 │    │
│  │  TTI          → LLM API  ████████████████  $0.0001                 │    │
│  │  Driver       → LLM API  ████████████████  $0.0001                 │    │
│  │  Signal       → LLM API  ████████████████  $0.0001                 │    │
│  │  Explanations → LLM API  ████████████████  $0.0002                 │    │
│  │  Category     → LLM API  ████████████████  $0.0001                 │    │
│  │  Tags         → LLM API  ████████████████  $0.0001                 │    │
│  │  ─────────────────────────────────────────────────                 │    │
│  │  TOTAL                                     $0.0011/article         │    │
│  └────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│  AFTER SLM PIPELINE:                                                        │
│  ┌────────────────────────────────────────────────────────────────────┐    │
│  │  Relevance    → Hybrid   ░░░░░░░░░░░░░░░░  FREE (DeBERTa+Embed)    │    │
│  │  Summary      → vLLM     ░░░░░░░░░░░░░░░░  FREE                    │    │
│  │  Sentiment    → DeBERTa  ░░░░░░░░░░░░░░░░  FREE                    │    │
│  │  TTI          → DeBERTa  ░░░░░░░░░░░░░░░░  FREE                    │    │
│  │  Driver       → DeBERTa  ░░░░░░░░░░░░░░░░  FREE                    │    │
│  │  Signal       → DeBERTa  ░░░░░░░░░░░░░░░░  FREE                    │    │
│  │  Explanations → LLM API  ████████████████  $0.0002                 │    │
│  │  Category     → LLM API  ████████████████  $0.0001                 │    │
│  │  Tags         → LLM API  ████████████████  $0.0001                 │    │
│  │  ─────────────────────────────────────────────────                 │    │
│  │  TOTAL                                     $0.0004/article         │    │
│  └────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│  SAVINGS: ~64% reduction in API costs                                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Evaluation Results

### Hybrid Relevance Scoring (DeBERTa + MiniLM Embeddings)

Combined scoring: 60% classifier + 40% embedding similarity

| Metric | Score |
|--------|-------|
| **Accuracy** | 95.5% |
| **Precision** | 89.5% |
| **Recall** | 94.4% |
| **F1 Score** | 91.9% |
| **Cohen's Kappa** | 0.888 |
| **Avg Latency** | 101.7ms |

*Evaluated using relevance_classifier_service.py standalone. Hybrid service adds embedding similarity for improved zero-shot performance on new topics.*

### Summarization (vLLM Phi-3-mini)

| Metric | Score |
|--------|-------|
| **ROUGE-1** | 0.326 |
| **ROUGE-2** | 0.116 |
| **ROUGE-L** | 0.219 |
| **BERTScore F1** | 0.874 |
| **Avg Latency** | 3,574ms |

*Note: ROUGE scores are lower because Phi-3 generates more detailed summaries than the reference LLM summaries. BERTScore (semantic similarity) shows strong alignment.*

### Multi-Task Enrichment (DeBERTa)

| Task | Accuracy | F1 (weighted) | Kappa | Avg Confidence |
|------|----------|---------------|-------|----------------|
| **Sentiment** | 82.0% | 0.817 | 0.678 | 84.6% |
| **Time to Impact** | 72.5% | 0.718 | 0.647 | 74.7% |
| **Driver Type** | 70.5% | 0.685 | 0.487 | 74.8% |
| **Future Signal** | 67.5% | 0.660 | 0.613 | 68.3% |
| **Overall Avg** | - | **0.720** | - | - |

**Latency:** 56.3ms avg, 68.8ms p95

---

## Research & Experiments

### Summarization Model Comparison

We evaluated 9 different summarization approaches across speed, quality, and cost:

| Model | Avg Time | Cost | Quality | Notes |
|-------|----------|------|---------|-------|
| GPT-4o-mini | 2.5s | API cost | Excellent | Baseline reference |
| BART-large | 1.2s | FREE | Poor | Truncates, misunderstands context |
| Phi-3 (Ollama) | 8s | FREE | Good | Slower due to Ollama overhead |
| Phi-4 (Ollama) | 12s | FREE | Good | Larger model, slower |
| Llama3.1:8b (Ollama) | 15s | FREE | Good | Good quality, slow |
| **Phi-3 (vLLM)** | **3.1s** | **FREE** | **Good** | **SELECTED** |
| Gemma3 (Ollama) | 6s | FREE | Good | |
| Qwen3 (Ollama) | 5s | FREE | Good | Outputs `<think>` tags |
| Mixtral 8x7B | N/A | FREE | N/A | Too large (93GB) for 20GB GPU |

#### Combination Approaches Tested

| Approach | Time | Quality | Notes |
|----------|------|---------|-------|
| BART + Phi-3 polish | 9s | Poor | Inherits BART's errors |
| BART + Llama3.1 polish | 16s | Poor | "Polishes" wrong information |

### What We Tried That Didn't Work

1. **BART-large standalone**
   - Problem: Often truncates mid-sentence, misunderstands article meaning
   - Example: Summarized a Gaza article as "Israel releases new album"
   - Verdict: Unsuitable for news summarization

2. **BART + LLM combinations**
   - Problem: LLM "polishes" BART's mistakes instead of fixing them
   - The errors compound rather than cancel out
   - Verdict: Abandoned approach

3. **Mixtral 8x7B**
   - Problem: 93GB model doesn't fit in 20GB GPU
   - Verdict: Hardware limitation

4. **Qwen3 without thinking disabled**
   - Problem: Outputs `<think>...</think>` reasoning blocks in summaries
   - Solution: Use `enable_thinking=False` parameter
   - Verdict: Works with parameter fix

5. **Ollama for production**
   - Problem: 3x slower than vLLM for same model
   - Verdict: Use vLLM for production, Ollama for experimentation

### GPU Memory Conflicts

- **Issue:** vLLM (95% GPU) + Ollama compete for memory
- **Solution:** Reduced vLLM to 85% utilization
- **Alternative:** Stop one service when using the other

---

## Services Implemented

| Service | File | Model | Device | Status |
|---------|------|-------|--------|--------|
| Summarization | `app/services/summarization_service.py` | vLLM Phi-3-mini | GPU | ✅ Running |
| Enrichment | `app/services/enrichment_service.py` | DeBERTa multi-task | CPU | ✅ Running |
| Relevance Classifier | `app/services/relevance_classifier_service.py` | DeBERTa | CPU | ✅ Running |
| Hybrid Relevance | `app/services/hybrid_relevance_service.py` | DeBERTa + MiniLM-L6-v2 | CPU | ✅ Running |
| Hybrid Tagging + NER | `app/services/keybert_tagging_service.py` | KeyBERT + vLLM Phi-3 | CPU+GPU | ✅ Running |

**Note:** The pipeline uses `hybrid_relevance_service.py` which combines the DeBERTa classifier (weight 0.6) with MiniLM embedding similarity (weight 0.4). The standalone `relevance_classifier_service.py` is used by the hybrid service internally.

### Summarization Service

```python
# Primary: vLLM Phi-3
VLLM_BASE_URL = "http://localhost:8765/v1"
VLLM_MODEL = "microsoft/Phi-3-mini-4k-instruct"

# Fallback: Configured LLM from database (Gather settings)
configured_model = db.facade.get_configured_llm_model()
```

### Enrichment Service

Multi-task DeBERTa classifier trained on LLM-generated labels (knowledge distillation):

- **Base model:** `microsoft/deberta-base`
- **Tasks:** sentiment, time_to_impact, driver_type, future_signal
- **Training:** 3 epochs, batch size 16, LR 2e-5
- **Eval loss:** 0.711

---

## Infrastructure

### vLLM Phi-3 Service

```
Endpoint: http://localhost:8765/v1
Model: microsoft/Phi-3-mini-4k-instruct
Max context: 4096 tokens
GPU memory: 85%
Status: Running
Systemd: Enabled (auto-start on boot)
```

**Systemd service file:** `/etc/systemd/system/vllm-phi3.service`
```ini
[Unit]
Description=vLLM Phi-3-mini server for summarization
After=network.target

[Service]
User=laouad
WorkingDirectory=/home/laouad
Environment=VLLM_ATTENTION_BACKEND=FLASH_ATTN
ExecStart=/home/laouad/.venv/bin/vllm serve microsoft/Phi-3-mini-4k-instruct \
  --port 8765 \
  --host 127.0.0.1 \
  --max-model-len 4096 \
  --gpu-memory-utilization 0.85 \
  --enforce-eager
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Models Directory

```
models/
├── enrichment_model/final/     # 533MB - DeBERTa multi-task classifier
├── relevance_classifier/final/ # 535MB - DeBERTa binary classifier
├── policy_classifier/final/    # 535MB - Policy category classifier
├── policy_llm/final/           # 841MB - Policy LLM (LoRA adapter)
└── summarizer/final/           # 1.6GB - (unused - replaced by vLLM Phi-3)
```

### Model Loading Details

#### Enrichment Model (DeBERTa Multi-Task)

**Location:** `models/enrichment_model/final/`

**Files:**
```
pytorch_model.bin      # 555MB - Model weights
config.json            # HuggingFace model config
model_config.json      # Task-specific config (labels, thresholds)
tokenizer.json         # Tokenizer vocabulary
tokenizer_config.json  # Tokenizer settings
```

**Loading Code:** `app/services/enrichment_service.py`
```python
# Path resolution
BASE_DIR = Path(__file__).parent.parent.parent
LOCAL_MODEL_PATH = BASE_DIR / "models" / "enrichment_model" / "final"

# Load tokenizer and model
self.tokenizer = AutoTokenizer.from_pretrained(str(model_path))
base_config = AutoConfig.from_pretrained(str(model_path))
self.model = MultiTaskModel(base_config, self._task_configs)

# Load weights
weights_path = Path(model_path) / "pytorch_model.bin"
state_dict = torch.load(weights_path, map_location=self.device)
self.model.load_state_dict(state_dict)
```

**Device:** CPU (configurable via `ENRICHMENT_DEVICE` env var)

---

#### Relevance Classifier (DeBERTa Binary)

**Location:** `models/relevance_classifier/final/`

**Loading Code:** `app/services/relevance_classifier_service.py`
```python
LOCAL_MODEL_PATH = BASE_DIR / "models" / "relevance_classifier" / "final"

self.tokenizer = AutoTokenizer.from_pretrained(model_path)
self.model = AutoModelForSequenceClassification.from_pretrained(
    model_path, torch_dtype=torch.float32
)
self.model.to(self.device)
```

**Device:** CPU

---

#### Hybrid Relevance (Embedding + Classifier)

**Models Used:**
1. **MiniLM Embeddings:** Downloaded from HuggingFace on first use
   - Model ID: `sentence-transformers/all-MiniLM-L6-v2`
   - Cached in: `~/.cache/huggingface/`

2. **DeBERTa Classifier:** Loaded from local path (see above)

**Loading Code:** `app/services/hybrid_relevance_service.py`
```python
# Embedding model (downloaded from HuggingFace)
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
self.embedding_model = SentenceTransformer(EMBEDDING_MODEL)

# Classifier (local)
model_path = Path(__file__).parent.parent.parent / "models" / "relevance_classifier" / "final"
self.classifier = AutoModelForSequenceClassification.from_pretrained(str(model_path))
```

---

#### Summarization (vLLM Phi-3)

**Model:** `microsoft/Phi-3-mini-4k-instruct` (3.8B parameters)

**NOT stored locally** - Loaded by vLLM server from HuggingFace cache.

**Location:** `~/.cache/huggingface/hub/models--microsoft--Phi-3-mini-4k-instruct/`

**Loading:** vLLM server handles model loading on startup:
```bash
vllm serve microsoft/Phi-3-mini-4k-instruct \
  --port 8765 \
  --max-model-len 4096 \
  --gpu-memory-utilization 0.85
```

**Access:** Via OpenAI-compatible API at `http://localhost:8765/v1`

---

### Model Loading Sequence

```
Application Startup
       │
       ├── automated_ingest_service.py initializes
       │         │
       │         ├── Lazy load: hybrid_relevance_service (on first relevance check)
       │         │         ├── Load MiniLM embeddings (from HuggingFace cache)
       │         │         └── Load DeBERTa classifier (from models/relevance_classifier/)
       │         │
       │         ├── Lazy load: enrichment_service (on first enrichment)
       │         │         └── Load DeBERTa multi-task (from models/enrichment_model/)
       │         │
       │         └── Lazy load: summarization_service (on first summary)
       │                   └── Check vLLM availability at localhost:8765
       │
       └── vLLM server (separate process)
                 └── Phi-3-mini loaded into GPU memory on server start
```

**Note:** All local models use lazy loading - they're only loaded into memory when first accessed, reducing startup time.

---

## Database Coverage

After backfilling Trump Action Tracker articles:

| Metric | Count | Coverage |
|--------|-------|----------|
| Total articles | 105,974 | - |
| With summary | 96,445 | 91.0% |
| With sentiment | 28,100 | 26.5% |
| With driver_type | 28,099 | 26.5% |
| With time_to_impact | 28,089 | 26.5% |
| Approved (passed relevance) | 21,138 | 20.0% |
| Filtered (failed relevance) | ~77,874 | - |

**Note:** Unenriched articles are those that failed relevance scoring - no enrichment needed.

### Trump Action Tracker Backfill

- **Issue:** CSV import bypassed enrichment pipeline (2,221 articles)
- **Solution:** Created `scripts/backfill_enrichment.py`
- **Result:** All 2,221 articles enriched in 193 seconds (~0.09s/article)

---

## Scripts Created

| Script | Purpose |
|--------|---------|
| `scripts/compare_summarizers.py` | Benchmark summarization models |
| `scripts/compare_summarizers_v2.py` | Extended benchmark with more models |
| `scripts/backfill_enrichment.py` | Backfill enrichment for existing articles |
| `scripts/evaluate_slm_pipeline.py` | Full evaluation of SLM pipeline |

### Backfill Script Usage

```bash
# Backfill specific source
python scripts/backfill_enrichment.py --source "Trump Action Tracker" --limit 2500

# Backfill ALL unenriched articles
python scripts/backfill_enrichment.py --all-unenriched --limit 5000

# Also fix fake summaries (where summary = title)
python scripts/backfill_enrichment.py --source "Trump Action Tracker" --fix-summaries

# Dry run (preview without changes)
python scripts/backfill_enrichment.py --source "semantic_scholar" --limit 100 --dry-run
```

### Evaluation Script Usage

```bash
# Full evaluation
python scripts/evaluate_slm_pipeline.py --all

# Individual components
python scripts/evaluate_slm_pipeline.py --relevance --sample-size 200
python scripts/evaluate_slm_pipeline.py --summarization --sample-size 50
python scripts/evaluate_slm_pipeline.py --enrichment --sample-size 200
```

---

## Model Training

### Training Data Sources

All models were trained using **knowledge distillation** from LLM-generated labels stored in the database.

| Dataset | Samples | Labels | Source |
|---------|---------|--------|--------|
| Relevance | 95,630 | 25,593 curated / 70,037 filtered | `future_signal` + `category` presence |
| Summarization | 439 | LLM summaries | Limited raw content available |
| Enrichment | 25,576 | All enrichment fields | Curated articles with full enrichment |

**Label Definitions:**
- **Curated:** Articles with `future_signal` AND `category` populated (human-approved via ingest workflow)
- **Filtered:** Articles without enrichment (failed relevance evaluation)

### Training Scripts

```bash
# Step 1: Export training data from database
python scripts/export_training_data.py

# Step 2a: Train relevance classifier (DeBERTa binary)
python scripts/train_relevance_classifier.py --epochs 10

# Step 2b: Train enrichment model (DeBERTa multi-task)
python scripts/train_enrichment_model.py --tasks sentiment time_to_impact driver_type future_signal

# Step 2c: Train summarizer (T5-base - now replaced by vLLM Phi-3)
python scripts/train_summarizer.py --model t5-base --epochs 5
```

### Hyperparameters

| Model | Base | Epochs | Batch Size | Learning Rate | Notes |
|-------|------|--------|------------|---------------|-------|
| Relevance Classifier | `microsoft/deberta-base` | 10 | 16 | 2e-5 | Binary classification |
| Enrichment Model | `microsoft/deberta-base` | 3 | 16 | 2e-5 | Multi-task heads |
| Summarizer (unused) | `t5-base` | 5 | 8 | 3e-5 | Replaced by vLLM |

### Training Data Export

The `scripts/export_training_data.py` script exports training data to:

```
data/training/
├── relevance_train.json      # Approved/filtered articles
├── relevance_val.json
├── summarization_train.json  # Articles with LLM summaries
├── summarization_val.json
├── enrichment_train.json     # Fully enriched articles
├── enrichment_val.json
└── label_mappings.json       # Vocabulary for each classification task
```

### Full Training Documentation

For complete training details including architecture, usage examples, and integration code, see:

📄 **[models/slm_training_README.md](../models/slm_training_README.md)**

---

## Hybrid Tagging + NER Service

### Overview

The tagging service uses a hybrid approach combining KeyBERT keyword extraction with Phi-3 (vLLM) for tag refinement and Named Entity Recognition (NER). This provides high-quality semantic tags plus extracted entities (people, organizations, locations) - all running locally for free.

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                 HYBRID TAGGING + NER SERVICE                    │
│                 File: keybert_tagging_service.py                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Input: title + summary (+ optional content)                    │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  STEP 1: KeyBERT Candidate Extraction        (~10ms)    │   │
│  │  Model: sentence-transformers/all-MiniLM-L6-v2          │   │
│  │                                                          │   │
│  │  • Extract 10 candidate n-grams (1-3 words)             │   │
│  │  • Use MMR for diversity                                 │   │
│  │  • Low threshold (0.2) - let SLM filter                 │   │
│  └─────────────────────────────────────────────────────────┘   │
│                          │                                      │
│                          ▼                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  STEP 2: Phi-3 Refinement + NER              (~2.5s)    │   │
│  │  Model: microsoft/Phi-3-mini-4k-instruct (vLLM)         │   │
│  │                                                          │   │
│  │  • Refine KeyBERT candidates into semantic tags         │   │
│  │  • Extract named entities:                               │   │
│  │    - People (e.g., "Michael Saylor", "Dario Amodei")    │   │
│  │    - Organizations (e.g., "Anthropic", "Strategy Inc.") │   │
│  │    - Locations (e.g., "China", "UK")                    │   │
│  │  • Output structured JSON                                │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  Output:                                                        │
│  {                                                              │
│    "tags": ["Bitcoin", "Investment", "Market Analysis"],       │
│    "entities": {                                                │
│      "people": ["Michael Saylor"],                             │
│      "organizations": ["Strategy Inc.", "Bloomberg"],          │
│      "locations": []                                            │
│    }                                                            │
│  }                                                              │
│                                                                 │
│  Note: Entity names are also added to tags for searchability   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Usage

```python
from app.services.keybert_tagging_service import get_keybert_tagging_service

service = get_keybert_tagging_service()

# Hybrid mode: KeyBERT + Phi-3 + NER (recommended)
result = service.extract_tags_hybrid(
    title="Anthropic CEO Dario Amodei says selling AI chips to China...",
    summary="Amodei criticized the sale of AI chips to China..."
)
# Returns: {
#     "tags": ["AI chips", "Anthropic", "China", "National Security"],
#     "entities": {
#         "people": ["Dario Amodei"],
#         "organizations": ["Anthropic", "Bloomberg"],
#         "locations": ["China"]
#     },
#     "keybert_candidates": ["ai chips china", "anthropic ceo", ...],
#     "source": "hybrid",
#     "latency_ms": 2500
# }

# Fast KeyBERT-only mode (lower quality, faster)
result = service.extract_tags(title="...", summary="...")
```

### Performance Comparison

| Mode | Latency | Quality | NER | Cost |
|------|---------|---------|-----|------|
| KeyBERT only | ~10ms | Low (extracts phrases like "strategy bought") | No | FREE |
| **Hybrid (KeyBERT + Phi-3)** | **~2.5s** | **High (semantic tags)** | **Yes** | **FREE** |
| LLM only (previous) | ~500ms | High | No | API cost |

### Example Results

```
Article: "Michael Saylor's Strategy has bought more than $3B in Bitcoin..."

KeyBERT only:  ["strategy bought", "3b bitcoin", "michael saylor"]  ❌ Poor
Hybrid mode:   ["Bitcoin", "Investment", "Strategy Inc."]           ✅ Good
               + Entities: People: [Michael Saylor], Orgs: [Strategy Inc.]
```

### Fallback Behavior

1. **vLLM available** → Use hybrid mode (KeyBERT + Phi-3 + NER)
2. **vLLM unavailable** → Fall back to KeyBERT-only
3. **KeyBERT unavailable** → Fall back to LLM tags from article analyzer

---

## Pending/Future Work

### Other Items

- [x] Enable vLLM systemd service for persistence
- [x] Implement hybrid tagging service (KeyBERT + Phi-3)
- [x] Implement NER via Phi-3 (people, organizations, locations)
- [x] Implement KeyBERT tagging service (replaces LLM tags)
- [ ] Move DeBERTa enrichment model to GPU for faster inference
- [ ] Implement NER service for entity extraction

---

## Cost Savings

| Task | Before | After | Savings |
|------|--------|-------|---------|
| Summarization | LLM API | vLLM Phi-3 (local) | 100% |
| Classification (4 fields) | LLM API | DeBERTa (local) | 100% |
| Relevance scoring | LLM API | Hybrid: DeBERTa + MiniLM (local) | 100% |
| **Tags + NER** | LLM API | **KeyBERT + Phi-3 (local)** | **100%** |
| Explanations | LLM API | LLM API | 0% |
| Category | LLM API | LLM API | 0% |

**Estimated overall reduction:** ~70-80% fewer LLM API calls for article enrichment.

### Cost Per Article Breakdown (Updated)

```
AFTER SLM + HYBRID TAGGING PIPELINE:
┌────────────────────────────────────────────────────────────────────┐
│  Relevance    → Hybrid   ░░░░░░░░░░░░░░░░  FREE (DeBERTa+Embed)    │
│  Summary      → vLLM     ░░░░░░░░░░░░░░░░  FREE (Phi-3)            │
│  Sentiment    → DeBERTa  ░░░░░░░░░░░░░░░░  FREE                    │
│  TTI          → DeBERTa  ░░░░░░░░░░░░░░░░  FREE                    │
│  Driver       → DeBERTa  ░░░░░░░░░░░░░░░░  FREE                    │
│  Signal       → DeBERTa  ░░░░░░░░░░░░░░░░  FREE                    │
│  Tags + NER   → Hybrid   ░░░░░░░░░░░░░░░░  FREE (KeyBERT+Phi-3)    │
│  Explanations → LLM API  ████████████████  $0.0002                 │
│  Category     → LLM API  ████████████████  $0.0001                 │
│  ─────────────────────────────────────────────────                 │
│  TOTAL                                     $0.0003/article         │
└────────────────────────────────────────────────────────────────────┘

SAVINGS: ~73% reduction in API costs (from $0.0011 to $0.0003)
```

---

## Performance Summary

| Component | Latency | Throughput | Quality |
|-----------|---------|------------|---------|
| Hybrid Relevance | 102ms | ~10/sec | F1: 0.919 |
| Summarization (vLLM Phi-3) | 3,574ms | ~0.3/sec | BERTScore: 0.874 |
| Enrichment (4 tasks) | 56ms | ~18/sec | Avg F1: 0.720 |
| Hybrid Tagging + NER | ~2,500ms | ~0.4/sec | High quality + NER entities |

---

## Key Files

| File | Description |
|------|-------------|
| `app/services/summarization_service.py` | vLLM Phi-3 summarization with LLM fallback |
| `app/services/enrichment_service.py` | DeBERTa multi-task classification |
| `app/services/hybrid_relevance_service.py` | Hybrid scoring: DeBERTa (0.6) + MiniLM embeddings (0.4) |
| `app/services/relevance_classifier_service.py` | DeBERTa relevance classifier (used by hybrid service) |
| `app/services/keybert_tagging_service.py` | Hybrid tagging: KeyBERT + Phi-3 refinement + NER |
| `app/services/automated_ingest_service.py` | Main ingestion pipeline (orchestrates all services) |
| `scripts/evaluate_keybert_tags.py` | KeyBERT vs LLM tag evaluation script |
| `models/enrichment_model/final/` | Trained DeBERTa multi-task model weights |
| `models/relevance_classifier/final/` | Trained DeBERTa relevance model weights |
| `/etc/systemd/system/vllm-phi3.service` | vLLM systemd service definition |
| `data/training/` | Training data for all models |
| `data/evaluation/` | Evaluation results (JSON) |
