"""
Semantic Scholar Data Provider

Fetches citation and academic metrics from Semantic Scholar API.
Free API with rate limits (100 requests/5 minutes without key).

API Documentation: https://api.semanticscholar.org/
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

import httpx
from fastapi.concurrency import run_in_threadpool

from .base_provider import (
    BaseDataProvider,
    CitationData,
    FundingData,
    MAData,
    RegulatoryData
)

logger = logging.getLogger(__name__)

SEMANTIC_SCHOLAR_BASE_URL = "https://api.semanticscholar.org/graph/v1"


class SemanticScholarProvider(BaseDataProvider):
    """
    Semantic Scholar API provider for academic metrics.

    Provides:
    - Citation counts and velocity
    - Paper discovery
    - Author metrics
    - Influential citation tracking

    Rate limits:
    - Without API key: 100 requests per 5 minutes
    - With API key: Higher limits available
    """

    PROVIDER_NAME = "semantic_scholar"

    def __init__(self, api_key: Optional[str] = None):
        super().__init__(api_key or os.getenv("SEMANTIC_SCHOLAR_API_KEY"))
        self._request_count = 0
        self._request_window_start = datetime.now()

    def is_available(self) -> bool:
        """
        Semantic Scholar works without API key (with rate limits).
        Always available for basic queries.
        """
        return True

    def get_status(self) -> Dict[str, Any]:
        """Get provider status with rate info."""
        return {
            "provider": self.PROVIDER_NAME,
            "available": self.is_available(),
            "has_api_key": bool(self.api_key),
            "rate_limited": not bool(self.api_key),  # Rate limited without key
            "request_count_in_window": self._request_count
        }

    async def fetch_citation_data(
        self,
        query: str,
        limit: int = 100
    ) -> CitationData:
        """
        Fetch citation metrics from Semantic Scholar.

        Searches for papers matching query and aggregates citation data.
        """
        papers = await self._search_papers(query, limit)

        if not papers:
            return CitationData(
                source=self.PROVIDER_NAME,
                fetched_at=datetime.now()
            )

        # Aggregate citation metrics
        total_citations = sum(p.get('citationCount', 0) or 0 for p in papers)
        influential_citations = sum(p.get('influentialCitationCount', 0) or 0 for p in papers)

        # Calculate citation velocity (citations in last year / 12)
        citation_velocity = 0.0
        recent_papers = [p for p in papers if self._is_recent(p, days=365)]
        if recent_papers:
            recent_citations = sum(p.get('citationCount', 0) or 0 for p in recent_papers)
            citation_velocity = recent_citations / 12.0

        # Get top papers by citation count
        top_papers = sorted(papers, key=lambda p: p.get('citationCount', 0) or 0, reverse=True)[:5]
        top_papers_formatted = [
            {
                "title": p.get('title', 'Unknown'),
                "year": p.get('year'),
                "citations": p.get('citationCount', 0),
                "url": p.get('url'),
                "paperId": p.get('paperId')
            }
            for p in top_papers
        ]

        return CitationData(
            total_citations=total_citations,
            citation_velocity=citation_velocity,
            influential_citations=influential_citations,
            papers_found=len(papers),
            top_papers=top_papers_formatted,
            source=self.PROVIDER_NAME,
            fetched_at=datetime.now()
        )

    async def fetch_funding_data(
        self,
        query: str,
        days_back: int = 90
    ) -> FundingData:
        """
        Semantic Scholar doesn't provide funding data.
        Returns empty result - use GoogleSearchProvider for funding.
        """
        return FundingData(
            source=self.PROVIDER_NAME,
            fetched_at=datetime.now()
        )

    async def fetch_ma_data(
        self,
        query: str,
        days_back: int = 90
    ) -> MAData:
        """
        Semantic Scholar doesn't provide M&A data.
        Returns empty result - use GoogleSearchProvider for M&A.
        """
        return MAData(
            source=self.PROVIDER_NAME,
            fetched_at=datetime.now()
        )

    async def fetch_regulatory_data(
        self,
        query: str,
        days_back: int = 90
    ) -> RegulatoryData:
        """
        Semantic Scholar doesn't provide regulatory data.
        Returns empty result - use GoogleSearchProvider for regulatory.
        """
        return RegulatoryData(
            source=self.PROVIDER_NAME,
            fetched_at=datetime.now()
        )

    async def _search_papers(
        self,
        query: str,
        limit: int = 100,
        fields: List[str] = None
    ) -> List[Dict]:
        """
        Search for papers matching query.

        Args:
            query: Search query
            limit: Maximum papers to return
            fields: Fields to include in response

        Returns:
            List of paper dictionaries
        """
        await self._respect_rate_limit()

        fields = fields or [
            "paperId",
            "title",
            "year",
            "citationCount",
            "influentialCitationCount",
            "url",
            "publicationDate",
            "venue"
        ]

        url = f"{SEMANTIC_SCHOLAR_BASE_URL}/paper/search"
        params = {
            "query": query,
            "limit": min(limit, 100),  # API max is 100 per request
            "fields": ",".join(fields)
        }

        headers = {}
        if self.api_key:
            headers["x-api-key"] = self.api_key

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, params=params, headers=headers)

                if response.status_code == 429:
                    logger.warning("Semantic Scholar rate limit hit")
                    return []

                response.raise_for_status()
                data = response.json()

                papers = data.get('data', [])
                logger.info(f"Semantic Scholar: Found {len(papers)} papers for '{query}'")

                # If we need more papers and there's a next page
                total = data.get('total', 0)
                if limit > 100 and total > 100:
                    # Fetch additional pages
                    offset = 100
                    while offset < min(limit, total):
                        await self._respect_rate_limit()
                        params['offset'] = offset
                        response = await client.get(url, params=params, headers=headers)
                        if response.status_code == 200:
                            more_papers = response.json().get('data', [])
                            papers.extend(more_papers)
                            offset += 100
                        else:
                            break

                return papers

        except httpx.HTTPError as e:
            logger.error(f"Semantic Scholar API error: {e}")
            return []
        except Exception as e:
            logger.error(f"Semantic Scholar unexpected error: {e}")
            return []

    async def get_paper_citations(
        self,
        paper_id: str,
        limit: int = 100
    ) -> List[Dict]:
        """
        Get papers that cite a specific paper.

        Useful for tracking citation growth of specific publications.
        """
        await self._respect_rate_limit()

        url = f"{SEMANTIC_SCHOLAR_BASE_URL}/paper/{paper_id}/citations"
        params = {
            "limit": min(limit, 100),
            "fields": "paperId,title,year,citationCount,venue"
        }

        headers = {}
        if self.api_key:
            headers["x-api-key"] = self.api_key

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, params=params, headers=headers)
                response.raise_for_status()
                data = response.json()
                return data.get('data', [])

        except Exception as e:
            logger.error(f"Failed to get citations for {paper_id}: {e}")
            return []

    async def get_author_papers(
        self,
        author_id: str,
        limit: int = 100
    ) -> List[Dict]:
        """
        Get papers by a specific author.

        Useful for tracking specific researchers or institutions.
        """
        await self._respect_rate_limit()

        url = f"{SEMANTIC_SCHOLAR_BASE_URL}/author/{author_id}/papers"
        params = {
            "limit": min(limit, 100),
            "fields": "paperId,title,year,citationCount,venue,publicationDate"
        }

        headers = {}
        if self.api_key:
            headers["x-api-key"] = self.api_key

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, params=params, headers=headers)
                response.raise_for_status()
                data = response.json()
                return data.get('data', [])

        except Exception as e:
            logger.error(f"Failed to get author papers for {author_id}: {e}")
            return []

    async def _respect_rate_limit(self):
        """
        Ensure we don't exceed rate limits.

        Without API key: 100 requests per 5 minutes
        With API key: Check response headers for limits
        """
        self._request_count += 1

        # Reset counter every 5 minutes
        now = datetime.now()
        if (now - self._request_window_start).total_seconds() > 300:
            self._request_count = 1
            self._request_window_start = now
            return

        # If approaching limit, wait
        if self._request_count >= 95 and not self.api_key:
            wait_time = 300 - (now - self._request_window_start).total_seconds()
            if wait_time > 0:
                logger.info(f"Semantic Scholar rate limit approaching, waiting {wait_time:.0f}s")
                await asyncio.sleep(min(wait_time, 60))  # Cap at 60s
                self._request_count = 0
                self._request_window_start = datetime.now()

    def _is_recent(self, paper: Dict, days: int = 365) -> bool:
        """Check if paper was published within last N days."""
        pub_date = paper.get('publicationDate')
        if not pub_date:
            # Fall back to year
            year = paper.get('year')
            if year:
                return year >= datetime.now().year - 1
            return False

        try:
            if isinstance(pub_date, str):
                # Handle various date formats
                for fmt in ["%Y-%m-%d", "%Y-%m", "%Y"]:
                    try:
                        date = datetime.strptime(pub_date[:len(fmt.replace('%', '').replace('-', ''))], fmt)
                        return (datetime.now() - date).days <= days
                    except:
                        continue
            return False
        except:
            return False


# Singleton instance
_semantic_scholar_provider: Optional[SemanticScholarProvider] = None


def get_semantic_scholar_provider() -> SemanticScholarProvider:
    """Get Semantic Scholar provider singleton."""
    global _semantic_scholar_provider
    if _semantic_scholar_provider is None:
        _semantic_scholar_provider = SemanticScholarProvider()
    return _semantic_scholar_provider
