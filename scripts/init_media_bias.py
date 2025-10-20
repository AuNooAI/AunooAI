#!/usr/bin/env python3
"""
Initialize media bias data from CSV file.
Works with both SQLite and PostgreSQL databases.
"""

import sys
import os
import logging
from pathlib import Path

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)
logger = logging.getLogger(__name__)


def init_media_bias():
    """Initialize media bias data from CSV file."""

    try:
        # Import after setting up path
        from app.database import Database
        from app.models.media_bias import MediaBias

        # Initialize database
        db = Database()
        media_bias = MediaBias(db)

        # Get CSV file path
        csv_path = Path('app/data/mbfc_raw.csv')

        if not csv_path.exists():
            logger.error(f"❌ Media bias CSV file not found: {csv_path}")
            return False

        logger.info(f"📁 Loading media bias data from: {csv_path}")

        # Check if data already exists
        existing_count = len(media_bias.get_all_sources())
        if existing_count > 0:
            logger.info(f"✅ Media bias data already initialized ({existing_count} sources)")
            return True

        # Import from CSV
        logger.info("⏳ Importing media bias data...")
        imported_count, failed_count = media_bias.import_from_csv(str(csv_path))

        if imported_count > 0:
            logger.info(f"✅ Successfully imported {imported_count} media bias sources")
            if failed_count > 0:
                logger.warning(f"⚠️  Failed to import {failed_count} sources")

            # Enable media bias enrichment by default
            media_bias.set_enabled(True)
            logger.info("✅ Media bias enrichment enabled")

            return True
        else:
            logger.error(f"❌ No media bias sources imported (failed: {failed_count})")
            return False

    except Exception as e:
        logger.error(f"❌ Error initializing media bias data: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    logger.info("=" * 70)
    logger.info("Media Bias Data Initialization")
    logger.info("=" * 70)

    success = init_media_bias()

    if success:
        logger.info("\n🎉 Media bias data initialized successfully!")
        sys.exit(0)
    else:
        logger.error("\n❌ Media bias initialization failed!")
        sys.exit(1)
