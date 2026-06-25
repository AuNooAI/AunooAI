#!/bin/bash
#
# Install Local Models from Package
#
# Extracts the local-models-package.tar.gz to the current tenant directory.
#
# Usage:
#   cd /path/to/tenant
#   tar -xzf local-models-package.tar.gz
#   # OR
#   ./scripts/install_local_models.sh
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TENANT_DIR="$(dirname "$SCRIPT_DIR")"

echo "================================"
echo "  Local Models Install"
echo "================================"
echo ""
echo "Tenant: $TENANT_DIR"
echo ""

# Check for package
PACKAGE="$TENANT_DIR/local-models-package.tar.gz"
if [ ! -f "$PACKAGE" ]; then
    echo "Error: Package not found at $PACKAGE"
    echo ""
    echo "Copy the package first:"
    echo "  scp local-models-package.tar.gz user@server:$TENANT_DIR/"
    exit 1
fi

echo "Extracting models..."
cd "$TENANT_DIR"
tar -xzvf local-models-package.tar.gz

echo ""
echo "Verifying installation..."

check_model() {
    local path="$1"
    local name="$2"
    if [ -d "$path" ] && [ -f "$path/config.json" ]; then
        local size=$(du -sh "$path" | cut -f1)
        echo "  [OK] $name ($size)"
    else
        echo "  [MISSING] $name"
    fi
}

check_model "$TENANT_DIR/models/enrichment_model/final" "DeBERTa Enrichment"
check_model "$TENANT_DIR/models/relevance_classifier/final" "DeBERTa Relevance"

echo ""
echo "================================"
echo "  Install Complete"
echo "================================"
echo ""
echo "Next: Restart the service"
echo "  sudo systemctl restart $(basename $TENANT_DIR).service"
echo ""
