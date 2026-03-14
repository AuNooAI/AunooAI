#!/bin/bash
#
# Setup vLLM on GPU Server
#
# Checks for NVIDIA GPU and sets up vLLM with Phi-3 and Qwen models.
# These models provide local LLM inference for "Local Only" mode.
#
# Usage:
#   ./scripts/setup_vllm_gpu.sh [--install] [--start] [--status] [--stop]
#
# Options:
#   --install   Install vLLM (requires pip)
#   --start     Start vLLM services (Phi-3 + Qwen)
#   --stop      Stop vLLM services
#   --status    Check GPU and vLLM status
#   (no args)   Check GPU, install if needed, and start services
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# vLLM Configuration
PHI3_MODEL="microsoft/Phi-3-mini-4k-instruct"
PHI3_PORT=8765
QWEN_MODEL="Qwen/Qwen2.5-3B-Instruct"
QWEN_PORT=8766

echo "================================"
echo "  vLLM GPU Setup"
echo "================================"
echo ""

# Function: Check for NVIDIA GPU
check_gpu() {
    echo -e "${BLUE}Checking for NVIDIA GPU...${NC}"

    if ! command -v nvidia-smi &> /dev/null; then
        echo -e "${RED}[ERROR] nvidia-smi not found${NC}"
        echo "NVIDIA drivers not installed or GPU not available."
        return 1
    fi

    GPU_INFO=$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null)
    if [ -z "$GPU_INFO" ]; then
        echo -e "${RED}[ERROR] No NVIDIA GPU detected${NC}"
        return 1
    fi

    echo -e "${GREEN}[OK] GPU found:${NC}"
    nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv,noheader | while read line; do
        echo "  $line"
    done

    # Check VRAM (need at least 8GB for both models)
    VRAM_MB=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1)
    if [ "$VRAM_MB" -lt 8000 ]; then
        echo -e "${YELLOW}[WARN] GPU has ${VRAM_MB}MB VRAM. Recommended: 8GB+${NC}"
        echo "  You may need to run only one model at a time."
    fi

    return 0
}

# Function: Check if vLLM is installed
check_vllm_installed() {
    if python3 -c "import vllm" 2>/dev/null; then
        VLLM_VERSION=$(python3 -c "import vllm; print(vllm.__version__)" 2>/dev/null)
        echo -e "${GREEN}[OK] vLLM installed: v${VLLM_VERSION}${NC}"
        return 0
    else
        echo -e "${YELLOW}[NOT INSTALLED] vLLM not found${NC}"
        return 1
    fi
}

# Function: Install vLLM
install_vllm() {
    echo -e "${BLUE}Installing vLLM...${NC}"
    pip install vllm
    echo -e "${GREEN}[OK] vLLM installed${NC}"
}

# Function: Check if vLLM service is running
check_vllm_service() {
    local port=$1
    local name=$2

    if curl -s --connect-timeout 2 "http://localhost:$port/v1/models" > /dev/null 2>&1; then
        local model=$(curl -s "http://localhost:$port/v1/models" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)
        echo -e "  ${GREEN}[RUNNING]${NC} $name (port $port) - $model"
        return 0
    else
        echo -e "  ${RED}[STOPPED]${NC} $name (port $port)"
        return 1
    fi
}

# Function: Start vLLM service
start_vllm_service() {
    local model=$1
    local port=$2
    local name=$3
    local gpu_util=$4

    # Check if already running
    if curl -s --connect-timeout 2 "http://localhost:$port/v1/models" > /dev/null 2>&1; then
        echo -e "${YELLOW}[SKIP]${NC} $name already running on port $port"
        return 0
    fi

    echo -e "${BLUE}Starting $name on port $port...${NC}"

    # Create log directory
    mkdir -p /var/log/vllm

    # Start vLLM in background
    nohup vllm serve "$model" \
        --port $port \
        --host 127.0.0.1 \
        --max-model-len 2048 \
        --gpu-memory-utilization $gpu_util \
        --enforce-eager \
        > /var/log/vllm/${name}.log 2>&1 &

    local pid=$!
    echo "  PID: $pid"
    echo "  Log: /var/log/vllm/${name}.log"

    # Wait for startup
    echo "  Waiting for model to load..."
    for i in {1..60}; do
        if curl -s --connect-timeout 1 "http://localhost:$port/v1/models" > /dev/null 2>&1; then
            echo -e "  ${GREEN}[OK]${NC} $name ready"
            return 0
        fi
        sleep 2
    done

    echo -e "  ${RED}[TIMEOUT]${NC} $name failed to start within 120s"
    echo "  Check log: tail -f /var/log/vllm/${name}.log"
    return 1
}

# Function: Stop vLLM services
stop_vllm_services() {
    echo -e "${BLUE}Stopping vLLM services...${NC}"

    # Find and kill vLLM processes
    pkill -f "vllm serve" 2>/dev/null || true

    sleep 2

    if pgrep -f "vllm serve" > /dev/null; then
        echo -e "${YELLOW}[WARN]${NC} Some vLLM processes still running, force killing..."
        pkill -9 -f "vllm serve" 2>/dev/null || true
    fi

    echo -e "${GREEN}[OK]${NC} vLLM services stopped"
}

# Function: Show status
show_status() {
    echo ""
    echo "GPU Status:"
    if check_gpu; then
        echo ""
        echo "vLLM Installation:"
        check_vllm_installed
        echo ""
        echo "vLLM Services:"
        check_vllm_service $PHI3_PORT "Phi-3"
        check_vllm_service $QWEN_PORT "Qwen"
    fi
}

# Function: Full setup
full_setup() {
    # Check GPU
    if ! check_gpu; then
        echo ""
        echo -e "${RED}No GPU found. Cannot setup vLLM.${NC}"
        echo "For CPU-only servers, use 'hybrid' or 'external' inference mode."
        exit 1
    fi

    echo ""

    # Check/install vLLM
    if ! check_vllm_installed; then
        echo ""
        read -p "Install vLLM now? [y/N] " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            install_vllm
        else
            echo "Skipping vLLM installation."
            exit 0
        fi
    fi

    echo ""
    echo "Starting vLLM services..."
    echo ""

    # Start Phi-3 (summarization) - 48% GPU memory
    start_vllm_service "$PHI3_MODEL" $PHI3_PORT "phi3" 0.48

    echo ""

    # Start Qwen (category/fallback) - 45% GPU memory
    start_vllm_service "$QWEN_MODEL" $QWEN_PORT "qwen" 0.45

    echo ""
    echo "================================"
    echo "  Setup Complete"
    echo "================================"
    echo ""
    echo "vLLM endpoints:"
    echo "  Phi-3 (summarization): http://localhost:$PHI3_PORT/v1"
    echo "  Qwen (category):       http://localhost:$QWEN_PORT/v1"
    echo ""
    echo "To use local models, set inference mode to 'Local' in the UI."
    echo ""
    echo "Logs:"
    echo "  tail -f /var/log/vllm/phi3.log"
    echo "  tail -f /var/log/vllm/qwen.log"
    echo ""
}

# Parse arguments
case "${1:-}" in
    --install)
        check_gpu && install_vllm
        ;;
    --start)
        start_vllm_service "$PHI3_MODEL" $PHI3_PORT "phi3" 0.48
        start_vllm_service "$QWEN_MODEL" $QWEN_PORT "qwen" 0.45
        ;;
    --stop)
        stop_vllm_services
        ;;
    --status)
        show_status
        ;;
    *)
        full_setup
        ;;
esac
