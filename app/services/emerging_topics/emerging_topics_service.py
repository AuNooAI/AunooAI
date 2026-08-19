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

import asyncio
import logging
import json as json_module
import os
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
from .date_utils import publication_ts_sql, utcnow
from .run_lock import (
    DetectionAlreadyRunning,
    DetectionRunLock,
    normalize_topic_filter,
)
from . import historical_backend
from . import historical_cutoff
from . import sentinels

# Keep old imports for backwards compatibility
from .cluster_detector import ClusterDetector, ClusterConfig, ClusterResult, ArticleCluster
from .temporal_tracker import TemporalTracker, TemporalConfig, ClusterChange
from .topic_summarizer import TopicSummarizer, TopicSummary

logger = logging.getLogger(__name__)


class DetectionFailed(RuntimeError):
    """A detection run failed. Carries a machine-readable code for the API."""

    def __init__(self, message: str, code: str = "detection_failed"):
        super().__init__(message)
        self.code = code


def _sanitize_error(exc: BaseException) -> str:
    """A short, safe error string for the run record and the error event.

    Keeps the exception type and message but caps the length, so a database
    error carrying a full statement (and its parameters) does not end up in an
    API response or a run row.
    """
    message = str(exc).strip().splitlines()[0] if str(exc).strip() else exc.__class__.__name__
    if len(message) > 300:
        message = message[:297] + "..."
    return f"{exc.__class__.__name__}: {message}"


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
    summarization_model: str = "gpt-5.4"
    model: str = "gpt-5.4"  # Primary model selection (overrides summarization_model if set)
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
    # The scope this topic belongs to. Part of its identity: the same label
    # under two filters is two topics.
    topic_filter: Optional[str] = None
    # Whether older coverage was found: 'ongoing', 'not_found' or 'unknown'.
    # 'unknown' is the normal answer until a validated E5 index exists.
    historical_coverage_status: str = "unknown"
    # What the shadow classifier would have said, when one ran.
    historical_shadow: Optional[Dict[str, Any]] = None

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
            "topic_filter": self.topic_filter,
            "historical_coverage_status": self.historical_coverage_status,
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
        # topic_summarizer is a cheap cluster-labeling step — kimi matched Sonnet
        # at ~7x less cost in the 2026-07-21 validation, so it runs on kimi while
        # theme_proposer (kept on Sonnet) stays on the primary model.
        summarizer_model = os.getenv("TOPIC_SUMMARIZER_MODEL", "bedrock-kimi-k2-5")

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
            default_model=summarizer_model
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

    def _fetch_articles_for_validation(
        self,
        article_uris: List[str]
    ) -> List[Dict[str, Any]]:
        """Fetch article details for validation, in the order asked for.

        Blocking; async callers route it through a worker thread. Raises on a
        database error rather than returning an empty list, which would be
        indistinguishable from "these articles do not exist".
        """
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
            by_uri = {row["uri"]: dict(row) for row in result.mappings()}
            # Preserve the caller's ranking; the validator's cost cap applies to
            # the first N articles by rank, not by whatever order the DB returns.
            return [by_uri[uri] for uri in article_uris if uri in by_uri]

        except Exception as e:
            logger.error(f"Error fetching articles for validation: {e}")
            raise RuntimeError(
                f"Could not read articles for relevance validation: {e}"
            ) from e
        finally:
            if conn:
                conn.close()

    async def run_detection_streaming(
        self,
        topic_filter: Optional[str] = None,
        days_back: Optional[int] = None,
        run_lock: Optional[DetectionRunLock] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Run v2 LLM-driven detection, yielding progress events.

        Every event carries an ``event`` key of ``progress``, ``complete``, or
        ``error``; the transport turns that into the SSE event name.

        Every run that creates a ``detection_runs`` row leaves it in exactly one
        terminal state. A run that samples articles but finds nothing is
        ``completed`` with zero topics. An encoder outage, a database error, an
        LLM failure, or a persistence failure is ``failed`` — none of them may
        look like a successful empty run.

        Args:
            run_lock: an already-held scope lock (the API takes it before the
                stream starts so it can answer 409 with a status code). When
                omitted the service takes and releases its own.
        """
        days = days_back or self.config.days_back
        topic_filter = normalize_topic_filter(topic_filter)
        detection_date = date.today()
        start_time = time.time()

        owns_lock = run_lock is None
        lock = run_lock or DetectionRunLock(topic_filter)
        if owns_lock:
            # Raises DetectionAlreadyRunning; no run row is created.
            await asyncio.to_thread(lock.acquire)

        run_id: Optional[int] = None
        terminal = False
        articles_sampled = 0

        try:
            run_config = {
                "days_back": days,
                "max_sample_articles": self.config.max_sample_articles,
                "distance_threshold": self.config.theme_distance_threshold,
                "min_articles_for_theme": self.config.min_articles_for_theme,
                "max_articles_per_theme": self.config.max_articles_per_theme,
            }
            model_name = getattr(self.theme_proposer, 'default_model', 'gpt-5.4') if self.theme_proposer else 'gpt-5.4'
            run_id = await asyncio.to_thread(
                self._create_detection_run, topic_filter, run_config, model_name
            )
            if run_id is None:
                raise DetectionFailed(
                    "Could not record the detection run — refusing to run "
                    "detection that cannot be accounted for.",
                    code="run_record_failed",
                )

            yield {
                "event": "progress",
                "step": 1,
                "progress": 5,
                "message": "Starting emerging topic detection...",
                "detection_date": str(detection_date),
                "run_id": run_id,
                "topic_filter": topic_filter,
            }

            # Step 1: LLM proposes themes from an article sample
            yield {
                "event": "progress",
                "step": 2,
                "progress": 10,
                "message": "Analyzing articles to identify emerging themes...",
                "run_id": run_id,
            }

            proposal = await self.theme_proposer.propose_themes(
                topic_filter=topic_filter,
                days_back=days,
                max_sample=self.config.max_sample_articles
            )
            proposed_themes = proposal.themes
            articles_sampled = proposal.articles_sampled

            if not proposed_themes:
                await self._finish_run(
                    run_id=run_id,
                    topics=[],
                    topic_filter=topic_filter,
                    articles_sampled=articles_sampled,
                    duration=time.time() - start_time,
                )
                terminal = True
                auto_retired = await asyncio.to_thread(
                    self._check_auto_retirement, [], topic_filter
                )
                yield self._completion_event(
                    run_id=run_id,
                    topics=[],
                    topic_filter=topic_filter,
                    articles_sampled=articles_sampled,
                    auto_retired=auto_retired,
                    duration=time.time() - start_time,
                    message="No emerging themes identified",
                )
                return

            yield {
                "event": "progress",
                "step": 2,
                "progress": 25,
                "message": f"LLM proposed {len(proposed_themes)} potential themes",
                "proposed_count": len(proposed_themes),
                "articles_sampled": articles_sampled,
                "run_id": run_id,
            }

            # Step 2: Assign articles to themes via semantic search
            yield {
                "event": "progress",
                "step": 3,
                "progress": 30,
                "message": "Assigning articles to themes via semantic search...",
                "run_id": run_id,
            }

            themes_with_articles = await self.theme_proposer.assign_articles_to_themes(
                themes=proposed_themes,
                topic_filter=topic_filter,
                days_back=days,
                max_per_theme=self.config.max_articles_per_theme,
                distance_threshold=self.config.theme_distance_threshold
            )

            yield {
                "event": "progress",
                "step": 3,
                "progress": 45,
                "message": "Articles assigned to themes",
                "run_id": run_id,
            }

            # Step 3.5: AI relevance sweep over the assigned articles
            yield {
                "event": "progress",
                "step": 3,
                "progress": 47,
                "message": "Validating article relevance with AI sweep...",
                "run_id": run_id,
            }

            for theme in themes_with_articles:
                await self._validate_theme_articles(theme)

            yield {
                "event": "progress",
                "step": 3,
                "progress": 49,
                "message": "Article relevance validation complete",
                "run_id": run_id,
            }

            # Step 4: Validate and merge overlapping themes
            yield {
                "event": "progress",
                "step": 4,
                "progress": 50,
                "message": "Validating theme coherence and merging duplicates...",
                "run_id": run_id,
            }

            validated_themes = await self.theme_validator.validate(themes_with_articles)

            if not validated_themes:
                await self._finish_run(
                    run_id=run_id,
                    topics=[],
                    topic_filter=topic_filter,
                    articles_sampled=articles_sampled,
                    duration=time.time() - start_time,
                )
                terminal = True
                auto_retired = await asyncio.to_thread(
                    self._check_auto_retirement, [], topic_filter
                )
                yield self._completion_event(
                    run_id=run_id,
                    topics=[],
                    topic_filter=topic_filter,
                    articles_sampled=articles_sampled,
                    auto_retired=auto_retired,
                    duration=time.time() - start_time,
                    message="No themes passed validation",
                )
                return

            yield {
                "event": "progress",
                "step": 4,
                "progress": 55,
                "message": f"{len(validated_themes)} themes validated",
                "validated_count": len(validated_themes),
                "run_id": run_id,
            }

            # Step 5: Deep analysis per theme
            yield {
                "event": "progress",
                "step": 5,
                "progress": 60,
                "message": "Running deep analysis on validated themes...",
                "run_id": run_id,
            }

            org_profile = await asyncio.to_thread(self._get_default_org_profile)
            if org_profile:
                logger.info(f"Using org profile '{org_profile.get('name')}' for deep analysis")

            emerging_topics = []
            total_themes = len(validated_themes)

            for i, theme in enumerate(validated_themes):
                progress = 60 + (i / total_themes) * 25
                yield {
                    "event": "progress",
                    "step": 5,
                    "progress": progress,
                    "message": f"Analyzing: {theme.theme_label}",
                    "run_id": run_id,
                }

                analysis = await self.deep_analyzer.analyze(
                    theme_label=theme.theme_label,
                    theme_description=theme.theme_description,
                    article_uris=theme.article_uris,
                    max_articles=self.config.max_articles_for_analysis,
                    org_profile=org_profile
                )

                trend = await asyncio.to_thread(
                    self.trend_scorer.calculate, theme.article_uris, days
                )

                # Has this been covered before? Usually "unknown" — see
                # historical_backend.py.
                historical_status, historical_shadow = await self._check_historical_coverage(
                    theme=theme,
                    days_back=days,
                    topic_filter=topic_filter,
                    history_window_days=60,
                    min_historical_articles=3
                )

                emerging_topics.append(self._create_topic_from_theme(
                    theme=theme,
                    analysis=analysis,
                    trend=trend,
                    detection_date=detection_date,
                    topic_filter=topic_filter,
                    historical_status=historical_status,
                    historical_shadow=historical_shadow,
                ))

            yield {
                "event": "progress",
                "step": 5,
                "progress": 85,
                "message": "Deep analysis complete",
                "run_id": run_id,
            }

            # Step 6: Score confidence and persist
            yield {
                "event": "progress",
                "step": 6,
                "progress": 90,
                "message": "Saving emerging topics...",
                "run_id": run_id,
            }

            for topic in emerging_topics:
                topic.confidence_score = self._calculate_confidence_v2(topic)

            await self._finish_run(
                run_id=run_id,
                topics=emerging_topics,
                topic_filter=topic_filter,
                articles_sampled=articles_sampled,
                duration=time.time() - start_time,
            )
            terminal = True

            yield {
                "event": "progress",
                "step": 6,
                "progress": 95,
                "message": "Topics saved to database",
                "run_id": run_id,
            }

            # Retirement is post-run cleanup; it cannot undo a completed run.
            auto_retired = await asyncio.to_thread(
                self._check_auto_retirement,
                [t.id for t in emerging_topics if t.id is not None],
                topic_filter,
            )

            yield self._completion_event(
                run_id=run_id,
                topics=emerging_topics,
                topic_filter=topic_filter,
                articles_sampled=articles_sampled,
                auto_retired=auto_retired,
                duration=time.time() - start_time,
            )

        except (GeneratorExit, asyncio.CancelledError):
            # The client went away mid-stream. Close the run record out — we
            # cannot yield anything at this point.
            if run_id is not None and not terminal:
                try:
                    self._fail_detection_run(
                        run_id,
                        "Detection cancelled before completion (client disconnected)",
                        time.time() - start_time,
                    )
                except Exception:
                    logger.exception("Could not mark cancelled run %s failed", run_id)
            raise

        except Exception as exc:
            logger.exception("Emerging topics detection failed")
            code = getattr(exc, "code", "detection_failed")
            message = _sanitize_error(exc)
            if run_id is not None and not terminal:
                try:
                    await asyncio.to_thread(
                        self._fail_detection_run,
                        run_id,
                        message,
                        time.time() - start_time,
                    )
                    terminal = True
                except Exception:
                    logger.exception("Could not mark run %s failed", run_id)
            yield {
                "event": "error",
                "step": 0,
                "progress": 100,
                "status": "failed",
                "code": code,
                "message": message,
                "run_id": run_id,
                "topic_filter": topic_filter,
            }

        finally:
            # Released synchronously on purpose. When a client disconnects the
            # generator is closed with GeneratorExit, and an async generator
            # that awaits while handling GeneratorExit raises "async generator
            # ignored GeneratorExit" — which would leave the scope locked for
            # exactly the case the lock has to survive. One pg_advisory_unlock
            # round trip on the loop is the cheaper trade.
            if owns_lock:
                lock.release()

    def _completion_event(
        self,
        run_id: Optional[int],
        topics: List[EmergingTopic],
        topic_filter: Optional[str],
        articles_sampled: int,
        auto_retired: int,
        duration: float,
        message: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build the single success event, emitted only after persistence."""
        retired_msg = f", {auto_retired} auto-retired" if auto_retired > 0 else ""
        return {
            "event": "complete",
            "step": 7,
            "progress": 100,
            "status": "completed",
            "message": message or (
                f"Detection complete: {len(topics)} emerging topics found{retired_msg}"
            ),
            "total_emerging_topics": len(topics),
            "emerging_topics": [t.to_dict() for t in topics],
            "auto_retired": auto_retired,
            "run_id": run_id,
            "topic_filter": topic_filter,
            "articles_sampled": articles_sampled,
            "articles_analyzed": articles_sampled,
            "duration_seconds": round(duration, 2),
        }

    async def _validate_theme_articles(self, theme: ProposedTheme) -> None:
        """Drop articles the relevance sweep rejects, keeping order and distances.

        The sweep judges the first N articles for cost; the rest of the theme's
        ranked list passes through untouched.
        """
        if not theme.article_uris:
            return

        cap = self.article_validator.MAX_VALIDATED
        articles = await asyncio.to_thread(
            self._fetch_articles_for_validation, theme.article_uris[:cap]
        )
        if not articles:
            return

        original_uris = list(theme.article_uris)
        original_distances = list(getattr(theme, 'article_distances', None) or [])

        kept = await self.article_validator.validate_theme_articles(
            theme_label=theme.theme_label,
            theme_description=theme.theme_description,
            key_entities=theme.key_entities or [],
            articles=articles,
            min_confidence=0.7,
            ordered_uris=original_uris,
        )

        theme.article_uris = kept
        if original_distances:
            uri_to_dist = dict(zip(original_uris, original_distances))
            theme.article_distances = [uri_to_dist.get(uri, 0.0) for uri in kept]

        logger.info(
            f"AI validation: {len(kept)}/{len(original_uris)} "
            f"articles passed for '{theme.theme_label}'"
        )

    async def _finish_run(
        self,
        run_id: int,
        topics: List[EmergingTopic],
        topic_filter: Optional[str],
        articles_sampled: int,
        duration: float,
    ) -> None:
        """Persist a completed run's results as one atomic unit.

        Topic rows, their history snapshots, the missed-run counters for topics
        this run did not see, and the run's own completion all commit together.
        If any part fails, nothing is written and the caller marks the run
        failed — there is no state where some topics saved and the run still
        claims success.
        """
        await asyncio.to_thread(
            self._persist_run_results,
            run_id,
            topics,
            topic_filter,
            articles_sampled,
            duration,
        )

    def _persist_run_results(
        self,
        run_id: int,
        topics: List[EmergingTopic],
        topic_filter: Optional[str],
        articles_sampled: int,
        duration: float,
    ) -> None:
        """Blocking half of :meth:`_finish_run`. One connection, one transaction."""
        conn = None
        try:
            conn = self._get_connection()
            for topic in topics:
                topic.topic_filter = topic_filter
                topic.id = self._save_emerging_topic(conn, topic, topic_filter)
                self._save_topic_history(conn, topic.id, run_id, topic)

            detected_ids = [t.id for t in topics if t.id is not None]
            self._apply_missed_runs(conn, detected_ids, topic_filter)
            self._complete_detection_run(
                conn, run_id, len(topics), articles_sampled, duration
            )
            conn.commit()
        except Exception:
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    logger.exception("Rollback failed while persisting run %s", run_id)
            raise
        finally:
            if conn is not None:
                conn.close()

    async def _check_historical_coverage(
        self,
        theme: ProposedTheme,
        days_back: int,
        topic_filter: Optional[str] = None,
        history_window_days: int = 60,
        min_historical_articles: int = 3
    ) -> tuple:
        """Has this theme already been covered before the analysis window?

        Returns ``(status, shadow)`` where status is one of ``ongoing``,
        ``not_found`` or ``unknown``, and shadow is the decision detail to
        record when running in shadow mode (None otherwise).

        ``unknown`` is the honest answer almost everywhere today. This check
        used to compare DeBERTa distances against a fixed 0.85, which matched
        100% of the corpus and so labelled every theme — including invented
        ones — as ongoing. That decision is gone rather than retuned: the
        signal is missing from the store, not the threshold. See
        historical_backend.py.

        Never raises for a classification problem. An unavailable index, a
        missing vector, or a failed query all mean "we could not tell", and the
        caller keeps ``llm_proposed``. Suppressing a genuinely new topic is the
        worse failure, because nobody sees a notification that never fires.
        """
        mode = historical_backend.resolve_mode()
        if mode == historical_backend.MODE_OFF:
            return (historical_backend.UNKNOWN, None)

        try:
            return await asyncio.to_thread(
                self._classify_historical_coverage,
                theme,
                days_back,
                topic_filter,
                history_window_days,
                min_historical_articles,
                mode,
            )
        except Exception as exc:
            logger.warning(
                "Historical coverage check failed for '%s' (%s); recording unknown",
                theme.theme_label, exc,
            )
            return (historical_backend.UNKNOWN, None)

    def _classify_historical_coverage(
        self,
        theme: ProposedTheme,
        days_back: int,
        topic_filter: Optional[str],
        history_window_days: int,
        min_historical_articles: int,
        mode: str,
    ) -> tuple:
        """Blocking half of :meth:`_check_historical_coverage`, E5 only.

        Anchors on the E5 vectors of the theme's own articles rather than
        embedding its label. Those vectors already exist in the store, so this
        costs one query instead of loading a 2GB sentence-transformer into the
        detection process — and comparing a theme's actual articles against
        older articles is a better question than comparing a short label string
        against them.
        """
        conn = None
        try:
            conn = self._get_connection()

            if not historical_backend.e5_available(conn):
                logger.info(
                    "Theme '%s': %s",
                    theme.theme_label,
                    historical_backend.describe(mode, False),
                )
                return (historical_backend.UNKNOWN, None)

            uris = list(theme.article_uris or [])[:30]
            if len(uris) < 2:
                return (historical_backend.UNKNOWN, None)

            placeholders = ", ".join(f":u{i}" for i in range(len(uris)))
            params = {f"u{i}": u for i, u in enumerate(uris)}

            # The theme's own vectors, averaged into a centroid. Anchoring on
            # the members is what removes the need for a query encoder.
            member_rows = conn.execute(text(f"""
                SELECT embedding::text
                FROM {historical_backend.E5_TABLE}
                WHERE article_uri IN ({placeholders})
            """), params).fetchall()

            vectors = []
            for row in member_rows:
                try:
                    vectors.append([float(v) for v in row[0].strip("[]").split(",")])
                except (AttributeError, ValueError):
                    continue
            if len(vectors) < 2:
                logger.info(
                    "Theme '%s': only %s of %s articles have E5 vectors; unknown",
                    theme.theme_label, len(vectors), len(uris),
                )
                return (historical_backend.UNKNOWN, None)

            dim = len(vectors[0])
            centroid = [sum(v[i] for v in vectors) / len(vectors) for i in range(dim)]
            norm = sum(c * c for c in centroid) ** 0.5 or 1.0
            centroid = [c / norm for c in centroid]
            centroid_literal = "[" + ",".join(str(c) for c in centroid) + "]"

            now = utcnow()
            published_ts = publication_ts_sql("a.publication_date")
            scope = {
                "centroid": centroid_literal,
                "history_start": now - timedelta(days=history_window_days),
                "history_end": now - timedelta(days=days_back),
                "limit": max(min_historical_articles * 10, self.HISTORICAL_CANDIDATE_LIMIT),
                "background": self.BACKGROUND_SAMPLE_SIZE,
            }
            topic_clause = ""
            if topic_filter:
                topic_clause = "AND a.topic = :topic"
                scope["topic"] = topic_filter

            # How close the theme's own members are to their centroid, which is
            # the "about as close as this theme's own articles" calibration term.
            theme_distances = [
                float(r[0]) for r in conn.execute(text(f"""
                    SELECT embedding <=> CAST(:centroid AS vector)
                    FROM {historical_backend.E5_TABLE}
                    WHERE article_uri IN ({placeholders})
                """), {**params, "centroid": centroid_literal}).fetchall()
            ]

            candidates = [
                {
                    "distance": float(r["distance"]),
                    "news_source": r["news_source"],
                    "publication_day": r["publication_day"],
                }
                for r in conn.execute(text(f"""
                    SELECT a.news_source,
                           ({published_ts})::date AS publication_day,
                           m.embedding <=> CAST(:centroid AS vector) AS distance
                    FROM {historical_backend.E5_TABLE} m
                    JOIN articles a ON a.uri = m.article_uri
                    WHERE {published_ts} >= :history_start
                      AND {published_ts} < :history_end
                      {topic_clause}
                    ORDER BY distance, a.uri
                    LIMIT :limit
                """), scope).mappings()
            ]

            background = [
                float(r[0]) for r in conn.execute(text(f"""
                    SELECT m.embedding <=> CAST(:centroid AS vector)
                    FROM {historical_backend.E5_TABLE} m
                    JOIN articles a ON a.uri = m.article_uri
                    WHERE {published_ts} >= :history_start
                      AND {published_ts} < :history_end
                      AND left(md5(m.article_uri), 1) IN ('0', '1')
                      {topic_clause}
                    LIMIT :background
                """), scope).fetchall()
            ]

            decision = historical_cutoff.decide(
                theme_distances=theme_distances,
                background_distances=background,
                candidates=candidates,
                backend=historical_backend.E5,
                min_articles=min_historical_articles,
            )

            shadow = {
                "backend": historical_backend.E5,
                "mode": mode,
                "would_be": (
                    historical_backend.ONGOING if decision.is_ongoing
                    else historical_backend.NOT_FOUND
                ),
                "cutoff": round(decision.cutoff, 4),
                "provisional": decision.provisional,
                "qualifying_articles": decision.qualifying_articles,
                "qualifying_sources": decision.qualifying_sources,
                "qualifying_dates": decision.qualifying_dates,
                "candidates_examined": decision.candidates_examined,
            }

            if mode == historical_backend.MODE_SHADOW:
                # Logged with a stable prefix so the labelled-set validation can
                # grep for it, and recorded on the topic so it can be queried.
                logger.info(
                    "HISTORICAL_SHADOW theme=%r %s",
                    theme.theme_label, decision.describe(),
                )
                return (historical_backend.UNKNOWN, shadow)

            status = (
                historical_backend.ONGOING if decision.is_ongoing
                else historical_backend.NOT_FOUND
            )
            logger.info(
                "Theme '%s' historical check (%s): %s",
                theme.theme_label, historical_backend.E5, decision.describe(),
            )
            return (status, shadow)

        finally:
            if conn:
                conn.close()

    def _create_topic_from_theme(
        self,
        theme: ProposedTheme,
        analysis: DeepAnalysis,
        trend: TrendScore,
        detection_date: date,
        topic_filter: Optional[str] = None,
        historical_status: str = historical_backend.UNKNOWN,
        historical_shadow: Optional[Dict[str, Any]] = None,
    ) -> EmergingTopic:
        """Create an EmergingTopic from theme, analysis, and trend data.

        The LLM's "Not mentioned" placeholders are cleaned out here, before
        anything is scored or stored, so an empty finding is stored as empty.
        """
        # Only a positive, enforced finding makes a topic "ongoing". Unknown
        # and not_found both stay llm_proposed: a topic wrongly marked ongoing
        # is suppressed from new-topic alerts and nobody sees the absence.
        topic_detection_type = (
            "ongoing_topic"
            if historical_status == historical_backend.ONGOING
            else "llm_proposed"
        )

        actors = sentinels.clean_list_dict(
            analysis.actors.to_dict() if analysis.actors else {}
        )
        events = sentinels.clean_events(
            analysis.events.to_dict() if analysis.events else {}
        )
        implications = sentinels.clean_str_dict(
            analysis.implications.to_dict() if analysis.implications else {}
        )
        org_implications = sentinels.clean_str_dict(
            analysis.organization_implications.to_dict()
            if analysis.organization_implications else {}
        )
        signals = sentinels.clean_list_dict(
            analysis.signals.to_dict() if analysis.signals else {}
        )
        synthesis = sentinels.clean_synthesis(
            analysis.synthesis.to_dict() if analysis.synthesis else {}
        )
        synthesis["model_used"] = analysis.model_used

        key_entities = sentinels.clean_list(theme.key_entities)

        return EmergingTopic(
            topic_label=theme.theme_label,
            topic_description=theme.theme_description,
            detection_date=detection_date,
            detection_type=topic_detection_type,
            cluster_id=f"theme_{detection_date.isoformat()}_{theme.theme_label[:20].replace(' ', '_')}",
            article_count=len(theme.article_uris),
            article_uris=theme.article_uris,
            topic_filter=normalize_topic_filter(topic_filter),
            historical_coverage_status=historical_status,
            historical_shadow=historical_shadow,
            # From theme proposal
            key_entities=key_entities,
            why_emerging=theme.why_emerging,
            search_query=theme.search_query,
            # From deep analysis
            actors=actors,
            events=events,
            implications=implications,
            organization_implications=org_implications,
            signals=signals,
            synthesis=synthesis,
            # From trend scoring
            volume_score=trend.volume_score,
            velocity_score=trend.velocity_score,
            diversity_score=trend.diversity_score,
            novelty_score=trend.novelty_score,
            composite_score=trend.composite_score,
            velocity=trend.velocity_label,
            source_count=trend.source_count,
            # Legacy compatibility
            key_themes=key_entities[:4],
            representative_keywords=[],
            emergence_rationale=theme.why_emerging,
            status="active",
        )

    def _calculate_confidence_v2(self, topic: EmergingTopic) -> float:
        """Confidence for a v2 topic, capped at 1.0.

        The deep-analysis increments require actual findings. Before, a topic
        whose actor lists all read "Not mentioned" collected the same points as
        one with named companies, because a list holding a placeholder string
        is still truthy.
        """
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

        # Substantive deep analysis = higher confidence
        if sentinels.has_substance(topic.actors):
            confidence += 0.05
        if topic.events and sentinels.has_substance(topic.events.get("trigger_event")):
            confidence += 0.05

        return min(1.0, confidence)

    def _save_emerging_topic(
        self,
        conn,
        topic: EmergingTopic,
        topic_filter: Optional[str]
    ) -> int:
        """Insert or update one emerging topic on the caller's connection.

        The caller owns the transaction, so a failure part-way through a run
        rolls the whole run back rather than leaving half the topics saved.

        Identity is (label, scope). Every lookup below is scoped by
        ``topic_filter``, using ``IS NOT DISTINCT FROM`` so the global NULL
        scope matches only itself: "AI Chip Export Controls" under the
        `semiconductors` filter and the same label under the global scope are
        two separate topics with separate counters.

        Raises on failure. It used to swallow the error and return None, which
        turned a failed save into a topic that reported success with no id.
        """
        topic_filter = normalize_topic_filter(topic_filter)

        # Exact label match within the same scope, last 7 days
        check_stmt = text("""
            SELECT id, topic_label FROM emerging_topics
            WHERE topic_label = :label
            AND topic_filter IS NOT DISTINCT FROM :topic_filter
            AND detection_date >= CURRENT_DATE - INTERVAL '7 days'
            ORDER BY detection_date DESC
            LIMIT 1
        """)
        existing = conn.execute(
            check_stmt, {"label": topic.topic_label, "topic_filter": topic_filter}
        ).fetchone()

        try:
            # If no exact match, check for similar labels (fuzzy match)
            if not existing:
                # Extract significant words from the new topic label (3+ chars, lowercase)
                label_words = set(w.lower() for w in topic.topic_label.split() if len(w) >= 3)
                # Remove common words
                label_words -= {'the', 'and', 'for', 'with', 'from', 'that', 'this', 'are', 'was', 'were'}

                if label_words:
                    # Candidates come from the same scope only.
                    similar_stmt = text("""
                        SELECT id, topic_label FROM emerging_topics
                        WHERE topic_filter IS NOT DISTINCT FROM :topic_filter
                        AND detection_date >= CURRENT_DATE - INTERVAL '7 days'
                        ORDER BY detection_date DESC
                    """)
                    candidates = conn.execute(
                        similar_stmt, {"topic_filter": topic_filter}
                    ).fetchall()

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
                        consecutive_detections = COALESCE(consecutive_detections, 0) + 1,
                        missed_runs = 0,
                        historical_coverage_status = :historical_status,
                        historical_shadow = CAST(:historical_shadow AS jsonb),
                        status = CASE WHEN status = 'retired' THEN status ELSE 'active' END
                    WHERE id = :id
                    AND topic_filter IS NOT DISTINCT FROM :topic_filter
                """)

                conn.execute(update_stmt, {
                    "id": existing_id,
                    "topic_filter": topic_filter,
                    "historical_status": topic.historical_coverage_status,
                    "historical_shadow": (
                        json_module.dumps(topic.historical_shadow)
                        if topic.historical_shadow else None
                    ),
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
                    first_detection_date, last_detection_date, detection_count,
                    consecutive_detections, missed_runs,
                    historical_coverage_status, historical_shadow
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
                    :date, :date, 1, 1, 0,
                    :historical_status, CAST(:historical_shadow AS jsonb)
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
                "historical_status": topic.historical_coverage_status,
                "historical_shadow": (
                    json_module.dumps(topic.historical_shadow)
                    if topic.historical_shadow else None
                ),
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

            row = result.fetchone()
            if not row:
                raise DetectionFailed(
                    f"Insert of emerging topic '{topic.topic_label}' returned no id",
                    code="topic_persist_failed",
                )
            return row[0]

        except DetectionFailed:
            raise
        except Exception as exc:
            logger.error(f"Error saving emerging topic '{topic.topic_label}': {exc}")
            raise DetectionFailed(
                f"Could not save emerging topic '{topic.topic_label}': {exc}",
                code="topic_persist_failed",
            ) from exc

    def _apply_missed_runs(
        self,
        conn,
        detected_topic_ids: List[int],
        topic_filter: Optional[str],
    ) -> int:
        """Count this completed run as a miss for topics it did not detect.

        Scoped to the run's own filter: a run over `climate` says nothing about
        a topic that belongs to `semiconductors` or to the global scope. Only
        completed runs reach this — a failed run must not move any counter.
        """
        topic_filter = normalize_topic_filter(topic_filter)
        stmt = text("""
            UPDATE emerging_topics
            SET missed_runs = COALESCE(missed_runs, 0) + 1,
                consecutive_detections = 0
            WHERE (status = 'active' OR status IS NULL)
              AND topic_filter IS NOT DISTINCT FROM :topic_filter
              AND NOT (id = ANY(:detected_ids))
        """)
        result = conn.execute(stmt, {
            "topic_filter": topic_filter,
            "detected_ids": list(detected_topic_ids or []),
        })
        return result.rowcount or 0

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
        conn,
        run_id: int,
        topics_detected: int,
        articles_sampled: int,
        duration_seconds: float
    ) -> None:
        """Mark a run completed on the caller's connection and transaction.

        Deliberately not swallowing errors: if the run record cannot be closed
        out, the whole run rolls back and is marked failed. A "successful" run
        nobody recorded is worse than a recorded failure.
        """
        stmt = text(f"""
            UPDATE detection_runs SET
                topics_detected = :topics,
                articles_sampled = :articles,
                duration_seconds = :duration,
                status = 'completed'
                {self._run_outcome_set_clause(completed=True)}
            WHERE id = :run_id
        """)
        conn.execute(stmt, {
            "run_id": run_id,
            "topics": topics_detected,
            "articles": articles_sampled,
            "duration": duration_seconds,
        })

    def _run_outcome_set_clause(self, completed: bool) -> str:
        """Extra SET columns for the run outcome, when the tenant has them.

        ``error_message`` and ``completed_at`` arrive with migration et_007. A
        tenant that has not run it yet still gets a correct terminal status.
        """
        if not self._has_run_outcome_columns():
            return ""
        if completed:
            return ", completed_at = NOW(), error_message = NULL"
        return ", completed_at = NOW(), error_message = :error"

    _run_outcome_columns: Optional[bool] = None

    def _has_run_outcome_columns(self) -> bool:
        """Probe once for the et_007 outcome columns."""
        if EmergingTopicsService._run_outcome_columns is not None:
            return EmergingTopicsService._run_outcome_columns
        conn = None
        try:
            conn = self._get_connection()
            present = conn.execute(text("""
                SELECT COUNT(*) FROM information_schema.columns
                WHERE table_name = 'detection_runs'
                AND column_name IN ('error_message', 'completed_at')
            """)).scalar()
            EmergingTopicsService._run_outcome_columns = (present == 2)
        except Exception as exc:
            logger.warning("Could not probe detection_runs columns: %s", exc)
            EmergingTopicsService._run_outcome_columns = False
        finally:
            if conn:
                conn.close()
        return EmergingTopicsService._run_outcome_columns

    def _fail_detection_run(
        self,
        run_id: int,
        error_message: str,
        duration_seconds: float,
    ) -> None:
        """Mark a run failed, on its own connection.

        Runs on the error path, so it must not depend on the transaction that
        just blew up. Errors here are logged, not raised — the caller is already
        reporting a failure.
        """
        conn = None
        try:
            conn = self._get_connection()
            stmt = text(f"""
                UPDATE detection_runs SET
                    status = 'failed',
                    duration_seconds = :duration
                    {self._run_outcome_set_clause(completed=False)}
                WHERE id = :run_id
            """)
            params = {"run_id": run_id, "duration": duration_seconds}
            if self._has_run_outcome_columns():
                params["error"] = error_message[:1000]
            conn.execute(stmt, params)
            conn.commit()
            logger.error("Detection run %s marked failed: %s", run_id, error_message)
        except Exception as exc:
            logger.error(f"Error marking detection run {run_id} failed: {exc}")
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
        finally:
            if conn:
                conn.close()

    def _save_topic_history(
        self,
        conn,
        topic_id: int,
        run_id: int,
        topic: EmergingTopic
    ) -> None:
        """Save a history snapshot for this topic in this run.

        Uses the caller's transaction, and raises rather than swallowing: a
        missing snapshot silently breaks the trajectory charts.
        """
        try:
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
        except Exception as exc:
            logger.error(f"Error saving topic history for topic {topic_id}: {exc}")
            raise DetectionFailed(
                f"Could not save the history snapshot for topic {topic_id}: {exc}",
                code="topic_history_persist_failed",
            ) from exc

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
        topic_filter = normalize_topic_filter(topic_filter)
        conn = None
        retired_count = 0
        try:
            conn = self._get_connection()

            # Candidates: active topics in THIS scope that this run did not
            # detect and that have been quiet for at least min_inactive_days.
            # The interval is a bound parameter, not string-substituted into the
            # SQL, and the scope test is null-safe so a global run cannot retire
            # a named-scope topic.
            check_stmt = text("""
                SELECT id, topic_label, last_detection_date, consecutive_detections
                FROM emerging_topics
                WHERE (status = 'active' OR status IS NULL)
                  AND topic_filter IS NOT DISTINCT FROM :topic_filter
                  AND NOT (id = ANY(:detected_ids))
                  AND last_detection_date < CURRENT_DATE - (:min_days * INTERVAL '1 day')
            """)

            result = conn.execute(check_stmt, {
                "topic_filter": topic_filter,
                "detected_ids": list(detected_topic_ids or []),
                "min_days": min_inactive_days,
            })
            candidates = result.fetchall()

            for row in candidates:
                topic_id = row[0]
                topic_label = row[1]
                last_detection = row[2]

                # How many completed runs in this scope have passed since the
                # topic was last seen. Failed runs do not count against it.
                runs_since_stmt = text("""
                    SELECT COUNT(*) FROM detection_runs
                    WHERE run_date > :last_detection
                    AND status = 'completed'
                    AND topic_filter IS NOT DISTINCT FROM :topic_filter
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
        days_back: Optional[int] = None,
        run_lock: Optional[DetectionRunLock] = None,
    ) -> Dict[str, Any]:
        """Run full detection without streaming.

        Raises :class:`DetectionFailed` when the run fails. It used to return an
        empty-but-successful result, so a caller could not tell "nothing is
        emerging" from "the encoder is down".
        """
        result = {
            "detection_date": str(date.today()),
            "topic_filter": normalize_topic_filter(topic_filter),
            "emerging_topics": [],
            "total_emerging_topics": 0,
            "articles_sampled": 0,
            "articles_analyzed": 0,
            "run_id": None,
            "status": "failed",
        }

        completed = False
        async for update in self.run_detection_streaming(
            topic_filter, days_back, run_lock=run_lock
        ):
            if update.get("event") == "error":
                raise DetectionFailed(
                    update.get("message", "Detection failed"),
                    code=update.get("code", "detection_failed"),
                )
            if update.get("event") == "complete":
                completed = True
                result["emerging_topics"] = update.get("emerging_topics", [])
                result["total_emerging_topics"] = update.get("total_emerging_topics", 0)
                result["articles_sampled"] = update.get("articles_sampled", 0)
                result["articles_analyzed"] = update.get("articles_analyzed", 0)
                result["run_id"] = update.get("run_id")
                result["auto_retired"] = update.get("auto_retired", 0)
                result["status"] = "completed"

        if not completed:
            raise DetectionFailed(
                "Detection ended without a completion event",
                code="detection_incomplete",
            )

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

            # An explicit filter selects that scope only. No filter means every
            # scope, which is what the "all topics" view asks for.
            topic_filter = normalize_topic_filter(topic_filter)
            if topic_filter:
                filter_clause += " AND topic_filter IS NOT DISTINCT FROM :topic"
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
                    emergence_rationale, article_uris, status, topic_filter,
                    historical_coverage_status,
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
                    topic_filter=row.get("topic_filter"),
                    historical_coverage_status=(
                        row.get("historical_coverage_status") or "unknown"),
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

            topic_filter = normalize_topic_filter(topic_filter)
            if topic_filter:
                filter_clause += " AND topic_filter IS NOT DISTINCT FROM :topic"
                params["topic"] = topic_filter

            stmt = text(f"""
                SELECT
                    id, topic_label, topic_description, detection_date,
                    detection_type, cluster_id, article_count, growth_rate,
                    velocity, confidence_score, key_themes, representative_keywords,
                    emergence_rationale, article_uris, status, topic_filter,
                    historical_coverage_status,
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
                    topic_filter=row.get("topic_filter"),
                    historical_coverage_status=(
                        row.get("historical_coverage_status") or "unknown"),
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
