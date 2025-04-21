# AunooAI Cloud Run Deployment Guide

This document outlines the process for deploying AunooAI to Google Cloud Run, including common issues and their solutions.

## Deployment Architecture

AunooAI can be deployed to Google Cloud Platform using two primary methods:
1. **Google Cloud Run** - Serverless container platform
2. **Google Kubernetes Engine (GKE)** - Managed Kubernetes service

This guide focuses on Cloud Run deployment.

## Environment Variables

### Cloud Run Environment Variables
- `INSTANCE`: The tenant name
- `ADMIN_PASSWORD`: Initial admin password
- `STORAGE_BUCKET`: The Cloud Storage bucket for tenant data
- **Note**: `PORT` is automatically set by Cloud Run and should not be provided

### GKE Environment Variables
- `CONTAINER_PORT`: The port the application will listen on (default: 8080)
- `INSTANCE`: The tenant name
- `ADMIN_PASSWORD`: Initial admin password
- `STORAGE_BUCKET`: The Cloud Storage bucket for tenant data

## Deployment Process

### Building the Docker Image

```bash
# Build the Docker image using the GCP-specific Dockerfile
docker build -f Dockerfile.gcp -t aunooai-app:latest .

# Tag the image for Google Container Registry
docker tag aunooai-app:latest gcr.io/[PROJECT_ID]/aunooai-app:latest

# To use a specific tag (e.g., litellm)
docker tag aunooai-app:latest gcr.io/[PROJECT_ID]/aunooai-app:litellm

# Push the image to Google Container Registry
docker push gcr.io/[PROJECT_ID]/aunooai-app:latest
# Or push the specific tag
docker push gcr.io/[PROJECT_ID]/aunooai-app:litellm
```

### Deploying to Cloud Run

```bash
# Deploy to Cloud Run with default latest tag
gcloud run deploy aunooai-[TENANT] \
  --image gcr.io/[PROJECT_ID]/aunooai-app:latest \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars="INSTANCE=[TENANT],ADMIN_PASSWORD=[PASSWORD],STORAGE_BUCKET=[BUCKET],DISABLE_SSL=true"

# Deploy to Cloud Run with a specific tag (e.g., litellm)
gcloud run deploy aunooai-[TENANT] \
  --image gcr.io/[PROJECT_ID]/aunooai-app:litellm \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars="INSTANCE=[TENANT],ADMIN_PASSWORD=[PASSWORD],STORAGE_BUCKET=[BUCKET],DISABLE_SSL=true"
```

### Deploying to GKE

```bash
# Deploy to GKE using the deployment script
./scripts/gcp-deploy.sh --project [PROJECT_ID] --tenant [TENANT] --admin-password [PASSWORD]
```

### Using the Deployment Script

```bash
# Deploy with the default latest tag
./scripts/deploy-to-cloud-run.sh --project [PROJECT_ID] --tenant [TENANT] --admin-password [PASSWORD]

# Deploy with a specific tag (e.g., litellm)
./scripts/deploy-to-cloud-run.sh --project [PROJECT_ID] --tenant [TENANT] --admin-password [PASSWORD] --image-tag litellm

# Deploy with SSL disabled to avoid redirect loops
./scripts/deploy-to-cloud-run.sh --project [PROJECT_ID] --tenant [TENANT] --admin-password [PASSWORD] --disable-ssl true

# Deploy with LiteLLM API keys
./scripts/deploy-to-cloud-run.sh --project [PROJECT_ID] --tenant [TENANT] --admin-password [PASSWORD] --openai-api-key "your-key" --anthropic-api-key "your-key" --google-api-key "your-key" --disable-ssl true

# Deploy with custom startup probe settings for applications that take longer to initialize
./scripts/deploy-to-cloud-run.sh --project [PROJECT_ID] --tenant [TENANT] --admin-password [PASSWORD] --startup-timeout 300s --startup-period 10s --startup-failure-threshold 30 --disable-ssl true

# Deploy with custom object retention period for data compliance
./scripts/deploy-to-cloud-run.sh --project [PROJECT_ID] --tenant [TENANT] --admin-password [PASSWORD] --retention-period 90d --disable-ssl true
```

## Common Issues and Solutions

### 1. ModuleNotFoundError: No module named 'scripts'

**Issue**: The application fails to start due to a missing 'scripts' module, which contains database merging functionality.

**Solution**: We implemented a defensive import strategy in `app/routes/database.py`:

```python
try:
    from scripts.db_merge import DatabaseMerger
except ImportError:
    # Create a stub implementation if scripts module is not available
    class DatabaseMerger:
        def __init__(self, *args, **kwargs):
            logging.warning("Using stub DatabaseMerger (import failed)")
            
        def merge_databases(self, source_db_path):
            logging.warning(f"STUB: Would merge database from {source_db_path}")
            return True
```

This allows the application to run even when the scripts module is not available, which is appropriate for Cloud Run deployments.

### 2. PORT Environment Variable Issues

**Issue**: Cloud Run automatically sets the `PORT` environment variable, which cannot be overridden.

**Solution**: We updated the entrypoint script to handle both `PORT` and `CONTAINER_PORT`:

```bash
# PORT handling: Cloud Run sets PORT automatically and we should use that
# For Kubernetes deployments, we use CONTAINER_PORT instead
if [ -z "$PORT" ] && [ -n "$CONTAINER_PORT" ]; then
  export PORT="$CONTAINER_PORT"
  echo "Using CONTAINER_PORT value for PORT: ${PORT}"
else
  # Cloud Run will have already set PORT
  echo "Using provided PORT: ${PORT}"
fi

# Make sure PORT is set to something if neither variable was provided
export PORT="${PORT:-8080}"
```

### 3. SSL Certificate Issues

**Issue**: Cloud Run handles SSL termination, but the application was trying to use its own SSL, causing redirect loops.

**Solution**: We explicitly disable SSL in the entrypoint script and through an environment variable:

```bash
# EXPLICITLY disable SSL for Cloud Run
export DISABLE_SSL="true"
export CERT_PATH="/dev/null"
export KEY_PATH="/dev/null"
```

And when deploying, we set the `DISABLE_SSL` environment variable:

```bash
--set-env-vars="INSTANCE=[TENANT],ADMIN_PASSWORD=[PASSWORD],STORAGE_BUCKET=[BUCKET],DISABLE_SSL=true"
```

This prevents the application from attempting to redirect HTTP requests to HTTPS, which would create a redirect loop since Cloud Run already handles SSL termination.

**IMPORTANT**: Always include `--disable-ssl true` when deploying to Cloud Run to avoid infinite redirect loops. Cloud Run manages SSL termination at its edge, and the application should not attempt to redirect HTTP to HTTPS.

### 4. Startup Probe Configuration

**Issue**: The application may take longer to start than the default Cloud Run startup probe allows, especially when initializing LiteLLM.

**Solution**: If your application takes longer to start, you can adjust the startup probe parameters:

```bash
# Using the correct startup probe format for Cloud Run
gcloud run deploy aunooai-[TENANT] \
  --image gcr.io/[PROJECT_ID]/aunooai-app:latest \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars="INSTANCE=[TENANT],ADMIN_PASSWORD=[PASSWORD],STORAGE_BUCKET=[BUCKET],DISABLE_SSL=true" \
  --startup-probe=tcp:port=8080,initial-delay=5s,timeout=300s,period=10s,failure-threshold=30
```

Or using the deployment script:

```bash
./scripts/deploy-to-cloud-run.sh --project [PROJECT_ID] --tenant [TENANT] --startup-timeout 300s --startup-period 10s --startup-failure-threshold 30
```

In some cases, you may need to omit the startup probe entirely for the initial deployment, then add it later once the application is running. This is particularly important when deploying with LiteLLM, as initializing LiteLLM can take longer than the default startup probe allows.

When debugging startup issues, check the container logs:

```bash
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=aunooai-[TENANT] AND severity>=ERROR" --limit=20
```

If you see HealthCheckContainerError, try deploying without the startup probe parameters initially:

```bash
./scripts/deploy-to-cloud-run.sh --project [PROJECT_ID] --tenant [TENANT] --admin-password [PASSWORD] --disable-ssl true
```

### 5. LiteLLM API Keys Configuration

**Issue**: LiteLLM requires API keys for various model providers, which need to be passed to the Cloud Run service.

**Solution**: Pass the API keys as environment variables when deploying:

```bash
# Deploy with LiteLLM API keys
gcloud run deploy aunooai-[TENANT] \
  --image gcr.io/[PROJECT_ID]/aunooai-app:latest \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars="INSTANCE=[TENANT],ADMIN_PASSWORD=[PASSWORD],STORAGE_BUCKET=[BUCKET],DISABLE_SSL=true,OPENAI_API_KEY=[KEY],ANTHROPIC_API_KEY=[KEY],GOOGLE_API_KEY=[KEY]"
```

Or using the deployment script:

```bash
./scripts/deploy-to-cloud-run.sh --project [PROJECT_ID] --tenant [TENANT] --admin-password [PASSWORD] --openai-api-key "your-key" --anthropic-api-key "your-key" --google-api-key "your-key"
```

This ensures that LiteLLM has the necessary credentials to access the various model providers.

### 6. Data Persistence Issues

**Issue**: Tenants may lose data if the Cloud Run container is terminated abruptly before syncing data back to the Cloud Storage bucket.

**Solution**: We've implemented two mechanisms for data persistence:

1. **Cloud Storage Volume Mount**: The storage bucket is mounted directly as a volume in the Cloud Run service:

```bash
# Using the newer syntax (recommended for Cloud SDK 400+)
gcloud run services update aunooai-[TENANT] \
  --region [REGION] \
  --add-volume name=storage,type=cloud-storage,bucket=[BUCKET_NAME] \
  --add-volume-mount volume=storage,mount-path=/app/app/data/[TENANT]

# Using the beta syntax (for older Cloud SDK versions)
gcloud beta run services update aunooai-[TENANT] \
  --region [REGION] \
  --update-volume-mounts mount-path=/app/app/data/[TENANT],volume=storage \
  --update-volumes name=storage,cloud-storage-bucket=[BUCKET_NAME]

# Using the direct mount syntax (legacy)
gcloud beta run services update aunooai-[TENANT] \
  --region [REGION] \
  --mount type=cloud-storage,bucket=[BUCKET_NAME],path=/app/app/data/[TENANT]
```

This provides direct file system access to the persistent storage, ensuring that all data written to this directory is automatically persisted to Cloud Storage.

2. **Periodic Sync Backup**: As a secondary backup mechanism, we've implemented periodic data syncing in the entrypoint script:

```bash
# Set up periodic sync to bucket (every 5 minutes) and on exit
function sync_data_to_bucket() {
  echo "$(date): Syncing data to gs://${STORAGE_BUCKET}..."
  gsutil -m rsync -r /app/app/data/${INSTANCE}/ gs://${STORAGE_BUCKET}/
  echo "$(date): Sync completed"
}

# Set up exit trap
trap sync_data_to_bucket EXIT

# Start periodic sync in background
(while true; do
  sleep 300  # 5 minutes
  sync_data_to_bucket
done) &
SYNC_PID=$!
echo "Started periodic sync process (PID: $SYNC_PID)"
```

To verify that volume mounts are properly configured, check the Cloud Run service details under "Revisions" -> "Volumes". You should see a Cloud Storage bucket mounted.

If the volume mount is missing, you can add it using:

```bash
./scripts/add-volume-mounts.sh --project [PROJECT_ID] --tenant [TENANT_NAME]
```

To add volume mounts to all tenants at once:

```bash
./scripts/add-volume-mounts.sh --project [PROJECT_ID]
```

The `add-volume-mounts.sh` script will automatically detect which volume mount syntax is compatible with your Google Cloud SDK version and apply the appropriate command.

### 7. Resource Constraints

**Issue**: Default resource allocation may be insufficient for production workloads.

**Solution**: Increase CPU, memory, and concurrency settings in the Cloud Run deployment:

```bash
gcloud run deploy aunooai-$TENANT \
  --image $IMAGE_NAME \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --set-env-vars="$ENV_VARS" \
  --service-account $SA_EMAIL \
  --cpu-boost \
  --min-instances=1 \
  --max-instances=10 \
  --cpu=2 \
  --memory=4Gi \
  --timeout=600s \
  --concurrency=80
```

Recommended resource settings:
- **CPU**: 2-4 cores depending on workload
- **Memory**: 4-8 GB depending on workload
- **Min Instances**: 1-2 to ensure availability
- **Max Instances**: 10-20 to handle traffic spikes
- **Concurrency**: 80-100 for better request handling
- **Timeout**: 600s to allow for longer-running operations

### 8. Docker Authentication Issues with GCR

**Issue**: When using `

### 9. Object Retention Settings

**Issue**: By default, Cloud Storage buckets do not have object retention policies enabled. Files persist indefinitely but can be deleted at any time, which might not meet compliance or data governance requirements.

**Solution**: You can optionally set a retention policy using the `--retention-period` parameter when deploying:

```bash
# Set a 100-year retention period (effectively unlimited)
./scripts/deploy-to-cloud-run.sh --project [PROJECT_ID] --tenant [TENANT] --retention-period 100y

# Set a 90-day retention period
./scripts/deploy-to-cloud-run.sh --project [PROJECT_ID] --tenant [TENANT] --retention-period 90d
```

For existing buckets, you can set retention policies using our utility script:

```bash
# Apply a 100-year retention to a specific bucket
./scripts/set-bucket-retention.sh --project [PROJECT_ID] --tenant [TENANT] --retention-period 100y

# Apply a 30-day retention to all tenant buckets in a project
./scripts/set-bucket-retention.sh --project [PROJECT_ID] --all-tenants --retention-period 30d

# Or use gsutil directly
gsutil retention set 30d gs://[PROJECT_ID]-aunooai-[TENANT]
```

The retention period format follows the gsutil convention:
- `30d` for 30 days
- `1y` for 1 year
- `100y` for 100 years (effectively unlimited retention)
- `36h` for 36 hours

**Important considerations:**
- **Without a retention policy** (default): Files persist indefinitely but can be deleted at any time
- **With a retention policy**: Files cannot be deleted until the retention period expires
- Once set, retention policies cannot be removed, only increased in duration
- Retention policies provide strong protection against accidental/intentional deletion, but reduce flexibility