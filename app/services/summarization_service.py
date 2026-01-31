"""
Summarization Service

ML-based article summarization using fine-tuned T5/BART models.
Supports both local model inference and LLM fallback.

Usage:
    from app.services.summarization_service import SummarizationService

    summarizer = SummarizationService()
    result = summarizer.summarize(
        title="OpenAI launches GPT-5",
        content="OpenAI has announced the release of GPT-5..."
    )
    # Returns: {"summary": "OpenAI releases GPT-5 with...", "source": "local"}
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# Model configuration
DEFAULT_MAX_SOURCE_LENGTH = 1024
DEFAULT_MAX_TARGET_LENGTH = 128
DEFAULT_NUM_BEAMS = 4

# Local model paths
BASE_DIR = Path(__file__).parent.parent.parent
LOCAL_MODEL_PATH = BASE_DIR / "models" / "summarizer" / "final"

# HuggingFace Hub model ID (for future distribution)
HF_MODEL_ID = "aunoo/article-summarizer-t5"


class SummarizationService:
    """
    ML-based article summarization service.

    Features:
    - T5/BART-based summarization
    - Configurable generation parameters
    - Batch processing support
    - LLM fallback when model unavailable
    - Caching support for efficiency
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
        max_source_length: int = DEFAULT_MAX_SOURCE_LENGTH,
        max_target_length: int = DEFAULT_MAX_TARGET_LENGTH,
    ):
        """
        Initialize the summarization service.

        Args:
            use_gpu: Whether to use GPU (default False for server stability)
            prefer_local: Prefer local models over HuggingFace Hub
            max_source_length: Maximum input length in tokens
            max_target_length: Maximum output length in tokens
        """
        if SummarizationService._initialized:
            return

        self.model = None
        self.tokenizer = None
        self.device = "cpu"

        self.max_source_length = max_source_length
        self.max_target_length = max_target_length
        self.prefer_local = prefer_local
        self.use_gpu = use_gpu

        self._models_loaded = False
        self._load_error = None
        self._model_config = None

        # Generation parameters
        self.num_beams = DEFAULT_NUM_BEAMS
        self.length_penalty = 1.0
        self.no_repeat_ngram_size = 3
        self.early_stopping = True

        SummarizationService._initialized = True

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
        Load the summarization model.

        Returns:
            True if model loaded successfully, False otherwise
        """
        if self._models_loaded and not force_reload:
            return True

        try:
            import torch
            from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
        except ImportError as e:
            if not self._load_error:
                self._load_error = f"Missing dependencies: {e}. Install with: pip install torch transformers"
                logger.warning(self._load_error)
            return False

        self.device = self._get_device()
        logger.info(f"Loading summarization model on {self.device}")

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
                    # Fallback to public T5 model
                    model_path = "t5-base"
                    logger.info(f"Using base T5 model: {model_path}")
            except ImportError:
                model_path = "t5-base"
                logger.info(f"Using base T5 model: {model_path}")

        if not model_path:
            self._load_error = "No summarization model found"
            logger.error(self._load_error)
            return False

        try:
            self.tokenizer = AutoTokenizer.from_pretrained(model_path)

            # Load with appropriate dtype
            if self.device == "cpu":
                import torch
                self.model = AutoModelForSeq2SeqLM.from_pretrained(
                    model_path, torch_dtype=torch.float32
                )
            else:
                self.model = AutoModelForSeq2SeqLM.from_pretrained(model_path)

            self.model.to(self.device)
            self.model.eval()

            # Load model config if available
            config_path = Path(model_path) / "model_config.json"
            if config_path.exists():
                with open(config_path) as f:
                    self._model_config = json.load(f)
                    self.max_source_length = self._model_config.get("max_source_length", DEFAULT_MAX_SOURCE_LENGTH)
                    self.max_target_length = self._model_config.get("max_target_length", DEFAULT_MAX_TARGET_LENGTH)
                    gen_config = self._model_config.get("generation_config", {})
                    self.num_beams = gen_config.get("num_beams", DEFAULT_NUM_BEAMS)

            self._models_loaded = True
            logger.info("Summarization model loaded successfully")
            return True

        except Exception as e:
            self._load_error = f"Failed to load model: {e}"
            logger.error(self._load_error)
            return False

    def is_available(self) -> bool:
        """Check if summarizer is available for use."""
        if not self._models_loaded:
            self.load_models()
        return self._models_loaded

    def get_status(self) -> Dict:
        """Get summarizer status and configuration."""
        return {
            "available": self._models_loaded,
            "error": self._load_error,
            "device": self.device,
            "model_loaded": self.model is not None,
            "max_source_length": self.max_source_length,
            "max_target_length": self.max_target_length,
            "num_beams": self.num_beams,
            "model_config": self._model_config,
        }

    def _prepare_input(self, title: str, content: str) -> str:
        """
        Prepare input text for summarization.

        Args:
            title: Article title
            content: Article content

        Returns:
            Formatted input text
        """
        title = str(title).strip() if title else ""
        content = str(content).strip() if content else ""

        # Format for T5: "summarize: title\n\ncontent"
        if title:
            return f"summarize: {title}\n\n{content}"
        else:
            return f"summarize: {content}"

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

        Args:
            title: Article title
            content: Article content
            max_length: Override max output length
            min_length: Minimum output length
            num_beams: Override beam search width

        Returns:
            Dict with 'summary' (str) and 'source' ('local' or 'llm')
        """
        if not self.is_available():
            # Fallback to LLM
            return self._summarize_with_llm(title, content)

        import torch

        max_length = max_length or self.max_target_length
        min_length = min_length or 30
        num_beams = num_beams or self.num_beams

        # Prepare input
        input_text = self._prepare_input(title, content)

        # Tokenize
        inputs = self.tokenizer(
            input_text,
            max_length=self.max_source_length,
            truncation=True,
            return_tensors="pt"
        ).to(self.device)

        # Generate
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_length=max_length,
                min_length=min_length,
                num_beams=num_beams,
                length_penalty=self.length_penalty,
                no_repeat_ngram_size=self.no_repeat_ngram_size,
                early_stopping=self.early_stopping,
            )

        # Decode
        summary = self.tokenizer.decode(outputs[0], skip_special_tokens=True)

        return {
            "summary": summary.strip(),
            "source": "local",
        }

    def summarize_batch(
        self,
        articles: List[Dict],
        max_length: Optional[int] = None,
        batch_size: int = 8,
    ) -> List[Dict]:
        """
        Generate summaries for multiple articles efficiently.

        Args:
            articles: List of dicts with 'title', 'content' keys
            max_length: Override max output length
            batch_size: Processing batch size

        Returns:
            List of dicts with 'summary' and 'source'
        """
        if not self.is_available():
            # Fallback to LLM for each article
            return [
                self._summarize_with_llm(
                    article.get("title", ""),
                    article.get("content", "")
                )
                for article in articles
            ]

        import torch

        max_length = max_length or self.max_target_length
        results = []

        # Prepare all inputs
        input_texts = [
            self._prepare_input(
                article.get("title", ""),
                article.get("content", "")
            )
            for article in articles
        ]

        # Process in batches
        for i in range(0, len(input_texts), batch_size):
            batch_texts = input_texts[i:i + batch_size]

            # Tokenize batch
            inputs = self.tokenizer(
                batch_texts,
                max_length=self.max_source_length,
                truncation=True,
                padding=True,
                return_tensors="pt"
            ).to(self.device)

            # Generate
            with torch.no_grad():
                outputs = self.model.generate(
                    **inputs,
                    max_length=max_length,
                    num_beams=self.num_beams,
                    length_penalty=self.length_penalty,
                    no_repeat_ngram_size=self.no_repeat_ngram_size,
                    early_stopping=self.early_stopping,
                )

            # Decode batch
            summaries = self.tokenizer.batch_decode(outputs, skip_special_tokens=True)

            for summary in summaries:
                results.append({
                    "summary": summary.strip(),
                    "source": "local",
                })

        return results

    def _summarize_with_llm(self, title: str, content: str) -> Dict:
        """
        Fallback summarization using LLM.

        Args:
            title: Article title
            content: Article content

        Returns:
            Dict with 'summary' and 'source'
        """
        try:
            from app.ai_models import AIModelFactory

            ai = AIModelFactory.get_model()

            # Truncate content if too long
            max_content = 4000  # ~1000 tokens
            if len(content) > max_content:
                content = content[:max_content] + "..."

            prompt = f"""Summarize the following article in 2-3 concise sentences.

Title: {title}

Content:
{content}

Summary:"""

            summary = ai.generate(prompt, max_tokens=200, temperature=0.3)

            return {
                "summary": summary.strip(),
                "source": "llm",
            }

        except Exception as e:
            logger.error(f"LLM fallback failed: {e}")
            # Return truncated content as last resort
            return {
                "summary": f"{title}. {content[:200]}...",
                "source": "fallback",
            }


# Singleton instance getter
_service_instance = None


def get_summarization_service() -> SummarizationService:
    """Get the singleton summarization service instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = SummarizationService()
    return _service_instance
