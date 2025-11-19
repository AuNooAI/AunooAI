# AunooAI Community Edition - Docker Deployment

## Quick Start

### Prerequisites
- Docker Engine 20.10+ and Docker Compose 1.29+
- At least 4GB RAM available for Docker
- OpenAI API key (required)

### Setup

1. **Clone the repository** (or download the release)
   ```bash
   git clone https://github.com/your-org/aunooai.git
   cd aunooai
   ```

2. **Configure environment variables**
   ```bash
   cp .env.docker.example .env
   # Edit .env and set your API keys and passwords
   nano .env
   ```

3. **Start the application**
   ```bash
   docker-compose up -d
   ```

4. **Access the application**
   - Open browser: `http://localhost:8080`
   - Default credentials will be created on first run

### Configuration

#### Required Environment Variables
- `OPENAI_API_KEY` - Your OpenAI API key (required for AI features)
- `POSTGRES_PASSWORD` - Secure password for PostgreSQL database

#### Optional Environment Variables
- `APP_PORT` - Application port (default: 8080)
- `ANTHROPIC_API_KEY` - Claude API key (optional)
- `NEWSAPI_KEY` - NewsAPI key for article collection
- `FIRECRAWL_API_KEY` - Firecrawl API for web scraping
- `ELEVENLABS_API_KEY` - ElevenLabs for text-to-speech

### Database

AunooAI Community Edition uses **PostgreSQL with pgvector** for vector search capabilities. SQLite is not supported in Docker deployments.

**PostgreSQL Configuration:**
- Default database: `aunoo_db`
- Default user: `aunoo_user`
- Default port: 5432 (mapped to host 5432)

**Connection pooling** is automatically configured:
- Pool size: 20 connections
- Max overflow: 10 additional connections
- Pool timeout: 30 seconds
- Connection recycling: 1 hour

### Volume Management

Docker volumes persist your data:
- `postgres_data` - PostgreSQL database files
- `aunooai_data` - Application data and configurations
- `aunooai_reports` - Generated reports and exports

**Backup volumes:**
```bash
docker run --rm -v aunooai_postgres_data:/data -v $(pwd):/backup \
  alpine tar czf /backup/aunooai-backup-$(date +%Y%m%d).tar.gz /data
```

**Restore volumes:**
```bash
docker run --rm -v aunooai_postgres_data:/data -v $(pwd):/backup \
  alpine tar xzf /backup/aunooai-backup-20250119.tar.gz -C /
```

### Common Commands

**View logs:**
```bash
docker-compose logs -f aunooai        # Application logs
docker-compose logs -f postgres       # Database logs
```

**Restart services:**
```bash
docker-compose restart aunooai
docker-compose restart postgres
```

**Stop services:**
```bash
docker-compose down                   # Stop but keep volumes
docker-compose down -v                # Stop and remove volumes (⚠️ data loss)
```

**Rebuild after updates:**
```bash
git pull
docker-compose build --no-cache
docker-compose up -d
```

**Run database migrations:**
```bash
docker-compose exec aunooai alembic upgrade head
```

**Access database directly:**
```bash
docker-compose exec postgres psql -U aunoo_user -d aunoo_db
```

### Troubleshooting

#### Container won't start - PORT error
**Symptom:** `ValueError: invalid literal for int() with base 10: ''`

**Solution:** Ensure `PORT` is set in `.env`:
```bash
APP_PORT=8080
```

#### PostgreSQL connection timeout
**Symptom:** `ERROR: PostgreSQL connection timeout!`

**Check:**
1. PostgreSQL container is running: `docker-compose ps`
2. Database credentials match in `.env`
3. Network connectivity: `docker-compose exec aunooai ping postgres`

#### Migration failed
**Symptom:** `Database migrations FAILED!`

**Solution:**
```bash
# Check PostgreSQL is healthy
docker-compose exec postgres pg_isready -U aunoo_user -d aunoo_db

# Manually run migrations
docker-compose exec aunooai alembic upgrade head

# Check migration history
docker-compose exec aunooai alembic current
```

#### Image size too large
**Note:** The Docker image uses multi-stage builds to minimize size:
- Builder stage: ~2GB (discarded)
- Runtime stage: ~1.5GB (includes ML models)

**Large dependencies:**
- sentence-transformers (~500MB) - For semantic search
- spaCy models (~100MB) - For NLP
- BERTopic (~300MB) - For topic modeling

These are required for AI features and cannot be reduced significantly.

### Security Recommendations

1. **Change default passwords** in `.env`
2. **Use secrets management** for production:
   ```bash
   docker secret create postgres_password /path/to/secret
   ```
3. **Enable HTTPS** via reverse proxy (Nginx, Caddy, Traefik)
4. **Restrict PostgreSQL port** - don't expose 5432 publicly
5. **Run as non-root** (uncomment USER line in Dockerfile)

### Production Deployment

For production environments:

1. **Use Docker secrets** instead of environment variables
2. **Set up reverse proxy** with SSL/TLS
3. **Configure backups** (automated daily snapshots)
4. **Monitor resources** (CPU, memory, disk)
5. **Set up logging** (centralized log aggregation)

**Example Nginx configuration:**
```nginx
server {
    listen 443 ssl http2;
    server_name aunoo.example.com;

    ssl_certificate /etc/ssl/certs/aunoo.crt;
    ssl_certificate_key /etc/ssl/private/aunoo.key;

    location / {
        proxy_pass http://localhost:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Performance Tuning

**For high-traffic deployments:**

1. **Increase connection pool:**
   ```env
   DB_POOL_SIZE=50
   DB_MAX_OVERFLOW=20
   ```

2. **Add resource limits** in docker-compose.yml:
   ```yaml
   aunooai:
     deploy:
       resources:
         limits:
           cpus: '2'
           memory: 4G
         reservations:
           cpus: '1'
           memory: 2G
   ```

3. **Enable pgvector index:**
   ```sql
   -- Connect to database
   docker-compose exec postgres psql -U aunoo_user -d aunoo_db

   -- Create HNSW index for faster searches
   CREATE INDEX ON articles USING hnsw (embedding vector_cosine_ops);
   ```

### Support

- GitHub Issues: https://github.com/your-org/aunooai/issues
- Documentation: https://docs.aunoo.ai
- Community: https://discord.gg/aunooai

### License

AunooAI Community Edition is licensed under [LICENSE TYPE].
See LICENSE file for details.
