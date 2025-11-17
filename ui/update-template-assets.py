#!/usr/bin/env python3
"""
Script to update trend_convergence_react.html template with current build asset filenames.
Run this after 'npm run build' to sync the template with the latest build.
"""

import re
import os
import shutil
from pathlib import Path

def extract_asset_filename(content: str, pattern: str) -> str:
    """Extract filename from HTML using regex pattern."""
    match = re.search(pattern, content)
    if not match:
        raise ValueError(f"Could not find asset matching pattern: {pattern}")
    return match.group(1)

def main():
    # Paths
    script_dir = Path(__file__).parent
    build_index = script_dir / "build" / "index.html"
    build_assets = script_dir / "build" / "assets"
    static_assets = script_dir.parent / "static" / "trend-convergence" / "assets"
    template_file = script_dir.parent / "templates" / "trend_convergence_react.html"

    if not build_index.exists():
        print(f"❌ Build file not found: {build_index}")
        print("   Run 'npm run build' first!")
        return 1

    if not template_file.exists():
        print(f"❌ Template file not found: {template_file}")
        return 1

    # Copy build assets to static directory (required for FastAPI to serve them)
    print(f"\n📦 Copying build assets to static directory...")
    static_assets.mkdir(parents=True, exist_ok=True)

    copied_count = 0
    for asset_file in build_assets.glob("*"):
        if asset_file.is_file():
            shutil.copy2(asset_file, static_assets / asset_file.name)
            copied_count += 1

    print(f"✅ Copied {copied_count} asset files to {static_assets}")

    # Read built index.html
    print(f"📖 Reading build assets from: {build_index}")
    with open(build_index, 'r') as f:
        build_content = f.read()

    # Extract asset filenames from build
    try:
        main_js = extract_asset_filename(
            build_content,
            r'src="/static/trend-convergence/assets/(main-[^"]+\.js)"'
        )
        index_js = extract_asset_filename(
            build_content,
            r'href="/static/trend-convergence/assets/(index-[^"]+\.js)"'
        )
        index_css = extract_asset_filename(
            build_content,
            r'href="/static/trend-convergence/assets/(index-[^"]+\.css)"'
        )
        main_css = extract_asset_filename(
            build_content,
            r'href="/static/trend-convergence/assets/(main-[^"]+\.css)"'
        )
    except ValueError as e:
        print(f"❌ Error extracting assets: {e}")
        return 1

    print(f"✅ Found assets:")
    print(f"   - Main JS:   {main_js}")
    print(f"   - Index JS:  {index_js}")
    print(f"   - Index CSS: {index_css}")
    print(f"   - Main CSS:  {main_css}")

    # Read template
    print(f"\n📝 Updating template: {template_file}")
    with open(template_file, 'r') as f:
        template_content = f.read()

    # Update template with new filenames
    # Update main JS
    template_content = re.sub(
        r'src="/static/trend-convergence/assets/main-[^"]+\.js"',
        f'src="/static/trend-convergence/assets/{main_js}"',
        template_content
    )

    # Update index JS
    template_content = re.sub(
        r'href="/static/trend-convergence/assets/index-[^"]+\.js"',
        f'href="/static/trend-convergence/assets/{index_js}"',
        template_content
    )

    # Update index CSS
    template_content = re.sub(
        r'href="/static/trend-convergence/assets/index-[^"]+\.css"',
        f'href="/static/trend-convergence/assets/{index_css}"',
        template_content
    )

    # Update main CSS
    template_content = re.sub(
        r'href="/static/trend-convergence/assets/main-[^"]+\.css"',
        f'href="/static/trend-convergence/assets/{main_css}"',
        template_content
    )

    # Write updated template
    with open(template_file, 'w') as f:
        f.write(template_content)

    print(f"✅ Template updated successfully!")
    print(f"\n🔄 Next steps:")
    print(f"   1. Copy assets to static: Already done!")
    print(f"   2. Restart the service: sudo systemctl restart multi.aunoo.ai")
    print(f"   3. Test at: https://multi.aunoo.ai/trend-convergence")

    return 0

if __name__ == "__main__":
    exit(main())
