#!/bin/bash
# Deploy React UI for Trend Convergence Dashboard
# This script builds the React app and deploys it to the static directory

set -e  # Exit on error

echo "================================"
echo "  Deploying React UI"
echo "================================"
echo ""

# Navigate to UI directory
cd "$(dirname "$0")"
UI_DIR="$(pwd)"
PROJECT_ROOT="$(dirname "$UI_DIR")"
STATIC_DIR="$PROJECT_ROOT/static/trend-convergence"

echo "📁 UI Directory: $UI_DIR"
echo "📁 Project Root: $PROJECT_ROOT"
echo "📁 Static Directory: $STATIC_DIR"
echo ""

# Build the React app
echo "🔨 Building React app..."
npm run build

if [ $? -ne 0 ]; then
    echo "❌ Build failed!"
    exit 1
fi

echo "✅ Build successful!"
echo ""

# Create static directory if it doesn't exist
echo "📂 Ensuring static directory exists..."
mkdir -p "$STATIC_DIR"

# Clear old files
echo "🧹 Clearing old files..."
rm -rf "$STATIC_DIR"/*

# Copy new build files
echo "📦 Copying build files..."
cp -r build/* "$STATIC_DIR/"

# Update title only (paths are already correct from vite config)
echo "🔧 Updating page title..."
sed -i 's|<title>.*</title>|<title>Trend Convergence Analysis - AuNoo AI</title>|' "$STATIC_DIR/index.html"

echo ""
echo "✅ Deployment complete!"
echo ""
echo "📊 Build artifacts:"
ls -lh "$STATIC_DIR"
echo ""
echo "🌐 React UI is now available at: /trend-convergence"
echo ""
echo "================================"
