"""
Category Classification Service

Classifies articles into topic-specific categories using Qwen SLM via vLLM.
Zero-shot classification - no finetuning required.

Usage:
    from app.services.category_service import get_category_service

    service = get_category_service()
    result = service.classify_category(
        title="OpenAI Announces GPT-5...",
        summary="OpenAI has unveiled GPT-5...",
        categories=["AI Model Releases", "AI Research", "AI Regulation", ...]
    )
    # Returns: {
    #     "category": "AI Model Releases",
    #     "confidence": 0.95,
    #     "source": "qwen",
    #     "latency_ms": 150
    # }
"""

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# vLLM Configuration for Qwen
VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://localhost:8765/v1")
VLLM_MODEL = "Qwen/Qwen2.5-3B-Instruct"


class CategoryService:
    """
    SLM-based category classification service using Qwen.
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if CategoryService._initialized:
            return

        self._vllm_available = None
        self._vllm_checked = False

        CategoryService._initialized = True

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
                        logger.info(f"Category service available: {model.get('id')}")
                        return True
            self._vllm_available = False
            self._vllm_checked = True
            return False
        except Exception as e:
            logger.warning(f"vLLM check failed for category service: {e}")
            self._vllm_available = False
            self._vllm_checked = True
            return False

    def is_available(self) -> bool:
        """Check if category service is available."""
        return self._check_vllm_available()

    def reset_availability_check(self):
        """Reset the availability check to retry on next call."""
        self._vllm_checked = False
        self._vllm_available = None

    def classify_category(
        self,
        title: str,
        summary: str,
        categories: List[str],
        topic: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Classify an article into one of the provided categories.

        Args:
            title: Article title
            summary: Article summary
            categories: List of valid category names for this topic
            topic: Optional topic name for context

        Returns:
            Dict with category, confidence, source, and latency_ms
        """
        start_time = time.time()

        if not categories:
            return {
                "category": None,
                "confidence": 0.0,
                "source": "no_categories",
                "latency_ms": int((time.time() - start_time) * 1000),
                "error": "No categories provided",
            }

        if not self.is_available():
            return {
                "category": None,
                "confidence": 0.0,
                "source": "unavailable",
                "latency_ms": int((time.time() - start_time) * 1000),
                "error": "Category service not available",
            }

        # Build category list for prompt
        category_list = "\n".join(f"- {cat}" for cat in categories)

        topic_context = f" for the topic '{topic}'" if topic else ""

        prompt = f"""Classify this article into exactly ONE of the following categories{topic_context}:

{category_list}

Article Title: {title}

Article Summary: {summary}

Instructions:
1. Read the article carefully
2. Choose the SINGLE most appropriate category from the list above
3. Respond with ONLY the category name, exactly as written above
4. Do not add any explanation or additional text

Category:"""

        try:
            from litellm import completion

            response = completion(
                model=f"openai/{VLLM_MODEL}",
                api_base=VLLM_BASE_URL,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a news categorization assistant. Classify articles into the provided categories. Output only the category name, nothing else."
                    },
                    {"role": "user", "content": prompt}
                ],
                max_tokens=50,
                temperature=0.1,
            )

            response_text = response.choices[0].message.content.strip()

            # Clean up response - remove any extra text
            predicted_category = self._extract_category(response_text, categories)

            # Calculate confidence based on exact match
            confidence = 1.0 if predicted_category in categories else 0.5

            return {
                "category": predicted_category,
                "confidence": confidence,
                "source": "qwen",
                "latency_ms": int((time.time() - start_time) * 1000),
            }

        except Exception as e:
            logger.warning(f"Category classification failed: {e}")
            self._vllm_checked = False  # Reset for retry
            return {
                "category": None,
                "confidence": 0.0,
                "source": "error",
                "latency_ms": int((time.time() - start_time) * 1000),
                "error": str(e),
            }

    def _extract_category(self, response_text: str, valid_categories: List[str]) -> Optional[str]:
        """Extract category from response, handling common formatting issues."""
        # Clean up response
        response_clean = response_text.strip()

        # Remove common prefixes
        prefixes_to_remove = ["Category:", "category:", "The category is", "Answer:"]
        for prefix in prefixes_to_remove:
            if response_clean.startswith(prefix):
                response_clean = response_clean[len(prefix):].strip()

        # Try exact match first
        if response_clean in valid_categories:
            return response_clean

        # Try case-insensitive match
        response_lower = response_clean.lower()
        for cat in valid_categories:
            if cat.lower() == response_lower:
                return cat

        # Try partial match (category contained in response)
        for cat in valid_categories:
            if cat.lower() in response_lower or response_lower in cat.lower():
                return cat

        # Return cleaned response even if not in list (let caller handle)
        logger.warning(f"Category '{response_clean}' not in valid list: {valid_categories[:5]}...")
        return response_clean if response_clean else None

    def classify_batch(
        self,
        articles: List[Dict[str, str]],
        categories: List[str],
        topic: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Classify multiple articles.

        Args:
            articles: List of dicts with 'title' and 'summary'
            categories: List of valid category names
            topic: Optional topic name

        Returns:
            List of classification results
        """
        results = []
        for article in articles:
            result = self.classify_category(
                title=article.get("title", ""),
                summary=article.get("summary", ""),
                categories=categories,
                topic=topic,
            )
            results.append(result)
        return results

    def get_status(self) -> Dict[str, Any]:
        """Get service status information."""
        return {
            "available": self.is_available(),
            "vllm_url": VLLM_BASE_URL,
            "model": VLLM_MODEL,
        }


# Singleton accessor
_service_instance = None


def get_category_service() -> CategoryService:
    """Get the singleton category service."""
    global _service_instance
    if _service_instance is None:
        _service_instance = CategoryService()
    return _service_instance
