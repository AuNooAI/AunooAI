"""
PAM Event Extraction Service

Background service that scans articles and extracts structured events:
- Financial Events: M&A, funding rounds, IPOs, valuations
- Regulatory Events: Policy changes, compliance requirements
- Power Events: Infrastructure control, partnership shifts
- Attention Events: AI ecosystem changes, visibility shifts

Events are stored in dedicated tables for efficient querying by PAM agents.
"""

import asyncio
import logging
import json
import os
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
import uuid
from dataclasses import dataclass

from app.database import get_database_instance
import litellm
from sqlalchemy import text

logger = logging.getLogger(__name__)


def _load_pam_config() -> Dict[str, Any]:
    """Load PAM config from file."""
    config_path = os.path.join(
        os.path.dirname(__file__),
        '..', '..', 'data', 'auspex', 'pam_config.json'
    )
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Could not load PAM config: {e}. Using defaults.")
        return {}


# Default keywords for initial article filtering (fast pre-filter before LLM)
# These are used if no config preset is provided or as fallbacks
DEFAULT_MA_KEYWORDS = [
    'acquisition', 'acquires', 'acquired', 'acquire', 'acquiring',
    'merger', 'merges', 'merged', 'merge', 'merging',
    'takeover', 'buyout', 'buy out',
    'deal announced', 'deal closed', 'transaction',
]

DEFAULT_FUNDING_KEYWORDS = [
    'funding', 'raises', 'raised', 'investment', 'investor',
    'series a', 'series b', 'series c', 'series d', 'series e',
    'seed round', 'seed funding', 'pre-seed',
    'ipo', 'initial public offering', 'goes public',
    'valuation', 'unicorn', 'decacorn',
    'venture capital', 'vc funding', 'growth equity',
]

# Power-related financial keywords (partnerships, infrastructure)
DEFAULT_POWER_FINANCIAL_KEYWORDS = [
    'partnership', 'partners', 'partnered', 'alliance', 'collaboration',
    'exclusive deal', 'exclusive agreement', 'exclusive partnership',
    'infrastructure deal', 'data center deal', 'compute agreement',
    'licensing deal', 'licensing agreement', 'content deal',
    'platform partnership', 'api partnership', 'integration deal',
]

DEFAULT_REGULATORY_KEYWORDS = [
    'regulation', 'regulatory', 'compliance', 'law', 'legislation',
    'eu ai act', 'ai act', 'copyright', 'intellectual property',
    'data protection', 'gdpr', 'privacy', 'antitrust',
    'ftc', 'sec', 'doj', 'european commission',
    'policy', 'mandate', 'requirement', 'ruling', 'court',
    'enforcement', 'fine', 'penalty', 'ban', 'restriction',
]

# Technology/AI events (for attention tracking)
DEFAULT_AI_TECH_KEYWORDS = [
    'launches', 'released', 'announces', 'unveils', 'introduces',
    'gpt-4', 'gpt-5', 'claude', 'gemini', 'llama', 'mistral',
    'model release', 'new model', 'ai model', 'language model',
    'benchmark', 'leaderboard', 'sota', 'state-of-the-art',
    'api update', 'api change', 'deprecation',
    'open source', 'open-source', 'opensources',
    'breakthrough', 'research paper', 'arxiv', 'publication',
]

DEFAULT_POWER_EVENT_KEYWORDS = [
    'partnership', 'partners', 'partnered', 'alliance', 'collaboration',
    'exclusive deal', 'exclusive agreement', 'exclusive partnership',
    'infrastructure', 'data center', 'compute', 'gpu', 'cloud',
    'platform', 'ecosystem', 'api', 'integration',
    'dominance', 'market share', 'monopoly', 'antitrust',
]

DEFAULT_ATTENTION_EVENT_KEYWORDS = [
    'benchmark', 'leaderboard', 'sota', 'state-of-the-art',
    'citation', 'paper', 'research', 'publication', 'arxiv',
    'chatgpt', 'claude', 'gemini', 'perplexity', 'copilot',
    'recommendation', 'mentioned by ai', 'ai recommends',
    'featured', 'trending', 'viral', 'breakthrough',
]


@dataclass
class ExtractionResult:
    """Result of event extraction from an article."""
    event_type: str  # 'financial', 'regulatory', 'power', 'attention'
    events: List[Dict[str, Any]]
    source_article_uri: str
    confidence: float


class PAMEventExtractionService:
    """Service for extracting structured events from articles."""

    # Default model for extraction
    DEFAULT_MODEL = "gpt-4.1-mini"

    def __init__(self, model: Optional[str] = None, keyword_preset: Optional[str] = None):
        self.db = get_database_instance()
        self._running = False
        self._last_run = None
        self._model = model or self.DEFAULT_MODEL

        # Load config and keywords
        self._config = _load_pam_config()
        self._keyword_preset = keyword_preset or self._config.get("keyword_preset", "scholarly_publishing")
        self._load_keywords()

    def _load_keywords(self) -> None:
        """Load keywords from config preset, falling back to defaults."""
        deep_search = self._config.get("deep_search_keywords", {})
        presets = deep_search.get("presets", {})
        preset_config = presets.get(self._keyword_preset, {})

        # Load MA/funding keywords (from ma_activity in config)
        config_ma = preset_config.get("ma_activity", [])
        self.ma_keywords = config_ma if config_ma else DEFAULT_MA_KEYWORDS + DEFAULT_FUNDING_KEYWORDS

        # Load regulatory keywords
        config_regulatory = preset_config.get("regulatory", [])
        self.regulatory_keywords = config_regulatory if config_regulatory else DEFAULT_REGULATORY_KEYWORDS

        # These don't have config equivalents yet, use defaults
        self.power_financial_keywords = DEFAULT_POWER_FINANCIAL_KEYWORDS
        self.ai_tech_keywords = DEFAULT_AI_TECH_KEYWORDS
        self.power_event_keywords = DEFAULT_POWER_EVENT_KEYWORDS
        self.attention_event_keywords = DEFAULT_ATTENTION_EVENT_KEYWORDS

        logger.info(f"Loaded keywords from preset '{self._keyword_preset}': "
                   f"MA={len(self.ma_keywords)}, Regulatory={len(self.regulatory_keywords)}")

    def set_model(self, model: str) -> None:
        """Update the model used for extraction."""
        self._model = model
        logger.info(f"Extraction model set to: {model}")

    async def run_extraction_cycle(
        self,
        days_back: int = 30,
        batch_size: int = 50,
        max_articles: int = 500,
        force_reprocess: bool = False
    ) -> Dict[str, int]:
        """
        Run a full extraction cycle.

        Args:
            days_back: How far back to look for articles
            batch_size: Articles per LLM call
            max_articles: Maximum articles to process in one cycle
            force_reprocess: If True, reprocess already-extracted articles

        Returns:
            Dict with counts of extracted events by type
        """
        logger.info(f"Starting PAM event extraction cycle (days_back={days_back})")
        self._running = True

        results = {
            'financial_events': 0,
            'regulatory_events': 0,
            'power_events': 0,
            'attention_events': 0,
            'articles_processed': 0,
            'errors': 0,
        }

        try:
            # Extract each type of event
            fin_count = await self._extract_financial_events(days_back, batch_size, max_articles)
            results['financial_events'] = fin_count

            reg_count = await self._extract_regulatory_events(days_back, batch_size, max_articles)
            results['regulatory_events'] = reg_count

            # Power and attention events will use the same articles but different extraction
            # For now, we'll track them in financial_events with event_type distinctions

            self._last_run = datetime.now()
            logger.info(f"Extraction cycle complete: {results}")

        except Exception as e:
            logger.error(f"Error during extraction cycle: {e}")
            results['errors'] += 1
        finally:
            self._running = False

        return results

    async def _extract_financial_events(
        self,
        days_back: int,
        batch_size: int,
        max_articles: int
    ) -> int:
        """Extract M&A, funding, and partnership events from articles."""

        # Build keyword filter - include power-related financial keywords
        # Uses instance keywords loaded from config or defaults
        all_keywords = self.ma_keywords + self.power_financial_keywords
        keyword_conditions = " OR ".join([
            f"(LOWER(title) LIKE '%{kw}%' OR LOWER(summary) LIKE '%{kw}%')"
            for kw in all_keywords
        ])

        # Query for candidate articles (publication_date is text, cast for comparison)
        query = f"""
            SELECT uri, title, summary, news_source, publication_date, topic
            FROM articles
            WHERE ({keyword_conditions})
            AND publication_date IS NOT NULL
            AND publication_date != ''
            AND publication_date::date >= CURRENT_DATE - INTERVAL '{days_back} days'
            ORDER BY publication_date DESC
            LIMIT {max_articles}
        """

        conn = self.db._temp_get_connection()
        result = conn.execute(text(query))
        rows = result.fetchall()

        if not rows:
            logger.info("No financial event candidates found")
            return 0

        logger.info(f"Found {len(rows)} candidate articles for financial events")

        # Process in batches
        events_extracted = 0
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i+batch_size]

            # Format articles for LLM
            articles_text = "\n\n".join([
                f"[Article {j+1}]\nTitle: {row[1]}\nSource: {row[3]}\nDate: {row[4]}\nSummary: {row[2]}"
                for j, row in enumerate(batch)
            ])

            # Call LLM to extract events
            events = await self._llm_extract_financial_events(articles_text, batch)

            # Store extracted events
            for event in events:
                try:
                    await self._store_financial_event(event)
                    events_extracted += 1
                except Exception as e:
                    logger.error(f"Error storing financial event: {e}")

        return events_extracted

    async def _llm_extract_financial_events(
        self,
        articles_text: str,
        source_articles: List[Any]
    ) -> List[Dict[str, Any]]:
        """Use LLM to extract financial events from article batch."""

        prompt = f"""Analyze these articles and extract M&A, funding, partnership, and licensing events.

ARTICLES:
{articles_text}

For each distinct event mentioned, extract:
1. event_type: One of:
   - "acquisition" - company buying another
   - "merger" - companies combining
   - "funding_round" - investment round
   - "ipo" - public listing
   - "partnership" - strategic alliance, collaboration, API integration
   - "licensing_deal" - content licensing, data licensing agreements
   - "infrastructure_deal" - compute, data center, cloud deals
2. event_date: Date of the event (YYYY-MM-DD format, use article date if not specified)
3. acquirer/investor: The acquiring company, investor, or initiating partner
4. target/company: The target company, partner, or licensor
5. deal_value_usd: Amount in USD if mentioned (just the number, no symbols)
6. funding_round: If funding, the round (seed, series_a, series_b, etc.)
7. headline: Brief headline (max 100 chars)
8. summary: 1-2 sentence description
9. strategic_significance: Why this matters for AI/publishing - focus on power dynamics
10. source_article_index: Which article(s) this came from (1-indexed)

Return ONLY valid JSON array. If no events found, return [].
Only include confirmed deals, not rumors or speculation.

Example output:
[
  {{
    "event_type": "partnership",
    "event_date": "2025-01-15",
    "acquirer": "OpenAI",
    "target": "News Corp",
    "headline": "OpenAI partners with News Corp for content access",
    "summary": "OpenAI announced partnership with News Corp for training data access.",
    "strategic_significance": "Shifts power dynamics by giving AI company exclusive content access",
    "source_article_index": [1]
  }}
]
"""

        try:
            logger.info(f"Extracting financial events using model: {self._model}")
            response = await litellm.acompletion(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=4000,
            )

            content = response.choices[0].message.content if response.choices else ''

            # Extract JSON from response
            json_match = re.search(r'\[[\s\S]*\]', content)
            if json_match:
                events = json.loads(json_match.group())

                # Add source article URIs
                for event in events:
                    indices = event.get('source_article_index', [])
                    if isinstance(indices, int):
                        indices = [indices]
                    event['source_articles'] = [
                        source_articles[i-1][0]  # URI is first column
                        for i in indices
                        if 0 < i <= len(source_articles)
                    ]

                return events

            return []

        except Exception as e:
            logger.error(f"Error in LLM financial event extraction: {e}")
            return []

    async def _store_financial_event(self, event: Dict[str, Any]) -> None:
        """Store a financial event in the database."""

        conn = self.db._temp_get_connection()

        # Check for duplicate (same acquirer/target/date)
        check_query = """
            SELECT id FROM pam_financial_events
            WHERE event_date = :event_date
            AND (acquirer = :acquirer OR target = :target)
            LIMIT 1
        """
        existing = conn.execute(text(check_query), {
            'event_date': event.get('event_date'),
            'acquirer': event.get('acquirer'),
            'target': event.get('target', event.get('company')),
        }).fetchone()

        if existing:
            logger.debug(f"Skipping duplicate financial event: {event.get('headline')}")
            return

        insert_query = """
            INSERT INTO pam_financial_events (
                id, event_date, event_type, acquirer, target,
                deal_value_usd, funding_round, headline, summary,
                strategic_significance, source_articles, verified, created_at
            ) VALUES (
                :id, :event_date, :event_type, :acquirer, :target,
                :deal_value_usd, :funding_round, :headline, :summary,
                :strategic_significance, :source_articles, :verified, NOW()
            )
        """

        conn.execute(text(insert_query), {
            'id': str(uuid.uuid4()),
            'event_date': event.get('event_date'),
            'event_type': event.get('event_type', 'unknown'),
            'acquirer': event.get('acquirer', event.get('investor')),
            'target': event.get('target', event.get('company')),
            'deal_value_usd': event.get('deal_value_usd'),
            'funding_round': event.get('funding_round'),
            'headline': event.get('headline', '')[:255],
            'summary': event.get('summary'),
            'strategic_significance': event.get('strategic_significance'),
            'source_articles': json.dumps(event.get('source_articles', [])),
            'verified': False,
        })
        conn.commit()

        logger.info(f"Stored financial event: {event.get('headline')}")

    async def _extract_regulatory_events(
        self,
        days_back: int,
        batch_size: int,
        max_articles: int
    ) -> int:
        """Extract regulatory events from articles."""

        # Build keyword filter - uses instance keywords loaded from config or defaults
        keyword_conditions = " OR ".join([
            f"(LOWER(title) LIKE '%{kw}%' OR LOWER(summary) LIKE '%{kw}%')"
            for kw in self.regulatory_keywords
        ])

        query = f"""
            SELECT uri, title, summary, news_source, publication_date, topic
            FROM articles
            WHERE ({keyword_conditions})
            AND publication_date IS NOT NULL
            AND publication_date != ''
            AND publication_date::date >= CURRENT_DATE - INTERVAL '{days_back} days'
            ORDER BY publication_date DESC
            LIMIT {max_articles}
        """

        conn = self.db._temp_get_connection()
        result = conn.execute(text(query))
        rows = result.fetchall()

        if not rows:
            logger.info("No regulatory event candidates found")
            return 0

        logger.info(f"Found {len(rows)} candidate articles for regulatory events")

        events_extracted = 0
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i+batch_size]

            articles_text = "\n\n".join([
                f"[Article {j+1}]\nTitle: {row[1]}\nSource: {row[3]}\nDate: {row[4]}\nSummary: {row[2]}"
                for j, row in enumerate(batch)
            ])

            events = await self._llm_extract_regulatory_events(articles_text, batch)

            for event in events:
                try:
                    await self._store_regulatory_event(event)
                    events_extracted += 1
                except Exception as e:
                    logger.error(f"Error storing regulatory event: {e}")

        return events_extracted

    async def _llm_extract_regulatory_events(
        self,
        articles_text: str,
        source_articles: List[Any]
    ) -> List[Dict[str, Any]]:
        """Use LLM to extract regulatory events from article batch."""

        prompt = f"""Analyze these articles and extract regulatory/policy events affecting AI and publishing.

ARTICLES:
{articles_text}

For each distinct regulatory event, extract:
1. event_type: One of "legislation_passed", "legislation_proposed", "ruling", "enforcement", "guideline", "investigation"
2. event_date: Date of the event (YYYY-MM-DD)
3. jurisdiction: Where (EU, US, UK, China, etc.)
4. regulation_name: Name of the regulation/law if applicable
5. headline: Brief headline (max 100 chars)
6. summary: 1-2 sentence description
7. publisher_implications: How this affects publishers specifically
8. tech_implications: How this affects AI/tech companies
9. t4_impact_score: Impact score 0.0-1.0 for regulatory pressure trend
10. source_article_index: Which article(s) (1-indexed)

Return ONLY valid JSON array. If no events found, return [].
Focus on events relevant to: AI regulation, copyright, data protection, antitrust, content moderation.

Example:
[
  {{
    "event_type": "legislation_passed",
    "event_date": "2025-01-20",
    "jurisdiction": "EU",
    "regulation_name": "EU AI Act",
    "headline": "EU AI Act enforcement begins",
    "summary": "EU begins enforcing AI Act provisions requiring transparency for AI systems.",
    "publisher_implications": "Publishers must disclose AI-generated content",
    "tech_implications": "AI companies face compliance requirements",
    "t4_impact_score": 0.85,
    "source_article_index": [2]
  }}
]
"""

        try:
            logger.info(f"Extracting regulatory events using model: {self._model}")
            response = await litellm.acompletion(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=4000,
            )

            content = response.choices[0].message.content if response.choices else ''

            json_match = re.search(r'\[[\s\S]*\]', content)
            if json_match:
                events = json.loads(json_match.group())

                for event in events:
                    indices = event.get('source_article_index', [])
                    if isinstance(indices, int):
                        indices = [indices]
                    event['source_articles'] = [
                        source_articles[i-1][0]
                        for i in indices
                        if 0 < i <= len(source_articles)
                    ]

                return events

            return []

        except Exception as e:
            logger.error(f"Error in LLM regulatory event extraction: {e}")
            return []

    async def _store_regulatory_event(self, event: Dict[str, Any]) -> None:
        """Store a regulatory event in the database."""

        conn = self.db._temp_get_connection()

        # Check for duplicate
        check_query = """
            SELECT id FROM pam_regulatory_events
            WHERE event_date = :event_date
            AND jurisdiction = :jurisdiction
            AND (regulation_name = :regulation_name OR headline = :headline)
            LIMIT 1
        """
        existing = conn.execute(text(check_query), {
            'event_date': event.get('event_date'),
            'jurisdiction': event.get('jurisdiction', 'Unknown'),
            'regulation_name': event.get('regulation_name'),
            'headline': event.get('headline'),
        }).fetchone()

        if existing:
            logger.debug(f"Skipping duplicate regulatory event: {event.get('headline')}")
            return

        insert_query = """
            INSERT INTO pam_regulatory_events (
                id, event_date, jurisdiction, regulation_name, event_type,
                headline, summary, publisher_implications, tech_implications,
                t4_impact_score, source_articles, verified, created_at
            ) VALUES (
                :id, :event_date, :jurisdiction, :regulation_name, :event_type,
                :headline, :summary, :publisher_implications, :tech_implications,
                :t4_impact_score, :source_articles, :verified, NOW()
            )
        """

        conn.execute(text(insert_query), {
            'id': str(uuid.uuid4()),
            'event_date': event.get('event_date'),
            'jurisdiction': event.get('jurisdiction', 'Unknown'),
            'regulation_name': event.get('regulation_name'),
            'event_type': event.get('event_type', 'unknown'),
            'headline': event.get('headline', '')[:255],
            'summary': event.get('summary'),
            'publisher_implications': event.get('publisher_implications'),
            'tech_implications': event.get('tech_implications'),
            't4_impact_score': event.get('t4_impact_score'),
            'source_articles': json.dumps(event.get('source_articles', [])),
            'verified': False,
        })
        conn.commit()

        logger.info(f"Stored regulatory event: {event.get('headline')}")

    async def get_recent_financial_events(
        self,
        event_type: Optional[str] = None,
        days_back: int = 90,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get recent financial events for PAM agent queries."""

        conn = self.db._temp_get_connection()

        # Build query with interval directly (can't parameterize PostgreSQL INTERVAL)
        query = f"""
            SELECT id, event_date, event_type, acquirer, target,
                   deal_value_usd, funding_round, headline, summary,
                   strategic_significance, market_impact_score
            FROM pam_financial_events
            WHERE event_date >= CURRENT_DATE - INTERVAL '{days_back} days'
        """
        params = {}

        if event_type:
            query += " AND event_type = :event_type"
            params['event_type'] = event_type

        query += f" ORDER BY event_date DESC LIMIT {limit}"

        result = conn.execute(text(query), params)
        rows = result.fetchall()

        return [
            {
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
            }
            for row in rows
        ]

    async def get_recent_regulatory_events(
        self,
        jurisdiction: Optional[str] = None,
        days_back: int = 90,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get recent regulatory events for PAM agent queries."""

        conn = self.db._temp_get_connection()

        # Build query with interval directly (can't parameterize PostgreSQL INTERVAL)
        query = f"""
            SELECT id, event_date, jurisdiction, regulation_name, event_type,
                   headline, summary, publisher_implications, tech_implications,
                   t4_impact_score
            FROM pam_regulatory_events
            WHERE event_date >= CURRENT_DATE - INTERVAL '{days_back} days'
        """
        params = {}

        if jurisdiction:
            query += " AND jurisdiction = :jurisdiction"
            params['jurisdiction'] = jurisdiction

        query += f" ORDER BY event_date DESC LIMIT {limit}"

        result = conn.execute(text(query), params)
        rows = result.fetchall()

        return [
            {
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
            }
            for row in rows
        ]


# Singleton instance
_extraction_service: Optional[PAMEventExtractionService] = None

def get_pam_event_extraction_service() -> PAMEventExtractionService:
    """Get or create the PAM event extraction service instance."""
    global _extraction_service
    if _extraction_service is None:
        _extraction_service = PAMEventExtractionService()
    return _extraction_service
