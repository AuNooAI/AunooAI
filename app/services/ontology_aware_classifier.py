"""
Ontology-Aware Classifier

Qwen-based zero-shot classifier for dynamic ontology values.
Used when DeBERTa doesn't have enough training data for a topic/field.

Supports topic-specific ontology values that can be different per topic.

Usage:
    from app.services.ontology_aware_classifier import get_ontology_aware_classifier

    classifier = get_ontology_aware_classifier()
    result = classifier.classify_field(
        title="OpenAI Announces GPT-5",
        summary="OpenAI has unveiled GPT-5...",
        field_name="sentiment",
        valid_values=["Positive", "Negative", "Neutral", "Mixed"],
        topic="AI and Machine Learning"
    )
    # Returns: {
    #     "value": "Positive",
    #     "confidence": 0.95,
    #     "source": "qwen",
    #     "latency_ms": 150
    # }
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# vLLM Configuration for Qwen
VLLM_BASE_URL = "http://localhost:8766/v1"
VLLM_MODEL = "Qwen/Qwen2.5-3B-Instruct"

# Field descriptions for better classification
FIELD_DESCRIPTIONS = {
    "sentiment": "The overall emotional tone or attitude expressed in the article",
    "time_to_impact": "How soon the topic/event discussed will have real-world effects",
    "driver_type": "The nature of how this development affects change in its domain",
    "future_signal": "The stage of emergence or evolution of the trend/technology discussed",
}


class OntologyAwareClassifier:
    """
    SLM-based zero-shot classifier for dynamic ontology values.
    Uses Qwen via vLLM for inference.
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if OntologyAwareClassifier._initialized:
            return

        self._vllm_available = None
        self._vllm_checked = False

        OntologyAwareClassifier._initialized = True

    def _check_vllm_available(self) -> bool:
        """Check if vLLM server with Qwen is running."""
        if self._vllm_checked:
            return self._vllm_available

        try:
            import requests
            response = requests.get(f"{VLLM_BASE_URL}/models", timeout=5)
            if response.status_code == 200:
                models = response.json().get("data", [])
                for model in models:
                    if "Qwen" in model.get("id", ""):
                        self._vllm_available = True
                        self._vllm_checked = True
                        logger.info(f"Ontology classifier available: {model.get('id')}")
                        return True
            self._vllm_available = False
            self._vllm_checked = True
            return False
        except Exception as e:
            logger.warning(f"vLLM check failed for ontology classifier: {e}")
            self._vllm_available = False
            self._vllm_checked = True
            return False

    def is_available(self) -> bool:
        """Check if classifier is available."""
        return self._check_vllm_available()

    def reset_availability_check(self):
        """Reset the availability check to retry on next call."""
        self._vllm_checked = False
        self._vllm_available = None

    def classify_field(
        self,
        title: str,
        summary: str,
        field_name: str,
        valid_values: List[str],
        topic: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Classify a single field using zero-shot prompting.

        Args:
            title: Article title
            summary: Article summary
            field_name: The field to classify (sentiment, time_to_impact, etc.)
            valid_values: List of valid values for this field
            topic: Optional topic name for context

        Returns:
            Dict with value, confidence, source, and latency_ms
        """
        start_time = time.time()

        if not valid_values:
            return {
                "value": None,
                "confidence": 0.0,
                "source": "no_values",
                "latency_ms": int((time.time() - start_time) * 1000),
                "error": "No valid values provided",
            }

        if not self.is_available():
            return {
                "value": None,
                "confidence": 0.0,
                "source": "unavailable",
                "latency_ms": int((time.time() - start_time) * 1000),
                "error": "Ontology classifier not available",
            }

        # Build values list for prompt
        values_list = "\n".join(f"- {v}" for v in valid_values)
        field_description = FIELD_DESCRIPTIONS.get(field_name, f"The {field_name} classification")

        topic_context = f" in the context of '{topic}'" if topic else ""

        prompt = f"""Classify this article's {field_name}{topic_context}.

{field_description}.

Valid values:
{values_list}

Article Title: {title}

Article Summary: {summary}

Instructions:
1. Read the article carefully
2. Choose the SINGLE most appropriate {field_name} value from the list above
3. Respond with ONLY the value, exactly as written above
4. Do not add any explanation or additional text

{field_name.replace('_', ' ').title()}:"""

        try:
            from litellm import completion

            response = completion(
                model=f"openai/{VLLM_MODEL}",
                api_base=VLLM_BASE_URL,
                messages=[
                    {
                        "role": "system",
                        "content": f"You are a news classification assistant. Classify articles by their {field_name}. Output only the value, nothing else."
                    },
                    {"role": "user", "content": prompt}
                ],
                max_tokens=50,
                temperature=0.1,
            )

            response_text = response.choices[0].message.content.strip()

            # Clean up and extract value
            predicted_value = self._extract_value(response_text, valid_values)

            # Calculate confidence based on exact match
            confidence = 1.0 if predicted_value in valid_values else 0.5

            return {
                "value": predicted_value,
                "confidence": confidence,
                "source": "qwen",
                "latency_ms": int((time.time() - start_time) * 1000),
            }

        except Exception as e:
            logger.warning(f"Field classification failed for {field_name}: {e}")
            self._vllm_checked = False  # Reset for retry
            return {
                "value": None,
                "confidence": 0.0,
                "source": "error",
                "latency_ms": int((time.time() - start_time) * 1000),
                "error": str(e),
            }

    def _extract_value(self, response_text: str, valid_values: List[str]) -> Optional[str]:
        """Extract value from response, handling common formatting issues."""
        response_clean = response_text.strip()

        # Remove common prefixes
        prefixes_to_remove = [":", "Answer:", "Value:", "The value is", "Result:"]
        for prefix in prefixes_to_remove:
            if response_clean.startswith(prefix):
                response_clean = response_clean[len(prefix):].strip()

        # Try exact match first
        if response_clean in valid_values:
            return response_clean

        # Try case-insensitive match
        response_lower = response_clean.lower()
        for val in valid_values:
            if val.lower() == response_lower:
                return val

        # Try partial match
        for val in valid_values:
            if val.lower() in response_lower or response_lower in val.lower():
                return val

        # Return cleaned response even if not in list
        logger.warning(f"Value '{response_clean}' not in valid list: {valid_values[:5]}...")
        return response_clean if response_clean else None

    def classify_all_fields(
        self,
        title: str,
        summary: str,
        topic_config: Dict[str, List[str]],
        topic: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Classify all 4 enrichment fields in a single LLM call.

        Args:
            title: Article title
            summary: Article summary
            topic_config: Dict mapping field_name -> list of valid values
            topic: Optional topic name

        Returns:
            Dict with all field classifications and metadata
        """
        start_time = time.time()

        if not self.is_available():
            return {
                "success": False,
                "source": "unavailable",
                "latency_ms": int((time.time() - start_time) * 1000),
                "error": "Ontology classifier not available",
            }

        # Build multi-field prompt
        field_sections = []
        for field_name, valid_values in topic_config.items():
            if valid_values:
                values_str = ", ".join(f'"{v}"' for v in valid_values)
                desc = FIELD_DESCRIPTIONS.get(field_name, f"The {field_name}")
                field_sections.append(f"- {field_name} ({desc}): Choose from [{values_str}]")

        if not field_sections:
            return {
                "success": False,
                "source": "no_config",
                "latency_ms": int((time.time() - start_time) * 1000),
                "error": "No field configuration provided",
            }

        fields_list = "\n".join(field_sections)
        topic_context = f" for the topic '{topic}'" if topic else ""

        prompt = f"""Classify this article{topic_context} according to the following fields:

{fields_list}

Article Title: {title}

Article Summary: {summary}

Instructions:
1. For each field, choose exactly ONE value from the allowed options
2. Consider the context carefully
3. Be consistent and accurate

Respond in JSON format only:
{{
    "sentiment": "...",
    "time_to_impact": "...",
    "driver_type": "...",
    "future_signal": "..."
}}"""

        try:
            from litellm import completion

            response = completion(
                model=f"openai/{VLLM_MODEL}",
                api_base=VLLM_BASE_URL,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a news classification assistant. Classify articles according to the provided fields. Output only valid JSON."
                    },
                    {"role": "user", "content": prompt}
                ],
                max_tokens=200,
                temperature=0.1,
            )

            response_text = response.choices[0].message.content.strip()

            # Parse JSON response
            result = self._parse_multi_field_response(response_text, topic_config)
            result["success"] = True
            result["source"] = "qwen"
            result["latency_ms"] = int((time.time() - start_time) * 1000)

            return result

        except Exception as e:
            logger.warning(f"Multi-field classification failed: {e}")
            self._vllm_checked = False
            return {
                "success": False,
                "source": "error",
                "latency_ms": int((time.time() - start_time) * 1000),
                "error": str(e),
            }

    def _parse_multi_field_response(
        self,
        response_text: str,
        topic_config: Dict[str, List[str]]
    ) -> Dict[str, Any]:
        """Parse multi-field JSON response."""
        result = {"fields": {}}

        try:
            # Clean up response
            response = response_text.strip()
            if response.startswith("```"):
                lines = response.split("\n")
                response = "\n".join(lines[1:-1])

            parsed = json.loads(response)

            for field_name, valid_values in topic_config.items():
                if field_name in parsed:
                    value = parsed[field_name]
                    # Validate against allowed values
                    validated = self._extract_value(str(value), valid_values)
                    confidence = 1.0 if validated in valid_values else 0.5
                    result["fields"][field_name] = {
                        "value": validated,
                        "confidence": confidence
                    }

        except json.JSONDecodeError:
            logger.warning(f"Failed to parse multi-field response: {response_text[:100]}")
            # Try to extract individual fields from text
            for field_name, valid_values in topic_config.items():
                extracted = self._extract_value(response_text, valid_values)
                if extracted:
                    result["fields"][field_name] = {
                        "value": extracted,
                        "confidence": 0.3
                    }

        return result

    def get_status(self) -> Dict[str, Any]:
        """Get service status information."""
        return {
            "available": self.is_available(),
            "vllm_url": VLLM_BASE_URL,
            "model": VLLM_MODEL,
            "supported_fields": list(FIELD_DESCRIPTIONS.keys()),
        }


# Singleton accessor
_classifier_instance = None


def get_ontology_aware_classifier() -> OntologyAwareClassifier:
    """Get the singleton ontology-aware classifier."""
    global _classifier_instance
    if _classifier_instance is None:
        _classifier_instance = OntologyAwareClassifier()
    return _classifier_instance
