"""
Google Programmable Search Data Provider

Fetches financial news, M&A, funding, and regulatory data via Google Custom Search.
Requires GOOGLE_CSE_API_KEY and GOOGLE_CSE_ID environment variables.

Free tier: 100 queries/day
Paid: $5 per 1000 queries
"""

import asyncio
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple

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

GOOGLE_SEARCH_URL = "https://www.googleapis.com/customsearch/v1"


class GoogleSearchProvider(BaseDataProvider):
    """
    Google Programmable Search API provider.

    Uses targeted search queries to find:
    - M&A announcements
    - Funding rounds
    - Regulatory developments

    This is an approximation - not as accurate as Crunchbase but available
    without paid subscription.
    """

    PROVIDER_NAME = "google_search"

    # Query templates for different data types
    FUNDING_QUERY_TEMPLATE = '"{topic}" AND ("raises" OR "funding" OR "series" OR "investment" OR "million" OR "venture capital")'
    MA_QUERY_TEMPLATE = '"{topic}" AND ("acquires" OR "acquisition" OR "merger" OR "acquired by" OR "buys")'
    REGULATORY_QUERY_TEMPLATE = '"{topic}" AND ("regulation" OR "regulatory" OR "policy" OR "legislation" OR "compliance" OR "EU AI Act" OR "FTC")'

    def __init__(
        self,
        api_key: Optional[str] = None,
        search_engine_id: Optional[str] = None
    ):
        super().__init__(api_key or os.getenv("GOOGLE_CSE_API_KEY"))
        self.search_engine_id = search_engine_id or os.getenv("GOOGLE_CSE_ID")
        self._daily_query_count = 0
        self._query_reset_date = datetime.now().date()

    def is_available(self) -> bool:
        """
        Check if Google Search provider is properly configured.
        Requires both GOOGLE_CSE_API_KEY and GOOGLE_CSE_ID.
        """
        return bool(self.api_key) and bool(self.search_engine_id)

    def get_status(self) -> Dict[str, Any]:
        """Get provider status with Google-specific info."""
        return {
            "provider": self.PROVIDER_NAME,
            "available": self.is_available(),
            "has_api_key": bool(self.api_key),
            "has_search_engine_id": bool(self.search_engine_id),
            "daily_query_count": self._daily_query_count
        }

    async def fetch_citation_data(
        self,
        query: str,
        limit: int = 100
    ) -> CitationData:
        """
        Google Search doesn't provide citation data.
        Use SemanticScholarProvider for citations.
        """
        return CitationData(
            source=self.PROVIDER_NAME,
            fetched_at=datetime.now()
        )

    async def fetch_funding_data(
        self,
        query: str,
        days_back: int = 90
    ) -> FundingData:
        """
        Search for funding announcements.

        Looks for news about funding rounds, investments, etc.
        """
        if not self._check_api_configured():
            return FundingData(source=self.PROVIDER_NAME)

        search_query = self.FUNDING_QUERY_TEMPLATE.format(topic=query)
        results = await self._search(search_query, limit=20, days_back=days_back)

        if not results:
            return FundingData(source=self.PROVIDER_NAME, fetched_at=datetime.now())

        # Parse funding information from search results
        deals = []
        total_funding = 0
        largest_deal = 0

        for result in results:
            title = result.get('title', '')
            snippet = result.get('snippet', '')

            # Try to extract funding amount
            amount = self._extract_funding_amount(title + " " + snippet)

            if amount:
                deals.append({
                    "title": title,
                    "url": result.get('link'),
                    "amount_usd": amount,
                    "source": "Google Search"
                })
                total_funding += amount
                largest_deal = max(largest_deal, amount)

        # Determine trend based on result count
        funding_trend = "stable"
        if len(deals) >= 5:
            funding_trend = "increasing"
        elif len(deals) <= 1:
            funding_trend = "decreasing"

        return FundingData(
            total_funding_usd=total_funding,
            deal_count=len(deals),
            largest_deal_usd=largest_deal,
            recent_deals=deals[:10],
            funding_trend=funding_trend,
            source=self.PROVIDER_NAME,
            fetched_at=datetime.now()
        )

    async def fetch_ma_data(
        self,
        query: str,
        days_back: int = 90
    ) -> MAData:
        """
        Search for M&A announcements.

        Looks for news about acquisitions, mergers, etc.
        """
        if not self._check_api_configured():
            return MAData(source=self.PROVIDER_NAME)

        search_query = self.MA_QUERY_TEMPLATE.format(topic=query)
        results = await self._search(search_query, limit=20, days_back=days_back)

        if not results:
            return MAData(source=self.PROVIDER_NAME, fetched_at=datetime.now())

        # Parse M&A information
        deals = []
        total_value = 0
        acquirers = set()

        for result in results:
            title = result.get('title', '')
            snippet = result.get('snippet', '')

            # Try to extract deal value
            value = self._extract_funding_amount(title + " " + snippet)

            # Try to extract acquirer
            acquirer = self._extract_acquirer(title)
            if acquirer:
                acquirers.add(acquirer)

            deals.append({
                "title": title,
                "url": result.get('link'),
                "value_usd": value,
                "acquirer": acquirer,
                "source": "Google Search"
            })

            if value:
                total_value += value

        # Determine consolidation trend
        consolidation_trend = "stable"
        if len(deals) >= 5:
            consolidation_trend = "accelerating"
        elif len(deals) <= 1:
            consolidation_trend = "slowing"

        return MAData(
            deal_count=len(deals),
            total_value_usd=total_value,
            recent_deals=deals[:10],
            consolidation_trend=consolidation_trend,
            key_acquirers=list(acquirers)[:5],
            source=self.PROVIDER_NAME,
            fetched_at=datetime.now()
        )

    async def fetch_regulatory_data(
        self,
        query: str,
        days_back: int = 90
    ) -> RegulatoryData:
        """
        Search for regulatory developments.

        Looks for news about regulations, policy, compliance.
        """
        if not self._check_api_configured():
            return RegulatoryData(source=self.PROVIDER_NAME)

        search_query = self.REGULATORY_QUERY_TEMPLATE.format(topic=query)
        results = await self._search(search_query, limit=20, days_back=days_back)

        if not results:
            return RegulatoryData(source=self.PROVIDER_NAME, fetched_at=datetime.now())

        # Parse regulatory information
        events = []
        jurisdictions = set()
        regulations = set()

        # Common jurisdiction keywords
        jurisdiction_keywords = {
            "EU": ["EU", "European", "Brussels", "GDPR"],
            "US": ["US", "United States", "FTC", "SEC", "Congress", "Biden", "White House"],
            "UK": ["UK", "Britain", "British", "London"],
            "China": ["China", "Chinese", "Beijing"],
            "Global": ["UN", "G20", "OECD", "global"]
        }

        # Common regulation keywords
        regulation_keywords = [
            "AI Act", "GDPR", "DSA", "DMA", "Copyright",
            "FTC", "Antitrust", "Data Privacy", "CCPA"
        ]

        for result in results:
            title = result.get('title', '')
            snippet = result.get('snippet', '')
            full_text = title + " " + snippet

            # Extract jurisdictions
            for jur, keywords in jurisdiction_keywords.items():
                if any(kw.lower() in full_text.lower() for kw in keywords):
                    jurisdictions.add(jur)

            # Extract regulations
            for reg in regulation_keywords:
                if reg.lower() in full_text.lower():
                    regulations.add(reg)

            events.append({
                "title": title,
                "url": result.get('link'),
                "source": "Google Search"
            })

        # Determine regulatory trend
        regulatory_trend = "stable"
        if len(events) >= 8:
            regulatory_trend = "increasing"
        elif len(events) <= 2:
            regulatory_trend = "decreasing"

        return RegulatoryData(
            event_count=len(events),
            recent_events=events[:10],
            jurisdictions=list(jurisdictions),
            regulatory_trend=regulatory_trend,
            key_regulations=list(regulations),
            source=self.PROVIDER_NAME,
            fetched_at=datetime.now()
        )

    async def _search(
        self,
        query: str,
        limit: int = 10,
        days_back: int = 90
    ) -> List[Dict]:
        """
        Execute Google Custom Search.

        Args:
            query: Search query
            limit: Max results (up to 100)
            days_back: Filter to recent results

        Returns:
            List of search result dictionaries
        """
        if not self._check_api_configured():
            return []

        if not self._check_daily_limit():
            logger.warning("Google Search daily limit reached")
            return []

        # Calculate date restriction
        date_restrict = f"d{days_back}"

        all_results = []
        start_index = 1

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                while len(all_results) < limit:
                    params = {
                        "key": self.api_key,
                        "cx": self.search_engine_id,
                        "q": query,
                        "start": start_index,
                        "num": min(10, limit - len(all_results)),  # Max 10 per request
                        "dateRestrict": date_restrict
                    }

                    response = await client.get(GOOGLE_SEARCH_URL, params=params)
                    self._daily_query_count += 1

                    if response.status_code == 429:
                        logger.warning("Google Search quota exceeded")
                        break

                    if response.status_code != 200:
                        logger.error(f"Google Search error: {response.status_code}")
                        break

                    data = response.json()
                    items = data.get('items', [])

                    if not items:
                        break

                    all_results.extend(items)
                    start_index += len(items)

                    # Avoid hammering the API
                    await asyncio.sleep(0.5)

            logger.info(f"Google Search: Found {len(all_results)} results for query")
            return all_results

        except Exception as e:
            logger.error(f"Google Search error: {e}")
            return []

    def _extract_funding_amount(self, text: str) -> Optional[int]:
        """
        Extract funding amount from text.

        Handles formats like:
        - "$50 million"
        - "$50M"
        - "50 million dollars"
        - "$1.5 billion"
        """
        # Patterns for different formats
        patterns = [
            r'\$(\d+(?:\.\d+)?)\s*(million|m|billion|b)',
            r'(\d+(?:\.\d+)?)\s*(million|m|billion|b)\s*(?:dollars|usd|\$)',
            r'raised\s*\$(\d+(?:\.\d+)?)\s*(million|m|billion|b)',
            r'(\d+(?:\.\d+)?)\s*(million|m|billion|b)\s*(?:deal|round|funding)',
        ]

        text_lower = text.lower()

        for pattern in patterns:
            match = re.search(pattern, text_lower, re.IGNORECASE)
            if match:
                amount = float(match.group(1))
                unit = match.group(2).lower()

                if unit in ['billion', 'b']:
                    return int(amount * 1_000_000_000)
                elif unit in ['million', 'm']:
                    return int(amount * 1_000_000)

        return None

    def _extract_acquirer(self, title: str) -> Optional[str]:
        """
        Try to extract acquirer name from title.

        Looks for patterns like "X acquires Y" or "X to buy Y"
        """
        patterns = [
            r'^(\w+(?:\s+\w+)?)\s+(?:acquires|buys|purchases|to acquire|to buy)',
            r'^(\w+(?:\s+\w+)?)\s+announces?\s+acquisition',
        ]

        for pattern in patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        return None

    def _check_api_configured(self) -> bool:
        """Check if API credentials are configured."""
        if not self.api_key or not self.search_engine_id:
            logger.warning("Google Search API not configured (missing GOOGLE_CSE_API_KEY or GOOGLE_CSE_ID)")
            return False
        return True

    def _check_daily_limit(self) -> bool:
        """Check daily query limit (100 free queries/day)."""
        today = datetime.now().date()

        # Reset counter if it's a new day
        if today > self._query_reset_date:
            self._daily_query_count = 0
            self._query_reset_date = today

        # Free tier limit
        if self._daily_query_count >= 95:  # Leave buffer
            return False

        return True


# Singleton instance
_google_search_provider: Optional[GoogleSearchProvider] = None


def get_google_search_provider() -> GoogleSearchProvider:
    """Get Google Search provider singleton."""
    global _google_search_provider
    if _google_search_provider is None:
        _google_search_provider = GoogleSearchProvider()
    return _google_search_provider
