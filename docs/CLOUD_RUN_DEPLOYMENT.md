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

# Push the image to Google Container Registry
docker push gcr.io/[PROJECT_ID]/aunooai-app:latest
```

### Deploying to Cloud Run

```bash
# Deploy to Cloud Run
gcloud run deploy aunooai-[TENANT] \
  --image gcr.io/[PROJECT_ID]/aunooai-app:latest \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars="INSTANCE=[TENANT],ADMIN_PASSWORD=[PASSWORD],STORAGE_BUCKET=[BUCKET]"
```

### Deploying to GKE

```bash
# Deploy to GKE using the deployment script
./scripts/gcp-deploy.sh --project [PROJECT_ID] --tenant [TENANT] --admin-password [PASSWORD]
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

**Issue**: Cloud Run handles SSL termination, but the application was trying to use its own SSL.

**Solution**: We explicitly disable SSL in the entrypoint script:

```bash
# EXPLICITLY disable SSL for Cloud Run
export DISABLE_SSL="true"
export CERT_PATH="/dev/null"
export KEY_PATH="/dev/null"
```

## Dockerfile Structure

The `Dockerfile.gcp` includes:

1. Base image and dependencies
2. Directory structure setup
3. Python dependencies installation
4. Application code copying
5. Configuration setup
6. Stub implementation for scripts module
7. Entrypoint script creation
8. Port configuration

## Entrypoint Script

The entrypoint script performs several key functions:

1. Creates tenant-specific data directories
2. Syncs data from Google Cloud Storage if specified
3. Handles PORT environment variable
4. Sets up environment variables
5. Sets initial admin password if provided
6. Verifies application structure
7. Starts the application using cloud_run_start.py

## Maintenance and Monitoring

### Viewing Logs

```bash
# View Cloud Run logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=aunooai-[TENANT]" --limit=50

# Stream logs in real-time
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=aunooai-[TENANT]" --limit=50 --format=json --stream
```

### Updating the Deployment

To update the deployment:

1. Make changes to the codebase
2. Rebuild the Docker image
3. Push the new image to Google Container Registry
4. Deploy the new image to Cloud Run or GKE

### Backup and Restore

Data is automatically synced to the specified Google Cloud Storage bucket. To restore:

1. Create a new deployment with the same STORAGE_BUCKET
2. The entrypoint script will automatically sync data from the bucket

## Best Practices

1. **Use defensive programming**: Handle potential errors gracefully
2. **Test locally**: Test Docker builds locally before deploying
3. **Monitor logs**: Regularly check logs for errors
4. **Version control**: Tag Docker images with meaningful versions
5. **Document changes**: Keep this document updated with new issues and solutions

## Troubleshooting

If the application fails to start:

1. Check Cloud Run logs for specific error messages
2. Verify environment variables are set correctly
3. Ensure the Docker image was built with the correct Dockerfile
4. Check that all necessary directories and files exist in the image
5. Verify that the entrypoint script has execute permissions

For database-related issues, check if the stub DatabaseMerger implementation is being used, which indicates that the scripts module was not found. 