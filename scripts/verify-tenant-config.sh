#!/bin/bash
# Script to verify and fix tenant configuration, focusing on environment variables

set -e

# Default values
REGION="us-central1"
FIX_ISSUES=false

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
    --fix)
      FIX_ISSUES=true
      shift
      ;;
    --help)
      echo "Usage: $0 --project PROJECT_ID --tenant TENANT_NAME [--region REGION] [--fix]"
      echo ""
      echo "Options:"
      echo "  --project ID         GCP Project ID (required)"
      echo "  --region REGION      GCP Region (default: us-central1)"
      echo "  --tenant NAME        Tenant name to verify (required)"
      echo "  --fix                Fix issues automatically"
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

if [ -z "$TENANT" ]; then
  echo "Error: --tenant is required"
  echo "Run '$0 --help' for usage information"
  exit 1
fi

# Configure gcloud
echo "Configuring gcloud..."
gcloud config set project $PROJECT_ID

# Check if tenant exists
echo "Checking if tenant exists..."
if ! gcloud run services describe aunooai-$TENANT --region $REGION &>/dev/null; then
  echo "Error: Service aunooai-$TENANT not found in region $REGION"
  exit 1
fi

# Get current configuration
echo "Getting current configuration for aunooai-$TENANT..."
CURRENT_ENV_VARS=$(gcloud run services describe aunooai-$TENANT --region $REGION --format="value(spec.template.spec.containers[0].env)")
CURRENT_IMAGE=$(gcloud run services describe aunooai-$TENANT --region $REGION --format="value(spec.template.spec.containers[0].image)")
SERVICE_ACCOUNT=$(gcloud run services describe aunooai-$TENANT --region $REGION --format="value(spec.template.spec.serviceAccountName)")

echo "Raw environment variables:"
echo "$CURRENT_ENV_VARS"
echo ""

# Extract environment variables using multiple methods
INSTANCE=""
ADMIN_PASSWORD=""
STORAGE_BUCKET=""

# Method 1: Parse using jq-like syntax for the specific format
while IFS= read -r line; do
  if [[ "$line" =~ \'name\':\ \'INSTANCE\',\ \'value\':\ \'([^\']*)\' ]]; then
    INSTANCE="${BASH_REMATCH[1]}"
    echo "Found INSTANCE: $INSTANCE"
  elif [[ "$line" =~ \'name\':\ \'ADMIN_PASSWORD\',\ \'value\':\ \'([^\']*)\' ]]; then
    ADMIN_PASSWORD="${BASH_REMATCH[1]}"
    echo "Found ADMIN_PASSWORD"
  elif [[ "$line" =~ \'name\':\ \'STORAGE_BUCKET\',\ \'value\':\ \'([^\']*)\' ]]; then
    STORAGE_BUCKET="${BASH_REMATCH[1]}"
    echo "Found STORAGE_BUCKET: $STORAGE_BUCKET"
  fi
done <<< "$CURRENT_ENV_VARS"

# Alternative parsing method
if [ -z "$INSTANCE" ]; then
  INSTANCE=$(echo "$CURRENT_ENV_VARS" | grep -o "'name': 'INSTANCE', 'value': '[^']*'" | grep -o "'value': '[^']*'" | cut -d"'" -f4)
  echo "Found INSTANCE (alt method): $INSTANCE"
fi

if [ -z "$ADMIN_PASSWORD" ]; then
  ADMIN_PASSWORD=$(echo "$CURRENT_ENV_VARS" | grep -o "'name': 'ADMIN_PASSWORD', 'value': '[^']*'" | grep -o "'value': '[^']*'" | cut -d"'" -f4)
  if [ -n "$ADMIN_PASSWORD" ]; then
    echo "Found ADMIN_PASSWORD (alt method)"
  fi
fi

if [ -z "$STORAGE_BUCKET" ]; then
  STORAGE_BUCKET=$(echo "$CURRENT_ENV_VARS" | grep -o "'name': 'STORAGE_BUCKET', 'value': '[^']*'" | grep -o "'value': '[^']*'" | cut -d"'" -f4)
  echo "Found STORAGE_BUCKET (alt method): $STORAGE_BUCKET"
fi

# If INSTANCE is still not set, use the tenant name
if [ -z "$INSTANCE" ]; then
  INSTANCE=$TENANT
  echo "INSTANCE not found, using tenant name: $INSTANCE"
fi

echo ""
echo "=== Configuration Summary ==="
echo "Tenant: $TENANT"
echo "Instance: $INSTANCE"
echo "Admin Password: [REDACTED]"
echo "Storage Bucket: $STORAGE_BUCKET"
echo "Service Account: $SERVICE_ACCOUNT"
echo "Image: $CURRENT_IMAGE"
echo ""

# Check for issues
ISSUES_FOUND=false

if [ -z "$STORAGE_BUCKET" ]; then
  echo "ISSUE: No STORAGE_BUCKET environment variable found"
  ISSUES_FOUND=true
  
  # Check if a bucket exists that we could use
  EXPECTED_BUCKET="${PROJECT_ID}-aunooai-${TENANT}"
  if gsutil ls -b gs://$EXPECTED_BUCKET &>/dev/null; then
    echo "Found existing bucket that could be used: $EXPECTED_BUCKET"
    STORAGE_BUCKET=$EXPECTED_BUCKET
  fi
else
  # Check if the bucket exists
  if ! gsutil ls -b gs://$STORAGE_BUCKET &>/dev/null; then
    echo "ISSUE: Storage bucket $STORAGE_BUCKET does not exist"
    ISSUES_FOUND=true
  fi
fi

if [ -z "$SERVICE_ACCOUNT" ]; then
  echo "ISSUE: No service account configured"
  ISSUES_FOUND=true
fi

# Fix issues if requested
if [ "$ISSUES_FOUND" = true ] && [ "$FIX_ISSUES" = true ]; then
  echo ""
  echo "=== Fixing Issues ==="
  
  # Create bucket if needed
  if [ -n "$STORAGE_BUCKET" ] && ! gsutil ls -b gs://$STORAGE_BUCKET &>/dev/null; then
    echo "Creating bucket: $STORAGE_BUCKET"
    gsutil mb -l $REGION gs://$STORAGE_BUCKET || echo "Failed to create bucket"
  elif [ -z "$STORAGE_BUCKET" ]; then
    STORAGE_BUCKET="${PROJECT_ID}-aunooai-${TENANT}"
    echo "Creating bucket: $STORAGE_BUCKET"
    gsutil mb -l $REGION gs://$STORAGE_BUCKET || echo "Failed to create bucket"
  fi
  
  # Create service account if needed
  if [ -z "$SERVICE_ACCOUNT" ]; then
    SA_NAME="aunooai-$TENANT-sa"
    SA_EMAIL="$SA_NAME@$PROJECT_ID.iam.gserviceaccount.com"
    
    echo "Creating service account: $SA_NAME"
    gcloud iam service-accounts create $SA_NAME \
      --display-name="AunooAI $TENANT Service Account" || echo "Service account already exists"
    
    SERVICE_ACCOUNT=$SA_EMAIL
  else
    SA_EMAIL=$SERVICE_ACCOUNT
  fi
  
  # Grant bucket access to service account
  echo "Granting bucket access to service account..."
  gsutil iam ch serviceAccount:$SA_EMAIL:objectAdmin gs://$STORAGE_BUCKET
  
  # Update environment variables
  echo "Updating environment variables..."
  ENV_VARS="INSTANCE=$INSTANCE,STORAGE_BUCKET=$STORAGE_BUCKET"
  
  # Add ADMIN_PASSWORD if it exists
  if [ -n "$ADMIN_PASSWORD" ]; then
    ENV_VARS="$ENV_VARS,ADMIN_PASSWORD=$ADMIN_PASSWORD"
  fi
  
  # Update the Cloud Run service
  echo "Updating Cloud Run service..."
  gcloud run services update aunooai-$TENANT \
    --region $REGION \
    --set-env-vars="$ENV_VARS" \
    --service-account $SERVICE_ACCOUNT
  
  echo ""
  echo "=== Fixes Applied ==="
  echo "Tenant: $TENANT"
  echo "Instance: $INSTANCE"
  echo "Storage Bucket: $STORAGE_BUCKET"
  echo "Service Account: $SERVICE_ACCOUNT"
  echo ""
  echo "To apply the data persistence improvements, you need to rebuild and redeploy the Docker image."
  echo "Run: ./scripts/gcp-deploy.sh --project $PROJECT_ID --tenant $TENANT --admin-password [PASSWORD]"
elif [ "$ISSUES_FOUND" = true ]; then
  echo ""
  echo "Issues were found but not fixed. Run with --fix to apply fixes."
else
  echo "No issues found. Configuration looks good!"
fi 