"""
Strategic Intelligence Oracle Service (Option C)
Full 24-hour news scan with clustering, verification, and intelligence brief generation.

Uses ArticleIntelligenceAnalyzer (Option A) as a building block for deep event analysis.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Dict, List, Optional, AsyncGenerator, Any, Tuple
from enum import Enum
from collections import defaultdict

import litellm
import numpy as np

from app.database import get_database_instance
from app.services.auspex_tools import get_auspex_tools_service
from app.services.search_router import get_search_router, SearchSource
from app.services.article_intelligence_analyzer import (
    ArticleIntelligenceAnalyzer,
    ArticleAnalysis,
    AnalyzerConfig,
    get_article_intelligence_analyzer
)
from app.services.tool_loader import get_tool_loader
from app.models.media_bias import MediaBias
from app.vector_store import search_articles as vector_search_articles

logger = logging.getLogger(__name__)


class SIOStage(str, Enum):
    """Strategic Intelligence Oracle workflow stages."""
    DISCOVERY = "discovery"
    TRIAGE = "triage"
    DEEP_ANALYSIS = "deep_analysis"
    SYNTHESIS = "synthesis"
    COMPLETE = "complete"
    ERROR = "error"


@dataclass
class EventCluster:
    """Represents a cluster of related articles about an event."""
    cluster_id: str
    title: str
    summary: str = ""
    category: str = ""
    articles: List[Dict] = field(default_factory=list)
    article_indices: List[int] = field(default_factory=list)
    representative_article: Optional[Dict] = None
    source_diversity_score: float = 0.0
    preliminary_importance: str = "medium"
    keywords: List[str] = field(default_factory=list)

    # Set after deep analysis
    analysis: Optional[ArticleAnalysis] = None
    final_importance_score: float = 0.0

    def to_dict(self) -> Dict:
        return {
            "cluster_id": self.cluster_id,
            "title": self.title,
            "summary": self.summary,
            "category": self.category,
            "article_count": len(self.articles),
            "source_diversity_score": self.source_diversity_score,
            "preliminary_importance": self.preliminary_importance,
            "keywords": self.keywords,
            "final_importance_score": self.final_importance_score,
            "analysis": self.analysis.to_dict() if self.analysis else None
        }


@dataclass
class SIOState:
    """Tracks state across SIO workflow stages."""
    scan_id: str
    topic: Optional[str] = None
    hours_back: int = 24
    created_at: datetime = field(default_factory=datetime.now)

    # Discovery outputs
    raw_articles: List[Dict] = field(default_factory=list)
    collection_stats: Dict = field(default_factory=dict)

    # Triage outputs
    screened_articles: List[Dict] = field(default_factory=list)
    event_clusters: List[EventCluster] = field(default_factory=list)

    # Deep analysis outputs
    analyzed_events: List[EventCluster] = field(default_factory=list)

    # Synthesis outputs
    intelligence_brief: str = ""
    audit_trail: Dict = field(default_factory=dict)

    # Progress tracking
    current_stage: SIOStage = SIOStage.DISCOVERY
    stage_progress: Dict[str, float] = field(default_factory=lambda: {
        "discovery": 0.0,
        "triage": 0.0,
        "deep_analysis": 0.0,
        "synthesis": 0.0
    })
    errors: List[str] = field(default_factory=list)

    def update_progress(self, stage: str, progress: float):
        self.stage_progress[stage] = min(1.0, max(0.0, progress))
        self.current_stage = SIOStage(stage)

    def overall_progress(self) -> float:
        weights = {
            "discovery": 0.2,
            "triage": 0.15,
            "deep_analysis": 0.45,
            "synthesis": 0.2
        }
        return sum(self.stage_progress.get(s, 0) * w for s, w in weights.items())

    def to_dict(self) -> Dict:
        return {
            "scan_id": self.scan_id,
            "topic": self.topic,
            "hours_back": self.hours_back,
            "created_at": self.created_at.isoformat(),
            "current_stage": self.current_stage.value,
            "stage_progress": self.stage_progress,
            "overall_progress": self.overall_progress(),
            "collection_stats": self.collection_stats,
            "clusters_found": len(self.event_clusters),
            "events_analyzed": len(self.analyzed_events),
            "errors": self.errors
        }


@dataclass
class SIOConfig:
    """Configuration for Strategic Intelligence Oracle."""
    # Time window
    hours_back: int = 24

    # Article limits
    max_discovery_articles: int = 500
    min_discovery_articles: int = 50
    max_events_to_analyze: int = 30
    min_articles_per_cluster: int = 1  # Allow single-article events

    # Quality thresholds
    credibility_threshold: int = 60
    min_factual_reporting: str = "Mostly Factual"
    confidence_threshold: float = 0.7

    # Clustering
    similarity_threshold: float = 0.75
    max_clusters: int = 50

    # Model settings
    discovery_model: str = "gpt-4.1-mini"
    triage_model: str = "gpt-4.1-mini"
    analysis_model: str = "gpt-4.1"
    synthesis_model: str = "gpt-4.1"

    # Timeouts (seconds)
    discovery_timeout: int = 120
    triage_timeout: int = 60
    analysis_timeout: int = 300
    synthesis_timeout: int = 120

    # Parallelism
    max_concurrent_analyses: int = 5

    @classmethod
    def from_workflow(cls, workflow_config: Dict) -> "SIOConfig":
        """Create config from workflow definition."""
        config = cls()

        if "config" in workflow_config:
            cfg = workflow_config["config"]
            config.hours_back = cfg.get("hours_back", config.hours_back)
            config.max_discovery_articles = cfg.get("max_discovery_articles", config.max_discovery_articles)
            config.max_events_to_analyze = cfg.get("max_events_to_analyze", config.max_events_to_analyze)
            config.credibility_threshold = cfg.get("credibility_threshold", config.credibility_threshold)

        if "clustering" in workflow_config:
            clust = workflow_config["clustering"]
            config.similarity_threshold = clust.get("similarity_threshold", config.similarity_threshold)
            config.max_clusters = clust.get("max_clusters", config.max_clusters)

        return config


class StrategicIntelligenceService:
    """
    Strategic Intelligence Oracle - Full 24-hour news analysis.

    Workflow:
    1. DISCOVERY: Gather 300-500 articles from past 24 hours
    2. TRIAGE: Screen for credibility, cluster into events
    3. DEEP ANALYSIS: Analyze top 30 events using ArticleIntelligenceAnalyzer
    4. SYNTHESIS: Generate intelligence brief
    """

    def __init__(self):
        self.db = get_database_instance()
        self.tools = get_auspex_tools_service()
        self.search_router = get_search_router()
        self.tool_loader = get_tool_loader()
        self.media_bias = MediaBias(self.db)
        self.analyzer = get_article_intelligence_analyzer()

    def _load_agent_prompt(self, agent_name: str) -> Optional[str]:
        """Load agent prompt from tool loader."""
        agent = self.tool_loader.get_agent(agent_name)
        if agent:
            return agent.content
        return None

    async def run_scan(
        self,
        topic: Optional[str] = None,
        hours_back: int = 24,
        max_events: int = 30,
        config: Optional[SIOConfig] = None
    ) -> AsyncGenerator[Dict, None]:
        """
        Run a full Strategic Intelligence Oracle scan.

        Args:
            topic: Optional topic filter (None = all topics)
            hours_back: Hours of news to analyze (default 24)
            max_events: Maximum events to deep-analyze (default 30)
            config: Optional configuration override

        Yields:
            Progress updates and final intelligence brief
        """
        # Load workflow config if available
        if config is None:
            workflow = self.tool_loader.get_workflow("strategic_intelligence_oracle")
            if workflow:
                config = SIOConfig.from_workflow(workflow.to_dict())
            else:
                config = SIOConfig()

        # Override with parameters
        config.hours_back = hours_back
        config.max_events_to_analyze = max_events

        state = SIOState(
            scan_id=str(uuid.uuid4()),
            topic=topic,
            hours_back=hours_back
        )

        state.audit_trail = {
            "scan_id": state.scan_id,
            "started_at": state.created_at.isoformat(),
            "config": {
                "topic": topic,
                "hours_back": hours_back,
                "max_events": max_events,
                "credibility_threshold": config.credibility_threshold
            },
            "models_used": [],
            "stages": []
        }

        try:
            # Stage 1: Discovery
            yield {"stage": "discovery", "status": "started", "progress": 0.0, "scan_id": state.scan_id}
            await asyncio.wait_for(
                self._run_discovery(state, config),
                timeout=config.discovery_timeout
            )
            state.update_progress("discovery", 1.0)
            state.audit_trail["stages"].append({
                "name": "discovery",
                "completed_at": datetime.now().isoformat(),
                "articles_collected": len(state.raw_articles)
            })
            yield {
                "stage": "discovery",
                "status": "completed",
                "progress": 1.0,
                "articles_collected": len(state.raw_articles),
                "stats": state.collection_stats
            }

            # Stage 2: Triage
            yield {"stage": "triage", "status": "started", "progress": 0.0}
            await asyncio.wait_for(
                self._run_triage(state, config),
                timeout=config.triage_timeout
            )
            state.update_progress("triage", 1.0)
            state.audit_trail["stages"].append({
                "name": "triage",
                "completed_at": datetime.now().isoformat(),
                "articles_screened": len(state.screened_articles),
                "clusters_identified": len(state.event_clusters)
            })
            yield {
                "stage": "triage",
                "status": "completed",
                "progress": 1.0,
                "articles_screened": len(state.screened_articles),
                "events_identified": len(state.event_clusters),
                "critical_events": len([c for c in state.event_clusters if c.preliminary_importance == "critical"])
            }

            # Stage 3: Deep Analysis
            yield {"stage": "deep_analysis", "status": "started", "progress": 0.0}
            async for progress in self._run_deep_analysis(state, config):
                state.update_progress("deep_analysis", progress["progress"])
                yield {"stage": "deep_analysis", **progress}
            state.update_progress("deep_analysis", 1.0)
            state.audit_trail["stages"].append({
                "name": "deep_analysis",
                "completed_at": datetime.now().isoformat(),
                "events_analyzed": len(state.analyzed_events)
            })
            yield {
                "stage": "deep_analysis",
                "status": "completed",
                "progress": 1.0,
                "events_analyzed": len(state.analyzed_events)
            }

            # Stage 4: Synthesis
            yield {"stage": "synthesis", "status": "started", "progress": 0.0}
            async for progress in self._run_synthesis(state, config):
                state.update_progress("synthesis", progress["progress"])
                yield {"stage": "synthesis", **progress}
            state.update_progress("synthesis", 1.0)
            state.audit_trail["stages"].append({
                "name": "synthesis",
                "completed_at": datetime.now().isoformat()
            })

            # Complete audit trail
            state.audit_trail["completed_at"] = datetime.now().isoformat()
            state.audit_trail["duration_seconds"] = (datetime.now() - state.created_at).total_seconds()

            # Prepare screened articles for frontend (simplified format)
            screened_articles_data = []
            for article in state.screened_articles:
                screened_articles_data.append({
                    "id": article.get("id"),
                    "title": article.get("title", "Untitled"),
                    "uri": article.get("uri") or article.get("url", ""),
                    "source": article.get("news_source") or article.get("source", "Unknown"),
                    "published_at": article.get("published_at") or article.get("publication_date"),
                    "credibility_score": article.get("credibility_score", 0),
                    "summary": (article.get("summary", "") or "")[:200]
                })

            # Final result
            yield {
                "stage": "complete",
                "status": "success",
                "progress": 1.0,
                "scan_id": state.scan_id,
                "brief": state.intelligence_brief,
                "metadata": {
                    "articles_collected": len(state.raw_articles),
                    "articles_screened": len(state.screened_articles),
                    "events_identified": len(state.event_clusters),
                    "events_analyzed": len(state.analyzed_events),
                    "duration_seconds": state.audit_trail["duration_seconds"],
                    "generated_at": datetime.now().isoformat()
                },
                "articles": screened_articles_data,
                "audit_trail": state.audit_trail
            }

        except asyncio.TimeoutError:
            logger.error(f"SIO stage timed out: {state.current_stage}")
            state.errors.append(f"Timeout in {state.current_stage.value} stage")
            yield {
                "stage": state.current_stage.value,
                "status": "timeout",
                "error": "Stage timed out",
                "progress": state.overall_progress(),
                "partial_results": state.to_dict()
            }

        except Exception as e:
            logger.error(f"SIO scan failed: {e}", exc_info=True)
            state.errors.append(str(e))
            yield {
                "stage": state.current_stage.value,
                "status": "error",
                "error": str(e),
                "progress": state.overall_progress(),
                "partial_results": state.to_dict()
            }

    async def _run_discovery(self, state: SIOState, config: SIOConfig):
        """
        Stage 1: Discovery
        Cast wide net to gather articles from past 24 hours.
        """
        logger.info(f"Starting discovery: {config.hours_back} hours back, max {config.max_discovery_articles} articles")

        all_articles = []
        seen_urls = set()

        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(hours=config.hours_back)

        # Generate search queries
        queries = await self._generate_discovery_queries(state.topic, config)

        state.audit_trail["models_used"].append(config.discovery_model)

        # Execute searches in parallel batches
        for i, query_batch in enumerate(self._batch_queries(queries, 3)):
            tasks = []
            for query_info in query_batch:
                query = query_info.get("query", "")
                # Force internal-only search - mine internal database only, no external API calls
                source = SearchSource.VECTOR_DB

                tasks.append(self._execute_search(
                    query=query,
                    topic=state.topic,
                    limit=config.max_discovery_articles // len(queries),
                    source=source,
                    start_date=start_date
                ))

            # Execute batch
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, Exception):
                    logger.warning(f"Search failed: {result}")
                    continue

                for article in result:
                    url = article.get("url") or article.get("uri", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_articles.append(article)

            if len(all_articles) >= config.max_discovery_articles:
                break

        # Store results
        state.raw_articles = all_articles[:config.max_discovery_articles]

        # Calculate collection stats
        sources = set()
        categories = set()
        for article in state.raw_articles:
            source = article.get("news_source") or article.get("source", "Unknown")
            sources.add(source)
            category = article.get("category", "Unknown")
            categories.add(category)

        state.collection_stats = {
            "total_articles": len(state.raw_articles),
            "unique_sources": len(sources),
            "categories_covered": list(categories),
            "time_range": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            }
        }

        logger.info(f"Discovery complete: {len(state.raw_articles)} articles from {len(sources)} sources")

    async def _generate_discovery_queries(
        self,
        topic: Optional[str],
        config: SIOConfig
    ) -> List[Dict]:
        """Generate search queries for discovery phase."""
        # Use the discovery agent prompt
        agent_prompt = self._load_agent_prompt("sio_discovery_agent")

        if topic:
            user_prompt = f"Generate search queries for a strategic intelligence scan focused on: {topic}"
        else:
            user_prompt = "Generate search queries for a comprehensive 24-hour strategic intelligence scan covering all major news categories."

        try:
            response = await litellm.acompletion(
                model=config.discovery_model,
                messages=[
                    {"role": "system", "content": agent_prompt or "Generate diverse search queries for news discovery."},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.2,
                max_tokens=1500,
                response_format={"type": "json_object"}
            )

            result = json.loads(response.choices[0].message.content)
            return result.get("search_queries", [])

        except Exception as e:
            logger.error(f"Query generation failed: {e}")
            # Fallback queries
            base_queries = [
                {"query": "breaking news today", "priority": "critical", "source_preference": "both"},
                {"query": "major developments world", "priority": "high", "source_preference": "both"},
                {"query": "economy market financial", "priority": "high", "source_preference": "both"},
                {"query": "politics government policy", "priority": "high", "source_preference": "both"},
                {"query": "technology cybersecurity", "priority": "medium", "source_preference": "both"},
                {"query": "security conflict military", "priority": "high", "source_preference": "both"},
            ]
            if topic:
                base_queries.insert(0, {"query": topic, "priority": "critical", "source_preference": "both"})
            return base_queries

    async def _execute_search(
        self,
        query: str,
        topic: Optional[str],
        limit: int,
        source: SearchSource,
        start_date: datetime
    ) -> List[Dict]:
        """Execute a single search query."""
        try:
            results = await self.search_router.execute_routed_search(
                query=query,
                topic=topic or "general",
                limit=limit,
                force_source=source,
                tools_service=self.tools
            )

            articles = results.get("articles", [])
            logger.info(f"Search for '{query}' returned {len(articles)} articles from search_router")

            # Filter by date
            filtered = []
            for article in articles:
                pub_date = article.get("publication_date", "")
                if pub_date:
                    try:
                        # Parse date and check if within range
                        if isinstance(pub_date, str):
                            date_part = pub_date.split(" ")[0] if " " in pub_date else pub_date[:10]
                            article_date = datetime.strptime(date_part, "%Y-%m-%d")
                            if article_date >= start_date:
                                filtered.append(article)
                            else:
                                logger.debug(f"Date filter: excluding article from {date_part} (before {start_date.strftime('%Y-%m-%d')})")
                        else:
                            filtered.append(article)
                    except:
                        filtered.append(article)  # Include if can't parse
                else:
                    filtered.append(article)  # Include if no date

            logger.info(f"After date filter (>= {start_date.strftime('%Y-%m-%d %H:%M')}): {len(filtered)}/{len(articles)} articles")
            return filtered

        except Exception as e:
            logger.warning(f"Search failed for '{query}': {e}")
            return []

    def _batch_queries(self, queries: List[Dict], batch_size: int) -> List[List[Dict]]:
        """Split queries into batches."""
        return [queries[i:i+batch_size] for i in range(0, len(queries), batch_size)]

    async def _run_triage(self, state: SIOState, config: SIOConfig):
        """
        Stage 2: Triage
        Screen for credibility and cluster into events.
        """
        logger.info(f"Starting triage: {len(state.raw_articles)} articles to screen")

        # Step 1: Credibility screening
        screened = []
        for article in state.raw_articles:
            source = article.get("news_source") or article.get("source", "")
            if source:
                bias_data = self.media_bias.get_bias_for_source(source)
                if bias_data:
                    rating = bias_data.get("mbfc_credibility_rating", "")
                    factual = bias_data.get("factual_reporting", "")
                    score = self._credibility_to_score(rating)

                    if score >= config.credibility_threshold:
                        article["credibility_score"] = score
                        article["bias"] = bias_data.get("bias")
                        article["factual_reporting"] = factual
                        screened.append(article)
                else:
                    # Unknown source - include with lower confidence
                    article["credibility_score"] = 50
                    screened.append(article)
            else:
                # No source info - include with caution
                article["credibility_score"] = 40
                screened.append(article)

        state.screened_articles = screened
        logger.info(f"Credibility screening: {len(screened)}/{len(state.raw_articles)} passed")

        # Step 2: Cluster into events
        clusters = await self._cluster_articles(screened, config)
        state.event_clusters = clusters

        logger.info(f"Clustering complete: {len(clusters)} events identified")

    async def _cluster_articles(
        self,
        articles: List[Dict],
        config: SIOConfig
    ) -> List[EventCluster]:
        """Cluster articles into events using LLM-based semantic grouping."""
        if len(articles) < 2:
            if articles:
                return [EventCluster(
                    cluster_id="evt_001",
                    title=articles[0].get("title", "Single Article"),
                    articles=articles,
                    article_indices=[0],
                    representative_article=articles[0],
                    preliminary_importance="medium"
                )]
            return []

        # Prepare article summaries for clustering
        article_summaries = []
        for i, article in enumerate(articles[:200]):  # Limit for context
            article_summaries.append({
                "index": i,
                "title": article.get("title", "")[:100],
                "source": article.get("news_source") or article.get("source", "Unknown"),
                "summary": (article.get("summary", "") or "")[:200],
                "credibility": article.get("credibility_score", 50)
            })

        # Use triage agent to cluster
        agent_prompt = self._load_agent_prompt("sio_triage_agent")

        prompt = f"""Analyze these {len(article_summaries)} PRE-SCREENED articles and cluster them into distinct events/stories.

IMPORTANT: These articles have ALREADY passed credibility screening. Your job is to GROUP them into events, NOT filter them.

ARTICLES:
{json.dumps(article_summaries, indent=2)}

Instructions:
1. Group related articles that cover the SAME event or story
2. Create event clusters - each article should belong to an event
3. Single-article events ARE allowed for unique stories
4. Assign importance: critical, high, medium, low
5. Return JSON with event_clusters array - NEVER return an empty array

You MUST create at least one event cluster for every few articles."""

        try:
            response = await litellm.acompletion(
                model=config.triage_model,
                messages=[
                    {"role": "system", "content": agent_prompt or "Cluster news articles into events."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=4000,
                response_format={"type": "json_object"}
            )

            raw_response = response.choices[0].message.content
            logger.info(f"Clustering LLM raw response (first 500 chars): {raw_response[:500]}")

            result = json.loads(raw_response)
            raw_clusters = result.get("event_clusters", [])

            # Check alternative keys the LLM might use
            if not raw_clusters:
                raw_clusters = result.get("clusters", [])
            if not raw_clusters:
                raw_clusters = result.get("events", [])

            logger.info(f"Clustering LLM returned {len(raw_clusters)} raw clusters")
            if raw_clusters:
                logger.info(f"First cluster sample: {raw_clusters[0]}")

            # Convert to EventCluster objects
            clusters = []
            skipped_too_few = 0
            for i, rc in enumerate(raw_clusters[:config.max_clusters]):
                indices = rc.get("article_indices", [])
                cluster_articles = [articles[idx] for idx in indices if idx < len(articles)]

                if len(cluster_articles) < config.min_articles_per_cluster:
                    skipped_too_few += 1
                    logger.debug(f"Skipping cluster '{rc.get('event_title', 'Unknown')}': only {len(cluster_articles)} articles (need {config.min_articles_per_cluster})")
                    continue

                # Calculate source diversity
                sources = set(a.get("news_source") or a.get("source", "") for a in cluster_articles)
                diversity = len(sources) / len(cluster_articles) if cluster_articles else 0

                # Select representative article
                representative = max(
                    cluster_articles,
                    key=lambda a: a.get("credibility_score", 0)
                ) if cluster_articles else None

                clusters.append(EventCluster(
                    cluster_id=rc.get("cluster_id", f"evt_{i+1:03d}"),
                    title=rc.get("event_title", f"Event {i+1}"),
                    summary=rc.get("event_summary", ""),
                    category=rc.get("category", "general"),
                    articles=cluster_articles,
                    article_indices=indices,
                    representative_article=representative,
                    source_diversity_score=diversity,
                    preliminary_importance=rc.get("preliminary_importance", "medium"),
                    keywords=rc.get("keywords", [])
                ))

            # Sort by importance
            importance_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            clusters.sort(key=lambda c: (
                importance_order.get(c.preliminary_importance, 2),
                -len(c.articles)
            ))

            logger.info(f"Clustering result: {len(clusters)} valid clusters, {skipped_too_few} skipped (too few articles)")

            return clusters

        except Exception as e:
            logger.error(f"Clustering failed: {e}")
            # Fallback: create one cluster per unique title pattern
            return self._fallback_clustering(articles, config)

    def _fallback_clustering(
        self,
        articles: List[Dict],
        config: SIOConfig
    ) -> List[EventCluster]:
        """Simple fallback clustering based on keyword overlap."""
        clusters = []
        used_indices = set()

        for i, article in enumerate(articles):
            if i in used_indices:
                continue

            title = article.get("title", "").lower()
            cluster_articles = [article]
            cluster_indices = [i]

            # Find similar articles
            for j, other in enumerate(articles[i+1:], start=i+1):
                if j in used_indices:
                    continue
                other_title = other.get("title", "").lower()

                # Simple word overlap check
                words1 = set(title.split())
                words2 = set(other_title.split())
                overlap = len(words1 & words2) / max(len(words1), len(words2), 1)

                if overlap > 0.5:
                    cluster_articles.append(other)
                    cluster_indices.append(j)
                    used_indices.add(j)

            used_indices.add(i)

            if len(cluster_articles) >= config.min_articles_per_cluster:
                clusters.append(EventCluster(
                    cluster_id=f"evt_{len(clusters)+1:03d}",
                    title=article.get("title", "")[:100],
                    articles=cluster_articles,
                    article_indices=cluster_indices,
                    representative_article=cluster_articles[0],
                    source_diversity_score=len(set(a.get("news_source", "") for a in cluster_articles)) / len(cluster_articles),
                    preliminary_importance="medium"
                ))

        return clusters[:config.max_clusters]

    async def _run_deep_analysis(
        self,
        state: SIOState,
        config: SIOConfig
    ) -> AsyncGenerator[Dict, None]:
        """
        Stage 3: Deep Analysis
        Analyze top events using ArticleIntelligenceAnalyzer.
        """
        events_to_analyze = state.event_clusters[:config.max_events_to_analyze]
        total = len(events_to_analyze)

        if total == 0:
            yield {"status": "no_events", "progress": 1.0}
            return

        logger.info(f"Starting deep analysis of {total} events")

        state.audit_trail["models_used"].append(config.analysis_model)

        # Process in batches for controlled parallelism
        batch_size = config.max_concurrent_analyses
        analyzed = []

        for batch_start in range(0, total, batch_size):
            batch = events_to_analyze[batch_start:batch_start + batch_size]

            tasks = []
            for cluster in batch:
                tasks.append(self._analyze_event(cluster, state.topic))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for i, result in enumerate(results):
                cluster = batch[i]
                if isinstance(result, Exception):
                    logger.warning(f"Analysis failed for {cluster.title}: {result}")
                    cluster.analysis = None
                else:
                    cluster.analysis = result
                    # Calculate final importance score
                    if result and result.impact_assessment:
                        cluster.final_importance_score = result.impact_assessment.get("overall_importance", 0.5)

                analyzed.append(cluster)

            progress = (batch_start + len(batch)) / total
            yield {
                "status": "analyzing",
                "progress": progress,
                "events_analyzed": len(analyzed),
                "current_event": batch[-1].title if batch else ""
            }

        # Sort by final importance
        analyzed.sort(key=lambda c: c.final_importance_score, reverse=True)
        state.analyzed_events = analyzed

        yield {
            "status": "completed",
            "progress": 1.0,
            "events_analyzed": len(analyzed)
        }

    async def _analyze_event(
        self,
        cluster: EventCluster,
        topic: Optional[str]
    ) -> Optional[ArticleAnalysis]:
        """Analyze a single event cluster."""
        try:
            analysis = await self.analyzer.analyze_cluster(
                articles=cluster.articles,
                cluster_title=cluster.title,
                topic=topic
            )
            return analysis
        except Exception as e:
            logger.error(f"Event analysis failed: {e}")
            return None

    async def _run_synthesis(
        self,
        state: SIOState,
        config: SIOConfig
    ) -> AsyncGenerator[Dict, None]:
        """
        Stage 4: Synthesis
        Generate final intelligence brief.
        """
        logger.info(f"Starting synthesis of {len(state.analyzed_events)} analyzed events")

        state.audit_trail["models_used"].append(config.synthesis_model)

        # Prepare event summaries for synthesis
        event_summaries = []
        for cluster in state.analyzed_events:
            summary = {
                "title": cluster.title,
                "category": cluster.category,
                "article_count": len(cluster.articles),
                "importance": cluster.preliminary_importance,
                "importance_score": cluster.final_importance_score,
                "summary": cluster.summary
            }

            if cluster.analysis:
                summary.update({
                    "key_facts": cluster.analysis.key_facts[:5],
                    "confidence": cluster.analysis.confidence_score,
                    "quality_gates": cluster.analysis.quality_gates,
                    "impact": cluster.analysis.impact_assessment,
                    "sources": [
                        xref.get("source") for xref in cluster.analysis.cross_references[:5]
                    ]
                })

            event_summaries.append(summary)

        # Use synthesis agent
        agent_prompt = self._load_agent_prompt("sio_synthesis_agent")

        # Calculate actual date range for the brief
        end_date = datetime.now()
        start_date = end_date - timedelta(hours=state.hours_back)
        date_range_str = f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"

        prompt = f"""Generate a Strategic Intelligence Brief based on these analyzed events.

TODAY'S DATE: {end_date.strftime('%Y-%m-%d')}
CURRENT TIME: {end_date.strftime('%H:%M:%S UTC')}

SCAN METADATA:
- Date range covered: {date_range_str}
- Time window: Past {state.hours_back} hours
- Topic filter: {state.topic or 'All topics'}
- Articles collected: {len(state.raw_articles)}
- Events analyzed: {len(state.analyzed_events)}

ANALYZED EVENTS:
{json.dumps(event_summaries[:25], indent=2)}

Generate a comprehensive intelligence brief following the standard structure:
1. Executive Summary (top 5 critical items)
2. Critical Events (ranked by importance)
3. Emerging Signals
4. Source Analysis
5. Confidence Assessment
6. Methodology

IMPORTANT:
- Use the dates provided above (Date range: {date_range_str}). Do NOT use any other dates.
- The brief header should show: "{state.topic or 'General Intelligence'} | {date_range_str}"
- Do NOT include an Audit Trail section - this will be added automatically.

Use markdown formatting. Include confidence indicators and source attributions."""

        yield {"status": "generating", "progress": 0.3}

        try:
            # Stream the response
            report_chunks = []

            response = await litellm.acompletion(
                model=config.synthesis_model,
                messages=[
                    {"role": "system", "content": agent_prompt or "Generate strategic intelligence briefs."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.4,
                max_tokens=8000,
                stream=True
            )

            async for chunk in response:
                content = chunk.choices[0].delta.content or ""
                report_chunks.append(content)

                current_length = sum(len(c) for c in report_chunks)
                progress = min(0.9, 0.3 + (current_length / 10000) * 0.6)

                yield {
                    "status": "writing",
                    "progress": progress,
                    "chunk": content
                }

            state.intelligence_brief = "".join(report_chunks)

            # Fix any markdown formatting issues from LLM output
            state.intelligence_brief = self._fix_markdown_formatting(state.intelligence_brief)

            # Add audit trail footer
            audit_footer = f"""

---

## Audit Trail

**Scan ID:** {state.scan_id}
**Generated:** {datetime.now().isoformat()}
**Time Window:** Past {state.hours_back} hours
**Topic Filter:** {state.topic or 'All topics'}

**Collection Statistics:**
- Articles Collected: {len(state.raw_articles)}
- Articles Screened: {len(state.screened_articles)}
- Events Identified: {len(state.event_clusters)}
- Events Analyzed: {len(state.analyzed_events)}

**AI Models Used:**
{', '.join(set(state.audit_trail.get('models_used', [])))}

**AI Disclosure:** This intelligence brief was generated with AI assistance using the Strategic Intelligence Oracle system. All factual claims have been cross-referenced against multiple sources where possible. Items marked with 🔴 LOW CONFIDENCE should be verified before action.

---
*Strategic Intelligence Oracle v1.0*
"""

            state.intelligence_brief += audit_footer

            yield {
                "status": "completed",
                "progress": 1.0,
                "brief_length": len(state.intelligence_brief)
            }

        except Exception as e:
            logger.error(f"Synthesis failed: {e}")
            # Generate basic fallback brief
            state.intelligence_brief = self._generate_fallback_brief(state)
            yield {
                "status": "completed_with_fallback",
                "progress": 1.0,
                "error": str(e)
            }

    def _fix_markdown_formatting(self, text: str) -> str:
        """Fix common markdown formatting issues in LLM output.

        Fixes issues like:
        - '• Nature:**' -> '- **Nature:**'
        - 'Nature:**' at start of line -> '- **Nature:**'
        - Missing opening ** markers
        """
        import re

        lines = text.split('\n')
        fixed_lines = []

        # Patterns for threat/opportunity fields that should be formatted as **Field:**
        field_patterns = [
            'Nature:', 'Likelihood:', 'Impact:', 'Time Horizon:',
            'Indicators to Watch:', 'Window:', 'Prerequisites:',
            'Risk if Missed:', 'Current Status:', 'Trigger Event:',
            'Escalation Action:'
        ]

        for line in lines:
            fixed_line = line

            # Fix bullet points: • -> -
            if fixed_line.strip().startswith('•'):
                fixed_line = fixed_line.replace('•', '-', 1)

            # Fix missing opening ** for known field patterns
            for field in field_patterns:
                # Pattern: "- Field:**" or "  - Field:**" (missing opening **)
                pattern = rf'^(\s*-\s*)({re.escape(field)})\*\*'
                if re.match(pattern, fixed_line):
                    fixed_line = re.sub(pattern, r'\1**\2**', fixed_line)

                # Pattern: "Field:**" at start of bullet (no opening **)
                pattern2 = rf'^(\s*-\s*)({re.escape(field[:-1])})\*\*:'
                if re.match(pattern2, fixed_line):
                    fixed_line = re.sub(pattern2, r'\1**\2:**', fixed_line)

            # Fix any remaining pattern: "- Word:**" -> "- **Word:**"
            # This catches cases like "- Likelihood:**" missing opening **
            fixed_line = re.sub(r'^(\s*-\s+)([A-Z][a-z\s]+):\*\*', r'\1**\2:**', fixed_line)

            # Also fix "• Word:**" patterns that were converted to "- Word:**"
            fixed_line = re.sub(r'^(\s*-\s+)([A-Z][a-z\s]+)\*\*:', r'\1**\2:**', fixed_line)

            fixed_lines.append(fixed_line)

        return '\n'.join(fixed_lines)

    def _generate_fallback_brief(self, state: SIOState) -> str:
        """Generate a basic fallback brief if synthesis fails."""
        lines = [
            "# Strategic Intelligence Brief",
            f"## 24-Hour Analysis: {datetime.now().strftime('%Y-%m-%d')}",
            "",
            "---",
            "",
            "## Executive Summary",
            "",
            f"Analyzed {len(state.raw_articles)} articles, identified {len(state.event_clusters)} events.",
            "",
            "## Critical Events",
            ""
        ]

        for i, cluster in enumerate(state.analyzed_events[:10]):
            importance = "🔴" if cluster.preliminary_importance == "critical" else "🟠" if cluster.preliminary_importance == "high" else "🟡"
            lines.append(f"### {importance} {cluster.title}")
            lines.append(f"*{len(cluster.articles)} articles | {cluster.category}*")
            lines.append("")
            if cluster.summary:
                lines.append(cluster.summary)
            lines.append("")

        lines.append("---")
        lines.append(f"*Generated: {datetime.now().isoformat()} | Scan ID: {state.scan_id}*")

        return "\n".join(lines)

    def _credibility_to_score(self, rating: str) -> int:
        """Convert MBFC credibility rating to numeric score."""
        rating_map = {
            "Very High": 95,
            "High": 85,
            "Mostly Factual": 70,
            "Mixed": 50,
            "Low": 30,
            "Very Low": 15
        }
        return rating_map.get(rating, 50)


# Singleton instance
_sio_instance: Optional[StrategicIntelligenceService] = None


def get_strategic_intelligence_service() -> StrategicIntelligenceService:
    """Get the global Strategic Intelligence Oracle service instance."""
    global _sio_instance
    if _sio_instance is None:
        _sio_instance = StrategicIntelligenceService()
    return _sio_instance
