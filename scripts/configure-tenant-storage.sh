#!/bin/bash

# AunooAI Tenant Storage Configuration Script
# ------------------------------------------
# This script configures Cloud Storage buckets for AunooAI tenants and
# updates existing Cloud Run services to use the storage buckets.

set -e  # Exit on error

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
      echo "  --tenant NAME        Specific tenant to configure (if not specified, all tenants will be configured)"
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
  SERVICE_INFO=$(gcloud run services describe aunooai-$TENANT --region $REGION 2>/dev/null || echo "")
  
  if [ -z "$SERVICE_INFO" ]; then
    echo "Error: Service aunooai-$TENANT not found in region $REGION"
    TENANTS_FAILED+=("$TENANT")
    continue
  fi
  
  # Check if STORAGE_BUCKET is already set
  CURRENT_ENV_VARS=$(echo "$SERVICE_INFO" | grep -A 100 "env:" | grep -B 100 "ports:" | grep -v "env:" | grep -v "ports:")
  STORAGE_BUCKET=$(echo "$CURRENT_ENV_VARS" | grep "name: STORAGE_BUCKET" -A 1 | grep "value:" | awk '{print $2}')
  
  if [ -n "$STORAGE_BUCKET" ]; then
    echo "STORAGE_BUCKET already set to: $STORAGE_BUCKET"
    
    # Check if bucket exists
    if gsutil ls -b gs://$STORAGE_BUCKET &>/dev/null; then
      echo "Storage bucket $STORAGE_BUCKET exists"
      TENANTS_UPDATED+=("$TENANT")
      continue
    else
      echo "Storage bucket $STORAGE_BUCKET does not exist. Creating it..."
    fi
  else
    # Create a new bucket name
    STORAGE_BUCKET="${PROJECT_ID}-aunooai-${TENANT}"
    echo "No STORAGE_BUCKET found. Will create: $STORAGE_BUCKET"
  fi
  
  # Create the storage bucket
  echo "Creating Cloud Storage bucket: $STORAGE_BUCKET"
  if gsutil mb -l $REGION gs://$STORAGE_BUCKET; then
    echo "Bucket created successfully"
  else
    echo "Failed to create bucket. Checking if it already exists..."
    if ! gsutil ls -b gs://$STORAGE_BUCKET &>/dev/null; then
      echo "Error: Failed to create bucket and it doesn't exist"
      TENANTS_FAILED+=("$TENANT")
      continue
    fi
  fi
  
  # Get the service account used by the Cloud Run service
  SERVICE_ACCOUNT=$(echo "$SERVICE_INFO" | grep "serviceAccount:" | awk '{print $2}')
  
  if [ -z "$SERVICE_ACCOUNT" ]; then
    echo "No service account found for aunooai-$TENANT. Creating one..."
    SA_NAME="aunooai-$TENANT-sa"
    SA_EMAIL="$SA_NAME@$PROJECT_ID.iam.gserviceaccount.com"
    
    # Create service account
    gcloud iam service-accounts create $SA_NAME \
      --display-name="AunooAI $TENANT Service Account" || echo "Service account already exists"
    
    SERVICE_ACCOUNT=$SA_EMAIL
  fi
  
  # Grant the service account access to the bucket
  echo "Granting bucket access to service account: $SERVICE_ACCOUNT"
  gsutil iam ch serviceAccount:$SERVICE_ACCOUNT:objectAdmin gs://$STORAGE_BUCKET
  
  # Update the Cloud Run service with the STORAGE_BUCKET environment variable
  echo "Updating Cloud Run service with STORAGE_BUCKET environment variable..."
  
  # Check if STORAGE_BUCKET is already set
  if echo "$CURRENT_ENV_VARS" | grep -q "name: STORAGE_BUCKET"; then
    echo "STORAGE_BUCKET environment variable already exists. Updating it..."
    gcloud run services update aunooai-$TENANT \
      --region $REGION \
      --update-env-vars="STORAGE_BUCKET=$STORAGE_BUCKET"
  else
    echo "Adding STORAGE_BUCKET environment variable..."
    gcloud run services update aunooai-$TENANT \
      --region $REGION \
      --set-env-vars="STORAGE_BUCKET=$STORAGE_BUCKET"
  fi
  
  if [ $? -eq 0 ]; then
    echo "Successfully updated Cloud Run service with STORAGE_BUCKET"
    TENANTS_UPDATED+=("$TENANT")
  else
    echo "Failed to update Cloud Run service"
    TENANTS_FAILED+=("$TENANT")
  fi
  
  echo ""
done

# Print summary
echo ""
echo "=== Storage Configuration Summary ==="
echo "Total tenants processed: ${#TENANTS[@]}"
echo "Successfully configured: ${#TENANTS_UPDATED[@]}"
echo "Failed: ${#TENANTS_FAILED[@]}"
echo ""

if [ ${#TENANTS_UPDATED[@]} -gt 0 ]; then
  echo "Successfully configured tenants:"
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