# AunooAI Docker Setup Script for Windows
# Run with: .\setup-docker.ps1

$ErrorActionPreference = "Stop"

# Banner
Write-Host @"

   ___                           ___  ____
  / _ | __ _____  ___  ___      / _ |/  _/
 / __ |/ // / _ \/ _ \/ _ \    / __ |_/ /
/_/ |_|\_,_/_//_/\___/\___/   /_/ |_/___/

Docker Setup Wizard (Windows)

"@

# Check Docker
Write-Host -ForegroundColor Yellow "Checking prerequisites..."

try {
    docker --version | Out-Null
    Write-Host -ForegroundColor Green "OK Docker is installed"
} catch {
    Write-Host -ForegroundColor Red "ERROR Docker is not installed"
    Write-Host "Please install Docker Desktop: https://www.docker.com/products/docker-desktop"
    exit 1
}

try {
    docker-compose --version | Out-Null
    Write-Host -ForegroundColor Green "OK Docker Compose is available"
} catch {
    Write-Host -ForegroundColor Red "ERROR Docker Compose is not installed"
    Write-Host "Please update Docker Desktop"
    exit 1
}

Write-Host ""

# Detect mode
if (Test-Path "docker-compose.yml") {
    $ComposeFile = "docker-compose.yml"
    $EnvTemplate = ".env.template"
    $Mode = "repo"
    Write-Host -ForegroundColor Blue "Detected: Building from source"
} elseif (Test-Path "docker-compose.hub.yml") {
    $ComposeFile = "docker-compose.hub.yml"
    $EnvTemplate = ".env.hub"
    $Mode = "hub"
    Write-Host -ForegroundColor Blue "Detected: Using Docker Hub images"
} else {
    Write-Host -ForegroundColor Yellow "No compose file found. Downloading from Docker Hub..."

    Invoke-WebRequest -Uri "https://raw.githubusercontent.com/orochford/AunooAI/main/docker-compose.hub.yml" -OutFile "docker-compose.hub.yml"
    Invoke-WebRequest -Uri "https://raw.githubusercontent.com/orochford/AunooAI/main/.env.hub" -OutFile ".env.hub"

    $ComposeFile = "docker-compose.hub.yml"
    $EnvTemplate = ".env.hub"
    $Mode = "hub"
    Write-Host -ForegroundColor Green "OK Downloaded deployment files"
}

Write-Host ""

# Check existing .env
$SkipConfig = $false
if (Test-Path ".env") {
    Write-Host -ForegroundColor Yellow "WARNING  Existing .env file found"
    $response = Read-Host "Do you want to reconfigure? (y/N)"
    if ($response -ne "y" -and $response -ne "Y") {
        Write-Host "Using existing configuration..."
        $SkipConfig = $true
    } else {
        $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
        Move-Item .env ".env.backup.$timestamp"
        Write-Host -ForegroundColor Green "Backed up existing .env"
    }
}

# Setup configuration with defaults
if (-not $SkipConfig) {
    Write-Host ""
    Write-Host "Setting up configuration with defaults..."
    Write-Host ""

    # Copy template with pre-populated defaults
    Copy-Item $EnvTemplate .env

    Write-Host -ForegroundColor Green "Configuration ready!"
    Write-Host ""
    Write-Host "Login credentials:"
    Write-Host "  Username: admin"
    Write-Host "  Password: admin123"
    Write-Host ""
    Write-Host -ForegroundColor Yellow "IMPORTANT: Change your password after first login!"
    Write-Host ""
}

# Docker Hub deployment uses default port 8080
$Port = "8080"

# Build or pull images
Write-Host ""
Write-Host -ForegroundColor Blue "-----------------------------------------"
Write-Host -ForegroundColor Blue "  Preparing Images"
Write-Host -ForegroundColor Blue "-----------------------------------------"
Write-Host ""

if ($Mode -eq "repo") {
    Write-Host "Building Docker images (this may take 3-5 minutes)..."
    docker-compose -f $ComposeFile build
} else {
    Write-Host "Pulling Docker images from Docker Hub..."
    docker-compose -f $ComposeFile pull
}

Write-Host -ForegroundColor Green "OK Images ready"
Write-Host ""

# Start services
Write-Host ""
Write-Host -ForegroundColor Blue "-----------------------------------------"
Write-Host -ForegroundColor Blue "  Starting Services"
Write-Host -ForegroundColor Blue "-----------------------------------------"
Write-Host ""

docker-compose -f $ComposeFile up -d

Write-Host ""
Write-Host "Waiting for services to be healthy..."
Start-Sleep -Seconds 5

# Wait for health checks (max 60 seconds)
$maxWait = 60
$elapsed = 0
while ($elapsed -lt $maxWait) {
    $status = docker-compose -f $ComposeFile ps
    if ($status -match "healthy") {
        break
    }
    Write-Host -NoNewline "."
    Start-Sleep -Seconds 2
    $elapsed += 2
}
Write-Host ""

# Check if services are running
$psOutput = docker-compose -f $ComposeFile ps
if ($psOutput -match "Up") {
    Write-Host -ForegroundColor Green "OK Services started successfully!"
} else {
    Write-Host -ForegroundColor Red "WARNING  Services may not be fully ready. Check logs with:"
    Write-Host "   docker-compose -f $ComposeFile logs -f"
}

Write-Host ""
Write-Host -ForegroundColor Blue "-----------------------------------------"
Write-Host -ForegroundColor Green "   Setup Complete!"
Write-Host -ForegroundColor Blue "-----------------------------------------"
Write-Host ""
Write-Host "Your Aunoo AI instance is running!"
Write-Host ""
Write-Host -ForegroundColor Green "Access your instance:"
Write-Host -ForegroundColor Blue "   http://localhost:$Port"
Write-Host ""
Write-Host -ForegroundColor Green "Login credentials:"
Write-Host "   Username: admin"
Write-Host "   Password: (the admin password you set)"
Write-Host ""
Write-Host -ForegroundColor Yellow "WARNING  Remember to change your admin password after first login!"
Write-Host ""
Write-Host -ForegroundColor Blue "Useful commands:"
Write-Host "   View logs:    docker-compose -f $ComposeFile logs -f"
Write-Host "   Stop:         docker-compose -f $ComposeFile down"
Write-Host "   Restart:      docker-compose -f $ComposeFile restart"
Write-Host "   Status:       docker-compose -f $ComposeFile ps"
Write-Host ""
Write-Host -ForegroundColor Green "Enjoy using Aunoo AI! 🚀"
Write-Host ""

# Open browser
$response = Read-Host "Open in browser now? (Y/n)"
if ($response -ne "n" -and $response -ne "N") {
    Start-Process "http://localhost:$Port"
}
