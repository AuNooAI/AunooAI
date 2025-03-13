#!/bin/bash
# Script to update existing Cloud Run deployments with improved resource settings and data persistence

set -e

# Default values
REGION="us-central1"
CPU="2"
MEMORY="4Gi"
MIN_INSTANCES="1"
MAX_INSTANCES="10"
CONCURRENCY="80"
TIMEOUT="600s"

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
    --cpu)
      CPU="$2"
      shift 2
      ;;
    --memory)
      MEMORY="$2"
      shift 2
      ;;
    --min-instances)
      MIN_INSTANCES="$2"
      shift 2
      ;;
    --max-instances)
      MAX_INSTANCES="$2"
      shift 2
      ;;
    --concurrency)
      CONCURRENCY="$2"
      shift 2
      ;;
    --timeout)
      TIMEOUT="$2"
      shift 2
      ;;
    --all-tenants)
      ALL_TENANTS=true
      shift
      ;;
    --help)
      echo "Usage: $0 --project PROJECT_ID [--region REGION] [--tenant TENANT_NAME | --all-tenants] [--cpu CPU] [--memory MEMORY] [--min-instances MIN] [--max-instances MAX] [--concurrency CONCURRENCY] [--timeout TIMEOUT]"
      echo ""
      echo "Options:"
      echo "  --project ID         GCP Project ID (required)"
      echo "  --region REGION      GCP Region (default: us-central1)"
      echo "  --tenant NAME        Tenant name to update"
      echo "  --all-tenants        Update all tenants in the project"
      echo "  --cpu CPU            CPU cores (default: 2)"
      echo "  --memory MEMORY      Memory allocation (default: 4Gi)"
      echo "  --min-instances MIN  Minimum instances (default: 1)"
      echo "  --max-instances MAX  Maximum instances (default: 10)"
      echo "  --concurrency CONC   Request concurrency (default: 80)"
      echo "  --timeout TIMEOUT    Request timeout (default: 600s)"
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

if [ -z "$TENANT" ] && [ "$ALL_TENANTS" != "true" ]; then
  echo "Error: Either --tenant or --all-tenants is required"
  echo "Run '$0 --help' for usage information"
  exit 1
fi

# Configure gcloud
echo "Configuring gcloud..."
gcloud config set project $PROJECT_ID

# Function to update a single tenant
update_tenant() {
  local tenant=$1
  echo "=== Updating tenant: $tenant ==="
  
  # Get current service configuration
  echo "Getting current configuration for aunooai-$tenant..."
  local current_env_vars=$(gcloud run services describe aunooai-$tenant --region $REGION --format="value(spec.template.spec.containers[0].env)" 2>/dev/null || echo "")
  
  if [ -z "$current_env_vars" ]; then
    echo "Error: Service aunooai-$tenant not found in region $REGION"
    return 1
  fi
  
  # Extract environment variables - improved parsing
  local instance=""
  local admin_password=""
  local storage_bucket=""
  
  # Read each environment variable
  while IFS= read -r line; do
    if [[ "$line" =~ \'name\':\ \'INSTANCE\',\ \'value\':\ \'([^\']*)\' ]]; then
      instance="${BASH_REMATCH[1]}"
    elif [[ "$line" =~ \'name\':\ \'ADMIN_PASSWORD\',\ \'value\':\ \'([^\']*)\' ]]; then
      admin_password="${BASH_REMATCH[1]}"
    elif [[ "$line" =~ \'name\':\ \'STORAGE_BUCKET\',\ \'value\':\ \'([^\']*)\' ]]; then
      storage_bucket="${BASH_REMATCH[1]}"
    fi
  done <<< "$current_env_vars"
  
  # Fallback to alternative method if the above didn't work
  if [ -z "$instance" ]; then
    instance=$(echo "$current_env_vars" | grep -o "'name': 'INSTANCE', 'value': '[^']*'" | grep -o "'value': '[^']*'" | cut -d"'" -f4)
  fi
  if [ -z "$admin_password" ]; then
    admin_password=$(echo "$current_env_vars" | grep -o "'name': 'ADMIN_PASSWORD', 'value': '[^']*'" | grep -o "'value': '[^']*'" | cut -d"'" -f4)
  fi
  if [ -z "$storage_bucket" ]; then
    storage_bucket=$(echo "$current_env_vars" | grep -o "'name': 'STORAGE_BUCKET', 'value': '[^']*'" | grep -o "'value': '[^']*'" | cut -d"'" -f4)
  fi
  
  # Debug output
  echo "Detected environment variables:"
  echo "  INSTANCE: $instance"
  echo "  ADMIN_PASSWORD: [REDACTED]"
  echo "  STORAGE_BUCKET: $storage_bucket"
  
  if [ -z "$storage_bucket" ]; then
    echo "Warning: No STORAGE_BUCKET found for aunooai-$tenant. Data persistence may not be configured."
    echo "Run ./scripts/configure-tenant-storage.sh --project $PROJECT_ID --tenant $tenant to configure storage."
    return 1
  fi
  
  # Get current image
  local current_image=$(gcloud run services describe aunooai-$tenant --region $REGION --format="value(spec.template.spec.containers[0].image)" 2>/dev/null)
  
  # Get service account
  local service_account=$(gcloud run services describe aunooai-$tenant --region $REGION --format="value(spec.template.spec.serviceAccountName)" 2>/dev/null)
  
  echo "Current configuration:"
  echo "  Instance: $instance"
  echo "  Storage Bucket: $storage_bucket"
  echo "  Image: $current_image"
  echo "  Service Account: $service_account"
  
  # Update the Cloud Run service
  echo "Updating Cloud Run service with new resource settings..."
  gcloud run services update aunooai-$tenant \
    --region $REGION \
    --cpu-boost \
    --min-instances=$MIN_INSTANCES \
    --max-instances=$MAX_INSTANCES \
    --cpu=$CPU \
    --memory=$MEMORY \
    --timeout=$TIMEOUT \
    --concurrency=$CONCURRENCY
  
  echo "Tenant $tenant updated successfully!"
  echo ""
}

# Update tenants
if [ "$ALL_TENANTS" = "true" ]; then
  echo "Updating all tenants in project $PROJECT_ID..."
  
  # Get all Cloud Run services that start with aunooai-
  TENANTS=$(gcloud run services list --region $REGION --format="value(metadata.name)" | grep "^aunooai-" | sed 's/^aunooai-//')
  
  if [ -z "$TENANTS" ]; then
    echo "No AunooAI tenants found in project $PROJECT_ID, region $REGION"
    exit 1
  fi
  
  echo "Found tenants: $TENANTS"
  
  for tenant in $TENANTS; do
    update_tenant $tenant
  done
else
  update_tenant $TENANT
fi

echo "=== Update Complete ==="
echo "Updated with the following resource settings:"
echo "  CPU: $CPU"
echo "  Memory: $MEMORY"
echo "  Min Instances: $MIN_INSTANCES"
echo "  Max Instances: $MAX_INSTANCES"
echo "  Concurrency: $CONCURRENCY"
echo "  Timeout: $TIMEOUT"
echo ""
echo "Note: To apply the data persistence improvements, you need to rebuild and redeploy the Docker image."
echo "Run: ./scripts/gcp-deploy.sh --project $PROJECT_ID --tenant [TENANT_NAME] --admin-password [PASSWORD]" 