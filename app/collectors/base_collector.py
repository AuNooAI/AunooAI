from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from datetime import datetime

class ArticleCollector(ABC):
    """Base class for article collectors."""
    
    @abstractmethod
    async def search_articles(
        self,
        query: str,
        topic: str,
        max_results: int = 10,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Dict]:
        """
        Search for articles based on query and topic.
        
        Args:
            query: Search query string
            topic: Topic name from the application's topics
            max_results: Maximum number of results to return
            start_date: Optional start date for filtering
            end_date: Optional end date for filtering
            
        Returns:
            List of article dictionaries with standardized fields:
            {
                'title': str,
                'summary': str,
                'authors': List[str],
                'published_date': datetime,
                'url': str,
                'source': str,
                'topic': str,
                'raw_data': Dict  # Source-specific raw data
            }
        """
        pass

    @abstractmethod
    async def fetch_article_content(self, url: str) -> Optional[Dict]:
        """
        Fetch full content of an article.
        
        Args:
            url: Article URL or identifier
            
        Returns:
            Dictionary containing article content and metadata
        """
        pass 