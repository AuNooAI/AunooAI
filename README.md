# AuNoo AI

## Overview

An AI-powered news research and analysis platform that uses Large Language Models (LLMs) and Machine Learning to extract insights from articles.

## Getting Started

### Clone the Repository
```bash
git clone https://github.com/orochford/AunooAI.git
cd AunooAI
```

### Local Development

1. Create and activate virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # On Unix/macOS
# or
.venv\Scripts\activate  # On Windows
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Generate SSL Certificate (Required):
```bash
# Generate self-signed certificate
openssl req -x509 -newkey rsa:4096 -nodes -out cert.pem -keyout key.pem -days 365
```

4. Start the app:
```bash
python app/run.py
```

5. Access the application:
```
https://localhost:8000
```

### Docker Deployment

Build the container:
```bash
docker build -t aunoo-ai .
```

Run using Docker Compose:
```bash
docker compose up
```

#### Multiple Instance Deployment

The docker-compose.yml includes several pre-configured instances:
- `aunoo-test`: Default testing instance
- `aunoo-customer-x`: Customer X instance
- `aunoo-customer-y`: Customer Y instance

To run a specific instance:
```bash
docker compose --profile customer-x up  # For Customer X instance
```

### Google Cloud Run Deployment

AunooAI can be deployed to Google Cloud Run for a scalable, serverless deployment with multi-tenant support.

#### Prerequisites

- Google Cloud Platform account
- `gcloud` CLI installed and configured
- Docker installed

#### Deployment Steps

1. Configure your GCP project:
```bash
gcloud config set project YOUR_PROJECT_ID
```

2. Deploy a new tenant:
```bash
./scripts/gcp-deploy.sh --project YOUR_PROJECT_ID --tenant TENANT_NAME --admin-password SECURE_PASSWORD
```

3. Check tenant storage configuration:
```bash
./scripts/check-tenant-storage.sh --project YOUR_PROJECT_ID --verbose
```

4. Update tenant resource settings:
```bash
./scripts/update-cloud-run-deployments.sh --project YOUR_PROJECT_ID --tenant TENANT_NAME
```

5. Fix all tenants at once:
```bash
./scripts/fix-all-tenants.sh --project YOUR_PROJECT_ID --admin-password SECURE_PASSWORD --redeploy
```

#### Resource Recommendations

For production workloads, we recommend the following resource settings:
- CPU: 2-4 cores
- Memory: 4-8 GB
- Min Instances: 1-2
- Max Instances: 10-20
- Concurrency: 80-100
- Timeout: 600s

These settings can be configured using the `update-cloud-run-deployments.sh` script.

#### Data Persistence

All tenant data is stored in Cloud Storage buckets, ensuring persistence across container restarts and updates. Each tenant has its own dedicated bucket:

```
gs://YOUR_PROJECT_ID-aunooai-TENANT_NAME/
```

Data is automatically synced to the bucket every 5 minutes and when the container exits.

### Self-Hosting Guide

1. System Requirements:
   - Python 3.11 or higher
   - 2GB RAM minimum
   - 10GB storage space
   - Linux/Unix environment recommended

2. Environment Configuration:
   ```bash
   # Copy example environment file
   cp .env.example .env
   
   # Edit with your settings
   nano .env
   ```

3. Start Application:
   ```bash
   # Using systemd (recommended for production)
   sudo cp deployment/aunoo-ai.service /etc/systemd/system/
   sudo systemctl enable aunoo-ai
   sudo systemctl start aunoo-ai
   ```

4. Monitor Logs:
   ```bash
   sudo journalctl -u aunoo-ai -f
   ```

5. Certificate Renewal:
   ```bash
   # Add to crontab
   0 0 1 * * /path/to/AunooAI/scripts/renew_cert.sh
   ```

## Troubleshooting

### Cloud Run Deployment Issues

1. **Missing Storage Bucket**: If a tenant is losing data, check if it has a storage bucket configured:
   ```bash
   ./scripts/verify-tenant-config.sh --project YOUR_PROJECT_ID --tenant TENANT_NAME
   ```
   
   If no storage bucket is found, configure one:
   ```bash
   ./scripts/configure-tenant-storage.sh --project YOUR_PROJECT_ID --tenant TENANT_NAME
   ```

2. **Resource Constraints**: If a tenant is experiencing performance issues, update its resource settings:
   ```bash
   ./scripts/update-cloud-run-deployments.sh --project YOUR_PROJECT_ID --tenant TENANT_NAME --cpu 4 --memory 8Gi
   ```

3. **Data Persistence Issues**: To ensure data persistence, redeploy the tenant:
   ```bash
   ./scripts/gcp-deploy.sh --project YOUR_PROJECT_ID --tenant TENANT_NAME --admin-password SECURE_PASSWORD
   ```
