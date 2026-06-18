"""
Power, Attention & Money (PAM) Service

Provides analysis of power, attention, and money flows in the knowledge economy,
tracking the 5 key trends reshaping scholarly publishing by 2030.

Architecture (v2.0):
- Pillar agents (Power, Attention, Money, Trend) run as true parallel agents
- External data providers (Semantic Scholar, Google Search) for measured metrics
- TrendCalculator for repeatable, measurable trend scoring
- Configurable prompts loaded from .md files (like Newsletter/EB)
- Config loaded from pam_config.json
"""

import asyncio
import json
import logging
import os
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, AsyncGenerator
from datetime import datetime, timedelta, date
from collections import defaultdict

from fastapi.concurrency import run_in_threadpool
import litellm

from app.database import get_database_instance
from app.database_query_facade import DatabaseQueryFacade
from app.vector_store_pgvector import search_articles as vector_search_articles
from app.ai_models import get_ai_model

# Import new agent architecture
from app.services.pam_agents import (
    BasePillarAgent, PillarConfig, AnalysisContext, AgentState,
    PowerAgent, AttentionAgent, MoneyAgent, TrendAgent
)
from app.services.trend_calculator import TrendCalculator
from app.services.external_data import SemanticScholarProvider, GoogleSearchProvider

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-5.4-mini"
CONFIG_PATH = Path(__file__).parent.parent.parent / "data" / "auspex" / "pam_config.json"
AGENTS_PATH = Path(__file__).parent.parent.parent / "data" / "auspex" / "agents"

# Trend definitions with search keywords
TREND_DEFINITIONS = {
    "T1": {
        "name": "Invisible LLM Ecosystems",
        "short_name": "Invisible LLMs",
        "description": "AI assistants become primary gateway; brand visibility diminishes",
        "keywords": [
            "AI assistant", "ChatGPT", "Claude AI", "LLM", "zero-click",
            "AI intermediary", "brand visibility", "direct traffic decline",
            "AI gateway", "conversational AI", "AI discovery"
        ],
        "dimension": "attention"
    },
    "T2": {
        "name": "Agentic AI Reshaping Workflows",
        "short_name": "Agentic AI",
        "description": "AI agents read literature, draft protocols, automate research",
        "keywords": [
            "AI agent", "autonomous research", "AI workflow", "research automation",
            "AI cognition", "scientific AI", "automated literature review",
            "AI manuscript", "research assistant AI", "lab automation"
        ],
        "dimension": "power"
    },
    "T3": {
        "name": "Decline of SEO, Rise of GEO",
        "short_name": "SEO to GEO",
        "description": "Traditional search collapses; generative engine optimization emerges",
        "keywords": [
            "SEO decline", "generative engine", "GEO optimization", "AI discoverability",
            "machine-readable content", "structured data", "metadata standards",
            "AI search", "zero-click search", "AI answer", "search traffic"
        ],
        "dimension": "attention"
    },
    "T4": {
        "name": "Regulatory & Provenance Pressures",
        "short_name": "Regulatory",
        "description": "AI regulations, copyright, and content provenance requirements",
        "keywords": [
            "AI regulation", "EU AI Act", "content provenance", "C2PA", "copyright AI",
            "licensing AI", "AI training rights", "opt-out AI", "AI governance",
            "content credentials", "watermarking AI", "AI compliance"
        ],
        "dimension": "power"
    },
    "T5": {
        "name": "Market Consolidation",
        "short_name": "Consolidation",
        "description": "Concentration around compute + data + AI giants",
        "keywords": [
            "AI acquisition", "tech consolidation", "publisher merger", "AI funding",
            "market concentration", "vertical integration", "AI monopoly",
            "big tech publishing", "content acquisition", "platform consolidation"
        ],
        "dimension": "money"
    }
}

# Publisher pillars
PUBLISHER_PILLARS = {
    "trust": {
        "name": "Trust Provider",
        "description": "Integrity and verification of knowledge",
        "components": [
            "peer_review_integrity",
            "retraction_transparency",
            "ai_content_detection",
            "data_verification",
            "misinformation_combat"
        ]
    },
    "infrastructure": {
        "name": "Content Infrastructure Provider",
        "description": "Technical backbone for knowledge creation and distribution",
        "components": [
            "api_accessibility",
            "metadata_quality",
            "rights_management",
            "ai_ready_pipelines",
            "provenance_systems"
        ]
    },
    "connector": {
        "name": "Researcher Connector",
        "description": "Persistent connections to researchers via incentive alignment",
        "components": [
            "author_relationships",
            "community_building",
            "workflow_integration",
            "discovery_reach",
            "incentive_systems"
        ]
    }
}

# 2030 Scenario definitions
SCENARIOS_2030 = {
    "trusted_ecosystem": {
        "name": "Trusted Ecosystem",
        "regulation": "high",
        "concentration": "low",
        "description": "Publishers as trusted custodians, diverse ecosystem",
        "probability": 0.30
    },
    "fragmented_compliance": {
        "name": "Fragmented Compliance",
        "regulation": "high",
        "concentration": "high",
        "description": "Multiple standards, regional silos, compliance burden",
        "probability": 0.25
    },
    "open_chaos": {
        "name": "Open Chaos",
        "regulation": "low",
        "concentration": "low",
        "description": "Wild west AI, no attribution, trust erosion",
        "probability": 0.15
    },
    "behemoth_control": {
        "name": "Behemoth Control",
        "regulation": "low",
        "concentration": "high",
        "description": "3-5 giants own everything, publishers commoditized",
        "probability": 0.30
    }
}


class PAMService:
    """Service for Power, Attention & Money flows analysis.

    Architecture v2.0:
    - Pillar agents run as parallel processes with optional different models
    - External data providers for measured metrics (Semantic Scholar, Google Search)
    - TrendCalculator for repeatable trend scoring
    - Configurable prompts loaded from .md files

    Config loaded from data/auspex/pam_config.json
    """

    def __init__(self):
        self.db = DatabaseQueryFacade(get_database_instance(), logger)
        self.model = DEFAULT_MODEL

        # Load configuration
        self.config = self._load_config()

        # Initialize external data providers
        self.semantic_scholar = SemanticScholarProvider()
        self.google_search = GoogleSearchProvider()

        # Check provider availability and log status
        self._check_provider_availability()

        # Initialize trend calculator with smoothing for score stability
        self.trend_calculator = TrendCalculator(
            weights=self.config.get("trend_calculator", {}).get("weights"),
            normalization=self.config.get("trend_calculator", {}).get("normalization"),
            velocity_thresholds=self.config.get("trend_calculator", {}).get("velocity_thresholds"),
            smoothing_factor=self.config.get("trend_calculator", {}).get("smoothing_factor")
        )

        # Agent instances (lazy initialization)
        self._power_agent: Optional[PowerAgent] = None
        self._attention_agent: Optional[AttentionAgent] = None
        self._money_agent: Optional[MoneyAgent] = None
        self._trend_agent: Optional[TrendAgent] = None

    def _check_provider_availability(self):
        """Check and log external data provider availability."""
        # Check Google Search provider
        if self.google_search.is_available():
            logger.info("PAM: Google Search provider is available")
        else:
            logger.warning("PAM: Google Search provider NOT available - missing GOOGLE_CSE_API_KEY or GOOGLE_CSE_ID")
            # Disable Google Search in external_data config
            ext_config = self.config.get("external_data", {})
            if "google_search" in ext_config:
                ext_config["google_search"]["enabled"] = False

        # Check Semantic Scholar provider
        ss_status = self.semantic_scholar.get_status()
        if ss_status.get("has_api_key"):
            logger.info("PAM: Semantic Scholar provider available with API key (no rate limits)")
        else:
            logger.info("PAM: Semantic Scholar provider available (rate-limited without API key)")

    def get_provider_status(self) -> Dict[str, Any]:
        """Get status of all external data providers."""
        return {
            "google_search": self.google_search.get_status(),
            "semantic_scholar": self.semantic_scholar.get_status(),
            "external_data_enabled": self.config.get("defaults", {}).get("enable_external_data", True)
        }

    def _load_config(self) -> Dict[str, Any]:
        """Load PAM configuration from JSON file."""
        try:
            if CONFIG_PATH.exists():
                with open(CONFIG_PATH, 'r') as f:
                    config = json.load(f)
                logger.info(f"Loaded PAM config v{config.get('version', 'unknown')}")
                return config
        except Exception as e:
            logger.warning(f"Failed to load PAM config: {e}")

        # Return defaults if config not found
        return {
            "defaults": {
                "days_back": 90,
                "article_limit": 100,
                "relevance_threshold": 0.75,
                "articles_per_topic": 20,
                "enable_external_data": True,
                "parallel_agents": True
            },
            "agents": {
                "power": {"model": "gpt-5.4-mini", "temperature": 0.3, "max_tokens": 4000},
                "attention": {"model": "gpt-5.4-mini", "temperature": 0.3, "max_tokens": 4000},
                "money": {"model": "gpt-5.4-mini", "temperature": 0.3, "max_tokens": 4000},
                "trends": {"model": "gpt-5.4-mini", "temperature": 0.3, "max_tokens": 3000},
                "synthesis": {"model": "gpt-5.4", "temperature": 0.4, "max_tokens": 5000}
            },
            "score_calculation": {
                "pillar_weights": {"power": 0.35, "attention": 0.35, "money": 0.30},
                "threat_levels": {"critical": 80, "high": 70, "elevated": 55, "moderate": 40}
            }
        }

    def _get_agent_config(self, pillar: str, overrides: Optional[Dict] = None) -> PillarConfig:
        """Build agent configuration with optional overrides."""
        agent_config = self.config.get("agents", {}).get(pillar, {})
        defaults = self.config.get("defaults", {})

        return PillarConfig(
            pillar=pillar,
            model=overrides.get(f"{pillar}_model") if overrides else None or agent_config.get("model", DEFAULT_MODEL),
            temperature=agent_config.get("temperature", 0.3),
            max_tokens=agent_config.get("max_tokens", 4000),
            prompt_file=agent_config.get("prompt_file", f"pam_{pillar}_agent.md"),
            relevance_threshold=overrides.get("relevance_threshold") if overrides else None or defaults.get("relevance_threshold", 0.65),
            articles_per_topic=overrides.get("articles_per_topic") if overrides else None or defaults.get("articles_per_topic", 20),
            enable_external_data=overrides.get("enable_external_data") if overrides else None or defaults.get("enable_external_data", True)
        )

    def get_deep_search_keywords(self, keyword_type: str, preset: str = None) -> List[str]:
        """
        Get deep search keywords for a specific type based on the configured preset.

        Args:
            keyword_type: One of 'cost_dynamics', 'ma_activity', 'regulatory'
            preset: Override the default preset (optional)

        Returns:
            List of keywords for the specified type
        """
        # Use provided preset or fall back to config default
        preset = preset or self.config.get("keyword_preset", "scholarly_publishing")

        # Get presets from config
        deep_search_config = self.config.get("deep_search_keywords", {})
        presets = deep_search_config.get("presets", {})

        # Get the specific preset
        preset_config = presets.get(preset, {})

        # Get keywords for the type
        keywords = preset_config.get(keyword_type, [])

        if not keywords:
            logger.warning(f"No keywords found for type '{keyword_type}' in preset '{preset}'. Using defaults.")
            # Fallback defaults
            defaults = {
                "cost_dynamics": ["cost cutting", "layoffs", "restructuring", "budget cuts"],
                "ma_activity": ["acquisition", "merger", "funding round", "investment"],
                "regulatory": ["regulation", "compliance", "law", "legislation"]
            }
            keywords = defaults.get(keyword_type, [])

        return keywords

    def get_entity_variations(self, preset: str = None) -> Dict[str, List[str]]:
        """Get entity name variations for the configured preset."""
        preset = preset or self.config.get("keyword_preset", "scholarly_publishing")
        deep_search_config = self.config.get("deep_search_keywords", {})
        presets = deep_search_config.get("presets", {})
        preset_config = presets.get(preset, {})
        return preset_config.get("entity_variations", {})

    def get_available_presets(self) -> List[Dict[str, str]]:
        """Get list of available keyword presets with descriptions."""
        deep_search_config = self.config.get("deep_search_keywords", {})
        presets = deep_search_config.get("presets", {})
        return [
            {"id": preset_id, "description": preset_data.get("description", preset_id)}
            for preset_id, preset_data in presets.items()
        ]

    def _get_power_agent(self, overrides: Optional[Dict] = None) -> PowerAgent:
        """Get or create power agent."""
        config = self._get_agent_config("power", overrides)
        return PowerAgent(config, google_search_provider=self.google_search)

    def _get_attention_agent(self, overrides: Optional[Dict] = None) -> AttentionAgent:
        """Get or create attention agent."""
        config = self._get_agent_config("attention", overrides)
        entity_variations = self.get_entity_variations()
        return AttentionAgent(config, semantic_scholar_provider=self.semantic_scholar, entity_variations=entity_variations)

    def _get_money_agent(self, overrides: Optional[Dict] = None) -> MoneyAgent:
        """Get or create money agent."""
        config = self._get_agent_config("money", overrides)
        cost_keywords = self.get_deep_search_keywords('cost_dynamics')
        return MoneyAgent(config, google_search_provider=self.google_search, cost_keywords=cost_keywords)

    def _get_trend_agent(self, overrides: Optional[Dict] = None) -> TrendAgent:
        """Get or create trend agent."""
        config = self._get_agent_config("trends", overrides)
        return TrendAgent(config, trend_calculator=self.trend_calculator)

    async def run_comprehensive_analysis(
        self,
        topic: Optional[str] = None,
        analysis_type: str = "comprehensive",
        entity_type: str = "publisher",
        time_horizon: str = "1_year",
        trend_focus: List[str] = None,
        days_back: int = 90,
        article_limit: int = 100,
        model: str = None,
        username: str = None,
        force_regenerate_queries: bool = False
    ) -> Dict[str, Any]:
        """
        Run comprehensive PAM analysis using pillar-by-pillar workflow.

        NEW WORKFLOW:
        1. For each pillar (Power, Attention, Money):
           - Generate/retrieve cached semantic queries for the pillar
           - Search across ALL topics, fetch articles
           - Select top N articles per topic by relevance
           - Synthesize pillar analysis with citations
        2. Map PAM to Publisher Pillars (Trust, Infrastructure, Connector)
        3. Synthesize scenarios from all analyses
        4. Store scores for trending over time
        5. Store article dataset used

        Args:
            article_limit: Maximum total articles to analyze. Controls articles_per_topic.
                          - 50 articles -> ~10 per topic
                          - 100 articles -> ~20 per topic
                          - 200 articles -> ~40 per topic

        Returns analysis of power, attention, and money flows with trend assessment.
        """
        start_time = datetime.now()
        run_id = str(uuid.uuid4())
        trend_focus = trend_focus or ["T1", "T2", "T3", "T4", "T5"]
        model = model or self.model
        all_dataset_records = []

        # Calculate articles_per_topic from article_limit
        # With ~5-7 topics and 3 pillars (some overlap), aim for article_limit / 5
        articles_per_topic = max(10, article_limit // 5)
        logger.info(f"PAM: article_limit={article_limit} -> articles_per_topic={articles_per_topic}")

        try:
            logger.info(f"PAM: Starting pillar-by-pillar analysis (run_id={run_id})")

            # === POWER PILLAR ===
            logger.info("PAM: Analyzing POWER pillar...")
            power_queries = await self._generate_pillar_queries('power', model, force_regenerate_queries)
            power_articles, power_dataset = await self._collect_pillar_articles(
                'power', power_queries, days_back, articles_per_topic
            )
            all_dataset_records.extend(power_dataset)

            if analysis_type in ["comprehensive", "power"]:
                power_analysis = await self._analyze_power(power_articles, topic, model)
            else:
                power_analysis = None

            # === ATTENTION PILLAR ===
            logger.info("PAM: Analyzing ATTENTION pillar...")
            attention_queries = await self._generate_pillar_queries('attention', model, force_regenerate_queries)
            attention_articles, attention_dataset = await self._collect_pillar_articles(
                'attention', attention_queries, days_back, articles_per_topic
            )
            all_dataset_records.extend(attention_dataset)

            if analysis_type in ["comprehensive", "attention"]:
                attention_analysis = await self._analyze_attention(attention_articles, topic, model)
            else:
                attention_analysis = None

            # === MONEY PILLAR ===
            logger.info("PAM: Analyzing MONEY pillar...")
            money_queries = await self._generate_pillar_queries('money', model, force_regenerate_queries)
            money_articles, money_dataset = await self._collect_pillar_articles(
                'money', money_queries, days_back, articles_per_topic
            )
            all_dataset_records.extend(money_dataset)

            # === SPECIALIZED DEEP SCANS (No Date Limit) ===
            # These search the ENTIRE database for trend-specific articles
            logger.info("PAM: Running specialized deep scans...")

            # AI Ecosystem Deep Scan for Attention pillar (T1: Invisible LLMs, T3: SEO to GEO)
            ai_articles, ai_dataset = await self._fetch_ai_ecosystem_articles(limit=30)
            seen_attention_uris = {a.get('uri') for a in attention_articles}
            new_attention = []
            for article in ai_articles:
                if article.get('uri') not in seen_attention_uris:
                    new_attention.append(article)
                    seen_attention_uris.add(article.get('uri'))
            attention_articles = new_attention + attention_articles  # Prepend
            all_dataset_records.extend(ai_dataset)

            # M&A Deep Scan for Money pillar (T5: Market Consolidation)
            ma_articles, ma_dataset = await self._fetch_ma_activity_articles(limit=30)
            seen_money_uris = {a.get('uri') for a in money_articles}
            new_money = []
            for article in ma_articles:
                if article.get('uri') not in seen_money_uris:
                    new_money.append(article)
                    seen_money_uris.add(article.get('uri'))
            money_articles = new_money + money_articles  # Prepend
            all_dataset_records.extend(ma_dataset)

            # Regulation Deep Scan for Power pillar (T4: Regulatory Pressures)
            reg_articles, reg_dataset = await self._fetch_regulation_articles(limit=30)
            seen_power_uris = {a.get('uri') for a in power_articles}
            new_power = []
            for article in reg_articles:
                if article.get('uri') not in seen_power_uris:
                    new_power.append(article)
                    seen_power_uris.add(article.get('uri'))
            power_articles = new_power + power_articles  # Prepend
            all_dataset_records.extend(reg_dataset)

            logger.info(f"PAM: After deep scans - Power: {len(power_articles)}, Attention: {len(attention_articles)}, Money: {len(money_articles)}")

            if analysis_type in ["comprehensive", "money"]:
                money_analysis = await self._analyze_money(money_articles, topic, model)
            else:
                money_analysis = None

            # === COMBINE ALL ARTICLES ===
            # Deduplicate by URI
            all_articles_dict = {}
            for a in power_articles + attention_articles + money_articles:
                uri = a.get('uri')
                if uri and uri not in all_articles_dict:
                    all_articles_dict[uri] = a
            all_articles = list(all_articles_dict.values())

            logger.info(f"PAM: Total unique articles collected: {len(all_articles)} (incl. deep scans)")

            # === TRENDS ANALYSIS ===
            logger.info("PAM: Analyzing trends...")
            trend_analysis = await self._analyze_trends(all_articles, trend_focus, model)

            # === CALCULATE SCORES ===
            scores = self._calculate_scores(power_analysis, attention_analysis, money_analysis)
            scores['articles_analyzed'] = len(all_articles)

            # === MAP TO PUBLISHER PILLARS ===
            publisher_pillars = self._map_to_publisher_pillars(
                power_analysis, attention_analysis, money_analysis
            )

            # === GET HISTORICAL CONTEXT ===
            historical_context = await self._get_historical_context(topic, days_back=30)

            # === GENERATE EXECUTIVE SUMMARY ===
            executive_summary = await self._generate_executive_summary(
                power_analysis, attention_analysis, money_analysis,
                trend_analysis, scores, model, historical_context
            )

            # === GENERATE RECOMMENDATIONS ===
            recommendations = await self._generate_recommendations(
                power_analysis, attention_analysis, money_analysis,
                trend_analysis, entity_type, model
            )

            # === ANALYZE SCENARIOS ===
            scenario_analysis = self._analyze_scenarios(trend_analysis)

            duration = (datetime.now() - start_time).total_seconds()

            # Build reference articles with proper indexing for citations
            reference_articles = [
                {
                    "id": idx + 1,  # 1-based for citation matching [1], [2], etc.
                    "uri": a.get("uri"),
                    "title": a.get("title", "Untitled"),
                    "source": a.get("news_source") or a.get("source", "Unknown"),
                    "publication_date": a.get("publication_date") or a.get("submission_date", ""),
                    "topic": a.get("topic") or a.get("_topic", ""),
                    "matched_pillar": a.get("_pillar", ""),
                    "relevance_score": a.get("_relevance_score", 0),
                }
                for idx, a in enumerate(all_articles) if a.get("uri")
            ]

            result = {
                "run_id": run_id,
                "topic": topic,
                "analysis_type": analysis_type,
                "entity_type": entity_type,
                "time_horizon": time_horizon,
                "executive_summary": executive_summary,
                "scores": scores,
                "power_analysis": power_analysis,
                "attention_analysis": attention_analysis,
                "money_analysis": money_analysis,
                "trend_analysis": trend_analysis,
                "scenario_analysis": scenario_analysis,
                "publisher_pillars": publisher_pillars,
                "strategic_recommendations": recommendations,
                "articles_analyzed": len(all_articles),
                "article_uris": [a.get("uri") for a in all_articles if a.get("uri")],
                "reference_articles": reference_articles,
                "pillar_queries": {
                    "power": power_queries,
                    "attention": attention_queries,
                    "money": money_queries
                },
                "model_used": model,
                "duration_seconds": duration,
                "created_at": datetime.now().isoformat()
            }

            # === SAVE RESULTS ===
            # Save to database
            await self._save_analysis_run(result, username)

            # Save trend snapshot for historical tracking
            await self._save_trend_snapshot(run_id, topic, scores, trend_analysis)

            # Save metrics time series
            await self._save_metrics_timeseries(run_id, scores, trend_analysis)

            # Save article dataset
            await self._save_article_dataset(run_id, all_dataset_records)

            # Cache the report for quick retrieval
            await self._cache_report(
                result=result,
                topic=topic,
                analysis_type=analysis_type,
                days_back=days_back,
                time_horizon=time_horizon,
                trend_focus=trend_focus,
                entity_type=entity_type,
                model=model,
                duration=duration,
                article_count=len(all_articles)
            )

            logger.info(f"PAM: Analysis complete in {duration:.1f}s, {len(all_articles)} articles analyzed")
            return result

        except Exception as e:
            logger.error(f"PAM analysis failed: {e}")
            raise

    # =========================================================================
    # NEW: Agent-based analysis (v2.0 architecture)
    # =========================================================================

    async def run_agent_based_analysis(
        self,
        topic: Optional[str] = None,
        analysis_type: str = "comprehensive",
        entity_type: str = "publisher",
        time_horizon: str = "1_year",
        trend_focus: List[str] = None,
        days_back: int = 90,
        article_limit: int = 100,
        model: str = None,
        username: str = None,
        force_regenerate_queries: bool = False,
        # New v2.0 parameters
        relevance_threshold: float = None,
        articles_per_topic: int = None,
        enable_external_data: bool = None,
        parallel_agents: bool = None,
        power_model: str = None,
        attention_model: str = None,
        money_model: str = None,
        trend_model: str = None,
        profile_id: Optional[int] = None  # Org profile for monitored brands
    ) -> Dict[str, Any]:
        """
        Run PAM analysis using the new agent-based architecture.

        This method uses true parallel agents with:
        - External data providers (Semantic Scholar, Google Search)
        - Configurable prompts loaded from .md files
        - TrendCalculator for repeatable, measurable trend scoring
        - Optional per-pillar model overrides

        Args:
            topic: Optional topic filter
            analysis_type: Type of analysis
            entity_type: Target entity type
            time_horizon: Analysis horizon
            trend_focus: Trends to focus on
            days_back: Days of data to analyze
            article_limit: Maximum articles
            model: Default model (can be overridden per pillar)
            username: User running analysis
            force_regenerate_queries: Force regeneration of cached queries
            relevance_threshold: Override default relevance threshold (0.3-0.9)
            articles_per_topic: Override articles per topic selection
            enable_external_data: Enable/disable external API calls
            parallel_agents: Run pillar agents in parallel
            power_model: Model override for power analysis
            attention_model: Model override for attention analysis
            money_model: Model override for money analysis
            trend_model: Model override for trend analysis

        Returns:
            Complete PAM analysis result with data source indicators
        """
        start_time = datetime.now()
        run_id = str(uuid.uuid4())
        trend_focus = trend_focus or ["T1", "T2", "T3", "T4", "T5"]
        model = model or self.model
        all_dataset_records = []

        # Get config values with overrides
        defaults = self.config.get("defaults", {})
        relevance_threshold = relevance_threshold or defaults.get("relevance_threshold", 0.65)
        articles_per_topic = articles_per_topic or defaults.get("articles_per_topic", 20)
        enable_external_data = enable_external_data if enable_external_data is not None else defaults.get("enable_external_data", True)
        parallel_agents = parallel_agents if parallel_agents is not None else defaults.get("parallel_agents", True)

        # Build overrides dict for agent configs
        overrides = {
            "relevance_threshold": relevance_threshold,
            "articles_per_topic": articles_per_topic,
            "enable_external_data": enable_external_data,
            "power_model": power_model or model,
            "attention_model": attention_model or model,
            "money_model": money_model or model,
            "trends_model": trend_model or model
        }

        logger.info(f"PAM v2: Starting agent-based analysis (run_id={run_id}, parallel={parallel_agents})")
        logger.info(f"PAM v2: Config: relevance={relevance_threshold}, articles_per_topic={articles_per_topic}, external_data={enable_external_data}")

        try:
            # === COLLECT ARTICLES FOR EACH PILLAR ===
            # Generate/retrieve cached queries
            power_queries = await self._generate_pillar_queries('power', model, force_regenerate_queries)
            attention_queries = await self._generate_pillar_queries('attention', model, force_regenerate_queries)
            money_queries = await self._generate_pillar_queries('money', model, force_regenerate_queries)

            # Collect articles per pillar (standard vector search with days_back)
            power_articles, power_dataset = await self._collect_pillar_articles(
                'power', power_queries, days_back, articles_per_topic, relevance_threshold
            )
            attention_articles, attention_dataset = await self._collect_pillar_articles(
                'attention', attention_queries, days_back, articles_per_topic, relevance_threshold
            )
            money_articles, money_dataset = await self._collect_pillar_articles(
                'money', money_queries, days_back, articles_per_topic, relevance_threshold
            )

            # === SPECIALIZED DEEP SCANS (No Date Limit) ===
            # These search the ENTIRE database for trend-specific articles
            # T1/T3 (AI Ecosystems, SEO to GEO) -> Attention pillar
            # T4 (Regulatory Pressures) -> Power pillar
            # T5 (Market Consolidation) -> Money pillar
            logger.info("PAM v2: Running specialized deep scans (entire database)...")

            # AI Ecosystem Deep Scan for Attention pillar (T1: Invisible LLMs, T3: SEO to GEO)
            ai_articles, ai_dataset = await self._fetch_ai_ecosystem_articles(limit=30)

            # M&A Deep Scan for Money pillar (T5: Market Consolidation)
            ma_articles, ma_dataset = await self._fetch_ma_activity_articles(limit=30)

            # Regulation Deep Scan for Power pillar (T4: Regulatory Pressures)
            reg_articles, reg_dataset = await self._fetch_regulation_articles(limit=30)

            # PREPEND deep scan articles (they're high-priority for their trends)
            # This ensures they make it into the LLM prompt (max_articles_for_llm=30)

            # Prepend AI Ecosystem articles to attention_articles (deduplicated)
            seen_attention_uris = {a.get('uri') for a in attention_articles}
            new_attention = []
            for article in ai_articles:
                if article.get('uri') not in seen_attention_uris:
                    new_attention.append(article)
                    seen_attention_uris.add(article.get('uri'))
            attention_articles = new_attention + attention_articles

            # Prepend M&A articles to money_articles (deduplicated)
            seen_money_uris = {a.get('uri') for a in money_articles}
            new_money = []
            for article in ma_articles:
                if article.get('uri') not in seen_money_uris:
                    new_money.append(article)
                    seen_money_uris.add(article.get('uri'))
            money_articles = new_money + money_articles

            # Prepend Regulation articles to power_articles (deduplicated)
            seen_power_uris = {a.get('uri') for a in power_articles}
            new_power = []
            for article in reg_articles:
                if article.get('uri') not in seen_power_uris:
                    new_power.append(article)
                    seen_power_uris.add(article.get('uri'))
            power_articles = new_power + power_articles

            logger.info(f"PAM v2: After deep scans - Power: {len(power_articles)}, Attention: {len(attention_articles)}, Money: {len(money_articles)}")

            all_dataset_records.extend(power_dataset)
            all_dataset_records.extend(attention_dataset)
            all_dataset_records.extend(money_dataset)
            all_dataset_records.extend(ai_dataset)
            all_dataset_records.extend(ma_dataset)
            all_dataset_records.extend(reg_dataset)

            # Combine all articles (deduplicated)
            all_articles_dict = {}
            for a in power_articles + attention_articles + money_articles:
                uri = a.get('uri')
                if uri and uri not in all_articles_dict:
                    all_articles_dict[uri] = a
            all_articles = list(all_articles_dict.values())

            logger.info(f"PAM v2: Collected {len(all_articles)} unique articles (incl. deep scans)")

            # Fetch pre-extracted events from event tables
            financial_events, regulatory_events = await self._fetch_extracted_events(days_back)
            logger.info(f"PAM v2: Loaded {len(financial_events)} financial events, {len(regulatory_events)} regulatory events")

            # Fetch monitored entities (from pam_entities table + org profile brands)
            monitored_entities = await self._fetch_monitored_entities(profile_id)
            logger.info(f"PAM v2: Loaded {len(monitored_entities)} monitored entities for brand tracking")

            # Build analysis context
            context = AnalysisContext(
                run_id=run_id,
                topic=topic or "Scholarly Publishing",
                entity_type=entity_type,
                time_horizon=time_horizon,
                trend_focus=trend_focus,
                days_back=days_back,
                financial_events=financial_events,
                regulatory_events=regulatory_events,
                monitored_entities=monitored_entities
            )

            # === RUN PILLAR AGENTS ===
            if parallel_agents:
                power_analysis, attention_analysis, money_analysis = await self._run_agents_parallel(
                    power_articles, attention_articles, money_articles, context, overrides
                )
            else:
                power_analysis, attention_analysis, money_analysis = await self._run_agents_sequential(
                    power_articles, attention_articles, money_articles, context, overrides
                )

            # === TREND ANALYSIS WITH CALCULATOR ===
            logger.info("PAM v2: Running trend analysis with TrendCalculator...")
            trend_agent = self._get_trend_agent(overrides)
            trend_results = []

            # Organize articles by trend for TrendAgent
            articles_by_trend = self._organize_articles_by_trend(all_articles, trend_focus)
            logger.info(f"PAM v2: Organized {len(all_articles)} articles across {len(articles_by_trend)} trends")

            # Fetch previous trend scores for EMA smoothing (stabilizes scores between runs)
            previous_trend_scores = await self._get_previous_trend_scores(topic)
            if previous_trend_scores:
                logger.info(f"PAM v2: Using previous scores for EMA smoothing: {list(previous_trend_scores.keys())}")

            async for progress in trend_agent.analyze_trends(
                articles_by_trend,
                context,
                previous_scores=previous_trend_scores
            ):
                if progress.get("stage") == "complete" and progress.get("result"):
                    trend_results = progress["result"]
                elif progress.get("stage") == "error":
                    logger.warning(f"Trend agent error: {progress.get('error')}")

            # Build trend analysis structure
            # TrendAgent returns {"trends": [...], ...}, extract the trends list
            if isinstance(trend_results, dict):
                trend_list = trend_results.get("trends", [])
            elif isinstance(trend_results, list):
                trend_list = trend_results
            else:
                trend_list = []
                logger.warning(f"Unexpected trend_results type: {type(trend_results)}")

            trend_analysis = self._build_trend_analysis(trend_list, trend_focus)

            # Preserve additional data from TrendAgent
            if isinstance(trend_results, dict):
                trend_analysis["external_data_used"] = trend_results.get("external_data_used", {})
                trend_analysis["calculation_method"] = trend_results.get("calculation_method", "")
                trend_analysis["model_used"] = trend_results.get("model_used", "")

            # === AGGREGATE TREND EVIDENCE FROM PILLAR AGENTS ===
            # Pillar agents now extract T1-T5 evidence as part of their analysis
            pillar_trend_evidence = self._aggregate_pillar_trend_evidence(
                power_analysis, attention_analysis, money_analysis
            )
            trend_analysis["pillar_evidence"] = pillar_trend_evidence

            # Enhance trend data with pillar evidence
            self._enhance_trends_with_pillar_evidence(trend_analysis, pillar_trend_evidence)

            # === CALCULATE SCORES ===
            scores = self._calculate_scores_v2(power_analysis, attention_analysis, money_analysis)
            scores['articles_analyzed'] = len(all_articles)
            scores['data_sources'] = self._collect_data_sources(power_analysis, attention_analysis, money_analysis)

            # === MAP TO PUBLISHER PILLARS ===
            publisher_pillars = self._map_to_publisher_pillars(
                power_analysis, attention_analysis, money_analysis
            )

            # === GET HISTORICAL CONTEXT ===
            historical_context = await self._get_historical_context(topic, days_back=30)

            # === GENERATE EXECUTIVE SUMMARY ===
            executive_summary = await self._generate_executive_summary_v2(
                power_analysis, attention_analysis, money_analysis,
                trend_analysis, scores, overrides, historical_context
            )

            # === GENERATE RECOMMENDATIONS ===
            recommendations = await self._generate_recommendations(
                power_analysis, attention_analysis, money_analysis,
                trend_analysis, entity_type, model
            )

            # === ANALYZE SCENARIOS ===
            scenario_analysis = self._analyze_scenarios(trend_analysis)

            duration = (datetime.now() - start_time).total_seconds()

            # Build reference articles with data source indicators
            reference_articles = [
                {
                    "id": idx + 1,
                    "uri": a.get("uri"),
                    "title": a.get("title", "Untitled"),
                    "source": a.get("news_source") or a.get("source", "Unknown"),
                    "publication_date": a.get("publication_date") or a.get("submission_date", ""),
                    "topic": a.get("topic") or a.get("_topic", ""),
                    "matched_pillar": a.get("_pillar", ""),
                    "relevance_score": a.get("_relevance_score", 0),
                }
                for idx, a in enumerate(all_articles) if a.get("uri")
            ]

            result = {
                "run_id": run_id,
                "topic": topic,
                "analysis_type": analysis_type,
                "entity_type": entity_type,
                "time_horizon": time_horizon,
                "executive_summary": executive_summary,
                "scores": scores,
                "power_analysis": power_analysis,
                "attention_analysis": attention_analysis,
                "money_analysis": money_analysis,
                "trend_analysis": trend_analysis,
                "scenario_analysis": scenario_analysis,
                "publisher_pillars": publisher_pillars,
                "strategic_recommendations": recommendations,
                "articles_analyzed": len(all_articles),
                "article_uris": [a.get("uri") for a in all_articles if a.get("uri")],
                "reference_articles": reference_articles,
                "pillar_queries": {
                    "power": power_queries,
                    "attention": attention_queries,
                    "money": money_queries
                },
                "config_used": {
                    "relevance_threshold": relevance_threshold,
                    "articles_per_topic": articles_per_topic,
                    "enable_external_data": enable_external_data,
                    "parallel_agents": parallel_agents,
                    "models": {
                        "power": overrides.get("power_model"),
                        "attention": overrides.get("attention_model"),
                        "money": overrides.get("money_model"),
                        "trend": overrides.get("trends_model")
                    }
                },
                "model_used": model,
                "duration_seconds": duration,
                "created_at": datetime.now().isoformat(),
                "architecture_version": "2.0"
            }

            # === SAVE RESULTS ===
            await self._save_analysis_run(result, username)
            await self._save_trend_snapshot(run_id, topic, scores, trend_analysis)
            await self._save_metrics_timeseries(run_id, scores, trend_analysis)
            await self._save_article_dataset(run_id, all_dataset_records)

            await self._cache_report(
                result=result,
                topic=topic,
                analysis_type=analysis_type,
                days_back=days_back,
                time_horizon=time_horizon,
                trend_focus=trend_focus,
                entity_type=entity_type,
                model=model,
                duration=duration,
                article_count=len(all_articles)
            )

            logger.info(f"PAM v2: Analysis complete in {duration:.1f}s, {len(all_articles)} articles")
            return result

        except Exception as e:
            logger.error(f"PAM v2 analysis failed: {e}")
            raise

    async def _run_agents_parallel(
        self,
        power_articles: List[Dict],
        attention_articles: List[Dict],
        money_articles: List[Dict],
        context: AnalysisContext,
        overrides: Dict
    ) -> Tuple[Dict, Dict, Dict]:
        """Run pillar agents in parallel using asyncio.gather."""
        logger.info("PAM v2: Running pillar agents in parallel...")

        async def run_power():
            agent = self._get_power_agent(overrides)
            async for progress in agent.analyze(power_articles, context):
                if progress.get("stage") == "complete":
                    return progress.get("result", {})
            return {}

        async def run_attention():
            agent = self._get_attention_agent(overrides)
            async for progress in agent.analyze(attention_articles, context):
                if progress.get("stage") == "complete":
                    return progress.get("result", {})
            return {}

        async def run_money():
            agent = self._get_money_agent(overrides)
            async for progress in agent.analyze(money_articles, context):
                if progress.get("stage") == "complete":
                    return progress.get("result", {})
            return {}

        power_result, attention_result, money_result = await asyncio.gather(
            run_power(), run_attention(), run_money()
        )

        return power_result, attention_result, money_result

    async def _run_agents_sequential(
        self,
        power_articles: List[Dict],
        attention_articles: List[Dict],
        money_articles: List[Dict],
        context: AnalysisContext,
        overrides: Dict
    ) -> Tuple[Dict, Dict, Dict]:
        """Run pillar agents sequentially."""
        logger.info("PAM v2: Running pillar agents sequentially...")

        # Power
        power_result = {}
        power_agent = self._get_power_agent(overrides)
        async for progress in power_agent.analyze(power_articles, context):
            if progress.get("stage") == "complete":
                power_result = progress.get("result", {})

        # Attention
        attention_result = {}
        attention_agent = self._get_attention_agent(overrides)
        async for progress in attention_agent.analyze(attention_articles, context):
            if progress.get("stage") == "complete":
                attention_result = progress.get("result", {})

        # Money
        money_result = {}
        money_agent = self._get_money_agent(overrides)
        async for progress in money_agent.analyze(money_articles, context):
            if progress.get("stage") == "complete":
                money_result = progress.get("result", {})

        return power_result, attention_result, money_result

    def _calculate_scores_v2(
        self,
        power_analysis: Optional[Dict],
        attention_analysis: Optional[Dict],
        money_analysis: Optional[Dict]
    ) -> Dict[str, Any]:
        """Calculate composite PAM scores using config weights with data source tracking."""
        # v2 agents return "score" key, fallback to legacy "power_score" etc for compatibility
        power_score = (power_analysis.get("score") or power_analysis.get("power_score", 50)) if power_analysis else 50
        attention_score = (attention_analysis.get("score") or attention_analysis.get("attention_score", 50)) if attention_analysis else 50
        money_score = (money_analysis.get("score") or money_analysis.get("money_score", 50)) if money_analysis else 50

        # Get weights from config
        weights = self.config.get("score_calculation", {}).get("pillar_weights", {
            "power": 0.35, "attention": 0.35, "money": 0.30
        })
        threat_levels_config = self.config.get("score_calculation", {}).get("threat_levels", {
            "critical": 80, "high": 70, "elevated": 55, "moderate": 40
        })

        # Calculate weighted overall score
        overall = (
            power_score * weights.get("power", 0.35) +
            attention_score * weights.get("attention", 0.35) +
            money_score * weights.get("money", 0.30)
        )

        # Determine threat level from config thresholds
        if overall >= threat_levels_config.get("critical", 80):
            threat_level = "critical"
        elif overall >= threat_levels_config.get("high", 70):
            threat_level = "high"
        elif overall >= threat_levels_config.get("elevated", 55):
            threat_level = "elevated"
        elif overall >= threat_levels_config.get("moderate", 40):
            threat_level = "moderate"
        else:
            threat_level = "low"

        return {
            "power_score": power_score,
            "attention_score": attention_score,
            "money_score": money_score,
            "overall_score": round(overall, 1),
            "threat_level": threat_level,
            "weights_used": weights
        }

    def _collect_data_sources(
        self,
        power_analysis: Optional[Dict],
        attention_analysis: Optional[Dict],
        money_analysis: Optional[Dict]
    ) -> Dict[str, List[str]]:
        """Collect data source information from all analyses."""
        sources = {
            "power": [],
            "attention": [],
            "money": []
        }

        if power_analysis:
            sources["power"] = power_analysis.get("data_sources", ["llm_analysis"])
        if attention_analysis:
            sources["attention"] = attention_analysis.get("data_sources", ["llm_analysis"])
        if money_analysis:
            sources["money"] = money_analysis.get("data_sources", ["llm_analysis"])

        return sources

    def _build_trend_analysis(
        self,
        trend_results: List[Dict],
        trend_focus: List[str]
    ) -> Dict[str, Any]:
        """Build trend analysis structure from agent results."""
        trends = []

        for trend_data in trend_results:
            # TrendAgent uses "id", legacy uses "trend_id"
            trend_id = trend_data.get("id") or trend_data.get("trend_id", "")
            if trend_id in trend_focus:
                trends.append({
                    "id": trend_id,
                    # TrendAgent uses "name", legacy uses "trend_name"
                    "name": trend_data.get("name") or trend_data.get("trend_name") or TREND_DEFINITIONS.get(trend_id, {}).get("name", ""),
                    "score": trend_data.get("score", 50),
                    "velocity": trend_data.get("velocity", "stable"),
                    "velocity_change_pct": trend_data.get("velocity_change_pct", 0),
                    "confidence": trend_data.get("confidence", "medium"),
                    "key_drivers": trend_data.get("key_drivers", []),
                    # TrendAgent returns evidence as list of {finding, source} dicts
                    "evidence": trend_data.get("evidence", []),
                    "publisher_implications": trend_data.get("publisher_implications", ""),
                    "urgency": trend_data.get("urgency", "near_term"),
                    # TrendAgent uses "score_components", we support both
                    "score_breakdown": trend_data.get("score_breakdown") or trend_data.get("score_components", {}),
                    "data_sources": trend_data.get("data_sources", [])
                })

        # Find dominant trend and overall trajectory
        if trends:
            dominant = max(trends, key=lambda t: t.get("score", 0))
            accelerating_count = sum(1 for t in trends if t.get("velocity") == "accelerating")

            if accelerating_count >= 3:
                trajectory = "Multiple trends accelerating, indicating rapid change"
            elif accelerating_count >= 2:
                trajectory = "Some trends accelerating, moderate change pace"
            else:
                trajectory = "Trends relatively stable"
        else:
            dominant = {"id": "T1", "name": "Unknown"}
            trajectory = "Insufficient data"

        return {
            "trends": trends,
            "overall_trajectory": trajectory,
            "dominant_trend": dominant.get("id", "T1"),
            "emerging_signals": [t.get("key_drivers", [])[0] for t in trends if t.get("velocity") == "accelerating" and t.get("key_drivers")],
            "scenario_implications": {
                "most_likely_scenario": self._determine_likely_scenario(trends),
                "probability_shift": "Based on calculated trend scores"
            }
        }

    def _determine_likely_scenario(self, trends: List[Dict]) -> str:
        """Determine most likely 2030 scenario from trend scores."""
        t4_score = next((t.get("score", 50) for t in trends if t.get("id") == "T4"), 50)
        t5_score = next((t.get("score", 50) for t in trends if t.get("id") == "T5"), 50)

        regulation_strength = t4_score / 100
        consolidation_strength = t5_score / 100

        if regulation_strength > 0.6 and consolidation_strength < 0.5:
            return "trusted_ecosystem"
        elif regulation_strength > 0.6 and consolidation_strength > 0.5:
            return "fragmented_compliance"
        elif regulation_strength < 0.5 and consolidation_strength > 0.6:
            return "behemoth_control"
        else:
            return "open_chaos"

    def _aggregate_pillar_trend_evidence(
        self,
        power_analysis: Optional[Dict],
        attention_analysis: Optional[Dict],
        money_analysis: Optional[Dict]
    ) -> Dict[str, Any]:
        """
        Aggregate T1-T5 evidence from pillar agents.

        Pillar agents now extract trend evidence as part of their analysis:
        - AttentionAgent: t1_evidence, t3_evidence
        - PowerAgent: t2_evidence, t4_evidence
        - MoneyAgent: t5_evidence

        Returns aggregated evidence by trend ID.
        """
        evidence = {
            "T1": {"signals": [], "evidence_count": 0, "trend_direction": "stable", "summary": ""},
            "T2": {"signals": [], "evidence_count": 0, "trend_direction": "stable", "summary": ""},
            "T3": {"signals": [], "evidence_count": 0, "trend_direction": "stable", "summary": ""},
            "T4": {"signals": [], "evidence_count": 0, "trend_direction": "stable", "summary": ""},
            "T5": {"signals": [], "evidence_count": 0, "trend_direction": "stable", "summary": ""}
        }

        # Extract T1 and T3 evidence from AttentionAgent
        if attention_analysis:
            t1 = attention_analysis.get("t1_evidence", {})
            if t1:
                evidence["T1"] = {
                    "signals": t1.get("signals", []),
                    "evidence_count": t1.get("evidence_count", 0),
                    "trend_direction": t1.get("trend_direction", "stable"),
                    "summary": t1.get("summary", ""),
                    "source_pillar": "attention"
                }

            t3 = attention_analysis.get("t3_evidence", {})
            if t3:
                evidence["T3"] = {
                    "signals": t3.get("signals", []),
                    "evidence_count": t3.get("evidence_count", 0),
                    "trend_direction": t3.get("trend_direction", "stable"),
                    "zero_click_evidence": t3.get("zero_click_evidence", []),
                    "summary": t3.get("summary", ""),
                    "source_pillar": "attention"
                }

        # Extract T2 and T4 evidence from PowerAgent
        if power_analysis:
            t2 = power_analysis.get("t2_evidence", {})
            if t2:
                evidence["T2"] = {
                    "signals": t2.get("signals", []),
                    "evidence_count": t2.get("evidence_count", 0),
                    "trend_direction": t2.get("trend_direction", "stable"),
                    "automation_examples": t2.get("automation_examples", []),
                    "summary": t2.get("summary", ""),
                    "source_pillar": "power"
                }

            t4 = power_analysis.get("t4_evidence", {})
            if t4:
                evidence["T4"] = {
                    "signals": t4.get("signals", []),
                    "evidence_count": t4.get("evidence_count", 0),
                    "trend_direction": t4.get("trend_direction", "stable"),
                    "regulatory_events": t4.get("regulatory_events", []),
                    "licensing_deals": t4.get("licensing_deals", []),
                    "summary": t4.get("summary", ""),
                    "source_pillar": "power"
                }

        # Extract T5 evidence from MoneyAgent
        if money_analysis:
            t5 = money_analysis.get("t5_evidence", {})
            if t5:
                evidence["T5"] = {
                    "signals": t5.get("signals", []),
                    "evidence_count": t5.get("evidence_count", 0),
                    "trend_direction": t5.get("trend_direction", "stable"),
                    "key_acquirers": t5.get("key_acquirers", []),
                    "deal_evidence": t5.get("deal_evidence", []),
                    "summary": t5.get("summary", ""),
                    "source_pillar": "money"
                }

        return evidence

    def _enhance_trends_with_pillar_evidence(
        self,
        trend_analysis: Dict,
        pillar_evidence: Dict[str, Any]
    ) -> None:
        """
        Enhance trend analysis with evidence from pillar agents.

        This adds pillar-extracted evidence to each trend, providing
        additional signals beyond what TrendAgent found.
        """
        trends = trend_analysis.get("trends", [])

        for trend in trends:
            trend_id = trend.get("id", "")
            if trend_id in pillar_evidence:
                pe = pillar_evidence[trend_id]

                # Add pillar evidence to trend
                trend["pillar_evidence"] = {
                    "signals": pe.get("signals", []),
                    "evidence_count": pe.get("evidence_count", 0),
                    "trend_direction": pe.get("trend_direction", "stable"),
                    "summary": pe.get("summary", ""),
                    "source_pillar": pe.get("source_pillar", "")
                }

                # Add trend-specific evidence
                if trend_id == "T3" and pe.get("zero_click_evidence"):
                    trend["pillar_evidence"]["zero_click_evidence"] = pe["zero_click_evidence"]
                if trend_id == "T2" and pe.get("automation_examples"):
                    trend["pillar_evidence"]["automation_examples"] = pe["automation_examples"]
                if trend_id == "T4":
                    if pe.get("regulatory_events"):
                        trend["pillar_evidence"]["regulatory_events"] = pe["regulatory_events"]
                    if pe.get("licensing_deals"):
                        trend["pillar_evidence"]["licensing_deals"] = pe["licensing_deals"]
                if trend_id == "T5":
                    if pe.get("key_acquirers"):
                        trend["pillar_evidence"]["key_acquirers"] = pe["key_acquirers"]
                    if pe.get("deal_evidence"):
                        trend["pillar_evidence"]["deal_evidence"] = pe["deal_evidence"]

                # Merge key_drivers if pillar has signals
                pillar_signals = pe.get("signals", [])
                if pillar_signals:
                    existing_drivers = trend.get("key_drivers", [])
                    new_drivers = [s.get("finding", "") for s in pillar_signals[:3] if s.get("finding")]
                    # Add unique drivers
                    for driver in new_drivers:
                        if driver and driver not in existing_drivers:
                            existing_drivers.append(driver)
                    trend["key_drivers"] = existing_drivers[:5]  # Cap at 5

                # Merge evidence if pillar has more
                pillar_summary = pe.get("summary", "")
                if pillar_summary and not trend.get("evidence"):
                    trend["evidence"] = [{"finding": pillar_summary, "source": f"{pe.get('source_pillar', 'pillar')} agent"}]

    async def _generate_executive_summary_v2(
        self,
        power_analysis: Optional[Dict],
        attention_analysis: Optional[Dict],
        money_analysis: Optional[Dict],
        trend_analysis: Dict,
        scores: Dict,
        overrides: Dict,
        historical_context: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Generate executive summary using synthesis agent prompt."""
        # Load synthesis prompt from file
        prompt_file = AGENTS_PATH / "pam_synthesis_agent.md"
        synthesis_model = self.config.get("agents", {}).get("synthesis", {}).get("model", "gpt-5.4")
        synthesis_temp = self.config.get("agents", {}).get("synthesis", {}).get("temperature", 0.4)

        # Build context
        context = {
            "power_score": scores.get("power_score", 50),
            "attention_score": scores.get("attention_score", 50),
            "money_score": scores.get("money_score", 50),
            "overall_score": scores.get("overall_score", 50),
            "threat_level": scores.get("threat_level", "moderate"),
            "power_summary": power_analysis.get("summary") if power_analysis else "N/A",
            "attention_summary": attention_analysis.get("summary") if attention_analysis else "N/A",
            "money_summary": money_analysis.get("summary") if money_analysis else "N/A",
            "trend_summary": trend_analysis.get("overall_trajectory", ""),
            "data_sources": scores.get("data_sources", {})
        }

        historical_text = ""
        if historical_context:
            historical_text = self._format_historical_context(historical_context)

        prompt = f"""Generate an executive summary for this PAM (Power, Attention, Money) analysis.

{historical_text}

ANALYSIS SCORES AND CONTEXT:
{json.dumps(context, indent=2)}

DATA SOURCES USED:
{json.dumps(scores.get('data_sources', {}), indent=2)}

Create a concise executive briefing with:
1. Headline assessment (one sentence)
2. Key takeaway for each dimension (power, attention, money)
3. Most critical trend
4. Top 3 strategic priorities
5. Threat level assessment
6. Note which insights are based on measured data vs LLM analysis

Provide as JSON:
{{
    "headline": "one sentence assessment",
    "threat_level": "low|moderate|elevated|high|critical",
    "power_takeaway": "key point with data source indicator",
    "attention_takeaway": "key point with data source indicator",
    "money_takeaway": "key point with data source indicator",
    "critical_trend": {{
        "id": "T1-T5",
        "name": "trend name",
        "urgency": "description"
    }},
    "strategic_priorities": [
        {{"priority": "description", "urgency": "high|medium|low"}}
    ],
    "key_events": ["event1", "event2", "event3"],
    "emerging_signals": ["signal1", "signal2"],
    "data_quality_note": "Brief note on data sources used"
}}

Return ONLY valid JSON."""

        try:
            response = await run_in_threadpool(
                litellm.completion,
                model=synthesis_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=synthesis_temp
            )

            content = response.choices[0].message.content
            content = self._extract_json(content)
            return json.loads(content)

        except Exception as e:
            logger.error(f"Executive summary v2 generation failed: {e}")
            return {
                "headline": "Analysis completed - see detailed sections",
                "threat_level": scores.get("threat_level", "moderate"),
                "power_takeaway": power_analysis.get("summary") if power_analysis else "N/A",
                "attention_takeaway": attention_analysis.get("summary") if attention_analysis else "N/A",
                "money_takeaway": money_analysis.get("summary") if money_analysis else "N/A"
            }

    # =========================================================================
    # Configuration and Prompt Management (for API endpoints)
    # =========================================================================

    def get_config(self) -> Dict[str, Any]:
        """Get current PAM configuration."""
        return self.config

    async def update_config(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update PAM configuration and save to file."""
        # Deep merge updates
        def deep_merge(base: dict, updates: dict) -> dict:
            result = base.copy()
            for key, value in updates.items():
                if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                    result[key] = deep_merge(result[key], value)
                else:
                    result[key] = value
            return result

        self.config = deep_merge(self.config, updates)

        # Save to file
        try:
            with open(CONFIG_PATH, 'w') as f:
                json.dump(self.config, f, indent=4)
            logger.info("PAM config updated and saved")
        except Exception as e:
            logger.error(f"Failed to save PAM config: {e}")

        return self.config

    def list_agent_prompts(self) -> List[Dict[str, Any]]:
        """List available PAM agent prompts."""
        prompts = []
        if not AGENTS_PATH.exists():
            return prompts

        for file in AGENTS_PATH.glob("pam_*.md"):
            try:
                content = file.read_text()
                # Parse YAML frontmatter
                if content.startswith("---"):
                    end = content.find("---", 3)
                    if end > 0:
                        import yaml
                        frontmatter = yaml.safe_load(content[3:end])
                        prompts.append({
                            "filename": file.name,
                            "name": frontmatter.get("name", file.stem),
                            "category": frontmatter.get("category", "pam"),
                            "version": frontmatter.get("version", "1.0.0"),
                            "description": frontmatter.get("description", ""),
                            "model_config": frontmatter.get("model_config", {})
                        })
            except Exception as e:
                logger.warning(f"Failed to parse prompt {file.name}: {e}")

        return prompts

    async def get_agent_prompt(self, prompt_name: str) -> Optional[Dict[str, Any]]:
        """Get a specific agent prompt with its content."""
        prompt_file = AGENTS_PATH / prompt_name
        if not prompt_file.suffix:
            prompt_file = AGENTS_PATH / f"{prompt_name}.md"

        if not prompt_file.exists():
            return None

        try:
            content = prompt_file.read_text()
            result = {"filename": prompt_file.name, "content": content}

            # Parse YAML frontmatter
            if content.startswith("---"):
                end = content.find("---", 3)
                if end > 0:
                    import yaml
                    frontmatter = yaml.safe_load(content[3:end])
                    result["metadata"] = frontmatter
                    result["prompt_body"] = content[end+3:].strip()

            return result
        except Exception as e:
            logger.error(f"Failed to read prompt {prompt_name}: {e}")
            return None

    async def update_agent_prompt(self, prompt_name: str, content: str) -> bool:
        """Update an agent prompt file."""
        prompt_file = AGENTS_PATH / prompt_name
        if not prompt_file.suffix:
            prompt_file = AGENTS_PATH / f"{prompt_name}.md"

        try:
            prompt_file.write_text(content)
            logger.info(f"Updated agent prompt: {prompt_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to update prompt {prompt_name}: {e}")
            return False

    async def get_pillar_queries_all(self) -> Dict[str, Any]:
        """Get all cached pillar queries."""
        try:
            db = get_database_instance()
            result = db.fetch_all(
                """SELECT pillar, queries, model_used, version, is_active, created_at
                   FROM pam_pillar_queries
                   WHERE is_active = TRUE
                   ORDER BY pillar""",
                ()
            )
            return {
                "queries": [dict(r) for r in result] if result else []
            }
        except Exception as e:
            logger.error(f"Failed to get pillar queries: {e}")
            return {"queries": [], "error": str(e)}

    async def get_pillar_queries(self, pillar: str) -> Optional[Dict[str, Any]]:
        """Get cached queries for a specific pillar."""
        try:
            db = get_database_instance()
            result = db.fetch_one(
                """SELECT pillar, queries, model_used, version, created_at
                   FROM pam_pillar_queries
                   WHERE pillar = ? AND is_active = TRUE
                   ORDER BY version DESC LIMIT 1""",
                (pillar,)
            )
            return dict(result) if result else None
        except Exception as e:
            logger.error(f"Failed to get queries for {pillar}: {e}")
            return None

    async def update_pillar_queries(self, pillar: str, queries: List[str]) -> bool:
        """Update queries for a specific pillar."""
        await self._save_pillar_queries(pillar, queries, self.model)
        return True

    async def delete_pillar_queries(self, pillar: str) -> bool:
        """Delete cached queries for a pillar (will regenerate on next run)."""
        try:
            db = get_database_instance()
            db.execute_query(
                "UPDATE pam_pillar_queries SET is_active = FALSE WHERE pillar = ?",
                (pillar,)
            )
            logger.info(f"Deleted cached queries for {pillar}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete queries for {pillar}: {e}")
            return False

    async def regenerate_pillar_queries(self, pillar: str, model: str = None) -> List[str]:
        """Force regenerate queries for a pillar."""
        return await self._generate_pillar_queries(pillar, model or self.model, force_regenerate=True)

    async def _collect_pam_articles(
        self,
        topic: Optional[str],
        days_back: int,
        limit: int,
        trend_focus: List[str] = None
    ) -> List[Dict]:
        """
        Collect articles related to PAM themes using trend-specific semantic queries.

        This method performs cross-topic semantic search using queries derived from
        the 5 key trends reshaping scholarly publishing by 2030:
        - T1: Invisible LLM ecosystems & loss of brand visibility
        - T2: Agentic AI reshaping research workflows
        - T3: Decline of SEO and rise of GEO
        - T4: Regulatory & provenance pressures
        - T5: Market consolidation around compute + data giants

        Args:
            topic: Optional topic filter (empty string = search ALL topics)
            days_back: Number of days to look back
            limit: Maximum number of articles to return
            trend_focus: List of trend IDs to focus on (e.g., ['T1', 'T2', 'T3'])

        Returns:
            List of relevant articles across all topics
        """
        all_articles = []
        seen_uris = set()
        trend_focus = trend_focus or list(TREND_DEFINITIONS.keys())

        logger.info(f"PAM: Collecting articles across {'all topics' if not topic else topic} for trends {trend_focus}")

        # Calculate date range
        from datetime import datetime, timedelta
        cutoff_date = datetime.now() - timedelta(days=days_back)
        start_date = cutoff_date.strftime('%Y-%m-%d')
        end_date = datetime.now().strftime('%Y-%m-%d')

        # Strategy 1: Trend-specific semantic searches
        # Each trend has specific keywords that we use to find relevant articles
        articles_per_trend = max(10, limit // len(trend_focus))

        for trend_id in trend_focus:
            if trend_id not in TREND_DEFINITIONS:
                continue

            trend = TREND_DEFINITIONS[trend_id]
            trend_keywords = trend["keywords"]

            # Build semantic query from trend keywords
            # Use top keywords for focused search
            semantic_query = " ".join(trend_keywords[:5])

            try:
                logger.info(f"PAM: Searching for trend {trend_id} ({trend['short_name']})")

                # No topic filter = search across ALL topics
                metadata_filter = None
                if topic:
                    metadata_filter = {"topic": topic}

                results = await run_in_threadpool(
                    vector_search_articles,
                    query=semantic_query,
                    top_k=articles_per_trend,
                    metadata_filter=metadata_filter
                )

                if results:
                    for r in results:
                        if isinstance(r, dict):
                            # Handle both metadata wrapper and direct article dict
                            article = r.get("metadata", r)
                            uri = article.get("uri")
                            if uri and uri not in seen_uris:
                                # Tag article with the trend that matched it
                                article["_matched_trend"] = trend_id
                                article["_trend_name"] = trend["name"]
                                all_articles.append(article)
                                seen_uris.add(uri)

            except Exception as e:
                logger.warning(f"Vector search failed for trend {trend_id}: {e}")

        # Strategy 2: Broader PAM-themed database search
        # Get recent articles across all topics that might be relevant
        pam_themed_queries = [
            "AI publishing scholarly research",
            "LLM content licensing copyright",
            "tech consolidation academic publishers",
            "AI regulation content provenance",
            "research workflow automation AI"
        ]

        for query in pam_themed_queries[:3]:  # Limit to avoid too many searches
            try:
                results = await run_in_threadpool(
                    vector_search_articles,
                    query=query,
                    top_k=10,
                    metadata_filter=None  # Cross-topic search
                )

                if results:
                    for r in results:
                        if isinstance(r, dict):
                            article = r.get("metadata", r)
                            uri = article.get("uri")
                            if uri and uri not in seen_uris:
                                article["_matched_trend"] = "general"
                                all_articles.append(article)
                                seen_uris.add(uri)

            except Exception as e:
                logger.warning(f"Broad PAM search failed: {e}")

        # Strategy 3: Recent articles from database (cross-topic)
        try:
            # Use cross-topic mode (topic_name=None) to get articles from all topics
            db_articles = await run_in_threadpool(
                self.db.get_recent_articles_by_topic,
                topic_name=topic if topic else None,  # None = all topics
                limit=limit // 2,
                start_date=start_date,
                end_date=end_date
            )

            if db_articles:
                for article in db_articles:
                    uri = article.get("uri")
                    if uri and uri not in seen_uris:
                        article["_matched_trend"] = "database"
                        all_articles.append(dict(article) if hasattr(article, 'keys') else article)
                        seen_uris.add(uri)

        except Exception as e:
            logger.warning(f"Database article fetch failed: {e}")

        logger.info(f"PAM: Collected {len(all_articles)} unique articles across all strategies")

        # Sort by relevance (trend-matched articles first, then by date)
        def sort_key(a):
            # Prioritize trend-matched over database-only
            trend_priority = 0 if a.get("_matched_trend") in trend_focus else 1
            # Then by date (newest first)
            date_str = a.get("publication_date") or a.get("submission_date") or ""
            return (trend_priority, -len(date_str), date_str)

        all_articles.sort(key=sort_key, reverse=True)

        return all_articles[:limit]

    async def _analyze_power(
        self,
        articles: List[Dict],
        topic: Optional[str],
        model: str
    ) -> Dict[str, Any]:
        """Analyze power dynamics in the knowledge economy."""
        if not articles:
            return self._empty_power_analysis()

        articles_text = self._format_articles_for_prompt(articles[:30])
        citation_instructions = self._get_citation_instructions()

        prompt = f"""Analyze POWER DYNAMICS in the knowledge economy based on these articles.

TOPIC: {topic or 'Scholarly Publishing'}

NUMBERED ARTICLE LIST (Use these numbers for citations):
{articles_text}

{citation_instructions}

Analyze the following power dimensions:

1. INFRASTRUCTURE CONTROL
- Who controls key technical infrastructure?
- API dependencies and data pipeline ownership
- Platform dominance indicators

2. REGULATORY INFLUENCE
- Policy developments affecting the sector
- Standards and governance initiatives
- Lobbying and advocacy activities

3. RESEARCH NETWORK CENTRALITY
- Key institutions and their influence
- Collaboration patterns
- Cross-sector partnerships

4. IP POSITIONING
- Patent and licensing developments
- Content rights negotiations
- Defensive publication strategies

Provide your analysis as JSON. IMPORTANT: Include [N] citations in all description fields:
{{
    "power_score": 0-100,
    "infrastructure_control": {{
        "score": 0-100,
        "key_players": ["name1", "name2"],
        "developments": ["Development description with citation [1]", "Another finding [2][3]"],
        "concentration_level": "low|medium|high"
    }},
    "regulatory_influence": {{
        "score": 0-100,
        "active_regulations": ["Regulation with citation [1]", "Another regulation [4]"],
        "key_developments": ["Development with citation [2]"],
        "direction": "increasing|stable|decreasing"
    }},
    "network_centrality": {{
        "score": 0-100,
        "influential_entities": ["entity1", "entity2"],
        "collaboration_trends": "Description of collaboration trends with citations [1][5]"
    }},
    "ip_positioning": {{
        "score": 0-100,
        "key_deals": ["Deal description with citation [3]"],
        "trends": "Description of IP trends with citations [2][4]"
    }},
    "key_events": [
        {{"event": "Event description with citation [1]", "impact": "high|medium|low", "citations": [1]}}
    ],
    "power_concentration_trend": "increasing|stable|decreasing",
    "summary": "2-3 sentence summary with citations [1][2][3] supporting key claims"
}}

Return ONLY valid JSON."""

        try:
            response = await run_in_threadpool(
                litellm.completion,
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )

            content = response.choices[0].message.content
            # Extract JSON from response
            content = self._extract_json(content)
            return json.loads(content)

        except Exception as e:
            logger.error(f"Power analysis failed: {e}")
            return self._empty_power_analysis()

    async def _analyze_attention(
        self,
        articles: List[Dict],
        topic: Optional[str],
        model: str
    ) -> Dict[str, Any]:
        """Analyze attention economy metrics."""
        if not articles:
            return self._empty_attention_analysis()

        articles_text = self._format_articles_for_prompt(articles[:30])
        citation_instructions = self._get_citation_instructions()

        prompt = f"""Analyze ATTENTION ECONOMY dynamics based on these articles.

TOPIC: {topic or 'Scholarly Publishing'}

NUMBERED ARTICLE LIST (Use these numbers for citations):
{articles_text}

{citation_instructions}

Analyze the following attention dimensions:

1. ACADEMIC VISIBILITY
- Citation patterns and velocity
- Research impact indicators
- Altmetric attention

2. AI ENGINE VISIBILITY
- LLM training data inclusion signals
- Metadata completeness indicators
- Structured data availability
- Provenance signal strength

3. BRAND VISIBILITY
- Direct traffic indicators
- Referral source patterns
- Social media presence

4. CONTENT SYNTHESIS EXPOSURE
- How content appears in AI summaries
- Attribution preservation
- Zero-click answer rate

Provide your analysis as JSON. IMPORTANT: Include [N] citations in all description fields:
{{
    "attention_score": 0-100,
    "academic_visibility": {{
        "score": 0-100,
        "citation_trends": "Description of citation trends with citations [1][2]",
        "key_indicators": ["Indicator with citation [1]", "Another indicator [3]"]
    }},
    "ai_visibility": {{
        "score": 0-100,
        "training_data_exposure": "low|medium|high",
        "metadata_readiness": 0-100,
        "provenance_strength": 0-100
    }},
    "brand_visibility": {{
        "score": 0-100,
        "traffic_trends": "Description of traffic trends with citations [2][4]",
        "key_channels": ["Channel with citation [1]"]
    }},
    "synthesis_exposure": {{
        "score": 0-100,
        "attribution_rate": 0-100,
        "zero_click_risk": "low|medium|high"
    }},
    "geo_readiness": {{
        "structured_metadata": 0-100,
        "machine_readable_rights": 0-100,
        "provenance_tagging": 0-100,
        "api_accessibility": 0-100,
        "ai_training_licensing": 0-100
    }},
    "attention_shift_direction": "toward_ai|toward_direct|balanced",
    "key_events": [
        {{"event": "Event description with citation [1]", "impact": "high|medium|low", "citations": [1]}}
    ],
    "summary": "2-3 sentence summary with citations [1][2][3] supporting key claims"
}}

Return ONLY valid JSON."""

        try:
            response = await run_in_threadpool(
                litellm.completion,
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )

            content = response.choices[0].message.content
            content = self._extract_json(content)
            return json.loads(content)

        except Exception as e:
            logger.error(f"Attention analysis failed: {e}")
            return self._empty_attention_analysis()

    async def _analyze_money(
        self,
        articles: List[Dict],
        topic: Optional[str],
        model: str
    ) -> Dict[str, Any]:
        """Analyze money flows and market dynamics."""
        if not articles:
            return self._empty_money_analysis()

        articles_text = self._format_articles_for_prompt(articles[:30])
        citation_instructions = self._get_citation_instructions()

        prompt = f"""Analyze MONEY FLOWS in the knowledge economy based on these articles.

TOPIC: {topic or 'Scholarly Publishing'}

NUMBERED ARTICLE LIST (Use these numbers for citations):
{articles_text}

{citation_instructions}

Analyze the following money dimensions:

1. FUNDING FLOWS
- Venture capital and investment trends
- Government grant patterns
- Corporate R&D allocation

2. REVENUE CONCENTRATION
- Market share by publisher
- Subscription vs OA revenue trends
- Licensing deal values

3. M&A ACTIVITY
- Recent acquisitions and mergers
- Vertical integration deals
- Content asset valuations

4. COST DYNAMICS
- Compute and infrastructure costs
- Publishing cost trends
- AI investment requirements

Provide your analysis as JSON. IMPORTANT: Include [N] citations in all description fields:
{{
    "money_score": 0-100,
    "funding_flows": {{
        "total_estimated_usd": "string estimate",
        "vc_activity": "increasing|stable|decreasing",
        "government_funding": "increasing|stable|decreasing",
        "key_deals": [
            {{"deal": "Deal description with citation [1]", "value": "amount", "parties": ["party1", "party2"], "citations": [1]}}
        ]
    }},
    "revenue_concentration": {{
        "concentration_level": "low|medium|high",
        "top_players_share": 0-100,
        "trend": "concentrating|stable|dispersing",
        "key_metrics": ["Metric with citation [2]"]
    }},
    "ma_activity": {{
        "activity_level": "low|medium|high",
        "recent_deals": [
            {{"acquirer": "name", "target": "name", "value": "amount", "type": "acquisition|merger|partnership", "citations": [3]}}
        ],
        "consolidation_trend": "accelerating|stable|slowing"
    }},
    "cost_dynamics": {{
        "compute_cost_trend": "increasing|stable|decreasing",
        "publishing_costs": "increasing|stable|decreasing",
        "key_factors": ["Factor with citation [4]"]
    }},
    "licensing_trends": {{
        "ai_training_rights_value": "estimate",
        "growth_rate": "percentage",
        "key_deals": ["Deal description with citation [5]"]
    }},
    "key_events": [
        {{"event": "Event description with citation [1]", "value": "amount if applicable", "impact": "high|medium|low", "citations": [1]}}
    ],
    "summary": "2-3 sentence summary with citations [1][2][3] supporting key claims"
}}

Return ONLY valid JSON."""

        try:
            response = await run_in_threadpool(
                litellm.completion,
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )

            content = response.choices[0].message.content
            content = self._extract_json(content)
            return json.loads(content)

        except Exception as e:
            logger.error(f"Money analysis failed: {e}")
            return self._empty_money_analysis()

    async def _analyze_trends(
        self,
        articles: List[Dict],
        trend_focus: List[str],
        model: str
    ) -> Dict[str, Any]:
        """Analyze status of 2030 trends."""
        if not articles:
            return self._empty_trend_analysis(trend_focus)

        articles_text = self._format_articles_for_prompt(articles[:40])
        citation_instructions = self._get_citation_instructions()

        # Build trend descriptions for prompt
        trend_descriptions = []
        for tid in trend_focus:
            if tid in TREND_DEFINITIONS:
                t = TREND_DEFINITIONS[tid]
                trend_descriptions.append(
                    f"{tid}: {t['name']} - {t['description']}"
                )

        prompt = f"""Analyze the status of these 2030 TRENDS based on the articles.

TRENDS TO ANALYZE:
{chr(10).join(trend_descriptions)}

NUMBERED ARTICLE LIST (Use these numbers for citations):
{articles_text}

{citation_instructions}

For each trend, assess:
1. Current strength (0-100%)
2. Velocity (accelerating/stable/decelerating)
3. Key drivers from the articles
4. Publisher implications

Provide your analysis as JSON. IMPORTANT: Include [N] citations in all description fields:
{{
    "trends": [
        {{
            "id": "T1",
            "name": "Invisible LLM Ecosystems",
            "score": 0-100,
            "velocity": "accelerating|stable|decelerating",
            "confidence": "high|medium|low",
            "key_drivers": ["Driver with citation [1]", "Another driver [2]"],
            "evidence": [
                {{"finding": "Finding description with citation [1]", "citations": [1]}}
            ],
            "publisher_implications": "Description of implications with citations [1][3]",
            "urgency": "immediate|near_term|medium_term"
        }}
    ],
    "overall_trajectory": "Description of overall direction with citations [1][2]",
    "dominant_trend": "T1|T2|T3|T4|T5",
    "emerging_signals": ["Signal with citation [3]", "Another signal [4]"],
    "scenario_implications": {{
        "most_likely_scenario": "trusted_ecosystem|fragmented_compliance|open_chaos|behemoth_control",
        "probability_shift": "Description of changes with citations [2][5]"
    }}
}}

Return ONLY valid JSON."""

        try:
            response = await run_in_threadpool(
                litellm.completion,
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )

            content = response.choices[0].message.content
            content = self._extract_json(content)
            return json.loads(content)

        except Exception as e:
            logger.error(f"Trend analysis failed: {e}")
            return self._empty_trend_analysis(trend_focus)

    async def _generate_executive_summary(
        self,
        power_analysis: Optional[Dict],
        attention_analysis: Optional[Dict],
        money_analysis: Optional[Dict],
        trend_analysis: Dict,
        scores: Dict,
        model: str,
        historical_context: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Generate executive summary of PAM analysis with historical context."""
        context = {
            "power": power_analysis.get("summary") if power_analysis else None,
            "attention": attention_analysis.get("summary") if attention_analysis else None,
            "money": money_analysis.get("summary") if money_analysis else None,
            "trends": trend_analysis.get("overall_trajectory"),
            "scores": scores
        }

        # Format historical context for the prompt
        historical_text = ""
        if historical_context:
            historical_text = self._format_historical_context(historical_context)

        prompt = f"""Generate an executive summary for this PAM (Power, Attention, Money) analysis.

{historical_text}

ANALYSIS CONTEXT:
{json.dumps(context, indent=2)}

Create a concise executive briefing with:
1. Headline assessment (one sentence)
2. Key takeaway for each dimension (power, attention, money)
3. Most critical trend
4. Top 3 strategic priorities
5. Threat level assessment

Provide as JSON:
{{
    "headline": "one sentence assessment",
    "threat_level": "low|moderate|elevated|high|critical",
    "power_takeaway": "key point",
    "attention_takeaway": "key point",
    "money_takeaway": "key point",
    "critical_trend": {{
        "id": "T1-T5",
        "name": "trend name",
        "urgency": "description"
    }},
    "strategic_priorities": [
        {{"priority": "description", "urgency": "high|medium|low"}}
    ],
    "key_events": ["event1", "event2", "event3"],
    "emerging_signals": ["signal1", "signal2"]
}}

Return ONLY valid JSON."""

        try:
            response = await run_in_threadpool(
                litellm.completion,
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )

            content = response.choices[0].message.content
            content = self._extract_json(content)
            return json.loads(content)

        except Exception as e:
            logger.error(f"Executive summary generation failed: {e}")
            return {
                "headline": "Analysis completed - see detailed sections",
                "threat_level": scores.get("threat_level", "moderate"),
                "power_takeaway": power_analysis.get("summary") if power_analysis else "N/A",
                "attention_takeaway": attention_analysis.get("summary") if attention_analysis else "N/A",
                "money_takeaway": money_analysis.get("summary") if money_analysis else "N/A"
            }

    async def _generate_recommendations(
        self,
        power_analysis: Optional[Dict],
        attention_analysis: Optional[Dict],
        money_analysis: Optional[Dict],
        trend_analysis: Dict,
        entity_type: str,
        model: str
    ) -> List[Dict]:
        """Generate strategic recommendations based on PAM analysis."""
        context = {
            "entity_type": entity_type,
            "power_summary": power_analysis.get("summary") if power_analysis else None,
            "attention_summary": attention_analysis.get("summary") if attention_analysis else None,
            "money_summary": money_analysis.get("summary") if money_analysis else None,
            "trends": trend_analysis.get("trends", []),
            "scenario": trend_analysis.get("scenario_implications", {})
        }

        prompt = f"""Generate strategic recommendations for a {entity_type} based on this PAM analysis.

ANALYSIS CONTEXT:
{json.dumps(context, indent=2)}

Provide 5-7 prioritized strategic recommendations that address:
1. Power positioning improvements
2. Attention capture strategies
3. Money flow optimization
4. Trend response actions
5. Scenario preparation

Format as JSON:
{{
    "recommendations": [
        {{
            "title": "short title",
            "description": "detailed recommendation",
            "dimension": "power|attention|money",
            "addresses_trends": ["T1", "T2"],
            "urgency": "immediate|near_term|medium_term",
            "effort": "low|medium|high",
            "impact": "low|medium|high",
            "rationale": "why this matters"
        }}
    ]
}}

Return ONLY valid JSON."""

        try:
            response = await run_in_threadpool(
                litellm.completion,
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4
            )

            content = response.choices[0].message.content
            content = self._extract_json(content)
            result = json.loads(content)
            return result.get("recommendations", [])

        except Exception as e:
            logger.error(f"Recommendations generation failed: {e}")
            return []

    def _calculate_scores(
        self,
        power_analysis: Optional[Dict],
        attention_analysis: Optional[Dict],
        money_analysis: Optional[Dict]
    ) -> Dict[str, Any]:
        """Calculate composite PAM scores."""
        power_score = power_analysis.get("power_score", 50) if power_analysis else 50
        attention_score = attention_analysis.get("attention_score", 50) if attention_analysis else 50
        money_score = money_analysis.get("money_score", 50) if money_analysis else 50

        # Calculate overall score (weighted average)
        overall = (power_score * 0.35 + attention_score * 0.35 + money_score * 0.30)

        # Determine threat level based on scores
        # Higher scores = greater disruption/concentration = higher threat
        if overall >= 80:
            threat_level = "critical"
        elif overall >= 70:
            threat_level = "high"
        elif overall >= 55:
            threat_level = "elevated"
        elif overall >= 40:
            threat_level = "moderate"
        else:
            threat_level = "low"

        return {
            "power_score": power_score,
            "attention_score": attention_score,
            "money_score": money_score,
            "overall_score": round(overall, 1),
            "threat_level": threat_level
        }

    def _analyze_scenarios(self, trend_analysis: Dict) -> Dict[str, Any]:
        """Analyze 2030 scenario probabilities based on trend data."""
        # Get trend scores
        trends = trend_analysis.get("trends", [])
        t4_score = next((t.get("score", 50) for t in trends if t.get("id") == "T4"), 50)
        t5_score = next((t.get("score", 50) for t in trends if t.get("id") == "T5"), 50)

        # Normalize to 0-1 range
        regulation_strength = t4_score / 100
        consolidation_strength = t5_score / 100

        # Calculate scenario probabilities based on trend data
        # Scenarios map to regulatory vs consolidation axes
        scenario_adjustments = {
            # High regulation, low consolidation -> trusted_ecosystem
            "trusted_ecosystem": regulation_strength * (1 - consolidation_strength),
            # High regulation, high consolidation -> fragmented_compliance
            "fragmented_compliance": regulation_strength * consolidation_strength,
            # Low regulation, high consolidation -> behemoth_control
            "behemoth_control": (1 - regulation_strength) * consolidation_strength,
            # Low regulation, low consolidation -> open_chaos
            "open_chaos": (1 - regulation_strength) * (1 - consolidation_strength)
        }

        # Normalize to percentages that sum to 100
        total = sum(scenario_adjustments.values()) or 1
        normalized_probs = {k: (v / total) * 100 for k, v in scenario_adjustments.items()}

        scenarios = {}
        for scenario_id, scenario in SCENARIOS_2030.items():
            scenarios[scenario_id] = {
                "name": scenario["name"],
                "description": scenario["description"],
                "base_probability": scenario["probability"],
                "current_probability": round(normalized_probs.get(scenario_id, scenario["probability"]), 1),
                "regulation_level": scenario["regulation"],
                "concentration_level": scenario["concentration"]
            }

        # Determine most likely scenario
        most_likely = max(normalized_probs, key=normalized_probs.get)

        return {
            "scenarios": scenarios,
            "most_likely": most_likely,
            "current_trajectory": trend_analysis.get("overall_trajectory", ""),
            "key_variables": {
                "regulation_strength": round(regulation_strength * 100, 1),
                "consolidation_strength": round(consolidation_strength * 100, 1)
            }
        }

    async def _save_analysis_run(self, result: Dict, username: Optional[str]):
        """Save analysis run to database."""
        try:
            # This would insert into pam_analysis_runs table
            # For now, just log
            logger.info(f"PAM analysis completed: {result.get('run_id')}")
        except Exception as e:
            logger.error(f"Failed to save PAM analysis: {e}")

    async def _cache_report(
        self,
        result: Dict,
        topic: Optional[str],
        analysis_type: str,
        days_back: int,
        time_horizon: str,
        trend_focus: List[str],
        entity_type: str,
        model: str,
        duration: float,
        article_count: int
    ):
        """Cache the PAM report for quick retrieval."""
        try:
            from app.services.dashboard_cache_service import DashboardCacheService

            # Get the database instance for the cache service
            db_instance = get_database_instance()
            cache_service = DashboardCacheService(db_instance)
            await cache_service.save_dashboard(
                dashboard_type='pam',
                date_range=f'{days_back}d',
                content=result,
                topic=topic or 'all_topics',
                persona=analysis_type,
                metadata={
                    'article_count': article_count,
                    'model_used': model,
                    'generation_time_seconds': duration,
                    'time_horizon': time_horizon,
                    'trend_focus': trend_focus,
                    'entity_type': entity_type
                }
            )
            logger.info(f"PAM report cached: {analysis_type} for topic={topic or 'all'}")
        except Exception as e:
            logger.warning(f"Failed to cache PAM report: {e}")
            # Don't fail the overall analysis if caching fails

    def _organize_articles_by_trend(
        self,
        articles: List[Dict],
        trend_focus: List[str]
    ) -> Dict[str, List[Dict]]:
        """
        Organize articles by trend for TrendAgent.

        Matches articles to trends based on keywords in title and summary.
        An article can match multiple trends.
        """
        articles_by_trend = {tid: [] for tid in trend_focus}

        for article in articles:
            title = (article.get('title') or '').lower()
            summary = (article.get('summary') or '').lower()
            text = f"{title} {summary}"

            for tid in trend_focus:
                if tid in TREND_DEFINITIONS:
                    keywords = TREND_DEFINITIONS[tid].get('keywords', [])
                    # Check if any keyword matches
                    for keyword in keywords:
                        if keyword.lower() in text:
                            articles_by_trend[tid].append(article)
                            break

        # Log distribution
        for tid, arts in articles_by_trend.items():
            if arts:
                logger.debug(f"PAM: Trend {tid} matched {len(arts)} articles")

        return articles_by_trend

    def _format_articles_for_prompt(self, articles: List[Dict]) -> str:
        """Format articles for LLM prompt with numbered citations."""
        formatted = []
        for i, article in enumerate(articles, 1):
            title = article.get("title") or "Untitled"
            source = article.get("news_source") or article.get("source") or "Unknown"
            date = article.get("publication_date") or ""
            summary = (article.get("summary") or "")[:500]
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
CRITICAL CITATION INSTRUCTIONS:
- Use numbered citations [1], [2], [3] etc. to reference specific articles
- Include citations in descriptions, summaries, and key findings
- Example: "Major tech companies are consolidating AI infrastructure [1][3], while regulators push back [2]"
- Every key claim should have at least one citation
- Use the article numbers from the NUMBERED ARTICLE LIST above
"""

    def _extract_json(self, content: str) -> str:
        """Extract JSON from LLM response."""
        content = content.strip()

        # Try to find JSON block
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

        # Find JSON object
        if "{" in content:
            start = content.find("{")
            # Find matching closing brace
            depth = 0
            for i, char in enumerate(content[start:], start):
                if char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        content = content[start:i+1]
                        break

        return content

    def _empty_power_analysis(self) -> Dict:
        """Return empty power analysis structure."""
        return {
            "power_score": 50,
            "infrastructure_control": {"score": 50, "key_players": [], "developments": []},
            "regulatory_influence": {"score": 50, "active_regulations": []},
            "network_centrality": {"score": 50, "influential_entities": []},
            "ip_positioning": {"score": 50, "key_deals": []},
            "key_events": [],
            "summary": "Insufficient data for power analysis"
        }

    def _empty_attention_analysis(self) -> Dict:
        """Return empty attention analysis structure."""
        return {
            "attention_score": 50,
            "academic_visibility": {"score": 50},
            "ai_visibility": {"score": 50},
            "brand_visibility": {"score": 50},
            "synthesis_exposure": {"score": 50},
            "geo_readiness": {},
            "key_events": [],
            "summary": "Insufficient data for attention analysis"
        }

    def _empty_money_analysis(self) -> Dict:
        """Return empty money analysis structure."""
        return {
            "money_score": 50,
            "funding_flows": {"key_deals": []},
            "revenue_concentration": {},
            "ma_activity": {"recent_deals": []},
            "cost_dynamics": {},
            "key_events": [],
            "summary": "Insufficient data for money analysis"
        }

    def _empty_trend_analysis(self, trend_focus: List[str]) -> Dict:
        """Return empty trend analysis structure."""
        trends = []
        for tid in trend_focus:
            if tid in TREND_DEFINITIONS:
                t = TREND_DEFINITIONS[tid]
                trends.append({
                    "id": tid,
                    "name": t["name"],
                    "score": 50,
                    "velocity": "stable",
                    "confidence": "low",
                    "key_drivers": [],
                    "evidence": [],
                    "publisher_implications": "Insufficient data"
                })

        return {
            "trends": trends,
            "overall_trajectory": "Insufficient data for trajectory assessment",
            "emerging_signals": []
        }

    # Additional methods for specific analyses

    async def get_trend_status(
        self,
        trend_ids: List[str] = None,
        days_back: int = 30,
        topic: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get current status of specified trends."""
        trend_ids = trend_ids or ["T1", "T2", "T3", "T4", "T5"]

        articles = await self._collect_pam_articles(topic, days_back, 50)
        trend_analysis = await self._analyze_trends(articles, trend_ids, self.model)

        return {
            "trends": trend_analysis.get("trends", []),
            "overall_trajectory": trend_analysis.get("overall_trajectory"),
            "dominant_trend": trend_analysis.get("dominant_trend"),
            "emerging_signals": trend_analysis.get("emerging_signals", []),
            "articles_analyzed": len(articles),
            "generated_at": datetime.now().isoformat()
        }

    async def analyze_publisher_position(
        self,
        publisher_name: Optional[str] = None,
        pillar_focus: str = "all",
        topic: Optional[str] = None
    ) -> Dict[str, Any]:
        """Analyze publisher strategic positioning."""
        articles = await self._collect_pam_articles(topic, 90, 50)

        # Build pillar-specific analysis prompt
        pillars_to_analyze = (
            [pillar_focus] if pillar_focus != "all"
            else ["trust", "infrastructure", "connector"]
        )

        articles_text = self._format_articles_for_prompt(articles[:30])

        prompt = f"""Analyze publisher strategic positioning based on the THREE VALUE PILLARS.

PUBLISHER: {publisher_name or 'Industry-wide'}
PILLARS TO ANALYZE: {', '.join(pillars_to_analyze)}

PILLAR DEFINITIONS:
- TRUST: Peer review integrity, verification, AI detection, retraction transparency
- INFRASTRUCTURE: APIs, metadata, rights management, AI-ready content, provenance
- CONNECTOR: Author relationships, community, workflow integration, incentives

ARTICLES:
{articles_text}

Provide analysis as JSON:
{{
    "publisher": "{publisher_name or 'Industry'}",
    "pillar_scores": {{
        "trust": {{
            "score": 0-100,
            "components": {{
                "peer_review_integrity": 0-100,
                "retraction_transparency": 0-100,
                "data_verification": 0-100,
                "ai_content_detection": 0-100
            }},
            "strengths": ["str1"],
            "weaknesses": ["weak1"]
        }},
        "infrastructure": {{
            "score": 0-100,
            "components": {{
                "api_accessibility": 0-100,
                "metadata_quality": 0-100,
                "rights_management": 0-100,
                "ai_ready_pipelines": 0-100
            }},
            "strengths": ["str1"],
            "weaknesses": ["weak1"]
        }},
        "connector": {{
            "score": 0-100,
            "components": {{
                "author_relationships": 0-100,
                "community_engagement": 0-100,
                "workflow_integration": 0-100,
                "incentive_alignment": 0-100
            }},
            "strengths": ["str1"],
            "weaknesses": ["weak1"]
        }}
    }},
    "overall_position": "trust_provider|infrastructure_provider|connector|commodity",
    "threat_exposure": 0-100,
    "opportunity_score": 0-100,
    "strategic_recommendations": [
        {{"recommendation": "desc", "pillar": "trust|infrastructure|connector", "urgency": "high|medium|low"}}
    ],
    "summary": "2-3 sentence assessment"
}}

Return ONLY valid JSON."""

        try:
            response = await run_in_threadpool(
                litellm.completion,
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )

            content = response.choices[0].message.content
            content = self._extract_json(content)
            result = json.loads(content)
            result["articles_analyzed"] = len(articles)
            result["generated_at"] = datetime.now().isoformat()
            return result

        except Exception as e:
            logger.error(f"Publisher position analysis failed: {e}")
            return {
                "publisher": publisher_name or "Industry",
                "error": str(e),
                "pillar_scores": {}
            }

    # =========================================================================
    # NEW: Pillar-by-pillar analysis methods with query caching
    # =========================================================================

    async def _get_all_topics(self) -> List[str]:
        """Get all unique topics from the database."""
        try:
            topics_data = await run_in_threadpool(
                self.db.get_topics_with_article_counts
            )
            return list(topics_data.keys()) if topics_data else []
        except Exception as e:
            logger.warning(f"Failed to get topics: {e}")
            return []

    async def _get_cached_pillar_queries(self, pillar: str) -> Optional[List[str]]:
        """Get cached semantic queries for a pillar from database."""
        try:
            db = get_database_instance()
            result = db.fetch_one(
                """SELECT queries FROM pam_pillar_queries
                   WHERE pillar = ? AND is_active = TRUE
                   ORDER BY version DESC LIMIT 1""",
                (pillar,)
            )
            if result and result.get('queries'):
                return result['queries']
            return None
        except Exception as e:
            logger.warning(f"Failed to get cached queries for {pillar}: {e}")
            return None

    async def _save_pillar_queries(self, pillar: str, queries: List[str], model: str):
        """Save generated semantic queries to database cache."""
        try:
            db = get_database_instance()
            # Get current max version
            result = db.fetch_one(
                "SELECT COALESCE(MAX(version), 0) as max_ver FROM pam_pillar_queries WHERE pillar = ?",
                (pillar,)
            )
            new_version = (result['max_ver'] if result else 0) + 1

            # Deactivate old versions
            db.execute_query(
                "UPDATE pam_pillar_queries SET is_active = FALSE WHERE pillar = ?",
                (pillar,)
            )

            # Insert new queries
            db.execute_query(
                """INSERT INTO pam_pillar_queries (pillar, queries, model_used, version, is_active, created_at)
                   VALUES (?, CAST(? AS jsonb), ?, ?, TRUE, NOW())""",
                (pillar, json.dumps(queries), model, new_version)
            )
            logger.info(f"Saved {len(queries)} queries for pillar {pillar} (version {new_version})")
        except Exception as e:
            logger.warning(f"Failed to save queries for {pillar}: {e}")

    async def _generate_pillar_queries(
        self,
        pillar: str,
        model: str,
        force_regenerate: bool = False
    ) -> List[str]:
        """
        Generate or retrieve cached semantic search queries for a pillar.

        Args:
            pillar: 'power', 'attention', or 'money'
            model: LLM model to use for generation
            force_regenerate: If True, regenerate even if cached queries exist

        Returns:
            List of semantic search query strings
        """
        # Check cache first (unless forced to regenerate)
        if not force_regenerate:
            cached = await self._get_cached_pillar_queries(pillar)
            if cached:
                logger.info(f"Using {len(cached)} cached queries for pillar {pillar}")
                return cached

        # Generate new queries using LLM
        pillar_contexts = {
            'power': """POWER dimension analyzes:
- Infrastructure control: Who owns technical platforms, APIs, data pipelines
- Regulatory influence: Policy developments, standards, governance initiatives
- Network centrality: Key institutions, collaboration patterns, influence networks
- IP positioning: Patents, licensing, content rights, defensive publications""",

            'attention': """ATTENTION dimension analyzes:
- Academic visibility: Citation patterns, research impact, altmetrics
- AI engine visibility: LLM training data inclusion, metadata quality, structured data
- Brand visibility: Direct traffic, referral patterns, social presence
- Content synthesis exposure: AI summaries, attribution preservation, zero-click answers
- GEO readiness: Generative Engine Optimization preparedness""",

            'money': """MONEY dimension analyzes:
- Funding flows: VC investment, government grants, corporate R&D
- Revenue concentration: Market share, subscription vs OA trends, licensing values
- M&A activity: Acquisitions, mergers, vertical integration, content valuations
- Cost dynamics: Compute costs, publishing costs, AI investment requirements
- Licensing trends: AI training rights, content deals, growth rates

IMPORTANT: Include queries specifically designed to find:
- Recent M&A announcements (e.g., "company acquired publisher", "merger deal announced")
- Funding rounds (e.g., "raises million funding", "series A investment")
- Major financial deals and partnerships"""
        }

        prompt = f"""Generate 8-10 semantic search queries for analyzing the {pillar.upper()} dimension
in the knowledge economy and scholarly publishing ecosystem.

{pillar_contexts.get(pillar, '')}

The queries should find articles about:
- Current developments and trends in this dimension
- Key players and their strategies
- Impact on publishers and research institutions
- AI and technology implications

Return ONLY a valid JSON array of query strings. Each query should be 3-6 words.
Example format: ["AI infrastructure dominance publishing", "regulatory AI content licensing", ...]

JSON array:"""

        try:
            response = await run_in_threadpool(
                litellm.completion,
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4
            )

            content = response.choices[0].message.content.strip()

            # Extract JSON array
            if '[' in content:
                start = content.find('[')
                end = content.rfind(']') + 1
                json_str = content[start:end]
                queries = json.loads(json_str)

                if isinstance(queries, list) and len(queries) > 0:
                    # Save to cache
                    await self._save_pillar_queries(pillar, queries, model)
                    logger.info(f"Generated and cached {len(queries)} queries for pillar {pillar}")
                    return queries

        except Exception as e:
            logger.error(f"Failed to generate queries for {pillar}: {e}")

        # Fallback to default queries based on trend keywords
        fallback_queries = self._get_fallback_pillar_queries(pillar)
        logger.warning(f"Using {len(fallback_queries)} fallback queries for pillar {pillar}")
        return fallback_queries

    def _get_fallback_pillar_queries(self, pillar: str) -> List[str]:
        """Get fallback queries from trend definitions when LLM fails."""
        # Explicit high-value queries for each pillar
        pillar_explicit_queries = {
            'power': [
                "AI infrastructure control platform",
                "regulatory AI publishing policy",
                "research collaboration network partnerships",
                "patent IP licensing content rights",
                "data pipeline ownership standards",
                "AI governance scholarly publishing",
                # T4-specific regulatory queries
                "EU AI Act compliance publishers",
                "copyright lawsuit AI training data",
                "content licensing deal news publisher",
                "C2PA content credentials watermarking",
                "AI regulation content provenance",
                "robots.txt opt-out AI crawling",
            ],
            'attention': [
                "AI visibility LLM training data",
                "citation impact altmetrics research",
                "brand visibility traffic decline",
                "SEO decline generative engine optimization",
                "AI summary attribution zero-click",
                "metadata structured data discoverability",
            ],
            'money': [
                # M&A specific queries
                "acquisition merger publishing company",
                "publisher acquired deal announced",
                "merger consolidation scholarly publishing",
                "content company acquisition tech",
                # Funding specific queries
                "venture capital funding publishing AI",
                "investment round series funding",
                "funding announced million publishing",
                "government grant research funding",
                # Market/Revenue queries
                "market share revenue publishing",
                "subscription open access revenue",
            ]
        }

        # Get explicit queries for this pillar
        queries = pillar_explicit_queries.get(pillar, [])

        # Also add queries from trend definitions as backup
        pillar_to_trends = {
            'power': ['T2', 'T4'],  # Agentic AI, Regulatory
            'attention': ['T1', 'T3'],  # Invisible LLM, SEO to GEO
            'money': ['T5']  # Consolidation
        }

        for trend_id in pillar_to_trends.get(pillar, []):
            if trend_id in TREND_DEFINITIONS:
                trend = TREND_DEFINITIONS[trend_id]
                queries.extend(trend['keywords'][:3])

        # Deduplicate and limit
        seen = set()
        unique_queries = []
        for q in queries:
            if q not in seen:
                seen.add(q)
                unique_queries.append(q)

        return unique_queries[:10] if unique_queries else [f"{pillar} scholarly publishing AI"]

    async def _collect_pillar_articles(
        self,
        pillar: str,
        queries: List[str],
        days_back: int = 90,
        articles_per_topic: int = 20,
        max_relevance_score: float = 0.65
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Collect articles for a pillar across all topics.

        For each topic:
        - Runs semantic search with pillar queries
        - Fetches up to 100 articles per query
        - Filters by relevance threshold (cosine distance < max_relevance_score)
        - Selects top N by relevance score

        Args:
            pillar: The pillar type (power, attention, money)
            queries: List of semantic search queries
            days_back: Days of articles to consider
            articles_per_topic: Max articles to select per topic
            max_relevance_score: Maximum cosine distance to accept (lower = more similar)
                                 Default 0.65 filters out poorly matched articles

        Returns:
            - articles: List of article dicts for analysis
            - dataset_records: List of records for pam_article_datasets table
        """
        topics = await self._get_all_topics()
        if not topics:
            logger.warning("No topics found, using cross-topic search only")
            topics = [None]  # Will search without topic filter

        all_articles = []
        dataset_records = []
        seen_uris = set()

        logger.info(f"Collecting {pillar} articles across {len(topics)} topics with {len(queries)} queries (max_relevance={max_relevance_score})")

        for topic in topics:
            topic_articles = []

            for query in queries:
                try:
                    metadata_filter = {"topic": topic} if topic else None
                    results = await run_in_threadpool(
                        vector_search_articles,
                        query=query,
                        top_k=100,
                        metadata_filter=metadata_filter
                    )

                    if results:
                        for r in results:
                            if isinstance(r, dict):
                                article = r.get('metadata', r)
                                uri = article.get('uri')
                                if uri and uri not in seen_uris:
                                    article['_relevance_score'] = r.get('score', 1.0)
                                    article['_pillar'] = pillar
                                    article['_topic'] = topic or article.get('topic', '')
                                    article['_query'] = query
                                    topic_articles.append(article)
                                    seen_uris.add(uri)

                except Exception as e:
                    logger.warning(f"Vector search failed for query '{query}' in topic '{topic}': {e}")

            # Sort by relevance (lower score = more similar in cosine distance)
            topic_articles.sort(key=lambda x: x.get('_relevance_score', 1.0))

            # Filter by relevance threshold - only keep well-matched articles
            relevant_articles = [
                a for a in topic_articles
                if a.get('_relevance_score', 1.0) <= max_relevance_score
            ]

            if len(relevant_articles) < len(topic_articles):
                filtered_count = len(topic_articles) - len(relevant_articles)
                logger.debug(f"Filtered {filtered_count} poor matches from topic '{topic}' (score > {max_relevance_score})")

            # Select top N per topic from relevant articles only
            selected = relevant_articles[:articles_per_topic]

            for article in selected:
                all_articles.append(article)
                dataset_records.append({
                    'pillar': pillar,
                    'topic': article.get('_topic', ''),
                    'article_uri': article.get('uri'),
                    'article_title': article.get('title'),
                    'article_source': article.get('news_source') or article.get('source'),
                    'relevance_score': article.get('_relevance_score'),
                    'publication_date': article.get('publication_date')
                })

        if all_articles:
            avg_score = sum(a.get('_relevance_score', 0) for a in all_articles) / len(all_articles)
            logger.info(f"Collected {len(all_articles)} articles for pillar {pillar} (avg relevance: {avg_score:.3f})")
        else:
            logger.warning(f"No relevant articles found for pillar {pillar} with threshold {max_relevance_score}")

        return all_articles, dataset_records

    def _map_to_publisher_pillars(
        self,
        power_analysis: Optional[Dict],
        attention_analysis: Optional[Dict],
        money_analysis: Optional[Dict]
    ) -> Dict[str, Any]:
        """
        Map PAM analysis to Publisher Pillars (Trust, Infrastructure, Connector).

        These three pillars represent strategic value positions:
        - Trust: Integrity and verification of knowledge
        - Infrastructure: Technical backbone for knowledge creation/distribution
        - Connector: Persistent connections to researchers via incentive alignment
        """
        power = power_analysis or {}
        attention = attention_analysis or {}
        money = money_analysis or {}

        # Trust Provider: Derived from regulatory influence + attribution + IP
        # Use "or 50" because .get('score', 50) returns None if key exists with value None
        trust_score = (
            (power.get('regulatory_influence', {}).get('score') or 50) * 0.4 +
            (attention.get('synthesis_exposure', {}).get('attribution_rate') or 50) * 0.3 +
            (power.get('ip_positioning', {}).get('score') or 50) * 0.3
        )

        # Infrastructure Provider: Derived from infrastructure control + AI readiness
        infrastructure_score = (
            (power.get('infrastructure_control', {}).get('score') or 50) * 0.4 +
            (attention.get('ai_visibility', {}).get('metadata_readiness') or 50) * 0.3 +
            (attention.get('geo_readiness', {}).get('api_accessibility') or 50) * 0.3
        )

        # Researcher Connector: Derived from network centrality + visibility
        # Note: academic_visibility removed (used citations, not relevant for news analysis)
        # Using ai_visibility instead (measures LLM ecosystem participation signals)
        connector_score = (
            (power.get('network_centrality', {}).get('score') or 50) * 0.4 +
            (attention.get('brand_visibility', {}).get('score') or 50) * 0.3 +
            (attention.get('ai_visibility', {}).get('score') or 50) * 0.3
        )

        return {
            'trust': {
                'score': round(trust_score, 1),
                'name': 'Trust Provider',
                'description': 'Integrity and verification of knowledge',
                'components': {
                    'regulatory_influence': power.get('regulatory_influence', {}).get('score', 50),
                    'attribution_preservation': attention.get('synthesis_exposure', {}).get('attribution_rate', 50),
                    'ip_positioning': power.get('ip_positioning', {}).get('score', 50)
                }
            },
            'infrastructure': {
                'score': round(infrastructure_score, 1),
                'name': 'Content Infrastructure Provider',
                'description': 'Technical backbone for knowledge creation and distribution',
                'components': {
                    'infrastructure_control': power.get('infrastructure_control', {}).get('score', 50),
                    'metadata_readiness': attention.get('ai_visibility', {}).get('metadata_readiness', 50),
                    'api_accessibility': attention.get('geo_readiness', {}).get('api_accessibility', 50)
                }
            },
            'connector': {
                'score': round(connector_score, 1),
                'name': 'Researcher Connector',
                'description': 'Persistent connections to researchers via incentive alignment',
                'components': {
                    'network_centrality': power.get('network_centrality', {}).get('score', 50),
                    'brand_visibility': attention.get('brand_visibility', {}).get('score', 50),
                    'ai_visibility': attention.get('ai_visibility', {}).get('score', 50)
                }
            }
        }

    # =========================================================================
    # Score storage methods for trending
    # =========================================================================

    async def _save_trend_snapshot(
        self,
        run_id: str,
        topic: Optional[str],
        scores: Dict,
        trend_analysis: Dict
    ):
        """Save daily trend snapshot for historical tracking."""
        try:
            db = get_database_instance()
            trends = {t.get('id'): t for t in trend_analysis.get('trends', [])}

            # Normalize topic - treat empty string as NULL
            topic = topic.strip() if topic else None
            if topic == '':
                topic = None

            # Check if snapshot exists for today
            today = date.today().isoformat()
            if topic:
                existing = db.fetch_one(
                    "SELECT id FROM pam_trend_snapshots WHERE snapshot_date = ? AND topic = ?",
                    (today, topic)
                )
            else:
                existing = db.fetch_one(
                    "SELECT id FROM pam_trend_snapshots WHERE snapshot_date = ? AND topic IS NULL",
                    (today,)
                )

            if existing:
                # Update existing snapshot
                if topic:
                    db.execute_query(
                        """UPDATE pam_trend_snapshots SET
                           t1_invisible_llm = ?, t2_agentic_ai = ?, t3_seo_geo_decline = ?,
                           t4_regulatory = ?, t5_consolidation = ?,
                           t1_velocity = ?, t2_velocity = ?, t3_velocity = ?,
                           t4_velocity = ?, t5_velocity = ?,
                           trend_details = CAST(? AS jsonb), model_used = ?, articles_analyzed = ?
                           WHERE snapshot_date = ? AND topic = ?""",
                        (
                            trends.get('T1', {}).get('score', 0),
                            trends.get('T2', {}).get('score', 0),
                            trends.get('T3', {}).get('score', 0),
                            trends.get('T4', {}).get('score', 0),
                            trends.get('T5', {}).get('score', 0),
                            trends.get('T1', {}).get('velocity', 'stable'),
                            trends.get('T2', {}).get('velocity', 'stable'),
                            trends.get('T3', {}).get('velocity', 'stable'),
                            trends.get('T4', {}).get('velocity', 'stable'),
                            trends.get('T5', {}).get('velocity', 'stable'),
                            json.dumps(trend_analysis),
                            self.model,
                            scores.get('articles_analyzed', 0),
                            today, topic
                        )
                    )
                else:
                    db.execute_query(
                        """UPDATE pam_trend_snapshots SET
                           t1_invisible_llm = ?, t2_agentic_ai = ?, t3_seo_geo_decline = ?,
                           t4_regulatory = ?, t5_consolidation = ?,
                           t1_velocity = ?, t2_velocity = ?, t3_velocity = ?,
                           t4_velocity = ?, t5_velocity = ?,
                           trend_details = CAST(? AS jsonb), model_used = ?, articles_analyzed = ?
                           WHERE snapshot_date = ? AND topic IS NULL""",
                        (
                            trends.get('T1', {}).get('score', 0),
                            trends.get('T2', {}).get('score', 0),
                            trends.get('T3', {}).get('score', 0),
                            trends.get('T4', {}).get('score', 0),
                            trends.get('T5', {}).get('score', 0),
                            trends.get('T1', {}).get('velocity', 'stable'),
                            trends.get('T2', {}).get('velocity', 'stable'),
                            trends.get('T3', {}).get('velocity', 'stable'),
                            trends.get('T4', {}).get('velocity', 'stable'),
                            trends.get('T5', {}).get('velocity', 'stable'),
                            json.dumps(trend_analysis),
                            self.model,
                            scores.get('articles_analyzed', 0),
                            today
                        )
                    )
            else:
                # Insert new snapshot
                db.execute_query(
                    """INSERT INTO pam_trend_snapshots
                       (snapshot_date, topic, t1_invisible_llm, t2_agentic_ai, t3_seo_geo_decline,
                        t4_regulatory, t5_consolidation, t1_velocity, t2_velocity, t3_velocity,
                        t4_velocity, t5_velocity, trend_details, model_used, articles_analyzed, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CAST(? AS jsonb), ?, ?, NOW())""",
                    (
                        today, topic,
                        trends.get('T1', {}).get('score', 0),
                        trends.get('T2', {}).get('score', 0),
                        trends.get('T3', {}).get('score', 0),
                        trends.get('T4', {}).get('score', 0),
                        trends.get('T5', {}).get('score', 0),
                        trends.get('T1', {}).get('velocity', 'stable'),
                        trends.get('T2', {}).get('velocity', 'stable'),
                        trends.get('T3', {}).get('velocity', 'stable'),
                        trends.get('T4', {}).get('velocity', 'stable'),
                        trends.get('T5', {}).get('velocity', 'stable'),
                        json.dumps(trend_analysis),
                        self.model,
                        scores.get('articles_analyzed', 0)
                    )
                )

            logger.info(f"Saved trend snapshot for {today}")
        except Exception as e:
            logger.warning(f"Failed to save trend snapshot: {e}")

    async def _save_metrics_timeseries(self, run_id: str, scores: Dict, trend_analysis: Dict):
        """Save individual metrics for time series analysis."""
        try:
            db = get_database_instance()
            today = date.today().isoformat()

            metrics = [
                ('power_score', scores.get('power_score', 0), 'power'),
                ('attention_score', scores.get('attention_score', 0), 'attention'),
                ('money_score', scores.get('money_score', 0), 'money'),
                ('overall_score', scores.get('overall_score', 0), 'overall'),
            ]

            # Add T1-T5 scores
            for trend in trend_analysis.get('trends', []):
                metrics.append((
                    f"{trend.get('id', 'T0').lower()}_score",
                    trend.get('score', 0),
                    'trend'
                ))

            for metric_name, value, category in metrics:
                db.execute_query(
                    """INSERT INTO pam_metrics_timeseries
                       (entity_name, metric_date, metric_name, metric_value, metric_category, metadata, created_at)
                       VALUES (?, ?, ?, ?, ?, CAST(? AS jsonb), NOW())""",
                    ('global', today, metric_name, value, category, json.dumps({'run_id': run_id}))
                )

            logger.info(f"Saved {len(metrics)} metrics for {today}")
        except Exception as e:
            logger.warning(f"Failed to save metrics timeseries: {e}")

    async def _save_article_dataset(self, run_id: str, dataset_records: List[Dict]):
        """Save the article dataset used for this analysis."""
        if not dataset_records:
            return

        try:
            db = get_database_instance()
            for record in dataset_records:
                db.execute_query(
                    """INSERT INTO pam_article_datasets
                       (run_id, pillar, topic, article_uri, article_title, article_source,
                        relevance_score, publication_date, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, NOW())""",
                    (
                        run_id,
                        record.get('pillar'),
                        record.get('topic'),
                        record.get('article_uri'),
                        record.get('article_title'),
                        record.get('article_source'),
                        record.get('relevance_score'),
                        record.get('publication_date')
                    )
                )

            logger.info(f"Saved {len(dataset_records)} article dataset records for run {run_id}")
        except Exception as e:
            logger.warning(f"Failed to save article dataset: {e}")

    # =========================================================================
    # Query methods for trending history
    # =========================================================================

    async def get_trend_history(
        self,
        days_back: int = 90,
        topic: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get historical trend scores for charting."""
        try:
            db = get_database_instance()
            from_date = (date.today() - timedelta(days=days_back)).isoformat()

            if topic:
                result = db.fetch_all(
                    """SELECT snapshot_date, t1_invisible_llm, t2_agentic_ai, t3_seo_geo_decline,
                              t4_regulatory, t5_consolidation, t1_velocity, t2_velocity,
                              t3_velocity, t4_velocity, t5_velocity
                       FROM pam_trend_snapshots
                       WHERE snapshot_date >= ? AND topic = ?
                       ORDER BY snapshot_date""",
                    (from_date, topic)
                )
            else:
                result = db.fetch_all(
                    """SELECT snapshot_date, t1_invisible_llm, t2_agentic_ai, t3_seo_geo_decline,
                              t4_regulatory, t5_consolidation, t1_velocity, t2_velocity,
                              t3_velocity, t4_velocity, t5_velocity
                       FROM pam_trend_snapshots
                       WHERE snapshot_date >= ? AND topic IS NULL
                       ORDER BY snapshot_date""",
                    (from_date,)
                )

            return {
                'data': [dict(r) for r in result] if result else [],
                'days_back': days_back,
                'topic': topic
            }
        except Exception as e:
            logger.error(f"Failed to get trend history: {e}")
            return {'data': [], 'error': str(e)}

    async def get_metrics_history(
        self,
        metric_names: List[str] = None,
        days_back: int = 90
    ) -> Dict[str, Any]:
        """Get historical metric values for trending analysis."""
        try:
            db = get_database_instance()
            from_date = (date.today() - timedelta(days=days_back)).isoformat()
            metric_names = metric_names or ['power_score', 'attention_score', 'money_score', 'overall_score']

            # Build placeholders for IN clause
            placeholders = ','.join(['?' for _ in metric_names])
            result = db.fetch_all(
                f"""SELECT metric_date, metric_name, metric_value
                    FROM pam_metrics_timeseries
                    WHERE metric_date >= ? AND metric_name IN ({placeholders})
                    ORDER BY metric_date, metric_name""",
                (from_date, *metric_names)
            )

            return {
                'data': [dict(r) for r in result] if result else [],
                'metric_names': metric_names,
                'days_back': days_back
            }
        except Exception as e:
            logger.error(f"Failed to get metrics history: {e}")
            return {'data': [], 'error': str(e)}

    async def get_run_dataset(self, run_id: str) -> Dict[str, Any]:
        """Get the article dataset used for a specific analysis run."""
        try:
            db = get_database_instance()
            result = db.fetch_all(
                """SELECT pillar, topic, article_uri, article_title, article_source,
                          relevance_score, publication_date
                   FROM pam_article_datasets
                   WHERE run_id = ?
                   ORDER BY pillar, relevance_score""",
                (run_id,)
            )

            articles = [dict(r) for r in result] if result else []

            # Group by pillar
            by_pillar = defaultdict(list)
            for article in articles:
                by_pillar[article['pillar']].append(article)

            return {
                'run_id': run_id,
                'total_articles': len(articles),
                'by_pillar': dict(by_pillar),
                'articles': articles
            }
        except Exception as e:
            logger.error(f"Failed to get run dataset: {e}")
            return {'run_id': run_id, 'error': str(e), 'articles': []}

    # =========================================================================
    # Historical context methods
    # =========================================================================

    async def _get_previous_trend_scores(self, topic: Optional[str] = None, max_age_days: int = 7) -> Dict[str, float]:
        """
        Get the most recent trend scores for EMA smoothing.

        Retrieves the latest snapshot within max_age_days to use as the
        historical baseline for exponential moving average smoothing.
        This prevents erratic jumps in trend scores between runs.

        Args:
            topic: Optional topic filter (None = global)
            max_age_days: Maximum age of snapshot to use (default 7 days)

        Returns:
            Dict mapping trend_id (T1-T5) to previous score, or empty dict if none
        """
        try:
            db = get_database_instance()
            min_date = (date.today() - timedelta(days=max_age_days)).isoformat()

            # Normalize topic
            topic = topic.strip() if topic else None
            if topic == '':
                topic = None

            # Get most recent snapshot
            if topic:
                snapshot = db.fetch_one(
                    """SELECT t1_invisible_llm, t2_agentic_ai, t3_seo_geo_decline,
                              t4_regulatory, t5_consolidation, snapshot_date
                       FROM pam_trend_snapshots
                       WHERE snapshot_date >= ? AND topic = ?
                       ORDER BY snapshot_date DESC LIMIT 1""",
                    (min_date, topic)
                )
            else:
                snapshot = db.fetch_one(
                    """SELECT t1_invisible_llm, t2_agentic_ai, t3_seo_geo_decline,
                              t4_regulatory, t5_consolidation, snapshot_date
                       FROM pam_trend_snapshots
                       WHERE snapshot_date >= ? AND topic IS NULL
                       ORDER BY snapshot_date DESC LIMIT 1""",
                    (min_date,)
                )

            if not snapshot:
                logger.info(f"No previous trend snapshot within {max_age_days} days for topic={topic}")
                return {}

            # Build dict of previous scores
            previous_scores = {}
            if snapshot.get('t1_invisible_llm') is not None:
                previous_scores['T1'] = float(snapshot['t1_invisible_llm'])
            if snapshot.get('t2_agentic_ai') is not None:
                previous_scores['T2'] = float(snapshot['t2_agentic_ai'])
            if snapshot.get('t3_seo_geo_decline') is not None:
                previous_scores['T3'] = float(snapshot['t3_seo_geo_decline'])
            if snapshot.get('t4_regulatory') is not None:
                previous_scores['T4'] = float(snapshot['t4_regulatory'])
            if snapshot.get('t5_consolidation') is not None:
                previous_scores['T5'] = float(snapshot['t5_consolidation'])

            logger.info(
                f"Found previous trend scores from {snapshot.get('snapshot_date')} "
                f"for topic={topic}: {previous_scores}"
            )
            return previous_scores

        except Exception as e:
            logger.warning(f"Failed to get previous trend scores: {e}")
            return {}

    async def _get_historical_context(self, topic: Optional[str] = None, days_back: int = 30) -> Dict[str, Any]:
        """
        Get historical context for LLM analysis.

        Returns recent trend scores and changes to provide context about past data.
        """
        try:
            db = get_database_instance()
            from_date = (date.today() - timedelta(days=days_back)).isoformat()

            # Get recent snapshots
            if topic:
                snapshots = db.fetch_all(
                    """SELECT snapshot_date, t1_invisible_llm, t2_agentic_ai, t3_seo_geo_decline,
                              t4_regulatory, t5_consolidation, articles_analyzed
                       FROM pam_trend_snapshots
                       WHERE snapshot_date >= ? AND topic = ?
                       ORDER BY snapshot_date DESC LIMIT 10""",
                    (from_date, topic)
                )
            else:
                snapshots = db.fetch_all(
                    """SELECT snapshot_date, t1_invisible_llm, t2_agentic_ai, t3_seo_geo_decline,
                              t4_regulatory, t5_consolidation, articles_analyzed
                       FROM pam_trend_snapshots
                       WHERE snapshot_date >= ? AND topic IS NULL
                       ORDER BY snapshot_date DESC LIMIT 10""",
                    (from_date,)
                )

            # Get recent PAM scores
            metrics = db.fetch_all(
                """SELECT metric_date, metric_name, metric_value
                   FROM pam_metrics_timeseries
                   WHERE metric_date >= ? AND metric_name IN ('power_score', 'attention_score', 'money_score', 'overall_score')
                   ORDER BY metric_date DESC LIMIT 40""",
                (from_date,)
            )

            # Build summary
            historical = {
                'has_history': len(snapshots) > 0 if snapshots else False,
                'snapshots': [dict(s) for s in snapshots] if snapshots else [],
                'metrics': [dict(m) for m in metrics] if metrics else [],
                'days_covered': days_back
            }

            # Calculate trend changes if we have enough data
            if snapshots and len(snapshots) >= 2:
                latest = snapshots[0]
                oldest = snapshots[-1]
                historical['trend_changes'] = {
                    'T1': (latest.get('t1_invisible_llm') or 0) - (oldest.get('t1_invisible_llm') or 0),
                    'T2': (latest.get('t2_agentic_ai') or 0) - (oldest.get('t2_agentic_ai') or 0),
                    'T3': (latest.get('t3_seo_geo_decline') or 0) - (oldest.get('t3_seo_geo_decline') or 0),
                    'T4': (latest.get('t4_regulatory') or 0) - (oldest.get('t4_regulatory') or 0),
                    'T5': (latest.get('t5_consolidation') or 0) - (oldest.get('t5_consolidation') or 0),
                }
                historical['period'] = f"{oldest.get('snapshot_date')} to {latest.get('snapshot_date')}"

            return historical

        except Exception as e:
            logger.warning(f"Failed to get historical context: {e}")
            return {'has_history': False, 'snapshots': [], 'metrics': []}

    def _format_historical_context(self, historical: Dict[str, Any]) -> str:
        """Format historical context for LLM prompt."""
        if not historical.get('has_history'):
            return "No historical data available - this is the first analysis run."

        lines = ["HISTORICAL CONTEXT (Previous Analysis Runs):"]

        if historical.get('period'):
            lines.append(f"Period covered: {historical['period']}")

        if historical.get('trend_changes'):
            lines.append("\nTrend Score Changes since last analysis:")
            changes = historical['trend_changes']
            for trend_id, change in changes.items():
                direction = "↑" if change > 0 else "↓" if change < 0 else "→"
                lines.append(f"  {trend_id}: {direction} {abs(change):.1f} points")

        if historical.get('snapshots'):
            latest = historical['snapshots'][0]
            lines.append(f"\nMost recent scores (from {latest.get('snapshot_date', 'unknown')}):")
            lines.append(f"  T1 (Invisible LLMs): {latest.get('t1_invisible_llm', 'N/A')}")
            lines.append(f"  T2 (Agentic AI): {latest.get('t2_agentic_ai', 'N/A')}")
            lines.append(f"  T3 (SEO to GEO): {latest.get('t3_seo_geo_decline', 'N/A')}")
            lines.append(f"  T4 (Regulatory): {latest.get('t4_regulatory', 'N/A')}")
            lines.append(f"  T5 (Consolidation): {latest.get('t5_consolidation', 'N/A')}")

        return "\n".join(lines)

    # =========================================================================
    # Data management methods
    # =========================================================================

    async def reset_tracking_data(self, confirm: bool = False) -> Dict[str, Any]:
        """
        Reset all PAM tracking data (trend snapshots, metrics, article datasets).

        Args:
            confirm: Must be True to actually perform the reset

        Returns:
            Summary of deleted records
        """
        if not confirm:
            return {
                'success': False,
                'message': 'Reset not confirmed. Set confirm=True to proceed.',
                'warning': 'This will delete all PAM trend snapshots, metrics, article datasets, and cached queries.'
            }

        try:
            db = get_database_instance()
            deleted = {}

            # Delete trend snapshots
            db.execute_query("DELETE FROM pam_trend_snapshots", ())
            deleted['trend_snapshots'] = 'deleted'

            # Delete metrics timeseries
            db.execute_query("DELETE FROM pam_metrics_timeseries", ())
            deleted['metrics_timeseries'] = 'deleted'

            # Delete article datasets
            db.execute_query("DELETE FROM pam_article_datasets", ())
            deleted['article_datasets'] = 'deleted'

            # Delete cached queries
            db.execute_query("DELETE FROM pam_pillar_queries", ())
            deleted['pillar_queries'] = 'deleted'

            logger.info("PAM tracking data reset complete")

            return {
                'success': True,
                'message': 'All PAM tracking data has been reset',
                'deleted': deleted
            }

        except Exception as e:
            logger.error(f"Failed to reset PAM tracking data: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    async def get_tracking_stats(self) -> Dict[str, Any]:
        """Get statistics about tracked PAM data."""
        try:
            db = get_database_instance()

            stats = {}

            # Count trend snapshots
            result = db.fetch_one("SELECT COUNT(*) as count FROM pam_trend_snapshots", ())
            stats['trend_snapshots'] = result['count'] if result else 0

            # Count metrics
            result = db.fetch_one("SELECT COUNT(*) as count FROM pam_metrics_timeseries", ())
            stats['metrics_records'] = result['count'] if result else 0

            # Count article datasets
            result = db.fetch_one("SELECT COUNT(*) as count FROM pam_article_datasets", ())
            stats['article_dataset_records'] = result['count'] if result else 0

            # Count cached queries
            result = db.fetch_one("SELECT COUNT(*) as count FROM pam_pillar_queries WHERE is_active = TRUE", ())
            stats['active_cached_queries'] = result['count'] if result else 0

            # Get date range
            result = db.fetch_one(
                "SELECT MIN(snapshot_date) as earliest, MAX(snapshot_date) as latest FROM pam_trend_snapshots",
                ()
            )
            if result and result.get('earliest'):
                stats['date_range'] = {
                    'earliest': str(result['earliest']),
                    'latest': str(result['latest'])
                }
            else:
                stats['date_range'] = None

            return stats

        except Exception as e:
            logger.error(f"Failed to get tracking stats: {e}")
            return {'error': str(e)}

    # =========================================================================
    # Specialized Database Search Methods (No Date Limit)
    # =========================================================================

    async def _fetch_ma_activity_articles(self, limit: int = 50) -> Tuple[List[Dict], List[Dict]]:
        """
        Search entire database for M&A activity articles in AI/publishing/tech sector.

        Returns articles about acquisitions, mergers, funding rounds, etc.
        No date limit - searches entire database for T5 (Market Consolidation) trend.

        Returns:
            - articles: List of article dicts
            - dataset_records: List of records for pam_article_datasets table
        """
        # M&A action keywords
        ma_keywords = [
            'acquisition', 'acquires', 'acquired', 'acquire',
            'merger', 'merges', 'merged', 'merge',
            'funding', 'raises', 'raised', 'investment',
            'series a', 'series b', 'series c', 'series d',
            'ipo', 'valuation', 'unicorn',
            'buyout', 'takeover', 'consolidation',
            'deal'
        ]

        # Sector keywords to ensure relevance to AI/publishing/tech
        sector_keywords = [
            'ai', 'artificial intelligence', 'machine learning', 'llm', 'gpt',
            'publisher', 'publishing', 'scholarly', 'academic', 'journal',
            'elsevier', 'springer', 'wiley', 'sage', 'taylor francis', 'pearson',
            'tech', 'technology', 'software', 'platform', 'startup',
            'openai', 'anthropic', 'google', 'microsoft', 'meta', 'amazon',
            'content', 'media', 'news', 'data', 'research'
        ]

        try:
            from sqlalchemy import text
            db = get_database_instance()
            conn = db._temp_get_connection()

            # Build search query: Must have M&A keyword AND sector keyword
            ma_conditions = " OR ".join([
                f"(LOWER(title) LIKE '%{kw}%' OR LOWER(summary) LIKE '%{kw}%')"
                for kw in ma_keywords
            ])

            sector_conditions = " OR ".join([
                f"(LOWER(title) LIKE '%{kw}%' OR LOWER(summary) LIKE '%{kw}%')"
                for kw in sector_keywords
            ])

            query = f"""
                SELECT uri, title, summary, news_source, publication_date, analyzed, topic
                FROM articles
                WHERE ({ma_conditions})
                AND ({sector_conditions})
                ORDER BY publication_date DESC NULLS LAST
                LIMIT :limit
            """

            result = conn.execute(text(query), {"limit": limit})
            rows = result.fetchall()

            articles = []
            dataset_records = []

            for row in rows:
                article = {
                    'uri': row[0],
                    'title': row[1],
                    'summary': row[2] or '',
                    'content': row[2] or '',  # Alias for compatibility
                    'news_source': row[3],
                    'source': row[3],
                    'publication_date': row[4] or '',
                    'analyzed': row[5],
                    'topic': row[6] or '',
                    '_pillar': 'money',
                    '_topic': row[6] or '',
                    '_query': 'M&A Deep Scan',
                    '_relevance_score': 0.3,  # High relevance for keyword match
                    '_search_type': 'ma_activity'
                }
                articles.append(article)

                dataset_records.append({
                    'pillar': 'money',
                    'topic': row[6] or '',
                    'article_uri': row[0],
                    'article_title': row[1],
                    'article_source': row[3],
                    'relevance_score': 0.3,
                    'publication_date': row[4] or ''
                })

            logger.info(f"M&A Deep Scan: Found {len(articles)} articles from entire database")
            return articles, dataset_records

        except Exception as e:
            logger.error(f"M&A Deep Scan failed: {e}", exc_info=True)
            return [], []

    async def _fetch_regulation_articles(self, limit: int = 50) -> Tuple[List[Dict], List[Dict]]:
        """
        Search entire database for regulation/policy articles.

        Returns articles about AI regulations, copyright, compliance, legal developments.
        No date limit - searches entire database for T4 (Regulatory Pressures) trend.

        Returns:
            - articles: List of article dicts
            - dataset_records: List of records for pam_article_datasets table
        """
        regulation_keywords = [
            'regulation', 'regulatory', 'regulator',
            'eu ai act', 'ai act', 'legislation',
            'copyright', 'licensing', 'intellectual property',
            'compliance', 'policy', 'policies',
            'government', 'legal', 'lawsuit', 'court',
            'antitrust', 'ftc', 'doj', 'enforcement',
            'privacy', 'gdpr', 'data protection',
            'transparency', 'accountability', 'audit',
            'executive order', 'bill', 'law'
        ]

        try:
            from sqlalchemy import text
            db = get_database_instance()
            conn = db._temp_get_connection()

            # Build search query with OR conditions for all keywords
            # Note: articles table uses 'summary' not 'content', 'news_source' not 'source'
            keyword_conditions = " OR ".join([
                f"(LOWER(title) LIKE '%{kw}%' OR LOWER(summary) LIKE '%{kw}%')"
                for kw in regulation_keywords
            ])

            query = f"""
                SELECT uri, title, summary, news_source, publication_date, analyzed, topic
                FROM articles
                WHERE ({keyword_conditions})
                ORDER BY publication_date DESC NULLS LAST
                LIMIT :limit
            """

            result = conn.execute(text(query), {"limit": limit})
            rows = result.fetchall()

            articles = []
            dataset_records = []

            for row in rows:
                article = {
                    'uri': row[0],
                    'title': row[1],
                    'summary': row[2] or '',
                    'content': row[2] or '',  # Alias for compatibility
                    'news_source': row[3],
                    'source': row[3],
                    'publication_date': row[4] or '',
                    'analyzed': row[5],
                    'topic': row[6] or '',
                    '_pillar': 'power',
                    '_topic': row[6] or '',
                    '_query': 'Regulation Deep Scan',
                    '_relevance_score': 0.3,  # High relevance for keyword match
                    '_search_type': 'regulation'
                }
                articles.append(article)

                dataset_records.append({
                    'pillar': 'power',
                    'topic': row[6] or '',
                    'article_uri': row[0],
                    'article_title': row[1],
                    'article_source': row[3],
                    'relevance_score': 0.3,
                    'publication_date': row[4] or ''
                })

            logger.info(f"Regulation Deep Scan: Found {len(articles)} articles from entire database")
            return articles, dataset_records

        except Exception as e:
            logger.error(f"Regulation Deep Scan failed: {e}", exc_info=True)
            return [], []

    async def _fetch_ai_ecosystem_articles(self, limit: int = 50) -> Tuple[List[Dict], List[Dict]]:
        """
        Search entire database for AI ecosystem/attention articles.

        Returns articles about AI assistants, LLM ecosystems, search dynamics.
        No date limit - searches entire database for T1 (Invisible LLMs) and T3 (SEO to GEO).

        Returns:
            - articles: List of article dicts
            - dataset_records: List of records for pam_article_datasets table
        """
        ai_ecosystem_keywords = [
            'chatgpt', 'claude', 'gemini', 'perplexity',
            'ai assistant', 'ai search', 'llm',
            'openai', 'anthropic', 'google ai',
            'search engine', 'seo', 'visibility',
            'ai overview', 'zero-click', 'traffic',
            'content discovery', 'ai gateway',
            'microsoft copilot', 'copilot'
        ]

        try:
            from sqlalchemy import text
            db = get_database_instance()
            conn = db._temp_get_connection()

            # Build search query with OR conditions for all keywords
            keyword_conditions = " OR ".join([
                f"(LOWER(title) LIKE '%{kw}%' OR LOWER(summary) LIKE '%{kw}%')"
                for kw in ai_ecosystem_keywords
            ])

            query = f"""
                SELECT uri, title, summary, news_source, publication_date, analyzed, topic
                FROM articles
                WHERE ({keyword_conditions})
                ORDER BY publication_date DESC NULLS LAST
                LIMIT :limit
            """

            result = conn.execute(text(query), {"limit": limit})
            rows = result.fetchall()

            articles = []
            dataset_records = []

            for row in rows:
                article = {
                    'uri': row[0],
                    'title': row[1],
                    'summary': row[2] or '',
                    'content': row[2] or '',  # Alias for compatibility
                    'news_source': row[3],
                    'source': row[3],
                    'publication_date': row[4] or '',
                    'analyzed': row[5],
                    'topic': row[6] or '',
                    '_pillar': 'attention',
                    '_topic': row[6] or '',
                    '_query': 'AI Ecosystem Deep Scan',
                    '_relevance_score': 0.3,  # High relevance for keyword match
                    '_search_type': 'ai_ecosystem'
                }
                articles.append(article)

                dataset_records.append({
                    'pillar': 'attention',
                    'topic': row[6] or '',
                    'article_uri': row[0],
                    'article_title': row[1],
                    'article_source': row[3],
                    'relevance_score': 0.3,
                    'publication_date': row[4] or ''
                })

            logger.info(f"AI Ecosystem Deep Scan: Found {len(articles)} articles from entire database")
            return articles, dataset_records

        except Exception as e:
            logger.error(f"AI Ecosystem Deep Scan failed: {e}", exc_info=True)
            return [], []

    async def _fetch_extracted_events(self, days_back: int = 90) -> Tuple[List[Dict], List[Dict]]:
        """
        Fetch pre-extracted financial and regulatory events from event tables.

        Returns:
            Tuple of (financial_events, regulatory_events) lists
        """
        from sqlalchemy import text

        financial_events = []
        regulatory_events = []

        try:
            db = get_database_instance()
            conn = db._temp_get_connection()

            # Fetch financial events (M&A, funding, IPOs)
            fin_query = f"""
                SELECT
                    id, event_date, event_type, acquirer, target,
                    deal_value_usd, funding_round, headline, summary,
                    strategic_significance, market_impact_score
                FROM pam_financial_events
                WHERE event_date >= CURRENT_DATE - INTERVAL '{days_back} days'
                ORDER BY event_date DESC
                LIMIT 50
            """
            fin_result = conn.execute(text(fin_query))
            fin_rows = fin_result.fetchall()

            for row in fin_rows:
                financial_events.append({
                    'id': row[0],
                    'event_date': str(row[1]) if row[1] else None,
                    'event_type': row[2],
                    'acquirer': row[3],
                    'target': row[4],
                    'deal_value_usd': row[5],
                    'funding_round': row[6],
                    'headline': row[7],
                    'summary': row[8],
                    'strategic_significance': row[9],
                    'market_impact_score': row[10],
                })

            # Fetch regulatory events
            reg_query = f"""
                SELECT
                    id, event_date, jurisdiction, regulation_name, event_type,
                    headline, summary, publisher_implications, tech_implications,
                    t4_impact_score
                FROM pam_regulatory_events
                WHERE event_date >= CURRENT_DATE - INTERVAL '{days_back} days'
                ORDER BY event_date DESC
                LIMIT 50
            """
            reg_result = conn.execute(text(reg_query))
            reg_rows = reg_result.fetchall()

            for row in reg_rows:
                regulatory_events.append({
                    'id': row[0],
                    'event_date': str(row[1]) if row[1] else None,
                    'jurisdiction': row[2],
                    'regulation_name': row[3],
                    'event_type': row[4],
                    'headline': row[5],
                    'summary': row[6],
                    'publisher_implications': row[7],
                    'tech_implications': row[8],
                    't4_impact_score': row[9],
                })

            logger.info(f"Fetched {len(financial_events)} financial events and {len(regulatory_events)} regulatory events from event tables")
            return financial_events, regulatory_events

        except Exception as e:
            logger.error(f"Failed to fetch extracted events: {e}", exc_info=True)
            return [], []

    async def _fetch_monitored_entities(self, profile_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Fetch monitored entities from both sources:
        1. pam_entities table (standalone entities)
        2. organizational_profiles.monitored_brands (if profile_id provided)

        Returns:
            List of entity dicts with {name, type, source}
        """
        import json
        from sqlalchemy import text

        entities = []
        seen_names = set()

        try:
            db = get_database_instance()
            conn = db._temp_get_connection()

            # 1. Fetch from pam_entities table
            entities_query = """
                SELECT entity_name, entity_type, entity_subtype
                FROM pam_entities
                ORDER BY created_at DESC
            """
            result = conn.execute(text(entities_query))
            rows = result.fetchall()

            for row in rows:
                name = row[0]
                if name.lower() not in seen_names:
                    entities.append({
                        'name': name,
                        'type': row[1] or 'brand',
                        'subtype': row[2],
                        'source': 'pam_entities'
                    })
                    seen_names.add(name.lower())

            # 2. Fetch from organizational profile if provided
            if profile_id:
                profile_query = """
                    SELECT monitored_brands
                    FROM organizational_profiles
                    WHERE id = :profile_id
                """
                result = conn.execute(text(profile_query), {'profile_id': profile_id})
                row = result.fetchone()

                if row and row[0]:
                    try:
                        brands = json.loads(row[0]) if isinstance(row[0], str) else row[0]
                        if isinstance(brands, list):
                            for brand in brands:
                                if brand and brand.lower() not in seen_names:
                                    entities.append({
                                        'name': brand,
                                        'type': 'brand',
                                        'subtype': None,
                                        'source': 'org_profile'
                                    })
                                    seen_names.add(brand.lower())
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse monitored_brands JSON for profile {profile_id}")

            logger.info(f"Fetched {len(entities)} monitored entities ({len([e for e in entities if e['source'] == 'pam_entities'])} from pam_entities, {len([e for e in entities if e['source'] == 'org_profile'])} from org profile)")
            return entities

        except Exception as e:
            logger.error(f"Failed to fetch monitored entities: {e}", exc_info=True)
            return []


# Singleton instance
_pam_service: Optional[PAMService] = None


def get_pam_service() -> PAMService:
    """Get PAM service singleton."""
    global _pam_service
    if _pam_service is None:
        _pam_service = PAMService()
    return _pam_service
