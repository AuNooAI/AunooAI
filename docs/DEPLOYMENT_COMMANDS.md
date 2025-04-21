# AunooAI Deployment Commands

This document provides quick reference commands for deploying and managing AunooAI on Google Cloud Platform.

## Local Development

```bash
# Run locally
python app/main.py

# Run with uvicorn
uvicorn app.main:app --reload
```

## Docker Commands

```bash
# Build Docker image
docker build -f Dockerfile.gcp -t aunooai-app:latest .

# Run Docker container locally
docker run -p 8080:8080 \
  -e INSTANCE=local \
  -e ADMIN_PASSWORD=admin \
  aunooai-app:latest

# View Docker logs
docker logs -f <container_id>
```

## Google Cloud Platform Commands

### Container Registry

```bash
# Tag Docker image for GCR
docker tag aunooai-app:latest gcr.io/[PROJECT_ID]/aunooai-app:latest

# Push to GCR
docker push gcr.io/[PROJECT_ID]/aunooai-app:latest

# List images in GCR
gcloud container images list --repository=gcr.io/[PROJECT_ID]
```

### Cloud Run

```bash
# Deploy to Cloud Run
gcloud run deploy aunooai-[TENANT] \
  --image gcr.io/[PROJECT_ID]/aunooai-app:latest \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars="INSTANCE=[TENANT],ADMIN_PASSWORD=[PASSWORD],STORAGE_BUCKET=[BUCKET]"

# List Cloud Run services
gcloud run services list

# Get Cloud Run service URL
gcloud run services describe aunooai-[TENANT] --format="value(status.url)"

# View Cloud Run logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=aunooai-[TENANT]" --limit=50
```

### Google Kubernetes Engine (GKE)

```bash
# Deploy to GKE using script
./scripts/gcp-deploy.sh --project [PROJECT_ID] --tenant [TENANT] --admin-password [PASSWORD]

# Get GKE clusters
gcloud container clusters list

# Get credentials for GKE cluster
gcloud container clusters get-credentials [CLUSTER_NAME] --region [REGION]

# List pods
kubectl get pods

# View pod logs
kubectl logs [POD_NAME]
```

### Cloud Storage

```bash
# Create a bucket
gsutil mb -l [REGION] gs://[BUCKET_NAME]

# List buckets
gsutil ls

# Copy data to bucket
gsutil cp -r [LOCAL_PATH] gs://[BUCKET_NAME]/

# Sync data with bucket
gsutil -m rsync -r [LOCAL_PATH] gs://[BUCKET_NAME]/
```

## Troubleshooting Commands

```bash
# Check Cloud Run service status
gcloud run services describe aunooai-[TENANT]

# View detailed logs with error messages
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=aunooai-[TENANT] AND severity>=ERROR" --limit=50

# Stream logs in real-time
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=aunooai-[TENANT]" --limit=50 --format=json --stream

# Check if container is healthy
gcloud run services describe aunooai-[TENANT] --format="value(status.conditions)"
```

## Cleanup Commands

```bash
# Delete Cloud Run service
gcloud run services delete aunooai-[TENANT]

# Delete GCR image
gcloud container images delete gcr.io/[PROJECT_ID]/aunooai-app:latest

# Delete Cloud Storage bucket
gsutil rm -r gs://[BUCKET_NAME]/
``` 