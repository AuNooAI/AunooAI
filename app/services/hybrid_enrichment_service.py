"""
Hybrid Enrichment Service

Routes between DeBERTa (finetuned) and GPT (bootstrap) based on training sample counts.
Stores GPT responses for training data collection.

Decision Logic (Simplified):
- samples >= 500 → Use DeBERTa (fast, accurate, no API cost)
- samples < 500 → Use GPT (gpt-4o-mini) + store sample for training

This simplified approach:
1. Uses GPT for quality classifications until enough training data exists
2. Automatically accumulates training samples from GPT responses
3. Switches to DeBERTa once 500+ samples collected (cost-free, fast)

Cost: ~$0.75 per topic to bootstrap 500 samples with gpt-4o-mini

Usage:
    from app.services.hybrid_enrichment_service import get_hybrid_enrichment_service

    service = get_hybrid_enrichment_service()
    result = await service.enrich_article(
        title="OpenAI Announces GPT-5",
        summary="OpenAI has unveiled GPT-5...",
        topic="AI and Machine Learning",
        article_uri="https://example.com/article"
    )
    # Returns: {
    #     "sentiment": "Positive",
    #     "time_to_impact": "Immediate",
    #     "driver_type": "accelerating",
    #     "future_signal": "Emerging",
    #     "sources": {
    #         "sentiment": "deberta",
    #         "time_to_impact": "gpt",
    #         ...
    #     }
    # }
"""

import logging
from typing import Any, Dict, List, Optional

from app.services.training_bootstrap_service import (
    get_training_bootstrap_service,
    TRAINING_THRESHOLDS,
    ENRICHMENT_FIELDS,
)
from app.services.enrichment_service import get_enrichment_service

logger = logging.getLogger(__name__)

# Threshold for switching from GPT to DeBERTa
DEBERTA_THRESHOLD = 500


class HybridEnrichmentService:
    """
    Routes between DeBERTa and GPT based on training sample counts.

    Simple two-tier approach:
    - GPT (gpt-4o-mini) for topics with < 500 samples
    - DeBERTa for topics with >= 500 samples
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if HybridEnrichmentService._initialized:
            return

        self._bootstrap_service = None
        self._deberta_service = None
        self._sample_counts_cache = {}
        self._cache_ttl = 60  # Cache sample counts for 60 seconds

        HybridEnrichmentService._initialized = True

    def _get_bootstrap_service(self):
        """Lazy-load bootstrap service (handles GPT classification + storage)."""
        if self._bootstrap_service is None:
            self._bootstrap_service = get_training_bootstrap_service()
        return self._bootstrap_service

    def _get_deberta_service(self):
        """Lazy-load DeBERTa enrichment service."""
        if self._deberta_service is None:
            self._deberta_service = get_enrichment_service()
        return self._deberta_service

    async def _get_sample_counts_for_topic(self, topic: str) -> Dict[str, int]:
        """Get sample counts for a topic, with caching."""
        import time

        cache_key = topic
        cached = self._sample_counts_cache.get(cache_key)

        if cached:
            counts, timestamp = cached
            if time.time() - timestamp < self._cache_ttl:
                return counts

        # Fetch fresh counts
        bootstrap = self._get_bootstrap_service()
        all_counts = await bootstrap.get_sample_counts(topic)
        counts = all_counts.get(topic, {})

        # Cache the result
        self._sample_counts_cache[cache_key] = (counts, time.time())

        return counts

    async def enrich_article(
        self,
        title: str,
        summary: str,
        topic: str,
        topic_config: Dict[str, List[str]] = None,
        article_uri: str = None,
        use_local_llm: bool = False,
    ) -> Dict[str, Any]:
        """
        Enrich article using the appropriate model for each field.

        Decision logic per field:
        - samples >= 500 → DeBERTa (trained model, fast, free)
        - samples < 500 → GPT (gpt-4o-mini, store for training) or Qwen (if use_local_llm=True)

        Args:
            title: Article title
            summary: Article summary
            topic: Topic name
            topic_config: Dict mapping field_name -> list of valid values
            article_uri: Article URI for storing bootstrap samples
            use_local_llm: If True, use local Qwen instead of GPT for bootstrapping

        Returns:
            Dict with enrichment values and sources tracking
        """
        result = {
            "topic": topic,
            "sources": {},
        }

        # Get sample counts for this topic
        sample_counts = await self._get_sample_counts_for_topic(topic)

        # Initialize services
        deberta = self._get_deberta_service()
        bootstrap = self._get_bootstrap_service()

        # Default topic config if not provided
        if topic_config is None:
            topic_config = self._get_default_topic_config()

        # Determine which model to use for each field
        deberta_fields = []
        gpt_fields = {}

        for field in ENRICHMENT_FIELDS:
            count = sample_counts.get(field, 0)

            if count >= DEBERTA_THRESHOLD:
                deberta_fields.append(field)
            else:
                gpt_fields[field] = topic_config.get(field, [])

        llm_type = "Qwen" if use_local_llm else "GPT"
        logger.info(
            f"Enrichment routing for '{topic}': "
            f"DeBERTa={deberta_fields}, {llm_type}={list(gpt_fields.keys())}"
        )

        # Process with DeBERTa (if available and fields assigned)
        if deberta_fields and deberta.is_available():
            try:
                deberta_result = deberta.enrich(title=title, summary=summary)
                for field in deberta_fields:
                    if field in deberta_result:
                        result[field] = deberta_result[field]
                        result["sources"][field] = "deberta"
                        # Store confidence if available
                        conf_key = f"{field}_confidence"
                        if conf_key in deberta_result:
                            result[conf_key] = deberta_result[conf_key]
            except Exception as e:
                logger.warning(f"DeBERTa enrichment failed, falling back to {llm_type}: {e}")
                # Move fields to LLM fallback
                for field in deberta_fields:
                    gpt_fields[field] = topic_config.get(field, [])

        # Process with LLM (GPT or Qwen depending on mode)
        if gpt_fields:
            try:
                if use_local_llm:
                    # Use local Qwen model
                    llm_result = self._classify_with_local_llm(
                        title=title,
                        summary=summary,
                        fields=list(gpt_fields.keys()),
                        valid_values=gpt_fields,
                    )
                    source_name = "qwen"
                else:
                    # Use GPT (stores samples for training)
                    llm_result = await bootstrap.bootstrap_classification(
                        article_uri=article_uri or "",
                        title=title,
                        summary=summary,
                        topic=topic,
                        fields=list(gpt_fields.keys()),
                        valid_values=gpt_fields,
                    )
                    source_name = "gpt"

                for field in gpt_fields:
                    if field in llm_result:
                        result[field] = llm_result[field]
                        result["sources"][field] = source_name
                        result[f"{field}_confidence"] = llm_result.get("confidence", 0.8)
            except Exception as e:
                logger.error(f"{llm_type} classification failed: {e}")

        # Fill in any missing fields with None
        for field in ENRICHMENT_FIELDS:
            if field not in result:
                result[field] = None
                result["sources"][field] = "unavailable"

        return result

    def _get_default_topic_config(self) -> Dict[str, List[str]]:
        """Get default valid values for each field."""
        return {
            "sentiment": ["Positive", "Negative", "Neutral", "Mixed"],
            "time_to_impact": ["Immediate", "Near-term", "Medium-term", "Long-term", "Uncertain"],
            "driver_type": ["accelerating", "constraining", "enabling", "disruptive", "stabilizing"],
            "future_signal": ["Emerging", "Evolving", "Established", "Declining", "Uncertain"],
        }

    def _classify_with_local_llm(
        self,
        title: str,
        summary: str,
        fields: List[str],
        valid_values: Dict[str, List[str]],
    ) -> Dict[str, Any]:
        """
        Classify article using local Qwen model (vLLM on port 8766).

        Used in local-only mode instead of GPT for bootstrapping.
        Note: Does NOT store samples for training (since we're avoiding external calls).

        Args:
            title: Article title
            summary: Article summary
            fields: List of fields to classify
            valid_values: Dict mapping field -> list of valid values

        Returns:
            Dict with classification values for each field
        """
        try:
            from litellm import completion
            import json

            VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://localhost:8000/v1")
            VLLM_MODEL = "Qwen/Qwen2.5-3B-Instruct"

            # Build classification prompt
            field_specs = []
            for field in fields:
                values = valid_values.get(field, [])
                field_specs.append(f'- {field}: one of {values}')

            prompt = f"""Classify this article for the following fields. Respond with JSON only.

Article Title: {title}
Article Summary: {summary}

Classify into these fields:
{chr(10).join(field_specs)}

Respond with ONLY a JSON object like: {{"sentiment": "...", "time_to_impact": "...", ...}}
No explanation, just JSON."""

            response = completion(
                model=f"openai/{VLLM_MODEL}",
                api_base=VLLM_BASE_URL,
                messages=[
                    {"role": "system", "content": "You are a news article classifier. Output only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=200,
                temperature=0.1,
            )

            response_text = response.choices[0].message.content.strip()

            # Try to parse JSON response
            try:
                # Handle markdown code blocks
                if response_text.startswith("```"):
                    response_text = response_text.split("```")[1]
                    if response_text.startswith("json"):
                        response_text = response_text[4:]
                    response_text = response_text.strip()

                result = json.loads(response_text)
                result["confidence"] = 0.7  # Lower confidence for local model
                logger.info(f"🏠 Local Qwen enrichment: {result}")
                return result

            except json.JSONDecodeError:
                logger.warning(f"Could not parse Qwen JSON response: {response_text}")
                return {"confidence": 0.0}

        except Exception as e:
            logger.error(f"Local LLM (Qwen) enrichment failed: {e}")
            return {"confidence": 0.0}

    async def get_routing_status(self, topic: str) -> Dict[str, Any]:
        """
        Get routing status for a topic - which model will be used for each field.

        Args:
            topic: Topic name

        Returns:
            Dict with routing information per field
        """
        sample_counts = await self._get_sample_counts_for_topic(topic)

        routing = {}
        for field in ENRICHMENT_FIELDS:
            count = sample_counts.get(field, 0)

            if count >= DEBERTA_THRESHOLD:
                model = "deberta"
                status = "ready"
            else:
                model = "gpt"
                status = "bootstrapping"

            samples_needed = max(0, DEBERTA_THRESHOLD - count)

            routing[field] = {
                "model": model,
                "status": status,
                "sample_count": count,
                "threshold": DEBERTA_THRESHOLD,
                "samples_needed": samples_needed,
                "progress_percent": min(100, int(count / DEBERTA_THRESHOLD * 100)),
            }

        return {
            "topic": topic,
            "fields": routing,
            "deberta_available": self._get_deberta_service().is_available(),
        }

    def get_status(self) -> Dict[str, Any]:
        """Get overall service status."""
        deberta = self._get_deberta_service()
        bootstrap = self._get_bootstrap_service()

        return {
            "deberta_available": deberta.is_available(),
            "deberta_threshold": DEBERTA_THRESHOLD,
            "enrichment_fields": ENRICHMENT_FIELDS,
            "bootstrap_model": bootstrap.get_bootstrap_model(),
        }


# Singleton accessor
_service_instance = None


def get_hybrid_enrichment_service() -> HybridEnrichmentService:
    """Get the singleton hybrid enrichment service."""
    global _service_instance
    if _service_instance is None:
        _service_instance = HybridEnrichmentService()
    return _service_instance
