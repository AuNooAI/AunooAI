#!/bin/bash
# Create deployment package for GitHub releases
# Run this script before creating a GitHub release

set -e

VERSION=${1:-latest}
RELEASE_DIR="aunooai-docker"

echo "Creating AunooAI Docker deployment package (version: $VERSION)"

# Create clean release directory
rm -rf "$RELEASE_DIR" "$RELEASE_DIR.zip" "$RELEASE_DIR.tar.gz"
mkdir -p "$RELEASE_DIR"

# Copy deployment files
echo "Copying deployment files..."
cp docker-compose.yml "$RELEASE_DIR/docker-compose.hub.yml"
cp .env.hub "$RELEASE_DIR/"
cp setup-docker.sh "$RELEASE_DIR/"
cp setup-docker.ps1 "$RELEASE_DIR/"
cp DOCKER_README.md "$RELEASE_DIR/README.md"
cp DOCKER_QUICKSTART.md "$RELEASE_DIR/"

# PowerShell works fine with Unix (LF) line endings, no conversion needed

# Make scripts executable
chmod +x "$RELEASE_DIR/setup-docker.sh"

# Create README for the package
cat > "$RELEASE_DIR/QUICK_START.txt" << 'EOF'
AunooAI Community Edition - Docker Deployment Package

QUICK START:

Windows Users:
1. Open PowerShell in this folder
2. Run: .\setup-docker.ps1
3. Follow the wizard prompts

Linux/Mac Users:
1. Open terminal in this folder
2. Run: ./setup-docker.sh
3. Follow the wizard prompts

Manual Setup (No Wizard):
1. Run: docker-compose up -d
2. Open browser to: http://localhost:8080
3. Login: admin / admin123
4. Configure API keys in onboarding wizard

For full documentation, see README.md

Default Settings:
- Admin: admin / admin123
- PostgreSQL password: aunoo_secure_2025
- Port: 8080

IMPORTANT: Change admin password after first login!
EOF

# Create version file
echo "$VERSION" > "$RELEASE_DIR/VERSION"

# Create checksums
echo "Generating checksums..."
cd "$RELEASE_DIR"
sha256sum * > SHA256SUMS 2>/dev/null || shasum -a 256 * > SHA256SUMS
cd ..

# Create archives
echo "Creating archives..."

# ZIP for Windows users
zip -r "$RELEASE_DIR.zip" "$RELEASE_DIR"
echo "✓ Created: $RELEASE_DIR.zip"

# TAR.GZ for Linux/Mac users
tar -czf "$RELEASE_DIR.tar.gz" "$RELEASE_DIR"
echo "✓ Created: $RELEASE_DIR.tar.gz"

# Show file sizes
echo ""
echo "Package sizes:"
ls -lh "$RELEASE_DIR.zip" "$RELEASE_DIR.tar.gz"

echo ""
echo "✅ Deployment packages ready!"
echo ""
echo "Upload these files to GitHub release:"
echo "  - $RELEASE_DIR.zip (for Windows)"
echo "  - $RELEASE_DIR.tar.gz (for Linux/Mac)"
echo ""
echo "Users can then download and run:"
echo "  Windows: .\setup-docker.ps1"
echo "  Linux/Mac: ./setup-docker.sh"
