"""
Theme Proposer Service

Uses LLM to identify emerging themes from a sample of high-novelty articles.
This is the core innovation of v2 - instead of clustering embeddings,
we ask the LLM to identify specific developments.

Inspired by Newsletter's section proposal pattern.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Dict, List, Optional, Any, Callable
from sqlalchemy import text
import numpy as np

from app.database import get_database_instance
from .date_utils import publication_ts_sql, utcnow
from .run_lock import normalize_topic_filter

logger = logging.getLogger(__name__)


THEME_PROPOSAL_PROMPT = """You are analyzing recent news to identify EMERGING topics -
specific developments that are NEW, GROWING, and NOTABLE.

Here are {n} recent articles from the past week:

{articles_summary}

Your task: Identify 5-10 SPECIFIC emerging topics.

Requirements:
- Must be SPECIFIC events/developments, not broad categories
- Each topic should have 3+ articles that clearly relate to it
- Focus on what's NEW or ACCELERATING, not ongoing coverage
- Look for: new announcements, breaking developments, policy changes,
  emerging trends, unexpected events

BAD examples (too broad):
- "AI Developments"
- "Tech News"
- "Market Updates"
- "Regulatory Changes"

GOOD examples (specific):
- "DeepSeek R1 Release and Global Response"
- "EU AI Act Implementation Deadlines"
- "OpenAI Enterprise Pricing Controversy"
- "Meta's Llama 3 Open Source Strategy"

Return ONLY valid JSON (no markdown):
{{
  "proposed_themes": [
    {{
      "theme_label": "Specific 3-7 word label",
      "theme_description": "One sentence describing the specific development",
      "search_query": "Semantic search query to find related articles",
      "key_entities": ["Company/Person/Org mentioned"],
      "why_emerging": "What makes this new/growing/notable"
    }}
  ]
}}"""


@dataclass
class ProposedTheme:
    """A theme proposed by the LLM."""
    theme_label: str
    theme_description: str
    search_query: str
    key_entities: List[str]
    why_emerging: str
    article_uris: List[str] = field(default_factory=list)
    article_distances: List[float] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "theme_label": self.theme_label,
            "theme_description": self.theme_description,
            "search_query": self.search_query,
            "key_entities": self.key_entities,
            "why_emerging": self.why_emerging,
            "article_uris": self.article_uris,
            "article_count": len(self.article_uris),
        }


@dataclass
class ProposalResult:
    """What one proposal step produced, including how much it actually read.

    ``sampled_uris`` is the real sample, so a run reports the number of articles
    it looked at rather than the configured ceiling.
    """
    themes: List[ProposedTheme] = field(default_factory=list)
    sampled_uris: List[str] = field(default_factory=list)

    @property
    def articles_sampled(self) -> int:
        return len(self.sampled_uris)


class ThemeProposer:
    """
    Uses LLM to propose emerging themes from article samples.
    """

    def __init__(
        self,
        ai_model_getter: Optional[Callable] = None,
        embedding_model_getter: Optional[Callable] = None,
        default_model: str = "gpt-5.4"
    ):
        self.ai_model_getter = ai_model_getter
        self.embedding_model_getter = embedding_model_getter
        self.default_model = default_model

    def _get_connection(self):
        """Get database connection."""
        db = get_database_instance()
        return db._temp_get_connection()

    # How many eligible rows the diversity pass may consider. The window
    # functions run in the database over this bounded set; Python only ever
    # receives ``max_articles`` rows.
    SCAN_CAP_MULTIPLIER = 20
    SCAN_CAP_FLOOR = 2000

    def _fetch_sample_articles(
        self,
        topic_filter: Optional[str] = None,
        days_back: int = 7,
        max_articles: int = 50
    ) -> List[Dict[str, Any]]:
        """Fetch a bounded, source-diverse sample of high-novelty recent articles.

        The whole sample is chosen in SQL. Ranking is a round robin over sources:
        every source contributes its best article before any source contributes
        its second, so one prolific wire cannot swallow the sample. Once every
        source has been drawn from, the remaining capacity fills with the next
        best articles regardless of source.

        Ordering is fully deterministic (novelty, then uri) so two runs over the
        same corpus sample the same articles.

        Raises:
            RuntimeError if the sample cannot be read. An empty sample and a
            broken query must not look alike to the caller.
        """
        topic_filter = normalize_topic_filter(topic_filter)
        conn = None
        try:
            conn = self._get_connection()

            scan_cap = max(self.SCAN_CAP_FLOOR, max_articles * self.SCAN_CAP_MULTIPLIER)
            cutoff = utcnow() - timedelta(days=days_back)
            params = {
                "cutoff": cutoff,
                "limit": max_articles,
                "scan_cap": scan_cap,
            }

            topic_clause = ""
            if topic_filter:
                topic_clause = "AND a.topic = :topic"
                params["topic"] = topic_filter

            published_ts = publication_ts_sql("a.publication_date")

            stmt = text(f"""
                WITH eligible AS (
                    SELECT
                        a.uri, a.title, a.summary, a.news_source,
                        a.publication_date, a.category,
                        COALESCE(n.composite_novelty_score, 50) AS novelty_score
                    FROM articles a
                    LEFT JOIN LATERAL (
                        SELECT ns.composite_novelty_score
                        FROM article_novelty_scores ns
                        WHERE ns.article_uri = a.uri
                        ORDER BY ns.calculation_date DESC, ns.id DESC
                        LIMIT 1
                    ) n ON TRUE
                    WHERE {published_ts} >= :cutoff
                      AND a.summary IS NOT NULL
                      AND LENGTH(a.summary) > 50
                      {topic_clause}
                    ORDER BY COALESCE(n.composite_novelty_score, 50) DESC, a.uri
                    LIMIT :scan_cap
                ),
                ranked AS (
                    SELECT
                        eligible.*,
                        ROW_NUMBER() OVER (
                            PARTITION BY COALESCE(news_source, '')
                            ORDER BY novelty_score DESC, uri
                        ) AS source_rank
                    FROM eligible
                )
                SELECT uri, title, summary, news_source, publication_date,
                       category, novelty_score
                FROM ranked
                ORDER BY source_rank, novelty_score DESC, uri
                LIMIT :limit
            """)

            result = conn.execute(stmt, params)
            return [dict(row) for row in result.mappings()]

        except Exception as exc:
            logger.error(f"Error fetching sample articles: {exc}")
            raise RuntimeError(
                f"Could not read the article sample for theme proposal: {exc}"
            ) from exc
        finally:
            if conn:
                conn.close()

    def _format_articles_for_prompt(self, articles: List[Dict[str, Any]]) -> str:
        """Format articles for the LLM prompt."""
        formatted = []
        for i, article in enumerate(articles, 1):
            title = article.get("title", "Untitled")
            summary = article.get("summary", "No summary")
            source = article.get("news_source", "Unknown")
            date = article.get("publication_date", "Unknown")

            # Truncate summary if too long
            if len(summary) > 300:
                summary = summary[:300] + "..."

            formatted.append(
                f"{i}. [{source}] {title}\n"
                f"   {summary}\n"
                f"   Date: {date}"
            )

        return "\n\n".join(formatted)

    def _parse_llm_response(self, response: Any) -> Optional[Dict[str, Any]]:
        """Parse LLM response as JSON."""
        try:
            # Handle various response types
            if hasattr(response, 'message') and hasattr(response.message, 'content'):
                # LiteLLM Choice object
                response = response.message.content
            elif hasattr(response, 'choices'):
                # Full OpenAI-style response
                response = response.choices[0].message.content
            elif hasattr(response, 'content') and isinstance(response.content, str):
                # Anthropic-style
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
            logger.error(f"Failed to parse LLM response as JSON: {exc}")
            logger.debug(f"Response was: {response[:500] if response else 'None'}")
            return None

    async def propose_themes(
        self,
        topic_filter: Optional[str] = None,
        days_back: int = 7,
        model_name: Optional[str] = None,
        max_sample: int = 250
    ) -> ProposalResult:
        """Use the LLM to propose emerging themes from an article sample.

        Returns a :class:`ProposalResult` carrying both the themes (without
        article assignments yet) and the URIs actually sampled.

        Raises:
            RuntimeError if the model is unavailable or the sample cannot be
            read. A thin corpus returns an empty result; a broken pipeline
            raises. The two must not look the same to the caller.
        """
        if not self.ai_model_getter:
            raise RuntimeError(
                "No AI model getter configured for theme proposal — detection "
                "cannot run without a model."
            )

        # Fetch sample articles (blocking DB work, kept off the event loop)
        articles = await asyncio.to_thread(
            self._fetch_sample_articles,
            topic_filter,
            days_back,
            max_sample,
        )
        sampled_uris = [a["uri"] for a in articles if a.get("uri")]

        if len(articles) < 5:
            logger.warning(f"Not enough articles ({len(articles)}) to propose themes")
            return ProposalResult(themes=[], sampled_uris=sampled_uris)

        logger.info(f"Proposing themes from {len(articles)} sample articles")

        # Format prompt
        articles_text = self._format_articles_for_prompt(articles)
        prompt = THEME_PROPOSAL_PROMPT.format(
            n=len(articles),
            articles_summary=articles_text
        )

        # Call LLM
        model_to_use = model_name or self.default_model

        model = self.ai_model_getter(model_to_use)
        if not model:
            raise RuntimeError(f"AI model '{model_to_use}' is not available")
        if not hasattr(model, 'generate'):
            raise RuntimeError(
                f"AI model '{model_to_use}' has no generate() method — "
                "theme proposal cannot run"
            )

        try:
            response = await model.generate(prompt, max_tokens=2000)
        except Exception as exc:
            logger.error(f"Theme proposal model call failed: {exc}")
            raise RuntimeError(f"Theme proposal model call failed: {exc}") from exc

        # A model that answers with unparseable text is a thin result, not an
        # infrastructure failure: the run completes with zero themes.
        parsed = self._parse_llm_response(response)
        if not parsed:
            logger.warning("Theme proposal returned no parseable JSON")
            return ProposalResult(themes=[], sampled_uris=sampled_uris)

        themes = []
        for theme_data in parsed.get("proposed_themes", []):
            if not isinstance(theme_data, dict):
                continue
            label = str(theme_data.get("theme_label") or "Unknown Theme")
            entities = theme_data.get("key_entities") or []
            if not isinstance(entities, list):
                entities = [str(entities)]
            themes.append(ProposedTheme(
                theme_label=label,
                theme_description=str(theme_data.get("theme_description") or ""),
                search_query=str(theme_data.get("search_query") or label),
                key_entities=[str(e) for e in entities if e],
                why_emerging=str(theme_data.get("why_emerging") or ""),
            ))

        logger.info(f"LLM proposed {len(themes)} themes")
        return ProposalResult(themes=themes, sampled_uris=sampled_uris)

    def _embed_query(self, query_text: str) -> np.ndarray:
        """Embed one search query. Raises if the encoder cannot answer.

        This is the synchronous encoder call; async callers route it through a
        worker thread. An encoder failure is an infrastructure failure and must
        reach the caller — a theme silently left without articles used to look
        exactly like a theme with no matching coverage.
        """
        from app.vector_store_pgvector import embed_query

        embedding = embed_query(query_text)
        if not embedding:
            raise RuntimeError("Encoder returned an empty embedding")
        return np.array(embedding)

    async def _get_embedding(self, text: str) -> np.ndarray:
        """Async wrapper around the blocking encoder call."""
        return await asyncio.to_thread(self._embed_query, text)

    def _assign_one_theme(
        self,
        theme: ProposedTheme,
        query_embedding: np.ndarray,
        topic_filter: Optional[str],
        days_back: int,
        max_per_theme: int,
        distance_threshold: float,
    ) -> None:
        """Fill one theme's article list by nearest-neighbour search (blocking)."""
        conn = None
        try:
            conn = self._get_connection()

            embedding_str = "[" + ",".join([str(v) for v in query_embedding]) + "]"
            params = {
                "query_embedding": embedding_str,
                "cutoff": utcnow() - timedelta(days=days_back),
                "limit": max_per_theme,
            }

            topic_clause = ""
            if topic_filter:
                topic_clause = "AND topic = :topic"
                params["topic"] = topic_filter

            published_ts = publication_ts_sql("publication_date")

            # OFFSET 0 forces materialization of the filtered set: the HNSW
            # index does not combine well with the date/topic pre-filters.
            stmt = text(f"""
                SELECT * FROM (
                    SELECT uri, title, summary,
                           embedding <=> CAST(:query_embedding AS vector) as distance
                    FROM articles
                    WHERE {published_ts} >= :cutoff
                    AND embedding IS NOT NULL
                    {topic_clause}
                    OFFSET 0
                ) filtered
                ORDER BY distance, uri
                LIMIT :limit
            """)

            result = conn.execute(stmt, params)

            uris: List[str] = []
            distances: List[float] = []
            for row in result.mappings():
                distance = float(row["distance"])
                if distance <= distance_threshold:
                    uris.append(row["uri"])
                    distances.append(distance)

            theme.article_uris = uris
            theme.article_distances = distances

            logger.info(
                f"Theme '{theme.theme_label}': assigned {len(uris)} articles "
                f"(threshold={distance_threshold})"
            )
        finally:
            if conn:
                conn.close()

    async def assign_articles_to_themes(
        self,
        themes: List[ProposedTheme],
        topic_filter: Optional[str] = None,
        days_back: int = 7,
        max_per_theme: int = 20,
        distance_threshold: float = 0.85
    ) -> List[ProposedTheme]:
        """Assign articles to themes by semantic search on each search_query.

        Raises on encoder or database failure. Assigning no articles to a theme
        is a legitimate outcome; failing to ask the question is not.
        """
        if not themes:
            return []

        topic_filter = normalize_topic_filter(topic_filter)

        for theme in themes:
            query_embedding = await self._get_embedding(theme.search_query)
            await asyncio.to_thread(
                self._assign_one_theme,
                theme,
                query_embedding,
                topic_filter,
                days_back,
                max_per_theme,
                distance_threshold,
            )

        return themes

    async def propose_and_assign(
        self,
        topic_filter: Optional[str] = None,
        days_back: int = 7,
        model_name: Optional[str] = None,
        max_sample: int = 250,
        max_per_theme: int = 30,
        distance_threshold: float = 0.85
    ) -> List[ProposedTheme]:
        """
        Full pipeline: propose themes via LLM, then assign articles via semantic search.
        """
        # Step 1: Propose themes
        proposal = await self.propose_themes(
            topic_filter=topic_filter,
            days_back=days_back,
            model_name=model_name,
            max_sample=max_sample
        )
        themes = proposal.themes

        if not themes:
            return []

        # Step 2: Assign articles
        themes = await self.assign_articles_to_themes(
            themes=themes,
            topic_filter=topic_filter,
            days_back=days_back,
            max_per_theme=max_per_theme,
            distance_threshold=distance_threshold
        )

        return themes
