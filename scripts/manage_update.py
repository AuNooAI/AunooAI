#!/usr/bin/env python3
"""
Manage application updates safely.
This script provides a workflow for updating the application while preserving
user-defined files and configurations.
"""

import os
import sys
import subprocess
import logging
import argparse
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def get_project_root():
    """Get the project root directory."""
    script_dir = Path(os.path.dirname(os.path.abspath(__file__)))
    return script_dir.parent


def run_command(command, capture_output=True):
    """Run a shell command and return the result."""
    logger.info(f"Running command: {command}")
    try:
        result = subprocess.run(
            command,
            shell=True,
            check=True,
            capture_output=capture_output,
            text=True,
        )
        if capture_output:
            return result.stdout.strip()
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed: {e}")
        if capture_output:
            logger.error(f"Error output: {e.stderr}")
        return False


def backup_user_files(backup_dir="backups"):
    """Backup user-defined files."""
    logger.info("Backing up user-defined files...")
    root_dir = get_project_root()
    script_path = root_dir / "scripts/preserve_user_files.py"
    
    if not script_path.exists():
        logger.error(f"Backup script not found: {script_path}")
        return False
    
    result = run_command(f"{script_path} backup --dir {backup_dir}")
    if result:
        logger.info("Backup completed successfully")
        return True
    
    logger.error("Backup failed")
    return False


def get_current_branch():
    """Get the name of the current git branch."""
    return run_command("git branch --show-current")


def get_current_commit():
    """Get the current commit hash."""
    return run_command("git rev-parse HEAD")


def fetch_updates():
    """Fetch the latest updates from the remote repository."""
    logger.info("Fetching updates...")
    return run_command("git fetch --all", capture_output=False)


def check_for_updates(branch=None):
    """Check if updates are available for the current or specified branch."""
    current_branch = branch or get_current_branch()
    local_commit = run_command(f"git rev-parse {current_branch}")
    remote_commit = run_command(f"git rev-parse origin/{current_branch}")
    
    if local_commit == remote_commit:
        logger.info("No updates available")
        return False
    
    logger.info(f"Updates available: {local_commit[:7]} → {remote_commit[:7]}")
    
    # Get commit messages for new changes
    log_output = run_command(
        f"git log --pretty=format:'%h - %s' {local_commit}..{remote_commit}"
    )
    if log_output:
        logger.info("Incoming changes:")
        for line in log_output.split("\n"):
            logger.info(f"  {line}")
    
    return True


def apply_update(branch=None, stash=True):
    """Apply the latest updates from the remote repository."""
    target_branch = branch or get_current_branch()
    
    # Save unstaged changes if requested
    if stash:
        logger.info("Stashing local changes...")
        run_command("git stash")
    
    # Pull the latest changes
    logger.info(f"Pulling updates for branch {target_branch}...")
    result = run_command(f"git pull origin {target_branch}", capture_output=False)
    
    if not result:
        logger.error("Failed to pull updates")
        return False
    
    logger.info("Updates applied successfully")
    return True


def checkout_branch(branch, create=False):
    """Checkout a different branch."""
    if create:
        logger.info(f"Creating and checking out branch {branch}...")
        cmd = f"git checkout -b {branch}"
    else:
        logger.info(f"Checking out branch {branch}...")
        cmd = f"git checkout {branch}"
    
    return run_command(cmd, capture_output=False)


def restore_user_files(backup_dir):
    """Restore user-defined files from backup."""
    logger.info(f"Restoring user files from {backup_dir}...")
    root_dir = get_project_root()
    script_path = root_dir / "scripts/preserve_user_files.py"
    
    if not script_path.exists():
        logger.error(f"Restore script not found: {script_path}")
        return False
    
    result = run_command(f"{script_path} restore {backup_dir}")
    if result:
        logger.info("Restore completed successfully")
        return True
    
    logger.error("Restore failed")
    return False


def initialize_defaults():
    """Initialize default configuration files."""
    logger.info("Initializing default configurations...")
    root_dir = get_project_root()
    script_path = root_dir / "scripts/init_defaults.py"
    
    if not script_path.exists():
        logger.error(f"Defaults initialization script not found: {script_path}")
        return False
    
    result = run_command(f"{script_path}", capture_output=False)
    if result:
        logger.info("Default configurations initialized successfully")
        return True
    
    logger.error("Failed to initialize default configurations")
    return False


def update_workflow(branch=None, skip_backup=False, skip_restore=False):
    """Run the complete update workflow."""
    # Get current branch and commit for reference
    current_branch = get_current_branch()
    current_commit = get_current_commit()
    logger.info(f"Current state: branch={current_branch}, commit={current_commit[:7]}")
    
    # Target branch for update
    target_branch = branch or current_branch
    
    # Fetch updates
    if not fetch_updates():
        logger.error("Failed to fetch updates, aborting")
        return False
    
    # Check for available updates
    if not check_for_updates(target_branch):
        logger.info("No updates available. Already at the latest version.")
        return True
    
    # Backup user files if not skipped
    backup_dir = None
    if not skip_backup:
        root_dir = get_project_root()
        backup_result = backup_user_files()
        if not backup_result:
            logger.error("Backup failed, aborting update")
            return False
        
        # Get the most recent backup directory
        script_path = root_dir / "scripts/preserve_user_files.py"
        latest_backup = run_command(f"{script_path} list --dir backups | grep -")
        if latest_backup:
            backup_dir = latest_backup.split("- ")[1].split(" ")[0]
            backup_dir = f"backups/{backup_dir}"
            logger.info(f"Latest backup directory: {backup_dir}")
    
    # Apply the update
    if target_branch != current_branch:
        # Switch to target branch
        if not checkout_branch(target_branch):
            logger.error(f"Failed to checkout branch {target_branch}")
            return False
    
    if not apply_update(target_branch):
        logger.error("Failed to apply update")
        return False
    
    # Initialize default configurations
    if not initialize_defaults():
        logger.warning("Failed to initialize default configurations")
    
    # Restore user files if not skipped and backup was created
    if not skip_restore and backup_dir:
        if not restore_user_files(backup_dir):
            logger.error("Failed to restore user files")
            logger.info(
                f"Your backup is still available at {backup_dir} for manual restoration"
            )
            return False
    
    logger.info("Update completed successfully!")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Manage application updates safely"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # Update command
    update_parser = subparsers.add_parser(
        "update", help="Update the application safely"
    )
    update_parser.add_argument(
        "--branch", help="Target branch to update to", default=None
    )
    update_parser.add_argument(
        "--skip-backup", action="store_true", help="Skip backup step"
    )
    update_parser.add_argument(
        "--skip-restore", action="store_true", help="Skip restore step"
    )
    
    # Check command
    check_parser = subparsers.add_parser(
        "check", help="Check for available updates"
    )
    check_parser.add_argument(
        "--branch", help="Branch to check for updates", default=None
    )
    
    # Backup command
    backup_parser = subparsers.add_parser(
        "backup", help="Backup user configuration files"
    )
    backup_parser.add_argument(
        "--dir", default="backups", help="Directory to store backups"
    )
    
    # Restore command
    restore_parser = subparsers.add_parser(
        "restore", help="Restore user configuration files"
    )
    restore_parser.add_argument(
        "backup_dir", help="Backup directory to restore from"
    )
    
    # Initialize command
    init_parser = subparsers.add_parser(
        "init", help="Initialize default configuration files"
    )
    
    args = parser.parse_args()
    
    if args.command == "update":
        update_workflow(args.branch, args.skip_backup, args.skip_restore)
    elif args.command == "check":
        fetch_updates()
        check_for_updates(args.branch)
    elif args.command == "backup":
        backup_user_files(args.dir)
    elif args.command == "restore":
        restore_user_files(args.backup_dir)
    elif args.command == "init":
        initialize_defaults()
    else:
        parser.print_help()


if __name__ == "__main__":
    main() 