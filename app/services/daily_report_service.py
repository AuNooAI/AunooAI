"""
Desk Briefing Synthesis Service (Briefing Desk Feature)

Generates AI-powered synthesis for curated briefings.
Unlike Executive Briefing, this skips article selection since
articles/incidents are manually curated by the user.

2-Stage Workflow:
1. ANALYSIS: Analyze each article and incident for key insights
2. SYNTHESIS: Create briefing summary, cross-item themes, priority actions
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Optional, AsyncGenerator, Any

import litellm

from app.ai_models import resolve_litellm_call_params
from app.services.tool_loader import get_tool_loader

logger = logging.getLogger(__name__)


def _llm_token_kwargs(model: str, *, output_tokens: int) -> dict:
    """LLM call params that respect the model family.

    OpenAI's gpt-5.4 series is a reasoning model — by default it burns the
    output token budget on internal reasoning before emitting any
    user-visible text, so a plain ``max_tokens=N`` returns 0 chars on any
    non-trivial prompt. Pass ``reasoning_effort='minimal'`` (smallest
    reasoning step) and ``max_completion_tokens`` (not ``max_tokens``)
    plus a 4× headroom multiplier so the JSON output has room.

    Non-reasoning models (gpt-5.4*, claude, etc.) keep the standard
    ``max_tokens`` shape; ``temperature`` continues to apply.
    """
    if (model or "").startswith("gpt-5"):
        from app.ai_models import minimal_reasoning_effort
        return {
            "reasoning_effort": minimal_reasoning_effort(model),
            "max_completion_tokens": max(output_tokens * 4, 4000),
        }
    return {"max_tokens": output_tokens}


@dataclass
class DRConfig:
    """Configuration for Desk Briefing synthesis."""
    # Model settings
    analysis_model: str = "gpt-5.4"
    synthesis_model: str = "gpt-5.4"

    # Temperature settings
    analysis_temp: float = 0.4
    synthesis_temp: float = 0.5

    # Timeouts (seconds)
    analysis_timeout: int = 120
    synthesis_timeout: int = 90


class DailyReportService:
    """
    Desk Briefing Synthesis Service

    Generates AI synthesis for user-curated briefings containing
    articles and incidents from any topic.
    """

    def __init__(self):
        self.tool_loader = get_tool_loader()

    def _load_agent_prompt(self, agent_name: str) -> Optional[str]:
        """Load agent prompt from tool loader."""
        agent = self.tool_loader.get_agent(agent_name)
        if agent:
            return agent.content
        return None

    def _get_agent_config(self, agent_name: str) -> Dict:
        """Get agent model config from tool loader."""
        agent = self.tool_loader.get_agent(agent_name)
        if agent and agent.metadata:
            return agent.metadata.get('model_config', {})
        return {}

    async def generate_synthesis(
        self,
        briefing_name: str,
        articles: List[Dict],
        incidents: List[Dict],
        model: str = "gpt-5.4",
        organizational_profile: str = None,
        persona: str = None
    ) -> AsyncGenerator[Dict, None]:
        """
        Generate AI synthesis for a desk briefing.

        Args:
            briefing_name: Name of the briefing
            articles: List of curated article dicts
            incidents: List of curated incident dicts
            model: AI model to use
            organizational_profile: Organization name/type for tailored context
            persona: Role/persona for tailored recommendations

        Yields:
            Progress updates and final synthesis
        """
        config = DRConfig(
            analysis_model=model,
            synthesis_model=model
        )

        scan_id = str(uuid.uuid4())
        total_items = len(articles) + len(incidents)

        try:
            # Stage 1: Analysis
            yield {
                "stage": "analysis",
                "status": "started",
                "progress": 0.0,
                "scan_id": scan_id,
                "total_items": total_items
            }

            analyzed_articles = []
            analyzed_incidents = []

            # Analyze articles
            for idx, article in enumerate(articles):
                yield {
                    "stage": "analysis",
                    "status": "analyzing_article",
                    "progress": idx / max(total_items, 1),
                    "current_item": idx + 1,
                    "total_items": total_items,
                    "item_title": article.get('title', '')[:50]
                }

                analyzed = await self._analyze_article(article, config)
                analyzed_articles.append(analyzed)

            # Analyze incidents
            for idx, incident in enumerate(incidents):
                progress = (len(articles) + idx) / max(total_items, 1)
                yield {
                    "stage": "analysis",
                    "status": "analyzing_incident",
                    "progress": progress,
                    "current_item": len(articles) + idx + 1,
                    "total_items": total_items,
                    "item_title": incident.get('name', '')[:50]
                }

                analyzed = await self._analyze_incident(incident, config)
                analyzed_incidents.append(analyzed)

            yield {
                "stage": "analysis",
                "status": "completed",
                "progress": 1.0,
                "articles_analyzed": len(analyzed_articles),
                "incidents_analyzed": len(analyzed_incidents)
            }

            # Stage 2: Synthesis
            yield {
                "stage": "synthesis",
                "status": "started",
                "progress": 0.0
            }

            synthesis_result = await asyncio.wait_for(
                self._run_synthesis(
                    briefing_name=briefing_name,
                    articles=analyzed_articles,
                    incidents=analyzed_incidents,
                    config=config,
                    organizational_profile=organizational_profile,
                    persona=persona
                ),
                timeout=config.synthesis_timeout
            )

            yield {
                "stage": "synthesis",
                "status": "completed",
                "progress": 1.0
            }

            # Final result
            yield {
                "stage": "complete",
                "status": "success",
                "progress": 1.0,
                "scan_id": scan_id,
                "synthesis": synthesis_result.get("briefing_summary", ""),
                "themes": synthesis_result.get("themes", []),
                "priority_actions": synthesis_result.get("priority_actions", []),
                "analyzed_articles": analyzed_articles,
                "analyzed_incidents": analyzed_incidents,
                "metadata": {
                    "briefing_name": briefing_name,
                    "articles_count": len(articles),
                    "incidents_count": len(incidents),
                    "generated_at": datetime.now().isoformat(),
                    "model": model
                }
            }

        except asyncio.TimeoutError:
            logger.error(f"Desk briefing synthesis timed out for '{briefing_name}'")
            yield {
                "stage": "error",
                "status": "timeout",
                "error": "Synthesis timed out"
            }

        except Exception as e:
            logger.error(f"Desk briefing synthesis failed: {e}", exc_info=True)
            yield {
                "stage": "error",
                "status": "failed",
                "error": str(e)
            }

    async def _analyze_article(self, article: Dict, config: DRConfig) -> Dict:
        """Analyze a single article for key insights."""
        # Load agent prompt if available
        agent_prompt = self._load_agent_prompt("dr_analysis_agent")
        agent_config = self._get_agent_config("dr_analysis_agent")

        model = agent_config.get('model', config.analysis_model)
        temperature = agent_config.get('temperature', config.analysis_temp)

        prompt = f"""Analyze this article and extract key insights for an executive briefing.

ARTICLE:
Title: {article.get('title', 'Untitled')}
Source: {article.get('source', 'Unknown')}
Date: {article.get('publication_date', 'Unknown')}
Topic: {article.get('topic', 'General')}

Summary:
{article.get('summary', 'No summary available.')[:800]}

Provide a brief analysis with:
1. Key Insight (1-2 sentences): The most important takeaway
2. Strategic Relevance: Why this matters for decision-makers
3. Category: policy/market/tech/workforce/security/society
4. Time Horizon: Immediate (30 days) / Medium (1-12 months) / Long-term (12+ months)
5. Risk/Opportunity: Is this primarily a risk, opportunity, or mixed?

Return JSON:
{{
    "key_insight": "The most important takeaway",
    "strategic_relevance": "Why this matters",
    "category": "market",
    "time_horizon": "Medium",
    "risk_opportunity": "opportunity"
}}
"""

        try:
            call_kwargs = {
                **resolve_litellm_call_params(model),
                "messages": [
                    {"role": "system", "content": agent_prompt or "You are an executive intelligence analyst extracting key insights from news articles."},
                    {"role": "user", "content": prompt}
                ],
                "response_format": {"type": "json_object"},
                **_llm_token_kwargs(model, output_tokens=1000),
            }
            if not model.startswith("gpt-5"):
                call_kwargs["temperature"] = temperature
            response = await litellm.acompletion(**call_kwargs)

            analysis = json.loads(response.choices[0].message.content)

            return {
                **article,
                "analysis": analysis
            }

        except Exception as e:
            logger.error(f"Article analysis failed: {e}")
            return {
                **article,
                "analysis": {
                    "key_insight": "Analysis unavailable",
                    "strategic_relevance": "",
                    "category": "unknown",
                    "time_horizon": "Medium",
                    "risk_opportunity": "mixed"
                }
            }

    async def _analyze_incident(self, incident: Dict, config: DRConfig) -> Dict:
        """Analyze a single incident for key insights."""
        agent_prompt = self._load_agent_prompt("dr_analysis_agent")
        agent_config = self._get_agent_config("dr_analysis_agent")

        model = agent_config.get('model', config.analysis_model)
        temperature = agent_config.get('temperature', config.analysis_temp)

        prompt = f"""Analyze this incident and extract key insights for an executive briefing.

INCIDENT:
Name: {incident.get('name', 'Untitled')}
Type: {incident.get('type', 'Unknown')}
Significance: {incident.get('significance', 'Unknown')}
Topic: {incident.get('topic', 'General')}
Timeline: {incident.get('timeline', 'Unknown')}

Description:
{incident.get('summary') or incident.get('description', 'No description available.')[:800]}

Provide a brief analysis with:
1. Key Insight (1-2 sentences): The most important takeaway
2. Strategic Relevance: Why this matters for decision-makers
3. Category: policy/market/tech/workforce/security/society
4. Time Horizon: Immediate (30 days) / Medium (1-12 months) / Long-term (12+ months)
5. Risk/Opportunity: Is this primarily a risk, opportunity, or mixed?

Return JSON:
{{
    "key_insight": "The most important takeaway",
    "strategic_relevance": "Why this matters",
    "category": "market",
    "time_horizon": "Medium",
    "risk_opportunity": "risk"
}}
"""

        try:
            call_kwargs = {
                **resolve_litellm_call_params(model),
                "messages": [
                    {"role": "system", "content": agent_prompt or "You are an executive intelligence analyst extracting key insights from incident reports."},
                    {"role": "user", "content": prompt}
                ],
                "response_format": {"type": "json_object"},
                **_llm_token_kwargs(model, output_tokens=1000),
            }
            if not model.startswith("gpt-5"):
                call_kwargs["temperature"] = temperature
            response = await litellm.acompletion(**call_kwargs)

            analysis = json.loads(response.choices[0].message.content)

            return {
                **incident,
                "analysis": analysis
            }

        except Exception as e:
            logger.error(f"Incident analysis failed: {e}")
            return {
                **incident,
                "analysis": {
                    "key_insight": "Analysis unavailable",
                    "strategic_relevance": "",
                    "category": "unknown",
                    "time_horizon": "Medium",
                    "risk_opportunity": "mixed"
                }
            }

    async def _run_synthesis(
        self,
        briefing_name: str,
        articles: List[Dict],
        incidents: List[Dict],
        config: DRConfig,
        organizational_profile: str = None,
        persona: str = None
    ) -> Dict:
        """Generate synthesis from analyzed articles and incidents."""
        agent_prompt = self._load_agent_prompt("dr_synthesis_agent")
        agent_config = self._get_agent_config("dr_synthesis_agent")

        model = agent_config.get('model', config.synthesis_model)
        temperature = agent_config.get('temperature', config.synthesis_temp)

        # Format articles for synthesis
        articles_text = ""
        for i, article in enumerate(articles, 1):
            analysis = article.get('analysis', {})
            articles_text += f"""
Article {i}: {article.get('title', 'Untitled')}
Source: {article.get('source', 'Unknown')} | Topic: {article.get('topic', 'General')}
Key Insight: {analysis.get('key_insight', 'N/A')}
Strategic Relevance: {analysis.get('strategic_relevance', 'N/A')}
Category: {analysis.get('category', 'unknown')} | Time Horizon: {analysis.get('time_horizon', 'Medium')}
Risk/Opportunity: {analysis.get('risk_opportunity', 'mixed')}
"""

        # Format incidents for synthesis
        incidents_text = ""
        for i, incident in enumerate(incidents, 1):
            analysis = incident.get('analysis', {})
            incidents_text += f"""
Incident {i}: {incident.get('name', 'Untitled')}
Type: {incident.get('type', 'Unknown')} | Significance: {incident.get('significance', 'Unknown')}
Topic: {incident.get('topic', 'General')}
Key Insight: {analysis.get('key_insight', 'N/A')}
Strategic Relevance: {analysis.get('strategic_relevance', 'N/A')}
Category: {analysis.get('category', 'unknown')} | Time Horizon: {analysis.get('time_horizon', 'Medium')}
Risk/Opportunity: {analysis.get('risk_opportunity', 'mixed')}
"""

        # Build context section based on profile and persona
        context_section = ""
        if organizational_profile or persona:
            context_section = "\nORGANIZATIONAL CONTEXT:\n"
            if organizational_profile:
                context_section += f"Organization: {organizational_profile}\n"
            if persona:
                context_section += f"Target Audience/Role: {persona}\n"
            context_section += """
CRITICAL FRAMING REQUIREMENTS:
- Frame all strategic considerations from the perspective of the specified role/persona
- Present DECISION OPTIONS with potential outcomes, NOT directives
- Never tell executives what to do - instead present choices they could consider
- For each consideration, explain the trade-offs and potential outcomes of different paths
- Use language like "Option to consider:", "Potential path:", "Decision point:" rather than commands
"""

        prompt = f"""Synthesize an executive briefing from these curated articles and incidents.

BRIEFING NAME: {briefing_name}
{context_section}
ARTICLES ({len(articles)} items):
{articles_text if articles_text else "No articles included."}

INCIDENTS ({len(incidents)} items):
{incidents_text if incidents_text else "No incidents included."}

STRICT REQUIREMENTS:

1. BRIEFING SUMMARY (3-5 sentences):
   - Start with the SINGLE most concrete finding - cite specific facts, names, numbers, or events
   - NO generic openings like "The [X] landscape is rapidly evolving" or "In today's environment"
   - Each sentence must contain specific information from the articles/incidents
   - Reference actual entities, dates, or metrics mentioned in the source material
   - End with a specific, actionable implication

2. CROSS-ITEM THEMES (2-4 themes):
   - Theme names must be specific (not generic like "Digital Transformation" or "Market Dynamics")
   - Good example: "Regulatory Pressure on AI Model Training Data"
   - Bad example: "Evolving Technology Landscape"
   - Each theme must cite which specific articles/incidents support it
   - Strategic implications must be concrete and actionable

3. STRATEGIC CONSIDERATIONS (3-5 decision points):
   - CRITICAL: Present these as DECISION OPTIONS with outcomes, NOT directives
   - Frame each as a choice the specified role/persona could consider
   - Include potential outcomes for different decision paths
   - NEVER use imperative/command language (no "Launch...", "Review...", "Implement...")
   - DO use framing like: "Consider whether to...", "Evaluate the option of...", "Weigh the trade-offs of..."
   - For each consideration, explain:
     a) What decision could be made
     b) Potential positive outcomes if pursued
     c) Risks or trade-offs to consider
   - Good example: "Consider whether to pilot AI-powered ad platforms: pursuing this could open new revenue streams with early-mover advantage, while waiting allows competitors to validate ROI first"
   - Bad example: "Launch a pilot program with OpenAI's ChatGPT ad platform by end of Q3"
   - These should inform executive judgment, not replace it

FORBIDDEN PHRASES (do not use these or similar):
- "rapidly evolving"
- "in today's landscape/environment"
- "staying ahead of the curve"
- "navigate the complexities"
- "dynamic environment"
- "ever-changing"
- "transformative"
- "unprecedented"
- "game-changing"

FORBIDDEN IN PRIORITY ACTIONS (never use imperative commands):
- "Launch..." / "Implement..." / "Deploy..."
- "Review..." / "Assess..." / "Evaluate..." (as commands)
- "Engage..." / "Contact..." / "Meet with..."
- "[Role] to [action]..." (e.g., "Legal team to review...")
- Any sentence that tells someone what to do

Return JSON:
{{
    "briefing_summary": "3-5 sentences with specific facts from the source material",
    "themes": [
        {{
            "theme_name": "Specific pattern name",
            "description": "Concrete description with cited evidence",
            "supporting_items": ["Article 1", "Incident 2"],
            "strategic_implication": "Specific actionable implication"
        }}
    ],
    "priority_actions": [
        {{
            "action": "Decision option framed as consideration with outcomes (e.g., 'Consider whether to X: pursuing this could Y, while not acting may Z')",
            "urgency": "immediate/this_week/this_month/this_quarter",
            "rationale": "Trade-offs and context for this decision, citing specific evidence"
        }}
    ]
}}

Present strategic considerations that inform executive judgment, not replace it."""

        try:
            call_kwargs = {
                **resolve_litellm_call_params(model),
                "messages": [
                    {"role": "system", "content": agent_prompt or "You are a strategic intelligence analyst synthesizing curated news and incidents into actionable executive briefings. You identify patterns across items and provide strategic guidance."},
                    {"role": "user", "content": prompt}
                ],
                "response_format": {"type": "json_object"},
                **_llm_token_kwargs(model, output_tokens=3000),
            }
            if not model.startswith("gpt-5"):
                call_kwargs["temperature"] = temperature
            response = await litellm.acompletion(**call_kwargs)

            raw = response.choices[0].message.content or ""
            logger.info("Briefing synthesis: %s returned %d chars for '%s'",
                        model, len(raw), briefing_name)
            result = json.loads(raw)
            logger.info(f"Synthesis complete for '{briefing_name}'")
            return result

        except Exception as e:
            logger.error(f"Synthesis failed ({model}): {type(e).__name__}: {e}")
            return {
                "briefing_summary": f"Briefing of {len(articles)} articles and {len(incidents)} incidents.",
                "themes": [],
                "priority_actions": []
            }


# Singleton instance
_dr_instance: Optional[DailyReportService] = None


def get_daily_report_service() -> DailyReportService:
    """Get the global Desk Briefing service instance."""
    global _dr_instance
    if _dr_instance is None:
        _dr_instance = DailyReportService()
    return _dr_instance
