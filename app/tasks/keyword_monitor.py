import asyncio
from datetime import datetime
from typing import List, Dict
from app.collectors.newsapi_collector import NewsAPICollector
from app.database import Database
import logging

logger = logging.getLogger(__name__)

class KeywordMonitor:
    def __init__(self, db: Database, check_interval: int = 900):  # 900 seconds = 15 minutes
        self.db = db
        self.collector = None
        self.last_collector_init_attempt = None
        self.check_interval = check_interval
    
    def _init_collector(self):
        """Try to initialize the collector if not already initialized"""
        try:
            if not self.collector:
                self.collector = NewsAPICollector()
            return True
        except ValueError as e:
            # Only log error once every hour
            current_time = datetime.now()
            if not self.last_collector_init_attempt or \
               (current_time - self.last_collector_init_attempt).total_seconds() > 3600:
                logger.error(f"Failed to initialize NewsAPI collector: {str(e)}")
                self.last_collector_init_attempt = current_time
            return False
    
    async def check_keywords(self):
        """Check all keywords for new matches"""
        if not self._init_collector():
            return  # Skip checking if collector isn't available
            
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT mk.id, mk.keyword, mk.last_checked, kg.topic
                    FROM monitored_keywords mk
                    JOIN keyword_groups kg ON mk.group_id = kg.id
                """)
                keywords = cursor.fetchall()
                
                for keyword in keywords:
                    keyword_id, keyword_text, last_checked, topic = keyword
                    
                    # Search for articles
                    articles = await self.collector.search_articles(
                        query=keyword_text,
                        topic=topic,
                        max_results=10,
                        start_date=last_checked if last_checked else None
                    )
                    
                    # Process each article
                    for article in articles:
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
                    
                    # Update last checked timestamp
                    cursor.execute(
                        "UPDATE monitored_keywords SET last_checked = ? WHERE id = ?",
                        (datetime.now().isoformat(), keyword_id)
                    )
                    
                conn.commit()
                
        except Exception as e:
            logger.error(f"Error checking keywords: {str(e)}")
            raise

async def run_keyword_monitor():
    """Background task to periodically check keywords"""
    db = Database()
    monitor = KeywordMonitor(db)
    
    while True:
        try:
            await monitor.check_keywords()
        except Exception as e:
            logger.error(f"Keyword monitor error: {str(e)}")
        
        await asyncio.sleep(monitor.check_interval) 