"""
Hybrid Relevance Service

Combines multiple approaches for robust relevance scoring:
1. Embedding similarity - Works for ANY topic (zero-shot)
2. Fine-tuned classifier - More accurate for known topics
3. LLM fallback - Most accurate, used when confidence is low

Scoring hierarchy:
- High confidence: Use hybrid (classifier + embedding)
- Medium confidence: Use embedding only
- Low confidence: Fall back to LLM

Usage:
    from app.services.hybrid_relevance_service import get_hybrid_relevance_service

    service = get_hybrid_relevance_service()
    result = service.score_relevance(
        topic="Climate Change Policy",
        title="New EPA regulations on carbon emissions",
        summary="The EPA announced new rules..."
    )
    # Returns: {
    #     "relevant": True,
    #     "score": 0.85,
    #     "embedding_score": 0.82,
    #     "classifier_score": 0.88,
    #     "method": "hybrid"
    # }
"""

import logging
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import numpy as np

logger = logging.getLogger(__name__)

# Configuration
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"  # Fast, good quality
CLASSIFIER_WEIGHT = 0.6  # Weight for classifier when available
EMBEDDING_WEIGHT = 0.4   # Weight for embedding similarity
NEW_TOPIC_THRESHOLD = 100  # Minimum training samples to trust classifier
DEFAULT_THRESHOLD = 0.5
LLM_FALLBACK_THRESHOLD = 0.3  # Use LLM if score is in uncertain range (0.3-0.7)
# Classifier/embedding disagreement handling: when the binary classifier was never
# trained on a topic, it returns ~0 for every article. If the embedding signal is
# strong, that's disagreement — don't let a no-signal classifier veto the decision.
CLASSIFIER_NO_SIGNAL_THRESHOLD = 0.1
EMBEDDING_CONFIDENT_THRESHOLD = 0.6
DISAGREEMENT_DELTA = 0.35  # |classifier - embedding| > this => force LLM arbitration


class HybridRelevanceService:
    """
    Hybrid relevance scoring combining embeddings and classification.
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if HybridRelevanceService._initialized:
            return

        self.embedding_model = None
        self.classifier = None
        self.classifier_tokenizer = None
        self.device = "cpu"

        self._embedding_loaded = False
        self._classifier_loaded = False
        self._topic_cache = {}  # Cache topic embeddings
        self._known_topics = set()  # Topics seen in training

        HybridRelevanceService._initialized = True

    def _load_embedding_model(self) -> bool:
        """Load the sentence embedding model."""
        if self._embedding_loaded:
            return True

        try:
            from sentence_transformers import SentenceTransformer

            logger.info(f"Loading embedding model: {EMBEDDING_MODEL} (CPU mode)")
            self.embedding_model = SentenceTransformer(EMBEDDING_MODEL, device='cpu')
            self._embedding_loaded = True
            logger.info("Embedding model loaded successfully on CPU")
            return True

        except ImportError:
            logger.warning("sentence-transformers not installed. Run: pip install sentence-transformers")
            return False
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            return False

    def _load_classifier(self) -> bool:
        """Load the fine-tuned relevance classifier."""
        if self._classifier_loaded:
            return True

        try:
            from transformers import AutoTokenizer, AutoModelForSequenceClassification
            import torch
            import json

            model_path = Path(__file__).parent.parent.parent / "models" / "relevance_classifier" / "final"

            if not model_path.exists():
                logger.warning(f"Classifier not found at {model_path}")
                return False

            logger.info(f"Loading classifier from {model_path}")
            self.classifier_tokenizer = AutoTokenizer.from_pretrained(str(model_path))
            self.classifier = AutoModelForSequenceClassification.from_pretrained(str(model_path))
            self.classifier.eval()

            # Load known topics from training data
            config_path = model_path / "model_config.json"
            if config_path.exists():
                with open(config_path) as f:
                    config = json.load(f)
                    # Could store known topics in config

            self._classifier_loaded = True
            logger.info("Classifier loaded successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to load classifier: {e}")
            return False

    def load_models(self) -> Dict[str, bool]:
        """Load all models."""
        return {
            "embedding": self._load_embedding_model(),
            "classifier": self._load_classifier(),
        }

    def is_available(self) -> bool:
        """Check if at least embedding model is available."""
        if not self._embedding_loaded:
            self._load_embedding_model()
        return self._embedding_loaded

    def _get_topic_embedding(self, topic: str) -> np.ndarray:
        """Get or compute topic embedding (cached).

        Enriches topic name with description and keywords for better semantic matching.
        """
        if topic not in self._topic_cache:
            # Try to get topic description and keywords from config
            topic_text = topic
            try:
                import json
                config_path = "app/config/config.json"
                with open(config_path, 'r') as f:
                    config = json.load(f)

                for t in config.get('topics', []):
                    if t.get('name') == topic:
                        # Enrich topic text with description and keywords
                        parts = [topic]
                        if t.get('description'):
                            parts.append(t['description'])
                        if t.get('keywords'):
                            # Filter out exclusion keywords (starting with -)
                            _entity_prefixes = ('company:', 'person:', 'tech:', 'location:')
                            keywords = [
                                k for k in t['keywords']
                                if not k.startswith('-')
                                and not any(k.startswith(p) for p in _entity_prefixes)
                            ]
                            if keywords:
                                parts.append(', '.join(keywords[:10]))  # Limit to 10 keywords
                        topic_text = '. '.join(parts)
                        logger.debug(f"Enriched topic embedding for '{topic}': {topic_text[:100]}...")
                        break
            except Exception as e:
                logger.debug(f"Could not enrich topic embedding: {e}")

            self._topic_cache[topic] = self.embedding_model.encode(topic_text, convert_to_numpy=True)
        return self._topic_cache[topic]

    def _compute_embedding_similarity(
        self,
        topic: str,
        title: str,
        summary: str,
        full_text: Optional[str] = None
    ) -> float:
        """
        Compute cosine similarity between topic and article.

        Uses full_text (truncated) when summary is short (<100 chars).
        """
        if not self._embedding_loaded:
            return 0.0

        # Get topic embedding (cached)
        topic_emb = self._get_topic_embedding(topic)

        # Compute article embedding
        # Use full_text fallback when summary is too short
        if full_text and len(summary or '') < 100:
            # Truncate full_text to ~1000 chars to stay within embedding limits
            truncated_text = full_text[:1000] if len(full_text) > 1000 else full_text
            article_text = f"{title}. {truncated_text}"
            logger.debug(f"Using truncated full_text for short summary ({len(summary or '')} chars)")
        else:
            article_text = f"{title}. {summary}"
        article_emb = self.embedding_model.encode(article_text, convert_to_numpy=True)

        # Cosine similarity
        similarity = np.dot(topic_emb, article_emb) / (
            np.linalg.norm(topic_emb) * np.linalg.norm(article_emb)
        )

        # Convert from [-1, 1] to [0, 1]
        score = (similarity + 1) / 2

        return float(score)

    def _compute_classifier_score(
        self,
        topic: str,
        title: str,
        summary: str
    ) -> Optional[float]:
        """
        Get relevance probability from fine-tuned classifier.
        """
        if not self._classifier_loaded:
            return None

        try:
            import torch

            # Format input like training data
            text = f"{topic} [SEP] {title}. {summary}"

            inputs = self.classifier_tokenizer(
                text,
                truncation=True,
                max_length=256,
                return_tensors="pt"
            )

            with torch.no_grad():
                outputs = self.classifier(**inputs)
                probs = torch.softmax(outputs.logits, dim=1)
                # Return probability of "relevant" class (index 1)
                score = probs[0, 1].item()

            return score

        except Exception as e:
            logger.error(f"Classifier inference failed: {e}")
            return None

    def _compute_llm_score(
        self,
        topic: str,
        title: str,
        summary: str,
        use_local: bool = False
    ) -> Optional[float]:
        """
        Get relevance score from LLM (most accurate, but slow/expensive).
        Used as fallback when other methods have low confidence.

        Args:
            topic: Topic to check relevance against
            title: Article title
            summary: Article summary
            use_local: If True, use local Qwen model instead of external GPT
        """
        prompt = f"""Rate the relevance of this article to the given topic on a scale of 0.0 to 1.0.

Topic: {topic}

Article Title: {title}
Article Summary: {summary}

Respond with ONLY a number between 0.0 and 1.0, where:
- 0.0 = completely irrelevant
- 0.5 = somewhat relevant
- 1.0 = highly relevant

Score:"""

        if use_local:
            return self._compute_local_llm_score(prompt)
        else:
            return self._compute_external_llm_score(prompt)

    def _compute_local_llm_score(self, prompt: str) -> Optional[float]:
        """Use local Qwen model (vLLM on port 8766) for relevance scoring."""
        try:
            from litellm import completion

            VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://localhost:8765/v1")
            VLLM_MODEL = "Qwen/Qwen2.5-3B-Instruct"

            response = completion(
                model=f"openai/{VLLM_MODEL}",
                api_base=VLLM_BASE_URL,
                messages=[
                    {"role": "system", "content": "You are a relevance scorer. Output only a number between 0.0 and 1.0."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=10,
                temperature=0.0,
            )

            response_text = response.choices[0].message.content.strip()
            # Extract first number from response
            match = re.search(r'(\d+\.?\d*)', response_text)
            if match:
                score = float(match.group(1))
                score = max(0.0, min(1.0, score))
                logger.info(f"🏠 Local Qwen relevance score: {score:.3f}")
                return score
            logger.warning(f"Could not parse local LLM score: {response_text}")
            return None

        except Exception as e:
            logger.error(f"Local LLM (Qwen) relevance scoring failed: {e}")
            return None

    def _compute_external_llm_score(self, prompt: str) -> Optional[float]:
        """Use external GPT model for relevance scoring."""
        try:
            from app.ai_models import AIModelFactory, extract_content

            ai = AIModelFactory.get_model()
            response = ai.generate_sync(prompt, max_tokens=10, temperature=0.0)

            response_text = extract_content(response)
            score = float(response_text.strip())
            score = max(0.0, min(1.0, score))
            logger.info(f"☁️ External GPT relevance score: {score:.3f}")
            return score

        except ValueError as e:
            logger.warning(f"Could not parse external LLM score: {e}")
            return None
        except Exception as e:
            logger.error(f"External LLM relevance scoring failed: {e}")
            return None

    def _is_uncertain(self, score: float) -> bool:
        """Check if score is in the uncertain range where LLM fallback would help."""
        return LLM_FALLBACK_THRESHOLD < score < (1 - LLM_FALLBACK_THRESHOLD)

    def score_relevance(
        self,
        topic: str,
        title: str,
        summary: str,
        threshold: float = DEFAULT_THRESHOLD,
        use_llm_fallback: bool = True,
        force_llm: bool = False,
        use_local_llm: bool = False,
        full_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Score article relevance using hybrid approach.

        Args:
            topic: The topic to check relevance against
            title: Article title
            summary: Article summary
            threshold: Score threshold for binary relevance
            use_llm_fallback: Whether to use LLM for uncertain scores
            force_llm: Force LLM usage (for comparison/testing)
            use_local_llm: If True, use local Qwen instead of external GPT for fallback
            full_text: Optional full article text (used when summary is short)

        Returns:
            Dict with relevance decision and component scores
        """
        # Force LLM mode
        if force_llm:
            llm_score = self._compute_llm_score(topic, title, summary, use_local=use_local_llm)
            return {
                "topic": topic,
                "relevant": (llm_score or 0) >= threshold,
                "score": llm_score or 0,
                "embedding_score": None,
                "classifier_score": None,
                "llm_score": llm_score,
                "method": "llm_only",
                "confidence": "high" if llm_score is not None else "failed",
            }

        # Ensure models are loaded
        if not self._embedding_loaded:
            self._load_embedding_model()
        if not self._classifier_loaded:
            self._load_classifier()

        result = {
            "topic": topic,
            "relevant": False,
            "score": 0.0,
            "embedding_score": None,
            "classifier_score": None,
            "llm_score": None,
            "method": "none",
            "confidence": "low",
        }

        # Compute embedding similarity (always available if loaded)
        if self._embedding_loaded:
            embedding_score = self._compute_embedding_similarity(topic, title, summary, full_text)
            result["embedding_score"] = embedding_score
        else:
            embedding_score = None

        # Compute classifier score (if available)
        if self._classifier_loaded:
            classifier_score = self._compute_classifier_score(topic, title, summary)
            result["classifier_score"] = classifier_score
        else:
            classifier_score = None

        # Combine scores based on availability
        disagreement = False
        if classifier_score is not None and embedding_score is not None:
            # When the classifier returns near-zero while the embedding is confident,
            # the classifier almost certainly has no signal for this topic (untrained).
            # Trust the embedding alone in that case rather than letting a 0.0 classifier
            # veto a semantically-relevant article.
            if (classifier_score < CLASSIFIER_NO_SIGNAL_THRESHOLD
                    and embedding_score >= EMBEDDING_CONFIDENT_THRESHOLD):
                result["score"] = embedding_score
                result["method"] = "embedding_fallback"
            else:
                combined_score = (
                    CLASSIFIER_WEIGHT * classifier_score +
                    EMBEDDING_WEIGHT * embedding_score
                )
                result["score"] = combined_score
                result["method"] = "hybrid"

            # Flag component disagreement: a large gap between classifier and embedding
            # means we should NOT treat the combined score as a confident decision —
            # this is the case LLM arbitration exists to resolve.
            disagreement = abs(classifier_score - embedding_score) > DISAGREEMENT_DELTA

        elif embedding_score is not None:
            # Only embedding available (new topic or classifier not loaded)
            result["score"] = embedding_score
            result["method"] = "embedding_only"

        elif classifier_score is not None:
            # Only classifier available
            result["score"] = classifier_score
            result["method"] = "classifier_only"

        # Confidence: disagreement between components forces low confidence regardless
        # of the combined score. Otherwise use score-position heuristic.
        if disagreement:
            result["confidence"] = "low"
        elif result["score"] < 0.35 or result["score"] > 0.65:
            result["confidence"] = "high"  # Clear decision, components agree
        else:
            result["confidence"] = "medium"  # Borderline, may benefit from LLM

        # LLM fallback for uncertain/borderline scores OR component disagreement
        if use_llm_fallback and result["confidence"] != "high":
            fallback_type = "🏠 Local Qwen" if use_local_llm else "☁️ GPT"
            logger.info(f"🤖 {fallback_type} fallback triggered for borderline score {result['score']:.3f}")
            llm_score = self._compute_llm_score(topic, title, summary, use_local=use_local_llm)
            if llm_score is not None:
                result["llm_score"] = llm_score
                result["score"] = llm_score  # LLM overrides when uncertain
                result["method"] = f"{result['method']}+{'local_llm' if use_local_llm else 'llm'}_fallback"
                result["confidence"] = "high"

        # Make binary decision
        result["relevant"] = result["score"] >= threshold

        return result

    def score_batch(
        self,
        articles: List[Dict],
        threshold: float = DEFAULT_THRESHOLD,
    ) -> List[Dict[str, Any]]:
        """
        Score multiple articles efficiently.

        Args:
            articles: List of dicts with 'topic', 'title', 'summary'
            threshold: Score threshold

        Returns:
            List of result dicts
        """
        results = []

        # TODO: Batch embedding computation for efficiency
        for article in articles:
            result = self.score_relevance(
                topic=article.get("topic", ""),
                title=article.get("title", ""),
                summary=article.get("summary", ""),
                threshold=threshold,
            )
            results.append(result)

        return results

    def get_status(self) -> Dict[str, Any]:
        """Get service status."""
        return {
            "embedding_loaded": self._embedding_loaded,
            "classifier_loaded": self._classifier_loaded,
            "embedding_model": EMBEDDING_MODEL if self._embedding_loaded else None,
            "cached_topics": list(self._topic_cache.keys()),
            "classifier_weight": CLASSIFIER_WEIGHT,
            "embedding_weight": EMBEDDING_WEIGHT,
        }


# Singleton accessor
_service_instance = None


def get_hybrid_relevance_service() -> HybridRelevanceService:
    """Get the singleton hybrid relevance service."""
    global _service_instance
    if _service_instance is None:
        _service_instance = HybridRelevanceService()
    return _service_instance
