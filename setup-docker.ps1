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

# Interactive configuration
if (-not $SkipConfig) {
    Write-Host ""
    Write-Host -ForegroundColor Blue "-----------------------------------------"
    Write-Host -ForegroundColor Blue "  Configuration Setup"
    Write-Host -ForegroundColor Blue "-----------------------------------------"
    Write-Host ""

    # Copy template
    Copy-Item $EnvTemplate .env

    # Database Password
    Write-Host -ForegroundColor Yellow "1. Database Password"
    Write-Host "   This secures your PostgreSQL database"
    do {
        $DbPassword = Read-Host "   Enter password (min 8 chars)" -AsSecureString
        $DbPasswordPlain = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($DbPassword))
        if ($DbPasswordPlain.Length -lt 8) {
            Write-Host -ForegroundColor Red "   Password must be at least 8 characters"
        }
    } while ($DbPasswordPlain.Length -lt 8)

    (Get-Content .env) -replace 'POSTGRES_PASSWORD=changeme', "POSTGRES_PASSWORD=$DbPasswordPlain" | Set-Content .env
    Write-Host -ForegroundColor Green "   OK Database password set"
    Write-Host ""

    # Admin Password
    Write-Host -ForegroundColor Yellow "2. Admin Password"
    Write-Host "   Login password for the admin user"
    $AdminPassword = Read-Host "   Enter admin password (press Enter for default 'admin')"
    if ($AdminPassword) {
        (Get-Content .env) -replace 'ADMIN_PASSWORD=admin', "ADMIN_PASSWORD=$AdminPassword" | Set-Content .env
        Write-Host -ForegroundColor Green "   OK Admin password set"
    } else {
        Write-Host -ForegroundColor Yellow "   INFO Using default password 'admin'"
    }
    Write-Host ""

    # OpenAI API Key
    Write-Host -ForegroundColor Yellow "3. OpenAI API Key " -NoNewline
    Write-Host -ForegroundColor Red "(Required)"
    Write-Host "   Get your key at: https://platform.openai.com/api-keys"
    do {
        $OpenAIKey = Read-Host "   Enter OpenAI API key"
        if ($OpenAIKey -notmatch '^sk-') {
            if ([string]::IsNullOrEmpty($OpenAIKey)) {
                Write-Host -ForegroundColor Red "   OpenAI API key is required"
            } else {
                Write-Host -ForegroundColor Red "   Invalid key format (should start with 'sk-')"
            }
        }
    } while ($OpenAIKey -notmatch '^sk-')

    (Get-Content .env) -replace 'OPENAI_API_KEY=', "OPENAI_API_KEY=$OpenAIKey" | Set-Content .env
    Write-Host -ForegroundColor Green "   OK OpenAI API key configured"
    Write-Host ""

    # Anthropic API Key (Optional)
    Write-Host -ForegroundColor Yellow "4. Anthropic API Key " -NoNewline
    Write-Host -ForegroundColor Blue "(Optional but recommended)"
    Write-Host "   Get your key at: https://console.anthropic.com/"
    $AnthropicKey = Read-Host "   Enter Anthropic API key (or press Enter to skip)"
    if ($AnthropicKey) {
        (Get-Content .env) -replace 'ANTHROPIC_API_KEY=', "ANTHROPIC_API_KEY=$AnthropicKey" | Set-Content .env
        Write-Host -ForegroundColor Green "   OK Anthropic API key configured"
    } else {
        Write-Host -ForegroundColor Yellow "   INFO Skipped (can add later via web UI)"
    }
    Write-Host ""

    # NewsAPI Key (Optional)
    Write-Host -ForegroundColor Yellow "5. NewsAPI Key " -NoNewline
    Write-Host -ForegroundColor Blue "(Optional for news features)"
    Write-Host "   Get your key at: https://newsapi.org/register"
    $NewsKey = Read-Host "   Enter NewsAPI key (or press Enter to skip)"
    if ($NewsKey) {
        (Get-Content .env) -replace 'NEWSAPI_KEY=', "NEWSAPI_KEY=$NewsKey" | Set-Content .env
        (Get-Content .env) -replace 'PROVIDER_NEWSAPI_KEY=', "PROVIDER_NEWSAPI_KEY=$NewsKey" | Set-Content .env
        Write-Host -ForegroundColor Green "   OK NewsAPI key configured"
    } else {
        Write-Host -ForegroundColor Yellow "   INFO Skipped (can add later via web UI)"
    }
    Write-Host ""

    # Firecrawl API Key (Optional)
    Write-Host -ForegroundColor Yellow "6. Firecrawl API Key " -NoNewline
    Write-Host -ForegroundColor Blue "(Optional for web scraping)"
    Write-Host "   Get your key at: https://www.firecrawl.dev/"
    $FirecrawlKey = Read-Host "   Enter Firecrawl API key (or press Enter to skip)"
    if ($FirecrawlKey) {
        (Get-Content .env) -replace 'FIRECRAWL_API_KEY=', "FIRECRAWL_API_KEY=$FirecrawlKey" | Set-Content .env
        (Get-Content .env) -replace 'PROVIDER_FIRECRAWL_KEY=', "PROVIDER_FIRECRAWL_KEY=$FirecrawlKey" | Set-Content .env
        Write-Host -ForegroundColor Green "   OK Firecrawl API key configured"
    } else {
        Write-Host -ForegroundColor Yellow "   INFO Skipped (can add later via web UI)"
    }
    Write-Host ""

    Write-Host -ForegroundColor Green "OK Configuration complete!"
    Write-Host ""
}

# Choose deployment profile
Write-Host ""
Write-Host -ForegroundColor Blue "-----------------------------------------"
Write-Host -ForegroundColor Blue "  Deployment Options"
Write-Host -ForegroundColor Blue "-----------------------------------------"
Write-Host ""
Write-Host "1. Development (port 6005) - recommended for testing"
Write-Host "2. Production (port 5008) - for live deployments"
Write-Host "3. Staging (port 5009) - for pre-production testing"
Write-Host ""
$DeployType = Read-Host "Select deployment type [1]"
if ([string]::IsNullOrEmpty($DeployType)) { $DeployType = "1" }

switch ($DeployType) {
    "1" {
        $Profile = ""
        $Port = "6005"
        $EnvType = "development"
    }
    "2" {
        $Profile = "--profile prod"
        $Port = "5008"
        $EnvType = "production"
    }
    "3" {
        $Profile = "--profile staging"
        $Port = "5009"
        $EnvType = "staging"
    }
    default {
        Write-Host -ForegroundColor Red "Invalid selection, using development"
        $Profile = ""
        $Port = "6005"
        $EnvType = "development"
    }
}
Write-Host ""

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

if ($Profile) {
    docker-compose -f $ComposeFile $Profile.Split() up -d
} else {
    docker-compose -f $ComposeFile up -d
}

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
