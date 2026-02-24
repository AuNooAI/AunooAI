"""
Emerging Topics Service (v2 - LLM-Driven)

Main orchestration service for emerging topic detection.
Uses multi-step LLM-driven pipeline:
1. Sample high-novelty articles
2. LLM proposes specific themes
3. Semantic search assigns articles to themes
4. Validate and merge themes
5. Deep analysis for actors/events
6. Calculate trend scores
"""

import logging
import json as json_module
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional, Any, AsyncGenerator, Callable
from sqlalchemy import text

from app.database import get_database_instance
from .novelty_scorer import NoveltyScorer, NoveltyConfig
from .theme_proposer import ThemeProposer, ProposedTheme
from .theme_validator import ThemeValidator
from .deep_analyzer import DeepAnalyzer, DeepAnalysis
from .trend_scorer import TrendScorer, TrendScore
from .article_validator import ArticleValidator

# Keep old imports for backwards compatibility
from .cluster_detector import ClusterDetector, ClusterConfig, ClusterResult, ArticleCluster
from .temporal_tracker import TemporalTracker, TemporalConfig, ClusterChange
from .topic_summarizer import TopicSummarizer, TopicSummary

logger = logging.getLogger(__name__)


@dataclass
class EmergingTopicsConfig:
    """Configuration for emerging topics detection."""
    novelty_config: NoveltyConfig = field(default_factory=NoveltyConfig)
    cluster_config: ClusterConfig = field(default_factory=ClusterConfig)
    temporal_config: TemporalConfig = field(default_factory=TemporalConfig)

    # Processing settings
    days_back: int = 7
    min_articles_for_theme: int = 3
    novelty_threshold: float = 70.0

    # Theme proposal settings
    max_sample_articles: int = 250
    max_articles_per_theme: int = 30
    theme_distance_threshold: float = 0.85  # Higher threshold needed - distances are typically 0.70-0.85

    # LLM settings
    summarization_model: str = "gpt-4o"
    model: str = "gpt-4o"  # Primary model selection (overrides summarization_model if set)
    max_articles_for_analysis: int = 15


@dataclass
class EmergingTopic:
    """Represents a detected emerging topic (v2)."""
    id: Optional[int] = None
    topic_label: str = ""
    topic_description: str = ""
    detection_date: date = None
    detection_type: str = "llm_proposed"  # 'llm_proposed', 'new_cluster', etc.

    cluster_id: str = ""
    article_count: int = 0
    article_uris: List[str] = field(default_factory=list)

    # V2: Key entities from proposal
    key_entities: List[str] = field(default_factory=list)
    why_emerging: str = ""
    search_query: str = ""

    # V2: Deep analysis
    actors: Dict[str, List[str]] = field(default_factory=dict)
    events: Dict[str, Any] = field(default_factory=dict)
    implications: Dict[str, str] = field(default_factory=dict)
    organization_implications: Dict[str, str] = field(default_factory=dict)
    signals: Dict[str, List[str]] = field(default_factory=dict)
    synthesis: Dict[str, Any] = field(default_factory=dict)

    # V2: Trend score
    volume_score: float = 0.0
    velocity_score: float = 0.0
    diversity_score: float = 0.0
    novelty_score: float = 0.0
    composite_score: float = 0.0
    velocity: str = "stable"
    source_count: int = 0

    # Legacy fields
    growth_rate: float = 0.0
    avg_novelty_score: float = 0.0
    confidence_score: float = 0.0
    key_themes: List[str] = field(default_factory=list)
    representative_keywords: List[str] = field(default_factory=list)
    emergence_rationale: str = ""

    status: str = "active"

    # V3: Temporal tracking
    first_detection_date: Optional[date] = None
    last_detection_date: Optional[date] = None
    detection_count: int = 1
    consecutive_detections: int = 1
    missed_runs: int = 0
    trajectory: Optional[str] = None  # 'rising', 'stable', 'declining', 'volatile'

    # Future horizons (saved scenarios)
    future_horizons: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "topic_label": self.topic_label,
            "topic_description": self.topic_description,
            "detection_date": str(self.detection_date) if self.detection_date else None,
            "detection_type": self.detection_type,
            "cluster_id": self.cluster_id,
            "article_count": self.article_count,
            # V2 fields
            "key_entities": self.key_entities,
            "why_emerging": self.why_emerging,
            "actors": self.actors,
            "events": self.events,
            "implications": self.implications,
            "organization_implications": self.organization_implications,
            "signals": self.signals,
            "synthesis": self.synthesis,
            "future_horizons": self.future_horizons,
            # Trend scores
            "trend_score": {
                "volume": round(self.volume_score, 1),
                "velocity": round(self.velocity_score, 1),
                "diversity": round(self.diversity_score, 1),
                "novelty": round(self.novelty_score, 1),
                "composite": round(self.composite_score, 1),
            },
            "velocity": self.velocity,
            "source_count": self.source_count,
            # Legacy
            "growth_rate": round(self.growth_rate, 2),
            "confidence_score": round(self.confidence_score, 2),
            "key_themes": self.key_themes,
            "representative_keywords": self.representative_keywords,
            "status": self.status,
            # Temporal tracking
            "first_detection_date": str(self.first_detection_date) if self.first_detection_date else None,
            "last_detection_date": str(self.last_detection_date) if self.last_detection_date else None,
            "detection_count": self.detection_count,
            "consecutive_detections": self.consecutive_detections,
            "missed_runs": self.missed_runs,
            "trajectory": self.trajectory,
        }


class EmergingTopicsService:
    """
    Main service orchestrating emerging topic detection (v2 - LLM-driven).
    """

    def __init__(
        self,
        config: Optional[EmergingTopicsConfig] = None,
        ai_model_getter: Optional[Callable] = None,
        embedding_model_getter: Optional[Callable] = None
    ):
        self.config = config or EmergingTopicsConfig()
        self.ai_model_getter = ai_model_getter
        self.embedding_model_getter = embedding_model_getter

        # Use config.model as primary, fallback to summarization_model
        model_to_use = self.config.model or self.config.summarization_model

        # V2 services
        self.theme_proposer = ThemeProposer(
            ai_model_getter=ai_model_getter,
            embedding_model_getter=embedding_model_getter,
            default_model=model_to_use
        )
        self.theme_validator = ThemeValidator(
            min_articles=self.config.min_articles_for_theme,
            max_pairwise_distance=0.40,
            merge_overlap_threshold=0.60
        )
        self.deep_analyzer = DeepAnalyzer(
            ai_model_getter=ai_model_getter,
            default_model=model_to_use
        )
        self.article_validator = ArticleValidator(
            ai_model_getter=ai_model_getter,
            model_name=model_to_use
        )
        self.trend_scorer = TrendScorer()

        # Legacy services (kept for fallback/comparison)
        self.novelty_scorer = NoveltyScorer(self.config.novelty_config)
        self.cluster_detector = ClusterDetector(self.config.cluster_config)
        self.temporal_tracker = TemporalTracker(self.config.temporal_config)
        self.topic_summarizer = TopicSummarizer(
            ai_model_getter=ai_model_getter,
            default_model=model_to_use
        )

    def _get_connection(self):
        """Get database connection."""
        db = get_database_instance()
        return db._temp_get_connection()

    def _get_default_org_profile(self) -> Optional[Dict[str, Any]]:
        """Fetch the default organizational profile for context-aware analysis."""
        conn = None
        try:
            conn = self._get_connection()
            stmt = text("""
                SELECT id, name, description, industry, organization_type,
                       key_concerns, strategic_priorities, risk_tolerance,
                       innovation_appetite, decision_making_style,
                       stakeholder_focus, competitive_landscape,
                       regulatory_environment, custom_context, region
                FROM organizational_profiles
                WHERE is_default = true
                LIMIT 1
            """)
            result = conn.execute(stmt)
            row = result.fetchone()

            if row:
                row_dict = dict(row._mapping)
                # Parse JSON fields
                for json_field in ['key_concerns', 'strategic_priorities', 'stakeholder_focus',
                                   'competitive_landscape', 'regulatory_environment']:
                    if row_dict.get(json_field):
                        try:
                            if isinstance(row_dict[json_field], str):
                                row_dict[json_field] = json_module.loads(row_dict[json_field])
                        except (json_module.JSONDecodeError, TypeError):
                            row_dict[json_field] = []
                return row_dict
            return None

        except Exception as e:
            logger.warning(f"Error fetching default org profile: {e}")
            return None
        finally:
            if conn:
                conn.close()

    async def _fetch_articles_for_validation(
        self,
        article_uris: List[str]
    ) -> List[Dict[str, Any]]:
        """Fetch article details for validation."""
        if not article_uris:
            return []

        conn = None
        try:
            conn = self._get_connection()

            placeholders = ", ".join([f":uri_{i}" for i in range(len(article_uris))])
            params = {f"uri_{i}": uri for i, uri in enumerate(article_uris)}

            stmt = text(f"""
                SELECT uri, title, summary, news_source, publication_date
                FROM articles
                WHERE uri IN ({placeholders})
            """)

            result = conn.execute(stmt, params)
            articles = []
            for row in result.mappings():
                articles.append(dict(row))

            return articles

        except Exception as e:
            logger.error(f"Error fetching articles for validation: {e}")
            return []
        finally:
            if conn:
                conn.close()

    async def run_detection_streaming(
        self,
        topic_filter: Optional[str] = None,
        days_back: Optional[int] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Run v2 LLM-driven detection with streaming progress updates.
        """
        days = days_back or self.config.days_back
        detection_date = date.today()
        start_time = time.time()

        # Create detection run record
        run_config = {
            "days_back": days,
            "max_sample_articles": self.config.max_sample_articles,
            "distance_threshold": self.config.theme_distance_threshold,
            "min_articles_for_theme": self.config.min_articles_for_theme,
            "max_articles_per_theme": self.config.max_articles_per_theme,
        }
        model_name = getattr(self.theme_proposer, 'default_model', 'gpt-4o') if self.theme_proposer else 'gpt-4o'
        run_id = self._create_detection_run(topic_filter, run_config, model_name)

        yield {
            "step": 1,
            "progress": 5,
            "message": "Starting emerging topic detection...",
            "detection_date": str(detection_date),
            "run_id": run_id,
        }

        # Step 1: LLM proposes themes from article sample
        yield {
            "step": 2,
            "progress": 10,
            "message": "Analyzing articles to identify emerging themes...",
        }

        proposed_themes = await self.theme_proposer.propose_themes(
            topic_filter=topic_filter,
            days_back=days,
            max_sample=self.config.max_sample_articles
        )

        if not proposed_themes:
            yield {
                "step": 2,
                "progress": 100,
                "message": "No emerging themes identified",
                "emerging_topics": [],
                "total_emerging_topics": 0,
            }
            return

        yield {
            "step": 2,
            "progress": 25,
            "message": f"LLM proposed {len(proposed_themes)} potential themes",
            "proposed_count": len(proposed_themes),
        }

        # Step 2: Assign articles to themes via semantic search
        yield {
            "step": 3,
            "progress": 30,
            "message": "Assigning articles to themes via semantic search...",
        }

        themes_with_articles = await self.theme_proposer.assign_articles_to_themes(
            themes=proposed_themes,
            topic_filter=topic_filter,
            days_back=days,
            max_per_theme=self.config.max_articles_per_theme,
            distance_threshold=self.config.theme_distance_threshold
        )

        yield {
            "step": 3,
            "progress": 45,
            "message": "Articles assigned to themes",
        }

        # Step 3.5: AI validation sweep to filter false positives
        yield {
            "step": 3,
            "progress": 47,
            "message": "Validating article relevance with AI sweep...",
        }

        for theme in themes_with_articles:
            if theme.article_uris and len(theme.article_uris) > 0:
                # Fetch article details for validation
                articles = await self._fetch_articles_for_validation(theme.article_uris[:15])

                if articles:
                    validated_uris = await self.article_validator.validate_theme_articles(
                        theme_label=theme.theme_label,
                        theme_description=theme.theme_description,
                        key_entities=theme.key_entities or [],
                        articles=articles,
                        min_confidence=0.7
                    )

                    # Keep original order but filter to validated URIs
                    original_uris = theme.article_uris
                    theme.article_uris = [uri for uri in original_uris if uri in validated_uris]

                    # Also filter distances if we have them
                    if hasattr(theme, 'article_distances') and theme.article_distances:
                        uri_to_dist = dict(zip(original_uris, theme.article_distances))
                        theme.article_distances = [uri_to_dist.get(uri, 0) for uri in theme.article_uris]

                    logger.info(
                        f"AI validation: {len(theme.article_uris)}/{len(original_uris)} "
                        f"articles passed for '{theme.theme_label}'"
                    )

        yield {
            "step": 3,
            "progress": 49,
            "message": "Article relevance validation complete",
        }

        # Step 4: Validate and merge overlapping themes
        yield {
            "step": 4,
            "progress": 50,
            "message": "Validating theme coherence and merging duplicates...",
        }

        validated_themes = await self.theme_validator.validate(themes_with_articles)

        if not validated_themes:
            yield {
                "step": 4,
                "progress": 100,
                "message": "No themes passed validation",
                "emerging_topics": [],
                "total_emerging_topics": 0,
            }
            return

        yield {
            "step": 4,
            "progress": 55,
            "message": f"{len(validated_themes)} themes validated",
            "validated_count": len(validated_themes),
        }

        # Step 4: Deep analysis for each theme
        yield {
            "step": 5,
            "progress": 60,
            "message": "Running deep analysis on validated themes...",
        }

        # Fetch organizational profile for context-aware analysis
        org_profile = self._get_default_org_profile()
        if org_profile:
            logger.info(f"Using org profile '{org_profile.get('name')}' for deep analysis")

        emerging_topics = []
        total_themes = len(validated_themes)

        for i, theme in enumerate(validated_themes):
            progress = 60 + (i / total_themes) * 25
            yield {
                "step": 5,
                "progress": progress,
                "message": f"Analyzing: {theme.theme_label}",
            }

            # Deep analysis with organizational context
            analysis = await self.deep_analyzer.analyze(
                theme_label=theme.theme_label,
                theme_description=theme.theme_description,
                article_uris=theme.article_uris,
                max_articles=self.config.max_articles_for_analysis,
                org_profile=org_profile
            )

            # Trend scoring
            trend = self.trend_scorer.calculate(
                article_uris=theme.article_uris,
                days_back=days
            )

            # Check if this is actually an ongoing topic with historical coverage
            is_ongoing = await self._check_historical_coverage(
                theme=theme,
                days_back=days,
                history_window_days=60,  # Look back 60 days for historical articles
                min_historical_articles=3
            )

            # Create EmergingTopic
            topic = self._create_topic_from_theme(
                theme=theme,
                analysis=analysis,
                trend=trend,
                detection_date=detection_date,
                is_ongoing=is_ongoing
            )

            emerging_topics.append(topic)

        yield {
            "step": 5,
            "progress": 85,
            "message": "Deep analysis complete",
        }

        # Step 5: Calculate confidence and save
        yield {
            "step": 6,
            "progress": 90,
            "message": "Saving emerging topics...",
        }

        articles_sampled = self.config.max_sample_articles
        for topic in emerging_topics:
            topic.confidence_score = self._calculate_confidence_v2(topic)
            topic.id = self._save_emerging_topic(topic, topic_filter)

            # Save history snapshot for this topic in this run
            if topic.id and run_id:
                self._save_topic_history(topic.id, run_id, topic)

        yield {
            "step": 6,
            "progress": 95,
            "message": "Topics saved to database",
        }

        # Complete the detection run
        duration = time.time() - start_time
        if run_id:
            self._complete_detection_run(run_id, len(emerging_topics), articles_sampled, duration)

        # Check for auto-retirement of themes not detected in this run
        # Uses conservative thresholds: 7 days inactive + 7 missed runs
        detected_ids = [t.id for t in emerging_topics if t.id is not None]
        auto_retired = self._check_auto_retirement(detected_ids, topic_filter)

        # Final result
        retired_msg = f", {auto_retired} auto-retired" if auto_retired > 0 else ""
        yield {
            "step": 7,
            "progress": 100,
            "message": f"Detection complete: {len(emerging_topics)} emerging topics found{retired_msg}",
            "total_emerging_topics": len(emerging_topics),
            "emerging_topics": [t.to_dict() for t in emerging_topics],
            "auto_retired": auto_retired,
            "run_id": run_id,
            "duration_seconds": round(duration, 2),
        }

    async def _check_historical_coverage(
        self,
        theme: ProposedTheme,
        days_back: int,
        history_window_days: int = 60,
        min_historical_articles: int = 3
    ) -> bool:
        """
        Check if this theme has historical coverage from before the analysis window.

        If articles exist about this topic from before the analysis window,
        the topic is not truly "emerging" but rather an ongoing topic.

        Args:
            theme: The proposed theme to check
            days_back: The analysis window (e.g., 3 days)
            history_window_days: How far back to look for historical articles
            min_historical_articles: Minimum articles to consider it historical

        Returns:
            True if historical coverage exists (topic is ongoing, not new)
        """
        try:
            from app.vector_store import search_articles

            # Search for articles older than the analysis window
            # Using the theme's search query or label as the search term
            search_text = theme.search_query or theme.theme_label

            # Search for matching articles with date filter for historical period
            # Articles from (history_window_days ago) to (days_back ago)
            conn = self._get_connection()
            try:
                # Get article URIs from the historical window
                stmt = text("""
                    SELECT uri FROM articles
                    WHERE publication_date >= CURRENT_DATE - :history_days
                    AND publication_date < CURRENT_DATE - :analysis_days
                """)
                result = conn.execute(stmt, {
                    "history_days": history_window_days,
                    "analysis_days": days_back
                })
                historical_uris = {row[0] for row in result.fetchall()}
            finally:
                conn.close()

            if not historical_uris:
                # No articles in historical window at all
                return False

            # Do a semantic search with the theme
            search_results = search_articles(
                query=search_text,
                top_k=50,
            )

            # Count how many results are from the historical window
            historical_matches = 0
            for result in search_results:
                uri = result.get('id') if isinstance(result, dict) else None
                if uri and uri in historical_uris:
                    historical_matches += 1

            if historical_matches >= min_historical_articles:
                logger.info(
                    f"Theme '{theme.theme_label}' has {historical_matches} historical articles "
                    f"(before {days_back} days ago) - marking as ongoing topic"
                )
                return True

            return False

        except Exception as e:
            logger.warning(f"Error checking historical coverage for '{theme.theme_label}': {e}")
            # On error, assume it's new to avoid false negatives
            return False

    def _create_topic_from_theme(
        self,
        theme: ProposedTheme,
        analysis: DeepAnalysis,
        trend: TrendScore,
        detection_date: date,
        is_ongoing: bool = False
    ) -> EmergingTopic:
        """Create EmergingTopic from theme, analysis, and trend data."""
        topic_detection_type = "ongoing_topic" if is_ongoing else "llm_proposed"
        return EmergingTopic(
            topic_label=theme.theme_label,
            topic_description=theme.theme_description,
            detection_date=detection_date,
            detection_type=topic_detection_type,
            cluster_id=f"theme_{detection_date.isoformat()}_{theme.theme_label[:20].replace(' ', '_')}",
            article_count=len(theme.article_uris),
            article_uris=theme.article_uris,
            # From theme proposal
            key_entities=theme.key_entities,
            why_emerging=theme.why_emerging,
            search_query=theme.search_query,
            # From deep analysis
            actors=analysis.actors.to_dict() if analysis.actors else {},
            events=analysis.events.to_dict() if analysis.events else {},
            implications=analysis.implications.to_dict() if analysis.implications else {},
            organization_implications=analysis.organization_implications.to_dict() if analysis.organization_implications else {},
            signals=analysis.signals.to_dict() if analysis.signals else {},
            synthesis={**(analysis.synthesis.to_dict() if analysis.synthesis else {}), "model_used": analysis.model_used},
            # From trend scoring
            volume_score=trend.volume_score,
            velocity_score=trend.velocity_score,
            diversity_score=trend.diversity_score,
            novelty_score=trend.novelty_score,
            composite_score=trend.composite_score,
            velocity=trend.velocity_label,
            source_count=trend.source_count,
            # Legacy compatibility
            key_themes=theme.key_entities[:4],
            representative_keywords=[],
            emergence_rationale=theme.why_emerging,
            status="active",
        )

    def _calculate_confidence_v2(self, topic: EmergingTopic) -> float:
        """Calculate confidence score for v2 topics."""
        confidence = 0.5  # Base

        # Higher composite trend score = higher confidence
        if topic.composite_score >= 70:
            confidence += 0.25
        elif topic.composite_score >= 50:
            confidence += 0.15
        elif topic.composite_score >= 30:
            confidence += 0.05

        # More articles = higher confidence
        if topic.article_count >= 10:
            confidence += 0.15
        elif topic.article_count >= 5:
            confidence += 0.10

        # Has deep analysis = higher confidence
        if topic.actors and any(topic.actors.values()):
            confidence += 0.05
        if topic.events and topic.events.get("trigger_event"):
            confidence += 0.05

        return min(1.0, confidence)

    def _save_emerging_topic(
        self,
        topic: EmergingTopic,
        topic_filter: Optional[str]
    ) -> int:
        """Save emerging topic to the database, updating if duplicate exists."""
        conn = None
        try:
            conn = self._get_connection()

            # Check for existing topic with same or similar label (within last 7 days)
            # First try exact match
            check_stmt = text("""
                SELECT id, topic_label FROM emerging_topics
                WHERE topic_label = :label
                AND detection_date >= CURRENT_DATE - INTERVAL '7 days'
                ORDER BY detection_date DESC
                LIMIT 1
            """)
            existing = conn.execute(check_stmt, {"label": topic.topic_label}).fetchone()

            # If no exact match, check for similar labels (fuzzy match)
            if not existing:
                # Extract significant words from the new topic label (3+ chars, lowercase)
                label_words = set(w.lower() for w in topic.topic_label.split() if len(w) >= 3)
                # Remove common words
                label_words -= {'the', 'and', 'for', 'with', 'from', 'that', 'this', 'are', 'was', 'were'}

                if label_words:
                    # Find topics with overlapping significant words
                    similar_stmt = text("""
                        SELECT id, topic_label FROM emerging_topics
                        WHERE detection_date >= CURRENT_DATE - INTERVAL '7 days'
                        ORDER BY detection_date DESC
                    """)
                    candidates = conn.execute(similar_stmt).fetchall()

                    for candidate in candidates:
                        candidate_words = set(w.lower() for w in candidate[1].split() if len(w) >= 3)
                        candidate_words -= {'the', 'and', 'for', 'with', 'from', 'that', 'this', 'are', 'was', 'were'}

                        # Check overlap - if 50%+ of significant words match, consider it a duplicate
                        if label_words and candidate_words:
                            overlap = len(label_words & candidate_words)
                            min_size = min(len(label_words), len(candidate_words))
                            if min_size > 0 and overlap / min_size >= 0.5:
                                logger.info(f"Fuzzy match: '{topic.topic_label}' similar to '{candidate[1]}'")
                                existing = candidate
                                break

            # Serialize complex fields
            actors_json = json_module.dumps(topic.actors) if topic.actors else "{}"
            events_json = json_module.dumps(topic.events) if topic.events else "{}"
            implications_json = json_module.dumps(topic.implications) if topic.implications else "{}"
            org_implications_json = json_module.dumps(topic.organization_implications) if topic.organization_implications else "{}"
            signals_json = json_module.dumps(topic.signals) if topic.signals else "{}"
            synthesis_json = json_module.dumps(topic.synthesis) if topic.synthesis else "{}"

            if existing:
                # Update existing topic instead of creating duplicate
                existing_id = existing[0]
                logger.info(f"Updating existing emerging topic '{topic.topic_label}' (id={existing_id})")

                update_stmt = text("""
                    UPDATE emerging_topics SET
                        topic_description = :description,
                        detection_date = :date,
                        article_count = :count,
                        growth_rate = :growth_rate,
                        velocity = :velocity,
                        confidence_score = :confidence,
                        key_themes = CAST(:themes AS jsonb),
                        representative_keywords = CAST(:keywords AS jsonb),
                        emergence_rationale = :rationale,
                        article_uris = :uris,
                        sample_article_uris = :sample_uris,
                        actors = CAST(:actors AS jsonb),
                        events = CAST(:events AS jsonb),
                        implications = CAST(:implications AS jsonb),
                        organization_implications = CAST(:org_implications AS jsonb),
                        signals = CAST(:signals AS jsonb),
                        synthesis = CAST(:synthesis AS jsonb),
                        volume_score = :volume_score,
                        velocity_score = :velocity_score,
                        diversity_score = :diversity_score,
                        novelty_score = :novelty_score,
                        composite_score = :composite_score,
                        last_detection_date = :date,
                        detection_count = COALESCE(detection_count, 0) + 1,
                        consecutive_detections = COALESCE(consecutive_detections, 0) + 1
                    WHERE id = :id
                """)

                conn.execute(update_stmt, {
                    "id": existing_id,
                    "description": topic.topic_description,
                    "date": topic.detection_date,
                    "count": topic.article_count,
                    "growth_rate": topic.growth_rate,
                    "velocity": topic.velocity,
                    "confidence": topic.confidence_score,
                    "themes": json_module.dumps(topic.key_themes),
                    "keywords": json_module.dumps(topic.representative_keywords),
                    "rationale": topic.emergence_rationale,
                    "uris": topic.article_uris,
                    "sample_uris": topic.article_uris[:5],
                    "actors": actors_json,
                    "events": events_json,
                    "implications": implications_json,
                    "org_implications": org_implications_json,
                    "signals": signals_json,
                    "synthesis": synthesis_json,
                    "volume_score": topic.volume_score,
                    "velocity_score": topic.velocity_score,
                    "diversity_score": topic.diversity_score,
                    "novelty_score": topic.novelty_score,
                    "composite_score": topic.composite_score,
                })
                conn.commit()
                return existing_id

            # Insert new topic
            stmt = text("""
                INSERT INTO emerging_topics (
                    topic_label, topic_description, detection_date, detection_type,
                    cluster_id, article_count, growth_rate, velocity,
                    confidence_score, key_themes, representative_keywords,
                    emergence_rationale, article_uris, sample_article_uris,
                    topic_filter, status,
                    actors, events, implications, organization_implications, signals, synthesis,
                    volume_score, velocity_score, diversity_score, novelty_score, composite_score,
                    first_detection_date, last_detection_date, detection_count, consecutive_detections
                ) VALUES (
                    :label, :description, :date, :type,
                    :cluster_id, :count, :growth_rate, :velocity,
                    :confidence, CAST(:themes AS jsonb), CAST(:keywords AS jsonb),
                    :rationale, :uris, :sample_uris,
                    :filter, :status,
                    CAST(:actors AS jsonb), CAST(:events AS jsonb),
                    CAST(:implications AS jsonb), CAST(:org_implications AS jsonb),
                    CAST(:signals AS jsonb), CAST(:synthesis AS jsonb),
                    :volume_score, :velocity_score, :diversity_score, :novelty_score, :composite_score,
                    :date, :date, 1, 1
                )
                RETURNING id
            """)

            result = conn.execute(stmt, {
                "label": topic.topic_label,
                "description": topic.topic_description,
                "date": topic.detection_date,
                "type": topic.detection_type,
                "cluster_id": topic.cluster_id,
                "count": topic.article_count,
                "growth_rate": topic.growth_rate,
                "velocity": topic.velocity,
                "confidence": topic.confidence_score,
                "themes": json_module.dumps(topic.key_themes),
                "keywords": json_module.dumps(topic.representative_keywords),
                "rationale": topic.emergence_rationale,
                "uris": topic.article_uris,
                "sample_uris": topic.article_uris[:5],
                "filter": topic_filter,
                "status": topic.status,
                "actors": actors_json,
                "events": events_json,
                "implications": implications_json,
                "org_implications": org_implications_json,
                "signals": signals_json,
                "synthesis": synthesis_json,
                "volume_score": topic.volume_score,
                "velocity_score": topic.velocity_score,
                "diversity_score": topic.diversity_score,
                "novelty_score": topic.novelty_score,
                "composite_score": topic.composite_score,
            })

            conn.commit()
            row = result.fetchone()
            return row[0] if row else None

        except Exception as exc:
            logger.error(f"Error saving emerging topic: {exc}")
            if conn:
                conn.rollback()
            return None
        finally:
            if conn:
                conn.close()

    def _create_detection_run(
        self,
        topic_filter: Optional[str],
        config: Dict[str, Any],
        model: str
    ) -> Optional[int]:
        """Create a detection run record and return its ID."""
        conn = None
        try:
            conn = self._get_connection()
            stmt = text("""
                INSERT INTO detection_runs (topic_filter, config, model_used, status)
                VALUES (:topic_filter, CAST(:config AS jsonb), :model, 'running')
                RETURNING id
            """)
            result = conn.execute(stmt, {
                "topic_filter": topic_filter,
                "config": json_module.dumps(config),
                "model": model,
            })
            conn.commit()
            row = result.fetchone()
            return row[0] if row else None
        except Exception as exc:
            logger.error(f"Error creating detection run: {exc}")
            return None
        finally:
            if conn:
                conn.close()

    def _complete_detection_run(
        self,
        run_id: int,
        topics_detected: int,
        articles_sampled: int,
        duration_seconds: float
    ) -> None:
        """Mark a detection run as complete with stats."""
        conn = None
        try:
            conn = self._get_connection()
            stmt = text("""
                UPDATE detection_runs SET
                    topics_detected = :topics,
                    articles_sampled = :articles,
                    duration_seconds = :duration,
                    status = 'completed'
                WHERE id = :run_id
            """)
            conn.execute(stmt, {
                "run_id": run_id,
                "topics": topics_detected,
                "articles": articles_sampled,
                "duration": duration_seconds,
            })
            conn.commit()
        except Exception as exc:
            logger.error(f"Error completing detection run: {exc}")
        finally:
            if conn:
                conn.close()

    def _save_topic_history(
        self,
        topic_id: int,
        run_id: int,
        topic: EmergingTopic
    ) -> None:
        """Save a history snapshot for this topic in this run."""
        conn = None
        try:
            conn = self._get_connection()
            stmt = text("""
                INSERT INTO topic_history (
                    topic_id, detection_run_id,
                    article_count, growth_rate, velocity, confidence_score,
                    volume_score, velocity_score, diversity_score, novelty_score, composite_score,
                    source_count, actors, events, synthesis
                ) VALUES (
                    :topic_id, :run_id,
                    :article_count, :growth_rate, :velocity, :confidence_score,
                    :volume_score, :velocity_score, :diversity_score, :novelty_score, :composite_score,
                    :source_count, CAST(:actors AS jsonb), CAST(:events AS jsonb), CAST(:synthesis AS jsonb)
                )
                ON CONFLICT (topic_id, detection_run_id) DO UPDATE SET
                    article_count = EXCLUDED.article_count,
                    growth_rate = EXCLUDED.growth_rate,
                    velocity = EXCLUDED.velocity,
                    confidence_score = EXCLUDED.confidence_score,
                    volume_score = EXCLUDED.volume_score,
                    velocity_score = EXCLUDED.velocity_score,
                    diversity_score = EXCLUDED.diversity_score,
                    novelty_score = EXCLUDED.novelty_score,
                    composite_score = EXCLUDED.composite_score,
                    source_count = EXCLUDED.source_count,
                    actors = EXCLUDED.actors,
                    events = EXCLUDED.events,
                    synthesis = EXCLUDED.synthesis
            """)
            conn.execute(stmt, {
                "topic_id": topic_id,
                "run_id": run_id,
                "article_count": topic.article_count,
                "growth_rate": topic.growth_rate,
                "velocity": topic.velocity,
                "confidence_score": topic.confidence_score,
                "volume_score": topic.volume_score,
                "velocity_score": topic.velocity_score,
                "diversity_score": topic.diversity_score,
                "novelty_score": topic.novelty_score,
                "composite_score": topic.composite_score,
                "source_count": topic.source_count,
                "actors": json_module.dumps(topic.actors) if topic.actors else "{}",
                "events": json_module.dumps(topic.events) if topic.events else "{}",
                "synthesis": json_module.dumps(topic.synthesis) if topic.synthesis else "{}",
            })
            conn.commit()
        except Exception as exc:
            logger.error(f"Error saving topic history: {exc}")
        finally:
            if conn:
                conn.close()

    def _check_auto_retirement(
        self,
        detected_topic_ids: List[int],
        topic_filter: Optional[str] = None,
        consecutive_miss_threshold: int = 7,
        min_inactive_days: int = 7
    ) -> int:
        """
        Auto-retire themes that haven't been detected for N consecutive runs.

        Uses conservative thresholds to avoid over-retiring themes.
        Human curation is the primary method - this is just cleanup.

        Args:
            detected_topic_ids: IDs of topics detected in this run
            topic_filter: Optional topic filter (e.g., 'climate')
            consecutive_miss_threshold: Number of consecutive misses before auto-retirement (default: 7)
            min_inactive_days: Minimum days since last detection before considering retirement (default: 7)

        Returns:
            Number of topics auto-retired
        """
        conn = None
        retired_count = 0
        try:
            conn = self._get_connection()

            # Build filter clause
            filter_clause = "WHERE (status = 'active' OR status IS NULL)"
            params = {"threshold": consecutive_miss_threshold, "min_days": min_inactive_days}

            if topic_filter:
                filter_clause += " AND topic_filter = :topic_filter"
                params["topic_filter"] = topic_filter

            # Exclude topics detected in this run
            if detected_topic_ids:
                filter_clause += " AND id NOT IN :detected_ids"
                # SQLAlchemy needs tuple for IN clause
                params["detected_ids"] = tuple(detected_topic_ids) if detected_topic_ids else (0,)

            # Find active themes NOT detected in this run that have been inactive for min_inactive_days
            check_stmt = text(f"""
                SELECT id, topic_label, last_detection_date, consecutive_detections
                FROM emerging_topics
                {filter_clause}
                AND last_detection_date < CURRENT_DATE - INTERVAL ':min_days days'
            """.replace(":min_days", str(min_inactive_days)))

            result = conn.execute(check_stmt, params)
            candidates = result.fetchall()

            for row in candidates:
                topic_id = row[0]
                topic_label = row[1]
                last_detection = row[2]

                # Count how many runs have occurred since this topic was last detected
                runs_since_stmt = text("""
                    SELECT COUNT(*) FROM detection_runs
                    WHERE run_date > :last_detection
                    AND status = 'completed'
                    AND (:topic_filter IS NULL OR topic_filter = :topic_filter)
                """)
                runs_result = conn.execute(runs_since_stmt, {
                    "last_detection": last_detection,
                    "topic_filter": topic_filter
                })
                runs_since = runs_result.scalar() or 0

                if runs_since >= consecutive_miss_threshold:
                    # Auto-retire this topic
                    retire_stmt = text("""
                        UPDATE emerging_topics
                        SET status = 'retired',
                            consecutive_detections = 0
                        WHERE id = :id
                    """)
                    conn.execute(retire_stmt, {"id": topic_id})
                    retired_count += 1
                    logger.info(
                        f"Auto-retired theme '{topic_label}' (id={topic_id}) - "
                        f"not detected in {runs_since} consecutive runs"
                    )

            if retired_count > 0:
                conn.commit()
                logger.info(f"Auto-retired {retired_count} declining themes")

        except Exception as exc:
            logger.error(f"Error in auto-retirement check: {exc}")
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()

        return retired_count

    async def run_detection(
        self,
        topic_filter: Optional[str] = None,
        days_back: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Run full detection (non-streaming version).
        """
        result = {
            "detection_date": str(date.today()),
            "topic_filter": topic_filter,
            "emerging_topics": [],
            "total_emerging_topics": 0,
        }

        async for update in self.run_detection_streaming(topic_filter, days_back):
            if "emerging_topics" in update:
                result["emerging_topics"] = update["emerging_topics"]
                result["total_emerging_topics"] = update.get("total_emerging_topics", 0)

        return result

    def get_emerging_topics(
        self,
        topic_filter: Optional[str] = None,
        days_back: int = 7,
        detection_type: Optional[str] = None,
        min_confidence: float = 0.0,
        limit: int = 50,
        include_retired: bool = False
    ) -> List[EmergingTopic]:
        """Get detected emerging topics from the database."""
        conn = None
        try:
            conn = self._get_connection()

            filter_clause = "WHERE detection_date >= CURRENT_DATE - :days_back"
            params = {"days_back": days_back, "limit": limit, "min_confidence": min_confidence}

            # Filter out retired themes by default
            if not include_retired:
                filter_clause += " AND (status IS NULL OR status != 'retired')"

            if topic_filter:
                filter_clause += " AND topic_filter = :topic"
                params["topic"] = topic_filter

            if detection_type:
                filter_clause += " AND detection_type = :type"
                params["type"] = detection_type

            filter_clause += " AND confidence_score >= :min_confidence"

            stmt = text(f"""
                SELECT
                    id, topic_label, topic_description, detection_date,
                    detection_type, cluster_id, article_count, growth_rate,
                    velocity, confidence_score, key_themes, representative_keywords,
                    emergence_rationale, article_uris, status,
                    actors, events, implications, organization_implications, signals, synthesis,
                    volume_score, velocity_score, diversity_score, novelty_score, composite_score,
                    first_detection_date, last_detection_date, detection_count, consecutive_detections,
                    missed_runs, future_horizons
                FROM emerging_topics
                {filter_clause}
                ORDER BY detection_date DESC, confidence_score DESC
                LIMIT :limit
            """)

            result = conn.execute(stmt, params)

            topics = []
            for row in result.mappings():
                topic = EmergingTopic(
                    id=row["id"],
                    topic_label=row["topic_label"],
                    topic_description=row["topic_description"],
                    detection_date=row["detection_date"],
                    detection_type=row["detection_type"],
                    cluster_id=row["cluster_id"],
                    article_count=row["article_count"],
                    article_uris=row["article_uris"] or [],
                    growth_rate=row["growth_rate"] or 0.0,
                    velocity=row["velocity"] or "stable",
                    confidence_score=row["confidence_score"] or 0.0,
                    key_themes=row["key_themes"] or [],
                    representative_keywords=row["representative_keywords"] or [],
                    emergence_rationale=row["emergence_rationale"] or "",
                    status=row["status"] or "active",
                    # V2 fields
                    actors=row.get("actors") or {},
                    events=row.get("events") or {},
                    implications=row.get("implications") or {},
                    organization_implications=row.get("organization_implications") or {},
                    signals=row.get("signals") or {},
                    synthesis=row.get("synthesis") or {},
                    volume_score=row.get("volume_score") or 0.0,
                    velocity_score=row.get("velocity_score") or 0.0,
                    diversity_score=row.get("diversity_score") or 0.0,
                    novelty_score=row.get("novelty_score") or 0.0,
                    composite_score=row.get("composite_score") or 0.0,
                    # V3 temporal fields
                    first_detection_date=row.get("first_detection_date"),
                    last_detection_date=row.get("last_detection_date"),
                    detection_count=row.get("detection_count") or 1,
                    consecutive_detections=row.get("consecutive_detections") or 1,
                    missed_runs=row.get("missed_runs") or 0,
                    # Future horizons
                    future_horizons=row.get("future_horizons"),
                )
                topics.append(topic)

            return topics

        except Exception as exc:
            logger.error(f"Error getting emerging topics: {exc}")
            return []
        finally:
            if conn:
                conn.close()

    def get_high_novelty_articles(
        self,
        threshold: Optional[float] = None,
        days_back: int = 7,
        topic_filter: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get articles with high novelty scores."""
        return self.novelty_scorer.get_high_novelty_articles(
            threshold=threshold or self.config.novelty_threshold,
            days_back=days_back,
            topic_filter=topic_filter,
            limit=limit
        )

    def get_retired_topics(
        self,
        topic_filter: Optional[str] = None,
        limit: int = 50
    ) -> List[EmergingTopic]:
        """Get retired emerging topics."""
        conn = None
        try:
            conn = self._get_connection()

            filter_clause = "WHERE status = 'retired'"
            params = {"limit": limit}

            if topic_filter:
                filter_clause += " AND topic_filter = :topic"
                params["topic"] = topic_filter

            stmt = text(f"""
                SELECT
                    id, topic_label, topic_description, detection_date,
                    detection_type, cluster_id, article_count, growth_rate,
                    velocity, confidence_score, key_themes, representative_keywords,
                    emergence_rationale, article_uris, status,
                    actors, events, implications, organization_implications, signals, synthesis,
                    volume_score, velocity_score, diversity_score, novelty_score, composite_score,
                    first_detection_date, last_detection_date, detection_count, consecutive_detections,
                    missed_runs, future_horizons
                FROM emerging_topics
                {filter_clause}
                ORDER BY detection_date DESC, confidence_score DESC
                LIMIT :limit
            """)

            result = conn.execute(stmt, params)

            topics = []
            for row in result.mappings():
                topic = EmergingTopic(
                    id=row["id"],
                    topic_label=row["topic_label"],
                    topic_description=row["topic_description"],
                    detection_date=row["detection_date"],
                    detection_type=row["detection_type"],
                    cluster_id=row["cluster_id"],
                    article_count=row["article_count"],
                    article_uris=row["article_uris"] or [],
                    growth_rate=row["growth_rate"] or 0.0,
                    velocity=row["velocity"] or "stable",
                    confidence_score=row["confidence_score"] or 0.0,
                    key_themes=row["key_themes"] or [],
                    representative_keywords=row["representative_keywords"] or [],
                    emergence_rationale=row["emergence_rationale"] or "",
                    status=row["status"] or "retired",
                    actors=row.get("actors") or {},
                    events=row.get("events") or {},
                    implications=row.get("implications") or {},
                    organization_implications=row.get("organization_implications") or {},
                    signals=row.get("signals") or {},
                    synthesis=row.get("synthesis") or {},
                    volume_score=row.get("volume_score") or 0.0,
                    velocity_score=row.get("velocity_score") or 0.0,
                    diversity_score=row.get("diversity_score") or 0.0,
                    novelty_score=row.get("novelty_score") or 0.0,
                    composite_score=row.get("composite_score") or 0.0,
                    first_detection_date=row.get("first_detection_date"),
                    last_detection_date=row.get("last_detection_date"),
                    detection_count=row.get("detection_count") or 1,
                    consecutive_detections=row.get("consecutive_detections") or 1,
                    missed_runs=row.get("missed_runs") or 0,
                    future_horizons=row.get("future_horizons"),
                )
                topics.append(topic)

            return topics

        except Exception as exc:
            logger.error(f"Error getting retired topics: {exc}")
            return []
        finally:
            if conn:
                conn.close()

    def retire_topic(self, topic_id: int) -> bool:
        """Manually retire an emerging topic."""
        conn = None
        try:
            conn = self._get_connection()
            stmt = text("""
                UPDATE emerging_topics
                SET status = 'retired', consecutive_detections = 0
                WHERE id = :topic_id
            """)
            result = conn.execute(stmt, {"topic_id": topic_id})
            conn.commit()
            return result.rowcount > 0
        except Exception as exc:
            logger.error(f"Error retiring topic {topic_id}: {exc}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                conn.close()

    def restore_topic(self, topic_id: int) -> bool:
        """Restore a retired topic to active status."""
        conn = None
        try:
            conn = self._get_connection()
            stmt = text("""
                UPDATE emerging_topics
                SET status = 'active'
                WHERE id = :topic_id
            """)
            result = conn.execute(stmt, {"topic_id": topic_id})
            conn.commit()
            return result.rowcount > 0
        except Exception as exc:
            logger.error(f"Error restoring topic {topic_id}: {exc}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                conn.close()


# Singleton instance
_emerging_topics_service: Optional[EmergingTopicsService] = None


def get_emerging_topics_service() -> EmergingTopicsService:
    """Get or create the emerging topics service singleton."""
    global _emerging_topics_service

    if _emerging_topics_service is None:
        from app.ai_models import get_ai_model

        # Try to get embedding model getter
        embedding_getter = None
        try:
            from app.ai_models import get_embedding_model
            embedding_getter = get_embedding_model
        except ImportError:
            pass

        _emerging_topics_service = EmergingTopicsService(
            ai_model_getter=get_ai_model,
            embedding_model_getter=embedding_getter
        )

    return _emerging_topics_service
