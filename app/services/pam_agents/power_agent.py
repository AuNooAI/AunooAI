"""
Power Agent

Analyzes the POWER dimension of PAM by extracting EVIDENCE from news articles
about how power dynamics are shifting for publishers.

Focuses on two key trends:
- T2: Agentic AI Reshaping Workflows (AI agents executing research autonomously)
- T4: Regulatory & Provenance Pressures (AI regulation, licensing, copyright)

This agent does NOT directly measure infrastructure control or regulatory influence.
It extracts what articles REPORT about these dynamics.
"""

import json
import logging
from typing import Dict, List, Any

from .base_pillar_agent import (
    BasePillarAgent,
    PillarConfig,
    AnalysisContext,
    MetricResult,
    DEFAULT_MODEL
)
from ..external_data import GoogleSearchProvider

logger = logging.getLogger(__name__)


class PowerAgent(BasePillarAgent):
    """Agent for analyzing the POWER dimension through article evidence extraction."""

    PILLAR = "power"

    # Evidence categories aligned with T2 and T4 trends
    CATEGORIES = [
        "t2_agentic_ai_evidence",
        "t4_regulatory_evidence",
        "infrastructure_signals",
        "ip_licensing_evidence"
    ]

    def __init__(self, config: PillarConfig = None, google_search_provider: GoogleSearchProvider = None):
        if config is None:
            config = PillarConfig(pillar="power")
        super().__init__(config)
        self._google_provider = google_search_provider

    @property
    def google_provider(self) -> GoogleSearchProvider:
        if self._google_provider is None:
            self._google_provider = GoogleSearchProvider()
        return self._google_provider

    async def _fetch_external_data(self, context: AnalysisContext) -> Dict[str, Any]:
        """
        Fetch regulatory and policy data for POWER dimension.

        Uses Google Search for regulatory developments.
        """
        if not self.config.enable_external_data:
            return {}

        external_data = {}
        query = context.topic or "AI publishing academic"

        try:
            # Fetch regulatory data
            regulatory = await self.google_provider.fetch_regulatory_data(
                query=query,
                days_back=context.days_back
            )
            external_data["regulatory"] = regulatory.to_dict()
            external_data["regulatory_score"] = regulatory.to_score()
        except Exception as e:
            logger.warning(f"Power: Failed to fetch regulatory data: {e}")
            external_data["regulatory_error"] = str(e)

        return external_data

    async def _run_llm_analysis(
        self,
        articles: List[Dict],
        context: AnalysisContext,
        external_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Run LLM analysis to extract EVIDENCE from articles about power dynamics."""

        formatted_articles = self._format_articles_for_prompt(articles)

        # Include external data in prompt if available
        external_context = ""
        if external_data.get("regulatory"):
            reg = external_data["regulatory"]
            external_context = f"""
REGULATORY DATA (from Google Search):
- Regulatory events found: {reg.get('event_count', 0)}
- Regulatory trend: {reg.get('regulatory_trend', 'unknown')}
- Key jurisdictions: {', '.join(reg.get('jurisdictions', []))}
- Key regulations: {', '.join(reg.get('key_regulations', []))}
"""

        # Include pre-extracted regulatory events from database
        if context.regulatory_events:
            external_context += f"""
PRE-EXTRACTED REGULATORY EVENTS ({len(context.regulatory_events)} events):
"""
            for i, evt in enumerate(context.regulatory_events[:15], 1):
                external_context += f"""
[REG-{i}] {evt.get('headline', 'Unknown')}
- Date: {evt.get('event_date', 'Unknown')}
- Jurisdiction: {evt.get('jurisdiction', 'Unknown')}
- Type: {evt.get('event_type', 'Unknown')}
- Impact: {evt.get('summary', '')}
- Publisher implications: {evt.get('publisher_implications', 'N/A')}
"""

        prompt = f"""
Analyze these articles to extract EVIDENCE about power dynamics in the AI/publishing sector.

IMPORTANT: You are NOT directly measuring infrastructure control or regulatory influence (those are abstractions).
You ARE extracting what these articles REPORT about how power is shifting.

{external_context}

NUMBERED ARTICLE LIST:
{formatted_articles}

{self._get_citation_instructions()}

Extract evidence for these two key trends:

## T2: AGENTIC AI RESHAPING WORKFLOWS
AI agents are increasingly executing complex research, publishing, and learning tasks autonomously.
By 2030, AI will read literature, draft protocols, run simulations, and prepare manuscripts.

Look for news articles that mention:

**AI Research & Discovery Tools:**
- AI research assistants (Elicit, Consensus, Semantic Scholar AI)
- AI in scientific discovery (AlphaFold, drug discovery, protein folding)
- AI-driven literature reviews and systematic reviews
- AI in clinical trials and lab automation

**AI Agent Platforms & Frameworks:**
- Autonomous AI agents (AutoGPT, BabyAGI, Claude Computer Use)
- Agent frameworks (LangChain, CrewAI, AutoGen)
- AI coding assistants (GitHub Copilot, Cursor, Codeium)
- Multi-agent systems and orchestration

**Publishing & Academic Workflow Changes:**
- AI peer review and manuscript screening
- AI-generated content in journals or news
- Publishers adopting AI tools
- Universities mandating or banning AI tools
- Changes to research workflows due to AI

**Content Creation & Journalism:**
- AI writing tools adoption (ChatGPT, Claude for drafting)
- AI-generated articles and reports
- Automated journalism and content farms
- Human-AI collaboration in writing

**Workflow Disruption Signals:**
- Reduced need for research assistants
- AI replacing specific job functions
- New AI-augmented roles emerging
- Productivity claims from AI adoption

## T4: REGULATORY & PROVENANCE PRESSURES
Growing regulation and licensing requirements are reshaping who has power in AI/publishing.

Look for articles that mention:
- EU AI Act or other AI regulations
- Copyright lawsuits (NYT vs OpenAI, etc.)
- Content licensing deals (Reddit, News Corp, etc.)
- Provenance and watermarking requirements
- AI training data consent issues
- Opt-out mechanisms and robots.txt changes
- Platform terms of service changes

## INFRASTRUCTURE & IP SIGNALS
Evidence of who controls key infrastructure and intellectual property.

Look for articles about:
- API control and access (OpenAI, Google, etc.)
- Platform gatekeeping
- Patents and IP positioning
- Data pipeline ownership
- Compute resource control

Respond with JSON (cite specific article numbers):
{{
    "power_score": <0-100 based on evidence volume and urgency>,
    "score_justification": "Score based on evidence found, citing articles [1][2]",

    "t2_evidence": {{
        "trend_name": "Agentic AI Reshaping Workflows",
        "evidence_count": <number of relevant articles>,
        "trend_direction": "accelerating|stable|decelerating",
        "signals": [
            {{"finding": "What the article reports about AI agents [1]", "source": "Source name", "impact": "high|medium|low"}},
            {{"finding": "Workflow automation evidence [2]", "source": "Source name", "impact": "high|medium|low"}}
        ],
        "automation_examples": ["Specific examples of AI automating tasks [1]"],
        "tools_mentioned": ["Specific AI tools/platforms mentioned (e.g., ChatGPT, Copilot, Elicit, AlphaFold)"],
        "adoption_signals": [
            {{"entity": "Who is adopting (company/university/publisher)", "tool_or_change": "What they adopted or changed", "source": "[1]"}}
        ],
        "summary": "Summary of T2 evidence from articles"
    }},

    "t4_evidence": {{
        "trend_name": "Regulatory & Provenance Pressures",
        "evidence_count": <number of relevant articles>,
        "trend_direction": "accelerating|stable|decelerating",
        "signals": [
            {{"finding": "Regulatory development mentioned [3]", "source": "Source name", "impact": "high|medium|low"}},
            {{"finding": "Licensing/copyright evidence [4]", "source": "Source name", "impact": "high|medium|low"}}
        ],
        "regulatory_events": [
            {{"event": "Specific regulation or lawsuit [5]", "jurisdiction": "EU|US|Global", "impact": "high|medium|low"}}
        ],
        "licensing_deals": [
            {{"deal": "Deal description [6]", "parties": ["Party A", "Party B"], "significance": "What this means"}}
        ],
        "summary": "Summary of T4 evidence from articles"
    }},

    "infrastructure_control": {{
        "key_players_mentioned": ["Companies controlling infrastructure discussed in articles"],
        "control_signals": [
            {{"finding": "What articles say about platform control [1]", "source": "Source name"}}
        ],
        "concentration_trend": "Based on article evidence, is control concentrating or fragmenting?"
    }},

    "ip_positioning": {{
        "patent_mentions": <number of articles mentioning patents>,
        "licensing_signals": [
            {{"finding": "What articles say about IP/licensing [2]", "source": "Source name"}}
        ],
        "key_developments": ["Specific IP developments mentioned"]
    }},

    "key_events": [
        {{"event": "Specific news event from articles [1]", "trend": "T2|T4", "impact": "high|medium|low", "source": "Source name"}}
    ],

    "publisher_implications": "Based on the article evidence, what does this mean for publisher power? Cite specific findings.",

    "summary": "2-3 sentence summary of power dynamics based on article evidence [1][2][3]"
}}
"""

        try:
            response = await self._call_llm(prompt)
            content = self._extract_json(response)
            return json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"Power: Failed to parse LLM response: {e}")
            return {
                "power_score": 50,
                "error": "Failed to parse analysis",
                "raw_response": response[:500] if response else None
            }
        except Exception as e:
            logger.error(f"Power: LLM analysis failed: {e}")
            return {"power_score": 50, "error": str(e)}

    async def _synthesize_results(
        self,
        articles: List[Dict],
        article_metrics: Dict[str, MetricResult],
        external_data: Dict[str, Any],
        llm_analysis: Dict[str, Any],
        context: AnalysisContext
    ) -> Dict[str, Any]:
        """Synthesize POWER results from all data sources."""

        # Calculate composite score
        # Weight: 40% LLM analysis (evidence-based), 30% external data, 30% article metrics
        llm_score = llm_analysis.get("power_score", 50)
        external_score = external_data.get("regulatory_score", 50)
        article_score = self._calculate_article_based_score(article_metrics)

        composite_score = (
            llm_score * 0.40 +
            external_score * 0.30 +
            article_score * 0.30
        )

        # Extract evidence components
        t2_evidence = llm_analysis.get("t2_evidence", {})
        t4_evidence = llm_analysis.get("t4_evidence", {})
        infrastructure_control = llm_analysis.get("infrastructure_control", {})
        ip_positioning = llm_analysis.get("ip_positioning", {})

        return {
            "pillar": "power",
            "power_score": round(composite_score, 1),
            "score": round(composite_score, 1),
            "score_justification": llm_analysis.get("score_justification", ""),
            "score_breakdown": {
                "llm_analysis": {"score": llm_score, "weight": 0.40, "source": "evidence_extraction"},
                "external_data": {"score": external_score, "weight": 0.30, "source": "google_search"},
                "article_metrics": {"score": article_score, "weight": 0.30, "source": "measured"}
            },

            # Measured metrics
            "measured": {
                metric.name: metric.to_dict()
                for metric in article_metrics.values()
            },

            # External data
            "external": external_data,

            # T2 Evidence: Agentic AI Reshaping Workflows
            "t2_evidence": {
                "trend_name": t2_evidence.get("trend_name", "Agentic AI Reshaping Workflows"),
                "evidence_count": t2_evidence.get("evidence_count", 0),
                "trend_direction": t2_evidence.get("trend_direction", "stable"),
                "signals": t2_evidence.get("signals", []),
                "automation_examples": t2_evidence.get("automation_examples", []),
                "tools_mentioned": t2_evidence.get("tools_mentioned", []),
                "adoption_signals": t2_evidence.get("adoption_signals", []),
                "summary": t2_evidence.get("summary", "No T2 evidence found in articles")
            },

            # T4 Evidence: Regulatory & Provenance Pressures
            "t4_evidence": {
                "trend_name": t4_evidence.get("trend_name", "Regulatory & Provenance Pressures"),
                "evidence_count": t4_evidence.get("evidence_count", 0),
                "trend_direction": t4_evidence.get("trend_direction", "stable"),
                "signals": t4_evidence.get("signals", []),
                "regulatory_events": t4_evidence.get("regulatory_events", []),
                "licensing_deals": t4_evidence.get("licensing_deals", []),
                "summary": t4_evidence.get("summary", "No T4 evidence found in articles")
            },

            # Infrastructure Control (from article evidence)
            "infrastructure_control": {
                "key_players_mentioned": infrastructure_control.get("key_players_mentioned", []),
                "control_signals": infrastructure_control.get("control_signals", []),
                "concentration_trend": infrastructure_control.get("concentration_trend", "Unable to assess from articles"),
                # Legacy fields for backwards compatibility
                "score": self._calculate_t2_score(t2_evidence),
                "key_players": infrastructure_control.get("key_players_mentioned", []),
                "developments": [s.get("finding", "") for s in t2_evidence.get("signals", [])[:3]],
                "concentration_level": self._assess_concentration(infrastructure_control)
            },

            # Regulatory Influence (from article evidence)
            "regulatory_influence": {
                "score": self._calculate_t4_score(t4_evidence),
                "active_regulations": [e.get("event", "") for e in t4_evidence.get("regulatory_events", [])],
                "key_developments": [s.get("finding", "") for s in t4_evidence.get("signals", [])[:3]],
                "direction": self._assess_regulatory_direction(t4_evidence)
            },

            # Network Centrality (derived from infrastructure evidence)
            "network_centrality": {
                "score": None,  # Cannot measure directly from articles
                "influential_entities": infrastructure_control.get("key_players_mentioned", []),
                "collaboration_trends": "See T2 evidence for workflow collaboration signals"
            },

            # IP Positioning (from article evidence)
            "ip_positioning": {
                "patent_mentions": ip_positioning.get("patent_mentions", 0),
                "licensing_signals": ip_positioning.get("licensing_signals", []),
                "key_developments": ip_positioning.get("key_developments", []),
                # Legacy fields
                "score": self._calculate_ip_score(ip_positioning, t4_evidence),
                "key_deals": [d.get("deal", "") for d in t4_evidence.get("licensing_deals", [])],
                "trends": "; ".join(ip_positioning.get("key_developments", [])[:2]) if ip_positioning.get("key_developments") else "No IP trends identified"
            },

            "key_events": llm_analysis.get("key_events", []),
            "publisher_implications": llm_analysis.get("publisher_implications", ""),
            "summary": llm_analysis.get("summary", ""),

            # Metadata
            "articles_analyzed": len(articles),
            "model_used": self.model,
            "data_sources": ["article_database", "evidence_extraction"] +
                           (["google_search"] if external_data.get("regulatory") else [])
        }

    def _calculate_article_based_score(self, metrics: Dict[str, MetricResult]) -> float:
        """Calculate score from article-based metrics."""
        article_count = metrics.get("article_count")
        if not article_count:
            return 50.0

        count = article_count.value

        # Logarithmic scaling
        import math
        if count <= 0:
            return 30.0

        # 10 articles = 50, 50 articles = 70, 100+ = 85
        score = 30 + (math.log10(count + 1) / math.log10(100)) * 55
        return min(85, max(30, score))

    def _calculate_t2_score(self, t2_evidence: Dict) -> int | None:
        """Calculate T2 score from evidence. Returns None if no evidence found."""
        count = t2_evidence.get("evidence_count", 0)
        direction = t2_evidence.get("trend_direction", "stable")
        automation_count = len(t2_evidence.get("automation_examples", []))

        # Return None if no evidence - don't show fake 50
        if count == 0 and automation_count == 0:
            return None

        base = 50
        if count > 5:
            base = 70
        elif count > 2:
            base = 60
        elif count > 0:
            base = 55

        # Boost for automation examples
        base += min(10, automation_count * 3)

        if direction == "accelerating":
            base += 10
        elif direction == "decelerating":
            base -= 10

        return min(100, max(0, base))

    def _calculate_t4_score(self, t4_evidence: Dict) -> int | None:
        """Calculate T4 score from evidence. Returns None if no evidence found."""
        count = t4_evidence.get("evidence_count", 0)
        direction = t4_evidence.get("trend_direction", "stable")
        reg_events = len(t4_evidence.get("regulatory_events", []))
        licensing_deals = len(t4_evidence.get("licensing_deals", []))

        # Return None if no evidence - don't show fake 50
        if count == 0 and reg_events == 0 and licensing_deals == 0:
            return None

        base = 50
        if count > 5:
            base = 70
        elif count > 2:
            base = 60
        elif count > 0:
            base = 55

        # Boost for specific regulatory events and deals
        base += min(15, reg_events * 4)
        base += min(10, licensing_deals * 3)

        if direction == "accelerating":
            base += 10
        elif direction == "decelerating":
            base -= 10

        return min(100, max(0, base))

    def _calculate_ip_score(self, ip_positioning: Dict, t4_evidence: Dict) -> int | None:
        """Calculate IP score from evidence. Returns None if no evidence found."""
        patent_mentions = ip_positioning.get("patent_mentions", 0)
        licensing_signals = len(ip_positioning.get("licensing_signals", []))
        licensing_deals = len(t4_evidence.get("licensing_deals", []))

        # Return None if no evidence - don't show fake 50
        if patent_mentions == 0 and licensing_signals == 0 and licensing_deals == 0:
            return None

        base = 50
        base += min(15, patent_mentions * 3)
        base += min(10, licensing_signals * 3)
        base += min(15, licensing_deals * 4)

        return min(100, max(0, base))

    def _assess_concentration(self, infrastructure: Dict) -> str:
        """Assess concentration level from evidence."""
        players = infrastructure.get("key_players_mentioned", [])
        trend = infrastructure.get("concentration_trend", "")

        if "concentrat" in trend.lower():
            return "high"
        elif len(players) > 5:
            return "moderate"
        elif len(players) > 2:
            return "moderate"
        return "low"

    def _assess_regulatory_direction(self, t4_evidence: Dict) -> str:
        """Assess regulatory direction from evidence."""
        direction = t4_evidence.get("trend_direction", "stable")
        events = len(t4_evidence.get("regulatory_events", []))

        if direction == "accelerating" or events > 3:
            return "tightening"
        elif direction == "decelerating":
            return "loosening"
        return "stable"
