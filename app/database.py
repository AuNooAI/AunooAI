import sqlite3
import os
import json
from config.settings import DATABASE_DIR
from datetime import datetime
from typing import List, Tuple, Optional, Dict
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
import logging
from fastapi import HTTPException

logger = logging.getLogger(__name__)

# Add this near the top of the file, after imports
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class Database:
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
        print(f"Database initialized: {self.db_path}")

    def get_connection(self):
        return sqlite3.connect(self.db_path)

    def init_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
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
                    driver_type_explanation TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT,
                    created_at TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS config (
                    name TEXT PRIMARY KEY,
                    content TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS raw_articles (
                    uri TEXT PRIMARY KEY,
                    raw_markdown TEXT,
                    submission_date TEXT,
                    last_updated TEXT
                )
            """)
            conn.commit()

    def migrate_database(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # ... (rest of the migrations)

            # Add driver_type column if it doesn't exist
            cursor.execute("""
            SELECT COUNT(*) FROM pragma_table_info('articles') WHERE name='driver_type';
            """)
            if cursor.fetchone()[0] == 0:
                cursor.execute("""
                ALTER TABLE articles ADD COLUMN driver_type TEXT;
                """)
                print("Added driver_type column to articles table")

            conn.commit()

    def create_database(self, name):
        if not name.endswith('.db'):
            name += '.db'
        new_db_path = os.path.join(DATABASE_DIR, name)
        new_db = Database(name)  # This will call init_db() and create all necessary tables
        return {"id": name, "name": name}

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
        if not name.endswith('.db'):
            name += '.db'
        self.db_path = os.path.join(DATABASE_DIR, name)
        self.init_db()
        self.save_active_database(name)
        return {"message": f"Active database set to {name}"}

    def save_active_database(self, name):
        config_path = os.path.join(DATABASE_DIR, 'config.json')
        with open(config_path, 'w') as f:
            json.dump({"active_database": name}, f)

    @staticmethod
    def get_active_database():
        config_path = os.path.join(DATABASE_DIR, 'config.json')
        with open(config_path, 'r') as f:
            config = json.load(f)
        return config.get('active_database', 'fnaapp.db')
        DATABASE_URL = f"sqlite:///./{get_active_database()}"
    

    def get_databases(self):
        databases = []
        for file in os.listdir(DATABASE_DIR):
            if file.endswith('.db'):
                databases.append({"id": file, "name": file})
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

    def update_or_create_article(self, article_data):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            if 'submission_date' not in article_data:
                article_data['submission_date'] = datetime.now().isoformat()

            cursor.execute("SELECT * FROM articles WHERE uri = ?", (article_data['uri'],))
            existing_article = cursor.fetchone()
            
            if existing_article:
                update_query = """
                UPDATE articles SET
                    title = ?, news_source = ?, publication_date = ?, summary = ?,
                    category = ?, future_signal = ?, future_signal_explanation = ?,
                    sentiment = ?, sentiment_explanation = ?, time_to_impact = ?,
                    time_to_impact_explanation = ?, tags = ?, driver_type = ?,
                    driver_type_explanation = ?, submission_date = ?, topic = ?
                WHERE uri = ?
                """
                cursor.execute(update_query, (
                    article_data['title'], article_data['news_source'],
                    article_data['publication_date'], article_data['summary'],
                    article_data['category'], article_data['future_signal'],
                    article_data['future_signal_explanation'], article_data['sentiment'],
                    article_data['sentiment_explanation'], article_data['time_to_impact'],
                    article_data['time_to_impact_explanation'], 
                    ','.join(article_data['tags']) if isinstance(article_data['tags'], list) else article_data['tags'],
                    article_data['driver_type'], article_data['driver_type_explanation'],
                    article_data['submission_date'], article_data['topic'], article_data['uri']
                ))
            else:
                insert_query = """
                INSERT INTO articles (
                    uri, title, news_source, publication_date, summary,
                    category, future_signal, future_signal_explanation,
                    sentiment, sentiment_explanation, time_to_impact,
                    time_to_impact_explanation, tags, driver_type,
                    driver_type_explanation, submission_date, topic
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                cursor.execute(insert_query, (
                    article_data['uri'], article_data['title'], article_data['news_source'],
                    article_data['publication_date'], article_data['summary'],
                    article_data['category'], article_data['future_signal'],
                    article_data['future_signal_explanation'], article_data['sentiment'],
                    article_data['sentiment_explanation'], article_data['time_to_impact'],
                    article_data['time_to_impact_explanation'], 
                    ','.join(article_data['tags']) if isinstance(article_data['tags'], list) else article_data['tags'],
                    article_data['driver_type'], article_data['driver_type_explanation'],
                    article_data['submission_date'], article_data['topic']
                ))
            
            conn.commit()
        
        return {"message": "Article updated or created successfully"}

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
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            query = """
            INSERT INTO articles (
            title, uri, news_source, summary, sentiment, time_to_impact, category, 
            future_signal, future_signal_explanation, publication_date, sentiment_explanation, 
            time_to_impact_explanation, tags, driver_type, driver_type_explanation, submission_date, topic
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            params = (
                article_data['title'], article_data['uri'], article_data['news_source'],
                article_data['summary'], article_data['sentiment'], article_data['time_to_impact'],
                article_data['category'], article_data['future_signal'], article_data['future_signal_explanation'],
                article_data['publication_date'], article_data['sentiment_explanation'],
                article_data['time_to_impact_explanation'], 
                ','.join(article_data['tags']) if isinstance(article_data['tags'], list) else article_data['tags'],
                article_data['driver_type'], article_data['driver_type_explanation'], 
                article_data['submission_date'], article_data['topic']
            )
            
            try:
                cursor.execute(query, params)
                conn.commit()
                return {"message": "Article saved successfully"}
            except Exception as e:
                logger.error(f"Error saving article: {str(e)}")
                logger.error(f"Article data: {article_data}")
                logger.error(f"Query: {query}")
                logger.error(f"Params: {params}")
                raise HTTPException(status_code=500, detail=f"Error saving article: {str(e)}")

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
        page: int = 1,
        per_page: int = 10
    ) -> Tuple[List[Dict], int]:
        """Search articles with filters including topic."""
        query_conditions = []
        params = []

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
            query_conditions.append("publication_date >= ?")
            params.append(pub_date_start)

        if pub_date_end:
            query_conditions.append("publication_date <= ?")
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
        logger.debug(f"Retrieved categories from database: {categories}")
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

    def save_raw_article(self, uri, raw_markdown):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            current_time = datetime.now().isoformat()
            
            cursor.execute("SELECT * FROM raw_articles WHERE uri = ?", (uri,))
            existing_raw_article = cursor.fetchone()
            
            if existing_raw_article:
                update_query = """
                UPDATE raw_articles SET
                    raw_markdown = ?, last_updated = ?
                WHERE uri = ?
                """
                cursor.execute(update_query, (raw_markdown, current_time, uri))
            else:
                insert_query = """
                INSERT INTO raw_articles (uri, raw_markdown, submission_date, last_updated)
                VALUES (?, ?, ?, ?)
                """
                cursor.execute(insert_query, (uri, raw_markdown, current_time, current_time))
            
            conn.commit()
        
        return {"message": "Raw article saved successfully"}

    def get_raw_article(self, uri: str):
        """Retrieve a raw article from the database."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
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

    def get_recent_articles_by_topic(self, topic_name, limit=10):
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM articles
                WHERE topic = ?
                ORDER BY COALESCE(submission_date, publication_date) DESC, rowid DESC
                LIMIT ?
            """, (topic_name, limit))
            articles = [dict(row) for row in cursor.fetchall()]
            
            # Convert tags string back to list
            for article in articles:
                if article['tags']:
                    article['tags'] = article['tags'].split(',')
                else:
                    article['tags'] = []
            
            return articles

DATABASE_URL = f"sqlite:///./{Database.get_active_database()}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
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


