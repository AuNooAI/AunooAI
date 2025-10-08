# Docker Deployment Guide

Complete guide for running AunooAI with Docker and Docker Compose.

---

## Quick Start

```bash
# 1. Copy environment file
cp .env.example .env

# 2. Edit .env and add your API keys
nano .env

# 3. Start development instance (SQLite)
docker-compose up aunooai-dev

# 4. Or start with PostgreSQL
docker-compose --profile postgres up
```

---

## Available Services

### Application Instances

| Service | Port | Database | Use Case |
|---------|------|----------|----------|
| `aunooai-dev` | 6005 | SQLite | Quick development, testing |
| `aunooai-dev-postgres` | 6006 | PostgreSQL | Development with PostgreSQL |
| `aunooai-prod` | 5008 | PostgreSQL | Production deployment |
| `aunooai-staging` | 5009 | PostgreSQL | Staging environment |

### Supporting Services

| Service | Port | Profile | Description |
|---------|------|---------|-------------|
| `postgres` | 5432 | (default) | PostgreSQL database |
| `pgadmin` | 5050 | admin | Database admin interface |

---

## Usage Examples

### Development with SQLite

```bash
# Start development instance
docker-compose up aunooai-dev

# Access at http://localhost:6005
```

### Development with PostgreSQL

```bash
# Start PostgreSQL and dev instance
docker-compose --profile postgres up

# Access at http://localhost:6006
```

### Production Deployment

```bash
# Start PostgreSQL and production instance
docker-compose --profile prod up -d

# Access at http://localhost:5008
```

### Staging Environment

```bash
# Start PostgreSQL and staging instance
docker-compose --profile staging up -d

# Access at http://localhost:5009
```

### With Database Admin (PgAdmin)

```bash
# Start with PgAdmin
docker-compose --profile postgres --profile admin up

# Access PgAdmin at http://localhost:5050
# Email: admin@aunoo.ai
# Password: (from PGADMIN_PASSWORD in .env)
```

---

## Configuration

### Environment Variables

Create `.env` file from `.env.example`:

```bash
cp .env.example .env
```

**Required variables:**

```bash
# Database password
POSTGRES_PASSWORD=your_secure_password

# API Keys
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
FIRECRAWL_API_KEY=fc-...
NEWSAPI_KEY=...
```

**Optional variables:**

```bash
# Admin passwords
ADMIN_PASSWORD=admin
PGADMIN_PASSWORD=admin

# Build metadata
APP_VERSION=1.0.0
GIT_BRANCH=main
BUILD_DATE=2025-01-01
```

---

## Docker Features

### Dockerfile Enhancements

**Python 3.12 Base:**
- Latest Python version
- Slim image for smaller size

**PostgreSQL Support:**
- PostgreSQL client installed
- `libpq-dev` for psycopg2
- Connection health checking

**Smart Entrypoint:**
- Auto-detects database type
- Waits for PostgreSQL to be ready
- Runs migrations automatically
- Configures .env from environment
- Displays startup information

**Health Checks:**
- HTTP health endpoint monitoring
- 30-second intervals
- Auto-restart on failure

**Directory Structure:**
- Creates all required directories
- Sets proper permissions
- Supports audio/podcast features

---

## Database Setup

### PostgreSQL Automatic Setup

When using PostgreSQL services, the entrypoint script:

1. ✅ Waits for PostgreSQL to be ready
2. ✅ Creates database URL in .env
3. ✅ Runs Alembic migrations
4. ✅ Verifies connectivity

### Multiple Databases

Each environment uses a separate database:

| Environment | Database Name |
|-------------|---------------|
| Development | `aunoo_db` |
| Production | `aunoo_db_prod` |
| Staging | `aunoo_db_staging` |

### Manual Database Access

```bash
# Connect to PostgreSQL
docker-compose exec postgres psql -U aunoo_user -d aunoo_db

# List databases
docker-compose exec postgres psql -U aunoo_user -c "\l"

# Backup database
docker-compose exec postgres pg_dump -U aunoo_user aunoo_db > backup.sql

# Restore database
docker-compose exec -T postgres psql -U aunoo_user aunoo_db < backup.sql
```

---

## Volume Management

### Persistent Data Volumes

Data persists across container restarts:

```bash
# List volumes
docker volume ls | grep aunooai

# Inspect volume
docker volume inspect aunooai_prod_data

# Backup volume
docker run --rm -v aunooai_prod_data:/data -v $(pwd):/backup alpine tar czf /backup/prod-data.tar.gz /data

# Restore volume
docker run --rm -v aunooai_prod_data:/data -v $(pwd):/backup alpine tar xzf /backup/prod-data.tar.gz -C /
```

### Cleaning Up Volumes

```bash
# Remove specific volume (⚠️ data loss!)
docker volume rm aunooai_dev_data

# Remove all unused volumes
docker volume prune
```

---

## Building Images

### Build with Metadata

```bash
# Set build args
export APP_VERSION=$(cat version.txt)
export GIT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
export BUILD_DATE=$(date -u +'%Y-%m-%d %H:%M:%S')

# Build image
docker-compose build
```

### Multi-Stage Build (Future)

Current Dockerfile is single-stage. For production optimization, consider:
- Builder stage for dependencies
- Runtime stage with minimal image
- Layer caching optimization

---

## Networking

### Service Communication

All services are on the `aunooai` network:

```yaml
networks:
  aunooai:
    driver: bridge
```

**Internal hostnames:**
- `postgres` - PostgreSQL server
- `aunooai-dev` - Dev instance
- `aunooai-prod` - Prod instance

### Port Mapping

| Internal Port | Host Port | Service |
|--------------|-----------|---------|
| 6005 | 6005 | Dev (SQLite) |
| 6006 | 6006 | Dev (PostgreSQL) |
| 5008 | 5008 | Production |
| 5009 | 5009 | Staging |
| 5432 | 5432 | PostgreSQL |
| 80 | 5050 | PgAdmin |

---

## Monitoring

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f aunooai-prod

# Last 100 lines
docker-compose logs --tail=100 aunooai-prod

# PostgreSQL logs
docker-compose logs -f postgres
```

### Health Status

```bash
# Check service status
docker-compose ps

# Check container health
docker inspect aunooai-prod | grep Health -A 10

# Test health endpoint
curl http://localhost:5008/health
```

### Resource Usage

```bash
# View resource usage
docker stats

# Specific container
docker stats aunooai-prod
```

---

## Troubleshooting

### Container Won't Start

**Check logs:**
```bash
docker-compose logs aunooai-prod
```

**Common issues:**
- Missing environment variables (check .env)
- Port already in use (change PORT in docker-compose.yml)
- Volume permission issues (check permissions)

### Database Connection Failed

**Check PostgreSQL status:**
```bash
docker-compose ps postgres
docker-compose logs postgres
```

**Verify connectivity:**
```bash
docker-compose exec aunooai-prod env | grep DB_
docker-compose exec postgres psql -U aunoo_user -d aunoo_db -c "\q"
```

**Reset database:**
```bash
docker-compose down -v  # ⚠️ Destroys all data!
docker-compose up postgres -d
# Wait for PostgreSQL to initialize
docker-compose up aunooai-prod
```

### Migration Errors

**Run migrations manually:**
```bash
docker-compose exec aunooai-prod alembic upgrade head
```

**Check migration history:**
```bash
docker-compose exec aunooai-prod alembic current
docker-compose exec aunooai-prod alembic history
```

### Out of Memory

**Increase Docker memory:**
- Docker Desktop: Settings → Resources → Memory
- Linux: Modify `/etc/docker/daemon.json`

**Check memory usage:**
```bash
docker stats
```

### Port Conflicts

**Change ports in docker-compose.yml:**
```yaml
ports:
  - "6006:6006"  # Change left side (host port)
```

**Find process using port:**
```bash
lsof -i :6005
```

---

## Production Checklist

Before deploying to production:

- [ ] Set strong `POSTGRES_PASSWORD` in .env
- [ ] Configure all required API keys
- [ ] Set `ENVIRONMENT=production`
- [ ] Use `--profile prod` for production services
- [ ] Enable restart policies (`restart: unless-stopped`)
- [ ] Setup regular database backups
- [ ] Configure log rotation
- [ ] Setup monitoring/alerting
- [ ] Use secrets management (not .env in production)
- [ ] Enable HTTPS with reverse proxy (nginx/traefik)
- [ ] Set resource limits in docker-compose.yml

---

## Advanced Configuration

### Resource Limits

Add to service definition:

```yaml
aunooai-prod:
  # ... other config
  deploy:
    resources:
      limits:
        cpus: '2'
        memory: 4G
      reservations:
        cpus: '1'
        memory: 2G
```

### Custom Networks

```yaml
networks:
  frontend:
    driver: bridge
  backend:
    driver: bridge
    internal: true  # No external access
```

### External Database

Use external PostgreSQL instead of container:

```yaml
aunooai-prod:
  environment:
    - DB_TYPE=postgresql
    - DB_HOST=external-postgres.example.com
    - DB_PORT=5432
    - DB_NAME=aunoo_production
    - DB_USER=aunoo_user
    - DB_PASSWORD=${EXTERNAL_DB_PASSWORD}
```

---

## Maintenance

### Regular Tasks

**Weekly:**
```bash
# Check logs for errors
docker-compose logs --tail=1000 | grep -i error

# Backup databases
docker-compose exec postgres pg_dumpall -U aunoo_user > backup-$(date +%Y%m%d).sql

# Check disk usage
docker system df
```

**Monthly:**
```bash
# Update images
docker-compose pull
docker-compose up -d

# Clean unused resources
docker system prune -a

# Rotate logs (if not using log driver)
truncate -s 0 $(docker inspect --format='{{.LogPath}}' aunooai-prod)
```

---

## Upgrading

### Application Updates

```bash
# 1. Pull latest code
git pull

# 2. Rebuild image
docker-compose build

# 3. Stop old container
docker-compose stop aunooai-prod

# 4. Start new container
docker-compose up -d aunooai-prod

# 5. Check logs
docker-compose logs -f aunooai-prod
```

### Database Migrations

Migrations run automatically on startup. To run manually:

```bash
docker-compose exec aunooai-prod alembic upgrade head
```

---

## References

- [Docker Documentation](https://docs.docker.com/)
- [Docker Compose Reference](https://docs.docker.com/compose/compose-file/)
- [PostgreSQL Docker](https://hub.docker.com/_/postgres)
- [Main README](README.md)
- [PostgreSQL Setup Guide](docs/POSTGRESQL_SETUP.md)

---

**Last Updated:** 2025-10-08
