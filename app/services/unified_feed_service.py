"""
Unified Feed Service

Aggregates feeds from multiple sources (social media and academic journals)
for the new feed system. Leverages existing collectors for ArXiv and Bluesky.
"""

import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Any
from dataclasses import dataclass

from app.database import Database
from app.collectors.arxiv_collector import ArxivCollector
from app.collectors.bluesky_collector import BlueskyCollector
from app.collectors.thenewsapi_collector import TheNewsAPICollector
from app.collectors.newsdata_collector import NewsdataCollector
from app.services.feed_group_service import FeedGroupService

# Configure logging
logger = logging.getLogger(__name__)

@dataclass
class FeedItem:
    """Data class for unified feed items."""
    id: Optional[int] = None
    source_type: str = ""  # 'bluesky', 'arxiv', etc.
    source_id: str = ""
    group_id: int = 0
    title: str = ""
    content: Optional[str] = None
    author: Optional[str] = None
    author_handle: Optional[str] = None
    url: str = ""
    publication_date: Optional[datetime] = None
    engagement_metrics: Dict[str, int] = None
    tags: List[str] = None
    mentions: List[str] = None
    images: List[str] = None
    is_hidden: bool = False
    is_starred: bool = False
    created_at: Optional[str] = None

    def __post_init__(self):
        if self.engagement_metrics is None:
            self.engagement_metrics = {}
        if self.tags is None:
            self.tags = []
        if self.mentions is None:
            self.mentions = []
        if self.images is None:
            self.images = []

class UnifiedFeedService:
    """Service for aggregating and managing unified feeds."""

    def __init__(self, db: Database = None):
        """Initialize the service with database and collectors."""
        self.db = db or Database()
        self.feed_group_service = FeedGroupService(self.db)
        
        # Initialize collectors
        try:
            self.arxiv_collector = ArxivCollector()
            logger.info("ArXiv collector initialized successfully")
        except Exception as e:
            logger.warning(f"Failed to initialize ArXiv collector: {str(e)}")
            self.arxiv_collector = None
        
        try:
            self.bluesky_collector = BlueskyCollector()
            logger.info("Bluesky collector initialized successfully")
        except Exception as e:
            logger.warning(f"Failed to initialize Bluesky collector: {str(e)}")
            self.bluesky_collector = None
            
        try:
            self.thenewsapi_collector = TheNewsAPICollector()
            logger.info("TheNewsAPI collector initialized successfully")
        except Exception as e:
            logger.warning(f"Failed to initialize TheNewsAPI collector: {str(e)}")
            self.thenewsapi_collector = None
            
        try:
            self.newsdata_collector = NewsdataCollector()
            logger.info("NewsData.io collector initialized successfully")
        except Exception as e:
            logger.warning(f"Failed to initialize NewsData.io collector: {str(e)}")
            self.newsdata_collector = None
        logger.info("UnifiedFeedService initialized")

    async def collect_feed_items_for_group(self, group_id: int, max_items_per_source: int = 20) -> Dict[str, Any]:
        """
        Collect new feed items for a specific feed group.
        
        Args:
            group_id: ID of the feed group
            max_items_per_source: Maximum items to collect per source
            
        Returns:
            Dictionary with collection results
        """
        try:
            logger.info(f"Collecting feed items for group {group_id}")
            
            # Get the feed group
            group = self.feed_group_service.get_feed_group(group_id)
            if not group:
                return {
                    "success": False,
                    "error": f"Feed group {group_id} not found"
                }
            
            if not group["is_active"]:
                logger.info(f"Skipping inactive group: {group['name']}")
                return {
                    "success": True,
                    "items_collected": 0,
                    "message": "Group is inactive"
                }
            
            total_collected = 0
            collection_results = {
                "social_media": 0,
                "academic_journals": 0,
                "errors": []
            }
            
            # Process each enabled source
            for source in group["sources"]:
                if not source["enabled"]:
                    continue
                
                source_type = source["source_type"]
                keywords = source["keywords"]
                
                logger.info(f"Processing {source_type} source with {len(keywords)} keywords")
                
                if source_type == "bluesky" and self.bluesky_collector:
                    # Collect from Bluesky
                    items_collected = await self._collect_bluesky_items(
                        group_id, keywords, max_items_per_source
                    )
                    collection_results["social_media"] += items_collected
                    total_collected += items_collected
                    
                elif source_type == "arxiv" and self.arxiv_collector:
                    # Collect from ArXiv
                    items_collected = await self._collect_arxiv_items(
                        group_id, keywords, max_items_per_source
                    )
                    collection_results["academic_journals"] += items_collected
                    total_collected += items_collected
                    
                elif source_type == "thenewsapi" and self.thenewsapi_collector:
                    # Collect from TheNewsAPI
                    items_collected = await self._collect_thenewsapi_items(
                        group_id, keywords, max_items_per_source
                    )
                    collection_results["news_sources"] = collection_results.get("news_sources", 0) + items_collected
                    total_collected += items_collected
                    
                elif source_type == "newsdata" and self.newsdata_collector:
                    # Collect from NewsData.io
                    items_collected = await self._collect_newsdata_items(
                        group_id, keywords, max_items_per_source
                    )
                    collection_results["news_sources"] = collection_results.get("news_sources", 0) + items_collected
                    total_collected += items_collected
                
                else:
                    error_msg = f"No collector available for {source_type}"
                    logger.warning(error_msg)
                    collection_results["errors"].append(error_msg)
            
            # Update last_checked timestamp for all sources
            await self._update_sources_last_checked(group_id)
            
            logger.info(f"Collected {total_collected} items for group {group['name']}")
            
            return {
                "success": True,
                "items_collected": total_collected,
                "details": collection_results
            }
            
        except Exception as e:
            logger.error(f"Error collecting feed items for group {group_id}: {str(e)}")
            return {
                "success": False,
                "error": f"Collection failed: {str(e)}"
            }

    async def _collect_bluesky_items(self, group_id: int, keywords: List[str], max_items: int) -> int:
        """Collect items from Bluesky for given keywords."""
        try:
            items_collected = 0
            
            for keyword in keywords:
                try:
                    # Search Bluesky for this keyword
                    articles = await self.bluesky_collector.search_articles(
                        query=keyword,
                        topic=f"feed_group_{group_id}",
                        max_results=max_items // len(keywords),  # Distribute across keywords
                        sort_by="latest"
                    )
                    
                    for article in articles:
                        # Extract source ID from Bluesky data
                        source_id = self._extract_bluesky_source_id(article)
                        if not source_id:
                            continue
                        
                        # Convert to feed item
                        feed_item = self._convert_bluesky_to_feed_item(
                            article, group_id, source_id
                        )
                        
                        # Save to database
                        if await self._save_feed_item(feed_item):
                            items_collected += 1
                    
                    logger.info(f"Collected {len(articles)} Bluesky items for keyword '{keyword}'")
                    
                except Exception as e:
                    logger.error(f"Error collecting Bluesky items for keyword '{keyword}': {str(e)}")
                    continue
            
            return items_collected
            
        except Exception as e:
            logger.error(f"Error in Bluesky collection: {str(e)}")
            return 0

    async def _collect_arxiv_items(self, group_id: int, keywords: List[str], max_items: int) -> int:
        """Collect items from ArXiv for given keywords."""
        try:
            items_collected = 0
            
            # Get ArXiv source settings for this group to determine date range
            arxiv_source_settings = self._get_arxiv_source_settings(group_id)
            
            for keyword in keywords:
                try:
                    # Calculate date range based on source settings
                    start_date, end_date = self._calculate_date_range(arxiv_source_settings)
                    
                    # Search ArXiv for this keyword
                    articles = await self.arxiv_collector.search_articles(
                        query=keyword,
                        topic=None,  # No category restrictions
                        max_results=max_items // len(keywords),  # Distribute across keywords
                        start_date=start_date,
                        end_date=end_date,
                        sort_by="submittedDate"
                    )
                    
                    for article in articles:
                        # Extract source ID from ArXiv data
                        source_id = self._extract_arxiv_source_id(article)
                        if not source_id:
                            continue
                        
                        # Convert to feed item
                        feed_item = self._convert_arxiv_to_feed_item(
                            article, group_id, source_id
                        )
                        
                        # Save to database
                        if await self._save_feed_item(feed_item):
                            items_collected += 1
                    
                    logger.info(f"Collected {len(articles)} ArXiv items for keyword '{keyword}'")
                    
                except Exception as e:
                    logger.error(f"Error collecting ArXiv items for keyword '{keyword}': {str(e)}")
                    continue
            
            return items_collected
            
        except Exception as e:
            logger.error(f"Error in ArXiv collection: {str(e)}")
            return 0

    def _extract_bluesky_source_id(self, article: Dict) -> Optional[str]:
        """Extract unique source ID from Bluesky article data."""
        try:
            # Use the URI from raw_data as the unique identifier
            if "raw_data" in article and "uri" in article["raw_data"]:
                return article["raw_data"]["uri"]
            
            # Fallback to URL
            return article.get("url", "")
            
        except Exception as e:
            logger.error(f"Error extracting Bluesky source ID: {str(e)}")
            return None

    def _extract_arxiv_source_id(self, article: Dict) -> Optional[str]:
        """Extract unique source ID from ArXiv article data."""
        try:
            # Use ArXiv ID from raw_data
            if "raw_data" in article and "arxiv_id" in article["raw_data"]:
                return article["raw_data"]["arxiv_id"]
            
            # Fallback to URL
            return article.get("url", "")
            
        except Exception as e:
            logger.error(f"Error extracting ArXiv source ID: {str(e)}")
            return None

    async def _collect_thenewsapi_items(self, group_id: int, keywords: List[str], max_items: int) -> int:
        """Collect items from TheNewsAPI for given keywords."""
        try:
            items_collected = 0
            
            # Get TheNewsAPI source settings for this group to determine date range
            thenewsapi_source_settings = self._get_thenewsapi_source_settings(group_id)
            
            for keyword in keywords:
                try:
                    # Calculate date range based on source settings
                    start_date, end_date = self._calculate_date_range(thenewsapi_source_settings)
                    
                    # Search TheNewsAPI for this keyword
                    articles = await self.thenewsapi_collector.search_articles(
                        query=keyword,
                        topic=None,  # No specific topic categorization
                        max_results=max_items // len(keywords),  # Distribute across keywords
                        start_date=start_date,
                        end_date=end_date,
                        sort_by="published_at"
                    )
                    
                    for article in articles:
                        # Extract source ID from TheNewsAPI data
                        source_id = self._extract_thenewsapi_source_id(article)
                        if not source_id:
                            continue
                        
                        # Convert to feed item
                        feed_item = self._convert_thenewsapi_to_feed_item(
                            article, group_id, source_id
                        )
                        
                        # Save to database
                        if await self._save_feed_item(feed_item):
                            items_collected += 1
                    
                    logger.info(f"Collected {len(articles)} TheNewsAPI items for keyword '{keyword}'")
                    
                except Exception as e:
                    logger.error(f"Error collecting TheNewsAPI items for keyword '{keyword}': {str(e)}")
                    continue
            
            return items_collected
            
        except Exception as e:
            logger.error(f"Error in TheNewsAPI collection: {str(e)}")
            return 0

    async def _collect_newsdata_items(self, group_id: int, keywords: List[str], max_items: int) -> int:
        """Collect items from NewsData.io for given keywords."""
        try:
            items_collected = 0
            
            # Get NewsData.io source settings for this group to determine date range
            newsdata_source_settings = self._get_newsdata_source_settings(group_id)
            
            for keyword in keywords:
                try:
                    # Calculate date range based on source settings
                    start_date, end_date = self._calculate_date_range(newsdata_source_settings)
                    
                    # Search NewsData.io for this keyword
                    articles = await self.newsdata_collector.search_articles(
                        query=keyword,
                        topic=None,  # No specific topic categorization
                        max_results=max_items // len(keywords),  # Distribute across keywords
                        start_date=start_date,
                        end_date=end_date,
                        language="en"
                    )
                    
                    for article in articles:
                        # Extract source ID from NewsData.io data
                        source_id = self._extract_newsdata_source_id(article)
                        if not source_id:
                            continue
                        
                        # Convert to feed item
                        feed_item = self._convert_newsdata_to_feed_item(
                            article, group_id, source_id
                        )
                        
                        # Save to database
                        if await self._save_feed_item(feed_item):
                            items_collected += 1
                    
                    logger.info(f"Collected {len(articles)} NewsData.io items for keyword '{keyword}'")
                    
                except Exception as e:
                    logger.error(f"Error collecting NewsData.io items for keyword '{keyword}': {str(e)}")
                    continue
            
            return items_collected
            
        except Exception as e:
            logger.error(f"Error in NewsData.io collection: {str(e)}")
            return 0

    def _extract_thenewsapi_source_id(self, article: Dict) -> Optional[str]:
        """Extract unique source ID from TheNewsAPI article data."""
        try:
            # Use URL as the unique identifier for news articles
            return article.get("url", "")
            
        except Exception as e:
            logger.error(f"Error extracting TheNewsAPI source ID: {str(e)}")
            return None

    def _convert_bluesky_to_feed_item(self, article: Dict, group_id: int, source_id: str) -> FeedItem:
        """Convert Bluesky article to FeedItem."""
        # Extract engagement metrics
        raw_data = article.get("raw_data", {})
        engagement_metrics = {
            "likes": raw_data.get("likes", 0),
            "reposts": raw_data.get("reposts", 0),
            "replies": raw_data.get("replies", 0),
            "quotes": raw_data.get("quotes", 0)
        }
        
        # Extract images
        images = []
        if "images" in raw_data:
            images = [img.get("url", "") for img in raw_data["images"] if img.get("url")]
        
        # Parse publication date
        pub_date = None
        if article.get("published_date"):
            try:
                pub_date = datetime.fromisoformat(article["published_date"].replace('Z', '+00:00'))
            except ValueError:
                pass
        
        return FeedItem(
            source_type="bluesky",
            source_id=source_id,
            group_id=group_id,
            title=article.get("title", ""),
            content=article.get("summary", ""),
            author=article.get("authors", [""])[0] if article.get("authors") else "",
            author_handle=raw_data.get("author_handle", ""),
            url=article.get("url", ""),
            publication_date=pub_date,
            engagement_metrics=engagement_metrics,
            images=images
        )

    def _convert_arxiv_to_feed_item(self, article: Dict, group_id: int, source_id: str) -> FeedItem:
        """Convert ArXiv article to FeedItem."""
        # Parse publication date
        pub_date = None
        if article.get("published_date"):
            try:
                pub_date = datetime.fromisoformat(article["published_date"])
            except ValueError:
                pass
        
        # Extract categories as tags
        raw_data = article.get("raw_data", {})
        tags = raw_data.get("categories", [])
        
        return FeedItem(
            source_type="arxiv",
            source_id=source_id,
            group_id=group_id,
            title=article.get("title", ""),
            content=article.get("summary", ""),
            author=", ".join(article.get("authors", [])),
            url=article.get("url", ""),
            publication_date=pub_date,
            tags=tags
        )

    def _convert_thenewsapi_to_feed_item(self, article: Dict, group_id: int, source_id: str) -> FeedItem:
        """Convert TheNewsAPI article to FeedItem."""
        # Parse publication date
        pub_date = None
        if article.get("published_date"):
            try:
                pub_date = datetime.fromisoformat(article["published_date"])
            except ValueError:
                pass
        
        # Extract keywords as tags
        raw_data = article.get("raw_data", {})
        tags = raw_data.get("keywords", [])
        
        # Get the source name from the article
        source_name = article.get("source", "")
        
        return FeedItem(
            source_type="thenewsapi",
            source_id=source_id,
            group_id=group_id,
            title=article.get("title", ""),
            content=article.get("summary", ""),
            author=", ".join(article.get("authors", [])) if article.get("authors") else source_name,
            url=article.get("url", ""),
            publication_date=pub_date,
            tags=tags
        )

    def _extract_newsdata_source_id(self, article: Dict) -> Optional[str]:
        """Extract unique source ID from NewsData.io article data."""
        try:
            # Use URL as the unique identifier for news articles
            return article.get("url", "")
            
        except Exception as e:
            logger.error(f"Error extracting NewsData.io source ID: {str(e)}")
            return None

    def _convert_newsdata_to_feed_item(self, article: Dict, group_id: int, source_id: str) -> FeedItem:
        """Convert NewsData.io article to FeedItem."""
        # Extract keywords as tags
        raw_data = article.get("raw_data", {})
        tags = raw_data.get("keywords", []) or []
        
        # Parse publication date
        pub_date = None
        if article.get("published_date"):
            if isinstance(article["published_date"], datetime):
                pub_date = article["published_date"]
            elif isinstance(article["published_date"], str):
                try:
                    pub_date = datetime.fromisoformat(article["published_date"].replace('Z', '+00:00'))
                except ValueError:
                    pub_date = datetime.now(timezone.utc)
            else:
                pub_date = datetime.now(timezone.utc)
        else:
            pub_date = datetime.now(timezone.utc)

        # Extract images
        images = []
        if raw_data.get("image_url"):
            images = [raw_data["image_url"]]

        # Extract author info
        authors = article.get("authors", []) or []
        author = ", ".join(authors) if authors else None

        return FeedItem(
            source_type="newsdata",
            source_id=source_id,
            group_id=group_id,
            title=article.get("title", ""),
            content=article.get("content", "") or article.get("summary", ""),  # NewsData.io provides full content
            author=author,
            author_handle=None,  # NewsData.io doesn't provide handles
            url=article.get("url", ""),
            publication_date=pub_date,
            engagement_metrics={},  # NewsData.io doesn't provide engagement metrics
            tags=tags,
            mentions=[],  # Not applicable for news articles
            images=images,
            is_hidden=False,
            is_starred=False
        )

    def _get_newsdata_source_settings(self, group_id: int) -> Dict[str, Any]:
        """Get NewsData.io source settings for a group."""
        try:
            query = """
            SELECT settings FROM feed_group_sources 
            WHERE group_id = ? AND source_type = 'newsdata' AND enabled = 1
            LIMIT 1
            """
            
            result = self.db.fetch_one(query, (group_id,))
            if result and result[0]:
                return json.loads(result[0])
            
            # Default settings
            return {
                "days_back": 7,  # Look back 7 days by default
                "language": "en",
                "country": None,
                "category": None
            }
            
        except Exception as e:
            logger.error(f"Error getting NewsData.io source settings: {str(e)}")
            return {"days_back": 7, "language": "en"}

    async def _save_feed_item(self, feed_item: FeedItem) -> bool:
        """Save a feed item to the database."""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                
                # Check if item already exists
                cursor.execute("""
                    SELECT id FROM feed_items 
                    WHERE source_type = ? AND source_id = ? AND group_id = ?
                """, (feed_item.source_type, feed_item.source_id, feed_item.group_id))
                
                if cursor.fetchone():
                    # Item already exists
                    return False
                
                # Insert new item
                cursor.execute("""
                    INSERT INTO feed_items (
                        source_type, source_id, group_id, title, content, 
                        author, author_handle, url, publication_date,
                        engagement_metrics, tags, mentions, images
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    feed_item.source_type,
                    feed_item.source_id,
                    feed_item.group_id,
                    feed_item.title,
                    feed_item.content,
                    feed_item.author,
                    feed_item.author_handle,
                    feed_item.url,
                    feed_item.publication_date.isoformat() if feed_item.publication_date else None,
                    json.dumps(feed_item.engagement_metrics),
                    json.dumps(feed_item.tags),
                    json.dumps(feed_item.mentions),
                    json.dumps(feed_item.images)
                ))
                
                conn.commit()
                return True
                
        except Exception as e:
            logger.error(f"Error saving feed item: {str(e)}")
            return False

    async def _update_sources_last_checked(self, group_id: int):
        """Update last_checked timestamp for all sources in a group."""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE feed_group_sources 
                    SET last_checked = ? 
                    WHERE group_id = ?
                """, (datetime.now().isoformat(), group_id))
                conn.commit()
                
        except Exception as e:
            logger.error(f"Error updating last_checked for group {group_id}: {str(e)}")

    def _get_arxiv_source_settings(self, group_id: int) -> Dict[str, Any]:
        """Get ArXiv source settings for a group."""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT date_range_days, custom_start_date, custom_end_date
                    FROM feed_group_sources
                    WHERE group_id = ? AND source_type = 'arxiv'
                    LIMIT 1
                """, (group_id,))
                
                result = cursor.fetchone()
                if result:
                    return {
                        "date_range_days": result[0] or 7,
                        "custom_start_date": result[1],
                        "custom_end_date": result[2]
                    }
                else:
                    return {"date_range_days": 7, "custom_start_date": None, "custom_end_date": None}
                    
        except Exception as e:
            logger.error(f"Error getting ArXiv source settings for group {group_id}: {str(e)}")
            return {"date_range_days": 7, "custom_start_date": None, "custom_end_date": None}

    def _get_thenewsapi_source_settings(self, group_id: int) -> Dict[str, Any]:
        """Get TheNewsAPI source settings for a group."""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT date_range_days, custom_start_date, custom_end_date
                    FROM feed_group_sources
                    WHERE group_id = ? AND source_type = 'thenewsapi'
                    LIMIT 1
                """, (group_id,))
                
                result = cursor.fetchone()
                if result:
                    return {
                        "date_range_days": result[0] or 7,
                        "custom_start_date": result[1],
                        "custom_end_date": result[2]
                    }
                else:
                    return {"date_range_days": 7, "custom_start_date": None, "custom_end_date": None}
                    
        except Exception as e:
            logger.error(f"Error getting TheNewsAPI source settings for group {group_id}: {str(e)}")
            return {"date_range_days": 7, "custom_start_date": None, "custom_end_date": None}

    def _calculate_date_range(self, source_settings: Dict[str, Any]) -> tuple:
        """Calculate start and end dates based on source settings."""
        try:
            now = datetime.now(timezone.utc)
            
            # Use custom dates if provided
            if source_settings.get("custom_start_date") and source_settings.get("custom_end_date"):
                try:
                    start_date = datetime.fromisoformat(source_settings["custom_start_date"].replace('Z', '+00:00'))
                    end_date = datetime.fromisoformat(source_settings["custom_end_date"].replace('Z', '+00:00'))
                    return start_date, end_date
                except ValueError:
                    pass  # Fall back to date_range_days
            
            # Use date_range_days
            days = source_settings.get("date_range_days", 7)
            start_date = now - timedelta(days=days)
            end_date = now
            
            return start_date, end_date
            
        except Exception as e:
            logger.error(f"Error calculating date range: {str(e)}")
            # Return default 7 days
            now = datetime.now(timezone.utc)
            return now - timedelta(days=7), now

    def get_unified_feed(self, limit: int = 50, offset: int = 0, 
                        group_ids: List[int] = None, 
                        source_types: List[str] = None,
                        include_hidden: bool = False,
                        combination_sources: List[str] = None,
                        combination_dates: List[str] = None,
                        dateRange: str = None,
                        search: str = None,
                        author: str = None,
                        min_engagement: int = None,
                        starred: str = None,
                        topic: str = None,
                        sort: str = "publication_date") -> dict:
        """
        Get unified feed items across all or specified groups.
        Supports advanced filtering by source+date combinations and all other filters.
        Args:
            limit: Maximum number of items to return
            offset: Number of items to skip
            group_ids: Optional list of group IDs to filter by
            source_types: Optional list of source types to filter by
            include_hidden: Whether to include hidden items
            combination_sources: Optional list of sources for combination filter
            combination_dates: Optional list of date ranges for combination filter (same length as combination_sources)
            dateRange: Optional date range filter (today, week, month, quarter)
            search: Optional search term for title and content
            author: Optional author name to filter by
            min_engagement: Optional minimum engagement score
            starred: Optional starred filter ('starred', 'unstarred', or None)
            topic: Optional topic to filter by
            sort: Sort order ('publication_date', 'created_at', or 'engagement')
        Returns:
            Dictionary with feed items and metadata
        """
        try:
            logger.info(f"Fetching unified feed (limit={limit}, offset={offset})")
            
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                
                # Build query
                where_conditions = []
                params = []
                
                if group_ids:
                    placeholders = ','.join(['?'] * len(group_ids))
                    where_conditions.append(f"fi.group_id IN ({placeholders})")
                    params.extend(group_ids)
                
                # Combination filter logic
                if combination_sources and combination_dates and len(combination_sources) == len(combination_dates):
                    combo_subclauses = []
                    for src, date in zip(combination_sources, combination_dates):
                        # Map date string to days
                        days = None
                        if date == 'today':
                            days = 0
                        elif date == 'week':
                            days = 7
                        elif date == 'month':
                            days = 30
                        elif date == 'quarter':
                            days = 90
                        
                        if date == 'alltime':
                            combo_subclauses.append("(fi.source_type = ?)")
                        else:
                            combo_subclauses.append(f"(fi.source_type = ? AND fi.publication_date >= NOW() - INTERVAL '{days} days')")
                        
                        params.extend([src])
                        
                    if combo_subclauses:
                        where_conditions.append('(' + ' OR '.join(combo_subclauses) + ')')
                elif source_types or dateRange:
                    # Individual source type filter
                    if source_types:
                        placeholders = ','.join(['?'] * len(source_types))
                        where_conditions.append(f"fi.source_type IN ({placeholders})")
                        params.extend(source_types)

                    # Individual date range filter
                    if dateRange:
                        days = None
                        if dateRange == 'today':
                            days = 0
                        elif dateRange == 'week':
                            days = 7
                        elif dateRange == 'month':
                            days = 30
                        elif dateRange == 'quarter':
                            days = 90
                        elif dateRange == 'alltime':
                            days = None

                        if days is not None:
                            where_conditions.append(f"fi.publication_date >= NOW() - INTERVAL '{days} days'")
                
                # Search filter
                if search:
                    where_conditions.append("(fi.title LIKE ? OR fi.content LIKE ?)")
                    search_term = f"%{search}%"
                    params.extend([search_term, search_term])
                
                # Author filter
                if author:
                    where_conditions.append("fi.author LIKE ?")
                    author_term = f"%{author}%"
                    params.append(author_term)
                
                # Engagement filter
                if min_engagement is not None:
                    where_conditions.append("""
                        (CAST(json_extract(fi.engagement_metrics, '$.likes') AS INTEGER) + 
                         CAST(json_extract(fi.engagement_metrics, '$.reposts') AS INTEGER) + 
                         CAST(json_extract(fi.engagement_metrics, '$.replies') AS INTEGER)) >= ?
                    """)
                    params.append(min_engagement)
                
                # Starred filter
                if starred == 'starred':
                    where_conditions.append("fi.is_starred = 1")
                elif starred == 'unstarred':
                    where_conditions.append("fi.is_starred = 0")
                
                # Topic filter
                if topic:
                    where_conditions.append("fi.topic = ?")
                    params.append(topic)
                
                if not include_hidden:
                    where_conditions.append("fi.is_hidden = 0")
                
                # Only show items from active groups
                where_conditions.append("fkg.is_active = 1")
                
                where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""
                
                # Build ORDER BY clause based on sort parameter
                if sort == "engagement":
                    order_clause = """ORDER BY 
                        (CAST(json_extract(fi.engagement_metrics, '$.likes') AS INTEGER) + 
                         CAST(json_extract(fi.engagement_metrics, '$.reposts') AS INTEGER) + 
                         CAST(json_extract(fi.engagement_metrics, '$.replies') AS INTEGER)) DESC,
                        fi.publication_date DESC"""
                elif sort == "created_at":
                    order_clause = "ORDER BY fi.created_at DESC, fi.publication_date DESC"
                else:  # default to publication_date
                    order_clause = "ORDER BY fi.publication_date DESC, fi.created_at DESC"
                
                # Main query
                query = f"""
                    SELECT 
                        fi.id, fi.source_type, fi.source_id, fi.group_id, fi.title,
                        fi.content, fi.author, fi.author_handle, fi.url, fi.publication_date,
                        fi.engagement_metrics, fi.tags, fi.mentions, fi.images,
                        fi.is_hidden, fi.is_starred, fi.created_at,
                        fkg.name as group_name, fkg.color as group_color
                    FROM feed_items fi
                    JOIN feed_keyword_groups fkg ON fi.group_id = fkg.id
                    {where_clause}
                    {order_clause}
                    LIMIT ? OFFSET ?
                """
                
                params.extend([limit, offset])
                cursor.execute(query, params)
                
                items = []
                for row in cursor.fetchall():
                    try:
                        engagement_metrics = json.loads(row[10]) if row[10] else {}
                        tags = json.loads(row[11]) if row[11] else []
                        mentions = json.loads(row[12]) if row[12] else []
                        images = json.loads(row[13]) if row[13] else []
                        
                        item = {
                            "id": row[0],
                            "source_type": row[1],
                            "source_id": row[2],
                            "group_id": row[3],
                            "title": row[4],
                            "content": row[5],
                            "author": row[6],
                            "author_handle": row[7],
                            "url": row[8],
                            "publication_date": row[9],
                            "engagement_metrics": engagement_metrics,
                            "tags": tags,
                            "mentions": mentions,
                            "images": images,
                            "is_hidden": bool(row[14]),
                            "is_starred": bool(row[15]),
                            "created_at": row[16],
                            "group_name": row[17],
                            "group_color": row[18]
                        }
                        items.append(item)
                        
                    except Exception as e:
                        logger.error(f"Error parsing feed item: {str(e)}")
                        continue
                
                # Get total count
                count_query = f"""
                    SELECT COUNT(*)
                    FROM feed_items fi
                    JOIN feed_keyword_groups fkg ON fi.group_id = fkg.id
                    {where_clause}
                """
                
                count_params = params[:-2]  # Remove limit and offset
                cursor.execute(count_query, count_params)
                total_count = cursor.fetchone()[0]
                
                logger.info(f"Retrieved {len(items)} feed items (total: {total_count})")
                
                return {
                    "success": True,
                    "items": items,
                    "total_count": total_count,
                    "limit": limit,
                    "offset": offset,
                    "has_more": offset + len(items) < total_count
                }
                
        except Exception as e:
            logger.error(f"Error fetching unified feed: {str(e)}")
            return {
                "success": False,
                "error": f"Failed to fetch feed: {str(e)}",
                "items": [],
                "total_count": 0
            }

    def get_group_feed(self, group_id: int, limit: int = 50, offset: int = 0,
                      source_types: List[str] = None, include_hidden: bool = False,
                      combination_sources: List[str] = None, combination_dates: List[str] = None,
                      dateRange: str = None, search: str = None, author: str = None, 
                      min_engagement: int = None, starred: str = None, topic: str = None,
                      sort: str = "publication_date") -> dict:
        """Get feed items for a specific group. Supports combination filter and all other filters."""
        return self.get_unified_feed(
            limit=limit,
            offset=offset,
            group_ids=[group_id],
            source_types=source_types,
            include_hidden=include_hidden,
            combination_sources=combination_sources,
            combination_dates=combination_dates,
            dateRange=dateRange,
            search=search,
            author=author,
            min_engagement=min_engagement,
            starred=starred,
            topic=topic,
            sort=sort
        )

    def hide_feed_item(self, item_id: int) -> Dict[str, Any]:
        """Hide a feed item."""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE feed_items SET is_hidden = 1 WHERE id = ?",
                    (item_id,)
                )
                
                if cursor.rowcount == 0:
                    return {
                        "success": False,
                        "error": f"Feed item {item_id} not found"
                    }
                
                conn.commit()
                
                logger.info(f"Hidden feed item {item_id}")
                return {"success": True}
                
        except Exception as e:
            logger.error(f"Error hiding feed item {item_id}: {str(e)}")
            return {
                "success": False,
                "error": f"Failed to hide item: {str(e)}"
            }

    def star_feed_item(self, item_id: int, starred: bool = True) -> Dict[str, Any]:
        """Star or unstar a feed item."""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE feed_items SET is_starred = ? WHERE id = ?",
                    (starred, item_id)
                )
                
                if cursor.rowcount == 0:
                    return {
                        "success": False,
                        "error": f"Feed item {item_id} not found"
                    }
                
                conn.commit()
                
                action = "starred" if starred else "unstarred"
                logger.info(f"{action.title()} feed item {item_id}")
                return {"success": True, "action": action}
                
        except Exception as e:
            logger.error(f"Error starring feed item {item_id}: {str(e)}")
            return {
                "success": False,
                "error": f"Failed to star item: {str(e)}"
            }

    async def collect_all_active_groups(self, max_items_per_group: int = 20) -> Dict[str, Any]:
        """Collect feed items for all active groups."""
        try:
            logger.info("Collecting feed items for all active groups")
            
            active_groups = self.feed_group_service.get_active_groups_with_sources()
            
            total_collected = 0
            results = []
            
            for group in active_groups:
                result = await self.collect_feed_items_for_group(
                    group["id"], max_items_per_group
                )
                results.append({
                    "group_id": group["id"],
                    "group_name": group["name"],
                    "result": result
                })
                
                if result["success"]:
                    total_collected += result["items_collected"]
            
            logger.info(f"Collected {total_collected} items across {len(active_groups)} groups")
            
            return {
                "success": True,
                "total_items_collected": total_collected,
                "groups_processed": len(active_groups),
                "results": results
            }
            
        except Exception as e:
            logger.error(f"Error collecting for all groups: {str(e)}")
            return {
                "success": False,
                "error": f"Collection failed: {str(e)}"
            }

# Export the service instance
unified_feed_service = UnifiedFeedService() 