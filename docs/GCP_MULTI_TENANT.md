# AunooAI Multi-Tenant Deployment on Google Cloud Platform

This guide provides instructions for deploying AunooAI as a multi-tenant application on Google Cloud Platform (GCP). Two deployment options are available:

1. **Cloud Run** - Serverless deployment, ideal for small to medium workloads
2. **Google Kubernetes Engine (GKE)** - Container orchestration, ideal for larger and more complex deployments

## Prerequisites

- [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) installed and configured
- [Docker](https://docs.docker.com/get-docker/) installed
- For GKE: [kubectl](https://kubernetes.io/docs/tasks/tools/) installed
- A GCP Project with billing enabled
- Required APIs enabled:
  - Cloud Run API
  - Container Registry API
  - Artifact Registry API
  - Kubernetes Engine API (for GKE)
  - Cloud Storage API

## Docker Setup

The deployment scripts require Docker to build and push container images. The scripts support different Docker installation methods:

1. **Traditional Docker Installation**:
   If Docker is installed directly on your system, you can configure it to run without sudo:
   ```bash
   sudo usermod -aG docker $USER
   # Log out and log back in for the changes to take effect
   ```

2. **Snap-based Docker Installation**:
   If Docker is installed via snap (common on Ubuntu systems), the scripts will automatically detect this and use sudo for Docker commands. No additional configuration is needed.

   You can verify your Docker installation method with:
   ```bash
   which docker
   # If it shows /snap/bin/docker, you have a snap-based installation
   ```

3. **Other Docker Installations**:
   For any installation where Docker requires sudo, the scripts will automatically detect this and use sudo for Docker commands.

**Note**: If you're having Docker permission issues, the scripts will handle them automatically by using sudo for Docker operations.

## Authentication Setup

Before running any deployment scripts, you need to authenticate with Google Cloud:

1. Log in to your Google Cloud account:
   ```bash
   gcloud auth login
   ```

2. Configure Docker to use the Google Cloud credentials:
   ```bash
   gcloud auth configure-docker gcr.io
   
   # For older Docker versions, you may also need:
   gcloud auth print-access-token | docker login -u oauth2accesstoken --password-stdin https://gcr.io
   ```

3. The deployment scripts will attempt to automatically grant the necessary permissions to your user account. If you encounter permission issues, verify you have the following roles:
   - Storage Admin role (`roles/storage.admin`)
   - Artifact Registry Writer role (`roles/artifactregistry.writer`)
   - Container Registry Service Agent role (`roles/containerregistry.ServiceAgent`)
   - Cloud Run Admin role (`roles/run.admin`) for Cloud Run deployments
   - Kubernetes Engine Admin role (`roles/container.admin`) for GKE deployments

4. You can manually grant these roles using the Google Cloud Console or the command line:
   ```bash
   # Replace YOUR_EMAIL with your Google account email
   # Replace PROJECT_ID with your GCP project ID
   
   gcloud projects add-iam-policy-binding PROJECT_ID --member="user:YOUR_EMAIL" --role="roles/artifactregistry.writer"
   gcloud projects add-iam-policy-binding PROJECT_ID --member="user:YOUR_EMAIL" --role="roles/storage.admin"
   gcloud projects add-iam-policy-binding PROJECT_ID --member="user:YOUR_EMAIL" --role="roles/containerregistry.ServiceAgent"
   ```

> **Note on using sudo**: It's recommended to run the deployment scripts without `sudo` to use your authenticated gcloud credentials. If you must use `sudo`, the scripts now detect this and use your user's gcloud configuration.

## Option 1: Cloud Run Deployment

Cloud Run provides a simple, serverless environment for running containerized applications.

### Deployment Steps

1. Make the deployment script executable:
   ```bash
   chmod +x scripts/gcp-deploy.sh
   ```

2. Deploy a single tenant:
   ```bash
   ./scripts/gcp-deploy.sh --project YOUR_PROJECT_ID --tenant TENANT_NAME --admin-password SECURE_PASSWORD
   ```

3. The script will:
   - Verify authentication and enable required APIs
   - Auto-grant necessary IAM permissions to your user
   - Create a Cloud Storage bucket for persistent data
   - Build and push the Docker image to Google Container Registry
   - Create a service account with appropriate permissions
   - Deploy the application to Cloud Run
   - Configure the environment with the tenant name and admin password

### Accessing the Deployment

After deployment, the script will output the URL for accessing the tenant instance. The default login credentials are:
- Username: admin
- Password: The value provided to `--admin-password` (default: "admin")

### Adding More Tenants

To add more tenants, simply run the deployment script again with a different tenant name:

```bash
./scripts/gcp-deploy.sh --project YOUR_PROJECT_ID --tenant ANOTHER_TENANT --admin-password SECURE_PASSWORD
```

## Option 2: GKE Deployment

Google Kubernetes Engine provides a managed Kubernetes environment for more complex deployments.

### Deployment Steps

1. Make the deployment script executable:
   ```bash
   chmod +x scripts/gcp-gke-deploy.sh
   ```

2. Deploy multiple tenants at once:
   ```bash
   ./scripts/gcp-gke-deploy.sh --project YOUR_PROJECT_ID --tenant TENANT1 --tenant TENANT2 --admin-password SECURE_PASSWORD
   ```

3. The script will:
   - Verify authentication and enable required APIs
   - Auto-grant necessary IAM permissions to your user
   - Create or use an existing GKE cluster
   - Create Cloud Storage buckets for each tenant
   - Create service accounts with appropriate permissions
   - Deploy the application to the GKE cluster with separate deployments for each tenant
   - Configure ingress rules for accessing each tenant

### Accessing the Deployment

After deployment, the script will output URLs for each tenant instance. The default login credentials are:
- Username: admin
- Password: The value provided to `--admin-password` (default: "admin")

### Adding More Tenants

To add more tenants to an existing cluster, run the deployment script with the new tenant names:

```bash
./scripts/gcp-gke-deploy.sh --project YOUR_PROJECT_ID --tenant NEW_TENANT --admin-password SECURE_PASSWORD
```

## Troubleshooting Authentication Issues

If you encounter authentication errors during deployment, try the following steps:

1. Ensure you're logged in with gcloud:
   ```bash
   gcloud auth login
   ```

2. Verify that Docker is configured to use gcloud credentials:
   ```bash
   # Check your Docker config
   cat ~/.docker/config.json
   
   # Configure Docker for GCR
   gcloud auth configure-docker gcr.io
   
   # Force login using access token (helpful for older Docker versions)
   gcloud auth print-access-token | docker login -u oauth2accesstoken --password-stdin https://gcr.io
   ```

3. Manually grant required permissions to your user:
   ```bash
   # Replace with your email and project
   gcloud projects add-iam-policy-binding PROJECT_ID --member="user:YOUR_EMAIL" --role="roles/artifactregistry.writer"
   gcloud projects add-iam-policy-binding PROJECT_ID --member="user:YOUR_EMAIL" --role="roles/storage.admin"
   gcloud projects add-iam-policy-binding PROJECT_ID --member="user:YOUR_EMAIL" --role="roles/containerregistry.ServiceAgent"
   ```

4. Verify the Artifact Registry or Container Registry exists:
   ```bash
   # List Artifact Registry repositories
   gcloud artifacts repositories list --project=PROJECT_ID
   
   # Create Artifact Registry repository if needed
   gcloud artifacts repositories create gcr.io --repository-format=docker --location=us --project=PROJECT_ID
   ```

5. If running in a CI/CD environment, use a service account with proper permissions:
   ```bash
   # Authenticate with service account
   gcloud auth activate-service-account --key-file=path/to/service-account-key.json
   
   # Configure Docker with service account credentials
   gcloud auth configure-docker gcr.io
   ```

## Data Persistence

All tenant data is stored in Cloud Storage buckets, ensuring persistence across container restarts and updates. Each tenant has its own dedicated bucket:

```
gs://YOUR_PROJECT_ID-aunooai-TENANT_NAME/
```

### Volume Mounts

For Cloud Run deployments, we use Cloud Storage volume mounts to provide direct file system access to the persistent storage. This ensures that all data written to the specified directory is automatically persisted to Cloud Storage.

The deployment script automatically configures volume mounts using the appropriate syntax for your Google Cloud SDK version:

```bash
# Using the newer syntax (recommended for Cloud SDK 400+)
--add-volume name=storage,type=cloud-storage,bucket=[BUCKET_NAME] \
--add-volume-mount volume=storage,mount-path=/app/app/data/[TENANT]
```

To verify that volume mounts are properly configured, check the Cloud Run service details under "Revisions" -> "Volumes". You should see:

```
Cloud Storage bucket
[BUCKET_NAME] mounted at /app/app/data/[TENANT_NAME]
```

If the volume mount is missing, you can add it using:

```bash
./scripts/add-volume-mounts.sh --project [PROJECT_ID] --tenant [TENANT_NAME]
```

To add volume mounts to all tenants at once:

```bash
./scripts/add-volume-mounts.sh --project [PROJECT_ID]
```

### Backup Mechanism

In addition to volume mounts, the application also implements a periodic sync mechanism that copies data to the Cloud Storage bucket every 5 minutes and when the container exits. This provides an additional layer of data protection.

## Environment Variables

The following environment variables can be configured:

- **For Cloud Run deployments**:
  - `INSTANCE`: The tenant name 
  - `ADMIN_PASSWORD`: Initial admin password
  - `STORAGE_BUCKET`: The Cloud Storage bucket for tenant data
  - Note: `PORT` is automatically set by Cloud Run and should not be provided

- **For GKE deployments**:
  - `CONTAINER_PORT`: The port the application will listen on (default: 8080)
  - `INSTANCE`: The tenant name 
  - `ADMIN_PASSWORD`: Initial admin password
  - `STORAGE_BUCKET`: The Cloud Storage bucket for tenant data

## Security Considerations

- Each tenant has its own dedicated service account with limited permissions
- Each tenant's data is isolated in a separate Cloud Storage bucket
- Admin passwords should be set to strong, unique values for each tenant
- Consider implementing Cloud Identity-Aware Proxy (IAP) for additional authentication

## Troubleshooting

### Unable to Access the Application

- Check that the deployment was successful by reviewing the logs:
  ```bash
  # For Cloud Run
  gcloud run services logs read aunooai-TENANT_NAME
  
  # For GKE
  kubectl logs -n aunooai deployment/aunooai-TENANT_NAME
  ```

### Database Connection Issues

- Verify that the service account has proper permissions to the Cloud Storage bucket
- Check the application logs for any errors related to database access

### Volume Mount Issues

If you encounter issues with volume mounts:

1. **Missing Volume Mount**: If the Cloud Run service doesn't show a volume mount under "Revisions" -> "Volumes":
   ```bash
   # Add volume mount for a specific tenant
   ./scripts/add-volume-mounts.sh --project YOUR_PROJECT_ID --tenant TENANT_NAME
   
   # Add volume mounts for all tenants
   ./scripts/add-volume-mounts.sh --project YOUR_PROJECT_ID
   ```

2. **Incompatible Volume Mount Syntax**: If you see errors like `unrecognized arguments: --mount` or `--add-volume`:
   ```bash
   # Check your Google Cloud SDK version
   gcloud --version
   
   # Update Google Cloud SDK if needed
   gcloud components update
   ```
   
   The `add-volume-mounts.sh` script will automatically try different syntaxes compatible with your Google Cloud SDK version.

3. **Permission Issues**: Ensure your service account has the necessary permissions:
   ```bash
   # Grant Storage Object Admin role to the service account
   gcloud projects add-iam-policy-binding PROJECT_ID \
     --member="serviceAccount:aunooai-TENANT-sa@PROJECT_ID.iam.gserviceaccount.com" \
     --role="roles/storage.objectAdmin"
   ```

4. **Data Not Persisting**: If data is still not persisting despite volume mounts:
   - Verify the application is writing to the correct path (`/app/app/data/TENANT_NAME`)
   - Check if the periodic sync mechanism is working by examining the logs
   - Consider redeploying the tenant with the latest deployment script

### SSL Certificate Issues

- The application uses Google-managed certificates. If you see certificate warnings, ensure you're accessing the application via HTTPS
- For custom domains, set up domain mapping and certificates in Cloud Run or GKE Ingress

## Customizing the Deployment

### Using a Custom Domain

To use a custom domain with your deployment:

1. **For Cloud Run**:
   ```bash
   gcloud run domain-mappings create --service aunooai-TENANT_NAME --domain TENANT.yourdomain.com
   ```

2. **For GKE**:
   Edit the Ingress rules in the tenant's deployment YAML to use your custom domain and set up appropriate certificate management.

### Scaling Configuration

To adjust scaling for a tenant:

1. **For Cloud Run**:
   ```bash
   gcloud run services update aunooai-TENANT_NAME --min-instances=1 --max-instances=10
   ```

2. **For GKE**:
   ```bash
   kubectl scale -n aunooai deployment/aunooai-TENANT_NAME --replicas=3
   ```

## Updating the Application

To update the application to a new version:

1. Build and push a new version of the Docker image
2. Update the deployment:

   **For Cloud Run**:
   ```bash
   gcloud run services update aunooai-TENANT_NAME --image gcr.io/YOUR_PROJECT_ID/aunooai-TENANT_NAME:new-version
   ```

   **For GKE**:
   ```bash
   kubectl set image -n aunooai deployment/aunooai-TENANT_NAME aunooai=gcr.io/YOUR_PROJECT_ID/aunooai:new-version
   ``` 