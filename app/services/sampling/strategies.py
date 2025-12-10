"""
Sampling strategy implementations.
Each strategy selects articles from a pool using different algorithms.
"""

from datetime import datetime
from typing import Dict, List, Optional
import random
from collections import defaultdict

from .base import SamplingStrategy, SamplingContext, ArticleScorer
from .scorers import RecencyScorer, SourceQualityScorer, DiversityScorer, CompositeScorer, ContentQualityScorer


class RecencySampling(SamplingStrategy):
    """
    Selects the most recent articles first.
    """

    name = "recency"
    description = "Select the most recent articles"

    def sample(self, articles: List[Dict], limit: int, context: SamplingContext) -> List[Dict]:
        def get_date(article: Dict) -> datetime:
            pub_date = article.get('pub_date') or article.get('publication_date')
            if not pub_date:
                return datetime.min

            try:
                if isinstance(pub_date, str):
                    if 'T' in pub_date:
                        return datetime.fromisoformat(pub_date.replace('Z', '+00:00')).replace(tzinfo=None)
                    return datetime.strptime(pub_date[:10], '%Y-%m-%d')
                elif isinstance(pub_date, datetime):
                    return pub_date.replace(tzinfo=None) if pub_date.tzinfo else pub_date
            except (ValueError, TypeError):
                return datetime.min

            return datetime.min

        sorted_articles = sorted(articles, key=get_date, reverse=True)
        return sorted_articles[:limit]


class QualitySampling(SamplingStrategy):
    """
    Selects highest quality articles using composite scoring.
    """

    name = "quality"
    description = "Select highest quality articles based on source and content"

    def __init__(self, scorer: Optional[ArticleScorer] = None):
        """
        Args:
            scorer: Custom scorer to use. If None, uses default composite scorer.
        """
        self.scorer = scorer or CompositeScorer([
            SourceQualityScorer(weight=2.0),
            ContentQualityScorer(weight=1.0),
            RecencyScorer(weight=1.0, half_life_days=7.0)
        ])

    def sample(self, articles: List[Dict], limit: int, context: SamplingContext) -> List[Dict]:
        if not articles:
            return []

        # Score all articles
        scores = self.scorer.score_batch(articles, context)

        # Sort by score descending
        scored = list(zip(articles, scores))
        scored.sort(key=lambda x: x[1], reverse=True)

        return [article for article, score in scored[:limit]]


class DiversitySampling(SamplingStrategy):
    """
    Selects articles to maximize diversity across categories and sources.
    Uses round-robin selection to ensure representation.
    """

    name = "diversity"
    description = "Select articles for maximum diversity across categories/sources"

    def __init__(self, category_weight: float = 0.5, source_weight: float = 0.3, topic_weight: float = 0.2):
        """
        Args:
            category_weight: Importance of category diversity (0-1)
            source_weight: Importance of source diversity (0-1)
            topic_weight: Importance of topic diversity (0-1, for cross-topic mode)
        """
        self.category_weight = category_weight
        self.source_weight = source_weight
        self.topic_weight = topic_weight

    def sample(self, articles: List[Dict], limit: int, context: SamplingContext) -> List[Dict]:
        if not articles:
            return []

        if len(articles) <= limit:
            return articles

        # Group articles by primary dimension (category)
        by_category: Dict[str, List[Dict]] = defaultdict(list)
        for article in articles:
            cat = article.get('category') or article.get('primary_category') or 'Unknown'
            by_category[cat].append(article)

        # Round-robin selection across categories
        selected = []
        selected_ids = set()

        # Keep selecting until we hit limit or exhaust all articles
        while len(selected) < limit:
            added_this_round = False
            for cat in list(by_category.keys()):
                if len(selected) >= limit:
                    break

                pool = by_category[cat]
                # Find an article not yet selected
                for i, article in enumerate(pool):
                    article_id = article.get('id') or article.get('uri') or article.get('title', '')
                    if article_id not in selected_ids:
                        selected.append(article)
                        selected_ids.add(article_id)
                        pool.pop(i)
                        added_this_round = True
                        break

                # Remove empty categories
                if not pool:
                    del by_category[cat]

            if not added_this_round:
                break  # No more articles to add

        return selected


class TopicBalancedSampling(SamplingStrategy):
    """
    Selects articles with balanced representation across topics.
    Useful for "All Topics" mode.
    """

    name = "topic_balanced"
    description = "Select articles with balanced representation across topics"

    def __init__(self, min_per_topic: int = 3, proportional: bool = True):
        """
        Args:
            min_per_topic: Minimum articles per topic (if available)
            proportional: If True, allocate remaining slots proportionally to topic size
        """
        self.min_per_topic = min_per_topic
        self.proportional = proportional

    def sample(self, articles: List[Dict], limit: int, context: SamplingContext) -> List[Dict]:
        if not articles:
            return []

        if len(articles) <= limit:
            return articles

        # Group by topic
        by_topic: Dict[str, List[Dict]] = defaultdict(list)
        for article in articles:
            topic = article.get('topic') or 'Unknown'
            by_topic[topic].append(article)

        # Sort articles within each topic by recency
        recency_sampler = RecencySampling()
        for topic in by_topic:
            by_topic[topic] = recency_sampler.sample(by_topic[topic], len(by_topic[topic]), context)

        selected = []
        topics = list(by_topic.keys())
        num_topics = len(topics)

        if num_topics == 0:
            return []

        # Phase 1: Ensure minimum per topic
        for topic in topics:
            pool = by_topic[topic]
            take = min(self.min_per_topic, len(pool), limit - len(selected))
            if take > 0:
                selected.extend(pool[:take])
                by_topic[topic] = pool[take:]

        # Phase 2: Fill remaining slots
        remaining = limit - len(selected)
        if remaining > 0 and self.proportional:
            # Allocate proportionally to remaining pool sizes
            total_remaining = sum(len(pool) for pool in by_topic.values())
            if total_remaining > 0:
                for topic in topics:
                    pool = by_topic[topic]
                    if not pool:
                        continue
                    # Proportional allocation
                    allocation = int((len(pool) / total_remaining) * remaining)
                    take = min(allocation, len(pool))
                    if take > 0:
                        selected.extend(pool[:take])

        # Phase 3: If still under limit, round-robin the rest
        while len(selected) < limit:
            added = False
            for topic in topics:
                if len(selected) >= limit:
                    break
                pool = by_topic[topic]
                if pool:
                    selected.append(pool.pop(0))
                    added = True
            if not added:
                break

        return selected[:limit]


class SemanticSampling(SamplingStrategy):
    """
    Selects articles with highest semantic relevance to a query.
    """

    name = "semantic"
    description = "Select articles most semantically relevant to the query"

    def sample(self, articles: List[Dict], limit: int, context: SamplingContext) -> List[Dict]:
        if not articles:
            return []

        # Sort by similarity score
        def get_similarity(article: Dict) -> float:
            sim = article.get('similarity_score') or article.get('similarity')
            if sim is not None:
                return float(sim)

            # Check context
            article_id = str(article.get('id') or article.get('uri', ''))
            return context.similarity_scores.get(article_id, 0.0)

        sorted_articles = sorted(articles, key=get_similarity, reverse=True)
        return sorted_articles[:limit]


class CompositeSampling(SamplingStrategy):
    """
    Combines multiple sampling strategies with weighted allocation.
    """

    name = "composite"
    description = "Combine multiple sampling strategies with weighted allocation"

    def __init__(self, strategies: List[tuple], deduplicate: bool = True):
        """
        Args:
            strategies: List of (strategy, weight) tuples. Weights determine allocation proportion.
            deduplicate: If True, remove duplicates across strategies
        """
        self.strategies = strategies
        self.deduplicate = deduplicate

    def sample(self, articles: List[Dict], limit: int, context: SamplingContext) -> List[Dict]:
        if not articles or not self.strategies:
            return []

        # Calculate allocation per strategy
        total_weight = sum(w for _, w in self.strategies)
        if total_weight == 0:
            return []

        selected = []
        selected_ids = set()

        for strategy, weight in self.strategies:
            allocation = int((weight / total_weight) * limit)
            if allocation == 0:
                continue

            # Get candidates from strategy
            if self.deduplicate:
                # Filter out already selected articles
                remaining = [
                    a for a in articles
                    if (a.get('id') or a.get('uri') or a.get('title', '')) not in selected_ids
                ]
                candidates = strategy.sample(remaining, allocation, context)
            else:
                candidates = strategy.sample(articles, allocation, context)

            for article in candidates:
                if len(selected) >= limit:
                    break
                article_id = article.get('id') or article.get('uri') or article.get('title', '')
                if not self.deduplicate or article_id not in selected_ids:
                    selected.append(article)
                    selected_ids.add(article_id)

        # Fill remaining slots with any unselected articles
        if len(selected) < limit and self.deduplicate:
            for article in articles:
                if len(selected) >= limit:
                    break
                article_id = article.get('id') or article.get('uri') or article.get('title', '')
                if article_id not in selected_ids:
                    selected.append(article)
                    selected_ids.add(article_id)

        return selected


class RecencyDiversitySampling(SamplingStrategy):
    """
    Default strategy for "All Topics" mode.
    Combines recency with diversity: 70% recent articles, 30% diversity fill.
    """

    name = "recency_diversity"
    description = "Recent articles balanced across categories/sources (default for All Topics)"

    def __init__(self, recency_ratio: float = 0.7):
        """
        Args:
            recency_ratio: Proportion of limit to fill with recent articles (0-1)
        """
        self.recency_ratio = recency_ratio
        self.recency_sampler = RecencySampling()
        self.diversity_sampler = DiversitySampling()

    def sample(self, articles: List[Dict], limit: int, context: SamplingContext) -> List[Dict]:
        if not articles:
            return []

        if len(articles) <= limit:
            return articles

        # Update context with article stats for diversity scoring
        context.update_stats(articles)

        # Phase 1: Get recent articles
        recency_limit = int(limit * self.recency_ratio)
        recent = self.recency_sampler.sample(articles, recency_limit, context)
        selected_ids = {a.get('id') or a.get('uri') or a.get('title', '') for a in recent}

        # Phase 2: Fill remaining with diverse selection
        remaining_pool = [
            a for a in articles
            if (a.get('id') or a.get('uri') or a.get('title', '')) not in selected_ids
        ]
        diversity_limit = limit - len(recent)

        if diversity_limit > 0 and remaining_pool:
            diverse = self.diversity_sampler.sample(remaining_pool, diversity_limit, context)
            return recent + diverse

        return recent


class RandomSampling(SamplingStrategy):
    """
    Selects articles randomly. Useful as a baseline or for variety.
    """

    name = "random"
    description = "Select articles randomly"

    def __init__(self, seed: Optional[int] = None):
        """
        Args:
            seed: Random seed for reproducibility (optional)
        """
        self.seed = seed

    def sample(self, articles: List[Dict], limit: int, context: SamplingContext) -> List[Dict]:
        if not articles:
            return []

        if len(articles) <= limit:
            return articles

        if self.seed is not None:
            random.seed(self.seed)

        return random.sample(articles, min(limit, len(articles)))
