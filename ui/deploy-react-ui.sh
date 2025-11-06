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

# Extract asset hashes from built index.html
echo "🔍 Extracting asset hashes from built files..."
TEMPLATE_FILE="$PROJECT_ROOT/templates/trend_convergence_react.html"

# Extract the hash from each asset file
INDEX_CSS=$(grep -oP 'index-[^.]+\.css' "$STATIC_DIR/index.html" | head -1)
MAIN_CSS=$(grep -oP 'main-[^.]+\.css' "$STATIC_DIR/index.html" | head -1)
MAIN_JS=$(grep -oP 'main-[^.]+\.js' "$STATIC_DIR/index.html" | head -1)
INDEX_JS=$(grep -oP 'index-[^.]+\.js' "$STATIC_DIR/index.html" | head -1)

echo "  📄 Index CSS: $INDEX_CSS"
echo "  📄 Main CSS: $MAIN_CSS"
echo "  📄 Main JS: $MAIN_JS"
echo "  📄 Index JS: $INDEX_JS"

# Update the Jinja2 template with new asset hashes
echo "🔧 Updating Jinja2 template with new asset hashes..."

# Backup the template
cp "$TEMPLATE_FILE" "$TEMPLATE_FILE.backup"

# Update CSS files (lines 15-16)
sed -i "s|/static/trend-convergence/assets/index-[^.]*\.css|/static/trend-convergence/assets/$INDEX_CSS|" "$TEMPLATE_FILE"
sed -i "s|/static/trend-convergence/assets/main-[^.]*\.css|/static/trend-convergence/assets/$MAIN_CSS|" "$TEMPLATE_FILE"

# Update JS files (lines 28-29)
sed -i "s|/static/trend-convergence/assets/main-[^.]*\.js|/static/trend-convergence/assets/$MAIN_JS|" "$TEMPLATE_FILE"
sed -i "s|/static/trend-convergence/assets/index-[^.]*\.js|/static/trend-convergence/assets/$INDEX_JS|" "$TEMPLATE_FILE"

echo "✅ Template updated successfully!"
echo ""

echo ""
echo "✅ Deployment complete!"
echo ""
echo "📊 Build artifacts:"
ls -lh "$STATIC_DIR/assets" | head -20
echo ""
echo "🌐 React UI is now available at: /trend-convergence"
echo "📝 Template updated: $TEMPLATE_FILE"
echo ""
echo "================================"
