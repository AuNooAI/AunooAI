#!/bin/bash

# Deploy React UI to FastAPI Static Directory
# This script builds the React app and deploys it to the FastAPI static directory

set -e  # Exit on error

echo "🚀 Starting React UI deployment..."

# Navigate to UI directory
cd "$(dirname "$0")/../ui" || exit 1

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo "📦 Installing npm dependencies..."
    npm install
fi

# Build the React application
echo "🔨 Building React application..."
npm run build

# Check if build was successful
if [ ! -f "build/index.html" ]; then
    echo "❌ Build failed: index.html not found"
    exit 1
fi

# Create static directory if it doesn't exist
STATIC_DIR="../static/trend-convergence"
mkdir -p "$STATIC_DIR"

# Backup existing files if they exist
if [ -d "$STATIC_DIR/assets" ]; then
    echo "💾 Backing up existing files..."
    mv "$STATIC_DIR" "${STATIC_DIR}.backup.$(date +%s)"
    mkdir -p "$STATIC_DIR"
fi

# Copy build files to static directory
echo "📋 Copying build files to static directory..."
cp -r build/* "$STATIC_DIR/"

# Fix asset paths in index.html
echo "🔧 Fixing asset paths..."
sed -i 's|src="/assets/|src="/static/trend-convergence/assets/|g' "$STATIC_DIR/index.html"
sed -i 's|href="/assets/|href="/static/trend-convergence/assets/|g' "$STATIC_DIR/index.html"

# Update title
sed -i 's|<title>.*</title>|<title>Strategic Recommendations - Trend Convergence Analysis</title>|g' "$STATIC_DIR/index.html"

echo "✅ React UI deployed successfully!"
echo "📍 Access at: http://localhost:<port>/trend-convergence"
echo ""
echo "⚠️  Note: This is a static Figma export. To make it dynamic:"
echo "   1. Connect React components to FastAPI endpoints"
echo "   2. Replace hardcoded data with API calls"
echo "   3. Add authentication integration"
