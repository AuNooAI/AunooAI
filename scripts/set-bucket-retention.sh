#!/bin/bash

# AunooAI GCP Bucket Retention Configuration Script
# ------------------------------------------------
# This script sets object retention policies on Cloud Storage buckets for AunooAI tenants.

set -e  # Exit on error

# Default configuration
PROJECT_ID=""
REGION="us-central1"
TENANT=""
RETENTION_PERIOD=""
ALL_TENANTS=false

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
    --retention-period)
      RETENTION_PERIOD="$2"
      shift 2
      ;;
    --all-tenants)
      ALL_TENANTS=true
      shift
      ;;
    --help)
      echo "Usage: $0 --project PROJECT_ID [OPTIONS]"
      echo ""
      echo "Required:"
      echo "  --project ID         GCP Project ID"
      echo ""
      echo "Options:"
      echo "  --region REGION      GCP Region (default: us-central1)"
      echo "  --tenant NAME        Specific tenant to configure"
      echo "  --retention-period PERIOD  Retention period (no default, format: e.g., 30d, 1y, 100y)"
      echo "                       If not specified, no retention policy will be set"
      echo "  --all-tenants        Configure all tenants (ignores --tenant)"
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

echo "============================================="
echo "AunooAI GCP Bucket Retention Configuration"
echo "============================================="
echo "Project ID: $PROJECT_ID"
echo "Region: $REGION"
if [ "$ALL_TENANTS" = true ]; then
  echo "Target: All tenants"
else
  if [ -z "$TENANT" ]; then
    echo "Error: Either --tenant or --all-tenants is required"
    exit 1
  fi
  echo "Target Tenant: $TENANT"
fi
echo "Retention Period: $RETENTION_PERIOD"
echo "============================================="

# Function to set retention on a bucket
set_bucket_retention() {
  local bucket_name="$1"
  
  echo "Setting retention policy on bucket: $bucket_name"
  
  # If no retention period specified, check if we should remove it (not actually possible)
  if [ -z "$RETENTION_PERIOD" ]; then
    echo "  - No retention period specified"
    
    if gsutil retention get gs://$bucket_name &>/dev/null; then
      current_retention=$(gsutil retention get gs://$bucket_name | grep -o 'Duration: [0-9]\+[dhmy]' | awk '{print $2}')
      echo "  - Current retention period: $current_retention"
      echo "  - WARNING: Retention periods cannot be removed once set"
      echo "  - Bucket will keep its current retention policy"
    else
      echo "  - No existing retention policy found"
      echo "  - Bucket will continue with Google's default behavior (files persist indefinitely until deleted)"
    fi
    return
  fi
  
  # If retention period specified, try to set it
  if gsutil retention get gs://$bucket_name &>/dev/null; then
    current_retention=$(gsutil retention get gs://$bucket_name | grep -o 'Duration: [0-9]\+[dhmy]' | awk '{print $2}')
    echo "  - Current retention period: $current_retention"
    echo "  - New retention period: $RETENTION_PERIOD"
    
    # Compare retention periods (convert to days for comparison)
    current_days=$(convert_to_days $current_retention)
    new_days=$(convert_to_days $RETENTION_PERIOD)
    
    if (( new_days < current_days )); then
      echo "  - WARNING: New retention period ($RETENTION_PERIOD) is shorter than current retention period ($current_retention)"
      echo "  - Retention periods can only be increased, not decreased. Skipping this bucket."
      return
    fi
  else
    echo "  - No existing retention policy"
  fi
  
  if gsutil retention set $RETENTION_PERIOD gs://$bucket_name; then
    echo "  - Successfully set retention policy to $RETENTION_PERIOD"
  else
    echo "  - Failed to set retention policy"
  fi
}

# Function to convert retention period to days (approximate)
convert_to_days() {
  local period="$1"
  local value=$(echo $period | grep -o '[0-9]\+')
  local unit=$(echo $period | grep -o '[dhmy]')
  
  case $unit in
    h)
      echo $(( value / 24 ))
      ;;
    d)
      echo $value
      ;;
    m)
      echo $(( value * 30 ))
      ;;
    y)
      echo $(( value * 365 ))
      ;;
    *)
      echo 0
      ;;
  esac
}

# Process buckets
if [ "$ALL_TENANTS" = true ]; then
  echo "Configuring all tenant buckets in project $PROJECT_ID..."
  
  # List all buckets for this project that match the AunooAI pattern
  buckets=$(gsutil ls -p $PROJECT_ID | grep "gs://${PROJECT_ID}-aunooai-" || echo "")
  
  if [ -z "$buckets" ]; then
    echo "No AunooAI tenant buckets found in project $PROJECT_ID"
    exit 0
  fi
  
  for bucket in $buckets; do
    bucket_name=$(echo $bucket | sed 's/gs:\/\///' | tr -d '/')
    set_bucket_retention $bucket_name
  done
else
  # Configure a specific tenant
  bucket_name="${PROJECT_ID}-aunooai-${TENANT}"
  
  # Check if the bucket exists
  if ! gsutil ls -p $PROJECT_ID | grep -q "gs://${bucket_name}"; then
    echo "Error: Bucket gs://${bucket_name} does not exist"
    exit 1
  fi
  
  set_bucket_retention $bucket_name
fi

echo "============================================="
echo "Bucket retention configuration completed"
echo "=============================================" 