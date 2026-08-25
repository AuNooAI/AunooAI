"""
Emerging Topics Detection Services (v2 - LLM-Driven)

This package provides services for detecting emerging topics in article collections
using multi-step LLM analysis.

V2 Components:
- ThemeProposer: LLM proposes themes from article samples
- ThemeValidator: Validates and merges proposed themes
- DeepAnalyzer: Extracts actors, events, implications
- TrendScorer: Calculates velocity, volume, diversity metrics
- EmergingTopicsService: Main orchestration service

Legacy Components (kept for fallback):
- NoveltyScorer: Calculates novelty scores for articles
- ClusterDetector: HDBSCAN-based clustering
- TemporalTracker: Tracks cluster evolution
- TopicSummarizer: Basic LLM summarization
"""

# V2 services
from .theme_proposer import ThemeProposer, ProposedTheme, ProposalResult
from .theme_validator import ThemeValidator, ValidationResult
from .deep_analyzer import DeepAnalyzer, DeepAnalysis, Actors, Events, Implications, Signals
from .trend_scorer import TrendScorer, TrendScore
from .article_validator import ArticleValidator, ValidationResult as ArticleValidationResult

# Legacy services
from .novelty_scorer import NoveltyScorer, NoveltyConfig, ArticleNoveltyScore
from .cluster_detector import ClusterDetector, ClusterConfig, ClusterResult, ArticleCluster
from .temporal_tracker import TemporalTracker, TemporalConfig, ClusterChange
from .topic_summarizer import TopicSummarizer, TopicSummary

# Run scoping, lifecycle, and notification vocabulary
from .run_lock import (
    DetectionAlreadyRunning,
    DetectionRunLock,
    normalize_topic_filter,
)
from .notification_filters import (
    ALLOWED_FILTERS,
    DEFAULT_FILTERS,
    DETECTION_TYPES,
    VELOCITY_STATES,
    normalize_filters,
    select_topics_for_notification,
    topic_matches_filters,
    validate_filters,
)

# Main service
from .emerging_topics_service import (
    DetectionFailed,
    EmergingTopicsService,
    EmergingTopicsConfig,
    EmergingTopic,
    get_emerging_topics_service,
)

__all__ = [
    # V2 services
    'ThemeProposer',
    'ProposedTheme',
    'ProposalResult',
    'ThemeValidator',
    'ValidationResult',
    'DeepAnalyzer',
    'DeepAnalysis',
    'Actors',
    'Events',
    'Implications',
    'Signals',
    'TrendScorer',
    'TrendScore',
    'ArticleValidator',
    'ArticleValidationResult',
    # Legacy services
    'NoveltyScorer',
    'NoveltyConfig',
    'ArticleNoveltyScore',
    'ClusterDetector',
    'ClusterConfig',
    'ClusterResult',
    'ArticleCluster',
    'TemporalTracker',
    'TemporalConfig',
    'ClusterChange',
    'TopicSummarizer',
    'TopicSummary',
    # Run scoping and lifecycle
    'DetectionAlreadyRunning',
    'DetectionRunLock',
    'DetectionFailed',
    'normalize_topic_filter',
    # Notification vocabulary
    'ALLOWED_FILTERS',
    'DEFAULT_FILTERS',
    'DETECTION_TYPES',
    'VELOCITY_STATES',
    'normalize_filters',
    'select_topics_for_notification',
    'topic_matches_filters',
    'validate_filters',
    # Main service
    'EmergingTopicsService',
    'EmergingTopicsConfig',
    'EmergingTopic',
    'get_emerging_topics_service',
]
