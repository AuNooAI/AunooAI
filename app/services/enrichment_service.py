"""
Enrichment Service

ML-based multi-task article enrichment for sentiment, time_to_impact,
driver_type, and future_signal prediction.

Supports both local SLM inference and LLM fallback with A/B testing capability.

Usage:
    from app.services.enrichment_service import EnrichmentService

    enricher = EnrichmentService()
    result = enricher.enrich(
        title="OpenAI launches GPT-5",
        summary="OpenAI has announced the release of GPT-5..."
    )
    # Returns: {
    #     "sentiment": "Positive",
    #     "time_to_impact": "Immediate",
    #     "driver_type": "accelerating",
    #     "future_signal": "Emerging",
    #     "source": "local"
    # }
"""

import json
import logging
import random
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import numpy as np

logger = logging.getLogger(__name__)

# Model configuration
BASE_DIR = Path(__file__).parent.parent.parent
LOCAL_MODEL_PATH = BASE_DIR / "models" / "enrichment_model" / "final"

# HuggingFace Hub model ID (for future distribution)
HF_MODEL_ID = "aunoo/article-enrichment-multitask"

# A/B testing configuration
DEFAULT_AB_TEST_ENABLED = False
DEFAULT_SLM_RATIO = 0.8  # 80% SLM, 20% LLM when A/B testing


class EnrichmentService:
    """
    Multi-task enrichment service for article analysis.

    Features:
    - Multi-task classification (sentiment, time_to_impact, driver_type, future_signal)
    - Batch processing support
    - A/B testing between SLM and LLM
    - Confidence scoring
    - LLM fallback when model unavailable
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
        prefer_local: bool = True,
        ab_test_enabled: bool = DEFAULT_AB_TEST_ENABLED,
        slm_ratio: float = DEFAULT_SLM_RATIO,
    ):
        """
        Initialize the enrichment service.

        Args:
            use_gpu: Whether to use GPU (default False for server stability)
            prefer_local: Prefer local models over HuggingFace Hub
            ab_test_enabled: Enable A/B testing between SLM and LLM
            slm_ratio: Ratio of requests to route to SLM (0-1)
        """
        if EnrichmentService._initialized:
            return

        self.model = None
        self.tokenizer = None
        self.device = "cpu"
        self.max_length = 256

        self.prefer_local = prefer_local
        self.use_gpu = use_gpu
        self.ab_test_enabled = ab_test_enabled
        self.slm_ratio = slm_ratio

        self._models_loaded = False
        self._load_error = None
        self._model_config = None
        self._task_configs = {}

        # Statistics for A/B testing
        self._stats = {
            'slm_requests': 0,
            'llm_requests': 0,
            'slm_latency_sum': 0,
            'llm_latency_sum': 0,
        }

        EnrichmentService._initialized = True

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
        Load the enrichment model.

        Returns:
            True if model loaded successfully, False otherwise
        """
        if self._models_loaded and not force_reload:
            return True

        try:
            import torch
            from transformers import AutoTokenizer, AutoModel, AutoConfig
        except ImportError as e:
            if not self._load_error:
                self._load_error = f"Missing dependencies: {e}. Install with: pip install torch transformers"
                logger.warning(self._load_error)
            return False

        self.device = self._get_device()
        logger.info(f"Loading enrichment model on {self.device}")

        model_path = None

        # Try local path first
        if self.prefer_local and LOCAL_MODEL_PATH.exists():
            model_path = LOCAL_MODEL_PATH
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
                    logger.warning(f"Model {HF_MODEL_ID} not found")
            except ImportError:
                pass

        if not model_path:
            self._load_error = "No enrichment model found"
            logger.warning(self._load_error)
            return False

        try:
            # Load config
            config_path = Path(model_path) / "model_config.json" if isinstance(model_path, Path) else None
            if config_path and config_path.exists():
                with open(config_path) as f:
                    self._model_config = json.load(f)
                    self._task_configs = self._model_config.get('tasks', {})
                    self.max_length = self._model_config.get('max_length', 256)

            # Load tokenizer
            self.tokenizer = AutoTokenizer.from_pretrained(str(model_path))

            # Load model
            base_config = AutoConfig.from_pretrained(str(model_path))

            # Import and instantiate the MultiTaskModel
            from scripts.train_enrichment_model import MultiTaskModel
            self.model = MultiTaskModel(base_config, self._task_configs)

            # Load weights with assign=True to handle meta tensor issues in PyTorch 2.x
            weights_path = Path(model_path) / "pytorch_model.bin"
            if weights_path.exists():
                state_dict = torch.load(weights_path, map_location=self.device, weights_only=False)
                # Use assign=True to properly copy weights to meta tensors (PyTorch 2.0+)
                self.model.load_state_dict(state_dict, assign=True)
                # Model is already on correct device from map_location, skip .to()
            else:
                self.model.to(self.device)

            self.model.eval()

            self._models_loaded = True
            logger.info(f"Enrichment model loaded with tasks: {list(self._task_configs.keys())}")
            return True

        except Exception as e:
            self._load_error = f"Failed to load model: {e}"
            logger.error(self._load_error)
            return False

    def is_available(self) -> bool:
        """Check if enrichment model is available for use."""
        if not self._models_loaded:
            self.load_models()
        return self._models_loaded

    def get_status(self) -> Dict:
        """Get service status and configuration."""
        return {
            "available": self._models_loaded,
            "error": self._load_error,
            "device": self.device,
            "model_loaded": self.model is not None,
            "max_length": self.max_length,
            "tasks": list(self._task_configs.keys()),
            "ab_test_enabled": self.ab_test_enabled,
            "slm_ratio": self.slm_ratio,
            "stats": self._stats,
            "model_config": self._model_config,
        }

    def _prepare_input(self, title: str, summary: str) -> str:
        """
        Prepare input text for classification.

        Args:
            title: Article title
            summary: Article summary

        Returns:
            Formatted text
        """
        title = str(title).strip() if title else ""
        summary = str(summary).strip() if summary else ""

        return f"{title}. {summary}"

    def _get_predictions(self, texts: List[str]) -> Dict[str, List[Tuple[str, float]]]:
        """
        Get predictions for batch of texts.

        Args:
            texts: List of prepared input texts

        Returns:
            Dict mapping task names to list of (label, confidence) tuples
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
            logits = outputs['logits']

        # Process each task
        results = {}
        for task, task_logits in logits.items():
            probs = torch.softmax(task_logits, dim=1)
            pred_ids = torch.argmax(probs, dim=1)
            confidences = probs.max(dim=1).values

            task_config = self._task_configs.get(task, {})
            id2label = task_config.get('id2label', {})

            task_results = []
            for i in range(len(texts)):
                pred_id = pred_ids[i].item()
                confidence = confidences[i].item()
                label = id2label.get(pred_id, id2label.get(str(pred_id), f"unknown_{pred_id}"))
                task_results.append((label, confidence))

            results[task] = task_results

        return results

    def _should_use_slm(self) -> bool:
        """Determine whether to use SLM based on A/B test config."""
        if not self.ab_test_enabled:
            return self.is_available()

        if not self.is_available():
            return False

        return random.random() < self.slm_ratio

    def enrich(
        self,
        title: str,
        summary: str,
        tasks: Optional[List[str]] = None,
        force_slm: bool = False,
        force_llm: bool = False,
    ) -> Dict[str, Any]:
        """
        Enrich a single article with analysis.

        Args:
            title: Article title
            summary: Article summary
            tasks: Specific tasks to run (default: all)
            force_slm: Force use of SLM (for testing)
            force_llm: Force use of LLM (for testing)

        Returns:
            Dict with predictions for each task and source indicator
        """
        import time

        start_time = time.time()

        # Determine source
        if force_llm:
            use_slm = False
        elif force_slm:
            use_slm = self.is_available()
        else:
            use_slm = self._should_use_slm()

        if use_slm:
            result = self._enrich_with_slm(title, summary, tasks)
            self._stats['slm_requests'] += 1
            elapsed = time.time() - start_time
            self._stats['slm_latency_sum'] += elapsed
            result['latency_ms'] = int(elapsed * 1000)
        else:
            result = self._enrich_with_llm(title, summary, tasks)
            self._stats['llm_requests'] += 1
            elapsed = time.time() - start_time
            self._stats['llm_latency_sum'] += elapsed
            result['latency_ms'] = int(elapsed * 1000)

        return result

    def _enrich_with_slm(
        self,
        title: str,
        summary: str,
        tasks: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Enrich using local SLM."""
        text = self._prepare_input(title, summary)
        predictions = self._get_predictions([text])

        result = {'source': 'slm'}
        for task, preds in predictions.items():
            if tasks and task not in tasks:
                continue
            label, confidence = preds[0]
            result[task] = label
            result[f'{task}_confidence'] = confidence

        return result

    def _enrich_with_llm(
        self,
        title: str,
        summary: str,
        tasks: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Enrich using LLM fallback."""
        try:
            from app.ai_models import AIModelFactory

            ai = AIModelFactory.get_model()

            # Build task-specific prompt
            task_list = tasks or list(self._task_configs.keys())
            task_descriptions = []

            for task in task_list:
                config = self._task_configs.get(task, {})
                labels = config.get('labels', [])
                if labels:
                    task_descriptions.append(f"- {task}: Choose from {labels}")

            if not task_descriptions:
                # Default tasks if no config available
                task_descriptions = [
                    "- sentiment: Choose from [Positive, Negative, Neutral]",
                    "- time_to_impact: Choose from [Immediate, 6 months, 1 year, 2+ years]",
                    "- driver_type: Choose from [accelerating, delaying, blocking, initiating, terminating, catalyzing]",
                    "- future_signal: Choose from [Emerging, Declining, Stable, Disruptive, Transformative]",
                ]

            prompt = f"""Analyze the following article and provide classifications:

Title: {title}
Summary: {summary}

For each of the following fields, provide the most appropriate classification:
{chr(10).join(task_descriptions)}

Respond in JSON format:
{{"sentiment": "...", "time_to_impact": "...", "driver_type": "...", "future_signal": "..."}}

JSON response:"""

            response = ai.generate(prompt, max_tokens=200, temperature=0.1)

            # Parse JSON response
            try:
                # Try to extract JSON from response
                import re
                json_match = re.search(r'\{[^}]+\}', response)
                if json_match:
                    result = json.loads(json_match.group())
                    result['source'] = 'llm'
                    return result
            except json.JSONDecodeError:
                pass

            # Fallback: return raw response
            return {
                'raw_response': response,
                'source': 'llm',
                'parse_error': True,
            }

        except Exception as e:
            logger.error(f"LLM enrichment failed: {e}")
            return {
                'error': str(e),
                'source': 'llm_failed',
            }

    def enrich_batch(
        self,
        articles: List[Dict],
        tasks: Optional[List[str]] = None,
        batch_size: int = 32,
        force_slm: bool = False,
        force_llm: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Enrich multiple articles efficiently.

        Args:
            articles: List of dicts with 'title', 'summary' keys
            tasks: Specific tasks to run
            batch_size: Processing batch size
            force_slm: Force use of SLM
            force_llm: Force use of LLM

        Returns:
            List of enrichment results
        """
        if force_llm or (not force_slm and not self.is_available()):
            # Use LLM for all
            return [
                self._enrich_with_llm(
                    article.get("title", ""),
                    article.get("summary", ""),
                    tasks
                )
                for article in articles
            ]

        # Use SLM with batch processing
        results = []
        texts = [
            self._prepare_input(
                article.get("title", ""),
                article.get("summary", "")
            )
            for article in articles
        ]

        # Process in batches
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i + batch_size]
            predictions = self._get_predictions(batch_texts)

            for j in range(len(batch_texts)):
                result = {'source': 'slm'}
                for task, preds in predictions.items():
                    if tasks and task not in tasks:
                        continue
                    label, confidence = preds[j]
                    result[task] = label
                    result[f'{task}_confidence'] = confidence
                results.append(result)

        return results

    def get_ab_test_stats(self) -> Dict[str, Any]:
        """Get A/B testing statistics."""
        stats = self._stats.copy()

        # Calculate averages
        if stats['slm_requests'] > 0:
            stats['slm_avg_latency'] = stats['slm_latency_sum'] / stats['slm_requests']
        else:
            stats['slm_avg_latency'] = 0

        if stats['llm_requests'] > 0:
            stats['llm_avg_latency'] = stats['llm_latency_sum'] / stats['llm_requests']
        else:
            stats['llm_avg_latency'] = 0

        total = stats['slm_requests'] + stats['llm_requests']
        if total > 0:
            stats['actual_slm_ratio'] = stats['slm_requests'] / total
        else:
            stats['actual_slm_ratio'] = 0

        return stats

    def reset_stats(self):
        """Reset A/B testing statistics."""
        self._stats = {
            'slm_requests': 0,
            'llm_requests': 0,
            'slm_latency_sum': 0,
            'llm_latency_sum': 0,
        }


# Singleton instance getter
_service_instance = None


def get_enrichment_service() -> EnrichmentService:
    """Get the singleton enrichment service instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = EnrichmentService()
    return _service_instance
