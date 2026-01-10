"""
Theme Validator Service

Validates and filters proposed themes:
- Minimum article count (≥3)
- Coherence check (avg pairwise distance < threshold)
- Duplicate detection and merging (>60% article overlap)

Ensures quality themes with truly related articles.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set
import numpy as np
from sqlalchemy import text

from app.database import get_database_instance

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of theme validation."""
    is_valid: bool
    reason: str = ""
    article_count: int = 0
    coherence_score: float = 0.0
    was_merged: bool = False
    merged_with: Optional[str] = None


class ThemeValidator:
    """
    Validates proposed themes for quality and merges duplicates.
    """

    def __init__(
        self,
        min_articles: int = 3,
        max_pairwise_distance: float = 0.40,
        merge_overlap_threshold: float = 0.60
    ):
        self.min_articles = min_articles
        self.max_pairwise_distance = max_pairwise_distance
        self.merge_overlap_threshold = merge_overlap_threshold

    def _get_connection(self):
        """Get database connection."""
        db = get_database_instance()
        return db._temp_get_connection()

    def _fetch_embeddings(
        self,
        article_uris: List[str]
    ) -> Dict[str, np.ndarray]:
        """Fetch embeddings for articles."""
        if not article_uris:
            return {}

        conn = None
        try:
            conn = self._get_connection()

            placeholders = ", ".join([f":uri_{i}" for i in range(len(article_uris))])
            params = {f"uri_{i}": uri for i, uri in enumerate(article_uris)}

            stmt = text(f"""
                SELECT uri, embedding
                FROM articles
                WHERE uri IN ({placeholders})
                AND embedding IS NOT NULL
            """)

            result = conn.execute(stmt, params)

            embeddings = {}
            for row in result.mappings():
                uri = row["uri"]
                emb_str = str(row["embedding"])
                emb_values = emb_str.strip("[]").split(",")
                embeddings[uri] = np.array([float(v) for v in emb_values])

            return embeddings

        except Exception as exc:
            logger.error(f"Error fetching embeddings for validation: {exc}")
            return {}
        finally:
            if conn:
                conn.close()

    def calculate_coherence(self, article_uris: List[str]) -> float:
        """
        Calculate average pairwise cosine distance between articles.

        Lower values mean more coherent (articles are similar).
        Returns 1.0 (worst) if cannot calculate.
        """
        if len(article_uris) < 2:
            return 0.0  # Single article is perfectly coherent

        embeddings = self._fetch_embeddings(article_uris)

        if len(embeddings) < 2:
            logger.warning("Could not fetch enough embeddings for coherence check")
            return 0.5  # Return middle value if we can't check

        # Calculate pairwise cosine distances
        uris = list(embeddings.keys())
        vectors = np.array([embeddings[uri] for uri in uris])

        # Normalize vectors
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        normalized = vectors / np.maximum(norms, 1e-10)

        # Cosine similarity matrix
        similarity_matrix = np.dot(normalized, normalized.T)

        # Convert to distance (1 - similarity)
        distance_matrix = 1 - similarity_matrix

        # Get upper triangle (excluding diagonal)
        upper_tri_indices = np.triu_indices(len(uris), k=1)
        pairwise_distances = distance_matrix[upper_tri_indices]

        if len(pairwise_distances) == 0:
            return 0.0

        avg_distance = float(np.mean(pairwise_distances))
        return avg_distance

    def calculate_overlap(
        self,
        theme1_uris: Set[str],
        theme2_uris: Set[str]
    ) -> float:
        """
        Calculate article overlap between two themes.

        Uses Jaccard similarity: intersection / union
        """
        if not theme1_uris or not theme2_uris:
            return 0.0

        intersection = len(theme1_uris & theme2_uris)
        union = len(theme1_uris | theme2_uris)

        if union == 0:
            return 0.0

        return intersection / union

    def validate_single(self, theme: Any) -> ValidationResult:
        """
        Validate a single theme.

        Args:
            theme: ProposedTheme object with article_uris

        Returns:
            ValidationResult with validity status and reason
        """
        result = ValidationResult(is_valid=True)

        article_uris = getattr(theme, 'article_uris', [])
        result.article_count = len(article_uris)

        # Check minimum articles
        if len(article_uris) < self.min_articles:
            result.is_valid = False
            result.reason = f"Too few articles ({len(article_uris)} < {self.min_articles})"
            return result

        # Check coherence
        coherence = self.calculate_coherence(article_uris)
        result.coherence_score = coherence

        if coherence > self.max_pairwise_distance:
            result.is_valid = False
            result.reason = f"Low coherence (avg distance {coherence:.3f} > {self.max_pairwise_distance})"
            return result

        result.reason = "Valid"
        return result

    def merge_themes(
        self,
        theme1: Any,
        theme2: Any
    ) -> Any:
        """
        Merge two themes into one.

        Combines article lists and keeps the label of the larger theme.
        """
        # Determine which theme is larger
        if len(theme1.article_uris) >= len(theme2.article_uris):
            primary = theme1
            secondary = theme2
        else:
            primary = theme2
            secondary = theme1

        # Combine article URIs (dedup)
        combined_uris = list(set(primary.article_uris) | set(secondary.article_uris))
        primary.article_uris = combined_uris

        # Combine key entities
        combined_entities = list(set(primary.key_entities) | set(secondary.key_entities))
        primary.key_entities = combined_entities[:10]  # Limit

        # Update description to note merge
        if secondary.theme_label not in primary.theme_description:
            primary.theme_description = f"{primary.theme_description} (merged with {secondary.theme_label})"

        logger.info(
            f"Merged theme '{secondary.theme_label}' into '{primary.theme_label}' "
            f"({len(combined_uris)} total articles)"
        )

        return primary

    def validate_and_merge(
        self,
        themes: List[Any]
    ) -> List[Any]:
        """
        Validate all themes and merge duplicates.

        Args:
            themes: List of ProposedTheme objects

        Returns:
            List of validated and merged themes
        """
        if not themes:
            return []

        # First pass: validate each theme
        valid_themes = []
        for theme in themes:
            result = self.validate_single(theme)

            if result.is_valid:
                valid_themes.append(theme)
                logger.info(
                    f"Theme '{theme.theme_label}' valid: "
                    f"{result.article_count} articles, coherence={result.coherence_score:.3f}"
                )
            else:
                logger.info(
                    f"Theme '{theme.theme_label}' invalid: {result.reason}"
                )

        # Second pass: merge overlapping themes
        merged_themes = []
        processed = set()

        for i, theme in enumerate(valid_themes):
            if i in processed:
                continue

            current = theme
            current_uris = set(theme.article_uris)

            # Look for themes to merge with
            for j in range(i + 1, len(valid_themes)):
                if j in processed:
                    continue

                other = valid_themes[j]
                other_uris = set(other.article_uris)

                overlap = self.calculate_overlap(current_uris, other_uris)

                if overlap >= self.merge_overlap_threshold:
                    logger.info(
                        f"Merging themes: '{current.theme_label}' and '{other.theme_label}' "
                        f"(overlap={overlap:.2f})"
                    )
                    current = self.merge_themes(current, other)
                    current_uris = set(current.article_uris)
                    processed.add(j)

            merged_themes.append(current)
            processed.add(i)

        logger.info(
            f"Validation complete: {len(themes)} proposed -> "
            f"{len(valid_themes)} valid -> {len(merged_themes)} after merge"
        )

        return merged_themes

    async def validate(self, themes: List[Any]) -> List[Any]:
        """
        Async wrapper for validate_and_merge.
        """
        return self.validate_and_merge(themes)
