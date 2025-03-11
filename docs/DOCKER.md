# AunooAI Docker Setup

This document provides instructions for running AunooAI in a Docker container.

## Prerequisites

- Docker Engine installed (version 19.03.0+)
- Docker Compose installed (version 1.27.0+)

## Quick Start

The easiest way to start AunooAI is to use the provided initialization script:

```bash
./scripts/docker-init.sh
```

This script will:
1. Check for required dependencies
2. Build the Docker image
3. Start the development instance
4. Provide access information

## Manual Setup

### Building the Docker Image

```bash
docker-compose build
```

### Running Instances

#### Development Instance

```bash
docker-compose up -d aunooai-dev
```

Access at: https://localhost:6005

#### Production Instance

```bash
docker-compose --profile prod up -d
```

Access at: https://localhost:5008

#### Staging Instance

```bash
docker-compose --profile staging up -d
```

Access at: https://localhost:5009

### Stopping Instances

```bash
docker-compose down
```

## Environment Configuration

The following environment variables can be configured in the docker-compose.yml file:

- `PORT`: The port the application will run on
- `INSTANCE`: The instance name (dev, prod, staging)
- `ADMIN_PASSWORD`: Initial admin password

## Persistent Data

Data is stored in Docker volumes to ensure persistence between container restarts:

- `aunooai_<instance>_data`: Database and configuration files
- `aunooai_<instance>_reports`: Generated reports

## Admin Access

After starting the container, you can access the application with:

- **Username**: admin
- **Password**: admin (or the value of ADMIN_PASSWORD if you changed it)

The system will prompt you to change this password on first login.

## Custom Database Management

### Executing the Admin Password Update Script

To manually update the admin password:

```bash
docker exec -it <container_name> python -c "from app.utils.update_admin import update_admin_password; update_admin_password('/app/app/data/<instance>/fnaapp.db', '<new_password>')"
```

Replace:
- `<container_name>` with the actual container name (e.g., aunooai-dev)
- `<instance>` with your instance name (e.g., dev, prod, staging)
- `<new_password>` with your desired password

## Troubleshooting

### Database Connection Issues

If you encounter database connection errors, check:
1. The database file exists in the volume
2. The permissions are correct
3. The database path in the application matches the volume path

### SSL Certificate Issues

The application uses self-signed certificates by default. You may:
1. Accept the self-signed certificate in your browser
2. Replace the certificates with your own valid certificates by mounting them into the container

### Container Logs

View logs with:

```bash
docker-compose logs -f aunooai-dev
``` 