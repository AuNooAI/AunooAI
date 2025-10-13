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
    
    # Connection pool settings
    MAX_CONNECTIONS = 10  # Reduced for async-first approach
    CONNECTION_TIMEOUT = 5  # seconds
    RETRY_ATTEMPTS = 3
    
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
        self.db_type = os.getenv('DB_TYPE', 'sqlite').lower()

        # Initialize instance variables for connection tracking
        self._connections = {}
        self._sqlalchemy_connections = {}
        self._facade = None  # Lazy initialization to avoid circular imports

        # Initialize SQLAlchemy connection pool on first use (lazy loading)
        logger.info(f"Database initialized: {self.db_path}")
        try:
            self._temp_get_connection()
            logger.info(f"Database connection pool ready for {db_name}")
        except Exception as e:
            logger.error(f"Failed to initialize database connection: {e}")
            raise RuntimeError(f"Database initialization failed: {e}") from e

    @property
    def facade(self):
        """Lazy initialization of database query facade to avoid circular imports."""
        if self._facade is None:
            from app.database_query_facade import DatabaseQueryFacade
            self._facade = DatabaseQueryFacade(self, logger)
        return self._facade

    # TODO: Replace get_connection with this function once all queries moved to SQLAlchemy.
    def _temp_get_connection(self):
        thread_id = threading.get_ident()

        # TODO: TEMPORARY PATCH FOR REPLACING DIRECT sqlite CONNECTIONS WITH SQLALCHEMY
        # TODO: FOR PGSL OR OTHER TYPES OF ENGINES RE-USE EXISTING CONNECTIONS TO AVOID EXHAUSTING RESOURCES!!!
        # TODO: MUST INCLUDE DEFAULT TABLE VALUES IN MIGRATIONS, SEE GIT COMMITS FOR WHAT HAS BEEN REMOVED!!!!!
        if thread_id not in self._sqlalchemy_connections:
            logger.debug(f"Creating new SQLAlchemy connection for thread {thread_id}")
            from sqlalchemy import create_engine
            import os

            # Check DB_TYPE environment variable to support PostgreSQL
            db_type = os.getenv('DB_TYPE', 'sqlite').lower()

            if db_type == 'postgresql':
                # Use PostgreSQL connection
                from app.config.settings import db_settings
                database_url = db_settings.get_sync_database_url()
                logger.info(f"Creating PostgreSQL connection: {db_settings.DB_NAME}")
                engine = create_engine(
                    database_url,
                    echo=True,
                    pool_pre_ping=True,
                    pool_size=10,
                    max_overflow=5
                )
            else:
                # Use SQLite connection (default)
                logger.debug(f"Creating SQLite connection: {self.db_path}")
                engine = create_engine(
                    f"sqlite:///{self.db_path}",
                    echo=True,
                    connect_args={"check_same_thread": False}
                )

            connection = engine.connect()

            # TODO: Rename this to a less verbose name.
            self._sqlalchemy_connections[thread_id] = connection
            logger.debug(f"Created SQLAlchemy connection for thread {thread_id}")

            # from sqlalchemy import select
            #
            # import database_models
            # select_stmt = select(database_models.t_users)
            # result = connection.execute(select_stmt)
            #
            # import pprint
            # pprint.pp([user for user in result])
            # TODO: END TEMPORARY PATCH
        else:
            logger.debug(f"Reusing existing SQLAlchemy connection for thread {thread_id}")
        return self._sqlalchemy_connections[thread_id]

    def get_connection(self):
        """Get a thread-local database connection with optimized settings and retry logic"""
        thread_id = threading.get_ident()
        
        # Check connection pool limits
        if len(self._connections) >= self.MAX_CONNECTIONS:
            logger.warning(f"Connection pool limit reached ({self.MAX_CONNECTIONS}). Cleaning up stale connections.")
            self._cleanup_stale_connections()
        
        if thread_id not in self._connections:
            for attempt in range(self.RETRY_ATTEMPTS):
                try:
                    self._connections[thread_id] = sqlite3.connect(
                        self.db_path, 
                        timeout=self.CONNECTION_TIMEOUT
                    )

                    # Enable foreign key support
                    self._connections[thread_id].execute("PRAGMA foreign_keys = ON")
                    
                    # Optimize for concurrent operations - with error handling
                    try:
                        # Core WAL mode configuration
                        self._connections[thread_id].execute("PRAGMA journal_mode = WAL")  # Write-Ahead Logging
                        self._connections[thread_id].execute("PRAGMA synchronous = NORMAL")  # Balance safety and speed
                        self._connections[thread_id].execute("PRAGMA temp_store = MEMORY")  # Store temp data in memory
                        
                        # Performance optimizations from SQLite tuning article
                        self._connections[thread_id].execute("PRAGMA mmap_size = 30000000000")  # 30GB memory mapping
                        # Note: page_size can only be set when creating a new database
                        # For existing databases, we'll work with the current page size
                        self._connections[thread_id].execute("PRAGMA cache_size = 50000")  # 50MB cache (increased from 10MB)
                        self._connections[thread_id].execute("PRAGMA busy_timeout = 30000")  # 30 second timeout
                        
                        # WAL checkpoint optimization
                        self._connections[thread_id].execute("PRAGMA wal_autocheckpoint = 1000")  # More frequent checkpoints
                        
                        # Additional optimizations
                        self._connections[thread_id].execute("PRAGMA optimize")  # Run query optimizer
                        
                    except sqlite3.DatabaseError as e:
                        logger.error(f"Failed to set SQLite optimizations: {e}")
                        logger.error("Database may be corrupted. Run scripts/fix_database_corruption.py to repair.")
                        raise
                    
                    break  # Success, exit retry loop
                    
                except sqlite3.OperationalError as e:
                    if "database is locked" in str(e).lower() and attempt < self.RETRY_ATTEMPTS - 1:
                        logger.warning(f"Database locked, retrying in {self.CONNECTION_TIMEOUT}s (attempt {attempt + 1}/{self.RETRY_ATTEMPTS})")
                        import time
                        time.sleep(self.CONNECTION_TIMEOUT)
                        continue
                    else:
                        logger.error(f"Database connection failed after {self.RETRY_ATTEMPTS} attempts: {e}")
                        logger.error(f"Database path: {self.db_path}")
                        logger.error("This usually indicates database corruption.")
                        logger.error("To fix: python scripts/fix_database_corruption.py")
                        raise
                except sqlite3.DatabaseError as e:
                    logger.error(f"Database connection failed: {e}")
                    logger.error(f"Database path: {self.db_path}")
                    logger.error("This usually indicates database corruption.")
                    logger.error("To fix: python scripts/fix_database_corruption.py")
                    raise
            
        return self._connections[thread_id]

    def _cleanup_stale_connections(self):
        """Clean up stale connections from the pool"""
        import threading
        current_threads = set(threading.enumerate())
        stale_connections = []
        
        for thread_id, conn in self._connections.items():
            # Check if thread is still alive
            thread_alive = any(t.ident == thread_id for t in current_threads)
            if not thread_alive:
                stale_connections.append(thread_id)
        
        # Close and remove stale connections
        for thread_id in stale_connections:
            try:
                self._connections[thread_id].close()
                del self._connections[thread_id]
                logger.info(f"Cleaned up stale connection for thread {thread_id}")
            except Exception as e:
                logger.error(f"Error cleaning up stale connection {thread_id}: {e}")

    def perform_wal_checkpoint(self, mode="PASSIVE"):
        """
        Perform WAL checkpoint to prevent WAL file from growing indefinitely
        
        Args:
            mode: Checkpoint mode - "PASSIVE", "FULL", or "RESTART"
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                if mode == "PASSIVE":
                    cursor.execute("PRAGMA wal_checkpoint(PASSIVE)")
                elif mode == "FULL":
                    cursor.execute("PRAGMA wal_checkpoint(FULL)")
                elif mode == "RESTART":
                    cursor.execute("PRAGMA wal_checkpoint(RESTART)")
                else:
                    cursor.execute("PRAGMA wal_checkpoint")
                
                result = cursor.fetchone()
                if result:
                    logger.info(f"WAL checkpoint ({mode}) completed: {result}")
                return result
        except Exception as e:
            logger.error(f"WAL checkpoint failed: {e}")
            return None

    def get_wal_info(self):
        """Get WAL file information"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("PRAGMA wal_checkpoint")
                result = cursor.fetchone()
                return result
        except Exception as e:
            logger.error(f"Failed to get WAL info: {e}")
            return None

    def close_connections(self):
        """Close all database connections"""
        # Perform final WAL checkpoint before closing
        try:
            self.perform_wal_checkpoint("FULL")
        except Exception as e:
            logger.error(f"Final WAL checkpoint failed: {e}")
        
        for conn in self._connections.values():
            try:
                conn.close()
            except Exception:
                pass
        self._connections.clear()

    def __del__(self):
        """Cleanup connections when the object is destroyed"""
        self.close_connections()

    def create_articles_table(self):
        # TODO: Move data initialisation to migrations.
        """Create the articles and related tables."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Initialize default Auspex prompt if it doesn't exist
            cursor.execute("SELECT COUNT(*) FROM auspex_prompts WHERE name = 'default'")
            if cursor.fetchone()[0] == 0:
                default_prompt = """You are Auspex, an advanced AI research assistant specialized in analyzing news trends, sentiment patterns, and providing strategic insights.

Your capabilities include:
- Analyzing vast amounts of news data and research
- Identifying emerging trends and patterns
- Providing sentiment analysis and future impact predictions
- Accessing real-time news data through specialized tools
- Comparing different categories and topics
- Offering strategic foresight and risk analysis

You have access to the following tools:
- search_news: Search for current news articles (PRIORITIZED for "latest/recent" queries)
- get_topic_articles: Retrieve articles from the database for specific topics
- analyze_sentiment_trends: Analyze sentiment patterns over time
- get_article_categories: Get category distributions for topics
- search_articles_by_keywords: Search articles by specific keywords

When tool data is provided to you, it will be clearly marked at the beginning of your context. Always acknowledge when you're using tool data and explain what insights you're drawing from it.

CRITICAL PRIORITIES:
- When users ask for "latest", "recent", "current", or "breaking" news, prioritize real-time news search results
- Clearly distinguish between real-time news data and database/historical data
- If news search provides results, focus primarily on those for latest information queries
- Only use database articles as fallback when news search fails or for historical analysis

RESPONSE FORMAT: When you receive tool results, always:
1. **IMMEDIATELY** identify the data source (Latest News Search vs Database Articles)
2. Acknowledge which tools were used (you'll see a "Tools Used" section)
3. Summarize the key findings from the tool data
4. Provide your analysis and insights based on this data
5. Be transparent about what the data shows vs. your interpretation

Always provide thorough, insightful analysis backed by data. When asked about trends or patterns, use your tools to gather current information. Be concise but comprehensive in your responses.

Remember to cite your sources and provide actionable insights where possible."""
                
                cursor.execute("""
                    INSERT INTO auspex_prompts (name, title, content, description, is_default)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    "default",
                    "Default Auspex Assistant",
                    default_prompt,
                    "The default system prompt for Auspex AI assistant with tool integration",
                    True
                ))
                conn.commit()

    def _get_default_summary_prompt_template(self) -> str:
        """Get the default prompt template for the topic summary section."""
        return (
            "You are an AI assistant analyzing articles about '{topic}' for a busy decision-maker.\n"
            "Write a concise, structured summary based on the provided articles. Focus on the most critical information. Use bullet points for lists.\n"
            "Do not reference article numbers in your output.\n\n"
            "Use the following format:\n\n"
            "**Summary of {topic}**\n"
            "- Provide a brief (2-3 sentences) high-level overview of the current state of '{topic}'.\n"
            "- For EVERY fact or assertion, include a proper citation using this format: **[Article Title](Article URI)**\n"
            "- Each citation must be on its own line, not inline with text.\n"
            "- Ensure your overview is directly based on the articles provided, not general knowledge.\n\n"
            "**Top Three Developments**\n"
            "- Development 1: [Briefly state the development].\n  **Why this is need-to-know:**\n  [Explain its significance in 1-2 sentences].\n  Cite: **[Relevant Article Title](Article URI)**\n"
            "- Development 2: [Briefly state the development].\n  **Why this is need-to-know:**\n  [Explain its significance in 1-2 sentences].\n  Cite: **[Relevant Article Title](Article URI)**\n"
            "- Development 3: [Briefly state the development].\n  **Why this is need-to-know:**\n  [Explain its significance in 1-2 sentences].\n  Cite: **[Relevant Article Title](Article URI)**\n\n"
            "**Top 3 Industry Trends**\n"
            "- Trend 1: [Briefly state the trend].\n  **Why this is interesting:**\n  [Explain its significance in 1-2 sentences].\n  Cite: **[Relevant Article Title](Article URI)**\n"
            "- Trend 2: [Briefly state the trend].\n  **Why this is interesting:**\n  [Explain its significance in 1-2 sentences].\n  Cite: **[Relevant Article Title](Article URI)**\n"
            "- Trend 3: [Briefly state the trend].\n  **Why this is interesting:**\n  [Explain its significance in 1-2 sentences].\n  Cite: **[Relevant Article Title](Article URI)**\n\n"
            "**Strategic Takeaways for Decision Makers:**\n"
            "- Provide 2-3 high-level strategic implications or actionable insights derived from the above points that a decision maker should consider.\n\n"
            "Important: Always use the exact article titles and URIs from the data. Be very concise and focus on impact.\n"
            "Each section MUST include proper citation links to the original articles. DO NOT skip adding links.\n"
            "PUT LINKS ON THEIR OWN LINES - this is critical for rendering."
        )

    def _get_default_trend_analysis_prompt_template(self) -> str:
        """Get the default prompt template for the trend analysis section."""
        return (
            "Analyze the following trend data for '{topic}'. "
            "Provide a concise, structured analysis of trends and patterns, noting emerging themes and developments based on these data patterns.\n\n"
            "**Overall Trend Data for {topic}:**\n"
            "- Categories Distribution: {categories_str}\n"
            "- Sentiment Distribution: {sentiments_str}\n"
            "- Future Signal Distribution: {signals_str}\n"
            "- Time to Impact Distribution: {tti_str}\n"
            "- Top Tags (up to 10 with counts): {tags_str}\n\n"
            "**Analysis & Insights:**\n"
            "Begin with a 1-2 sentence overview of the general sentiment and activity level for '{topic}'.\n"
            "Then, for each of the following aspects, provide 2-3 bullet points highlighting key patterns, shifts, or noteworthy observations. If an observation is particularly illustrated by a specific article, cite it using **[Article Title](Article URI)** from the reference list below. Put each citation on its own line for proper rendering:\n"
            "  - **Category Insights:** (e.g., Dominant categories, significant shifts in category focus, surprising under/over-representation).\n"
            "    *Observation 1... \n"
            "    Cite if applicable.*\n"
            "    *Observation 2... \n"
            "    Cite if applicable.*\n"
            "  - **Sentiment Insights:** (e.g., Predominant sentiment, changes over time if inferable, sentiment drivers).\n"
            "    *Observation 1... \n"
            "    Cite if applicable.*\n"
            "    *Observation 2... \n"
            "    Cite if applicable.*\n"
            "  - **Future Outlook (Signals & TTI):** (e.g., Implications of future signals, common TTI, alignment or divergence between signals and TTI).\n"
            "    *Observation 1... \n"
            "    Cite if applicable.*\n"
            "    *Observation 2... \n"
            "    Cite if applicable.*\n"
            "  - **Key Tag Themes:** (e.g., Dominant tags and what they signify, clusters of related tags appearing frequently).\n"
            "    *Observation 1... \n"
            "    Cite if applicable.*\n"
            "    *Observation 2... \n"
            "    Cite if applicable.*\n\n"
            "Conclude with a 2-3 sentence synthesis on any connections between these different distributions or overall strategic insights valuable for decision-making.\n\n"
            "Be specific and data-driven. Avoid generic statements."
        )

    def _get_default_article_insights_prompt_template(self) -> str:
        """Get the default prompt template for article insights."""
        return (
            "Identify 3-5 major themes from the articles about \"{topic}\". For each theme:\n"
            "- Provide a theme title\n"
            "- Write a 1-2 sentence summary of the theme\n"
            "- List the relevant articles for the theme, each with:\n"
            "    - title\n"
            "    - url\n"
            "    - news source\n"
            "    - publication date\n"
            "    - a 1-2 sentence summary\n"
            "\n"
            "Do not reference article numbers. Do not mention 'Article X'.\n"
            "\n"
            "Format your response as a JSON list of themes, each with:\n"
            "- theme_name\n"
            "- theme_summary\n"
            "- articles: list of dicts with title, uri, news_source, publication_date, short_summary"
        )

    def _get_default_key_articles_prompt_template(self) -> str:
        """Get the default prompt template for why an article merits attention."""
        return (
            "Article Title: \"{article_title}\"\n"
            "Article Summary: \"{article_summary}\"\n\n"
            "Based on the title and summary above, provide a single, concise sentence (max 25 words) explaining to a busy decision maker why this specific article merits their attention. Focus on its key insight, implication, or relevance for strategic thinking."
        )

    def _get_default_ethical_impact_prompt_template(self) -> str:
        """Get the default prompt template for ethical and societal impact analysis."""
        return (
            "Analyze the ethical and societal impacts related to '{topic}' based on the following articles.\n"
            "Provide a concise analysis (2-3 paragraphs) highlighting key ethical dilemmas, societal consequences, and considerations. Cite specific examples from the articles provided using markdown links: **[Article Title](Article URI)**."
        )

    def _get_default_business_impact_prompt_template(self) -> str:
        """Get the default prompt template for business impact analysis."""
        return (
            "Analyze the business impacts and opportunities related to '{topic}' based on the following articles.\n"
            "Provide a concise analysis (2-3 paragraphs) highlighting key business implications, potential opportunities, disruptions, and strategic considerations for businesses. Cite specific examples from the articles provided using markdown links: **[Article Title](Article URI)**."
        )

    def _get_default_market_impact_prompt_template(self) -> str:
        """Get the default prompt template for market impact analysis."""
        return (
            "Analyze the market impacts, trends, and competitive landscape related to '{topic}' based on the following articles.\n"
            "Provide a concise analysis (2-3 paragraphs) highlighting key market trends, competitive dynamics, potential market shifts, and implications for market positioning. Cite specific examples from the articles provided using markdown links: **[Article Title](Article URI)**."
        )

    def _get_default_key_charts_prompt_template(self) -> str:
        """Get the default prompt template for key charts."""
        return (
            "Generate informative charts showing sentiment trends and future signals for '{topic}'."
        )

    def _get_default_podcast_prompt_template(self) -> str:
        """Get the default prompt template for latest podcast."""
        return (
            "Summarize the transcript of this podcast about '{topic}', highlighting key insights and takeaways in 2-3 concise paragraphs."
        )

    # ------------------------------------------------------------------
    # Podcast settings helpers
    # ------------------------------------------------------------------

    def get_podcast_settings(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM settings_podcasts LIMIT 1")
            settings = cursor.fetchone()
            
            if settings:
                columns = [col[0] for col in cursor.description]
                return dict(zip(columns, settings))
            else:
                # Default settings if none exist
                return {
                    "id": 1,
                    "podcast_enabled": 0,
                    "transcribe_enabled": 1,
                    "openai_model": "whisper-1",
                    "transcript_format": "text",
                    "uploads_folder": "podcast_uploads",
                    "output_folder": "podcasts"
                }
                
    def update_podcast_settings(self, settings):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if settings exist
            cursor.execute("SELECT COUNT(*) FROM settings_podcasts")
            count = cursor.fetchone()[0]
            
            if count == 0:
                # Insert new settings
                cursor.execute("""
                    INSERT INTO settings_podcasts (
                        podcast_enabled, transcribe_enabled, openai_model, 
                        transcript_format, uploads_folder, output_folder
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    settings.get('podcast_enabled', 0),
                    settings.get('transcribe_enabled', 1),
                    settings.get('openai_model', 'whisper-1'),
                    settings.get('transcript_format', 'text'),
                    settings.get('uploads_folder', 'podcast_uploads'),
                    settings.get('output_folder', 'podcasts')
                ))
            else:
                # Update existing settings
                cursor.execute("""
                    UPDATE settings_podcasts SET
                        podcast_enabled = ?,
                        transcribe_enabled = ?,
                        openai_model = ?,
                        transcript_format = ?,
                        uploads_folder = ?,
                        output_folder = ?
                """, (
                    settings.get('podcast_enabled', 0),
                    settings.get('transcribe_enabled', 1),
                    settings.get('openai_model', 'whisper-1'),
                    settings.get('transcript_format', 'text'),
                    settings.get('uploads_folder', 'podcast_uploads'),
                    settings.get('output_folder', 'podcasts')
                ))
            
            conn.commit()
            return True

    # ------------------------------------------------------------------
    # Newsletter prompt methods
    # ------------------------------------------------------------------

    def get_newsletter_prompt(self, content_type_id: str) -> dict:
        """Get the prompt template for a specific newsletter content type."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT content_type_id, prompt_template, description, last_updated 
                FROM newsletter_prompts 
                WHERE content_type_id = ?
                """, 
                (content_type_id,)
            )
            result = cursor.fetchone()
            
            if result:
                return {
                    "content_type_id": result[0],
                    "prompt_template": result[1],
                    "description": result[2],
                    "last_updated": result[3]
                }
            return None

    def get_all_newsletter_prompts(self) -> list:
        """Get all newsletter prompt templates."""
        try:
            logger.info("Fetching all newsletter prompt templates")
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT content_type_id, prompt_template, description, last_updated 
                    FROM newsletter_prompts
                    """
                )
                results = cursor.fetchall()
                
                logger.info(f"Found {len(results)} prompt templates in database")
                for result in results:
                    logger.info(f"Template found in DB: {result[0]}")
                
                templates = [{
                    "content_type_id": result[0],
                    "prompt_template": result[1],
                    "description": result[2],
                    "last_updated": result[3]
                } for result in results]
                
                logger.info(f"Returning {len(templates)} prompt templates")
                return templates
        except Exception as e:
            logger.error(f"Error fetching newsletter prompt templates: {str(e)}", exc_info=True)
            # Return an empty list instead of propagating the error
            return []

    def update_newsletter_prompt(self, content_type_id: str, prompt_template: str, description: str = None) -> bool:
        """Update the prompt template for a specific newsletter content type."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Get current prompt to check if description should be updated
                if description is None:
                    cursor.execute(
                        "SELECT description FROM newsletter_prompts WHERE content_type_id = ?",
                        (content_type_id,)
                    )
                    result = cursor.fetchone()
                    if result:
                        description = result[0]
                    else:
                        description = "Custom prompt template"
                
                # Update the prompt
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO newsletter_prompts 
                    (content_type_id, prompt_template, description, last_updated) 
                    VALUES (?, ?, ?, datetime('now'))
                    """, 
                    (content_type_id, prompt_template, description)
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error updating newsletter prompt: {str(e)}")
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
        # Use PostgreSQL-compatible connection via SQLAlchemy
        from sqlalchemy import text
        conn = self._temp_get_connection()

        # Execute query with .mappings() for dictionary access
        # Note: Do not close the connection - it's managed by the connection pool
        result = conn.execute(text("SELECT * FROM articles WHERE uri = :uri"), {"uri": uri}).mappings()
        article = result.fetchone()

        if article:
            article_dict = dict(article)
            if article_dict.get('tags'):
                article_dict['tags'] = article_dict['tags'].split(',')
            else:
                article_dict['tags'] = []
            logger.debug(f"Article found: {article_dict['title']}")
            return article_dict
        else:
            logger.debug("Article not found")
            return None
            
    def save_article(self, article_data):
        """Save article to database.

        Handles both new articles and updates to existing ones.
        Supports the new media bias fields.
        Uses SQLAlchemy facade for PostgreSQL compatibility.
        """
        try:
            return self.facade.upsert_article(article_data)
        except Exception as e:
            logging.error(f"Error in save_article: {str(e)}")
            raise

    def delete_article(self, uri):
        """Delete article from database.

        Uses SQLAlchemy facade for PostgreSQL compatibility.
        """
        logger.info(f"Attempting to delete article with URI: {uri}")
        try:
            deleted_count = self.facade.delete_article_by_url(uri)
            logger.info(f"Deleted {deleted_count} article(s) with URI: {uri}")
            return deleted_count > 0
        except Exception as e:
            logger.error(f"Error deleting article: {e}", exc_info=True)
            return False

    def save_article_analysis_cache(self, article_uri: str, analysis_type: str, content: str, model_used: str, metadata: dict = None) -> bool:
        """Save analysis result to cache with expiration."""
        from datetime import datetime, timedelta
        import sqlite3
        
        expires_at = datetime.utcnow() + timedelta(days=7)  # Cache for 7 days
        metadata_json = json.dumps(metadata) if metadata else None
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                # Create table without foreign key constraint for better cache flexibility
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS article_analysis_cache (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        article_uri TEXT NOT NULL,
                        analysis_type TEXT NOT NULL,
                        content TEXT NOT NULL,
                        model_used TEXT NOT NULL,
                        generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        expires_at TIMESTAMP,
                        metadata TEXT,
                        UNIQUE(article_uri, analysis_type, model_used)
                    )
                """)
                
                # Insert or replace cached analysis
                cursor.execute("""
                    INSERT OR REPLACE INTO article_analysis_cache 
                    (article_uri, analysis_type, content, model_used, expires_at, metadata)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (article_uri, analysis_type, content, model_used, expires_at, metadata_json))
                
                conn.commit()
                logger.info(f"Cached {analysis_type} analysis for article {article_uri} with model {model_used}")
                return True
            except sqlite3.IntegrityError as ie:
                # Handle foreign key constraint violations specifically
                if "FOREIGN KEY constraint failed" in str(ie):
                    logger.warning(f"Article {article_uri} not found in articles table, but caching analysis anyway")
                    # Try to migrate the table to remove foreign key constraint
                    try:
                        # Check if we need to migrate the table structure
                        cursor.execute("PRAGMA table_info(article_analysis_cache)")
                        columns = cursor.fetchall()
                        
                        # Check if table has foreign key constraint by looking at schema
                        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='article_analysis_cache'")
                        schema_result = cursor.fetchone()
                        
                        if schema_result and "FOREIGN KEY" in schema_result[0]:
                            logger.info("Migrating cache table to remove foreign key constraint")
                            
                            # Create new table without foreign key
                            cursor.execute("""
                                CREATE TABLE article_analysis_cache_new (
                                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                                    article_uri TEXT NOT NULL,
                                    analysis_type TEXT NOT NULL,
                                    content TEXT NOT NULL,
                                    model_used TEXT NOT NULL,
                                    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                    expires_at TIMESTAMP,
                                    metadata TEXT,
                                    UNIQUE(article_uri, analysis_type, model_used)
                                )
                            """)
                            
                            # Copy existing data
                            cursor.execute("""
                                INSERT INTO article_analysis_cache_new 
                                SELECT id, article_uri, analysis_type, content, model_used, generated_at, expires_at, metadata 
                                FROM article_analysis_cache
                            """)
                            
                            # Drop old table and rename
                            cursor.execute("DROP TABLE article_analysis_cache")
                            cursor.execute("ALTER TABLE article_analysis_cache_new RENAME TO article_analysis_cache")
                            
                            # Now insert the new record
                            cursor.execute("""
                                INSERT OR REPLACE INTO article_analysis_cache 
                                (article_uri, analysis_type, content, model_used, expires_at, metadata)
                                VALUES (?, ?, ?, ?, ?, ?)
                            """, (article_uri, analysis_type, content, model_used, expires_at, metadata_json))
                            
                            conn.commit()
                            logger.info(f"Cached {analysis_type} analysis for article {article_uri} with model {model_used} (migrated table)")
                            return True
                        else:
                            # Table already doesn't have foreign key, something else went wrong
                            logger.error(f"Unexpected integrity error: {ie}")
                            conn.rollback()
                            return False
                            
                    except Exception as migrate_error:
                        logger.error(f"Failed to migrate cache table: {migrate_error}")
                        conn.rollback()
                        return False
                else:
                    logger.error(f"Integrity error saving analysis cache: {ie}")
                    conn.rollback()
                    return False
            except Exception as e:
                logger.error(f"Error saving analysis cache: {e}")
                conn.rollback()
                return False

    def get_article_analysis_cache(self, article_uri: str, analysis_type: str, model_used: str = None) -> dict:
        """Get cached analysis result if not expired."""
        from datetime import datetime
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                # Create table if it doesn't exist
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS article_analysis_cache (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        article_uri TEXT NOT NULL,
                        analysis_type TEXT NOT NULL,
                        content TEXT NOT NULL,
                        model_used TEXT NOT NULL,
                        generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        expires_at TIMESTAMP,
                        metadata TEXT,
                        FOREIGN KEY (article_uri) REFERENCES articles(uri) ON DELETE CASCADE,
                        UNIQUE(article_uri, analysis_type, model_used)
                    )
                """)
                
                # Query for cached analysis
                if model_used:
                    cursor.execute("""
                        SELECT content, model_used, generated_at, metadata 
                        FROM article_analysis_cache 
                        WHERE article_uri = ? AND analysis_type = ? AND model_used = ? 
                        AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
                        ORDER BY generated_at DESC LIMIT 1
                    """, (article_uri, analysis_type, model_used))
                else:
                    cursor.execute("""
                        SELECT content, model_used, generated_at, metadata 
                        FROM article_analysis_cache 
                        WHERE article_uri = ? AND analysis_type = ? 
                        AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
                        ORDER BY generated_at DESC LIMIT 1
                    """, (article_uri, analysis_type))
                
                result = cursor.fetchone()
                if result:
                    metadata = json.loads(result[3]) if result[3] else {}
                    return {
                        'content': result[0],
                        'model_used': result[1],
                        'generated_at': result[2],
                        'metadata': metadata
                    }
                return None
            except Exception as e:
                logger.error(f"Error getting analysis cache: {e}")
                return None

    def clean_expired_analysis_cache(self) -> int:
        """Clean up expired analysis cache entries."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    DELETE FROM article_analysis_cache 
                    WHERE expires_at IS NOT NULL AND expires_at < CURRENT_TIMESTAMP
                """)
                conn.commit()
                deleted_count = cursor.rowcount
                logger.info(f"Cleaned up {deleted_count} expired analysis cache entries")
                return deleted_count
            except Exception as e:
                logger.error(f"Error cleaning analysis cache: {e}")
                return 0

    def save_signal_instruction(self, name: str, description: str, instruction: str, topic: str = None, is_active: bool = True) -> bool:
        """Save a custom signal instruction for threat hunting."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                # Create table if it doesn't exist
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS signal_instructions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL UNIQUE,
                        description TEXT,
                        instruction TEXT NOT NULL,
                        topic TEXT,
                        is_active BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Insert or replace signal instruction
                cursor.execute("""
                    INSERT OR REPLACE INTO signal_instructions 
                    (name, description, instruction, topic, is_active, updated_at)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (name, description, instruction, topic, is_active))
                
                conn.commit()
                logger.info(f"Saved signal instruction: {name}")
                return True
            except Exception as e:
                logger.error(f"Error saving signal instruction: {e}")
                conn.rollback()
                return False

    def get_signal_instructions(self, topic: str = None, active_only: bool = True) -> List[Dict]:
        """Get signal instructions, optionally filtered by topic."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                # Create table if it doesn't exist
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS signal_instructions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL UNIQUE,
                        description TEXT,
                        instruction TEXT NOT NULL,
                        topic TEXT,
                        is_active BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Query signal instructions
                if topic:
                    if active_only:
                        cursor.execute("""
                            SELECT id, name, description, instruction, topic, is_active, created_at, updated_at
                            FROM signal_instructions 
                            WHERE (topic = ? OR topic IS NULL) AND is_active = TRUE
                            ORDER BY updated_at DESC
                        """, (topic,))
                    else:
                        cursor.execute("""
                            SELECT id, name, description, instruction, topic, is_active, created_at, updated_at
                            FROM signal_instructions 
                            WHERE (topic = ? OR topic IS NULL)
                            ORDER BY updated_at DESC
                        """, (topic,))
                else:
                    if active_only:
                        cursor.execute("""
                            SELECT id, name, description, instruction, topic, is_active, created_at, updated_at
                            FROM signal_instructions 
                            WHERE is_active = TRUE
                            ORDER BY updated_at DESC
                        """)
                    else:
                        cursor.execute("""
                            SELECT id, name, description, instruction, topic, is_active, created_at, updated_at
                            FROM signal_instructions 
                            ORDER BY updated_at DESC
                        """)
                
                results = cursor.fetchall()
                instructions = []
                for row in results:
                    instructions.append({
                        'id': row[0],
                        'name': row[1],
                        'description': row[2],
                        'instruction': row[3],
                        'topic': row[4],
                        'is_active': bool(row[5]),
                        'created_at': row[6],
                        'updated_at': row[7]
                    })
                
                return instructions
            except Exception as e:
                logger.error(f"Error getting signal instructions: {e}")
                return []

    def delete_signal_instruction(self, instruction_id: int) -> bool:
        """Delete a signal instruction."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("DELETE FROM signal_instructions WHERE id = ?", (instruction_id,))
                conn.commit()
                deleted = cursor.rowcount > 0
                if deleted:
                    logger.info(f"Deleted signal instruction ID: {instruction_id}")
                return deleted
            except Exception as e:
                logger.error(f"Error deleting signal instruction: {e}")
                return False

    def save_signal_alert(self, article_uri: str, instruction_id: int, instruction_name: str, 
                         confidence: float, threat_level: str, summary: str, detected_at: str = None) -> bool:
        """Save a signal alert when an article matches a signal instruction."""
        from datetime import datetime
        
        if not detected_at:
            detected_at = datetime.now().isoformat()
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                # Create table if it doesn't exist
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS signal_alerts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        article_uri TEXT NOT NULL,
                        instruction_id INTEGER NOT NULL,
                        instruction_name TEXT NOT NULL,
                        confidence REAL NOT NULL,
                        threat_level TEXT NOT NULL,
                        summary TEXT,
                        detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        is_acknowledged BOOLEAN DEFAULT FALSE,
                        acknowledged_at TIMESTAMP,
                        FOREIGN KEY (instruction_id) REFERENCES signal_instructions(id) ON DELETE CASCADE,
                        UNIQUE(article_uri, instruction_id)
                    )
                """)
                
                # Insert or replace alert
                cursor.execute("""
                    INSERT OR REPLACE INTO signal_alerts 
                    (article_uri, instruction_id, instruction_name, confidence, threat_level, summary, detected_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (article_uri, instruction_id, instruction_name, confidence, threat_level, summary, detected_at))
                
                conn.commit()
                logger.info(f"Saved signal alert for article {article_uri} with instruction {instruction_name}")
                return True
            except Exception as e:
                logger.error(f"Error saving signal alert: {e}")
                conn.rollback()
                return False

    def get_signal_alerts(self, topic: str = None, instruction_id: int = None, 
                         acknowledged: bool = None, limit: int = 100) -> List[Dict]:
        """Get signal alerts with optional filters."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                # Create table if it doesn't exist
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS signal_alerts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        article_uri TEXT NOT NULL,
                        instruction_id INTEGER NOT NULL,
                        instruction_name TEXT NOT NULL,
                        confidence REAL NOT NULL,
                        threat_level TEXT NOT NULL,
                        summary TEXT,
                        detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        is_acknowledged BOOLEAN DEFAULT FALSE,
                        acknowledged_at TIMESTAMP,
                        FOREIGN KEY (instruction_id) REFERENCES signal_instructions(id) ON DELETE CASCADE,
                        UNIQUE(article_uri, instruction_id)
                    )
                """)
                
                # Build query with filters - simplified to avoid JOIN issues
                if topic:
                    # If topic filter is specified, use JOIN
                    query = """
                    SELECT sa.id, sa.article_uri, sa.instruction_id, sa.instruction_name, 
                           sa.confidence, sa.threat_level, sa.summary, sa.detected_at,
                           sa.is_acknowledged, sa.acknowledged_at,
                           a.title, a.news_source, a.publication_date
                    FROM signal_alerts sa
                    LEFT JOIN articles a ON sa.article_uri = a.uri
                    WHERE 1=1
                    """
                    params = []
                    
                    if instruction_id:
                        query += " AND sa.instruction_id = ?"
                        params.append(instruction_id)
                    
                    if acknowledged is not None:
                        query += " AND sa.is_acknowledged = ?"
                        # Convert Python boolean to SQLite integer (0/1)
                        params.append(1 if acknowledged else 0)
                    
                    query += " AND (a.topic = ? OR a.title LIKE ? OR a.summary LIKE ?)"
                    topic_pattern = f"%{topic}%"
                    params.extend([topic, topic_pattern, topic_pattern])
                    
                    query += " ORDER BY sa.detected_at DESC LIMIT ?"
                    params.append(limit)
                else:
                    # If no topic filter, still JOIN to get article details
                    query = """
                    SELECT sa.id, sa.article_uri, sa.instruction_id, sa.instruction_name, 
                           sa.confidence, sa.threat_level, sa.summary, sa.detected_at,
                           sa.is_acknowledged, sa.acknowledged_at,
                           a.title, a.news_source, a.publication_date
                    FROM signal_alerts sa
                    LEFT JOIN articles a ON sa.article_uri = a.uri
                    WHERE 1=1
                    """
                    params = []
                    
                    if instruction_id:
                        query += " AND sa.instruction_id = ?"
                        params.append(instruction_id)
                    
                    if acknowledged is not None:
                        query += " AND sa.is_acknowledged = ?"
                        # Convert Python boolean to SQLite integer (0/1)
                        params.append(1 if acknowledged else 0)
                    
                    query += " ORDER BY sa.detected_at DESC LIMIT ?"
                    params.append(limit)
                
                logger.info(f"Signal alerts query: {query}")
                logger.info(f"Signal alerts params: {params}")
                
                # Debug: Check what's actually in the table
                cursor.execute("SELECT COUNT(*) FROM signal_alerts")
                total_alerts = cursor.fetchone()[0]
                logger.info(f"Total alerts in database: {total_alerts}")
                
                cursor.execute("SELECT id, instruction_name, is_acknowledged FROM signal_alerts ORDER BY detected_at DESC LIMIT 5")
                sample_alerts = cursor.fetchall()
                logger.info(f"Sample alerts: {sample_alerts}")
                
                # Execute the main query
                results = cursor.execute(query, params).fetchall()
                logger.info(f"Signal alerts query returned {len(results)} rows")
                
                alerts = []
                for row in results:
                    alerts.append({
                        'id': row[0],
                        'article_uri': row[1],
                        'instruction_id': row[2],
                        'instruction_name': row[3],
                        'confidence': row[4],
                        'threat_level': row[5],
                        'summary': row[6],
                        'detected_at': row[7],
                        'is_acknowledged': bool(row[8]),
                        'acknowledged_at': row[9],
                        'article_title': row[10],
                        'article_source': row[11],
                        'article_publication_date': row[12]
                    })
                
                return alerts
            except Exception as e:
                logger.error(f"Error getting signal alerts: {e}")
                return []

    def acknowledge_signal_alert(self, alert_id: int) -> bool:
        """Mark a signal alert as acknowledged."""
        from datetime import datetime
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    UPDATE signal_alerts 
                    SET is_acknowledged = TRUE, acknowledged_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (alert_id,))
                
                conn.commit()
                updated = cursor.rowcount > 0
                if updated:
                    logger.info(f"Acknowledged signal alert ID: {alert_id}")
                return updated
            except Exception as e:
                logger.error(f"Error acknowledging signal alert: {e}")
                return False

    def add_article_tag(self, article_uri: str, tag: str, tag_type: str = "signal") -> bool:
        """Add a tag to an article."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                # Get current tags
                cursor.execute("SELECT tags FROM articles WHERE uri = ?", (article_uri,))
                result = cursor.fetchone()
                
                if result:
                    current_tags = result[0] or ""
                    tags_list = [t.strip() for t in current_tags.split(',') if t.strip()] if current_tags else []
                    
                    # Add new tag if not already present
                    tag_with_type = f"{tag_type}:{tag}"
                    if tag_with_type not in tags_list:
                        tags_list.append(tag_with_type)
                        new_tags = ",".join(tags_list)
                        
                        cursor.execute("UPDATE articles SET tags = ? WHERE uri = ?", (new_tags, article_uri))
                        conn.commit()
                        logger.info(f"Added tag '{tag_with_type}' to article {article_uri}")
                        return True
                    else:
                        logger.info(f"Tag '{tag_with_type}' already exists on article {article_uri}")
                        return True
                else:
                    logger.warning(f"Article {article_uri} not found for tagging")
                    return False
            except Exception as e:
                logger.error(f"Error adding article tag: {e}")
                conn.rollback()
                return False

    def create_incident_status_table(self) -> bool:
        """Create the incident status tracking table."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS incident_status (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        incident_name TEXT NOT NULL,
                        topic TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'active',  -- 'active', 'seen', 'deleted'
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(incident_name, topic)
                    )
                """)
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"Error creating incident_status table: {e}")
                return False

    def update_incident_status(self, incident_name: str, topic: str, status: str) -> bool:
        """Update or create incident status."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                # Create table if it doesn't exist
                self.create_incident_status_table()
                
                cursor.execute("""
                    INSERT OR REPLACE INTO incident_status (incident_name, topic, status, updated_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                """, (incident_name, topic, status))
                
                conn.commit()
                logger.info(f"Updated incident status: {incident_name} -> {status}")
                return True
            except Exception as e:
                logger.error(f"Error updating incident status: {e}")
                conn.rollback()
                return False

    def get_incident_status(self, topic: str) -> Dict[str, str]:
        """Get all incident statuses for a topic."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                # Create table if it doesn't exist
                self.create_incident_status_table()
                
                cursor.execute("""
                    SELECT incident_name, status FROM incident_status 
                    WHERE topic = ? AND status != 'deleted'
                """, (topic,))
                
                results = cursor.fetchall()
                return {row[0]: row[1] for row in results}
            except Exception as e:
                logger.error(f"Error getting incident status: {e}")
                return {}

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
        date_field: str = None,  # Add date_field parameter
        require_category: bool = False # New parameter to filter for articles with a category
    ) -> Tuple[List[Dict], int]:
        """Search articles with filters including topic."""
        # Use facade method which has proper SQLAlchemy implementation
        return self.facade.search_articles(
            topic=topic,
            category=category,
            future_signal=future_signal,
            sentiment=sentiment,
            tags=tags,
            keyword=keyword,
            pub_date_start=pub_date_start,
            pub_date_end=pub_date_end,
            page=page,
            per_page=per_page,
            date_type=date_type,
            date_field=date_field,
            require_category=require_category
        )

    def save_report(self, content: str) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO reports (content, created_at) VALUES (?, ?)",
                           (content, datetime.now().isoformat()))
            conn.commit()
            return cursor.lastrowid

    def execute_query(self, query: str, params=None) -> int:
        """Execute a query and return the last inserted row ID (for INSERT operations)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            conn.commit()
            return cursor.lastrowid

    def fetch_one(self, query: str, params=None):
        """Fetch a single row from the database (PostgreSQL-compatible)"""
        from sqlalchemy import text

        conn = self._temp_get_connection()

        try:
            # Convert ? placeholders to PostgreSQL-style if needed
            if self.db_type == 'postgresql' and '?' in query:
                # Convert SQLite-style ? to PostgreSQL-style numbered parameters
                param_count = query.count('?')
                for i in range(1, param_count + 1):
                    query = query.replace('?', f':param{i}', 1)
                # Create named parameters dict
                if params:
                    params_dict = {f'param{i+1}': params[i] for i in range(len(params))}
                else:
                    params_dict = {}
                result = conn.execute(text(query), params_dict)
            else:
                # SQLite path (legacy)
                result = conn.execute(text(query), params or {})

            row = result.fetchone()
            if row:
                # Convert row to dictionary using _mapping for SQLAlchemy Row object
                return dict(row._mapping)
            return None
        except Exception as e:
            conn.rollback()
            logger.error(f"Error in fetch_one: {e}")
            raise

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
        """Fetch all rows from a query (PostgreSQL-compatible)"""
        from sqlalchemy import text

        conn = self._temp_get_connection()

        try:
            # Convert ? placeholders to PostgreSQL-style if needed
            if self.db_type == 'postgresql' and '?' in query:
                # Convert SQLite-style ? to PostgreSQL-style numbered parameters
                param_count = query.count('?')
                for i in range(1, param_count + 1):
                    query = query.replace('?', f':param{i}', 1)
                # Create named parameters dict
                if params:
                    params_dict = {f'param{i+1}': params[i] for i in range(len(params))}
                else:
                    params_dict = {}
                result = conn.execute(text(query), params_dict).mappings()
            else:
                # SQLite path (legacy)
                result = conn.execute(text(query), params or {}).mappings()

            # Convert to list of dicts
            return [dict(row) for row in result]
        except Exception as e:
            conn.rollback()
            logger.error(f"Error in fetch_all: {e}")
            raise

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

    def save_raw_article(self, uri, raw_markdown, topic, create_placeholder=False):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            current_time = datetime.now().isoformat()

            # Ensure parent article exists before saving raw article
            cursor.execute("SELECT uri FROM articles WHERE uri = ?", (uri,))
            if not cursor.fetchone():
                # NEVER create placeholders - article must exist with full data first
                logger.error(f"No article entry found for URI: {uri}. Raw article will not be saved.")
                logger.error("Article must be created with full data (title, summary, etc.) before saving raw content.")
                logger.error(f"create_placeholder parameter ignored: {create_placeholder}")
                raise ValueError(f"No article entry found for URI: {uri} - article must be created first with full data")
            
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
        """
        Get list of all unique topics from articles.

        PostgreSQL-compatible implementation using SQLAlchemy Core.
        Migrated as part of Week 1 PostgreSQL migration (2025-10-13).

        Returns:
            List of topic names (strings)

        Raises:
            Exception: Database errors are logged and re-raised
        """
        from sqlalchemy import select, distinct
        from app.database_models import t_articles

        conn = self._temp_get_connection()

        try:
            stmt = select(distinct(t_articles.c.topic)).where(
                t_articles.c.topic.isnot(None)
            ).order_by(t_articles.c.topic)

            result = conn.execute(stmt).mappings()  # CRITICAL: .mappings() for PostgreSQL

            topics = [row['topic'] for row in result if row['topic']]

            logger.debug(f"Retrieved {len(topics)} topics")
            return topics

        except Exception as e:
            logger.error(f"Error getting topics: {e}")
            conn.rollback()
            raise

    def get_recent_articles_by_topic(self, topic_name, limit=10, start_date=None, end_date=None):
        """
        Get recent articles for a specific topic.

        PostgreSQL-compatible implementation using SQLAlchemy Core.
        Migrated as part of Week 1 PostgreSQL migration (2025-10-13).
        Falls back to facade if available.

        Args:
            topic_name: Topic name to filter by
            limit: Maximum number of articles to return (default: 10)
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            List of article dictionaries ordered by publication_date DESC

        Raises:
            Exception: Database errors are logged and re-raised
        """
        # Try facade first if available (has optimized implementation)
        if hasattr(self, 'facade') and self.facade:
            try:
                return self.facade.get_articles_by_topic(topic_name, limit=limit)
            except Exception as e:
                logger.warning(f"Facade method failed, using direct query: {e}")

        # Fallback to direct query
        from sqlalchemy import select, or_, func
        from app.database_models import t_articles

        conn = self._temp_get_connection()

        try:
            # Build base query
            stmt = select(t_articles).where(t_articles.c.topic == topic_name)

            # Add date filters if provided
            if start_date or end_date:
                date_col = func.coalesce(t_articles.c.submission_date, t_articles.c.publication_date)
                if start_date:
                    stmt = stmt.where(date_col >= start_date)
                if end_date:
                    stmt = stmt.where(date_col <= end_date)

            # Order and limit
            stmt = stmt.order_by(
                func.coalesce(t_articles.c.submission_date, t_articles.c.publication_date).desc()
            ).limit(limit)

            result = conn.execute(stmt).mappings()  # CRITICAL: .mappings() for PostgreSQL
            articles = [dict(row) for row in result]

            # Convert tags string back to list
            for article in articles:
                if article.get('tags'):
                    article['tags'] = article['tags'].split(',')
                else:
                    article['tags'] = []

            logger.debug(f"Retrieved {len(articles)} articles for topic: {topic_name}")
            return articles

        except Exception as e:
            logger.error(f"Error getting articles for topic '{topic_name}': {e}")
            conn.rollback()
            raise

    def get_article_count_by_topic(self, topic_name: str) -> int:
        """
        Get count of articles for a specific topic.

        PostgreSQL-compatible implementation using SQLAlchemy Core.
        Migrated as part of Week 1 PostgreSQL migration (2025-10-13).

        Args:
            topic_name: Topic name to count articles for

        Returns:
            Number of articles (integer)

        Raises:
            Exception: Database errors are logged and re-raised
        """
        from sqlalchemy import select, func
        from app.database_models import t_articles

        conn = self._temp_get_connection()

        try:
            stmt = select(func.count()).select_from(t_articles).where(
                t_articles.c.topic == topic_name
            )

            result = conn.execute(stmt)
            count = result.scalar() or 0

            logger.debug(f"Article count for topic '{topic_name}': {count}")
            return count

        except Exception as e:
            logger.error(f"Error getting article count for topic '{topic_name}': {e}")
            conn.rollback()
            raise

    def get_latest_article_date_by_topic(self, topic_name: str) -> Optional[str]:
        """
        Get latest article publication date for a topic.

        PostgreSQL-compatible implementation using SQLAlchemy Core.
        Migrated as part of Week 1 PostgreSQL migration (2025-10-13).

        Args:
            topic_name: Topic name to get latest date for

        Returns:
            Latest publication date (string) or None if no articles

        Raises:
            Exception: Database errors are logged and re-raised
        """
        from sqlalchemy import select, func
        from app.database_models import t_articles
        from typing import Optional

        conn = self._temp_get_connection()

        try:
            # Get MAX of COALESCE(submission_date, publication_date)
            date_col = func.coalesce(t_articles.c.submission_date, t_articles.c.publication_date)
            stmt = select(func.max(date_col)).where(t_articles.c.topic == topic_name)

            result = conn.execute(stmt)
            latest_date = result.scalar()

            logger.debug(f"Latest article date for topic '{topic_name}': {latest_date}")
            return latest_date

        except Exception as e:
            logger.error(f"Error getting latest article date for topic '{topic_name}': {e}")
            conn.rollback()
            raise

    def delete_topic(self, topic_name: str) -> bool:
        """
        Delete a topic and all its associated data from the database.

        PostgreSQL-compatible implementation using SQLAlchemy Core.
        Migrated as part of Week 1 PostgreSQL migration (2025-10-13).

        Args:
            topic_name: Name of topic to delete

        Returns:
            True if topic deleted successfully

        Raises:
            Exception: Database errors are logged and re-raised
        """
        from sqlalchemy import delete
        from app.database_models import t_articles, t_raw_articles

        conn = self._temp_get_connection()

        try:
            # Delete articles associated with the topic
            stmt_articles = delete(t_articles).where(t_articles.c.topic == topic_name)
            result_articles = conn.execute(stmt_articles)
            logger.info(f"Deleted {result_articles.rowcount} articles for topic '{topic_name}'")

            # Delete raw articles associated with the topic
            stmt_raw = delete(t_raw_articles).where(t_raw_articles.c.topic == topic_name)
            result_raw = conn.execute(stmt_raw)
            logger.info(f"Deleted {result_raw.rowcount} raw articles for topic '{topic_name}'")

            # Commit all changes
            conn.commit()

            logger.info(f"Topic deleted successfully: {topic_name}")
            return True

        except Exception as e:
            logger.error(f"Error deleting topic '{topic_name}': {e}")
            conn.rollback()
            raise

    def get_user(self, username: str):
        """
        Get user by username for authentication.

        PostgreSQL-compatible implementation using SQLAlchemy Core.
        Migrated as part of Week 1 PostgreSQL migration (2025-10-13).

        Args:
            username: Username to retrieve

        Returns:
            Dict with user data or None if not found

        Raises:
            Exception: Database errors are logged and re-raised
        """
        from sqlalchemy import select
        from app.database_models import t_users

        conn = self._temp_get_connection()

        try:
            stmt = select(
                t_users.c.username,
                t_users.c.password_hash,
                t_users.c.force_password_change,
                t_users.c.completed_onboarding
            ).where(t_users.c.username == username)

            result = conn.execute(stmt).mappings()  # CRITICAL: .mappings() for PostgreSQL
            row = result.fetchone()

            if row:
                return {
                    'username': row['username'],
                    'password': row['password_hash'],  # Keep the key as 'password' for compatibility
                    'force_password_change': bool(row['force_password_change']),
                    'completed_onboarding': bool(row['completed_onboarding'])
                }

            return None

        except Exception as e:
            logger.error(f"Error getting user '{username}': {e}")
            conn.rollback()
            raise

    def update_user_password(self, username: str, new_password: str) -> bool:
        """
        Update user password and clear force_password_change flag.

        PostgreSQL-compatible implementation using SQLAlchemy Core.
        Migrated as part of Week 1 PostgreSQL migration (2025-10-13).

        Args:
            username: Username to update
            new_password: New plain text password (will be hashed)

        Returns:
            True if password updated, False if user not found

        Raises:
            Exception: Database errors are logged and re-raised
        """
        from sqlalchemy import update
        from app.database_models import t_users

        # Hash new password
        password_hash = get_password_hash(new_password)

        conn = self._temp_get_connection()

        try:
            stmt = update(t_users).where(
                t_users.c.username == username
            ).values(
                password_hash=password_hash,
                force_password_change=False
            )

            result = conn.execute(stmt)
            conn.commit()

            if result.rowcount > 0:
                logger.info(f"Password updated successfully for user: {username}")
                return True
            else:
                logger.warning(f"Password update failed - user not found: {username}")
                return False

        except Exception as e:
            logger.error(f"Error updating password for user '{username}': {e}")
            conn.rollback()
            raise

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
        """
        Create a new user account with hashed password.

        PostgreSQL-compatible implementation using SQLAlchemy Core.
        Migrated as part of Week 1 PostgreSQL migration (2025-10-13).

        Args:
            username: Unique username
            password_hash: Pre-hashed password
            force_password_change: Whether to force password change on next login

        Returns:
            True if user created successfully

        Raises:
            IntegrityError: If username already exists
            Exception: Other database errors
        """
        from sqlalchemy import insert
        from sqlalchemy.exc import IntegrityError
        from app.database_models import t_users

        conn = self._temp_get_connection()

        try:
            stmt = insert(t_users).values(
                username=username,
                password_hash=password_hash,
                force_password_change=force_password_change,
                completed_onboarding=False
            )

            conn.execute(stmt)
            conn.commit()

            logger.info(f"User created successfully: {username}")
            return True

        except IntegrityError as e:
            logger.warning(f"User creation failed - username already exists: {username}")
            conn.rollback()
            raise ValueError(f"Username '{username}' already exists")

        except Exception as e:
            logger.error(f"Error creating user '{username}': {e}")
            conn.rollback()
            raise

    def update_user_onboarding(self, username, completed):
        """
        Update user onboarding completion status.

        PostgreSQL-compatible implementation using SQLAlchemy Core.
        Migrated as part of Week 1 PostgreSQL migration (2025-10-13).

        Args:
            username: Username to update
            completed: Whether onboarding is completed (True/False)

        Returns:
            True if updated, False if user not found

        Raises:
            Exception: Database errors are logged and re-raised
        """
        from sqlalchemy import update
        from app.database_models import t_users

        conn = self._temp_get_connection()

        try:
            stmt = update(t_users).where(
                t_users.c.username == username
            ).values(
                completed_onboarding=completed
            )

            result = conn.execute(stmt)
            conn.commit()

            if result.rowcount > 0:
                logger.info(f"Onboarding status updated for user: {username} (completed={completed})")
                return True
            else:
                logger.warning(f"Onboarding update failed - user not found: {username}")
                return False

        except Exception as e:
            logger.error(f"Error updating onboarding for user '{username}': {e}")
            conn.rollback()
            raise

    def set_force_password_change(self, username: str, force: bool = True) -> bool:
        """
        Set or clear force password change flag for user.

        PostgreSQL-compatible implementation using SQLAlchemy Core.
        Migrated as part of Week 1 PostgreSQL migration (2025-10-13).

        Args:
            username: Username to update
            force: Whether to force password change (default: True)

        Returns:
            True if updated, False if user not found

        Raises:
            Exception: Database errors are logged and re-raised
        """
        from sqlalchemy import update
        from app.database_models import t_users

        conn = self._temp_get_connection()

        try:
            stmt = update(t_users).where(
                t_users.c.username == username
            ).values(
                force_password_change=force
            )

            result = conn.execute(stmt)
            conn.commit()

            if result.rowcount > 0:
                logger.info(f"Force password change flag set for user: {username} (force={force})")
                return True
            else:
                logger.warning(f"Force password change update failed - user not found: {username}")
                return False

        except Exception as e:
            logger.error(f"Error setting force password change for user '{username}': {e}")
            conn.rollback()
            raise

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
        """Get total article count - works with both SQLite and PostgreSQL"""
        from sqlalchemy import select, func
        from app.database_models import t_articles

        conn = self._temp_get_connection()
        try:
            statement = select(func.count()).select_from(t_articles)
            result = conn.execute(statement)
            return result.scalar() or 0
        except Exception as e:
            logger.error(f"Error getting total articles: {e}")
            return 0

    async def get_articles_today(self) -> int:
        """Get articles added today - works with both SQLite and PostgreSQL"""
        from sqlalchemy import select, func, cast, Date
        from app.database_models import t_articles

        conn = self._temp_get_connection()
        try:
            today = datetime.now().date()
            statement = select(func.count()).select_from(t_articles).where(
                cast(t_articles.c.submission_date, Date) == today
            )
            result = conn.execute(statement)
            return result.scalar() or 0
        except Exception as e:
            logger.error(f"Error getting articles today: {e}")
            return 0

    async def get_keyword_group_count(self) -> int:
        """Get keyword group count - works with both SQLite and PostgreSQL"""
        from sqlalchemy import select, func
        from app.database_models import t_keyword_groups

        conn = self._temp_get_connection()
        try:
            statement = select(func.count()).select_from(t_keyword_groups)
            result = conn.execute(statement)
            return result.scalar() or 0
        except Exception as e:
            logger.error(f"Error getting keyword group count: {e}")
            return 0

    async def get_topic_count(self) -> int:
        """Get distinct topic count - works with both SQLite and PostgreSQL"""
        from sqlalchemy import select, func
        from app.database_models import t_articles

        conn = self._temp_get_connection()
        try:
            statement = select(func.count(func.distinct(t_articles.c.topic))).select_from(t_articles)
            result = conn.execute(statement)
            return result.scalar() or 0
        except Exception as e:
            logger.error(f"Error getting topic count: {e}")
            return 0

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
        """Delete multiple articles using PostgreSQL-compatible SQLAlchemy Core."""
        if not uris:
            logger.warning("No URIs provided for bulk delete")
            return 0

        logger.info(f"Attempting to bulk delete {len(uris)} articles")
        decoded_uris = [unquote_plus(unquote_plus(uri)) for uri in uris]

        try:
            from sqlalchemy import delete
            from app.database_models import (
                t_articles, t_raw_articles, t_keyword_article_matches,
                t_article_annotations
            )

            # Use SQLAlchemy connection for PostgreSQL compatibility
            conn = self._temp_get_connection()

            logger.debug(f"First few URIs to delete: {decoded_uris[:3]}")

            # Check if we're already in a transaction
            # If yes, use a nested transaction (savepoint), otherwise start a new one
            try:
                if conn.in_transaction():
                    logger.debug("Using nested transaction (savepoint)")
                    trans = conn.begin_nested()
                else:
                    logger.debug("Starting new transaction")
                    trans = conn.begin()
            except Exception as trans_error:
                logger.warning(f"Could not begin transaction: {trans_error}, continuing without explicit transaction")
                trans = None

            try:
                deleted_count = 0

                # Delete from keyword_article_matches (new keyword alerts table)
                try:
                    stmt = delete(t_keyword_article_matches).where(
                        t_keyword_article_matches.c.article_uri.in_(decoded_uris)
                    )
                    result = conn.execute(stmt)
                    logger.debug(f"Deleted {result.rowcount} keyword article matches")
                except Exception as e:
                    logger.debug(f"No keyword_article_matches deleted (table may not exist or no matches): {e}")

                # Delete from article_annotations
                try:
                    stmt = delete(t_article_annotations).where(
                        t_article_annotations.c.article_uri.in_(decoded_uris)
                    )
                    result = conn.execute(stmt)
                    logger.debug(f"Deleted {result.rowcount} annotations")
                except Exception as e:
                    logger.debug(f"No annotations deleted: {e}")

                # Delete from raw_articles
                try:
                    stmt = delete(t_raw_articles).where(
                        t_raw_articles.c.uri.in_(decoded_uris)
                    )
                    result = conn.execute(stmt)
                    logger.debug(f"Deleted {result.rowcount} raw articles")
                except Exception as e:
                    logger.debug(f"No raw articles deleted: {e}")

                # Finally delete the articles
                stmt = delete(t_articles).where(
                    t_articles.c.uri.in_(decoded_uris)
                )
                result = conn.execute(stmt)
                deleted_count = result.rowcount
                logger.debug(f"Deleted {deleted_count} articles")

                # Commit transaction if we have one
                if trans is not None:
                    trans.commit()
                    logger.debug("Transaction committed")

                logger.info(f"Successfully deleted {deleted_count} articles")
                return deleted_count

            except Exception as e:
                # Rollback transaction if we have one
                if trans is not None:
                    trans.rollback()
                    logger.error(f"Transaction rolled back due to error: {e}")
                else:
                    logger.error(f"Error during deletion (no transaction to rollback): {e}")
                raise

        except Exception as e:
            logger.error(f"Error in bulk_delete_articles: {e}")
            raise

    def create_topic(self, topic_name: str) -> bool:
        """
        Create a new topic by adding an initial placeholder article.

        PostgreSQL-compatible implementation using SQLAlchemy Core.
        Migrated as part of Week 1 PostgreSQL migration (2025-10-13).

        Note: This method creates a placeholder article to register the topic.
        The actual topic metadata should be managed in config.json (Phase 0).

        Args:
            topic_name: Unique name for the topic

        Returns:
            True if topic created successfully

        Raises:
            Exception: Database errors are logged and re-raised
        """
        from sqlalchemy import insert
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from app.database_models import t_articles
        from datetime import datetime

        conn = self._temp_get_connection()

        try:
            # Create initial placeholder article for the topic
            # Use INSERT ... ON CONFLICT DO NOTHING for both SQLite and PostgreSQL
            if self.db_type == 'postgresql':
                # PostgreSQL: Use ON CONFLICT DO NOTHING
                stmt = pg_insert(t_articles).values(
                    topic=topic_name,
                    title='Topic Created',
                    uri='initial',
                    submission_date=datetime.now()
                ).on_conflict_do_nothing()
            else:
                # SQLite: Use INSERT OR IGNORE (handled in SQLAlchemy)
                stmt = insert(t_articles).prefix_with('OR IGNORE').values(
                    topic=topic_name,
                    title='Topic Created',
                    uri='initial',
                    submission_date=datetime.now()
                )

            conn.execute(stmt)
            conn.commit()

            logger.info(f"Topic created successfully: {topic_name}")
            return True

        except Exception as e:
            logger.error(f"Error creating topic '{topic_name}': {e}")
            conn.rollback()
            raise

    def update_topic(self, topic_name: str) -> bool:
        """
        Update topic metadata (currently verifies/creates topic).

        PostgreSQL-compatible implementation using SQLAlchemy Core.
        Migrated as part of Week 1 PostgreSQL migration (2025-10-13).

        Args:
            topic_name: Name of topic to update

        Returns:
            True if topic exists or was created

        Raises:
            Exception: Database errors are logged and re-raised
        """
        from sqlalchemy import select, func
        from app.database_models import t_articles

        conn = self._temp_get_connection()

        try:
            # Check if topic exists
            stmt = select(func.count()).select_from(t_articles).where(
                t_articles.c.topic == topic_name
            )

            result = conn.execute(stmt)
            count = result.scalar()

            if count == 0:
                # If topic doesn't exist, create it
                logger.info(f"Topic '{topic_name}' not found, creating...")
                return self.create_topic(topic_name)

            logger.debug(f"Topic '{topic_name}' exists with {count} articles")
            return True

        except Exception as e:
            logger.error(f"Error updating topic '{topic_name}': {e}")
            conn.rollback()
            raise

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

    # TODO: Potentially not used.
    def create_ontology_tables(self):
        """Ensure tables for BuildingBlocks, Scenarios and their M2M link exist."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

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

            # TODO: Move to migrations.
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

    # ------------------------------------------------------------------
    # Podcast settings helpers – key/value access
    # ------------------------------------------------------------------

    def get_podcast_setting(self, key: str):
        """Return the raw JSON string stored for *key* in settings_podcasts.
        If the key is not present, return ``None``.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings_podcasts WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row[0] if row else None

    def set_podcast_setting(self, key: str, value: str) -> bool:
        """Insert or update the given *key* with *value* in settings_podcasts.
        The *value* should be a JSON-serialised string.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO settings_podcasts (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )
            conn.commit()
            return True

    def get_podcast_settings(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM settings_podcasts LIMIT 1")
            settings = cursor.fetchone()
            
            if settings:
                columns = [col[0] for col in cursor.description]
                return dict(zip(columns, settings))
            else:
                # Default settings if none exist
                return {
                    "id": 1,
                    "podcast_enabled": 0,
                    "transcribe_enabled": 1,
                    "openai_model": "whisper-1",
                    "transcript_format": "text",
                    "uploads_folder": "podcast_uploads",
                    "output_folder": "podcasts"
                }

    # Auspex Chat Management Methods
    def create_auspex_chat(self, topic: str, title: str = None, user_id: str = None, profile_id: int = None, metadata: dict = None) -> int:
        """Create a new Auspex chat session with optional organizational profile."""
        return self.facade.create_auspex_chat(topic, title, user_id, profile_id, metadata)

    def update_auspex_chat_profile(self, chat_id: int, profile_id: int) -> bool:
        """Update an existing chat session with a profile_id."""
        return self.facade.update_auspex_chat_profile(chat_id, profile_id)

    def get_auspex_chats(self, topic: str = None, user_id: str = None, limit: int = 50) -> List[Dict]:
        """Get Auspex chat sessions with message counts from PostgreSQL."""
        # Use facade to query PostgreSQL, not SQLite
        return self.facade.get_auspex_chats(topic=topic, user_id=user_id, limit=limit)

    def get_auspex_chat(self, chat_id: int) -> Optional[Dict]:
        """Get a specific Auspex chat."""
        return self.facade.get_auspex_chat(chat_id)

    def update_auspex_chat(self, chat_id: int, title: str = None, metadata: dict = None) -> bool:
        """Update an Auspex chat."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            updates = []
            params = []
            
            if title is not None:
                updates.append("title = ?")
                params.append(title)
            if metadata is not None:
                updates.append("metadata = ?")
                params.append(json.dumps(metadata))
                
            if not updates:
                return True
                
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(chat_id)
            
            query = f"UPDATE auspex_chats SET {', '.join(updates)} WHERE id = ?"
            cursor.execute(query, params)
            conn.commit()
            return cursor.rowcount > 0

    def delete_auspex_chat(self, chat_id: int) -> bool:
        """Delete an Auspex chat and all its messages."""
        return self.facade.delete_auspex_chat(chat_id)

    def add_auspex_message(self, chat_id: int, role: str, content: str,
                          model_used: str = None, tokens_used: int = None,
                          metadata: dict = None) -> int:
        """Add a message to an Auspex chat."""
        return self.facade.add_auspex_message(chat_id, role, content, model_used, tokens_used, metadata)

    def get_auspex_messages(self, chat_id: int) -> List[Dict]:
        """Get all messages for an Auspex chat."""
        return self.facade.get_auspex_messages(chat_id)

    # Auspex Prompt Management Methods
    def create_auspex_prompt(self, name: str, title: str, content: str,
                           description: str = None, is_default: bool = False,
                           user_created: str = None) -> int:
        """Create a new Auspex prompt template."""
        return self.facade.create_auspex_prompt(name, title, content, description, is_default, user_created)

    def get_auspex_prompts(self) -> List[Dict]:
        """Get all Auspex prompt templates."""
        return self.facade.get_all_auspex_prompts()

    def get_auspex_prompt(self, name: str) -> Optional[Dict]:
        """Get a specific Auspex prompt by name."""
        return self.facade.get_auspex_prompt(name)

    def update_auspex_prompt(self, name: str, title: str = None, content: str = None,
                           description: str = None) -> bool:
        """Update an Auspex prompt template."""
        return self.facade.update_auspex_prompt(name, title, content, description)

    def delete_auspex_prompt(self, name: str) -> bool:
        """Delete an Auspex prompt template."""
        return self.facade.delete_auspex_prompt(name)

    def get_default_auspex_prompt(self) -> Optional[Dict]:
        """Get the default Auspex system prompt."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, name, title, content, description, is_default, created_at, updated_at, user_created
                FROM auspex_prompts 
                WHERE is_default = 1
                LIMIT 1
            """)
            
            row = cursor.fetchone()
            if not row:
                return None
                
            return {
                'id': row[0],
                'name': row[1],
                'title': row[2],
                'content': row[3],
                'description': row[4],
                'is_default': bool(row[5]),
                'created_at': row[6],
                'updated_at': row[7],
                'user_created': row[8]
            }

    def upsert_vantage_desk_filters(self, user_key: str, group_id: int = None, **filters) -> int:
        """
        Insert or update a user's Vantage Desk filter preset.
        The unique key is (user_key, group_id) where group_id may be NULL.
        Returns the row id.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Encode JSON-able field source_date_combinations
            if 'source_date_combinations' in filters and isinstance(filters['source_date_combinations'], (list, dict)):
                filters['source_date_combinations'] = json.dumps(filters['source_date_combinations'])

            # Prepare placeholders and update params for update query
            placeholders = ", ".join([f"{k} = ?" for k in filters.keys()])
            update_params = [v for k, v in filters.items()]

            # Add user_key and group_id to filters for insert query
            filters['user_key'] = user_key
            filters['group_id'] = group_id
            
            # Prepare placeholders and insert params for insert query
            insert_cols = ", ".join(filters.keys())
            insert_values = ", ".join(["?" for _ in filters.keys()])
            insert_params = list(filters.values())

            # Try UPDATE first
            cursor.execute(
                f"UPDATE vantage_desk_filters SET {placeholders} WHERE user_key = ? AND group_id IS ?",
                update_params + [user_key, group_id]
            )
            
            if cursor.rowcount == 0:
                # Insert if no rows were updated
                cursor.execute(
                    f"INSERT INTO vantage_desk_filters ({insert_cols}) VALUES ({insert_values})",
                    insert_params
                )
                conn.commit()
                return cursor.lastrowid
            else:
                # Get the id of the updated row
                cursor.execute(
                    "SELECT id FROM vantage_desk_filters WHERE user_key = ? AND group_id IS ?",
                    (user_key, group_id)
                )
                result = cursor.fetchone()
                conn.commit()
                return result[0] if result else None

    def get_vantage_desk_filters(self, user_key: str, group_id: int = None) -> Optional[Dict]:
        """Retrieve the saved filter preset for a user (and optionally a specific group)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM vantage_desk_filters WHERE user_key = ? AND group_id IS ? LIMIT 1",
                (user_key, group_id)
            )
            row = cursor.fetchone()
            if not row:
                return None
            columns = [desc[0] for desc in cursor.description]
            result = dict(zip(columns, row))

            # Try to decode json column source_date_combinations
            if result.get('source_date_combinations'):
                try:
                    result['source_date_combinations'] = json.loads(result['source_date_combinations'])
                except json.JSONDecodeError:
                    pass
            return result

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


