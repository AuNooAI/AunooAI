#!/bin/bash

# AunooAI GKE Multi-Tenant Deployment Script
# -----------------------------------------

set -e  # Exit on error

# Default configuration
PROJECT_ID=""
CLUSTER_NAME="aunooai-cluster"
REGION="us-central1"
ZONE="${REGION}-a"
TENANTS=()
ADMIN_PASSWORD="admin"
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
    --cluster)
      CLUSTER_NAME="$2"
      shift 2
      ;;
    --region)
      REGION="$2"
      ZONE="${REGION}-a"
      shift 2
      ;;
    --zone)
      ZONE="$2"
      shift 2
      ;;
    --tenant)
      TENANTS+=("$2")
      shift 2
      ;;
    --admin-password)
      ADMIN_PASSWORD="$2"
      shift 2
      ;;
    --help)
      echo "Usage: $0 --project PROJECT_ID --tenant TENANT1 [--tenant TENANT2 ...] [--region REGION] [--cluster CLUSTER_NAME] [--admin-password PASSWORD]"
      echo ""
      echo "Options:"
      echo "  --project ID         GCP Project ID (required)"
      echo "  --tenant NAME        Tenant name (can be specified multiple times)"
      echo "  --region REGION      GCP Region (default: us-central1)"
      echo "  --cluster NAME       GKE Cluster name (default: aunooai-cluster)"
      echo "  --zone ZONE          GCP Zone (default: derived from region)"
      echo "  --admin-password PWD Default admin password (default: admin)"
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

if [ ${#TENANTS[@]} -eq 0 ]; then
  echo "Error: at least one --tenant is required"
  echo "Run '$0 --help' for usage information"
  exit 1
fi

# Display configuration
echo "=== AunooAI GKE Deployment ==="
echo "Project ID: $PROJECT_ID"
echo "Region: $REGION, Zone: $ZONE"
echo "Cluster: $CLUSTER_NAME"
echo "Tenants: ${TENANTS[*]}"
echo "Admin Password: [REDACTED]"
echo "==============================="

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
gcloud services enable artifactregistry.googleapis.com containerregistry.googleapis.com container.googleapis.com storage-api.googleapis.com

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
    
  # Grant Kubernetes Engine Admin role for GKE operations
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="user:$EMAIL" \
    --role="roles/container.admin" > /dev/null 2>&1 || true
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

# Check if cluster exists, create if not
if gcloud container clusters list --region $REGION --filter="name=$CLUSTER_NAME" | grep -q $CLUSTER_NAME; then
  echo "Cluster $CLUSTER_NAME already exists"
else
  echo "Creating GKE cluster $CLUSTER_NAME..."
  gcloud container clusters create $CLUSTER_NAME \
    --region $REGION \
    --num-nodes=1 \
    --machine-type=e2-standard-2
fi

# Get credentials for the cluster
echo "Fetching cluster credentials..."
gcloud container clusters get-credentials $CLUSTER_NAME --region $REGION

# Build the Docker image
IMAGE_NAME="gcr.io/$PROJECT_ID/aunooai"
echo "Building Docker image: $IMAGE_NAME"
if [ "$USE_SUDO_FOR_DOCKER" = true ]; then
  sudo docker build -f Dockerfile.gcp -t $IMAGE_NAME .
else
  docker build -f Dockerfile.gcp -t $IMAGE_NAME .
fi

# Push the image to Google Container Registry
echo "Pushing image to Google Container Registry..."
if [ "$USE_SUDO_FOR_DOCKER" = true ]; then
  sudo docker push $IMAGE_NAME
else
  docker push $IMAGE_NAME
fi

# Create a namespace for AunooAI if it doesn't exist
if ! kubectl get namespace aunooai &> /dev/null; then
  echo "Creating kubernetes namespace: aunooai"
  kubectl create namespace aunooai
fi

# Deploy each tenant
for TENANT in "${TENANTS[@]}"; do
  echo "=== Deploying tenant: $TENANT ==="
  
  # Create bucket for tenant data
  BUCKET_NAME="${PROJECT_ID}-aunooai-${TENANT}"
  echo "Creating Cloud Storage bucket: $BUCKET_NAME"
  gsutil mb -l $REGION gs://$BUCKET_NAME || echo "Bucket already exists"
  
  # Create service account for the tenant
  SA_NAME="aunooai-$TENANT-sa"
  SA_EMAIL="$SA_NAME@$PROJECT_ID.iam.gserviceaccount.com"
  
  echo "Creating service account: $SA_NAME"
  gcloud iam service-accounts create $SA_NAME \
    --display-name="AunooAI $TENANT Service Account" || echo "Service account already exists"
  
  # Create and download key for service account
  SA_KEY_FILE="${SA_NAME}-key.json"
  echo "Creating service account key..."
  gcloud iam service-accounts keys create $SA_KEY_FILE \
    --iam-account=$SA_EMAIL
  
  # Grant the service account access to the bucket
  echo "Granting bucket access to service account..."
  gsutil iam ch serviceAccount:$SA_EMAIL:objectAdmin gs://$BUCKET_NAME
  
  # Create Kubernetes secret from service account key
  echo "Creating Kubernetes secret for service account..."
  kubectl create secret generic $SA_NAME-key \
    --namespace=aunooai \
    --from-file=key.json=$SA_KEY_FILE \
    --dry-run=client -o yaml | kubectl apply -f -
  
  # Remove the key file
  rm $SA_KEY_FILE
  
  # Create deployment YAML
  cat > ${TENANT}-deployment.yaml <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: aunooai-${TENANT}
  namespace: aunooai
spec:
  replicas: 1
  selector:
    matchLabels:
      app: aunooai
      tenant: ${TENANT}
  template:
    metadata:
      labels:
        app: aunooai
        tenant: ${TENANT}
    spec:
      containers:
      - name: aunooai
        image: ${IMAGE_NAME}
        ports:
        - containerPort: 8080
        env:
        - name: CONTAINER_PORT
          value: "8080"
        - name: INSTANCE
          value: "${TENANT}"
        - name: ADMIN_PASSWORD
          value: "${ADMIN_PASSWORD}"
        - name: STORAGE_BUCKET
          value: "${BUCKET_NAME}"
        - name: GOOGLE_APPLICATION_CREDENTIALS
          value: /var/secrets/google/key.json
        volumeMounts:
        - name: google-cloud-key
          mountPath: /var/secrets/google
      volumes:
      - name: google-cloud-key
        secret:
          secretName: ${SA_NAME}-key
---
apiVersion: v1
kind: Service
metadata:
  name: aunooai-${TENANT}
  namespace: aunooai
spec:
  selector:
    app: aunooai
    tenant: ${TENANT}
  ports:
  - port: 80
    targetPort: 8080
  type: ClusterIP
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: aunooai-${TENANT}
  namespace: aunooai
  annotations:
    kubernetes.io/ingress.class: "gce"
spec:
  rules:
  - host: ${TENANT}.aunooai.${PROJECT_ID}.cloud.goog
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: aunooai-${TENANT}
            port:
              number: 80
EOF

  # Apply the deployment
  echo "Applying Kubernetes deployment for tenant: $TENANT"
  kubectl apply -f ${TENANT}-deployment.yaml
  
  # Clean up deployment file
  rm ${TENANT}-deployment.yaml
  
  echo "Tenant $TENANT deployed at https://${TENANT}.aunooai.${PROJECT_ID}.cloud.goog"
  echo ""
done

echo "=== Multi-tenant Deployment Complete ==="
echo "Tenants deployed:"
for TENANT in "${TENANTS[@]}"; do
  echo "- $TENANT: https://${TENANT}.aunooai.${PROJECT_ID}.cloud.goog"
done
echo ""
echo "Admin credentials for each tenant:"
echo "Username: admin"
echo "Password: $ADMIN_PASSWORD"
echo ""
echo "To add more tenants, run:"
echo "$0 --project $PROJECT_ID --tenant NEW_TENANT_NAME --admin-password SECURE_PASSWORD"
echo "" 