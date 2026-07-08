"""
Executive Briefing Service

Generates executive-focused article briefings with persona-based analysis.
Transforms raw news articles into actionable intelligence for busy executives.

3-Stage Workflow:
1. SELECTION: Score and select top N articles based on persona criteria
2. ANALYSIS: Generate executive analysis for each selected article
3. SYNTHESIS: Create briefing summary, cross-article themes, priority actions
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Optional, AsyncGenerator, Any
from enum import Enum

import litellm

from app.ai_models import resolve_litellm_call_params
from app.database import get_database_instance
from app.services.tool_loader import get_tool_loader

logger = logging.getLogger(__name__)


class EBStage(str, Enum):
    """Executive Briefing generation workflow stages."""
    SELECTION = "selection"
    ANALYSIS = "analysis"
    SYNTHESIS = "synthesis"
    PODCAST = "podcast"
    COMPLETE = "complete"
    ERROR = "error"


# Default persona configurations
DEFAULT_PERSONAS = {
    "CEO": {
        "priorities": "Regulation, enterprise adoption, scaling limits, market dynamics, security/safety, workforce impact, strategic partnerships",
        "risk_appetite": "moderate",
        "focus": "business strategy, market positioning, competitive advantage, and regulatory compliance"
    },
    "CMO": {
        "priorities": "Market trends, customer behavior, brand impact, advertising innovation, customer experience, competitive positioning",
        "risk_appetite": "high",
        "focus": "marketing strategies, customer engagement, brand differentiation, and market opportunities"
    },
    "CTO": {
        "priorities": "Technical breakthroughs, infrastructure, scalability, development tools, architecture patterns, security vulnerabilities",
        "risk_appetite": "high",
        "focus": "technical architecture, development practices, technology stack decisions, and engineering excellence"
    },
    "CISO": {
        "priorities": "Security threats, vulnerabilities, compliance requirements, risk management, data protection, incident response",
        "risk_appetite": "low",
        "focus": "security risks, compliance requirements, threat mitigation, and data protection"
    }
}


@dataclass
class BriefingArticle:
    """Represents an analyzed article in the executive briefing."""
    # Basic info
    title: str
    source: str
    date: str
    url: str
    uri: str

    # Executive analysis
    executive_takeaway: str = ""  # <20 words critical insight
    summary: str = ""  # 2-3 sentences
    strategic_relevance: str = ""  # Why it matters for persona

    # Classification
    time_horizon: str = "Medium"  # Immediate/Medium/Long-term
    risk_opportunity: str = "mixed"  # risk/opportunity/mixed
    signal_strength: str = "moderate"  # weak/moderate/strong
    category: str = "market"  # policy/market/tech/workforce/security/society

    # Actions and relationships
    executive_action: List[str] = field(default_factory=list)
    key_entities: List[str] = field(default_factory=list)
    related_topics: List[str] = field(default_factory=list)

    # Scores
    scores: Dict[str, int] = field(default_factory=lambda: {
        "relevance": 3,
        "novelty": 3,
        "credibility": 3,
        "representativeness": 3
    })

    # Selection metadata
    selection_rationale: str = ""
    overall_score: float = 0.0

    # User edits
    user_notes: Optional[str] = None
    user_edited: bool = False

    def to_dict(self) -> Dict:
        return {
            "title": self.title,
            "source": self.source,
            "date": self.date,
            "url": self.url,
            "uri": self.uri,
            "executive_takeaway": self.executive_takeaway,
            "summary": self.summary,
            "strategic_relevance": self.strategic_relevance,
            "time_horizon": self.time_horizon,
            "risk_opportunity": self.risk_opportunity,
            "signal_strength": self.signal_strength,
            "category": self.category,
            "executive_action": self.executive_action,
            "key_entities": self.key_entities,
            "related_topics": self.related_topics,
            "scores": self.scores,
            "selection_rationale": self.selection_rationale,
            "overall_score": self.overall_score,
            "user_notes": self.user_notes,
            "user_edited": self.user_edited
        }


@dataclass
class EBState:
    """Tracks state across Executive Briefing workflow stages."""
    scan_id: str
    topic: str
    persona: str
    created_at: datetime = field(default_factory=datetime.now)

    # Stage 1: Selection outputs
    raw_articles: List[Dict] = field(default_factory=list)
    selected_articles: List[Dict] = field(default_factory=list)

    # Stage 2: Analysis outputs
    analyzed_articles: List[BriefingArticle] = field(default_factory=list)

    # Stage 3: Synthesis outputs
    briefing_summary: str = ""
    themes: List[Dict] = field(default_factory=list)
    priority_actions: List[Dict] = field(default_factory=list)
    risk_summary: Dict = field(default_factory=dict)
    opportunity_summary: Dict = field(default_factory=dict)
    focus_areas: List[Dict] = field(default_factory=list)

    # Stage 4: Podcast script (optional)
    podcast_script: str = ""

    # Progress tracking
    current_stage: EBStage = EBStage.SELECTION
    stage_progress: Dict[str, float] = field(default_factory=lambda: {
        "selection": 0.0,
        "analysis": 0.0,
        "synthesis": 0.0,
        "podcast": 0.0
    })
    articles_processed: int = 0
    errors: List[str] = field(default_factory=list)

    def update_progress(self, stage: str, progress: float):
        self.stage_progress[stage] = min(1.0, max(0.0, progress))
        self.current_stage = EBStage(stage)

    def overall_progress(self) -> float:
        weights = {
            "selection": 0.25,
            "analysis": 0.50,
            "synthesis": 0.25
        }
        return sum(self.stage_progress.get(s, 0) * w for s, w in weights.items())

    def to_dict(self) -> Dict:
        return {
            "scan_id": self.scan_id,
            "topic": self.topic,
            "persona": self.persona,
            "created_at": self.created_at.isoformat(),
            "current_stage": self.current_stage.value,
            "stage_progress": self.stage_progress,
            "overall_progress": self.overall_progress(),
            "articles_total": len(self.raw_articles),
            "articles_selected": len(self.selected_articles),
            "articles_analyzed": len(self.analyzed_articles),
            "articles_processed": self.articles_processed,
            "errors": self.errors
        }


@dataclass
class EBConfig:
    """Configuration for Executive Briefing generation."""
    # Persona settings
    persona: str = "CEO"
    custom_persona: Optional[Dict] = None
    article_count: int = 6  # 1-8 articles

    # Content settings
    days_back: int = 1
    include_bias_analysis: bool = True
    include_synthesis: bool = True
    include_podcast_script: bool = False  # Optional podcast script generation
    podcast_duration: str = "short"  # short, medium, long

    # Model settings
    selection_model: str = "gpt-5.4"
    analysis_model: str = "gpt-5.4"
    synthesis_model: str = "gpt-5.4"
    podcast_model: str = "gpt-5.4"

    # Temperature settings
    selection_temp: float = 0.3
    analysis_temp: float = 0.4
    synthesis_temp: float = 0.5
    podcast_temp: float = 0.7

    # Timeouts (seconds)
    selection_timeout: int = 60
    analysis_timeout: int = 120
    synthesis_timeout: int = 60
    podcast_timeout: int = 60


class ExecutiveBriefingService:
    """
    Executive Briefing Service

    Generates executive-focused article briefings with persona-based analysis.

    Workflow:
    1. SELECTION: Score and select top N articles based on persona criteria
    2. ANALYSIS: Generate executive analysis for each selected article
    3. SYNTHESIS: Create briefing summary, cross-article themes, priority actions
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

    def _get_persona_config(self, persona: str, custom_persona: Optional[Dict] = None) -> Dict:
        """Get persona configuration."""
        if custom_persona:
            return custom_persona
        return DEFAULT_PERSONAS.get(persona, DEFAULT_PERSONAS["CEO"])

    async def run_generation(
        self,
        topic: str,
        articles: List[Dict],
        config: Optional[EBConfig] = None
    ) -> AsyncGenerator[Dict, None]:
        """
        Run Executive Briefing generation.

        Args:
            topic: The topic being analyzed
            articles: List of articles (with optional enrichment data)
            config: Optional configuration override

        Yields:
            Progress updates and final briefing
        """
        if config is None:
            config = EBConfig()

        state = EBState(
            scan_id=str(uuid.uuid4()),
            topic=topic,
            persona=config.persona,
            raw_articles=articles
        )

        try:
            # Stage 1: Selection
            yield {
                "stage": "selection",
                "status": "started",
                "progress": 0.0,
                "scan_id": state.scan_id,
                "total_articles": len(articles)
            }
            await asyncio.wait_for(
                self._run_selection(state, config),
                timeout=config.selection_timeout
            )
            state.update_progress("selection", 1.0)
            yield {
                "stage": "selection",
                "status": "completed",
                "progress": 1.0,
                "articles_selected": len(state.selected_articles)
            }

            # Stage 2: Analysis
            yield {
                "stage": "analysis",
                "status": "started",
                "progress": 0.0,
                "articles_to_analyze": len(state.selected_articles)
            }
            async for progress in self._run_analysis(state, config):
                state.update_progress("analysis", progress.get("progress", 0.0))
                yield {"stage": "analysis", **progress}
            state.update_progress("analysis", 1.0)
            yield {
                "stage": "analysis",
                "status": "completed",
                "progress": 1.0,
                "articles_analyzed": len(state.analyzed_articles)
            }

            # Stage 3: Synthesis
            if config.include_synthesis:
                yield {
                    "stage": "synthesis",
                    "status": "started",
                    "progress": 0.0
                }
                await asyncio.wait_for(
                    self._run_synthesis(state, config),
                    timeout=config.synthesis_timeout
                )
                state.update_progress("synthesis", 1.0)
            else:
                state.update_progress("synthesis", 1.0)

            # Stage 4: Podcast Script (optional)
            if config.include_podcast_script and state.briefing_summary:
                yield {
                    "stage": "podcast",
                    "status": "started",
                    "progress": 0.0
                }
                await asyncio.wait_for(
                    self._run_podcast_script(state, config),
                    timeout=config.podcast_timeout
                )
                state.update_progress("podcast", 1.0)
                yield {
                    "stage": "podcast",
                    "status": "completed",
                    "progress": 1.0,
                    "script_length": len(state.podcast_script)
                }
            else:
                state.update_progress("podcast", 1.0)

            # Final result
            yield {
                "stage": "complete",
                "status": "success",
                "progress": 1.0,
                "scan_id": state.scan_id,
                "articles": [a.to_dict() for a in state.analyzed_articles],
                "briefing_summary": state.briefing_summary,
                "themes": state.themes,
                "priority_actions": state.priority_actions,
                "risk_summary": state.risk_summary,
                "opportunity_summary": state.opportunity_summary,
                "focus_areas": state.focus_areas,
                "podcast_script": state.podcast_script,
                "metadata": {
                    "topic": topic,
                    "persona": config.persona,
                    "articles_analyzed": len(state.analyzed_articles),
                    "articles_total": len(state.raw_articles),
                    "generated_at": datetime.now().isoformat(),
                    "config": {
                        "article_count": config.article_count,
                        "days_back": config.days_back,
                        "include_synthesis": config.include_synthesis,
                        "include_podcast_script": config.include_podcast_script
                    }
                }
            }

        except asyncio.TimeoutError:
            logger.error(f"Executive briefing stage timed out: {state.current_stage}")
            state.errors.append(f"Timeout in {state.current_stage.value} stage")
            yield {
                "stage": state.current_stage.value,
                "status": "timeout",
                "error": "Stage timed out",
                "progress": state.overall_progress(),
                "partial_results": state.to_dict()
            }

        except Exception as e:
            logger.error(f"Executive briefing generation failed: {e}", exc_info=True)
            state.errors.append(str(e))
            yield {
                "stage": state.current_stage.value,
                "status": "error",
                "error": str(e),
                "progress": state.overall_progress(),
                "partial_results": state.to_dict()
            }

    def _extract_article_context(self, articles: List[Dict], include_full: bool = False) -> str:
        """Extract relevant context from articles for prompts."""
        context_parts = []
        limit = 30 if not include_full else len(articles)

        for i, article in enumerate(articles[:limit]):
            enrichment = article.get('enrichment', {})

            article_ctx = {
                "index": i,
                "title": article.get('title', '')[:200],
                "source": article.get('news_source', article.get('source', '')),
                "date": article.get('publication_date', article.get('date', '')),
                "url": article.get('uri', article.get('url', '')),
                "summary": article.get('summary', '')[:400],
            }

            # Add enrichment if available
            if enrichment:
                article_ctx.update({
                    "sentiment": enrichment.get('sentiment', 'neutral'),
                    "political_bias": enrichment.get('political_bias', article.get('bias', 'unknown')),
                    "categories": enrichment.get('categories', [])[:3],
                    "driver_type": enrichment.get('driver_type', article.get('driver_type', '')),
                    "factuality": enrichment.get('factuality', article.get('factual_reporting', ''))
                })
            else:
                # Use article-level fields if no enrichment
                article_ctx.update({
                    "sentiment": article.get('sentiment', 'neutral'),
                    "political_bias": article.get('bias', 'unknown'),
                    "factuality": article.get('factual_reporting', '')
                })

            context_parts.append(article_ctx)

        return json.dumps(context_parts, indent=2)

    async def _run_selection(self, state: EBState, config: EBConfig):
        """
        Stage 1: Selection
        Score and select top N articles based on persona criteria.
        """
        logger.info(f"Starting article selection for {state.topic} ({config.persona} persona)")

        agent_prompt = self._load_agent_prompt("eb_selection_agent")
        agent_config = self._get_agent_config("eb_selection_agent")

        model = agent_config.get('model', config.selection_model)
        temperature = agent_config.get('temperature', config.selection_temp)

        persona_config = self._get_persona_config(config.persona, config.custom_persona)
        article_context = self._extract_article_context(state.raw_articles)

        prompt = f"""Select the top {config.article_count} most strategically relevant articles for a {config.persona} executive about "{state.topic}".

PERSONA PROFILE:
- Role: {config.persona}
- Priorities: {persona_config.get('priorities', '')}
- Risk Appetite: {persona_config.get('risk_appetite', 'moderate')}
- Focus: {persona_config.get('focus', '')}

CANDIDATE ARTICLES:
{article_context}

SELECTION CRITERIA (score 0-5 on each):
1. Strategic Relevance: How directly does this impact the {config.persona}'s priorities?
2. Novelty: Does this provide new information or perspectives?
3. Credibility: How reliable is this source and its claims?
4. Representativeness: Does selecting this add perspective diversity?

SELECTION RULES:
- Select exactly {config.article_count} articles (or fewer if not enough quality candidates)
- Maximum 2 articles from any single news source
- Prioritize balance of perspectives when relevant
- Consider political bias diversity if bias data available

Return JSON with:
{{
    "selected_articles": [
        {{
            "article_index": 0,
            "title": "Article title",
            "source": "Source name",
            "url": "Article URL",
            "date": "Publication date",
            "relevance_score": 5,
            "novelty_score": 4,
            "credibility_score": 4,
            "representativeness_score": 3,
            "overall_score": 4.2,
            "selection_rationale": "Why this article matters for the {config.persona}"
        }}
    ],
    "selection_stats": {{
        "total_candidates": {len(state.raw_articles)},
        "articles_selected": {config.article_count},
        "domains_represented": 4,
        "bias_diversity_score": 0.75
    }}
}}

Select the articles that will best inform executive decision-making."""

        try:
            response = await litellm.acompletion(
                **resolve_litellm_call_params(model),
                messages=[
                    {"role": "system", "content": agent_prompt or "You are an executive news curator specializing in selecting strategically relevant articles for busy executives. You prioritize quality, relevance, and diversity."},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                max_tokens=3000,
                response_format={"type": "json_object"}
            )

            result = json.loads(response.choices[0].message.content)
            state.selected_articles = result.get("selected_articles", [])

        except Exception as e:
            logger.error(f"Selection stage failed: {e}")
            # Fallback: take first N articles
            state.selected_articles = [
                {
                    "article_index": i,
                    "title": a.get('title', ''),
                    "source": a.get('news_source', a.get('source', '')),
                    "url": a.get('uri', a.get('url', '')),
                    "date": a.get('publication_date', a.get('date', '')),
                    "overall_score": 3.0,
                    "selection_rationale": "Selected by fallback"
                }
                for i, a in enumerate(state.raw_articles[:config.article_count])
            ]

        logger.info(f"Articles selected: {len(state.selected_articles)}")

    async def _run_analysis(
        self,
        state: EBState,
        config: EBConfig
    ) -> AsyncGenerator[Dict, None]:
        """
        Stage 2: Analysis
        Generate executive analysis for each selected article.
        """
        logger.info(f"Analyzing {len(state.selected_articles)} articles for {config.persona}")

        agent_prompt = self._load_agent_prompt("eb_analysis_agent")
        agent_config = self._get_agent_config("eb_analysis_agent")

        model = agent_config.get('model', config.analysis_model)
        temperature = agent_config.get('temperature', config.analysis_temp)

        persona_config = self._get_persona_config(config.persona, config.custom_persona)

        total_articles = len(state.selected_articles)

        for idx, selected in enumerate(state.selected_articles):
            article_index = selected.get("article_index", idx)
            if article_index >= len(state.raw_articles):
                continue

            article = state.raw_articles[article_index]

            yield {
                "status": "analyzing",
                "progress": idx / total_articles,
                "current_article": idx + 1,
                "total_articles": total_articles,
                "article_title": article.get('title', '')[:50]
            }

            prompt = f"""Analyze this article for a {config.persona} executive about "{state.topic}".

PERSONA PROFILE:
- Role: {config.persona}
- Priorities: {persona_config.get('priorities', '')}
- Risk Appetite: {persona_config.get('risk_appetite', 'moderate')}
- Focus: {persona_config.get('focus', '')}

ARTICLE:
Title: {article.get('title', '')}
Source: {article.get('news_source', article.get('source', ''))}
Date: {article.get('publication_date', article.get('date', ''))}
URL: {article.get('uri', article.get('url', ''))}

Content Summary:
{article.get('summary', '')[:800]}

Selection Rationale: {selected.get('selection_rationale', '')}

ANALYSIS REQUIREMENTS:

1. Executive Takeaway (MAXIMUM 20 words): The single most important insight
2. Summary (2-3 sentences): Core facts only, no opinions
3. Strategic Relevance: Why this matters specifically for a {config.persona}
4. Time Horizon: Immediate (30 days) / Medium (1-12 months) / Long-term (12+ months)
5. Risk/Opportunity: Is this a risk, opportunity, or mixed for the organization?
6. Signal Strength: weak (single source) / moderate (developing story) / strong (well-established)
7. Executive Actions: 2-4 concrete, executive-level actions to consider
8. Category: policy/market/tech/workforce/security/society

Return JSON with:
{{
    "analyzed_article": {{
        "title": "{article.get('title', '')}",
        "source": "{article.get('news_source', article.get('source', ''))}",
        "date": "{article.get('publication_date', article.get('date', ''))}",
        "url": "{article.get('uri', article.get('url', ''))}",
        "executive_takeaway": "Maximum 20 words capturing the critical insight",
        "summary": "2-3 sentences of core facts",
        "strategic_relevance": "Why this matters for the {config.persona}",
        "time_horizon": "Immediate/Medium/Long-term",
        "risk_opportunity": "risk/opportunity/mixed",
        "signal_strength": "weak/moderate/strong",
        "executive_action": ["Action 1", "Action 2", "Action 3"],
        "category": "policy/market/tech/workforce/security/society",
        "scores": {{
            "relevance": 4,
            "novelty": 3,
            "credibility": 4,
            "representativeness": 3
        }},
        "key_entities": ["Entity1", "Entity2"],
        "related_topics": ["Topic1", "Topic2"]
    }}
}}

Write as if this will be the only thing the executive reads about this topic today."""

            try:
                response = await litellm.acompletion(
                    **resolve_litellm_call_params(model),
                    messages=[
                        {"role": "system", "content": agent_prompt or "You are an executive intelligence analyst specializing in distilling complex news into actionable insights. You write with precision and brevity for busy executives."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=temperature,
                    max_tokens=2000,
                    response_format={"type": "json_object"}
                )

                result = json.loads(response.choices[0].message.content)
                analyzed = result.get("analyzed_article", {})

                briefing_article = BriefingArticle(
                    title=analyzed.get("title", article.get('title', '')),
                    source=analyzed.get("source", article.get('news_source', article.get('source', ''))),
                    date=analyzed.get("date", article.get('publication_date', article.get('date', ''))),
                    url=analyzed.get("url", article.get('uri', article.get('url', ''))),
                    uri=article.get('uri', article.get('url', '')),
                    executive_takeaway=analyzed.get("executive_takeaway", ""),
                    summary=analyzed.get("summary", ""),
                    strategic_relevance=analyzed.get("strategic_relevance", ""),
                    time_horizon=analyzed.get("time_horizon", "Medium"),
                    risk_opportunity=analyzed.get("risk_opportunity", "mixed"),
                    signal_strength=analyzed.get("signal_strength", "moderate"),
                    category=analyzed.get("category", "market"),
                    executive_action=analyzed.get("executive_action", []),
                    key_entities=analyzed.get("key_entities", []),
                    related_topics=analyzed.get("related_topics", []),
                    scores=analyzed.get("scores", {"relevance": 3, "novelty": 3, "credibility": 3, "representativeness": 3}),
                    selection_rationale=selected.get("selection_rationale", ""),
                    overall_score=selected.get("overall_score", 3.0)
                )

                state.analyzed_articles.append(briefing_article)
                state.articles_processed += 1

            except Exception as e:
                logger.error(f"Analysis failed for article {idx}: {e}")
                # Add basic article info on failure
                state.analyzed_articles.append(BriefingArticle(
                    title=article.get('title', 'Analysis failed'),
                    source=article.get('news_source', article.get('source', '')),
                    date=article.get('publication_date', article.get('date', '')),
                    url=article.get('uri', article.get('url', '')),
                    uri=article.get('uri', article.get('url', '')),
                    executive_takeaway="Analysis unavailable",
                    summary=article.get('summary', '')[:200],
                    selection_rationale=selected.get("selection_rationale", "")
                ))

        yield {
            "status": "completed",
            "progress": 1.0,
            "articles_analyzed": len(state.analyzed_articles)
        }

    async def _run_synthesis(self, state: EBState, config: EBConfig):
        """
        Stage 3: Synthesis
        Create briefing summary, cross-article themes, priority actions.
        """
        logger.info(f"Synthesizing briefing for {len(state.analyzed_articles)} articles")

        agent_prompt = self._load_agent_prompt("eb_synthesis_agent")
        agent_config = self._get_agent_config("eb_synthesis_agent")

        model = agent_config.get('model', config.synthesis_model)
        temperature = agent_config.get('temperature', config.synthesis_temp)

        persona_config = self._get_persona_config(config.persona, config.custom_persona)
        articles_json = [a.to_dict() for a in state.analyzed_articles]

        prompt = f"""Synthesize an EXECUTIVE BRIEFING from these analyzed articles for a {config.persona} about "{state.topic}".

PERSONA PROFILE:
- Role: {config.persona}
- Priorities: {persona_config.get('priorities', '')}
- Risk Appetite: {persona_config.get('risk_appetite', 'moderate')}
- Focus: {persona_config.get('focus', '')}

ANALYZED ARTICLES:
{json.dumps(articles_json, indent=2)}

CREATE A SYNTHESIS WITH:

1. BRIEFING SUMMARY (3-5 sentences):
   - Lead with the most important insight
   - Connect articles into a coherent narrative
   - End with key implication or call to action

2. CROSS-ARTICLE THEMES (2-4 themes):
   - Pattern name
   - Description of the pattern
   - Which articles support it
   - Strategic implication

3. PRIORITY ACTIONS (3-5 actions):
   - Deduplicate similar actions from individual articles
   - Prioritize by urgency and impact
   - Include urgency level and rationale
   - CRITICAL: Every action must be one a {config.persona} can personally initiate — a decision, directive to their own organization, partnership, resourcing, or monitoring/hedging move that is within their actual sphere of control. NEVER recommend actions for governments, regulators, health authorities, NGOs, or any third party the reader does not run. If the news is about a crisis the reader cannot directly act on, the action is how the {config.persona} should respond within their own remit (e.g. commissioning, editorial, portfolio, research, or communication decisions), not how the crisis itself should be managed.
   - Name the actor for each action: it must be the {config.persona} or a function they command.

4. RISK SUMMARY:
   - Overall risk level: low/moderate/elevated/high
   - Top 3-5 key risks
   - Mitigation opportunities

5. OPPORTUNITY SUMMARY:
   - Overall opportunity level: limited/moderate/significant/transformative
   - Top 3-5 key opportunities
   - Time-sensitive action windows

6. FOCUS AREAS (2-4 areas):
   - Areas requiring close monitoring
   - Why they need attention
   - Time sensitivity

Return JSON with:
{{
    "briefing_summary": "3-5 sentence executive summary",
    "themes": [
        {{
            "theme_name": "Theme name",
            "description": "Pattern description",
            "articles_supporting": [0, 1, 2],
            "strategic_implication": "What this means for the {config.persona}"
        }}
    ],
    "priority_actions": [
        {{
            "action": "Specific action the {config.persona} can personally initiate",
            "actor": "The {config.persona} or a function they command",
            "urgency": "immediate/this_week/this_month/this_quarter",
            "rationale": "Why this matters",
            "related_themes": ["Theme name"]
        }}
    ],
    "risk_summary": {{
        "overall_risk_level": "low/moderate/elevated/high",
        "key_risks": ["Risk 1", "Risk 2", "Risk 3"],
        "mitigation_opportunities": ["Mitigation 1", "Mitigation 2"]
    }},
    "opportunity_summary": {{
        "overall_opportunity_level": "limited/moderate/significant/transformative",
        "key_opportunities": ["Opportunity 1", "Opportunity 2"],
        "action_windows": ["Window 1", "Window 2"]
    }},
    "focus_areas": [
        {{
            "area": "Focus area name",
            "reason": "Why it needs attention",
            "time_sensitivity": "Description of urgency"
        }}
    ],
    "briefing_metadata": {{
        "total_articles_analyzed": {len(state.analyzed_articles)},
        "dominant_category": "market",
        "average_signal_strength": "moderate",
        "time_horizon_distribution": {{
            "immediate": 1,
            "medium": 3,
            "long_term": 2
        }}
    }}
}}

Enable the {config.persona} to make better decisions in the next 24-48 hours."""

        try:
            response = await litellm.acompletion(
                **resolve_litellm_call_params(model),
                messages=[
                    {"role": "system", "content": agent_prompt or "You are a strategic intelligence analyst synthesizing multiple article analyses into actionable executive briefings. You identify patterns, prioritize actions, and provide strategic guidance."},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                max_tokens=4000,
                response_format={"type": "json_object"}
            )

            result = json.loads(response.choices[0].message.content)
            state.briefing_summary = result.get("briefing_summary", "")
            state.themes = result.get("themes", [])
            state.priority_actions = result.get("priority_actions", [])
            state.risk_summary = result.get("risk_summary", {})
            state.opportunity_summary = result.get("opportunity_summary", {})
            state.focus_areas = result.get("focus_areas", [])

        except Exception as e:
            logger.error(f"Synthesis stage failed: {e}")
            state.briefing_summary = f"Executive briefing of {len(state.analyzed_articles)} articles about {state.topic}."
            state.themes = []
            state.priority_actions = []
            state.risk_summary = {"overall_risk_level": "moderate", "key_risks": []}
            state.opportunity_summary = {"overall_opportunity_level": "moderate", "key_opportunities": []}
            state.focus_areas = []

        logger.info(f"Synthesis complete: {len(state.briefing_summary)} chars")

    async def _run_podcast_script(self, state: EBState, config: EBConfig):
        """
        Stage 4: Podcast Script Generation
        Create a professional podcast script from the briefing.
        """
        logger.info(f"Generating podcast script for {state.topic}")

        # Load agent prompt and config
        agent_prompt = self._load_agent_prompt("eb_podcast_agent")
        agent_config = self._get_agent_config("eb_podcast_agent")

        model = agent_config.get('model', config.podcast_model)
        temperature = agent_config.get('temperature', config.podcast_temp)

        # Duration guidance
        duration_map = {
            "short": "2-3 minutes (approximately 400-500 words)",
            "medium": "4-5 minutes (approximately 700-900 words)",
            "long": "7-10 minutes (approximately 1200-1500 words)"
        }
        duration_guidance = duration_map.get(config.podcast_duration, duration_map["short"])

        # Format themes
        themes_text = ""
        if state.themes:
            for i, theme in enumerate(state.themes[:5], 1):
                theme_name = theme.get('theme_name', 'Unknown Theme')
                description = theme.get('description', '')
                implication = theme.get('strategic_implication', '')
                themes_text += f"{i}. {theme_name}\n   {description}\n"
                if implication:
                    themes_text += f"   Strategic Implication: {implication}\n"
                themes_text += "\n"
        else:
            themes_text = "No specific themes identified."

        # Format priority actions
        actions_text = ""
        if state.priority_actions:
            for i, action in enumerate(state.priority_actions[:5], 1):
                action_text = action.get('action', '')
                urgency = action.get('urgency', 'this_month').replace('_', ' ')
                rationale = action.get('rationale', '')
                actions_text += f"{i}. [{urgency.upper()}] {action_text}\n"
                if rationale:
                    actions_text += f"   Rationale: {rationale}\n"
                actions_text += "\n"
        else:
            actions_text = "No specific actions recommended."

        # Build system prompt from agent prompt or fallback
        if agent_prompt:
            system_prompt = agent_prompt
        else:
            system_prompt = """You are an expert podcast script writer creating an executive intelligence briefing.

Create a concise, engaging podcast script for an executive audience. The script should:
1. Be written for a single presenter (news bulletin style)
2. Open with a brief welcome and topic introduction
3. Summarize the key intelligence findings
4. Highlight the most important themes and their strategic implications
5. Mention specific priority actions executives should consider
6. Close with a brief sign-off

Guidelines:
- Keep the tone professional but engaging
- Focus on strategic implications, not just facts
- Make it conversational but authoritative
- Do NOT include sound effects, music cues, or stage directions
- Do NOT include speaker tags like [Host] or timestamps
- Write as continuous prose that flows naturally when read aloud"""

        # User message with briefing content
        user_message = f"""Generate a podcast script with these specifications:

Target Duration: {duration_guidance}

Topic: {state.topic}

Executive Summary:
{state.briefing_summary}

Key Themes:
{themes_text}

Priority Actions:
{actions_text}

Generate a polished podcast script that an executive would want to listen to during their commute."""

        try:
            response = await litellm.acompletion(
                **resolve_litellm_call_params(model),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                temperature=temperature,
                max_tokens=agent_config.get('max_tokens', 3000)
            )

            state.podcast_script = response.choices[0].message.content.strip()
            logger.info(f"Podcast script generated: {len(state.podcast_script)} chars")

        except Exception as e:
            logger.error(f"Podcast script generation failed: {e}")
            # Fallback to basic script
            state.podcast_script = f"""Welcome to this executive briefing on {state.topic}.

{state.briefing_summary}

That concludes today's briefing. Stay informed and make strategic decisions."""


# Singleton instance
_eb_instance: Optional[ExecutiveBriefingService] = None


def get_executive_briefing_service() -> ExecutiveBriefingService:
    """Get the global Executive Briefing service instance."""
    global _eb_instance
    if _eb_instance is None:
        _eb_instance = ExecutiveBriefingService()
    return _eb_instance
