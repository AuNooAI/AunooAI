"""
Article Relevance Validator for Emerging Topics

Validates that semantically-assigned articles are truly relevant to themes.
Uses LLM to verify article-theme alignment after semantic search assignment.
"""

import json
from app.model_tiers import default_model
import logging
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Callable

logger = logging.getLogger(__name__)

VALIDATION_PROMPT = """You are validating whether articles truly belong to an emerging topic theme.

THEME:
Label: {theme_label}
Description: {theme_description}
Key Entities: {key_entities}

ARTICLES TO VALIDATE:
{articles_text}

For each article, determine if it is TRULY about this specific theme (not just tangentially related).
Be strict - only mark articles as relevant if they directly discuss the theme's core subject matter.
An article about the same industry or a neighbouring subject is NOT relevant.

Return a JSON array with one object per article, using the article's ID:
[
  {{"id": "A1", "relevant": true, "confidence": 0.95, "reason": "about the theme's event"}},
  {{"id": "A2", "relevant": false, "confidence": 0.85, "reason": "different company, same sector"}}
]

Important:
- Use the exact ID from the input, and judge every article
- Keep each reason under ten words
- confidence should be between 0.0 and 1.0
- Be conservative - when in doubt, mark as not relevant"""


@dataclass
class ValidationResult:
    """Result of validating a single article."""
    uri: str
    relevant: bool
    confidence: float
    reason: str


class ArticleValidator:
    """Validates article relevance to themes using LLM."""

    def __init__(
        self,
        ai_model_getter: Callable,
        model_name: str = default_model("standard")
    ):
        """
        Initialize the article validator.

        Args:
            ai_model_getter: Function to get AI model by name
            model_name: Name of the model to use for validation
        """
        self.ai_model_getter = ai_model_getter
        self.model_name = model_name

    # Articles per model call. Each batch is one prompt; every article the
    # caller passes in is judged.
    MAX_VALIDATED = 15

    async def validate_theme_articles(
        self,
        theme_label: str,
        theme_description: str,
        key_entities: List[str],
        articles: List[Dict[str, Any]],
        min_confidence: float = 0.7,
        ordered_uris: Optional[List[str]] = None,
    ) -> List[str]:
        """Keep only the articles the LLM approves, in their original order.

        Every article is judged, ``MAX_VALIDATED`` per model call. An article
        stays in the theme only on an explicit "relevant" verdict at or above
        ``min_confidence``. An article the model did not judge is dropped:
        the reply was cut off, unparseable, or the call failed.

        This used to fail open. It judged the first 15 articles and kept the
        rest unseen, and kept everything when the reply did not parse. On
        bugfixing on 7 Oct 2026 that left themes such as "Flydubai Flight
        Cockpit Incident" with 15 unjudged articles after all 15 judged ones
        were rejected, and the deep analysis then wrote timelines out of
        unrelated stories. A theme left with too few articles is dropped
        later by the theme validator, which is the right outcome.

        Args:
            theme_label: The theme name
            theme_description: Theme description
            key_entities: Key entities for the theme
            articles: Article dicts (uri, title, summary) to judge
            min_confidence: Confidence a "relevant" verdict needs to count
            ordered_uris: The theme's ranked URI list. Defaults to the URIs
                of ``articles``. The return value preserves this order; a
                URI absent from ``articles`` was not judged and is dropped.

        Returns:
            The approved URIs, in their original ranking order.
        """
        def uri_of(a: Dict[str, Any]) -> Optional[str]:
            return a.get('uri', a.get('article_uri'))

        articles = [a for a in articles if uri_of(a)]
        if ordered_uris is None:
            ordered_uris = [uri_of(a) for a in articles]
        if not articles:
            return []

        approved: set = set()
        for start in range(0, len(articles), self.MAX_VALIDATED):
            batch = articles[start:start + self.MAX_VALIDATED]
            approved |= await self._judge_batch(
                theme_label, theme_description, key_entities, batch, min_confidence
            )

        kept = [uri for uri in ordered_uris if uri in approved]
        logger.info(
            f"Validated {len(articles)} of {len(ordered_uris)} articles for "
            f"theme '{theme_label}': {len(kept)} approved, "
            f"{len(ordered_uris) - len(kept)} dropped"
        )
        return kept

    async def _judge_batch(
        self,
        theme_label: str,
        theme_description: str,
        key_entities: List[str],
        batch: List[Dict[str, Any]],
        min_confidence: float,
    ) -> set:
        """Return the URIs in one batch the model approves.

        Articles are labelled A1, A2, ... so the model echoes a short id
        rather than a long URL; the URL echo is what pushed replies past the
        token cap. One retry on an unparseable reply, then the batch counts
        as unjudged.
        """
        id_to_uri = {
            f"A{i}": a.get('uri', a.get('article_uri'))
            for i, a in enumerate(batch, 1)
        }
        articles_text = "\n".join(
            f"- ID: A{i}\n  Title: {a.get('title', 'N/A')}\n"
            f"  Summary: {str(a.get('summary', 'N/A'))[:300]}"
            for i, a in enumerate(batch, 1)
        )
        prompt = VALIDATION_PROMPT.format(
            theme_label=theme_label,
            theme_description=theme_description,
            key_entities=", ".join(key_entities) if key_entities else "None specified",
            articles_text=articles_text
        )

        for attempt in (1, 2):
            try:
                model = self.ai_model_getter(self.model_name)
                if hasattr(model, 'generate'):
                    response = await model.generate(prompt, max_tokens=3000)
                elif hasattr(model, 'generate_response'):
                    # Synchronous fallback
                    response = model.generate_response([{"role": "user", "content": prompt}])
                else:
                    logger.error("Model does not have generate or generate_response method")
                    return set()
            except Exception as e:
                logger.error(f"Validation error for theme '{theme_label}': {e}")
                return set()

            results = self._parse_response(response)
            if results:
                return {
                    id_to_uri[v.uri]
                    for v in results
                    if v.uri in id_to_uri
                    and v.relevant
                    and v.confidence >= min_confidence
                }
            logger.warning(
                f"Unparseable validation reply for theme '{theme_label}' "
                f"(attempt {attempt} of 2)"
            )

        return set()

    def _parse_response(self, response: Any) -> List[ValidationResult]:
        """Parse LLM response into ValidationResult list."""
        # Extract text from various response object types
        text = self._extract_text(response)

        if not text:
            logger.warning("Empty response from LLM")
            return []

        # Handle markdown code blocks
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            json_lines = []
            in_json = False
            for line in lines:
                if line.startswith("```"):
                    in_json = not in_json
                    continue
                if in_json:
                    json_lines.append(line)
            text = "\n".join(json_lines)

        # Find JSON array in response
        start_idx = text.find('[')
        end_idx = text.rfind(']') + 1

        if start_idx == -1 or end_idx == 0:
            logger.warning(f"No JSON array found in response: {text[:200]}")
            return []

        json_str = text[start_idx:end_idx]

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON response: {e}")
            return []

        results = []
        for item in data:
            if not isinstance(item, dict):
                continue

            results.append(ValidationResult(
                uri=str(item.get("id", item.get("uri", ""))),
                relevant=bool(item.get("relevant", False)),
                confidence=float(item.get("confidence", 0)),
                reason=str(item.get("reason", ""))
            ))

        return results

    def _extract_text(self, response: Any) -> str:
        """Extract text content from various response object types."""
        if isinstance(response, str):
            return response

        # LiteLLM/OpenAI response format
        if hasattr(response, 'message') and hasattr(response.message, 'content'):
            return response.message.content

        # OpenAI choices format
        if hasattr(response, 'choices') and response.choices:
            choice = response.choices[0]
            if hasattr(choice, 'message') and hasattr(choice.message, 'content'):
                return choice.message.content

        # Direct content attribute
        if hasattr(response, 'content'):
            if isinstance(response.content, str):
                return response.content
            if isinstance(response.content, list) and response.content:
                # Anthropic format
                first = response.content[0]
                if hasattr(first, 'text'):
                    return first.text

        # Fallback to string conversion
        return str(response)
