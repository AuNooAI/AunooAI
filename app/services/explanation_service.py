"""
Explanation Service

Generates explanations for article classifications using Qwen SLM via vLLM.
Explains WHY an article was classified with specific sentiment, time_to_impact,
driver_type, and future_signal values.

Usage:
    from app.services.explanation_service import get_explanation_service

    service = get_explanation_service()
    result = service.generate_explanations(
        title="...",
        summary="...",
        sentiment="Negative",
        time_to_impact="0-6 months",
        driver_type="Economic",
        future_signal="Accelerating Trend"
    )
    # Returns: {
    #     "sentiment_explanation": "The article uses negative language...",
    #     "time_to_impact_explanation": "The mention of 'this week'...",
    #     "driver_type_explanation": "The focus on layoffs...",
    #     "future_signal_explanation": "The phrase 'increasingly at risk'...",
    #     "source": "qwen",
    #     "latency_ms": 3500
    # }
"""

import json
import logging
import os
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# vLLM Configuration for Qwen (separate port from Phi-3)
VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://localhost:8000/v1")
VLLM_MODEL = "Qwen/Qwen2.5-3B-Instruct"


class ExplanationService:
    """
    SLM-based explanation generation service using Qwen.
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if ExplanationService._initialized:
            return

        self._vllm_available = None
        self._vllm_checked = False

        ExplanationService._initialized = True

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
                        logger.info(f"Explanation service available: {model.get('id')}")
                        return True
            self._vllm_available = False
            self._vllm_checked = True
            return False
        except Exception as e:
            logger.warning(f"vLLM check failed for explanation service: {e}")
            self._vllm_available = False
            self._vllm_checked = True
            return False

    def is_available(self) -> bool:
        """Check if explanation service is available."""
        return self._check_vllm_available()

    def reset_availability_check(self):
        """Reset the availability check to retry on next call."""
        self._vllm_checked = False
        self._vllm_available = None

    def generate_explanations(
        self,
        title: str,
        summary: str,
        sentiment: Optional[str] = None,
        time_to_impact: Optional[str] = None,
        driver_type: Optional[str] = None,
        future_signal: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate explanations for article classifications.

        Args:
            title: Article title
            summary: Article summary
            sentiment: Classified sentiment (e.g., "Positive", "Negative", "Neutral")
            time_to_impact: Classified time to impact (e.g., "0-6 months")
            driver_type: Classified driver type (e.g., "Technology", "Economic")
            future_signal: Classified future signal (e.g., "Emerging Trend")

        Returns:
            Dict with explanation fields and metadata
        """
        start_time = time.time()

        if not self.is_available():
            return {
                "sentiment_explanation": None,
                "time_to_impact_explanation": None,
                "driver_type_explanation": None,
                "future_signal_explanation": None,
                "source": "unavailable",
                "latency_ms": int((time.time() - start_time) * 1000),
                "error": "Explanation service not available",
            }

        # Build classification list for prompt
        classifications = []
        if sentiment:
            classifications.append(f"- Sentiment: {sentiment}")
        if time_to_impact:
            classifications.append(f"- Time to Impact: {time_to_impact}")
        if driver_type:
            classifications.append(f"- Driver Type: {driver_type}")
        if future_signal:
            classifications.append(f"- Future Signal: {future_signal}")

        if not classifications:
            return {
                "sentiment_explanation": None,
                "time_to_impact_explanation": None,
                "driver_type_explanation": None,
                "future_signal_explanation": None,
                "source": "no_classifications",
                "latency_ms": int((time.time() - start_time) * 1000),
            }

        classifications_str = "\n".join(classifications)

        # Build JSON template based on provided classifications
        json_fields = []
        if sentiment:
            json_fields.append(f'"sentiment_explanation": "What indicates {sentiment} sentiment"')
        if time_to_impact:
            json_fields.append(f'"time_to_impact_explanation": "What suggests {time_to_impact} timeframe"')
        if driver_type:
            json_fields.append(f'"driver_type_explanation": "What makes {driver_type} the primary driver"')
        if future_signal:
            json_fields.append(f'"future_signal_explanation": "What indicates {future_signal}"')

        json_template = "{\n  " + ",\n  ".join(json_fields) + "\n}"

        prompt = f"""Analyze this article and explain what indicates each classification. Write brief explanations (1-2 sentences) that help a reader understand the analysis.

Article Title: {title}

Article Summary: {summary}

Classifications:
{classifications_str}

For each, explain what in the article indicates this. Be specific - reference key phrases or facts.

Respond in JSON format only:
{json_template}"""

        try:
            from litellm import completion

            response = completion(
                model=f"openai/{VLLM_MODEL}",
                api_base=VLLM_BASE_URL,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a news analyst. Provide concise explanations for article classifications. Reference specific phrases or facts from the article. Output valid JSON only."
                    },
                    {"role": "user", "content": prompt}
                ],
                max_tokens=400,
                temperature=0.3,
            )

            response_text = response.choices[0].message.content.strip()
            result = self._parse_json_response(response_text)

            return {
                "sentiment_explanation": result.get("sentiment_explanation"),
                "time_to_impact_explanation": result.get("time_to_impact_explanation"),
                "driver_type_explanation": result.get("driver_type_explanation"),
                "future_signal_explanation": result.get("future_signal_explanation"),
                "source": "qwen",
                "latency_ms": int((time.time() - start_time) * 1000),
            }

        except Exception as e:
            logger.warning(f"Explanation generation failed: {e}")
            self._vllm_checked = False  # Reset for retry
            return {
                "sentiment_explanation": None,
                "time_to_impact_explanation": None,
                "driver_type_explanation": None,
                "future_signal_explanation": None,
                "source": "error",
                "latency_ms": int((time.time() - start_time) * 1000),
                "error": str(e),
            }

    def _parse_json_response(self, response_text: str) -> Dict[str, Any]:
        """Parse JSON response, handling common formatting issues."""
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            pass

        # Try to extract JSON from markdown code block
        if "```" in response_text:
            try:
                json_str = response_text.split("```")[1]
                if json_str.startswith("json"):
                    json_str = json_str[4:]
                return json.loads(json_str.strip())
            except (json.JSONDecodeError, IndexError):
                pass

        # Try to find JSON object in response
        try:
            start = response_text.find("{")
            end = response_text.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(response_text[start:end])
        except json.JSONDecodeError:
            pass

        logger.warning(f"Failed to parse explanation response: {response_text[:200]}")
        return {}

    def get_status(self) -> Dict[str, Any]:
        """Get service status information."""
        return {
            "available": self.is_available(),
            "vllm_url": VLLM_BASE_URL,
            "model": VLLM_MODEL,
        }


# Singleton accessor
_service_instance = None


def get_explanation_service() -> ExplanationService:
    """Get the singleton explanation service."""
    global _service_instance
    if _service_instance is None:
        _service_instance = ExplanationService()
    return _service_instance
