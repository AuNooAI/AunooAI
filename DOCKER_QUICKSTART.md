# Aunoo AI - One-Command Setup

Get Aunoo AI running with Docker in under 5 minutes!

## Prerequisites

- Docker Desktop installed ([Download](https://www.docker.com/products/docker-desktop))
- 8GB RAM minimum
- 10GB disk space

Verify Docker is running:
```bash
docker --version
```

Should show version 20.x or higher.

---

## 🚀 Automated Setup (Recommended)

### Windows Users

Download and run the setup script:

```powershell
# Download setup script
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/orochford/AunooAI/main/setup-docker.ps1" -OutFile "setup-docker.ps1"

# Run setup wizard
.\setup-docker.ps1
```

The wizard will:
- ✅ Download all necessary files
- ✅ Guide you through configuration (API keys, passwords)
- ✅ Start Docker containers automatically
- ✅ Open your browser to the application

### Linux/Mac Users

Download and run the setup script:

```bash
# Download and run setup script
curl -fsSL https://raw.githubusercontent.com/orochford/AunooAI/main/setup-docker.sh | bash

# Or download first, then run
curl -fsSL https://raw.githubusercontent.com/orochford/AunooAI/main/setup-docker.sh -o setup-docker.sh
chmod +x setup-docker.sh
./setup-docker.sh
```

---

## 📦 Manual Setup (Alternative)

If you prefer to do it manually:

### Step 1: Get Files

```bash
# Option 1: Clone repository
git clone https://github.com/orochford/aunoo-ai.git
cd aunoo-ai

# Option 2: Download just the deployment files
curl -O https://raw.githubusercontent.com/orochford/AunooAI/main/docker-compose.yml
curl -O https://raw.githubusercontent.com/orochford/AunooAI/main/.env.hub
cp .env.hub .env
```

### Step 2: Configure

**Optional:** Edit `.env` file to customize passwords (works with defaults!)

The application uses these defaults:
- Admin login: `admin` / `admin123`
- Database password: `aunoo_secure_2025`

**Recommended for production:**
- Change `ADMIN_PASSWORD` to a secure password
- Change `POSTGRES_PASSWORD` to a secure password

**Note:** API keys are configured via onboarding wizard after first login!

### Step 3: Start

```bash
docker-compose up -d
```

Wait 30-60 seconds for services to be healthy:
```bash
docker-compose ps
```

Look for **"Up (healthy)"** status.

### Login & Configure

Open browser: **http://localhost:8080**

**Login:**
- Username: `admin`
- Password: (the password you set in `.env` ADMIN_PASSWORD)

**Follow the setup wizard:**
1. Change your password
2. Add API keys (OpenAI, Anthropic, etc.)
3. Configure preferences
4. Done!

---

## You're Ready!

Your Aunoo AI instance is now running at:
```
http://localhost:8080
```

### What's Next?

- Read the [Quick Start Guide](QUICK_START_GUIDE.md)
- Try analyzing your first article
- Set up keyword monitoring
- Chat with the AI assistant

---

## Something Not Working?

### Can't access http://localhost:8080?

**Check containers are running:**
```bash
docker-compose ps
```

Both should show "Up (healthy)":
- `postgres`
- `aunooai`

**View logs:**
```bash
docker-compose logs -f
```

### Login not working?

- Use port **8080**
- Username: `admin` (lowercase)
- Password: (the one you set in ADMIN_PASSWORD)

### Containers won't start?

```bash
# Stop everything
docker-compose down

# Pull latest image and restart
docker pull aunooai/aunoo-community:latest
docker-compose up -d
```

### Port already in use?

Change the APP_PORT in `.env`:
```bash
APP_PORT=9000  # Change to any available port
```

---

## Stopping Aunoo AI

```bash
# Stop services
docker-compose down

# Stop but keep data
docker-compose stop

# Restart
docker-compose restart
```

---

## More Help

- **[Docker Hub Deployment](DOCKER_HUB_DEPLOYMENT.md)** - Deploy from pre-built images without cloning
- **Full Documentation** - See README.md in the repository
- **Support** - Contact support or open an issue on GitHub

---

## Alternative: Deploy from Docker Hub

Don't want to clone the repository or build images? You can deploy from pre-built Docker Hub images:

```bash
# Download deployment files only
curl -O https://raw.githubusercontent.com/orochford/AunooAI/main/docker-compose.yml
curl -O https://raw.githubusercontent.com/orochford/AunooAI/main/.env.hub

# Configure and deploy
cp .env.hub .env
nano .env  # Add your API keys
docker-compose up -d
```

See **[DOCKER_README.md](DOCKER_README.md)** for full details.

---

**That's it!** You now have Aunoo AI running in Docker. 🚀

*Questions? Contact support or visit the repository.*
