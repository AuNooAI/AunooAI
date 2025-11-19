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
    echo -e "${RED}ERROR Docker is not installed${NC}"
    echo "Please install Docker Desktop: https://www.docker.com/products/docker-desktop"
    exit 1
fi

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null 2>&1; then
    echo -e "${RED}ERROR Docker Compose is not installed${NC}"
    echo "Please install Docker Compose or update Docker Desktop"
    exit 1
fi

# Determine docker-compose command
if command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE="docker-compose"
else
    DOCKER_COMPOSE="docker compose"
fi

echo -e "${GREEN}OK Docker is installed${NC}"
echo -e "${GREEN}OK Docker Compose is available${NC}"
echo ""

# Download deployment files
echo -e "${BLUE}Downloading deployment files...${NC}"

curl -fsSL -o docker-compose.hub.yml https://raw.githubusercontent.com/orochford/AunooAI/main/docker-compose.hub.yml
curl -fsSL -o .env.hub https://raw.githubusercontent.com/orochford/AunooAI/main/.env.hub

COMPOSE_FILE="docker-compose.hub.yml"
ENV_TEMPLATE=".env.hub"

echo -e "${GREEN}OK Downloaded deployment files${NC}"
echo ""

# Check if .env exists
if [ -f ".env" ]; then
    echo -e "${YELLOW}WARNING  Existing .env file found${NC}"
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

# Setup configuration with defaults
if [ "$SKIP_CONFIG" = false ]; then
    echo ""
    echo "Setting up configuration with defaults..."
    echo ""

    cp "$ENV_TEMPLATE" .env

    echo -e "${GREEN}Configuration ready!${NC}"
    echo ""
    echo "Login credentials:"
    echo "  Username: admin"
    echo "  Password: admin123"
    echo ""
    echo -e "${YELLOW}IMPORTANT: Change your password after first login!${NC}"
    echo ""
fi

# Docker Hub deployment uses default port 8080
PORT="8080"

# Pull images
echo -e "${BLUE}-----------------------------------------${NC}"
echo -e "${BLUE}  Pulling Images${NC}"
echo -e "${BLUE}-----------------------------------------${NC}"
echo ""

$DOCKER_COMPOSE -f "$COMPOSE_FILE" pull

echo -e "${GREEN}OK Images ready${NC}"
echo ""

# Start services
echo -e "${BLUE}-----------------------------------------${NC}"
echo -e "${BLUE}  Starting Services${NC}"
echo -e "${BLUE}-----------------------------------------${NC}"
echo ""

$DOCKER_COMPOSE -f "$COMPOSE_FILE" up -d

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
    echo -e "${GREEN}OK Services started successfully!${NC}"
else
    echo -e "${RED}WARNING  Services may not be fully ready. Check logs with:${NC}"
    echo "   $DOCKER_COMPOSE -f $COMPOSE_FILE logs -f"
fi

echo ""
echo -e "${BLUE}-----------------------------------------${NC}"
echo -e "${GREEN}   Setup Complete!${NC}"
echo -e "${BLUE}-----------------------------------------${NC}"
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
echo -e "${YELLOW}WARNING  Remember to change your admin password after first login!${NC}"
echo ""
echo -e "${BLUE}Useful commands:${NC}"
echo "   View logs:    $DOCKER_COMPOSE -f $COMPOSE_FILE logs -f"
echo "   Stop:         $DOCKER_COMPOSE -f $COMPOSE_FILE down"
echo "   Restart:      $DOCKER_COMPOSE -f $COMPOSE_FILE restart"
echo "   Status:       $DOCKER_COMPOSE -f $COMPOSE_FILE ps"
echo ""
echo -e "${GREEN}Enjoy using Aunoo AI! 🚀${NC}"
echo ""
