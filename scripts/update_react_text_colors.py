#!/usr/bin/env python3
"""
Update React/Tailwind text colors to match Bootstrap template readability.

This script updates Tailwind text color classes in React components to use
darker, more readable colors that match the Bootstrap templates.

Mapping:
- text-gray-700 → text-gray-800 (for body text)
- text-gray-600 → text-gray-700 (for secondary text)
- text-gray-500 → text-gray-600 (for muted text)
- text-gray-400 → text-gray-500 (for very muted text)

We also ensure primary headings use text-gray-950 for maximum contrast.
"""

import os
import re
from pathlib import Path

# Color mappings - make text darker for better readability
COLOR_MAPPINGS = {
    # Make body text darker (was too light)
    'text-gray-700': 'text-gray-800',
    'text-gray-600': 'text-gray-700',
    'text-gray-500': 'text-gray-600',
    'text-gray-400': 'text-gray-500',

    # Ensure headings use darkest color
    'text-gray-900': 'text-gray-950',
}

def update_file(filepath):
    """Update text color classes in a single file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        original_content = content
        changes_made = 0

        # Apply each color mapping
        for old_color, new_color in COLOR_MAPPINGS.items():
            # Match the class in various contexts (className, class, etc.)
            pattern = r'\b' + re.escape(old_color) + r'\b'
            matches = len(re.findall(pattern, content))
            if matches > 0:
                content = re.sub(pattern, new_color, content)
                changes_made += matches

        # Only write if changes were made
        if content != original_content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            return changes_made

        return 0

    except Exception as e:
        print(f"Error processing {filepath}: {e}")
        return 0

def main():
    """Update all React component files."""
    ui_src_path = Path('/home/orochford/tenants/multi.aunoo.ai/ui/src')

    if not ui_src_path.exists():
        print(f"Error: {ui_src_path} does not exist")
        return

    print("Updating React text colors for better readability...")
    print("=" * 60)

    total_files = 0
    total_changes = 0
    files_modified = []

    # Find all .tsx and .jsx files
    for ext in ['*.tsx', '*.jsx']:
        for filepath in ui_src_path.rglob(ext):
            changes = update_file(filepath)
            if changes > 0:
                total_files += 1
                total_changes += changes
                files_modified.append((filepath.relative_to(ui_src_path), changes))
                print(f"✓ {filepath.relative_to(ui_src_path)}: {changes} changes")

    print("=" * 60)
    print(f"\nSummary:")
    print(f"  Files modified: {total_files}")
    print(f"  Total changes: {total_changes}")

    if files_modified:
        print(f"\nTop modified files:")
        for filepath, changes in sorted(files_modified, key=lambda x: x[1], reverse=True)[:10]:
            print(f"  - {filepath}: {changes} changes")

    print("\n✓ React text colors updated to match Bootstrap readability!")

if __name__ == "__main__":
    main()
