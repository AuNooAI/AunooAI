# AunooAI Docker - Quick Install

Fast installation guide for Windows and Linux users.

## Prerequisites

- Docker Desktop (Windows) or Docker (Linux)
- 4GB RAM minimum, 8GB recommended

## Install in 3 Steps

### 1. Download Deployment Files

**Windows (PowerShell):**
```powershell
mkdir aunooai
cd aunooai
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/orochford/AunooAI/main/docker-compose.yml" -OutFile "docker-compose.yml"
```

**Linux:**
```bash
mkdir aunooai && cd aunooai
curl -O https://raw.githubusercontent.com/orochford/AunooAI/main/docker-compose.yml
```

### 2. Start AunooAI

```bash
docker-compose up -d
```

Wait 30-60 seconds for containers to start.

### 3. Access & Configure

Open browser: **http://localhost:10001**

**Default Login:**
- Username: `admin`
- Password: `admin123`

⚠️ Change password and add API keys via the onboarding wizard!

---

## Optional: Custom Configuration

Create a `.env` file before starting:

```env
# Custom Settings
APP_PORT=10001
ADMIN_PASSWORD=your_secure_password

# Database
POSTGRES_PASSWORD=your_db_password
POSTGRES_PORT=5433

# API Keys (or configure via wizard)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
NEWSAPI_KEY=...
```

Then start:
```bash
docker-compose up -d
```

---

## Common Commands

**View Logs:**
```bash
docker-compose logs -f aunooai
```

**Stop:**
```bash
docker-compose down
```

**Restart:**
```bash
docker-compose restart
```

**Update:**
```bash
docker-compose pull
docker-compose up -d
```

**Check Status:**
```bash
docker-compose ps
```

---

## Troubleshooting

### Port 10001 Already in Use?

Change port in `.env`:
```env
APP_PORT=10002
```

Then restart:
```bash
docker-compose down
docker-compose up -d
```

### Container Won't Start?

Check logs:
```bash
docker-compose logs aunooai
docker-compose logs postgres
```

### Can't Access UI?

Verify containers are healthy:
```bash
docker-compose ps
```

Both `postgres` and `aunooai` should show "Up (healthy)".

### Database Issues?

Reset database:
```bash
docker-compose down -v  # Removes all volumes!
docker-compose up -d
```

---

## Data Persistence

Your data is stored in Docker volumes:
- `aunooai_data` - Application data
- `aunooai_env` - API keys and configuration
- `aunooai_reports` - Generated reports
- `postgres_data` - Database

These persist even when containers are stopped.

---

## Production Deployment

For production use:

1. **Use strong passwords** in `.env`
2. **Configure reverse proxy** (nginx/Caddy)
3. **Enable HTTPS**
4. **Backup volumes** regularly
5. **Monitor logs**

Example nginx config:
```nginx
server {
    listen 443 ssl;
    server_name aunoo.yourdomain.com;

    location / {
        proxy_pass http://localhost:10001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## Support

- Documentation: Full README.md in repository
- Issues: GitHub Issues
- Docker Hub: https://hub.docker.com/r/aunooai/aunoo-community

---

**That's it! You're ready to use AunooAI.**
