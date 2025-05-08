# flake8: noqa
import sqlite3
import os
import json
from app.config.settings import DATABASE_DIR
from datetime import datetime
from typing import List, Tuple, Optional, Dict
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
import logging
from fastapi import HTTPException, Query
from app.security.auth import get_password_hash
import shutil
from fastapi.responses import FileResponse
from pathlib import Path
from urllib.parse import unquote_plus
import threading

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Database instance for dependency injection
_db_instance = None

def get_database_instance():
    global _db_instance
    if _db_instance is None:
        _db_instance = Database()
    return _db_instance

class Database:
    _connections = {}
    
    @staticmethod
    def get_active_database():
        config_path = os.path.join(DATABASE_DIR, 'config.json')
        with open(config_path, 'r') as f:
            config = json.load(f)
        return config.get('active_database', 'fnaapp.db')

    def __init__(self, db_name=None):
        if db_name is None:
            db_name = self.get_active_database()
        self.db_path = os.path.join(DATABASE_DIR, db_name)
        self.init_db()

    def get_connection(self):
        """Get a thread-local database connection"""
        thread_id = threading.get_ident()
        
        if thread_id not in self._connections:
            self._connections[thread_id] = sqlite3.connect(self.db_path)
            # Enable foreign key support
            self._connections[thread_id].execute("PRAGMA foreign_keys = ON")
            
        return self._connections[thread_id]

    def close_connections(self):
        """Close all database connections"""
        for conn in self._connections.values():
            try:
                conn.close()
            except Exception:
                pass
        self._connections.clear()

    def __del__(self):
        """Cleanup connections when the object is destroyed"""
        self.close_connections()

    def init_db(self):
        """Initialize the database and create necessary tables if they don't exist."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Enable foreign keys
            cursor.execute("PRAGMA foreign_keys = ON")
            
            # Create users table with proper schema
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    force_password_change BOOLEAN DEFAULT 0,
                    completed_onboarding BOOLEAN DEFAULT 0
                )
            """)
            
            # Create articles table with URI as primary key
            self.create_articles_table()
            
            # Create ontology tables (building_blocks, scenarios, scenario_blocks)
            self.create_ontology_tables()
            
            # Run migrations to ensure schema is up to date
            self.migrate_db()
            
            conn.commit()

    def create_articles_table(self):
        """Create the articles and related tables."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Create articles table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS articles (
                    uri TEXT PRIMARY KEY,
                    title TEXT,
                    news_source TEXT,
                    publication_date TEXT,
                    submission_date TEXT DEFAULT CURRENT_TIMESTAMP,
                    summary TEXT,
                    category TEXT,
                    future_signal TEXT,
                    future_signal_explanation TEXT,
                    sentiment TEXT,
                    sentiment_explanation TEXT,
                    time_to_impact TEXT,
                    time_to_impact_explanation TEXT,
                    tags TEXT,
                    driver_type TEXT,
                    driver_type_explanation TEXT,
                    topic TEXT,
                    analyzed BOOLEAN DEFAULT FALSE
                )
            """)
            
            # Create raw_articles table for storing original content
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS raw_articles (
                    uri TEXT PRIMARY KEY,
                    raw_markdown TEXT,
                    submission_date TEXT DEFAULT CURRENT_TIMESTAMP,
                    last_updated TEXT,
                    topic TEXT,
                    FOREIGN KEY (uri) REFERENCES articles(uri) ON DELETE CASCADE
                )
            """)
            
            # Create unique index on URI
            cursor.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_articles_uri 
                ON articles(uri)
            """)
            
            # Create keyword alerts table with proper foreign key constraints
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS keyword_alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    keyword_id INTEGER NOT NULL,
                    article_uri TEXT NOT NULL,
                    detected_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    is_read INTEGER DEFAULT 0,
                    FOREIGN KEY (keyword_id) REFERENCES monitored_keywords(id) ON DELETE CASCADE,
                    FOREIGN KEY (article_uri) REFERENCES articles(uri) ON DELETE CASCADE,
                    UNIQUE(keyword_id, article_uri)
                )
            """)
            
            # Ensure podcasts table exists (schema enforced by migrations)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS podcasts (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    status TEXT DEFAULT 'processing',
                    audio_url TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    error TEXT,
                    transcript TEXT,
                    metadata TEXT
                )
            """)
            
            conn.commit()

    def migrate_db(self):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # First ensure migrations table exists
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS migrations (
                        id INTEGER PRIMARY KEY,
                        name TEXT UNIQUE,
                        applied_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.commit()
                
                # Get applied migrations
                cursor.execute("SELECT name FROM migrations")
                applied = {row[0] for row in cursor.fetchall()}
                
                # Define migrations
                migrations = [
                    ("ensure_users_table_schema", self._ensure_users_table_schema),
                    ("ensure_podcasts_table_schema", self._ensure_podcasts_table_schema),
                    ("ensure_settings_podcasts_table", self._ensure_settings_podcasts_table),
                    ("add_metadata_column_to_podcasts", self._add_metadata_column_to_podcasts)
                ]
                
                # Apply missing migrations
                for name, migrate_func in migrations:
                    if name not in applied:
                        try:
                            logger.info(f"Applying migration: {name}")
                            migrate_func(cursor)
                            
                            # Record successful migration
                            cursor.execute(
                                "INSERT INTO migrations (name) VALUES (?)",
                                (name,)
                            )
                            conn.commit()
                            logger.info(f"Migration {name} applied successfully")
                        except sqlite3.IntegrityError as e:
                            logger.warning(f"Integrity error during migration {name}: {str(e)}")
                            # Continue with next migration despite the error
                            continue
                        except Exception as e:
                            logger.error(f"Error applying migration {name}: {str(e)}")
                            # Continue with next migration despite the error
                            continue
                
                return True
        except Exception as e:
            logger.error(f"Error during migration: {str(e)}")
            raise
            
    def _ensure_users_table_schema(self, cursor):
        """Ensure users table has the correct schema with password_hash column."""
        # Check if users table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        if cursor.fetchone():
            # Check if password_hash column exists
            cursor.execute("PRAGMA table_info(users)")
            columns = {row[1] for row in cursor.fetchall()}
            
            if 'password_hash' not in columns:
                logger.info("Adding password_hash column to users table")
                # Create a temporary table with the correct schema
                cursor.execute("""
                    CREATE TABLE users_temp (
                        username TEXT PRIMARY KEY,
                        password_hash TEXT NOT NULL,
                        force_password_change BOOLEAN DEFAULT 0,
                        completed_onboarding BOOLEAN DEFAULT 0
                    )
                """)
                
                # Copy data from old table to new table
                cursor.execute("""
                    INSERT INTO users_temp (username, force_password_change, completed_onboarding)
                    SELECT username, force_password_change, completed_onboarding FROM users
                """)
                
                # Drop the old table
                cursor.execute("DROP TABLE users")
                
                # Rename the new table to the original name
                cursor.execute("ALTER TABLE users_temp RENAME TO users")
        else:
            # Create the users table if it doesn't exist
            cursor.execute("""
                CREATE TABLE users (
                    username TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    force_password_change BOOLEAN DEFAULT 0,
                    completed_onboarding BOOLEAN DEFAULT 0
                )
            """)

    def _ensure_podcasts_table_schema(self, cursor):
        """Ensure podcasts table has the correct schema."""
        # Check if podcasts table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='podcasts'")
        if cursor.fetchone():
            # Check if all required columns exist
            cursor.execute("PRAGMA table_info(podcasts)")
            columns = {row[1] for row in cursor.fetchall()}
            
            required_columns = {
                'id', 'title', 'status', 'audio_url', 'created_at', 
                'completed_at', 'error', 'transcript', 'metadata'
            }
            
            missing = required_columns - columns
            for col in missing:
                logger.info(f"Adding missing column '{col}' to podcasts table")
                col_def = "TEXT"
                if col in {"created_at", "completed_at"}:
                    col_def = "TIMESTAMP"
                cursor.execute(f"ALTER TABLE podcasts ADD COLUMN {col} {col_def}")
        else:
            # Create podcasts table if it doesn't exist
            cursor.execute("""
                CREATE TABLE podcasts (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    status TEXT DEFAULT 'processing',
                    audio_url TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    error TEXT,
                    transcript TEXT,
                    metadata TEXT
                )
            """)

    def _ensure_settings_podcasts_table(self, cursor):
        """Ensure settings_podcasts key‑value table exists."""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings_podcasts (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

    def _add_metadata_column_to_podcasts(self, cursor):
        """Add metadata column to podcasts table."""
        # Check if podcasts table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='podcasts'")
        if cursor.fetchone():
            # Check if metadata column exists
            cursor.execute("PRAGMA table_info(podcasts)")
            columns = {row[1] for row in cursor.fetchall()}
            
            if 'metadata' not in columns:
                logger.info("Adding metadata column to podcasts table")
                cursor.execute("ALTER TABLE podcasts ADD COLUMN metadata TEXT")
        else:
            # Create podcasts table if it doesn't exist
            cursor.execute("""
                CREATE TABLE podcasts (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    status TEXT DEFAULT 'processing',
                    audio_url TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    error TEXT,
                    transcript TEXT,
                    metadata TEXT
                )
            """)

    # ------------------------------------------------------------------
    # Podcast settings helpers
    # ------------------------------------------------------------------

    def get_podcast_setting(self, key: str, default=None):
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT value FROM settings_podcasts WHERE key = ?", (key,))
                row = cur.fetchone()
                return row[0] if row else default
        except Exception as e:
            logger.error(f"Error fetching podcast setting {key}: {e}")
            return default

    def set_podcast_setting(self, key: str, value: str):
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                cur.execute("REPLACE INTO settings_podcasts (key, value) VALUES (?, ?)", (key, value))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error saving podcast setting {key}: {e}")
            return False

    def create_database(self, name):
        # Sanitize the database name
        name = name.strip()
        if not name:
            raise ValueError("Database name cannot be empty")
        
        # Remove .db if it exists, then add it back
        if name.endswith('.db'):
            name = name[:-3]
        
        # Ensure name is not just '.db'
        if not name:
            raise ValueError("Invalid database name")
        
        db_name = f"{name}.db"
        new_db_path = os.path.join(DATABASE_DIR, db_name)
        
        # Check if database already exists
        if os.path.exists(new_db_path):
            raise ValueError(f"Database {name} already exists")
        
        # Create new database instance and initialize it
        new_db = Database(db_name)
        new_db.init_db()
        
        # Copy users from current database to new database
        try:
            with self.get_connection() as old_conn:
                old_cursor = old_conn.cursor()
                old_cursor.execute("SELECT username, password, force_password_change FROM users")
                users = old_cursor.fetchall()
                
                if users:
                    with new_db.get_connection() as new_conn:
                        new_cursor = new_conn.cursor()
                        new_cursor.executemany(
                            "INSERT INTO users (username, password, force_password_change) VALUES (?, ?, ?)",
                            users
                        )
                        new_conn.commit()
        except Exception as e:
            logger.error(f"Error copying users to new database: {str(e)}")
        
        return {"id": db_name, "name": name}  # Return both full name and display name

    def delete_database(self, name):
        if not name.endswith('.db'):
            name += '.db'
        db_path = os.path.join(DATABASE_DIR, name)
        if os.path.exists(db_path):
            os.remove(db_path)
            return {"message": f"Database {name} deleted successfully"}
        else:
            return {"message": f"Database {name} not found"}

    def set_active_database(self, name):
        """Set the active database and ensure it's properly initialized"""
        try:
            if not name.endswith('.db'):
                name = f"{name}.db"
            
            db_path = os.path.join(DATABASE_DIR, name)
            if not os.path.exists(db_path):
                raise ValueError(f"Database {name} does not exist")
            
            # Update config
            config_path = os.path.join(DATABASE_DIR, 'config.json')
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            config['active_database'] = name
            
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=4)
            
            # Close existing per-thread connections so that a new database file
            # is opened on the next `get_connection()` call.
            self.close_connections()
            
            # Initialize the new database
            self.db_path = db_path
            
            try:
                self.init_db()
            except sqlite3.IntegrityError as e:
                logger.warning(f"Integrity error during database initialization: {str(e)}")
                # Continue despite the integrity error - tables may already exist
                pass
            except Exception as e:
                logger.error(f"Error initializing database: {str(e)}")
                raise
            
            return {"message": f"Active database set to {name}"}
            
        except Exception as e:
            logger.error(f"Error setting active database: {str(e)}")
            raise

    def get_databases(self):
        databases = []
        for file in os.listdir(DATABASE_DIR):
            if file.endswith('.db'):
                # Remove .db extension for display
                display_name = file[:-3] if file.endswith('.db') else file
                databases.append({
                    "id": file,  # Keep full name with .db for operations
                    "name": display_name  # Display name without .db
                })
        return databases

    def get_config_item(self, item_name):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT content FROM config WHERE name = ?", (item_name,))
            result = cursor.fetchone()
            return result[0] if result else None

    def save_config_item(self, item_name, content):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO config (name, content) VALUES (?, ?)", (item_name, content))
            conn.commit()

    def get_recent_articles(self, limit=10):
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM articles
                ORDER BY COALESCE(submission_date, publication_date) DESC, rowid DESC
                LIMIT ?
            """, (limit,))
            articles = [dict(row) for row in cursor.fetchall()]
            
            # Convert tags string back to list
            for article in articles:
                if article['tags']:
                    article['tags'] = article['tags'].split(',')
                else:
                    article['tags'] = []
            
            return articles

    def update_or_create_article(self, article_data: dict) -> bool:
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Check if article exists
                cursor.execute("""
                    SELECT 1 FROM articles WHERE uri = ?
                """, (article_data['uri'],))
                
                exists = cursor.fetchone() is not None
                
                if exists:
                    # Update existing article
                    cursor.execute("""
                        UPDATE articles 
                        SET title = ?, news_source = ?, summary = ?, 
                            sentiment = ?, time_to_impact = ?, category = ?,
                            future_signal = ?, future_signal_explanation = ?,
                            publication_date = ?, topic = ?, analyzed = TRUE,
                            sentiment_explanation = ?, time_to_impact_explanation = ?,
                            tags = ?, driver_type = ?, driver_type_explanation = ?
                        WHERE uri = ?
                    """, (
                        article_data['title'], article_data['news_source'],
                        article_data['summary'], article_data['sentiment'],
                        article_data['time_to_impact'], article_data['category'],
                        article_data['future_signal'], article_data['future_signal_explanation'],
                        article_data['publication_date'], article_data['topic'],
                        article_data['sentiment_explanation'], article_data['time_to_impact_explanation'],
                        article_data['tags'], article_data['driver_type'],
                        article_data['driver_type_explanation'], article_data['uri']
                    ))
                else:
                    # Insert new article
                    cursor.execute("""
                        INSERT INTO articles (
                            uri, title, news_source, summary, sentiment,
                            time_to_impact, category, future_signal,
                            future_signal_explanation, publication_date, topic,
                            sentiment_explanation, time_to_impact_explanation,
                            tags, driver_type, driver_type_explanation, analyzed
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, TRUE)
                    """, (
                        article_data['uri'], article_data['title'],
                        article_data['news_source'], article_data['summary'],
                        article_data['sentiment'], article_data['time_to_impact'],
                        article_data['category'], article_data['future_signal'],
                        article_data['future_signal_explanation'],
                        article_data['publication_date'], article_data['topic'],
                        article_data['sentiment_explanation'],
                        article_data['time_to_impact_explanation'],
                        article_data['tags'], article_data['driver_type'],
                        article_data['driver_type_explanation']
                    ))
                
                return True
                
        except Exception as e:
            logger.error(f"Error saving article: {str(e)}")
            return False

    def get_article(self, uri):
        logger.debug(f"Fetching article with URI: {uri}")
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM articles WHERE uri = ?", (uri,))
            article = cursor.fetchone()
            
            if article:
                article_dict = dict(article)
                if article_dict['tags']:
                    article_dict['tags'] = article_dict['tags'].split(',')
                else:
                    article_dict['tags'] = []
                logger.debug(f"Article found: {article_dict['title']}")
                return article_dict
            else:
                logger.debug("Article not found")
                return None
            
    async def save_article(self, article_data):
        logger.info(f"Database.save_article called with data: {json.dumps(article_data, indent=2)}")
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            try:
                # Standardize submission_date format
                if 'submission_date' not in article_data:
                    article_data['submission_date'] = datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%f')
                else:
                    try:
                        date_obj = datetime.fromisoformat(article_data['submission_date'].replace('Z', '+00:00'))
                        article_data['submission_date'] = date_obj.strftime('%Y-%m-%dT%H:%M:%S.%f')
                    except (ValueError, AttributeError):
                        logger.warning(f"Invalid submission_date format: {article_data['submission_date']}")
                        article_data['submission_date'] = datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%f')
                
                # Also standardize publication_date format 
                if 'publication_date' in article_data and article_data['publication_date']:
                    try:
                        # Check if it's date-only format (like 2025-04-06)
                        if 'T' not in article_data['publication_date'] and len(article_data['publication_date']) <= 10:
                            # Keep date-only format as is
                            pass
                        else:
                            # If it has time component, standardize it
                            date_obj = datetime.fromisoformat(article_data['publication_date'].replace('Z', '+00:00'))
                            article_data['publication_date'] = date_obj.strftime('%Y-%m-%dT%H:%M:%S.%f')
                    except (ValueError, AttributeError):
                        logger.warning(f"Invalid publication_date format: {article_data['publication_date']}")
                        # Keep as is rather than replacing, as this might be an intentional date-only value
                elif 'publication_date' not in article_data or not article_data['publication_date']:
                    # Set a default value when publication_date is empty
                    article_data['publication_date'] = datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%f')
                    logger.warning(f"Empty publication_date detected, setting to now: {article_data['publication_date']}")
                
                # Convert tags list to string if necessary
                tags = article_data.get('tags', [])
                if isinstance(tags, list):
                    tags = ','.join(str(tag) for tag in tags)
                elif tags is None:
                    tags = ''
                
                # Check if article already exists
                cursor.execute("SELECT 1 FROM articles WHERE uri = ?", (article_data['uri'],))
                exists = cursor.fetchone() is not None
                
                if exists:
                    # Update existing article
                    query = """
                    UPDATE articles SET 
                        title = ?, news_source = ?, summary = ?, sentiment = ?,
                        time_to_impact = ?, category = ?, future_signal = ?,
                        future_signal_explanation = ?, publication_date = ?,
                        sentiment_explanation = ?, time_to_impact_explanation = ?,
                        tags = ?, driver_type = ?, driver_type_explanation = ?,
                        submission_date = ?, topic = ?
                    WHERE uri = ?
                    """
                    params = (
                        article_data['title'], article_data['news_source'],
                        article_data['summary'], article_data['sentiment'],
                        article_data['time_to_impact'], article_data['category'],
                        article_data['future_signal'], article_data['future_signal_explanation'],
                        article_data['publication_date'], article_data['sentiment_explanation'],
                        article_data['time_to_impact_explanation'], tags,
                        article_data['driver_type'], article_data['driver_type_explanation'],
                        article_data['submission_date'], article_data['topic'],
                        article_data['uri']
                    )
                else:
                    # Insert new article
                    query = """
                    INSERT INTO articles (
                        title, uri, news_source, summary, sentiment, time_to_impact,
                        category, future_signal, future_signal_explanation,
                        publication_date, sentiment_explanation, time_to_impact_explanation,
                        tags, driver_type, driver_type_explanation, submission_date, topic
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                    params = (
                        article_data['title'], article_data['uri'], article_data['news_source'],
                        article_data['summary'], article_data['sentiment'], article_data['time_to_impact'],
                        article_data['category'], article_data['future_signal'], article_data['future_signal_explanation'],
                        article_data['publication_date'], article_data['sentiment_explanation'],
                        article_data['time_to_impact_explanation'], tags,
                        article_data['driver_type'], article_data['driver_type_explanation'],
                        article_data['submission_date'], article_data['topic']
                    )
                
                cursor.execute(query, params)
                conn.commit()
                # After committing to the relational DB, index the article in
                # the vector store.  We swallow any errors so that a failure
                # in the secondary store does not break the primary flow.
                try:
                    from app.vector_store import upsert_article  # Local import to avoid circular deps

                    upsert_article({
                        **article_data,
                        # Provide the original *summary* as the document text
                        # if available.  Raw content will be attached by
                        # *Research* when present.
                    })
                except Exception as vector_exc:  # pragma: no cover
                    logger.warning(
                        "Vector indexing failed for article %s – %s",
                        article_data.get("uri"),
                        vector_exc,
                    )
                return {"message": "Article saved successfully"}
                
            except Exception as e:
                logger.error(f"Error saving article: {str(e)}")
                logger.error(f"Article data: {article_data}")
                conn.rollback()  # Rollback any changes on error
                raise HTTPException(
                    status_code=500,
                    detail=f"Error saving article: {str(e)}"
                ) from e

    def delete_article(self, uri):
        logger.info(f"Attempting to delete article with URI: {uri}")
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("DELETE FROM articles WHERE uri = ?", (uri,))
                conn.commit()
                deleted_count = cursor.rowcount
                logger.info(f"Deleted {deleted_count} article(s) with URI: {uri}")
                return deleted_count > 0
            except Exception as e:
                logger.error(f"Error deleting article: {e}", exc_info=True)
                return False

    def search_articles(
        self,
        topic: Optional[str] = None,
        category: Optional[List[str]] = None,
        future_signal: Optional[List[str]] = None,
        sentiment: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        keyword: Optional[str] = None,
        pub_date_start: Optional[str] = None,
        pub_date_end: Optional[str] = None,
        page: int = Query(1),
        per_page: int = Query(10),
        date_type: str = 'publication',  # Add date_type parameter with default
        date_field: str = None  # Add date_field parameter
    ) -> Tuple[List[Dict], int]:
        """Search articles with filters including topic."""
        query_conditions = []
        params = []

        # Use the appropriate date field based on date_type
        date_field = 'publication_date' if date_type == 'publication' else 'submission_date'

        # Add topic filter
        if topic:
            query_conditions.append("topic = ?")
            params.append(topic)

        if category:
            placeholders = ','.join(['?' for _ in category])
            query_conditions.append(f"category IN ({placeholders})")
            params.extend(category)

        if future_signal:
            placeholders = ','.join(['?' for _ in future_signal])
            query_conditions.append(f"future_signal IN ({placeholders})")
            params.extend(future_signal)

        if sentiment:
            placeholders = ','.join(['?' for _ in sentiment])
            query_conditions.append(f"sentiment IN ({placeholders})")
            params.extend(sentiment)

        if tags:
            tag_conditions = []
            for tag in tags:
                tag_conditions.append("tags LIKE ?")
                params.append(f"%{tag}%")
            if tag_conditions:
                query_conditions.append(f"({' OR '.join(tag_conditions)})")

        if keyword:
            keyword_conditions = [
                "title LIKE ?",
                "summary LIKE ?",
                "category LIKE ?",
                "future_signal LIKE ?",
                "sentiment LIKE ?",
                "tags LIKE ?"
            ]
            query_conditions.append(f"({' OR '.join(keyword_conditions)})")
            params.extend([f"%{keyword}%"] * 6)

        if pub_date_start:
            query_conditions.append(f"{date_field} >= ?")  # Use the selected date field
            params.append(pub_date_start)

        if pub_date_end:
            query_conditions.append(f"{date_field} <= ?")  # Use the selected date field
            params.append(pub_date_end)

        where_clause = " AND ".join(query_conditions) if query_conditions else "1=1"
        
        # Count total results
        count_query = f"SELECT COUNT(*) FROM articles WHERE {where_clause}"
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(count_query, params)
            total_count = cursor.fetchone()[0]

        # Get paginated results
        offset = (page - 1) * per_page
        query = f"""
            SELECT *
            FROM articles
            WHERE {where_clause}
            ORDER BY submission_date DESC
            LIMIT ? OFFSET ?
        """
        params.extend([per_page, offset])

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            articles = [dict(zip([col[0] for col in cursor.description], row)) for row in cursor.fetchall()]

        return articles, total_count

    def save_report(self, content: str) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO reports (content, created_at) VALUES (?, ?)",
                           (content, datetime.now().isoformat()))
            conn.commit()
            return cursor.lastrowid

    def get_articles_by_ids(self, article_ids):
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            placeholders = ','.join(['?' for _ in article_ids])
            query = f"SELECT * FROM articles WHERE uri IN ({placeholders})"
            
            cursor.execute(query, article_ids)
            articles = []
            for row in cursor.fetchall():
                article = dict(row)
                if article['tags']:
                    article['tags'] = article['tags'].split(',')
                else:
                    article['tags'] = []
                
                # If 'url' doesn't exist, use 'uri' as a fallback
                if 'url' not in article and 'uri' in article:
                    article['url'] = article['uri']
                
                articles.append(article)
            
            print(f"Fetched {len(articles)} articles from database")  # Add this line for debugging
            
            # Check for missing articles
            fetched_ids = set(article['uri'] for article in articles)
            missing_ids = set(article_ids) - fetched_ids
            if missing_ids:
                print(f"Warning: Could not fetch articles with IDs: {missing_ids}")
            
            return articles

    def get_all_articles(self):
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM articles")
            articles = []
            for row in cursor.fetchall():
                article = dict(row)
                # Handle potentially missing fields
                for field in ['tags', 'sentiment', 'category', 'future_signal', 'time_to_impact']:
                    if field not in article or article[field] is None:
                        article[field] = '' if field != 'tags' else []
                
                if article['tags'] and isinstance(article['tags'], str):
                    article['tags'] = article['tags'].split(',')
                
                articles.append(article)
            
            return articles

    def fetch_all(self, query, params=None):
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            return cursor.fetchall()

    def get_categories(self):
        query = "SELECT DISTINCT category FROM articles WHERE category IS NOT NULL AND category != '' ORDER BY category"
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            categories = [row[0] for row in cursor.fetchall()]
        return categories

    def get_database_info(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row[0] for row in cursor.fetchall()]
            
            # Get article count
            cursor.execute("SELECT COUNT(*) FROM articles;")
            article_count = cursor.fetchone()[0]
            
            # Get last entry date
            cursor.execute("SELECT MAX(submission_date) FROM articles;")
            last_entry = cursor.fetchone()[0]
            
            return {
                "tables": tables,
                "article_count": article_count,
                "last_entry": last_entry
            }

    def save_raw_article(self, uri, raw_markdown, topic):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            current_time = datetime.now().isoformat()
            
            # Check if the raw_articles table exists, create it if not
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='raw_articles'")
            if not cursor.fetchone():
                logger.info("Creating raw_articles table as it does not exist")
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS raw_articles (
                        uri TEXT PRIMARY KEY,
                        raw_markdown TEXT,
                        submission_date TEXT DEFAULT CURRENT_TIMESTAMP,
                        last_updated TEXT,
                        topic TEXT,
                        FOREIGN KEY (uri) REFERENCES articles(uri) ON DELETE CASCADE
                    )
                """)
                conn.commit()
            
            cursor.execute("SELECT * FROM raw_articles WHERE uri = ?", (uri,))
            existing_raw_article = cursor.fetchone()
            
            if existing_raw_article:
                update_query = """
                UPDATE raw_articles SET
                    raw_markdown = ?, last_updated = ?, topic = ?
                WHERE uri = ?
                """
                cursor.execute(update_query, (raw_markdown, current_time, topic, uri))
            else:
                insert_query = """
                INSERT INTO raw_articles (uri, raw_markdown, submission_date, last_updated, topic)
                VALUES (?, ?, ?, ?, ?)
                """
                cursor.execute(insert_query, (uri, raw_markdown, current_time, current_time, topic))
            
            conn.commit()
        
        return {"message": "Raw article saved successfully"}

    def get_raw_article(self, uri: str):
        """Retrieve a raw article from the database."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # First check if the raw_articles table exists
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='raw_articles'")
                if not cursor.fetchone():
                    logger.warning("raw_articles table does not exist yet")
                    return None
                
                cursor.execute("SELECT * FROM raw_articles WHERE uri = ?", (uri,))
                result = cursor.fetchone()
                if result:
                    return {
                        "uri": result[0],
                        "raw_markdown": result[1],
                        "submission_date": result[2],
                        "last_updated": result[3]
                    }
                return None
        except Exception as e:
            logger.error(f"Error retrieving raw article: {str(e)}")
            return None

    def get_topics(self):
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT topic FROM articles ORDER BY topic")
            return [{"id": row['topic'], "name": row['topic']} for row in cursor.fetchall()]

    def get_recent_articles_by_topic(self, topic_name, limit=10, start_date=None, end_date=None):
        logger.info(f"Database: Fetching {limit} recent articles for topic {topic_name} (date range: {start_date} to {end_date})")
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            query = """
                SELECT * FROM articles 
                WHERE topic = ?
                {}  
                ORDER BY COALESCE(submission_date, publication_date) DESC, rowid DESC
                LIMIT ?
            """
            
            params = [topic_name]
            date_conditions = []
            
            if start_date:
                date_conditions.append("AND COALESCE(submission_date, publication_date) >= ?")
                params.append(start_date)
            if end_date:
                date_conditions.append("AND COALESCE(submission_date, publication_date) <= ?")
                params.append(end_date)
                
            date_clause = " ".join(date_conditions)
            query = query.format(date_clause)
            params.append(limit)
            
            logger.debug(f"Executing query: {query} with params: {params}")
            cursor.execute(query, params)
            articles = [dict(row) for row in cursor.fetchall()]
            logger.info(f"Found {len(articles)} articles in database")
            
            # Convert tags string back to list
            for article in articles:
                if article['tags']:
                    article['tags'] = article['tags'].split(',')
                else:
                    article['tags'] = []
            
            return articles

    def get_article_count_by_topic(self, topic_name: str) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM articles WHERE topic = ?", (topic_name,))
            return cursor.fetchone()[0]

    def get_latest_article_date_by_topic(self, topic_name: str) -> Optional[str]:
        logger.debug(f"Getting latest article date for topic: {topic_name}")
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COALESCE(submission_date, publication_date) as article_date 
                FROM articles 
                WHERE topic = ? 
                ORDER BY article_date DESC 
                LIMIT 1
            """, (topic_name,))
            result = cursor.fetchone()
            logger.debug(f"Latest article date for topic {topic_name}: {result[0] if result else None}")
            return result[0] if result else None

    def delete_topic(self, topic_name: str) -> bool:
        """Delete a topic and all its associated data from the database."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Delete articles associated with the topic
                cursor.execute("DELETE FROM articles WHERE topic = ?", (topic_name,))
                
                # Delete raw articles associated with the topic
                cursor.execute("DELETE FROM raw_articles WHERE topic = ?", (topic_name,))
                
                # Delete any other topic-related data here if needed
                # For example:
                # cursor.execute("DELETE FROM topic_metadata WHERE topic = ?", (topic_name,))
                
                conn.commit()
                return True
                
        except Exception as e:
            logger.error(f"Error deleting topic {topic_name} from database: {str(e)}")
            return False

    def get_user(self, username: str):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # First check if the users table exists
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
                if not cursor.fetchone():
                    logger.error("Users table does not exist")
                    return None
                
                # Check if password_hash column exists
                cursor.execute("PRAGMA table_info(users)")
                columns = {row[1] for row in cursor.fetchall()}
                
                if 'password_hash' not in columns:
                    logger.error("password_hash column does not exist in users table")
                    # Try to fix the schema
                    self._ensure_users_table_schema(cursor)
                    conn.commit()
                    # Return None to indicate the user needs to be recreated
                    return None
                
                # Query the user with the correct schema
                cursor.execute("""
                    SELECT username, password_hash, force_password_change, completed_onboarding
                    FROM users WHERE username = ?
                """, (username,))
                user = cursor.fetchone()
                if user:
                    return {
                        "username": user[0],
                        "password": user[1],  # Keep the key as 'password' for compatibility
                        "force_password_change": bool(user[2]),
                        "completed_onboarding": bool(user[3])
                    }
                return None
        except Exception as e:
            logger.error(f"Error getting user: {str(e)}")
            return None

    def update_user_password(self, username: str, new_password: str) -> bool:
        """Update user password and set force_password_change to false."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                # Hash the new password
                hashed_password = get_password_hash(new_password)
                
                # Update password and force_password_change flag
                cursor.execute("""
                    UPDATE users 
                    SET password_hash = ?, force_password_change = 0 
                    WHERE username = ?
                """, (hashed_password, username))
                conn.commit()
                
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error updating user password: {str(e)}")
            return False

    def backup_database(self, backup_name: str = None) -> str:
        """Create a backup of the current database"""
        try:
            if not backup_name:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                backup_name = f"backup_{timestamp}.db"
            elif not backup_name.endswith('.db'):
                backup_name += '.db'

            # Use the correct backup directory
            backup_dir = Path("app/data/backups")
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup_path = backup_dir / backup_name
            
            logger.info(f"Creating backup at: {backup_path}")
            
            # Create backup
            shutil.copy2(self.db_path, backup_path)
            logger.info(f"Created backup at {backup_path}")
            
            return {"message": f"Database backed up to {backup_name}"}
        except Exception as e:
            logger.error(f"Error creating backup: {str(e)}")
            raise

    def reset_database(self) -> dict:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                # Delete all data from the tables
                cursor.execute("DELETE FROM articles")
                cursor.execute("DELETE FROM raw_articles")
                cursor.execute("DELETE FROM reports")
                
                # Reset autoincrement counters
                cursor.execute("DELETE FROM sqlite_sequence WHERE name='reports'")
                
                conn.commit()
                return {"message": "Database reset successful"}
            except Exception as e:
                logger.error(f"Error resetting database: {str(e)}")
                raise

    def create_user(self, username, password_hash, force_password_change=False):
        """Create a new user."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    force_password_change BOOLEAN DEFAULT 0,
                    completed_onboarding BOOLEAN DEFAULT 0
                )
            """)
            cursor.execute(
                "INSERT INTO users (username, password_hash, force_password_change, completed_onboarding) VALUES (?, ?, ?, ?)",
                (username, password_hash, force_password_change, False)
            )
            conn.commit()

    def update_user_onboarding(self, username, completed):
        """Update user's onboarding status."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET completed_onboarding = ? WHERE username = ?",
                (completed, username)
            )
            conn.commit()
            return cursor.rowcount > 0

    def set_force_password_change(self, username: str, force: bool = True) -> bool:
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE users 
                    SET force_password_change = ?
                    WHERE username = ?
                """, (1 if force else 0, username))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error setting force_password_change: {str(e)}")
            return False

    def get_database_path(self, db_name: str) -> str:
        """Get the full path to a database file."""
        # Ensure the database name ends with .db
        if not db_name.endswith('.db'):
            db_name = f"{db_name}.db"
        return os.path.join(DATABASE_DIR, db_name)

    def download_database(self, db_name: str) -> str:
        """
        Prepare database for download and return the path.
        Creates a copy to avoid locking issues.
        """
        try:
            # Ensure the database name ends with .db
            if not db_name.endswith('.db'):
                db_name = f"{db_name}.db"
            
            src_path = self.get_database_path(db_name)
            if not os.path.exists(src_path):
                raise FileNotFoundError(f"Database {db_name} not found")

            # Create a temporary copy for download
            download_path = os.path.join(DATABASE_DIR, f"download_{db_name}")
            
            # Ensure the source database is not locked
            with open(src_path, 'rb') as src, open(download_path, 'wb') as dst:
                dst.write(src.read())
            
            return download_path
        except Exception as e:
            logger.error(f"Error preparing database for download: {str(e)}")
            raise

    async def get_total_articles(self) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM articles")
            return cursor.fetchone()[0]

    async def get_articles_today(self) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            today = datetime.now().strftime('%Y-%m-%d')
            cursor.execute("""
                SELECT COUNT(*) FROM articles 
                WHERE DATE(submission_date) = ?
            """, (today,))
            return cursor.fetchone()[0]

    async def get_keyword_group_count(self) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM keyword_groups")
            return cursor.fetchone()[0]

    async def get_topic_count(self) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(DISTINCT topic) FROM articles")
            return cursor.fetchone()[0]

    def add_article_annotation(self, article_uri: str, author: str, content: str, is_private: bool = False) -> int:
        logger.debug(f"Adding annotation for article URI: {article_uri}")
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO article_annotations 
                    (article_uri, author, content, is_private)
                    VALUES (?, ?, ?, ?)
                """, (article_uri, author, content, is_private))
                annotation_id = cursor.lastrowid
                logger.debug(f"Successfully added annotation with ID: {annotation_id}")
                return annotation_id
        except sqlite3.Error as e:
            logger.error(f"Database error adding annotation: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error adding annotation: {str(e)}")
            raise

    def get_article_annotations(self, article_uri: str, include_private: bool = False) -> list:
        logger.debug(f"Getting annotations for article URI: {article_uri}")
        try:
            with self.get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                query = """
                    SELECT * FROM article_annotations 
                    WHERE article_uri = ?
                """
                if not include_private:
                    query += " AND is_private = 0"
                query += " ORDER BY created_at DESC"
                
                logger.debug(f"Executing query: {query} with URI: {article_uri}")  # Fixed debug logging
                cursor.execute(query, (article_uri,))
                annotations = [dict(row) for row in cursor.fetchall()]
                logger.debug(f"Found {len(annotations)} annotations")
                return annotations
        except sqlite3.Error as e:
            logger.error(f"Database error getting annotations: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error getting annotations: {str(e)}")
            raise

    def update_article_annotation(self, annotation_id: int, content: str, is_private: bool) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE article_annotations 
                SET content = ?, is_private = ?
                WHERE id = ?
            """, (content, is_private, annotation_id))
            return cursor.rowcount > 0

    def delete_article_annotation(self, annotation_id: int) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM article_annotations WHERE id = ?", (annotation_id,))
            return cursor.rowcount > 0

    def bulk_delete_articles(self, uris: List[str]) -> int:
        if not uris:
            logger.warning("No URIs provided for bulk delete")
            return 0
        
        logger.info(f"Attempting to bulk delete {len(uris)} articles")
        decoded_uris = [unquote_plus(unquote_plus(uri)) for uri in uris]
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                logger.debug(f"First few URIs to delete: {decoded_uris[:3]}")
                
                # Temporarily disable foreign key constraints
                cursor.execute("PRAGMA foreign_keys = OFF")
                
                cursor.execute("BEGIN TRANSACTION")
                try:
                    placeholders = ','.join(['?' for _ in decoded_uris])
                    
                    # Delete from related tables first
                    cursor.execute(f"""
                        DELETE FROM keyword_alerts 
                        WHERE article_uri IN ({placeholders})
                    """, decoded_uris)
                    logger.debug(f"Deleted {cursor.rowcount} keyword alerts")
                    
                    cursor.execute(f"""
                        DELETE FROM article_annotations 
                        WHERE article_uri IN ({placeholders})
                    """, decoded_uris)
                    logger.debug(f"Deleted {cursor.rowcount} annotations")
                    
                    cursor.execute(f"""
                        DELETE FROM raw_articles 
                        WHERE uri IN ({placeholders})
                    """, decoded_uris)
                    logger.debug(f"Deleted {cursor.rowcount} raw articles")
                    
                    # Finally delete the articles
                    cursor.execute(f"""
                        DELETE FROM articles 
                        WHERE uri IN ({placeholders})
                    """, decoded_uris)
                    deleted_count = cursor.rowcount
                    logger.debug(f"Deleted {deleted_count} articles")
                    
                    cursor.execute("COMMIT")
                    
                    # Re-enable foreign key constraints
                    cursor.execute("PRAGMA foreign_keys = ON")
                    
                    logger.info(f"Successfully deleted {deleted_count} articles")
                    return deleted_count
                    
                except Exception as e:
                    cursor.execute("ROLLBACK")
                    # Re-enable foreign key constraints even on error
                    cursor.execute("PRAGMA foreign_keys = ON")
                    logger.error(f"Error during bulk delete transaction: {e}")
                    raise
                
        except Exception as e:
            logger.error(f"Error in bulk_delete_articles: {e}")
            raise

    def create_topic(self, topic_name: str) -> bool:
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                # Create an initial empty entry for the topic
                cursor.execute("""
                    INSERT OR IGNORE INTO articles 
                    (topic, title, uri, submission_date) 
                    VALUES (?, 'Topic Created', 'initial', datetime('now'))
                """, (topic_name,))
                return True
        except Exception as e:
            logger.error(f"Error creating topic in database: {str(e)}")
            return False

    def update_topic(self, topic_name: str) -> bool:
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                # Check if topic exists
                cursor.execute("SELECT 1 FROM articles WHERE topic = ? LIMIT 1", (topic_name,))
                if not cursor.fetchone():
                    # If topic doesn't exist, create it
                    return self.create_topic(topic_name)
                return True
        except Exception as e:
            logger.error(f"Error updating topic in database: {str(e)}")
            return False

    def _debug_schema(self):
        """Print the schema and foreign keys of relevant tables"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            tables = ['articles', 'keyword_alerts', 'article_annotations', 
                     'raw_articles', 'tags', 'article_tags']
            
            for table in tables:
                logger.debug(f"\nSchema for {table}:")
                cursor.execute(f"PRAGMA table_info({table})")
                columns = cursor.fetchall()
                for col in columns:
                    logger.debug(f"  {col}")
                    
                logger.debug(f"\nForeign keys for {table}:")
                cursor.execute(f"PRAGMA foreign_key_list({table})")
                foreign_keys = cursor.fetchall()
                for fk in foreign_keys:
                    logger.debug(f"  {fk}")

    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists in the database."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?;",
                    (table_name,),
                )
                return cursor.fetchone() is not None
        except sqlite3.Error as e:
            logging.error(f"Error checking if table {table_name} exists: {e}")
            return False

    # ------------------------------------------------------------------
    # Ontology / Scenario support (dynamic building-block framework)
    # ------------------------------------------------------------------

    def create_ontology_tables(self):
        """Ensure tables for BuildingBlocks, Scenarios and their M2M link exist."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Building blocks (driver_type, sentiment, custom etc.)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS building_blocks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    kind TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    options TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            # If the table existed previously, ensure the `options` column exists
            cursor.execute("PRAGMA table_info(building_blocks)")
            cols = {row[1] for row in cursor.fetchall()}
            if "options" not in cols:
                cursor.execute("ALTER TABLE building_blocks ADD COLUMN options TEXT")

            # Scenarios (group of building blocks per topic)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS scenarios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    topic TEXT NOT NULL,
                    article_table TEXT UNIQUE,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            # Many-to-many link
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS scenario_blocks (
                    scenario_id INTEGER NOT NULL,
                    building_block_id INTEGER NOT NULL,
                    PRIMARY KEY (scenario_id, building_block_id),
                    FOREIGN KEY (scenario_id) REFERENCES scenarios(id) ON DELETE CASCADE,
                    FOREIGN KEY (building_block_id) REFERENCES building_blocks(id) ON DELETE CASCADE
                )
                """
            )

            conn.commit()

            # Load defaults from config.json (first topic)
            import json, os
            cfg_path = os.path.join(os.path.dirname(__file__), "config/config.json")
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                topic_cfg = cfg.get("topics", [])[0] if cfg.get("topics") else {}
            except Exception:
                topic_cfg = {}

            cats = topic_cfg.get("categories", [])
            sentiments = topic_cfg.get("sentiment", [])
            futures = topic_cfg.get("future_signals", [])
            drivers = topic_cfg.get("driver_types", [])
            tti = topic_cfg.get("time_to_impact", [])

            default_blocks = [
                (
                    "Categorize Article",
                    "categorization",
                    "Classify the article into one of the configured categories. If none fit choose 'Other'. Provide one-sentence rationale.",
                    json.dumps(cats + ["Other"]),
                ),
                (
                    "Topic Sentiment",
                    "sentiment",
                    "What is the article's sentiment towards the given topic? Provide a brief explanation.",
                    json.dumps(sentiments or ["Positive", "Negative", "Neutral"]),
                ),
                (
                    "Relationship to Topic",
                    "relationship",
                    "Does the article act as a blocker, catalyst, accelerator, initiator, or supporting datapoint for the topic? Explain why.",
                    json.dumps(["Accelerator", "Blocker", "Catalyst", "Initiator", "Supporting"]),
                ),
                (
                    "Objectivity Score",
                    "weighting",
                    "On a scale of 0–1, how objective is this article? Justify the rating in one sentence.",
                    json.dumps(["0", "0.5", "1"]),
                ),
                (
                    "Sensitivity Level",
                    "classification",
                    "Assign a sensitivity class (Public, Internal, Confidential, Secret) to the article and give one-sentence rationale.",
                    json.dumps(["Public", "Internal", "Confidential", "Secret"]),
                ),
                (
                    "Journalist Summary",
                    "summarization",
                    "Provide a concise three-sentence summary of the article from the perspective of an investigative journalist.",
                    None,
                ),
                (
                    "Time to Impact",
                    "classification",
                    "Classify the time-to-impact as one of the configured options (e.g. Immediate, Short-term, Medium-term, Long-term). Provide a brief explanation.",
                    json.dumps(tti or ["Immediate", "Short-term", "Medium-term", "Long-term"]),
                ),
                (
                    "Driver Type",
                    "classification",
                    "Classify the article into one of the configured driver types and give a short explanation.",
                    json.dumps(drivers or ["Accelerator", "Blocker", "Catalyst", "Initiator", "Delayer"]),
                ),
                (
                    "Relevant Tags",
                    "classification",
                    "Generate 3-5 relevant tags that capture the main themes of the article.",
                    None,
                ),
                (
                    "Future Signal",
                    "classification",
                    "Classify the article into one of the configured future signals and explain your choice briefly.",
                    json.dumps(futures),
                ),
                (
                    "Keywords",
                    "classification",
                    "Generate a list of concise keyword tags capturing the core themes of the article.",
                    None,
                ),
            ]

            cursor.executemany(
                "INSERT OR IGNORE INTO building_blocks (name, kind, prompt, options) VALUES (?,?,?,?)",
                default_blocks,
            )
            conn.commit()

    # ------------------------------------------------------------------
    # Dynamic article tables per scenario
    # ------------------------------------------------------------------

    def _sanitize_identifier(self, name: str) -> str:
        """Return a lowercase, safe SQLite identifier (letters, digits, _)."""
        import re
        return re.sub(r"[^0-9a-zA-Z_]+", "_", name.strip().lower())

    def create_custom_articles_table(self, table_name: str, building_block_names: list[str]):
        """Create a custom articles table for a scenario if it doesn't exist.

        The new table is **loosely based** on the base `articles` schema and
        is extended with a column for each selected building block plus an
        optional `<block>_explanation` column.
        """

        safe_table = self._sanitize_identifier(table_name)

        # Do nothing if the table already exists
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (safe_table,)
            )
            if cursor.fetchone():
                return  # Table already present

            # Base schema copied from the default articles table
            columns_sql = [
                "uri TEXT PRIMARY KEY",
                "title TEXT",
                "news_source TEXT",
                "publication_date TEXT",
                "submission_date TEXT DEFAULT CURRENT_TIMESTAMP",
                "summary TEXT",
                "tags TEXT",
                "topic TEXT",
                "analyzed BOOLEAN DEFAULT FALSE",
            ]

            existing_cols = set(k.split()[0] for k in columns_sql)  # track base names

            for raw_name in building_block_names:
                base_col = self._sanitize_identifier(raw_name)

                # Avoid clashes with core / previously added names
                col = base_col
                suffix = 1
                while col in existing_cols or col in (
                    "uri",
                    "title",
                    "news_source",
                    "publication_date",
                    "submission_date",
                    "summary",
                    "tags",
                    "topic",
                    "analyzed",
                ):
                    col = f"{base_col}_{suffix}"
                    suffix += 1

                existing_cols.add(col)

                columns_sql.append(f"{col} TEXT")
                columns_sql.append(f"{col}_explanation TEXT")

            create_sql = f"CREATE TABLE IF NOT EXISTS {safe_table} (" + ", ".join(columns_sql) + ")"
            cursor.execute(create_sql)
            conn.commit()
            self._debug_schema()  # Optional: logs new schema

# Use the static method for DATABASE_URL
DATABASE_URL = f"sqlite:///./{Database.get_active_database()}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Initialize the database
db = Database()

def initialize_db():
    # This function is now synchronous and doesn't need to do anything
    # since the database is initialized when the Database object is created
    pass


