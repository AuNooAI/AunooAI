"""Dashboard cache service for saving and retrieving last generated dashboards."""

import logging
import json
from typing import Optional, Dict, Any
from datetime import datetime

from app.database import Database

logger = logging.getLogger(__name__)


class DashboardCacheService:
    """Service for caching and managing last generated dashboards."""

    def __init__(self, db: Database):
        self.db = db
        self.facade = db.facade

    @staticmethod
    def generate_cache_key(
        dashboard_type: str,
        date_range: str,
        topic: Optional[str] = None,
        persona: Optional[str] = None,
        profile_id: Optional[int] = None
    ) -> str:
        """Generate unique cache key for dashboard configuration.

        Format: dashboard_type:date_range:topic:persona:profile_id
        Example: news_feed:24h:AI:CEO:null
        """
        parts = [
            dashboard_type,
            date_range,
            topic or 'null',
            persona or 'null',
            str(profile_id or 'null')
        ]
        return ':'.join(parts)

    async def save_dashboard(
        self,
        dashboard_type: str,
        date_range: str,
        content: Dict[str, Any],
        topic: Optional[str] = None,
        persona: Optional[str] = None,
        profile_id: Optional[int] = None,
        metadata: Optional[Dict] = None
    ) -> str:
        """Save dashboard to cache (replaces existing if same key).

        Args:
            dashboard_type: Type of dashboard ('news_feed', 'six_articles', 'insights')
            date_range: Date range used ('24h', '7d', '30d', etc.)
            content: Full dashboard content as dictionary
            topic: Optional topic filter
            persona: Optional persona (CEO, CTO, etc.)
            profile_id: Optional organizational profile ID
            metadata: Optional metadata dict with article_count, model_used, etc.

        Returns:
            cache_key: Unique key for this cached dashboard
        """
        cache_key = self.generate_cache_key(
            dashboard_type, date_range, topic, persona, profile_id
        )

        # Extract summary text for exports
        summary_text = self._extract_summary_text(content, dashboard_type)

        # Extract metadata
        article_count = 0
        model_used = None
        generation_time = None

        if metadata:
            article_count = metadata.get('article_count', 0)
            model_used = metadata.get('model_used')
            generation_time = metadata.get('generation_time_seconds')

        # Store in database (upsert - replaces if exists)
        from starlette.concurrency import run_in_threadpool

        await run_in_threadpool(
            self.facade.upsert_dashboard_cache,
            cache_key=cache_key,
            dashboard_type=dashboard_type,
            date_range=date_range,
            topic=topic,
            profile_id=profile_id,
            persona=persona,
            content_json=json.dumps(content),
            summary_text=summary_text,
            article_count=article_count,
            model_used=model_used,
            generation_time_seconds=generation_time
        )

        logger.info(f"Dashboard cached: {cache_key} ({article_count} articles)")
        return cache_key

    async def get_dashboard(self, cache_key: str) -> Optional[Dict]:
        """Retrieve cached dashboard by key.

        Args:
            cache_key: Unique cache key

        Returns:
            Dashboard data dict or None if not found
        """
        from starlette.concurrency import run_in_threadpool

        cached = await run_in_threadpool(
            self.facade.get_dashboard_cache,
            cache_key
        )

        if cached:
            # Update accessed_at timestamp
            await run_in_threadpool(
                self.facade.update_dashboard_cache_access,
                cache_key
            )

        return cached

    async def get_latest_dashboard(
        self,
        dashboard_type: str,
        topic: Optional[str] = None
    ) -> Optional[Dict]:
        """Get the most recently generated dashboard of this type/topic.

        Args:
            dashboard_type: Type of dashboard
            topic: Optional topic filter

        Returns:
            Latest dashboard data or None
        """
        from starlette.concurrency import run_in_threadpool

        return await run_in_threadpool(
            self.facade.get_latest_dashboard_cache,
            dashboard_type,
            topic
        )

    async def list_cached_dashboards(self, limit: int = 20) -> list:
        """List all cached dashboards, most recently accessed first.

        Args:
            limit: Maximum number of results

        Returns:
            List of dashboard metadata dicts
        """
        from starlette.concurrency import run_in_threadpool

        return await run_in_threadpool(
            self.facade.list_dashboard_cache,
            limit
        )

    async def delete_dashboard(self, cache_key: str) -> bool:
        """Delete a cached dashboard.

        Args:
            cache_key: Unique cache key

        Returns:
            True if deleted, False if not found
        """
        from starlette.concurrency import run_in_threadpool

        return await run_in_threadpool(
            self.facade.delete_dashboard_cache,
            cache_key
        )

    def _extract_summary_text(self, content: Dict, dashboard_type: str) -> str:
        """Extract plain text summary from dashboard content for exports.

        Args:
            content: Dashboard content dictionary
            dashboard_type: Type of dashboard

        Returns:
            Plain text summary
        """
        try:
            if dashboard_type == 'news_feed':
                # Extract article titles and summaries
                items = content.get('items', [])
                lines = [f"News Feed - {len(items)} articles\n"]

                for item in items[:10]:  # First 10 articles
                    title = item.get('title', 'Untitled')
                    summary = item.get('summary', '')[:200]  # Truncate
                    lines.append(f"\n• {title}\n  {summary}\n")

                return '\n'.join(lines)

            elif dashboard_type == 'six_articles':
                # Extract detailed article analysis
                articles = content if isinstance(content, list) else content.get('articles', [])
                lines = [f"Six Articles Report - {len(articles)} articles\n"]

                for i, article in enumerate(articles, 1):
                    title = article.get('headline', 'Untitled')
                    summary = article.get('summary', '')[:200]
                    lines.append(f"\n{i}. {title}\n   {summary}\n")

                return '\n'.join(lines)

            elif dashboard_type == 'insights':
                # Extract insights
                insights = content.get('insights', [])
                lines = [f"Insights - {len(insights)} items\n"]

                for insight in insights[:10]:
                    title = insight.get('title', 'Untitled')
                    description = insight.get('description', '')[:200]
                    lines.append(f"\n• {title}\n  {description}\n")

                return '\n'.join(lines)

            else:
                # Generic fallback
                return json.dumps(content, indent=2)[:1000]

        except Exception as e:
            logger.error(f"Error extracting summary text: {e}")
            return "Summary unavailable"
