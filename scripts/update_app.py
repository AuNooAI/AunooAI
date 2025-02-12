import subprocess
import shutil
import os
from pathlib import Path
import logging
from datetime import datetime
from db_merge import DatabaseMerger

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class AppUpdater:
    def __init__(self):
        self.root_dir = Path().absolute()
        self.backup_dir = self.root_dir / "backups"
        self.backup_dir.mkdir(exist_ok=True)
        self.db_merger = DatabaseMerger()

    def create_backup(self) -> Path:
        """Create timestamped backup of critical files"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.backup_dir / timestamp
        backup_path.mkdir(exist_ok=True)

        # Backup .env file if it exists
        env_file = self.root_dir / ".env"
        if env_file.exists():
            shutil.copy2(env_file, backup_path / ".env")
            logging.info(f"Backed up .env file to {backup_path}")

        # Backup database
        db_backup = self.db_merger.create_backup()
        if db_backup.exists():
            shutil.copy2(db_backup, backup_path / db_backup.name)
            logging.info(f"Backed up database to {backup_path}")

        # Backup keyword monitor config if it exists
        keyword_config = self.root_dir / "app/config/keyword_monitor.json"
        if keyword_config.exists():
            backup_config_dir = backup_path / "app/config"
            backup_config_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(keyword_config, backup_config_dir / "keyword_monitor.json")
            logging.info(f"Backed up keyword monitor config to {backup_path}")

        return backup_path

    def git_pull(self) -> bool:
        """Pull latest changes from git"""
        try:
            # Stash any local changes
            subprocess.run(["git", "stash"], check=True)
            logging.info("Stashed local changes")

            # Pull latest changes
            result = subprocess.run(
                ["git", "pull"], 
                capture_output=True, 
                text=True, 
                check=True
            )
            logging.info(f"Git pull output: {result.stdout}")

            # Pop stashed changes
            subprocess.run(["git", "stash", "pop"], check=False)
            return True

        except subprocess.CalledProcessError as e:
            logging.error(f"Git operation failed: {e.stderr}")
            return False

    def restore_backup(self, backup_path: Path) -> None:
        """Restore files from backup"""
        try:
            # Restore .env
            env_backup = backup_path / ".env"
            if env_backup.exists():
                shutil.copy2(env_backup, self.root_dir / ".env")
                logging.info("Restored .env file")

            # Restore keyword monitor config
            keyword_config_backup = backup_path / "app/config/keyword_monitor.json"
            if keyword_config_backup.exists():
                config_dir = self.root_dir / "app/config"
                config_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(
                    keyword_config_backup, 
                    config_dir / "keyword_monitor.json"
                )
                logging.info("Restored keyword monitor config")

            # Restore database
            db_backup = next(backup_path.glob("backup_*.db"))
            if db_backup.exists():
                shutil.copy2(
                    db_backup, 
                    self.db_merger.db_path
                )
                logging.info("Restored database from backup")

        except Exception as e:
            logging.error(f"Error restoring backup: {e}")
            raise

    def update(self) -> bool:
        """Run the complete update process"""
        try:
            # Create backup
            logging.info("Starting update process...")
            backup_path = self.create_backup()
            logging.info("Backup created successfully")

            # Pull latest changes
            if not self.git_pull():
                logging.error("Failed to pull latest changes")
                self.restore_backup(backup_path)
                return False

            # Check if there's a new database to merge
            new_db = self.root_dir / "new_research.db"
            if new_db.exists():
                try:
                    self.db_merger.merge_databases(new_db)
                    logging.info("Database merged successfully")
                except Exception as e:
                    logging.error(f"Database merge failed: {e}")
                    self.restore_backup(backup_path)
                    return False

            logging.info("Update completed successfully")
            return True

        except Exception as e:
            logging.error(f"Update failed: {e}")
            return False

def main():
    updater = AppUpdater()
    success = updater.update()
    
    if success:
        logging.info("Application updated successfully!")
    else:
        logging.error("Update failed - check logs for details")

if __name__ == "__main__":
    main() 