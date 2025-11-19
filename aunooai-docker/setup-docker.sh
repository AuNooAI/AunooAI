#!/bin/bash
# AunooAI Docker Setup Script
# Run with: curl -fsSL https://raw.githubusercontent.com/orochford/AunooAI/main/setup-docker.sh | bash

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Banner
echo -e "${BLUE}"
cat << "EOF"
   ___                           ___  ____
  / _ | __ _____  ___  ___      / _ |/  _/
 / __ |/ // / _ \/ _ \/ _ \    / __ |_/ /
/_/ |_|\_,_/_//_/\___/\___/   /_/ |_/___/

EOF
echo -e "Docker Setup Wizard${NC}"
echo ""

# Check prerequisites
echo -e "${YELLOW}Checking prerequisites...${NC}"

if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker is not installed${NC}"
    echo "Please install Docker Desktop: https://www.docker.com/products/docker-desktop"
    exit 1
fi

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null 2>&1; then
    echo -e "${RED}❌ Docker Compose is not installed${NC}"
    echo "Please install Docker Compose or update Docker Desktop"
    exit 1
fi

# Determine docker-compose command
if command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE="docker-compose"
else
    DOCKER_COMPOSE="docker compose"
fi

echo -e "${GREEN}✓ Docker is installed${NC}"
echo -e "${GREEN}✓ Docker Compose is available${NC}"
echo ""

# Download deployment files
echo -e "${BLUE}Downloading deployment files...${NC}"

curl -fsSL -o docker-compose.hub.yml https://raw.githubusercontent.com/orochford/AunooAI/main/docker-compose.hub.yml
curl -fsSL -o .env.hub https://raw.githubusercontent.com/orochford/AunooAI/main/.env.hub

COMPOSE_FILE="docker-compose.hub.yml"
ENV_TEMPLATE=".env.hub"

echo -e "${GREEN}✓ Downloaded deployment files${NC}"
echo ""

# Check if .env exists
if [ -f ".env" ]; then
    echo -e "${YELLOW}⚠️  Existing .env file found${NC}"
    read -p "Do you want to reconfigure? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Using existing configuration..."
        SKIP_CONFIG=true
    else
        mv .env .env.backup.$(date +%Y%m%d_%H%M%S)
        echo -e "${GREEN}Backed up existing .env${NC}"
        SKIP_CONFIG=false
    fi
else
    SKIP_CONFIG=false
fi

# Interactive configuration
if [ "$SKIP_CONFIG" = false ]; then
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}  Configuration Setup${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""

    cp "$ENV_TEMPLATE" .env

    # Database Password
    echo -e "${YELLOW}1. Database Password${NC}"
    echo "   This secures your PostgreSQL database"
    while true; do
        read -sp "   Enter password (min 8 chars): " DB_PASSWORD
        echo
        if [ ${#DB_PASSWORD} -ge 8 ]; then
            break
        else
            echo -e "${RED}   Password must be at least 8 characters${NC}"
        fi
    done

    # Use different sed syntax for macOS vs Linux
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' "s|POSTGRES_PASSWORD=changeme|POSTGRES_PASSWORD=$DB_PASSWORD|g" .env
    else
        sed -i "s|POSTGRES_PASSWORD=changeme|POSTGRES_PASSWORD=$DB_PASSWORD|g" .env
    fi

    echo -e "${GREEN}   ✓ Database password set${NC}"
    echo ""

    # Admin Password
    echo -e "${YELLOW}2. Admin Password${NC}"
    echo "   Login password for the admin user"
    read -sp "   Enter admin password (press Enter for default 'admin'): " ADMIN_PASSWORD
    echo
    if [ -n "$ADMIN_PASSWORD" ]; then
        if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' "s|ADMIN_PASSWORD=admin|ADMIN_PASSWORD=$ADMIN_PASSWORD|g" .env
        else
            sed -i "s|ADMIN_PASSWORD=admin|ADMIN_PASSWORD=$ADMIN_PASSWORD|g" .env
        fi
        echo -e "${GREEN}   ✓ Admin password set${NC}"
    else
        echo -e "${YELLOW}   ℹ Using default password 'admin'${NC}"
    fi
    echo ""

    # OpenAI API Key
    echo -e "${YELLOW}3. OpenAI API Key ${RED}(Required)${NC}"
    echo "   Get your key at: https://platform.openai.com/api-keys"
    while true; do
        read -p "   Enter OpenAI API key: " OPENAI_KEY
        if [[ $OPENAI_KEY =~ ^sk- ]]; then
            if [[ "$OSTYPE" == "darwin"* ]]; then
                sed -i '' "s|OPENAI_API_KEY=|OPENAI_API_KEY=$OPENAI_KEY|g" .env
            else
                sed -i "s|OPENAI_API_KEY=|OPENAI_API_KEY=$OPENAI_KEY|g" .env
            fi
            echo -e "${GREEN}   ✓ OpenAI API key configured${NC}"
            break
        elif [ -z "$OPENAI_KEY" ]; then
            echo -e "${RED}   OpenAI API key is required${NC}"
        else
            echo -e "${RED}   Invalid key format (should start with 'sk-')${NC}"
        fi
    done
    echo ""

    # Anthropic API Key
    echo -e "${YELLOW}4. Anthropic API Key ${BLUE}(Optional but recommended)${NC}"
    echo "   Get your key at: https://console.anthropic.com/"
    read -p "   Enter Anthropic API key (or press Enter to skip): " ANTHROPIC_KEY
    if [ -n "$ANTHROPIC_KEY" ]; then
        if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' "s|ANTHROPIC_API_KEY=|ANTHROPIC_API_KEY=$ANTHROPIC_KEY|g" .env
        else
            sed -i "s|ANTHROPIC_API_KEY=|ANTHROPIC_API_KEY=$ANTHROPIC_KEY|g" .env
        fi
        echo -e "${GREEN}   ✓ Anthropic API key configured${NC}"
    else
        echo -e "${YELLOW}   ℹ Skipped (can add later via web UI)${NC}"
    fi
    echo ""

    # NewsAPI Key
    echo -e "${YELLOW}5. NewsAPI Key ${BLUE}(Optional for news features)${NC}"
    echo "   Get your key at: https://newsapi.org/register"
    read -p "   Enter NewsAPI key (or press Enter to skip): " NEWS_KEY
    if [ -n "$NEWS_KEY" ]; then
        if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' "s|NEWSAPI_KEY=|NEWSAPI_KEY=$NEWS_KEY|g" .env
            sed -i '' "s|PROVIDER_NEWSAPI_KEY=|PROVIDER_NEWSAPI_KEY=$NEWS_KEY|g" .env
        else
            sed -i "s|NEWSAPI_KEY=|NEWSAPI_KEY=$NEWS_KEY|g" .env
            sed -i "s|PROVIDER_NEWSAPI_KEY=|PROVIDER_NEWSAPI_KEY=$NEWS_KEY|g" .env
        fi
        echo -e "${GREEN}   ✓ NewsAPI key configured${NC}"
    else
        echo -e "${YELLOW}   ℹ Skipped (can add later via web UI)${NC}"
    fi
    echo ""

    # Firecrawl API Key
    echo -e "${YELLOW}6. Firecrawl API Key ${BLUE}(Optional for web scraping)${NC}"
    echo "   Get your key at: https://www.firecrawl.dev/"
    read -p "   Enter Firecrawl API key (or press Enter to skip): " FIRECRAWL_KEY
    if [ -n "$FIRECRAWL_KEY" ]; then
        if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' "s|FIRECRAWL_API_KEY=|FIRECRAWL_API_KEY=$FIRECRAWL_KEY|g" .env
            sed -i '' "s|PROVIDER_FIRECRAWL_KEY=|PROVIDER_FIRECRAWL_KEY=$FIRECRAWL_KEY|g" .env
        else
            sed -i "s|FIRECRAWL_API_KEY=|FIRECRAWL_API_KEY=$FIRECRAWL_KEY|g" .env
            sed -i "s|PROVIDER_FIRECRAWL_KEY=|PROVIDER_FIRECRAWL_KEY=$FIRECRAWL_KEY|g" .env
        fi
        echo -e "${GREEN}   ✓ Firecrawl API key configured${NC}"
    else
        echo -e "${YELLOW}   ℹ Skipped (can add later via web UI)${NC}"
    fi
    echo ""

    echo -e "${GREEN}✓ Configuration complete!${NC}"
    echo ""
fi

# Choose deployment profile
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}  Deployment Options${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "1. Development (port 6005) - recommended for testing"
echo "2. Production (port 5008) - for live deployments"
echo "3. Staging (port 5009) - for pre-production testing"
echo ""
read -p "Select deployment type [1]: " DEPLOY_TYPE
DEPLOY_TYPE=${DEPLOY_TYPE:-1}

case $DEPLOY_TYPE in
    1)
        PROFILE=""
        PORT="6005"
        ;;
    2)
        PROFILE="--profile prod"
        PORT="5008"
        ;;
    3)
        PROFILE="--profile staging"
        PORT="5009"
        ;;
    *)
        echo -e "${RED}Invalid selection, using development${NC}"
        PROFILE=""
        PORT="6005"
        ;;
esac
echo ""

# Pull images
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}  Pulling Images${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

$DOCKER_COMPOSE -f "$COMPOSE_FILE" pull

echo -e "${GREEN}✓ Images ready${NC}"
echo ""

# Start services
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}  Starting Services${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

$DOCKER_COMPOSE -f "$COMPOSE_FILE" $PROFILE up -d

echo ""
echo "Waiting for services to be healthy..."
sleep 5

# Wait for health checks
SECONDS=0
MAX_WAIT=60
while [ $SECONDS -lt $MAX_WAIT ]; do
    if $DOCKER_COMPOSE -f "$COMPOSE_FILE" ps | grep -q "healthy"; then
        break
    fi
    echo -n "."
    sleep 2
done
echo ""

# Check status
if $DOCKER_COMPOSE -f "$COMPOSE_FILE" ps | grep -q "Up"; then
    echo -e "${GREEN}✓ Services started successfully!${NC}"
else
    echo -e "${RED}⚠️  Services may not be fully ready. Check logs with:${NC}"
    echo "   $DOCKER_COMPOSE -f $COMPOSE_FILE logs -f"
fi

echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  🎉 Setup Complete!${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "Your Aunoo AI instance is running!"
echo ""
echo -e "${GREEN}Access your instance:${NC}"
echo -e "   ${BLUE}http://localhost:$PORT${NC}"
echo ""
echo -e "${GREEN}Login credentials:${NC}"
echo "   Username: admin"
echo "   Password: (the admin password you set)"
echo ""
echo -e "${YELLOW}⚠️  Remember to change your admin password after first login!${NC}"
echo ""
echo -e "${BLUE}Useful commands:${NC}"
echo "   View logs:    $DOCKER_COMPOSE -f $COMPOSE_FILE logs -f"
echo "   Stop:         $DOCKER_COMPOSE -f $COMPOSE_FILE down"
echo "   Restart:      $DOCKER_COMPOSE -f $COMPOSE_FILE restart"
echo "   Status:       $DOCKER_COMPOSE -f $COMPOSE_FILE ps"
echo ""
echo -e "${GREEN}Enjoy using Aunoo AI! 🚀${NC}"
echo ""
