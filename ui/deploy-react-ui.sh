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

# Type-check before building. `vite build` uses esbuild, which strips types
# without checking them, so a wrong property name ships silently. This fails
# only on errors that are not in ui/tsconfig.baseline.txt. Set
# SKIP_TYPECHECK=1 to deploy anyway.
if [ "$SKIP_TYPECHECK" = "1" ]; then
    echo "⏭️  Type check skipped (SKIP_TYPECHECK=1)"
else
    echo "🔎 Type checking..."
    if ! npm run --silent typecheck; then
        echo "❌ Type check failed — new errors above. Fix them, or re-run with SKIP_TYPECHECK=1."
        exit 1
    fi
fi
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
# Switch CSS contains NotificationBell/gather.css styles - find from build
NOTIFICATIONBELL_CSS=$(ls "$STATIC_DIR/assets/" | grep -oP '(switch|label)-[^.]+\.css' | head -1)
# PAM CSS files
PAM_CSS=$(ls "$STATIC_DIR/assets/" | grep -oP 'pam-[^.]+\.css' | head -1)
USEPAM_CSS=$(ls "$STATIC_DIR/assets/" | grep -oP 'usePAM-[^.]+\.css' | head -1)

echo "  📄 Index CSS: $INDEX_CSS"
echo "  📄 Main CSS: $MAIN_CSS"
echo "  📄 Main JS: $MAIN_JS"
echo "  📄 Index JS: $INDEX_JS"
echo "  📄 NotificationBell CSS: $NOTIFICATIONBELL_CSS"
echo "  📄 PAM CSS: $PAM_CSS"
echo "  📄 usePAM CSS: $USEPAM_CSS"

# Update the Jinja2 template with new asset hashes
echo "🔧 Updating Jinja2 template with new asset hashes..."

# Backup the template
cp "$TEMPLATE_FILE" "$TEMPLATE_FILE.backup"

# Update CSS files (lines 15-16)
sed -i "s|/static/trend-convergence/assets/index-[^.]*\.css|/static/trend-convergence/assets/$INDEX_CSS|" "$TEMPLATE_FILE"
sed -i "s|/static/trend-convergence/assets/main-[^.]*\.css|/static/trend-convergence/assets/$MAIN_CSS|" "$TEMPLATE_FILE"
# Update NotificationBell/Switch CSS (contains gather.css)
if [ -n "$NOTIFICATIONBELL_CSS" ]; then
    sed -i "s|/static/trend-convergence/assets/NotificationBell-[^.]*\.css|/static/trend-convergence/assets/$NOTIFICATIONBELL_CSS|" "$TEMPLATE_FILE"
    sed -i "s|/static/trend-convergence/assets/switch-[^.]*\.css|/static/trend-convergence/assets/$NOTIFICATIONBELL_CSS|" "$TEMPLATE_FILE"
    sed -i "s|/static/trend-convergence/assets/label-[^.]*\.css|/static/trend-convergence/assets/$NOTIFICATIONBELL_CSS|" "$TEMPLATE_FILE"
fi

# Update PAM CSS files (handle both old PAMDashboard-* and new pam-* naming)
if [ -n "$PAM_CSS" ]; then
    sed -i "s|/static/trend-convergence/assets/pam-[^.]*\.css|/static/trend-convergence/assets/$PAM_CSS|" "$TEMPLATE_FILE"
    sed -i "s|/static/trend-convergence/assets/PAMDashboard-[^.]*\.css|/static/trend-convergence/assets/$PAM_CSS|" "$TEMPLATE_FILE"
fi
if [ -n "$USEPAM_CSS" ]; then
    sed -i "s|/static/trend-convergence/assets/usePAM-[^.]*\.css|/static/trend-convergence/assets/$USEPAM_CSS|" "$TEMPLATE_FILE"
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

        # Also update NotificationBell/Switch CSS (contains gather.css)
        if [ -n "$NOTIFICATIONBELL_CSS" ]; then
            sed -i "s|/static/trend-convergence/assets/NotificationBell-[^.]*\.css|/static/trend-convergence/assets/$NOTIFICATIONBELL_CSS|" "$GATHER_TEMPLATE"
            sed -i "s|/static/trend-convergence/assets/switch-[^.]*\.css|/static/trend-convergence/assets/$NOTIFICATIONBELL_CSS|" "$GATHER_TEMPLATE"
            sed -i "s|/static/trend-convergence/assets/label-[^.]*\.css|/static/trend-convergence/assets/$NOTIFICATIONBELL_CSS|" "$GATHER_TEMPLATE"
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

        # Also update NotificationBell/Switch CSS
        if [ -n "$NOTIFICATIONBELL_CSS" ]; then
            sed -i "s|/static/trend-convergence/assets/NotificationBell-[^.]*\.css|/static/trend-convergence/assets/$NOTIFICATIONBELL_CSS|" "$EXPLORE_TEMPLATE"
            sed -i "s|/static/trend-convergence/assets/switch-[^.]*\.css|/static/trend-convergence/assets/$NOTIFICATIONBELL_CSS|" "$EXPLORE_TEMPLATE"
            sed -i "s|/static/trend-convergence/assets/label-[^.]*\.css|/static/trend-convergence/assets/$NOTIFICATIONBELL_CSS|" "$EXPLORE_TEMPLATE"
        fi

        # Update gather layout CSS (explore uses same layout as gather)
        if [ -n "$GATHER_CSS" ]; then
            sed -i "s|/static/trend-convergence/assets/gather-[^.]*\.css|/static/trend-convergence/assets/$GATHER_CSS|" "$EXPLORE_TEMPLATE"
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

# ================================
# PAM PAGE DEPLOYMENT
# ================================
echo "================================"
echo "  Deploying PAM Page"
echo "================================"
echo ""

PAM_TEMPLATE="$PROJECT_ROOT/templates/pam_react.html"

# Extract the hash from pam assets
if [ -f "$STATIC_DIR/index-pam.html" ]; then
    PAM_JS=$(grep -oP 'pam-[^.]+\.js' "$STATIC_DIR/index-pam.html" | head -1)

    echo "  📄 PAM JS: $PAM_JS"

    if [ -f "$PAM_TEMPLATE" ]; then
        # Backup the template
        cp "$PAM_TEMPLATE" "$PAM_TEMPLATE.backup"

        # Update JS file
        if [ -n "$PAM_JS" ]; then
            sed -i "s|/static/trend-convergence/assets/pam-[^.]*\.js|/static/trend-convergence/assets/$PAM_JS|" "$PAM_TEMPLATE"
            # Also replace PLACEHOLDER if this is first deployment
            sed -i "s|/static/trend-convergence/assets/pam-PLACEHOLDER\.js|/static/trend-convergence/assets/$PAM_JS|" "$PAM_TEMPLATE"
        fi

        # Also update shared CSS (index.css)
        if [ -n "$INDEX_CSS" ]; then
            sed -i "s|/static/trend-convergence/assets/index-[^.]*\.css|/static/trend-convergence/assets/$INDEX_CSS|" "$PAM_TEMPLATE"
        fi

        # Also update NotificationBell CSS
        if [ -n "$NOTIFICATIONBELL_CSS" ]; then
            sed -i "s|/static/trend-convergence/assets/NotificationBell-[^.]*\.css|/static/trend-convergence/assets/$NOTIFICATIONBELL_CSS|" "$PAM_TEMPLATE"
        fi

        # Also update PAM CSS files
        if [ -n "$PAM_CSS" ]; then
            sed -i "s|/static/trend-convergence/assets/pam-[^.]*\.css|/static/trend-convergence/assets/$PAM_CSS|" "$PAM_TEMPLATE"
        fi
        if [ -n "$USEPAM_CSS" ]; then
            sed -i "s|/static/trend-convergence/assets/usePAM-[^.]*\.css|/static/trend-convergence/assets/$USEPAM_CSS|" "$PAM_TEMPLATE"
        fi

        # Also update shared JS (index.js) for modulepreload
        if [ -n "$INDEX_JS" ]; then
            sed -i "s|/static/trend-convergence/assets/index-[^.]*\.js|/static/trend-convergence/assets/$INDEX_JS|" "$PAM_TEMPLATE"
        fi

        echo "✅ PAM template updated successfully!"
    else
        echo "⚠️  PAM template not found: $PAM_TEMPLATE"
    fi
else
    echo "⚠️  index-pam.html not found in build output"
fi

# ================================
# OPERATIONS HQ PAGE DEPLOYMENT
# ================================
echo "================================"
echo "  Deploying Operations HQ Page"
echo "================================"
echo ""

OPERATIONS_TEMPLATE="$PROJECT_ROOT/templates/operations_react.html"

# Extract the hash from operations assets
if [ -f "$STATIC_DIR/index-operations.html" ]; then
    OPERATIONS_JS=$(grep -oP 'operations-[^.]+\.js' "$STATIC_DIR/index-operations.html" | head -1)
    # CSS for switch/notification bell component (Vite may name it switch- or NotificationBell-)
    COMPONENT_CSS=$(grep -oP '(switch|NotificationBell|label)-[^.]+\.css' "$STATIC_DIR/index-operations.html" | head -1)

    echo "  📄 Operations JS: $OPERATIONS_JS"
    echo "  📄 Component CSS: $COMPONENT_CSS"

    if [ -f "$OPERATIONS_TEMPLATE" ]; then
        # Backup the template
        cp "$OPERATIONS_TEMPLATE" "$OPERATIONS_TEMPLATE.backup"

        # Update JS file
        if [ -n "$OPERATIONS_JS" ]; then
            sed -i "s|/static/trend-convergence/assets/operations-[^.]*\.js|/static/trend-convergence/assets/$OPERATIONS_JS|" "$OPERATIONS_TEMPLATE"
        fi

        # Also update shared CSS (index.css)
        if [ -n "$INDEX_CSS" ]; then
            sed -i "s|/static/trend-convergence/assets/index-[^.]*\.css|/static/trend-convergence/assets/$INDEX_CSS|" "$OPERATIONS_TEMPLATE"
        fi

        # Update component CSS (switch or NotificationBell)
        if [ -n "$COMPONENT_CSS" ]; then
            # Check if any component CSS line exists
            if grep -qE "(switch|NotificationBell|label)-" "$OPERATIONS_TEMPLATE"; then
                sed -i "s|/static/trend-convergence/assets/\(switch\|NotificationBell\|label\)-[^.]*\.css|/static/trend-convergence/assets/$COMPONENT_CSS|" "$OPERATIONS_TEMPLATE"
            else
                # Add after index CSS line
                sed -i "/index-.*\.css/a\\    <link rel=\"stylesheet\" crossorigin href=\"/static/trend-convergence/assets/$COMPONENT_CSS\">" "$OPERATIONS_TEMPLATE"
            fi
        fi

        # Also update shared JS (index.js) for modulepreload
        if [ -n "$INDEX_JS" ]; then
            sed -i "s|/static/trend-convergence/assets/index-[^.]*\.js|/static/trend-convergence/assets/$INDEX_JS|" "$OPERATIONS_TEMPLATE"
        fi

        echo "✅ Operations HQ template updated successfully!"
    else
        echo "⚠️  Operations template not found: $OPERATIONS_TEMPLATE"
    fi
else
    echo "⚠️  index-operations.html not found in build output"
fi

# ================================
# SUBMIT ARTICLES PAGE DEPLOYMENT
# ================================
echo "================================"
echo "  Deploying Submit Articles Page"
echo "================================"
echo ""

SUBMIT_ARTICLES_TEMPLATE="$PROJECT_ROOT/templates/submit_articles_react.html"

# Extract the hash from submit-articles assets
if [ -f "$STATIC_DIR/index-submit-articles.html" ]; then
    SUBMIT_ARTICLES_JS=$(grep -oP 'submitArticles-[^.]+\.js' "$STATIC_DIR/index-submit-articles.html" | head -1)

    echo "  📄 Submit Articles JS: $SUBMIT_ARTICLES_JS"

    if [ -f "$SUBMIT_ARTICLES_TEMPLATE" ]; then
        # Backup the template
        cp "$SUBMIT_ARTICLES_TEMPLATE" "$SUBMIT_ARTICLES_TEMPLATE.backup"

        # Update JS file
        if [ -n "$SUBMIT_ARTICLES_JS" ]; then
            sed -i "s|/static/trend-convergence/assets/submitArticles-[^.]*\.js|/static/trend-convergence/assets/$SUBMIT_ARTICLES_JS|" "$SUBMIT_ARTICLES_TEMPLATE"
            # Also replace PLACEHOLDER if this is first deployment
            sed -i "s|/static/trend-convergence/assets/submitArticles-PLACEHOLDER\.js|/static/trend-convergence/assets/$SUBMIT_ARTICLES_JS|" "$SUBMIT_ARTICLES_TEMPLATE"
        fi

        # Also update shared CSS (index.css)
        if [ -n "$INDEX_CSS" ]; then
            sed -i "s|/static/trend-convergence/assets/index-[^.]*\.css|/static/trend-convergence/assets/$INDEX_CSS|" "$SUBMIT_ARTICLES_TEMPLATE"
        fi

        # Also update NotificationBell CSS
        if [ -n "$NOTIFICATIONBELL_CSS" ]; then
            sed -i "s|/static/trend-convergence/assets/NotificationBell-[^.]*\.css|/static/trend-convergence/assets/$NOTIFICATIONBELL_CSS|" "$SUBMIT_ARTICLES_TEMPLATE"
        fi

        # Update gather CSS (submit articles uses similar layout)
        if [ -n "$GATHER_CSS" ]; then
            sed -i "s|/static/trend-convergence/assets/gather-[^.]*\.css|/static/trend-convergence/assets/$GATHER_CSS|" "$SUBMIT_ARTICLES_TEMPLATE"
        fi

        # Also update shared JS (index.js) for modulepreload
        if [ -n "$INDEX_JS" ]; then
            sed -i "s|/static/trend-convergence/assets/index-[^.]*\.js|/static/trend-convergence/assets/$INDEX_JS|" "$SUBMIT_ARTICLES_TEMPLATE"
        fi

        echo "✅ Submit Articles template updated successfully!"
    else
        echo "⚠️  Submit Articles template not found: $SUBMIT_ARTICLES_TEMPLATE"
    fi
else
    echo "⚠️  index-submit-articles.html not found in build output"
fi

echo ""
echo "✅ Deployment complete!"
echo ""
echo "📊 Build artifacts:"
ls -lh "$STATIC_DIR/assets" | head -20
echo ""
echo "🌐 Operations HQ is now available at: /"
echo "🌐 React UI is now available at: /trend-convergence"
echo "🌐 Gather is now available at: /gather"
echo "🌐 Explore is now available at: /explore"
echo "🌐 PAM is now available at: /pam"
echo "🌐 Submit Articles is now available at: /submit-articles"
echo "📝 Templates updated:"
echo "   - $OPERATIONS_TEMPLATE"
echo "   - $TEMPLATE_FILE"
echo "   - $GATHER_TEMPLATE"
echo "   - $EXPLORE_TEMPLATE"
echo "   - $PAM_TEMPLATE"
echo "   - $SUBMIT_ARTICLES_TEMPLATE"
echo ""
echo "================================"
