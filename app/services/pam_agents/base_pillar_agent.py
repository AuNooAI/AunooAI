"""
Base Pillar Agent

Abstract base class for PAM pillar agents. Provides common functionality
for article collection, external data fetching, LLM analysis, and streaming.
"""

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any, AsyncGenerator, Tuple

from fastapi.concurrency import run_in_threadpool
import litellm

from app.ai_models import resolve_litellm_call_params

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-5.4-mini"


class AgentStage(Enum):
    """Agent execution stages."""
    INITIALIZING = "initializing"
    COLLECTING_ARTICLES = "collecting_articles"
    FETCHING_EXTERNAL = "fetching_external"
    ANALYZING = "analyzing"
    SYNTHESIZING = "synthesizing"
    COMPLETE = "complete"
    ERROR = "error"


@dataclass
class AgentState:
    """Tracks agent execution state."""
    stage: AgentStage = AgentStage.INITIALIZING
    progress: float = 0.0
    message: str = ""
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None

    def update(self, stage: AgentStage, progress: float, message: str = ""):
        """Update state and return progress dict."""
        self.stage = stage
        self.progress = progress
        self.message = message
        return self.to_dict()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage": self.stage.value,
            "progress": self.progress,
            "message": self.message,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error
        }


@dataclass
class PillarConfig:
    """Configuration for a pillar agent."""
    pillar: str  # 'power', 'attention', 'money'
    model: str = DEFAULT_MODEL
    temperature: float = 0.3
    max_tokens: int = 4000
    prompt_file: str = ""
    relevance_threshold: float = 0.65
    articles_per_topic: int = 20
    max_articles_for_llm: int = 30
    enable_external_data: bool = True
    external_providers: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict) -> 'PillarConfig':
        return cls(
            pillar=data.get('pillar', 'unknown'),
            model=data.get('model', DEFAULT_MODEL),
            temperature=data.get('temperature', 0.3),
            max_tokens=data.get('max_tokens', 4000),
            prompt_file=data.get('prompt_file', ''),
            relevance_threshold=data.get('relevance_threshold', 0.65),
            articles_per_topic=data.get('articles_per_topic', 20),
            max_articles_for_llm=data.get('max_articles_for_llm', 30),
            enable_external_data=data.get('enable_external_data', True),
            external_providers=data.get('external_providers', [])
        )


@dataclass
class AnalysisContext:
    """Context for running an analysis."""
    run_id: str
    topic: Optional[str] = None
    days_back: int = 90
    trend_focus: List[str] = field(default_factory=lambda: ["T1", "T2", "T3", "T4", "T5"])
    entity_type: str = "publisher"
    time_horizon: str = "1_year"
    # Pre-extracted events from event tables
    financial_events: List[Dict[str, Any]] = field(default_factory=list)
    regulatory_events: List[Dict[str, Any]] = field(default_factory=list)
    # Monitored entities/brands for tracking in analysis
    monitored_entities: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class MetricResult:
    """A metric with its data source clearly labeled."""
    name: str
    value: Any
    source: str  # 'measured', 'external_api', 'article_count', 'llm_estimate'
    confidence: str = "medium"  # 'high', 'medium', 'low'
    provider: Optional[str] = None  # e.g., 'semantic_scholar', 'crunchbase'

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "source": self.source,
            "confidence": self.confidence,
            "provider": self.provider
        }


class BasePillarAgent(ABC):
    """
    Abstract base class for PAM pillar agents.

    Each pillar agent:
    1. Receives pre-collected articles
    2. Optionally fetches external data (citations, funding, etc.)
    3. Calculates measured metrics from countable data
    4. Runs LLM for qualitative interpretation
    5. Streams progress throughout execution
    """

    PILLAR: str = "base"  # Override in subclasses

    def __init__(self, config: PillarConfig):
        self.config = config
        self.model = config.model
        self.state = AgentState()
        self._external_providers: Dict[str, Any] = {}

    async def analyze(
        self,
        articles: List[Dict],
        context: AnalysisContext
    ) -> AsyncGenerator[Dict, None]:
        """
        Run pillar analysis with streaming progress.

        Yields progress updates and final result.

        Args:
            articles: Pre-collected articles for this pillar
            context: Analysis context (topic, timeframe, etc.)

        Yields:
            Dict with stage, progress, and eventually result
        """
        self.state = AgentState(started_at=datetime.now())

        try:
            # Stage 1: Initialize
            yield self.state.update(AgentStage.INITIALIZING, 0.05, "Initializing analysis")

            # Stage 2: Collect measured metrics from articles
            yield self.state.update(AgentStage.COLLECTING_ARTICLES, 0.1, f"Processing {len(articles)} articles")
            article_metrics = await self._calculate_article_metrics(articles)

            # Stage 3: Fetch external data if enabled
            external_data = {}
            if self.config.enable_external_data:
                yield self.state.update(AgentStage.FETCHING_EXTERNAL, 0.25, "Fetching external data")
                external_data = await self._fetch_external_data(context)

            # Stage 4: Run LLM analysis
            yield self.state.update(AgentStage.ANALYZING, 0.5, "Running AI analysis")
            llm_analysis = await self._run_llm_analysis(articles, context, external_data)

            # Stage 5: Synthesize results
            yield self.state.update(AgentStage.SYNTHESIZING, 0.85, "Synthesizing results")
            result = await self._synthesize_results(
                articles=articles,
                article_metrics=article_metrics,
                external_data=external_data,
                llm_analysis=llm_analysis,
                context=context
            )

            # Complete
            self.state.completed_at = datetime.now()
            yield {
                **self.state.update(AgentStage.COMPLETE, 1.0, "Analysis complete"),
                "result": result
            }

        except Exception as e:
            logger.error(f"{self.PILLAR} agent error: {e}")
            self.state.error = str(e)
            yield {
                **self.state.update(AgentStage.ERROR, self.state.progress, f"Error: {e}"),
                "error": str(e)
            }

    async def _calculate_article_metrics(self, articles: List[Dict]) -> Dict[str, MetricResult]:
        """
        Calculate measurable metrics from articles.

        These are REAL, COUNTABLE metrics - not LLM estimates.
        """
        if not articles:
            return {}

        # Article volume
        article_count = len(articles)

        # Source diversity
        sources = set(a.get('news_source') or a.get('source', 'Unknown') for a in articles)
        source_count = len(sources)

        # Recency distribution
        from datetime import datetime, timedelta
        recent_cutoff = datetime.now() - timedelta(days=30)
        recent_count = 0
        for a in articles:
            date_str = a.get('publication_date') or a.get('submission_date', '')
            if date_str:
                try:
                    if isinstance(date_str, str):
                        pub_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    else:
                        pub_date = date_str
                    if pub_date.replace(tzinfo=None) > recent_cutoff:
                        recent_count += 1
                except:
                    pass

        recency_pct = (recent_count / article_count * 100) if article_count > 0 else 0

        # Average relevance score (from vector search)
        relevance_scores = [a.get('_relevance_score', 0.5) for a in articles]
        avg_relevance = sum(relevance_scores) / len(relevance_scores) if relevance_scores else 0.5

        return {
            "article_count": MetricResult(
                name="Article Count",
                value=article_count,
                source="measured",
                confidence="high"
            ),
            "source_diversity": MetricResult(
                name="Source Diversity",
                value=source_count,
                source="measured",
                confidence="high"
            ),
            "recency_pct": MetricResult(
                name="Recent Articles %",
                value=round(recency_pct, 1),
                source="measured",
                confidence="high"
            ),
            "avg_relevance": MetricResult(
                name="Average Relevance",
                value=round(1 - avg_relevance, 3),  # Convert distance to similarity
                source="measured",
                confidence="high"
            )
        }

    @abstractmethod
    async def _fetch_external_data(self, context: AnalysisContext) -> Dict[str, Any]:
        """
        Fetch data from external APIs (Semantic Scholar, Crunchbase, etc.)

        Override in subclasses to implement pillar-specific data fetching.
        """
        pass

    @abstractmethod
    async def _run_llm_analysis(
        self,
        articles: List[Dict],
        context: AnalysisContext,
        external_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Run LLM analysis for qualitative interpretation.

        Override in subclasses to implement pillar-specific prompts.
        """
        pass

    @abstractmethod
    async def _synthesize_results(
        self,
        articles: List[Dict],
        article_metrics: Dict[str, MetricResult],
        external_data: Dict[str, Any],
        llm_analysis: Dict[str, Any],
        context: AnalysisContext
    ) -> Dict[str, Any]:
        """
        Synthesize final results from all data sources.

        Override in subclasses to implement pillar-specific synthesis.
        """
        pass

    def _format_articles_for_prompt(self, articles: List[Dict], max_articles: int = None) -> str:
        """Format articles for LLM prompt with numbered citations."""
        max_articles = max_articles or self.config.max_articles_for_llm
        formatted = []

        for i, article in enumerate(articles[:max_articles], 1):
            title = article.get("title") or "Untitled"
            source = article.get("news_source") or article.get("source") or "Unknown"
            date = article.get("publication_date") or ""
            summary = (article.get("summary") or "")[:1000]
            url = article.get("uri") or article.get("url") or ""

            formatted.append(
                f"[{i}] {title}\n"
                f"    Source: {source} | Date: {date}\n"
                f"    URL: {url}\n"
                f"    Summary: {summary}\n"
            )

        return "\n".join(formatted)

    def _get_citation_instructions(self) -> str:
        """Get citation instructions for LLM prompts."""
        return """
CITATION INSTRUCTIONS:
- Use numbered citations [1], [2], [3] to reference specific articles
- Include citations in descriptions, summaries, and findings
- Every key claim should have at least one citation
- Use the article numbers from the NUMBERED ARTICLE LIST above
"""

    def _extract_json(self, content: str) -> str:
        """Extract and repair JSON from LLM response."""
        import re

        content = content.strip()

        # Extract from code blocks
        if "```json" in content:
            start = content.find("```json") + 7
            end = content.find("```", start)
            if end > start:
                content = content[start:end].strip()
        elif "```" in content:
            start = content.find("```") + 3
            end = content.find("```", start)
            if end > start:
                content = content[start:end].strip()

        # Find the JSON object
        if "{" in content:
            start = content.find("{")
            depth = 0
            for i, char in enumerate(content[start:], start):
                if char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        content = content[start:i+1]
                        break

        # Repair common JSON issues from LLMs
        content = self._repair_json(content)

        return content

    def _repair_json(self, content: str) -> str:
        """Repair common JSON issues from LLM responses."""
        import re

        # Remove trailing commas before } or ]
        content = re.sub(r',\s*([}\]])', r'\1', content)

        # Fix unescaped newlines in strings (common LLM issue)
        # This is tricky - we need to find strings and escape newlines within them
        # Simple approach: replace actual newlines that aren't escaped
        lines = content.split('\n')
        fixed_lines = []
        in_string = False
        for line in lines:
            # Count unescaped quotes to track string state
            quote_count = 0
            i = 0
            while i < len(line):
                if line[i] == '"' and (i == 0 or line[i-1] != '\\'):
                    quote_count += 1
                i += 1

            if in_string and quote_count % 2 == 0:
                # We're in a string and this line doesn't close it
                # The newline should be escaped
                if fixed_lines:
                    fixed_lines[-1] = fixed_lines[-1] + '\\n' + line
                else:
                    fixed_lines.append(line)
            else:
                fixed_lines.append(line)
                in_string = (quote_count % 2 == 1)

        content = '\n'.join(fixed_lines)

        # Remove JavaScript-style comments
        content = re.sub(r'//[^\n]*\n', '\n', content)
        content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)

        return content

    async def _call_llm(self, prompt: str, temperature: float = 0.3) -> str:
        """Call LLM with the configured model."""
        try:
            response = await run_in_threadpool(
                litellm.completion,
                **resolve_litellm_call_params(self.model),
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise
