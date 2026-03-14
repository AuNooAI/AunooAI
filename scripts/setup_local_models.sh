#!/bin/bash
#
# Setup Local Models Script
#
# Copies trained DeBERTa models to a target tenant directory.
# These models are required for "Local Only" inference mode.
#
# Usage:
#   ./scripts/setup_local_models.sh <target_tenant_path>
#
# Example:
#   ./scripts/setup_local_models.sh /home/orochford/tenants/skunkworkx.aunoo.ai
#
# Models copied:
#   - models/enrichment_model/final     (DeBERTa Enrichment - sentiment, time_to_impact, etc.)
#   - models/relevance_classifier/final (DeBERTa Relevance - article relevance scoring)
#
# Prerequisites (shared system-wide):
#   - vLLM with Phi-3 running on port 8765 (summarization)
#   - vLLM with Qwen running on port 8766 (category classification, local fallback)
#   - sentence-transformers/all-MiniLM-L6-v2 (auto-downloaded on first use)
#
# vLLM Setup (run once per server):
#   # Phi-3 for summarization
#   vllm serve microsoft/Phi-3-mini-4k-instruct --port 8765 --host 127.0.0.1 \
#       --max-model-len 2048 --gpu-memory-utilization 0.48 --enforce-eager
#
#   # Qwen for category/local fallback
#   vllm serve Qwen/Qwen2.5-3B-Instruct --port 8766 --host 127.0.0.1 \
#       --max-model-len 2048 --gpu-memory-utilization 0.45 --enforce-eager
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Source directory (where this script lives)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(dirname "$SCRIPT_DIR")"

# Check arguments
if [ -z "$1" ]; then
    echo -e "${RED}Error: Target tenant path required${NC}"
    echo ""
    echo "Usage: $0 <target_tenant_path>"
    echo ""
    echo "Example:"
    echo "  $0 /home/orochford/tenants/skunkworkx.aunoo.ai"
    exit 1
fi

TARGET_DIR="$1"

# Validate target directory
if [ ! -d "$TARGET_DIR" ]; then
    echo -e "${RED}Error: Target directory does not exist: $TARGET_DIR${NC}"
    exit 1
fi

echo "================================"
echo "  Local Models Setup Script"
echo "================================"
echo ""
echo -e "Source: ${GREEN}$SOURCE_DIR${NC}"
echo -e "Target: ${GREEN}$TARGET_DIR${NC}"
echo ""

# Create models directory if needed
mkdir -p "$TARGET_DIR/models"

# Function to copy model
copy_model() {
    local model_name="$1"
    local src_path="$SOURCE_DIR/models/$model_name"
    local dst_path="$TARGET_DIR/models/$model_name"

    if [ ! -d "$src_path" ]; then
        echo -e "  ${RED}[SKIP]${NC} $model_name - Source not found"
        return 1
    fi

    # Check if final directory exists
    if [ ! -d "$src_path/final" ]; then
        echo -e "  ${YELLOW}[WARN]${NC} $model_name - No 'final' directory (not trained yet)"
        return 1
    fi

    echo -e "  Copying ${BLUE}$model_name${NC}..."

    # Create parent directory
    mkdir -p "$dst_path"

    # Copy final model (the deployed trained model)
    if [ -d "$dst_path/final" ]; then
        rm -rf "$dst_path/final"
    fi
    cp -r "$src_path/final" "$dst_path/final"

    # Copy backup if exists
    if [ -d "$src_path/backup" ]; then
        if [ -d "$dst_path/backup" ]; then
            rm -rf "$dst_path/backup"
        fi
        cp -r "$src_path/backup" "$dst_path/backup"
    fi

    # Get model size
    local size=$(du -sh "$dst_path/final" 2>/dev/null | cut -f1)
    echo -e "    ${GREEN}[OK]${NC} $model_name ($size)"
    return 0
}

echo "Step 1: Copying DeBERTa models..."
echo ""

# Copy each model
MODELS_COPIED=0

copy_model "enrichment_model" && ((MODELS_COPIED++)) || true
copy_model "relevance_classifier" && ((MODELS_COPIED++)) || true

# Optional: Copy policy classifier if exists
if [ -d "$SOURCE_DIR/models/policy_classifier/final" ]; then
    copy_model "policy_classifier" && ((MODELS_COPIED++)) || true
fi

echo ""
echo -e "  ${GREEN}$MODELS_COPIED DeBERTa models copied${NC}"
echo ""

# Check vLLM services
echo "Step 2: Checking vLLM services (shared system-wide)..."
echo ""

check_vllm() {
    local port="$1"
    local name="$2"

    if curl -s --connect-timeout 2 "http://localhost:$port/v1/models" > /dev/null 2>&1; then
        local model=$(curl -s "http://localhost:$port/v1/models" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)
        echo -e "  ${GREEN}[OK]${NC} $name (port $port) - $model"
        return 0
    else
        echo -e "  ${RED}[DOWN]${NC} $name (port $port) - not running"
        return 1
    fi
}

VLLM_OK=0
check_vllm 8765 "Phi-3 (Summarization)" && ((VLLM_OK++)) || true
check_vllm 8766 "Qwen (Category/Fallback)" && ((VLLM_OK++)) || true

echo ""
if [ $VLLM_OK -eq 2 ]; then
    echo -e "  ${GREEN}All vLLM services running${NC}"
else
    echo -e "  ${YELLOW}Warning: $((2-VLLM_OK)) vLLM service(s) not running${NC}"
    echo ""
    echo "  To start vLLM services, run:"
    echo "    # Phi-3"
    echo "    vllm serve microsoft/Phi-3-mini-4k-instruct --port 8765 --host 127.0.0.1 \\"
    echo "        --max-model-len 2048 --gpu-memory-utilization 0.48 --enforce-eager &"
    echo ""
    echo "    # Qwen"
    echo "    vllm serve Qwen/Qwen2.5-3B-Instruct --port 8766 --host 127.0.0.1 \\"
    echo "        --max-model-len 2048 --gpu-memory-utilization 0.45 --enforce-eager &"
fi

echo ""
echo "================================"
echo "  Setup Complete"
echo "================================"
echo ""
echo "Models installed:"
echo "  - DeBERTa Enrichment (sentiment, time_to_impact, driver_type, future_signal)"
echo "  - DeBERTa Relevance (article relevance scoring)"
echo "  - Phi-3 via vLLM (summarization)"
echo "  - Qwen via vLLM (category, local fallback)"
echo "  - KeyBERT/MiniLM (auto-downloaded on first use)"
echo ""
echo "Next steps:"
echo "  1. Restart the target service:"
echo "     sudo systemctl restart $(basename $TARGET_DIR).service"
echo ""
echo "  2. Verify at /gather -> AI Pipeline Mgmt. & Training"
echo "     - Check 'Local models ready' status badge"
echo "     - Try switching to 'Local Only' mode"
echo ""
