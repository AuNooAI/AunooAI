"""
Attention Agent

Analyzes the ATTENTION dimension of PAM by extracting EVIDENCE from news articles
about how attention flows are changing for publishers.

Focuses on two key trends:
- T1: Invisible LLM Ecosystems (AI becoming primary gateway, bypassing publishers)
- T3: Decline of SEO, Rise of GEO (search disruption, zero-click answers)

This agent does NOT directly measure brand visibility or AI training inclusion.
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
from ..external_data import SemanticScholarProvider

logger = logging.getLogger(__name__)


class AttentionAgent(BasePillarAgent):
    """Agent for analyzing the ATTENTION dimension through article evidence extraction."""

    PILLAR = "attention"

    # Evidence categories aligned with T1 and T3 trends
    CATEGORIES = [
        "t1_llm_gateway_evidence",
        "t3_seo_geo_evidence",
        "publisher_visibility_signals",
        "content_attribution_evidence"
    ]

    def __init__(
        self,
        config: PillarConfig = None,
        semantic_scholar_provider: SemanticScholarProvider = None,
        entity_variations: Dict[str, List[str]] = None
    ):
        if config is None:
            config = PillarConfig(pillar="attention")
        super().__init__(config)
        self._semantic_scholar = semantic_scholar_provider
        # Entity name variations from config (e.g., "Wiley": ["Wiley", "John Wiley", "Wiley Publishing"])
        self.entity_variations = entity_variations or {}

    @property
    def semantic_scholar(self) -> SemanticScholarProvider:
        if self._semantic_scholar is None:
            self._semantic_scholar = SemanticScholarProvider()
        return self._semantic_scholar

    async def _fetch_external_data(self, context: AnalysisContext) -> Dict[str, Any]:
        """
        Fetch external data for ATTENTION dimension.

        Includes:
        - Entity-specific article search for monitored brands
        """
        if not self.config.enable_external_data:
            return {}

        external_data = {}

        # Search for articles specifically mentioning monitored entities
        if context.monitored_entities:
            entity_articles = await self._search_entity_articles(context)
            if entity_articles:
                external_data['entity_articles'] = entity_articles
                logger.info(f"Found {sum(len(arts) for arts in entity_articles.values())} articles mentioning monitored entities")

        return external_data

    async def _search_entity_articles(self, context: AnalysisContext) -> Dict[str, List[Dict]]:
        """
        Search for articles that specifically mention monitored entities.
        Does a SQL LIKE search for each entity name in titles and summaries.
        Uses entity_variations from config to expand search to include name variations.
        """
        from app.database import get_database_instance
        from sqlalchemy import text

        db = get_database_instance()
        conn = db._temp_get_connection()

        entity_articles = {}

        for entity in context.monitored_entities[:20]:  # Limit to 20 entities
            entity_name = entity.get('name', '')
            if not entity_name:
                continue

            # Get name variations from config, or use just the entity name
            variations = self.entity_variations.get(entity_name, [entity_name])
            if entity_name not in variations:
                variations = [entity_name] + list(variations)

            # Build OR conditions for all variations
            variation_conditions = " OR ".join([
                f"(LOWER(title) LIKE '%{v.lower()}%' OR LOWER(summary) LIKE '%{v.lower()}%')"
                for v in variations
            ])

            # Note: INTERVAL cannot be parameterized in PostgreSQL, so we use f-string
            query = text(f"""
                SELECT uri, title, summary, news_source, publication_date, topic
                FROM articles
                WHERE ({variation_conditions})
                AND publication_date IS NOT NULL
                AND publication_date != ''
                AND publication_date::date >= CURRENT_DATE - INTERVAL '{context.days_back} days'
                ORDER BY publication_date DESC
                LIMIT 50
            """)

            try:
                result = conn.execute(query)
                rows = result.fetchall()

                if rows:
                    entity_articles[entity_name] = [
                        {
                            'uri': row[0],
                            'title': row[1],
                            'summary': row[2][:500] if row[2] else '',
                            'source': row[3],
                            'date': row[4],
                            'topic': row[5]
                        }
                        for row in rows
                    ]
                    variations_msg = f" (searched: {', '.join(variations)})" if len(variations) > 1 else ""
                    logger.info(f"Found {len(rows)} articles mentioning '{entity_name}'{variations_msg}")
                else:
                    entity_articles[entity_name] = []
                    logger.info(f"No articles found mentioning '{entity_name}'")

            except Exception as e:
                logger.error(f"Error searching for entity '{entity_name}': {e}")
                entity_articles[entity_name] = []

        return entity_articles

    async def _run_llm_analysis(
        self,
        articles: List[Dict],
        context: AnalysisContext,
        external_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Run LLM analysis to extract EVIDENCE from articles about attention dynamics."""

        formatted_articles = self._format_articles_for_prompt(articles)

        # Build external context with monitored entities
        external_context = ""
        entity_tracking_instructions = ""
        entity_articles_section = ""

        # Check if we have pre-searched entity articles from external_data
        entity_articles = external_data.get('entity_articles', {})

        if context.monitored_entities:
            entity_names = [e['name'] for e in context.monitored_entities[:20]]

            # Build entity articles section if we found any via SQL search
            if entity_articles:
                entities_with_articles = []
                for entity_name, arts in entity_articles.items():
                    if arts:
                        entities_with_articles.append(entity_name)
                        # Format the entity-specific articles
                        entity_articles_section += f"\n### ARTICLES MENTIONING '{entity_name}' ({len(arts)} found):\n"
                        for i, art in enumerate(arts[:10], 1):  # Limit to 10 per entity
                            entity_articles_section += (
                                f"  [{entity_name}-{i}] {art['title']}\n"
                                f"      Source: {art['source']} | Date: {art['date']}\n"
                                f"      Summary: {art['summary'][:300]}...\n\n"
                            )

                if entities_with_articles:
                    external_context = f"""
## MONITORED ENTITY ARTICLES (Pre-searched via database)

The following articles were found that SPECIFICALLY mention your monitored entities.
These are CONFIRMED mentions - the entity name appears in the title or summary.

{entity_articles_section}

For each entity above, analyze:
1. How is the entity discussed? (context)
2. Is the sentiment positive, negative, or neutral?
3. What are the key themes/topics where they appear?
"""
                    entity_tracking_instructions = f"""
## ENTITY MENTIONS OUTPUT FORMAT

Based on the pre-searched entity articles above, populate entity_mentions for:
{', '.join(entities_with_articles)}

For each entity with articles found:
- entity: The exact entity name
- mention_count: Number of articles found (shown in parentheses above)
- context: Summary of HOW they are discussed across the articles
- sentiment: Overall sentiment based on the article content
- articles: Reference the entity-specific article IDs, e.g., ["Wiley-1", "Wiley-3"]

Entities NOT in the pre-searched results (no articles found): {', '.join([n for n in entity_names if n not in entities_with_articles]) or 'none'}
Do NOT include entities with no articles found.
"""
                else:
                    # No entity-specific articles found
                    external_context = f"""
## MONITORED ENTITIES (No dedicated articles found)

We searched for articles mentioning these entities but found none in the database:
{', '.join(entity_names)}

Check the general article list below for any incidental mentions.
If no mentions are found, return an empty array for entity_mentions.
"""
                    entity_tracking_instructions = """
## ENTITY MENTIONS OUTPUT FORMAT

Since no dedicated entity articles were found, check the general articles for incidental mentions.
If none found, return: "entity_mentions": []
"""
            else:
                # No entity search was performed (external data disabled)
                entity_list = '\n'.join([f"  - {name}" for name in entity_names])
                external_context = f"""
## MONITORED ENTITIES (Search in general articles)

Look for mentions of these entities in the article list below:
{entity_list}
"""
                entity_tracking_instructions = """
## ENTITY MENTIONS OUTPUT FORMAT

Only include entities that are ACTUALLY mentioned in the articles.
If none found, return: "entity_mentions": []
"""

        prompt = f"""
Analyze these articles to extract EVIDENCE about attention dynamics in the AI/publishing sector.

IMPORTANT: You are NOT measuring brand visibility or AI training inclusion directly (those are unmeasurable).
You ARE extracting what these articles REPORT about how attention flows are changing.

{external_context}

NUMBERED ARTICLE LIST:
{formatted_articles}

{self._get_citation_instructions()}

Extract evidence for these two key trends:

## T1: INVISIBLE LLM ECOSYSTEMS
AI assistants and chatbots are becoming primary information gateways, potentially bypassing publishers.

Look for articles that mention:
- AI assistants (ChatGPT, Claude, Gemini, Copilot) becoming primary research tools
- Users getting answers without visiting source websites
- Publishers losing direct user relationships
- Platform changes affecting content distribution
- Traffic disruption from AI intermediaries

## T3: DECLINE OF SEO, RISE OF GEO
Traditional search is being disrupted by AI-generated answers and zero-click results.

Look for articles that mention:
- Traditional search traffic declining
- Zero-click answers and AI summaries
- Generative Engine Optimization (GEO) strategies
- Google SGE, Bing Chat, or AI search features
- Changes in how users find information
- Publisher strategies for AI visibility

## PUBLISHER IMPLICATIONS
Based on the evidence, what are the implications for publishers?

{entity_tracking_instructions}

Respond with JSON (cite specific article numbers):
{{
    "attention_score": <0-100 based on evidence volume and urgency>,
    "score_justification": "Score based on evidence found, citing articles [1][2]",

    "t1_evidence": {{
        "trend_name": "Invisible LLM Ecosystems",
        "evidence_count": <number of relevant articles>,
        "trend_direction": "accelerating|stable|decelerating",
        "signals": [
            {{"finding": "What the article reports about AI gateways [1]", "source": "Article title or source name", "impact": "high|medium|low"}},
            {{"finding": "Another finding about publisher bypass [2]", "source": "Source name", "impact": "high|medium|low"}}
        ],
        "summary": "Summary of T1 evidence from articles"
    }},

    "t3_evidence": {{
        "trend_name": "Decline of SEO, Rise of GEO",
        "evidence_count": <number of relevant articles>,
        "trend_direction": "accelerating|stable|decelerating",
        "signals": [
            {{"finding": "What article says about search decline [3]", "source": "Source name", "impact": "high|medium|low"}},
            {{"finding": "Evidence of GEO adoption [4]", "source": "Source name", "impact": "high|medium|low"}}
        ],
        "zero_click_evidence": [
            {{"finding": "Specific zero-click mention [5]", "source": "Source name"}}
        ],
        "summary": "Summary of T3 evidence from articles"
    }},

    "content_attribution": {{
        "mentions_found": <number of articles mentioning attribution issues>,
        "signals": [
            {{"finding": "What articles say about content attribution [6]", "source": "Source name"}}
        ],
        "trend": "How attribution practices are changing based on evidence"
    }},

    "publisher_visibility": {{
        "threats_mentioned": ["Specific threats to publisher visibility mentioned in articles [1]"],
        "opportunities_mentioned": ["Opportunities or strategies mentioned in articles [3]"],
        "entities_discussed": ["Names of publishers/platforms specifically discussed"]
    }},

    "entity_mentions": [],

    "key_events": [
        {{"event": "Specific news event from articles [1]", "trend": "T1|T3", "impact": "high|medium|low", "source": "Source name"}}
    ],

    "publisher_implications": "Based on the article evidence, what does this mean for publishers? Cite specific findings.",

    "summary": "2-3 sentence summary of attention dynamics based on article evidence [1][2][3]"
}}
"""

        try:
            response = await self._call_llm(prompt)
            content = self._extract_json(response)
            return json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"Attention: Failed to parse LLM response: {e}")
            return {
                "attention_score": 50,
                "error": "Failed to parse analysis",
                "raw_response": response[:500] if response else None
            }
        except Exception as e:
            logger.error(f"Attention: LLM analysis failed: {e}")
            return {"attention_score": 50, "error": str(e)}

    async def _synthesize_results(
        self,
        articles: List[Dict],
        article_metrics: Dict[str, MetricResult],
        external_data: Dict[str, Any],
        llm_analysis: Dict[str, Any],
        context: AnalysisContext
    ) -> Dict[str, Any]:
        """Synthesize ATTENTION results from all data sources."""

        # Calculate composite score
        # Weight: 60% LLM analysis (evidence-based from articles), 40% article metrics
        # Note: No external data - ATTENTION metrics derived entirely from news article evidence
        llm_score = llm_analysis.get("attention_score", 50)
        article_score = self._calculate_article_based_score(article_metrics)

        composite_score = (
            llm_score * 0.60 +
            article_score * 0.40
        )

        # Extract evidence components
        t1_evidence = llm_analysis.get("t1_evidence", {})
        t3_evidence = llm_analysis.get("t3_evidence", {})
        content_attribution = llm_analysis.get("content_attribution", {})
        publisher_visibility = llm_analysis.get("publisher_visibility", {})

        return {
            "pillar": "attention",
            "attention_score": round(composite_score, 1),
            "score": round(composite_score, 1),
            "score_justification": llm_analysis.get("score_justification", ""),
            "score_breakdown": {
                "llm_analysis": {"score": llm_score, "weight": 0.60, "source": "evidence_extraction"},
                "article_metrics": {"score": article_score, "weight": 0.40, "source": "measured"}
            },

            # Measured metrics
            "measured": {
                metric.name: metric.to_dict()
                for metric in article_metrics.values()
            },

            # External data
            "external": external_data,

            # T1 Evidence: Invisible LLM Ecosystems
            "t1_evidence": {
                "trend_name": t1_evidence.get("trend_name", "Invisible LLM Ecosystems"),
                "evidence_count": t1_evidence.get("evidence_count", 0),
                "trend_direction": t1_evidence.get("trend_direction", "stable"),
                "signals": t1_evidence.get("signals", []),
                "summary": t1_evidence.get("summary", "No T1 evidence found in articles")
            },

            # T3 Evidence: Decline of SEO, Rise of GEO
            "t3_evidence": {
                "trend_name": t3_evidence.get("trend_name", "Decline of SEO, Rise of GEO"),
                "evidence_count": t3_evidence.get("evidence_count", 0),
                "trend_direction": t3_evidence.get("trend_direction", "stable"),
                "signals": t3_evidence.get("signals", []),
                "zero_click_evidence": t3_evidence.get("zero_click_evidence", []),
                "summary": t3_evidence.get("summary", "No T3 evidence found in articles")
            },

            # Content Attribution Evidence
            "content_attribution": {
                "mentions_found": content_attribution.get("mentions_found", 0),
                "signals": content_attribution.get("signals", []),
                "trend": content_attribution.get("trend", "No attribution evidence found")
            },

            # Publisher Visibility Signals (from article evidence, not direct measurement)
            "publisher_visibility": {
                "threats_mentioned": publisher_visibility.get("threats_mentioned", []),
                "opportunities_mentioned": publisher_visibility.get("opportunities_mentioned", []),
                "entities_discussed": publisher_visibility.get("entities_discussed", [])
            },

            # Entity mentions tracking (from monitored brands/entities)
            "entity_mentions": llm_analysis.get("entity_mentions", []),

            # Entity search results (ground truth from SQL search)
            "entity_search_results": {
                entity_name: len(arts)
                for entity_name, arts in external_data.get('entity_articles', {}).items()
            } if external_data.get('entity_articles') else {},

            # Visibility metrics derived from article evidence
            "ai_visibility": {
                "score": self._calculate_t1_score(t1_evidence),
                "training_data_exposure": t1_evidence.get("summary", "See T1 evidence for LLM ecosystem signals"),
                "training_data_exposure_description": t1_evidence.get("summary", "")
            },
            "brand_visibility": {
                "score": self._calculate_visibility_score(publisher_visibility),
                "traffic_trends": self._summarize_visibility_threats(publisher_visibility),
                "key_channels": publisher_visibility.get("entities_discussed", [])
            },
            "synthesis_exposure": {
                "score": self._calculate_t3_score(t3_evidence),
                "description": t3_evidence.get("summary", "See T3 evidence for zero-click/GEO signals"),
                "attribution_rate": content_attribution.get("mentions_found", 0) * 10,  # Rough proxy
                "attribution_assessment": content_attribution.get("trend", ""),
                "zero_click_risk": self._assess_zero_click_risk(t3_evidence),
                "zero_click_details": self._summarize_zero_click_evidence(t3_evidence)
            },
            "key_events": llm_analysis.get("key_events", []),
            "publisher_implications": llm_analysis.get("publisher_implications", ""),
            "summary": llm_analysis.get("summary", ""),

            # Metadata
            "articles_analyzed": len(articles),
            "model_used": self.model,
            "data_sources": ["article_database", "evidence_extraction"]
        }

    def _calculate_article_based_score(self, metrics: Dict[str, MetricResult]) -> float:
        """Calculate score from article-based metrics."""
        article_count = metrics.get("article_count")
        recency = metrics.get("recency_pct")

        if not article_count:
            return 50.0

        count = article_count.value
        recency_pct = recency.value if recency else 30

        # Base score from article count
        import math
        if count <= 0:
            return 30.0

        base_score = 30 + (math.log10(count + 1) / math.log10(100)) * 40

        # Boost for recency (more recent = higher attention currently)
        recency_boost = (recency_pct - 30) * 0.3  # -9 to +21 boost

        return min(85, max(30, base_score + recency_boost))

    def _calculate_t1_score(self, t1_evidence: Dict) -> int | None:
        """Calculate T1 score from evidence. Returns None if no evidence found."""
        count = t1_evidence.get("evidence_count", 0)
        direction = t1_evidence.get("trend_direction", "stable")

        # Return None if no evidence - don't show fake 50
        if count == 0:
            return None

        base = 50
        if count > 5:
            base = 70
        elif count > 2:
            base = 60
        elif count > 0:
            base = 55

        if direction == "accelerating":
            base += 10
        elif direction == "decelerating":
            base -= 10

        return min(100, max(0, base))

    def _calculate_t3_score(self, t3_evidence: Dict) -> int | None:
        """Calculate T3 score from evidence. Returns None if no evidence found."""
        count = t3_evidence.get("evidence_count", 0)
        direction = t3_evidence.get("trend_direction", "stable")
        zero_click_count = len(t3_evidence.get("zero_click_evidence", []))

        # Return None if no evidence - don't show fake 50
        if count == 0 and zero_click_count == 0:
            return None

        base = 50
        if count > 5:
            base = 70
        elif count > 2:
            base = 60
        elif count > 0:
            base = 55

        # Boost for zero-click evidence
        base += min(15, zero_click_count * 5)

        if direction == "accelerating":
            base += 10
        elif direction == "decelerating":
            base -= 10

        return min(100, max(0, base))

    def _calculate_visibility_score(self, visibility: Dict) -> int | None:
        """Calculate visibility score from evidence. Returns None if no evidence found."""
        threats = len(visibility.get("threats_mentioned", []))
        opportunities = len(visibility.get("opportunities_mentioned", []))

        # Return None if no evidence - don't show fake 50
        if threats == 0 and opportunities == 0:
            return None

        # More threats = lower visibility score (inverted)
        base = 50
        base -= threats * 5
        base += opportunities * 3

        return min(100, max(0, base))

    def _summarize_visibility_threats(self, visibility: Dict) -> str:
        """Summarize visibility threats from evidence."""
        threats = visibility.get("threats_mentioned", [])
        if threats:
            return "; ".join(threats[:3])
        return "No specific visibility threats mentioned in articles"

    def _assess_zero_click_risk(self, t3_evidence: Dict) -> str:
        """Assess zero-click risk from evidence."""
        zero_click = t3_evidence.get("zero_click_evidence", [])
        direction = t3_evidence.get("trend_direction", "stable")

        if len(zero_click) > 3 or direction == "accelerating":
            return "high"
        elif len(zero_click) > 0:
            return "medium"
        return "low"

    def _summarize_zero_click_evidence(self, t3_evidence: Dict) -> str:
        """Summarize zero-click evidence."""
        zero_click = t3_evidence.get("zero_click_evidence", [])
        if zero_click:
            findings = [z.get("finding", "") for z in zero_click[:3]]
            return "; ".join(findings)
        return "No specific zero-click evidence found in articles"
