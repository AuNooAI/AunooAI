from typing import Dict, Type, Optional
from .base_collector import ArticleCollector
from .arxiv_collector import ArxivCollector
from .newsapi_collector import NewsAPICollector
from .thenewsapi_collector import TheNewsAPICollector
from .bluesky_collector import BlueskyCollector
from app.database import Database

class CollectorFactory:
    """Factory for creating article collectors."""
    
    _collectors: Dict[str, Type[ArticleCollector]] = {
        'arxiv': ArxivCollector,
        'newsapi': NewsAPICollector,
        'thenewsapi': TheNewsAPICollector,
        'bluesky': BlueskyCollector
    }

    @classmethod
    def get_collector(cls, source: str, db: Optional[Database] = None) -> ArticleCollector:
        """Get a collector instance for the specified source."""
        collector_class = cls._collectors.get(source)
        if not collector_class:
            raise ValueError(f"No collector available for source: {source}")
            
        # Handle collectors that need database instance
        if collector_class == NewsAPICollector:
            if db is None:
                raise ValueError("Database instance required for NewsAPI collector")
            return collector_class(db)
            
        return collector_class()

    @classmethod
    def register_collector(cls, source: str, collector_class: Type[ArticleCollector]):
        """Register a new collector."""
        cls._collectors[source] = collector_class

    @classmethod
    def get_available_sources(cls) -> list[str]:
        """Get list of available source names."""
        return list(cls._collectors.keys()) 