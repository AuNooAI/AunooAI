import sqlite3
import shutil
import os
from datetime import datetime
import logging
from pathlib import Path
from typing import Optional, List, Tuple

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class DatabaseMerger:
    def __init__(self):
        # Use the correct database directory structure
        self.db_dir = Path("app/data")
        self.backup_dir = self.db_dir / "backups"
        self.backup_dir.mkdir(exist_ok=True)
        
        # Get active database from config
        self.db_path = self._get_active_database()

    def _get_active_database(self) -> Path:
        # Get the database path from the Database class
        from app.database import Database
        db_name = Database.get_active_database()
        return self.db_dir / db_name

    def create_backup(self) -> Path:
        """Create a backup of the current database"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.backup_dir / f"backup_{timestamp}.db"
        
        if self.db_path.exists():
            shutil.copy2(self.db_path, backup_path)
            logging.info(f"Created backup at {backup_path}")
            return backup_path
        
        logging.warning("No existing database found to backup")
        return backup_path

    def merge_databases(self, new_db_path: Path) -> None:
        """Merge the new database with existing data"""
        if not self.db_path.exists():
            logging.error("No existing database found.")
            return

        backup_path = self.create_backup()

        try:
            # Connect to both databases
            old_conn = sqlite3.connect(self.db_path)
            new_conn = sqlite3.connect(new_db_path)
            
            # First copy the new database over the old one to get latest schema
            old_conn.close()
            shutil.copy2(new_db_path, self.db_path)
            
            # Reconnect to the updated database
            old_conn = sqlite3.connect(self.db_path)
            
            # Now merge articles from backup into the new schema
            self._merge_articles_from_backup(backup_path, old_conn)
            
            old_conn.commit()
            logging.info("Database merge completed successfully")

        except Exception as e:
            logging.error(f"Error during merge: {e}")
            # Restore from backup if something went wrong
            shutil.copy2(backup_path, self.db_path)
            logging.info("Restored from backup due to merge error")
            raise

        finally:
            old_conn.close()
            new_conn.close()

    def _merge_articles_from_backup(self, backup_path: Path, current_conn: sqlite3.Connection) -> None:
        """Merge articles from backup into current database"""
        try:
            backup_conn = sqlite3.connect(backup_path)
            cursor = backup_conn.cursor()
            current_cursor = current_conn.cursor()
            
            # Merge articles
            logging.info("Merging articles from backup...")
            
            # Get existing articles in current db
            current_cursor.execute("SELECT uri FROM articles")
            existing_uris = {row[0] for row in current_cursor.fetchall()}
            
            # Get articles from backup
            cursor.execute("SELECT * FROM articles")
            articles = cursor.fetchall()
            columns = [description[0] for description in cursor.description]
            columns_str = ", ".join(columns)
            
            # Insert articles from backup that don't exist in current
            placeholders = ",".join(["?" for _ in columns])
            added_count = 0
            for article in articles:
                uri = article[columns.index('uri')]
                if uri not in existing_uris:
                    current_cursor.execute(
                        f"INSERT INTO articles ({columns_str}) VALUES ({placeholders})",
                        article
                    )
                    added_count += 1
            
            logging.info(f"Added {added_count} articles from backup")
            
            # Merge raw_articles
            logging.info("Merging raw_articles from backup...")
            
            # Get existing raw_articles in current db
            current_cursor.execute("SELECT uri FROM raw_articles")
            existing_raw_uris = {row[0] for row in current_cursor.fetchall()}
            
            # Get raw_articles from backup
            cursor.execute("SELECT * FROM raw_articles")
            raw_articles = cursor.fetchall()
            raw_columns = [description[0] for description in cursor.description]
            raw_columns_str = ", ".join(raw_columns)
            
            # Insert raw_articles from backup that don't exist in current
            raw_placeholders = ",".join(["?" for _ in raw_columns])
            added_raw_count = 0
            for article in raw_articles:
                uri = article[raw_columns.index('uri')]
                if uri not in existing_raw_uris:
                    current_cursor.execute(
                        f"INSERT INTO raw_articles ({raw_columns_str}) VALUES ({raw_placeholders})",
                        article
                    )
                    added_raw_count += 1
            
            logging.info(f"Added {added_raw_count} raw articles from backup")
            
            current_conn.commit()
            
        except Exception as e:
            logging.error(f"Error merging from backup: {e}")
            raise
        finally:
            backup_conn.close()

    def _copy_articles(self, old_conn: sqlite3.Connection, new_conn: sqlite3.Connection) -> None:
        try:
            cursor = old_conn.cursor()
            new_cursor = new_conn.cursor()
            
            # Get existing articles from new database
            new_cursor.execute("SELECT uri FROM articles")
            existing_uris = {row[0] for row in new_cursor.fetchall()}
            
            # Get articles from old database
            cursor.execute("SELECT * FROM articles")
            articles = cursor.fetchall()
            columns = [description[0] for description in cursor.description]
            columns_str = ", ".join(columns)
            
            if not articles:
                logging.info("No articles to copy from old database")
                return
            
            # Copy articles to new database, preserving existing ones
            placeholders = ",".join(["?" for _ in columns])
            for article in articles:
                uri = article[columns.index('uri')]
                if uri not in existing_uris:
                    new_cursor.execute(
                        f"INSERT INTO articles ({columns_str}) VALUES ({placeholders})",
                        article
                    )
                    logging.info(f"Copied article: {uri}")
                else:
                    logging.info(f"Skipping existing article: {uri}")
            
            new_conn.commit()
            
        except Exception as e:
            logging.error(f"Error copying articles: {e}")
            raise

    def _copy_raw_articles(self, old_conn: sqlite3.Connection, new_conn: sqlite3.Connection) -> None:
        try:
            cursor = old_conn.cursor()
            new_cursor = new_conn.cursor()
            
            # Get existing raw articles from new database
            new_cursor.execute("SELECT uri FROM raw_articles")
            existing_uris = {row[0] for row in new_cursor.fetchall()}
            
            # Get raw articles from old database
            cursor.execute("SELECT * FROM raw_articles")
            raw_articles = cursor.fetchall()
            
            if not raw_articles:
                logging.info("No raw articles to copy from old database")
                return
            
            # Get column names
            columns = [description[0] for description in cursor.description]
            columns_str = ", ".join(columns)
            
            # Copy raw articles to new database, preserving existing ones
            placeholders = ",".join(["?" for _ in columns])
            for article in raw_articles:
                uri = article[columns.index('uri')]
                if uri not in existing_uris:
                    new_cursor.execute(
                        f"INSERT INTO raw_articles ({columns_str}) VALUES ({placeholders})",
                        article
                    )
                    logging.info(f"Copied raw article: {uri}")
                else:
                    logging.info(f"Skipping existing raw article: {uri}")
            
            new_conn.commit()
            
        except Exception as e:
            logging.error(f"Error copying raw articles: {e}")
            raise

    def _merge_tags(self, existing_conn: sqlite3.Connection, new_conn: sqlite3.Connection) -> None:
        try:
            cursor = new_conn.cursor()
            existing_cursor = existing_conn.cursor()
            
            # Get existing tags
            existing_cursor.execute("SELECT name FROM tags")
            existing_tags = {row[0] for row in existing_cursor.fetchall()}
            
            # Insert new tags
            cursor.execute("SELECT name FROM tags")
            for row in cursor.fetchall():
                tag_name = row[0]
                if tag_name not in existing_tags:
                    existing_cursor.execute("INSERT INTO tags (name) VALUES (?)", (tag_name,))
                    logging.info(f"Inserted new tag: {tag_name}")
            
            existing_conn.commit()
            
        except Exception as e:
            logging.error(f"Error merging tags: {e}")
            raise

    def _preserve_user_data(self, existing_conn: sqlite3.Connection, new_conn: sqlite3.Connection) -> None:
        # List of tables that should not be merged/overwritten
        preserved_tables = {'users', 'migrations', 'article_annotations'}
        logging.info(f"Preserving user data in tables: {preserved_tables}")

def main():
    merger = DatabaseMerger()
    
    # Create backup of current database
    backup_path = merger.create_backup()
    
    # Check if there's a new database to merge
    new_db_path = Path("new_research.db")
    if new_db_path.exists():
        try:
            merger.merge_databases(new_db_path)
            logging.info("Database merge completed successfully")
        except Exception as e:
            logging.error(f"Failed to merge databases: {e}")
            return
    else:
        logging.info("No new database found to merge")

if __name__ == "__main__":
    main() 