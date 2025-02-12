"""Monitor keywords and collect matching news articles."""

import logging
import asyncio
from datetime import datetime
from typing import List, Dict
from app.collectors.newsapi_collector import NewsAPICollector
from app.database import Database

logger = logging.getLogger(__name__)

class KeywordMonitor:
    def __init__(self, db: Database):
        self.db = db
        self.collector = None
        self.last_collector_init_attempt = None
        self._load_settings()
        self._init_tables()
    
    def _load_settings(self):
        """Load settings from database"""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                
                # Check if table exists and get its columns
                cursor.execute("PRAGMA table_info(keyword_monitor_settings)")
                columns = {col[1] for col in cursor.fetchall()}
                
                if not columns:
                    # Create table if it doesn't exist
                    cursor.execute("""
                        CREATE TABLE keyword_monitor_settings (
                            id INTEGER PRIMARY KEY,
                            check_interval INTEGER NOT NULL DEFAULT 15,
                            interval_unit INTEGER NOT NULL DEFAULT 60,
                            search_fields TEXT NOT NULL DEFAULT 'title,description,content',
                            language TEXT NOT NULL DEFAULT 'en',
                            sort_by TEXT NOT NULL DEFAULT 'publishedAt',
                            page_size INTEGER NOT NULL DEFAULT 10,
                            is_enabled BOOLEAN NOT NULL DEFAULT 1,
                            daily_request_limit INTEGER NOT NULL DEFAULT 100
                        )
                    """)
                    # Insert default settings
                    cursor.execute("""
                        INSERT INTO keyword_monitor_settings (id) VALUES (1)
                    """)
                    conn.commit()
                else:
                    # Add any missing columns
                    if 'is_enabled' not in columns:
                        cursor.execute("""
                            ALTER TABLE keyword_monitor_settings 
                            ADD COLUMN is_enabled BOOLEAN NOT NULL DEFAULT 1
                        """)
                    if 'daily_request_limit' not in columns:
                        cursor.execute("""
                            ALTER TABLE keyword_monitor_settings 
                            ADD COLUMN daily_request_limit INTEGER NOT NULL DEFAULT 100
                        """)
                    conn.commit()
                
                # Load settings
                cursor.execute("""
                    SELECT 
                        check_interval,
                        interval_unit,
                        search_fields,
                        language,
                        sort_by,
                        page_size,
                        is_enabled,
                        daily_request_limit
                    FROM keyword_monitor_settings 
                    WHERE id = 1
                """)
                settings = cursor.fetchone()
                
                if settings:
                    self.check_interval = settings[0] * settings[1]  # interval * unit
                    self.search_fields = settings[2]
                    self.language = settings[3]
                    self.sort_by = settings[4]
                    self.page_size = settings[5]
                    self.is_enabled = settings[6]
                    self.daily_request_limit = settings[7]
                else:
                    # Use defaults
                    self.check_interval = 900  # 15 minutes
                    self.search_fields = "title,description,content"
                    self.language = "en"
                    self.sort_by = "publishedAt"
                    self.page_size = 10
                    self.is_enabled = True
                    self.daily_request_limit = 100
                    
        except Exception as e:
            logger.error(f"Error loading settings: {str(e)}")
            # Use defaults
            self.check_interval = 900
            self.search_fields = "title,description,content"
            self.language = "en"
            self.sort_by = "publishedAt"
            self.page_size = 10
            self.is_enabled = True
            self.daily_request_limit = 100
    
    def _init_tables(self):
        """Initialize required database tables"""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                
                # Check if table exists and get its columns
                cursor.execute("PRAGMA table_info(keyword_monitor_status)")
                columns = {col[1] for col in cursor.fetchall()}
                
                if not columns:
                    # Table doesn't exist, create it with all columns
                    cursor.execute("""
                        CREATE TABLE keyword_monitor_status (
                            id INTEGER PRIMARY KEY,
                            last_check_time TEXT,
                            last_error TEXT,
                            requests_today INTEGER DEFAULT 0,
                            last_reset_date TEXT
                        )
                    """)
                elif 'last_reset_date' not in columns:
                    # Add last_reset_date column if it doesn't exist
                    cursor.execute("""
                        ALTER TABLE keyword_monitor_status
                        ADD COLUMN last_reset_date TEXT
                    """)
                
                # Create initial status record if it doesn't exist
                cursor.execute("""
                    INSERT OR IGNORE INTO keyword_monitor_status (
                        id, last_check_time, last_error, requests_today, last_reset_date
                    ) VALUES (1, NULL, NULL, 0, NULL)
                """)
                
                conn.commit()
                
                # Check if we need to reset the counter
                cursor.execute("""
                    SELECT requests_today, last_reset_date 
                    FROM keyword_monitor_status 
                    WHERE id = 1
                """)
                row = cursor.fetchone()
                if row:
                    last_reset = row[1]
                    today = datetime.now().date().isoformat()
                    
                    if not last_reset or last_reset < today:
                        # Reset counter for new day
                        cursor.execute("""
                            UPDATE keyword_monitor_status 
                            SET requests_today = 0,
                                last_reset_date = ?
                            WHERE id = 1
                        """, (today,))
                        conn.commit()
            
        except Exception as e:
            logger.error(f"Error initializing tables: {str(e)}")
            raise
    
    def _init_collector(self):
        """Initialize the NewsAPI collector with database access"""
        if not self.collector:
            try:
                self.collector = NewsAPICollector(self.db)
                self.last_collector_init_attempt = datetime.now()
                return True  # Return True on successful initialization
            except Exception as e:
                logger.error(f"Failed to initialize collector: {str(e)}")
                self.last_collector_init_attempt = datetime.now()
                return False  # Return False if initialization fails
        return True  # Return True if collector already exists
    
    async def check_keywords(self):
        """Check all keywords for new matches"""
        logger.info("Starting keyword check...")
        if not self._init_collector():  # Check return value
            logger.error("Failed to initialize collector, skipping check")
            return
        
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                
                # Store check start time and reset error
                check_start_time = datetime.now().isoformat()
                cursor.execute("""
                    INSERT OR REPLACE INTO keyword_monitor_status (
                        id, last_check_time, last_error, requests_today
                    ) VALUES (1, ?, NULL, ?)
                """, (check_start_time, self.collector.requests_today))
                conn.commit()
                
                cursor.execute("""
                    SELECT mk.id, mk.keyword, mk.last_checked, kg.topic
                    FROM monitored_keywords mk
                    JOIN keyword_groups kg ON mk.group_id = kg.id
                """)
                keywords = cursor.fetchall()
                logger.info(f"Found {len(keywords)} keywords to check")
                
                for keyword in keywords:
                    keyword_id, keyword_text, last_checked, topic = keyword
                    logger.info(
                        f"Checking keyword: {keyword_text} (topic: {topic}, "
                        f"requests_today: {self.collector.requests_today}/100)"
                    )
                    
                    try:
                        articles = await self.collector.search_articles(
                            query=keyword_text,
                            topic=topic,
                            max_results=self.page_size,
                            start_date=last_checked if last_checked else None,
                            search_fields=self.search_fields,
                            language=self.language,
                            sort_by=self.sort_by
                        )
                        
                        if not articles:
                            logger.warning(f"No articles found or error occurred for keyword: {keyword_text}")
                            continue

                        logger.info(f"Found {len(articles)} new articles for keyword: {keyword_text}")
                        
                        # Process each article
                        for article in articles:
                            try:
                                # Check if article exists
                                cursor.execute(
                                    "SELECT 1 FROM articles WHERE uri = ?",
                                    (article['url'],)
                                )
                                if not cursor.fetchone():
                                    # Save new article
                                    cursor.execute("""
                                        INSERT INTO articles (
                                            uri, title, news_source, publication_date,
                                            summary, topic
                                        ) VALUES (?, ?, ?, ?, ?, ?)
                                    """, (
                                        article['url'],
                                        article['title'],
                                        article['source'],
                                        article['published_date'],
                                        article['summary'],
                                        topic
                                    ))
                                
                                # Create alert
                                cursor.execute("""
                                    INSERT INTO keyword_alerts (
                                        keyword_id, article_uri
                                    ) VALUES (?, ?)
                                    ON CONFLICT DO NOTHING
                                """, (keyword_id, article['url']))
                                
                            except Exception as e:
                                logger.error(f"Error processing article {article.get('url', 'unknown')}: {str(e)}")
                                continue
                        
                        # Update last checked timestamp
                        cursor.execute(
                            "UPDATE monitored_keywords SET last_checked = ? WHERE id = ?",
                            (datetime.now().isoformat(), keyword_id)
                        )
                        conn.commit()
                        
                        # Update request count in status
                        cursor.execute("""
                            UPDATE keyword_monitor_status 
                            SET requests_today = ? 
                            WHERE id = 1
                        """, (self.collector.requests_today,))
                        conn.commit()
                        
                    except ValueError as e:
                        if "Rate limit exceeded" in str(e):
                            error_msg = "NewsAPI daily request limit reached (100/100 requests used)"
                            logger.error(error_msg)
                            cursor.execute("""
                                INSERT OR REPLACE INTO keyword_monitor_status (
                                    id, last_check_time, last_error, requests_today
                                ) VALUES (1, ?, ?, ?)
                            """, (check_start_time, error_msg, self.collector.requests_today))
                            conn.commit()
                            raise ValueError(error_msg)
                        raise
                
        except Exception as e:
            logger.error(f"Error checking keywords: {str(e)}")
            raise

async def run_keyword_monitor():
    """Background task to periodically check keywords"""
    db = Database()
    monitor = KeywordMonitor(db)
    
    while True:
        try:
            # Check if polling is enabled
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT is_enabled FROM keyword_monitor_settings WHERE id = 1")
                row = cursor.fetchone()
                is_enabled = row[0] if row and row[0] is not None else True

            if is_enabled:
                await monitor.check_keywords()
                
        except Exception as e:
            logger.error(f"Keyword monitor error: {str(e)}")
        
        await asyncio.sleep(monitor.check_interval) 