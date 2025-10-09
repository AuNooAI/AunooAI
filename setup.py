#!/usr/bin/env python
"""
Setup script for the AunooAI application.
This script:
1. Installs Python dependencies
2. Creates necessary directories
3. Configures database (SQLite or PostgreSQL)
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

def setup_database():
    """Prompt user for database setup."""
    logger.info("\n" + "=" * 60)
    logger.info("Database Configuration")
    logger.info("=" * 60)

    # Check if .env already has DB_TYPE configured
    env_path = Path(".env")
    db_type = None

    if env_path.exists():
        with open(env_path, 'r') as f:
            for line in f:
                if line.startswith('DB_TYPE='):
                    db_type = line.split('=')[1].strip()
                    break

    if db_type:
        logger.info(f"Current database: {db_type}")
        response = input("\nWould you like to change database configuration? (y/N): ").lower()
        if response != 'y':
            logger.info("Keeping current database configuration")
            return True

    logger.info("\nAunooAI supports two database options:")
    logger.info("1. SQLite (default) - Simple, file-based, good for development")
    logger.info("2. PostgreSQL - Production-grade, better for concurrent users")

    choice = input("\nChoose database (1 for SQLite, 2 for PostgreSQL) [1]: ").strip()

    if choice == '2':
        logger.info("\nSetting up PostgreSQL...")
        postgresql_script = Path("scripts/setup_postgresql.py")

        if postgresql_script.exists():
            if run_script(postgresql_script):
                logger.info("✅ PostgreSQL setup completed")
                return True
            else:
                logger.error("PostgreSQL setup failed")
                return False
        else:
            logger.error(f"PostgreSQL setup script not found: {postgresql_script}")
            return False
    else:
        logger.info("\nUsing SQLite database (default)")

        # Ensure .env has DB_TYPE=sqlite
        if env_path.exists():
            with open(env_path, 'r') as f:
                lines = f.readlines()

            # Update or add DB_TYPE
            found = False
            for i, line in enumerate(lines):
                if line.startswith('DB_TYPE='):
                    lines[i] = 'DB_TYPE=sqlite\n'
                    found = True
                    break

            if not found:
                lines.append('DB_TYPE=sqlite\n')

            with open(env_path, 'w') as f:
                f.writelines(lines)

        logger.info("✅ SQLite configured")
        return True

def initialize_org_profiles():
    """Initialize default organizational profiles."""
    logger.info("\nInitializing organizational profiles...")

    # Check if database exists and has organizational_profiles table
    env_path = Path(".env")
    db_type = 'sqlite'  # default

    if env_path.exists():
        with open(env_path, 'r') as f:
            for line in f:
                if line.strip().startswith('DB_TYPE='):
                    db_type = line.split('=')[1].strip().lower()
                    break

    # Run appropriate initialization based on database type
    if db_type == 'postgresql':
        # For PostgreSQL, we need Alembic migrations to be run first
        logger.info("PostgreSQL detected - organizational profiles should be created via migrations")
        logger.info("Run: alembic upgrade head")
        return True
    else:
        # For SQLite, run the migration script that creates profiles
        script_path = Path("scripts/migrate_organizational_profiles.py")
        if script_path.exists():
            try:
                result = subprocess.run([sys.executable, str(script_path)], check=False)
                if result.returncode == 0:
                    logger.info("✅ Organizational profiles initialized")
                    return True
                else:
                    logger.warning("⚠️  Organizational profiles initialization had warnings (non-fatal)")
                    return True
            except Exception as e:
                logger.warning(f"⚠️  Could not initialize organizational profiles: {e}")
                logger.info("You can manually run: python scripts/migrate_organizational_profiles.py")
                return True
        else:
            logger.info("Organizational profiles script not found - skipping")
            return True

def main():
    """Run the setup process."""
    logger.info("Starting setup process...")

    # Install dependencies
    if not install_dependencies():
        logger.error("Dependency installation failed. Setup aborted.")
        return False

    # Create necessary directories
    if not create_directories():
        logger.error("Directory creation failed. Setup aborted.")
        return False

    # Setup database
    if not setup_database():
        logger.error("Database setup failed. Setup aborted.")
        return False

    # Initialize organizational profiles (non-fatal)
    initialize_org_profiles()

    logger.info("\n" + "=" * 60)
    logger.info("Setup completed successfully!")
    logger.info("=" * 60)
    logger.info("\nYou can now start the application with:")
    logger.info("  python app/run.py")
    logger.info("")
    return True

if __name__ == "__main__":
    if main():
        logger.info("Setup completed successfully.")
        sys.exit(0)
    else:
        logger.error("Setup failed.")
        sys.exit(1) 