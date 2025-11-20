#!/bin/bash
set -e

# AunooAI Docker Build Script
# Builds optimized Docker image with proper versioning

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}AunooAI Community Edition - Docker Build${NC}"
echo -e "${GREEN}================================================${NC}"

# Get version information
GIT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
GIT_COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
BUILD_DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
VERSION="${1:-community-${GIT_COMMIT}}"

echo -e "${YELLOW}Build Information:${NC}"
echo "  Version:     $VERSION"
echo "  Branch:      $GIT_BRANCH"
echo "  Commit:      $GIT_COMMIT"
echo "  Build Date:  $BUILD_DATE"
echo ""

# Check if .env file exists
if [ ! -f .env ]; then
    echo -e "${YELLOW}Warning: .env file not found${NC}"
    echo -e "${YELLOW}Creating from .env.docker.example...${NC}"
    if [ -f .env.docker.example ]; then
        cp .env.docker.example .env
        echo -e "${GREEN}✓ Created .env file${NC}"
        echo -e "${RED}⚠️  Please edit .env and set your API keys before running!${NC}"
    else
        echo -e "${RED}Error: .env.docker.example not found${NC}"
        exit 1
    fi
fi

# Build Docker image with multi-stage optimization
echo -e "${GREEN}Building Docker image...${NC}"
docker build \
    --build-arg APP_VERSION="$VERSION" \
    --build-arg APP_GIT_BRANCH="$GIT_BRANCH" \
    --build-arg APP_BUILD_DATE="$BUILD_DATE" \
    -t aunooai:latest \
    -t aunooai:$VERSION \
    .

if [ $? -eq 0 ]; then
    echo -e "${GREEN}================================================${NC}"
    echo -e "${GREEN}✓ Build successful!${NC}"
    echo -e "${GREEN}================================================${NC}"
    echo ""
    echo "Image tags created:"
    echo "  - aunooai:latest"
    echo "  - aunooai:$VERSION"
    echo ""
    echo "Image size:"
    docker images aunooai:latest --format "  {{.Repository}}:{{.Tag}} - {{.Size}}"
    echo ""
    echo -e "${YELLOW}Next steps:${NC}"
    echo "  1. Review and edit .env file with your API keys"
    echo "  2. Start services: docker-compose up -d"
    echo "  3. View logs: docker-compose logs -f aunooai"
    echo "  4. Access app: http://localhost:8080"
    echo ""
else
    echo -e "${RED}================================================${NC}"
    echo -e "${RED}✗ Build failed!${NC}"
    echo -e "${RED}================================================${NC}"
    exit 1
fi
