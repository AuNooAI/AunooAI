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
        """Return list of collector source names that are currently usable.

        Sources which rely on provider credentials (API keys or username/password)
        will be included only when the required environment variables are present.
        This prevents the frontend collect page from showing sources that the
        user has not configured yet.
        """
        import os

        def _is_configured(source: str) -> bool:  # noqa: ANN001
            """Return True if the given source has the credentials it needs."""

            if source == "newsapi":
                return any(
                    os.getenv(env)
                    for env in (
                        "PROVIDER_NEWSAPI_API_KEY",
                        "PROVIDER_NEWSAPI_KEY",
                        "NEWSAPI_KEY",
                    )
                )

            if source == "thenewsapi":
                return any(
                    os.getenv(env)
                    for env in (
                        "PROVIDER_THENEWSAPI_API_KEY",
                        "PROVIDER_THENEWSAPI_KEY",
                    )
                )

            if source == "bluesky":
                return os.getenv("PROVIDER_BLUESKY_USERNAME") and os.getenv(
                    "PROVIDER_BLUESKY_PASSWORD"
                )

            # arxiv and others do not require credentials
            return True

        return [name for name in cls._collectors.keys() if _is_configured(name)] 