"""
Sampling and Filtering Strategies Framework

This module provides composable building blocks for article selection:
- Scorers: Calculate relevance/quality scores for articles
- Filters: Include/exclude articles based on criteria
- Strategies: Select articles from pools using different algorithms
- Pipeline: Chain filters and strategies together
- Registry: Discover and access all components
"""

from .base import (
    ArticleScorer,
    FilterStrategy,
    SamplingStrategy,
    SamplingContext,
)
from .scorers import (
    SourceQualityScorer,
    RecencyScorer,
    ContentQualityScorer,
    DiversityScorer,
    SemanticRelevanceScorer,
    CompositeScorer,
)
from .filters import (
    TopicFilter,
    DateRangeFilter,
    BiasFilter,
    FactualityFilter,
    CategoryFilter,
    QualityGateFilter,
    CompositeFilter,
)
from .strategies import (
    RecencySampling,
    QualitySampling,
    DiversitySampling,
    TopicBalancedSampling,
    SemanticSampling,
    CompositeSampling,
    RecencyDiversitySampling,
)
from .pipeline import ArticlePipeline
from .registry import StrategyRegistry, get_registry

__all__ = [
    # Base classes
    'ArticleScorer',
    'FilterStrategy',
    'SamplingStrategy',
    'SamplingContext',
    # Scorers
    'SourceQualityScorer',
    'RecencyScorer',
    'ContentQualityScorer',
    'DiversityScorer',
    'SemanticRelevanceScorer',
    'CompositeScorer',
    # Filters
    'TopicFilter',
    'DateRangeFilter',
    'BiasFilter',
    'FactualityFilter',
    'CategoryFilter',
    'QualityGateFilter',
    'CompositeFilter',
    # Strategies
    'RecencySampling',
    'QualitySampling',
    'DiversitySampling',
    'TopicBalancedSampling',
    'SemanticSampling',
    'CompositeSampling',
    'RecencyDiversitySampling',
    # Pipeline & Registry
    'ArticlePipeline',
    'StrategyRegistry',
    'get_registry',
]
