"""
External Data Providers

Integrates with external APIs to fetch real, measured data:
- Semantic Scholar: Citation counts, paper metrics, academic influence
- Google Programmable Search: Financial news, M&A announcements, funding
- Crunchbase: M&A deals, funding rounds (requires paid API key)
"""

from .base_provider import BaseDataProvider, CitationData, FundingData, MAData, ExternalDataResult
from .semantic_scholar import SemanticScholarProvider
from .google_search import GoogleSearchProvider

__all__ = [
    'BaseDataProvider',
    'CitationData',
    'FundingData',
    'MAData',
    'ExternalDataResult',
    'SemanticScholarProvider',
    'GoogleSearchProvider',
]
