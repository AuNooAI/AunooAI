#!/usr/bin/env python3
"""
Script to preserve user-defined files during updates.
This script can be run before and after pulling updates to protect custom
configurations.
"""

import os
import shutil
import json
import argparse
import logging
from pathlib import Path
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# Files to preserve (relative to project root)
USER_FILES = [
    "app/data/fnapp.db",
    "app/config/config.json",
    "app/config/litellm_config.yaml",
    "app/config/templates.json",
    "app/config/provider_config.json",
    ".env"
]


def get_project_root():
    """Get the project root directory."""
    script_dir = Path(os.path.dirname(os.path.abspath(__file__)))
    return script_dir.parent


def backup_files(backup_dir):
    """Backup user files to the specified directory."""
    root_dir = get_project_root()
    backup_path = root_dir / backup_dir
    
    # Create backup directory if it doesn't exist
    if not backup_path.exists():
        backup_path.mkdir(parents=True)
    
    # Create timestamp for this backup
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_timestamp_dir = backup_path / timestamp
    backup_timestamp_dir.mkdir()
    
    logger.info(f"Backing up user files to {backup_timestamp_dir}")
    
    # Copy each file to backup directory
    for file_path in USER_FILES:
        src_path = root_dir / file_path
        if not src_path.exists():
            logger.warning(f"File {src_path} does not exist, skipping backup")
            continue
            
        # Create destination directory structure
        dst_path = backup_timestamp_dir / file_path
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Backup file or directory
        if src_path.is_dir():
            shutil.copytree(src_path, dst_path)
            logger.info(f"Backed up directory {file_path}")
        else:
            shutil.copy2(src_path, dst_path)
            logger.info(f"Backed up file {file_path}")
    
    # Write manifest file with backup info
    manifest = {
        "timestamp": timestamp,
        "files": USER_FILES,
        "backup_date": datetime.now().isoformat()
    }
    
    with open(backup_timestamp_dir / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)
    
    logger.info(f"Backup completed successfully to {backup_timestamp_dir}")
    return backup_timestamp_dir


def restore_files(backup_dir):
    """Restore user files from the specified backup directory."""
    root_dir = get_project_root()
    backup_path = Path(backup_dir)
    
    if not backup_path.exists():
        logger.error(f"Backup directory {backup_path} does not exist")
        return False
    
    # Verify manifest file exists
    manifest_path = backup_path / "manifest.json"
    if not manifest_path.exists():
        logger.error(f"Manifest file not found in {backup_path}")
        return False
    
    # Load manifest
    with open(manifest_path) as f:
        manifest = json.load(f)
    
    logger.info(f"Restoring files from backup {backup_path}")
    
    # Restore each file
    for file_path in manifest["files"]:
        src_path = backup_path / file_path
        dst_path = root_dir / file_path
        
        if not src_path.exists():
            logger.warning(f"File {file_path} not found in backup, skipping")
            continue
        
        # Ensure target directory exists
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Check if the original file exists and protect if needed
        if dst_path.exists():
            # Skip if directory and it already exists
            if dst_path.is_dir() and src_path.is_dir():
                logger.info(f"Directory {file_path} already exists, merging contents")
                # For directories, copy contents instead of replacing
                for item in src_path.glob("**/*"):
                    if item.is_file():
                        rel_path = item.relative_to(src_path)
                        target = dst_path / rel_path
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(item, target)
            else:
                # For files, make a backup before overwriting
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_file = f"{dst_path}.{timestamp}.bak"
                shutil.copy2(dst_path, backup_file)
                logger.info(f"Created backup of existing file: {backup_file}")
                
                # Remove existing file/directory
                if dst_path.is_dir():
                    shutil.rmtree(dst_path)
                else:
                    os.remove(dst_path)
        
        # Restore from backup
        if src_path.is_dir():
            shutil.copytree(src_path, dst_path)
            logger.info(f"Restored directory {file_path}")
        else:
            shutil.copy2(src_path, dst_path)
            logger.info(f"Restored file {file_path}")
    
    logger.info("Restore completed successfully")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Backup and restore user-defined configuration files"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # Backup command
    backup_parser = subparsers.add_parser("backup", help="Backup user files")
    backup_parser.add_argument(
        "--dir", 
        default="backups", 
        help="Directory to store backups (relative to project root)"
    )
    
    # Restore command
    restore_parser = subparsers.add_parser("restore", help="Restore user files")
    restore_parser.add_argument(
        "backup_dir", 
        help="Path to backup directory containing the files to restore"
    )
    
    # List command
    list_parser = subparsers.add_parser("list", help="List available backups")
    list_parser.add_argument(
        "--dir", 
        default="backups", 
        help="Directory containing backups (relative to project root)"
    )
    
    args = parser.parse_args()
    
    if args.command == "backup":
        backup_files(args.dir)
    elif args.command == "restore":
        restore_files(args.backup_dir)
    elif args.command == "list":
        root_dir = get_project_root()
        backup_dir = root_dir / args.dir
        
        if not backup_dir.exists():
            logger.error(f"Backup directory {backup_dir} does not exist")
            return
        
        backups = sorted([d for d in backup_dir.iterdir() if d.is_dir()])
        
        if not backups:
            logger.info("No backups found")
            return
        
        logger.info(f"Available backups in {backup_dir}:")
        for backup in backups:
            manifest_path = backup / "manifest.json"
            if manifest_path.exists():
                with open(manifest_path) as f:
                    manifest = json.load(f)
                    backup_date = manifest.get("backup_date", "Unknown date")
                    logger.info(f"- {backup.name} ({backup_date})")
            else:
                logger.info(f"- {backup.name} (No manifest file)")
    else:
        parser.print_help()


if __name__ == "__main__":
    main() 