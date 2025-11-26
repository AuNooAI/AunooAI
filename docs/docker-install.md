# Docker Installation Guide

## Quick Start (5 Minutes)

Get AunooAI running using the pre-built Docker Hub image.

### Prerequisites

- Docker Engine 20.10+ and Docker Compose v2+
- 4GB RAM minimum (8GB recommended)
- 10GB disk space

### Installation Steps

1. **Download the configuration files**
   ```bash
   # Create directory
   mkdir aunooai && cd aunooai

   # Download docker-compose.yml
   curl -O https://raw.githubusercontent.com/AuNooAI/AunooAI/main/docker-compose.hub.yml
   mv docker-compose.hub.yml docker-compose.yml

   # Download .env template
   curl -O https://raw.githubusercontent.com/AuNooAI/AunooAI/main/.env.hub
   cp .env.hub .env
   ```

2. **Configure settings**
   ```bash
   nano .env
   ```

   **Required changes:**
   - `POSTGRES_PASSWORD`: Change from default `aunoo_secure_2025`
   - `ADMIN_PASSWORD`: Change from default `admin123`

3. **Start the application**
   ```bash
   docker-compose up -d
   ```

4. **Access AunooAI**
   - URL: http://localhost:10001
   - Username: `admin`
   - Password: (what you set in `ADMIN_PASSWORD`)

5. **Configure API keys**
   - Log in to the application
   - Go to **Settings → AI-guided Topic Setup**
   - Add your API keys (OpenAI, Anthropic, NewsAPI, Firecrawl)
   - Keys are saved in a persistent Docker volume

**That's it!** You're now running AunooAI Community Edition.

---

## Docker Hub Image

**Image:** `aunooai/aunoo-community:latest`

Pre-built images are available at:
https://hub.docker.com/repository/docker/aunooai/aunoo-community

**Tags:**
- `latest` - Most recent stable release (recommended)
- `v1.x.x` - Specific version tags
- `dev` - Development/testing builds (not recommended for production)

---

## Configuration

### Environment Variables

Edit `.env` to customize your deployment:

**Required Settings:**
```bash
# Database password (CHANGE THIS!)
POSTGRES_PASSWORD=your-secure-password

# Admin login password (CHANGE THIS!)
ADMIN_PASSWORD=your-admin-password

# Application port
APP_PORT=10001

# PostgreSQL port (change if 5432 is in use)
POSTGRES_PORT=5433
```

**API Keys (configure via web interface after first login):**
```bash
# AI Providers (at least one required)
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GEMINI_API_KEY=

# News Providers (at least one required)
NEWSAPI_KEY=
THENEWSAPI_KEY=
NEWSDATA_API_KEY=

# Web Scraping (required)
FIRECRAWL_API_KEY=

# Optional
ELEVENLABS_API_KEY=    # For audio/podcast generation
```

**Database Settings:**
```bash
POSTGRES_USER=aunoo_user
POSTGRES_DB=aunoo_db
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=10
```

---

## Common Commands

### Start/Stop Services

```bash
# Start all services
docker-compose up -d

# Stop all services
docker-compose down

# Restart application only
docker-compose restart aunooai

# Restart everything
docker-compose restart
```

### View Logs

```bash
# All services
docker-compose logs -f

# Application only
docker-compose logs -f aunooai

# PostgreSQL only
docker-compose logs -f postgres

# Last 100 lines
docker-compose logs --tail=100 aunooai
```

### Update to Latest Version

```bash
# Pull latest image
docker-compose pull aunooai

# Restart with new image
docker-compose up -d aunooai
```

---

## Data Persistence

### Docker Volumes

Your data is stored in Docker volumes:

- `postgres_data` - Database files
- `aunooai_data` - SQLite files, uploads
- `aunooai_reports` - Generated reports
- `aunooai_env` - API keys and configuration
- `aunooai_config` - Application settings

**List volumes:**
```bash
docker volume ls | grep aunooai
```

### Backup Data

**Backup database:**
```bash
# Create backup file
docker-compose exec postgres pg_dump -U aunoo_user aunoo_db > aunoo_backup_$(date +%Y%m%d).sql

# Or with compression
docker-compose exec postgres pg_dump -U aunoo_user aunoo_db | gzip > aunoo_backup_$(date +%Y%m%d).sql.gz
```

**Backup volumes:**
```bash
# Backup all volumes
docker run --rm -v aunooai_data:/data -v $(pwd):/backup \
  alpine tar czf /backup/aunooai_volumes_$(date +%Y%m%d).tar.gz -C / data

# Backup specific volume
docker run --rm -v aunooai_env:/data -v $(pwd):/backup \
  alpine tar czf /backup/aunooai_env_$(date +%Y%m%d).tar.gz -C /data .
```

### Restore Data

**Restore database:**
```bash
# From SQL file
docker-compose exec -T postgres psql -U aunoo_user aunoo_db < aunoo_backup.sql

# From compressed file
gunzip -c aunoo_backup.sql.gz | docker-compose exec -T postgres psql -U aunoo_user aunoo_db
```

**Restore volume:**
```bash
# Stop application first
docker-compose down aunooai

# Restore volume
docker run --rm -v aunooai_env:/data -v $(pwd):/backup \
  alpine tar xzf /backup/aunooai_env_backup.tar.gz -C /data

# Restart
docker-compose up -d
```

---

## Troubleshooting

### Application won't start

**Check logs:**
```bash
docker-compose logs aunooai
```

**Common issues:**

1. **Port already in use**
   - Change `APP_PORT` in `.env`
   - Change `POSTGRES_PORT` if PostgreSQL port conflicts

2. **Database connection failed**
   ```bash
   # Check PostgreSQL is healthy
   docker-compose ps postgres

   # Wait for health check (may take 30s)
   docker-compose logs postgres | grep "ready to accept connections"
   ```

3. **Permission errors**
   ```bash
   # Fix volume permissions
   docker-compose down
   docker volume rm aunooai_data aunooai_reports
   docker-compose up -d
   ```

### Can't log in

**Reset admin password:**
```bash
# Stop application
docker-compose down aunooai

# Update .env with new ADMIN_PASSWORD
nano .env

# Restart
docker-compose up -d aunooai
```

### Database errors

**Check PostgreSQL logs:**
```bash
docker-compose logs postgres | grep ERROR
```

**Connect to database:**
```bash
docker-compose exec postgres psql -U aunoo_user aunoo_db
```

**Check connection pool:**
```bash
# Inside PostgreSQL
SELECT count(*) FROM pg_stat_activity WHERE datname = 'aunoo_db';
```

### Out of disk space

**Check disk usage:**
```bash
docker system df -v
```

**Clean up:**
```bash
# Remove unused images
docker image prune -a

# Remove unused volumes (careful!)
docker volume prune

# Full cleanup (WARNING: removes all stopped containers, unused networks, etc.)
docker system prune -a
```

### Application running slowly

**Check container resources:**
```bash
docker stats aunooai postgres
```

**Increase database pool size:**
```bash
# Edit .env
DB_POOL_SIZE=30
DB_MAX_OVERFLOW=20

# Restart
docker-compose restart aunooai
```

---

## Production Deployment

### Security Checklist

- [ ] Change default `POSTGRES_PASSWORD` in `.env`
- [ ] Change default `ADMIN_PASSWORD` in `.env`
- [ ] Use strong, unique passwords (20+ characters)
- [ ] Restrict port access (use firewall)
- [ ] Set up reverse proxy with HTTPS (nginx/Caddy/Traefik)
- [ ] Regular database backups (daily recommended)
- [ ] Monitor logs for errors
- [ ] Keep image updated: `docker-compose pull && docker-compose up -d`
- [ ] Limit PostgreSQL port exposure (remove from `ports:` or use firewall)

### Reverse Proxy (Nginx Example)

```nginx
server {
    listen 80;
    server_name aunoo.example.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name aunoo.example.com;

    ssl_certificate /etc/letsencrypt/live/aunoo.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/aunoo.example.com/privkey.pem;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;

    # Proxy to AunooAI
    location / {
        proxy_pass http://localhost:10001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support (if needed)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

### Monitoring

**Health check:**
```bash
curl http://localhost:10001/health
```

Expected response:
```json
{
  "status": "healthy",
  "uptime": {...},
  "database": "connected"
}
```

**Monitor resources:**
```bash
# Real-time stats
docker stats aunooai postgres

# Check logs for errors
docker-compose logs aunooai | grep -i error
```

### Automated Backups

Add to crontab (`crontab -e`):
```bash
# Daily backup at 2 AM
0 2 * * * cd /path/to/aunooai && docker-compose exec -T postgres pg_dump -U aunoo_user aunoo_db | gzip > /backups/aunoo_$(date +\%Y\%m\%d).sql.gz

# Weekly volume backup (Sundays at 3 AM)
0 3 * * 0 cd /path/to/aunooai && docker run --rm -v aunooai_data:/data -v /backups:/backup alpine tar czf /backup/aunoo_volumes_$(date +\%Y\%m\%d).tar.gz -C /data .

# Cleanup old backups (keep 30 days)
0 4 * * * find /backups -name "aunoo_*.sql.gz" -mtime +30 -delete
```

---

## Upgrading

### To Latest Version

```bash
# Backup first!
docker-compose exec postgres pg_dump -U aunoo_user aunoo_db > backup_before_upgrade.sql

# Pull latest image
docker-compose pull aunooai

# Stop and restart with new image
docker-compose down aunooai
docker-compose up -d aunooai

# Check logs
docker-compose logs -f aunooai
```

### To Specific Version

```bash
# Edit docker-compose.yml
nano docker-compose.yml

# Change image line:
# image: aunooai/aunoo-community:v1.2.3

# Pull and restart
docker-compose pull aunooai
docker-compose up -d aunooai
```

### Rollback

```bash
# Stop application
docker-compose down aunooai

# Edit docker-compose.yml to previous version
nano docker-compose.yml

# Restore database if needed
docker-compose exec -T postgres psql -U aunoo_user aunoo_db < backup_before_upgrade.sql

# Start with old version
docker-compose up -d aunooai
```

---

## Advanced Configuration

### Custom Ports

Edit `docker-compose.yml`:
```yaml
services:
  aunooai:
    ports:
      - "8080:10001"  # Access at localhost:8080
```

### Multiple Instances

Run multiple AunooAI instances:
```bash
# Create separate directories
mkdir aunooai-prod aunooai-dev

# Copy files to each
cp docker-compose.yml aunooai-prod/
cp docker-compose.yml aunooai-dev/

# Edit .env in each with different ports
# aunooai-prod/.env: APP_PORT=10001, POSTGRES_PORT=5433
# aunooai-dev/.env: APP_PORT=10002, POSTGRES_PORT=5434

# Start each instance
cd aunooai-prod && docker-compose up -d
cd ../aunooai-dev && docker-compose up -d
```

### Resource Limits

Edit `docker-compose.yml` to add resource limits:
```yaml
services:
  aunooai:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 4G
        reservations:
          cpus: '1.0'
          memory: 2G
```

---

## Getting Help

**Application Issues:**
- Check logs: `docker-compose logs -f aunooai`
- Health status: `curl http://localhost:10001/health`
- [Getting Started Guide](getting-started-5-minutes.md)
- [Operations HQ](getting-started-operations-hq.md) - System health monitoring

**Docker Issues:**
- System status: `docker-compose ps`
- Resource usage: `docker stats`
- Disk space: `docker system df`

**Community Support:**
- GitHub Issues: https://github.com/AuNooAI/AunooAI/issues
- Docker Hub: https://hub.docker.com/repository/docker/aunooai/aunoo-community

---

*Last updated: 2025-11-25*
