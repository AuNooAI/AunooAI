"""
Money Agent

Analyzes the MONEY dimension of PAM by extracting EVIDENCE from news articles
about how capital flows are shifting for publishers.

Focuses on one key trend:
- T5: Market Consolidation (M&A activity, funding concentration around compute+data giants)

This agent extracts what articles REPORT about funding, acquisitions, and revenue.
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


class MoneyAgent(BasePillarAgent):
    """Agent for analyzing the MONEY dimension through article evidence extraction."""

    PILLAR = "money"

    # Evidence categories aligned with T5 trend
    CATEGORIES = [
        "t5_consolidation_evidence",
        "funding_flow_signals",
        "ma_activity_evidence",
        "revenue_dynamics_signals"
    ]

    # Default keywords for cost dynamics article search (fallback)
    # These are paired with sector context in the search query
    DEFAULT_COST_KEYWORDS = [
        'cost cutting', 'cost-cutting', 'layoffs', 'layoff', 'job cuts',
        'budget cuts', 'budget reduction', 'restructuring', 'downsizing',
        'compute costs', 'gpu costs', 'infrastructure costs', 'cloud costs',
        'training costs', 'ai costs', 'operating costs', 'publishing costs',
        'price increase', 'price cut', 'pricing', 'subscription costs',
        'revenue decline', 'losses', 'profitability', 'margins', 'burn rate'
    ]

    # Sector keywords to filter cost articles to relevant domain
    SECTOR_KEYWORDS = [
        'ai', 'artificial intelligence', 'machine learning', 'llm',
        'publisher', 'publishing', 'scholarly', 'academic', 'journal',
        'tech', 'technology', 'software', 'platform', 'startup',
        'openai', 'anthropic', 'google', 'microsoft', 'meta',
        'content', 'media', 'research'
    ]

    def __init__(
        self,
        config: PillarConfig = None,
        google_search_provider: GoogleSearchProvider = None,
        cost_keywords: List[str] = None
    ):
        if config is None:
            config = PillarConfig(pillar="money")
        super().__init__(config)
        self._google_provider = google_search_provider
        # Use provided keywords or fall back to defaults
        self.cost_keywords = cost_keywords if cost_keywords else self.DEFAULT_COST_KEYWORDS
        logger.info(f"MoneyAgent initialized with {len(self.cost_keywords)} cost keywords")

    @property
    def google_provider(self) -> GoogleSearchProvider:
        if self._google_provider is None:
            self._google_provider = GoogleSearchProvider()
        return self._google_provider

    async def _fetch_external_data(self, context: AnalysisContext) -> Dict[str, Any]:
        """
        Fetch funding and M&A data for MONEY dimension.

        Uses Google Search for financial news + SQL search for cost articles.
        """
        if not self.config.enable_external_data:
            return {}

        external_data = {}
        query = context.topic or "AI publishing academic"

        try:
            # Fetch funding data
            funding = await self.google_provider.fetch_funding_data(
                query=query,
                days_back=context.days_back
            )
            external_data["funding"] = funding.to_dict()
            external_data["funding_score"] = funding.to_score()
        except Exception as e:
            logger.warning(f"Money: Failed to fetch funding data: {e}")
            external_data["funding_error"] = str(e)

        try:
            # Fetch M&A data
            ma = await self.google_provider.fetch_ma_data(
                query=query,
                days_back=context.days_back
            )
            external_data["ma_activity"] = ma.to_dict()
            external_data["ma_score"] = ma.to_score()
        except Exception as e:
            logger.warning(f"Money: Failed to fetch M&A data: {e}")
            external_data["ma_error"] = str(e)

        # Search for cost dynamics articles in the database
        try:
            cost_articles = await self._search_cost_articles(context)
            if cost_articles:
                external_data["cost_articles"] = cost_articles
                logger.info(f"Found {len(cost_articles)} cost-related articles")
        except Exception as e:
            logger.warning(f"Money: Failed to search cost articles: {e}")

        return external_data

    async def _search_cost_articles(self, context: AnalysisContext) -> List[Dict]:
        """
        Search for articles about cost dynamics in AI/publishing/tech sector.
        Uses keyword matching with sector filter for relevance.
        """
        from app.database import get_database_instance
        from sqlalchemy import text

        db = get_database_instance()
        conn = db._temp_get_connection()

        # Build OR conditions for cost keyword matching
        keyword_conditions = " OR ".join([
            f"(LOWER(title) LIKE '%{kw}%' OR LOWER(summary) LIKE '%{kw}%')"
            for kw in self.cost_keywords
        ])

        # Build OR conditions for sector relevance
        sector_conditions = " OR ".join([
            f"(LOWER(title) LIKE '%{kw}%' OR LOWER(summary) LIKE '%{kw}%')"
            for kw in self.SECTOR_KEYWORDS
        ])

        # Articles must have cost keyword AND be in relevant sector
        query = text(f"""
            SELECT uri, title, summary, news_source, publication_date, topic
            FROM articles
            WHERE ({keyword_conditions})
            AND ({sector_conditions})
            AND publication_date IS NOT NULL
            AND publication_date != ''
            AND publication_date::date >= CURRENT_DATE - INTERVAL '{context.days_back} days'
            ORDER BY publication_date DESC
            LIMIT 30
        """)

        try:
            result = conn.execute(query)
            rows = result.fetchall()

            articles = [
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
            return articles
        except Exception as e:
            logger.error(f"Error searching cost articles: {e}")
            return []

    async def _run_llm_analysis(
        self,
        articles: List[Dict],
        context: AnalysisContext,
        external_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Run LLM analysis to extract EVIDENCE from articles about money dynamics."""

        formatted_articles = self._format_articles_for_prompt(articles)

        # Include external data in prompt if available
        external_context = ""
        if external_data.get("funding"):
            fund = external_data["funding"]
            external_context += f"""
FUNDING DATA (from Google Search):
- Deals found: {fund.get('deal_count', 0)}
- Total funding (estimated): ${fund.get('total_funding_usd', 0):,}
- Largest deal: ${fund.get('largest_deal_usd', 0):,}
- Funding trend: {fund.get('funding_trend', 'unknown')}
"""

        if external_data.get("ma_activity"):
            ma = external_data["ma_activity"]
            external_context += f"""
M&A DATA (from Google Search):
- Deals found: {ma.get('deal_count', 0)}
- Consolidation trend: {ma.get('consolidation_trend', 'unknown')}
- Key acquirers: {', '.join(ma.get('key_acquirers', [])[:3])}
"""

        # Include pre-extracted financial events from database
        if context.financial_events:
            external_context += f"""
PRE-EXTRACTED FINANCIAL EVENTS ({len(context.financial_events)} events):
"""
            for i, evt in enumerate(context.financial_events[:20], 1):
                deal_str = f"${evt.get('deal_value_usd', 0):,}" if evt.get('deal_value_usd') else "Undisclosed"
                external_context += f"""
[FIN-{i}] {evt.get('headline', 'Unknown')}
- Date: {evt.get('event_date', 'Unknown')}
- Type: {evt.get('event_type', 'Unknown')}
- Parties: {evt.get('acquirer', 'N/A')} → {evt.get('target', 'N/A')}
- Deal value: {deal_str}
- Significance: {evt.get('strategic_significance', 'N/A')}
"""

        # Include cost dynamics articles from database search
        if external_data.get("cost_articles"):
            cost_arts = external_data["cost_articles"]
            external_context += f"""
## COST DYNAMICS ARTICLES (Pre-searched from database - {len(cost_arts)} found)
These articles specifically mention cost-related topics (layoffs, budget cuts, compute costs, pricing, etc.):
"""
            for i, art in enumerate(cost_arts[:15], 1):
                external_context += f"""
[COST-{i}] {art['title']}
- Source: {art['source']} | Date: {art['date']}
- Summary: {art['summary'][:300]}...
"""

        prompt = f"""
Analyze these articles to extract EVIDENCE about money dynamics in the AI/publishing sector.

IMPORTANT: You ARE extracting what these articles REPORT about funding, M&A, and revenue shifts.

{external_context}

NUMBERED ARTICLE LIST:
{formatted_articles}

{self._get_citation_instructions()}

Extract evidence for this key trend:

## T5: MARKET CONSOLIDATION
Capital and market power are consolidating around a few compute+data giants.

Look for articles that mention:
- Major acquisitions (company X acquired by company Y)
- Funding rounds (VC investments, especially large ones)
- Market concentration (few players dominating)
- Platform consolidation
- Vertical integration (companies buying up/down the value chain)
- Publishing company acquisitions
- Content licensing deals with dollar values
- Layoffs or cost-cutting at publishers
- Revenue shifts between platforms

## FUNDING FLOWS
Evidence of where investment capital is going.

IMPORTANT: Include funding rounds from the PRE-EXTRACTED FINANCIAL EVENTS section above (marked [FIN-X]).
These are verified funding events - incorporate them into your signals.

Also look for additional funding evidence in articles:
- Venture capital investments (amounts, recipients)
- Government grants and funding programs
- Corporate R&D spending
- Investment in AI vs traditional publishing

## M&A ACTIVITY
Evidence of who is acquiring whom.

IMPORTANT: Include deals from the PRE-EXTRACTED FINANCIAL EVENTS section above (marked [FIN-X]).
These are verified M&A events - incorporate them into your deals list.

Also look for additional deals in articles:
- Completed or announced acquisitions
- Merger discussions
- Strategic partnerships with equity stakes
- Acqui-hires

## REVENUE DYNAMICS
Evidence of how revenue models are changing.

Look for articles about:
- Subscription revenue trends
- Advertising revenue shifts
- Licensing revenue (especially AI training licensing)
- Open access financial models
- Platform fees and revenue sharing

Respond with JSON (cite specific article numbers):
{{
    "money_score": <0-100 based on evidence volume and consolidation intensity>,
    "score_justification": "Score based on evidence found, citing articles [1][2]",

    "t5_evidence": {{
        "trend_name": "Market Consolidation",
        "evidence_count": <number of relevant articles>,
        "trend_direction": "accelerating|stable|decelerating",
        "signals": [
            {{"finding": "What the article reports about consolidation [1]", "source": "Source name", "impact": "high|medium|low"}},
            {{"finding": "Another consolidation signal [2]", "source": "Source name", "impact": "high|medium|low"}}
        ],
        "key_acquirers": ["Companies making acquisitions mentioned in articles"],
        "deal_evidence": [
            {{"deal": "Deal description [3]", "parties": ["Acquirer", "Target"], "value": "$X million or undisclosed", "type": "acquisition|investment|partnership"}}
        ],
        "summary": "Summary of T5 consolidation evidence from articles"
    }},

    "funding_flows": {{
        "evidence_count": <number of articles mentioning funding>,
        "total_mentioned": "Rough total of funding mentioned in articles (e.g., '$2.5B across 5 deals')",
        "vc_activity_trend": "Based on articles: increasing|stable|decreasing",
        "signals": [
            {{"finding": "Funding announcement [4]", "source": "Source name", "value": "$X million"}},
            {{"finding": "Investment trend mentioned [5]", "source": "Source name", "value": "N/A"}}
        ],
        "government_funding_mentions": ["Government funding programs mentioned [6]"],
        "summary": "Summary of funding evidence from articles"
    }},

    "ma_activity": {{
        "evidence_count": <total count: pre-extracted events + articles mentioning M&A>,
        "activity_level": "Based on volume: high|moderate|low",
        "deals": [
            {{"acquirer": "Company A", "target": "Company B", "value": "$X million or undisclosed", "type": "acquisition|merger|funding|partnership|ipo", "source": "[FIN-1] or Source name [7]"}}
        ],
        "consolidation_pattern": "Based on evidence: compute giants buying content|publishers merging|vertical integration|other",
        "summary": "Summary of M&A evidence from pre-extracted events and articles"
    }},

    "revenue_dynamics": {{
        "evidence_count": <number of articles mentioning revenue changes>,
        "signals": [
            {{"finding": "Revenue trend mentioned [8]", "source": "Source name", "direction": "up|down|mixed"}}
        ],
        "subscription_trends": "What articles say about subscription revenue",
        "licensing_trends": "What articles say about licensing revenue (especially AI training)",
        "summary": "Summary of revenue evidence from articles"
    }},

    "cost_dynamics": {{
        "compute_cost_mentions": <number of articles mentioning compute costs>,
        "signals": [
            {{"finding": "Cost trend mentioned [9]", "source": "Source name"}}
        ],
        "trend": "Based on evidence: costs increasing|decreasing|stable"
    }},

    "key_events": [
        {{"event": "Specific financial event from articles [1]", "type": "acquisition|funding|revenue_change|partnership", "value": "$X million or N/A", "impact": "high|medium|low", "source": "Source name"}}
    ],

    "publisher_implications": "Based on the article evidence, what does this mean for publisher finances? Cite specific findings.",

    "summary": "2-3 sentence summary of money dynamics based on article evidence [1][2][3]"
}}
"""

        try:
            response = await self._call_llm(prompt)
            content = self._extract_json(response)
            return json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"Money: Failed to parse LLM response: {e}")
            return {
                "money_score": 50,
                "error": "Failed to parse analysis",
                "raw_response": response[:500] if response else None
            }
        except Exception as e:
            logger.error(f"Money: LLM analysis failed: {e}")
            return {"money_score": 50, "error": str(e)}

    async def _synthesize_results(
        self,
        articles: List[Dict],
        article_metrics: Dict[str, MetricResult],
        external_data: Dict[str, Any],
        llm_analysis: Dict[str, Any],
        context: AnalysisContext
    ) -> Dict[str, Any]:
        """Synthesize MONEY results from all data sources."""

        # Calculate composite score
        # Weight: 30% LLM (evidence-based), 35% funding data, 20% M&A data, 15% article metrics
        llm_score = llm_analysis.get("money_score", 50)
        funding_score = external_data.get("funding_score", 50)
        ma_score = external_data.get("ma_score", 50)
        article_score = self._calculate_article_based_score(article_metrics)

        composite_score = (
            llm_score * 0.30 +
            funding_score * 0.35 +
            ma_score * 0.20 +
            article_score * 0.15
        )

        # Extract evidence components
        t5_evidence = llm_analysis.get("t5_evidence", {})
        funding_flows = llm_analysis.get("funding_flows", {})
        ma_activity = llm_analysis.get("ma_activity", {})
        revenue_dynamics = llm_analysis.get("revenue_dynamics", {})
        cost_dynamics = llm_analysis.get("cost_dynamics", {})

        # Fallback: If LLM returned no M&A deals, use pre-extracted financial events
        llm_deals = ma_activity.get("deals", [])
        if not llm_deals and context.financial_events:
            logger.info(f"Money: Using {len(context.financial_events)} pre-extracted financial events as fallback")
            # Convert pre-extracted events to the expected deal format
            ma_activity["deals"] = [
                {
                    "acquirer": evt.get("acquirer", "Unknown"),
                    "target": evt.get("target", "Unknown"),
                    "value": f"${evt.get('deal_value_usd', 0):,}" if evt.get('deal_value_usd') else "undisclosed",
                    "type": evt.get("event_type", "deal"),
                    "source": f"[FIN] {evt.get('headline', '')[:50]}"
                }
                for evt in context.financial_events[:10]
            ]
            ma_activity["evidence_count"] = len(context.financial_events)
            ma_activity["activity_level"] = "high" if len(context.financial_events) >= 10 else "moderate" if len(context.financial_events) >= 5 else "low"
            ma_activity["summary"] = f"Based on {len(context.financial_events)} pre-extracted M&A and funding events"

        return {
            "pillar": "money",
            "money_score": round(composite_score, 1),
            "score": round(composite_score, 1),
            "score_justification": llm_analysis.get("score_justification", ""),
            "score_breakdown": {
                "llm_analysis": {"score": llm_score, "weight": 0.30, "source": "evidence_extraction"},
                "funding_data": {"score": funding_score, "weight": 0.35, "source": "google_search"},
                "ma_data": {"score": ma_score, "weight": 0.20, "source": "google_search"},
                "article_metrics": {"score": article_score, "weight": 0.15, "source": "measured"}
            },

            # Measured metrics
            "measured": {
                metric.name: metric.to_dict()
                for metric in article_metrics.values()
            },

            # External data
            "external": external_data,

            # T5 Evidence: Market Consolidation
            "t5_evidence": {
                "trend_name": t5_evidence.get("trend_name", "Market Consolidation"),
                "evidence_count": t5_evidence.get("evidence_count", 0),
                "trend_direction": t5_evidence.get("trend_direction", "stable"),
                "signals": t5_evidence.get("signals", []),
                "key_acquirers": t5_evidence.get("key_acquirers", []),
                "deal_evidence": t5_evidence.get("deal_evidence", []),
                "summary": t5_evidence.get("summary", "No T5 consolidation evidence found in articles")
            },

            # Funding Flows (from article evidence)
            "funding_flows": {
                "evidence_count": funding_flows.get("evidence_count", 0),
                "total_mentioned": funding_flows.get("total_mentioned", "N/A"),
                "vc_activity_trend": funding_flows.get("vc_activity_trend", "stable"),
                "signals": funding_flows.get("signals", []),
                "government_funding_mentions": funding_flows.get("government_funding_mentions", []),
                "summary": funding_flows.get("summary", "No funding evidence found in articles"),
                # Legacy fields for backwards compatibility
                "total_estimated_usd": funding_flows.get("total_mentioned", "N/A"),
                "vc_activity": funding_flows.get("vc_activity_trend", "stable"),
                "government_funding": "; ".join(funding_flows.get("government_funding_mentions", [])[:2]) if funding_flows.get("government_funding_mentions") else "No government funding mentioned",
                "key_deals": [
                    {"deal": s.get("finding", ""), "value": s.get("value", "N/A"), "parties": []}
                    for s in funding_flows.get("signals", [])[:3]
                ],
                "score": self._calculate_funding_score(funding_flows, t5_evidence)
            },

            # M&A Activity (from article evidence)
            "ma_activity": {
                "evidence_count": ma_activity.get("evidence_count", 0),
                "activity_level": ma_activity.get("activity_level", "moderate"),
                "level": ma_activity.get("activity_level", "moderate"),  # UI expects 'level'
                "deals": ma_activity.get("deals", []),
                "consolidation_pattern": ma_activity.get("consolidation_pattern", ""),
                "summary": ma_activity.get("summary", "No M&A evidence found in articles"),
                # Legacy fields for backwards compatibility
                "consolidation_trend": self._assess_consolidation_trend(t5_evidence),
                "recent_deals": [
                    {"acquirer": d.get("acquirer", ""), "target": d.get("target", ""), "value": d.get("value", "N/A"), "type": d.get("type", "")}
                    for d in ma_activity.get("deals", [])[:3]
                ],
                # UI expects key_deals as formatted strings for display
                "key_deals": [
                    f"{d.get('acquirer', 'Unknown')} → {d.get('target', 'Unknown')}: {d.get('value', 'undisclosed')} ({d.get('type', 'deal')})"
                    for d in ma_activity.get("deals", [])[:5]
                ],
                "key_acquirers": list(set(d.get("acquirer", "") for d in ma_activity.get("deals", []) if d.get("acquirer")))[:5],
                "score": self._calculate_ma_score(ma_activity, t5_evidence)
            },

            # Revenue Concentration (derived from evidence)
            # Only set level/trend if we have actual evidence
            "revenue_concentration": {
                "evidence_count": revenue_dynamics.get("evidence_count", 0),
                "concentration_level": self._assess_concentration_level(t5_evidence) if (revenue_dynamics.get("evidence_count", 0) > 0 or t5_evidence.get("evidence_count", 0) > 0) else None,
                "top_players_share": 0,  # Cannot measure directly
                "trend": self._assess_consolidation_trend(t5_evidence) if (revenue_dynamics.get("evidence_count", 0) > 0 or t5_evidence.get("evidence_count", 0) > 0) else None,
                "key_metrics": [s.get("finding", "") for s in revenue_dynamics.get("signals", [])[:3]],
                "licensing_trends": [s.get("finding", "") for s in revenue_dynamics.get("signals", []) if "licens" in s.get("finding", "").lower()][:3],
                "score": self._calculate_revenue_score(revenue_dynamics, t5_evidence)
            },

            # Revenue Dynamics (from article evidence)
            "revenue_dynamics": {
                "evidence_count": revenue_dynamics.get("evidence_count", 0),
                "signals": revenue_dynamics.get("signals", []),
                "subscription_trends": revenue_dynamics.get("subscription_trends", "No subscription data in articles"),
                "licensing_trends": revenue_dynamics.get("licensing_trends", "No licensing data in articles"),
                "summary": revenue_dynamics.get("summary", "No revenue evidence found in articles")
            },

            # Cost Dynamics (from article evidence + dedicated search)
            # Only set trends if we have actual evidence
            "cost_dynamics": {
                "compute_cost_mentions": cost_dynamics.get("compute_cost_mentions", 0),
                "cost_articles_found": len(external_data.get("cost_articles", [])),
                "signals": cost_dynamics.get("signals", []),
                "trend": cost_dynamics.get("trend") if (cost_dynamics.get("compute_cost_mentions", 0) > 0 or len(cost_dynamics.get("signals", [])) > 0) else None,
                # Legacy fields - only set if evidence exists
                "compute_cost_trend": cost_dynamics.get("trend") if (cost_dynamics.get("compute_cost_mentions", 0) > 0 or len(cost_dynamics.get("signals", [])) > 0) else None,
                "publishing_costs": "; ".join([s.get("finding", "") for s in cost_dynamics.get("signals", [])[:2]]) if cost_dynamics.get("signals") else ("See cost articles below" if external_data.get("cost_articles") else None),
                "key_factors": [s.get("finding", "") for s in cost_dynamics.get("signals", [])[:3]],
                "key_findings": [s.get("finding", "") for s in cost_dynamics.get("signals", [])[:5]],  # More findings for display
                "score": None if cost_dynamics.get("compute_cost_mentions", 0) == 0 and len(cost_dynamics.get("signals", [])) == 0 else 50 + (cost_dynamics.get("compute_cost_mentions", 0) * 5)
            },

            # Cost Articles Search Results (from dedicated SQL search)
            "cost_articles_search": {
                "articles_found": len(external_data.get("cost_articles", [])),
                "articles": external_data.get("cost_articles", [])[:10]  # Include first 10 for UI display
            },

            "key_events": llm_analysis.get("key_events", []),
            "publisher_implications": llm_analysis.get("publisher_implications", ""),
            "summary": llm_analysis.get("summary", ""),

            # Metadata
            "articles_analyzed": len(articles),
            "model_used": self.model,
            "data_sources": ["article_database", "evidence_extraction"] +
                           (["google_search_funding"] if external_data.get("funding") else []) +
                           (["google_search_ma"] if external_data.get("ma_activity") else [])
        }

    def _calculate_article_based_score(self, metrics: Dict[str, MetricResult]) -> float:
        """Calculate score from article-based metrics."""
        article_count = metrics.get("article_count")
        source_diversity = metrics.get("source_diversity")

        if not article_count:
            return 50.0

        count = article_count.value
        diversity = source_diversity.value if source_diversity else 1

        # Base score from article count
        import math
        if count <= 0:
            return 30.0

        base_score = 30 + (math.log10(count + 1) / math.log10(100)) * 35

        # Boost for source diversity (more sources = broader coverage)
        diversity_boost = min(15, diversity * 2)

        return min(85, max(30, base_score + diversity_boost))

    def _calculate_funding_score(self, funding_flows: Dict, t5_evidence: Dict) -> int | None:
        """Calculate funding score from evidence. Returns None if no evidence found."""
        evidence_count = funding_flows.get("evidence_count", 0)
        signals = len(funding_flows.get("signals", []))
        trend = funding_flows.get("vc_activity_trend", "stable")

        # Return None if no evidence - don't show fake 50
        if evidence_count == 0 and signals == 0:
            return None

        base = 50
        if evidence_count > 5:
            base = 70
        elif evidence_count > 2:
            base = 60
        elif evidence_count > 0:
            base = 55

        base += min(15, signals * 3)

        if trend == "increasing":
            base += 10
        elif trend == "decreasing":
            base -= 10

        return min(100, max(0, base))

    def _calculate_ma_score(self, ma_activity: Dict, t5_evidence: Dict) -> int | None:
        """Calculate M&A score from evidence. Returns None if no evidence found."""
        evidence_count = ma_activity.get("evidence_count", 0)
        deals = len(ma_activity.get("deals", []))
        activity = ma_activity.get("activity_level", "moderate")

        # Return None if no evidence - don't show fake 50
        if evidence_count == 0 and deals == 0:
            return None

        base = 50
        if evidence_count > 5 or deals > 3:
            base = 70
        elif evidence_count > 2 or deals > 1:
            base = 60
        elif evidence_count > 0 or deals > 0:
            base = 55

        base += min(20, deals * 5)

        if activity == "high":
            base += 10
        elif activity == "low":
            base -= 10

        return min(100, max(0, base))

    def _calculate_revenue_score(self, revenue_dynamics: Dict, t5_evidence: Dict) -> int | None:
        """Calculate revenue score from evidence. Returns None if no evidence found."""
        evidence_count = revenue_dynamics.get("evidence_count", 0)
        signals = len(revenue_dynamics.get("signals", []))
        t5_direction = t5_evidence.get("trend_direction", "stable")

        # Return None if no evidence - don't show fake 50
        if evidence_count == 0 and signals == 0:
            return None

        base = 50
        if evidence_count > 3:
            base = 60
        elif evidence_count > 0:
            base = 55

        base += min(10, signals * 3)

        # More consolidation = higher concentration score
        if t5_direction == "accelerating":
            base += 10

        return min(100, max(0, base))

    def _assess_consolidation_trend(self, t5_evidence: Dict) -> str | None:
        """Assess consolidation trend from evidence. Returns None if no evidence."""
        evidence_count = t5_evidence.get("evidence_count", 0)
        deals = len(t5_evidence.get("deal_evidence", []))
        signals = len(t5_evidence.get("signals", []))

        # Return None if no actual evidence - don't make up trends
        if evidence_count == 0 and deals == 0 and signals == 0:
            return None

        direction = t5_evidence.get("trend_direction", "stable")

        if direction == "accelerating" or deals > 3:
            return "accelerating"
        elif direction == "decelerating":
            return "slowing"
        return "stable"

    def _assess_concentration_level(self, t5_evidence: Dict) -> str | None:
        """Assess concentration level from evidence. Returns None if no evidence."""
        evidence_count = t5_evidence.get("evidence_count", 0)
        acquirers = t5_evidence.get("key_acquirers", [])
        deals = len(t5_evidence.get("deal_evidence", []))
        signals = len(t5_evidence.get("signals", []))

        # Return None if no actual evidence - don't make up levels
        if evidence_count == 0 and len(acquirers) == 0 and deals == 0 and signals == 0:
            return None

        direction = t5_evidence.get("trend_direction", "stable")

        # Only assess based on actual evidence
        if direction == "accelerating" or deals > 3:
            return "high"
        elif len(acquirers) > 5:
            return "moderate"
        elif deals > 0 or len(acquirers) > 0:
            return "moderate"
        return None
