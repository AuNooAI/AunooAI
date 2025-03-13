#!/bin/bash
# Script to configure storage bucket for tenants that are missing it

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
      echo "Usage: $0 --project PROJECT_ID --tenant TENANT_NAME [--region REGION]"
      echo ""
      echo "Options:"
      echo "  --project ID         GCP Project ID (required)"
      echo "  --region REGION      GCP Region (default: us-central1)"
      echo "  --tenant NAME        Tenant name to configure (required)"
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

# Extract environment variables
INSTANCE=""
ADMIN_PASSWORD=""
STORAGE_BUCKET=""

# Parse using regex for the specific format
while IFS= read -r line; do
  if [[ "$line" =~ \'name\':\ \'INSTANCE\',\ \'value\':\ \'([^\']*)\' ]]; then
    INSTANCE="${BASH_REMATCH[1]}"
  elif [[ "$line" =~ \'name\':\ \'ADMIN_PASSWORD\',\ \'value\':\ \'([^\']*)\' ]]; then
    ADMIN_PASSWORD="${BASH_REMATCH[1]}"
  elif [[ "$line" =~ \'name\':\ \'STORAGE_BUCKET\',\ \'value\':\ \'([^\']*)\' ]]; then
    STORAGE_BUCKET="${BASH_REMATCH[1]}"
  fi
done <<< "$CURRENT_ENV_VARS"

# Alternative parsing method
if [ -z "$INSTANCE" ]; then
  INSTANCE=$(echo "$CURRENT_ENV_VARS" | grep -o "'name': 'INSTANCE', 'value': '[^']*'" | grep -o "'value': '[^']*'" | cut -d"'" -f4)
fi
if [ -z "$ADMIN_PASSWORD" ]; then
  ADMIN_PASSWORD=$(echo "$CURRENT_ENV_VARS" | grep -o "'name': 'ADMIN_PASSWORD', 'value': '[^']*'" | grep -o "'value': '[^']*'" | cut -d"'" -f4)
fi
if [ -z "$STORAGE_BUCKET" ]; then
  STORAGE_BUCKET=$(echo "$CURRENT_ENV_VARS" | grep -o "'name': 'STORAGE_BUCKET', 'value': '[^']*'" | grep -o "'value': '[^']*'" | cut -d"'" -f4)
fi

# If INSTANCE is not set, use the tenant name
if [ -z "$INSTANCE" ]; then
  INSTANCE=$TENANT
  echo "INSTANCE not found, using tenant name: $INSTANCE"
fi

# Check if STORAGE_BUCKET is already set
if [ -n "$STORAGE_BUCKET" ]; then
  echo "STORAGE_BUCKET is already configured: $STORAGE_BUCKET"
  echo "No changes needed."
  exit 0
fi

# Create a bucket name
BUCKET_NAME="${PROJECT_ID}-aunooai-${TENANT}"
echo "Creating Cloud Storage bucket: $BUCKET_NAME"
gsutil mb -l $REGION gs://$BUCKET_NAME || echo "Bucket already exists"

# Create or update service account if needed
if [ -z "$SERVICE_ACCOUNT" ]; then
  echo "No service account found, creating one..."
  SA_NAME="aunooai-$TENANT-sa"
  SA_EMAIL="$SA_NAME@$PROJECT_ID.iam.gserviceaccount.com"
  
  echo "Creating service account: $SA_NAME"
  gcloud iam service-accounts create $SA_NAME \
    --display-name="AunooAI $TENANT Service Account" || echo "Service account already exists"
  
  SERVICE_ACCOUNT=$SA_EMAIL
else
  echo "Using existing service account: $SERVICE_ACCOUNT"
  SA_EMAIL=$SERVICE_ACCOUNT
fi

# Grant the service account access to the bucket
echo "Granting bucket access to service account..."
gsutil iam ch serviceAccount:$SA_EMAIL:objectAdmin gs://$BUCKET_NAME

# Update environment variables
echo "Updating environment variables for aunooai-$TENANT..."
ENV_VARS="INSTANCE=$INSTANCE,STORAGE_BUCKET=$BUCKET_NAME"

# Add ADMIN_PASSWORD if it exists
if [ -n "$ADMIN_PASSWORD" ]; then
  ENV_VARS="$ENV_VARS,ADMIN_PASSWORD=$ADMIN_PASSWORD"
fi

# Update the Cloud Run service
echo "Updating Cloud Run service with storage bucket configuration..."
gcloud run services update aunooai-$TENANT \
  --region $REGION \
  --set-env-vars="$ENV_VARS" \
  --service-account $SERVICE_ACCOUNT

# Add storage bucket mount
echo "Adding storage bucket mount..."
gcloud run services update aunooai-$TENANT \
  --region $REGION \
  --mount type=cloud-storage,bucket=$BUCKET_NAME,path=/app/app/data/$INSTANCE

echo ""
echo "=== Storage Configuration Complete ==="
echo "Tenant: $TENANT"
echo "Storage Bucket: $BUCKET_NAME"
echo "Service Account: $SERVICE_ACCOUNT"
echo ""
echo "To apply the data persistence improvements, you need to rebuild and redeploy the Docker image."
echo "Run: ./scripts/gcp-deploy.sh --project $PROJECT_ID --tenant $TENANT --admin-password [PASSWORD]"
echo ""
echo "Note: If you have existing data in the tenant that you want to preserve,"
echo "you should export it before redeploying, then import it after redeployment." 