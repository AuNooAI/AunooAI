#!/bin/bash
# Script to add Cloud Storage volume mounts to all existing tenants

set -e

# Default values
REGION="us-central1"

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
    --tenant)
      TENANT="$2"
      shift 2
      ;;
    --help)
      echo "Usage: $0 --project PROJECT_ID [--region REGION] [--tenant TENANT_NAME]"
      echo ""
      echo "Options:"
      echo "  --project ID         GCP Project ID (required)"
      echo "  --region REGION      GCP Region (default: us-central1)"
      echo "  --tenant NAME        Specific tenant to update (if not specified, all tenants will be updated)"
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

# Configure gcloud
echo "Configuring gcloud..."
gcloud config set project $PROJECT_ID

# Get tenants to process
if [ -n "$TENANT" ]; then
  TENANTS=($TENANT)
  echo "Processing single tenant: $TENANT"
else
  echo "Finding AunooAI tenants in project $PROJECT_ID..."
  TENANTS=$(gcloud run services list --region $REGION --format="value(metadata.name)" | grep "^aunooai-" | sed 's/^aunooai-//')
  
  if [ -z "$TENANTS" ]; then
    echo "No AunooAI tenants found in project $PROJECT_ID, region $REGION"
    exit 1
  fi
  
  echo "Found tenants: $TENANTS"
fi

echo ""

# Arrays to track progress
TENANTS_UPDATED=()
TENANTS_FAILED=()

# Process each tenant
for TENANT in $TENANTS; do
  echo "=== Processing tenant: $TENANT ==="
  
  # Get current configuration
  echo "Getting current configuration for aunooai-$TENANT..."
  CURRENT_ENV_VARS=$(gcloud run services describe aunooai-$TENANT --region $REGION --format="value(spec.template.spec.containers[0].env)" 2>/dev/null || echo "")
  
  if [ -z "$CURRENT_ENV_VARS" ]; then
    echo "Error: Service aunooai-$TENANT not found in region $REGION"
    TENANTS_FAILED+=("$TENANT")
    continue
  fi
  
  # Extract storage bucket
  STORAGE_BUCKET=""
  
  # Parse using regex for the specific format
  while IFS= read -r line; do
    if [[ "$line" =~ \'name\':\ \'STORAGE_BUCKET\',\ \'value\':\ \'([^\']*)\' ]]; then
      STORAGE_BUCKET="${BASH_REMATCH[1]}"
      echo "Found STORAGE_BUCKET: $STORAGE_BUCKET"
    fi
  done <<< "$CURRENT_ENV_VARS"
  
  # Alternative parsing method
  if [ -z "$STORAGE_BUCKET" ]; then
    STORAGE_BUCKET=$(echo "$CURRENT_ENV_VARS" | grep -o "'name': 'STORAGE_BUCKET', 'value': '[^']*'" | grep -o "'value': '[^']*'" | cut -d"'" -f4)
    if [ -n "$STORAGE_BUCKET" ]; then
      echo "Found STORAGE_BUCKET (alt method): $STORAGE_BUCKET"
    fi
  fi
  
  # Check if storage bucket is set
  if [ -z "$STORAGE_BUCKET" ]; then
    echo "Error: No STORAGE_BUCKET found for aunooai-$TENANT"
    echo "Please run ./scripts/configure-tenant-storage.sh --project $PROJECT_ID --tenant $TENANT first"
    TENANTS_FAILED+=("$TENANT")
    continue
  fi
  
  # Check if bucket exists
  if ! gsutil ls -b gs://$STORAGE_BUCKET &>/dev/null; then
    echo "Error: Storage bucket $STORAGE_BUCKET does not exist"
    TENANTS_FAILED+=("$TENANT")
    continue
  fi
  
  # Check if volume mount already exists
  if gcloud run services describe aunooai-$TENANT --region $REGION | grep -q "type: cloud-storage"; then
    echo "Volume mount already exists for aunooai-$TENANT"
    TENANTS_UPDATED+=("$TENANT")
    continue
  fi
  
  # Add volume mount - using the correct syntax for volume mounts
  echo "Adding volume mount for storage bucket $STORAGE_BUCKET..."
  
  # Try the newer syntax first
  if gcloud run services update aunooai-$TENANT \
    --region $REGION \
    --add-volume name=storage,type=cloud-storage,bucket=$STORAGE_BUCKET \
    --add-volume-mount volume=storage,mount-path=/app/app/data/$TENANT; then
    echo "Volume mount added successfully using new syntax"
    TENANTS_UPDATED+=("$TENANT")
  # If that fails, try the older syntax
  elif gcloud beta run services update aunooai-$TENANT \
    --region $REGION \
    --update-volume-mounts mount-path=/app/app/data/$TENANT,volume=storage \
    --update-volumes name=storage,cloud-storage-bucket=$STORAGE_BUCKET; then
    echo "Volume mount added successfully using beta syntax"
    TENANTS_UPDATED+=("$TENANT")
  # If both fail, try the direct mount syntax
  elif gcloud beta run services update aunooai-$TENANT \
    --region $REGION \
    --mount type=cloud-storage,bucket=$STORAGE_BUCKET,path=/app/app/data/$TENANT; then
    echo "Volume mount added successfully using direct mount syntax"
    TENANTS_UPDATED+=("$TENANT")
  else
    echo "Failed to add volume mount with any syntax"
    TENANTS_FAILED+=("$TENANT")
  fi
  
  echo ""
done

# Print summary
echo ""
echo "=== Volume Mount Summary ==="
echo "Total tenants processed: ${#TENANTS[@]}"
echo "Successfully updated: ${#TENANTS_UPDATED[@]}"
echo "Failed: ${#TENANTS_FAILED[@]}"
echo ""

if [ ${#TENANTS_UPDATED[@]} -gt 0 ]; then
  echo "Successfully updated tenants:"
  for TENANT in "${TENANTS_UPDATED[@]}"; do
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