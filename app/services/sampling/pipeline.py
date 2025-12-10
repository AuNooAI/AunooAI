"""
Article processing pipeline.
Chains filters and sampling strategies together.
"""

from typing import Dict, List, Optional
import logging

from .base import FilterStrategy, SamplingStrategy, SamplingContext

logger = logging.getLogger(__name__)


class ArticlePipeline:
    """
    Composable article processing pipeline.
    Applies filters in sequence, then sampling strategy.
    """

    def __init__(
        self,
        filters: Optional[List[FilterStrategy]] = None,
        sampler: Optional[SamplingStrategy] = None,
        name: str = "custom"
    ):
        """
        Args:
            filters: List of filter strategies to apply in sequence
            sampler: Sampling strategy for final selection
            name: Name of this pipeline configuration
        """
        self.filters = filters or []
        self.sampler = sampler
        self.name = name

    def execute(
        self,
        articles: List[Dict],
        limit: int,
        context: Optional[SamplingContext] = None
    ) -> List[Dict]:
        """
        Execute the pipeline on articles.

        Args:
            articles: Input article list
            limit: Maximum articles to return
            context: Sampling context (created if not provided)

        Returns:
            Processed and sampled articles
        """
        if context is None:
            context = SamplingContext()

        # Update context statistics
        context.update_stats(articles)

        logger.debug(f"Pipeline '{self.name}': Starting with {len(articles)} articles")

        # Apply filters in sequence
        filtered = articles
        for f in self.filters:
            before_count = len(filtered)
            filtered = f.filter(filtered, context)
            logger.debug(f"Filter '{f.name}': {before_count} -> {len(filtered)} articles")
            if not filtered:
                logger.debug("Pipeline: No articles left after filtering")
                return []

        # Apply sampling strategy
        if self.sampler:
            result = self.sampler.sample(filtered, limit, context)
            logger.debug(f"Sampler '{self.sampler.name}': {len(filtered)} -> {len(result)} articles")
        else:
            # No sampler, just truncate to limit
            result = filtered[:limit]

        return result

    def add_filter(self, filter_strategy: FilterStrategy) -> 'ArticlePipeline':
        """Add a filter to the pipeline. Returns self for chaining."""
        self.filters.append(filter_strategy)
        return self

    def set_sampler(self, sampler: SamplingStrategy) -> 'ArticlePipeline':
        """Set the sampling strategy. Returns self for chaining."""
        self.sampler = sampler
        return self

    def __repr__(self) -> str:
        filter_names = [f.name for f in self.filters]
        sampler_name = self.sampler.name if self.sampler else "none"
        return f"ArticlePipeline(name='{self.name}', filters={filter_names}, sampler='{sampler_name}')"


class PipelineBuilder:
    """
    Builder for creating article pipelines from configuration.
    """

    def __init__(self, registry=None):
        """
        Args:
            registry: StrategyRegistry instance for looking up components
        """
        self.registry = registry
        self._filters: List[FilterStrategy] = []
        self._sampler: Optional[SamplingStrategy] = None
        self._name = "custom"

    def with_filter(self, filter_strategy: FilterStrategy) -> 'PipelineBuilder':
        """Add a filter instance."""
        self._filters.append(filter_strategy)
        return self

    def with_filter_by_name(self, name: str, **params) -> 'PipelineBuilder':
        """Add a filter by name (requires registry)."""
        if self.registry is None:
            raise ValueError("Registry required to look up filter by name")
        filter_class = self.registry.get_filter(name)
        if filter_class:
            self._filters.append(filter_class(**params))
        return self

    def with_sampler(self, sampler: SamplingStrategy) -> 'PipelineBuilder':
        """Set the sampler instance."""
        self._sampler = sampler
        return self

    def with_sampler_by_name(self, name: str, **params) -> 'PipelineBuilder':
        """Set sampler by name (requires registry)."""
        if self.registry is None:
            raise ValueError("Registry required to look up sampler by name")
        sampler_class = self.registry.get_strategy(name)
        if sampler_class:
            self._sampler = sampler_class(**params)
        return self

    def named(self, name: str) -> 'PipelineBuilder':
        """Set pipeline name."""
        self._name = name
        return self

    def build(self) -> ArticlePipeline:
        """Build the pipeline."""
        return ArticlePipeline(
            filters=self._filters.copy(),
            sampler=self._sampler,
            name=self._name
        )

    @classmethod
    def from_config(cls, config: Dict, registry=None) -> ArticlePipeline:
        """
        Create a pipeline from a configuration dictionary.

        Config format:
        {
            "name": "my_pipeline",
            "filters": [
                {"type": "date_range", "params": {"days_back": 7}},
                {"type": "quality_gate", "params": {"require_title": True}}
            ],
            "sampling": {
                "type": "recency_diversity",
                "params": {"recency_ratio": 0.7}
            }
        }
        """
        builder = cls(registry)

        if 'name' in config:
            builder.named(config['name'])

        # Add filters
        for filter_config in config.get('filters', []):
            filter_type = filter_config.get('type')
            params = filter_config.get('params', {})

            if registry:
                builder.with_filter_by_name(filter_type, **params)
            else:
                # Try to import and instantiate directly
                from . import filters as filter_module
                filter_class = getattr(filter_module, _type_to_class_name(filter_type), None)
                if filter_class:
                    builder.with_filter(filter_class(**params))

        # Set sampler
        sampling_config = config.get('sampling', {})
        if sampling_config:
            sampler_type = sampling_config.get('type')
            params = sampling_config.get('params', {})

            if registry:
                builder.with_sampler_by_name(sampler_type, **params)
            else:
                from . import strategies as strategy_module
                sampler_class = getattr(strategy_module, _type_to_class_name(sampler_type), None)
                if sampler_class:
                    builder.with_sampler(sampler_class(**params))

        return builder.build()


def _type_to_class_name(type_name: str) -> str:
    """Convert snake_case type name to PascalCase class name."""
    # Handle common patterns
    mappings = {
        'date_range': 'DateRangeFilter',
        'quality_gate': 'QualityGateFilter',
        'topic': 'TopicFilter',
        'bias': 'BiasFilter',
        'factuality': 'FactualityFilter',
        'category': 'CategoryFilter',
        'composite': 'CompositeFilter',
        'duplicate': 'DuplicateFilter',
        'recency': 'RecencySampling',
        'quality': 'QualitySampling',
        'diversity': 'DiversitySampling',
        'topic_balanced': 'TopicBalancedSampling',
        'semantic': 'SemanticSampling',
        'recency_diversity': 'RecencyDiversitySampling',
        'random': 'RandomSampling',
    }
    return mappings.get(type_name, type_name)
