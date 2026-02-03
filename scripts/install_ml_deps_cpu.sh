#!/bin/bash
#
# Install ML Dependencies (CPU-only) for Frontend Server
#
# Installs PyTorch (CPU), transformers, datasets, etc. for DeBERTa models.
# Run this on the frontend server (no GPU).
#
# Usage:
#   ./scripts/install_ml_deps_cpu.sh [tenant_path]
#
# Examples:
#   ./scripts/install_ml_deps_cpu.sh                           # Install for current tenant
#   ./scripts/install_ml_deps_cpu.sh /path/to/tenant           # Install for specific tenant
#   for t in /home/orochford/tenants/*.aunoo.ai; do            # Install for all tenants
#       $t/scripts/install_ml_deps_cpu.sh "$t"
#   done
#

set -e

# Determine tenant directory
if [ -n "$1" ]; then
    TENANT_DIR="$1"
else
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    TENANT_DIR="$(dirname "$SCRIPT_DIR")"
fi

TENANT_NAME=$(basename "$TENANT_DIR")

echo "================================"
echo "  ML Dependencies Install (CPU)"
echo "================================"
echo ""
echo "Tenant: $TENANT_NAME"
echo "Path: $TENANT_DIR"
echo ""

# Check venv exists
if [ ! -d "$TENANT_DIR/.venv" ]; then
    echo "Error: No .venv found at $TENANT_DIR"
    exit 1
fi

cd "$TENANT_DIR"
source .venv/bin/activate

echo "Installing CPU-only PyTorch..."
pip install torch --index-url https://download.pytorch.org/whl/cpu

echo ""
echo "Installing ML packages..."
pip install datasets transformers sentence-transformers accelerate safetensors

deactivate

echo ""
echo "================================"
echo "  Install Complete"
echo "================================"
echo ""
echo "Next: Restart the service"
echo "  sudo systemctl restart $TENANT_NAME.service"
echo ""
