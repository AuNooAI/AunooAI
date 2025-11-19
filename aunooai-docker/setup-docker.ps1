# AunooAI Docker Setup Script for Windows
# Run with: .\setup-docker.ps1

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "   ___                           ___  ____" -ForegroundColor Blue
Write-Host "  / _ | __ _____  ___  ___      / _ |/  _/" -ForegroundColor Blue
Write-Host " / __ |/ // / _ \/ _ \/ _ \    / __ |_/ /" -ForegroundColor Blue
Write-Host "/_/ |_|\_,_/_//_/\___/\___/   /_/ |_/___/" -ForegroundColor Blue
Write-Host ""
Write-Host "Docker Setup Wizard (Windows)" -ForegroundColor Blue
Write-Host ""

# Check Docker
Write-Host "Checking prerequisites..." -ForegroundColor Yellow

try {
    docker --version | Out-Null
    Write-Host "✓ Docker is installed" -ForegroundColor Green
} catch {
    Write-Host "❌ Docker is not installed" -ForegroundColor Red
    Write-Host "Please install Docker Desktop: https://www.docker.com/products/docker-desktop"
    exit 1
}

try {
    docker-compose --version | Out-Null
    Write-Host "✓ Docker Compose is available" -ForegroundColor Green
} catch {
    Write-Host "❌ Docker Compose is not installed" -ForegroundColor Red
    Write-Host "Please update Docker Desktop"
    exit 1
}

Write-Host ""

# Download files if needed
if (!(Test-Path "docker-compose.yml")) {
    Write-Host "Downloading deployment files..." -ForegroundColor Yellow
    Invoke-WebRequest -Uri "https://raw.githubusercontent.com/orochford/AunooAI/main/docker-compose.yml" -OutFile "docker-compose.yml"
    Invoke-WebRequest -Uri "https://raw.githubusercontent.com/orochford/AunooAI/main/.env.hub" -OutFile ".env.hub"
    Write-Host "✓ Files downloaded" -ForegroundColor Green
}

$ComposeFile = "docker-compose.yml"

# Check if .env exists
$SkipConfig = $false
if (Test-Path ".env") {
    Write-Host "⚠️  Existing .env file found" -ForegroundColor Yellow
    $response = Read-Host "Do you want to reconfigure? (y/N)"
    if ($response -ne "y" -and $response -ne "Y") {
        Write-Host "Using existing configuration..."
        $SkipConfig = $true
    }
}

# Interactive configuration
if (-not $SkipConfig) {
    Write-Host ""
    Write-Host "Configuration Setup" -ForegroundColor Blue
    Write-Host ""

    # Copy template
    if (Test-Path ".env.hub") {
        Copy-Item .env.hub .env
    } else {
        New-Item .env -ItemType File
    }

    # Since we have defaults, just inform the user
    Write-Host "Default configuration will be used:" -ForegroundColor Green
    Write-Host "  - Admin login: admin / admin123"
    Write-Host "  - PostgreSQL password: aunoo_secure_2025"
    Write-Host "  - Port: 8080"
    Write-Host ""
    Write-Host "You can customize these in the .env file if needed." -ForegroundColor Yellow
    Write-Host "API keys will be configured via the web interface after first login." -ForegroundColor Yellow
    Write-Host ""
}

# Pull images
Write-Host ""
Write-Host "Pulling Docker Images" -ForegroundColor Blue
Write-Host ""

docker-compose -f $ComposeFile pull

Write-Host ""
Write-Host "✓ Images ready" -ForegroundColor Green
Write-Host ""

# Start services
Write-Host ""
Write-Host "Starting Services" -ForegroundColor Blue
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
    Write-Host "✓ Services started successfully!" -ForegroundColor Green
} else {
    Write-Host "⚠️  Services may not be fully ready. Check logs with:" -ForegroundColor Red
    Write-Host "   docker-compose -f $ComposeFile logs -f"
}

Write-Host ""
Write-Host "🎉 Setup Complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Your Aunoo AI instance is running!"
Write-Host ""
Write-Host "Access your instance:" -ForegroundColor Green
Write-Host "   http://localhost:8080" -ForegroundColor Blue
Write-Host ""
Write-Host "Login credentials:" -ForegroundColor Green
Write-Host "   Username: admin"
Write-Host "   Password: admin123"
Write-Host ""
Write-Host "⚠️  IMPORTANT:" -ForegroundColor Yellow
Write-Host "   1. Change your admin password after first login!"
Write-Host "   2. Configure API keys via the onboarding wizard"
Write-Host ""
Write-Host "Useful commands:" -ForegroundColor Blue
Write-Host "   View logs:    docker-compose -f $ComposeFile logs -f"
Write-Host "   Stop:         docker-compose -f $ComposeFile down"
Write-Host "   Restart:      docker-compose -f $ComposeFile restart"
Write-Host "   Status:       docker-compose -f $ComposeFile ps"
Write-Host ""
Write-Host "Enjoy using Aunoo AI! 🚀" -ForegroundColor Green
Write-Host ""

# Open browser
$response = Read-Host "Open in browser now? (Y/n)"
if ($response -ne "n" -and $response -ne "N") {
    Start-Process "http://localhost:8080"
}
