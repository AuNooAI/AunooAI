"""
Trend Scorer Service

Calculates measurable trend metrics for emerging themes:
- Volume score: Article count vs baseline
- Velocity score: Growth rate over time window
- Diversity score: Source diversity
- Novelty score: Average article novelty

Inspired by TrendCalculator pattern from PAM.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from collections import Counter
from sqlalchemy import text

from app.database import get_database_instance

logger = logging.getLogger(__name__)


@dataclass
class TrendScore:
    """Trend metrics for a theme."""
    volume_score: float = 0.0        # 0-100: Article count vs baseline
    velocity_score: float = 0.0      # 0-100: Growth rate over time
    diversity_score: float = 0.0     # 0-100: Source diversity
    novelty_score: float = 0.0       # 0-100: Avg article novelty
    composite_score: float = 0.0     # 0-100: Weighted combination
    velocity_label: str = "stable"   # 'accelerating', 'stable', 'decelerating'
    article_count: int = 0
    source_count: int = 0
    articles_first_half: int = 0
    articles_second_half: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "volume_score": round(self.volume_score, 1),
            "velocity_score": round(self.velocity_score, 1),
            "diversity_score": round(self.diversity_score, 1),
            "novelty_score": round(self.novelty_score, 1),
            "composite_score": round(self.composite_score, 1),
            "velocity_label": self.velocity_label,
            "article_count": self.article_count,
            "source_count": self.source_count,
            "articles_first_half": self.articles_first_half,
            "articles_second_half": self.articles_second_half,
        }


class TrendScorer:
    """
    Calculates trend metrics for emerging themes.
    """

    def __init__(
        self,
        avg_topic_size: float = 10.0,  # Baseline for volume scoring
        weights: Optional[Dict[str, float]] = None
    ):
        self.avg_topic_size = avg_topic_size
        self.weights = weights or {
            "volume": 0.25,
            "velocity": 0.30,
            "diversity": 0.20,
            "novelty": 0.25
        }

    def _get_connection(self):
        """Get database connection."""
        db = get_database_instance()
        return db._temp_get_connection()

    def _fetch_article_metadata(
        self,
        article_uris: List[str]
    ) -> List[Dict[str, Any]]:
        """Fetch article metadata for scoring."""
        if not article_uris:
            return []

        conn = None
        try:
            conn = self._get_connection()

            placeholders = ", ".join([f":uri_{i}" for i in range(len(article_uris))])
            params = {f"uri_{i}": uri for i, uri in enumerate(article_uris)}

            stmt = text(f"""
                SELECT a.uri, a.news_source, a.publication_date,
                       COALESCE(n.composite_novelty_score, 50) as novelty_score
                FROM articles a
                LEFT JOIN article_novelty_scores n ON a.uri = n.article_uri
                WHERE a.uri IN ({placeholders})
            """)

            result = conn.execute(stmt, params)
            return [dict(row) for row in result.mappings()]

        except Exception as exc:
            logger.error(f"Error fetching article metadata: {exc}")
            return []
        finally:
            if conn:
                conn.close()

    def _parse_date(self, date_val: Any) -> Optional[datetime]:
        """Parse date from various formats."""
        if date_val is None:
            return None

        if isinstance(date_val, datetime):
            return date_val

        try:
            date_str = str(date_val)
            # Try common formats
            for fmt in ["%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"]:
                try:
                    return datetime.strptime(date_str[:len(fmt.replace("%", "").replace("-", "").replace(":", "").replace("T", "").replace(" ", "")) + 4], fmt)
                except ValueError:
                    continue
            # Fallback: try parsing just the date part
            return datetime.strptime(date_str[:10], "%Y-%m-%d")
        except Exception:
            return None

    def calculate_volume_score(self, article_count: int) -> float:
        """
        Calculate volume score based on article count vs baseline.

        Score formula: min(100, (count / baseline) * 50)
        - 10 articles (1x baseline) = 50
        - 20 articles (2x baseline) = 100
        """
        if article_count <= 0:
            return 0.0

        ratio = article_count / self.avg_topic_size
        score = min(100, ratio * 50)
        return score

    def calculate_velocity_score(
        self,
        articles: List[Dict[str, Any]],
        days_back: int = 7
    ) -> tuple:
        """
        Calculate velocity score by comparing first half vs second half of time window.

        Returns (score, label, first_half_count, second_half_count)
        """
        if not articles:
            return (50.0, "stable", 0, 0)

        # Parse dates
        dated_articles = []
        for article in articles:
            dt = self._parse_date(article.get("publication_date"))
            if dt:
                dated_articles.append(dt)

        if not dated_articles:
            return (50.0, "stable", 0, 0)

        # Define time window
        now = datetime.now()
        window_start = now - timedelta(days=days_back)
        midpoint = window_start + timedelta(days=days_back / 2)

        # Count articles in each half
        first_half = sum(1 for dt in dated_articles if window_start <= dt < midpoint)
        second_half = sum(1 for dt in dated_articles if midpoint <= dt <= now)

        # Calculate velocity ratio
        if first_half == 0 and second_half == 0:
            return (50.0, "stable", 0, 0)
        elif first_half == 0:
            # All articles in second half - accelerating
            velocity_ratio = 2.0
        else:
            velocity_ratio = second_half / first_half

        # Convert to score
        # ratio < 0.5 = decelerating
        # ratio 0.5-1.5 = stable
        # ratio > 1.5 = accelerating
        if velocity_ratio < 0.5:
            score = max(0, 25 + (velocity_ratio * 50))  # 0-50
            label = "decelerating"
        elif velocity_ratio <= 1.5:
            score = 50 + ((velocity_ratio - 0.5) * 25)  # 50-75
            label = "stable"
        else:
            score = min(100, 75 + ((velocity_ratio - 1.5) * 25))  # 75-100
            label = "accelerating"

        return (score, label, first_half, second_half)

    def calculate_diversity_score(self, articles: List[Dict[str, Any]]) -> tuple:
        """
        Calculate source diversity score.

        Returns (score, unique_source_count)
        """
        if not articles:
            return (0.0, 0)

        sources = [a.get("news_source", "Unknown") for a in articles]
        unique_sources = len(set(sources))

        # Score formula: min(100, unique_sources * 15)
        # 1 source = 15, 3 sources = 45, 7+ sources = 100
        score = min(100, unique_sources * 15)

        return (score, unique_sources)

    def calculate_novelty_score(self, articles: List[Dict[str, Any]]) -> float:
        """
        Calculate average novelty score across articles.
        """
        if not articles:
            return 50.0

        novelty_scores = [
            a.get("novelty_score", 50)
            for a in articles
            if a.get("novelty_score") is not None
        ]

        if not novelty_scores:
            return 50.0

        return sum(novelty_scores) / len(novelty_scores)

    def calculate(
        self,
        article_uris: List[str],
        days_back: int = 7
    ) -> TrendScore:
        """
        Calculate all trend metrics for a set of articles.

        Args:
            article_uris: List of article URIs in the theme
            days_back: Time window for velocity calculation

        Returns:
            TrendScore with all metrics
        """
        result = TrendScore()

        if not article_uris:
            return result

        # Fetch article metadata
        articles = self._fetch_article_metadata(article_uris)

        result.article_count = len(articles)

        # Volume score
        result.volume_score = self.calculate_volume_score(len(articles))

        # Velocity score
        vel_score, vel_label, first, second = self.calculate_velocity_score(
            articles, days_back
        )
        result.velocity_score = vel_score
        result.velocity_label = vel_label
        result.articles_first_half = first
        result.articles_second_half = second

        # Diversity score
        div_score, source_count = self.calculate_diversity_score(articles)
        result.diversity_score = div_score
        result.source_count = source_count

        # Novelty score
        result.novelty_score = self.calculate_novelty_score(articles)

        # Composite score
        result.composite_score = (
            self.weights["volume"] * result.volume_score +
            self.weights["velocity"] * result.velocity_score +
            self.weights["diversity"] * result.diversity_score +
            self.weights["novelty"] * result.novelty_score
        )

        logger.debug(
            f"Trend score: vol={result.volume_score:.1f}, vel={result.velocity_score:.1f}, "
            f"div={result.diversity_score:.1f}, nov={result.novelty_score:.1f}, "
            f"composite={result.composite_score:.1f}, label={result.velocity_label}"
        )

        return result

    def calculate_for_theme(self, theme: Any, days_back: int = 7) -> TrendScore:
        """
        Convenience method that takes a ProposedTheme object.
        """
        return self.calculate(
            article_uris=theme.article_uris,
            days_back=days_back
        )
