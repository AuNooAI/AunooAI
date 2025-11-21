# Aunoo AI - Docker Deployment Guide

Deploy Aunoo AI using pre-built Docker images from Docker Hub in under 5 minutes.

**Docker Hub Image**: https://hub.docker.com/r/aunooai/aunoo-community
**Community Repository**: https://github.com/AuNooAI/aunooai-community

---

## 🚀 Quick Start (3 Steps)

### 1. Download Deployment Files

**Using curl (Linux/Mac):**
```bash
mkdir aunooai && cd aunooai
curl -O https://raw.githubusercontent.com/AuNooAI/aunooai-community/main/docker-compose.yml
```

**Using PowerShell (Windows):**
```powershell
mkdir aunooai; cd aunooai
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/AuNooAI/aunooai-community/main/docker-compose.yml" -OutFile "docker-compose.yml"
```

### 2. Start Aunoo AI

```bash
docker-compose up -d
```

Wait 30-60 seconds for services to initialize.

### 3. Access & Configure

Open browser: **http://localhost:10001**

**Default credentials:**
- Username: `admin`
- Password: `admin123`

⚠️ **Change password immediately and configure API keys via the onboarding wizard!**

---

## 📦 Automated Setup (Recommended)

For a guided setup experience with interactive configuration:

### Windows (PowerShell)

```powershell
# Download setup wizard
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/AuNooAI/aunooai-community/main/setup-docker.ps1" -OutFile "setup-docker.ps1"

# Run wizard
.\setup-docker.ps1
```

### Linux/Mac

```bash
# Download and run setup wizard
curl -fsSL https://raw.githubusercontent.com/AuNooAI/aunooai-community/main/setup-docker.sh | bash
```

The wizard will:
- ✅ Download required files
- ✅ Guide you through configuration (passwords, API keys)
- ✅ Start Docker containers automatically
- ✅ Open your browser to the application

---

## 🔧 Configuration

### Default Settings (Works Out of the Box)

| Setting | Default | Description |
|---------|---------|-------------|
| Admin Username | `admin` | Default login |
| Admin Password | `admin123` | Change after first login |
| App Port | `10001` | Web interface port |
| Database Password | `aunoo_secure_2025` | PostgreSQL password |

### Custom Configuration (Optional)

Create a `.env` file before starting:

```env
# Security (recommended to change)
ADMIN_PASSWORD=your_secure_password
POSTGRES_PASSWORD=your_db_password

# Ports (if defaults are in use)
APP_PORT=10001
POSTGRES_PORT=5432

# API Keys (or configure via web UI)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
NEWSAPI_KEY=...
ELEVENLABS_API_KEY=...
```

Then start:
```bash
docker-compose up -d
```

---

## 📋 Prerequisites

- **Docker Desktop** ([Download](https://www.docker.com/products/docker-desktop))
- **8GB RAM** minimum (16GB recommended)
- **10GB disk space** available

Verify Docker is running:
```bash
docker --version
# Should show version 20.x or higher
```

---

## 🎯 What's Included

- **Aunoo AI Platform** - Full AI analysis capabilities
- **PostgreSQL + pgvector** - Vector-enabled database
- **React UI** - Modern web interface
- **Persistent Storage** - Data survives container restarts
- **Automatic Migrations** - Database updates handled automatically
- **Health Checks** - Service monitoring built-in

---

## 🛠️ Management Commands

### Basic Operations

```bash
# Start services
docker-compose up -d

# Stop services (keeps data)
docker-compose stop

# Restart services
docker-compose restart

# View logs
docker-compose logs -f

# Check status
docker-compose ps
```

### Updates

```bash
# Pull latest image
docker pull aunooai/aunoo-community:latest

# Restart with new image
docker-compose down
docker-compose up -d
```

### Data Management

```bash
# Backup database
docker-compose exec postgres pg_dump -U aunoo_user aunoo_db > backup_$(date +%Y%m%d).sql

# Restore database
cat backup_20250119.sql | docker-compose exec -T postgres psql -U aunoo_user aunoo_db

# Remove everything (⚠️ deletes all data!)
docker-compose down -v
```

---

## 🐛 Troubleshooting

### Can't Access http://localhost:10001

**Check containers are running:**
```bash
docker-compose ps
```

Both should show "Up (healthy)":
- `postgres`
- `aunooai`

**View logs:**
```bash
docker-compose logs -f aunooai
```

### Port Already in Use

Change port in `.env`:
```env
APP_PORT=10002  # or any available port
```

Then restart:
```bash
docker-compose down
docker-compose up -d
```

### Container Won't Start

**Check logs for errors:**
```bash
docker-compose logs aunooai
docker-compose logs postgres
```

**Common issues:**
- PostgreSQL not ready → Wait 30 seconds
- Missing dependencies → Pull latest image: `docker pull aunooai/aunoo-community:latest`
- Corrupted volumes → Reset: `docker-compose down -v` then `docker-compose up -d`

### Login Issues

- Use port **10001** (or your custom APP_PORT)
- Username is **lowercase**: `admin`
- Default password: `admin123` (or what you set in ADMIN_PASSWORD)

### Database Connection Failed

**Verify PostgreSQL:**
```bash
docker-compose exec postgres pg_isready -U aunoo_user
```

**Check connection settings:**
```bash
docker-compose exec aunooai env | grep DB_
```

---

## 🔒 Production Deployment

### Security Checklist

1. **Change default passwords** in `.env`:
   ```env
   ADMIN_PASSWORD=<strong-random-password>
   POSTGRES_PASSWORD=<strong-random-password>
   ```

2. **Don't expose PostgreSQL** publicly (remove `ports:` from postgres in docker-compose.yml)

3. **Use reverse proxy** with SSL:

   **Nginx example:**
   ```nginx
   server {
       listen 443 ssl;
       server_name aunoo.yourdomain.com;

       ssl_certificate /path/to/cert.pem;
       ssl_certificate_key /path/to/key.pem;

       location / {
           proxy_pass http://localhost:10001;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
   }
   ```

4. **Enable firewall**:
   ```bash
   # Allow only necessary ports
   ufw allow 80/tcp
   ufw allow 443/tcp
   ufw enable
   ```

5. **Regular backups**:
   ```bash
   # Daily backup cron job
   0 2 * * * cd /path/to/aunooai && docker-compose exec postgres pg_dump -U aunoo_user aunoo_db > /backups/aunoo_$(date +\%Y\%m\%d).sql
   ```

6. **Monitor logs**:
   ```bash
   docker-compose logs --tail=100 --follow
   ```

7. **Update regularly**:
   ```bash
   docker pull aunooai/aunoo-community:latest
   docker-compose up -d
   ```

---

## 📊 System Requirements

### Minimum
- **CPU:** 2 cores
- **RAM:** 8GB
- **Disk:** 10GB
- **OS:** Linux, macOS, Windows with Docker

### Recommended
- **CPU:** 4+ cores
- **RAM:** 16GB
- **Disk:** 50GB+ (for articles and reports)
- **OS:** Linux (Ubuntu 20.04+, Debian 11+)

---

## 🌐 Advanced Configuration

### Custom Network

```yaml
# docker-compose.yml
networks:
  aunoo_network:
    driver: bridge
    ipam:
      config:
        - subnet: 172.28.0.0/16
```

### Resource Limits

```yaml
# docker-compose.yml
services:
  aunooai:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G
```

### Multiple Instances

Run multiple isolated instances:

```bash
# Instance 1
cd ~/aunooai-prod
APP_PORT=10001 docker-compose up -d

# Instance 2
cd ~/aunooai-dev
APP_PORT=10002 docker-compose up -d
```

---

## 📚 Additional Resources

- **Docker Hub**: https://hub.docker.com/r/aunooai/aunoo-community
- **Community Repo**: https://github.com/AuNooAI/aunooai-community
- **API Documentation**: http://localhost:10001/docs (after starting)
- **License**: Business Source License 1.1 (see LICENSE)

---

## ❓ Getting Help

**Before asking for help:**
1. Check logs: `docker-compose logs -f`
2. Verify services: `docker-compose ps`
3. Check health: `curl http://localhost:10001/health`
4. Try restart: `docker-compose restart`

**Get support:**
- GitHub Issues: https://github.com/AuNooAI/aunooai-community/issues
- Email: support@aunoo.ai

---

## 🎉 Next Steps

After deployment:

1. **Change admin password** (Settings → Account)
2. **Configure API keys** (Settings → API Keys or onboarding wizard)
   - OpenAI (required for AI features)
   - Anthropic Claude (optional)
   - NewsAPI (optional)
   - ElevenLabs (optional for TTS)
3. **Explore features**:
   - Article analysis
   - Keyword monitoring
   - Six Articles briefing
   - Trend convergence dashboard
4. **Read documentation** in the web UI

---

**Version**: Community Edition
**Last Updated**: 2024-11-21
**License**: Business Source License 1.1

**Questions?** Open an issue or contact support@aunoo.ai
