"""
Synthetic Focus Group Service

Generates stakeholder personas by analyzing articles to DISCOVER personas from content.
Creates rich psychographic profiles (15-20 attributes) that can be annotated, edited, saved, and exported.

4-Stage Workflow:
1. DISCOVERY: Fetch articles, extract stakeholder mentions using enrichment data
2. CLUSTERING: Group mentions into distinct persona archetypes (1-6 based on evidence)
3. PROFILING: Build rich psychographic profiles for each discovered archetype
4. SYNTHESIS: Generate focus group summary, interaction dynamics, consensus/tension points
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

from app.database import get_database_instance
from app.services.tool_loader import get_tool_loader

logger = logging.getLogger(__name__)


class FGStage(str, Enum):
    """Focus Group generation workflow stages."""
    DISCOVERY = "discovery"
    CLUSTERING = "clustering"
    PROFILING = "profiling"
    SYNTHESIS = "synthesis"
    COMPLETE = "complete"
    ERROR = "error"


@dataclass
class Persona:
    """Represents a single stakeholder persona with rich psychographic profile."""
    # Identity
    id: str
    name: str  # e.g., "Dr. Sarah Chen"
    archetype: str  # e.g., "Skeptical Regulator"
    role_title: str  # e.g., "Compliance Officer"
    sector: str  # e.g., "Financial Services"

    # Demographics
    experience_level: str = "senior"  # junior/mid/senior/executive
    decision_authority: str = "team_influencer"  # individual/team_influencer/budget_holder/c_suite

    # Values
    primary_values: List[str] = field(default_factory=list)  # e.g., ["stability", "compliance"]
    risk_tolerance: float = 0.5  # 0.0 (risk-averse) to 1.0 (risk-seeking)
    time_horizon_focus: str = "quarterly"  # immediate/quarterly/annual/multi_year

    # Attitudes
    change_receptivity: str = "cautious"  # resistant/cautious/adaptive/embracing
    technology_stance: str = "pragmatist"  # skeptic/pragmatist/enthusiast/evangelist
    authority_trust: str = "questioning"  # distrustful/questioning/neutral/trusting
    media_trust: str = "selective"  # cynical/selective/moderate/high
    topic_attitudes: Dict[str, str] = field(default_factory=dict)  # topic -> positive/negative/neutral/mixed

    # Behaviors
    information_consumption: str = "deep_reader"  # scanner/deep_reader/curator/sharer
    decision_style: str = "analytical"  # analytical/intuitive/consultative/directive
    communication_preference: str = "data_driven"  # formal/data_driven/narrative/visual

    # Concerns
    primary_concerns: List[str] = field(default_factory=list)
    fear_triggers: List[str] = field(default_factory=list)
    opportunity_interests: List[str] = field(default_factory=list)

    # Voice (for future LLM querying)
    voice_description: str = ""  # How they speak
    typical_questions: List[str] = field(default_factory=list)  # Questions they'd ask
    decision_factors: List[str] = field(default_factory=list)  # What drives their decisions
    influence_vectors: List[str] = field(default_factory=list)  # How to persuade them

    # Provenance
    source_articles: List[str] = field(default_factory=list)  # Article URIs
    confidence_score: float = 0.0  # 0.0-1.0 based on evidence strength
    mention_count: int = 0  # How often referenced in articles

    # User edits
    user_notes: Optional[str] = None
    user_edited: bool = False

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "archetype": self.archetype,
            "role_title": self.role_title,
            "sector": self.sector,
            "experience_level": self.experience_level,
            "decision_authority": self.decision_authority,
            "primary_values": self.primary_values,
            "risk_tolerance": self.risk_tolerance,
            "time_horizon_focus": self.time_horizon_focus,
            "change_receptivity": self.change_receptivity,
            "technology_stance": self.technology_stance,
            "authority_trust": self.authority_trust,
            "media_trust": self.media_trust,
            "topic_attitudes": self.topic_attitudes,
            "information_consumption": self.information_consumption,
            "decision_style": self.decision_style,
            "communication_preference": self.communication_preference,
            "primary_concerns": self.primary_concerns,
            "fear_triggers": self.fear_triggers,
            "opportunity_interests": self.opportunity_interests,
            "voice_description": self.voice_description,
            "typical_questions": self.typical_questions,
            "decision_factors": self.decision_factors,
            "influence_vectors": self.influence_vectors,
            "source_articles": self.source_articles,
            "confidence_score": self.confidence_score,
            "mention_count": self.mention_count,
            "user_notes": self.user_notes,
            "user_edited": self.user_edited
        }


@dataclass
class FGState:
    """Tracks state across Focus Group workflow stages."""
    scan_id: str
    topic: str
    created_at: datetime = field(default_factory=datetime.now)

    # Stage 1: Discovery outputs
    raw_articles: List[Dict] = field(default_factory=list)
    stakeholder_mentions: List[Dict] = field(default_factory=list)

    # Stage 2: Clustering outputs
    persona_clusters: List[Dict] = field(default_factory=list)

    # Stage 3: Profiling outputs
    personas: List[Persona] = field(default_factory=list)

    # Stage 4: Synthesis outputs
    focus_group_summary: str = ""
    interaction_dynamics: Dict = field(default_factory=dict)

    # Progress tracking
    current_stage: FGStage = FGStage.DISCOVERY
    stage_progress: Dict[str, float] = field(default_factory=lambda: {
        "discovery": 0.0,
        "clustering": 0.0,
        "profiling": 0.0,
        "synthesis": 0.0
    })
    errors: List[str] = field(default_factory=list)

    def update_progress(self, stage: str, progress: float):
        self.stage_progress[stage] = min(1.0, max(0.0, progress))
        self.current_stage = FGStage(stage)

    def overall_progress(self) -> float:
        weights = {
            "discovery": 0.20,
            "clustering": 0.25,
            "profiling": 0.35,
            "synthesis": 0.20
        }
        return sum(self.stage_progress.get(s, 0) * w for s, w in weights.items())

    def to_dict(self) -> Dict:
        return {
            "scan_id": self.scan_id,
            "topic": self.topic,
            "created_at": self.created_at.isoformat(),
            "current_stage": self.current_stage.value,
            "stage_progress": self.stage_progress,
            "overall_progress": self.overall_progress(),
            "articles_analyzed": len(self.raw_articles),
            "mentions_found": len(self.stakeholder_mentions),
            "clusters_formed": len(self.persona_clusters),
            "personas_generated": len(self.personas),
            "errors": self.errors
        }


@dataclass
class FGConfig:
    """Configuration for Focus Group generation."""
    # Persona settings
    max_personas: int = 6  # Ceiling, not target
    min_evidence_threshold: int = 2  # Min article mentions to create persona

    # Profile depth
    include_demographics: bool = True
    include_psychographics: bool = True
    include_voice: bool = True  # For future LLM querying

    # Model settings
    discovery_model: str = "gpt-4o"
    clustering_model: str = "gpt-4o"
    profiling_model: str = "gpt-4o"
    synthesis_model: str = "gpt-4o"

    # Temperature settings
    discovery_temp: float = 0.3
    clustering_temp: float = 0.4
    profiling_temp: float = 0.5
    synthesis_temp: float = 0.5

    # Timeouts (seconds)
    discovery_timeout: int = 90
    clustering_timeout: int = 90
    profiling_timeout: int = 120
    synthesis_timeout: int = 90


class FocusGroupService:
    """
    Synthetic Focus Group Service

    Generates stakeholder personas by analyzing articles to DISCOVER personas from content.
    Key principle: Personas are discovered, not invented.

    Workflow:
    1. DISCOVERY: Extract stakeholder mentions from articles using enrichment data
    2. CLUSTERING: Group mentions into 1-6 distinct archetypes based on evidence
    3. PROFILING: Build rich psychographic profiles (15-20 attributes)
    4. SYNTHESIS: Create focus group dynamics - consensus, tensions, diversity
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

    async def run_generation(
        self,
        topic: str,
        articles: List[Dict],
        config: Optional[FGConfig] = None
    ) -> AsyncGenerator[Dict, None]:
        """
        Run Focus Group generation.

        Args:
            topic: The topic being analyzed
            articles: List of enriched articles (with sentiment, categories, etc.)
            config: Optional configuration override

        Yields:
            Progress updates and final personas
        """
        if config is None:
            config = FGConfig()

        state = FGState(
            scan_id=str(uuid.uuid4()),
            topic=topic,
            raw_articles=articles
        )

        try:
            # Stage 1: Discovery
            yield {
                "stage": "discovery",
                "status": "started",
                "progress": 0.0,
                "scan_id": state.scan_id
            }
            await asyncio.wait_for(
                self._run_discovery(state, config),
                timeout=config.discovery_timeout
            )
            state.update_progress("discovery", 1.0)
            yield {
                "stage": "discovery",
                "status": "completed",
                "progress": 1.0,
                "mentions_found": len(state.stakeholder_mentions)
            }

            # Stage 2: Clustering
            yield {
                "stage": "clustering",
                "status": "started",
                "progress": 0.0
            }
            await asyncio.wait_for(
                self._run_clustering(state, config),
                timeout=config.clustering_timeout
            )
            state.update_progress("clustering", 1.0)
            yield {
                "stage": "clustering",
                "status": "completed",
                "progress": 1.0,
                "clusters_formed": len(state.persona_clusters)
            }

            # Stage 3: Profiling
            yield {
                "stage": "profiling",
                "status": "started",
                "progress": 0.0
            }
            async for progress in self._run_profiling(state, config):
                state.update_progress("profiling", progress["progress"])
                yield {"stage": "profiling", **progress}
            state.update_progress("profiling", 1.0)
            yield {
                "stage": "profiling",
                "status": "completed",
                "progress": 1.0,
                "personas_created": len(state.personas)
            }

            # Stage 4: Synthesis
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

            # Collect all article URIs used
            all_article_uris = []
            for article in state.raw_articles:
                uri = article.get("uri") or article.get("url", "")
                if uri and uri not in all_article_uris:
                    all_article_uris.append(uri)

            # Final result
            yield {
                "stage": "complete",
                "status": "success",
                "progress": 1.0,
                "scan_id": state.scan_id,
                "personas": [p.to_dict() for p in state.personas],
                "focus_group_summary": state.focus_group_summary,
                "interaction_dynamics": state.interaction_dynamics,
                "article_uris": all_article_uris,
                "articles": [
                    {
                        "title": a.get("title", "Untitled"),
                        "uri": a.get("uri") or a.get("url", ""),
                        "source": a.get("source", "Unknown"),
                        "published_at": a.get("published_at")
                    }
                    for a in state.raw_articles
                ],
                "metadata": {
                    "topic": topic,
                    "articles_analyzed": len(state.raw_articles),
                    "mentions_found": len(state.stakeholder_mentions),
                    "personas_generated": len(state.personas),
                    "generated_at": datetime.now().isoformat(),
                    "config": {
                        "max_personas": config.max_personas,
                        "min_evidence_threshold": config.min_evidence_threshold
                    }
                }
            }

        except asyncio.TimeoutError:
            logger.error(f"Focus group stage timed out: {state.current_stage}")
            state.errors.append(f"Timeout in {state.current_stage.value} stage")
            yield {
                "stage": state.current_stage.value,
                "status": "timeout",
                "error": "Stage timed out",
                "progress": state.overall_progress(),
                "partial_results": state.to_dict()
            }

        except Exception as e:
            logger.error(f"Focus group generation failed: {e}", exc_info=True)
            state.errors.append(str(e))
            yield {
                "stage": state.current_stage.value,
                "status": "error",
                "error": str(e),
                "progress": state.overall_progress(),
                "partial_results": state.to_dict()
            }

    def _extract_article_context(self, articles: List[Dict]) -> str:
        """Extract relevant context from articles for prompts."""
        context_parts = []
        for i, article in enumerate(articles[:30]):  # Limit to avoid token overflow
            enrichment = article.get('enrichment', {})
            context_parts.append({
                "index": i,
                "title": article.get('title', '')[:200],
                "summary": article.get('summary', '')[:300],
                "source": article.get('source', ''),
                "uri": article.get('uri', ''),
                "sentiment": enrichment.get('sentiment', 'neutral'),
                "political_bias": enrichment.get('political_bias', 'unknown'),
                "categories": enrichment.get('categories', [])[:3],
                "driver_type": enrichment.get('driver_type', ''),
                "factuality": enrichment.get('factuality', '')
            })
        return json.dumps(context_parts, indent=2)

    async def _run_discovery(self, state: FGState, config: FGConfig):
        """
        Stage 1: Discovery
        Extract stakeholder mentions from articles using enrichment data.
        """
        logger.info(f"Starting stakeholder discovery for {state.topic}")

        agent_prompt = self._load_agent_prompt("fg_discovery_agent")
        agent_config = self._get_agent_config("fg_discovery_agent")

        model = agent_config.get('model', config.discovery_model)
        temperature = agent_config.get('temperature', config.discovery_temp)

        article_context = self._extract_article_context(state.raw_articles)

        prompt = f"""Analyze these articles about "{state.topic}" and DISCOVER explicit and implicit stakeholder mentions.

ARTICLES TO ANALYZE:
{article_context}

Your task is to extract STAKEHOLDER MENTIONS - explicit references to groups, roles, or perspectives in the articles.

Look for:
1. **Explicit mentions**: Named organizations, roles, job titles, demographic groups
2. **Quoted sources**: People/organizations quoted or cited
3. **Affected parties**: Groups described as impacted by events
4. **Decision makers**: Those with agency over outcomes
5. **Critics/supporters**: Those expressing opinions on the topic
6. **Implicit audiences**: Who the articles seem written for

For each mention, extract:
- The stakeholder type/role
- The context they appear in
- Their apparent stance on the topic
- The source article(s)

Return JSON with:
{{
    "stakeholder_mentions": [
        {{
            "mention_id": "m_001",
            "stakeholder_type": "e.g., 'regulators', 'small business owners', 'tech executives'",
            "specific_reference": "The exact phrase or reference from the article",
            "context": "What they were doing/saying/being affected by",
            "apparent_stance": "positive/negative/neutral/mixed toward the topic",
            "quoted": true/false,
            "source_indices": [0, 5, 12],
            "prominence": "high/medium/low"
        }}
    ],
    "discovery_stats": {{
        "total_mentions": 25,
        "unique_stakeholder_types": 8,
        "explicit_quotes": 10,
        "implicit_audiences": 3
    }}
}}

Extract ALL stakeholder mentions you find - we will cluster them in the next stage."""

        try:
            response = await litellm.acompletion(
                model=model,
                messages=[
                    {"role": "system", "content": agent_prompt or "You are a stakeholder analyst specializing in identifying all parties with interest in a topic from news coverage. You extract both explicit mentions and implicit stakeholders."},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                max_tokens=4000,
                response_format={"type": "json_object"}
            )

            result = json.loads(response.choices[0].message.content)
            state.stakeholder_mentions = result.get("stakeholder_mentions", [])

        except Exception as e:
            logger.error(f"Discovery stage failed: {e}")
            # Fallback: create basic mentions from articles
            state.stakeholder_mentions = self._fallback_discovery(state.raw_articles)

        logger.info(f"Stakeholder mentions discovered: {len(state.stakeholder_mentions)}")

    def _fallback_discovery(self, articles: List[Dict]) -> List[Dict]:
        """Generate fallback stakeholder mentions if LLM fails."""
        mentions = []
        sources = set()
        for i, article in enumerate(articles[:10]):
            source = article.get('source', 'Unknown')
            if source not in sources:
                sources.add(source)
                mentions.append({
                    "mention_id": f"m_{i+1:03d}",
                    "stakeholder_type": "news consumer",
                    "specific_reference": f"Reader of {source}",
                    "context": "Target audience of publication",
                    "apparent_stance": "neutral",
                    "quoted": False,
                    "source_indices": [i],
                    "prominence": "medium"
                })
        return mentions

    async def _run_clustering(self, state: FGState, config: FGConfig):
        """
        Stage 2: Clustering
        Group stakeholder mentions into 1-6 distinct persona archetypes.
        Only create personas with sufficient evidence.
        """
        logger.info(f"Clustering {len(state.stakeholder_mentions)} mentions into archetypes")

        agent_prompt = self._load_agent_prompt("fg_clustering_agent")
        agent_config = self._get_agent_config("fg_clustering_agent")

        model = agent_config.get('model', config.clustering_model)
        temperature = agent_config.get('temperature', config.clustering_temp)

        prompt = f"""Group these stakeholder mentions into DISTINCT PERSONA ARCHETYPES for "{state.topic}".

STAKEHOLDER MENTIONS:
{json.dumps(state.stakeholder_mentions, indent=2)}

CRITICAL RULES:
1. Create 1-6 archetypes based on EVIDENCE, not imagination
2. Only create an archetype if it has {config.min_evidence_threshold}+ supporting mentions
3. Archetypes should be DISTINCT - don't create similar ones
4. Look for natural groupings by: role, stance, concerns, sector
5. Merge overlapping mentions into single archetypes

For each archetype, identify:
- A descriptive label (e.g., "Skeptical Regulator", "Optimistic Entrepreneur")
- The mentions that support this archetype
- The common characteristics
- The dominant stance on the topic

Return JSON with:
{{
    "persona_clusters": [
        {{
            "cluster_id": "c_001",
            "archetype_label": "e.g., 'Skeptical Regulator'",
            "description": "Brief description of this stakeholder type",
            "supporting_mentions": ["m_001", "m_005", "m_012"],
            "mention_count": 3,
            "common_characteristics": [
                "Works in regulatory/compliance role",
                "Concerned about risks and accountability",
                "Preference for caution over speed"
            ],
            "dominant_stance": "negative/positive/neutral/mixed",
            "confidence": 0.85,
            "sectors": ["government", "financial services"],
            "key_quotes": ["Quote from article if available"]
        }}
    ],
    "clustering_stats": {{
        "total_clusters": 4,
        "mentions_clustered": 20,
        "mentions_orphaned": 5,
        "avg_cluster_size": 5
    }}
}}

Remember: DISCOVER personas from evidence, don't INVENT them."""

        try:
            response = await litellm.acompletion(
                model=model,
                messages=[
                    {"role": "system", "content": agent_prompt or "You are a persona researcher specializing in clustering stakeholder mentions into meaningful archetypes. You only create archetypes with sufficient evidence."},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                max_tokens=3000,
                response_format={"type": "json_object"}
            )

            result = json.loads(response.choices[0].message.content)
            # Filter to only clusters meeting threshold
            clusters = result.get("persona_clusters", [])
            state.persona_clusters = [
                c for c in clusters
                if c.get("mention_count", 0) >= config.min_evidence_threshold
            ][:config.max_personas]

        except Exception as e:
            logger.error(f"Clustering stage failed: {e}")
            state.persona_clusters = []

        logger.info(f"Persona clusters formed: {len(state.persona_clusters)}")

    async def _run_profiling(
        self,
        state: FGState,
        config: FGConfig
    ) -> AsyncGenerator[Dict, None]:
        """
        Stage 3: Profiling
        Build rich psychographic profiles (15-20 attributes) for each archetype.
        """
        logger.info(f"Building profiles for {len(state.persona_clusters)} archetypes")

        agent_prompt = self._load_agent_prompt("fg_profiling_agent")
        agent_config = self._get_agent_config("fg_profiling_agent")

        model = agent_config.get('model', config.profiling_model)
        temperature = agent_config.get('temperature', config.profiling_temp)

        article_context = self._extract_article_context(state.raw_articles[:15])

        prompt = f"""Create RICH PSYCHOGRAPHIC PROFILES for these stakeholder archetypes about "{state.topic}".

ARTICLE CONTEXT:
{article_context}

ARCHETYPES TO PROFILE:
{json.dumps(state.persona_clusters, indent=2)}

For each archetype, create a detailed persona with:

IDENTITY (4 attributes):
- name: A representative fictional name
- archetype: The archetype label
- role_title: A typical job title
- sector: Primary industry/sector

DEMOGRAPHICS (2 attributes):
- experience_level: junior/mid/senior/executive
- decision_authority: individual/team_influencer/budget_holder/c_suite

VALUES (3 attributes):
- primary_values: List of 3-5 core values
- risk_tolerance: 0.0 (risk-averse) to 1.0 (risk-seeking)
- time_horizon_focus: immediate/quarterly/annual/multi_year

ATTITUDES (5 attributes):
- change_receptivity: resistant/cautious/adaptive/embracing
- technology_stance: skeptic/pragmatist/enthusiast/evangelist
- authority_trust: distrustful/questioning/neutral/trusting
- media_trust: cynical/selective/moderate/high
- topic_attitudes: Dict of key topic aspects -> positive/negative/neutral/mixed

BEHAVIORS (3 attributes):
- information_consumption: scanner/deep_reader/curator/sharer
- decision_style: analytical/intuitive/consultative/directive
- communication_preference: formal/data_driven/narrative/visual

CONCERNS (3 attributes):
- primary_concerns: List of 3-5 main worries
- fear_triggers: What makes them anxious
- opportunity_interests: What opportunities excite them

VOICE (4 attributes - for future querying):
- voice_description: How they speak/communicate
- typical_questions: 3-5 questions they'd ask about the topic
- decision_factors: What influences their decisions
- influence_vectors: How to persuade them

Return JSON with:
{{
    "personas": [
        {{
            "id": "persona_001",
            "cluster_id": "c_001",
            "name": "Dr. Sarah Chen",
            "archetype": "Skeptical Regulator",
            "role_title": "Chief Compliance Officer",
            "sector": "Financial Services",
            "experience_level": "executive",
            "decision_authority": "c_suite",
            "primary_values": ["stability", "compliance", "accountability"],
            "risk_tolerance": 0.2,
            "time_horizon_focus": "annual",
            "change_receptivity": "cautious",
            "technology_stance": "skeptic",
            "authority_trust": "neutral",
            "media_trust": "selective",
            "topic_attitudes": {{"innovation": "mixed", "regulation": "positive"}},
            "information_consumption": "deep_reader",
            "decision_style": "analytical",
            "communication_preference": "data_driven",
            "primary_concerns": ["regulatory compliance", "systemic risk", "consumer protection"],
            "fear_triggers": ["unintended consequences", "regulatory gaps", "reputational damage"],
            "opportunity_interests": ["improved oversight tools", "industry standards", "public trust"],
            "voice_description": "Measured, precise, evidence-based. Uses regulatory language and cites precedents.",
            "typical_questions": [
                "What safeguards are in place?",
                "How does this comply with existing regulations?",
                "What are the worst-case scenarios?"
            ],
            "decision_factors": ["regulatory precedent", "risk assessment", "stakeholder consensus"],
            "influence_vectors": ["empirical evidence", "case studies", "regulatory guidance"],
            "confidence_score": 0.85,
            "mention_count": 5
        }}
    ]
}}

Make profiles DISTINCT and based on article evidence. Each persona should feel like a real individual."""

        yield {"status": "generating", "progress": 0.3}

        try:
            response = await litellm.acompletion(
                model=model,
                messages=[
                    {"role": "system", "content": agent_prompt or "You are a psychographic profiling expert creating rich, evidence-based stakeholder personas. Each persona should feel like a real individual with distinct characteristics."},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                max_tokens=6000,
                response_format={"type": "json_object"}
            )

            result = json.loads(response.choices[0].message.content)
            raw_personas = result.get("personas", [])

            yield {"status": "processing", "progress": 0.7}

            # Convert to Persona objects
            for raw in raw_personas:
                # Get source articles from the cluster
                cluster_id = raw.get("cluster_id", "")
                cluster = next((c for c in state.persona_clusters if c.get("cluster_id") == cluster_id), {})
                source_mentions = cluster.get("supporting_mentions", [])

                # Map mentions back to article URIs
                source_article_uris = []
                for mention_id in source_mentions[:5]:
                    mention = next((m for m in state.stakeholder_mentions if m.get("mention_id") == mention_id), None)
                    if mention:
                        for idx in mention.get("source_indices", []):
                            if idx < len(state.raw_articles):
                                uri = state.raw_articles[idx].get("uri")
                                if uri and uri not in source_article_uris:
                                    source_article_uris.append(uri)

                persona = Persona(
                    id=raw.get("id", str(uuid.uuid4())[:8]),
                    name=raw.get("name", "Unknown"),
                    archetype=raw.get("archetype", ""),
                    role_title=raw.get("role_title", ""),
                    sector=raw.get("sector", ""),
                    experience_level=raw.get("experience_level", "senior"),
                    decision_authority=raw.get("decision_authority", "team_influencer"),
                    primary_values=raw.get("primary_values", []),
                    risk_tolerance=raw.get("risk_tolerance", 0.5),
                    time_horizon_focus=raw.get("time_horizon_focus", "quarterly"),
                    change_receptivity=raw.get("change_receptivity", "cautious"),
                    technology_stance=raw.get("technology_stance", "pragmatist"),
                    authority_trust=raw.get("authority_trust", "neutral"),
                    media_trust=raw.get("media_trust", "selective"),
                    topic_attitudes=raw.get("topic_attitudes", {}),
                    information_consumption=raw.get("information_consumption", "deep_reader"),
                    decision_style=raw.get("decision_style", "analytical"),
                    communication_preference=raw.get("communication_preference", "data_driven"),
                    primary_concerns=raw.get("primary_concerns", []),
                    fear_triggers=raw.get("fear_triggers", []),
                    opportunity_interests=raw.get("opportunity_interests", []),
                    voice_description=raw.get("voice_description", ""),
                    typical_questions=raw.get("typical_questions", []),
                    decision_factors=raw.get("decision_factors", []),
                    influence_vectors=raw.get("influence_vectors", []),
                    source_articles=source_article_uris,
                    confidence_score=raw.get("confidence_score", 0.5),
                    mention_count=raw.get("mention_count", cluster.get("mention_count", 0))
                )
                state.personas.append(persona)

            yield {"status": "completed", "progress": 1.0, "personas_created": len(state.personas)}

        except Exception as e:
            logger.error(f"Profiling stage failed: {e}")
            yield {"status": "error", "progress": 0.9, "error": str(e)}

    async def _run_synthesis(self, state: FGState, config: FGConfig):
        """
        Stage 4: Synthesis
        Generate focus group summary, interaction dynamics, consensus/tension points.
        """
        logger.info(f"Synthesizing focus group dynamics for {len(state.personas)} personas")

        agent_prompt = self._load_agent_prompt("fg_synthesis_agent")
        agent_config = self._get_agent_config("fg_synthesis_agent")

        model = agent_config.get('model', config.synthesis_model)
        temperature = agent_config.get('temperature', config.synthesis_temp)

        personas_json = [p.to_dict() for p in state.personas]

        prompt = f"""Synthesize a FOCUS GROUP ANALYSIS for these stakeholder personas about "{state.topic}".

PERSONAS IN THE FOCUS GROUP:
{json.dumps(personas_json, indent=2)}

Analyze:
1. How would these personas INTERACT if discussing {state.topic}?
2. Where would they AGREE (consensus areas)?
3. Where would they DISAGREE (tension points)?
4. What's the overall DIVERSITY of perspectives?
5. What INSIGHTS emerge from this group composition?

Return JSON with:
{{
    "focus_group_summary": "A 2-3 paragraph narrative describing this focus group as a whole - who they are, what they represent, and what insights they bring to {state.topic}",

    "interaction_dynamics": {{
        "consensus_areas": [
            {{
                "topic": "Area of agreement",
                "description": "Why they agree on this",
                "supporting_personas": ["persona_001", "persona_002"]
            }}
        ],
        "tension_points": [
            {{
                "topic": "Area of disagreement",
                "description": "The nature of the tension",
                "opposing_sides": {{
                    "side_a": ["persona_001"],
                    "side_b": ["persona_002", "persona_003"]
                }}
            }}
        ],
        "power_dynamics": {{
            "most_influential": "persona_id",
            "most_vulnerable": "persona_id",
            "likely_coalition": ["persona_ids who might ally"]
        }},
        "diversity_score": 0.75,
        "diversity_analysis": "Assessment of how diverse this group's perspectives are",
        "blind_spots": ["Perspectives or stakeholder types NOT represented"],
        "key_insight": "The single most important insight from analyzing this focus group"
    }}
}}

Be specific about how the personas' characteristics would lead to these dynamics."""

        try:
            response = await litellm.acompletion(
                model=model,
                messages=[
                    {"role": "system", "content": agent_prompt or "You are a focus group facilitator and analyst. You understand group dynamics, consensus building, and conflict patterns. You synthesize insights from diverse stakeholder perspectives."},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                max_tokens=3000,
                response_format={"type": "json_object"}
            )

            result = json.loads(response.choices[0].message.content)
            state.focus_group_summary = result.get("focus_group_summary", "")
            state.interaction_dynamics = result.get("interaction_dynamics", {})

        except Exception as e:
            logger.error(f"Synthesis stage failed: {e}")
            state.focus_group_summary = f"Focus group of {len(state.personas)} personas analyzing {state.topic}."
            state.interaction_dynamics = {
                "consensus_areas": [],
                "tension_points": [],
                "diversity_score": 0.5,
                "key_insight": "Synthesis analysis unavailable"
            }

        logger.info(f"Synthesis complete: {len(state.focus_group_summary)} chars")


# Singleton instance
_fg_instance: Optional[FocusGroupService] = None


def get_focus_group_service() -> FocusGroupService:
    """Get the global Focus Group service instance."""
    global _fg_instance
    if _fg_instance is None:
        _fg_instance = FocusGroupService()
    return _fg_instance
