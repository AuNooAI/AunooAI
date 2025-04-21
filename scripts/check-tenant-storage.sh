#!/bin/bash
# Script to check all tenants for proper storage configuration

set -e

# Default values
REGION="us-central1"
VERBOSE=false

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
    --verbose)
      VERBOSE=true
      shift
      ;;
    --help)
      echo "Usage: $0 --project PROJECT_ID [--region REGION] [--verbose]"
      echo ""
      echo "Options:"
      echo "  --project ID         GCP Project ID (required)"
      echo "  --region REGION      GCP Region (default: us-central1)"
      echo "  --verbose            Show detailed information for each tenant"
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

# Get all Cloud Run services that start with aunooai-
echo "Finding AunooAI tenants in project $PROJECT_ID..."
TENANTS=$(gcloud run services list --region $REGION --format="value(metadata.name)" | grep "^aunooai-" | sed 's/^aunooai-//')

if [ -z "$TENANTS" ]; then
  echo "No AunooAI tenants found in project $PROJECT_ID, region $REGION"
  exit 1
fi

echo "Found tenants: $TENANTS"
echo ""

# Arrays to store results
TENANTS_WITH_STORAGE=()
TENANTS_WITHOUT_STORAGE=()
TENANTS_WITH_ISSUES=()

# Check each tenant
for TENANT in $TENANTS; do
  if [ "$VERBOSE" = true ]; then
    echo "=== Checking tenant: $TENANT ==="
  else
    echo -n "Checking tenant $TENANT... "
  fi
  
  # Get current configuration
  CURRENT_ENV_VARS=$(gcloud run services describe aunooai-$TENANT --region $REGION --format="value(spec.template.spec.containers[0].env)" 2>/dev/null || echo "")
  
  if [ -z "$CURRENT_ENV_VARS" ]; then
    echo "Error: Could not retrieve configuration"
    TENANTS_WITH_ISSUES+=("$TENANT")
    continue
  fi
  
  # Extract environment variables
  STORAGE_BUCKET=""
  
  # Parse using regex for the specific format
  while IFS= read -r line; do
    if [[ "$line" =~ \'name\':\ \'STORAGE_BUCKET\',\ \'value\':\ \'([^\']*)\' ]]; then
      STORAGE_BUCKET="${BASH_REMATCH[1]}"
      if [ "$VERBOSE" = true ]; then
        echo "Found STORAGE_BUCKET: $STORAGE_BUCKET"
      fi
    fi
  done <<< "$CURRENT_ENV_VARS"
  
  # Alternative parsing method
  if [ -z "$STORAGE_BUCKET" ]; then
    STORAGE_BUCKET=$(echo "$CURRENT_ENV_VARS" | grep -o "'name': 'STORAGE_BUCKET', 'value': '[^']*'" | grep -o "'value': '[^']*'" | cut -d"'" -f4)
    if [ -n "$STORAGE_BUCKET" ] && [ "$VERBOSE" = true ]; then
      echo "Found STORAGE_BUCKET (alt method): $STORAGE_BUCKET"
    fi
  fi
  
  # Check if STORAGE_BUCKET is set
  if [ -n "$STORAGE_BUCKET" ]; then
    # Check if bucket exists
    if gsutil ls -b gs://$STORAGE_BUCKET &>/dev/null; then
      if [ "$VERBOSE" = true ]; then
        echo "Storage bucket configured: $STORAGE_BUCKET"
        echo "Bucket exists: Yes"
      else
        echo "OK (bucket: $STORAGE_BUCKET)"
      fi
      TENANTS_WITH_STORAGE+=("$TENANT")
    else
      if [ "$VERBOSE" = true ]; then
        echo "Storage bucket configured: $STORAGE_BUCKET"
        echo "Bucket exists: No (ERROR)"
      else
        echo "ERROR (bucket $STORAGE_BUCKET does not exist)"
      fi
      TENANTS_WITH_ISSUES+=("$TENANT")
    fi
  else
    if [ "$VERBOSE" = true ]; then
      echo "No storage bucket configured"
    else
      echo "MISSING STORAGE"
    fi
    TENANTS_WITHOUT_STORAGE+=("$TENANT")
  fi
  
  if [ "$VERBOSE" = true ]; then
    echo ""
  fi
done

# Print summary
echo ""
echo "=== Storage Configuration Summary ==="
echo "Total tenants: ${#TENANTS[@]}"
echo "Tenants with storage: ${#TENANTS_WITH_STORAGE[@]}"
echo "Tenants without storage: ${#TENANTS_WITHOUT_STORAGE[@]}"
echo "Tenants with issues: ${#TENANTS_WITH_ISSUES[@]}"
echo ""

if [ ${#TENANTS_WITHOUT_STORAGE[@]} -gt 0 ]; then
  echo "Tenants without storage:"
  for TENANT in "${TENANTS_WITHOUT_STORAGE[@]}"; do
    echo "  - $TENANT"
  done
  echo ""
  echo "To configure storage for these tenants, run:"
  echo "./scripts/configure-tenant-storage.sh --project $PROJECT_ID --tenant TENANT_NAME"
fi

if [ ${#TENANTS_WITH_ISSUES[@]} -gt 0 ]; then
  echo "Tenants with issues:"
  for TENANT in "${TENANTS_WITH_ISSUES[@]}"; do
    echo "  - $TENANT"
  done
  echo ""
  echo "These tenants have configuration issues that need manual investigation."
fi 