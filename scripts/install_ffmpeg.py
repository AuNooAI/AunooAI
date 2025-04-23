#!/usr/bin/env python
"""
Script to install FFmpeg if it's not already installed.
This script should be run before starting the application to ensure
FFmpeg is properly installed and available.
"""

import os
import sys
import subprocess
import platform
import logging
import shutil
from pathlib import Path

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def check_ffmpeg_installed():
    """Check if FFmpeg is already installed."""
    logger.info("Checking if FFmpeg is installed...")
    
    # Check if ffmpeg is in PATH
    ffmpeg_path = shutil.which("ffmpeg")
    ffprobe_path = shutil.which("ffprobe")
    
    if ffmpeg_path and ffprobe_path:
        logger.info(f"FFmpeg is already installed: {ffmpeg_path}")
        logger.info(f"FFprobe is already installed: {ffprobe_path}")
        return True
    
    logger.info("FFmpeg is not installed or not in PATH")
    return False

def install_ffmpeg_linux():
    """Install FFmpeg on Linux."""
    logger.info("Installing FFmpeg on Linux...")
    
    try:
        # Try to install using apt (Debian/Ubuntu)
        subprocess.run(["sudo", "apt-get", "update"], check=True)
        subprocess.run(["sudo", "apt-get", "install", "-y", "ffmpeg"], check=True)
        logger.info("Successfully installed FFmpeg using apt")
        return True
    except subprocess.CalledProcessError:
        logger.warning("Failed to install FFmpeg using apt")
        
        try:
            # Try to install using yum (RHEL/CentOS)
            subprocess.run(["sudo", "yum", "install", "-y", "ffmpeg"], check=True)
            logger.info("Successfully installed FFmpeg using yum")
            return True
        except subprocess.CalledProcessError:
            logger.warning("Failed to install FFmpeg using yum")
            
            try:
                # Try to install using dnf (Fedora)
                subprocess.run(["sudo", "dnf", "install", "-y", "ffmpeg"], check=True)
                logger.info("Successfully installed FFmpeg using dnf")
                return True
            except subprocess.CalledProcessError:
                logger.error("Failed to install FFmpeg using dnf")
                return False

def install_ffmpeg_macos():
    """Install FFmpeg on macOS."""
    logger.info("Installing FFmpeg on macOS...")
    
    try:
        # Check if Homebrew is installed
        if shutil.which("brew"):
            subprocess.run(["brew", "install", "ffmpeg"], check=True)
            logger.info("Successfully installed FFmpeg using Homebrew")
            return True
        else:
            logger.error("Homebrew is not installed. Please install Homebrew first.")
            return False
    except subprocess.CalledProcessError:
        logger.error("Failed to install FFmpeg using Homebrew")
        return False

def install_ffmpeg_windows():
    """Install FFmpeg on Windows."""
    logger.info("Installing FFmpeg on Windows...")
    
    try:
        # Check if Chocolatey is installed
        if shutil.which("choco"):
            subprocess.run(["choco", "install", "ffmpeg", "-y"], check=True)
            logger.info("Successfully installed FFmpeg using Chocolatey")
            return True
        else:
            logger.error("Chocolatey is not installed. Please install Chocolatey first.")
            logger.info("You can install Chocolatey by running the following command in PowerShell as Administrator:")
            logger.info('Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString("https://community.chocolatey.org/install.ps1"))')
            return False
    except subprocess.CalledProcessError:
        logger.error("Failed to install FFmpeg using Chocolatey")
        return False

def download_ffmpeg_windows():
    """Download FFmpeg for Windows."""
    logger.info("Downloading FFmpeg for Windows...")
    
    try:
        # Create ffmpeg directory
        base_dir = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        ffmpeg_dir = base_dir / "ffmpeg"
        ffmpeg_dir.mkdir(parents=True, exist_ok=True)
        
        # Download FFmpeg
        ffmpeg_url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
        zip_path = ffmpeg_dir / "ffmpeg.zip"
        
        subprocess.run(["curl", "-L", ffmpeg_url, "-o", str(zip_path)], check=True)
        
        # Extract FFmpeg
        import zipfile
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(ffmpeg_dir)
        
        # Remove zip file
        zip_path.unlink()
        
        logger.info("Successfully downloaded and extracted FFmpeg")
        return True
    except Exception as e:
        logger.error(f"Failed to download FFmpeg: {str(e)}")
        return False

def main():
    """Install FFmpeg if it's not already installed."""
    logger.info("Starting FFmpeg installation check...")
    
    # Check if FFmpeg is already installed
    if check_ffmpeg_installed():
        logger.info("FFmpeg is already installed. No need to install.")
        return True
    
    # Install FFmpeg based on the operating system
    system = platform.system().lower()
    
    if system == "linux":
        return install_ffmpeg_linux()
    elif system == "darwin":  # macOS
        return install_ffmpeg_macos()
    elif system == "windows":
        # Try to install using Chocolatey first
        if install_ffmpeg_windows():
            return True
        
        # If Chocolatey fails, download FFmpeg
        return download_ffmpeg_windows()
    else:
        logger.error(f"Unsupported operating system: {system}")
        return False

if __name__ == "__main__":
    if main():
        logger.info("FFmpeg installation completed successfully.")
        sys.exit(0)
    else:
        logger.error("FFmpeg installation failed.")
        sys.exit(1) 