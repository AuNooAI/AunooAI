"""
Deep Research Agent Service
Multi-step autonomous research with exploration, planning, parallel searching, synthesis, and reporting.

This service orchestrates the 5-stage deep research workflow:
0. Exploration - Understand corpus content BEFORE planning (themes, stats, samples)
1. Planning - Analyze query with corpus context, create objectives and search strategy
2. Searching - Execute PARALLEL multi-strategy search (semantic, temporal, category, quality, future signals)
3. Synthesis - Analyze findings, resolve contradictions, assess confidence
4. Writing - Produce professional research report with citations

Key improvements (2025):
- Corpus exploration stage provides actual article samples to inform query generation
- 5 parallel search strategies execute concurrently for comprehensive coverage
- Smart sampling (semantic + quality + diversity) selects best articles
- Increased limits: 500 max articles (up from 100), 100 per query (up from 20)
- Cross-topic search for related content from other topics
- Future signals integration for predictive content
"""

import asyncio
import json
import logging
from typing import Dict, List, Optional, AsyncGenerator, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum

import litellm

from app.ai_models import resolve_litellm_call_params
from app.database import get_database_instance
from app.services.auspex_tools import get_auspex_tools_service
from app.services.tool_loader import get_tool_loader
from app.services.search_router import get_search_router, SearchSource
from app.services.relevance_scorer import get_relevance_scorer, RelevanceScoringConfig
from app.services.sampling import (
    get_registry,
    SamplingContext,
    CompositeSampling,
    QualitySampling,
    DiversitySampling,
    SemanticSampling,
    TopicBalancedSampling,
    RecencySampling,
)

logger = logging.getLogger(__name__)


class ResearchStage(str, Enum):
    """Research workflow stages."""
    EXPLORATION = "exploration"
    PLANNING = "planning"
    SEARCHING = "searching"
    SYNTHESIS = "synthesis"
    WRITING = "writing"
    COMPLETE = "complete"
    ERROR = "error"


@dataclass
class ResearchState:
    """Tracks state across research stages."""

    query: str
    topic: str
    chat_id: Optional[int] = None
    username: Optional[str] = None
    session_id: Optional[int] = None
    created_at: datetime = field(default_factory=datetime.now)

    # Corpus exploration context (populated in exploration stage)
    corpus_context: Dict = field(default_factory=dict)

    # Stage outputs
    research_objectives: List[Dict] = field(default_factory=list)
    search_queries: List[Dict] = field(default_factory=list)
    report_outline: Dict = field(default_factory=dict)
    raw_results: List[Dict] = field(default_factory=list)
    source_metadata: Dict = field(default_factory=dict)
    synthesized_findings: Dict = field(default_factory=dict)
    credibility_assessment: Dict = field(default_factory=dict)
    final_report: str = ""

    # Source tracking for internal vs external attribution
    sources_used: Dict[str, int] = field(default_factory=lambda: {"internal": 0, "external": 0})

    # Progress tracking
    current_stage: ResearchStage = ResearchStage.EXPLORATION
    stage_progress: Dict[str, float] = field(default_factory=lambda: {
        "exploration": 0.0,
        "planning": 0.0,
        "searching": 0.0,
        "synthesis": 0.0,
        "writing": 0.0
    })
    errors: List[str] = field(default_factory=list)

    def update_progress(self, stage: str, progress: float):
        """Update progress for a stage."""
        self.stage_progress[stage] = min(1.0, max(0.0, progress))
        self.current_stage = ResearchStage(stage)

    def overall_progress(self) -> float:
        """Calculate overall progress."""
        weights = {"exploration": 0.05, "planning": 0.1, "searching": 0.35, "synthesis": 0.3, "writing": 0.2}
        return sum(self.stage_progress.get(s, 0) * w for s, w in weights.items())

    def to_dict(self) -> Dict:
        """Convert state to dictionary for storage."""
        return {
            "query": self.query,
            "topic": self.topic,
            "chat_id": self.chat_id,
            "username": self.username,
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat(),
            "corpus_context": self.corpus_context,
            "research_objectives": self.research_objectives,
            "search_queries": self.search_queries,
            "report_outline": self.report_outline,
            "source_metadata": self.source_metadata,
            "synthesized_findings": self.synthesized_findings,
            "credibility_assessment": self.credibility_assessment,
            "current_stage": self.current_stage.value,
            "stage_progress": self.stage_progress,
            "errors": self.errors,
            "articles_count": len(self.raw_results),
            "sources_used": self.sources_used
        }


@dataclass
class ResearchConfig:
    """Configuration for a research session."""

    # Token and article limits
    max_total_tokens: int = 100000
    max_articles: int = 500  # Increased from 100 for better corpus utilization
    articles_per_query: int = 100  # Increased from 20 for broader search coverage

    # Quality thresholds
    credibility_threshold: int = 40
    source_diversity_min: int = 10  # Increased from 5 for better diversity
    min_section_length: int = 500
    max_per_source: int = 30  # Cap per source for diversity

    # Temporal distribution requirements
    temporal_distribution_recent: float = 0.3  # 30% from last 7 days
    temporal_distribution_medium: float = 0.4  # 40% from last 30 days
    temporal_distribution_older: float = 0.3  # 30% older context

    # Model settings
    planning_model: str = "gpt-5.4-mini"
    planning_temperature: float = 0.3
    synthesis_model: str = "gpt-5.4"
    synthesis_temperature: float = 0.4
    writing_model: str = "gpt-5.4"
    writing_temperature: float = 0.5

    # Timeouts (seconds)
    exploration_timeout: int = 30
    planning_timeout: int = 30
    searching_timeout: int = 180  # Increased from 120 for more comprehensive search
    synthesis_timeout: int = 300  # Increased for batched synthesis (5 min total)
    synthesis_batch_timeout: int = 60  # Timeout per batch
    writing_timeout: int = 120  # Increased from 90 for comprehensive reports

    # Batch processing
    synthesis_batch_size: int = 50  # Articles per synthesis batch

    # Feature flags
    allow_external_search: bool = True
    include_charts: bool = True

    # Research mode settings
    search_source: str = "hybrid"  # 'internal', 'external', 'hybrid'
    research_mode: str = "hybrid"  # 'off', 'internal', 'hybrid', 'external', 'extend'
    extend_mode: bool = False
    previous_research: Optional[str] = None

    # Phase 2: Relevance scoring (behind feature flag)
    enable_relevance_scoring: bool = True  # Filter irrelevant results before synthesis
    relevance_threshold: float = 0.6  # Minimum score to include article
    relevance_scoring_timeout: int = 120  # Increased from 60 for large article sets

    # Phase 3: Iterative refinement (behind feature flag)
    enable_refinement: bool = True  # Enable iterative search refinement
    max_refinement_iterations: int = 2  # Maximum refinement rounds
    min_coverage_threshold: float = 0.7  # Minimum coverage before stopping refinement

    @classmethod
    def from_workflow(cls, workflow_config: Dict) -> "ResearchConfig":
        """Create config from workflow definition."""
        config = cls()

        # General config
        if "config" in workflow_config:
            cfg = workflow_config["config"]
            config.max_total_tokens = cfg.get("max_total_tokens", config.max_total_tokens)
            config.credibility_threshold = cfg.get("credibility_threshold", config.credibility_threshold)
            config.source_diversity_min = cfg.get("source_diversity_min", config.source_diversity_min)
            config.allow_external_search = cfg.get("allow_external_search", config.allow_external_search)

        # Sampling config
        if "sampling" in workflow_config:
            sampling = workflow_config["sampling"]
            config.max_articles = sampling.get("max_total_articles", config.max_articles)
            config.articles_per_query = sampling.get("articles_per_query", config.articles_per_query)

        # Model config
        if "model_config" in workflow_config:
            mc = workflow_config["model_config"]
            stages = mc.get("stages", {})

            if "planning" in stages:
                config.planning_model = stages["planning"].get("model", config.planning_model)
                config.planning_temperature = stages["planning"].get("temperature", config.planning_temperature)

            if "synthesis" in stages:
                config.synthesis_model = stages["synthesis"].get("model", config.synthesis_model)
                config.synthesis_temperature = stages["synthesis"].get("temperature", config.synthesis_temperature)

            if "writing" in stages:
                config.writing_model = stages["writing"].get("model", config.writing_model)
                config.writing_temperature = stages["writing"].get("temperature", config.writing_temperature)

        # Phase 2 & 3 feature flags
        if "features" in workflow_config:
            features = workflow_config["features"]
            config.enable_relevance_scoring = features.get("enable_relevance_scoring", config.enable_relevance_scoring)
            config.relevance_threshold = features.get("relevance_threshold", config.relevance_threshold)
            config.enable_refinement = features.get("enable_refinement", config.enable_refinement)
            config.max_refinement_iterations = features.get("max_refinement_iterations", config.max_refinement_iterations)
            config.min_coverage_threshold = features.get("min_coverage_threshold", config.min_coverage_threshold)

        return config


class DeepResearchService:
    """Service for conducting deep, multi-step research."""

    # Topic values that indicate cross-topic (all topics) mode
    CROSS_TOPIC_VALUES = {"__all__", "All Topics", "all", "all_topics", "", None}

    def __init__(self):
        # IMPORTANT: Use database facade pattern for all DB operations
        # Access methods via self.db.facade.method_name()
        self.db = get_database_instance()
        self.tools = get_auspex_tools_service()
        self.tool_loader = get_tool_loader()
        self.search_router = get_search_router()

    def _normalize_topic(self, topic: Optional[str]) -> Optional[str]:
        """
        Normalize topic for database queries.
        Special values like '__all__', 'All Topics' are converted to None for cross-topic mode.
        """
        if topic is None or topic in self.CROSS_TOPIC_VALUES:
            return None
        return topic

    def _load_agent_prompt(self, agent_name: str) -> Optional[str]:
        """Load agent prompt from tool loader and inject current date."""
        agent = self.tool_loader.get_agent(agent_name)
        if agent:
            content = agent.content
            # Inject current date for context
            current_date = datetime.now().strftime("%B %d, %Y")
            content = content.replace("{{CURRENT_DATE}}", current_date)
            return content
        return None

    async def conduct_research(
        self,
        query: str,
        topic: str,
        username: str,
        chat_id: Optional[int] = None,
        config: Optional[ResearchConfig] = None
    ) -> AsyncGenerator[Dict, None]:
        """
        Conduct deep research with progress streaming.

        Yields progress updates and final result.
        """
        # Handle short/greeting queries gracefully - prompt for more details
        if len(query.strip()) < 10 or query.strip().lower() in ['hi', 'hello', 'hey', 'help', 'test']:
            friendly_response = f"""Hi! I'm ready to help with deep research on **{topic}**.

To get started, please ask a specific research question like:
- "What are the recent trends in [specific area]?"
- "Analyze sentiment around [topic or event]"
- "What are the key developments in [area] over the last month?"
- "Compare coverage of [X] vs [Y]"

The more specific your question, the better insights I can provide!"""
            yield {
                "stage": "complete",
                "status": "completed",
                "progress": 1.0,
                "report": friendly_response,
                "needs_more_input": True
            }
            return

        # Load workflow config if available
        if config is None:
            workflow = self.tool_loader.get_workflow("deep_research_workflow")
            if workflow:
                config = ResearchConfig.from_workflow(workflow.to_dict())
            else:
                config = ResearchConfig()

        state = ResearchState(
            query=query,
            topic=topic,
            chat_id=chat_id,
            username=username
        )

        try:
            # Stage 0: Exploration - Understand corpus before planning
            yield {"stage": "exploration", "status": "started", "progress": 0.0}
            await asyncio.wait_for(
                self._run_exploration(state, config),
                timeout=config.exploration_timeout
            )
            state.update_progress("exploration", 1.0)
            yield {
                "stage": "exploration",
                "status": "completed",
                "progress": 1.0,
                "corpus_size": state.corpus_context.get("stats", {}).get("total_articles", 0),
                "themes_found": len(state.corpus_context.get("themes", []))
            }

            # Stage 1: Planning (now corpus-informed)
            yield {"stage": "planning", "status": "started", "progress": 0.0}
            await asyncio.wait_for(
                self._run_planning(state, config),
                timeout=config.planning_timeout
            )
            state.update_progress("planning", 1.0)
            yield {
                "stage": "planning",
                "status": "completed",
                "progress": 1.0,
                "objectives_count": len(state.research_objectives),
                "queries_count": len(state.search_queries)
            }

            # Stage 2: Searching
            yield {"stage": "searching", "status": "started", "progress": 0.0}
            async for progress in self._run_searching(state, config):
                state.update_progress("searching", progress["progress"])
                yield {"stage": "searching", **progress}
            state.update_progress("searching", 1.0)
            yield {
                "stage": "searching",
                "status": "completed",
                "progress": 1.0,
                "articles_found": len(state.raw_results),
                "unique_sources": state.source_metadata.get("unique_sources", 0)
            }

            # Phase 2: Relevance Scoring (if enabled)
            if config.enable_relevance_scoring and state.raw_results:
                yield {"stage": "relevance_scoring", "status": "started", "progress": 0.0}
                try:
                    original_count = len(state.raw_results)
                    scorer_config = RelevanceScoringConfig(
                        relevance_threshold=config.relevance_threshold
                    )
                    scorer = get_relevance_scorer(scorer_config)

                    state.raw_results = await asyncio.wait_for(
                        scorer.score_articles(
                            articles=state.raw_results,
                            query=state.query,
                            objectives=state.research_objectives,
                            filter_below_threshold=True
                        ),
                        timeout=config.relevance_scoring_timeout
                    )

                    filtered_count = original_count - len(state.raw_results)
                    logger.info(f"Relevance scoring: {original_count} -> {len(state.raw_results)} articles (filtered {filtered_count})")

                    yield {
                        "stage": "relevance_scoring",
                        "status": "completed",
                        "progress": 1.0,
                        "original_count": original_count,
                        "filtered_count": filtered_count,
                        "remaining_count": len(state.raw_results)
                    }
                except asyncio.TimeoutError:
                    logger.warning("Relevance scoring timed out, proceeding with unfiltered results")
                    yield {
                        "stage": "relevance_scoring",
                        "status": "timeout",
                        "progress": 1.0,
                        "message": "Scoring timed out, using all results"
                    }
                except Exception as e:
                    logger.warning(f"Relevance scoring failed: {e}, proceeding with unfiltered results")
                    yield {
                        "stage": "relevance_scoring",
                        "status": "error",
                        "progress": 1.0,
                        "message": str(e)
                    }

            # Stage 3: Synthesis (Batched with Progress)
            yield {"stage": "synthesis", "status": "started", "progress": 0.0}
            try:
                async for progress in self._run_synthesis(state, config):
                    state.update_progress("synthesis", progress.get("progress", 0))
                    yield {"stage": "synthesis", **progress}
            except asyncio.TimeoutError:
                logger.warning("Synthesis overall timeout, proceeding with partial results")
                yield {
                    "stage": "synthesis",
                    "status": "partial_timeout",
                    "progress": 0.9,
                    "message": "Synthesis timed out, using partial results"
                }
            state.update_progress("synthesis", 1.0)
            yield {
                "stage": "synthesis",
                "status": "completed",
                "progress": 1.0,
                "confidence": state.credibility_assessment.get("overall_confidence", "unknown"),
                "total_findings": len(state.synthesized_findings)
            }

            # Stage 4: Writing
            yield {"stage": "writing", "status": "started", "progress": 0.0}
            async for progress in self._run_writing(state, config):
                state.update_progress("writing", progress["progress"])
                yield {"stage": "writing", **progress}
            state.update_progress("writing", 1.0)

            # Final result
            yield {
                "stage": "complete",
                "status": "success",
                "progress": 1.0,
                "report": state.final_report,
                "metadata": {
                    "objectives": len(state.research_objectives),
                    "articles_analyzed": len(state.raw_results),
                    "sources": state.source_metadata.get("unique_sources", 0),
                    "credibility": state.credibility_assessment.get("reliability_score", 0),
                    "duration_seconds": (datetime.now() - state.created_at).total_seconds()
                }
            }

        except asyncio.TimeoutError as e:
            logger.error(f"Research stage timed out: {state.current_stage}")
            state.errors.append(f"Timeout in {state.current_stage.value} stage")
            yield {
                "stage": state.current_stage.value,
                "status": "timeout",
                "error": f"Stage timed out after limit exceeded",
                "progress": state.overall_progress(),
                "partial_results": state.to_dict()
            }

        except Exception as e:
            logger.error(f"Deep research failed: {e}", exc_info=True)
            state.errors.append(str(e))
            yield {
                "stage": state.current_stage.value,
                "status": "error",
                "error": str(e),
                "progress": state.overall_progress(),
                "partial_results": state.to_dict()
            }

    async def _run_exploration(self, state: ResearchState, config: ResearchConfig):
        """
        Stage 0: Exploration
        Understand corpus content BEFORE planning to inform query generation.
        """
        logger.info(f"Starting corpus exploration for topic: {state.topic}")

        # Normalize topic - convert '__all__' to None for cross-topic mode
        normalized_topic = self._normalize_topic(state.topic)

        try:
            # 1. Get corpus statistics
            stats = {}
            if normalized_topic:
                stats["total_articles"] = self.db.facade.get_topic_articles_count(normalized_topic)
            else:
                # Cross-topic mode - estimate from recent articles
                stats["total_articles"] = 0

            # 2. Get filter options (categories, sentiments, sources available)
            filter_options = self.db.facade.get_article_filter_options(topic=normalized_topic)

            # 3. Get date range for topic
            date_range = self._get_date_range_for_topic(normalized_topic)
            stats["date_range"] = date_range

            # 4. Sample diverse articles to understand content
            sample_articles = await self._get_diverse_sample(
                topic=normalized_topic,
                sample_size=50,
                strategy="topic_balanced" if normalized_topic is None else "diversity"
            )

            # 5. Extract themes from sample titles/summaries
            themes = await self._extract_themes_from_sample(sample_articles)

            # Build corpus context
            state.corpus_context = {
                "stats": stats,
                "available_categories": [c.get("level") or c.get("name", "") for c in filter_options.get("bias", [])][:10],
                "available_sources": [s.get("name", "") for s in filter_options.get("sources", [])][:20],
                "available_factuality": [f.get("level", "") for f in filter_options.get("factuality", [])][:5],
                "sample_titles": [a.get("title", "")[:100] for a in sample_articles[:20]],
                "sample_summaries": [a.get("summary", "")[:200] for a in sample_articles[:10] if a.get("summary")],
                "themes": themes,
                "date_range": date_range,
                "sample_count": len(sample_articles)
            }

            logger.info(
                f"Exploration complete: {stats.get('total_articles', 0)} articles, "
                f"{len(themes)} themes, {len(sample_articles)} samples"
            )

        except Exception as e:
            logger.warning(f"Exploration stage failed (non-fatal): {e}")
            # Provide empty context - planning will still work
            state.corpus_context = {
                "stats": {"total_articles": 0},
                "available_categories": [],
                "available_sources": [],
                "sample_titles": [],
                "themes": [],
                "date_range": None
            }

    def _get_date_range_for_topic(self, topic: Optional[str]) -> Optional[Dict]:
        """Get the date range of articles for a topic."""
        try:
            # Get a few recent and old articles to estimate range
            recent = self.db.facade.get_recent_articles_by_topic(
                topic_name=topic,
                limit=1
            )
            oldest = self.db.facade.get_recent_articles_by_topic(
                topic_name=topic,
                limit=1,
                start_date=(datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d'),
                end_date=(datetime.now() - timedelta(days=300)).strftime('%Y-%m-%d')
            )

            if recent:
                newest_date = recent[0].get('publication_date') or recent[0].get('submission_date')
            else:
                newest_date = datetime.now().isoformat()

            if oldest:
                oldest_date = oldest[0].get('publication_date') or oldest[0].get('submission_date')
            else:
                oldest_date = (datetime.now() - timedelta(days=30)).isoformat()

            return {
                "newest": newest_date,
                "oldest": oldest_date
            }
        except Exception as e:
            logger.warning(f"Failed to get date range: {e}")
            return None

    async def _get_diverse_sample(
        self,
        topic: Optional[str],
        sample_size: int,
        strategy: str = "diversity"
    ) -> List[Dict]:
        """Get a diverse sample of articles to understand corpus content."""
        try:
            # Fetch more articles than needed for sampling
            raw_articles = self.db.facade.get_recent_articles_by_topic(
                topic_name=topic,
                limit=sample_size * 3
            )

            if not raw_articles:
                return []

            # Apply sampling strategy
            context = SamplingContext(topic=topic)

            if strategy == "topic_balanced" and topic is None:
                sampler = TopicBalancedSampling(min_per_topic=5)
            else:
                sampler = DiversitySampling()

            return sampler.sample(raw_articles, sample_size, context)

        except Exception as e:
            logger.warning(f"Failed to get diverse sample: {e}")
            return []

    async def _extract_themes_from_sample(self, articles: List[Dict]) -> List[str]:
        """Extract key themes from sample articles using LLM."""
        if not articles:
            return []

        try:
            # Build input from titles and summaries
            content_items = []
            for article in articles[:30]:
                title = article.get("title", "")
                summary = article.get("summary", "")[:200] if article.get("summary") else ""
                if title:
                    content_items.append(f"- {title}")
                    if summary:
                        content_items.append(f"  {summary}")

            if not content_items:
                return []

            content = "\n".join(content_items)

            response = await litellm.acompletion(
                **resolve_litellm_call_params("gpt-5.4-mini"),
                messages=[
                    {
                        "role": "system",
                        "content": """You are a content analyst. Extract 5-10 key themes/topics from these article titles and summaries.

Return a JSON object with a single "themes" array containing short theme phrases (2-4 words each).
Focus on specific entities, events, and topics - NOT abstract concepts like "news coverage" or "recent developments".

Example output: {"themes": ["Tesla electric vehicles", "Federal Reserve rates", "Ukraine conflict", "AI regulation", "Climate policy"]}"""
                    },
                    {
                        "role": "user",
                        "content": f"Extract themes from these articles:\n\n{content}"
                    }
                ],
                temperature=0.2,
                max_tokens=500,
                response_format={"type": "json_object"}
            )

            result = json.loads(response.choices[0].message.content)
            themes = result.get("themes", [])
            logger.info(f"Extracted {len(themes)} themes from sample")
            return themes

        except Exception as e:
            logger.warning(f"Theme extraction failed: {e}")
            return []

    async def _run_planning(self, state: ResearchState, config: ResearchConfig):
        """
        Stage 1: Planning
        Analyze query and create research objectives, search queries, and report outline.
        Now enhanced with corpus context from exploration stage.
        """
        planner_prompt = self._load_agent_prompt("research_planner")
        if not planner_prompt:
            planner_prompt = self._get_default_planner_prompt()

        # Inject corpus context into the prompt
        system_prompt = self._inject_corpus_context(planner_prompt, state)

        user_prompt = f"""Research Query: {state.query}
Topic Area: {state.topic}

Please analyze this query and create:
1. 3-5 specific research objectives
2. Targeted search queries for each objective
3. A report outline structure

Respond with valid JSON matching the expected schema."""

        try:
            response = await litellm.acompletion(
                **resolve_litellm_call_params(config.planning_model),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=config.planning_temperature,
                max_tokens=2000,
                response_format={"type": "json_object"}
            )

            result_text = response.choices[0].message.content
            result = json.loads(result_text)

            state.research_objectives = result.get("research_objectives", [])
            state.search_queries = result.get("search_queries", [])
            state.report_outline = result.get("report_outline", {})

            logger.info(f"Planning complete: {len(state.research_objectives)} objectives, {len(state.search_queries)} queries")

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse planning response: {e}")
            # Create default objectives from query
            state.research_objectives = [
                {"id": "obj_1", "objective": f"Analyze {state.query}", "priority": "high"}
            ]
            state.search_queries = [
                {"objective_id": "obj_1", "query": state.query, "search_type": "both"}
            ]

    async def _run_searching(
        self,
        state: ResearchState,
        config: ResearchConfig
    ) -> AsyncGenerator[Dict, None]:
        """
        Stage 2: Searching
        Execute PARALLEL multi-strategy search plus planner queries.
        Now uses 5+ search strategies concurrently for comprehensive coverage.
        """
        all_articles = []
        seen_urls = set()

        # Determine forced search source based on research mode config
        forced_source = None
        logger.info(f"Research config - search_source: {config.search_source}, research_mode: {config.research_mode}")
        if config.search_source == "internal":
            forced_source = SearchSource.VECTOR_DB
            logger.info("Forcing INTERNAL (VECTOR_DB) search only")
        elif config.search_source == "external":
            forced_source = SearchSource.EXTERNAL if config.allow_external_search else SearchSource.VECTOR_DB
            logger.info(f"Forcing EXTERNAL search (allow_external: {config.allow_external_search})")
        elif config.search_source == "hybrid":
            forced_source = SearchSource.HYBRID
            logger.info("Forcing HYBRID search (both internal and external)")

        # =====================================================
        # PHASE 1: PARALLEL MULTI-STRATEGY SEARCH (NEW)
        # Execute 5 strategies concurrently for comprehensive coverage
        # =====================================================
        yield {
            "status": "parallel_search",
            "progress": 0.1,
            "message": "Executing parallel multi-strategy search"
        }

        try:
            # Define parallel search strategies
            per_strategy_limit = config.articles_per_query

            strategies = [
                # Strategy 1: Semantic search using primary query
                self._search_semantic(state, config, per_strategy_limit),

                # Strategy 2: Temporal coverage (recent + historical)
                self._search_temporal(state, config, per_strategy_limit),

                # Strategy 3: Category diversity
                self._search_by_categories(state, config, per_strategy_limit // 2),

                # Strategy 4: High-credibility sources (bias/factuality data)
                self._search_quality_sources(state, config, per_strategy_limit // 2),

                # Strategy 5: Future signals (predictive content)
                self._search_future_signals(state, config, per_strategy_limit // 2),
            ]

            # Add cross-topic search if in single-topic mode (for related content)
            if state.topic:
                strategies.append(
                    self._search_cross_topic(state, config, per_strategy_limit // 3)
                )

            # Execute ALL strategies in parallel
            logger.info(f"Executing {len(strategies)} parallel search strategies with per_strategy_limit={per_strategy_limit}")
            strategy_results = await asyncio.gather(*strategies, return_exceptions=True)

            # Process parallel results
            strategy_names = ["semantic", "temporal", "category", "quality", "future_signals", "cross_topic"]
            strategy_stats = {}
            internal_from_parallel = 0
            for i, result in enumerate(strategy_results):
                strategy_name = strategy_names[i] if i < len(strategy_names) else f"strategy_{i}"
                if isinstance(result, Exception):
                    logger.warning(f"Search strategy '{strategy_name}' FAILED: {result}")
                    strategy_stats[strategy_name] = 0
                    continue

                articles = result if isinstance(result, list) else []
                strategy_stats[strategy_name] = len(articles)
                logger.info(f"Strategy '{strategy_name}' returned {len(articles)} articles (internal)")

                for article in articles:
                    url = article.get("url") or article.get("uri", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        article["_search_strategy"] = strategy_name
                        article["_source_type"] = "internal"
                        state.sources_used["internal"] += 1
                        all_articles.append(article)
                        internal_from_parallel += 1

            logger.info(f"Parallel strategies collected {len(all_articles)} unique INTERNAL articles")
            logger.info(f"Strategy stats: {strategy_stats}")

        except Exception as e:
            logger.warning(f"Parallel search phase failed: {e}")

        yield {
            "status": "parallel_search_complete",
            "progress": 0.4,
            "articles_from_parallel": len(all_articles),
            "internal_articles": internal_from_parallel,
            "strategy_stats": strategy_stats
        }

        # =====================================================
        # PHASE 2: PLANNER QUERY EXECUTION (ENHANCED)
        # Execute queries from research planner
        # PREFER INTERNAL when we already have good internal coverage
        # =====================================================
        total_queries = len(state.search_queries)
        if total_queries == 0:
            state.search_queries = [{"query": state.query, "search_type": "both"}]
            total_queries = 1

        # Determine if we should prefer internal search based on parallel results
        # If parallel strategies returned 150+ internal articles, prefer internal for planner queries
        prefer_internal = internal_from_parallel >= 150
        if prefer_internal:
            logger.info(f"Preferring INTERNAL search for planner queries (have {internal_from_parallel} internal articles)")

        for i, search_query in enumerate(state.search_queries):
            query_text = search_query.get("query", state.query)
            search_type = search_query.get("search_type", "both")

            # Calculate progress: parallel=0-0.4, queries=0.4-0.8, refinement=0.8-1.0
            query_progress = 0.4 + (0.4 * (i / total_queries))

            yield {
                "status": "searching",
                "progress": query_progress,
                "current_query": query_text,
                "query_index": i + 1,
                "total_queries": total_queries
            }

            try:
                source = forced_source
                if source is None:
                    # If we have enough internal articles, prefer internal search
                    if prefer_internal:
                        source = SearchSource.VECTOR_DB
                    elif search_type == "database":
                        source = SearchSource.VECTOR_DB
                    elif search_type == "external":
                        source = SearchSource.EXTERNAL if config.allow_external_search else SearchSource.VECTOR_DB
                    else:
                        source = None

                results = await self.search_router.execute_routed_search(
                    query=query_text,
                    topic=state.topic,
                    limit=config.articles_per_query,
                    force_source=source,
                    tools_service=self.tools
                )

                actual_source = results.get("source_used", results.get("source_type", "unknown"))

                for article in results.get("articles", []):
                    url = article.get("url") or article.get("uri", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        article["_objective_id"] = search_query.get("objective_id")
                        article["_search_strategy"] = "planner_query"

                        # Track source type
                        if actual_source == "vector_db":
                            article["_source_type"] = "internal"
                            state.sources_used["internal"] += 1
                        elif actual_source == "external":
                            article["_source_type"] = "external"
                            state.sources_used["external"] += 1
                        elif actual_source == "hybrid":
                            article_source = article.get("source_type")
                            if article_source == "database" or article.get("_from_vector_db"):
                                article["_source_type"] = "internal"
                                state.sources_used["internal"] += 1
                            else:
                                article["_source_type"] = "external"
                                state.sources_used["external"] += 1
                        else:
                            if config.search_source == "internal":
                                article["_source_type"] = "internal"
                                state.sources_used["internal"] += 1
                            elif article.get("source_type") == "database" or article.get("_from_vector_db"):
                                article["_source_type"] = "internal"
                                state.sources_used["internal"] += 1
                            else:
                                article["_source_type"] = "external"
                                state.sources_used["external"] += 1

                        all_articles.append(article)

                    if len(all_articles) >= config.max_articles * 1.5:
                        break

            except Exception as e:
                logger.warning(f"Search query failed: {query_text}: {e}")
                state.errors.append(f"Search failed: {query_text}")

        # =====================================================
        # PHASE 3: SMART SAMPLING (NEW - uses sampling framework)
        # Apply quality + diversity + semantic sampling to select best articles
        # =====================================================
        yield {
            "status": "smart_sampling",
            "progress": 0.85,
            "articles_before_sampling": len(all_articles)
        }

        if len(all_articles) > config.max_articles:
            original_count = len(all_articles)
            all_articles = await self._apply_smart_sampling(
                all_articles,
                config.max_articles,
                state
            )
            logger.info(f"Smart sampling reduced {original_count} -> {len(all_articles)} articles")

        # Store results
        state.raw_results = all_articles

        # Calculate source metadata
        sources = set()
        categories = set()
        sentiments = {}
        strategies_used = set()

        for article in all_articles:
            source = article.get("news_source") or article.get("source", "Unknown")
            sources.add(source)

            category = article.get("category", "Unknown")
            categories.add(category)

            sentiment = article.get("sentiment", "Unknown")
            sentiments[sentiment] = sentiments.get(sentiment, 0) + 1

            strategy = article.get("_search_strategy", "unknown")
            strategies_used.add(strategy)

        state.source_metadata = {
            "unique_sources": len(sources),
            "sources_list": list(sources)[:20],
            "categories": list(categories),
            "sentiment_distribution": sentiments,
            "total_articles": len(all_articles),
            "sources_used": state.sources_used,
            "search_strategies_used": list(strategies_used)
        }

        # =====================================================
        # PHASE 4: ITERATIVE REFINEMENT (EXISTING)
        # Fill gaps identified by coverage assessment
        # =====================================================
        if config.enable_refinement and len(state.raw_results) > 0:
            for iteration in range(config.max_refinement_iterations):
                yield {
                    "status": "refining",
                    "progress": 0.9 + (iteration * 0.05),
                    "iteration": iteration + 1,
                    "max_iterations": config.max_refinement_iterations,
                    "articles_so_far": len(state.raw_results)
                }

                try:
                    coverage = await self._assess_coverage(state, config)
                    overall_coverage = coverage.get("overall_coverage", 0)

                    logger.info(f"Refinement iteration {iteration + 1}: coverage = {overall_coverage:.1%}")

                    if overall_coverage >= config.min_coverage_threshold:
                        logger.info(f"Coverage threshold met ({overall_coverage:.1%} >= {config.min_coverage_threshold:.1%})")
                        break

                    refinement_queries = await self._generate_refinement_queries(state, coverage, config)

                    if not refinement_queries:
                        logger.info("No refinement queries generated")
                        break

                    for search_query in refinement_queries:
                        query_text = search_query.get("query", "")
                        search_type = search_query.get("search_type", "database")

                        try:
                            source = SearchSource.VECTOR_DB if search_type == "database" else None
                            results = await self.search_router.execute_routed_search(
                                query=query_text,
                                topic=state.topic,
                                limit=config.articles_per_query // 2,
                                force_source=source,
                                tools_service=self.tools
                            )

                            for article in results.get("articles", []):
                                url = article.get("url") or article.get("uri", "")
                                if url and url not in seen_urls:
                                    seen_urls.add(url)
                                    article["_objective_id"] = "refinement"
                                    article["_refinement_iteration"] = iteration + 1
                                    article["_search_strategy"] = "refinement"

                                    if article.get("source_type") == "database" or article.get("_from_vector_db"):
                                        article["_source_type"] = "internal"
                                        state.sources_used["internal"] += 1
                                    else:
                                        article["_source_type"] = "external"
                                        state.sources_used["external"] += 1

                                    state.raw_results.append(article)

                        except Exception as e:
                            logger.warning(f"Refinement query failed: {query_text}: {e}")

                except Exception as e:
                    logger.warning(f"Refinement iteration {iteration + 1} failed: {e}")
                    break

        yield {
            "status": "completed",
            "progress": 1.0,
            "articles_found": len(state.raw_results),
            "unique_sources": len(sources),
            "sources_used": state.sources_used,
            "search_strategies_used": list(strategies_used)
        }

    # =====================================================
    # PARALLEL SEARCH STRATEGY METHODS
    # =====================================================

    async def _search_semantic(self, state: ResearchState, config: ResearchConfig, limit: int) -> List[Dict]:
        """Strategy 1: Vector search for semantic relevance."""
        try:
            from app.vector_store import search_articles_async

            # Normalize topic - convert '__all__' to None for cross-topic mode
            normalized_topic = self._normalize_topic(state.topic)
            metadata_filter = {"topic": normalized_topic} if normalized_topic else {}

            results = await search_articles_async(
                query=state.query,
                top_k=limit,
                metadata_filter=metadata_filter
            )

            # Convert to standard article format
            articles = []
            for result in results:
                article = result.get("metadata", {})
                article["similarity_score"] = result.get("score", 0)
                article["_from_vector_db"] = True
                # Ensure url is set for deduplication (vector store uses 'uri')
                if not article.get("url") and article.get("uri"):
                    article["url"] = article["uri"]
                articles.append(article)

            logger.info(f"Semantic search returned {len(articles)} articles from vector store")
            return articles

        except Exception as e:
            logger.warning(f"Semantic search failed: {e}")
            return []

    async def _search_temporal(self, state: ResearchState, config: ResearchConfig, limit: int) -> List[Dict]:
        """Strategy 2: Stratified temporal search - recent + historical."""
        try:
            articles = []

            # Normalize topic - convert '__all__' to None for cross-topic mode
            normalized_topic = self._normalize_topic(state.topic)

            # Recent articles (last 7 days)
            recent_limit = int(limit * config.temporal_distribution_recent)
            recent = self.db.facade.get_recent_articles_by_topic(
                topic_name=normalized_topic,
                limit=recent_limit,
                start_date=(datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
            )
            articles.extend(recent)

            # Medium-term articles (8-30 days)
            medium_limit = int(limit * config.temporal_distribution_medium)
            medium = self.db.facade.get_recent_articles_by_topic(
                topic_name=normalized_topic,
                limit=medium_limit,
                start_date=(datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'),
                end_date=(datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
            )
            articles.extend(medium)

            # Historical context (31-90 days)
            older_limit = int(limit * config.temporal_distribution_older)
            older = self.db.facade.get_recent_articles_by_topic(
                topic_name=normalized_topic,
                limit=older_limit,
                start_date=(datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d'),
                end_date=(datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
            )
            articles.extend(older)

            # Ensure url is set for deduplication (database uses 'uri')
            for article in articles:
                if not article.get("url") and article.get("uri"):
                    article["url"] = article["uri"]
                article["_from_vector_db"] = True

            logger.info(f"Temporal search returned {len(articles)} articles")
            return articles

        except Exception as e:
            logger.warning(f"Temporal search failed: {e}")
            return []

    async def _search_by_categories(self, state: ResearchState, config: ResearchConfig, limit: int) -> List[Dict]:
        """Strategy 3: Search across available categories for diversity."""
        try:
            # Normalize topic - convert '__all__' to None for cross-topic mode
            normalized_topic = self._normalize_topic(state.topic)

            filter_options = self.db.facade.get_article_filter_options(topic=normalized_topic)
            bias_levels = [b.get("level") for b in filter_options.get("bias", []) if b.get("level")][:5]

            if not bias_levels:
                logger.info("No bias levels found for category search")
                return []

            articles = []
            per_category = max(1, limit // len(bias_levels))

            for bias in bias_levels:
                try:
                    category_articles, _ = self.db.facade.search_articles(
                        topic=normalized_topic,
                        category=[bias],
                        per_page=per_category
                    )
                    articles.extend(category_articles)
                except Exception as e:
                    logger.debug(f"Category search for '{bias}' failed: {e}")

            # Ensure url is set for deduplication
            for article in articles:
                if not article.get("url") and article.get("uri"):
                    article["url"] = article["uri"]
                article["_from_vector_db"] = True

            logger.info(f"Category search returned {len(articles)} articles")
            return articles

        except Exception as e:
            logger.warning(f"Category search failed: {e}")
            return []

    async def _search_quality_sources(self, state: ResearchState, config: ResearchConfig, limit: int) -> List[Dict]:
        """Strategy 4: Search for high-credibility articles with bias data."""
        try:
            # Normalize topic - convert '__all__' to None for cross-topic mode
            normalized_topic = self._normalize_topic(state.topic)

            articles = self.db.facade.get_articles_with_bias_data(
                topic_name=normalized_topic,
                limit=limit,
                days_back=30
            )

            # Ensure url is set for deduplication
            for article in articles:
                if not article.get("url") and article.get("uri"):
                    article["url"] = article["uri"]
                article["_from_vector_db"] = True

            logger.info(f"Quality sources search returned {len(articles)} articles")
            return articles

        except Exception as e:
            logger.warning(f"Quality sources search failed: {e}")
            return []

    async def _search_future_signals(self, state: ResearchState, config: ResearchConfig, limit: int) -> List[Dict]:
        """Strategy 5: Get articles with future/predictive signals."""
        try:
            # Normalize topic - convert '__all__' to None for cross-topic mode
            normalized_topic = self._normalize_topic(state.topic)

            articles = self.db.facade.get_articles_with_future_signals(
                topic_name=normalized_topic,
                limit=limit,
                days_back=30
            )

            # Ensure url is set for deduplication
            for article in articles:
                if not article.get("url") and article.get("uri"):
                    article["url"] = article["uri"]
                article["_from_vector_db"] = True

            logger.info(f"Future signals search returned {len(articles)} articles")
            return articles

        except Exception as e:
            logger.warning(f"Future signals search failed: {e}")
            return []

    async def _search_cross_topic(self, state: ResearchState, config: ResearchConfig, limit: int) -> List[Dict]:
        """Strategy 6: Search across ALL topics for related content."""
        try:
            # Search cross-topic (topic_name=None)
            articles = self.db.facade.get_recent_articles_by_topic(
                topic_name=None,  # Cross-topic mode
                limit=limit,
                start_date=(datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d')
            )

            # Ensure url is set and mark as cross-topic
            for article in articles:
                if not article.get("url") and article.get("uri"):
                    article["url"] = article["uri"]
                article["_cross_topic"] = True
                article["_from_vector_db"] = True

            logger.info(f"Cross-topic search returned {len(articles)} articles")
            return articles

        except Exception as e:
            logger.warning(f"Cross-topic search failed: {e}")
            return []

    async def _apply_smart_sampling(
        self,
        articles: List[Dict],
        limit: int,
        state: ResearchState
    ) -> List[Dict]:
        """Apply sophisticated sampling to select best articles."""
        try:
            context = SamplingContext(topic=state.topic, query=state.query)
            context.update_stats(articles)

            # Store similarity scores in context for semantic sampling
            for article in articles:
                article_id = str(article.get('id') or article.get('uri', ''))
                if article.get('similarity_score'):
                    context.similarity_scores[article_id] = article['similarity_score']

            # Use composite sampling: semantic + quality + diversity
            if state.topic is None:
                # Cross-topic mode: prioritize topic balance
                sampler = CompositeSampling([
                    (TopicBalancedSampling(min_per_topic=5), 0.4),
                    (SemanticSampling(), 0.3),
                    (DiversitySampling(), 0.3),
                ])
            else:
                # Single topic mode: semantic relevance + quality + diversity
                sampler = CompositeSampling([
                    (SemanticSampling(), 0.4),
                    (QualitySampling(), 0.35),
                    (DiversitySampling(), 0.25),
                ])

            return sampler.sample(articles, limit, context)

        except Exception as e:
            logger.warning(f"Smart sampling failed, using simple truncation: {e}")
            return articles[:limit]

    async def _run_synthesis(
        self,
        state: ResearchState,
        config: ResearchConfig
    ) -> AsyncGenerator[Dict, None]:
        """
        Stage 3: Synthesis (Batched with Progress)
        Analyze findings in batches, resolve contradictions, assess confidence.
        Yields progress updates after each batch.
        """
        synthesizer_prompt = self._load_agent_prompt("research_synthesizer")
        if not synthesizer_prompt:
            synthesizer_prompt = self._get_default_synthesizer_prompt()

        # Prepare article summaries for synthesis with RICH METADATA
        # Prioritize enriched articles (those with category, sentiment, future_signal)
        synthesis_limit = min(200, len(state.raw_results))  # Increased limit for batched processing

        # Sort to prioritize enriched articles
        enriched_articles = []
        basic_articles = []
        for article in state.raw_results:
            has_category = article.get("category") and article.get("category") not in ("Uncategorized", "Unknown", "", None)
            has_sentiment = article.get("sentiment") and article.get("sentiment") not in ("Unknown", "", None)
            has_future_signal = article.get("future_signal") and article.get("future_signal") not in ("", None)
            has_summary = article.get("summary") and len(article.get("summary", "")) > 50

            if (has_category or has_sentiment or has_future_signal) and has_summary:
                enriched_articles.append(article)
            else:
                basic_articles.append(article)

        # Prioritize enriched articles, then add basic ones if needed
        prioritized_articles = enriched_articles[:synthesis_limit]
        if len(prioritized_articles) < synthesis_limit:
            remaining = synthesis_limit - len(prioritized_articles)
            prioritized_articles.extend(basic_articles[:remaining])

        logger.info(f"Synthesis: {len(enriched_articles)} enriched articles, {len(basic_articles)} basic articles")

        # Build global metadata stats from ALL prioritized articles
        metadata_stats = {
            "sentiment_counts": {},
            "category_counts": {},
            "future_signals": [],
            "time_impacts": []
        }

        article_summaries = []
        for i, article in enumerate(prioritized_articles):
            # Track metadata stats
            sentiment = article.get("sentiment", "Unknown")
            metadata_stats["sentiment_counts"][sentiment] = metadata_stats["sentiment_counts"].get(sentiment, 0) + 1

            category = article.get("category", "Uncategorized")
            metadata_stats["category_counts"][category] = metadata_stats["category_counts"].get(category, 0) + 1

            if article.get("future_signal"):
                metadata_stats["future_signals"].append({
                    "signal": article.get("future_signal"),
                    "time_to_impact": article.get("time_to_impact", "Unknown"),
                    "source": article.get("news_source") or article.get("source", "Unknown"),
                    "title": article.get("title", "")[:100]
                })

            if article.get("time_to_impact"):
                metadata_stats["time_impacts"].append(article.get("time_to_impact"))

            summary = {
                "index": i + 1,
                "title": article.get("title", "Untitled"),
                "source": article.get("news_source") or article.get("source", "Unknown"),
                "date": article.get("publication_date", "Unknown"),
                "sentiment": sentiment,
                "category": category,
                "future_signal": article.get("future_signal", ""),
                "time_to_impact": article.get("time_to_impact", ""),
                "credibility": article.get("credibility_score", 50),
                "summary": (article.get("summary") or article.get("content", ""))[:500],
                "url": article.get("url") or article.get("uri", ""),
                "objective_id": article.get("_objective_id"),
                "is_enriched": article in enriched_articles
            }
            article_summaries.append(summary)

        # Store metadata_stats in state for writer to use
        state.source_metadata["metadata_stats"] = metadata_stats

        # Split into batches
        batch_size = config.synthesis_batch_size
        batches = [article_summaries[i:i + batch_size] for i in range(0, len(article_summaries), batch_size)]
        total_batches = len(batches)

        logger.info(f"Processing {len(article_summaries)} articles in {total_batches} batches of {batch_size}")

        yield {
            "status": "batching",
            "progress": 0.0,
            "total_articles": len(article_summaries),
            "total_batches": total_batches,
            "batch_size": batch_size
        }

        # Build date context header
        current_date = datetime.now().strftime("%B %d, %Y")
        current_year = datetime.now().year

        date_context = f"""**TODAY'S DATE: {current_date} | CURRENT YEAR: {current_year}**

⚠️ CRITICAL: Article content reflects CURRENT reality. Your training data is OUTDATED.
- Donald Trump IS the current US President (elected November 2024, inaugurated January 2025)
- Joe Biden is the FORMER president
- Accept what articles say about current events, office holders, and policies as FACT
- Do NOT "correct" article content based on your training knowledge

---"""

        # Process batches and collect results
        batch_results = []
        all_key_points = []
        all_contradictions = []

        for batch_idx, batch in enumerate(batches):
            batch_num = batch_idx + 1
            progress = batch_num / total_batches

            yield {
                "status": "synthesizing_batch",
                "progress": progress * 0.9,  # Reserve 10% for final merge
                "current_batch": batch_num,
                "total_batches": total_batches,
                "articles_in_batch": len(batch),
                "message": f"Synthesizing batch {batch_num}/{total_batches} ({len(batch)} articles)"
            }

            # Build batch-specific prompt with article indices for citation mapping
            batch_prompt = f"""{date_context}

Research Query: {state.query}
Topic: {state.topic}

Research Objectives:
{json.dumps(state.research_objectives, indent=2)}

## GLOBAL METADATA (from all {len(article_summaries)} articles)

Sentiment Distribution:
{json.dumps(metadata_stats["sentiment_counts"], indent=2)}

Category Distribution:
{json.dumps(metadata_stats["category_counts"], indent=2)}

## BATCH {batch_num}/{total_batches} - Articles {batch[0]['index']} to {batch[-1]['index']}:

IMPORTANT: Each article has an "index" number, "title", and "url". Use these for citations!

{json.dumps(batch, indent=2)}

Extract 5-10 KEY FINDINGS from this batch. For each finding:
1. Identify which research objective it relates to
2. Extract specific facts, statistics, or direct quotes
3. CRITICAL: Include the article index numbers that support this finding
4. Note the article titles for citation

Respond with valid JSON:
{{
  "batch_findings": [
    {{
      "objective_id": "obj_1",
      "finding": "Specific finding with concrete details",
      "evidence": "Direct quote or specific statistic from the article",
      "article_indices": [1, 3, 7],
      "article_titles": ["Title of Article 1", "Title of Article 3"],
      "confidence": "high"
    }}
  ],
  "key_statistics": [
    {{
      "statistic": "$500 million military base planned",
      "article_index": 2,
      "article_title": "US plans to establish..."
    }}
  ],
  "contradictions": [
    {{
      "topic": "What the contradiction is about",
      "finding_a": "One perspective (Article X)",
      "finding_b": "Contradicting perspective (Article Y)"
    }}
  ],
  "batch_summary": "2-3 sentence summary of key themes in this batch"
}}"""

            try:
                response = await asyncio.wait_for(
                    litellm.acompletion(
                        **resolve_litellm_call_params(config.synthesis_model),
                        messages=[
                            {"role": "system", "content": synthesizer_prompt},
                            {"role": "user", "content": batch_prompt}
                        ],
                        temperature=config.synthesis_temperature,
                        max_tokens=3000,  # Increased for richer findings with citations
                        response_format={"type": "json_object"}
                    ),
                    timeout=config.synthesis_batch_timeout
                )

                result_text = response.choices[0].message.content
                batch_result = json.loads(result_text)
                batch_results.append(batch_result)

                # Collect findings with full data
                for finding in batch_result.get("batch_findings", []):
                    # Preserve all data including article indices for citation mapping
                    all_key_points.append({
                        "objective_id": finding.get("objective_id", "general"),
                        "finding": finding.get("finding", ""),
                        "evidence": finding.get("evidence", ""),
                        "article_indices": finding.get("article_indices", []),
                        "article_titles": finding.get("article_titles", []),
                        "confidence": finding.get("confidence", "medium")
                    })

                # Collect key statistics
                for stat in batch_result.get("key_statistics", []):
                    all_key_points.append({
                        "objective_id": "statistics",
                        "finding": stat.get("statistic", ""),
                        "evidence": stat.get("statistic", ""),
                        "article_indices": [stat.get("article_index")] if stat.get("article_index") else [],
                        "article_titles": [stat.get("article_title", "")],
                        "confidence": "high"
                    })

                # Collect contradictions
                for contradiction in batch_result.get("contradictions", []):
                    all_contradictions.append(contradiction)

                # Collect batch summaries
                if batch_result.get("batch_summary"):
                    batch_results.append({
                        "batch_num": batch_num,
                        "summary": batch_result.get("batch_summary"),
                        "findings_count": len(batch_result.get("batch_findings", []))
                    })

                logger.info(f"Batch {batch_num}/{total_batches} complete: {len(batch_result.get('batch_findings', []))} findings, {len(batch_result.get('key_statistics', []))} statistics")

            except asyncio.TimeoutError:
                logger.warning(f"Batch {batch_num} timed out, continuing with partial results")
                yield {
                    "status": "batch_timeout",
                    "progress": progress * 0.9,
                    "current_batch": batch_num,
                    "message": f"Batch {batch_num} timed out, continuing..."
                }
            except json.JSONDecodeError as e:
                logger.warning(f"Batch {batch_num} JSON parse error: {e}")
            except Exception as e:
                logger.warning(f"Batch {batch_num} failed: {e}")

        # Final merge phase
        yield {
            "status": "merging",
            "progress": 0.95,
            "message": f"Merging {len(batch_results)} batch results"
        }

        # Merge batch results into final synthesis
        await self._merge_synthesis_results(state, config, all_key_points, all_contradictions, metadata_stats)

        logger.info(f"Synthesis complete: {len(state.synthesized_findings)} findings from {total_batches} batches")

        yield {
            "status": "completed",
            "progress": 1.0,
            "total_findings": len(all_key_points),
            "contradictions_found": len(all_contradictions)
        }

    async def _merge_synthesis_results(
        self,
        state: ResearchState,
        config: ResearchConfig,
        all_key_points: List[Dict],
        all_contradictions: List[Dict],
        metadata_stats: Dict
    ):
        """Merge batch synthesis results into final coherent findings with citation data."""

        # Build article index to reference mapping for citations
        article_refs = {}
        for i, article in enumerate(state.raw_results[:200]):
            article_refs[i + 1] = {
                "title": article.get("title", "Untitled"),
                "url": article.get("url") or article.get("uri", ""),
                "source": article.get("news_source") or article.get("source", "Unknown")
            }

        # Group findings by objective with FULL DATA preservation
        findings_by_objective = {}
        for finding in all_key_points:
            obj_id = finding.get("objective_id", "general")
            if obj_id not in findings_by_objective:
                findings_by_objective[obj_id] = {
                    "findings": [],  # Full finding objects
                    "article_indices": set(),
                    "confidence_scores": []
                }

            # Build citable finding with article references
            citable_finding = {
                "finding": finding.get("finding", ""),
                "evidence": finding.get("evidence", ""),
                "citations": []
            }

            # Map article indices to actual references
            for idx in finding.get("article_indices", []):
                if idx in article_refs:
                    ref = article_refs[idx]
                    citable_finding["citations"].append({
                        "title": ref["title"],
                        "url": ref["url"],
                        "source": ref["source"]
                    })
                    findings_by_objective[obj_id]["article_indices"].add(idx)

            # Also try to match by title if indices not available
            for title in finding.get("article_titles", []):
                for idx, ref in article_refs.items():
                    if title and title.lower() in ref["title"].lower():
                        if not any(c["title"] == ref["title"] for c in citable_finding["citations"]):
                            citable_finding["citations"].append({
                                "title": ref["title"],
                                "url": ref["url"],
                                "source": ref["source"]
                            })
                            findings_by_objective[obj_id]["article_indices"].add(idx)
                        break

            findings_by_objective[obj_id]["findings"].append(citable_finding)

            conf = finding.get("confidence", "medium")
            findings_by_objective[obj_id]["confidence_scores"].append(
                {"high": 1.0, "medium": 0.6, "low": 0.3}.get(conf, 0.5)
            )

        # Build rich synthesized findings structure
        synthesized = {}
        for obj_id, data in findings_by_objective.items():
            avg_confidence = sum(data["confidence_scores"]) / len(data["confidence_scores"]) if data["confidence_scores"] else 0.5
            confidence_label = "high" if avg_confidence > 0.7 else "medium" if avg_confidence > 0.4 else "low"

            # Build key points with inline citation hints
            key_points_with_citations = []
            for f in data["findings"][:15]:  # Limit to 15 per objective
                if f["citations"]:
                    # Format: "Finding text [Citation Title](URL)"
                    citation_str = f["finding"]
                    if f["evidence"] and f["evidence"] != f["finding"]:
                        citation_str += f" Evidence: {f['evidence']}"
                    for c in f["citations"][:2]:  # Max 2 citations per finding
                        citation_str += f" [{c['title'][:60]}]({c['url']})"
                    key_points_with_citations.append(citation_str)
                else:
                    key_points_with_citations.append(f["finding"])

            synthesized[obj_id] = {
                "summary": f"Analysis based on {len(data['findings'])} findings from {len(data['article_indices'])} articles",
                "key_points": key_points_with_citations,
                "findings_with_citations": data["findings"][:15],
                "article_count": len(data["article_indices"]),
                "confidence": confidence_label
            }

        # Add metadata analysis with sentiment and future signals
        synthesized["metadata_analysis"] = {
            "sentiment_distribution": metadata_stats["sentiment_counts"],
            "sentiment_summary": self._summarize_sentiment(metadata_stats["sentiment_counts"]),
            "future_signals": metadata_stats["future_signals"][:20],
            "future_signals_by_timeline": self._group_signals_by_timeline(metadata_stats["future_signals"]),
            "category_insights": {
                "dominant_categories": sorted(
                    metadata_stats["category_counts"].items(),
                    key=lambda x: x[1],
                    reverse=True
                )[:5]
            }
        }

        state.synthesized_findings = synthesized

        # Build credibility assessment
        all_article_indices = set()
        for data in findings_by_objective.values():
            all_article_indices.update(data["article_indices"])

        state.credibility_assessment = {
            "overall_confidence": "high" if len(all_article_indices) > 30 else "medium" if len(all_article_indices) > 15 else "low",
            "reliability_score": min(1.0, len(all_article_indices) / 50),
            "source_diversity": {
                "unique_articles_cited": len(all_article_indices),
                "sentiment_balance": metadata_stats["sentiment_counts"]
            },
            "contradictions": all_contradictions[:5]
        }

    def _summarize_sentiment(self, sentiment_counts: Dict) -> str:
        """Generate a human-readable sentiment summary."""
        total = sum(sentiment_counts.values())
        if total == 0:
            return "No sentiment data available"

        positive = sentiment_counts.get("Positive", 0)
        negative = sentiment_counts.get("Negative", 0)
        neutral = sentiment_counts.get("Neutral", 0)

        pos_pct = (positive / total) * 100
        neg_pct = (negative / total) * 100
        neu_pct = (neutral / total) * 100

        if pos_pct > neg_pct + 20:
            tone = "predominantly positive"
        elif neg_pct > pos_pct + 20:
            tone = "predominantly negative"
        elif neu_pct > 50:
            tone = "mostly neutral"
        else:
            tone = "mixed"

        return f"Coverage is {tone}: {pos_pct:.0f}% positive, {neg_pct:.0f}% negative, {neu_pct:.0f}% neutral across {total} articles"

    def _group_signals_by_timeline(self, signals: List[Dict]) -> Dict:
        """Group future signals by time to impact."""
        grouped = {
            "immediate": [],  # days to weeks
            "short_term": [],  # 1-3 months
            "medium_term": [],  # 3-6 months
            "long_term": []  # 6+ months
        }

        for signal in signals:
            # Handle None values - use empty string if time_to_impact is None
            time_impact = (signal.get("time_to_impact") or "").lower()
            if any(x in time_impact for x in ["immediate", "days", "week", "imminent"]):
                grouped["immediate"].append(signal)
            elif any(x in time_impact for x in ["1-3 month", "month", "weeks"]):
                grouped["short_term"].append(signal)
            elif any(x in time_impact for x in ["3-6 month", "quarter"]):
                grouped["medium_term"].append(signal)
            else:
                grouped["long_term"].append(signal)

        return grouped

    async def _run_writing(
        self,
        state: ResearchState,
        config: ResearchConfig
    ) -> AsyncGenerator[Dict, None]:
        """
        Stage 4: Writing
        Produce the final research report with source attribution.
        """
        writer_prompt = self._load_agent_prompt("report_writer")
        if not writer_prompt:
            writer_prompt = self._get_default_writer_prompt()

        # Build context for writing
        system_prompt = writer_prompt

        # Prepare article references for citations with source type
        # Increased from 30 to 100 for more comprehensive citations
        citation_limit = min(100, len(state.raw_results))
        article_refs = []
        for i, article in enumerate(state.raw_results[:citation_limit]):
            ref = {
                "id": i + 1,
                "title": article.get("title", "Untitled"),
                "source": article.get("news_source") or article.get("source", "Unknown"),
                "url": article.get("url") or article.get("uri", ""),
                "date": article.get("publication_date", ""),
                "source_type": article.get("_source_type", "unknown")  # internal or external
            }
            article_refs.append(ref)

        # Build source summary header
        internal_count = state.sources_used.get("internal", 0)
        external_count = state.sources_used.get("external", 0)
        source_summary = f"Sources: {internal_count} internal, {external_count} external"

        # Build sentiment and future signals data for the writer
        sentiment_dist = state.source_metadata.get('sentiment_distribution', {})

        # Extract future signals from raw results
        future_signals_data = []
        for article in state.raw_results[:100]:
            if article.get("future_signal"):
                future_signals_data.append({
                    "signal": article.get("future_signal"),
                    "time_to_impact": article.get("time_to_impact", "Unknown"),
                    "source": article.get("news_source") or article.get("source", "Unknown"),
                    "title": article.get("title", "")[:80]
                })

        # Build date context header for the user prompt
        current_date_writer = datetime.now().strftime("%B %d, %Y")
        current_year_writer = datetime.now().year

        # Get metadata analysis from synthesized findings
        metadata_analysis = state.synthesized_findings.get("metadata_analysis", {})
        sentiment_summary = metadata_analysis.get("sentiment_summary", "No sentiment data available")
        signals_by_timeline = metadata_analysis.get("future_signals_by_timeline", {})

        # DEBUG LOGGING - See what data we actually have
        logger.info(f"=== WRITER DATA DEBUG ===")
        logger.info(f"synthesized_findings keys: {list(state.synthesized_findings.keys())}")
        logger.info(f"sentiment_dist: {sentiment_dist}")
        logger.info(f"sentiment_summary: {sentiment_summary}")
        logger.info(f"signals_by_timeline counts: immediate={len(signals_by_timeline.get('immediate', []))}, short={len(signals_by_timeline.get('short_term', []))}, medium={len(signals_by_timeline.get('medium_term', []))}, long={len(signals_by_timeline.get('long_term', []))}")
        logger.info(f"future_signals_data count: {len(future_signals_data)}")
        logger.info(f"article_refs count: {len(article_refs)}")
        logger.info(f"article_refs[0] sample: {article_refs[0] if article_refs else 'EMPTY'}")
        logger.info(f"=== END DEBUG ===")

        # Build pre-structured citation reference list
        citation_list = []
        for i, ref in enumerate(article_refs[:75]):
            citation_list.append(f"[{i+1}] \"{ref['title']}\" - {ref['url']} *({ref.get('source_type', 'internal')})*")

        # Build findings sections from synthesized data
        findings_sections = []
        for obj_id, obj_data in state.synthesized_findings.items():
            if obj_id == "metadata_analysis":
                continue
            if isinstance(obj_data, dict) and "key_points" in obj_data:
                # Make nicer section titles
                if obj_id.startswith("obj_"):
                    # Try to get objective name from research_objectives
                    obj_idx = int(obj_id.split("_")[1]) - 1 if obj_id.split("_")[1].isdigit() else 0
                    if obj_idx < len(state.research_objectives):
                        section_title = state.research_objectives[obj_idx].get("objective", obj_id)[:80]
                    else:
                        section_title = f"Research Finding {obj_id.split('_')[1]}"
                elif obj_id == "general":
                    section_title = "General Findings"
                elif obj_id == "statistics":
                    section_title = "Key Statistics"
                else:
                    section_title = obj_id.replace('_', ' ').title()

                section = f"### {section_title}\n"
                for point in obj_data.get("key_points", [])[:8]:
                    section += f"- {point}\n"
                findings_sections.append(section)
                logger.info(f"Built findings section '{section_title}' with {len(obj_data.get('key_points', []))} points")

        # Build future signals by timeline
        immediate_signals = signals_by_timeline.get("immediate", [])[:5]
        short_term_signals = signals_by_timeline.get("short_term", [])[:5]
        medium_term_signals = signals_by_timeline.get("medium_term", [])[:5]
        long_term_signals = signals_by_timeline.get("long_term", [])[:5]

        user_prompt = f"""**TODAY'S DATE: {current_date_writer} | CURRENT YEAR: {current_year_writer}**

⚠️ Your training data is OUTDATED. Article content reflects CURRENT {current_year_writer} reality:
- Donald Trump IS the current US President (inaugurated January 2025)
- Accept all article content as factual current events

---

# WRITE A COMPLETE RESEARCH REPORT

**Research Query:** {state.query}
**Topic:** {state.topic}
**Sources:** {internal_count} internal articles, {external_count} external articles

---

## YOUR REPORT MUST HAVE EXACTLY THESE 9 SECTIONS:

### 1. EXECUTIVE SUMMARY (write 3-4 paragraphs)
Summarize key findings. Include forward-looking predictions.

### 2. METHODOLOGY (write 1-2 paragraphs)
- Analyzed {len(state.raw_results)} articles ({internal_count} internal, {external_count} external)
- Search strategies: {', '.join(state.source_metadata.get('search_strategies_used', ['semantic', 'temporal']))}
- Categories covered: {', '.join(c for c in state.source_metadata.get('categories', [])[:8] if c)}

### 3. KEY FINDINGS (write 4-6 subsections with citations)
Use these findings - ADD CITATIONS from the reference list below:

{chr(10).join(findings_sections) if findings_sections else "Analyze the synthesized findings to identify key themes and patterns."}

### 4. SENTIMENT ANALYSIS (REQUIRED - write 2-3 paragraphs)
**You MUST include this section.** Use this data:

Sentiment Distribution: {json.dumps(sentiment_dist, indent=2)}

Summary: {sentiment_summary}

Discuss: What does this sentiment distribution reveal? Are there concerning trends?

### 5. FORWARD-LOOKING SIGNALS (REQUIRED - write 2-3 paragraphs with subsections)
**You MUST include this section.** Categorize predictions by timeline:

**Immediate (days to weeks):**
{json.dumps(immediate_signals, indent=2) if immediate_signals else "No immediate signals identified"}

**Short-term (1-3 months):**
{json.dumps(short_term_signals, indent=2) if short_term_signals else "No short-term signals identified"}

**Medium-term (3-6 months):**
{json.dumps(medium_term_signals, indent=2) if medium_term_signals else "No medium-term signals identified"}

**Long-term (6+ months):**
{json.dumps(long_term_signals, indent=2) if long_term_signals else "No long-term signals identified"}

### 6. DETAILED ANALYSIS (write 3-4 paragraphs)
Cross-reference findings with predictions. Identify patterns and implications.

### 7. CONCLUSIONS (write 2-3 paragraphs)
Actionable recommendations based on findings. Frame every recommendation as an action the reader/commissioning organization can take within its own remit; do NOT issue directives to governments, regulators, health authorities, or other third parties the reader does not control.

### 8. LIMITATIONS (write 1-2 paragraphs)
Data gaps, potential biases, confidence levels.

### 9. REFERENCES (list ALL cited sources)
Include at least 20 references with full URLs. Format: "[N] Title - URL *(internal)* or *(web)*"

---

## CITATION REFERENCE LIST (use these for inline citations)
Format inline citations as: [Article Title](URL)

{chr(10).join(citation_list[:50])}

---

## CREDIBILITY DATA
{json.dumps(state.credibility_assessment, indent=2)}

---

**INSTRUCTIONS:**
1. Write ALL 9 sections in order
2. Each section must have a ## heading
3. Use [Article Title](URL) format for EVERY claim
4. The References section must list 20+ sources with full URLs
5. Make the report comprehensive - at least 2000 words total"""

        # Stream the response
        report_chunks = []

        # FIXED: Correct async streaming pattern for litellm
        response = await litellm.acompletion(
            **resolve_litellm_call_params(config.writing_model),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=config.writing_temperature,
            max_tokens=12000,  # Increased for comprehensive 9-section reports
            stream=True
        )
        async for chunk in response:
            content = chunk.choices[0].delta.content or ""
            report_chunks.append(content)

            # Estimate progress based on content length
            current_length = sum(len(c) for c in report_chunks)
            estimated_total = 5000  # Rough estimate
            progress = min(0.95, current_length / estimated_total)

            yield {
                "status": "writing",
                "progress": progress,
                "chunk": content
            }

        raw_report = "".join(report_chunks)

        # Post-process to add source attribution if not already present
        state.final_report = self._add_source_attribution(raw_report, article_refs, state)

        # Add chart if include_charts is enabled
        if config.include_charts and state.raw_results:
            chart_marker = self._generate_chart_for_report(state.raw_results, state.topic)
            if chart_marker:
                # Insert chart at the beginning of the report (after title)
                lines = state.final_report.split('\n', 2)
                if len(lines) >= 2:
                    state.final_report = lines[0] + '\n' + lines[1] + '\n\n' + chart_marker + '\n\n' + (lines[2] if len(lines) > 2 else '')
                else:
                    state.final_report = chart_marker + '\n\n' + state.final_report
                logger.info(f"Added chart to research report (include_charts={config.include_charts})")

        yield {
            "status": "completed",
            "progress": 1.0,
            "report_length": len(state.final_report),
            "sources_used": state.sources_used
        }

    def _add_source_attribution(self, report: str, article_refs: List[Dict], state: ResearchState) -> str:
        """
        Post-process report to ensure source attribution in References section.
        Adds *(internal)* or *(web)* after each reference if not already present.
        """
        import re

        # Find the References section
        references_match = re.search(r'(##?\s*References?.*?)($|\n##)', report, re.IGNORECASE | re.DOTALL)
        if not references_match:
            # No references section found, add source summary at the end
            internal_count = state.sources_used.get("internal", 0)
            external_count = state.sources_used.get("external", 0)
            source_header = f"\n\n---\n**Sources:** {internal_count} internal, {external_count} external\n"
            return report + source_header

        references_section = references_match.group(1)
        before_refs = report[:references_match.start()]
        after_refs = report[references_match.end():]
        if references_match.group(2) == '\n##':
            after_refs = '\n##' + after_refs

        # Build URL to source type mapping
        url_to_source_type = {}
        domain_to_source_type = {}  # Fallback: map domains to source types

        for ref in article_refs:
            url = ref.get("url", "")
            if url:
                url_to_source_type[url] = ref.get("source_type", "unknown")
                # Also extract domain for fallback matching
                domain_match = re.search(r'https?://([^/]+)', url)
                if domain_match:
                    domain = domain_match.group(1)
                    # Only set domain mapping if we have a definite source type
                    if ref.get("source_type") in ["internal", "external"]:
                        domain_to_source_type[domain] = ref.get("source_type")

        # Also check raw_results for more complete mapping
        for article in state.raw_results:
            url = article.get("url") or article.get("uri", "")
            if url:
                if url not in url_to_source_type:
                    url_to_source_type[url] = article.get("_source_type", "unknown")
                # Extract domain for fallback
                domain_match = re.search(r'https?://([^/]+)', url)
                if domain_match:
                    domain = domain_match.group(1)
                    if article.get("_source_type") in ["internal", "external"]:
                        domain_to_source_type[domain] = article.get("_source_type")

        logger.debug(f"URL mapping has {len(url_to_source_type)} URLs, {len(domain_to_source_type)} domains")

        # Process each line in references section
        lines = references_section.split('\n')
        processed_lines = []

        for line in lines:
            # Skip if already has attribution
            if '*(internal)*' in line or '*(web)*' in line:
                processed_lines.append(line)
                continue

            # Check if line contains a URL
            url_match = re.search(r'https?://[^\s\)]+', line)
            if url_match:
                url = url_match.group(0).rstrip(')')
                source_type = url_to_source_type.get(url, "unknown")

                # Fallback: try domain matching if URL not found
                if source_type == "unknown":
                    domain_match = re.search(r'https?://([^/]+)', url)
                    if domain_match:
                        domain = domain_match.group(1)
                        source_type = domain_to_source_type.get(domain, "unknown")

                if source_type == "internal":
                    line = line.rstrip() + " *(internal)*"
                elif source_type == "external":
                    line = line.rstrip() + " *(web)*"

            processed_lines.append(line)

        # Add source summary header before references
        internal_count = state.sources_used.get("internal", 0)
        external_count = state.sources_used.get("external", 0)
        source_header = f"\n**Sources:** {internal_count} internal, {external_count} external\n\n"

        new_references = '\n'.join(processed_lines)

        return before_refs + source_header + new_references + after_refs

    def _inject_corpus_context(self, prompt: str, state: ResearchState) -> str:
        """
        Inject corpus context into the planner prompt so queries match actual content.
        """
        corpus_context = state.corpus_context
        if not corpus_context:
            return prompt

        # Build corpus context section
        current_date = datetime.now().strftime("%B %d, %Y")
        stats = corpus_context.get("stats", {})
        themes = corpus_context.get("themes", [])
        sample_titles = corpus_context.get("sample_titles", [])
        date_range = corpus_context.get("date_range", {})

        # Get current year for context
        current_year = datetime.now().year

        # Normalize topic for display
        display_topic = state.topic
        if state.topic in self.CROSS_TOPIC_VALUES:
            display_topic = "All Topics (cross-topic mode)"

        context_section = f"""
## CRITICAL DATE CONTEXT
**TODAY'S DATE:** {current_date}
**CURRENT YEAR:** {current_year}

⚠️ **IMPORTANT:** You MUST base all queries on {current_year} reality:
- Donald Trump is the current US President (elected November 2024, inaugurated January 2025)
- Joe Biden is the FORMER president - do NOT generate queries assuming he is in office
- Generate queries relevant to TODAY ({current_date}), not historical events

## Corpus Context (Auto-injected from Exploration Stage)
**Topic:** {display_topic}
**Total Articles Available:** {stats.get("total_articles", "Unknown")}
**Date Range:** {date_range.get("oldest", "Unknown")[:10] if date_range else "Unknown"} to {date_range.get("newest", "Unknown")[:10] if date_range else "Unknown"}
**Available Sources:** {len(corpus_context.get("available_sources", []))} news outlets

**Key Themes Found in Corpus:**
{chr(10).join("- " + theme for theme in themes[:10]) if themes else "- No themes extracted"}

**Sample Article Titles (from actual corpus):**
{chr(10).join("- " + title for title in sample_titles[:15]) if sample_titles else "- No samples available"}

## CRITICAL Query Generation Rules (Based on Corpus Analysis)
1. Your queries MUST use words that appear in the sample titles above
2. DO NOT use abstract concepts like "emerging trends" or "news coverage patterns"
3. DO NOT use year numbers in queries - vector search matches content, not dates
4. USE specific entities, topics, and terminology from the themes and samples
5. USE the key themes above as starting points for your queries
6. If a theme mentions "Tesla electric vehicles", query for "Tesla EV sales" not "automotive industry trends"
7. If a theme mentions "Federal Reserve rates", query for "interest rate hike Fed" not "economic policy developments"
8. NEVER reference outdated political figures as current leaders

**Remember:** Vector search finds articles by semantic similarity. Your queries will FAIL if they use abstract terms not in the corpus.

---

"""

        # Insert context after the header but before the main instructions
        # Look for common prompt section markers
        insert_markers = ["## Your Task", "## Task", "You are an expert"]
        for marker in insert_markers:
            if marker in prompt:
                idx = prompt.find(marker)
                return prompt[:idx] + context_section + prompt[idx:]

        # If no marker found, prepend to prompt
        return context_section + prompt

    def _get_default_planner_prompt(self) -> str:
        """Default planner prompt if agent not loaded."""
        return """You are an expert research planner. Analyze research queries and create:
1. 3-5 specific research objectives
2. Targeted search queries
3. Report outline

Respond with JSON:
{
  "research_objectives": [{"id": "obj_1", "objective": "...", "priority": "high"}],
  "search_queries": [{"objective_id": "obj_1", "query": "...", "search_type": "both"}],
  "report_outline": {"title": "...", "sections": [...]}
}"""

    def _get_default_synthesizer_prompt(self) -> str:
        """Default synthesizer prompt if agent not loaded."""
        return """You are an expert research analyst. Synthesize findings from multiple sources.

Respond with JSON:
{
  "synthesized_findings": {"obj_1": {"summary": "...", "key_points": [...], "confidence": "high"}},
  "credibility_assessment": {"overall_confidence": "medium", "reliability_score": 0.7, "contradictions": []}
}"""

    def _get_default_writer_prompt(self) -> str:
        """Default writer prompt if agent not loaded."""
        return """You are an expert research report writer. Write professional, well-cited reports.

Include:
- Executive Summary
- Methodology
- Findings (organized by objective)
- Analysis
- Conclusions
- Limitations
- References

Use inline citations: [Article Title](URL)"""

    async def _assess_coverage(
        self,
        state: ResearchState,
        config: ResearchConfig
    ) -> Dict:
        """
        Assess how well current results cover research objectives.
        Returns coverage scores and identifies gaps.
        """
        if not state.raw_results or not state.research_objectives:
            return {"overall_coverage": 0.0, "objective_coverage": {}, "gaps": []}

        # Build a summary of articles per objective
        objective_articles = {}
        for obj in state.research_objectives:
            obj_id = obj.get("id", "unknown")
            objective_articles[obj_id] = [
                a for a in state.raw_results
                if a.get("_objective_id") == obj_id
            ]

        # Format for LLM assessment
        coverage_data = []
        for obj in state.research_objectives:
            obj_id = obj.get("id", "unknown")
            articles = objective_articles.get(obj_id, [])
            coverage_data.append({
                "objective_id": obj_id,
                "objective": obj.get("objective", ""),
                "priority": obj.get("priority", "medium"),
                "article_count": len(articles),
                "article_titles": [a.get("title", "")[:100] for a in articles[:5]]
            })

        system_prompt = """You are a research coverage analyst. Assess how well search results cover research objectives.

For each objective, evaluate:
1. Coverage score (0.0-1.0): How well do the found articles address this objective?
2. Gaps: What specific aspects are missing or underrepresented?

Consider:
- Article count and relevance
- Whether titles suggest direct coverage
- Missing perspectives or time periods

Respond with JSON:
{
  "overall_coverage": 0.7,
  "objective_coverage": {
    "obj_1": {"score": 0.8, "gap": "Missing recent developments"},
    "obj_2": {"score": 0.5, "gap": "No coverage of specific aspect X"}
  },
  "gaps": ["Gap description 1", "Gap description 2"],
  "suggested_queries": ["Follow-up query 1", "Follow-up query 2"]
}"""

        user_prompt = f"""Research Query: {state.query}
Topic: {state.topic}

Objectives and Current Coverage:
{json.dumps(coverage_data, indent=2)}

Total articles found: {len(state.raw_results)}

Assess the coverage and identify gaps that need follow-up searches."""

        try:
            response = await litellm.acompletion(
                **resolve_litellm_call_params(config.planning_model),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.2,
                max_tokens=1000,
                response_format={"type": "json_object"}
            )

            result_text = response.choices[0].message.content
            assessment = json.loads(result_text)

            logger.info(
                f"Coverage assessment: overall={assessment.get('overall_coverage', 0):.1%}, "
                f"gaps={len(assessment.get('gaps', []))}"
            )

            return assessment

        except Exception as e:
            logger.warning(f"Coverage assessment failed: {e}")
            # Return conservative estimate
            return {
                "overall_coverage": 0.5,
                "objective_coverage": {},
                "gaps": [],
                "suggested_queries": []
            }

    async def _generate_refinement_queries(
        self,
        state: ResearchState,
        coverage_assessment: Dict,
        config: ResearchConfig
    ) -> List[Dict]:
        """
        Generate follow-up queries to fill identified gaps.
        """
        gaps = coverage_assessment.get("gaps", [])
        suggested = coverage_assessment.get("suggested_queries", [])

        if not gaps and not suggested:
            return []

        # Use suggested queries from assessment, or generate new ones
        refinement_queries = []

        # Add suggested queries from coverage assessment
        for i, query in enumerate(suggested[:3]):
            refinement_queries.append({
                "query": query,
                "search_type": "database",  # Prefer internal for refinement
                "objective_id": "refinement",
                "rationale": f"Gap-filling query {i+1}"
            })

        # If no suggestions but we have gaps, generate queries for gaps
        if not refinement_queries and gaps:
            for gap in gaps[:2]:
                # Create a query targeting the gap
                refinement_queries.append({
                    "query": f"{state.topic} {gap}",
                    "search_type": "database",
                    "objective_id": "refinement",
                    "rationale": f"Addressing gap: {gap}"
                })

        logger.info(f"Generated {len(refinement_queries)} refinement queries")
        return refinement_queries

    def _generate_chart_for_report(self, articles: List[Dict], topic: str) -> Optional[str]:
        """Generate a chart marker for the research report based on article sentiments."""
        from collections import Counter
        import json

        try:
            # Count sentiments
            sentiments = Counter()
            for article in articles:
                sentiment = article.get('sentiment', 'Unknown')
                if sentiment:
                    sentiments[sentiment] += 1

            if not sentiments:
                logger.warning("No sentiment data available for chart")
                return None

            # Prepare chart data
            labels = list(sentiments.keys())
            values = list(sentiments.values())

            # Color mapping for sentiments
            color_map = {
                'Positive': '#10B981',  # Green
                'Negative': '#EF4444',  # Red
                'Neutral': '#6B7280',   # Gray
                'Mixed': '#F59E0B',     # Amber
                'Unknown': '#9CA3AF'    # Light gray
            }
            colors = [color_map.get(label, '#6B7280') for label in labels]

            chart_data = {
                "chart_type": "sentiment_donut",
                "data": {
                    "labels": labels,
                    "values": values,
                    "colors": colors
                },
                "layout": {
                    "title": f"Sentiment Distribution: {topic}",
                    "showlegend": True
                }
            }

            # Return chart marker that the frontend can process
            chart_marker = f"<!-- CHART_DATA:{json.dumps(chart_data)}:END_CHART -->"
            logger.info(f"Generated sentiment chart: {len(articles)} articles, distribution: {dict(sentiments)}")
            return chart_marker

        except Exception as e:
            logger.error(f"Error generating chart for report: {e}")
            return None


# Singleton instance
_deep_research_instance: Optional[DeepResearchService] = None


def get_deep_research_service() -> DeepResearchService:
    """Get the global deep research service instance."""
    global _deep_research_instance
    if _deep_research_instance is None:
        _deep_research_instance = DeepResearchService()
    return _deep_research_instance
