#!/bin/bash

# AunooAI GCP Authentication Setup Script
# ---------------------------------------

set -e  # Exit on error

# Handle sudo execution by preserving the actual user's HOME
if [ -n "$SUDO_USER" ]; then
  echo "Running with sudo. Using $SUDO_USER's gcloud configuration..."
  REAL_USER_HOME=$(eval echo ~$SUDO_USER)
  export CLOUDSDK_CONFIG="$REAL_USER_HOME/.config/gcloud"
fi

# Default configuration
SA_KEY_FILE=""
PROJECT_ID=""

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  key="$1"
  case $key in
    --key-file)
      SA_KEY_FILE="$2"
      shift 2
      ;;
    --project)
      PROJECT_ID="$2"
      shift 2
      ;;
    --help)
      echo "Usage: $0 --key-file SERVICE_ACCOUNT_KEY_FILE [--project PROJECT_ID]"
      echo ""
      echo "Options:"
      echo "  --key-file FILE    Path to service account key JSON file (required)"
      echo "  --project ID       GCP Project ID (if not specified, extracted from key file)"
      echo ""
      echo "This script configures authentication for GCP using a service account key file."
      echo "It's particularly useful for CI/CD environments."
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
if [ -z "$SA_KEY_FILE" ]; then
  echo "Error: --key-file is required"
  echo "Run '$0 --help' for usage information"
  exit 1
fi

# Check if the key file exists
if [ ! -f "$SA_KEY_FILE" ]; then
  echo "Error: Key file '$SA_KEY_FILE' not found"
  exit 1
fi

# Display confirmation
echo "=== AunooAI GCP Authentication Setup ==="
echo "Service Account Key File: $SA_KEY_FILE"

# Extract project ID from key file if not provided
if [ -z "$PROJECT_ID" ]; then
  if ! command -v jq &> /dev/null; then
    echo "Warning: 'jq' is not installed. Cannot extract project ID from key file."
    echo "Please install jq or specify --project parameter."
    exit 1
  fi
  
  PROJECT_ID=$(jq -r '.project_id' "$SA_KEY_FILE")
  if [ -z "$PROJECT_ID" ] || [ "$PROJECT_ID" = "null" ]; then
    echo "Error: Could not extract project ID from key file. Please specify --project parameter."
    exit 1
  fi
  
  echo "Project ID (extracted from key file): $PROJECT_ID"
else
  echo "Project ID: $PROJECT_ID"
fi
echo "===================================="

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
  echo "Error: gcloud CLI is not installed"
  echo "Please install the Google Cloud SDK: https://cloud.google.com/sdk/docs/install"
  exit 1
fi

# Check if docker is installed
if ! command -v docker &> /dev/null; then
  echo "Warning: Docker is not installed. Container image operations will not work."
fi

# Authenticate with service account
echo "Activating service account..."
gcloud auth activate-service-account --key-file="$SA_KEY_FILE"

# Configure Docker with service account credentials for GCR
if command -v docker &> /dev/null; then
  echo "Configuring Docker authentication for Google Container Registry..."
  gcloud auth configure-docker gcr.io --quiet
  
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
    gcloud auth print-access-token | docker login -u oauth2accesstoken --password-stdin https://gcr.io
  fi
fi

# Set project in gcloud config
echo "Setting default project to: $PROJECT_ID"
gcloud config set project "$PROJECT_ID"

# Enable required APIs
echo "Enabling required GCP APIs..."
gcloud services enable artifactregistry.googleapis.com containerregistry.googleapis.com run.googleapis.com storage-api.googleapis.com container.googleapis.com

# Verify authentication
echo "Verifying authentication..."
gcloud auth list --format="value(account)" 2>/dev/null

# Ensure the service account has required permissions
echo "Verifying and granting required permissions..."
SA_EMAIL=$(gcloud auth list --format="value(account)" 2>/dev/null | head -1)
if [[ "$SA_EMAIL" == *"@"*".iam.gserviceaccount.com" ]]; then
  # Grant the service account Artifact Registry Writer role
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/artifactregistry.writer" > /dev/null 2>&1 || true
    
  # Also grant the Storage Admin role which is needed for bucket operations
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/storage.admin" > /dev/null 2>&1 || true
    
  # Grant Container Registry Writer role for backward compatibility
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/containerregistry.ServiceAgent" > /dev/null 2>&1 || true
    
  # Grant Cloud Run Admin role for Cloud Run deployments
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/run.admin" > /dev/null 2>&1 || true
    
  # Grant Kubernetes Engine Admin role for GKE deployments
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/container.admin" > /dev/null 2>&1 || true
fi

echo ""
echo "=== Authentication Setup Complete ==="
echo "Service account is now active and Docker is configured for GCR access."
echo ""
echo "You can now run the deployment scripts:"
echo "- ./scripts/gcp-deploy.sh --project $PROJECT_ID --tenant YOUR_TENANT"
echo "- ./scripts/gcp-gke-deploy.sh --project $PROJECT_ID --tenant YOUR_TENANT"
echo "" 