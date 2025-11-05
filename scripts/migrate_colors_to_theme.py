#!/usr/bin/env python3
"""
Migrate hardcoded colors to design system variables
"""

import re
import os
from pathlib import Path

# Color mapping from hardcoded hex to CSS variables
COLOR_MAPPINGS = {
    # Pink/Accent colors
    '#ec4899': 'var(--colors-accent-8)',
    '#EC4899': 'var(--colors-accent-8)',
    '#FF69B4': 'var(--colors-accent-7)',
    '#ff69b4': 'var(--colors-accent-7)',
    '#FF1493': 'var(--colors-accent-10)',
    '#ff1493': 'var(--colors-accent-10)',
    '#f472b6': 'var(--colors-accent-6)',
    '#fdf2f8': 'var(--colors-accent-1)',
    '#fbcfe8': 'var(--colors-accent-3)',

    # Neutral/Grey colors
    '#111827': 'var(--colors-neutral-12)',
    '#1c2024': 'var(--colors-neutral-12)',
    '#212529': 'var(--colors-neutral-11)',
    '#343a40': 'var(--colors-neutral-10)',
    '#495057': 'var(--colors-neutral-9)',
    '#6c757d': 'var(--colors-neutral-8)',
    '#6b7280': 'var(--colors-neutral-8)',
    '#868e96': 'var(--colors-neutral-8)',
    '#adb5bd': 'var(--colors-neutral-7)',
    '#ced4da': 'var(--colors-neutral-6)',
    '#dee2e6': 'var(--colors-neutral-5)',
    '#e9ecef': 'var(--colors-neutral-4)',
    '#e5e7eb': 'var(--colors-neutral-4)',
    '#f1f3f5': 'var(--colors-neutral-3)',
    '#f3f4f6': 'var(--colors-neutral-3)',
    '#f8f9fa': 'var(--colors-neutral-2)',
    '#f9fafb': 'var(--colors-neutral-2)',
    '#fcfcfd': 'var(--colors-neutral-1)',

    # Success/Green colors
    '#10b981': 'var(--colors-success-9)',
    '#28a745': 'var(--colors-success-9)',
    '#22c55e': 'var(--colors-success-6)',
    '#16a34a': 'var(--colors-success-7)',
    '#15803d': 'var(--colors-success-8)',
    '#d4edda': 'var(--colors-success-2)',
    '#c3e6cb': 'var(--colors-success-3)',

    # Error/Red colors
    '#dc3545': 'var(--colors-error-9)',
    '#DC3545': 'var(--colors-error-9)',
    '#ef4444': 'var(--colors-error-6)',
    '#dc2626': 'var(--colors-error-7)',
    '#b91c1c': 'var(--colors-error-8)',
    '#f8d7da': 'var(--colors-error-2)',
    '#f5c6cb': 'var(--colors-error-3)',
    '#fee2e2': 'var(--colors-error-2)',

    # Warning/Amber colors
    '#ffc107': 'var(--colors-warning-9)',
    '#FFC107': 'var(--colors-warning-9)',
    '#f59e0b': 'var(--colors-warning-6)',
    '#d97706': 'var(--colors-warning-7)',
    '#fff3cd': 'var(--colors-warning-2)',
    '#ffeeba': 'var(--colors-warning-3)',

    # Info/Sky colors
    '#17a2b8': 'var(--colors-info-9)',
    '#0ea5e9': 'var(--colors-info-6)',
    '#0284c7': 'var(--colors-info-7)',
    '#d1ecf1': 'var(--colors-info-2)',
    '#bee5eb': 'var(--colors-info-3)',
    '#5dade2': 'var(--colors-info-5)',

    # Basic colors
    '#ffffff': 'var(--colors-white)',
    '#FFFFFF': 'var(--colors-white)',
    '#fff': 'var(--colors-white)',
    '#FFF': 'var(--colors-white)',
    '#000000': 'var(--colors-black)',
    '#000': 'var(--colors-black)',

    # Common shorthands to neutral
    '#333': 'var(--colors-neutral-11)',
    '#666': 'var(--colors-neutral-8)',
    '#999': 'var(--colors-neutral-7)',
    '#ccc': 'var(--colors-neutral-6)',
    '#ddd': 'var(--colors-neutral-5)',
    '#eee': 'var(--colors-neutral-4)',
    '#f5f5f5': 'var(--colors-neutral-3)',
}

def migrate_file(filepath):
    """Migrate a single file"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        original_content = content
        changes_made = 0

        # Replace each color
        for old_color, new_var in COLOR_MAPPINGS.items():
            # Case-insensitive replacement for hex colors
            pattern = re.compile(re.escape(old_color), re.IGNORECASE)
            matches = pattern.findall(content)
            if matches:
                content = pattern.sub(new_var, content)
                changes_made += len(matches)

        # Only write if changes were made
        if content != original_content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"✓ {filepath.name}: {changes_made} color replacements")
            return changes_made
        else:
            return 0

    except Exception as e:
        print(f"✗ Error processing {filepath}: {e}")
        return 0

def main():
    """Main migration function"""
    templates_dir = Path(__file__).parent.parent / 'templates'

    print("🎨 Migrating hardcoded colors to design system variables...\n")

    # Get all HTML files
    html_files = list(templates_dir.glob('*.html'))

    total_changes = 0
    files_modified = 0

    for filepath in sorted(html_files):
        changes = migrate_file(filepath)
        if changes > 0:
            total_changes += changes
            files_modified += 1

    print(f"\n✅ Migration complete!")
    print(f"   Files modified: {files_modified}/{len(html_files)}")
    print(f"   Total color replacements: {total_changes}")
    print(f"\n📝 Next steps:")
    print(f"   1. Review changes: git diff templates/")
    print(f"   2. Test pages for visual regressions")
    print(f"   3. Commit changes: git add templates/ && git commit -m 'Migrate to design system'")

if __name__ == '__main__':
    main()
