"""
Theme Proposer Service

Uses LLM to identify emerging themes from a sample of high-novelty articles.
This is the core innovation of v2 - instead of clustering embeddings,
we ask the LLM to identify specific developments.

Inspired by Newsletter's section proposal pattern.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from sqlalchemy import text
import numpy as np

from app.database import get_database_instance

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


class ThemeProposer:
    """
    Uses LLM to propose emerging themes from article samples.
    """

    def __init__(
        self,
        ai_model_getter: Optional[Callable] = None,
        embedding_model_getter: Optional[Callable] = None,
        default_model: str = "gpt-4o"
    ):
        self.ai_model_getter = ai_model_getter
        self.embedding_model_getter = embedding_model_getter
        self.default_model = default_model

    def _get_connection(self):
        """Get database connection."""
        db = get_database_instance()
        return db._temp_get_connection()

    def _fetch_sample_articles(
        self,
        topic_filter: Optional[str] = None,
        days_back: int = 7,
        max_articles: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Fetch a diverse sample of high-novelty recent articles.
        Prioritizes novelty score, recency, and source diversity.
        """
        conn = None
        try:
            conn = self._get_connection()

            # Build query - prioritize novelty if scores exist, else recency
            params = {"days_back": days_back, "limit": max_articles}

            topic_clause = ""
            if topic_filter:
                topic_clause = "AND a.topic = :topic"
                params["topic"] = topic_filter

            stmt = text(f"""
                SELECT DISTINCT ON (a.news_source, a.uri)
                    a.uri, a.title, a.summary, a.news_source,
                    a.publication_date, a.category,
                    COALESCE(n.composite_novelty_score, 50) as novelty_score
                FROM articles a
                LEFT JOIN article_novelty_scores n ON a.uri = n.article_uri
                WHERE a.publication_date::date >= CURRENT_DATE - :days_back
                AND a.summary IS NOT NULL
                AND LENGTH(a.summary) > 50
                {topic_clause}
                ORDER BY a.news_source, a.uri, COALESCE(n.composite_novelty_score, 50) DESC
            """)

            result = conn.execute(stmt, params)
            rows = [dict(row) for row in result.mappings()]

            # Sort by novelty and take top articles
            rows.sort(key=lambda x: x.get("novelty_score", 50), reverse=True)
            return rows[:max_articles]

        except Exception as exc:
            logger.error(f"Error fetching sample articles: {exc}")
            return []
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
    ) -> List[ProposedTheme]:
        """
        Use LLM to propose emerging themes from article sample.

        Returns list of ProposedTheme objects (without article assignments yet).
        """
        if not self.ai_model_getter:
            logger.warning("No AI model getter configured")
            return []

        # Fetch sample articles
        articles = self._fetch_sample_articles(
            topic_filter=topic_filter,
            days_back=days_back,
            max_articles=max_sample
        )

        if len(articles) < 5:
            logger.warning(f"Not enough articles ({len(articles)}) to propose themes")
            return []

        logger.info(f"Proposing themes from {len(articles)} sample articles")

        # Format prompt
        articles_text = self._format_articles_for_prompt(articles)
        prompt = THEME_PROPOSAL_PROMPT.format(
            n=len(articles),
            articles_summary=articles_text
        )

        # Call LLM
        model_to_use = model_name or self.default_model

        try:
            model = self.ai_model_getter(model_to_use)
            if not model:
                logger.error(f"Could not get AI model: {model_to_use}")
                return []

            if hasattr(model, 'generate'):
                response = await model.generate(prompt, max_tokens=2000)
            else:
                logger.error("Model does not have generate method")
                return []

            # Parse response
            parsed = self._parse_llm_response(response)
            if not parsed:
                return []

            # Convert to ProposedTheme objects
            themes = []
            proposed = parsed.get("proposed_themes", [])

            for theme_data in proposed:
                theme = ProposedTheme(
                    theme_label=theme_data.get("theme_label", "Unknown Theme"),
                    theme_description=theme_data.get("theme_description", ""),
                    search_query=theme_data.get("search_query", theme_data.get("theme_label", "")),
                    key_entities=theme_data.get("key_entities", []),
                    why_emerging=theme_data.get("why_emerging", ""),
                )
                themes.append(theme)

            logger.info(f"LLM proposed {len(themes)} themes")
            return themes

        except Exception as exc:
            logger.error(f"Error proposing themes: {exc}")
            return []

    async def _get_embedding(self, text: str) -> Optional[np.ndarray]:
        """Get embedding for text using pgvector's embedding function."""
        try:
            # Use the existing pgvector embedding function directly
            from app.vector_store_pgvector import _embed_texts

            embeddings = _embed_texts([text])
            if embeddings and len(embeddings) > 0:
                return np.array(embeddings[0])
            else:
                logger.error("Empty embedding returned")
                return None
        except Exception as exc:
            logger.error(f"Error getting embedding: {exc}")
            return None

    async def assign_articles_to_themes(
        self,
        themes: List[ProposedTheme],
        topic_filter: Optional[str] = None,
        days_back: int = 7,
        max_per_theme: int = 20,
        distance_threshold: float = 0.85
    ) -> List[ProposedTheme]:
        """
        Assign articles to themes using semantic search on search_query.

        For each theme, embed its search_query and find similar articles.
        """
        if not themes:
            return []

        conn = None
        try:
            conn = self._get_connection()

            for theme in themes:
                # Get embedding for search query
                query_embedding = await self._get_embedding(theme.search_query)
                if query_embedding is None:
                    logger.warning(f"Could not get embedding for theme: {theme.theme_label}")
                    continue

                # Convert to pgvector format
                embedding_str = "[" + ",".join([str(v) for v in query_embedding]) + "]"

                # Build query
                params = {
                    "query_embedding": embedding_str,
                    "days_back": days_back,
                    "threshold": distance_threshold,
                    "limit": max_per_theme
                }

                topic_clause = ""
                if topic_filter:
                    topic_clause = "AND topic = :topic"
                    params["topic"] = topic_filter

                # Use subquery with OFFSET 0 to force materialization and avoid HNSW index issue
                # The HNSW index doesn't work well with pre-filters (date, topic)
                stmt = text(f"""
                    SELECT * FROM (
                        SELECT uri, title, summary,
                               embedding <=> CAST(:query_embedding AS vector) as distance
                        FROM articles
                        WHERE publication_date::date >= CURRENT_DATE - CAST(:days_back AS INTEGER)
                        AND embedding IS NOT NULL
                        {topic_clause}
                        OFFSET 0
                    ) filtered
                    ORDER BY distance
                    LIMIT :limit
                """)

                result = conn.execute(stmt, params)

                theme.article_uris = []
                theme.article_distances = []

                for row in result.mappings():
                    distance = float(row["distance"])
                    if distance <= distance_threshold:
                        theme.article_uris.append(row["uri"])
                        theme.article_distances.append(distance)

                logger.info(
                    f"Theme '{theme.theme_label}': assigned {len(theme.article_uris)} articles "
                    f"(threshold={distance_threshold})"
                )

            return themes

        except Exception as exc:
            logger.error(f"Error assigning articles to themes: {exc}")
            return themes
        finally:
            if conn:
                conn.close()

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
        themes = await self.propose_themes(
            topic_filter=topic_filter,
            days_back=days_back,
            model_name=model_name,
            max_sample=max_sample
        )

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
