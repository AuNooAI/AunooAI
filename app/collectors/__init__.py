# This file makes the collectors directory a Python package
from .base_collector import ArticleCollector
from .arxiv_collector import ArxivCollector
from .newsapi_collector import NewsAPICollector
from .thenewsapi_collector import TheNewsAPICollector
from .collector_factory import CollectorFactory

__all__ = [
    'ArticleCollector',
    'ArxivCollector',
    'NewsAPICollector',
    'TheNewsAPICollector',
    'CollectorFactory'
] 