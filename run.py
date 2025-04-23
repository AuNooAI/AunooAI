#!/usr/bin/env python
"""
Run script for the AunooAI application.
This script:
1. Runs the setup script to ensure FFmpeg is installed
2. Starts the FastAPI application
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

def run_setup():
    """Run the setup script and return True if successful."""
    logger.info("Running setup script...")
    
    # Get the directory of this script
    script_dir = Path(os.path.dirname(os.path.abspath(__file__)))
    setup_script = script_dir / "scripts" / "setup.py"
    
    try:
        result = subprocess.run([sys.executable, setup_script], check=True)
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        logger.error(f"Setup script failed with error: {str(e)}")
        return False

def start_application():
    """Start the FastAPI application."""
    logger.info("Starting the application...")
    
    try:
        # Start the FastAPI application using uvicorn
        subprocess.run([
            sys.executable, 
            "-m", 
            "uvicorn", 
            "app.main:app", 
            "--host", 
            "0.0.0.0", 
            "--port", 
            "8000", 
            "--reload"
        ], check=True)
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to start the application: {str(e)}")
        return False
    except KeyboardInterrupt:
        logger.info("Application stopped by user.")
        return True

def main():
    """Run the application."""
    logger.info("Starting AunooAI application...")
    
    # Run the setup script
    if not run_setup():
        logger.error("Setup failed. Application startup aborted.")
        return False
    
    # Start the application
    return start_application()

if __name__ == "__main__":
    if main():
        logger.info("Application started successfully.")
        sys.exit(0)
    else:
        logger.error("Application failed to start.")
        sys.exit(1) 