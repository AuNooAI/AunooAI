#!/bin/bash
# transfer_models_to_remote.sh
# Transfer pretrained ML models to remote server
#
# Usage:
#   ./scripts/transfer_models_to_remote.sh orochford@88.99.149.48
#
# This transfers only the final/ model directories (no checkpoints)
# Total size: ~4.4GB

set -e

REMOTE_HOST="${1:-orochford@88.99.149.48}"
SOURCE_DIR="/home/orochford/tenants/bugfixing.aunoo.ai/models"
REMOTE_BASE="/home/orochford"

echo "=============================================="
echo "  Model Transfer to Remote Server"
echo "=============================================="
echo "Remote: $REMOTE_HOST"
echo "Source: $SOURCE_DIR"
echo ""

# Check SSH connection
echo "Testing SSH connection..."
ssh -o ConnectTimeout=5 "$REMOTE_HOST" "echo 'SSH connection OK'" || {
    echo "ERROR: Cannot connect to $REMOTE_HOST"
    exit 1
}

# Create remote directory structure
echo ""
echo "Creating remote directory structure..."
ssh "$REMOTE_HOST" "mkdir -p $REMOTE_BASE/pretrained_models/{policy_classifier,policy_llm,summarizer}"

# Transfer models (only final/ directories, no checkpoints)
echo ""
echo "Transferring policy_classifier/final/ (~535MB)..."
rsync -avz --progress \
    "$SOURCE_DIR/policy_classifier/final/" \
    "$REMOTE_HOST:$REMOTE_BASE/pretrained_models/policy_classifier/final/"

echo ""
echo "Transferring policy_classifier/final_roberta_large/ (~1.4GB)..."
rsync -avz --progress \
    "$SOURCE_DIR/policy_classifier/final_roberta_large/" \
    "$REMOTE_HOST:$REMOTE_BASE/pretrained_models/policy_classifier/final_roberta_large/"

echo ""
echo "Transferring policy_llm/final/ (~841MB)..."
rsync -avz --progress \
    "$SOURCE_DIR/policy_llm/final/" \
    "$REMOTE_HOST:$REMOTE_BASE/pretrained_models/policy_llm/final/"

echo ""
echo "Transferring summarizer/final/ (~1.6GB)..."
rsync -avz --progress \
    "$SOURCE_DIR/summarizer/final/" \
    "$REMOTE_HOST:$REMOTE_BASE/pretrained_models/summarizer/final/"

# Transfer documentation
echo ""
echo "Transferring setup instructions..."
rsync -avz --progress \
    "/home/orochford/tenants/bugfixing.aunoo.ai/docs/MODEL_DEPLOYMENT.md" \
    "$REMOTE_HOST:$REMOTE_BASE/pretrained_models/"

# Create README on remote
ssh "$REMOTE_HOST" "cat > $REMOTE_BASE/pretrained_models/README.md << 'REMOTE_EOF'
# Pretrained Models for AunooAI

These models were transferred from the training server (bugfixing.aunoo.ai).

## Contents

| Model | Size | Purpose |
|-------|------|---------|
| policy_classifier/final/ | 535MB | DeBERTa policy classifier |
| policy_classifier/final_roberta_large/ | 1.4GB | RoBERTa-large policy classifier (ensemble) |
| policy_llm/final/ | 841MB | Policy-specific LLM adapter |
| summarizer/final/ | 1.6GB | Article summarization model |

## Setup Instructions for Claude

To set up models for a tenant:

\`\`\`bash
# 1. Create models directory for tenant
TENANT=\"your-tenant.aunoo.ai\"
mkdir -p /home/orochford/tenants/\$TENANT/models

# 2. Copy pretrained models (not symlink - full isolation)
cp -r /home/orochford/pretrained_models/policy_classifier /home/orochford/tenants/\$TENANT/models/
cp -r /home/orochford/pretrained_models/policy_llm /home/orochford/tenants/\$TENANT/models/
cp -r /home/orochford/pretrained_models/summarizer /home/orochford/tenants/\$TENANT/models/

# 3. Fix ownership
chown -R orochford:orochford /home/orochford/tenants/\$TENANT/models/
\`\`\`

## User-Trainable Models

These are NOT included - they are generated per-tenant:
- enrichment_model/ - Trained via ACT system when 500+ samples collected
- relevance_classifier/ - Trained from user feedback

See MODEL_DEPLOYMENT.md for full documentation.

## Transfer Date
$(date '+%Y-%m-%d %H:%M:%S')
REMOTE_EOF"

echo ""
echo "=============================================="
echo "  Transfer Complete!"
echo "=============================================="
echo ""
echo "Models are now at: $REMOTE_HOST:$REMOTE_BASE/pretrained_models/"
echo ""
echo "To set up a tenant on the remote server, run:"
echo "  ssh $REMOTE_HOST"
echo "  cat $REMOTE_BASE/pretrained_models/README.md"
echo ""
