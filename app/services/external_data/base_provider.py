"""
Base Data Provider Interface

Abstract base class for external data providers.
All providers must implement the same interface for consistency.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


@dataclass
class CitationData:
    """Citation and academic metrics from external sources."""
    total_citations: int = 0
    citation_velocity: float = 0.0  # Citations per month
    h_index: Optional[int] = None
    influential_citations: int = 0
    papers_found: int = 0
    top_papers: List[Dict] = field(default_factory=list)
    source: str = "unknown"
    fetched_at: datetime = field(default_factory=datetime.now)

    def to_score(self) -> float:
        """Convert to 0-100 score for use in trend calculation."""
        # Logarithmic scaling for citations
        import math
        if self.total_citations <= 0:
            return 30.0  # Baseline for no data

        # Scale: 100 citations = 50, 1000 = 70, 10000 = 90
        log_citations = math.log10(self.total_citations + 1)
        score = min(100, 20 + (log_citations * 20))
        return score

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_citations": self.total_citations,
            "citation_velocity": self.citation_velocity,
            "h_index": self.h_index,
            "influential_citations": self.influential_citations,
            "papers_found": self.papers_found,
            "source": self.source,
            "score": self.to_score()
        }


@dataclass
class FundingData:
    """Funding and investment data from external sources."""
    total_funding_usd: int = 0
    deal_count: int = 0
    largest_deal_usd: int = 0
    recent_deals: List[Dict] = field(default_factory=list)
    funding_trend: str = "stable"  # 'increasing', 'stable', 'decreasing'
    source: str = "unknown"
    fetched_at: datetime = field(default_factory=datetime.now)

    def to_score(self) -> float:
        """Convert to 0-100 score for use in trend calculation."""
        import math
        if self.deal_count == 0:
            return 30.0  # Baseline

        # Score based on deal count and total funding
        deal_score = min(50, self.deal_count * 10)

        funding_score = 0
        if self.total_funding_usd > 0:
            log_funding = math.log10(self.total_funding_usd + 1)
            funding_score = min(50, log_funding * 5)

        return min(100, deal_score + funding_score)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_funding_usd": self.total_funding_usd,
            "deal_count": self.deal_count,
            "largest_deal_usd": self.largest_deal_usd,
            "recent_deals": self.recent_deals[:5],  # Top 5
            "funding_trend": self.funding_trend,
            "source": self.source,
            "score": self.to_score()
        }


@dataclass
class MAData:
    """M&A (Mergers & Acquisitions) data from external sources."""
    deal_count: int = 0
    total_value_usd: int = 0
    recent_deals: List[Dict] = field(default_factory=list)
    consolidation_trend: str = "stable"  # 'accelerating', 'stable', 'slowing'
    key_acquirers: List[str] = field(default_factory=list)
    source: str = "unknown"
    fetched_at: datetime = field(default_factory=datetime.now)

    def to_score(self) -> float:
        """Convert to 0-100 score for use in trend calculation."""
        import math
        if self.deal_count == 0:
            return 30.0  # Baseline

        # Score based on deal count
        deal_score = min(60, self.deal_count * 15)

        # Boost for trend
        trend_boost = 0
        if self.consolidation_trend == "accelerating":
            trend_boost = 20
        elif self.consolidation_trend == "slowing":
            trend_boost = -10

        return min(100, max(0, deal_score + trend_boost))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "deal_count": self.deal_count,
            "total_value_usd": self.total_value_usd,
            "recent_deals": self.recent_deals[:5],
            "consolidation_trend": self.consolidation_trend,
            "key_acquirers": self.key_acquirers[:5],
            "source": self.source,
            "score": self.to_score()
        }


@dataclass
class RegulatoryData:
    """Regulatory and policy data from external sources."""
    event_count: int = 0
    recent_events: List[Dict] = field(default_factory=list)
    jurisdictions: List[str] = field(default_factory=list)
    regulatory_trend: str = "stable"  # 'increasing', 'stable', 'decreasing'
    key_regulations: List[str] = field(default_factory=list)
    source: str = "unknown"
    fetched_at: datetime = field(default_factory=datetime.now)

    def to_score(self) -> float:
        """Convert to 0-100 score."""
        if self.event_count == 0:
            return 40.0  # Baseline - some regulatory activity assumed

        # More regulatory events = higher score
        event_score = min(70, 40 + (self.event_count * 5))

        # Boost for increasing regulation
        trend_boost = 0
        if self.regulatory_trend == "increasing":
            trend_boost = 15
        elif self.regulatory_trend == "decreasing":
            trend_boost = -10

        return min(100, max(0, event_score + trend_boost))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_count": self.event_count,
            "recent_events": self.recent_events[:5],
            "jurisdictions": self.jurisdictions,
            "regulatory_trend": self.regulatory_trend,
            "key_regulations": self.key_regulations[:5],
            "source": self.source,
            "score": self.to_score()
        }


@dataclass
class ExternalDataResult:
    """Aggregated result from external data fetch."""
    citations: Optional[CitationData] = None
    funding: Optional[FundingData] = None
    ma_activity: Optional[MAData] = None
    regulatory: Optional[RegulatoryData] = None
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        result = {"errors": self.errors}
        if self.citations:
            result["citations"] = self.citations.to_dict()
        if self.funding:
            result["funding"] = self.funding.to_dict()
        if self.ma_activity:
            result["ma_activity"] = self.ma_activity.to_dict()
        if self.regulatory:
            result["regulatory"] = self.regulatory.to_dict()
        return result


class BaseDataProvider(ABC):
    """
    Abstract base class for external data providers.

    Each provider implements methods for fetching specific data types.
    Providers should handle their own rate limiting and error handling.
    """

    PROVIDER_NAME: str = "base"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self._rate_limit_remaining: Optional[int] = None
        self._last_request_time: Optional[datetime] = None

    def is_available(self) -> bool:
        """
        Check if the provider is properly configured and available.
        Override in subclasses for specific requirements.

        Returns:
            True if provider can be used, False otherwise
        """
        return True

    def get_status(self) -> Dict[str, Any]:
        """
        Get provider status including availability and configuration.

        Returns:
            Dict with provider status information
        """
        return {
            "provider": self.PROVIDER_NAME,
            "available": self.is_available(),
            "has_api_key": bool(self.api_key)
        }

    @abstractmethod
    async def fetch_citation_data(
        self,
        query: str,
        limit: int = 100
    ) -> CitationData:
        """
        Fetch citation and academic metrics.

        Args:
            query: Search query (topic, keyword, etc.)
            limit: Maximum results to fetch

        Returns:
            CitationData with aggregated metrics
        """
        pass

    @abstractmethod
    async def fetch_funding_data(
        self,
        query: str,
        days_back: int = 90
    ) -> FundingData:
        """
        Fetch funding and investment data.

        Args:
            query: Search query
            days_back: How far back to search

        Returns:
            FundingData with aggregated metrics
        """
        pass

    @abstractmethod
    async def fetch_ma_data(
        self,
        query: str,
        days_back: int = 90
    ) -> MAData:
        """
        Fetch M&A (mergers & acquisitions) data.

        Args:
            query: Search query
            days_back: How far back to search

        Returns:
            MAData with aggregated metrics
        """
        pass

    @abstractmethod
    async def fetch_regulatory_data(
        self,
        query: str,
        days_back: int = 90
    ) -> RegulatoryData:
        """
        Fetch regulatory and policy data.

        Args:
            query: Search query
            days_back: How far back to search

        Returns:
            RegulatoryData with aggregated metrics
        """
        pass

    async def fetch_all(
        self,
        query: str,
        days_back: int = 90,
        include: List[str] = None
    ) -> ExternalDataResult:
        """
        Fetch all available data types.

        Args:
            query: Search query
            days_back: How far back to search
            include: List of data types to include ['citations', 'funding', 'ma', 'regulatory']
                    If None, fetches all.

        Returns:
            ExternalDataResult with all fetched data
        """
        include = include or ['citations', 'funding', 'ma', 'regulatory']
        result = ExternalDataResult()

        if 'citations' in include:
            try:
                result.citations = await self.fetch_citation_data(query)
            except Exception as e:
                logger.warning(f"{self.PROVIDER_NAME}: Citation fetch failed: {e}")
                result.errors.append(f"citations: {str(e)}")

        if 'funding' in include:
            try:
                result.funding = await self.fetch_funding_data(query, days_back)
            except Exception as e:
                logger.warning(f"{self.PROVIDER_NAME}: Funding fetch failed: {e}")
                result.errors.append(f"funding: {str(e)}")

        if 'ma' in include:
            try:
                result.ma_activity = await self.fetch_ma_data(query, days_back)
            except Exception as e:
                logger.warning(f"{self.PROVIDER_NAME}: M&A fetch failed: {e}")
                result.errors.append(f"ma: {str(e)}")

        if 'regulatory' in include:
            try:
                result.regulatory = await self.fetch_regulatory_data(query, days_back)
            except Exception as e:
                logger.warning(f"{self.PROVIDER_NAME}: Regulatory fetch failed: {e}")
                result.errors.append(f"regulatory: {str(e)}")

        return result

    def _check_rate_limit(self) -> bool:
        """Check if we should wait before making another request."""
        if self._rate_limit_remaining is not None and self._rate_limit_remaining <= 0:
            return False
        return True
