#!/bin/bash
# Deploy React UI for Trend Convergence Dashboard and Gather
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
# NotificationBell CSS contains gather.css styles - find from gather build
NOTIFICATIONBELL_CSS=$(ls "$STATIC_DIR/assets/" | grep -oP 'NotificationBell-[^.]+\.css' | head -1)

echo "  📄 Index CSS: $INDEX_CSS"
echo "  📄 Main CSS: $MAIN_CSS"
echo "  📄 Main JS: $MAIN_JS"
echo "  📄 Index JS: $INDEX_JS"
echo "  📄 NotificationBell CSS: $NOTIFICATIONBELL_CSS"

# Update the Jinja2 template with new asset hashes
echo "🔧 Updating Jinja2 template with new asset hashes..."

# Backup the template
cp "$TEMPLATE_FILE" "$TEMPLATE_FILE.backup"

# Update CSS files (lines 15-16)
sed -i "s|/static/trend-convergence/assets/index-[^.]*\.css|/static/trend-convergence/assets/$INDEX_CSS|" "$TEMPLATE_FILE"
sed -i "s|/static/trend-convergence/assets/main-[^.]*\.css|/static/trend-convergence/assets/$MAIN_CSS|" "$TEMPLATE_FILE"
# Update NotificationBell CSS (contains gather.css)
if [ -n "$NOTIFICATIONBELL_CSS" ]; then
    sed -i "s|/static/trend-convergence/assets/NotificationBell-[^.]*\.css|/static/trend-convergence/assets/$NOTIFICATIONBELL_CSS|" "$TEMPLATE_FILE"
fi

# Update JS files (lines 28-29)
sed -i "s|/static/trend-convergence/assets/main-[^.]*\.js|/static/trend-convergence/assets/$MAIN_JS|" "$TEMPLATE_FILE"
sed -i "s|/static/trend-convergence/assets/index-[^.]*\.js|/static/trend-convergence/assets/$INDEX_JS|" "$TEMPLATE_FILE"

echo "✅ Template updated successfully!"
echo ""

# ================================
# GATHER PAGE DEPLOYMENT
# ================================
echo "================================"
echo "  Deploying Gather Page"
echo "================================"
echo ""

GATHER_TEMPLATE="$PROJECT_ROOT/templates/gather_react.html"

# Extract the hash from gather assets
if [ -f "$STATIC_DIR/index-gather.html" ]; then
    GATHER_CSS=$(grep -oP 'gather-[^.]+\.css' "$STATIC_DIR/index-gather.html" | head -1)
    GATHER_JS=$(grep -oP 'gather-[^.]+\.js' "$STATIC_DIR/index-gather.html" | head -1)

    echo "  📄 Gather CSS: $GATHER_CSS"
    echo "  📄 Gather JS: $GATHER_JS"

    if [ -f "$GATHER_TEMPLATE" ]; then
        # Backup the template
        cp "$GATHER_TEMPLATE" "$GATHER_TEMPLATE.backup"

        # Update CSS file
        if [ -n "$GATHER_CSS" ]; then
            sed -i "s|/static/trend-convergence/assets/gather-[^.]*\.css|/static/trend-convergence/assets/$GATHER_CSS|" "$GATHER_TEMPLATE"
        fi

        # Update JS file
        if [ -n "$GATHER_JS" ]; then
            sed -i "s|/static/trend-convergence/assets/gather-[^.]*\.js|/static/trend-convergence/assets/$GATHER_JS|" "$GATHER_TEMPLATE"
        fi

        # Also update shared CSS (index.css) if gather uses it
        if [ -n "$INDEX_CSS" ]; then
            sed -i "s|/static/trend-convergence/assets/index-[^.]*\.css|/static/trend-convergence/assets/$INDEX_CSS|" "$GATHER_TEMPLATE"
        fi

        # Also update NotificationBell CSS (contains gather.css)
        if [ -n "$NOTIFICATIONBELL_CSS" ]; then
            sed -i "s|/static/trend-convergence/assets/NotificationBell-[^.]*\.css|/static/trend-convergence/assets/$NOTIFICATIONBELL_CSS|" "$GATHER_TEMPLATE"
        fi

        # Also update shared JS (index.js) for modulepreload
        if [ -n "$INDEX_JS" ]; then
            sed -i "s|/static/trend-convergence/assets/index-[^.]*\.js|/static/trend-convergence/assets/$INDEX_JS|" "$GATHER_TEMPLATE"
        fi

        echo "✅ Gather template updated successfully!"
    else
        echo "⚠️  Gather template not found: $GATHER_TEMPLATE"
    fi
else
    echo "⚠️  index-gather.html not found in build output"
fi

# ================================
# EXPLORE/NEWSFEED PAGE DEPLOYMENT
# ================================
echo "================================"
echo "  Deploying Explore Page"
echo "================================"
echo ""

EXPLORE_TEMPLATE="$PROJECT_ROOT/templates/explore_react.html"

# Extract the hash from newsfeed assets
if [ -f "$STATIC_DIR/index-newsfeed.html" ]; then
    NEWSFEED_JS=$(grep -oP 'newsfeed-[^.]+\.js' "$STATIC_DIR/index-newsfeed.html" | head -1)

    echo "  📄 Newsfeed JS: $NEWSFEED_JS"

    if [ -f "$EXPLORE_TEMPLATE" ]; then
        # Backup the template
        cp "$EXPLORE_TEMPLATE" "$EXPLORE_TEMPLATE.backup"

        # Update JS file
        if [ -n "$NEWSFEED_JS" ]; then
            sed -i "s|/static/trend-convergence/assets/newsfeed-[^.]*\.js|/static/trend-convergence/assets/$NEWSFEED_JS|" "$EXPLORE_TEMPLATE"
        fi

        # Also update shared CSS (index.css)
        if [ -n "$INDEX_CSS" ]; then
            sed -i "s|/static/trend-convergence/assets/index-[^.]*\.css|/static/trend-convergence/assets/$INDEX_CSS|" "$EXPLORE_TEMPLATE"
        fi

        # Also update NotificationBell CSS (contains gather.css)
        if [ -n "$NOTIFICATIONBELL_CSS" ]; then
            sed -i "s|/static/trend-convergence/assets/NotificationBell-[^.]*\.css|/static/trend-convergence/assets/$NOTIFICATIONBELL_CSS|" "$EXPLORE_TEMPLATE"
        fi

        # Also update shared JS (index.js) for modulepreload
        if [ -n "$INDEX_JS" ]; then
            sed -i "s|/static/trend-convergence/assets/index-[^.]*\.js|/static/trend-convergence/assets/$INDEX_JS|" "$EXPLORE_TEMPLATE"
        fi

        echo "✅ Explore template updated successfully!"
    else
        echo "⚠️  Explore template not found: $EXPLORE_TEMPLATE"
    fi
else
    echo "⚠️  index-newsfeed.html not found in build output"
fi

echo ""
echo "✅ Deployment complete!"
echo ""
echo "📊 Build artifacts:"
ls -lh "$STATIC_DIR/assets" | head -20
echo ""
echo "🌐 React UI is now available at: /trend-convergence"
echo "🌐 Gather is now available at: /gather"
echo "🌐 Explore is now available at: /explore"
echo "📝 Templates updated:"
echo "   - $TEMPLATE_FILE"
echo "   - $GATHER_TEMPLATE"
echo "   - $EXPLORE_TEMPLATE"
echo ""
echo "================================"
