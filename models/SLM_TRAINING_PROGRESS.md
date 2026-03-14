# SLM Training Progress

**Last Updated:** 2026-01-31

## Completed

### 1. Relevance Classifier ✅

**Model:** DeBERTa-base
**Location:** `models/relevance_classifier/final/`
**Training Time:** ~2 hours on RTX 4000 SFF Ada

**Test Results:**
| Metric | Value |
|--------|-------|
| Accuracy | 99.31% |
| F1 Score | 98.71% |
| Precision | 99.06% |
| Recall | 98.36% |
| AUC | 99.97% |

**Cross-Topic Validation (Geopolitics):**
- 100% of approved geopolitics articles correctly identified as relevant
- Model generalizes well across topics
- Actually MORE accurate than original LLM scoring on geopolitics articles

**Confusion Matrix (Test Set):**
```
                 Predicted
              Irrelevant  Relevant
Actual Irrelevant    6979        24
       Relevant        42      2518
```

## In Progress

### 2. Summarizer Model 🔄

**Status:** Not started
**Model:** T5-base (planned)
**Location:** `models/summarizer/final/` (when complete)

**To Run:**
```bash
python scripts/train_summarizer.py --epochs 3 --batch-size 4
```

### 3. Multi-Task Enrichment Model 🔄

**Status:** Not started
**Model:** DeBERTa-base with multi-task heads
**Location:** `models/enrichment_model/final/` (when complete)

**To Run:**
```bash
python scripts/train_enrichment_model.py --epochs 3
```

## Training Data

Located in `data/training/`:

| Dataset | Train | Val | Test |
|---------|-------|-----|------|
| Relevance | 76,504 | 9,563 | 9,563 |
| Summarization | 33,219 | 4,152 | 4,153 |
| Enrichment | 26,541 | 3,318 | 3,318 |

## Scripts

| Script | Purpose | Status |
|--------|---------|--------|
| `scripts/export_training_data.py` | Export data from DB | ✅ Complete |
| `scripts/train_relevance_classifier.py` | Train relevance model | ✅ Complete |
| `scripts/train_summarizer.py` | Train summarizer | Ready to run |
| `scripts/train_enrichment_model.py` | Train enrichment model | Ready to run |
| `scripts/evaluate_slm_pipeline.py` | Evaluate all models | Ready to run |

## Services (Integration)

| Service | Purpose | Status |
|---------|---------|--------|
| `app/services/relevance_classifier_service.py` | Inference service | ✅ Created |
| `app/services/summarization_service.py` | Summarizer inference | Pending |
| `app/services/enrichment_service.py` | Enrichment inference | Pending |

## Next Steps

1. Run summarizer training: `python scripts/train_summarizer.py --epochs 3 --batch-size 4`
2. Run enrichment model training: `python scripts/train_enrichment_model.py --epochs 3`
3. Run evaluation: `python scripts/evaluate_slm_pipeline.py --all`
4. Integrate services into `app/services/automated_ingest_service.py`

## Key Findings

1. **Relevance Classifier outperforms LLM** - The distilled model learned better relevance patterns than the teacher LLM, correctly identifying geopolitics articles that the LLM scored too conservatively.

2. **Cross-topic generalization** - Model trained primarily on AI articles generalizes well to Geopolitical Hotspots topic (100% recall on approved articles).

3. **Training considerations** - DeBERTa requires fp32 (not fp16) due to overflow issues.
