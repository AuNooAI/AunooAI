#!/bin/bash

# Docker initialization script for AunooAI

# Make script executable
chmod +x "$0"

echo "=== AunooAI Docker Initialization ==="

# Check if docker is installed
if ! command -v docker &> /dev/null; then
    echo "Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if docker-compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Build the Docker image
echo "Building Docker image..."
docker-compose build

# Start the development instance
echo "Starting the development instance..."
docker-compose up -d aunooai-dev

echo ""
echo "=== AunooAI is now running ==="
echo "Access the application at: https://localhost:6005"
echo "Username: admin"
echo "Password: admin"
echo ""
echo "To start production or staging instances:"
echo "- docker-compose --profile prod up -d"
echo "- docker-compose --profile staging up -d"
echo ""
echo "To stop the services:"
echo "- docker-compose down"
echo "" 