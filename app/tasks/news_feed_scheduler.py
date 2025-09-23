import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional
import json
import os

from app.database import get_database_instance
from app.services.news_feed_service import get_news_feed_service
from app.schemas.news_feed import NewsFeedRequest

logger = logging.getLogger(__name__)


class NewsFeedScheduler:
    """
    Scheduler for automated daily news feed generation.
    Can be integrated with cron jobs, APScheduler, or other scheduling systems.
    """
    
    def __init__(self):
        self.db = get_database_instance()
        self.news_feed_service = get_news_feed_service(self.db)
        
    async def generate_daily_feeds(self, date: Optional[datetime] = None, topics: Optional[list] = None):
        """Generate daily news feeds for specified date and topics"""
        
        target_date = date or datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Default topics to generate feeds for
        default_topics = [
            "artificial intelligence",
            "technology", 
            "politics",
            "business",
            "science",
            "climate",
            None  # General news (no topic filter)
        ]
        
        topics_to_process = topics or default_topics
        
        logger.info(f"Starting daily news feed generation for {target_date.date()}")
        logger.info(f"Topics to process: {topics_to_process}")
        
        results = {}
        
        for topic in topics_to_process:
            try:
                logger.info(f"Generating feed for topic: {topic or 'General'}")
                
                # Create request
                request = NewsFeedRequest(
                    date=target_date,
                    topic=topic,
                    max_articles=50,
                    include_bias_analysis=True,
                    model="gpt-4o"
                )
                
                # Generate feed
                feed_response = await self.news_feed_service.generate_daily_feed(request)
                
                # Store results
                topic_key = topic or "general"
                results[topic_key] = {
                    "success": True,
                    "overview_stories": len(feed_response.overview.top_stories),
                    "six_articles_count": len(feed_response.six_articles.articles),
                    "processing_time": feed_response.processing_time_seconds,
                    "generated_at": feed_response.generated_at.isoformat()
                }
                
                # Save to database/cache if needed
                await self._save_generated_feed(topic_key, target_date, feed_response)
                
                logger.info(f"Successfully generated feed for {topic or 'General'}: "
                          f"{len(feed_response.overview.top_stories)} stories, "
                          f"{len(feed_response.six_articles.articles)} detailed articles")
                
            except Exception as e:
                logger.error(f"Error generating feed for topic '{topic}': {e}")
                topic_key = topic or "general"
                results[topic_key] = {
                    "success": False,
                    "error": str(e)
                }
        
        # Log summary
        successful = sum(1 for r in results.values() if r.get("success"))
        total = len(results)
        logger.info(f"Daily feed generation completed: {successful}/{total} successful")
        
        return results
    
    async def _save_generated_feed(self, topic: str, date: datetime, feed_response):
        """Save generated feed to database for caching/retrieval"""
        
        try:
            # Create table if it doesn't exist
            create_table_query = """
            CREATE TABLE IF NOT EXISTS daily_news_feeds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT NOT NULL,
                feed_date DATE NOT NULL,
                overview_data TEXT NOT NULL,
                six_articles_data TEXT NOT NULL,
                generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processing_time_seconds REAL,
                model_used TEXT,
                UNIQUE(topic, feed_date)
            )
            """
            self.db.execute_query(create_table_query)
            
            # Save feed data
            insert_query = """
            INSERT OR REPLACE INTO daily_news_feeds 
            (topic, feed_date, overview_data, six_articles_data, generated_at, processing_time_seconds, model_used)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """
            
            self.db.execute_query(insert_query, (
                topic,
                date.date(),
                json.dumps(feed_response.overview.dict(), default=str),
                json.dumps(feed_response.six_articles.dict(), default=str),
                feed_response.generated_at.isoformat(),
                feed_response.processing_time_seconds,
                "gpt-4o"  # Default model used
            ))
            
            logger.debug(f"Saved generated feed to database: {topic}, {date.date()}")
            
        except Exception as e:
            logger.error(f"Error saving generated feed to database: {e}")
    
    async def get_cached_feed(self, topic: str, date: datetime):
        """Retrieve cached feed from database"""
        
        try:
            query = """
            SELECT overview_data, six_articles_data, generated_at, processing_time_seconds
            FROM daily_news_feeds 
            WHERE topic = ? AND feed_date = ?
            ORDER BY generated_at DESC
            LIMIT 1
            """
            
            result = self.db.fetch_one(query, (topic, date.date()))
            
            if result:
                return {
                    "overview": json.loads(result[0]),
                    "six_articles": json.loads(result[1]),
                    "generated_at": result[2],
                    "processing_time_seconds": result[3],
                    "cached": True
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error retrieving cached feed: {e}")
            return None
    
    async def cleanup_old_feeds(self, days_to_keep: int = 30):
        """Clean up old cached feeds to save space"""
        
        try:
            cutoff_date = datetime.now() - timedelta(days=days_to_keep)
            
            delete_query = """
            DELETE FROM daily_news_feeds 
            WHERE feed_date < ?
            """
            
            # Get count of feeds to be deleted first
            count_query = "SELECT COUNT(*) FROM daily_news_feeds WHERE feed_date < ?"
            result = self.db.fetch_one(count_query, (cutoff_date.date(),))
            deleted_count = result[0] if result else 0
            
            # Execute delete query
            self.db.execute_query(delete_query, (cutoff_date.date(),))
            
            logger.info(f"Cleaned up {deleted_count} old news feeds (older than {days_to_keep} days)")
            
            return deleted_count
            
        except Exception as e:
            logger.error(f"Error cleaning up old feeds: {e}")
            return 0


# Standalone functions for cron job integration
async def run_daily_feed_generation():
    """Standalone function for cron job integration"""
    
    scheduler = NewsFeedScheduler()
    
    try:
        results = await scheduler.generate_daily_feeds()
        
        # Log results for monitoring
        successful_topics = [topic for topic, result in results.items() if result.get("success")]
        failed_topics = [topic for topic, result in results.items() if not result.get("success")]
        
        logger.info(f"Daily feed generation completed:")
        logger.info(f"Successful topics: {successful_topics}")
        if failed_topics:
            logger.warning(f"Failed topics: {failed_topics}")
        
        return results
        
    except Exception as e:
        logger.error(f"Critical error in daily feed generation: {e}")
        raise


async def run_feed_cleanup():
    """Standalone function for cleaning up old feeds"""
    
    scheduler = NewsFeedScheduler()
    
    try:
        deleted_count = await scheduler.cleanup_old_feeds(days_to_keep=30)
        logger.info(f"Feed cleanup completed: {deleted_count} old feeds removed")
        return deleted_count
        
    except Exception as e:
        logger.error(f"Error in feed cleanup: {e}")
        raise


# CLI interface for manual execution
if __name__ == "__main__":
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description="News Feed Scheduler")
    parser.add_argument("--action", choices=["generate", "cleanup"], default="generate",
                       help="Action to perform")
    parser.add_argument("--date", type=str, help="Date in YYYY-MM-DD format (default: today)")
    parser.add_argument("--topic", type=str, help="Specific topic to generate (default: all)")
    parser.add_argument("--cleanup-days", type=int, default=30, 
                       help="Days of feeds to keep when cleaning up")
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    async def main():
        scheduler = NewsFeedScheduler()
        
        if args.action == "generate":
            # Parse date if provided
            target_date = None
            if args.date:
                try:
                    target_date = datetime.strptime(args.date, "%Y-%m-%d")
                except ValueError:
                    print(f"Invalid date format: {args.date}. Use YYYY-MM-DD")
                    sys.exit(1)
            
            # Parse topics if provided
            topics = [args.topic] if args.topic else None
            
            # Generate feeds
            results = await scheduler.generate_daily_feeds(date=target_date, topics=topics)
            
            # Print results
            print(f"\nDaily News Feed Generation Results:")
            print(f"Date: {(target_date or datetime.now()).date()}")
            print(f"Topics processed: {len(results)}")
            
            for topic, result in results.items():
                status = "✓" if result.get("success") else "✗"
                if result.get("success"):
                    print(f"{status} {topic}: {result.get('overview_stories', 0)} stories, "
                          f"{result.get('six_articles_count', 0)} detailed articles "
                          f"({result.get('processing_time', 0):.1f}s)")
                else:
                    print(f"{status} {topic}: {result.get('error', 'Unknown error')}")
        
        elif args.action == "cleanup":
            deleted_count = await scheduler.cleanup_old_feeds(days_to_keep=args.cleanup_days)
            print(f"Cleanup completed: {deleted_count} old feeds removed")
    
    # Run the main function
    asyncio.run(main())
