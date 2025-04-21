import sqlite3
import logging
from datetime import datetime
import argparse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DataMigrator:
    def __init__(self, source_db_path: str, target_db_path: str):
        """
        Initialize the data migrator.
        
        Args:
            source_db_path (str): Path to the source database file
            target_db_path (str): Path to the target database file
        """
        self.source_db_path = source_db_path
        self.target_db_path = target_db_path

    def _connect_db(self, db_path: str) -> sqlite3.Connection:
        """Connect to a database and return the connection."""
        return sqlite3.connect(db_path)

    def _get_table_data(self, conn: sqlite3.Connection, table: str) -> list:
        """Get all data from a table and return as a list of dictionaries."""
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM {table}")
        columns = [description[0] for description in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def _insert_articles(self, source_conn: sqlite3.Connection, target_conn: sqlite3.Connection) -> None:
        """Migrate articles and their associated data."""
        try:
            logger.info("Migrating articles...")
            
            # Get articles from source
            articles = self._get_table_data(source_conn, "articles")
            raw_articles = self._get_table_data(source_conn, "raw_articles")
            
            target_cursor = target_conn.cursor()
            
            # Insert articles
            for article in articles:
                try:
                    target_cursor.execute("""
                        INSERT OR IGNORE INTO articles (
                            uri, title, news_source, publication_date, submission_date,
                            summary, category, future_signal, future_signal_explanation,
                            sentiment, sentiment_explanation, time_to_impact,
                            time_to_impact_explanation, tags, driver_type,
                            driver_type_explanation, topic, analyzed
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        article['uri'], article['title'], article['news_source'],
                        article['publication_date'], article['submission_date'],
                        article['summary'], article['category'], article['future_signal'],
                        article['future_signal_explanation'], article['sentiment'],
                        article['sentiment_explanation'], article['time_to_impact'],
                        article['time_to_impact_explanation'], article['tags'],
                        article['driver_type'], article['driver_type_explanation'],
                        article['topic'], article['analyzed']
                    ))
                except Exception as e:
                    logger.error(f"Error inserting article {article['uri']}: {str(e)}")
            
            # Insert raw articles
            for raw_article in raw_articles:
                try:
                    target_cursor.execute("""
                        INSERT OR IGNORE INTO raw_articles (
                            uri, raw_markdown, submission_date, last_updated, topic
                        ) VALUES (?, ?, ?, ?, ?)
                    """, (
                        raw_article['uri'], raw_article['raw_markdown'],
                        raw_article['submission_date'], raw_article['last_updated'],
                        raw_article['topic']
                    ))
                except Exception as e:
                    logger.error(f"Error inserting raw article {raw_article['uri']}: {str(e)}")
            
            target_conn.commit()
            logger.info(f"Migrated {len(articles)} articles and {len(raw_articles)} raw articles")
            
        except Exception as e:
            logger.error(f"Error migrating articles: {str(e)}")
            raise

    def _insert_keyword_data(self, source_conn: sqlite3.Connection, target_conn: sqlite3.Connection) -> None:
        """Migrate keyword groups, monitored keywords, alerts, and matches."""
        try:
            logger.info("Migrating keyword data...")
            
            # Get data from source
            keyword_groups = self._get_table_data(source_conn, "keyword_groups")
            monitored_keywords = self._get_table_data(source_conn, "monitored_keywords")
            keyword_alerts = self._get_table_data(source_conn, "keyword_alerts")
            keyword_article_matches = self._get_table_data(source_conn, "keyword_article_matches")
            
            target_cursor = target_conn.cursor()
            
            # Insert keyword groups
            for group in keyword_groups:
                try:
                    target_cursor.execute("""
                        INSERT OR IGNORE INTO keyword_groups (
                            id, name, topic, created_at
                        ) VALUES (?, ?, ?, ?)
                    """, (
                        group['id'], group['name'], group['topic'],
                        group['created_at']
                    ))
                except Exception as e:
                    logger.error(f"Error inserting keyword group {group['id']}: {str(e)}")
            
            # Insert monitored keywords
            for keyword in monitored_keywords:
                try:
                    target_cursor.execute("""
                        INSERT OR IGNORE INTO monitored_keywords (
                            id, group_id, keyword, created_at, last_checked
                        ) VALUES (?, ?, ?, ?, ?)
                    """, (
                        keyword['id'], keyword['group_id'], keyword['keyword'],
                        keyword['created_at'], keyword['last_checked']
                    ))
                except Exception as e:
                    logger.error(f"Error inserting monitored keyword {keyword['id']}: {str(e)}")
            
            # Insert keyword alerts
            for alert in keyword_alerts:
                try:
                    target_cursor.execute("""
                        INSERT OR IGNORE INTO keyword_alerts (
                            id, keyword_id, article_uri, detected_at, is_read
                        ) VALUES (?, ?, ?, ?, ?)
                    """, (
                        alert['id'], alert['keyword_id'], alert['article_uri'],
                        alert['detected_at'], alert['is_read']
                    ))
                except Exception as e:
                    logger.error(f"Error inserting keyword alert {alert['id']}: {str(e)}")
            
            # Insert keyword article matches
            for match in keyword_article_matches:
                try:
                    target_cursor.execute("""
                        INSERT OR IGNORE INTO keyword_article_matches (
                            id, article_uri, keyword_ids, group_id, detected_at, is_read
                        ) VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        match['id'], match['article_uri'], match['keyword_ids'],
                        match['group_id'], match['detected_at'], match['is_read']
                    ))
                except Exception as e:
                    logger.error(f"Error inserting keyword article match {match['id']}: {str(e)}")
            
            target_conn.commit()
            logger.info(f"Migrated {len(keyword_groups)} keyword groups, {len(monitored_keywords)} monitored keywords, "
                       f"{len(keyword_alerts)} alerts, and {len(keyword_article_matches)} article matches")
            
        except Exception as e:
            logger.error(f"Error migrating keyword data: {str(e)}")
            raise

    def migrate_data(self) -> None:
        """Migrate all data from source to target database."""
        try:
            logger.info(f"Starting data migration from {self.source_db_path} to {self.target_db_path}")
            
            source_conn = self._connect_db(self.source_db_path)
            target_conn = self._connect_db(self.target_db_path)
            
            # Enable foreign keys in target database
            target_conn.execute("PRAGMA foreign_keys = ON")
            
            # Migrate data
            self._insert_articles(source_conn, target_conn)
            self._insert_keyword_data(source_conn, target_conn)
            
            source_conn.close()
            target_conn.close()
            
            logger.info("Data migration completed successfully")
            
        except Exception as e:
            logger.error(f"Error during data migration: {str(e)}")
            raise

def main():
    """Main function to run the data migration."""
    parser = argparse.ArgumentParser(description='Migrate data from one database to another.')
    parser.add_argument('--source-db', type=str, required=True, help='Path to the source database file')
    parser.add_argument('--target-db', type=str, required=True, help='Path to the target database file')
    args = parser.parse_args()
    
    migrator = DataMigrator(args.source_db, args.target_db)
    migrator.migrate_data()

if __name__ == "__main__":
    main() 