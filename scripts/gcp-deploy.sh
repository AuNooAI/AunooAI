#!/bin/bash

# AunooAI GCP Multi-Tenant Deployment Script
# -----------------------------------------

set -e  # Exit on error

# Default configuration
PROJECT_ID=""
REGION="us-central1"
TENANT="tenant1"
ADMIN_PASSWORD="admin"
PORT="8080"
USE_SUDO_FOR_DOCKER=false

# Check if user has Docker permissions
if ! docker info &>/dev/null; then
  # For snap-based Docker installations
  if command -v snap &>/dev/null && snap list docker &>/dev/null; then
    echo "Docker is installed via snap. Using sudo for Docker commands."
    USE_SUDO_FOR_DOCKER=true
  elif sudo docker info &>/dev/null; then
    echo "Docker requires sudo privileges. Will use sudo for Docker commands."
    USE_SUDO_FOR_DOCKER=true
  else
    echo "Error: Docker is not running or you don't have permissions to use it."
    echo "Please make sure Docker is installed and running, and you have the necessary permissions."
    echo "If you're using snap-based Docker, the script will automatically use sudo."
    exit 1
  fi
fi

# Handle sudo execution by preserving the actual user's HOME
if [ -n "$SUDO_USER" ]; then
  echo "Running with sudo. Using $SUDO_USER's gcloud configuration..."
  REAL_USER_HOME=$(eval echo ~$SUDO_USER)
  export CLOUDSDK_CONFIG="$REAL_USER_HOME/.config/gcloud"
fi

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
    --admin-password)
      ADMIN_PASSWORD="$2"
      shift 2
      ;;
    --port)
      PORT="$2"
      shift 2
      ;;
    --help)
      echo "Usage: $0 --project PROJECT_ID [--region REGION] [--tenant TENANT_NAME] [--admin-password PASSWORD] [--port PORT]"
      echo ""
      echo "Options:"
      echo "  --project ID         GCP Project ID (required)"
      echo "  --region REGION      GCP Region (default: us-central1)"
      echo "  --tenant NAME        Tenant name (default: tenant1)"
      echo "  --admin-password PWD Admin password (default: admin)"
      echo "  --port PORT          Container port (default: 8080)"
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

# Display configuration
echo "=== AunooAI GCP Deployment ==="
echo "Project ID: $PROJECT_ID"
echo "Region: $REGION"
echo "Tenant: $TENANT"
echo "Admin Password: [REDACTED]"
echo "Port: $PORT"
echo "============================"

# Ensure gcloud is authenticated
echo "Checking authentication..."
if ! gcloud auth list --format="value(account)" 2>/dev/null | grep -q "@"; then
  echo "You need to authenticate with gcloud first."
  echo "Run: gcloud auth login"
  exit 1
fi

# Configure gcloud
echo "Configuring gcloud..."
gcloud config set project $PROJECT_ID

# Enable required APIs
echo "Enabling required GCP APIs..."
gcloud services enable artifactregistry.googleapis.com containerregistry.googleapis.com run.googleapis.com storage-api.googleapis.com

# Authenticate Docker for GCR
echo "Configuring Docker authentication for Google Container Registry..."
gcloud auth configure-docker gcr.io --quiet

# Ensure the user has required permissions
echo "Verifying and granting required permissions..."
EMAIL=$(gcloud auth list --format="value(account)" 2>/dev/null | head -1)
if [ -n "$EMAIL" ]; then
  # Grant the user Artifact Registry Writer role if they don't have it
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="user:$EMAIL" \
    --role="roles/artifactregistry.writer" > /dev/null 2>&1 || true
    
  # Also grant the Storage Admin role which is needed for bucket operations
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="user:$EMAIL" \
    --role="roles/storage.admin" > /dev/null 2>&1 || true
    
  # Grant Container Registry Writer role for backward compatibility
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="user:$EMAIL" \
    --role="roles/containerregistry.ServiceAgent" > /dev/null 2>&1 || true
fi

# Create a temporary Docker config to force a fresh authentication
mkdir -p ~/.docker
cat > ~/.docker/config.json <<EOF
{
  "credHelpers": {
    "gcr.io": "gcloud"
  }
}
EOF

# For older Docker versions, we should also refresh the credential helper
if [ -f ~/.docker/config.json ]; then
  if [ "$USE_SUDO_FOR_DOCKER" = true ]; then
    # If using sudo for Docker, we need to make sure root has the same Docker config
    sudo mkdir -p /root/.docker
    sudo cp ~/.docker/config.json /root/.docker/
    
    # Get the access token without sudo first, then pass it to sudo docker login
    ACCESS_TOKEN=$(gcloud auth print-access-token)
    echo "$ACCESS_TOKEN" | sudo docker login -u oauth2accesstoken --password-stdin https://gcr.io
  else
    gcloud auth print-access-token | docker login -u oauth2accesstoken --password-stdin https://gcr.io
  fi
fi

# Create Cloud Storage bucket for tenant data
BUCKET_NAME="${PROJECT_ID}-aunooai-${TENANT}"
echo "Creating Cloud Storage bucket: $BUCKET_NAME"
gsutil mb -l $REGION gs://$BUCKET_NAME || echo "Bucket already exists"

# Build and tag the Docker image
IMAGE_NAME="gcr.io/$PROJECT_ID/aunooai-$TENANT"
echo "Building Docker image: $IMAGE_NAME"
if [ "$USE_SUDO_FOR_DOCKER" = true ]; then
  sudo docker build -t $IMAGE_NAME .
else
  docker build -t $IMAGE_NAME .
fi

# Push the image to Google Container Registry
echo "Pushing image to Google Container Registry..."
if [ "$USE_SUDO_FOR_DOCKER" = true ]; then
  sudo docker push $IMAGE_NAME
else
  docker push $IMAGE_NAME
fi

# Create a service account for the tenant
SA_NAME="aunooai-$TENANT-sa"
SA_EMAIL="$SA_NAME@$PROJECT_ID.iam.gserviceaccount.com"

echo "Creating service account: $SA_NAME"
gcloud iam service-accounts create $SA_NAME \
  --display-name="AunooAI $TENANT Service Account" || echo "Service account already exists"

# Grant the service account access to the bucket
echo "Granting bucket access to service account..."
gsutil iam ch serviceAccount:$SA_EMAIL:objectAdmin gs://$BUCKET_NAME

# Deploy to Cloud Run
echo "Deploying to Cloud Run..."
# Create environment variables string without PORT (which is reserved in Cloud Run)
ENV_VARS="INSTANCE=$TENANT,ADMIN_PASSWORD=$ADMIN_PASSWORD,STORAGE_BUCKET=$BUCKET_NAME"

gcloud run deploy aunooai-$TENANT \
  --image $IMAGE_NAME \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --set-env-vars="$ENV_VARS" \
  --service-account $SA_EMAIL \
  --cpu-boost \
  --min-instances=1 \
  --cpu=1 \
  --memory=1Gi \
  --timeout=300s

# Get the service URL
SERVICE_URL=$(gcloud run services describe aunooai-$TENANT --region $REGION --format="value(status.url)")

echo ""
echo "=== Deployment Complete ==="
echo "Tenant: $TENANT"
echo "Service URL: $SERVICE_URL"
echo "Admin Username: admin"
echo "Admin Password: $ADMIN_PASSWORD"
echo ""
echo "To deploy another tenant, run:"
echo "$0 --project $PROJECT_ID --tenant NEW_TENANT_NAME --admin-password SECURE_PASSWORD"
echo "" 