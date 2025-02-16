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
