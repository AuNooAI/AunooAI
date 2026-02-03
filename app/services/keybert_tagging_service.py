"""
KeyBERT Tagging Service

Extracts keywords/tags from articles using KeyBERT with MiniLM embeddings.
Uses MMR (Maximal Marginal Relevance) for diverse, non-redundant tags.

Hybrid mode: KeyBERT extracts candidates, then Phi-3 (vLLM) refines them
and extracts named entities (people, organizations, locations).

Usage:
    from app.services.keybert_tagging_service import get_keybert_tagging_service

    service = get_keybert_tagging_service()

    # Fast KeyBERT-only extraction
    result = service.extract_tags(title="...", summary="...")

    # Hybrid: KeyBERT + SLM refinement + NER
    result = service.extract_tags_hybrid(title="...", summary="...")
    # Returns: {
    #     "tags": ["Bitcoin", "cryptocurrency", "investment"],
    #     "entities": {
    #         "people": ["Michael Saylor"],
    #         "organizations": ["Strategy", "MicroStrategy"],
    #         "locations": []
    #     },
    #     "source": "hybrid",
    #     "latency_ms": 450
    # }
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Use same embedding model as hybrid_relevance_service
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# vLLM Configuration (same as summarization_service)
VLLM_BASE_URL = "http://localhost:8765/v1"
VLLM_MODEL = "microsoft/Phi-3-mini-4k-instruct"

# Default extraction parameters
DEFAULT_TOP_N = 5
DEFAULT_DIVERSITY = 0.7
DEFAULT_MIN_SCORE = 0.3
DEFAULT_NGRAM_RANGE = (1, 2)


class KeyBERTTaggingService:
    """
    KeyBERT-based keyword extraction service with optional SLM refinement.
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if KeyBERTTaggingService._initialized:
            return

        self.keybert_model = None
        self.embedding_model = None
        self._loaded = False
        self._vllm_available = None
        self._vllm_checked = False

        KeyBERTTaggingService._initialized = True

    def _load_model(self) -> bool:
        """Load KeyBERT with MiniLM embedding model."""
        if self._loaded:
            return True

        try:
            from keybert import KeyBERT
            from sentence_transformers import SentenceTransformer

            logger.info(f"Loading KeyBERT with embedding model: {EMBEDDING_MODEL}")

            # Disable meta tensor lazy loading to avoid CPU loading issues
            self.embedding_model = SentenceTransformer(
                EMBEDDING_MODEL,
                model_kwargs={'low_cpu_mem_usage': False}
            )

            # Initialize KeyBERT with the embedding model
            self.keybert_model = KeyBERT(model=self.embedding_model)

            self._loaded = True
            logger.info("KeyBERT tagging service loaded successfully")
            return True

        except ImportError as e:
            logger.warning(f"KeyBERT not installed: {e}. Run: pip install keybert")
            return False
        except Exception as e:
            logger.error(f"Failed to load KeyBERT model: {e}")
            return False

    def _check_vllm_available(self) -> bool:
        """Check if vLLM server is running."""
        if self._vllm_checked:
            return self._vllm_available

        try:
            import requests
            response = requests.get(f"{VLLM_BASE_URL}/models", timeout=5)
            if response.status_code == 200:
                models = response.json().get("data", [])
                for model in models:
                    if VLLM_MODEL in model.get("id", ""):
                        self._vllm_available = True
                        self._vllm_checked = True
                        logger.info(f"vLLM available for tagging: {VLLM_MODEL}")
                        return True
            self._vllm_available = False
            self._vllm_checked = True
            return False
        except Exception as e:
            logger.warning(f"vLLM check failed: {e}")
            self._vllm_available = False
            self._vllm_checked = True
            return False

    def is_available(self) -> bool:
        """Check if KeyBERT service is available."""
        if not self._loaded:
            return self._load_model()
        return self._loaded

    def is_hybrid_available(self) -> bool:
        """Check if hybrid mode (KeyBERT + vLLM) is available."""
        return self.is_available() and self._check_vllm_available()

    def extract_tags(
        self,
        title: str,
        summary: str,
        content: Optional[str] = None,
        top_n: int = DEFAULT_TOP_N,
        diversity: float = DEFAULT_DIVERSITY,
        min_score: float = DEFAULT_MIN_SCORE,
        ngram_range: tuple = DEFAULT_NGRAM_RANGE,
    ) -> Dict[str, Any]:
        """
        Extract keywords/tags using KeyBERT only (fast, but lower quality).

        Args:
            title: Article title
            summary: Article summary
            content: Optional full article content
            top_n: Number of tags to extract
            diversity: MMR diversity factor 0-1
            min_score: Minimum confidence threshold
            ngram_range: Tuple of (min, max) n-gram length

        Returns:
            Dict with tags, scores, source, and latency_ms
        """
        start_time = time.time()

        if not self.is_available():
            return {
                "tags": [],
                "scores": [],
                "source": "keybert_unavailable",
                "latency_ms": int((time.time() - start_time) * 1000),
                "error": "KeyBERT service not available",
            }

        # Combine text for extraction
        doc = f"{title}. {summary}"
        if content:
            max_content_chars = 2000
            truncated_content = content[:max_content_chars] if len(content) > max_content_chars else content
            doc = f"{title}. {summary} {truncated_content}"

        try:
            keywords = self.keybert_model.extract_keywords(
                doc,
                keyphrase_ngram_range=ngram_range,
                stop_words="english",
                use_mmr=True,
                diversity=diversity,
                top_n=top_n + 2,
            )

            filtered_keywords = [
                (kw, score) for kw, score in keywords if score >= min_score
            ][:top_n]

            tags = [kw for kw, _ in filtered_keywords]
            scores = [round(score, 4) for _, score in filtered_keywords]

            return {
                "tags": tags,
                "scores": scores,
                "source": "keybert",
                "latency_ms": int((time.time() - start_time) * 1000),
            }

        except Exception as e:
            logger.error(f"KeyBERT extraction failed: {e}")
            return {
                "tags": [],
                "scores": [],
                "source": "keybert_error",
                "latency_ms": int((time.time() - start_time) * 1000),
                "error": str(e),
            }

    def extract_tags_hybrid(
        self,
        title: str,
        summary: str,
        content: Optional[str] = None,
        top_n: int = DEFAULT_TOP_N,
    ) -> Dict[str, Any]:
        """
        Extract tags using KeyBERT + SLM refinement + NER.

        Process:
        1. KeyBERT extracts keyword candidates
        2. Phi-3 (vLLM) refines tags and extracts named entities

        Args:
            title: Article title
            summary: Article summary
            content: Optional full article content
            top_n: Number of tags to return

        Returns:
            Dict with:
                - tags: List of refined semantic tags
                - entities: Dict with people, organizations, locations
                - keybert_candidates: Raw KeyBERT extractions
                - source: "hybrid" or fallback source
                - latency_ms: Total processing time
        """
        start_time = time.time()

        # Step 1: Extract KeyBERT candidates
        keybert_result = self.extract_tags(
            title=title,
            summary=summary,
            content=content,
            top_n=10,  # Get more candidates for SLM to choose from
            ngram_range=(1, 3),  # Wider range for more options
            min_score=0.2,  # Lower threshold, let SLM filter
        )

        keybert_candidates = keybert_result.get("tags", [])
        keybert_time = keybert_result.get("latency_ms", 0)

        # Step 2: Use vLLM to refine tags and extract entities
        if not self._check_vllm_available():
            # Fallback to KeyBERT-only
            return {
                "tags": keybert_candidates[:top_n],
                "entities": {"people": [], "organizations": [], "locations": []},
                "keybert_candidates": keybert_candidates,
                "source": "keybert_only",
                "latency_ms": int((time.time() - start_time) * 1000),
            }

        try:
            from litellm import completion

            # Build prompt for SLM
            prompt = f"""Analyze this news article and extract:
1. Tags: {top_n} relevant topic tags (single words or short phrases)
2. Entities: Named entities (people, organizations, locations)

Article Title: {title}

Article Summary: {summary}

KeyBERT keyword candidates: {', '.join(keybert_candidates)}

Respond in JSON format only:
{{
  "tags": ["tag1", "tag2", ...],
  "people": ["Person Name", ...],
  "organizations": ["Org Name", ...],
  "locations": ["Location", ...]
}}"""

            response = completion(
                model=f"openai/{VLLM_MODEL}",
                api_base=VLLM_BASE_URL,
                messages=[
                    {"role": "system", "content": "You are a news analysis assistant. Extract tags and named entities. Output valid JSON only."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=300,
                temperature=0.1,
            )

            response_text = response.choices[0].message.content.strip()

            # Parse JSON response
            result = self._parse_slm_response(response_text)

            return {
                "tags": result.get("tags", [])[:top_n],
                "entities": {
                    "people": result.get("people", []),
                    "organizations": result.get("organizations", []),
                    "locations": result.get("locations", []),
                },
                "keybert_candidates": keybert_candidates,
                "source": "hybrid",
                "latency_ms": int((time.time() - start_time) * 1000),
            }

        except Exception as e:
            logger.warning(f"vLLM tagging failed, falling back to KeyBERT: {e}")
            self._vllm_checked = False  # Reset for retry
            return {
                "tags": keybert_candidates[:top_n],
                "entities": {"people": [], "organizations": [], "locations": []},
                "keybert_candidates": keybert_candidates,
                "source": "keybert_fallback",
                "latency_ms": int((time.time() - start_time) * 1000),
                "error": str(e),
            }

    def _parse_slm_response(self, response_text: str) -> Dict[str, Any]:
        """Parse JSON response from SLM, handling common formatting issues."""
        try:
            # Try direct JSON parse
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

        logger.warning(f"Failed to parse SLM response: {response_text[:200]}")
        return {"tags": [], "people": [], "organizations": [], "locations": []}

    def extract_tags_batch(
        self,
        articles: List[Dict[str, str]],
        top_n: int = DEFAULT_TOP_N,
        use_hybrid: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Extract tags from multiple articles.

        Args:
            articles: List of dicts with 'title', 'summary', optional 'content'
            top_n: Number of tags per article
            use_hybrid: Use hybrid mode (KeyBERT + SLM)

        Returns:
            List of extraction results
        """
        results = []
        extract_fn = self.extract_tags_hybrid if use_hybrid else self.extract_tags

        for article in articles:
            result = extract_fn(
                title=article.get("title", ""),
                summary=article.get("summary", ""),
                content=article.get("content"),
                top_n=top_n,
            )
            results.append(result)
        return results

    def get_embedding_model(self):
        """Get the underlying SentenceTransformer model."""
        if not self._loaded:
            self._load_model()
        return self.embedding_model

    def get_status(self) -> Dict[str, Any]:
        """Get service status information."""
        return {
            "keybert_loaded": self._loaded,
            "vllm_available": self._check_vllm_available(),
            "hybrid_available": self.is_hybrid_available(),
            "embedding_model": EMBEDDING_MODEL if self._loaded else None,
            "vllm_model": VLLM_MODEL,
        }


# Singleton accessor
_service_instance = None


def get_keybert_tagging_service() -> KeyBERTTaggingService:
    """Get the singleton KeyBERT tagging service."""
    global _service_instance
    if _service_instance is None:
        _service_instance = KeyBERTTaggingService()
    return _service_instance
