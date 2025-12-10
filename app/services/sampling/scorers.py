"""
Article scoring implementations.
Each scorer calculates a 0-100 score based on specific criteria.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional
import math

from .base import ArticleScorer, SamplingContext


# Source quality tiers (shared across the application)
HIGH_QUALITY_SOURCES = {
    "reuters", "ft", "financial times", "wsj", "wall street journal", "bloomberg",
    "ap", "associated press", "mit technology review", "nature", "science",
    "wired", "ars technica", "the verge", "techcrunch", "nyt", "new york times",
    "washington post", "guardian", "economist", "bbc", "npr"
}

MEDIUM_QUALITY_SOURCES = {
    "forbes", "fortune", "cnbc", "venturebeat", "zdnet", "cnet", "engadget",
    "ieee spectrum", "hacker news", "medium", "substack", "stratechery",
    "the register", "information", "protocol", "semafor", "axios", "politico"
}


class SourceQualityScorer(ArticleScorer):
    """
    Scores articles based on source credibility tier.
    High-quality sources get higher scores.
    """

    name = "source_quality"
    description = "Scores articles based on source credibility (high/medium/other tiers)"

    def __init__(self, weight: float = 1.0):
        self.weight = weight

    def score(self, article: Dict, context: SamplingContext) -> float:
        source = (article.get('source') or article.get('source_name') or '').lower()

        if any(hs in source for hs in HIGH_QUALITY_SOURCES):
            return 100.0
        elif any(ms in source for ms in MEDIUM_QUALITY_SOURCES):
            return 60.0
        else:
            return 30.0


class RecencyScorer(ArticleScorer):
    """
    Scores articles based on publication date.
    More recent articles get higher scores with exponential decay.
    """

    name = "recency"
    description = "Scores articles based on how recently they were published"

    def __init__(self, weight: float = 1.0, half_life_days: float = 3.0):
        """
        Args:
            weight: Scorer weight for composite scoring
            half_life_days: Number of days for score to decay by half (default 3 days)
        """
        self.weight = weight
        self.half_life_days = half_life_days

    def score(self, article: Dict, context: SamplingContext) -> float:
        pub_date = article.get('pub_date') or article.get('publication_date')

        if not pub_date:
            return 20.0  # Default score for articles without dates

        try:
            if isinstance(pub_date, str):
                if 'T' in pub_date:
                    date_obj = datetime.fromisoformat(pub_date.replace('Z', '+00:00'))
                else:
                    date_obj = datetime.strptime(pub_date[:10], '%Y-%m-%d')
            elif isinstance(pub_date, datetime):
                date_obj = pub_date
            else:
                return 20.0

            # Make naive if needed for comparison
            if date_obj.tzinfo is not None:
                date_obj = date_obj.replace(tzinfo=None)

            now = datetime.now()
            age_days = (now - date_obj).total_seconds() / 86400

            if age_days < 0:
                age_days = 0  # Future dates treated as now

            # Exponential decay: score = 100 * 0.5^(age/half_life)
            decay = math.pow(0.5, age_days / self.half_life_days)
            return max(5.0, 100.0 * decay)  # Minimum score of 5

        except (ValueError, TypeError):
            return 20.0


class ContentQualityScorer(ArticleScorer):
    """
    Scores articles based on content completeness and quality indicators.
    Checks for summary length, title quality, etc.
    """

    name = "content_quality"
    description = "Scores articles based on content completeness (summary length, title, etc.)"

    def __init__(self, weight: float = 1.0):
        self.weight = weight

    def score(self, article: Dict, context: SamplingContext) -> float:
        score = 0.0

        # Title quality (0-25 points)
        title = article.get('title', '')
        if title:
            if len(title) > 20:
                score += 25
            elif len(title) > 10:
                score += 15
            else:
                score += 5

        # Summary/content quality (0-50 points)
        summary = article.get('summary') or article.get('ai_summary') or article.get('content', '')
        if summary:
            word_count = len(summary.split())
            if word_count > 200:
                score += 50
            elif word_count > 100:
                score += 40
            elif word_count > 50:
                score += 30
            elif word_count > 20:
                score += 20
            else:
                score += 10

        # Has categories (0-10 points)
        if article.get('category') or article.get('primary_category') or article.get('categories'):
            score += 10

        # Has sentiment analysis (0-10 points)
        if article.get('sentiment') or article.get('sentiment_score') is not None:
            score += 10

        # Has URL (0-5 points)
        if article.get('link') or article.get('url') or article.get('uri'):
            score += 5

        return min(100.0, score)


class DiversityScorer(ArticleScorer):
    """
    Scores articles to promote diversity in selections.
    Articles from underrepresented categories/sources get higher scores.
    Must be used with context.update_stats() called first.
    """

    name = "diversity"
    description = "Bonus score for articles from underrepresented categories/sources"

    def __init__(self, weight: float = 1.0, category_weight: float = 0.5, source_weight: float = 0.3, topic_weight: float = 0.2):
        """
        Args:
            weight: Overall scorer weight
            category_weight: Weight for category diversity (0-1)
            source_weight: Weight for source diversity (0-1)
            topic_weight: Weight for topic diversity (0-1)
        """
        self.weight = weight
        self.category_weight = category_weight
        self.source_weight = source_weight
        self.topic_weight = topic_weight

    def score(self, article: Dict, context: SamplingContext) -> float:
        if context.total_articles == 0:
            return 50.0  # Neutral score if no stats

        score = 0.0
        total_weight = self.category_weight + self.source_weight + self.topic_weight

        # Category diversity score
        if context.categories_seen and self.category_weight > 0:
            category = article.get('category') or article.get('primary_category') or 'Unknown'
            cat_count = context.categories_seen.get(category, 0)
            # Inverse frequency: rare categories get higher scores
            cat_freq = cat_count / context.total_articles if context.total_articles > 0 else 1
            cat_score = (1 - cat_freq) * 100
            score += cat_score * (self.category_weight / total_weight)

        # Source diversity score
        if context.sources_seen and self.source_weight > 0:
            source = article.get('source') or article.get('source_name') or 'Unknown'
            src_count = context.sources_seen.get(source, 0)
            src_freq = src_count / context.total_articles if context.total_articles > 0 else 1
            src_score = (1 - src_freq) * 100
            score += src_score * (self.source_weight / total_weight)

        # Topic diversity score (for cross-topic mode)
        if context.topics_seen and self.topic_weight > 0:
            topic = article.get('topic') or 'Unknown'
            topic_count = context.topics_seen.get(topic, 0)
            topic_freq = topic_count / context.total_articles if context.total_articles > 0 else 1
            topic_score = (1 - topic_freq) * 100
            score += topic_score * (self.topic_weight / total_weight)

        return score * 100 / 100  # Normalize to 0-100


class SemanticRelevanceScorer(ArticleScorer):
    """
    Scores articles based on semantic similarity to a query.
    Uses pre-computed similarity scores from context.
    """

    name = "semantic_relevance"
    description = "Scores articles based on semantic similarity to search query"

    def __init__(self, weight: float = 1.0):
        self.weight = weight

    def score(self, article: Dict, context: SamplingContext) -> float:
        # Check for similarity score in article or context
        similarity = article.get('similarity_score') or article.get('similarity')

        if similarity is None:
            # Check context similarity scores by article ID
            article_id = str(article.get('id') or article.get('uri', ''))
            similarity = context.similarity_scores.get(article_id)

        if similarity is not None:
            # Similarity scores are typically 0-1, convert to 0-100
            return min(100.0, max(0.0, float(similarity) * 100))

        # No similarity score available - return neutral
        return 50.0


class CompositeScorer(ArticleScorer):
    """
    Combines multiple scorers with configurable weights.
    """

    name = "composite"
    description = "Combines multiple scorers with weighted averaging"

    def __init__(self, scorers: List[ArticleScorer], normalize: bool = True):
        """
        Args:
            scorers: List of scorer instances (each with its own weight)
            normalize: If True, normalize weights to sum to 1
        """
        self.scorers = scorers
        self.normalize = normalize
        self.weight = 1.0

    def score(self, article: Dict, context: SamplingContext) -> float:
        if not self.scorers:
            return 50.0

        total_weight = sum(s.weight for s in self.scorers) if self.normalize else 1.0
        if total_weight == 0:
            return 50.0

        weighted_sum = 0.0
        for scorer in self.scorers:
            s = scorer.score(article, context)
            weighted_sum += s * scorer.weight

        return weighted_sum / total_weight if self.normalize else weighted_sum

    def score_batch(self, articles: List[Dict], context: SamplingContext) -> List[float]:
        """Optimized batch scoring."""
        if not self.scorers:
            return [50.0] * len(articles)

        # Get scores from all scorers
        all_scores = []
        for scorer in self.scorers:
            all_scores.append(scorer.score_batch(articles, context))

        # Combine scores
        total_weight = sum(s.weight for s in self.scorers) if self.normalize else 1.0
        if total_weight == 0:
            return [50.0] * len(articles)

        result = []
        for i in range(len(articles)):
            weighted_sum = sum(
                all_scores[j][i] * self.scorers[j].weight
                for j in range(len(self.scorers))
            )
            result.append(weighted_sum / total_weight if self.normalize else weighted_sum)

        return result
