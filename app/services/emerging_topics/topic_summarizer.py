"""
Topic Summarizer Service

Uses LLM to generate human-readable labels and descriptions for emerging topics.
Takes a sample of articles from a cluster and generates:
- Topic label (3-7 words)
- One-sentence description
- Key themes (2-4)
- Representative keywords (5-10)
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from sqlalchemy import text

from app.database import get_database_instance

logger = logging.getLogger(__name__)


SUMMARIZATION_PROMPT = """Analyze these {n} articles that form an emerging topic cluster. Identify what connects them.

Articles:
{articles_text}

Your task: Identify the SPECIFIC topic or event these articles share. Look for:
- Common actors (companies, people, organizations)
- Shared events or developments
- Related geographic regions
- Connected themes or issues

Provide a summary as valid JSON:

{{
    "label": "Specific descriptive title (e.g., 'DeepSeek AI Regulatory Scrutiny in Europe' not 'AI Developments')",
    "description": "One sentence explaining the specific development or trend these articles cover",
    "actors": ["List specific companies, people, or organizations mentioned across articles"],
    "themes": ["2-4 specific themes like 'regulatory compliance', 'market expansion'"],
    "keywords": ["5-10 specific terms that appear across articles"],
    "what_connects_them": "Explain specifically what these articles have in common"
}}

Requirements:
- Label MUST be specific, not generic. Bad: "AI News", Good: "OpenAI Enterprise Expansion Plans"
- Actors should be real entities mentioned in multiple articles
- Description should capture the specific shared development
- If articles don't seem related, say so in what_connects_them

Return ONLY the JSON object."""


@dataclass
class TopicSummary:
    """Result of topic summarization."""
    label: str
    description: str
    themes: List[str]
    keywords: List[str]
    emergence_rationale: str
    actors: List[str] = field(default_factory=list)
    model_used: str = ""
    article_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "description": self.description,
            "themes": self.themes,
            "keywords": self.keywords,
            "actors": self.actors,
            "emergence_rationale": self.emergence_rationale,
            "model_used": self.model_used,
            "article_count": self.article_count,
        }


class TopicSummarizer:
    """
    Generates topic labels and descriptions using LLM.
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
        max_articles: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Fetch article details for summarization.
        """
        if not article_uris:
            return []

        # Limit to max_articles
        uris_to_fetch = article_uris[:max_articles]

        conn = None
        try:
            conn = self._get_connection()

            placeholders = ", ".join([f":uri_{i}" for i in range(len(uris_to_fetch))])
            params = {f"uri_{i}": uri for i, uri in enumerate(uris_to_fetch)}

            stmt = text(f"""
                SELECT uri, title, summary, publication_date, news_source, category
                FROM articles
                WHERE uri IN ({placeholders})
            """)

            result = conn.execute(stmt, params)
            return [dict(row) for row in result.mappings()]

        except Exception as exc:
            logger.error(f"Error fetching articles: {exc}")
            return []
        finally:
            if conn:
                conn.close()

    def _format_articles_for_prompt(self, articles: List[Dict[str, Any]]) -> str:
        """
        Format articles for the LLM prompt.
        """
        formatted = []
        for i, article in enumerate(articles, 1):
            title = article.get("title", "Untitled")
            summary = article.get("summary", "No summary available")
            source = article.get("news_source", "Unknown")
            date = article.get("publication_date", "Unknown date")

            formatted.append(
                f"Article {i}:\n"
                f"Title: {title}\n"
                f"Source: {source} | Date: {date}\n"
                f"Summary: {summary}\n"
            )

        return "\n---\n".join(formatted)

    def _parse_llm_response(self, response: Any) -> Optional[Dict[str, Any]]:
        """
        Parse LLM response as JSON.
        """
        try:
            # Handle various response types
            if hasattr(response, 'message') and hasattr(response.message, 'content'):
                # LiteLLM Choice object (response.choices[0])
                response = response.message.content
            elif hasattr(response, 'choices'):
                # Full OpenAI-style response object
                response = response.choices[0].message.content
            elif hasattr(response, 'content') and isinstance(response.content, str):
                # Anthropic-style response
                response = response.content
            elif not isinstance(response, str):
                response = str(response)

            # Try to extract JSON from response
            response = response.strip()

            # Handle markdown code blocks
            if response.startswith("```"):
                lines = response.split("\n")
                # Remove first and last lines (```json and ```)
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
            logger.debug(f"Response was: {response[:500]}")
            return None

    async def summarize_cluster(
        self,
        article_uris: List[str],
        model_name: Optional[str] = None,
        max_articles: int = 10
    ) -> Optional[TopicSummary]:
        """
        Generate a summary for a cluster of articles.
        """
        if not article_uris:
            return None

        if not self.ai_model_getter:
            logger.warning("No AI model getter configured")
            return self._generate_fallback_summary(article_uris)

        # Fetch articles
        articles = self._fetch_articles(article_uris, max_articles)
        if not articles:
            return None

        # Format prompt
        articles_text = self._format_articles_for_prompt(articles)
        prompt = SUMMARIZATION_PROMPT.format(
            n=len(articles),
            articles_text=articles_text
        )

        # Call LLM
        model_to_use = model_name or self.default_model

        try:
            model = self.ai_model_getter(model_to_use)
            if not model:
                logger.error(f"Could not get AI model: {model_to_use}")
                return self._generate_fallback_summary(article_uris)

            if hasattr(model, 'generate'):
                response = await model.generate(prompt, max_tokens=1000)
            else:
                logger.error("Model does not have generate method")
                return self._generate_fallback_summary(article_uris)

            # Parse response
            parsed = self._parse_llm_response(response)
            if not parsed:
                return self._generate_fallback_summary(article_uris)

            return TopicSummary(
                label=parsed.get("label", "Unknown Topic"),
                description=parsed.get("description", "No description available"),
                themes=parsed.get("themes", []),
                keywords=parsed.get("keywords", []),
                actors=parsed.get("actors", []),
                emergence_rationale=parsed.get("what_connects_them", parsed.get("emergence_rationale", "")),
                model_used=model_to_use,
                article_count=len(articles),
            )

        except Exception as exc:
            logger.error(f"Error generating topic summary: {exc}")
            return self._generate_fallback_summary(article_uris)

    def _generate_fallback_summary(
        self,
        article_uris: List[str]
    ) -> TopicSummary:
        """
        Generate a basic fallback summary without LLM.
        """
        articles = self._fetch_articles(article_uris, 5)

        # Extract basic info
        titles = [a.get("title", "") for a in articles]
        categories = set(a.get("category", "") for a in articles if a.get("category"))

        # Simple keyword extraction from titles
        words = []
        for title in titles:
            words.extend(title.lower().split())

        # Filter common words
        common_words = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "is", "are", "was", "were"}
        keywords = [w for w in words if w not in common_words and len(w) > 3]

        # Get most common keywords
        from collections import Counter
        keyword_counts = Counter(keywords)
        top_keywords = [k for k, _ in keyword_counts.most_common(8)]

        return TopicSummary(
            label=f"Emerging Topic ({len(article_uris)} articles)",
            description=f"A cluster of {len(article_uris)} related articles.",
            themes=list(categories)[:4] if categories else ["General"],
            keywords=top_keywords,
            emergence_rationale="Cluster identified by semantic similarity.",
            model_used="fallback",
            article_count=len(article_uris),
        )

    async def batch_summarize(
        self,
        clusters: List[Dict[str, Any]],
        model_name: Optional[str] = None
    ) -> Dict[str, TopicSummary]:
        """
        Generate summaries for multiple clusters.

        Takes a list of dicts with 'cluster_id' and 'article_uris' keys.
        Returns dict mapping cluster_id to TopicSummary.
        """
        results = {}

        for cluster in clusters:
            cluster_id = cluster.get("cluster_id")
            article_uris = cluster.get("article_uris", [])

            if not cluster_id or not article_uris:
                continue

            summary = await self.summarize_cluster(
                article_uris,
                model_name=model_name
            )

            if summary:
                results[cluster_id] = summary

        logger.info(f"Generated summaries for {len(results)} clusters")
        return results

    def extract_key_themes(
        self,
        articles: List[Dict[str, Any]]
    ) -> List[str]:
        """
        Extract key themes from articles without LLM (basic extraction).
        """
        categories = set()
        for article in articles:
            if article.get("category"):
                categories.add(article["category"])

        return list(categories)[:4]
