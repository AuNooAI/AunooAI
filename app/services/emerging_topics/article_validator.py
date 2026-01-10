"""
Article Relevance Validator for Emerging Topics

Validates that semantically-assigned articles are truly relevant to themes.
Uses LLM to verify article-theme alignment after semantic search assignment.
"""

import json
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

Return a JSON array with one object per article:
[
  {{"uri": "article_uri_here", "relevant": true, "confidence": 0.95, "reason": "Directly discusses the theme"}},
  {{"uri": "another_uri", "relevant": false, "confidence": 0.85, "reason": "Only mentions theme tangentially"}}
]

Important:
- Use the exact URI from the input
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
        model_name: str = "gpt-4o"
    ):
        """
        Initialize the article validator.

        Args:
            ai_model_getter: Function to get AI model by name
            model_name: Name of the model to use for validation
        """
        self.ai_model_getter = ai_model_getter
        self.model_name = model_name

    async def validate_theme_articles(
        self,
        theme_label: str,
        theme_description: str,
        key_entities: List[str],
        articles: List[Dict[str, Any]],
        min_confidence: float = 0.7
    ) -> List[str]:
        """
        Validate articles and return URIs that pass validation.

        Args:
            theme_label: The theme name
            theme_description: Theme description
            key_entities: Key entities for the theme
            articles: List of article dicts with uri, title, summary
            min_confidence: Minimum confidence to keep article

        Returns:
            List of article URIs that are validated as relevant
        """
        if not articles:
            return []

        # Limit to 15 articles for token efficiency
        articles_to_validate = articles[:15]

        # Format articles for prompt
        articles_text = "\n".join([
            f"- URI: {a.get('uri', a.get('article_uri', 'unknown'))}\n  Title: {a.get('title', 'N/A')}\n  Summary: {str(a.get('summary', 'N/A'))[:300]}"
            for a in articles_to_validate
        ])

        prompt = VALIDATION_PROMPT.format(
            theme_label=theme_label,
            theme_description=theme_description,
            key_entities=", ".join(key_entities) if key_entities else "None specified",
            articles_text=articles_text
        )

        try:
            model = self.ai_model_getter(self.model_name)

            if hasattr(model, 'generate'):
                response = await model.generate(prompt, max_tokens=1500)
            elif hasattr(model, 'generate_response'):
                # Synchronous fallback
                response = model.generate_response([{"role": "user", "content": prompt}])
            else:
                logger.error("Model does not have generate or generate_response method")
                return [a.get('uri', a.get('article_uri')) for a in articles_to_validate]

            # Parse response
            results = self._parse_response(response)

            # Filter by confidence and relevance
            valid_uris = [
                r.uri for r in results
                if r.relevant and r.confidence >= min_confidence
            ]

            logger.info(
                f"Validated {len(valid_uris)}/{len(articles_to_validate)} articles "
                f"for theme '{theme_label}'"
            )

            # Return valid URIs plus any articles beyond the 15 we validated
            # (we assume they're okay since we couldn't validate them all)
            extra_uris = [
                a.get('uri', a.get('article_uri'))
                for a in articles[15:]
            ]

            return valid_uris + extra_uris

        except Exception as e:
            logger.error(f"Validation error for theme '{theme_label}': {e}")
            # On error, return all articles (fail open to avoid data loss)
            return [a.get('uri', a.get('article_uri')) for a in articles]

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
                uri=str(item.get("uri", "")),
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
