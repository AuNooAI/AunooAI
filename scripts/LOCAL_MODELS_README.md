# Local Models Package

This package contains trained DeBERTa models and setup scripts for running AunooAI in local/hybrid inference mode.

## Contents

```
local-models-package.tar.gz
├── models/
│   ├── enrichment_model/final/      # DeBERTa for sentiment, time_to_impact, driver_type, future_signal
│   └── relevance_classifier/final/  # DeBERTa for article relevance scoring
└── scripts/
    ├── LOCAL_MODELS_README.md       # This file
    ├── install_local_models.sh      # Extract this package
    ├── install_ml_deps_cpu.sh       # Install ML dependencies (CPU-only PyTorch)
    ├── setup_vllm_gpu.sh            # Check GPU & setup vLLM (Phi-3 + Qwen)
    ├── setup_local_models.sh        # Copy models from another tenant
    └── backfill_training_samples.py # Convert existing articles to training samples
```

## Quick Start

### 1. Extract Package

```bash
cd /path/to/tenant
tar -xzf local-models-package.tar.gz
# Or use the script:
./scripts/install_local_models.sh
```

### 2. Install ML Dependencies

**For CPU-only servers (no GPU):**
```bash
./scripts/install_ml_deps_cpu.sh
```

**For GPU servers:**
```bash
source .venv/bin/activate
pip install datasets transformers torch sentence-transformers accelerate safetensors
```

### 3. Backfill Training Samples (Optional)

Convert existing enriched articles into training samples:

```bash
source .venv/bin/activate
python scripts/backfill_training_samples.py
```

Options:
- `--limit N` - Process only N articles
- `--topic "Topic Name"` - Process only specific topic

### 4. Restart Service

```bash
sudo systemctl restart <tenant>.service
```

## Inference Modes

Set via UI at `/gather` → AI Pipeline Mgmt. & Training:

| Mode | DeBERTa | LLM Fallback | Best For |
|------|---------|--------------|----------|
| **Local** | ✅ | Qwen (vLLM) | GPU servers with vLLM |
| **Hybrid** | ✅ | GPT | CPU servers, cost optimization |
| **External** | ❌ | GPT only | No local models |

## Server Requirements

### GPU Server (Local Mode)
- NVIDIA GPU with 8GB+ VRAM
- vLLM running Phi-3 (port 8765) and Qwen (port 8766)
- ~2GB disk for models

### CPU Server (Hybrid Mode)
- 16GB+ RAM recommended (256GB ideal)
- ~2GB disk for models
- CPU-only PyTorch (~200MB)

## vLLM Setup (GPU Server Only)

**Automatic setup (recommended):**
```bash
./scripts/setup_vllm_gpu.sh
```

This script will:
1. Check for NVIDIA GPU
2. Install vLLM if needed
3. Start Phi-3 and Qwen services
4. Verify everything is running

**Script options:**
```bash
./scripts/setup_vllm_gpu.sh --status   # Check GPU and vLLM status
./scripts/setup_vllm_gpu.sh --start    # Start vLLM services
./scripts/setup_vllm_gpu.sh --stop     # Stop vLLM services
./scripts/setup_vllm_gpu.sh --install  # Install vLLM only
```

**Manual setup:**
```bash
# Phi-3 for summarization
vllm serve microsoft/Phi-3-mini-4k-instruct --port 8765 --host 127.0.0.1 \
    --max-model-len 2048 --gpu-memory-utilization 0.48 --enforce-eager &

# Qwen for category/local fallback
vllm serve Qwen/Qwen2.5-3B-Instruct --port 8766 --host 127.0.0.1 \
    --max-model-len 2048 --gpu-memory-utilization 0.45 --enforce-eager &
```

## Troubleshooting

### "No module named 'datasets'"
Run: `./scripts/install_ml_deps_cpu.sh`

### "DeBERTa model not found"
Check models exist: `ls models/enrichment_model/final/config.json`

### Low DeBERTa confidence (falling back to LLM)
- Need 500+ training samples per topic for good accuracy
- Run backfill script to populate samples
- Check sample counts at `/gather` → Training tab

### "Local models unavailable" in UI
- Verify models extracted correctly
- Check inference mode is set to `local` or `hybrid`
- Restart service after extracting models

## Model Details

| Model | Size | Task |
|-------|------|------|
| enrichment_model | ~500MB | Classify sentiment, time_to_impact, driver_type, future_signal |
| relevance_classifier | ~500MB | Score article relevance (0-1) |

Both models are fine-tuned DeBERTa-v3-base on your article data.

## Training Thresholds

- **< 500 samples**: Uses LLM (GPT/Qwen) + stores for training
- **≥ 500 samples**: Uses DeBERTa (fast, free, local)

Check training readiness at `/gather` → AI Pipeline Mgmt. & Training
