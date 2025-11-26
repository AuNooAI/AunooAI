"""
Deep Research Agent Service
Multi-step autonomous research with planning, searching, synthesis, and reporting.

This service orchestrates the 4-stage deep research workflow:
1. Planning - Analyze query, create objectives and search strategy
2. Searching - Execute searches with diversity and credibility filtering
3. Synthesis - Analyze findings, resolve contradictions, assess confidence
4. Writing - Produce professional research report with citations
"""

import asyncio
import json
import logging
from typing import Dict, List, Optional, AsyncGenerator, Any
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum

import litellm

from app.database import get_database_instance
from app.services.auspex_tools import get_auspex_tools_service
from app.services.tool_loader import get_tool_loader
from app.services.search_router import get_search_router, SearchSource

logger = logging.getLogger(__name__)


class ResearchStage(str, Enum):
    """Research workflow stages."""
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
    current_stage: ResearchStage = ResearchStage.PLANNING
    stage_progress: Dict[str, float] = field(default_factory=lambda: {
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
        weights = {"planning": 0.1, "searching": 0.4, "synthesis": 0.3, "writing": 0.2}
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
    max_articles: int = 100
    articles_per_query: int = 20

    # Quality thresholds
    credibility_threshold: int = 40
    source_diversity_min: int = 5
    min_section_length: int = 500

    # Model settings
    planning_model: str = "gpt-4.1-mini"
    planning_temperature: float = 0.3
    synthesis_model: str = "gpt-4o"
    synthesis_temperature: float = 0.4
    writing_model: str = "gpt-4o"
    writing_temperature: float = 0.5

    # Timeouts (seconds)
    planning_timeout: int = 30
    searching_timeout: int = 120
    synthesis_timeout: int = 60
    writing_timeout: int = 90

    # Feature flags
    allow_external_search: bool = True
    include_charts: bool = True

    # Research mode settings
    search_source: str = "hybrid"  # 'internal', 'external', 'hybrid'
    research_mode: str = "hybrid"  # 'off', 'internal', 'hybrid', 'external', 'extend'
    extend_mode: bool = False
    previous_research: Optional[str] = None

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

        return config


class DeepResearchService:
    """Service for conducting deep, multi-step research."""

    def __init__(self):
        # IMPORTANT: Use database facade pattern for all DB operations
        # Access methods via self.db.facade.method_name()
        self.db = get_database_instance()
        self.tools = get_auspex_tools_service()
        self.tool_loader = get_tool_loader()
        self.search_router = get_search_router()

    def _load_agent_prompt(self, agent_name: str) -> Optional[str]:
        """Load agent prompt from tool loader."""
        agent = self.tool_loader.get_agent(agent_name)
        if agent:
            return agent.content
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
            # Stage 1: Planning
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

            # Stage 3: Synthesis
            yield {"stage": "synthesis", "status": "started", "progress": 0.0}
            await asyncio.wait_for(
                self._run_synthesis(state, config),
                timeout=config.synthesis_timeout
            )
            state.update_progress("synthesis", 1.0)
            yield {
                "stage": "synthesis",
                "status": "completed",
                "progress": 1.0,
                "confidence": state.credibility_assessment.get("overall_confidence", "unknown")
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

    async def _run_planning(self, state: ResearchState, config: ResearchConfig):
        """
        Stage 1: Planning
        Analyze query and create research objectives, search queries, and report outline.
        """
        planner_prompt = self._load_agent_prompt("research_planner")
        if not planner_prompt:
            planner_prompt = self._get_default_planner_prompt()

        system_prompt = planner_prompt

        user_prompt = f"""Research Query: {state.query}
Topic Area: {state.topic}

Please analyze this query and create:
1. 3-5 specific research objectives
2. Targeted search queries for each objective
3. A report outline structure

Respond with valid JSON matching the expected schema."""

        try:
            response = await litellm.acompletion(
                model=config.planning_model,
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
        Execute search queries and gather articles.
        Tracks source type (internal/external) for each article.
        """
        total_queries = len(state.search_queries)
        if total_queries == 0:
            state.search_queries = [{"query": state.query, "search_type": "both"}]
            total_queries = 1

        all_articles = []
        seen_urls = set()

        # Determine forced search source based on research mode config
        forced_source = None
        if config.search_source == "internal":
            forced_source = SearchSource.VECTOR_DB
        elif config.search_source == "external":
            forced_source = SearchSource.EXTERNAL if config.allow_external_search else SearchSource.VECTOR_DB
        elif config.search_source == "hybrid":
            forced_source = None  # Let router decide

        for i, search_query in enumerate(state.search_queries):
            query_text = search_query.get("query", state.query)
            search_type = search_query.get("search_type", "both")

            yield {
                "status": "searching",
                "progress": i / total_queries,
                "current_query": query_text,
                "query_index": i + 1,
                "total_queries": total_queries
            }

            try:
                # Use forced source from config, or fall back to query-specific type
                source = forced_source
                if source is None:
                    if search_type == "database":
                        source = SearchSource.VECTOR_DB
                    elif search_type == "external":
                        source = SearchSource.EXTERNAL if config.allow_external_search else SearchSource.VECTOR_DB
                    else:
                        source = None  # Let router decide

                # Execute search
                results = await self.search_router.execute_routed_search(
                    query=query_text,
                    topic=state.topic,
                    limit=config.articles_per_query,
                    force_source=source,
                    tools_service=self.tools
                )

                # Determine actual source type from results
                actual_source = results.get("source_type", "unknown")

                # Deduplicate and add articles with source tracking
                for article in results.get("articles", []):
                    url = article.get("url") or article.get("uri", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        article["_objective_id"] = search_query.get("objective_id")

                        # Track source type for attribution
                        # Check if article came from vector DB (internal) or external search
                        if actual_source == "vector_db" or article.get("_from_vector_db"):
                            article["_source_type"] = "internal"
                            state.sources_used["internal"] += 1
                        elif actual_source == "external" or article.get("_from_external"):
                            article["_source_type"] = "external"
                            state.sources_used["external"] += 1
                        else:
                            # Default based on presence of certain fields
                            if article.get("embedding") or article.get("vector_score"):
                                article["_source_type"] = "internal"
                                state.sources_used["internal"] += 1
                            else:
                                article["_source_type"] = "external"
                                state.sources_used["external"] += 1

                        all_articles.append(article)

                    # Stop if we have enough
                    if len(all_articles) >= config.max_articles:
                        break

            except Exception as e:
                logger.warning(f"Search query failed: {query_text}: {e}")
                state.errors.append(f"Search failed: {query_text}")

            if len(all_articles) >= config.max_articles:
                break

        # Store results
        state.raw_results = all_articles

        # Calculate source metadata
        sources = set()
        categories = set()
        sentiments = {}

        for article in all_articles:
            source = article.get("news_source") or article.get("source", "Unknown")
            sources.add(source)

            category = article.get("category", "Unknown")
            categories.add(category)

            sentiment = article.get("sentiment", "Unknown")
            sentiments[sentiment] = sentiments.get(sentiment, 0) + 1

        state.source_metadata = {
            "unique_sources": len(sources),
            "sources_list": list(sources)[:20],
            "categories": list(categories),
            "sentiment_distribution": sentiments,
            "total_articles": len(all_articles),
            "sources_used": state.sources_used
        }

        yield {
            "status": "completed",
            "progress": 1.0,
            "articles_found": len(all_articles),
            "unique_sources": len(sources),
            "sources_used": state.sources_used
        }

    async def _run_synthesis(self, state: ResearchState, config: ResearchConfig):
        """
        Stage 3: Synthesis
        Analyze findings, resolve contradictions, assess confidence.
        """
        synthesizer_prompt = self._load_agent_prompt("research_synthesizer")
        if not synthesizer_prompt:
            synthesizer_prompt = self._get_default_synthesizer_prompt()

        # Prepare article summaries for synthesis (limit context)
        article_summaries = []
        for i, article in enumerate(state.raw_results[:50]):  # Limit to 50 for context
            summary = {
                "index": i + 1,
                "title": article.get("title", "Untitled"),
                "source": article.get("news_source") or article.get("source", "Unknown"),
                "date": article.get("publication_date", "Unknown"),
                "sentiment": article.get("sentiment", "Unknown"),
                "credibility": article.get("credibility_score", 50),
                "summary": (article.get("summary") or article.get("content", ""))[:500],
                "url": article.get("url") or article.get("uri", ""),
                "objective_id": article.get("_objective_id")
            }
            article_summaries.append(summary)

        user_prompt = f"""Research Query: {state.query}
Topic: {state.topic}

Research Objectives:
{json.dumps(state.research_objectives, indent=2)}

Articles Found ({len(article_summaries)} of {len(state.raw_results)}):
{json.dumps(article_summaries, indent=2)}

Source Metadata:
{json.dumps(state.source_metadata, indent=2)}

Please synthesize these findings and provide:
1. Key findings organized by objective
2. Credibility assessment
3. Identified contradictions (if any)

Respond with valid JSON."""

        try:
            response = await litellm.acompletion(
                model=config.synthesis_model,
                messages=[
                    {"role": "system", "content": synthesizer_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=config.synthesis_temperature,
                max_tokens=4000,
                response_format={"type": "json_object"}
            )

            result_text = response.choices[0].message.content
            result = json.loads(result_text)

            state.synthesized_findings = result.get("synthesized_findings", {})
            state.credibility_assessment = result.get("credibility_assessment", {})

            logger.info(f"Synthesis complete: {len(state.synthesized_findings)} findings")

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse synthesis response: {e}")
            # Create basic synthesis
            state.synthesized_findings = {
                "summary": f"Analysis of {len(state.raw_results)} articles on {state.topic}"
            }
            state.credibility_assessment = {
                "overall_confidence": "medium",
                "reliability_score": 0.5
            }

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
        article_refs = []
        for i, article in enumerate(state.raw_results[:30]):  # Top 30 for citations
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

        user_prompt = f"""Write a comprehensive research report based on the following:

## Research Query
{state.query}

## Topic
{state.topic}

## Source Summary
{source_summary}

## Report Outline
{json.dumps(state.report_outline, indent=2)}

## Synthesized Findings
{json.dumps(state.synthesized_findings, indent=2)}

## Credibility Assessment
{json.dumps(state.credibility_assessment, indent=2)}

## Available Sources for Citation
Each source has a "source_type" field indicating if it's from our internal database ("internal") or external web search ("external").
{json.dumps(article_refs, indent=2)}

## Source Metadata
- Total articles analyzed: {len(state.raw_results)}
- Internal sources: {internal_count}
- External sources: {external_count}
- Unique news outlets: {state.source_metadata.get('unique_sources', 0)}
- Categories covered: {', '.join(c for c in state.source_metadata.get('categories', [])[:10] if c)}

Write the complete research report with inline citations using [Source Name](URL) format.
Include: Executive Summary, Methodology, Findings, Analysis, Conclusions, Limitations, and References.

IMPORTANT: In the References section at the end, after each reference add the source attribution:
- For internal database sources: add *(internal)* after the reference
- For external web sources: add *(web)* after the reference
Example: [1] Article Title - https://example.com *(internal)*"""

        # Stream the response
        report_chunks = []

        # FIXED: Correct async streaming pattern for litellm
        response = await litellm.acompletion(
            model=config.writing_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=config.writing_temperature,
            max_tokens=8000,
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
        for ref in article_refs:
            url = ref.get("url", "")
            if url:
                url_to_source_type[url] = ref.get("source_type", "unknown")

        # Also check raw_results for more complete mapping
        for article in state.raw_results:
            url = article.get("url") or article.get("uri", "")
            if url and url not in url_to_source_type:
                url_to_source_type[url] = article.get("_source_type", "unknown")

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


# Singleton instance
_deep_research_instance: Optional[DeepResearchService] = None


def get_deep_research_service() -> DeepResearchService:
    """Get the global deep research service instance."""
    global _deep_research_instance
    if _deep_research_instance is None:
        _deep_research_instance = DeepResearchService()
    return _deep_research_instance
