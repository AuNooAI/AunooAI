"""
SLM Integration Module

Provides hybrid SLM/LLM functionality for the automated ingest pipeline.
Allows seamless switching between fast local SLM models and LLM fallback.

Usage:
    from app.services.slm_integration import SLMIntegration

    slm = SLMIntegration()

    # Score relevance (uses SLM if available, LLM fallback)
    score = slm.score_relevance(topic, title, summary)

    # Enrich article (uses SLM if available, LLM fallback)
    enrichment = slm.enrich_article(title, summary)
"""

import logging
import os
from typing import Dict, List, Optional, Any, Tuple

logger = logging.getLogger(__name__)

# Environment variable to control SLM usage
SLM_ENABLED = os.getenv('SLM_ENABLED', 'true').lower() == 'true'
SLM_RELEVANCE_ENABLED = os.getenv('SLM_RELEVANCE_ENABLED', 'true').lower() == 'true'
SLM_ENRICHMENT_ENABLED = os.getenv('SLM_ENRICHMENT_ENABLED', 'true').lower() == 'true'
SLM_SUMMARIZATION_ENABLED = os.getenv('SLM_SUMMARIZATION_ENABLED', 'true').lower() == 'true'


class SLMIntegration:
    """
    Hybrid SLM/LLM integration for article processing.

    Provides a unified interface that:
    - Uses local SLM models when available and enabled
    - Falls back to LLM when SLM unavailable or disabled
    - Tracks usage statistics for monitoring
    - Supports A/B testing between SLM and LLM
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if SLMIntegration._initialized:
            return

        self._relevance_service = None
        self._enrichment_service = None
        self._summarization_service = None

        self._stats = {
            'relevance_slm': 0,
            'relevance_llm': 0,
            'enrichment_slm': 0,
            'enrichment_llm': 0,
            'summarization_slm': 0,
            'summarization_llm': 0,
        }

        SLMIntegration._initialized = True
        logger.info(f"SLMIntegration initialized (enabled={SLM_ENABLED})")

    @property
    def relevance_service(self):
        """Lazy load relevance classifier service."""
        if self._relevance_service is None and SLM_ENABLED and SLM_RELEVANCE_ENABLED:
            try:
                from app.services.relevance_classifier_service import get_relevance_classifier
                self._relevance_service = get_relevance_classifier()
            except ImportError as e:
                logger.warning(f"Could not import relevance classifier: {e}")
        return self._relevance_service

    @property
    def enrichment_service(self):
        """Lazy load enrichment service."""
        if self._enrichment_service is None and SLM_ENABLED and SLM_ENRICHMENT_ENABLED:
            try:
                from app.services.enrichment_service import get_enrichment_service
                self._enrichment_service = get_enrichment_service()
            except ImportError as e:
                logger.warning(f"Could not import enrichment service: {e}")
        return self._enrichment_service

    @property
    def summarization_service(self):
        """Lazy load summarization service."""
        if self._summarization_service is None and SLM_ENABLED and SLM_SUMMARIZATION_ENABLED:
            try:
                from app.services.summarization_service import get_summarization_service
                self._summarization_service = get_summarization_service()
            except ImportError as e:
                logger.warning(f"Could not import summarization service: {e}")
        return self._summarization_service

    def is_relevance_available(self) -> bool:
        """Check if SLM relevance scoring is available."""
        service = self.relevance_service
        return service is not None and service.is_available()

    def is_enrichment_available(self) -> bool:
        """Check if SLM enrichment is available."""
        service = self.enrichment_service
        return service is not None and service.is_available()

    def is_summarization_available(self) -> bool:
        """Check if SLM summarization is available."""
        service = self.summarization_service
        return service is not None and service.is_available()

    def get_status(self) -> Dict[str, Any]:
        """Get integration status."""
        return {
            'slm_enabled': SLM_ENABLED,
            'relevance': {
                'enabled': SLM_RELEVANCE_ENABLED,
                'available': self.is_relevance_available(),
            },
            'enrichment': {
                'enabled': SLM_ENRICHMENT_ENABLED,
                'available': self.is_enrichment_available(),
            },
            'summarization': {
                'enabled': SLM_SUMMARIZATION_ENABLED,
                'available': self.is_summarization_available(),
            },
            'stats': self._stats,
        }

    def score_relevance(
        self,
        topic: str,
        title: str,
        summary: str,
        keywords: Optional[List[str]] = None,
        force_llm: bool = False,
    ) -> Dict[str, Any]:
        """
        Score article relevance to topic.

        Uses SLM if available, falls back to LLM.

        Args:
            topic: Target topic
            title: Article title
            summary: Article summary
            keywords: Optional keywords (used by LLM only)
            force_llm: Force LLM usage

        Returns:
            Dict with relevance_score, topic_alignment_score, confidence, source
        """
        # Try SLM first
        if not force_llm and self.is_relevance_available():
            try:
                result = self.relevance_service.classify(topic, title, summary)
                self._stats['relevance_slm'] += 1

                return {
                    'relevance_score': result['score'],
                    'topic_alignment_score': result['score'],
                    'keyword_relevance_score': result['score'],  # SLM doesn't separate these
                    'confidence_score': 0.9 if result['confidence'] == 'high' else 0.7 if result['confidence'] == 'medium' else 0.5,
                    'overall_match_explanation': f"SLM relevance: {result['confidence']} confidence",
                    'source': 'slm',
                }
            except Exception as e:
                logger.warning(f"SLM relevance failed, falling back to LLM: {e}")

        # Fallback to LLM
        self._stats['relevance_llm'] += 1
        return self._score_relevance_llm(topic, title, summary, keywords)

    def _score_relevance_llm(
        self,
        topic: str,
        title: str,
        summary: str,
        keywords: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Score relevance using LLM (existing pipeline)."""
        try:
            from app.relevance import RelevanceCalculator
            from app.config.config import get_topic_description

            # Get model from settings
            from app.database import get_database_instance
            db = get_database_instance()
            model_name = db.facade.get_setting('llm_model', 'gpt-5.4-mini')

            calculator = RelevanceCalculator(model_name=model_name)
            topic_description = get_topic_description(topic)

            keywords_str = ", ".join(keywords) if keywords else ""
            article_text = f"{title}\n\n{summary}"

            result = calculator.analyze_relevance(
                title=title,
                source="",
                content=article_text,
                topic=topic,
                keywords=keywords_str,
                topic_description=topic_description
            )

            result['source'] = 'llm'
            return result

        except Exception as e:
            logger.error(f"LLM relevance scoring failed: {e}")
            return {
                'relevance_score': 0.0,
                'topic_alignment_score': 0.0,
                'keyword_relevance_score': 0.0,
                'confidence_score': 0.0,
                'overall_match_explanation': f"Error: {str(e)}",
                'source': 'error',
            }

    def enrich_article(
        self,
        title: str,
        summary: str,
        topic: Optional[str] = None,
        force_llm: bool = False,
    ) -> Dict[str, Any]:
        """
        Enrich article with sentiment, time_to_impact, driver_type, etc.

        Uses SLM if available, falls back to LLM.

        Args:
            title: Article title
            summary: Article summary
            topic: Optional topic for context
            force_llm: Force LLM usage

        Returns:
            Dict with enrichment fields and source indicator
        """
        # Try SLM first
        if not force_llm and self.is_enrichment_available():
            try:
                result = self.enrichment_service.enrich(title, summary)
                self._stats['enrichment_slm'] += 1
                return result
            except Exception as e:
                logger.warning(f"SLM enrichment failed, falling back to LLM: {e}")

        # Fallback to LLM
        self._stats['enrichment_llm'] += 1
        return self._enrich_article_llm(title, summary, topic)

    def _enrich_article_llm(
        self,
        title: str,
        summary: str,
        topic: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Enrich article using LLM (existing pipeline)."""
        try:
            from app.analyzers.article_analyzer import ArticleAnalyzer
            from app.database import get_database_instance

            db = get_database_instance()
            model_name = db.facade.get_setting('llm_model', 'gpt-5.4-mini')

            analyzer = ArticleAnalyzer(model_name=model_name)

            # This would call the full analysis - simplified for now
            # In production, integrate with the actual ArticleAnalyzer
            result = {
                'sentiment': None,
                'time_to_impact': None,
                'driver_type': None,
                'future_signal': None,
                'category': None,
                'source': 'llm',
            }
            return result

        except Exception as e:
            logger.error(f"LLM enrichment failed: {e}")
            return {'source': 'error', 'error': str(e)}

    def summarize_article(
        self,
        title: str,
        content: str,
        force_llm: bool = False,
    ) -> Dict[str, Any]:
        """
        Generate article summary.

        Uses SLM if available, falls back to LLM.

        Args:
            title: Article title
            content: Article content
            force_llm: Force LLM usage

        Returns:
            Dict with summary and source indicator
        """
        # Try SLM first
        if not force_llm and self.is_summarization_available():
            try:
                result = self.summarization_service.summarize(title, content)
                self._stats['summarization_slm'] += 1
                return result
            except Exception as e:
                logger.warning(f"SLM summarization failed, falling back to LLM: {e}")

        # Fallback to LLM
        self._stats['summarization_llm'] += 1
        return self._summarize_article_llm(title, content)

    def _summarize_article_llm(
        self,
        title: str,
        content: str,
    ) -> Dict[str, Any]:
        """Summarize article using LLM."""
        try:
            from app.ai_models import AIModelFactory

            ai = AIModelFactory.get_model()

            # Truncate content
            max_content = 4000
            if len(content) > max_content:
                content = content[:max_content] + "..."

            prompt = f"""Summarize the following article in 2-3 concise sentences.

Title: {title}

Content:
{content}

Summary:"""

            response = ai.generate_sync(prompt, max_tokens=200, temperature=0.3)
            from app.ai_models import extract_content
            summary = extract_content(response)

            return {
                'summary': summary.strip(),
                'source': 'llm',
            }

        except Exception as e:
            logger.error(f"LLM summarization failed: {e}")
            return {
                'summary': f"{title}. {content[:200]}...",
                'source': 'fallback',
            }

    def get_stats(self) -> Dict[str, Any]:
        """Get usage statistics."""
        stats = self._stats.copy()

        # Calculate ratios
        for task in ['relevance', 'enrichment', 'summarization']:
            slm = stats.get(f'{task}_slm', 0)
            llm = stats.get(f'{task}_llm', 0)
            total = slm + llm
            stats[f'{task}_slm_ratio'] = slm / total if total > 0 else 0

        return stats

    def reset_stats(self):
        """Reset usage statistics."""
        self._stats = {
            'relevance_slm': 0,
            'relevance_llm': 0,
            'enrichment_slm': 0,
            'enrichment_llm': 0,
            'summarization_slm': 0,
            'summarization_llm': 0,
        }


# Singleton getter
_integration_instance = None


def get_slm_integration() -> SLMIntegration:
    """Get singleton SLM integration instance."""
    global _integration_instance
    if _integration_instance is None:
        _integration_instance = SLMIntegration()
    return _integration_instance
