# AunooAI Community Edition - Docker Deployment Guide

Run AunooAI with Docker in under 5 minutes!

---

## 🚀 Quick Start (Automated Setup)

### Windows Users

1. **Download the deployment package:**

   **Option A: From GitHub Releases (recommended)**
   - Download the latest release: https://github.com/orochford/AunooAI/releases/latest
   - Extract `aunooai-docker.zip`
   - Open PowerShell in the extracted folder

   **Option B: Direct script download (if repository is public)**
   ```powershell
   # Download the setup wizard
   Invoke-WebRequest -Uri "https://raw.githubusercontent.com/orochford/AunooAI/main/setup-docker.ps1" -OutFile "setup-docker.ps1"
   ```

2. **Run the setup wizard:**
   ```powershell
   # Run the wizard
   .\setup-docker.ps1
   ```

2. **Follow the prompts:**
   - Enter your PostgreSQL password
   - Enter your admin password
   - Add your OpenAI API key (required)
   - Optionally add other API keys (Anthropic, NewsAPI, etc.)

3. **Access your instance:**
   - Open browser to: **http://localhost:10001**
   - Username: `admin`
   - Password: (the one you set)

### Linux/Mac Users

1. **Download the deployment package:**

   **Option A: From GitHub Releases (recommended)**
   ```bash
   # Download and extract the latest release
   wget https://github.com/orochford/AunooAI/releases/latest/download/aunooai-docker.tar.gz
   tar -xzf aunooai-docker.tar.gz
   cd aunooai-docker
   ```

   **Option B: Direct script download (if repository is public)**
   ```bash
   # Download the setup script
   curl -fsSL https://raw.githubusercontent.com/orochford/AunooAI/main/setup-docker.sh -o setup-docker.sh
   chmod +x setup-docker.sh
   ```

2. **Run the setup wizard:**
   ```bash
   # Run the wizard
   ./setup-docker.sh
   ```

2. **Follow the prompts:**
   - Enter your PostgreSQL password
   - Enter your admin password
   - Add your OpenAI API key (required)
   - Optionally add other API keys

3. **Access your instance:**
   - Open browser to: **http://localhost:10001**
   - Username: `admin`
   - Password: (the one you set)

---

## 📦 Manual Setup (Alternative)

If you prefer manual setup:

### Step 1: Create Environment File (Optional)

The application works out of the box with default settings! You can optionally customize:

```bash
# Copy the example file
cp .env.hub .env

# Edit if you want to customize
nano .env  # or use your preferred editor
```

**Default settings (works without changes):**
- Admin username: `admin`
- Admin password: `admin123` (change after first login!)
- PostgreSQL password: `aunoo_secure_2025`
- Port: `10001`

**Optional customizations:**
```bash
# Change admin password (recommended for production)
ADMIN_PASSWORD=your_secure_password

# Change database password (recommended for production)
POSTGRES_PASSWORD=your_secure_db_password

# Change ports if needed
APP_PORT=10001
POSTGRES_PORT=5432
```

**Note:** API keys (OpenAI, Anthropic, etc.) are configured through the onboarding wizard after first login. You don't need to set them in `.env`!

### Step 2: Start the Services

```bash
# Start AunooAI and PostgreSQL (uses defaults, no .env needed!)
docker-compose up -d

# Check that services are running
docker-compose ps

# View logs (optional)
docker-compose logs -f
```

**That's it!** The application is ready to use with default settings.

### Step 3: Access the Application

Open your browser to: **http://localhost:10001**

**Default login:**
- Username: `admin`
- Password: `admin123`

**⚠️ Important:**
1. Change your admin password after first login!
2. Configure your API keys through the onboarding wizard (OpenAI, Anthropic, etc.)

---

## 📋 Prerequisites

Before you start, make sure you have:

- **Docker Desktop** installed ([Download here](https://www.docker.com/products/docker-desktop))
- **8GB RAM** minimum (16GB recommended)
- **10GB disk space** available

Verify Docker is running:
```bash
docker --version
# Should show version 20.x or higher
```

**Note:** API keys (OpenAI, Anthropic, etc.) will be configured through the web interface after first login!

---

## 🔧 Configuration

### Default Configuration (Works Out of the Box!)

| Setting | Default Value | Description |
|---------|--------------|-------------|
| `ADMIN_PASSWORD` | `admin123` | Admin password (change after first login) |
| `POSTGRES_PASSWORD` | `aunoo_secure_2025` | Database password |
| `APP_PORT` | `10001` | Application port |

**API keys are configured via the onboarding wizard** - no need to set them in `.env`!

### Optional Configuration

| Setting | Description | Where to get it |
|---------|-------------|-----------------|
| `ANTHROPIC_API_KEY` | Claude AI models | https://console.anthropic.com/ |
| `NEWSAPI_KEY` | News aggregation | https://newsapi.org/register |
| `FIRECRAWL_API_KEY` | Web scraping | https://www.firecrawl.dev/ |
| `ELEVENLABS_API_KEY` | Text-to-speech | https://elevenlabs.io/ |
| `GEMINI_API_KEY` | Google Gemini | https://makersuite.google.com/app/apikey |

### Port Configuration

If the default ports are already in use on your system:

```bash
# In .env file, change:
APP_PORT=10001        # Change to any available port (e.g., 9000)
POSTGRES_PORT=5432   # Change if PostgreSQL is already running (e.g., 5433)
```

---

## 🎯 What's Included

The Docker deployment includes:

- **AunooAI Application** - Full-featured AI analysis platform
- **PostgreSQL + pgvector** - Vector-enabled database
- **React UI** - Modern web interface (Trend Convergence dashboard)
- **Persistent Storage** - Your data survives container restarts
- **Automatic Migrations** - Database schema updates automatically
- **Health Checks** - Ensures services are running properly

---

## 🔍 Verification

### Check Services are Running

```bash
docker-compose ps
```

You should see:
- `postgres` - Status: "Up (healthy)"
- `aunooai` - Status: "Up (healthy)"

### Check Logs

```bash
# View all logs
docker-compose logs -f

# View just AunooAI logs
docker-compose logs -f aunooai

# View just PostgreSQL logs
docker-compose logs -f postgres
```

### Test the Application

```bash
# Health check endpoint
curl http://localhost:10001/health

# Should return: {"status": "ok"}
```

---

## 🛠️ Common Commands

### Managing the Application

```bash
# Start services
docker-compose up -d

# Stop services (keeps data)
docker-compose stop

# Restart services
docker-compose restart

# Stop and remove containers (keeps data in volumes)
docker-compose down

# View logs
docker-compose logs -f

# Check status
docker-compose ps
```

### Updating to Latest Version

```bash
# Pull the latest image
docker pull aunooai/aunoo-community:latest

# Restart with new image
docker-compose up -d

# Or manually restart
docker-compose down
docker-compose up -d
```

### Backup Your Data

```bash
# Backup database
docker-compose exec postgres pg_dump -U aunoo_user aunoo_db > backup_$(date +%Y%m%d).sql

# Backup all volumes
docker run --rm \
  -v testbedaunooai_aunooai_data:/data \
  -v testbedaunooai_aunooai_reports:/reports \
  -v testbedaunooai_aunooai_env:/env \
  -v $(pwd):/backup \
  alpine tar czf /backup/aunooai_backup_$(date +%Y%m%d).tar.gz /data /reports /env
```

### Restore from Backup

```bash
# Restore database
cat backup_20250119.sql | docker-compose exec -T postgres psql -U aunoo_user aunoo_db
```

---

## 🐛 Troubleshooting

### Container Won't Start

**Check the logs:**
```bash
docker-compose logs -f aunooai
```

**Common issues:**
- PostgreSQL not ready → Wait 30 seconds and check `docker-compose ps`
- Missing API keys → Check `.env` file has `OPENAI_API_KEY` set
- Port conflict → Change `APP_PORT` in `.env` to different port

### Can't Access http://localhost:10001

**Verify containers are running:**
```bash
docker-compose ps
```

**Check what port is actually mapped:**
```bash
docker-compose ps aunooai
```

Look for the port mapping (e.g., `0.0.0.0:10001->10001/tcp`)

**Try accessing by IP:**
```bash
# Get container IP
docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' $(docker-compose ps -q aunooai)

# Access directly
curl http://<container-ip>:10001/health
```

### Database Connection Failed

**Verify PostgreSQL is running:**
```bash
docker-compose ps postgres
```

**Test database connection:**
```bash
docker-compose exec postgres pg_isready -U aunoo_user
```

**Check environment variables:**
```bash
docker-compose exec aunooai env | grep DB_
```

### Permission Errors

**Fix volume permissions:**
```bash
docker-compose exec aunooai chmod -R 777 /app/app/data /app/reports /app/tmp
```

### Reset Everything (⚠️ Deletes all data!)

```bash
# Stop and remove containers
docker-compose down

# Remove volumes (THIS DELETES ALL DATA!)
docker volume rm testbedaunooai_postgres_data testbedaunooai_aunooai_data testbedaunooai_aunooai_reports testbedaunooai_aunooai_env testbedaunooai_aunooai_config

# Start fresh
docker-compose up -d
```

---

## 🔒 Security Best Practices

### For Production Deployments

1. **Use strong passwords:**
   - PostgreSQL: minimum 16 characters, random
   - Admin: minimum 12 characters, random

2. **Secure API keys:**
   - Never commit `.env` to version control
   - Use environment-specific `.env` files
   - Rotate keys regularly

3. **Network security:**
   - Don't expose PostgreSQL port to public (remove from `ports:` in docker-compose.yml)
   - Use reverse proxy (nginx/traefik) with SSL
   - Enable firewall rules

4. **Regular updates:**
   ```bash
   # Update to latest version weekly
   docker pull aunooai/aunoo-community:latest
   docker-compose up -d
   ```

5. **Monitor logs:**
   ```bash
   # Check for suspicious activity
   docker-compose logs --tail=100 aunooai
   ```

---

## 📊 System Requirements

### Minimum Requirements

- **CPU:** 2 cores
- **RAM:** 8GB
- **Disk:** 10GB free space
- **Network:** Internet connection for API calls

### Recommended Requirements

- **CPU:** 4+ cores
- **RAM:** 16GB
- **Disk:** 50GB+ free space (for articles and reports)
- **Network:** Fast internet for better API response times

---

## 🌐 Advanced Configuration

### Using a Reverse Proxy

**Nginx example:**
```nginx
server {
    listen 80;
    server_name aunoo.example.com;

    location / {
        proxy_pass http://localhost:10001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

**Add SSL with Let's Encrypt:**
```bash
sudo certbot --nginx -d aunoo.example.com
```

### Custom Domain Setup

1. Point your domain DNS to your server IP
2. Configure reverse proxy (see above)
3. Update `.env`:
   ```bash
   ENVIRONMENT=production
   ```

---

## 📚 Additional Resources

- **Full Documentation:** See main README.md
- **API Documentation:** http://localhost:10001/docs (after starting)
- **GitHub Repository:** https://github.com/orochford/AunooAI
- **Docker Hub:** https://hub.docker.com/r/aunooai/aunoo-community

---

## ❓ Getting Help

### Before Asking for Help

1. Check the logs: `docker-compose logs -f`
2. Verify all services are healthy: `docker-compose ps`
3. Check your `.env` file has all required settings
4. Try restarting: `docker-compose restart`

### Where to Get Help

- **GitHub Issues:** https://github.com/orochford/AunooAI/issues
- **Documentation:** Check this file for complete deployment guide
- **Health Check:** http://localhost:10001/health

---

## 🎉 Next Steps

After your AunooAI instance is running:

1. **Change your admin password** (Settings → Account)
2. **Configure additional API keys** (Settings → API Keys)
3. **Try the Trend Convergence dashboard** (http://localhost:10001/trend-convergence)
4. **Add keywords to monitor** (Keywords page)
5. **Analyze your first article** (Paste URL or text)

---

**Last Updated:** 2025-11-19
**Version:** Community Edition
**Image:** aunooai/aunoo-community:latest
