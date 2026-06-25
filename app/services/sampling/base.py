"""
Base classes and interfaces for the sampling framework.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from datetime import datetime


@dataclass
class SamplingContext:
    """
    Context passed to scorers, filters, and strategies.
    Contains metadata about the sampling operation.
    """
    topic: Optional[str] = None  # None means all topics
    query: Optional[str] = None  # Search query if applicable
    date_range: Optional[tuple] = None  # (start_date, end_date)
    user_preferences: Dict[str, Any] = field(default_factory=dict)

    # Statistics about the article pool (populated during processing)
    total_articles: int = 0
    categories_seen: Dict[str, int] = field(default_factory=dict)
    sources_seen: Dict[str, int] = field(default_factory=dict)
    topics_seen: Dict[str, int] = field(default_factory=dict)

    # For semantic search context
    similarity_scores: Dict[str, float] = field(default_factory=dict)

    def update_stats(self, articles: List[Dict]) -> None:
        """Update context statistics from article pool."""
        self.total_articles = len(articles)
        self.categories_seen.clear()
        self.sources_seen.clear()
        self.topics_seen.clear()

        for article in articles:
            # Count categories
            category = article.get('category') or article.get('primary_category') or 'Unknown'
            self.categories_seen[category] = self.categories_seen.get(category, 0) + 1

            # Count sources
            source = article.get('source') or article.get('source_name') or 'Unknown'
            self.sources_seen[source] = self.sources_seen.get(source, 0) + 1

            # Count topics
            topic = article.get('topic') or 'Unknown'
            self.topics_seen[topic] = self.topics_seen.get(topic, 0) + 1


class ArticleScorer(ABC):
    """
    Abstract base class for article scoring functions.
    Scorers calculate a 0-100 score for each article based on specific criteria.
    """

    name: str = "base_scorer"
    description: str = "Base article scorer"
    weight: float = 1.0

    @abstractmethod
    def score(self, article: Dict, context: SamplingContext) -> float:
        """
        Calculate score for an article.

        Args:
            article: Article dictionary with fields like title, summary, source, etc.
            context: Sampling context with metadata about the operation

        Returns:
            Score from 0-100 (higher is better)
        """
        pass

    def score_batch(self, articles: List[Dict], context: SamplingContext) -> List[float]:
        """
        Score multiple articles. Override for batch optimization.

        Args:
            articles: List of article dictionaries
            context: Sampling context

        Returns:
            List of scores in same order as input articles
        """
        return [self.score(article, context) for article in articles]

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name='{self.name}', weight={self.weight})"


class FilterStrategy(ABC):
    """
    Abstract base class for filtering articles.
    Filters include or exclude articles based on criteria.
    """

    name: str = "base_filter"
    description: str = "Base filter strategy"

    @abstractmethod
    def filter(self, articles: List[Dict], context: SamplingContext) -> List[Dict]:
        """
        Filter articles based on criteria.

        Args:
            articles: List of article dictionaries
            context: Sampling context with metadata and parameters

        Returns:
            Filtered list of articles (subset of input)
        """
        pass

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name='{self.name}')"


class SamplingStrategy(ABC):
    """
    Abstract base class for sampling strategies.
    Strategies select a subset of articles according to specific algorithms.
    """

    name: str = "base_strategy"
    description: str = "Base sampling strategy"

    @abstractmethod
    def sample(self, articles: List[Dict], limit: int, context: SamplingContext) -> List[Dict]:
        """
        Select articles from pool according to strategy.

        Args:
            articles: List of article dictionaries to sample from
            limit: Maximum number of articles to return
            context: Sampling context with metadata

        Returns:
            Selected articles (up to limit)
        """
        pass

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name='{self.name}')"
