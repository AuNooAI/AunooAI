# AunooAI GCP Deployment Quick Reference

This quick reference guide provides common commands and procedures for deploying and managing AunooAI on Google Cloud Platform.

## Initial Setup

### Authentication
```bash
# Login to Google Cloud
gcloud auth login

# Configure Docker for GCR
gcloud auth configure-docker gcr.io
```

### Project Configuration
```bash
# Set project
gcloud config set project YOUR_PROJECT_ID

# Enable required APIs
gcloud services enable artifactregistry.googleapis.com containerregistry.googleapis.com run.googleapis.com storage-api.googleapis.com
```

## Deployment Commands

### Deploy New Tenant
```bash
# Basic deployment
./scripts/deploy-to-cloud-run.sh --project YOUR_PROJECT_ID --tenant TENANT_NAME --admin-password PASSWORD --disable-ssl true

# Deployment with custom resources
./scripts/deploy-to-cloud-run.sh --project YOUR_PROJECT_ID --tenant TENANT_NAME --admin-password PASSWORD --memory 8Gi --cpu 4 --min-instances 2 --disable-ssl true

# Deployment with LiteLLM configuration
./scripts/deploy-to-cloud-run.sh --project YOUR_PROJECT_ID --tenant TENANT_NAME --admin-password PASSWORD --openai-api-key "your-key" --anthropic-api-key "your-key" --google-api-key "your-key" --disable-ssl true

# Deployment with custom startup probe settings
./scripts/deploy-to-cloud-run.sh --project YOUR_PROJECT_ID --tenant TENANT_NAME --admin-password PASSWORD --startup-timeout 300s --startup-period 10s --startup-failure-threshold 30 --disable-ssl true
```

### Update Existing Tenant
```bash
# Update deployment with same parameters
./scripts/deploy-to-cloud-run.sh --project YOUR_PROJECT_ID --tenant TENANT_NAME --admin-password PASSWORD

# Update specific resources
gcloud run services update aunooai-TENANT_NAME --region REGION --memory 8Gi --cpu 4
```

### Add Storage to Existing Tenant
```bash
# Configure storage for a specific tenant
./scripts/configure-tenant-storage.sh --project YOUR_PROJECT_ID --tenant TENANT_NAME

# Configure storage for all tenants
./scripts/configure-tenant-storage.sh --project YOUR_PROJECT_ID
```

### Add Volume Mounts to Existing Tenant
```bash
# Add volume mounts for a specific tenant
./scripts/add-volume-mounts-to-cloud-run.sh --project YOUR_PROJECT_ID --tenant TENANT_NAME

# Add volume mounts for all tenants
./scripts/add-volume-mounts-to-cloud-run.sh --project YOUR_PROJECT_ID
```

## Monitoring and Management

### View Service Information
```bash
# Get service details
gcloud run services describe aunooai-TENANT_NAME --region REGION

# List all services
gcloud run services list --region REGION
```

### View Logs
```bash
# View recent logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=aunooai-TENANT_NAME" --limit=50

# View error logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=aunooai-TENANT_NAME AND severity>=ERROR" --limit=20
```

### Manage Revisions
```bash
# List revisions
gcloud run revisions list --service aunooai-TENANT_NAME --region REGION

# Delete old revisions
gcloud run revisions delete REVISION_NAME --region REGION
```

## Storage Management

### Bucket Operations
```bash
# List buckets
gsutil ls

# View bucket contents
gsutil ls -r gs://YOUR_PROJECT_ID-aunooai-TENANT_NAME/

# Copy data to bucket
gsutil cp LOCAL_FILE gs://YOUR_PROJECT_ID-aunooai-TENANT_NAME/

# Download data from bucket
gsutil cp gs://YOUR_PROJECT_ID-aunooai-TENANT_NAME/FILE LOCAL_DESTINATION
```

### Bucket Permissions
```bash
# View bucket permissions
gsutil iam get gs://YOUR_PROJECT_ID-aunooai-TENANT_NAME/

# Grant permissions to service account
gsutil iam ch serviceAccount:SERVICE_ACCOUNT_EMAIL:objectAdmin gs://YOUR_PROJECT_ID-aunooai-TENANT_NAME/
```

## Service Account Management

### Create Service Account
```bash
# Create service account
gcloud iam service-accounts create aunooai-TENANT_NAME-sa --display-name="AunooAI TENANT_NAME Service Account"
```

### Manage Service Account Permissions
```bash
# Grant Storage Admin role
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID --member="serviceAccount:aunooai-TENANT_NAME-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com" --role="roles/storage.admin"

# List service account roles
gcloud projects get-iam-policy YOUR_PROJECT_ID --flatten="bindings[].members" --format="table(bindings.role)" --filter="bindings.members:aunooai-TENANT_NAME-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com"
```

## Troubleshooting

### Common Issues

#### SSL Redirect Loop
```bash
# Fix SSL redirect loop by disabling SSL in the application
gcloud run services update aunooai-TENANT_NAME --region REGION --set-env-vars=DISABLE_SSL=true
```

#### Startup Probe Failures
```bash
# For applications that take longer to start (especially with LiteLLM)
# Adjust startup probe parameters
gcloud run services update aunooai-TENANT_NAME --region REGION --startup-probe=tcp:port=8080,initial-delay=5s,timeout=300s,period=10s,failure-threshold=30

# Or remove startup probe for initial deployment
gcloud run deploy aunooai-TENANT_NAME --image IMAGE_URL --no-startup-probe --region REGION
```

#### LiteLLM Configuration
```bash
# Update service with LiteLLM API keys
gcloud run services update aunooai-TENANT_NAME --region REGION --set-env-vars=OPENAI_API_KEY=your-key,ANTHROPIC_API_KEY=your-key,GOOGLE_API_KEY=your-key
```

### Check Service Status
```bash
# Check service status
gcloud run services describe aunooai-TENANT_NAME --region REGION --format="value(status)"
```

### Check Container Logs
```bash
# View container startup logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=aunooai-TENANT_NAME AND textPayload:Starting" --limit=10

# View error logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=aunooai-TENANT_NAME AND severity>=ERROR" --limit=20

# Check for healthcheck errors
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=aunooai-TENANT_NAME AND textPayload:'HealthCheckContainerError'" --limit=10
```

### Test Service Connectivity
```bash
# Get service URL
SERVICE_URL=$(gcloud run services describe aunooai-TENANT_NAME --region REGION --format="value(status.url)")

# Test connectivity
curl -v $SERVICE_URL
```

### Restart Service
```bash
# Force new deployment (restart)
gcloud run services update aunooai-TENANT_NAME --region REGION --no-traffic
gcloud run services update aunooai-TENANT_NAME --region REGION --to-latest
```

## Cleanup

### Delete Service
```bash
# Delete Cloud Run service
gcloud run services delete aunooai-TENANT_NAME --region REGION
```

### Delete Storage Bucket
```bash
# Delete bucket and all contents
gsutil rm -r gs://YOUR_PROJECT_ID-aunooai-TENANT_NAME/
```

### Delete Service Account
```bash
# Delete service account
gcloud iam service-accounts delete aunooai-TENANT_NAME-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com
```