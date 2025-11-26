"""
Smart Search Router
Intelligently routes queries to vector database, external APIs, or both.

Routes queries based on:
1. Recency signals ("today", "breaking", "just now")
2. Explicit user requests ("search the web", "from database")
3. Comparative queries ("compare", "vs", "difference")
4. Topic coverage in internal database
"""

import logging
import re
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from enum import Enum

from app.database import get_database_instance

logger = logging.getLogger(__name__)


class SearchSource(str, Enum):
    """Available search sources."""
    VECTOR_DB = "vector_db"
    EXTERNAL = "external"
    HYBRID = "hybrid"


class SearchRouter:
    """Routes search queries to appropriate sources based on query analysis."""

    def __init__(self):
        self.db = get_database_instance()

        # Recency patterns - suggest external search for very recent events
        self.recency_patterns = [
            r"\btoday\b",
            r"\bjust\s+now\b",
            r"\bbreaking\b",
            r"\bhappening\s+now\b",
            r"\blast\s+hour\b",
            r"\bminutes?\s+ago\b",
            r"\bthis\s+morning\b",
            r"\bthis\s+afternoon\b",
            r"\bright\s+now\b",
            r"\bcurrent(ly)?\b",
            r"\blatest\b",
            r"\bjust\s+announced\b",
            r"\bjust\s+released\b"
        ]

        # Explicit external search patterns
        self.external_explicit_patterns = [
            r"\bsearch\s+the\s+web\b",
            r"\bnews\s+api\b",
            r"\bexternal\s+sources?\b",
            r"\bgoogle\s+for\b",
            r"\bfind\s+online\b",
            r"\blatest\s+news\b",
            r"\breal[\s-]?time\b",
            r"\blive\s+news\b",
            r"\bfresh\s+news\b"
        ]

        # Explicit internal database patterns
        self.internal_explicit_patterns = [
            r"\bour\s+database\b",
            r"\bour\s+articles?\b",
            r"\bin\s+the\s+database\b",
            r"\bfrom\s+database\b",
            r"\bstored\s+articles?\b",
            r"\bexisting\s+data\b",
            r"\bwe\s+have\b",
            r"\bour\s+records\b",
            r"\binternal\s+data\b"
        ]

        # Comparative/hybrid patterns
        self.comparative_patterns = [
            r"\bcompare\b",
            r"\bvs\.?\b",
            r"\bversus\b",
            r"\bdifference\s+between\b",
            r"\bcontrast\b",
            r"\bboth\s+(?:internal|external)\b",
            r"\ball\s+sources\b",
            r"\beverywhere\b",
            r"\bcomprehensive\b"
        ]

    def analyze_query(self, query: str, topic: Optional[str] = None) -> Dict:
        """
        Analyze a query to determine optimal search strategy.

        Args:
            query: The user's search query
            topic: Optional topic context

        Returns:
            Dict with source recommendation and reasoning
        """
        query_lower = query.lower()
        analysis = {
            "query": query,
            "topic": topic,
            "source": SearchSource.VECTOR_DB,
            "confidence": 0.5,
            "reasoning": [],
            "signals": {}
        }

        # Check for recency signals
        recency_score = self._check_patterns(query_lower, self.recency_patterns)
        if recency_score > 0:
            analysis["signals"]["recency"] = recency_score
            analysis["reasoning"].append(f"Recency signal detected (score: {recency_score:.2f})")

        # Check for explicit external request
        external_score = self._check_patterns(query_lower, self.external_explicit_patterns)
        if external_score > 0:
            analysis["signals"]["external_explicit"] = external_score
            analysis["reasoning"].append("Explicit external search requested")

        # Check for explicit internal request
        internal_score = self._check_patterns(query_lower, self.internal_explicit_patterns)
        if internal_score > 0:
            analysis["signals"]["internal_explicit"] = internal_score
            analysis["reasoning"].append("Explicit database search requested")

        # Check for comparative/hybrid needs
        comparative_score = self._check_patterns(query_lower, self.comparative_patterns)
        if comparative_score > 0:
            analysis["signals"]["comparative"] = comparative_score
            analysis["reasoning"].append("Comparative analysis suggested")

        # Check topic coverage in database
        if topic:
            topic_coverage = self._check_topic_coverage(topic)
            analysis["signals"]["topic_coverage"] = topic_coverage
            if topic_coverage > 0.7:
                analysis["reasoning"].append(f"Good topic coverage in database ({topic_coverage:.0%})")
            elif topic_coverage < 0.3:
                analysis["reasoning"].append(f"Limited topic coverage ({topic_coverage:.0%}), consider external")

        # Determine final recommendation
        source, confidence = self._determine_source(analysis["signals"])
        analysis["source"] = source
        analysis["confidence"] = confidence

        # Add final reasoning
        analysis["reasoning"].append(f"Recommended source: {source.value} (confidence: {confidence:.0%})")

        return analysis

    def _check_patterns(self, text: str, patterns: List[str]) -> float:
        """
        Check how many patterns match and return a normalized score.

        Returns:
            Score between 0.0 and 1.0 based on pattern matches
        """
        if not patterns:
            return 0.0

        matches = 0
        for pattern in patterns:
            try:
                if re.search(pattern, text, re.IGNORECASE):
                    matches += 1
            except re.error:
                # Treat as literal string if not valid regex
                if pattern.lower() in text:
                    matches += 1

        return min(1.0, matches / len(patterns) * 2)  # Scale up, cap at 1.0

    def _check_topic_coverage(self, topic: str) -> float:
        """
        Check how well our database covers this topic.

        Returns:
            Coverage score between 0.0 and 1.0
        """
        try:
            # Get article count for topic using facade
            articles, total = self.db.facade.search_articles(topic=topic, page=1, per_page=1)

            if total == 0:
                return 0.0
            elif total < 50:
                return 0.3
            elif total < 200:
                return 0.6
            elif total < 500:
                return 0.8
            else:
                return 0.95
        except Exception as e:
            logger.warning(f"Error checking topic coverage: {e}")
            return 0.5  # Default to moderate coverage on error

    def _determine_source(self, signals: Dict) -> Tuple[SearchSource, float]:
        """
        Determine the best source based on accumulated signals.

        Returns:
            Tuple of (SearchSource, confidence_score)
        """
        # Explicit requests override everything
        if signals.get("internal_explicit", 0) > 0.3:
            return SearchSource.VECTOR_DB, 0.95

        if signals.get("external_explicit", 0) > 0.3:
            return SearchSource.EXTERNAL, 0.95

        # Comparative queries suggest hybrid
        if signals.get("comparative", 0) > 0.2:
            return SearchSource.HYBRID, 0.85

        # Very recent queries suggest external
        recency = signals.get("recency", 0)
        if recency > 0.5:
            return SearchSource.EXTERNAL, 0.8
        elif recency > 0.3:
            return SearchSource.HYBRID, 0.7

        # Good topic coverage suggests internal
        topic_coverage = signals.get("topic_coverage", 0.5)
        if topic_coverage > 0.7:
            return SearchSource.VECTOR_DB, 0.85
        elif topic_coverage < 0.3:
            return SearchSource.HYBRID, 0.65

        # Default to vector database with moderate confidence
        return SearchSource.VECTOR_DB, 0.6

    async def execute_routed_search(
        self,
        query: str,
        topic: str,
        limit: int = 50,
        force_source: Optional[SearchSource] = None,
        tools_service=None
    ) -> Dict:
        """
        Execute a search with automatic or forced routing.

        Args:
            query: Search query
            topic: Topic to search within
            limit: Maximum results
            force_source: Force a specific source (overrides analysis)
            tools_service: AuspexToolsService instance for executing searches

        Returns:
            Dict with search results and routing metadata
        """
        import asyncio

        # Analyze query if not forcing source
        if force_source:
            source = force_source
            analysis = {
                "source": source,
                "reasoning": ["Forced source selection"],
                "confidence": 1.0
            }
        else:
            analysis = self.analyze_query(query, topic)
            source = analysis["source"]

        results = {
            "query": query,
            "topic": topic,
            "source_used": source.value,
            "routing_analysis": analysis,
            "articles": [],
            "total_count": 0,
            "metadata": {}
        }

        # Need tools service to execute searches
        if tools_service is None:
            from app.services.auspex_tools import get_auspex_tools_service
            tools_service = get_auspex_tools_service()

        try:
            if source == SearchSource.VECTOR_DB:
                db_results = await tools_service.enhanced_database_search(
                    query=query,
                    topic=topic,
                    limit=limit
                )
                results["articles"] = db_results.get("articles", [])
                results["total_count"] = db_results.get("total_articles", 0)
                results["metadata"]["search_method"] = db_results.get("search_method", "vector")

            elif source == SearchSource.EXTERNAL:
                # Try Google PSE first, fall back to TheNewsAPI
                ext_results = await tools_service.google_web_search(
                    query=query,
                    max_results=limit
                )

                # If Google search failed or returned no results, try TheNewsAPI
                if ext_results.get("error") or ext_results.get("total_results", 0) == 0:
                    logger.info("Google PSE unavailable or returned no results, falling back to TheNewsAPI")
                    ext_results = await tools_service.search_news(
                        query=query,
                        max_results=limit,
                        days_back=7
                    )
                    results["metadata"]["search_method"] = "thenewsapi"
                else:
                    results["metadata"]["search_method"] = "google_pse"

                results["articles"] = ext_results.get("articles", [])
                results["total_count"] = ext_results.get("total_results", 0)

            elif source == SearchSource.HYBRID:
                # Execute both searches in parallel - use Google PSE for external
                db_task = tools_service.enhanced_database_search(
                    query=query,
                    topic=topic,
                    limit=limit // 2
                )
                ext_task = tools_service.google_web_search(
                    query=query,
                    max_results=limit // 2
                )

                db_results, ext_results = await asyncio.gather(
                    db_task, ext_task,
                    return_exceptions=True
                )

                # Combine results
                combined_articles = []

                # Process database results
                if not isinstance(db_results, Exception):
                    db_articles = db_results.get("articles", [])
                    logger.info(f"Hybrid: Database search returned {len(db_articles)} articles")
                    for article in db_articles:
                        article["source_type"] = "database"
                        combined_articles.append(article)
                else:
                    logger.warning(f"Database search failed in hybrid: {db_results}")

                # Process external results - check for errors and fallback to TheNewsAPI
                ext_articles = []
                if isinstance(ext_results, Exception):
                    logger.warning(f"External search exception in hybrid: {ext_results}")
                elif ext_results.get("error") or ext_results.get("total_results", 0) == 0:
                    # Google PSE failed or returned no results, try TheNewsAPI as fallback
                    logger.info(f"Hybrid: Google PSE unavailable or empty (error: {ext_results.get('error')}), falling back to TheNewsAPI")
                    try:
                        news_results = await tools_service.search_news(
                            query=query,
                            max_results=limit // 2,
                            days_back=7
                        )
                        ext_articles = news_results.get("articles", [])
                        logger.info(f"Hybrid: TheNewsAPI fallback returned {len(ext_articles)} articles")
                    except Exception as news_err:
                        logger.warning(f"Hybrid: TheNewsAPI fallback also failed: {news_err}")
                else:
                    ext_articles = ext_results.get("articles", [])
                    logger.info(f"Hybrid: Google PSE returned {len(ext_articles)} articles")

                for article in ext_articles:
                    article["source_type"] = "external"
                    combined_articles.append(article)

                # Deduplicate by URL/URI
                seen_urls = set()
                unique_articles = []
                for article in combined_articles:
                    url = article.get("url") or article.get("uri", "")
                    if url:
                        if url not in seen_urls:
                            seen_urls.add(url)
                            unique_articles.append(article)
                    else:
                        # No URL, include based on title dedup
                        title = article.get("title", "").lower().strip()
                        if title and title not in seen_urls:
                            seen_urls.add(title)
                            unique_articles.append(article)

                results["articles"] = unique_articles[:limit]
                results["total_count"] = len(unique_articles)
                results["metadata"]["search_method"] = "hybrid"
                results["metadata"]["db_count"] = len([a for a in unique_articles if a.get("source_type") == "database"])
                results["metadata"]["external_count"] = len([a for a in unique_articles if a.get("source_type") == "external"])
                logger.info(f"Hybrid search complete: {results['metadata']['db_count']} internal + {results['metadata']['external_count']} external = {results['total_count']} total")

        except Exception as e:
            logger.error(f"Routed search failed: {e}")
            results["error"] = str(e)

        return results

    def get_routing_explanation(self, analysis: Dict) -> str:
        """
        Generate a human-readable explanation of the routing decision.

        Args:
            analysis: Result from analyze_query()

        Returns:
            Explanation string
        """
        source = analysis.get("source", SearchSource.VECTOR_DB)
        confidence = analysis.get("confidence", 0.5)
        reasons = analysis.get("reasoning", [])

        source_names = {
            SearchSource.VECTOR_DB: "internal database",
            SearchSource.EXTERNAL: "external news APIs",
            SearchSource.HYBRID: "both internal database and external APIs"
        }

        explanation = f"Searching {source_names.get(source, 'database')} "
        explanation += f"(confidence: {confidence:.0%}). "

        if reasons:
            explanation += "Reasons: " + "; ".join(reasons[:3])

        return explanation


# Singleton instance
_router_instance: Optional[SearchRouter] = None


def get_search_router() -> SearchRouter:
    """Get the global search router instance."""
    global _router_instance
    if _router_instance is None:
        _router_instance = SearchRouter()
    return _router_instance
