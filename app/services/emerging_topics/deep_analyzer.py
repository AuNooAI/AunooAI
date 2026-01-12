"""
Deep Analyzer Service

Performs deep analysis on validated themes to extract:
- Actors (companies, people, organizations)
- Events (trigger event, timeline, current status)
- Implications (industry, regulatory, market)
- Signals (growth indicators, risk factors, watch items)

Inspired by PAM's pillar agents pattern.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from sqlalchemy import text

from app.database import get_database_instance

logger = logging.getLogger(__name__)


DEEP_ANALYSIS_PROMPT = """Analyze this emerging topic in depth.

Topic: {theme_label}
Description: {theme_description}
{org_context}
Related Articles ({article_count} articles):
{articles_text}

Provide comprehensive analysis as valid JSON (no markdown):

{{
  "actors": {{
    "companies": ["List companies mentioned with brief role description"],
    "people": ["Key individuals and their positions/relevance"],
    "organizations": ["Government bodies, NGOs, institutions involved"]
  }},
  "events": {{
    "trigger_event": "What specific event or announcement started/drives this topic",
    "timeline": ["Chronological list of key developments mentioned in articles"],
    "current_status": "Where things stand now based on most recent articles"
  }},
  "general_implications": {{
    "industry_impact": "How this affects the industry or sector broadly",
    "regulatory": "General regulatory or policy implications",
    "market": "Broad market, business, or economic implications"
  }},
  "organization_implications": {{
    "strategic_relevance": "How this relates to the organization's strategic priorities (or general strategic considerations if no org context)",
    "stakeholder_impact": "Impact on key stakeholders",
    "risk_assessment": "Risks or opportunities this presents",
    "recommended_response": "Suggested actions or response"
  }},
  "signals": {{
    "growth_indicators": ["Signs this topic is growing in importance"],
    "risk_factors": ["Potential concerns or downsides mentioned"],
    "watch_for": ["What developments to monitor next"]
  }},
  "synthesis": {{
    "key_takeaway": "Single most important insight from this topic",
    "stakeholders_affected": ["Who is most impacted by this development"],
    "urgency": "low|medium|high - how time-sensitive is this topic"
  }}
}}

Requirements:
- Be SPECIFIC - use actual names, dates, numbers from articles
- For actors, only list those actually mentioned in the articles
- For timeline, include approximate dates if mentioned
- If information is not available in articles, say "Not mentioned"
- For organization_implications, tailor analysis to the organizational context if provided
"""


@dataclass
class Actors:
    """People and organizations involved."""
    companies: List[str] = field(default_factory=list)
    people: List[str] = field(default_factory=list)
    organizations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, List[str]]:
        return {
            "companies": self.companies,
            "people": self.people,
            "organizations": self.organizations,
        }


@dataclass
class Events:
    """Event timeline and status."""
    trigger_event: str = ""
    timeline: List[str] = field(default_factory=list)
    current_status: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trigger_event": self.trigger_event,
            "timeline": self.timeline,
            "current_status": self.current_status,
        }


@dataclass
class Implications:
    """General impact analysis (kept for backward compatibility)."""
    industry_impact: str = ""
    regulatory: str = ""
    market: str = ""

    def to_dict(self) -> Dict[str, str]:
        return {
            "industry_impact": self.industry_impact,
            "regulatory": self.regulatory,
            "market": self.market,
        }


@dataclass
class OrganizationImplications:
    """Organization-specific impact analysis."""
    strategic_relevance: str = ""
    stakeholder_impact: str = ""
    risk_assessment: str = ""
    recommended_response: str = ""

    def to_dict(self) -> Dict[str, str]:
        return {
            "strategic_relevance": self.strategic_relevance,
            "stakeholder_impact": self.stakeholder_impact,
            "risk_assessment": self.risk_assessment,
            "recommended_response": self.recommended_response,
        }


@dataclass
class Signals:
    """Growth and risk indicators."""
    growth_indicators: List[str] = field(default_factory=list)
    risk_factors: List[str] = field(default_factory=list)
    watch_for: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, List[str]]:
        return {
            "growth_indicators": self.growth_indicators,
            "risk_factors": self.risk_factors,
            "watch_for": self.watch_for,
        }


@dataclass
class Synthesis:
    """High-level synthesis."""
    key_takeaway: str = ""
    stakeholders_affected: List[str] = field(default_factory=list)
    urgency: str = "medium"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key_takeaway": self.key_takeaway,
            "stakeholders_affected": self.stakeholders_affected,
            "urgency": self.urgency,
        }


@dataclass
class DeepAnalysis:
    """Complete deep analysis result."""
    actors: Actors = field(default_factory=Actors)
    events: Events = field(default_factory=Events)
    implications: Implications = field(default_factory=Implications)
    organization_implications: OrganizationImplications = field(default_factory=OrganizationImplications)
    signals: Signals = field(default_factory=Signals)
    synthesis: Synthesis = field(default_factory=Synthesis)
    model_used: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "actors": self.actors.to_dict(),
            "events": self.events.to_dict(),
            "implications": self.implications.to_dict(),
            "organization_implications": self.organization_implications.to_dict(),
            "signals": self.signals.to_dict(),
            "synthesis": self.synthesis.to_dict(),
            "model_used": self.model_used,
        }


class DeepAnalyzer:
    """
    Performs deep analysis on emerging themes using LLM.
    """

    def __init__(
        self,
        ai_model_getter: Optional[Callable] = None,
        default_model: str = "gpt-4o"
    ):
        self.ai_model_getter = ai_model_getter
        self.default_model = default_model

    def _get_connection(self):
        """Get database connection."""
        db = get_database_instance()
        return db._temp_get_connection()

    def _fetch_articles(
        self,
        article_uris: List[str],
        max_articles: int = 15
    ) -> List[Dict[str, Any]]:
        """Fetch full article data for analysis."""
        if not article_uris:
            return []

        conn = None
        try:
            conn = self._get_connection()

            # Limit articles
            uris_to_fetch = article_uris[:max_articles]

            placeholders = ", ".join([f":uri_{i}" for i in range(len(uris_to_fetch))])
            params = {f"uri_{i}": uri for i, uri in enumerate(uris_to_fetch)}

            stmt = text(f"""
                SELECT uri, title, summary, news_source, publication_date, category, url
                FROM articles
                WHERE uri IN ({placeholders})
                ORDER BY publication_date DESC
            """)

            result = conn.execute(stmt, params)
            return [dict(row) for row in result.mappings()]

        except Exception as exc:
            logger.error(f"Error fetching articles for deep analysis: {exc}")
            return []
        finally:
            if conn:
                conn.close()

    def _normalize_actor_list(self, actors: List[Any]) -> List[str]:
        """
        Normalize actor list to ensure all items are strings.

        LLMs sometimes return objects like {name: "OpenAI", role: "AI company"}
        instead of strings. This converts them to flat strings.
        """
        normalized = []
        for actor in actors:
            if isinstance(actor, str):
                normalized.append(actor)
            elif isinstance(actor, dict):
                # Handle various object formats the LLM might return
                name = actor.get("name", actor.get("company", actor.get("person", actor.get("organization", ""))))
                role = actor.get("role", actor.get("position", actor.get("relevance", actor.get("description", ""))))

                if name and role:
                    normalized.append(f"{name} ({role})")
                elif name:
                    normalized.append(name)
                else:
                    # Fallback: join all values
                    values = [str(v) for v in actor.values() if v]
                    if values:
                        normalized.append(" - ".join(values))
            else:
                # Convert anything else to string
                normalized.append(str(actor))

        return normalized

    def _format_articles_for_analysis(self, articles: List[Dict[str, Any]]) -> str:
        """Format articles for deep analysis prompt."""
        formatted = []
        for i, article in enumerate(articles, 1):
            title = article.get("title", "Untitled")
            summary = article.get("summary", "No summary")
            source = article.get("news_source", "Unknown")
            date = article.get("publication_date", "Unknown")

            formatted.append(
                f"Article {i}: {title}\n"
                f"Source: {source} | Date: {date}\n"
                f"Summary: {summary}\n"
            )

        return "\n---\n".join(formatted)

    def _build_org_context(self, org_profile: Optional[Dict[str, Any]]) -> str:
        """Build organizational context string for the prompt."""
        if not org_profile:
            return ""

        # Extract lists safely
        key_concerns = org_profile.get('key_concerns', [])
        if isinstance(key_concerns, str):
            key_concerns = [key_concerns]

        strategic_priorities = org_profile.get('strategic_priorities', [])
        if isinstance(strategic_priorities, str):
            strategic_priorities = [strategic_priorities]

        stakeholder_focus = org_profile.get('stakeholder_focus', [])
        if isinstance(stakeholder_focus, str):
            stakeholder_focus = [stakeholder_focus]

        return f"""
ORGANIZATIONAL CONTEXT:
Organization: {org_profile.get('name', 'Unknown')} ({org_profile.get('organization_type', '')} in {org_profile.get('industry', '')})
Key Concerns: {', '.join(key_concerns) if key_concerns else 'Not specified'}
Strategic Priorities: {', '.join(strategic_priorities) if strategic_priorities else 'Not specified'}
Risk Tolerance: {org_profile.get('risk_tolerance', 'Medium')}
Key Stakeholders: {', '.join(stakeholder_focus) if stakeholder_focus else 'Not specified'}

When analyzing organization_implications, specifically address how this topic affects THIS organization based on the context above.
"""

    def _parse_llm_response(self, response: Any) -> Optional[Dict[str, Any]]:
        """Parse LLM response as JSON."""
        try:
            # Handle various response types
            if hasattr(response, 'message') and hasattr(response.message, 'content'):
                response = response.message.content
            elif hasattr(response, 'choices'):
                response = response.choices[0].message.content
            elif hasattr(response, 'content') and isinstance(response.content, str):
                response = response.content
            elif not isinstance(response, str):
                response = str(response)

            response = response.strip()

            # Handle markdown code blocks
            if response.startswith("```"):
                lines = response.split("\n")
                json_lines = []
                in_json = False
                for line in lines:
                    if line.startswith("```"):
                        in_json = not in_json
                        continue
                    if in_json:
                        json_lines.append(line)
                response = "\n".join(json_lines)

            return json.loads(response)

        except json.JSONDecodeError as exc:
            logger.error(f"Failed to parse deep analysis response: {exc}")
            logger.debug(f"Response was: {response[:500] if response else 'None'}")
            return None

    async def analyze(
        self,
        theme_label: str,
        theme_description: str,
        article_uris: List[str],
        model_name: Optional[str] = None,
        max_articles: int = 15,
        org_profile: Optional[Dict[str, Any]] = None
    ) -> DeepAnalysis:
        """
        Perform deep analysis on a theme.

        Args:
            theme_label: The theme title
            theme_description: One-line description
            article_uris: List of article URIs assigned to this theme
            model_name: Optional LLM model override
            max_articles: Max articles to include in prompt
            org_profile: Optional organizational profile for context-aware analysis

        Returns:
            DeepAnalysis object with structured analysis
        """
        result = DeepAnalysis()

        if not article_uris:
            logger.warning(f"No articles for theme: {theme_label}")
            return result

        if not self.ai_model_getter:
            logger.warning("No AI model getter configured for deep analysis")
            return result

        # Fetch articles
        articles = self._fetch_articles(article_uris, max_articles)
        if not articles:
            logger.warning(f"Could not fetch articles for theme: {theme_label}")
            return result

        # Build organizational context
        org_context = self._build_org_context(org_profile)

        # Format prompt
        articles_text = self._format_articles_for_analysis(articles)
        prompt = DEEP_ANALYSIS_PROMPT.format(
            theme_label=theme_label,
            theme_description=theme_description,
            org_context=org_context,
            article_count=len(articles),
            articles_text=articles_text
        )

        # Call LLM
        model_to_use = model_name or self.default_model
        result.model_used = model_to_use

        try:
            model = self.ai_model_getter(model_to_use)
            if not model:
                logger.error(f"Could not get AI model: {model_to_use}")
                return result

            if hasattr(model, 'generate'):
                response = await model.generate(prompt, max_tokens=2000)
            else:
                logger.error("Model does not have generate method")
                return result

            # Parse response
            parsed = self._parse_llm_response(response)
            if not parsed:
                return result

            # Build result - normalize data to ensure strings not objects
            actors_data = parsed.get("actors", {})
            result.actors = Actors(
                companies=self._normalize_actor_list(actors_data.get("companies", [])),
                people=self._normalize_actor_list(actors_data.get("people", [])),
                organizations=self._normalize_actor_list(actors_data.get("organizations", []))
            )

            events_data = parsed.get("events", {})
            result.events = Events(
                trigger_event=events_data.get("trigger_event", ""),
                timeline=events_data.get("timeline", []),
                current_status=events_data.get("current_status", "")
            )

            # Parse general implications (check both old and new field names for compatibility)
            implications_data = parsed.get("general_implications", parsed.get("implications", {}))
            result.implications = Implications(
                industry_impact=implications_data.get("industry_impact", ""),
                regulatory=implications_data.get("regulatory", ""),
                market=implications_data.get("market", "")
            )

            # Parse organization-specific implications
            org_implications_data = parsed.get("organization_implications", {})
            result.organization_implications = OrganizationImplications(
                strategic_relevance=org_implications_data.get("strategic_relevance", ""),
                stakeholder_impact=org_implications_data.get("stakeholder_impact", ""),
                risk_assessment=org_implications_data.get("risk_assessment", ""),
                recommended_response=org_implications_data.get("recommended_response", "")
            )

            signals_data = parsed.get("signals", {})
            result.signals = Signals(
                growth_indicators=signals_data.get("growth_indicators", []),
                risk_factors=signals_data.get("risk_factors", []),
                watch_for=signals_data.get("watch_for", [])
            )

            synthesis_data = parsed.get("synthesis", {})
            result.synthesis = Synthesis(
                key_takeaway=synthesis_data.get("key_takeaway", ""),
                stakeholders_affected=synthesis_data.get("stakeholders_affected", []),
                urgency=synthesis_data.get("urgency", "medium")
            )

            logger.info(f"Deep analysis complete for theme: {theme_label}")
            return result

        except Exception as exc:
            logger.error(f"Error in deep analysis for '{theme_label}': {exc}")
            return result

    async def analyze_theme(self, theme: Any) -> DeepAnalysis:
        """
        Convenience method that takes a ProposedTheme object.
        """
        return await self.analyze(
            theme_label=theme.theme_label,
            theme_description=theme.theme_description,
            article_uris=theme.article_uris
        )
