#!/usr/bin/env python
"""
Setup script for the AunooAI application.
This script:
1. Installs FFmpeg if it's not already installed
2. Sets up the application environment
3. Installs dependencies
"""

import os
import sys
import subprocess
import logging
from pathlib import Path

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def run_script(script_path):
    """Run a Python script and return True if successful."""
    logger.info(f"Running script: {script_path}")
    
    try:
        result = subprocess.run([sys.executable, script_path], check=True)
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        logger.error(f"Script {script_path} failed with error: {str(e)}")
        return False

def install_dependencies():
    """Install Python dependencies."""
    logger.info("Installing Python dependencies...")
    
    try:
        # Install dependencies from requirements.txt
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], check=True)
        logger.info("Successfully installed Python dependencies")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to install Python dependencies: {str(e)}")
        return False

def create_directories():
    """Create necessary directories."""
    logger.info("Creating necessary directories...")
    
    try:
        # Create static/audio directory
        audio_dir = Path("static/audio")
        audio_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created directory: {audio_dir}")
        
        # Create tmp directory
        tmp_dir = Path("tmp")
        tmp_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created directory: {tmp_dir}")
        
        # Create tmp/aunoo_audio directory
        aunoo_audio_dir = tmp_dir / "aunoo_audio"
        aunoo_audio_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created directory: {aunoo_audio_dir}")
        
        return True
    except Exception as e:
        logger.error(f"Failed to create directories: {str(e)}")
        return False

def main():
    """Run the setup process."""
    logger.info("Starting setup process...")
    
    # Get the directory of this script
    script_dir = Path(os.path.dirname(os.path.abspath(__file__)))
    
    # Run the FFmpeg installation script
    ffmpeg_script = script_dir / "install_ffmpeg.py"
    if not run_script(ffmpeg_script):
        logger.error("FFmpeg installation failed. Setup aborted.")
        return False
    
    # Install dependencies
    if not install_dependencies():
        logger.error("Dependency installation failed. Setup aborted.")
        return False
    
    # Create necessary directories
    if not create_directories():
        logger.error("Directory creation failed. Setup aborted.")
        return False
    
    logger.info("Setup completed successfully.")
    return True

if __name__ == "__main__":
    if main():
        logger.info("Setup completed successfully.")
        sys.exit(0)
    else:
        logger.error("Setup failed.")
        sys.exit(1) 