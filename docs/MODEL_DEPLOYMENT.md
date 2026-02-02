# Model Deployment Guide

This document describes the ML model architecture, deployment options, and how the system handles fresh installations.

## Model Overview

AunooAI uses a hybrid approach combining local Small Language Models (SLMs) with LLM fallbacks to minimize costs while maintaining quality.

### Model Categories

| Category | Models | Storage | Source |
|----------|--------|---------|--------|
| **Pretrained** | policy_classifier, policy_llm, summarizer | Ship with release or download | Fixed training data |
| **User-trainable** | enrichment_model, relevance_classifier | Generated per-installation | User's data via ACT |
| **Base models** | DeBERTa, Phi-3, Qwen | Downloaded from HuggingFace | On-demand |

### Model Directory Structure

```
models/
├── policy_classifier/          # Pretrained - policy domain classification
│   └── final/
│       ├── model.safetensors   # ~530MB
│       └── category_mapping.json
│
├── policy_llm/                 # Pretrained - policy-specific LLM adapter
│   └── final/
│       ├── adapter_model.safetensors  # ~840MB (LoRA adapter)
│       └── policy_config.json
│
├── summarizer/                 # Pretrained - article summarization
│   └── final/
│       └── model.safetensors   # ~1.6GB
│
├── enrichment_model/           # User-trainable - classification fields
│   └── final/                  # Created after first training
│       ├── pytorch_model.bin   # ~530MB
│       └── model_config.json
│
└── relevance_classifier/       # User-trainable - relevance scoring
    └── final/                  # Created after first training
        ├── model.safetensors   # ~530MB
        └── model_config.json
```

## Fresh Installation Flow

### Phase 1: No Local Models (Day 1)

On a fresh install, no user-trainable models exist. The system operates in full LLM fallback mode:

```
Article Ingested
├── Summarization    → gpt-4o-mini ($)
├── Category         → gpt-4o-mini ($)
├── Explanations     → gpt-4o-mini ($)
├── Tags             → KeyBERT only (free, no NER)
├── Enrichment       → gpt-4o-mini ($)
│   ├── sentiment
│   ├── time_to_impact
│   ├── driver_type
│   └── future_signal
└── Relevance        → Embedding similarity only (free)

Cost: ~$0.001-0.002 per article
```

### Phase 2: Data Collection (Days 1-14)

As articles are processed, the system automatically collects training samples:

- LLM responses are saved to `enrichment_training_samples` table
- User feedback ("more like this" / "less like this") saved to `user_relevance_feedback` table
- UI shows progress: "Training Progress: 127/500 samples"

### Phase 3: Training Threshold Reached

When a topic accumulates 500+ labeled samples:

1. User clicks "Train Model" in the Training tab (or auto-trigger)
2. Training script downloads base model from HuggingFace:
   ```python
   # ~500MB download, cached to ~/.cache/huggingface/
   model = AutoModel.from_pretrained("microsoft/deberta-base")
   ```
3. Fine-tunes on collected samples (~10-30 minutes on GPU)
4. Saves to `models/enrichment_model/final/`

### Phase 4: Hybrid Mode (Ongoing)

After training, the system uses local models when confident:

```
Article Ingested
├── Summarization    → Phi-3 via vLLM (free) or gpt-4o-mini ($)
├── Category         → Qwen via vLLM (free) or gpt-4o-mini ($)
├── Explanations     → Qwen via vLLM (free) or gpt-4o-mini ($)
├── Tags             → KeyBERT + Phi-3 NER (free)
├── Enrichment       → DeBERTa when confidence ≥ 0.6 (free)
│                    → gpt-4o-mini when confidence < 0.6 ($)
└── Relevance        → DeBERTa + embeddings (free)

Cost: ~$0/article when all local models available and confident
```

## vLLM Dependency

vLLM provides GPU-accelerated inference for Phi-3 and Qwen models.

### With vLLM Installed

```bash
# Start vLLM servers (typically via systemd)
vllm serve microsoft/Phi-3-mini-4k-instruct --port 8765
vllm serve Qwen/Qwen2.5-3B-Instruct --port 8766
```

| Service | Port | Model | Used For |
|---------|------|-------|----------|
| Phi-3 | 8765 | microsoft/Phi-3-mini-4k-instruct | Summarization, Tag refinement + NER |
| Qwen | 8766 | Qwen/Qwen2.5-3B-Instruct | Category classification, Explanations |

### Without vLLM (Fallback Behavior)

| Service | Without vLLM | Cost Impact |
|---------|--------------|-------------|
| Summarization | → gpt-4o-mini | +$0.0003/article |
| Category | → gpt-4o-mini | +$0.0002/article |
| Explanations | → gpt-4o-mini | +$0.0003/article |
| Tags/NER | → KeyBERT only | Free (reduced quality) |
| Enrichment (DeBERTa) | Works (CPU) | Free |
| Relevance (DeBERTa) | Works (CPU) | Free |

**The system is fully functional without vLLM**, just with higher per-article costs until local models are trained.

## Model Training Requirements

### DeBERTa (Enrichment & Relevance)

- **Base model**: `microsoft/deberta-base` (~500MB, downloaded from HuggingFace)
- **Training hardware**: CPU or GPU (GPU recommended, ~10x faster)
- **Training data**: 500+ labeled samples per topic
- **Training time**: ~10-30 minutes (GPU) / ~2-4 hours (CPU)
- **Memory**: ~8GB RAM minimum

### Phi-3 / Qwen (via vLLM)

- **Hardware**: NVIDIA GPU with 8GB+ VRAM
- **Models**: Downloaded automatically by vLLM on first start
- **No training required**: Used for zero-shot inference

## Deployment Options

### Option 1: Full Local (Recommended for Production)

```
Prerequisites:
- NVIDIA GPU (RTX 3080+ or equivalent)
- 16GB+ RAM
- vLLM installed and running

Costs: ~$0/article after initial training period
```

### Option 2: CPU-Only + LLM Fallback

```
Prerequisites:
- 8GB+ RAM
- OpenAI API key

Costs: ~$0.001/article (LLM calls for summarization, category, explanations)
DeBERTa models still run locally on CPU for enrichment/relevance
```

### Option 3: Full LLM (Development/Testing)

```
Prerequisites:
- OpenAI API key

Costs: ~$0.002/article
All processing via gpt-4o-mini
```

## Storage Recommendations

### Git Repository

**Include:**
- All code
- Configuration files
- Database migrations
- Documentation

**Exclude (add to .gitignore):**
```gitignore
# User-trainable models (generated per-installation)
models/enrichment_model/
models/relevance_classifier/

# Experimental/test models
models/comparison_test/

# HuggingFace cache (downloaded on-demand)
.cache/

# Large pretrained models (store separately)
models/summarizer/
models/policy_classifier/
models/policy_llm/
```

### Pretrained Models

Store separately from git:
- **HuggingFace Hub** (private org): Best for sharing across deployments
- **S3/GCS bucket**: Good for cloud deployments
- **Release artifacts**: Attach to GitHub releases

Download script example:
```bash
#!/bin/bash
# scripts/download_pretrained_models.sh

HF_ORG="your-org"
MODELS_DIR="models"

# Download pretrained models from HuggingFace Hub
huggingface-cli download $HF_ORG/policy-classifier --local-dir $MODELS_DIR/policy_classifier/final
huggingface-cli download $HF_ORG/policy-llm --local-dir $MODELS_DIR/policy_llm/final
huggingface-cli download $HF_ORG/summarizer --local-dir $MODELS_DIR/summarizer/final

echo "Pretrained models downloaded successfully"
```

## Monitoring & Verification

### Check Model Status

```bash
# API endpoint
curl -s https://your-domain/api/training/model-config | jq

# Response shows availability and latency for each model
{
  "local_models": [
    {"name": "DeBERTa", "status": "available", "latency": "56ms"},
    {"name": "Phi-3", "status": "available", "latency": "3.2s"},
    {"name": "Qwen", "status": "available", "latency": "4.8s"},
    ...
  ]
}
```

### Check Training Progress

```bash
curl -s https://your-domain/api/training/topics-status | jq
```

### Check Cost Savings

```bash
curl -s https://your-domain/api/training/cost-savings | jq

# Shows local vs LLM usage percentages
{
  "local_percentage": 94.2,
  "savings_percentage": 94.2,
  "method_breakdown": {"hybrid": 450, "llm": 28}
}
```

## Troubleshooting

### "DeBERTa unavailable"

1. Check if model exists: `ls models/enrichment_model/final/`
2. If missing, system uses LLM fallback (working as designed)
3. Train model when 500+ samples collected

### "Phi-3/Qwen unavailable"

1. Check vLLM status: `curl http://localhost:8765/v1/models`
2. If vLLM not running, system falls back to gpt-4o-mini
3. Start vLLM: `sudo systemctl start vllm-phi3`

### High LLM costs

1. Check `/api/training/cost-savings` for breakdown
2. Train local models to reduce LLM usage
3. Install vLLM for free summarization/category/explanations

### Training fails

1. Check sample count: `/api/training/topics-status`
2. Need 500+ samples per topic
3. Check GPU memory if training on GPU
4. Try CPU training with `--device cpu` flag
