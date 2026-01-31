# SLM Training for Article Enrichment

This directory contains trained Small Language Models (SLMs) for article enrichment, replacing/augmenting LLM calls for cost efficiency and lower latency.

## Training Data Statistics

| Dataset | Total | Positive | Negative | Notes |
|---------|-------|----------|----------|-------|
| Relevance | 95,630 | 25,593 curated | 70,037 filtered | Based on future_signal + category presence |
| Summarization | 439 | - | - | Limited raw content available |
| Enrichment | 25,576 | - | - | All curated articles with full enrichment |

**Label Sources**:
- **Curated**: Articles with `future_signal` AND `category` populated (human-approved)
- **Filtered**: Articles without enrichment (failed relevance evaluation)

## Models

### 1. Relevance Classifier (`relevance_classifier/`)
Binary classifier determining if an article is relevant to a topic.

**Architecture**: DeBERTa-base fine-tuned for binary classification
**Input**: `topic [SEP] title. summary`
**Output**: Relevance score (0-1)

**Training**:
```bash
# Export training data first
python scripts/export_training_data.py

# Train the classifier
python scripts/train_relevance_classifier.py --epochs 10
```

**Usage**:
```python
from app.services.relevance_classifier_service import get_relevance_classifier

classifier = get_relevance_classifier()
result = classifier.classify(
    topic="Artificial Intelligence",
    title="OpenAI launches GPT-5",
    summary="OpenAI announced..."
)
# Returns: {"relevant": True, "score": 0.92, "confidence": "high"}
```

### 2. Summarizer (`summarizer/`)
Article summarization using T5-base fine-tuned on LLM-generated summaries.

**Architecture**: T5-base encoder-decoder
**Input**: `summarize: title\n\ncontent`
**Output**: 50-100 word summary

**Training**:
```bash
python scripts/train_summarizer.py --model t5-base --epochs 5
```

**Usage**:
```python
from app.services.summarization_service import get_summarization_service

summarizer = get_summarization_service()
result = summarizer.summarize(
    title="OpenAI launches GPT-5",
    content="Full article content..."
)
# Returns: {"summary": "OpenAI releases...", "source": "local"}
```

### 3. Multi-Task Enrichment (`enrichment_model/`)
Multi-task classifier for sentiment, time_to_impact, driver_type, and future_signal.

**Architecture**: DeBERTa-base with multiple classification heads
**Input**: `title. summary`
**Output**: JSON with predictions for each task

**Training**:
```bash
python scripts/train_enrichment_model.py --tasks sentiment time_to_impact driver_type future_signal
```

**Usage**:
```python
from app.services.enrichment_service import get_enrichment_service

enricher = get_enrichment_service()
result = enricher.enrich(
    title="OpenAI launches GPT-5",
    summary="OpenAI announced..."
)
# Returns: {
#     "sentiment": "Positive",
#     "time_to_impact": "Immediate",
#     "driver_type": "accelerating",
#     "future_signal": "Emerging",
#     "source": "slm"
# }
```

## Training Pipeline

### 1. Export Training Data
```bash
python scripts/export_training_data.py
```

This exports from the database:
- `data/training/relevance_*.json` - Approved/filtered articles
- `data/training/summarization_*.json` - Articles with summaries
- `data/training/enrichment_*.json` - Fully enriched articles
- `data/training/label_mappings.json` - Label vocabularies

**Note**: First ~2000 AI topic articles are human-curated (gold labels).

### 2. Train Models
```bash
# Relevance classifier (fastest)
python scripts/train_relevance_classifier.py

# Summarizer
python scripts/train_summarizer.py

# Multi-task enrichment
python scripts/train_enrichment_model.py
```

### 3. Evaluate
```bash
# Evaluate all models
python scripts/evaluate_slm_pipeline.py --all

# Evaluate specific model
python scripts/evaluate_slm_pipeline.py --relevance --sample-size 500
```

## Model Files Structure

```
models/
├── policy_classifier/          # Existing policy classification
│   ├── final/
│   └── final_roberta_large/
├── relevance_classifier/       # NEW: Topic relevance
│   └── final/
│       ├── config.json
│       ├── model_config.json
│       ├── pytorch_model.bin
│       └── tokenizer files
├── summarizer/                 # NEW: Article summarization
│   └── final/
│       ├── config.json
│       ├── model_config.json
│       ├── pytorch_model.bin
│       └── tokenizer files
└── enrichment_model/           # NEW: Multi-task enrichment
    └── final/
        ├── config.json
        ├── model_config.json
        ├── pytorch_model.bin
        └── tokenizer files
```

## Integration

### Service Layer
New services in `app/services/`:
- `relevance_classifier_service.py` - Relevance scoring
- `summarization_service.py` - Article summarization
- `enrichment_service.py` - Multi-task enrichment (with A/B testing)
- `slm_integration.py` - Unified SLM/LLM hybrid interface

### Quick Integration (Recommended)

Use the unified `SLMIntegration` class for automatic SLM/LLM switching:

```python
from app.services.slm_integration import get_slm_integration

slm = get_slm_integration()

# Score relevance (auto-selects SLM or LLM)
result = slm.score_relevance(topic, title, summary)
# Returns: {'relevance_score': 0.85, 'source': 'slm', ...}

# Enrich article
enrichment = slm.enrich_article(title, summary)
# Returns: {'sentiment': 'Positive', 'source': 'slm', ...}

# Check status
status = slm.get_status()
```

### Environment Variables

Control SLM usage via environment:
```bash
SLM_ENABLED=true              # Master switch for all SLM models
SLM_RELEVANCE_ENABLED=true    # Enable SLM relevance scoring
SLM_ENRICHMENT_ENABLED=true   # Enable SLM enrichment
SLM_SUMMARIZATION_ENABLED=true # Enable SLM summarization
```

### Direct Service Usage

```python
# Option 1: Replace LLM relevance scoring
from app.services.relevance_classifier_service import get_relevance_classifier

classifier = get_relevance_classifier()
if classifier.is_available():
    result = classifier.classify(topic, title, summary)
    topic_alignment_score = result['score']
else:
    # Fallback to LLM
    ...

# Option 2: Use enrichment service with A/B testing
from app.services.enrichment_service import get_enrichment_service

enricher = get_enrichment_service()
enricher.ab_test_enabled = True
enricher.slm_ratio = 0.8  # 80% SLM, 20% LLM

result = enricher.enrich(title, summary)
# Automatically routes to SLM or LLM based on ratio
```

### Automated Ingest Pipeline Integration

In `app/services/automated_ingest_service.py`, replace:

```python
# Before (LLM only):
relevance_result = self.relevance_calculator.analyze_relevance(...)

# After (SLM with LLM fallback):
from app.services.slm_integration import get_slm_integration
slm = get_slm_integration()
relevance_result = slm.score_relevance(topic, title, summary, keywords)
```

## Metrics Targets

| Model | Metric | Target | Notes |
|-------|--------|--------|-------|
| Relevance | F1 | >0.95 | Human-curated AI articles as gold standard |
| Summarization | ROUGE-1 | >0.40 | Distillation from LLM summaries |
| Summarization | BERTScore | >0.85 | Semantic similarity |
| Enrichment | Avg F1 | >0.85 | Per-task weighted F1 |

## Cost Comparison

| Method | Cost per Article | Latency |
|--------|-----------------|---------|
| LLM (gpt-4o-mini) | ~$0.0003 | ~500ms |
| SLM (local) | $0 | ~50ms |

At 10,000 articles/day:
- LLM: ~$3/day, ~$90/month
- SLM: $0 (after training)

## Requirements

```bash
pip install torch transformers datasets accelerate scikit-learn pandas rouge-score bert-score
```

For GPU training (recommended):
- CUDA 11.8+
- 8GB+ VRAM for T5-base
- 16GB+ VRAM for larger models
