"""
Extreme Outlier Scenarios (EOS) Service

Generates Black Swan events, Contrarian Analysis, and Wild Card Futures
by analyzing existing Future Narratives/Convergence analysis data.

4-Stage Workflow:
1. WEAK SIGNALS: Detect faint patterns and anomalies in trend data
2. AMPLIFICATION: Explore how weak signals could cascade into major disruptions
3. SCENARIO BUILDING: Construct detailed outlier narratives with causal chains
4. IMPLICATIONS: Strategic hedging recommendations and early warning indicators
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

from app.services.tool_loader import get_tool_loader

logger = logging.getLogger(__name__)


class EOSStage(str, Enum):
    """Extreme Outlier Scenarios workflow stages."""
    WEAK_SIGNALS = "weak_signals"
    AMPLIFICATION = "amplification"
    SCENARIO_BUILDING = "scenario_building"
    IMPLICATIONS = "implications"
    COMPLETE = "complete"
    ERROR = "error"


@dataclass
class OutlierScenario:
    """Represents a single extreme outlier scenario."""
    id: str
    category: str  # 'black_swan', 'contrarian', 'wild_card'
    title: str
    subtitle: str = ""
    description: str = ""
    probability: str = "low"  # 'very_low', 'low', 'moderate'
    impact_rating: int = 5  # 1-10
    time_horizon: str = ""

    # Causal chain elements
    weak_signals: List[str] = field(default_factory=list)
    amplification_path: str = ""
    trigger_events: List[str] = field(default_factory=list)

    # Strategic elements
    early_warning_signs: List[str] = field(default_factory=list)
    strategic_implications: str = ""
    preparation_actions: List[str] = field(default_factory=list)

    # Source attribution
    source_trends: List[str] = field(default_factory=list)
    source_consensus: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "category": self.category,
            "title": self.title,
            "subtitle": self.subtitle,
            "description": self.description,
            "probability": self.probability,
            "impact_rating": self.impact_rating,
            "time_horizon": self.time_horizon,
            "weak_signals": self.weak_signals,
            "amplification_path": self.amplification_path,
            "trigger_events": self.trigger_events,
            "early_warning_signs": self.early_warning_signs,
            "strategic_implications": self.strategic_implications,
            "preparation_actions": self.preparation_actions,
            "source_trends": self.source_trends,
            "source_consensus": self.source_consensus
        }


@dataclass
class EOSState:
    """Tracks state across EOS workflow stages."""
    scan_id: str
    topic: str
    created_at: datetime = field(default_factory=datetime.now)

    # Input data (from existing analysis)
    source_analysis: Dict = field(default_factory=dict)
    trends_data: List[Dict] = field(default_factory=list)
    consensus_data: List[Dict] = field(default_factory=list)

    # Raw articles used for analysis
    raw_articles: List[Dict] = field(default_factory=list)

    # Stage 1: Weak Signals
    weak_signals: List[Dict] = field(default_factory=list)

    # Stage 2: Amplification
    amplified_pathways: List[Dict] = field(default_factory=list)

    # Stage 3: Scenario Building
    raw_scenarios: List[Dict] = field(default_factory=list)

    # Stage 4: Final Scenarios
    scenarios: List[OutlierScenario] = field(default_factory=list)

    # Progress tracking
    current_stage: EOSStage = EOSStage.WEAK_SIGNALS
    stage_progress: Dict[str, float] = field(default_factory=lambda: {
        "weak_signals": 0.0,
        "amplification": 0.0,
        "scenario_building": 0.0,
        "implications": 0.0
    })
    errors: List[str] = field(default_factory=list)

    def update_progress(self, stage: str, progress: float):
        self.stage_progress[stage] = min(1.0, max(0.0, progress))
        self.current_stage = EOSStage(stage)

    def overall_progress(self) -> float:
        weights = {
            "weak_signals": 0.2,
            "amplification": 0.25,
            "scenario_building": 0.35,
            "implications": 0.2
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
            "weak_signals_found": len(self.weak_signals),
            "pathways_amplified": len(self.amplified_pathways),
            "scenarios_generated": len(self.scenarios),
            "errors": self.errors
        }


@dataclass
class EOSConfig:
    """Configuration for Extreme Outlier Scenarios generation."""
    # Output settings
    scenario_count: int = 5
    include_black_swans: bool = True
    include_contrarian: bool = True
    include_wild_cards: bool = True

    # Time horizon focus
    time_horizon: str = "mid"  # 'near' (0-2y), 'mid' (2-5y), 'long' (5-10y)

    # Model settings
    weak_signals_model: str = "gpt-5.4"
    amplification_model: str = "gpt-5.4"
    scenario_model: str = "gpt-5.4"
    implications_model: str = "gpt-5.4"

    # Temperature settings (higher for more creative scenarios)
    weak_signals_temp: float = 0.3
    amplification_temp: float = 0.5
    scenario_temp: float = 0.7
    implications_temp: float = 0.4

    # Timeouts (seconds)
    weak_signals_timeout: int = 60
    amplification_timeout: int = 90
    scenario_timeout: int = 120
    implications_timeout: int = 90


class ExtremeOutlierService:
    """
    Extreme Outlier Scenarios Service

    Generates Black Swan events, Contrarian Analysis, and Wild Card Futures
    by analyzing existing trend convergence data.

    Workflow:
    1. WEAK SIGNALS: Extract overlooked patterns from existing analysis
    2. AMPLIFICATION: Model how signals could cascade into disruptions
    3. SCENARIO BUILDING: Create detailed extreme scenario narratives
    4. IMPLICATIONS: Add strategic hedging and early warning indicators
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
        source_analysis: Dict,
        config: Optional[EOSConfig] = None,
        raw_articles: Optional[List[Dict]] = None
    ) -> AsyncGenerator[Dict, None]:
        """
        Run Extreme Outlier Scenarios generation.

        Args:
            topic: The topic being analyzed
            source_analysis: Existing trend convergence analysis data
            config: Optional configuration override
            raw_articles: Optional list of source articles for grounding scenarios

        Yields:
            Progress updates and final scenarios
        """
        if config is None:
            config = EOSConfig()

        state = EOSState(
            scan_id=str(uuid.uuid4()),
            topic=topic,
            source_analysis=source_analysis,
            raw_articles=raw_articles or []
        )

        # Extract trend and consensus data from source analysis
        state.trends_data = self._extract_trends(source_analysis)
        state.consensus_data = self._extract_consensus(source_analysis)

        try:
            # Stage 1: Weak Signals
            yield {
                "stage": "weak_signals",
                "status": "started",
                "progress": 0.0,
                "scan_id": state.scan_id
            }
            await asyncio.wait_for(
                self._run_weak_signals(state, config),
                timeout=config.weak_signals_timeout
            )
            state.update_progress("weak_signals", 1.0)
            yield {
                "stage": "weak_signals",
                "status": "completed",
                "progress": 1.0,
                "signals_detected": len(state.weak_signals)
            }

            # Stage 2: Amplification
            yield {
                "stage": "amplification",
                "status": "started",
                "progress": 0.0
            }
            await asyncio.wait_for(
                self._run_amplification(state, config),
                timeout=config.amplification_timeout
            )
            state.update_progress("amplification", 1.0)
            yield {
                "stage": "amplification",
                "status": "completed",
                "progress": 1.0,
                "pathways_identified": len(state.amplified_pathways)
            }

            # Stage 3: Scenario Building
            yield {
                "stage": "scenario_building",
                "status": "started",
                "progress": 0.0
            }
            async for progress in self._run_scenario_building(state, config):
                state.update_progress("scenario_building", progress["progress"])
                yield {"stage": "scenario_building", **progress}
            state.update_progress("scenario_building", 1.0)
            yield {
                "stage": "scenario_building",
                "status": "completed",
                "progress": 1.0,
                "scenarios_built": len(state.raw_scenarios)
            }

            # Stage 4: Implications
            yield {
                "stage": "implications",
                "status": "started",
                "progress": 0.0
            }
            async for progress in self._run_implications(state, config):
                state.update_progress("implications", progress["progress"])
                yield {"stage": "implications", **progress}
            state.update_progress("implications", 1.0)

            # Final result
            yield {
                "stage": "complete",
                "status": "success",
                "progress": 1.0,
                "scan_id": state.scan_id,
                "scenarios": [s.to_dict() for s in state.scenarios],
                "metadata": {
                    "topic": topic,
                    "signals_detected": len(state.weak_signals),
                    "pathways_explored": len(state.amplified_pathways),
                    "scenarios_generated": len(state.scenarios),
                    "generated_at": datetime.now().isoformat(),
                    "config": {
                        "scenario_count": config.scenario_count,
                        "time_horizon": config.time_horizon,
                        "include_black_swans": config.include_black_swans,
                        "include_contrarian": config.include_contrarian,
                        "include_wild_cards": config.include_wild_cards
                    }
                }
            }

        except asyncio.TimeoutError:
            logger.error(f"EOS stage timed out: {state.current_stage}")
            state.errors.append(f"Timeout in {state.current_stage.value} stage")
            yield {
                "stage": state.current_stage.value,
                "status": "timeout",
                "error": "Stage timed out",
                "progress": state.overall_progress(),
                "partial_results": state.to_dict()
            }

        except Exception as e:
            logger.error(f"EOS generation failed: {e}", exc_info=True)
            state.errors.append(str(e))
            yield {
                "stage": state.current_stage.value,
                "status": "error",
                "error": str(e),
                "progress": state.overall_progress(),
                "partial_results": state.to_dict()
            }

    def _extract_trends(self, source_analysis: Dict) -> List[Dict]:
        """Extract trend data from source analysis."""
        trends = []

        # Extract from market signals
        market_signals = source_analysis.get('market_signals', {})
        for signal in market_signals.get('emerging_trends', []):
            trends.append({
                "type": "emerging_trend",
                "title": signal.get('title', ''),
                "description": signal.get('description', ''),
                "source": "market_signals"
            })

        # Extract from convergences
        convergences = source_analysis.get('convergences', [])
        for conv in convergences:
            trends.append({
                "type": "convergence",
                "title": conv.get('title', ''),
                "description": conv.get('summary', ''),
                "themes": conv.get('themes', []),
                "source": "convergence_analysis"
            })

        # Extract from strategic recommendations
        strategic = source_analysis.get('strategic_recommendations', {})
        for horizon in ['near_term', 'mid_term', 'long_term']:
            horizon_data = strategic.get(horizon, {})
            for trend in horizon_data.get('key_trends', []):
                trends.append({
                    "type": f"strategic_{horizon}",
                    "title": trend.get('trend', ''),
                    "description": trend.get('implication', ''),
                    "source": "strategic_recommendations"
                })

        return trends

    def _extract_consensus(self, source_analysis: Dict) -> List[Dict]:
        """Extract consensus data from source analysis."""
        consensus = []

        # Extract from consensus categories if available
        consensus_data = source_analysis.get('consensus', {})
        if isinstance(consensus_data, dict):
            for category, data in consensus_data.items():
                if isinstance(data, dict):
                    consensus.append({
                        "category": category,
                        "title": data.get('title', category),
                        "summary": data.get('summary', ''),
                        "source": "consensus_analysis"
                    })

        return consensus

    def _format_article_excerpts(
        self,
        articles: List[Dict],
        limit: int = 20,
        summary_length: int = 250
    ) -> str:
        """Format articles as numbered excerpts for prompts."""
        if not articles:
            return ""
        excerpts = []
        for i, article in enumerate(articles[:limit]):
            title = article.get("title", "Untitled")
            source = article.get("source", "Unknown")
            summary = (article.get("summary", "") or "")[:summary_length]
            excerpts.append(f"[{i+1}] {title} ({source}): {summary}")
        return "\n".join(excerpts)

    async def _run_weak_signals(self, state: EOSState, config: EOSConfig):
        """
        Stage 1: Weak Signals Detection
        Extract overlooked patterns and faint signals from existing analysis.
        """
        logger.info(f"Starting weak signals detection for {state.topic}")

        # Load agent prompt
        agent_prompt = self._load_agent_prompt("eos_weak_signals_agent")
        agent_config = self._get_agent_config("eos_weak_signals_agent")

        model = agent_config.get('model', config.weak_signals_model)
        temperature = agent_config.get('temperature', config.weak_signals_temp)

        article_excerpts = self._format_article_excerpts(state.raw_articles, limit=25)

        prompt = f"""Analyze the source articles and trend data for {state.topic} to identify WEAK SIGNALS - minority viewpoints and outlier positions that mainstream analysis overlooks.

CRITICAL: Weak signals must be derived from actual content in the source articles below.
Reference articles by number [1], [2], etc. and quote or paraphrase specific claims.

SOURCE ARTICLES:
{article_excerpts if article_excerpts else "(No articles - use trend data below)"}

TREND DATA:
{json.dumps(state.trends_data[:15], indent=2)}

CONSENSUS THEMES:
{json.dumps(state.consensus_data[:8], indent=2)}

Identify weak signals by looking for:
1. Minority viewpoints in specific articles that challenge the consensus
2. Contrarian claims or predictions from outlier sources
3. Contradictions between different articles/sources
4. Edge cases and tail risks mentioned but not emphasized
5. Assumptions in mainstream coverage that specific articles question

Return JSON:
{{
    "weak_signals": [
        {{
            "signal_id": "ws_001",
            "title": "Signal title (descriptive)",
            "description": "What this signal indicates - cite specific article(s)",
            "source_articles": [1, 5],
            "source_quote": "Key quote or paraphrase from source",
            "source_contradiction": "Which mainstream view it challenges",
            "amplification_potential": "high/medium/low",
            "time_sensitivity": "How soon this could become significant",
            "related_trends": ["trend titles from source data"]
        }}
    ]
}}

Identify 8-12 weak signals. Each MUST reference at least one source article."""

        try:
            response = await litellm.acompletion(
                model=model,
                messages=[
                    {"role": "system", "content": agent_prompt or "You are a contrarian analyst specializing in identifying weak signals and early warning indicators that mainstream analysis overlooks."},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                max_tokens=3000,
                response_format={"type": "json_object"}
            )

            result = json.loads(response.choices[0].message.content)
            state.weak_signals = result.get("weak_signals", [])

        except Exception as e:
            logger.error(f"Weak signals detection failed: {e}")
            # Fallback: create basic signals from trends
            state.weak_signals = self._fallback_weak_signals(state.trends_data)

        logger.info(f"Weak signals detected: {len(state.weak_signals)}")

    def _fallback_weak_signals(self, trends: List[Dict]) -> List[Dict]:
        """Generate fallback weak signals if LLM fails."""
        signals = []
        for i, trend in enumerate(trends[:5]):
            signals.append({
                "signal_id": f"ws_{i+1:03d}",
                "title": f"Contrarian view on: {trend.get('title', 'Unknown trend')}",
                "description": "Consider opposite scenarios",
                "amplification_potential": "medium",
                "related_trends": [trend.get('title', '')]
            })
        return signals

    async def _run_amplification(self, state: EOSState, config: EOSConfig):
        """
        Stage 2: Amplification
        Model how weak signals could cascade into major disruptions.
        """
        logger.info(f"Starting amplification analysis for {len(state.weak_signals)} signals")

        agent_prompt = self._load_agent_prompt("eos_amplification_agent")
        agent_config = self._get_agent_config("eos_amplification_agent")

        model = agent_config.get('model', config.amplification_model)
        temperature = agent_config.get('temperature', config.amplification_temp)

        # Select high-potential signals
        high_potential = [s for s in state.weak_signals
                         if s.get('amplification_potential') in ['high', 'medium']][:8]

        prompt = f"""For each weak signal, model how it could AMPLIFY into a major disruption for {state.topic}.

WEAK SIGNALS TO AMPLIFY:
{json.dumps(high_potential, indent=2)}

TIME HORIZON FOCUS: {config.time_horizon} term
- near: 0-2 years
- mid: 2-5 years
- long: 5-10 years

For each signal, explore:
1. What trigger events could accelerate this signal?
2. What cascading effects would follow?
3. What positive feedback loops could amplify the impact?
4. What system vulnerabilities would this exploit?
5. What would the peak disruption look like?

Return JSON with:
{{
    "amplified_pathways": [
        {{
            "pathway_id": "amp_001",
            "source_signal": "Signal title",
            "category": "black_swan/contrarian/wild_card",
            "trigger_events": ["Event 1", "Event 2"],
            "cascade_chain": "Step-by-step escalation narrative",
            "feedback_loops": ["Loop 1", "Loop 2"],
            "peak_disruption": "Description of maximum impact",
            "probability": "very_low/low/moderate",
            "impact_potential": 1-10,
            "time_to_peak": "Estimated timeline"
        }}
    ]
}}

Generate 6-10 amplified pathways across the three categories:
- black_swan: Unpredictable high-impact events
- contrarian: Scenarios that contradict consensus
- wild_card: Low probability but transformative possibilities"""

        try:
            response = await litellm.acompletion(
                model=model,
                messages=[
                    {"role": "system", "content": agent_prompt or "You are a systems analyst specializing in cascade effects and amplification dynamics. You identify how small signals can grow into major disruptions."},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                max_tokens=4000,
                response_format={"type": "json_object"}
            )

            result = json.loads(response.choices[0].message.content)
            state.amplified_pathways = result.get("amplified_pathways", [])

        except Exception as e:
            logger.error(f"Amplification analysis failed: {e}")
            state.amplified_pathways = []

        logger.info(f"Amplified pathways: {len(state.amplified_pathways)}")

    async def _run_scenario_building(
        self,
        state: EOSState,
        config: EOSConfig
    ) -> AsyncGenerator[Dict, None]:
        """
        Stage 3: Scenario Building
        Construct detailed extreme scenario narratives.
        """
        logger.info(f"Building scenarios from {len(state.amplified_pathways)} pathways")

        agent_prompt = self._load_agent_prompt("eos_scenario_building_agent")
        agent_config = self._get_agent_config("eos_scenario_building_agent")

        model = agent_config.get('model', config.scenario_model)
        temperature = agent_config.get('temperature', config.scenario_temp)

        # Determine scenario distribution
        target_count = config.scenario_count
        categories_enabled = []
        if config.include_black_swans:
            categories_enabled.append("black_swan")
        if config.include_contrarian:
            categories_enabled.append("contrarian")
        if config.include_wild_cards:
            categories_enabled.append("wild_card")

        article_excerpts = self._format_article_excerpts(state.raw_articles, limit=20, summary_length=300)

        prompt = f"""Create {target_count} analytical EXTREME OUTLIER SCENARIOS for {state.topic}.

CRITICAL INSTRUCTION: All scenarios MUST be derived from the source articles and weak signals below.
- Reference specific articles by number [1], [2], etc.
- Quote or paraphrase actual claims from the sources
- NEVER invent fictional names, companies, people, or events
- Use descriptive placeholders like "a major manufacturer" if needed

SOURCE ARTICLES FROM CORPUS:
{article_excerpts if article_excerpts else "(No articles provided - use trends and pathways below)"}

WEAK SIGNALS DETECTED:
{json.dumps(state.weak_signals[:10], indent=2)}

AMPLIFIED PATHWAYS:
{json.dumps(state.amplified_pathways, indent=2)}

SCENARIO CATEGORIES TO INCLUDE: {', '.join(categories_enabled)}

TIME HORIZON: {config.time_horizon} term

For each scenario:
1. Title summarizing the extrapolation (descriptive, not evocative)
2. Subtitle stating the key assumption being challenged
3. Analysis (2-3 paragraphs) with:
   - TRAJECTORY: Which weak signal, its current state, direction of extrapolation
   - MECHANISM: Causal chain - if [signal] then [consequence] because [mechanism]
   - ENDPOINT: Projected state if trajectory completes
4. Source article references (by number)
5. Specific trigger events from the pathways
6. Probability, impact rating (1-10), and time horizon

Return JSON:
{{
    "scenarios": [
        {{
            "scenario_id": "scn_001",
            "category": "black_swan/contrarian/wild_card",
            "title": "Descriptive scenario title",
            "subtitle": "Key assumption being challenged",
            "analysis": "2-3 paragraph analytical extrapolation citing sources",
            "weak_signals": ["Signal from source data"],
            "source_articles": [1, 3, 7],
            "trigger_events": ["Trigger from pathways"],
            "probability": "very_low/low/moderate",
            "impact_rating": 1-10,
            "time_horizon": "2025-2027",
            "source_pathways": ["pathway_id references"]
        }}
    ]
}}"""

        yield {"status": "generating", "progress": 0.3}

        try:
            response = await litellm.acompletion(
                model=model,
                messages=[
                    {"role": "system", "content": agent_prompt or "You are an analytical forecaster. You construct logical extrapolations from weak signals - projecting how outlier positions could develop if their premises prove correct. Ground all scenarios in source data."},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                max_tokens=6000,
                response_format={"type": "json_object"}
            )

            result = json.loads(response.choices[0].message.content)
            state.raw_scenarios = result.get("scenarios", [])

            yield {"status": "scenarios_built", "progress": 0.9, "count": len(state.raw_scenarios)}

        except Exception as e:
            logger.error(f"Scenario building failed: {e}")
            state.raw_scenarios = []
            yield {"status": "fallback", "progress": 0.9, "error": str(e)}

        yield {"status": "completed", "progress": 1.0}

    async def _run_implications(
        self,
        state: EOSState,
        config: EOSConfig
    ) -> AsyncGenerator[Dict, None]:
        """
        Stage 4: Implications
        Add strategic hedging recommendations and early warning indicators.
        """
        logger.info(f"Generating implications for {len(state.raw_scenarios)} scenarios")

        agent_prompt = self._load_agent_prompt("eos_implications_agent")
        agent_config = self._get_agent_config("eos_implications_agent")

        model = agent_config.get('model', config.implications_model)
        temperature = agent_config.get('temperature', config.implications_temp)

        prompt = f"""For each extreme scenario, provide STRATEGIC IMPLICATIONS and EARLY WARNING INDICATORS.

SCENARIOS:
{json.dumps(state.raw_scenarios, indent=2)}

For each scenario, add:
1. Early warning signs (3-5 observable indicators that would signal this scenario is materializing)
2. Strategic implications (what it would mean for organizations in this space)
3. Preparation actions (3-5 concrete steps to hedge against or prepare for this scenario). Each preparation action must be one the READER's own organization can take within its remit — do NOT recommend actions for governments, regulators, or other third parties the reader does not control; frame them as how the reader should prepare, not how the wider world should manage the scenario.

Return JSON with:
{{
    "enhanced_scenarios": [
        {{
            "scenario_id": "from original",
            "early_warning_signs": [
                "Specific observable indicator 1",
                "Specific observable indicator 2"
            ],
            "strategic_implications": "Detailed strategic analysis",
            "preparation_actions": [
                "Concrete action 1",
                "Concrete action 2"
            ]
        }}
    ]
}}

Focus on ACTIONABLE indicators and preparations. Warning signs should be specific and measurable."""

        yield {"status": "analyzing", "progress": 0.3}

        try:
            response = await litellm.acompletion(
                model=model,
                messages=[
                    {"role": "system", "content": agent_prompt or "You are a strategic advisor specializing in risk hedging and contingency planning for extreme scenarios."},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                max_tokens=4000,
                response_format={"type": "json_object"}
            )

            result = json.loads(response.choices[0].message.content)
            enhancements = {e["scenario_id"]: e for e in result.get("enhanced_scenarios", [])}

            yield {"status": "merging", "progress": 0.7}

            # Build pathway lookup for amplification_path
            pathway_lookup = {p.get("pathway_id", ""): p for p in state.amplified_pathways}

            # Merge into final scenarios
            for raw in state.raw_scenarios:
                scenario_id = raw.get("scenario_id", "")
                enhancement = enhancements.get(scenario_id, {})

                # Find amplification path from source pathways
                amplification_path = ""
                for pid in raw.get("source_pathways", []):
                    pathway = pathway_lookup.get(pid)
                    if pathway and pathway.get("cascade_chain"):
                        amplification_path = pathway["cascade_chain"]
                        break

                scenario = OutlierScenario(
                    id=scenario_id,
                    category=raw.get("category", "wild_card"),
                    title=raw.get("title", "Unknown Scenario"),
                    subtitle=raw.get("subtitle", ""),
                    description=raw.get("analysis") or raw.get("narrative", ""),
                    probability=raw.get("probability", "low"),
                    impact_rating=raw.get("impact_rating", 5),
                    time_horizon=raw.get("time_horizon", ""),
                    weak_signals=raw.get("weak_signals", []),
                    amplification_path=amplification_path,
                    trigger_events=raw.get("trigger_events", []),
                    early_warning_signs=enhancement.get("early_warning_signs", []),
                    strategic_implications=enhancement.get("strategic_implications", ""),
                    preparation_actions=enhancement.get("preparation_actions", []),
                    source_trends=[t.get("title", "") for t in state.trends_data[:3]],
                    source_consensus=[c.get("category", "") for c in state.consensus_data[:3]]
                )
                state.scenarios.append(scenario)

            yield {"status": "completed", "progress": 1.0, "scenarios": len(state.scenarios)}

        except Exception as e:
            logger.error(f"Implications generation failed: {e}")
            # Create basic scenarios without enhancements
            for raw in state.raw_scenarios:
                scenario = OutlierScenario(
                    id=raw.get("scenario_id", str(uuid.uuid4())[:8]),
                    category=raw.get("category", "wild_card"),
                    title=raw.get("title", "Unknown Scenario"),
                    subtitle=raw.get("subtitle", ""),
                    description=raw.get("analysis") or raw.get("narrative", ""),
                    probability=raw.get("probability", "low"),
                    impact_rating=raw.get("impact_rating", 5),
                    time_horizon=raw.get("time_horizon", ""),
                    weak_signals=raw.get("weak_signals", []),
                    trigger_events=raw.get("trigger_events", [])
                )
                state.scenarios.append(scenario)

            yield {"status": "completed_with_fallback", "progress": 1.0, "scenarios": len(state.scenarios)}


# Singleton instance
_eos_instance: Optional[ExtremeOutlierService] = None


def get_extreme_outlier_service() -> ExtremeOutlierService:
    """Get the global Extreme Outlier Scenarios service instance."""
    global _eos_instance
    if _eos_instance is None:
        _eos_instance = ExtremeOutlierService()
    return _eos_instance
