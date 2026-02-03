"""
Policy Classifier Service

Production-ready ML-based policy classification using the RoBERTa + DeBERTa ensemble.
Supports both local model files and HuggingFace Hub distribution.

Usage:
    from app.services.policy_classifier_service import PolicyClassifierService

    classifier = PolicyClassifierService()
    categories = classifier.classify("Trump fires FBI director")
    # Returns: ['undermining_democracy', 'suppressing_dissent', 'corruption']
"""

import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from functools import lru_cache

import numpy as np

logger = logging.getLogger(__name__)

# Model configuration
DEFAULT_THRESHOLD = 0.5
ENSEMBLE_WEIGHTS = {"roberta": 0.5, "deberta": 0.5}

# HuggingFace Hub model IDs (for distribution)
# Update these after pushing to HuggingFace Hub
HF_ROBERTA_MODEL = "aunoo/policy-classifier-roberta-large"
HF_DEBERTA_MODEL = "aunoo/policy-classifier-deberta-base"

# Local model paths
BASE_DIR = Path(__file__).parent.parent.parent
LOCAL_ROBERTA_PATH = BASE_DIR / "models/policy_classifier/final_roberta_large"
LOCAL_DEBERTA_PATH = BASE_DIR / "models/policy_classifier/final"

# Category mapping (internal names to display names)
CATEGORY_DISPLAY_NAMES = {
    "undermining_democracy": "Undermining Democracy",
    "hollowing_state": "Hollowing State",
    "suppressing_dissent": "Suppressing Dissent",
    "controlling_information": "Controlling Information",
    "attacking_science": "Attacking Science",
    "attacking_education": "Attacking Education",
    "weakening_civil_rights": "Weakening Civil Rights",
    "corruption": "Corruption",
    "foreign_policy": "Foreign Policy",
    "nationalism_immigration": "Nationalism & Immigration",
}

CATEGORIES = list(CATEGORY_DISPLAY_NAMES.keys())


class PolicyClassifierService:
    """
    Production ML classifier service for policy categorization.

    Features:
    - RoBERTa + DeBERTa ensemble (configurable weights)
    - Automatic model download from HuggingFace Hub
    - Fallback to local models if available
    - Graceful degradation if models unavailable
    - Batch processing support
    - Confidence scores for all categories
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
        roberta_weight: float = 0.5,
        deberta_weight: float = 0.5,
        threshold: float = DEFAULT_THRESHOLD,
        prefer_local: bool = True,
    ):
        """
        Initialize the classifier service.

        Args:
            use_gpu: Whether to use GPU (default False for server stability)
            roberta_weight: Weight for RoBERTa in ensemble (0-1)
            deberta_weight: Weight for DeBERTa in ensemble (0-1)
            threshold: Classification threshold (default 0.5)
            prefer_local: Prefer local models over HuggingFace Hub
        """
        if PolicyClassifierService._initialized:
            return

        self.roberta_model = None
        self.deberta_model = None
        self.roberta_tokenizer = None
        self.deberta_tokenizer = None
        self.device = "cpu"
        self.categories = CATEGORIES
        self.id2label = {i: cat for i, cat in enumerate(CATEGORIES)}
        self.label2id = {cat: i for i, cat in enumerate(CATEGORIES)}

        self.roberta_weight = roberta_weight
        self.deberta_weight = deberta_weight
        self.threshold = threshold
        self.prefer_local = prefer_local
        self.use_gpu = use_gpu

        self._models_loaded = False
        self._load_error = None

        PolicyClassifierService._initialized = True

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
        Load both classifier models.

        Returns:
            True if models loaded successfully, False otherwise
        """
        if self._models_loaded and not force_reload:
            return True

        try:
            import torch
            from transformers import AutoTokenizer, AutoModelForSequenceClassification
        except ImportError as e:
            if not self._load_error:  # Only log once
                self._load_error = f"Missing dependencies: {e}. Install with: pip install torch transformers"
                logger.warning(self._load_error)
            return False

        self.device = self._get_device()
        logger.info(f"Loading policy classifier models on {self.device}")

        # Load RoBERTa
        roberta_loaded = self._load_single_model(
            "roberta",
            LOCAL_ROBERTA_PATH if self.prefer_local else None,
            HF_ROBERTA_MODEL,
        )

        # Load DeBERTa
        deberta_loaded = self._load_single_model(
            "deberta",
            LOCAL_DEBERTA_PATH if self.prefer_local else None,
            HF_DEBERTA_MODEL,
        )

        if roberta_loaded or deberta_loaded:
            self._models_loaded = True
            logger.info(
                f"Models loaded - RoBERTa: {roberta_loaded}, DeBERTa: {deberta_loaded}"
            )

            # Adjust weights if only one model loaded
            if not roberta_loaded:
                self.roberta_weight = 0
                self.deberta_weight = 1
            elif not deberta_loaded:
                self.roberta_weight = 1
                self.deberta_weight = 0

            return True
        else:
            self._load_error = "Failed to load any classifier models"
            logger.error(self._load_error)
            return False

    def _load_single_model(
        self,
        name: str,
        local_path: Optional[Path],
        hf_model_id: str,
    ) -> bool:
        """Load a single model from local path or HuggingFace Hub."""
        import torch
        from transformers import AutoTokenizer, AutoModelForSequenceClassification

        model_path = None

        # Try local path first
        if local_path and local_path.exists():
            model_path = str(local_path)
            logger.info(f"Loading {name} from local: {model_path}")
        else:
            # Try HuggingFace Hub
            try:
                from huggingface_hub import hf_hub_download, HfApi
                api = HfApi()
                # Check if model exists on Hub
                try:
                    api.model_info(hf_model_id)
                    model_path = hf_model_id
                    logger.info(f"Loading {name} from HuggingFace Hub: {model_path}")
                except Exception:
                    logger.warning(f"Model {hf_model_id} not found on HuggingFace Hub")
                    return False
            except ImportError:
                logger.warning("huggingface_hub not installed, skipping Hub check")
                return False

        if not model_path:
            return False

        try:
            tokenizer = AutoTokenizer.from_pretrained(model_path)

            # Disable meta tensor lazy loading to avoid CPU loading issues
            model = AutoModelForSequenceClassification.from_pretrained(
                model_path,
                low_cpu_mem_usage=False
            )
            model.eval()

            if name == "roberta":
                self.roberta_model = model
                self.roberta_tokenizer = tokenizer
            else:
                self.deberta_model = model
                self.deberta_tokenizer = tokenizer

            return True

        except Exception as e:
            logger.error(f"Failed to load {name} model: {e}")
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
            "roberta_loaded": self.roberta_model is not None,
            "deberta_loaded": self.deberta_model is not None,
            "roberta_weight": self.roberta_weight,
            "deberta_weight": self.deberta_weight,
            "threshold": self.threshold,
            "categories": self.categories,
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
            Dict with 'categories' (list) and optionally 'scores' (dict)
        """
        if not self.is_available():
            raise RuntimeError(f"Classifier not available: {self._load_error}")

        threshold = threshold or self.threshold
        scores = self._get_ensemble_scores([text])[0]

        # Get categories above threshold
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
        """
        Classify multiple texts efficiently.

        Args:
            texts: List of texts to classify
            threshold: Override default threshold
            return_scores: Include raw scores in response
            batch_size: Processing batch size

        Returns:
            List of dicts with 'categories' and optionally 'scores'
        """
        if not self.is_available():
            raise RuntimeError(f"Classifier not available: {self._load_error}")

        threshold = threshold or self.threshold
        results = []

        # Process in batches
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i + batch_size]
            batch_scores = self._get_ensemble_scores(batch_texts)

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

    def _get_ensemble_scores(self, texts: List[str]) -> np.ndarray:
        """Get ensemble scores from both models."""
        import torch

        scores = np.zeros((len(texts), len(self.categories)))
        total_weight = 0

        # RoBERTa scores
        if self.roberta_model is not None and self.roberta_weight > 0:
            roberta_scores = self._get_model_scores(
                texts, self.roberta_model, self.roberta_tokenizer
            )
            scores += self.roberta_weight * roberta_scores
            total_weight += self.roberta_weight

        # DeBERTa scores
        if self.deberta_model is not None and self.deberta_weight > 0:
            deberta_scores = self._get_model_scores(
                texts, self.deberta_model, self.deberta_tokenizer
            )
            scores += self.deberta_weight * deberta_scores
            total_weight += self.deberta_weight

        # Normalize by total weight
        if total_weight > 0:
            scores /= total_weight

        return scores

    def _get_model_scores(self, texts: List[str], model, tokenizer) -> np.ndarray:
        """Get sigmoid scores from a single model."""
        import torch

        inputs = tokenizer(
            texts,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=256,
        ).to(self.device)

        with torch.no_grad():
            outputs = model(**inputs)
            probs = torch.sigmoid(outputs.logits).cpu().numpy()

        return probs

    def get_display_categories(self, internal_categories: List[str]) -> List[str]:
        """Convert internal category names to display names."""
        return [
            CATEGORY_DISPLAY_NAMES.get(cat, cat)
            for cat in internal_categories
        ]


# Singleton instance for easy access
_classifier_service: Optional[PolicyClassifierService] = None


def get_classifier_service() -> PolicyClassifierService:
    """Get or create the classifier service singleton."""
    global _classifier_service
    if _classifier_service is None:
        _classifier_service = PolicyClassifierService()
    return _classifier_service


def classify_article_ml(
    title: str,
    summary: Optional[str] = None,
    threshold: float = DEFAULT_THRESHOLD,
) -> Tuple[List[str], Dict[str, float]]:
    """
    Convenience function to classify an article using ML.

    Args:
        title: Article title
        summary: Optional article summary
        threshold: Classification threshold

    Returns:
        Tuple of (category_list, scores_dict)
    """
    classifier = get_classifier_service()

    if not classifier.is_available():
        # Fallback - return empty (caller should use keyword-based)
        return [], {}

    # Combine title and summary
    text = title
    if summary:
        text = f"{title}. {summary}"

    result = classifier.classify(text, threshold=threshold, return_scores=True)

    return result["categories"], result.get("scores", {})
