#!/usr/bin/env python3
"""
Clear cache files that were created before the bug fix.
This ensures re-analysis will generate fresh results with the topic field.
"""

import os
import json
from pathlib import Path
from datetime import datetime

# Cache directory
CACHE_DIR = Path("cache")

# Cutoff time - cache files created before this need to be cleared
# Set to when the bug fix was applied (October 15, 2025 10:35 UTC)
CUTOFF_TIME = datetime(2025, 10, 15, 10, 35, 0).timestamp()

def clear_bad_cache():
    """Clear cache files created before the bug fix."""

    print(f"\n{'='*80}")
    print(f"Clearing Cache Files Created Before Bug Fix")
    print(f"Cutoff time: {datetime.fromtimestamp(CUTOFF_TIME)}")
    print(f"{'='*80}\n")

    cleared_count = 0
    kept_count = 0

    # Walk through cache directory
    for cache_file in CACHE_DIR.rglob("*.json"):
        try:
            # Get file modification time
            mtime = cache_file.stat().st_mtime

            # If file was created before cutoff, check if it needs clearing
            if mtime < CUTOFF_TIME:
                # Read the cache file to check if it has the bug
                with open(cache_file, 'r') as f:
                    cache_data = json.load(f)

                    # Check if analysis result is missing the topic field
                    analysis = cache_data.get('analysis', {})
                    if 'uri' in analysis and 'topic' not in analysis:
                        # This cache file has the bug - delete it
                        cache_file.unlink()
                        cleared_count += 1
                        if cleared_count <= 5:  # Show first 5
                            print(f"🗑️  Cleared: {cache_file.name}")
                    else:
                        kept_count += 1
            else:
                kept_count += 1

        except Exception as e:
            print(f"⚠️  Error processing {cache_file}: {e}")

    print(f"\n{'='*80}")
    print(f"Summary:")
    print(f"  🗑️  Cleared: {cleared_count} cache files")
    print(f"  ✅ Kept: {kept_count} cache files")
    print(f"{'='*80}\n")

if __name__ == "__main__":
    clear_bad_cache()
