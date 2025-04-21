#!/usr/bin/env python
"""
Script to ensure the audio directory exists and has proper permissions.
This script should be run before starting the application to ensure
the audio directory is properly set up.
"""

import os
import sys
import stat
import logging
from pathlib import Path

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def ensure_audio_directory():
    """Ensure the audio directory exists and has proper permissions."""
    try:
        # Get the base directory (where the app is located)
        base_dir = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        audio_dir = base_dir / "static" / "audio"
        
        logger.info(f"Checking audio directory: {audio_dir}")
        
        # Create the audio directory if it doesn't exist
        audio_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created audio directory: {audio_dir}")
        
        # Set directory permissions to allow writing
        try:
            os.chmod(str(audio_dir), stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
            logger.info(f"Set permissions on audio directory: {audio_dir}")
        except Exception as e:
            logger.warning(f"Could not set permissions on audio directory: {str(e)}")
        
        # Verify write permissions by attempting to create a test file
        test_file = audio_dir / ".test_write"
        try:
            test_file.touch()
            test_file.unlink()
            logger.info(f"Write permissions verified for audio directory: {audio_dir}")
            return True
        except Exception as e:
            logger.error(f"No write permissions for audio directory: {str(e)}")
            return False
            
    except Exception as e:
        logger.error(f"Error ensuring audio directory exists: {str(e)}")
        return False

if __name__ == "__main__":
    logger.info("Starting audio directory check...")
    if ensure_audio_directory():
        logger.info("Audio directory check completed successfully.")
        sys.exit(0)
    else:
        logger.error("Audio directory check failed.")
        sys.exit(1) 