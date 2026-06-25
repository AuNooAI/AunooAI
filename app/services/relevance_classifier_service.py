"""
Relevance Classifier Service

ML-based relevance classification for article-topic matching.
Replaces/augments LLM-based relevance scoring in the ingest pipeline.

Usage:
    from app.services.relevance_classifier_service import RelevanceClassifierService

    classifier = RelevanceClassifierService()
    result = classifier.classify(
        topic="Artificial Intelligence",
        title="OpenAI launches new GPT model",
        summary="OpenAI has announced GPT-5..."
    )
    # Returns: {"relevant": True, "score": 0.92, "confidence": "high"}
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# Model configuration
DEFAULT_THRESHOLD = 0.5
HIGH_CONFIDENCE_THRESHOLD = 0.8
LOW_CONFIDENCE_THRESHOLD = 0.3

# Local model paths
BASE_DIR = Path(__file__).parent.parent.parent
LOCAL_MODEL_PATH = BASE_DIR / "models" / "relevance_classifier" / "final"

# HuggingFace Hub model ID (for future distribution)
HF_MODEL_ID = "aunoo/relevance-classifier-deberta"


class RelevanceClassifierService:
    """
    ML-based relevance classifier for article-topic matching.

    Features:
    - DeBERTa-based binary classification
    - Confidence scoring with high/medium/low buckets
    - Batch processing support
    - Graceful fallback to LLM if model unavailable
    - Input format: topic [SEP] title. summary
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        """Singleton pattern for efficient model loading."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        use_gpu: bool = False,
        threshold: float = DEFAULT_THRESHOLD,
        prefer_local: bool = True,
    ):
        """
        Initialize the relevance classifier service.

        Args:
            use_gpu: Whether to use GPU (default False for server stability)
            threshold: Classification threshold (default 0.5)
            prefer_local: Prefer local models over HuggingFace Hub
        """
        if RelevanceClassifierService._initialized:
            return

        self.model = None
        self.tokenizer = None
        self.device = "cpu"
        self.max_length = 256  # Default, will be overridden from config

        self.threshold = threshold
        self.prefer_local = prefer_local
        self.use_gpu = use_gpu

        self._models_loaded = False
        self._load_error = None
        self._model_config = None

        RelevanceClassifierService._initialized = True

    def _get_device(self) -> str:
        """Determine device to use."""
        if self.use_gpu:
            try:
                import torch
                if torch.cuda.is_available():
                    return "cuda"
            except ImportError:
                pass
        return "cpu"

    def load_models(self, force_reload: bool = False) -> bool:
        """
        Load the classifier model.

        Returns:
            True if model loaded successfully, False otherwise
        """
        if self._models_loaded and not force_reload:
            return True

        try:
            import torch
            from transformers import AutoTokenizer, AutoModelForSequenceClassification
        except ImportError as e:
            if not self._load_error:
                self._load_error = f"Missing dependencies: {e}. Install with: pip install torch transformers"
                logger.warning(self._load_error)
            return False

        self.device = self._get_device()
        logger.info(f"Loading relevance classifier on {self.device}")

        model_path = None

        # Try local path first
        if self.prefer_local and LOCAL_MODEL_PATH.exists():
            model_path = str(LOCAL_MODEL_PATH)
            logger.info(f"Loading from local: {model_path}")
        else:
            # Try HuggingFace Hub
            try:
                from huggingface_hub import HfApi
                api = HfApi()
                try:
                    api.model_info(HF_MODEL_ID)
                    model_path = HF_MODEL_ID
                    logger.info(f"Loading from HuggingFace Hub: {model_path}")
                except Exception:
                    logger.warning(f"Model {HF_MODEL_ID} not found on HuggingFace Hub")
            except ImportError:
                logger.warning("huggingface_hub not installed, skipping Hub check")

        if not model_path:
            self._load_error = "No relevance classifier model found"
            logger.error(self._load_error)
            return False

        try:
            self.tokenizer = AutoTokenizer.from_pretrained(model_path)

            # Load with appropriate dtype
            if self.device == "cpu":
                self.model = AutoModelForSequenceClassification.from_pretrained(
                    model_path, torch_dtype=torch.float32
                )
            else:
                self.model = AutoModelForSequenceClassification.from_pretrained(model_path)

            self.model.to(self.device)
            self.model.eval()

            # Load model config if available
            config_path = Path(model_path) / "model_config.json"
            if config_path.exists():
                with open(config_path) as f:
                    self._model_config = json.load(f)
                    self.max_length = self._model_config.get("max_length", 256)
                    if "recommended_threshold" in self._model_config:
                        self.threshold = self._model_config["recommended_threshold"]

            self._models_loaded = True
            logger.info("Relevance classifier loaded successfully")
            return True

        except Exception as e:
            self._load_error = f"Failed to load model: {e}"
            logger.error(self._load_error)
            return False

    def is_available(self) -> bool:
        """Check if classifier is available for use."""
        if not self._models_loaded:
            self.load_models()
        return self._models_loaded

    def get_status(self) -> Dict:
        """Get classifier status and configuration."""
        return {
            "available": self._models_loaded,
            "error": self._load_error,
            "device": self.device,
            "model_loaded": self.model is not None,
            "threshold": self.threshold,
            "max_length": self.max_length,
            "model_config": self._model_config,
        }

    def _prepare_input(self, topic: str, title: str, summary: str) -> str:
        """
        Prepare input text in format: topic [SEP] title. summary

        Args:
            topic: Target topic for relevance
            title: Article title
            summary: Article summary

        Returns:
            Formatted input text
        """
        topic = str(topic).strip() if topic else ""
        title = str(title).strip() if title else ""
        summary = str(summary).strip() if summary else ""

        return f"{topic} [SEP] {title}. {summary}"

    def _get_confidence_level(self, score: float) -> str:
        """
        Convert score to confidence level.

        Args:
            score: Relevance score (0-1)

        Returns:
            "high", "medium", or "low"
        """
        if score >= HIGH_CONFIDENCE_THRESHOLD or score <= (1 - HIGH_CONFIDENCE_THRESHOLD):
            return "high"
        elif score >= LOW_CONFIDENCE_THRESHOLD and score <= (1 - LOW_CONFIDENCE_THRESHOLD):
            return "low"
        else:
            return "medium"

    def _get_scores(self, texts: List[str]) -> np.ndarray:
        """
        Get relevance scores for batch of texts.

        Args:
            texts: List of prepared input texts

        Returns:
            Array of relevance scores (0-1)
        """
        import torch

        with torch.no_grad():
            # Tokenize
            inputs = self.tokenizer(
                texts,
                padding=True,
                truncation=True,
                max_length=self.max_length,
                return_tensors="pt"
            )
            inputs = {k: v.to(self.device) for k, v in inputs.items()}

            # Get predictions
            outputs = self.model(**inputs)
            logits = outputs.logits

            # Convert to probabilities
            probs = torch.softmax(logits, dim=1)

            # Return probability of "relevant" class (index 1)
            scores = probs[:, 1].cpu().numpy()

        return scores

    def classify(
        self,
        topic: str,
        title: str,
        summary: str,
        threshold: Optional[float] = None,
    ) -> Dict:
        """
        Classify a single article for relevance to topic.

        Args:
            topic: Target topic
            title: Article title
            summary: Article summary
            threshold: Override default threshold

        Returns:
            Dict with 'relevant' (bool), 'score' (float), 'confidence' (str)
        """
        if not self.is_available():
            raise RuntimeError(f"Classifier not available: {self._load_error}")

        threshold = threshold or self.threshold
        text = self._prepare_input(topic, title, summary)
        score = self._get_scores([text])[0]

        return {
            "relevant": bool(score >= threshold),
            "score": float(score),
            "confidence": self._get_confidence_level(score),
        }

    def classify_batch(
        self,
        articles: List[Dict],
        threshold: Optional[float] = None,
        batch_size: int = 32,
    ) -> List[Dict]:
        """
        Classify multiple articles efficiently.

        Args:
            articles: List of dicts with 'topic', 'title', 'summary' keys
            threshold: Override default threshold
            batch_size: Processing batch size

        Returns:
            List of dicts with 'relevant', 'score', 'confidence'
        """
        if not self.is_available():
            raise RuntimeError(f"Classifier not available: {self._load_error}")

        threshold = threshold or self.threshold
        results = []

        # Prepare all texts
        texts = [
            self._prepare_input(
                article.get("topic", ""),
                article.get("title", ""),
                article.get("summary", "")
            )
            for article in articles
        ]

        # Process in batches
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i + batch_size]
            batch_scores = self._get_scores(batch_texts)

            for score in batch_scores:
                results.append({
                    "relevant": bool(score >= threshold),
                    "score": float(score),
                    "confidence": self._get_confidence_level(score),
                })

        return results

    def score_relevance(
        self,
        topic: str,
        title: str,
        summary: str,
    ) -> Tuple[float, str]:
        """
        Get relevance score (compatible with existing relevance scoring API).

        Args:
            topic: Target topic
            title: Article title
            summary: Article summary

        Returns:
            Tuple of (score, confidence_level)
        """
        result = self.classify(topic, title, summary)
        return result["score"], result["confidence"]


# Singleton instance getter
_service_instance = None


def get_relevance_classifier() -> RelevanceClassifierService:
    """Get the singleton relevance classifier service instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = RelevanceClassifierService()
    return _service_instance
