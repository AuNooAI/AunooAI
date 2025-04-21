#!/bin/bash
# Script to fix all tenants at once by configuring storage and updating resources

set -e

# Default values
REGION="us-central1"
CPU="2"
MEMORY="4Gi"
MIN_INSTANCES="1"
MAX_INSTANCES="10"
CONCURRENCY="80"
TIMEOUT="600s"
REDEPLOY=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  key="$1"
  case $key in
    --project)
      PROJECT_ID="$2"
      shift 2
      ;;
    --region)
      REGION="$2"
      shift 2
      ;;
    --admin-password)
      ADMIN_PASSWORD="$2"
      shift 2
      ;;
    --redeploy)
      REDEPLOY=true
      shift
      ;;
    --help)
      echo "Usage: $0 --project PROJECT_ID [--region REGION] [--admin-password PASSWORD] [--redeploy]"
      echo ""
      echo "Options:"
      echo "  --project ID         GCP Project ID (required)"
      echo "  --region REGION      GCP Region (default: us-central1)"
      echo "  --admin-password PWD Admin password for redeployment (required if --redeploy is used)"
      echo "  --redeploy           Redeploy tenants after configuration (requires admin password)"
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      echo "Run '$0 --help' for usage information"
      exit 1
      ;;
  esac
done

# Validate required parameters
if [ -z "$PROJECT_ID" ]; then
  echo "Error: --project is required"
  echo "Run '$0 --help' for usage information"
  exit 1
fi

if [ "$REDEPLOY" = true ] && [ -z "$ADMIN_PASSWORD" ]; then
  echo "Error: --admin-password is required when using --redeploy"
  echo "Run '$0 --help' for usage information"
  exit 1
fi

# Configure gcloud
echo "Configuring gcloud..."
gcloud config set project $PROJECT_ID

# Get all Cloud Run services that start with aunooai-
echo "Finding AunooAI tenants in project $PROJECT_ID..."
TENANTS=$(gcloud run services list --region $REGION --format="value(metadata.name)" | grep "^aunooai-" | sed 's/^aunooai-//')

if [ -z "$TENANTS" ]; then
  echo "No AunooAI tenants found in project $PROJECT_ID, region $REGION"
  exit 1
fi

echo "Found tenants: $TENANTS"
echo ""

# Arrays to track progress
TENANTS_FIXED=()
TENANTS_FAILED=()
TENANTS_REDEPLOYED=()

# Process each tenant
for TENANT in $TENANTS; do
  echo "=== Processing tenant: $TENANT ==="
  
  # Step 1: Configure storage if needed
  echo "Checking storage configuration..."
  if ./scripts/verify-tenant-config.sh --project $PROJECT_ID --tenant $TENANT | grep -q "No issues found"; then
    echo "Storage already configured correctly."
  else
    echo "Configuring storage..."
    if ./scripts/configure-tenant-storage.sh --project $PROJECT_ID --tenant $TENANT; then
      echo "Storage configuration successful."
    else
      echo "Failed to configure storage for $TENANT."
      TENANTS_FAILED+=("$TENANT")
      continue
    fi
  fi
  
  # Step 2: Update resource settings
  echo "Updating resource settings..."
  if ./scripts/update-cloud-run-deployments.sh --project $PROJECT_ID --tenant $TENANT --cpu $CPU --memory $MEMORY --min-instances $MIN_INSTANCES --max-instances $MAX_INSTANCES --concurrency $CONCURRENCY --timeout $TIMEOUT; then
    echo "Resource update successful."
  else
    echo "Failed to update resources for $TENANT."
    TENANTS_FAILED+=("$TENANT")
    continue
  fi
  
  # Step 3: Redeploy if requested
  if [ "$REDEPLOY" = true ]; then
    echo "Redeploying tenant..."
    if ./scripts/gcp-deploy.sh --project $PROJECT_ID --tenant $TENANT --admin-password "$ADMIN_PASSWORD"; then
      echo "Redeployment successful."
      TENANTS_REDEPLOYED+=("$TENANT")
    else
      echo "Failed to redeploy $TENANT."
      TENANTS_FAILED+=("$TENANT")
      continue
    fi
  fi
  
  TENANTS_FIXED+=("$TENANT")
  echo "Tenant $TENANT processed successfully."
  echo ""
done

# Print summary
echo ""
echo "=== Processing Summary ==="
echo "Total tenants: ${#TENANTS[@]}"
echo "Successfully fixed: ${#TENANTS_FIXED[@]}"
if [ "$REDEPLOY" = true ]; then
  echo "Successfully redeployed: ${#TENANTS_REDEPLOYED[@]}"
fi
echo "Failed: ${#TENANTS_FAILED[@]}"
echo ""

if [ ${#TENANTS_FIXED[@]} -gt 0 ]; then
  echo "Successfully fixed tenants:"
  for TENANT in "${TENANTS_FIXED[@]}"; do
    echo "  - $TENANT"
  done
  echo ""
fi

if [ ${#TENANTS_FAILED[@]} -gt 0 ]; then
  echo "Failed tenants:"
  for TENANT in "${TENANTS_FAILED[@]}"; do
    echo "  - $TENANT"
  done
  echo ""
  echo "These tenants need manual investigation."
fi

if [ "$REDEPLOY" = false ] && [ ${#TENANTS_FIXED[@]} -gt 0 ]; then
  echo "To apply the data persistence improvements, you need to redeploy each tenant:"
  echo "./scripts/gcp-deploy.sh --project $PROJECT_ID --tenant TENANT_NAME --admin-password PASSWORD"
  echo ""
  echo "Or run this script again with the --redeploy option:"
  echo "$0 --project $PROJECT_ID --admin-password PASSWORD --redeploy"
fi 