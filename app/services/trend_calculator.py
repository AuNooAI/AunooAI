"""
Trend Calculator

Calculates T1-T5 trend scores from MEASURABLE inputs, not LLM guesses.
This ensures repeatability and transparency in trend scoring.

Trend Definitions:
- T1: Invisible LLM Ecosystems (attention dimension)
- T2: Agentic AI Reshaping Workflows (power dimension)
- T3: Decline of SEO, Rise of GEO (attention dimension)
- T4: Regulatory & Provenance Pressures (power dimension)
- T5: Market Consolidation (money dimension)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class TrendData:
    """Input data for trend score calculation."""
    trend_id: str
    trend_name: str

    # Article-based metrics (measured)
    article_count: int = 0
    recent_30d_count: int = 0
    recent_30d_pct: float = 0.0
    avg_source_score: float = 50.0  # Source credibility average
    source_diversity: int = 0  # Unique sources

    # Velocity metrics (measured from historical data)
    current_month_count: int = 0
    previous_month_count: int = 0
    monthly_counts: List[int] = field(default_factory=list)

    # External signal metrics (from APIs)
    citation_score: Optional[float] = None  # From Semantic Scholar
    funding_activity_score: Optional[float] = None  # From Crunchbase/Google Search
    regulatory_activity_score: Optional[float] = None  # From Google Search


@dataclass
class TrendScore:
    """Result of trend score calculation with full breakdown."""
    trend_id: str
    trend_name: str
    score: float  # 0-100 composite score

    # Component scores (all 0-100)
    article_volume_score: float
    recency_score: float
    source_authority_score: float
    velocity_score: float
    external_signals_score: float

    # Velocity direction
    velocity_direction: str  # 'accelerating', 'stable', 'decelerating'
    velocity_change_pct: float  # Month-over-month % change

    # Data sources used
    data_sources: List[str] = field(default_factory=list)

    # Confidence based on data availability
    confidence: str = "medium"  # 'high', 'medium', 'low'

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trend_id": self.trend_id,
            "trend_name": self.trend_name,
            "score": round(self.score, 1),
            "components": {
                "article_volume": {"score": round(self.article_volume_score, 1), "weight": 0.25},
                "recency": {"score": round(self.recency_score, 1), "weight": 0.20},
                "source_authority": {"score": round(self.source_authority_score, 1), "weight": 0.20},
                "velocity": {"score": round(self.velocity_score, 1), "weight": 0.20},
                "external_signals": {"score": round(self.external_signals_score, 1), "weight": 0.15}
            },
            "velocity": {
                "direction": self.velocity_direction,
                "change_pct": round(self.velocity_change_pct, 1)
            },
            "data_sources": self.data_sources,
            "confidence": self.confidence
        }


class TrendCalculator:
    """
    Calculate T1-T5 scores from measurable inputs.

    This replaces LLM-generated scores with a deterministic formula
    based on countable metrics. The LLM's role shifts to interpretation
    of the calculated score rather than generating it.
    """

    # Configurable weights for score components
    WEIGHTS = {
        "article_volume": 0.25,      # How many articles mention this trend
        "recency": 0.20,             # % from last 30 days
        "source_authority": 0.20,    # Avg source credibility score
        "velocity": 0.20,            # Month-over-month change
        "external_signals": 0.15,    # From external APIs
    }

    # Normalization parameters for article counts
    # These define "typical" and "high" article counts for normalization
    ARTICLE_COUNT_BASELINE = 20  # Expected baseline for 90 days
    ARTICLE_COUNT_MAX = 100  # Considered "very high" activity

    # Velocity thresholds
    VELOCITY_ACCELERATING_THRESHOLD = 20  # +20% MoM = accelerating
    VELOCITY_DECELERATING_THRESHOLD = -15  # -15% MoM = decelerating

    def __init__(
        self,
        weights: Optional[Dict[str, float]] = None,
        normalization: Optional[Dict[str, int]] = None,
        velocity_thresholds: Optional[Dict[str, int]] = None
    ):
        """
        Initialize with optional custom configuration.

        Args:
            weights: Custom weights for score components
            normalization: Custom normalization params (article_count_baseline, article_count_max)
            velocity_thresholds: Custom velocity thresholds (accelerating, decelerating)
        """
        if weights:
            self.weights = {**self.WEIGHTS, **weights}
        else:
            self.weights = self.WEIGHTS.copy()

        # Apply normalization config
        if normalization:
            if "article_count_baseline" in normalization:
                self.ARTICLE_COUNT_BASELINE = normalization["article_count_baseline"]
            if "article_count_max" in normalization:
                self.ARTICLE_COUNT_MAX = normalization["article_count_max"]

        # Apply velocity thresholds
        if velocity_thresholds:
            if "accelerating" in velocity_thresholds:
                self.VELOCITY_ACCELERATING_THRESHOLD = velocity_thresholds["accelerating"]
            if "decelerating" in velocity_thresholds:
                self.VELOCITY_DECELERATING_THRESHOLD = velocity_thresholds["decelerating"]

    def calculate_trend_score(self, data: TrendData) -> TrendScore:
        """
        Calculate a trend score from measured inputs.

        Args:
            data: TrendData with all measured metrics

        Returns:
            TrendScore with composite score and breakdown
        """
        # 1. Article Volume Score (0-100)
        # More articles = higher awareness of this trend
        article_volume_score = self._normalize_article_count(data.article_count)

        # 2. Recency Score (0-100)
        # Higher % of recent articles = more current relevance
        recency_score = min(100, data.recent_30d_pct * 1.5)  # Boost recent activity

        # 3. Source Authority Score (0-100)
        # Already normalized to 0-100 from source credibility
        source_authority_score = data.avg_source_score

        # 4. Velocity Score (0-100)
        # Based on month-over-month change
        velocity_score, velocity_direction, velocity_change = self._calculate_velocity(data)

        # 5. External Signals Score (0-100)
        # Weighted average of available external data
        external_signals_score = self._calculate_external_score(data)

        # Calculate composite score
        composite = (
            self.weights["article_volume"] * article_volume_score +
            self.weights["recency"] * recency_score +
            self.weights["source_authority"] * source_authority_score +
            self.weights["velocity"] * velocity_score +
            self.weights["external_signals"] * external_signals_score
        )

        # Determine data sources used
        data_sources = ["article_database"]
        if data.citation_score is not None:
            data_sources.append("semantic_scholar")
        if data.funding_activity_score is not None:
            data_sources.append("financial_data")
        if data.regulatory_activity_score is not None:
            data_sources.append("regulatory_data")

        # Determine confidence based on data availability
        confidence = self._assess_confidence(data, data_sources)

        return TrendScore(
            trend_id=data.trend_id,
            trend_name=data.trend_name,
            score=composite,
            article_volume_score=article_volume_score,
            recency_score=recency_score,
            source_authority_score=source_authority_score,
            velocity_score=velocity_score,
            external_signals_score=external_signals_score,
            velocity_direction=velocity_direction,
            velocity_change_pct=velocity_change,
            data_sources=data_sources,
            confidence=confidence
        )

    def _normalize_article_count(self, count: int) -> float:
        """
        Normalize article count to 0-100 score.

        Uses a logarithmic scale to prevent extreme values:
        - 0 articles = 0
        - BASELINE articles = 50
        - MAX articles = 90
        - 2x MAX = ~100
        """
        if count <= 0:
            return 0.0

        import math

        # Logarithmic normalization
        # log(count + 1) / log(max + 1) * 100
        log_count = math.log(count + 1)
        log_baseline = math.log(self.ARTICLE_COUNT_BASELINE + 1)
        log_max = math.log(self.ARTICLE_COUNT_MAX * 2 + 1)

        # Scale so baseline = 50, max = 90
        normalized = (log_count / log_max) * 100

        return min(100, max(0, normalized))

    def _calculate_velocity(self, data: TrendData) -> Tuple[float, str, float]:
        """
        Calculate velocity score and direction.

        Returns:
            (velocity_score, direction, change_pct)
        """
        if data.previous_month_count == 0:
            if data.current_month_count > 0:
                # New trend emerging
                return (75.0, "accelerating", 100.0)
            else:
                # No data
                return (50.0, "stable", 0.0)

        # Calculate month-over-month change
        change_pct = ((data.current_month_count - data.previous_month_count)
                      / data.previous_month_count * 100)

        # Determine direction
        if change_pct >= self.VELOCITY_ACCELERATING_THRESHOLD:
            direction = "accelerating"
        elif change_pct <= self.VELOCITY_DECELERATING_THRESHOLD:
            direction = "decelerating"
        else:
            direction = "stable"

        # Convert to 0-100 score
        # -50% change = 25, 0% = 50, +50% change = 75, +100% = 100
        velocity_score = 50 + (change_pct / 2)
        velocity_score = min(100, max(0, velocity_score))

        return (velocity_score, direction, change_pct)

    def _calculate_external_score(self, data: TrendData) -> float:
        """
        Calculate external signals score from available API data.

        If no external data available, returns neutral 50.
        """
        scores = []
        weights = []

        if data.citation_score is not None:
            scores.append(data.citation_score)
            weights.append(1.0)

        if data.funding_activity_score is not None:
            scores.append(data.funding_activity_score)
            weights.append(1.5)  # Funding is a strong signal

        if data.regulatory_activity_score is not None:
            scores.append(data.regulatory_activity_score)
            weights.append(1.0)

        if not scores:
            # No external data available - neutral score
            return 50.0

        # Weighted average
        weighted_sum = sum(s * w for s, w in zip(scores, weights))
        total_weight = sum(weights)

        return weighted_sum / total_weight

    def _assess_confidence(self, data: TrendData, data_sources: List[str]) -> str:
        """
        Assess confidence in the calculated score.

        High confidence: Multiple data sources, sufficient articles
        Medium confidence: One data source or limited articles
        Low confidence: Minimal data
        """
        factors = 0

        # Article count factor
        if data.article_count >= 20:
            factors += 2
        elif data.article_count >= 5:
            factors += 1

        # External data factor
        external_count = len(data_sources) - 1  # Subtract article_database
        factors += external_count

        # Source diversity factor
        if data.source_diversity >= 5:
            factors += 1

        # Historical data factor
        if len(data.monthly_counts) >= 3:
            factors += 1

        if factors >= 5:
            return "high"
        elif factors >= 2:
            return "medium"
        else:
            return "low"

    def calculate_all_trends(
        self,
        articles_by_trend: Dict[str, List[Dict]],
        trend_definitions: Dict[str, Dict],
        external_data: Optional[Dict[str, Dict]] = None
    ) -> Dict[str, TrendScore]:
        """
        Calculate scores for all T1-T5 trends.

        Args:
            articles_by_trend: Dict mapping trend_id to list of articles
            trend_definitions: TREND_DEFINITIONS from pam_service
            external_data: Optional external API data by trend

        Returns:
            Dict mapping trend_id to TrendScore
        """
        results = {}
        external_data = external_data or {}

        for trend_id, definition in trend_definitions.items():
            articles = articles_by_trend.get(trend_id, [])

            # Build TrendData from articles
            data = self._build_trend_data(
                trend_id=trend_id,
                trend_name=definition.get("name", trend_id),
                articles=articles,
                external=external_data.get(trend_id, {})
            )

            # Calculate score
            results[trend_id] = self.calculate_trend_score(data)

        return results

    def _build_trend_data(
        self,
        trend_id: str,
        trend_name: str,
        articles: List[Dict],
        external: Dict[str, Any]
    ) -> TrendData:
        """Build TrendData from articles and external data."""
        from datetime import datetime, timedelta

        now = datetime.now()
        thirty_days_ago = now - timedelta(days=30)
        sixty_days_ago = now - timedelta(days=60)

        # Count articles by time period
        article_count = len(articles)
        recent_30d_count = 0
        current_month_count = 0
        previous_month_count = 0

        # Source tracking
        sources = set()
        source_scores = []

        for article in articles:
            # Get publication date
            date_str = article.get('publication_date') or article.get('submission_date', '')
            if date_str:
                try:
                    if isinstance(date_str, str):
                        pub_date = datetime.fromisoformat(date_str.replace('Z', '+00:00')).replace(tzinfo=None)
                    else:
                        pub_date = date_str.replace(tzinfo=None) if hasattr(date_str, 'replace') else date_str

                    # Recent 30 days
                    if pub_date > thirty_days_ago:
                        recent_30d_count += 1
                        current_month_count += 1
                    elif pub_date > sixty_days_ago:
                        previous_month_count += 1
                except Exception:
                    pass

            # Track sources
            source = article.get('news_source') or article.get('source', 'Unknown')
            sources.add(source)

            # Source credibility score (if available)
            if 'source_score' in article:
                source_scores.append(article['source_score'])

        # Calculate averages
        recent_30d_pct = (recent_30d_count / article_count * 100) if article_count > 0 else 0
        avg_source_score = sum(source_scores) / len(source_scores) if source_scores else 50.0

        return TrendData(
            trend_id=trend_id,
            trend_name=trend_name,
            article_count=article_count,
            recent_30d_count=recent_30d_count,
            recent_30d_pct=recent_30d_pct,
            avg_source_score=avg_source_score,
            source_diversity=len(sources),
            current_month_count=current_month_count,
            previous_month_count=previous_month_count,
            citation_score=external.get('citation_score'),
            funding_activity_score=external.get('funding_activity_score'),
            regulatory_activity_score=external.get('regulatory_activity_score')
        )


def get_interpretation_prompt(trend_score: TrendScore, articles: List[Dict]) -> str:
    """
    Generate a prompt for LLM to INTERPRET the calculated score.

    The LLM does NOT generate the score - it explains it.
    """
    return f"""
Trend: {trend_score.trend_id} - {trend_score.trend_name}

CALCULATED SCORE (from measured data): {trend_score.score:.1f}/100

SCORE BREAKDOWN:
- Article Volume: {trend_score.article_volume_score:.1f}/100 (weight: 25%)
- Recency: {trend_score.recency_score:.1f}/100 (weight: 20%)
- Source Authority: {trend_score.source_authority_score:.1f}/100 (weight: 20%)
- Velocity: {trend_score.velocity_score:.1f}/100 (weight: 20%) - {trend_score.velocity_direction} ({trend_score.velocity_change_pct:+.1f}% MoM)
- External Signals: {trend_score.external_signals_score:.1f}/100 (weight: 15%)

Data Sources: {', '.join(trend_score.data_sources)}
Confidence: {trend_score.confidence}

YOUR TASK:
Based on the articles provided, explain WHY this trend has this score.
Do NOT generate a different score. Interpret and explain the calculated score.

Provide:
1. Key drivers: What's causing this score level?
2. Evidence: Specific findings from articles [cite with numbers]
3. Publisher implications: What does this mean for publishers?
4. Urgency assessment: immediate/near_term/medium_term

Respond with JSON:
{{
    "key_drivers": ["Driver 1 with citation [1]", "Driver 2 with citation [2]"],
    "evidence": [
        {{"finding": "Finding description [1]", "source": "Source name or article title"}},
        {{"finding": "Another finding [2][3]", "source": "Another source name"}}
    ],
    "publisher_implications": "Description with citations [1][4]",
    "urgency": "immediate|near_term|medium_term"
}}
"""
