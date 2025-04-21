#!/usr/bin/env python
"""
Script to test audio file operations.
This script creates a simple audio file and tests the audio utility functions.
"""

import os
import sys
import logging
from pathlib import Path
import tempfile
import shutil
import time

# Add the parent directory to the path so we can import the app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Add FFmpeg to system PATH
base_dir = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ffmpeg_dir = str(base_dir / "ffmpeg" / "ffmpeg-master-latest-win64-gpl" / "bin")
os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")

from app.utils.audio import (
    ensure_audio_directory,
    save_audio_file,
    combine_audio_files,
    AUDIO_DIR,
    USER_TEMP_DIR
)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def verify_ffmpeg():
    """Verify FFmpeg installation."""
    logger.info("Verifying FFmpeg installation...")
    
    try:
        import subprocess
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
        if result.returncode == 0:
            logger.info("FFmpeg is available")
            logger.info(f"FFmpeg version: {result.stdout.splitlines()[0]}")
            return True
        else:
            logger.error("FFmpeg test failed")
            logger.error(f"Error output: {result.stderr}")
            return False
    except Exception as e:
        logger.error(f"Error verifying FFmpeg: {str(e)}")
        return False

def create_test_audio():
    """Create a simple test audio file."""
    # Create a simple audio file (1 second of silence)
    from pydub import AudioSegment
    from pydub.generators import Sine
    
    # Generate a 1-second sine wave at 440 Hz
    audio = Sine(440).to_audio_segment(duration=1000)
    
    # Export to bytes using a temporary file
    temp_dir = tempfile.mkdtemp()
    temp_path = os.path.join(temp_dir, "temp.mp3")
    
    try:
        audio.export(temp_path, format="mp3")
        with open(temp_path, "rb") as f:
            audio_bytes = f.read()
        return audio_bytes
    finally:
        try:
            # Clean up temporary files
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception as e:
            logger.warning(f"Failed to clean up temporary directory: {str(e)}")

def test_save_audio_file():
    """Test saving an audio file."""
    logger.info("Testing save_audio_file...")
    
    try:
        # Create a test audio file
        audio_bytes = create_test_audio()
        if not audio_bytes:
            logger.error("Failed to create test audio")
            return False
        
        # Save the audio file
        filename = f"test_audio_{int(time.time())}.mp3"
        result = save_audio_file(audio_bytes, filename)
        
        logger.info(f"Saved audio file: {result}")
        
        # Check if the file exists
        file_path = AUDIO_DIR / filename
        if file_path.exists():
            logger.info(f"File exists: {file_path}")
            logger.info(f"File size: {file_path.stat().st_size} bytes")
            return True
        else:
            logger.error(f"File does not exist: {file_path}")
            return False
    except Exception as e:
        logger.error(f"Error in test_save_audio_file: {str(e)}")
        return False

def test_combine_audio_files():
    """Test combining audio files."""
    logger.info("Testing combine_audio_files...")
    
    try:
        # Create test audio files
        audio_bytes1 = create_test_audio()
        audio_bytes2 = create_test_audio()
        
        if not audio_bytes1 or not audio_bytes2:
            logger.error("Failed to create test audio files")
            return False
        
        # Combine the audio files
        output_filename = f"test_combined_{int(time.time())}.mp3"
        duration = combine_audio_files([audio_bytes1, audio_bytes2], output_filename)
        
        logger.info(f"Combined audio duration: {duration:.2f} seconds")
        
        # Check if the file exists
        file_path = AUDIO_DIR / output_filename
        if file_path.exists():
            logger.info(f"File exists: {file_path}")
            logger.info(f"File size: {file_path.stat().st_size} bytes")
            return True
        else:
            logger.error(f"File does not exist: {file_path}")
            return False
    except Exception as e:
        logger.error(f"Error in test_combine_audio_files: {str(e)}")
        return False

def main():
    """Run the tests."""
    logger.info("Starting audio operations test...")
    
    # Verify FFmpeg installation
    if not verify_ffmpeg():
        logger.error("FFmpeg verification failed. Please check FFmpeg installation.")
        return False
    
    # Ensure the audio directory exists
    if not ensure_audio_directory():
        logger.error("Failed to ensure audio directory exists.")
        return False
    
    # Test saving an audio file
    if not test_save_audio_file():
        logger.error("Failed to save audio file.")
        return False
    
    # Test combining audio files
    if not test_combine_audio_files():
        logger.error("Failed to combine audio files.")
        return False
    
    logger.info("All tests completed successfully.")
    return True

if __name__ == "__main__":
    if main():
        sys.exit(0)
    else:
        sys.exit(1) 