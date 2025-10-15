# AunooAI Docker Setup

This document provides comprehensive instructions for running AunooAI in Docker containers with both SQLite and PostgreSQL database backends.

## Prerequisites

- Docker Engine installed (version 19.03.0+)
- Docker Compose installed (version 1.27.0+)
- For PostgreSQL: Understanding of basic PostgreSQL concepts

## Quick Start

### Option 1: SQLite (Simplest)

The easiest way to start AunooAI with SQLite is:

```bash
./scripts/docker-init.sh
```

Or manually:

```bash
docker-compose build
docker-compose up -d aunooai-dev
```

Access at: http://localhost:6005

### Option 2: PostgreSQL (Recommended for Production)

For production-like testing with PostgreSQL:

```bash
docker-compose build
docker-compose --profile postgres up -d
```

Access at: http://localhost:6006

## Available Instances

AunooAI provides multiple pre-configured instances:

| Instance | Database | Port | Profile | Use Case |
|----------|----------|------|---------|----------|
| `aunooai-dev` | SQLite | 6005 | (default) | Quick local development |
| `aunooai-dev-postgres` | PostgreSQL | 6006 | `postgres` | Production-like testing |
| `aunooai-prod` | PostgreSQL | 5008 | `prod` | Production deployment |
| `aunooai-staging` | PostgreSQL | 5009 | `staging` | Staging environment |
| `pgadmin` | - | 5050 | `admin` | PostgreSQL management UI |

## Database Configuration

### SQLite Configuration

The `aunooai-dev` instance uses SQLite by default:

```yaml
environment:
  - DB_TYPE=sqlite
  - ADMIN_PASSWORD=${ADMIN_PASSWORD:-admin}
```

**Advantages:**
- No external database required
- Simple setup and configuration
- Ideal for local development and testing

**Limitations:**
- Single-threaded write operations
- Not suitable for high-concurrency scenarios
- Limited to single-server deployments

### PostgreSQL Configuration

All PostgreSQL instances (`aunooai-dev-postgres`, `aunooai-prod`, `aunooai-staging`) share the same PostgreSQL service:

```yaml
environment:
  - DB_TYPE=postgresql
  - DB_HOST=postgres
  - DB_PORT=5432
  - DB_NAME=aunoo_db
  - DB_USER=aunoo_user
  - DB_PASSWORD=${POSTGRES_PASSWORD:-changeme}
  # Connection Pooling
  - DB_POOL_SIZE=20
  - DB_MAX_OVERFLOW=10
  - DB_POOL_TIMEOUT=30
  - DB_POOL_RECYCLE=3600
```

**Advantages:**
- Production-grade database
- Better concurrency handling
- Advanced features (JSONB, full-text search)
- Connection pooling for performance

**Connection Pooling Settings:**
- `DB_POOL_SIZE`: Maximum number of permanent connections
- `DB_MAX_OVERFLOW`: Additional temporary connections beyond pool size
- `DB_POOL_TIMEOUT`: Seconds to wait for available connection
- `DB_POOL_RECYCLE`: Recycle connections after this many seconds (prevents stale connections)

## Environment Variables

### Required for All Instances

```bash
PORT=6005                    # Port the application runs on
INSTANCE=dev                 # Instance name (dev, prod, staging)
ENVIRONMENT=development      # Environment (development, staging, production)
```

### API Keys (Optional but Recommended)

```bash
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
FIRECRAWL_API_KEY=fc-...
NEWSAPI_KEY=...
ELEVENLABS_API_KEY=...
```

### PostgreSQL-Specific

```bash
POSTGRES_PASSWORD=changeme    # Set this in production!
DB_POOL_SIZE=20               # Adjust based on load
DB_MAX_OVERFLOW=10            # Additional connections
```

### Setting Environment Variables

Create a `.env` file in the project root:

```bash
# Database
POSTGRES_PASSWORD=your_secure_password_here

# API Keys
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
FIRECRAWL_API_KEY=fc-...
NEWSAPI_KEY=...
ELEVENLABS_API_KEY=...

# Optional: Build metadata
APP_VERSION=1.0.0
GIT_BRANCH=main
BUILD_DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
```

## Starting Instances

### Development with SQLite

```bash
# Build and start
docker-compose up -d aunooai-dev

# View logs
docker-compose logs -f aunooai-dev

# Access
open http://localhost:6005
```

### Development with PostgreSQL

```bash
# Start PostgreSQL and app
docker-compose --profile postgres up -d

# Check PostgreSQL health
docker-compose ps postgres

# View logs
docker-compose logs -f aunooai-dev-postgres

# Access
open http://localhost:6006
```

### Production Deployment

```bash
# Start production instance with PostgreSQL
docker-compose --profile prod up -d

# View logs
docker-compose logs -f aunooai-prod

# Check status
docker-compose ps

# Access
open http://localhost:5008
```

### Staging Environment

```bash
# Start staging instance
docker-compose --profile staging up -d

# Access
open http://localhost:5009
```

### PostgreSQL Administration (PgAdmin)

```bash
# Start PgAdmin
docker-compose --profile admin up -d pgadmin

# Access
open http://localhost:5050
```

**PgAdmin Login:**
- Email: `admin@aunoo.ai`
- Password: Value of `PGADMIN_PASSWORD` (default: `admin`)

**Connecting to PostgreSQL from PgAdmin:**
1. Add new server
2. Name: `AunooAI`
3. Host: `postgres`
4. Port: `5432`
5. Database: `aunoo_db` (or `aunoo_db_prod`, `aunoo_db_staging`)
6. Username: `aunoo_user`
7. Password: Value of `POSTGRES_PASSWORD`

## Stopping and Cleaning Up

### Stop All Services

```bash
docker-compose down
```

### Stop Specific Instance

```bash
docker-compose stop aunooai-dev
docker-compose stop aunooai-dev-postgres
```

### Remove Volumes (CAUTION: Deletes Data)

```bash
# Remove all volumes
docker-compose down -v

# Remove specific volume
docker volume rm skunkworkxaunooai_postgres_data
```

## Database Migrations

### Automatic Migrations (PostgreSQL)

Migrations run automatically when PostgreSQL containers start. The entrypoint script will:

1. Wait for PostgreSQL to be ready
2. Run `alembic upgrade head`
3. Start the application

### Manual Migration

```bash
# Enter the container
docker-compose exec aunooai-dev-postgres bash

# Run migrations
alembic upgrade head

# Check migration status
alembic current

# View migration history
alembic history
```

## Persistent Data

Data is stored in Docker volumes:

### SQLite Volumes
- `aunooai_dev_data`: Database file and configuration
- `aunooai_dev_reports`: Generated reports

### PostgreSQL Volumes
- `postgres_data`: PostgreSQL database files
- `aunooai_dev_postgres_data`: Instance-specific data
- `aunooai_dev_postgres_reports`: Generated reports
- `aunooai_prod_data`: Production instance data
- `aunooai_staging_data`: Staging instance data

### Backing Up Data

#### PostgreSQL Backup

```bash
# Backup database
docker-compose exec postgres pg_dump -U aunoo_user aunoo_db > backup.sql

# Restore database
docker-compose exec -T postgres psql -U aunoo_user aunoo_db < backup.sql
```

#### SQLite Backup

```bash
# Backup SQLite database
docker-compose exec aunooai-dev cp /app/app/data/dev/fnaapp.db /app/reports/backup.db
docker cp $(docker-compose ps -q aunooai-dev):/app/reports/backup.db ./backup.db
```

## Admin Access

### Default Credentials

After starting any container:

- **Username**: `admin`
- **Password**: `admin` (or value of `ADMIN_PASSWORD` environment variable)

**IMPORTANT**: The system will prompt you to change the password on first login.

### Resetting Admin Password

#### SQLite

```bash
docker-compose exec aunooai-dev python -c "from app.utils.update_admin import update_admin_password; update_admin_password('/app/app/data/dev/fnaapp.db', 'new_password')"
```

#### PostgreSQL

Admin password management for PostgreSQL is handled through the application UI or database directly.

## Troubleshooting

### PostgreSQL Connection Issues

**Symptom**: Application fails to connect to PostgreSQL

**Solutions**:

1. Check PostgreSQL is running:
   ```bash
   docker-compose ps postgres
   ```

2. Check PostgreSQL health:
   ```bash
   docker-compose exec postgres pg_isready -U aunoo_user
   ```

3. Verify connection settings:
   ```bash
   docker-compose exec aunooai-dev-postgres env | grep DB_
   ```

4. Check PostgreSQL logs:
   ```bash
   docker-compose logs postgres
   ```

5. Test manual connection:
   ```bash
   docker-compose exec postgres psql -U aunoo_user -d aunoo_db -c "SELECT version();"
   ```

### Migration Failures

**Symptom**: `alembic upgrade head` fails

**Solutions**:

1. Check migration status:
   ```bash
   docker-compose exec aunooai-dev-postgres alembic current
   ```

2. View migration logs:
   ```bash
   docker-compose logs aunooai-dev-postgres | grep -i migration
   ```

3. Reset migrations (CAUTION):
   ```bash
   docker-compose exec aunooai-dev-postgres alembic downgrade base
   docker-compose exec aunooai-dev-postgres alembic upgrade head
   ```

### Container Startup Issues

**Symptom**: Container exits immediately

**Solutions**:

1. View container logs:
   ```bash
   docker-compose logs aunooai-dev-postgres
   ```

2. Check entrypoint script:
   ```bash
   docker-compose exec aunooai-dev-postgres cat /entrypoint.sh
   ```

3. Start with interactive shell:
   ```bash
   docker-compose run --rm --entrypoint bash aunooai-dev-postgres
   ```

### Port Already in Use

**Symptom**: `port is already allocated`

**Solutions**:

1. Check what's using the port:
   ```bash
   lsof -i :6005
   sudo netstat -tlnp | grep 6005
   ```

2. Change port in `docker-compose.yml` or stop the conflicting service

### SSL Certificate Issues

The application uses self-signed certificates by default (`DISABLE_SSL=true` in Docker).

**To use custom certificates**:

1. Mount certificates into container:
   ```yaml
   volumes:
     - ./certs:/app/certs
   ```

2. Set environment variables:
   ```yaml
   environment:
     - DISABLE_SSL=false
     - SSL_CERT_FILE=/app/certs/cert.pem
     - SSL_KEY_FILE=/app/certs/key.pem
   ```

### Database Migration Status Warning

**NOTE**: The PostgreSQL migration is currently in progress. As documented in `spec-files-aunoo/plans/COMPLETE_MIGRATION_AUDIT.md`:

- **41 database methods** still use SQLite-only patterns
- Most common features work correctly (articles, topics, analysis)
- Some admin features may have issues:
  - User management
  - Newsletter configuration
  - Database administration tools

**Affected Subsystems**:
- ⚠️ User authentication (OAuth, password changes)
- ⚠️ Topic management (creation, deletion)
- ⚠️ Newsletter prompts
- ⚠️ Configuration settings
- ⚠️ Database introspection tools

**Workaround**: For full compatibility, continue using SQLite (`aunooai-dev`) until migration is complete.

## Performance Tuning

### PostgreSQL Performance

Edit connection pool settings in `docker-compose.yml`:

```yaml
environment:
  # Increase for high-traffic production
  - DB_POOL_SIZE=50
  - DB_MAX_OVERFLOW=20
  - DB_POOL_TIMEOUT=30
  - DB_POOL_RECYCLE=3600
```

**Guidelines**:
- Development: `POOL_SIZE=10-20`
- Staging: `POOL_SIZE=20-30`
- Production: `POOL_SIZE=50-100`

### Resource Limits

Add resource constraints to `docker-compose.yml`:

```yaml
services:
  aunooai-prod:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 4G
        reservations:
          cpus: '1.0'
          memory: 2G
```

## Advanced Configuration

### Custom Database Names

Each instance can use a different database:

```yaml
environment:
  - DB_NAME=aunoo_db_prod      # Production
  - DB_NAME=aunoo_db_staging   # Staging
  - DB_NAME=aunoo_db_dev       # Development
```

### External PostgreSQL

To use an external PostgreSQL server:

```yaml
environment:
  - DB_TYPE=postgresql
  - DB_HOST=external-postgres.example.com
  - DB_PORT=5432
  - DB_NAME=aunoo_db
  - DB_USER=aunoo_user
  - DB_PASSWORD=${EXTERNAL_DB_PASSWORD}
```

### Health Checks

The Dockerfile includes a health check:

```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1
```

Check health status:

```bash
docker-compose ps
docker inspect $(docker-compose ps -q aunooai-dev) | grep -A 10 Health
```

## Building Custom Images

### With Build Arguments

```bash
docker-compose build \
  --build-arg APP_VERSION=1.2.3 \
  --build-arg APP_GIT_BRANCH=main \
  --build-arg APP_BUILD_DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
```

### Pushing to Registry

```bash
# Tag image
docker tag aunooai:latest myregistry.com/aunooai:1.2.3

# Push to registry
docker push myregistry.com/aunooai:1.2.3
```

## Security Best Practices

1. **Change default passwords**:
   ```bash
   export POSTGRES_PASSWORD=$(openssl rand -base64 32)
   export ADMIN_PASSWORD=$(openssl rand -base64 32)
   ```

2. **Don't commit `.env` files** to version control

3. **Use secrets management** in production (Docker Swarm secrets, Kubernetes secrets)

4. **Restrict PostgreSQL port** exposure (don't expose to public internet)

5. **Use SSL certificates** for production deployments

6. **Regular backups** of volumes and databases

7. **Update base images** regularly:
   ```bash
   docker-compose pull
   docker-compose build --pull
   ```

## Monitoring and Logs

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f aunooai-dev-postgres

# Last 100 lines
docker-compose logs --tail=100 aunooai-dev-postgres

# Since timestamp
docker-compose logs --since 2024-01-01T10:00:00 aunooai-dev-postgres
```

### Container Stats

```bash
# Resource usage
docker stats

# Specific container
docker stats $(docker-compose ps -q aunooai-dev-postgres)
```

## Next Steps

1. Review the [PostgreSQL migration audit](../spec-files-aunoo/plans/COMPLETE_MIGRATION_AUDIT.md)
2. Check [main specification](../spec-files-aunoo/main.md) for feature details
3. See [compilation instructions](../spec-files-aunoo/compile.claude.md) for development guidelines
4. Set up [monitoring and alerting](#monitoring-and-logs)
5. Configure [backups](#backing-up-data)

## Support

For issues and questions:
- Check troubleshooting section above
- Review container logs
- Inspect database connectivity
- Verify environment variables
- Check the [migration audit](../spec-files-aunoo/plans/COMPLETE_MIGRATION_AUDIT.md) for known limitations
