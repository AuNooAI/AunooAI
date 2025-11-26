# Docker Installation Guide

### Quick Start (5 Minutes)

Get AunooAI running using the pre-built Docker Hub image.

#### Prerequisites

* Docker Engine 20.10+ and Docker Compose v2+
* 4GB RAM minimum (8GB recommended)
* 10GB disk space

#### Installation Steps

1. Download the configuration files

```
# Create directory
mkdir aunooai && cd aunooai
# Download docker-compose.yml
curl -O https://github.com/AuNooAI/AunooAI/blob/main/docker-compose.yml
mv docker-compose.hub.yml docker-compose.yml
# Download .env template
curl -O https://github.com/AuNooAI/AunooAI/blob/main/.env.hub
cp .env.hub .env
```

2. Configure settings

```
nano .env
```

Required changes:

* POSTGRES\_PASSWORD: Change from default aunoo\_secure\_2025
* ADMIN\_PASSWORD: Change from default admin123

3. Start the application

```
docker-compose up -d
```

4. Access AunooAI

* URL: [http://localhost:10001](http://localhost:10001)
* Username: admin
* Password: (what you set in ADMIN\_PASSWORD)

5. Configure API keys

* Log in to the application
* Go to Settings → AI-guided Topic Setup
* Add your API keys (OpenAI, Anthropic, NewsAPI, Firecrawl)
* Keys are saved in a persistent Docker volume

That's it! You're now running AunooAI Community Edition.

***

### Docker Hub Image

Image: aunooai/aunoo-community:latest\
Pre-built images are available at: [https://hub.docker.com/repository/docker/aunooai/aunoo-community](https://hub.docker.com/repository/docker/aunooai/aunoo-community)

Tags:

* latest - Most recent stable release (recommended)
* v1.x.x - Specific version tags
* dev - Development/testing builds (not recommended for production)

***

### Configuration

#### Environment Variables

Edit .env to customize your deployment:

Required Settings:

```
# Database password (CHANGE THIS!)
POSTGRES_PASSWORD=your-secure-password
# Admin login password (CHANGE THIS!)
ADMIN_PASSWORD=your-admin-password
# Application port
APP_PORT=10001
# PostgreSQL port (change if 5432 is in use)
POSTGRES_PORT=5433
API Keys (configure via web interface after first login):
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
# Database Settings:
POSTGRES_USER=aunoo_user
POSTGRES_DB=aunoo_db
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=10
```

***

### Common Commands

#### Start/Stop Services

```
# Start all services
docker-compose up -d
# Stop all services
docker-compose down
# Restart application only
docker-compose restart aunooai
# Restart everything
docker-compose restart
```

#### View Logs

```
# All services
docker-compose logs -f
# Application only
docker-compose logs -f aunooai
# PostgreSQL only
docker-compose logs -f postgres
# Last 100 lines
docker-compose logs --tail=100 aunooai
```

#### Update to Latest Version

```
# Pull latest image
docker-compose pull aunooai
# Restart with new image
docker-compose up -d aunooai
```



***

### Data Persistence

#### Docker Volumes

Your data is stored in Docker volumes:

* postgres\_data - Database files
* aunooai\_data - SQLite files, uploads
* aunooai\_reports - Generated reports
* aunooai\_env - API keys and configuration
* aunooai\_config - Application settings

List volumes:

```
docker volume ls | grep aunooai
```

#### Backup Data

Backup database:

```
# Create backup file
docker-compose exec postgres pg_dump -U aunoo_user aunoo_db > aunoo_backup_$(date +%Y%m%d).sql
# Or with compression
docker-compose exec postgres pg_dump -U aunoo_user aunoo_db | gzip > aunoo_backup_$(date +%Y%m%d).sql.gz
```

Backup volumes:

```
# Backup all volumes
docker run --rm -v aunooai_data:/data -v $(pwd):/backup \
alpine tar czf /backup/aunooai_volumes_$(date +%Y%m%d).tar.gz -C / data
# Backup specific volume
docker run --rm -v aunooai_env:/data -v $(pwd):/backup \
  alpine tar czf /backup/aunooai_env_$(date +%Y%m%d).tar.gz -C /data .
```

#### Restore Data

Restore database:

```
# From SQL file
docker-compose exec -T postgres psql -U aunoo_user aunoo_db < aunoo_backup.sql
# From compressed file
gunzip -c aunoo_backup.sql.gz | docker-compose exec -T postgres psql -U aunoo_user aunoo_db
```

Restore volume:

```
# Stop application first
docker-compose down aunooai
# Restore volume
docker run --rm -v aunooai_env:/data -v $(pwd):/backup \
  alpine tar xzf /backup/aunooai_env_backup.tar.gz -C /data
# Restart
docker-compose up -d
```

***

### Troubleshooting

#### Application won't start

Check logs:

```
docker-compose logs aunooai
```

#### &#x20;Port already in use

* Change APP\_PORT in .env
* Change POSTGRES\_PORT if PostgreSQL port conflicts

#### Database connection failed

```
# Check PostgreSQL is healthy
docker-compose ps postgres
# Wait for health check (may take 30s)
docker-compose logs postgres | grep "ready to accept connections"
```

#### Permission errors

```
# Fix volume permissions
docker-compose down
docker volume rm aunooai_data aunooai_reports
docker-compose up -d
```

#### Can't log in

Reset admin password:

```
# Stop application
docker-compose down aunooai
# Update .env with new ADMIN_PASSWORD
nano .env
# Restart
docker-compose up -d aunooai
```

#### Database errors

Check PostgreSQL logs:

```
docker-compose logs postgres | grep ERROR
```

Connect to database:

```
docker-compose exec postgres psql -U aunoo_user aunoo_db
```

Check connection pool:

```
# Inside PostgreSQL
SELECT count(*) FROM pg_stat_activity WHERE datname = 'aunoo_db';
```

***

### Upgrading

#### To Latest Version

```
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

#### To Specific Version

```
# Edit docker-compose.yml
nano docker-compose.yml
# Change image line:
# image: aunooai/aunoo-community:v1.2.3
# Pull and restart
docker-compose pull aunooai
docker-compose up -d aunooai
```

#### Rollback

```
# Stop application
docker-compose down aunooai
# Edit docker-compose.yml to previous version
nano docker-compose.yml
# Restore database if needed
docker-compose exec -T postgres psql -U aunoo_user aunoo_db < backup_before_upgrade.sql
# Start with old version
docker-compose up -d aunooai
```

***

### Advanced Configuration

#### Custom Ports

Edit docker-compose.yml:

```
services:
 aunooai:
 ports:
  - "8080:10001"  # Access at localhost:8080
```

#### Multiple Instances

Run multiple AunooAI instances:

```
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

#### Resource Limits

Edit docker-compose.yml to add resource limits:

```
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

***

### Getting Help

Application Issues:

* Check logs: docker-compose logs -f aunooai
* Health status: curl http://localhost:10001/health
* [Getting Started Guide](https://docs.google.com/document/d/1Rkk_Hz4fXedv-J4-R_h_cTaLuQWJWsBEc6GreckkinM/edit?tab=t.0)
* [Operations HQ](https://docs.google.com/document/d/1Rkk_Hz4fXedv-J4-R_h_cTaLuQWJWsBEc6GreckkinM/edit?tab=t.ijpfkxcdprf) - System health monitoring

Docker Issues:

* System status: docker-compose ps
* Resource usage: docker stats
* Disk space: docker system df

<br>
