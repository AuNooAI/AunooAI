"""
Summarization Service

Uses vLLM with Phi-3-mini as the primary summarizer for fast, local inference.
Falls back to the configured LLM model (from Gather settings) if vLLM is unavailable.

Usage:
    from app.services.summarization_service import get_summarization_service

    summarizer = get_summarization_service()
    result = summarizer.summarize(
        title="OpenAI launches GPT-5",
        content="OpenAI has announced the release of GPT-5..."
    )
    # Returns: {"summary": "OpenAI releases GPT-5 with...", "source": "vllm", "latency_ms": 2500}
"""

import logging
import time
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# vLLM Configuration
VLLM_BASE_URL = "http://localhost:8765/v1"
VLLM_MODEL = "microsoft/Phi-3-mini-4k-instruct"


class SummarizationService:
    """
    Summarization service using vLLM Phi-3-mini with LLM fallback.

    Features:
    - vLLM Phi-3-mini for fast local inference (~3s per summary)
    - Automatic fallback to configured LLM model
    - Batch processing support
    - Zero API cost for primary path
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        """Singleton pattern for efficient resource usage."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize the summarization service."""
        if SummarizationService._initialized:
            return

        self._vllm_available = None  # Lazy check
        self._vllm_checked = False

        SummarizationService._initialized = True

    def _check_vllm_available(self) -> bool:
        """Check if vLLM server is running and responsive."""
        if self._vllm_checked:
            return self._vllm_available

        try:
            import requests
            response = requests.get(f"{VLLM_BASE_URL}/models", timeout=5)
            if response.status_code == 200:
                models = response.json().get("data", [])
                # Check if our model is loaded
                for model in models:
                    if VLLM_MODEL in model.get("id", ""):
                        self._vllm_available = True
                        self._vllm_checked = True
                        logger.info(f"vLLM available with model: {VLLM_MODEL}")
                        return True
            self._vllm_available = False
            self._vllm_checked = True
            logger.warning(f"vLLM not available or model not loaded")
            return False
        except Exception as e:
            logger.warning(f"vLLM check failed: {e}")
            self._vllm_available = False
            self._vllm_checked = True
            return False

    def is_available(self) -> bool:
        """Check if summarizer is available (vLLM or fallback)."""
        # Always available since we have LLM fallback
        return True

    def get_status(self) -> Dict:
        """Get summarizer status and configuration."""
        return {
            "available": True,
            "vllm_available": self._check_vllm_available(),
            "vllm_url": VLLM_BASE_URL,
            "vllm_model": VLLM_MODEL,
            "fallback": "configured_llm",
        }

    def _summarize_with_vllm(self, title: str, content: str) -> Optional[Dict]:
        """
        Summarize using vLLM Phi-3-mini.

        Args:
            title: Article title
            content: Article content

        Returns:
            Dict with 'summary' and 'source', or None if failed
        """
        if not self._check_vllm_available():
            return None

        try:
            from litellm import completion

            # Truncate content if too long
            max_content = 3000
            if len(content) > max_content:
                content = content[:max_content] + "..."

            response = completion(
                model=f"openai/{VLLM_MODEL}",
                api_base=VLLM_BASE_URL,
                messages=[
                    {"role": "system", "content": "You are a news summarizer. Output only the summary, nothing else."},
                    {"role": "user", "content": f"Summarize in 2-3 sentences:\n\nTitle: {title}\n\nContent: {content}"}
                ],
                max_tokens=150,
                temperature=0.2,
            )

            summary = response.choices[0].message.content.strip()

            # Validate summary
            if len(summary) < 20:
                logger.warning(f"vLLM returned short summary: {summary}")
                return None

            return {
                "summary": summary,
                "source": "vllm",
            }

        except Exception as e:
            logger.warning(f"vLLM summarization failed: {e}")
            # Reset availability check for next time
            self._vllm_checked = False
            return None

    def _summarize_with_configured_llm(self, title: str, content: str) -> Dict:
        """
        Fallback summarization using the configured LLM from Gather settings.

        Args:
            title: Article title
            content: Article content

        Returns:
            Dict with 'summary' and 'source'
        """
        try:
            from litellm import completion
            from app.database import Database

            # Get configured model from database
            db = Database()
            configured_model = db.facade.get_configured_llm_model()

            if not configured_model:
                # Get first available model
                from app.ai_models import get_available_models
                available = get_available_models()
                if available and len(available) > 0:
                    configured_model = available[0].get('name')
                else:
                    configured_model = "gpt-5.4-mini"  # Ultimate fallback

            logger.info(f"Using fallback LLM for summarization: {configured_model}")

            # Truncate content if too long
            max_content = 4000
            if len(content) > max_content:
                content = content[:max_content] + "..."

            response = completion(
                model=configured_model,
                messages=[
                    {"role": "user", "content": f"Summarize the following article in 2-3 concise sentences.\n\nTitle: {title}\n\nContent:\n{content}\n\nSummary:"}
                ],
                max_tokens=200,
                temperature=0.3,
            )

            summary = response.choices[0].message.content.strip()

            return {
                "summary": summary,
                "source": "llm",
                "model": configured_model,
            }

        except Exception as e:
            logger.error(f"LLM fallback failed: {e}")
            # Return truncated content as last resort
            return {
                "summary": f"{title}. {content[:200]}...",
                "source": "fallback",
            }

    def summarize(
        self,
        title: str,
        content: str,
        max_length: Optional[int] = None,
        min_length: Optional[int] = None,
        num_beams: Optional[int] = None,
    ) -> Dict:
        """
        Generate a summary for an article.

        Primary: vLLM Phi-3-mini (fast, local, free)
        Fallback: Configured LLM from Gather settings

        Args:
            title: Article title
            content: Article content
            max_length: Ignored (kept for API compatibility)
            min_length: Ignored (kept for API compatibility)
            num_beams: Ignored (kept for API compatibility)

        Returns:
            Dict with 'summary' (str), 'source' ('vllm', 'llm', or 'fallback'), and 'latency_ms'
        """
        start_time = time.time()

        # Try vLLM first
        result = self._summarize_with_vllm(title, content)
        if result:
            result['latency_ms'] = int((time.time() - start_time) * 1000)
            return result

        # Fall back to configured LLM
        result = self._summarize_with_configured_llm(title, content)
        result['latency_ms'] = int((time.time() - start_time) * 1000)
        return result

    def summarize_batch(
        self,
        articles: List[Dict],
        max_length: Optional[int] = None,
        batch_size: int = 8,
    ) -> List[Dict]:
        """
        Generate summaries for multiple articles.

        Args:
            articles: List of dicts with 'title', 'content' keys
            max_length: Ignored (kept for API compatibility)
            batch_size: Ignored (vLLM handles batching internally)

        Returns:
            List of dicts with 'summary' and 'source'
        """
        results = []
        for article in articles:
            result = self.summarize(
                title=article.get("title", ""),
                content=article.get("content", "")
            )
            results.append(result)
        return results

    def reset_vllm_check(self):
        """Reset vLLM availability check to force re-check on next call."""
        self._vllm_checked = False
        self._vllm_available = None


# Singleton instance getter
_service_instance = None


def get_summarization_service() -> SummarizationService:
    """Get the singleton summarization service instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = SummarizationService()
    return _service_instance
