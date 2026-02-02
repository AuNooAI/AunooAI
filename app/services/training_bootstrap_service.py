"""
Training Bootstrap Service

Generates training samples using external LLM (gpt-4o-mini) for new topics/ontology values.
Tracks sample counts per topic/field for training readiness assessment.

Usage:
    from app.services.training_bootstrap_service import get_training_bootstrap_service

    service = get_training_bootstrap_service()

    # Bootstrap classification for an article
    result = await service.bootstrap_classification(
        article_uri="https://example.com/article",
        title="OpenAI Announces GPT-5",
        summary="OpenAI has unveiled GPT-5...",
        topic="AI and Machine Learning",
        fields=["sentiment", "time_to_impact", "driver_type", "future_signal"]
    )

    # Get sample counts
    counts = await service.get_sample_counts(topic="AI and Machine Learning")

    # Get training readiness status
    readiness = await service.get_training_readiness(topic="AI and Machine Learning")
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid

logger = logging.getLogger(__name__)

# Training thresholds (simplified two-tier: GPT -> DeBERTa)
TRAINING_THRESHOLDS = {
    "red": 500,       # < 500: use GPT (gpt-4o-mini) + store for training
    "yellow": 500,    # (kept for backward compatibility, same as red)
    "green": 500,     # 500+: ready for DeBERTa
    "min_per_class": 50,  # Minimum samples per class value
    "finetune_min": 1000  # Minimum total to trigger finetuning
}

# Enrichment fields we track
ENRICHMENT_FIELDS = ["sentiment", "time_to_impact", "driver_type", "future_signal"]


class TrainingBootstrapService:
    """
    Service for generating and tracking training samples using LLM.
    """

    _instance = None
    _initialized = False

    # Default bootstrap model - can be overridden via config
    DEFAULT_BOOTSTRAP_MODEL = "gpt-4o-mini"

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if TrainingBootstrapService._initialized:
            return

        self._db = None
        self._bootstrap_model = None  # Lazy-loaded from config
        TrainingBootstrapService._initialized = True

    def get_bootstrap_model(self) -> str:
        """
        Get the model name to use for bootstrap classification.

        Reads from database config (keyword_monitor_settings.default_llm_model)
        with fallback to DEFAULT_BOOTSTRAP_MODEL.

        Returns:
            Model name string (e.g., "gpt-4o-mini")
        """
        if self._bootstrap_model is None:
            try:
                db = self._get_db()
                configured = db.facade.get_configured_llm_model()
                if configured:
                    self._bootstrap_model = configured
                    logger.info(f"Bootstrap model configured from settings: {configured}")
                else:
                    self._bootstrap_model = self.DEFAULT_BOOTSTRAP_MODEL
                    logger.info(f"Using default bootstrap model: {self.DEFAULT_BOOTSTRAP_MODEL}")
            except Exception as e:
                logger.warning(f"Failed to get bootstrap model from config: {e}")
                self._bootstrap_model = self.DEFAULT_BOOTSTRAP_MODEL
        return self._bootstrap_model

    def set_bootstrap_model(self, model_name: str):
        """Override the bootstrap model (useful for testing)."""
        self._bootstrap_model = model_name
        logger.info(f"Bootstrap model manually set to: {model_name}")

    def _get_db(self):
        """Lazy-load database connection."""
        if self._db is None:
            from app.database import Database
            self._db = Database()
        return self._db

    async def bootstrap_classification(
        self,
        article_uri: str,
        title: str,
        summary: str,
        topic: str,
        fields: List[str] = None,
        valid_values: Dict[str, List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Use gpt-4o-mini to generate classifications and store for training.

        Args:
            article_uri: URI of the article
            title: Article title
            summary: Article summary
            topic: Topic name
            fields: Fields to classify (defaults to all enrichment fields)
            valid_values: Dict mapping field names to valid values

        Returns:
            Dict with classification results and metadata
        """
        if fields is None:
            fields = ENRICHMENT_FIELDS

        try:
            from app.ai_models import LiteLLMModel

            # Use configured bootstrap model
            model_name = self.get_bootstrap_model()
            model = LiteLLMModel.get_instance(model_name)

            # Build prompt for multi-field classification
            prompt = self._build_classification_prompt(
                title=title,
                summary=summary,
                topic=topic,
                fields=fields,
                valid_values=valid_values
            )

            response = model.generate(prompt, max_tokens=500, temperature=0.1)

            # Parse response
            results = self._parse_classification_response(response, fields, valid_values)
            results["model_used"] = model_name
            results["source"] = "llm_bootstrap"

            # Store samples in database
            await self._store_training_samples(
                article_uri=article_uri,
                topic=topic,
                results=results,
                model_used=model_name
            )

            logger.info(f"Bootstrapped {len(fields)} fields for {article_uri[:50]}")
            return results

        except Exception as e:
            logger.error(f"Bootstrap classification failed: {e}")
            return {
                "error": str(e),
                "source": "error"
            }

    def _build_classification_prompt(
        self,
        title: str,
        summary: str,
        topic: str,
        fields: List[str],
        valid_values: Dict[str, List[str]] = None,
    ) -> str:
        """Build prompt for multi-field classification."""
        valid_values = valid_values or {}

        field_instructions = []
        for field in fields:
            values = valid_values.get(field, [])
            if values:
                values_str = ", ".join(f'"{v}"' for v in values)
                field_instructions.append(f"- {field}: Choose from [{values_str}]")
            else:
                # Default values for standard fields
                if field == "sentiment":
                    field_instructions.append('- sentiment: Choose from ["Positive", "Negative", "Neutral", "Mixed"]')
                elif field == "time_to_impact":
                    field_instructions.append('- time_to_impact: Choose from ["Immediate", "Near-term", "Medium-term", "Long-term", "Uncertain"]')
                elif field == "driver_type":
                    field_instructions.append('- driver_type: Choose from ["accelerating", "constraining", "enabling", "disruptive", "stabilizing"]')
                elif field == "future_signal":
                    field_instructions.append('- future_signal: Choose from ["Emerging", "Evolving", "Established", "Declining", "Uncertain"]')

        field_list = "\n".join(field_instructions)

        return f"""Analyze this article and classify it according to the following fields:

Topic Context: {topic}

Article Title: {title}

Article Summary: {summary}

Classification Fields:
{field_list}

Instructions:
1. For each field, provide exactly one value from the allowed options
2. Consider the topic context when making classifications
3. Be consistent and accurate

Respond in JSON format:
{{
    "sentiment": "...",
    "time_to_impact": "...",
    "driver_type": "...",
    "future_signal": "...",
    "confidence": 0.0-1.0
}}

Response:"""

    def _parse_classification_response(
        self,
        response: str,
        fields: List[str],
        valid_values: Dict[str, List[str]] = None,
    ) -> Dict[str, Any]:
        """Parse LLM response to extract classifications."""
        import json

        result = {}
        valid_values = valid_values or {}

        try:
            # Try to parse as JSON
            response = response.strip()
            # Remove markdown code blocks if present
            if response.startswith("```"):
                lines = response.split("\n")
                response = "\n".join(lines[1:-1])

            parsed = json.loads(response)

            for field in fields:
                if field in parsed:
                    value = parsed[field]
                    # Validate against allowed values if provided
                    allowed = valid_values.get(field, [])
                    if allowed and value not in allowed:
                        # Try case-insensitive match
                        value_lower = value.lower()
                        for av in allowed:
                            if av.lower() == value_lower:
                                value = av
                                break
                    result[field] = value

            result["confidence"] = parsed.get("confidence", 0.8)

        except json.JSONDecodeError:
            # Fallback: try to extract values from text
            for field in fields:
                result[field] = self._extract_field_from_text(response, field, valid_values.get(field, []))
            result["confidence"] = 0.5

        return result

    def _extract_field_from_text(self, text: str, field: str, valid_values: List[str]) -> Optional[str]:
        """Extract a field value from unstructured text."""
        text_lower = text.lower()

        for value in valid_values:
            if value.lower() in text_lower:
                return value

        return None

    async def _store_training_samples(
        self,
        article_uri: str,
        topic: str,
        results: Dict[str, Any],
        model_used: str
    ):
        """Store training samples in database."""
        db = self._get_db()
        confidence = results.get("confidence", 0.8)

        with db.get_connection() as conn:
            cursor = conn.cursor()
            for field in ENRICHMENT_FIELDS:
                if field in results and results[field]:
                    try:
                        # Insert or update training sample
                        cursor.execute("""
                            INSERT INTO enrichment_training_samples
                            (article_uri, topic, field_name, field_value, source, model_used, confidence)
                            VALUES (:uri, :topic, :field, :value, :source, :model, :conf)
                            ON CONFLICT (article_uri, field_name)
                            DO UPDATE SET
                                field_value = EXCLUDED.field_value,
                                source = EXCLUDED.source,
                                model_used = EXCLUDED.model_used,
                                confidence = EXCLUDED.confidence,
                                created_at = NOW()
                        """, {
                            'uri': article_uri,
                            'topic': topic,
                            'field': field,
                            'value': results[field],
                            'source': 'llm_bootstrap',
                            'model': model_used,
                            'conf': confidence
                        })

                        # Update aggregated counts
                        await self._update_sample_counts(topic, field, results[field])

                    except Exception as e:
                        logger.warning(f"Failed to store training sample for {field}: {e}")

            conn.commit()

    async def _update_sample_counts(self, topic: str, field_name: str, field_value: str):
        """Update aggregated sample counts."""
        db = self._get_db()

        try:
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO training_sample_counts (topic, field_name, field_value, sample_count, last_updated)
                    VALUES (:topic, :field, :value, 1, NOW())
                    ON CONFLICT (topic, field_name, field_value)
                    DO UPDATE SET
                        sample_count = training_sample_counts.sample_count + 1,
                        last_updated = NOW()
                """, {'topic': topic, 'field': field_name, 'value': field_value})
                conn.commit()
        except Exception as e:
            logger.warning(f"Failed to update sample counts: {e}")

    async def get_sample_counts(self, topic: str = None) -> Dict[str, Dict[str, int]]:
        """
        Get sample counts per topic per field.

        Args:
            topic: Optional topic to filter by

        Returns:
            Dict mapping topic -> field -> count
        """
        db = self._get_db()

        try:
            with db.get_connection() as conn:
                cursor = conn.cursor()
                if topic:
                    cursor.execute("""
                        SELECT topic, field_name, SUM(sample_count) as total
                        FROM training_sample_counts
                        WHERE topic = :topic
                        GROUP BY topic, field_name
                        ORDER BY topic, field_name
                    """, {'topic': topic})
                else:
                    cursor.execute("""
                        SELECT topic, field_name, SUM(sample_count) as total
                        FROM training_sample_counts
                        GROUP BY topic, field_name
                        ORDER BY topic, field_name
                    """)

                rows = cursor.fetchall()

                counts = {}
                for row in rows:
                    topic_name = row[0]
                    field_name = row[1]
                    total = row[2]

                    if topic_name not in counts:
                        counts[topic_name] = {}
                    counts[topic_name][field_name] = int(total)

                return counts

        except Exception as e:
            logger.error(f"Failed to get sample counts: {e}")
            return {}

    async def get_sample_counts_by_value(self, topic: str, field_name: str) -> Dict[str, int]:
        """
        Get sample counts for each value of a field.

        Args:
            topic: Topic name
            field_name: Field name (sentiment, time_to_impact, etc.)

        Returns:
            Dict mapping field_value -> count
        """
        db = self._get_db()

        try:
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT field_value, sample_count
                    FROM training_sample_counts
                    WHERE topic = :topic AND field_name = :field
                    ORDER BY sample_count DESC
                """, {'topic': topic, 'field': field_name})

                rows = cursor.fetchall()
                return {row[0]: row[1] for row in rows}

        except Exception as e:
            logger.error(f"Failed to get sample counts by value: {e}")
            return {}

    async def get_training_readiness(self, topic: str) -> Dict[str, str]:
        """
        Get training readiness status for each field.

        Args:
            topic: Topic name

        Returns:
            Dict mapping field_name -> status ('red', 'yellow', 'green')
        """
        counts = await self.get_sample_counts(topic)
        topic_counts = counts.get(topic, {})

        readiness = {}
        for field in ENRICHMENT_FIELDS:
            count = topic_counts.get(field, 0)
            if count < TRAINING_THRESHOLDS["red"]:
                readiness[field] = "red"
            elif count < TRAINING_THRESHOLDS["yellow"]:
                readiness[field] = "yellow"
            else:
                readiness[field] = "green"

        return readiness

    async def get_all_topics_status(self) -> List[Dict[str, Any]]:
        """
        Get training status for all topics.

        Returns:
            List of topic status objects with sample counts and readiness
        """
        db = self._get_db()

        try:
            with db.get_connection() as conn:
                cursor = conn.cursor()
                # Get all unique topics from articles
                cursor.execute("""
                    SELECT DISTINCT topic, COUNT(*) as article_count
                    FROM articles
                    WHERE topic IS NOT NULL AND topic != ''
                    GROUP BY topic
                    ORDER BY article_count DESC
                """)
                topics_rows = cursor.fetchall()

            # Get sample counts
            all_counts = await self.get_sample_counts()

            results = []
            for row in topics_rows:
                topic = row[0]
                article_count = row[1]
                topic_counts = all_counts.get(topic, {})

                # Calculate readiness for each field
                readiness = await self.get_training_readiness(topic)

                # Calculate total samples
                total_samples = sum(topic_counts.values())

                # Determine overall status
                statuses = list(readiness.values())
                if all(s == "green" for s in statuses):
                    overall_status = "ready"
                elif any(s == "green" for s in statuses):
                    overall_status = "partial"
                elif any(s == "yellow" for s in statuses):
                    overall_status = "marginal"
                else:
                    overall_status = "not_ready"

                results.append({
                    "topic": topic,
                    "article_count": article_count,
                    "total_samples": total_samples,
                    "field_counts": topic_counts,
                    "field_readiness": readiness,
                    "overall_status": overall_status,
                })

            return results

        except Exception as e:
            logger.error(f"Failed to get all topics status: {e}")
            return []

    async def get_field_distribution(self, topic: str, field_name: str) -> Dict[str, Any]:
        """
        Get distribution of values for a specific field.

        Args:
            topic: Topic name
            field_name: Field name

        Returns:
            Dict with value distribution and statistics
        """
        value_counts = await self.get_sample_counts_by_value(topic, field_name)
        total = sum(value_counts.values())

        distribution = []
        for value, count in sorted(value_counts.items(), key=lambda x: -x[1]):
            distribution.append({
                "value": value,
                "count": count,
                "percentage": round(count / total * 100, 1) if total > 0 else 0
            })

        return {
            "topic": topic,
            "field_name": field_name,
            "total_samples": total,
            "unique_values": len(value_counts),
            "distribution": distribution,
            "min_per_class_met": all(c >= TRAINING_THRESHOLDS["min_per_class"] for c in value_counts.values()) if value_counts else False
        }

    def get_thresholds(self) -> Dict[str, int]:
        """Get the current training thresholds."""
        return TRAINING_THRESHOLDS.copy()


# Singleton accessor
_service_instance = None


def get_training_bootstrap_service() -> TrainingBootstrapService:
    """Get the singleton training bootstrap service."""
    global _service_instance
    if _service_instance is None:
        _service_instance = TrainingBootstrapService()
    return _service_instance
