# AunooAI Deployment Guide for Google Cloud Platform

This guide provides detailed instructions for deploying AunooAI to Google Cloud Platform (GCP) using Cloud Run. The deployment process is automated through a set of scripts that handle authentication, Docker image building, Cloud Storage setup, and Cloud Run deployment.

## Prerequisites

Before you begin, ensure you have the following:

1. **Google Cloud Platform Account**: You need a GCP account with billing enabled.
2. **Google Cloud SDK**: Install the [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) on your local machine.
3. **Docker**: Install [Docker](https://docs.docker.com/get-docker/) on your local machine.
4. **Git**: Install [Git](https://git-scm.com/downloads) to clone the repository.

## Setup

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/your-organization/AunooAI.git
   cd AunooAI
   ```

2. **Authenticate with Google Cloud**:
   ```bash
   gcloud auth login
   ```

3. **Set Up Project**:
   ```bash
   gcloud projects create YOUR_PROJECT_ID --name="AunooAI Deployment"
   gcloud config set project YOUR_PROJECT_ID
   ```

4. **Enable Billing**:
   Enable billing for your project through the [GCP Console](https://console.cloud.google.com/billing/projects).

5. **Enable Required APIs**:
   ```bash
   gcloud services enable artifactregistry.googleapis.com containerregistry.googleapis.com run.googleapis.com storage-api.googleapis.com
   ```

## Deployment Scripts

The repository includes several scripts to automate the deployment process:

### 1. Deploy to Cloud Run

The `deploy-to-cloud-run.sh` script handles the complete deployment process, including:
- Creating a Cloud Storage bucket for tenant data
- Building and pushing the Docker image
- Creating a service account with appropriate permissions
- Deploying the application to Cloud Run with volume mounts

**Usage**:
```bash
./scripts/deploy-to-cloud-run.sh --project YOUR_PROJECT_ID [OPTIONS]
```

**Required Parameters**:
- `--project ID`: Your GCP Project ID

**Optional Parameters**:
- `--region REGION`: GCP Region (default: us-central1)
- `--tenant NAME`: Tenant name (default: tenant1)
- `--admin-password PWD`: Admin password (default: admin)
- `--port PORT`: Container port (default: 8080)
- `--memory MEMORY`: Memory allocation (default: 4Gi)
- `--cpu CPU`: CPU allocation (default: 2)
- `--min-instances N`: Minimum instances (default: 1)
- `--max-instances N`: Maximum instances (default: 10)
- `--concurrency N`: Concurrency per instance (default: 80)
- `--timeout SEC`: Request timeout in seconds (default: 600s)
- `--image-tag TAG`: Docker image tag (default: latest)
- `--disable-ssl BOOL`: Disable SSL redirect (default: false)
- `--openai-api-key KEY`: OpenAI API key
- `--anthropic-api-key KEY`: Anthropic API key
- `--google-api-key KEY`: Google API key
- `--litellm-config PATH`: Path to LiteLLM config file
- `--startup-timeout SEC`: Startup probe timeout (default: 300s)
- `--startup-period SEC`: Startup probe period (default: 10s)
- `--startup-failure-threshold N`: Startup probe failure threshold (default: 30)

**Example**:
```bash
./scripts/deploy-to-cloud-run.sh --project aunooai-prod --tenant customer1 --admin-password securepass123 --region us-west1 --disable-ssl true
```

### 2. Configure Tenant Storage

The `configure-tenant-storage.sh` script configures Cloud Storage buckets for existing AunooAI tenants and updates Cloud Run services to use the storage buckets.

**Usage**:
```bash
./scripts/configure-tenant-storage.sh --project YOUR_PROJECT_ID [OPTIONS]
```

**Required Parameters**:
- `--project ID`: Your GCP Project ID

**Optional Parameters**:
- `--region REGION`: GCP Region (default: us-central1)
- `--tenant NAME`: Specific tenant to configure (if not specified, all tenants will be configured)

**Example**:
```bash
./scripts/configure-tenant-storage.sh --project aunooai-prod --tenant customer1
```

### 3. Add Volume Mounts to Cloud Run

The `add-volume-mounts-to-cloud-run.sh` script adds Cloud Storage volume mounts to existing AunooAI deployments on Cloud Run.

**Usage**:
```bash
./scripts/add-volume-mounts-to-cloud-run.sh --project YOUR_PROJECT_ID [OPTIONS]
```

**Required Parameters**:
- `--project ID`: Your GCP Project ID

**Optional Parameters**:
- `--region REGION`: GCP Region (default: us-central1)
- `--tenant NAME`: Specific tenant to update (if not specified, all tenants will be updated)

**Example**:
```bash
./scripts/add-volume-mounts-to-cloud-run.sh --project aunooai-prod --tenant customer1
```

## Multi-Tenant Deployment

AunooAI supports multi-tenant deployments, where each tenant has its own isolated environment. To deploy multiple tenants:

1. **Deploy the First Tenant**:
   ```bash
   ./scripts/deploy-to-cloud-run.sh --project YOUR_PROJECT_ID --tenant tenant1 --admin-password password1
   ```

2. **Deploy Additional Tenants**:
   ```bash
   ./scripts/deploy-to-cloud-run.sh --project YOUR_PROJECT_ID --tenant tenant2 --admin-password password2
   ```

Each tenant will have:
- A separate Cloud Run service (`aunooai-tenant1`, `aunooai-tenant2`, etc.)
- A dedicated Cloud Storage bucket for persistent data
- Its own service account with appropriate permissions

## Architecture

The AunooAI deployment on GCP Cloud Run consists of the following components:

1. **Cloud Run Service**: Hosts the AunooAI application container
2. **Cloud Storage Bucket**: Stores persistent data for each tenant
3. **Service Account**: Provides necessary permissions for the application
4. **Container Registry**: Stores the Docker images

The application uses a custom Docker image defined in `Dockerfile.gcp`, which includes:
- Python 3.11 runtime
- Google Cloud SDK
- Application code and dependencies
- Custom entrypoint script for Cloud Run

## Data Persistence

AunooAI uses Cloud Storage buckets for data persistence. Each tenant has its own bucket, which is mounted to the Cloud Run service at `/app/app/data/{tenant}`. The application automatically syncs data between the container and the bucket.

## Common Issues and Solutions

### 1. SSL Redirection Issues

**Issue**: The application may enter an infinite redirect loop when deployed to Cloud Run due to SSL redirection conflicts.

**Solution**: Disable SSL redirection in the application by setting the `DISABLE_SSL` environment variable to `true`:

```bash
./scripts/deploy-to-cloud-run.sh --project YOUR_PROJECT_ID --tenant TENANT_NAME --disable-ssl true
```

This prevents the application from trying to redirect HTTP to HTTPS, which would create a redirect loop because Cloud Run already handles SSL termination.

### 2. Startup Probe Configuration

**Issue**: The application may take longer to start than the default Cloud Run startup probe allows, especially when initializing LiteLLM.

**Solution**: Configure the startup probe with longer timeouts:

```bash
./scripts/deploy-to-cloud-run.sh --project YOUR_PROJECT_ID --tenant TENANT_NAME --startup-timeout 300s --startup-period 10s --startup-failure-threshold 30
```

The correct format for the startup probe parameter in Cloud Run is:
```
--startup-probe=tcp:port=8080,initial-delay=5s,timeout=300s,period=10s,failure-threshold=30
```

In some cases, you may need to omit the startup probe entirely for the initial deployment, especially if the application is initializing LiteLLM configurations and API connections during startup.

### 3. LiteLLM API Key Configuration

**Issue**: LiteLLM requires API keys for various model providers, which need to be properly configured.

**Solution**: Pass the required API keys as environment variables during deployment:

```bash
./scripts/deploy-to-cloud-run.sh --project YOUR_PROJECT_ID --tenant TENANT_NAME --openai-api-key "your-openai-key" --anthropic-api-key "your-anthropic-key" --google-api-key "your-google-key"
```

These API keys will be passed to the LiteLLM library for authentication with the respective model providers.

### 4. Volume Mount Issues

**Issue**: Cloud Run may fail to mount the Cloud Storage bucket properly, leading to data persistence issues.

**Solution**: Use the volume mount commands explicitly:

```bash
gcloud run deploy aunooai-TENANT_NAME \
  --region REGION \
  --add-volume name=storage,type=cloud-storage,bucket=BUCKET_NAME \
  --add-volume-mount volume=storage,mount-path=/app/app/data/TENANT_NAME
```

Or use the helper script:

```bash
./scripts/add-volume-mounts-to-cloud-run.sh --project YOUR_PROJECT_ID --tenant TENANT_NAME
```

## Monitoring and Maintenance

### Monitoring

Monitor your Cloud Run services through the GCP Console:
```
https://console.cloud.google.com/run/detail/{region}/aunooai-{tenant}/metrics
```

### Viewing Logs

To view logs for your deployment:

```bash
# View all logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=aunooai-TENANT_NAME" --limit=50

# View error logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=aunooai-TENANT_NAME AND severity>=ERROR" --limit=20

# Stream logs in real-time
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=aunooai-TENANT_NAME" --limit=10 --format=json --stream
```

### Updating Deployments

To update an existing deployment:
1. Make changes to your application code
2. Run the deployment script again with the same parameters:
   ```bash
   ./scripts/deploy-to-cloud-run.sh --project YOUR_PROJECT_ID --tenant TENANT_NAME --admin-password PASSWORD
   ```

### Scaling

Cloud Run automatically scales based on traffic. You can configure the scaling behavior using the following parameters:
- `--min-instances`: Minimum number of instances to keep running
- `--max-instances`: Maximum number of instances to scale to
- `--concurrency`: Maximum number of requests per instance

## Troubleshooting

### Common Issues

1. **Deployment Fails with Permission Errors**:
   - Ensure you have the necessary IAM permissions
   - Run `gcloud auth login` to refresh your credentials

2. **Container Fails to Start**:
   - Check the Cloud Run logs for error messages
   - Verify that all required environment variables are set

3. **Data Persistence Issues**:
   - Ensure the Cloud Storage bucket exists and is accessible
   - Check that the service account has the necessary permissions
   - Verify that the volume mount is correctly configured

### Viewing Logs

View logs for a specific tenant:
```bash
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=aunooai-TENANT_NAME" --limit=50
```

## Security Considerations

1. **Admin Password**: Always use a strong, unique password for each tenant
2. **Service Accounts**: Use dedicated service accounts with minimal permissions
3. **Network Security**: Consider using VPC-SC for additional network security
4. **Secrets Management**: Use Secret Manager for sensitive configuration values

## Cost Optimization

1. **Instance Scaling**: Configure min/max instances appropriately
2. **Memory and CPU**: Allocate resources based on actual needs
3. **Idle Instances**: Set minimum instances to 0 for non-critical tenants
4. **Storage**: Monitor and clean up unused storage

## Additional Resources

- [Cloud Run Documentation](https://cloud.google.com/run/docs)
- [Cloud Storage Documentation](https://cloud.google.com/storage/docs)
- [Container Registry Documentation](https://cloud.google.com/container-registry/docs)
- [IAM Documentation](https://cloud.google.com/iam/docs) 