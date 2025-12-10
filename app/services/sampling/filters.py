"""
Filter strategy implementations.
Each filter includes/excludes articles based on specific criteria.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Any

from .base import FilterStrategy, SamplingContext


class TopicFilter(FilterStrategy):
    """
    Filters articles by topic(s).
    """

    name = "topic"
    description = "Filter articles by topic"

    def __init__(self, topics: Optional[List[str]] = None, exclude: bool = False):
        """
        Args:
            topics: List of topic names to include (or exclude if exclude=True)
            exclude: If True, exclude matching topics instead of including
        """
        self.topics = set(t.lower() for t in topics) if topics else None
        self.exclude = exclude

    def filter(self, articles: List[Dict], context: SamplingContext) -> List[Dict]:
        # If no topics specified, use context topic
        topics = self.topics
        if topics is None and context.topic:
            topics = {context.topic.lower()}

        # If still no topics, return all (no filtering)
        if not topics:
            return articles

        result = []
        for article in articles:
            article_topic = (article.get('topic') or '').lower()
            matches = article_topic in topics

            if self.exclude:
                if not matches:
                    result.append(article)
            else:
                if matches:
                    result.append(article)

        return result


class DateRangeFilter(FilterStrategy):
    """
    Filters articles by publication date range.
    """

    name = "date_range"
    description = "Filter articles by publication date range"

    def __init__(self, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None, days_back: Optional[int] = None):
        """
        Args:
            start_date: Earliest publication date to include
            end_date: Latest publication date to include
            days_back: Alternative to start_date - number of days back from now
        """
        self.start_date = start_date
        self.end_date = end_date
        self.days_back = days_back

    def filter(self, articles: List[Dict], context: SamplingContext) -> List[Dict]:
        # Determine date range
        start = self.start_date
        end = self.end_date

        if self.days_back is not None and start is None:
            start = datetime.now() - timedelta(days=self.days_back)

        # Use context date range if not specified
        if context.date_range:
            if start is None:
                start = context.date_range[0]
            if end is None:
                end = context.date_range[1]

        # If no date constraints, return all
        if start is None and end is None:
            return articles

        result = []
        for article in articles:
            pub_date = article.get('pub_date') or article.get('publication_date')
            if not pub_date:
                continue  # Skip articles without dates

            try:
                if isinstance(pub_date, str):
                    if 'T' in pub_date:
                        date_obj = datetime.fromisoformat(pub_date.replace('Z', '+00:00'))
                    else:
                        date_obj = datetime.strptime(pub_date[:10], '%Y-%m-%d')
                elif isinstance(pub_date, datetime):
                    date_obj = pub_date
                else:
                    continue

                # Make naive for comparison
                if date_obj.tzinfo is not None:
                    date_obj = date_obj.replace(tzinfo=None)

                # Check range
                if start and date_obj < start:
                    continue
                if end and date_obj > end:
                    continue

                result.append(article)

            except (ValueError, TypeError):
                continue

        return result


class BiasFilter(FilterStrategy):
    """
    Filters articles by political bias rating.
    """

    name = "bias"
    description = "Filter articles by political bias rating"

    # Standard bias categories
    BIAS_LEVELS = {
        'left': -2,
        'left-center': -1,
        'center': 0,
        'right-center': 1,
        'right': 2
    }

    def __init__(self, allowed_biases: Optional[List[str]] = None, max_bias_deviation: Optional[int] = None):
        """
        Args:
            allowed_biases: List of bias ratings to include (e.g., ['center', 'left-center', 'right-center'])
            max_bias_deviation: Maximum deviation from center (0=center only, 1=center+center-leaning, 2=all)
        """
        self.allowed_biases = set(b.lower() for b in allowed_biases) if allowed_biases else None
        self.max_bias_deviation = max_bias_deviation

    def filter(self, articles: List[Dict], context: SamplingContext) -> List[Dict]:
        # If no constraints, return all
        if self.allowed_biases is None and self.max_bias_deviation is None:
            return articles

        result = []
        for article in articles:
            bias = (article.get('bias') or article.get('political_bias') or '').lower()

            if not bias:
                result.append(article)  # Include articles without bias rating
                continue

            # Check allowed biases
            if self.allowed_biases and bias not in self.allowed_biases:
                continue

            # Check max deviation from center
            if self.max_bias_deviation is not None:
                bias_level = self.BIAS_LEVELS.get(bias, 0)
                if abs(bias_level) > self.max_bias_deviation:
                    continue

            result.append(article)

        return result


class FactualityFilter(FilterStrategy):
    """
    Filters articles by factuality/credibility rating.
    """

    name = "factuality"
    description = "Filter articles by factuality rating"

    # Factuality tiers
    HIGH_FACTUALITY = {'high', 'very high', 'mostly factual', 'factual'}
    MEDIUM_FACTUALITY = {'mixed', 'mostly factual'}

    def __init__(self, min_factuality: str = 'medium'):
        """
        Args:
            min_factuality: Minimum factuality level ('low', 'medium', 'high')
        """
        self.min_factuality = min_factuality.lower()

    def filter(self, articles: List[Dict], context: SamplingContext) -> List[Dict]:
        result = []
        for article in articles:
            factuality = (article.get('factuality') or article.get('credibility') or '').lower()

            if not factuality:
                # Include articles without factuality rating (assume medium)
                if self.min_factuality != 'high':
                    result.append(article)
                continue

            if self.min_factuality == 'high':
                if factuality in self.HIGH_FACTUALITY:
                    result.append(article)
            elif self.min_factuality == 'medium':
                if factuality in self.HIGH_FACTUALITY or factuality in self.MEDIUM_FACTUALITY:
                    result.append(article)
            else:
                result.append(article)  # Low = include all

        return result


class CategoryFilter(FilterStrategy):
    """
    Filters articles by category.
    """

    name = "category"
    description = "Filter articles by category"

    def __init__(self, categories: Optional[List[str]] = None, exclude: bool = False):
        """
        Args:
            categories: List of categories to include (or exclude if exclude=True)
            exclude: If True, exclude matching categories instead of including
        """
        self.categories = set(c.lower() for c in categories) if categories else None
        self.exclude = exclude

    def filter(self, articles: List[Dict], context: SamplingContext) -> List[Dict]:
        if not self.categories:
            return articles

        result = []
        for article in articles:
            # Check various category fields
            article_cats = set()
            if article.get('category'):
                article_cats.add(article['category'].lower())
            if article.get('primary_category'):
                article_cats.add(article['primary_category'].lower())
            if article.get('categories'):
                cats = article['categories']
                if isinstance(cats, str):
                    article_cats.update(c.strip().lower() for c in cats.split(','))
                elif isinstance(cats, list):
                    article_cats.update(c.lower() for c in cats if c)

            if not article_cats:
                article_cats.add('unknown')

            matches = bool(article_cats & self.categories)

            if self.exclude:
                if not matches:
                    result.append(article)
            else:
                if matches:
                    result.append(article)

        return result


class QualityGateFilter(FilterStrategy):
    """
    Filters articles that don't meet minimum quality requirements.
    Checks for required fields and content thresholds.
    """

    name = "quality_gate"
    description = "Filter articles that don't meet minimum quality requirements"

    def __init__(
        self,
        require_title: bool = True,
        require_summary: bool = False,
        min_summary_words: int = 0,
        require_date: bool = False,
        require_url: bool = False,
        require_source: bool = False
    ):
        """
        Args:
            require_title: Require non-empty title
            require_summary: Require non-empty summary
            min_summary_words: Minimum word count for summary
            require_date: Require publication date
            require_url: Require URL/link
            require_source: Require source name
        """
        self.require_title = require_title
        self.require_summary = require_summary
        self.min_summary_words = min_summary_words
        self.require_date = require_date
        self.require_url = require_url
        self.require_source = require_source

    def filter(self, articles: List[Dict], context: SamplingContext) -> List[Dict]:
        result = []
        for article in articles:
            # Check title
            if self.require_title:
                title = article.get('title', '').strip()
                if not title:
                    continue

            # Check summary
            summary = article.get('summary') or article.get('ai_summary') or article.get('content', '')
            if self.require_summary and not summary.strip():
                continue
            if self.min_summary_words > 0:
                word_count = len(summary.split())
                if word_count < self.min_summary_words:
                    continue

            # Check date
            if self.require_date:
                pub_date = article.get('pub_date') or article.get('publication_date')
                if not pub_date:
                    continue

            # Check URL
            if self.require_url:
                url = article.get('link') or article.get('url') or article.get('uri')
                if not url:
                    continue

            # Check source
            if self.require_source:
                source = article.get('source') or article.get('source_name')
                if not source:
                    continue

            result.append(article)

        return result


class CompositeFilter(FilterStrategy):
    """
    Chains multiple filters together.
    Articles must pass ALL filters (AND logic).
    """

    name = "composite"
    description = "Chain multiple filters together (AND logic)"

    def __init__(self, filters: List[FilterStrategy]):
        """
        Args:
            filters: List of filter instances to apply in sequence
        """
        self.filters = filters

    def filter(self, articles: List[Dict], context: SamplingContext) -> List[Dict]:
        result = articles
        for f in self.filters:
            result = f.filter(result, context)
            if not result:
                break  # No articles left, stop filtering
        return result


class DuplicateFilter(FilterStrategy):
    """
    Filters out duplicate articles based on title similarity.
    """

    name = "duplicate"
    description = "Filter out duplicate or near-duplicate articles"

    def __init__(self, similarity_threshold: float = 0.9):
        """
        Args:
            similarity_threshold: Title similarity threshold (0-1) for considering duplicates
        """
        self.similarity_threshold = similarity_threshold

    def _normalize_title(self, title: str) -> str:
        """Normalize title for comparison."""
        import re
        # Lowercase, remove punctuation, normalize whitespace
        title = title.lower()
        title = re.sub(r'[^\w\s]', '', title)
        title = ' '.join(title.split())
        return title

    def _simple_similarity(self, s1: str, s2: str) -> float:
        """Simple word overlap similarity."""
        if not s1 or not s2:
            return 0.0
        words1 = set(s1.split())
        words2 = set(s2.split())
        if not words1 or not words2:
            return 0.0
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        return intersection / union if union > 0 else 0.0

    def filter(self, articles: List[Dict], context: SamplingContext) -> List[Dict]:
        seen_titles: List[str] = []
        result = []

        for article in articles:
            title = self._normalize_title(article.get('title', ''))
            if not title:
                result.append(article)
                continue

            # Check similarity against seen titles
            is_duplicate = False
            for seen in seen_titles:
                if self._simple_similarity(title, seen) >= self.similarity_threshold:
                    is_duplicate = True
                    break

            if not is_duplicate:
                seen_titles.append(title)
                result.append(article)

        return result
