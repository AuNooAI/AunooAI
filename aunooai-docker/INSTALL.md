# AunooAI - Quick Install Guide

Get AunooAI running in 3 simple steps.

## What You Need

- Docker Desktop installed ([Download here](https://www.docker.com/products/docker-desktop))
- 5 minutes of your time

## Installation

### Windows

1. **Download the installer**
   - Get `aunooai-docker.zip` from the latest release
   - Extract the ZIP file

2. **Run the setup**
   ```powershell
   .\setup-docker.ps1
   ```

3. **Open your browser**
   - Go to: http://localhost:10001
   - Login with:
     - Username: `admin`
     - Password: `admin123`
   - Change your password on first login

### Linux / Mac

1. **Download the installer**
   - Get `aunooai-docker.tar.gz` from the latest release
   - Extract: `tar -xzf aunooai-docker.tar.gz`
   - Enter directory: `cd aunooai-docker`

2. **Run the setup**
   ```bash
   chmod +x setup-docker.sh
   ./setup-docker.sh
   ```

3. **Open your browser**
   - Go to: http://localhost:10001
   - Login with:
     - Username: `admin`
     - Password: `admin123`
   - Change your password on first login

## That's It!

Your AunooAI instance is now running. The setup script:
- Downloaded the Docker images
- Started PostgreSQL database
- Started the AunooAI application
- Configured everything with secure defaults

## Next Steps

After logging in:
1. Change the default admin password (Settings > User Management)
2. Configure your API keys via the onboarding wizard
3. Start exploring the features

## Common Commands

View logs:
```bash
# Windows
docker-compose -f docker-compose.hub.yml logs -f

# Linux/Mac
docker-compose -f docker-compose.hub.yml logs -f
```

Stop AunooAI:
```bash
docker-compose -f docker-compose.hub.yml down
```

Restart AunooAI:
```bash
docker-compose -f docker-compose.hub.yml restart
```

## Need Help?

- Full documentation: See `README.md` in the package
- Quick start guide: See `DOCKER_QUICKSTART.md`
- Check service status: `docker-compose -f docker-compose.hub.yml ps`

## Troubleshooting

**Can't access http://localhost:10001?**

Check if services are running:
```bash
docker-compose -f docker-compose.hub.yml ps
```

View logs for errors:
```bash
docker-compose -f docker-compose.hub.yml logs aunooai
```

**Port 10001 already in use?**

Edit `.env` file and change `APP_PORT=10001` to another port (e.g., `APP_PORT=10002`), then restart:
```bash
docker-compose -f docker-compose.hub.yml restart
```
