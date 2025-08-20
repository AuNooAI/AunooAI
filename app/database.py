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
        """Get a thread-local database connection with optimized settings"""
        thread_id = threading.get_ident()
        
        if thread_id not in self._connections:
            try:
                self._connections[thread_id] = sqlite3.connect(self.db_path)
                
                # Enable foreign key support
                self._connections[thread_id].execute("PRAGMA foreign_keys = ON")
                
                # Optimize for concurrent operations - with error handling
                try:
                    self._connections[thread_id].execute("PRAGMA journal_mode = WAL")  # Write-Ahead Logging
                except sqlite3.DatabaseError as e:
                    logger.error(f"Failed to set WAL mode: {e}")
                    logger.error("Database may be corrupted. Run scripts/fix_database_corruption.py to repair.")
                    raise
                    
                self._connections[thread_id].execute("PRAGMA synchronous = NORMAL")  # Balance safety and speed
                self._connections[thread_id].execute("PRAGMA cache_size = 10000")  # 10MB cache
                self._connections[thread_id].execute("PRAGMA temp_store = MEMORY")  # Store temp data in memory
                self._connections[thread_id].execute("PRAGMA busy_timeout = 30000")  # 30 second timeout
                
            except sqlite3.DatabaseError as e:
                logger.error(f"Database connection failed: {e}")
                logger.error(f"Database path: {self.db_path}")
                logger.error("This usually indicates database corruption.")
                logger.error("To fix: python scripts/fix_database_corruption.py")
                raise
            
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
            
            # Create vantage desk filters table
            self.create_vantage_desk_filters_table()
            
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
            
            # Create auspex_chats table for chat persistence
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS auspex_chats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic TEXT NOT NULL,
                    title TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    user_id TEXT,
                    metadata TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(username) ON DELETE SET NULL
                )
            """)
            
            # Create auspex_messages table for individual messages
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS auspex_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
                    content TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    model_used TEXT,
                    tokens_used INTEGER,
                    metadata TEXT,
                    FOREIGN KEY (chat_id) REFERENCES auspex_chats(id) ON DELETE CASCADE
                )
            """)
            
            # Create auspex_prompts table for editable system prompts
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS auspex_prompts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    description TEXT,
                    is_default BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    user_created TEXT,
                    FOREIGN KEY (user_created) REFERENCES users(username) ON DELETE SET NULL
                )
            """)
            
            conn.commit()
            
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
            
            # Add indexes for better performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_auspex_chats_topic ON auspex_chats(topic)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_auspex_chats_user_id ON auspex_chats(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_auspex_messages_chat_id ON auspex_messages(chat_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_auspex_messages_role ON auspex_messages(role)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_auspex_prompts_name ON auspex_prompts(name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_auspex_prompts_is_default ON auspex_prompts(is_default)")
            
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
                    ("add_metadata_column_to_podcasts", self._add_metadata_column_to_podcasts),
                    ("create_newsletter_prompts_table", self._create_newsletter_prompts_table),
                    ("add_relevance_columns_to_articles", self._add_relevance_columns_to_articles),
                    ("add_auto_ingest_columns", self._add_auto_ingest_columns)
                ]
                
                # Apply migrations that haven't been applied yet
                for name, callback in migrations:
                    if name not in applied:
                        try:
                            callback(cursor)
                            cursor.execute("INSERT INTO migrations (name) VALUES (?)", (name,))
                            logger.info(f"Applied migration: {name}")
                        except Exception as migration_error:
                            logger.error(f"Error applying migration {name}: {str(migration_error)}")
                            raise
                
                # Commit all migrations
                conn.commit()
                
        except Exception as e:
            logger.error(f"Database migration failed: {str(e)}")
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

    def _create_newsletter_prompts_table(self, cursor):
        """Create the newsletter_prompts table to store prompt templates."""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS newsletter_prompts (
                content_type_id TEXT PRIMARY KEY,
                prompt_template TEXT NOT NULL,
                description TEXT NOT NULL,
                last_updated TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Insert default prompts for each content type
        default_prompts = [
            (
                "topic_summary",
                self._get_default_summary_prompt_template(),
                "Prompt template for generating topic summaries with recent developments and citations"
            ),
            (
                "trend_analysis",
                self._get_default_trend_analysis_prompt_template(),
                "Prompt template for analyzing trends, patterns, and signals from article metadata"
            ),
            (
                "article_insights",
                self._get_default_article_insights_prompt_template(),
                "Prompt template for grouping articles by themes and providing insights on each theme"
            ),
            (
                "key_articles",
                self._get_default_key_articles_prompt_template(),
                "Prompt template for explaining why specific articles merit attention"
            ),
            (
                "ethical_societal_impact",
                self._get_default_ethical_impact_prompt_template(),
                "Prompt template for analyzing ethical and societal impacts related to a topic"
            ),
            (
                "business_impact",
                self._get_default_business_impact_prompt_template(),
                "Prompt template for analyzing business opportunities and impacts related to a topic"
            ),
            (
                "market_impact",
                self._get_default_market_impact_prompt_template(),
                "Prompt template for analyzing market trends and competitive landscape"
            ),
            (
                "key_charts",
                self._get_default_key_charts_prompt_template(),
                "Prompt template for generating chart descriptions and insights for data visualizations"
            ),
            (
                "latest_podcast",
                self._get_default_podcast_prompt_template(),
                "Prompt template for summarizing podcast content related to the topic"
            )
        ]
        
        # Check which prompts already exist
        cursor.execute("SELECT content_type_id FROM newsletter_prompts")
        existing_types = {row[0] for row in cursor.fetchall()}
        
        # Insert only those prompts that don't exist
        for prompt in default_prompts:
            if prompt[0] not in existing_types:
                cursor.execute(
                    """
                    INSERT INTO newsletter_prompts (content_type_id, prompt_template, description)
                    VALUES (?, ?, ?)
                    """,
                    prompt
                )
        
        # Commit changes
        cursor.connection.commit()

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
            
    def save_article(self, article_data):
        """Save article to database.
        
        Handles both new articles and updates to existing ones.
        Supports the new media bias fields.
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Check if article already exists
            cursor.execute("SELECT uri FROM articles WHERE uri = ?", (article_data['uri'],))
            existing = cursor.fetchone()
            
            # Define all possible fields, including media bias fields
            all_fields = [
                'uri', 'title', 'news_source', 'summary', 'sentiment', 
                'time_to_impact', 'category', 'future_signal', 
                'future_signal_explanation', 'publication_date', 
                'submission_date', 'topic', 'sentiment_explanation', 
                'time_to_impact_explanation', 'tags', 'driver_type', 
                'driver_type_explanation', 'analyzed',
                # Media bias fields
                'bias', 'factual_reporting', 'mbfc_credibility_rating',
                'bias_source', 'bias_country', 'press_freedom', 
                'media_type', 'popularity',
                # Relevance score fields
                'topic_alignment_score', 'keyword_relevance_score', 
                'confidence_score', 'overall_match_explanation',
                'extracted_article_topics', 'extracted_article_keywords'
            ]

            # Filter fields that exist in the article_data
            fields = [f for f in all_fields if f in article_data]
            
            # Convert tags list to string if necessary
            if 'tags' in article_data and isinstance(article_data['tags'], list):
                article_data['tags'] = ','.join(article_data['tags'])
            
            # Either update or insert
            if existing:
                # Build set statements for SQL
                set_clauses = [f"{field} = ?" for field in fields if field != 'uri']
                values = [article_data[field] for field in fields if field != 'uri']
                values.append(article_data['uri'])  # For the WHERE clause
                
                # Execute update
                sql = f"UPDATE articles SET {', '.join(set_clauses)} WHERE uri = ?"
                cursor.execute(sql, values)
            else:
                # Build insert statement
                placeholders = ", ".join(["?"] * len(fields))
                values = [article_data[field] for field in fields]
                
                # Execute insert
                sql = f"INSERT INTO articles ({', '.join(fields)}) VALUES ({placeholders})"
                cursor.execute(sql, values)
            
            conn.commit()
            return {"success": True, "uri": article_data['uri']}
        except Exception as e:
            conn.rollback()
            logging.error(f"Error in save_article: {str(e)}")
            raise
        finally:
            cursor.close()

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
        date_field: str = None,  # Add date_field parameter
        require_category: bool = False # New parameter to filter for articles with a category
    ) -> Tuple[List[Dict], int]:
        """Search articles with filters including topic."""
        query_conditions = []
        params = []

        # Use the appropriate date field based on date_type
        date_field_to_use = 'publication_date' if date_type == 'publication' else 'submission_date'
        # Override with date_field if explicitly provided (for backward compatibility or specific needs)
        if date_field:
            date_field_to_use = date_field

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
            query_conditions.append(f"{date_field_to_use} >= ?")  # Use the selected date field
            params.append(pub_date_start)

        if pub_date_end:
            query_conditions.append(f"{date_field_to_use} <= ?")  # Use the selected date field
            params.append(pub_date_end)

        # Add filter for requiring a category if specified
        if require_category:
            query_conditions.append("category IS NOT NULL AND category != ''")

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
            
            # Ensure parent article exists before saving raw article
            cursor.execute("SELECT uri FROM articles WHERE uri = ?", (uri,))
            if not cursor.fetchone():
                logger.warning(f"No article entry found for URI: {uri}. Raw article will not be saved.")
                logger.warning("This means content extraction may have failed. Check extraction logic.")
                # Don't create placeholder - let the calling code handle content extraction first
                return {"error": "No article entry found - content extraction may have failed"}
            
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

    def _add_relevance_columns_to_articles(self, cursor):
        """Add relevance columns to articles table if they don't exist."""
        try:
            cursor.execute("ALTER TABLE articles ADD COLUMN relevance_score REAL")
            logger.info("Added relevance_score column to articles table")
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        try:
            cursor.execute("ALTER TABLE articles ADD COLUMN relevance_reason TEXT")
            logger.info("Added relevance_reason column to articles table")
        except sqlite3.OperationalError:
            pass  # Column already exists

    def _add_auto_ingest_columns(self, cursor):
        """Add auto-ingest columns to articles and keyword_monitor_settings tables."""
        # Add auto-ingest columns to articles table
        auto_ingest_article_columns = [
            ("auto_ingested", "BOOLEAN DEFAULT FALSE"),
            ("ingest_status", "TEXT"),
            ("quality_score", "REAL"),
            ("quality_issues", "TEXT")
        ]
        
        for column_name, column_def in auto_ingest_article_columns:
            try:
                cursor.execute(f"ALTER TABLE articles ADD COLUMN {column_name} {column_def}")
                logger.info(f"Added {column_name} column to articles table")
            except sqlite3.OperationalError:
                pass  # Column already exists
        
        # Add auto-ingest settings to keyword_monitor_settings table
        auto_ingest_settings_columns = [
            ("auto_ingest_enabled", "BOOLEAN NOT NULL DEFAULT FALSE"),
            ("min_relevance_threshold", "REAL NOT NULL DEFAULT 0.0"),
            ("quality_control_enabled", "BOOLEAN NOT NULL DEFAULT TRUE"),
            ("auto_save_approved_only", "BOOLEAN NOT NULL DEFAULT FALSE"),
            ("default_llm_model", "TEXT NOT NULL DEFAULT 'gpt-4o-mini'"),
            ("llm_temperature", "REAL NOT NULL DEFAULT 0.1"),
            ("llm_max_tokens", "INTEGER NOT NULL DEFAULT 1000")
        ]
        
        for column_name, column_def in auto_ingest_settings_columns:
            try:
                cursor.execute(f"ALTER TABLE keyword_monitor_settings ADD COLUMN {column_name} {column_def}")
                logger.info(f"Added {column_name} column to keyword_monitor_settings table")
            except sqlite3.OperationalError:
                pass  # Column already exists
        
        # Create indexes for better performance
        try:
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_articles_auto_ingested ON articles(auto_ingested)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_articles_ingest_status ON articles(ingest_status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_articles_quality_score ON articles(quality_score)")
            logger.info("Created auto-ingest indexes on articles table")
        except sqlite3.OperationalError:
            pass  # Indexes already exist

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
    def create_auspex_chat(self, topic: str, title: str = None, user_id: str = None, metadata: dict = None) -> int:
        """Create a new Auspex chat session."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            metadata_json = json.dumps(metadata) if metadata else None
            cursor.execute("""
                INSERT INTO auspex_chats (topic, title, user_id, metadata)
                VALUES (?, ?, ?, ?)
            """, (topic, title, user_id, metadata_json))
            conn.commit()
            return cursor.lastrowid

    def get_auspex_chats(self, topic: str = None, user_id: str = None, limit: int = 50) -> List[Dict]:
        """Get Auspex chat sessions with message counts."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Join with auspex_messages to get message count for each chat
            query = """
                SELECT c.*, COALESCE(m.message_count, 0) as message_count
                FROM auspex_chats c
                LEFT JOIN (
                    SELECT chat_id, COUNT(*) as message_count
                    FROM auspex_messages
                    GROUP BY chat_id
                ) m ON c.id = m.chat_id
                WHERE 1=1
            """
            params = []
            
            if topic:
                query += " AND c.topic = ?"
                params.append(topic)
            if user_id:
                query += " AND c.user_id = ?"
                params.append(user_id)
                
            query += " ORDER BY c.updated_at DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            return [{
                'id': row[0],
                'topic': row[1],
                'title': row[2],
                'created_at': row[3],
                'updated_at': row[4],
                'user_id': row[5],
                'metadata': json.loads(row[6]) if row[6] else None,
                'message_count': row[7]
            } for row in rows]

    def get_auspex_chat(self, chat_id: int) -> Optional[Dict]:
        """Get a specific Auspex chat."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM auspex_chats WHERE id = ?", (chat_id,))
            row = cursor.fetchone()
            
            if not row:
                return None
                
            return {
                'id': row[0],
                'topic': row[1],
                'title': row[2],
                'created_at': row[3],
                'updated_at': row[4],
                'user_id': row[5],
                'metadata': json.loads(row[6]) if row[6] else None
            }

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
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM auspex_chats WHERE id = ?", (chat_id,))
            conn.commit()
            return cursor.rowcount > 0

    def add_auspex_message(self, chat_id: int, role: str, content: str, 
                          model_used: str = None, tokens_used: int = None, 
                          metadata: dict = None) -> int:
        """Add a message to an Auspex chat."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            metadata_json = json.dumps(metadata) if metadata else None
            
            cursor.execute("""
                INSERT INTO auspex_messages (chat_id, role, content, model_used, tokens_used, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (chat_id, role, content, model_used, tokens_used, metadata_json))
            
            # Update chat's updated_at timestamp
            cursor.execute("UPDATE auspex_chats SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (chat_id,))
            
            conn.commit()
            return cursor.lastrowid

    def get_auspex_messages(self, chat_id: int) -> List[Dict]:
        """Get all messages for an Auspex chat."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, chat_id, role, content, timestamp, model_used, tokens_used, metadata
                FROM auspex_messages 
                WHERE chat_id = ? 
                ORDER BY timestamp ASC
            """, (chat_id,))
            
            rows = cursor.fetchall()
            return [{
                'id': row[0],
                'chat_id': row[1],
                'role': row[2],
                'content': row[3],
                'timestamp': row[4],
                'model_used': row[5],
                'tokens_used': row[6],
                'metadata': json.loads(row[7]) if row[7] else None
            } for row in rows]

    # Auspex Prompt Management Methods
    def create_auspex_prompt(self, name: str, title: str, content: str, 
                           description: str = None, is_default: bool = False, 
                           user_created: str = None) -> int:
        """Create a new Auspex prompt template."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO auspex_prompts (name, title, content, description, is_default, user_created)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (name, title, content, description, is_default, user_created))
            conn.commit()
            return cursor.lastrowid

    def get_auspex_prompts(self) -> List[Dict]:
        """Get all Auspex prompt templates."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, name, title, content, description, is_default, created_at, updated_at, user_created
                FROM auspex_prompts 
                ORDER BY is_default DESC, title ASC
            """)
            
            rows = cursor.fetchall()
            return [{
                'id': row[0],
                'name': row[1],
                'title': row[2],
                'content': row[3],
                'description': row[4],
                'is_default': bool(row[5]),
                'created_at': row[6],
                'updated_at': row[7],
                'user_created': row[8]
            } for row in rows]

    def get_auspex_prompt(self, name: str) -> Optional[Dict]:
        """Get a specific Auspex prompt by name."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, name, title, content, description, is_default, created_at, updated_at, user_created
                FROM auspex_prompts 
                WHERE name = ?
            """, (name,))
            
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

    def update_auspex_prompt(self, name: str, title: str = None, content: str = None, 
                           description: str = None) -> bool:
        """Update an Auspex prompt template."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            updates = []
            params = []
            
            if title is not None:
                updates.append("title = ?")
                params.append(title)
            if content is not None:
                updates.append("content = ?")
                params.append(content)
            if description is not None:
                updates.append("description = ?")
                params.append(description)
                
            if not updates:
                return True
                
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(name)
            
            query = f"UPDATE auspex_prompts SET {', '.join(updates)} WHERE name = ?"
            cursor.execute(query, params)
            conn.commit()
            return cursor.rowcount > 0

    def delete_auspex_prompt(self, name: str) -> bool:
        """Delete an Auspex prompt template."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM auspex_prompts WHERE name = ? AND is_default = 0", (name,))
            conn.commit()
            return cursor.rowcount > 0

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

    # Vantage Desk Filter Methods
    def create_vantage_desk_filters_table(self):
        """Create the vantage_desk_filters table if it does not exist."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS vantage_desk_filters (
                    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_key             TEXT    NOT NULL,
                    group_id             INTEGER,
                    source_type          TEXT,
                    sort_by              TEXT       DEFAULT 'publication_date',
                    limit_count          INTEGER    DEFAULT 50,
                    search_term          TEXT,
                    date_range           TEXT,
                    author_filter        TEXT,
                    min_engagement       INTEGER,
                    starred_filter       TEXT,
                    include_hidden       BOOLEAN    DEFAULT 0,
                    layout_mode          TEXT       DEFAULT 'cards',
                    topic_filter         TEXT,
                    source_date_combinations TEXT
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_vdf_user ON vantage_desk_filters (user_key)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_vdf_user_group ON vantage_desk_filters (user_key, group_id)")
            conn.commit()
   
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


