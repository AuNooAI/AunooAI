"""
Trend Agent

Analyzes 2030 Trends (T1-T5) using the TrendCalculator for
repeatable, measurable scores with LLM interpretation.

Trends:
- T1: Invisible LLM Ecosystems (attention dimension)
- T2: Agentic AI Reshaping Workflows (power dimension)
- T3: Decline of SEO, Rise of GEO (attention dimension)
- T4: Regulatory & Provenance Pressures (power dimension)
- T5: Market Consolidation (money dimension)
"""

import json
import logging
from typing import Dict, List, Any, Optional

from .base_pillar_agent import (
    BasePillarAgent,
    PillarConfig,
    AnalysisContext,
    MetricResult,
    AgentState,
    AgentStage,
    DEFAULT_MODEL
)
from ..trend_calculator import (
    TrendCalculator,
    TrendData,
    TrendScore,
    get_interpretation_prompt
)
from ..external_data import SemanticScholarProvider, GoogleSearchProvider

logger = logging.getLogger(__name__)

# Trend definitions (same as in pam_service.py)
TREND_DEFINITIONS = {
    "T1": {
        "name": "Invisible LLM Ecosystems",
        "short_name": "LLM Ecosystems",
        "dimension": "attention",
        "description": "Content increasingly consumed through AI interfaces, bypassing traditional discovery",
        "keywords": ["LLM", "ChatGPT", "AI assistant", "embedding", "RAG", "training data"]
    },
    "T2": {
        "name": "Agentic AI Reshaping Workflows",
        "short_name": "Agentic AI",
        "dimension": "power",
        "description": "AI agents autonomously executing research and analysis workflows",
        "keywords": ["AI agent", "autonomous", "workflow", "automation", "research assistant"]
    },
    "T3": {
        "name": "Decline of SEO, Rise of GEO",
        "short_name": "SEO to GEO",
        "dimension": "attention",
        "description": "Search engine optimization giving way to Generative Engine Optimization",
        "keywords": ["SEO", "GEO", "search", "AI search", "Perplexity", "Google AI"]
    },
    "T4": {
        "name": "Regulatory & Provenance Pressures",
        "short_name": "Regulation",
        "dimension": "power",
        "description": "Growing regulatory frameworks around AI, data provenance, and content licensing",
        "keywords": ["regulation", "AI Act", "copyright", "licensing", "provenance", "compliance"]
    },
    "T5": {
        "name": "Market Consolidation",
        "short_name": "Consolidation",
        "dimension": "money",
        "description": "Mergers, acquisitions, and market concentration in AI and publishing",
        "keywords": ["acquisition", "merger", "consolidation", "market share", "funding"]
    }
}


class TrendAgent(BasePillarAgent):
    """
    Agent for analyzing 2030 Trends with repeatable scoring.

    Unlike other pillar agents, TrendAgent calculates scores from
    measurable inputs using TrendCalculator, then uses LLM only
    for interpretation of the calculated scores.
    """

    PILLAR = "trends"

    def __init__(self, config: PillarConfig = None, trend_calculator: TrendCalculator = None):
        if config is None:
            config = PillarConfig(pillar="trends")
        super().__init__(config)
        self.trend_calculator = trend_calculator if trend_calculator else TrendCalculator()
        self._semantic_scholar = None
        self._google_provider = None

    @property
    def semantic_scholar(self) -> SemanticScholarProvider:
        if self._semantic_scholar is None:
            self._semantic_scholar = SemanticScholarProvider()
        return self._semantic_scholar

    @property
    def google_provider(self) -> GoogleSearchProvider:
        if self._google_provider is None:
            self._google_provider = GoogleSearchProvider()
        return self._google_provider

    async def analyze_trends(
        self,
        articles_by_trend: Dict[str, List[Dict]],
        context: AnalysisContext,
        previous_scores: Optional[Dict[str, float]] = None
    ):
        """
        Analyze all trends with streaming progress.

        This is the main entry point for trend analysis, different
        from the base analyze() method.

        Args:
            articles_by_trend: Dict mapping trend_id to list of articles
            context: Analysis context with topic, days_back, etc.
            previous_scores: Optional dict of {T1: score, T2: score, ...} for EMA smoothing
        """
        self.state = AgentState(started_at=__import__('datetime').datetime.now())

        try:
            yield self.state.update(AgentStage.INITIALIZING, 0.05, "Initializing trend analysis")

            # Stage 1: Fetch external data for trends
            yield self.state.update(AgentStage.FETCHING_EXTERNAL, 0.1, "Fetching external data")
            external_data = await self._fetch_trend_external_data(context)

            # Stage 2: Calculate measurable scores with EMA smoothing
            yield self.state.update(AgentStage.ANALYZING, 0.3, "Calculating trend scores")
            trend_scores = await self._calculate_trend_scores(
                articles_by_trend,
                external_data,
                previous_scores=previous_scores
            )

            # Stage 3: Get LLM interpretations
            yield self.state.update(AgentStage.SYNTHESIZING, 0.5, "Generating interpretations")
            interpretations = await self._get_trend_interpretations(
                trend_scores,
                articles_by_trend
            )

            # Stage 4: Synthesize results
            yield self.state.update(AgentStage.SYNTHESIZING, 0.85, "Synthesizing results")
            result = self._synthesize_trend_results(
                trend_scores,
                interpretations,
                external_data,
                context
            )

            self.state.completed_at = __import__('datetime').datetime.now()
            yield {
                **self.state.update(AgentStage.COMPLETE, 1.0, "Trend analysis complete"),
                "result": result
            }

        except Exception as e:
            logger.error(f"Trend agent error: {e}")
            self.state.error = str(e)
            yield {
                **self.state.update(AgentStage.ERROR, self.state.progress, f"Error: {e}"),
                "error": str(e)
            }

    async def _fetch_external_data(self, context: AnalysisContext) -> Dict[str, Any]:
        """Not used by TrendAgent - see _fetch_trend_external_data."""
        return {}

    async def _run_llm_analysis(
        self,
        articles: List[Dict],
        context: AnalysisContext,
        external_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Not used by TrendAgent - see _get_trend_interpretations."""
        return {}

    async def _synthesize_results(
        self,
        articles: List[Dict],
        article_metrics: Dict[str, MetricResult],
        external_data: Dict[str, Any],
        llm_analysis: Dict[str, Any],
        context: AnalysisContext
    ) -> Dict[str, Any]:
        """Not used by TrendAgent - see _synthesize_trend_results."""
        return {}

    async def _fetch_trend_external_data(
        self,
        context: AnalysisContext
    ) -> Dict[str, Dict]:
        """
        Fetch external data relevant to each trend.

        Returns dict mapping trend_id to external data.
        """
        if not self.config.enable_external_data:
            return {}

        external_data = {}
        topic = context.topic or "AI publishing"

        # T1, T3: Citation data (attention trends)
        try:
            citations = await self.semantic_scholar.fetch_citation_data(
                query=f"{topic} LLM AI search",
                limit=50
            )
            external_data["T1"] = {"citation_score": citations.to_score()}
            external_data["T3"] = {"citation_score": citations.to_score()}
        except Exception as e:
            logger.warning(f"Trend external: Citation fetch failed: {e}")

        # T4: Regulatory data
        try:
            regulatory = await self.google_provider.fetch_regulatory_data(
                query=f"{topic} AI regulation",
                days_back=context.days_back
            )
            external_data["T4"] = {"regulatory_activity_score": regulatory.to_score()}
        except Exception as e:
            logger.warning(f"Trend external: Regulatory fetch failed: {e}")

        # T5: M&A data
        try:
            ma = await self.google_provider.fetch_ma_data(
                query=f"{topic} acquisition merger",
                days_back=context.days_back
            )
            external_data["T5"] = {"funding_activity_score": ma.to_score()}
        except Exception as e:
            logger.warning(f"Trend external: M&A fetch failed: {e}")

        return external_data

    async def _calculate_trend_scores(
        self,
        articles_by_trend: Dict[str, List[Dict]],
        external_data: Dict[str, Dict],
        previous_scores: Optional[Dict[str, float]] = None
    ) -> Dict[str, TrendScore]:
        """
        Calculate trend scores using TrendCalculator with optional EMA smoothing.

        This produces REPEATABLE, MEASURABLE scores based on:
        - Article counts
        - Recency distribution
        - Source diversity
        - Velocity (month-over-month change using 3-month rolling average)
        - External signals
        - EMA smoothing with previous scores (if available)
        """
        return self.trend_calculator.calculate_all_trends(
            articles_by_trend=articles_by_trend,
            trend_definitions=TREND_DEFINITIONS,
            external_data=external_data,
            previous_scores=previous_scores
        )

    async def _get_trend_interpretations(
        self,
        trend_scores: Dict[str, TrendScore],
        articles_by_trend: Dict[str, List[Dict]]
    ) -> Dict[str, Dict]:
        """
        Get LLM interpretations for each trend score.

        The LLM INTERPRETS the calculated score, it doesn't generate one.
        """
        interpretations = {}

        for trend_id, score in trend_scores.items():
            articles = articles_by_trend.get(trend_id, [])

            if not articles:
                interpretations[trend_id] = {
                    "key_drivers": [],
                    "evidence": [],
                    "publisher_implications": "Insufficient data for interpretation",
                    "urgency": "medium_term"
                }
                continue

            # Build interpretation prompt
            formatted_articles = self._format_articles_for_prompt(articles, max_articles=20)
            prompt = get_interpretation_prompt(score, articles)
            prompt += f"\n\nARTICLE EVIDENCE:\n{formatted_articles}"

            try:
                response = await self._call_llm(prompt)
                content = self._extract_json(response)
                interpretation = json.loads(content)
                interpretations[trend_id] = interpretation
            except Exception as e:
                logger.error(f"Trend {trend_id} interpretation failed: {e}")
                interpretations[trend_id] = {
                    "key_drivers": [f"Error generating interpretation: {e}"],
                    "evidence": [],
                    "publisher_implications": "Unable to generate interpretation",
                    "urgency": "medium_term"
                }

        return interpretations

    def _synthesize_trend_results(
        self,
        trend_scores: Dict[str, TrendScore],
        interpretations: Dict[str, Dict],
        external_data: Dict[str, Dict],
        context: AnalysisContext
    ) -> Dict[str, Any]:
        """
        Synthesize final trend results.
        """
        trends = []

        for trend_id, score in trend_scores.items():
            definition = TREND_DEFINITIONS.get(trend_id, {})
            interpretation = interpretations.get(trend_id, {})

            trends.append({
                "id": trend_id,
                "name": definition.get("name", trend_id),
                "short_name": definition.get("short_name", trend_id),
                "dimension": definition.get("dimension", "unknown"),

                # Calculated score with full breakdown
                "score": score.score,
                "score_components": score.to_dict()["components"],
                "data_sources": score.data_sources,
                "confidence": score.confidence,

                # Velocity
                "velocity": score.velocity_direction,
                "velocity_change_pct": score.velocity_change_pct,

                # LLM interpretation
                "key_drivers": interpretation.get("key_drivers", []),
                "evidence": interpretation.get("evidence", []),
                "publisher_implications": interpretation.get("publisher_implications", ""),
                "urgency": interpretation.get("urgency", "medium_term")
            })

        # Sort by score descending
        trends.sort(key=lambda t: t["score"], reverse=True)

        return {
            "trends": trends,
            "external_data_used": external_data,
            "calculation_method": "countable_metrics",
            "interpretation_method": "llm_analysis",
            "model_used": self.model
        }


def get_trend_definitions() -> Dict[str, Dict]:
    """Get trend definitions for external use."""
    return TREND_DEFINITIONS.copy()
