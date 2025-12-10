"""
Strategy registry for discovering and accessing sampling components.
"""

from typing import Dict, Type, Optional, List
import os
import yaml
import logging

from .base import ArticleScorer, FilterStrategy, SamplingStrategy, SamplingContext
from .scorers import (
    SourceQualityScorer, RecencyScorer, ContentQualityScorer,
    DiversityScorer, SemanticRelevanceScorer, CompositeScorer
)
from .filters import (
    TopicFilter, DateRangeFilter, BiasFilter, FactualityFilter,
    CategoryFilter, QualityGateFilter, CompositeFilter, DuplicateFilter
)
from .strategies import (
    RecencySampling, QualitySampling, DiversitySampling,
    TopicBalancedSampling, SemanticSampling, CompositeSampling,
    RecencyDiversitySampling, RandomSampling
)
from .pipeline import ArticlePipeline, PipelineBuilder

logger = logging.getLogger(__name__)


class StrategyRegistry:
    """
    Central registry for all sampling components.
    Provides discovery, instantiation, and preset pipelines.
    """

    def __init__(self, custom_strategies_dir: Optional[str] = None):
        """
        Args:
            custom_strategies_dir: Directory containing custom YAML strategy definitions
        """
        self._scorers: Dict[str, Type[ArticleScorer]] = {}
        self._filters: Dict[str, Type[FilterStrategy]] = {}
        self._strategies: Dict[str, Type[SamplingStrategy]] = {}
        self._presets: Dict[str, dict] = {}  # Named pipeline presets

        self.custom_strategies_dir = custom_strategies_dir

        # Register built-in components
        self._register_builtins()

        # Load custom strategies
        if custom_strategies_dir:
            self._load_custom_strategies()

    def _register_builtins(self):
        """Register all built-in components."""
        # Scorers
        self.register_scorer('source_quality', SourceQualityScorer)
        self.register_scorer('recency', RecencyScorer)
        self.register_scorer('content_quality', ContentQualityScorer)
        self.register_scorer('diversity', DiversityScorer)
        self.register_scorer('semantic_relevance', SemanticRelevanceScorer)
        self.register_scorer('composite', CompositeScorer)

        # Filters
        self.register_filter('topic', TopicFilter)
        self.register_filter('date_range', DateRangeFilter)
        self.register_filter('bias', BiasFilter)
        self.register_filter('factuality', FactualityFilter)
        self.register_filter('category', CategoryFilter)
        self.register_filter('quality_gate', QualityGateFilter)
        self.register_filter('composite', CompositeFilter)
        self.register_filter('duplicate', DuplicateFilter)

        # Sampling strategies
        self.register_strategy('recency', RecencySampling)
        self.register_strategy('quality', QualitySampling)
        self.register_strategy('diversity', DiversitySampling)
        self.register_strategy('topic_balanced', TopicBalancedSampling)
        self.register_strategy('semantic', SemanticSampling)
        self.register_strategy('composite', CompositeSampling)
        self.register_strategy('recency_diversity', RecencyDiversitySampling)
        self.register_strategy('random', RandomSampling)

        # Register preset pipelines
        self._register_preset_pipelines()

    def _register_preset_pipelines(self):
        """Register common pipeline presets."""
        # Default for All Topics - Recency + Diversity
        self.register_preset('all_topics_default', {
            'name': 'all_topics_default',
            'description': 'Default strategy for All Topics: recent articles with diversity balance',
            'filters': [
                {'type': 'quality_gate', 'params': {'require_title': True}}
            ],
            'sampling': {
                'type': 'recency_diversity',
                'params': {'recency_ratio': 0.7}
            }
        })

        # Quality-focused
        self.register_preset('quality_first', {
            'name': 'quality_first',
            'description': 'Prioritize high-quality sources and content',
            'filters': [
                {'type': 'quality_gate', 'params': {'require_title': True, 'require_summary': True}}
            ],
            'sampling': {
                'type': 'quality',
                'params': {}
            }
        })

        # Recent only
        self.register_preset('latest', {
            'name': 'latest',
            'description': 'Most recent articles only',
            'filters': [],
            'sampling': {
                'type': 'recency',
                'params': {}
            }
        })

        # Diverse coverage
        self.register_preset('diverse', {
            'name': 'diverse',
            'description': 'Maximum diversity across categories and sources',
            'filters': [
                {'type': 'duplicate', 'params': {}}
            ],
            'sampling': {
                'type': 'diversity',
                'params': {'category_weight': 0.5, 'source_weight': 0.3, 'topic_weight': 0.2}
            }
        })

        # Topic balanced (for cross-topic)
        self.register_preset('balanced_topics', {
            'name': 'balanced_topics',
            'description': 'Balanced representation across all topics',
            'filters': [],
            'sampling': {
                'type': 'topic_balanced',
                'params': {'min_per_topic': 3, 'proportional': True}
            }
        })

        # Newsletter-style (quality + recency)
        self.register_preset('newsletter', {
            'name': 'newsletter',
            'description': 'Newsletter-optimized: high quality, recent, deduplicated',
            'filters': [
                {'type': 'quality_gate', 'params': {'require_title': True, 'min_summary_words': 20}},
                {'type': 'duplicate', 'params': {'similarity_threshold': 0.8}}
            ],
            'sampling': {
                'type': 'quality',
                'params': {}
            }
        })

        # Semantic search results
        self.register_preset('semantic_search', {
            'name': 'semantic_search',
            'description': 'For semantic search results: highest relevance first',
            'filters': [],
            'sampling': {
                'type': 'semantic',
                'params': {}
            }
        })

    def _load_custom_strategies(self):
        """Load custom strategy definitions from YAML files."""
        if not self.custom_strategies_dir or not os.path.exists(self.custom_strategies_dir):
            return

        for filename in os.listdir(self.custom_strategies_dir):
            if filename.endswith('.yaml') or filename.endswith('.yml'):
                filepath = os.path.join(self.custom_strategies_dir, filename)
                try:
                    with open(filepath, 'r') as f:
                        config = yaml.safe_load(f)
                        if config and 'name' in config:
                            self.register_preset(config['name'], config)
                            logger.info(f"Loaded custom strategy: {config['name']}")
                except Exception as e:
                    logger.warning(f"Failed to load custom strategy from {filename}: {e}")

    # Registration methods
    def register_scorer(self, name: str, scorer_class: Type[ArticleScorer]):
        """Register a scorer class."""
        self._scorers[name] = scorer_class

    def register_filter(self, name: str, filter_class: Type[FilterStrategy]):
        """Register a filter class."""
        self._filters[name] = filter_class

    def register_strategy(self, name: str, strategy_class: Type[SamplingStrategy]):
        """Register a sampling strategy class."""
        self._strategies[name] = strategy_class

    def register_preset(self, name: str, config: dict):
        """Register a pipeline preset configuration."""
        self._presets[name] = config

    # Lookup methods
    def get_scorer(self, name: str) -> Optional[Type[ArticleScorer]]:
        """Get a scorer class by name."""
        return self._scorers.get(name)

    def get_filter(self, name: str) -> Optional[Type[FilterStrategy]]:
        """Get a filter class by name."""
        return self._filters.get(name)

    def get_strategy(self, name: str) -> Optional[Type[SamplingStrategy]]:
        """Get a sampling strategy class by name."""
        return self._strategies.get(name)

    def get_preset(self, name: str) -> Optional[dict]:
        """Get a preset configuration by name."""
        return self._presets.get(name)

    # Listing methods
    def list_scorers(self) -> List[Dict]:
        """List all registered scorers with metadata."""
        result = []
        for name, cls in self._scorers.items():
            result.append({
                'name': name,
                'description': getattr(cls, 'description', ''),
                'class': cls.__name__
            })
        return result

    def list_filters(self) -> List[Dict]:
        """List all registered filters with metadata."""
        result = []
        for name, cls in self._filters.items():
            result.append({
                'name': name,
                'description': getattr(cls, 'description', ''),
                'class': cls.__name__
            })
        return result

    def list_strategies(self) -> List[Dict]:
        """List all registered strategies with metadata."""
        result = []
        for name, cls in self._strategies.items():
            result.append({
                'name': name,
                'description': getattr(cls, 'description', ''),
                'class': cls.__name__
            })
        return result

    def list_presets(self) -> List[Dict]:
        """List all registered presets with metadata."""
        result = []
        for name, config in self._presets.items():
            result.append({
                'name': name,
                'description': config.get('description', ''),
                'filters': [f.get('type') for f in config.get('filters', [])],
                'sampling': config.get('sampling', {}).get('type', '')
            })
        return result

    # Pipeline creation
    def create_pipeline(self, config: dict) -> ArticlePipeline:
        """Create a pipeline from configuration."""
        return PipelineBuilder.from_config(config, registry=self)

    def create_pipeline_from_preset(self, preset_name: str) -> Optional[ArticlePipeline]:
        """Create a pipeline from a preset name."""
        config = self.get_preset(preset_name)
        if config:
            return self.create_pipeline(config)
        return None

    def get_default_pipeline(self, topic: Optional[str] = None) -> ArticlePipeline:
        """
        Get the default pipeline based on context.

        Args:
            topic: Topic name (None or '__all__' for cross-topic mode)

        Returns:
            Appropriate default pipeline
        """
        if topic is None or topic == '__all__':
            return self.create_pipeline_from_preset('all_topics_default')
        else:
            return self.create_pipeline_from_preset('quality_first')


# Global registry instance
_registry: Optional[StrategyRegistry] = None


def get_registry(custom_dir: Optional[str] = None) -> StrategyRegistry:
    """
    Get the global registry instance.

    Args:
        custom_dir: Custom strategies directory (only used on first call)

    Returns:
        Global StrategyRegistry instance
    """
    global _registry
    if _registry is None:
        _registry = StrategyRegistry(custom_dir)
    return _registry


def reset_registry():
    """Reset the global registry (useful for testing)."""
    global _registry
    _registry = None
