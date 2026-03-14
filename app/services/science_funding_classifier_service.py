"""
Science Funding Classifier Service

ML-based science funding category classification using DeBERTa.
Distilled from LLM (gpt-4.1-mini) classifications.

Usage:
    from app.services.science_funding_classifier_service import ScienceFundingClassifierService

    classifier = ScienceFundingClassifierService()
    result = classifier.classify("NIH freezes $1.2 billion in grants")
    # Returns: {'categories': ['Grant Freezes & Cuts', 'NIH & Biomedical'], 'scores': {...}}
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLD = 0.5

BASE_DIR = Path(__file__).parent.parent.parent
LOCAL_MODEL_PATH = BASE_DIR / "models/science_funding_classifier/final"

CATEGORIES = [
    "Grant Freezes & Cuts",
    "NIH & Biomedical",
    "NSF & Basic Science",
    "DOE & Energy Research",
    "University Impact",
    "Brain Drain & Workforce",
    "Climate & Environmental",
    "DEI & Ideological Targeting",
    "Public Health & Medical",
    "International Collaboration",
]


class ScienceFundingClassifierService:
    """
    Production ML classifier for science funding categories.

    Features:
    - DeBERTa-based multi-label classification
    - Batch processing support
    - Configurable threshold
    - Graceful degradation if model unavailable
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, use_gpu: bool = False, threshold: float = DEFAULT_THRESHOLD):
        if ScienceFundingClassifierService._initialized:
            return

        self.model = None
        self.tokenizer = None
        self.device = "cpu"
        self.threshold = threshold
        self.use_gpu = use_gpu
        self.categories = CATEGORIES
        self.id2label = {i: cat for i, cat in enumerate(CATEGORIES)}
        self.label2id = {cat: i for i, cat in enumerate(CATEGORIES)}
        self._models_loaded = False
        self._load_error = None

        ScienceFundingClassifierService._initialized = True

    def _get_device(self) -> str:
        if self.use_gpu:
            try:
                import torch
                if torch.cuda.is_available():
                    return "cuda"
            except ImportError:
                pass
        return "cpu"

    def load_models(self, force_reload: bool = False) -> bool:
        """Load the classifier model."""
        if self._models_loaded and not force_reload:
            return True

        try:
            import torch
            from transformers import AutoTokenizer, AutoModelForSequenceClassification
        except ImportError as e:
            self._load_error = f"Missing dependencies: {e}"
            logger.warning(self._load_error)
            return False

        model_path = LOCAL_MODEL_PATH

        # Load category mapping if available
        mapping_path = model_path / "category_mapping.json"
        if mapping_path.exists():
            with open(mapping_path) as f:
                config = json.load(f)
                self.categories = config.get("categories", CATEGORIES)
                self.threshold = config.get("recommended_threshold", self.threshold)
                self.id2label = {int(k): v for k, v in config.get("id2label", {}).items()}
                self.label2id = config.get("label2id", {})
                logger.info(f"Loaded config: {len(self.categories)} categories, threshold={self.threshold}")

        if not model_path.exists():
            self._load_error = f"Model not found at {model_path}"
            logger.warning(self._load_error)
            return False

        try:
            self.device = self._get_device()
            logger.info(f"Loading science funding classifier from {model_path} on {self.device}")

            self.tokenizer = AutoTokenizer.from_pretrained(str(model_path))

            if self.device == "cpu":
                self.model = AutoModelForSequenceClassification.from_pretrained(
                    str(model_path), torch_dtype=torch.float32
                )
            else:
                self.model = AutoModelForSequenceClassification.from_pretrained(str(model_path))

            self.model.to(self.device)
            self.model.eval()
            self._models_loaded = True
            logger.info("Science funding classifier loaded successfully")
            return True

        except Exception as e:
            self._load_error = f"Failed to load model: {e}"
            logger.error(self._load_error)
            return False

    def is_available(self) -> bool:
        if not self._models_loaded:
            self.load_models()
        return self._models_loaded

    def get_status(self) -> Dict:
        return {
            "available": self._models_loaded,
            "error": self._load_error,
            "device": self.device,
            "model_loaded": self.model is not None,
            "threshold": self.threshold,
            "categories": self.categories,
            "model_path": str(LOCAL_MODEL_PATH),
        }

    def classify(
        self,
        text: str,
        threshold: Optional[float] = None,
        return_scores: bool = False,
    ) -> Dict:
        """
        Classify a single text.

        Args:
            text: Article title/text to classify
            threshold: Override default threshold
            return_scores: Include raw scores in response

        Returns:
            Dict with 'categories' and optionally 'scores'
        """
        if not self.is_available():
            raise RuntimeError(f"Classifier not available: {self._load_error}")

        threshold = threshold or self.threshold
        scores = self._get_scores([text])[0]

        categories = [
            self.id2label[i]
            for i, score in enumerate(scores)
            if score >= threshold
        ]

        result = {"categories": categories}
        if return_scores:
            result["scores"] = {
                self.id2label[i]: float(score)
                for i, score in enumerate(scores)
            }
        return result

    def classify_batch(
        self,
        texts: List[str],
        threshold: Optional[float] = None,
        return_scores: bool = False,
        batch_size: int = 32,
    ) -> List[Dict]:
        """Classify multiple texts efficiently."""
        if not self.is_available():
            raise RuntimeError(f"Classifier not available: {self._load_error}")

        threshold = threshold or self.threshold
        results = []

        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i + batch_size]
            batch_scores = self._get_scores(batch_texts)

            for scores in batch_scores:
                categories = [
                    self.id2label[j]
                    for j, score in enumerate(scores)
                    if score >= threshold
                ]
                result = {"categories": categories}
                if return_scores:
                    result["scores"] = {
                        self.id2label[j]: float(score)
                        for j, score in enumerate(scores)
                    }
                results.append(result)

        return results

    def _get_scores(self, texts: List[str]) -> np.ndarray:
        """Get sigmoid scores from the model."""
        import torch

        inputs = self.tokenizer(
            texts,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=256,
        ).to(self.device)

        with torch.no_grad():
            outputs = self.model(**inputs)
            probs = torch.sigmoid(outputs.logits).cpu().numpy()

        return probs


# Singleton accessor
_classifier_service: Optional[ScienceFundingClassifierService] = None


def get_science_funding_classifier() -> ScienceFundingClassifierService:
    """Get or create the classifier service singleton."""
    global _classifier_service
    if _classifier_service is None:
        _classifier_service = ScienceFundingClassifierService()
    return _classifier_service


def classify_science_article_ml(
    title: str,
    summary: Optional[str] = None,
    threshold: float = DEFAULT_THRESHOLD,
) -> Tuple[List[str], Dict[str, float]]:
    """
    Convenience function to classify a science funding article.

    Returns:
        Tuple of (category_list, scores_dict)
    """
    classifier = get_science_funding_classifier()

    if not classifier.is_available():
        return [], {}

    text = title
    if summary:
        text = f"{title}. {summary}"

    result = classifier.classify(text, threshold=threshold, return_scores=True)
    return result["categories"], result.get("scores", {})
