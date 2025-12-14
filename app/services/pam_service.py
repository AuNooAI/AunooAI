"""
Power, Attention & Money (PAM) Service

Provides analysis of power, attention, and money flows in the knowledge economy,
tracking the 5 key trends reshaping scholarly publishing by 2030.
"""

import asyncio
import json
import logging
import uuid
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta, date
from collections import defaultdict

from fastapi.concurrency import run_in_threadpool
import litellm

from app.database import get_database_instance
from app.database_query_facade import DatabaseQueryFacade
from app.vector_store_pgvector import search_articles as vector_search_articles
from app.ai_models import get_ai_model

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-4.1-mini"

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
    """Service for Power, Attention & Money flows analysis."""

    def __init__(self):
        self.db = DatabaseQueryFacade(get_database_instance(), logger)
        self.model = DEFAULT_MODEL

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

            logger.info(f"PAM: Total unique articles collected: {len(all_articles)}")

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
        scenarios = {}

        for scenario_id, scenario in SCENARIOS_2030.items():
            scenarios[scenario_id] = {
                "name": scenario["name"],
                "description": scenario["description"],
                "base_probability": scenario["probability"],
                "current_probability": scenario["probability"],  # Could adjust based on trends
                "regulation_level": scenario["regulation"],
                "concentration_level": scenario["concentration"]
            }

        # Determine current trajectory
        trends = trend_analysis.get("trends", [])
        t4_score = next((t.get("score", 50) for t in trends if t.get("id") == "T4"), 50)
        t5_score = next((t.get("score", 50) for t in trends if t.get("id") == "T5"), 50)

        # Adjust probabilities based on T4 (regulatory) and T5 (consolidation)
        regulation_strength = t4_score / 100
        consolidation_strength = t5_score / 100

        # Higher T4 = more likely high-regulation scenarios
        # Higher T5 = more likely high-concentration scenarios
        if regulation_strength > 0.6 and consolidation_strength < 0.5:
            most_likely = "trusted_ecosystem"
        elif regulation_strength > 0.6 and consolidation_strength > 0.5:
            most_likely = "fragmented_compliance"
        elif regulation_strength < 0.5 and consolidation_strength > 0.6:
            most_likely = "behemoth_control"
        else:
            most_likely = "open_chaos"

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
        trust_score = (
            power.get('regulatory_influence', {}).get('score', 50) * 0.4 +
            attention.get('synthesis_exposure', {}).get('attribution_rate', 50) * 0.3 +
            power.get('ip_positioning', {}).get('score', 50) * 0.3
        )

        # Infrastructure Provider: Derived from infrastructure control + AI readiness
        infrastructure_score = (
            power.get('infrastructure_control', {}).get('score', 50) * 0.4 +
            attention.get('ai_visibility', {}).get('metadata_readiness', 50) * 0.3 +
            attention.get('geo_readiness', {}).get('api_accessibility', 50) * 0.3
        )

        # Researcher Connector: Derived from network centrality + visibility
        connector_score = (
            power.get('network_centrality', {}).get('score', 50) * 0.4 +
            attention.get('brand_visibility', {}).get('score', 50) * 0.3 +
            attention.get('academic_visibility', {}).get('score', 50) * 0.3
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
                    'academic_visibility': attention.get('academic_visibility', {}).get('score', 50)
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


# Singleton instance
_pam_service: Optional[PAMService] = None


def get_pam_service() -> PAMService:
    """Get PAM service singleton."""
    global _pam_service
    if _pam_service is None:
        _pam_service = PAMService()
    return _pam_service
