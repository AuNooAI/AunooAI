"""
Automated Ingest Service

This service handles the automated ingestion pipeline that:
1. Fetches articles from TheNewsAPI for monitored keywords
2. Enriches with media bias and factuality data  
3. Scores articles for relevance
4. Applies quality control validation
5. Auto-saves articles that pass quality checks

Enhanced with:
- Async database operations for better performance
- Progressive processing with real-time WebSocket updates
- Concurrent article processing
- Optimized SQLite operations
"""

import logging
from typing import Dict, List, Optional, Any, AsyncGenerator
from datetime import datetime
from app.database import Database
from app.database_query_facade import DatabaseQueryFacade
from app.services.async_db import AsyncDatabase, get_async_database_instance
from app.models.media_bias import MediaBias
from app.relevance import RelevanceCalculator
from app.services.hybrid_relevance_service import get_hybrid_relevance_service
from app.services.enrichment_service import get_enrichment_service
from app.services.hybrid_enrichment_service import get_hybrid_enrichment_service
from app.services.summarization_service import get_summarization_service
from app.services.keybert_tagging_service import get_keybert_tagging_service
from app.services.explanation_service import get_explanation_service
from app.services.category_service import get_category_service
from app.analyzers.article_analyzer import ArticleAnalyzer
from app.ai_models import LiteLLMModel, get_available_models
import asyncio
import nest_asyncio
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
import requests
from app.config.config import load_config, get_topic_description
import time

# Allow nested event loops (needed when called from FastAPI routes)
nest_asyncio.apply()

# Set up logging
logger = logging.getLogger(__name__)

class AutomatedIngestService:
    """Service for automated article ingestion and processing"""
    
    def __init__(self, db: Database, config: Dict[str, Any] = None):
        """
        Initialize the automated ingest service

        Args:
            db: Database instance for data operations
            config: Optional configuration dictionary
        """
        self.db = db
        self.async_db = get_async_database_instance()
        self.config = config or load_config()
        self.relevance_calculator = None
        self.hybrid_relevance_service = None  # Lazy-loaded SLM-based relevance
        self.enrichment_service = None  # Lazy-loaded SLM-based enrichment
        self.hybrid_enrichment_service = None  # Lazy-loaded adaptive enrichment (GPT -> DeBERTa)
        self.use_adaptive_enrichment = self.config.get('use_adaptive_enrichment', True)  # Use hybrid enrichment that respects inference_mode
        self.summarization_service = None  # Lazy-loaded SLM-based summarization
        self.keybert_tagging_service = None  # Lazy-loaded KeyBERT tagging
        self.explanation_service = None  # Lazy-loaded SLM-based explanations
        self.category_service = None  # Lazy-loaded SLM-based category classification
        self.media_bias = MediaBias(db)
        self.article_analyzer = None

        # Dedicated executor for blocking I/O operations (e.g., Firecrawl scraping)
        # Using 3 workers allows parallel scraping of multiple keyword groups
        self._blocking_executor = ThreadPoolExecutor(
            max_workers=3,
            thread_name_prefix="blocking_io_"
        )

        # Configure logging
        self.logger = logger
        self.logger.info("AutomatedIngestService initialized with async capabilities and dedicated blocking I/O executor (3 workers)")

    def get_inference_mode(self) -> str:
        """
        Get the inference mode from database settings.

        Returns:
            'local' - Use local models only (DeBERTa, no LLM fallback)
            'hybrid' - Use local models with LLM fallback for low confidence (default)
            'external' - Use LLM for everything
        """
        try:
            from sqlalchemy import text
            result = self.db.facade._execute_with_rollback(
                text("SELECT inference_mode FROM keyword_monitor_settings WHERE id = 1")
            ).fetchone()
            mode = result[0] if result else 'hybrid'
            return mode
        except Exception as e:
            self.logger.warning(f"Failed to get inference mode, defaulting to hybrid: {e}")
            return 'hybrid'

    def get_llm_client(self, model_override: str = None) -> str:
        """
        Get the LLM model name to use for processing

        Args:
            model_override: Optional model name to override default

        Returns:
            LLM model name to use
        """
        if model_override:
            return model_override

        # Get from database settings
        try:
            configured_model = self.db.facade.get_configured_llm_model()
            if configured_model:
                return configured_model

            # If no model configured (None), use first available model
            available = get_available_models()
            if available and len(available) > 0:
                first_model = available[0].get('name')
                self.logger.info(f"No default model configured, using first available: {first_model}")
                return first_model
        except Exception as e:
            self.logger.warning(f"Could not get LLM settings from database: {e}")

        return "gpt-4o-mini"  # Ultimate fallback
    
    def get_llm_parameters(self) -> Dict[str, Any]:
        """
        Get LLM parameters from database settings
        
        Returns:
            Dictionary containing temperature and max_tokens
        """
        try:
            settings = self.db.facade.get_llm_parameters()
            if settings:
                return {
                    "temperature": settings[0] or 0.1,
                    "max_tokens": settings[1] or 1000
                }
        except Exception as e:
            self.logger.warning(f"Could not get LLM parameters from database: {e}")
        
        return {"temperature": 0.1, "max_tokens": 1000}  # Default fallback
    
    def enrich_article_with_bias(self, article_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enrich article with media bias and factuality data
        
        Args:
            article_data: Article data dictionary
            
        Returns:
            Enriched article data with bias information
        """
        try:
            source = article_data.get('news_source') or article_data.get('source')
            if not source:
                self.logger.warning(f"No source found for article: {article_data.get('uri', 'unknown')}")
                return article_data
            
            # Get bias information using existing MediaBias class
            bias_info = self.media_bias.get_bias_for_source(source)
            
            if bias_info:
                article_data.update({
                    'bias': bias_info.get('bias'),
                    'factual_reporting': bias_info.get('factual_reporting'),
                    'mbfc_credibility_rating': bias_info.get('mbfc_credibility_rating'),
                    'bias_source': bias_info.get('bias_source'),
                    'bias_country': bias_info.get('bias_country'),
                    'press_freedom': bias_info.get('press_freedom'),
                    'media_type': bias_info.get('media_type'),
                    'popularity': bias_info.get('popularity')
                })
                self.logger.debug(f"Enriched article {article_data.get('uri')} with bias data from {source}")
            else:
                self.logger.debug(f"No bias data found for source: {source}")
            
            return article_data
            
        except Exception as e:
            self.logger.error(f"Error enriching article with bias data: {e}")
            return article_data
    
    def analyze_article_content(self, article_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform full article analysis using hybrid SLM + LLM approach.

        SLM handles: sentiment, time_to_impact, driver_type, future_signal (classification)
        LLM handles: summary, explanations, category, tags (generation)

        Args:
            article_data: Article data dictionary

        Returns:
            Article data enriched with analysis results
        """
        try:
            # Prepare content for analysis
            article_text = article_data.get('summary', '') or article_data.get('content', '')
            title = article_data.get('title', '')
            source = article_data.get('news_source', '')
            uri = article_data.get('uri', '')

            if not article_text or not title:
                self.logger.warning(f"Insufficient content for analysis: {uri}")
                return article_data

            topic = article_data.get('topic')
            if not topic:
                self.logger.error(f"No topic specified for article {uri} - cannot determine ontology")
                return article_data

            # Step 1: Try SLM/Hybrid enrichment for classification fields
            slm_result = {}
            slm_fields_used = []
            enrichment_sources = {}

            try:
                if self.use_adaptive_enrichment:
                    # Use adaptive hybrid enrichment (GPT for new topics, DeBERTa for trained)
                    if not self.hybrid_enrichment_service:
                        self.hybrid_enrichment_service = get_hybrid_enrichment_service()

                    # Get inference mode to determine if we use local LLM (Qwen) instead of GPT
                    inference_mode = self.get_inference_mode()
                    use_local_llm = inference_mode == 'local'
                    llm_type = "Qwen" if use_local_llm else "GPT"

                    self.logger.info(f"    🔄 Using adaptive enrichment ({llm_type} fallback): {title[:50]}...")

                    # Run async coroutine (nest_asyncio applied at module level)
                    slm_result = asyncio.run(
                        self.hybrid_enrichment_service.enrich_article(
                            title=title,
                            summary=article_text,
                            topic=topic,
                            article_uri=uri,
                            use_local_llm=use_local_llm,
                        )
                    )

                    # Track which fields were handled and by which model
                    enrichment_sources = slm_result.get('sources', {})
                    for field in ['sentiment', 'time_to_impact', 'driver_type', 'future_signal']:
                        if field in slm_result and slm_result[field]:
                            slm_fields_used.append(field)

                    if slm_fields_used:
                        sources_str = ', '.join(f"{f}={enrichment_sources.get(f, '?')}" for f in slm_fields_used)
                        self.logger.info(f"    ✅ Adaptive enrichment: {sources_str}")

                    # Record confidence stats for frontend tracking (hybrid enrichment path)
                    # Only record for fields that used DeBERTa (not GPT)
                    try:
                        deberta_confidence_scores = {}
                        for field in ['sentiment', 'time_to_impact', 'driver_type', 'future_signal']:
                            if enrichment_sources.get(field) == 'deberta':
                                conf = slm_result.get(f'{field}_confidence', 0)
                                deberta_confidence_scores[field] = conf

                        if deberta_confidence_scores:
                            from app.routes.training_routes import get_confidence_tracker
                            tracker = get_confidence_tracker()
                            tracker.record(topic, deberta_confidence_scores)
                    except Exception as tracker_err:
                        self.logger.debug(f"Failed to record confidence stats (hybrid): {tracker_err}")

                else:
                    # Use standard DeBERTa enrichment service
                    if not self.enrichment_service:
                        self.enrichment_service = get_enrichment_service()

                    if self.enrichment_service.is_available():
                        self.logger.info(f"    🧠 Using SLM for classification: {title[:50]}...")
                        slm_result = self.enrichment_service.enrich(title=title, summary=article_text)

                        # Check which fields have high confidence and track scores
                        confidence_threshold = 0.6
                        confidence_scores = {}
                        for field in ['sentiment', 'time_to_impact', 'driver_type', 'future_signal']:
                            conf = slm_result.get(f'{field}_confidence', 0)
                            confidence_scores[field] = conf
                            if field in slm_result and conf >= confidence_threshold:
                                slm_fields_used.append(field)
                                enrichment_sources[field] = 'deberta'

                        # Calculate and log average confidence
                        avg_conf = sum(confidence_scores.values()) / len(confidence_scores) if confidence_scores else 0
                        conf_str = ', '.join(f"{f[:3]}={c:.2f}" for f, c in confidence_scores.items())

                        # Record confidence stats for frontend tracking
                        try:
                            from app.routes.training_routes import get_confidence_tracker
                            tracker = get_confidence_tracker()
                            tracker.record(topic, confidence_scores)
                        except Exception as tracker_err:
                            self.logger.debug(f"Failed to record confidence stats: {tracker_err}")

                        if slm_fields_used:
                            self.logger.info(f"    ✅ SLM confident for: {', '.join(slm_fields_used)} (avg={avg_conf:.2f}, {conf_str})")
                        else:
                            self.logger.info(f"    ⚠️ SLM low confidence (avg={avg_conf:.2f}, {conf_str}), will use LLM for all fields")

            except Exception as e:
                self.logger.warning(f"Enrichment failed, falling back to LLM: {e}")

            # Step 2: Use LLM for generative fields (summary, explanations) and low-confidence classifications
            # Initialize article analyzer if not already done
            if not self.article_analyzer:
                model_name = self.get_llm_client()
                ai_model = LiteLLMModel.get_instance(model_name)
                self.article_analyzer = ArticleAnalyzer(ai_model, use_cache=True)

            # Get topic-specific ontology
            from app.research import Research
            model_name = self.get_llm_client()
            research = Research(self.db, model_name=model_name)
            self.logger.info(f"    🤖 Using LLM ({model_name}) for summary & explanations")

            research.set_topic(topic)

            # Get ontology data
            try:
                loop = asyncio.get_running_loop()
                def run_async_in_thread(coro_func, *args):
                    return asyncio.run(coro_func(*args))

                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future_categories = executor.submit(run_async_in_thread, research.get_categories, topic)
                    future_signals_f = executor.submit(run_async_in_thread, research.get_future_signals, topic)
                    future_sentiments = executor.submit(run_async_in_thread, research.get_sentiments, topic)
                    future_time_to_impact = executor.submit(run_async_in_thread, research.get_time_to_impact, topic)
                    future_driver_types = executor.submit(run_async_in_thread, research.get_driver_types, topic)

                    categories = future_categories.result()
                    future_signals = future_signals_f.result()
                    sentiment_options = future_sentiments.result()
                    time_to_impact_options = future_time_to_impact.result()
                    driver_types = future_driver_types.result()
            except RuntimeError:
                categories = asyncio.run(research.get_categories(topic))
                future_signals = asyncio.run(research.get_future_signals(topic))
                sentiment_options = asyncio.run(research.get_sentiments(topic))
                time_to_impact_options = asyncio.run(research.get_time_to_impact(topic))
                driver_types = asyncio.run(research.get_driver_types(topic))

            # Perform LLM analysis for summary, explanations, and low-confidence fields
            analysis_result = self.article_analyzer.analyze_content(
                article_text=article_text,
                title=title,
                source=source,
                uri=uri,
                summary_length=50,
                summary_voice="neutral",
                summary_type="informative",
                categories=categories,
                future_signals=future_signals,
                sentiment_options=sentiment_options,
                time_to_impact_options=time_to_impact_options,
                driver_types=driver_types
            )

            # Step 3: Merge results - SLM for confident classifications, LLM for rest
            tags = analysis_result.get('tags', [])
            tags_str = ','.join(tags) if isinstance(tags, list) else str(tags) if tags else None

            # Start with LLM results
            final_result = {
                'summary': analysis_result.get('summary'),
                'category': analysis_result.get('category'),
                'sentiment': analysis_result.get('sentiment'),
                'future_signal': analysis_result.get('future_signal'),
                'future_signal_explanation': analysis_result.get('future_signal_explanation'),
                'sentiment_explanation': analysis_result.get('sentiment_explanation'),
                'time_to_impact': analysis_result.get('time_to_impact'),
                'time_to_impact_explanation': analysis_result.get('time_to_impact_explanation'),
                'driver_type': analysis_result.get('driver_type'),
                'driver_type_explanation': analysis_result.get('driver_type_explanation'),
                'tags': tags_str,
                'analyzed': True,
                '_enrichment_method': 'llm_only'
            }

            # Override with SLM results for high-confidence fields
            if slm_fields_used:
                for field in slm_fields_used:
                    if field in slm_result:
                        final_result[field] = slm_result[field]
                final_result['_enrichment_method'] = f"hybrid_slm({','.join(slm_fields_used)})"

            # Track which model was used for each field (for UI reporting)
            # Fields not in slm_fields_used were handled by LLM
            for field in ['sentiment', 'time_to_impact', 'driver_type', 'future_signal']:
                if field not in enrichment_sources:
                    enrichment_sources[field] = 'gpt'  # LLM fallback was used

            final_result['enrichment_sources'] = enrichment_sources

            article_data.update(final_result)

            method = final_result.get('_enrichment_method', 'unknown')
            self.logger.info(f"    📝 Enriched {uri[:50]}: method={method}, sentiment={final_result.get('sentiment')}, summary_len={len(final_result.get('summary', ''))}")

            return article_data

        except Exception as e:
            self.logger.error(f"Error analyzing article content: {e}")
            return article_data
    
    def score_article_relevance(self, article_data: Dict[str, Any], topic: str, keywords: List[str]) -> Dict[str, Any]:
        """
        Score article relevance using the Hybrid Relevance Service (SLM + LLM fallback).

        The hybrid approach uses:
        1. Embedding similarity (fast, works for any topic)
        2. Fine-tuned classifier (accurate for trained topics)
        3. LLM fallback (for uncertain scores in 0.3-0.7 range)

        Args:
            article_data: Article data dictionary
            topic: Topic name for context
            keywords: List of keywords to check relevance against

        Returns:
            Dictionary containing relevance score and details
        """
        try:
            # Initialize hybrid relevance service if not already done
            if not self.hybrid_relevance_service:
                self.hybrid_relevance_service = get_hybrid_relevance_service()
                self.hybrid_relevance_service.load_models()
                self.logger.info("🤖 Initialized Hybrid Relevance Service (embedding + classifier + LLM fallback)")

            # Prepare article text
            article_full_content = article_data.get('content', '')
            article_summary = article_data.get('summary', '')
            article_content = article_full_content or article_summary
            title = article_data.get('title', '')

            # Log content source for debugging
            content_source = "full content" if article_full_content else ("summary" if article_summary else "none")

            # Get inference mode to control LLM usage
            inference_mode = self.get_inference_mode()
            use_llm_fallback = inference_mode in ('hybrid', 'external')
            force_llm = inference_mode == 'external'

            mode_label = {'local': '🏠 Local', 'hybrid': '🔄 Hybrid', 'external': '☁️ External'}
            self.logger.info(f"📊 {mode_label.get(inference_mode, inference_mode)} relevance check using {content_source} ({len(article_content)} chars) for: {title[:60]}...")

            # In local mode, use Qwen for LLM fallback instead of GPT
            use_local_llm = inference_mode == 'local'

            # Score using hybrid service (embedding + classifier + optional LLM fallback)
            hybrid_result = self.hybrid_relevance_service.score_relevance(
                topic=topic,
                title=title,
                summary=article_content,
                threshold=self.get_relevance_threshold(),
                use_llm_fallback=use_llm_fallback,
                force_llm=force_llm,
                use_local_llm=use_local_llm
            )

            # Map hybrid result to expected pipeline format
            relevance_result = {
                "relevance_score": hybrid_result.get("score", 0.0),
                "topic_alignment_score": hybrid_result.get("score", 0.0),  # Use combined score
                "keyword_relevance_score": hybrid_result.get("embedding_score", 0.0),  # Embedding as keyword proxy
                "confidence_score": 1.0 if hybrid_result.get("confidence") == "high" else 0.5,
                "overall_match_explanation": f"Hybrid scoring: {hybrid_result.get('method')} (embed={hybrid_result.get('embedding_score', 0):.2f}, class={hybrid_result.get('classifier_score', 0):.2f})",
                # Additional hybrid metadata
                "_hybrid_method": hybrid_result.get("method"),
                "_hybrid_confidence": hybrid_result.get("confidence"),
                "_embedding_score": hybrid_result.get("embedding_score"),
                "_classifier_score": hybrid_result.get("classifier_score"),
                "_llm_score": hybrid_result.get("llm_score"),
            }

            # Record relevance confidence stats for frontend tracking
            try:
                from app.routes.training_routes import get_relevance_confidence_tracker
                tracker = get_relevance_confidence_tracker()
                tracker.record(
                    topic=topic,
                    score=hybrid_result.get("score", 0.0),
                    classifier_score=hybrid_result.get("classifier_score"),
                    embedding_score=hybrid_result.get("embedding_score"),
                    method=hybrid_result.get("method", "unknown"),
                    relevant=hybrid_result.get("relevant")
                )
            except Exception as tracker_err:
                self.logger.debug(f"Failed to record relevance confidence stats: {tracker_err}")

            self.logger.debug(f"Hybrid relevance for {article_data.get('uri')}: score={relevance_result['relevance_score']:.3f}, method={hybrid_result.get('method')}")

            return relevance_result

        except Exception as e:
            self.logger.error(f"Error in hybrid relevance scoring: {e}")
            # Fall back to LLM-only scoring if hybrid fails
            self.logger.info("Falling back to LLM-only relevance scoring...")
            return self._score_article_relevance_llm_only(article_data, topic, keywords)

    def _score_article_relevance_llm_only(self, article_data: Dict[str, Any], topic: str, keywords: List[str]) -> Dict[str, Any]:
        """Fallback to full LLM-based relevance scoring if hybrid service fails."""
        try:
            if not self.relevance_calculator:
                from app.relevance import RelevanceCalculator
                model_name = self.get_llm_client()
                self.relevance_calculator = RelevanceCalculator(model_name=model_name)

            topic_description = get_topic_description(topic)
            article_full_content = article_data.get('content', '')
            article_summary = article_data.get('summary', '')
            article_content = article_full_content or article_summary
            article_text = f"{article_data.get('title', '')}\n\n{article_content}"

            keywords_str = ", ".join(keywords) if isinstance(keywords, list) else str(keywords)
            return self.relevance_calculator.analyze_relevance(
                title=article_data.get('title', ''),
                source=article_data.get('news_source', ''),
                content=article_text,
                topic=topic,
                keywords=keywords_str,
                topic_description=topic_description
            )
        except Exception as e:
            self.logger.error(f"LLM fallback also failed: {e}")
            return {
                "relevance_score": 0.0,
                "topic_alignment_score": 0.0,
                "keyword_relevance_score": 0.0,
                "confidence_score": 0.0,
                "overall_match_explanation": f"Error calculating relevance: {str(e)}"
            }
    
    def quality_check_article(self, article_data: Dict[str, Any], content: str = None) -> Dict[str, Any]:
        """
        Perform quality control check on article content
        
        Args:
            article_data: Article data dictionary
            content: Optional full article content
            
        Returns:
            Dictionary containing quality assessment results
        """
        try:
            # Prepare content review request
            review_request = {
                "article_title": article_data.get('title', ''),
                "article_summary": article_data.get('summary', ''),
                "article_source": article_data.get('news_source', ''),
                "model_name": self.get_llm_client(),
                "article_url": article_data.get('uri', '')
            }
            
            # For now, we'll return a placeholder quality check
            # In a real implementation, this would call the quality control endpoint
            quality_result = {
                "quality_score": 0.8,  # Placeholder score
                "quality_issues": None,
                "approved": True
            }
            
            self.logger.debug(f"Quality check for article {article_data.get('uri')}: {quality_result}")
            
            return quality_result
            
        except Exception as e:
            self.logger.error(f"Error performing quality check: {e}")
            return {
                "quality_score": 0.0,
                "quality_issues": f"Quality check failed: {str(e)}",
                "approved": False
            }
    
    async def scrape_article_content(self, uri: str) -> Optional[str]:
        """
        Scrape full article content from URI with token limiting
        
        Args:
            uri: Article URI to scrape
            
        Returns:
            Scraped content or None if failed
        """
        try:
            self.logger.debug(f"Scraping content for URI: {uri}")
            
            # Check if we already have raw content
            existing_raw = await self.async_db.get_raw_article_async(uri)
            if existing_raw and existing_raw.get('raw_markdown'):
                self.logger.debug(f"Found existing raw content ({len(existing_raw['raw_markdown'])} chars)")
                return existing_raw['raw_markdown']
            
            # Initialize Research class for scraping (reuse existing infrastructure)
            from app.research import Research
            research = Research(self.db)
            
            # Scrape the article
            scrape_result = await research.scrape_article(uri)
            
            if scrape_result and scrape_result.get('content'):
                content = scrape_result['content']
                
                # Apply token limiting - truncate to reasonable size for processing
                # Use ArticleAnalyzer's truncate_text method with 65K char limit (roughly 16K tokens)
                from app.analyzers.article_analyzer import ArticleAnalyzer
                truncated_content = ArticleAnalyzer.truncate_text(None, content, max_chars=65000)
                
                if len(content) > len(truncated_content):
                    self.logger.info(f"Truncated content from {len(content)} to {len(truncated_content)} chars")
                
                return truncated_content
            else:
                self.logger.warning(f"No content returned from scraping: {uri}")
                return None
                
        except Exception as e:
            self.logger.error(f"Error scraping article content: {e}")
            return None
    
    async def process_articles_progressive(
        self, 
        articles: List[Dict[str, Any]], 
        topic: str = None, 
        keywords: List[str] = None,
        batch_size: int = 5,
        job_id: str = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Process articles progressively with real-time updates
        
        Args:
            articles: List of articles to process
            topic: Topic for context
            keywords: Keywords for relevance
            batch_size: How many articles to process concurrently
            job_id: Job ID for WebSocket updates
        
        Yields:
            Progress updates and results
        """
        total_articles = len(articles)
        processed_count = 0
        results = {
            "processed": 0,
            "enriched": 0,
            "relevant": 0,
            "quality_passed": 0,
            "saved": 0,
            "vector_indexed": 0,
            "errors": []
        }
        
        self.logger.info(f"🚀 Starting progressive processing of {total_articles} articles")
        
        try:
            # Send WebSocket update if job_id provided
            if job_id:
                try:
                    from app.routes.websocket_routes import send_progress_update
                    await send_progress_update(job_id, {
                        "progress": 0,
                        "processed": 0,
                        "total": total_articles,
                        "message": f"Starting processing of {total_articles} articles",
                        "stage": "initializing"
                    })
                except Exception as e:
                    self.logger.warning(f"Failed to send WebSocket update: {e}")
            
            # Process in batches to avoid overwhelming the system
            for i in range(0, total_articles, batch_size):
                batch = articles[i:i + batch_size]
                batch_number = (i // batch_size) + 1
                total_batches = (total_articles + batch_size - 1) // batch_size
                
                self.logger.info(f"📦 Processing batch {batch_number}/{total_batches} ({len(batch)} articles)")
                
                # Process batch concurrently
                tasks = []
                for article in batch:
                    task = asyncio.create_task(
                        self._process_single_article_async(article, topic, keywords)
                    )
                    tasks.append(task)
                
                # Wait for batch completion with timeout
                try:
                    batch_results = await asyncio.wait_for(
                        asyncio.gather(*tasks, return_exceptions=True), 
                        timeout=300  # 5 minute timeout per batch
                    )
                    
                    # Process batch results
                    for result in batch_results:
                        if isinstance(result, Exception):
                            results["errors"].append(str(result))
                        elif isinstance(result, dict):
                            if result.get("status") == "success":
                                results["saved"] += 1
                                results["vector_indexed"] += 1
                                results["quality_passed"] += 1
                            elif result.get("status") == "filtered":
                                pass  # Article was filtered out
                            elif result.get("status") == "error":
                                results["errors"].append(result.get("error", "Unknown error"))
                            
                            results["processed"] += 1
                            results["enriched"] += 1
                            if result.get("relevance_score", 0) >= self.get_relevance_threshold():
                                results["relevant"] += 1
                    
                    processed_count += len(batch)
                    progress_percentage = (processed_count / total_articles) * 100
                    
                    # Yield progress update
                    progress_data = {
                        "type": "progress",
                        "processed": processed_count,
                        "total": total_articles,
                        "percentage": progress_percentage,
                        "batch_number": batch_number,
                        "total_batches": total_batches,
                        "current_results": results.copy(),
                        "timestamp": datetime.utcnow().isoformat(),
                        "stage": "processing"
                    }
                    
                    yield progress_data
                    
                    # Send WebSocket update
                    if job_id:
                        try:
                            from app.routes.websocket_routes import send_batch_update
                            await send_batch_update(job_id, {
                                "progress": progress_percentage,
                                "processed": processed_count,
                                "total": total_articles,
                                "batch_completed": batch_number,
                                "total_batches": total_batches,
                                "message": f"Completed batch {batch_number}/{total_batches}",
                                "results": results.copy()
                            })
                        except Exception as e:
                            self.logger.warning(f"Failed to send WebSocket batch update: {e}")
                    
                    # Brief pause to yield control
                    await asyncio.sleep(0.1)
                    
                except asyncio.TimeoutError:
                    error_msg = f"Batch {batch_number} timed out"
                    self.logger.error(error_msg)
                    results["errors"].append(error_msg)
                    
                    yield {
                        "type": "error",
                        "message": error_msg,
                        "processed": processed_count,
                        "total": total_articles,
                        "batch_number": batch_number
                    }
            
            # Final results
            final_results = {
                "type": "completed",
                "processed": processed_count,
                "total": total_articles,
                "percentage": 100,
                "final_results": results,
                "timestamp": datetime.utcnow().isoformat(),
                "stage": "completed"
            }
            
            yield final_results
            
            # Send final WebSocket update
            if job_id:
                try:
                    from app.routes.websocket_routes import send_completion_update
                    await send_completion_update(job_id, results)
                except Exception as e:
                    self.logger.warning(f"Failed to send WebSocket completion update: {e}")
            
            self.logger.info(f"✅ Progressive processing completed: {results}")
            
        except Exception as e:
            error_msg = f"Progressive processing failed: {str(e)}"
            self.logger.error(error_msg)
            results["errors"].append(error_msg)
            
            yield {
                "type": "error",
                "message": error_msg,
                "processed": processed_count,
                "total": total_articles,
                "final_results": results
            }
            
            # Send error WebSocket update
            if job_id:
                try:
                    from app.routes.websocket_routes import send_error_update
                    await send_error_update(job_id, error_msg)
                except Exception as e:
                    self.logger.warning(f"Failed to send WebSocket error update: {e}")

    async def _process_single_article_async(
        self,
        article: Dict[str, Any],
        topic: str,
        keywords: List[str],
        relevance_threshold_override: float = None
    ) -> Dict[str, Any]:
        """Process a single article asynchronously with optimized database operations

        Args:
            relevance_threshold_override: If provided, use this threshold instead of global.
                                          If 0, skip relevance filtering entirely.
        """
        article_uri = article.get('uri', 'unknown')
        article_title = article.get('title', 'Unknown Title')

        # CRITICAL: Preserve original data from API throughout processing
        original_title = article.get('title', '')
        original_summary = article.get('summary', '')
        original_source = article.get('news_source', '')
        original_pub_date = article.get('publication_date', '')

        try:
            self.logger.debug(f"🔄 Processing article: {article_title}")
            self.logger.debug(f"📝 Original title: {original_title[:100]}")

            # Step 1: QUICK relevance check FIRST (before expensive operations)
            # Use only title and existing summary to save costs

            # Determine relevance threshold: override=0 means skip filtering entirely
            self.logger.info(f"🔍 Relevance override for {article_uri}: {relevance_threshold_override} (type: {type(relevance_threshold_override).__name__})")
            if relevance_threshold_override is not None and relevance_threshold_override == 0:
                # Skip relevance filtering for this article (e.g., RSS feed with threshold=0)
                self.logger.debug(f"⚡ Skipping relevance filtering for {article_uri} (threshold override = 0)")
                quick_relevance_score = 1.0  # Treat as fully relevant
                quick_relevance_result = {"relevance_score": 1.0, "keyword_relevance_score": 1.0, "topic_alignment_score": 1.0, "confidence_score": 1.0}
                relevance_threshold = 0
            else:
                try:
                    # Do a quick relevance check with just title + summary (no scraping/LLM yet)
                    quick_relevance_result = await self._score_article_relevance_async(
                        article, topic, keywords
                    )
                    quick_relevance_score = quick_relevance_result.get("relevance_score", 0)
                    # Use override if provided, otherwise use global setting
                    relevance_threshold = relevance_threshold_override if relevance_threshold_override is not None else self.get_relevance_threshold()

                    self.logger.debug(f"🎯 Quick relevance check: {quick_relevance_score} (threshold: {relevance_threshold})")

                    # If article fails relevance threshold, stop processing immediately
                    if quick_relevance_score < relevance_threshold:
                        self.logger.info(f"⚡ Article {article_uri} filtered early (score: {quick_relevance_score} < {relevance_threshold}) - saving costs")

                        # Save with minimal data to database
                        try:
                            article.update({
                                "topic": topic,
                                "ingest_status": "filtered_relevance",
                                # Populate ALL three score fields from relevance result
                                "keyword_relevance_score": quick_relevance_result.get("keyword_relevance_score", quick_relevance_score),
                                "topic_alignment_score": quick_relevance_result.get("topic_alignment_score", quick_relevance_score),
                                "confidence_score": quick_relevance_result.get("confidence_score", quick_relevance_score),
                                "overall_match_explanation": quick_relevance_result.get("overall_match_explanation", "")
                            })
                            await self.async_db.save_below_threshold_article(article)
                            self.db.facade.mark_article_as_below_threshold(article_uri)
                        except Exception as e:
                            self.logger.warning(f"Failed to save below-threshold article: {e}")

                        return {
                            "status": "filtered",
                            "uri": article_uri,
                            "relevance_score": quick_relevance_score,
                            "reason": "relevance_threshold",
                            "threshold": relevance_threshold
                        }

                except Exception as e:
                    self.logger.error(f"Quick relevance check failed for {article_uri}: {e}")
                    # Save article with error status but preserve attempt record
                    article.update({
                        "topic": topic,
                        "ingest_status": "relevance_check_failed",
                        "keyword_relevance_score": 0.0,
                        "topic_alignment_score": 0.0,
                        "confidence_score": 0.0,
                        "overall_match_explanation": f"Relevance check failed: {str(e)}"
                    })
                    await self.async_db.save_below_threshold_article(article)
                    self.logger.info(f"Saved article {article_uri} with relevance_check_failed status")
                    # Return early - skip enrichment for this article
                    return {
                        "status": "error",
                        "uri": article_uri,
                        "error": str(e),
                        "reason": "relevance_check_failed"
                    }

            # Step 2: Article PASSED quick check - now do expensive operations
            self.logger.info(f"✅ Article {article_uri} passed quick check (score: {quick_relevance_score}) - proceeding with enrichment")

            # Concurrent bias enrichment and content scraping
            bias_task = asyncio.create_task(
                self._enrich_article_with_bias_async(article)
            )

            # Check if we already have pre-scraped content (from batch processing)
            raw_content = article.get('_scraped_content')

            if raw_content:
                self.logger.debug(f"📄 Using pre-scraped content for {article_uri} ({len(raw_content)} chars)")
                # Only need to wait for bias enrichment
                try:
                    enriched_article = await bias_task
                except Exception as e:
                    self.logger.error(f"Bias enrichment failed for {article_uri}: {e}")
                    enriched_article = article
            else:
                # No pre-scraped content, scrape it now
                content_task = asyncio.create_task(
                    self.scrape_article_content(article_uri)
                )

                # Wait for both to complete
                try:
                    enriched_article, raw_content = await asyncio.gather(
                        bias_task, content_task, return_exceptions=True
                    )
                except Exception as e:
                    self.logger.error(f"Error in concurrent operations for {article_uri}: {e}")
                    enriched_article = article
                    raw_content = None

                # Handle exceptions from concurrent operations
                if isinstance(enriched_article, Exception):
                    self.logger.warning(f"Bias enrichment failed for {article_uri}: {enriched_article}")
                    enriched_article = article  # Fallback to original
                if isinstance(raw_content, Exception):
                    self.logger.warning(f"Content scraping failed for {article_uri}: {raw_content}")
                    raw_content = None

            # CRITICAL: Ensure original data is preserved after bias enrichment
            # IMPORTANT: Do NOT overwrite summary - it may have been generated by LLM
            enriched_article['title'] = enriched_article.get('title') or original_title
            # enriched_article['summary'] = enriched_article.get('summary') or original_summary  # REMOVED - prevents overwriting AI summaries
            enriched_article['news_source'] = enriched_article.get('news_source') or original_source
            enriched_article['publication_date'] = enriched_article.get('publication_date') or original_pub_date

            # Save raw content if available
            if raw_content:
                try:
                    await self.async_db.save_raw_article_async(article_uri, raw_content, topic)
                    self.logger.debug(f"📄 Raw content saved for {article_uri}")
                except Exception as e:
                    self.logger.warning(f"Failed to save raw content for {article_uri}: {e}")

            # Step 3: LLM analysis with timeout (only for relevant articles)
            try:
                enriched_article = await asyncio.wait_for(
                    self._analyze_article_content_async(enriched_article, topic),
                    timeout=60  # 1 minute timeout
                )
                self.logger.debug(f"🧠 LLM analysis completed for {article_uri}")

                # CRITICAL: Re-ensure original data after LLM analysis (in case it got lost)
                # IMPORTANT: Do NOT overwrite summary - LLM analysis generates the proper summary
                enriched_article['title'] = enriched_article.get('title') or original_title
                # enriched_article['summary'] = enriched_article.get('summary') or original_summary  # REMOVED - prevents overwriting AI summaries
                enriched_article['news_source'] = enriched_article.get('news_source') or original_source
                enriched_article['publication_date'] = enriched_article.get('publication_date') or original_pub_date

            except asyncio.TimeoutError:
                self.logger.warning(f"LLM analysis timed out for {article_uri}")
                enriched_article["analysis_error"] = "LLM analysis timed out"
            except Exception as e:
                self.logger.error(f"LLM analysis failed for {article_uri}: {e}")
                enriched_article["analysis_error"] = str(e)

            # Step 4: Final relevance scoring with full content
            try:
                relevance_result = await self._score_article_relevance_async(
                    enriched_article, topic, keywords
                )
                enriched_article.update(relevance_result)
                self.logger.debug(f"🎯 Final relevance scoring completed for {article_uri}")
            except Exception as e:
                self.logger.error(f"Final relevance scoring failed for {article_uri}: {e}")
                relevance_result = {
                    "relevance_score": quick_relevance_score,
                    "topic_alignment_score": quick_relevance_score,
                    "keyword_relevance_score": quick_relevance_score,
                    "confidence_score": quick_relevance_score,
                    "overall_match_explanation": f"Final scoring failed, using quick score: {str(e)}"
                }
                enriched_article.update(relevance_result)

            # Step 5: Check final relevance threshold (double-check after full analysis)
            relevance_score = relevance_result.get("relevance_score", quick_relevance_score)
            # Use the override threshold if provided, otherwise use global setting
            # Note: relevance_threshold was already set earlier for override=0 case
            if relevance_threshold_override is not None:
                if relevance_threshold_override == 0:
                    relevance_threshold = 0  # Skip filtering for RSS feeds with threshold=0
                else:
                    relevance_threshold = relevance_threshold_override
            else:
                relevance_threshold = self.get_relevance_threshold()

            if relevance_score >= relevance_threshold:
                # Step 5: Quality check (simplified for async)
                try:
                    quality_result = await self._quality_check_article_async(enriched_article)
                    enriched_article.update(quality_result)
                    self.logger.debug(f"🔍 Quality check completed for {article_uri}")
                except Exception as e:
                    self.logger.error(f"Quality check failed for {article_uri}: {e}")
                    quality_result = {"quality_score": 0.0, "approved": False, "quality_issues": str(e)}
                    enriched_article.update(quality_result)
                
                if quality_result.get("approved", False):
                    # CRITICAL: Validate enrichment succeeded before approving
                    if not enriched_article.get("analyzed", False):
                        self.logger.error(
                            f"❌ Enrichment validation failed for {article_uri}: "
                            f"Article passed quality check but 'analyzed' flag is False. "
                            f"This indicates enrichment failed silently. Marking as enrichment_failed."
                        )
                        return {
                            "status": "error",
                            "uri": article_uri,
                            "error": "Enrichment failed - analyzed=False after quality check"
                        }

                    # Step 6: Async database update
                    try:
                        enriched_article.update({
                            "ingest_status": "approved",
                            "auto_ingested": True,
                            "article_origin": "aunoo"
                        })
                        
                        success = await self.async_db.update_article_with_enrichment(enriched_article)

                        if success:
                            # Step 7: Vector database upsert (kept async but with timeout)
                            try:
                                await asyncio.wait_for(
                                    self._upsert_to_vector_db_async(enriched_article, raw_content),
                                    timeout=30  # 30 second timeout
                                )
                                self.logger.debug(f"🔍 Vector indexing completed for {article_uri}")
                            except asyncio.TimeoutError:
                                self.logger.warning(f"Vector indexing timed out for {article_uri}")
                            except Exception as e:
                                self.logger.error(f"Vector indexing failed for {article_uri}: {e}")
                            
                            return {
                                "status": "success",
                                "uri": article_uri,
                                "relevance_score": relevance_score,
                                "quality_score": quality_result.get("quality_score")
                            }
                        else:
                            return {
                                "status": "error",
                                "uri": article_uri,
                                "error": "Database update failed"
                            }
                    except Exception as e:
                        return {
                            "status": "error",
                            "uri": article_uri,
                            "error": f"Database operation failed: {str(e)}"
                        }
                else:
                    return {
                        "status": "filtered",
                        "uri": article_uri,
                        "relevance_score": relevance_score,
                        "reason": "quality_check_failed",
                        "quality_issues": quality_result.get("quality_issues")
                    }
            else:
                # Save article with relevance scores even though it failed threshold
                # This ensures the article is visible in the UI with proper context
                try:
                    # Prepare article data with relevance scores
                    enriched_article.update({
                        "topic": topic,  # Ensure topic is set
                        "ingest_status": "filtered_relevance"
                    })

                    # Save to articles table with relevance scores
                    await self.async_db.save_below_threshold_article(enriched_article)
                    self.logger.debug(f"Saved below-threshold article {article_uri} with relevance scores")

                    # Mark as below threshold in keyword_article_matches
                    self.db.facade.mark_article_as_below_threshold(article_uri)
                    self.logger.debug(f"Marked article {article_uri} as below threshold in keyword_article_matches")
                except Exception as e:
                    self.logger.warning(f"Failed to save below-threshold article: {e}")

                return {
                    "status": "filtered",
                    "uri": article_uri,
                    "relevance_score": relevance_score,
                    "reason": "relevance_threshold",
                    "threshold": relevance_threshold
                }
                
        except Exception as e:
            self.logger.error(f"Error processing article {article_uri}: {e}")
            return {
                "status": "error",
                "uri": article_uri,
                "error": str(e)
            }

    async def _enrich_article_with_bias_async(self, article_data: Dict[str, Any]) -> Dict[str, Any]:
        """Async version of bias enrichment"""
        # For now, this is just a wrapper around the sync version
        # Could be optimized further with async bias lookups
        return self.enrich_article_with_bias(article_data)

    def _check_slm_services_available(self) -> bool:
        """Check if all SLM services are available for full SLM mode."""
        try:
            # Check explanation service
            if not self.explanation_service:
                self.explanation_service = get_explanation_service()
            if not self.explanation_service.is_available():
                return False

            # Check category service
            if not self.category_service:
                self.category_service = get_category_service()
            if not self.category_service.is_available():
                return False

            # Check tagging service
            if not self.keybert_tagging_service:
                self.keybert_tagging_service = get_keybert_tagging_service()
            if not self.keybert_tagging_service.is_hybrid_available():
                return False

            return True
        except Exception:
            return False

    async def _analyze_article_content_async(self, article_data: Dict[str, Any], topic: str) -> Dict[str, Any]:
        """
        Async version of article analysis using hybrid SLM + LLM approach.

        SLM handles:
        - sentiment, time_to_impact, driver_type, future_signal (DeBERTa classification)
        - summary (vLLM Phi-3 local inference)

        LLM handles (fallback only): explanations, category, tags (generation)
        """
        try:
            # Prepare content for analysis
            article_text = article_data.get('summary', '') or article_data.get('content', '')
            title = article_data.get('title', '')
            source = article_data.get('news_source', '')
            uri = article_data.get('uri', '')

            if not article_text or not title:
                self.logger.warning(f"Insufficient content for analysis: {uri}")
                return article_data

            if not topic:
                topic = article_data.get('topic')
            if not topic:
                self.logger.error(f"No topic specified for article {uri} - cannot determine ontology")
                return article_data

            if not article_data.get('topic'):
                article_data['topic'] = topic

            # Step 1: Try SLM enrichment for classification fields
            slm_result = {}
            slm_fields_used = []
            enrichment_sources = {}  # Track which model (deberta/llm) was used for each field
            try:
                if not self.enrichment_service:
                    self.enrichment_service = get_enrichment_service()

                if self.enrichment_service.is_available():
                    self.logger.info(f"    🧠 SLM enrichment for: {title[:50]}...")
                    loop = asyncio.get_event_loop()
                    slm_result = await loop.run_in_executor(
                        None,
                        lambda: self.enrichment_service.enrich(title=title, summary=article_text)
                    )

                    # Check which fields have high confidence and track scores
                    confidence_threshold = 0.6
                    confidence_scores = {}
                    for field in ['sentiment', 'time_to_impact', 'driver_type', 'future_signal']:
                        conf = slm_result.get(f'{field}_confidence', 0)
                        confidence_scores[field] = conf
                        if field in slm_result and conf >= confidence_threshold:
                            slm_fields_used.append(field)
                            enrichment_sources[field] = 'deberta'

                    # Calculate and log average confidence
                    avg_conf = sum(confidence_scores.values()) / len(confidence_scores) if confidence_scores else 0
                    conf_str = ', '.join(f"{f[:3]}={c:.2f}" for f, c in confidence_scores.items())

                    # Record confidence stats for frontend tracking
                    try:
                        from app.routes.training_routes import get_confidence_tracker
                        tracker = get_confidence_tracker()
                        tracker.record(topic, confidence_scores)
                    except Exception as tracker_err:
                        self.logger.debug(f"Failed to record confidence stats: {tracker_err}")

                    # Record DeBERTa latency for model config
                    if slm_result.get('latency_ms') and slm_result.get('source') == 'slm':
                        try:
                            from app.routes.training_routes import get_latency_tracker
                            get_latency_tracker().record('DeBERTa', slm_result['latency_ms'])
                        except Exception:
                            pass

                    if slm_fields_used:
                        self.logger.info(f"    ✅ SLM confident: {', '.join(slm_fields_used)} (avg={avg_conf:.2f}, {conf_str})")
                    else:
                        self.logger.info(f"    ⚠️ SLM low confidence (avg={avg_conf:.2f}, {conf_str}), using LLM for all")
            except Exception as e:
                self.logger.warning(f"SLM enrichment failed: {e}")

            # Step 1.5: Try local summarization (vLLM Phi-3) before LLM
            slm_summary = None
            summary_source = "llm"
            try:
                if not self.summarization_service:
                    self.summarization_service = get_summarization_service()

                if self.summarization_service.is_available():
                    self.logger.info(f"    📝 Local summarization for: {title[:50]}...")
                    loop = asyncio.get_event_loop()
                    summary_result = await loop.run_in_executor(
                        None,
                        lambda: self.summarization_service.summarize(title=title, content=article_text)
                    )
                    if summary_result and summary_result.get('summary'):
                        slm_summary = summary_result['summary']
                        summary_source = summary_result.get('source', 'vllm')
                        self.logger.info(f"    ✅ Summary generated via {summary_source} ({len(slm_summary)} chars)")
                        # Record Phi-3 latency for model config
                        if summary_result.get('latency_ms'):
                            try:
                                from app.routes.training_routes import get_latency_tracker
                                get_latency_tracker().record('Phi-3', summary_result['latency_ms'])
                            except Exception:
                                pass
            except Exception as e:
                self.logger.warning(f"Local summarization failed, falling back to LLM: {e}")

            # Step 2: Get ontology data for classification (needed for SLM category service)
            from app.research import Research
            model_name = self.get_llm_client()
            research = Research(self.db, model_name=model_name)
            research.set_topic(topic)

            # Get ontology data asynchronously
            categories = await research.get_categories(topic)
            future_signals = await research.get_future_signals(topic)
            sentiment_options = await research.get_sentiments(topic)
            time_to_impact_options = await research.get_time_to_impact(topic)
            driver_types = await research.get_driver_types(topic)

            # Check if all SLM services are available to potentially skip LLM entirely
            slm_fully_available = (
                slm_summary is not None and  # Summary via Phi-3
                len(slm_fields_used) >= 4 and  # All 4 classification fields confident
                self._check_slm_services_available()  # Explanations + category services
            )

            loop = asyncio.get_event_loop()
            analysis_result = {}

            if slm_fully_available:
                # 🎉 100% SLM mode - skip LLM entirely!
                self.logger.info(f"    ✨ Full SLM mode - skipping LLM call")
            else:
                # Fall back to LLM for missing components
                if not self.article_analyzer:
                    ai_model = LiteLLMModel.get_instance(model_name)
                    self.article_analyzer = ArticleAnalyzer(ai_model, use_cache=True)

                missing_components = []
                if not slm_summary:
                    missing_components.append("summary")
                if len(slm_fields_used) < 4:
                    missing_fields = [f for f in ['sentiment', 'time_to_impact', 'driver_type', 'future_signal'] if f not in slm_fields_used]
                    missing_components.extend(missing_fields)
                    # Track LLM sources for missing fields
                    for field in missing_fields:
                        enrichment_sources[field] = 'llm'

                self.logger.info(f"    🤖 LLM ({model_name}) for {', '.join(missing_components) if missing_components else 'fallback'}")

                analysis_result = await loop.run_in_executor(
                    None,
                    self.article_analyzer.analyze_content,
                    article_text, title, source, uri,
                    50, "neutral", "informative",
                    categories, future_signals, sentiment_options,
                    time_to_impact_options, driver_types
                )

            # Use local summary if available, otherwise use LLM summary
            final_summary = slm_summary if slm_summary else analysis_result.get('summary')

            # Step 3: Extract tags + NER using hybrid mode (KeyBERT + Phi-3)
            tags = []
            entities = {}
            tag_source = "llm"
            try:
                if not self.keybert_tagging_service:
                    self.keybert_tagging_service = get_keybert_tagging_service()

                if self.keybert_tagging_service.is_hybrid_available():
                    # Use hybrid mode: KeyBERT candidates + Phi-3 refinement + NER
                    raw_content = article_data.get('raw_content') or article_data.get('content')
                    tag_result = await loop.run_in_executor(
                        None,
                        lambda: self.keybert_tagging_service.extract_tags_hybrid(
                            title=title,
                            summary=final_summary or article_text,
                            content=raw_content
                        )
                    )
                    if tag_result.get('tags'):
                        tags = tag_result['tags']
                        entities = tag_result.get('entities', {})
                        tag_source = tag_result.get('source', 'hybrid')
                        self.logger.info(f"    🏷️ Hybrid tags: {tags} | Entities: {len(entities.get('people', []))}P/{len(entities.get('organizations', []))}O/{len(entities.get('locations', []))}L ({tag_result.get('latency_ms', 0)}ms)")
                        # Record KeyBERT latency (hybrid mode still uses KeyBERT as base)
                        if tag_result.get('latency_ms'):
                            try:
                                from app.routes.training_routes import get_latency_tracker
                                get_latency_tracker().record('KeyBERT', tag_result['latency_ms'])
                            except Exception:
                                pass
                elif self.keybert_tagging_service.is_available():
                    # Fallback to KeyBERT-only if vLLM unavailable
                    raw_content = article_data.get('raw_content') or article_data.get('content')
                    tag_result = await loop.run_in_executor(
                        None,
                        lambda: self.keybert_tagging_service.extract_tags(
                            title=title,
                            summary=final_summary or article_text,
                            content=raw_content
                        )
                    )
                    if tag_result.get('tags'):
                        tags = tag_result['tags']
                        tag_source = "keybert"
                        self.logger.info(f"    🏷️ KeyBERT tags: {tags} ({tag_result.get('latency_ms', 0)}ms)")
                        # Record KeyBERT latency
                        if tag_result.get('latency_ms'):
                            try:
                                from app.routes.training_routes import get_latency_tracker
                                get_latency_tracker().record('KeyBERT', tag_result['latency_ms'])
                            except Exception:
                                pass
            except Exception as e:
                self.logger.warning(f"Hybrid tagging failed, using LLM fallback: {e}")

            # Fallback to LLM tags if hybrid/KeyBERT unavailable or returned no results
            if not tags:
                tags = analysis_result.get('tags', [])
                tag_source = "llm"

            # Include entity names in tags for searchability
            if entities:
                entity_names = (
                    entities.get('people', []) +
                    entities.get('organizations', []) +
                    entities.get('locations', [])
                )
                # Add entities that aren't already in tags
                existing_tags_lower = [t.lower() for t in tags]
                for entity in entity_names:
                    if entity.lower() not in existing_tags_lower:
                        tags.append(entity)

            tags_str = ','.join(tags) if isinstance(tags, list) else str(tags) if tags else None

            # Step 4: Generate explanations using SLM (Qwen)
            slm_explanations = {}
            explanation_source = "llm"
            try:
                if not self.explanation_service:
                    self.explanation_service = get_explanation_service()

                if self.explanation_service.is_available():
                    # Get classification values (prefer SLM values if available)
                    sentiment_val = slm_result.get('sentiment') if 'sentiment' in slm_fields_used else analysis_result.get('sentiment')
                    time_to_impact_val = slm_result.get('time_to_impact') if 'time_to_impact' in slm_fields_used else analysis_result.get('time_to_impact')
                    driver_type_val = slm_result.get('driver_type') if 'driver_type' in slm_fields_used else analysis_result.get('driver_type')
                    future_signal_val = slm_result.get('future_signal') if 'future_signal' in slm_fields_used else analysis_result.get('future_signal')

                    explanation_result = await loop.run_in_executor(
                        None,
                        lambda: self.explanation_service.generate_explanations(
                            title=title,
                            summary=final_summary or article_text,
                            sentiment=sentiment_val,
                            time_to_impact=time_to_impact_val,
                            driver_type=driver_type_val,
                            future_signal=future_signal_val
                        )
                    )

                    if explanation_result.get('source') == 'qwen':
                        slm_explanations = explanation_result
                        explanation_source = "qwen"
                        self.logger.info(f"    💬 SLM explanations generated ({explanation_result.get('latency_ms', 0)}ms)")
                        # Record Qwen latency for explanations
                        if explanation_result.get('latency_ms'):
                            try:
                                from app.routes.training_routes import get_latency_tracker
                                get_latency_tracker().record('Qwen', explanation_result['latency_ms'])
                            except Exception:
                                pass
            except Exception as e:
                self.logger.warning(f"SLM explanation generation failed, using LLM fallback: {e}")

            # Step 5: Classify category using SLM (Qwen)
            slm_category = None
            category_source = "llm"
            try:
                if not self.category_service:
                    self.category_service = get_category_service()

                if self.category_service.is_available() and categories:
                    category_result = await loop.run_in_executor(
                        None,
                        lambda: self.category_service.classify_category(
                            title=title,
                            summary=final_summary or article_text,
                            categories=categories,
                            topic=topic
                        )
                    )

                    if category_result.get('source') == 'qwen' and category_result.get('category'):
                        slm_category = category_result['category']
                        category_source = "qwen"
                        self.logger.info(f"    📂 SLM category: {slm_category} ({category_result.get('latency_ms', 0)}ms)")
                        # Record Qwen latency for category
                        if category_result.get('latency_ms'):
                            try:
                                from app.routes.training_routes import get_latency_tracker
                                get_latency_tracker().record('Qwen', category_result['latency_ms'])
                            except Exception:
                                pass
            except Exception as e:
                self.logger.warning(f"SLM category classification failed, using LLM fallback: {e}")

            final_result = {
                'summary': final_summary,
                'category': slm_category or analysis_result.get('category'),
                'sentiment': analysis_result.get('sentiment'),
                'future_signal': analysis_result.get('future_signal'),
                'future_signal_explanation': slm_explanations.get('future_signal_explanation') or analysis_result.get('future_signal_explanation'),
                'sentiment_explanation': slm_explanations.get('sentiment_explanation') or analysis_result.get('sentiment_explanation'),
                'time_to_impact': analysis_result.get('time_to_impact'),
                'time_to_impact_explanation': slm_explanations.get('time_to_impact_explanation') or analysis_result.get('time_to_impact_explanation'),
                'driver_type': analysis_result.get('driver_type'),
                'driver_type_explanation': slm_explanations.get('driver_type_explanation') or analysis_result.get('driver_type_explanation'),
                'tags': tags_str,
                'analyzed': True,
                '_enrichment_method': 'llm_only',
                '_summary_source': summary_source,
                '_enrichment_sources': enrichment_sources,  # Track which model was used for each field
            }

            # Override with SLM results for high-confidence fields
            slm_components = []
            if slm_summary:
                slm_components.append('summary')
            if slm_fields_used:
                for field in slm_fields_used:
                    if field in slm_result:
                        final_result[field] = slm_result[field]
                slm_components.extend(slm_fields_used)
            if tag_source in ("keybert", "hybrid"):
                slm_components.append('tags')
            if entities:
                slm_components.append('ner')
            if explanation_source == "qwen":
                slm_components.append('explanations')
            if category_source == "qwen":
                slm_components.append('category')

            if slm_components:
                final_result['_enrichment_method'] = f"hybrid_slm({','.join(slm_components)})"

            article_data.update(final_result)

            method = final_result.get('_enrichment_method', 'unknown')
            self.logger.info(f"    📝 Enriched: method={method}, sentiment={final_result.get('sentiment')}")

            return article_data

        except Exception as e:
            self.logger.error(f"Error in async article analysis: {e}")
            return article_data

    async def _score_article_relevance_async(
        self, 
        article_data: Dict[str, Any], 
        topic: str, 
        keywords: List[str]
    ) -> Dict[str, Any]:
        """Async version of relevance scoring"""
        # For now, this wraps the sync version in a thread executor
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.score_article_relevance, article_data, topic, keywords)

    async def _quality_check_article_async(self, article_data: Dict[str, Any]) -> Dict[str, Any]:
        """Async version of quality check"""
        # Simplified quality check for async processing
        return {
            "quality_score": 0.8,  # Placeholder score
            "quality_issues": None,
            "approved": True
        }

    async def _upsert_to_vector_db_async(self, article_data: Dict[str, Any], raw_content: str = None):
        """Async vector database upsert - OPTIMIZED for pgvector"""
        try:
            # CRITICAL FIX: Use native async pgvector function to avoid thread pool overhead
            from app.vector_store_pgvector import upsert_article_async

            # Prepare article for vector indexing
            vector_article = article_data.copy()
            if raw_content:
                vector_article['raw'] = raw_content

            # Use native async function - no thread pool needed
            await upsert_article_async(vector_article)

        except Exception as e:
            self.logger.error(f"Vector database upsert failed: {e}")
            raise

    async def process_articles_batch(self, articles: List[Dict[str, Any]], topic: str = None, keywords: List[str] = None, dry_run: bool = False, relevance_threshold_override: float = None) -> Dict[str, Any]:
        """
        Process a batch of articles through the enrichment pipeline

        Args:
            articles: List of article data dictionaries
            topic: Topic name for context
            keywords: List of keywords for relevance scoring
            dry_run: If True, skip database operations
            relevance_threshold_override: If provided, use this threshold instead of global.
                                          If 0, skip relevance filtering entirely.

        Returns:
            Processing results summary
        """
        results = {
            "processed": 0,
            "enriched": 0,
            "relevant": 0,
            "quality_passed": 0,
            "saved": 0,
            "vector_indexed": 0,
            "errors": []
        }
        
        try:
            # QUICK FIX: Use concurrent async processing instead of sequential loop
            # This prevents blocking the event loop during auto-ingest

            # Separate articles that need scraping from those that already have content
            # NewsFirehose and NewsData.io provide full content - no scraping needed
            articles_needing_scrape = []
            articles_with_content = {}

            for article in articles:
                article_uri = article.get('uri')
                if not article_uri:
                    continue

                # Check if article already has content from collector
                existing_content = article.get('content')
                if existing_content and len(existing_content) > 200:
                    # Article has substantial content from collector - skip scraping
                    articles_with_content[article_uri] = existing_content
                    self.logger.debug(f"📄 Using collector content for {article_uri} ({len(existing_content)} chars)")
                else:
                    articles_needing_scrape.append(article_uri)

            self.logger.info(f"📊 Content status: {len(articles_with_content)} have content, {len(articles_needing_scrape)} need scraping")

            # Only batch scrape articles that don't have content
            scraped_content = {}
            if articles_needing_scrape:
                self.logger.info(f"🚀 Pre-scraping {len(articles_needing_scrape)} articles in batch...")
                scraped_content = await self.scrape_articles_batch(articles_needing_scrape)
                self.logger.info(f"✅ Batch scraping completed: {len(scraped_content)} articles")

            # Combine content from collectors and scraped content
            all_content = {**articles_with_content, **scraped_content}

            # Process articles concurrently using existing async infrastructure
            # This is the KEY FIX: use _process_single_article_async() which properly uses
            # run_in_executor() for blocking operations instead of blocking the event loop

            MAX_CONCURRENT = 5  # Process 5 articles at a time to avoid overwhelming system

            self.logger.info(f"🔄 Processing {len(articles)} articles concurrently (max {MAX_CONCURRENT} at a time)...")

            # Create tasks for all articles
            all_article_data = []
            for article in articles:
                # Attach content to article for processing (from collector or scraped)
                article_uri = article.get('uri', 'unknown')
                article['_scraped_content'] = all_content.get(article_uri)
                all_article_data.append(article)

            # Process in batches to prevent connection pool exhaustion
            for batch_idx in range(0, len(all_article_data), MAX_CONCURRENT):
                batch = all_article_data[batch_idx:batch_idx + MAX_CONCURRENT]
                batch_num = (batch_idx // MAX_CONCURRENT) + 1
                total_batches = (len(all_article_data) + MAX_CONCURRENT - 1) // MAX_CONCURRENT

                self.logger.info(f"📦 Processing batch {batch_num}/{total_batches} ({len(batch)} articles)...")

                # Create tasks for this batch
                tasks = []
                for article in batch:
                    task = asyncio.create_task(
                        self._process_single_article_async(article, topic, keywords, relevance_threshold_override)
                    )
                    tasks.append(task)

                # Wait for batch completion with timeout
                try:
                    batch_results = await asyncio.wait_for(
                        asyncio.gather(*tasks, return_exceptions=True),
                        timeout=300  # 5 minute timeout per batch
                    )

                    # Aggregate results from this batch
                    for result in batch_results:
                        if isinstance(result, Exception):
                            results["errors"].append(str(result))
                            self.logger.error(f"Article processing failed: {result}")
                        elif isinstance(result, dict):
                            results["processed"] += 1

                            if result.get("status") == "success":
                                results["saved"] += 1
                                results["vector_indexed"] += 1
                                results["quality_passed"] += 1
                                results["relevant"] += 1
                                results["enriched"] += 1
                            elif result.get("status") == "filtered":
                                results["enriched"] += 1
                                # Article was filtered out by relevance or quality
                                if result.get("reason") == "relevance_threshold":
                                    pass  # Count as processed but not relevant
                                elif result.get("reason") == "quality_check_failed":
                                    results["relevant"] += 1  # Was relevant but failed quality
                            elif result.get("status") == "error":
                                results["errors"].append(result.get("error", "Unknown error"))

                    self.logger.info(f"✅ Batch {batch_num}/{total_batches} completed: "
                                   f"{len([r for r in batch_results if isinstance(r, dict) and r.get('status') == 'success'])} saved, "
                                   f"{len([r for r in batch_results if isinstance(r, Exception)])} errors")

                    # Brief pause between batches to yield control
                    await asyncio.sleep(0.1)

                except asyncio.TimeoutError:
                    error_msg = f"Batch {batch_num} timed out after 300 seconds"
                    self.logger.error(error_msg)
                    results["errors"].append(error_msg)

            self.logger.info(f"🏁 All batches completed: {results['processed']} processed, "
                           f"{results['saved']} saved, {len(results['errors'])} errors")

            return results

        except Exception as e:
            self.logger.error(f"❌ Error in batch processing: {e}")
            results["errors"].append(f"Batch processing error: {str(e)}")
            return results

    def save_approved_articles(self, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Save approved articles to the database and enrich with policy categories

        Args:
            articles: List of processed and approved articles

        Returns:
            Save operation results
        """
        results = {"saved": 0, "categorized": 0, "errors": []}

        try:
            for article in articles:
                try:
                    # Ensure article_origin is set for automated ingest
                    article["article_origin"] = "aunoo"
                    # Use existing database save_article method
                    self.db.save_article(article)
                    results["saved"] += 1
                    self.logger.debug(f"Saved article: {article.get('uri')}")

                    # Enrich with policy categories if topic matches policy tracker
                    try:
                        self._enrich_with_policy_categories(article)
                        results["categorized"] += 1
                    except Exception as cat_error:
                        self.logger.warning(f"Policy categorization failed for {article.get('uri')}: {cat_error}")

                except Exception as e:
                    error_msg = f"Error saving article {article.get('uri', 'unknown')}: {str(e)}"
                    results["errors"].append(error_msg)
                    self.logger.error(error_msg)

            self.logger.info(f"Article save completed: {results}")

        except Exception as e:
            self.logger.error(f"Error in save_approved_articles: {e}")
            results["errors"].append(f"Save operation error: {str(e)}")

        return results

    def _enrich_with_policy_categories(self, article: Dict[str, Any]) -> None:
        """
        Enrich an article with policy categories using keyword-based classification.

        Args:
            article: Article data dictionary
        """
        from app.routes.policy_tracker_routes import (
            categorize_article,
            store_article_categories,
            DEFAULT_TRACKER_TOPIC
        )
        from sqlalchemy import text

        uri = article.get('uri')
        title = article.get('title', '')
        summary = article.get('summary', '')
        topic = article.get('topic', '')

        if not uri or not (title or summary):
            return

        # Categorize using keyword matching
        categories = categorize_article(title, summary)

        if not categories:
            return

        # Store categories in the policy tracker table
        conn = self.db._temp_get_connection()
        try:
            for category in categories:
                conn.execute(text("""
                    INSERT INTO policy_article_categories
                    (article_uri, category, topic, classification_method)
                    VALUES (:uri, :category, :topic, 'auto_ingest')
                    ON CONFLICT (article_uri, category) DO NOTHING
                """), {
                    "uri": uri,
                    "category": category,
                    "topic": topic or DEFAULT_TRACKER_TOPIC
                })
            conn.commit()
            self.logger.debug(f"Added {len(categories)} policy categories for {uri}")
        except Exception as e:
            self.logger.warning(f"Failed to store policy categories: {e}")
        finally:
            conn.close()
    
    def get_relevance_threshold(self) -> float:
        """
        Get the minimum relevance threshold from database settings
        
        Returns:
            Relevance threshold value (0.0-1.0)
        """
        try:
            return self.db.facade.get_min_relevance_threshold()
        except Exception as e:
            self.logger.warning(f"Could not get relevance threshold from database: {e}")
        
        return 0.0  # Default fallback
    
    def get_auto_ingest_settings(self) -> Dict[str, Any]:
        """
        Get all auto-ingest settings from database

        Returns:
            Dictionary containing all auto-ingest configuration
        """
        try:
            settings = self.db.facade.get_auto_ingest_settings()

            if settings:
                # Get default model - if None, use first available
                default_model = settings[4]
                if not default_model:
                    available = get_available_models()
                    if available and len(available) > 0:
                        default_model = available[0].get('name')

                return {
                    "auto_ingest_enabled": bool(settings[0]),
                    "min_relevance_threshold": float(settings[1] or 0.0),
                    "quality_control_enabled": bool(settings[2]),
                    "auto_save_approved_only": bool(settings[3]),
                    "default_llm_model": default_model,
                    "llm_temperature": float(settings[5] if settings[5] is not None else 0.2),
                    "llm_max_tokens": int(settings[6] or 1000)
                }
        except Exception as e:
            self.logger.error(f"Error getting auto-ingest settings: {e}")

        # Return defaults for new users - get first available model
        default_model = None
        try:
            available = get_available_models()
            if available and len(available) > 0:
                default_model = available[0].get('name')
        except:
            pass

        return {
            "auto_ingest_enabled": True,  # Auto-processing ON by default
            "min_relevance_threshold": 0.0,
            "quality_control_enabled": True,
            "auto_save_approved_only": True,  # Save Approved Only ON by default
            "default_llm_model": default_model,
            "llm_temperature": 0.2,  # Temperature 0.2 default
            "llm_max_tokens": 1000
        }
    
    async def bulk_process_topic_articles(self, topic_id: str, options: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Process all articles for a specific topic group with custom options
        
        Args:
            topic_id: Topic ID to process articles for
            options: Processing options (thresholds, limits, etc.)
            
        Returns:
            Detailed processing report
        """
        options = options or {}
        
        try:
            # Get articles for the topic through keyword matches
            # Check which table structure to use
            use_new_table = self.db.facade.check_if_keyword_article_matches_table_exists()

            if use_new_table:
                # Use new table structure
                rows = self.db.facade.get_topic_articles_to_ingest_using_new_table_structure(topic_id)
            else:
                # Use old table structure
                rows = self.db.facade.get_topic_articles_to_ingest_using_old_table_structure(topic_id)

            all_articles = []
            for row in rows:
                all_articles.append({
                    "uri": row['uri'],
                    "title": row['title'],
                    "summary": row['summary'],
                    "news_source": row['news_source'],
                    "topic": row['topic']
                })

            # For processing, filter to only unprocessed AND unread articles
            if use_new_table:
                rows = self.db.facade.get_topic_unprocessed_and_unread_articles_using_new_table_structure(topic_id)
            else:
                rows = self.db.facade.get_topic_unprocessed_and_unread_articles_using_old_table_structure(topic_id)

            unprocessed_unread_articles = []
            for row in rows:
                unprocessed_unread_articles.append({
                    "uri": row['uri'],
                    "title": row['title'],
                    "summary": row['summary'],
                    "news_source": row['news_source'],
                    "topic": row['topic']
                })

            # Get keywords for the topic
            keywords = self.db.facade.get_topic_keywords(topic_id)
            
            if not all_articles:
                return {
                    "success": True,
                    "message": f"No articles found for topic: {topic_id}",
                    "processed": 0,
                    "articles_found": 0,
                    "total_count": 0
                }
            
            # Apply options
            max_articles = options.get("max_articles", len(unprocessed_unread_articles))
            articles_to_process = unprocessed_unread_articles[:max_articles]
            
            # Process the batch
            if options.get("dry_run", False):
                # Dry run - just return what would be processed
                return {
                    "success": True,
                    "dry_run": True,
                    "articles_found": len(all_articles),
                    "unprocessed_unread_articles": len(unprocessed_unread_articles),
                    "would_process": min(len(unprocessed_unread_articles), max_articles),
                    "topic": topic_id,
                    "keywords": keywords,
                    # Add expected UI fields for dry run
                    "processed_count": 0,
                    "total_count": len(all_articles),
                    "approved_count": 0,
                    "filtered_count": 0,
                    "failed_count": 0,
                    "processing_log": [f"DRY RUN: Found {len(all_articles)} total articles for topic '{topic_id}'. {len(unprocessed_unread_articles)} unprocessed & unread. Would process {min(len(unprocessed_unread_articles), max_articles)} articles."]
                }
            else:
                # Actually process the articles
                results = await self.process_articles_batch(articles_to_process, topic_id, keywords)
                
                # Map internal field names to UI expected field names
                ui_results = {
                    "success": True,
                    "topic": topic_id,
                    "articles_found": len(all_articles),
                    "unprocessed_unread_articles": len(unprocessed_unread_articles),
                    "keywords_used": keywords,
                    "processed_count": results.get("processed", 0),
                    "total_count": len(all_articles),
                    "approved_count": results.get("quality_passed", 0),
                    "filtered_count": results.get("processed", 0) - results.get("relevant", 0),  # Articles that didn't meet relevance threshold
                    "failed_count": len(results.get("errors", [])),
                    "processing_log": [
                        f"Total articles for topic: {len(all_articles)}",
                        f"Unprocessed & unread articles: {len(unprocessed_unread_articles)}",
                        f"Processed {results.get('processed', 0)} articles",
                        f"Found {results.get('relevant', 0)} relevant articles",
                        f"Quality passed: {results.get('quality_passed', 0)}",
                        f"Saved: {results.get('saved', 0)}",
                        f"Errors: {len(results.get('errors', []))}"
                    ] + results.get("errors", [])
                }
                
                return ui_results
                
        except Exception as e:
            self.logger.error(f"Error in bulk_process_topic_articles: {e}")
            return {
                "success": False,
                "error": str(e),
                "topic": topic_id
            }
    
    async def scrape_articles_batch(self, uris: List[str]) -> Dict[str, Optional[str]]:
        """
        Scrape multiple articles using Firecrawl's batch API
        
        Args:
            uris: List of article URIs to scrape
            
        Returns:
            Dictionary mapping URIs to scraped content (or None if failed)
        """
        if not uris:
            return {}
            
        results = {}
        
        try:
            self.logger.info(f"Starting batch scraping for {len(uris)} articles")
            
            # Check for existing articles first
            existing_articles = {}
            for uri in uris:
                existing_raw = await self.async_db.get_raw_article_async(uri)
                if existing_raw and existing_raw.get('raw_markdown'):
                    existing_articles[uri] = existing_raw['raw_markdown']
                    self.logger.debug(f"Found existing content for {uri}")
            
            # Filter out articles we already have
            uris_to_scrape = [uri for uri in uris if uri not in existing_articles]
            
            if not uris_to_scrape:
                self.logger.info("All articles already scraped, returning existing content")
                return existing_articles
            
            # Initialize Research class for Firecrawl access
            from app.research import Research
            research = Research(self.db)
            
            if not research.firecrawl_app:
                self.logger.warning("Firecrawl not available, falling back to individual scraping")
                return await self._fallback_individual_scraping(uris)
            
            # Use Firecrawl batch API
            batch_result = await self._firecrawl_batch_scrape(research.firecrawl_app, uris_to_scrape)
            
            # Combine existing and newly scraped content
            results.update(existing_articles)
            results.update(batch_result)
            
            self.logger.info(f"Batch scraping completed: {len(results)} articles processed")
            return results
            
        except Exception as e:
            self.logger.error(f"Error in batch scraping: {e}")
            # Fallback to individual scraping on batch failure
            return await self._fallback_individual_scraping(uris)
    
    async def _firecrawl_batch_scrape(self, firecrawl_app, uris: List[str]) -> Dict[str, Optional[str]]:
        """
        Use Firecrawl's batch API to scrape multiple URLs

        Args:
            firecrawl_app: Firecrawl application instance
            uris: List of URIs to scrape

        Returns:
            Dictionary mapping URIs to scraped content
        """
        try:
            self.logger.info(f"Starting Firecrawl batch scrape for {len(uris)} URLs")
            start_time = time.time()

            # Use Firecrawl SDK's built-in polling method instead of manual polling
            # Documentation: https://docs.firecrawl.dev/features/batch-scrape
            # batch_scrape() handles submission + polling automatically
            # IMPORTANT: Firecrawl SDK is synchronous, so we must use run_in_executor to avoid blocking the event loop
            # PERFORMANCE FIX: Use dedicated executor instead of default (None) to prevent blocking other operations
            loop = asyncio.get_event_loop()

            self.logger.info(f"Submitting to dedicated blocking I/O executor (poll_interval=5, wait_timeout=300)")
            batch_job = await loop.run_in_executor(
                self._blocking_executor,  # Use dedicated executor instead of None
                lambda: firecrawl_app.batch_scrape(
                    uris,
                    formats=['markdown'],
                    poll_interval=5,  # Check every 5 seconds
                    wait_timeout=300  # Wait up to 5 minutes
                )
            )

            if not batch_job:
                self.logger.error(f"Batch scrape returned None")
                return {}

            # Check status
            status = getattr(batch_job, 'status', None)
            data = getattr(batch_job, 'data', [])

            self.logger.info(f"✅ Batch scrape completed with status: {status}, {len(data)} results")

            if status != 'completed':
                self.logger.warning(f"Batch scrape status is '{status}', not 'completed'")
                return {}

            # Process results
            processed_results = {}
            for idx, item in enumerate(data):
                # Get URL from metadata
                metadata = getattr(item, 'metadata', None) or (item.get('metadata') if isinstance(item, dict) else None)
                url = None
                if metadata:
                    if isinstance(metadata, dict):
                        url = metadata.get('sourceURL') or metadata.get('source_url')
                    else:
                        url = getattr(metadata, 'sourceURL', None) or getattr(metadata, 'source_url', None)

                # Get markdown content
                markdown = getattr(item, 'markdown', None) or (item.get('markdown') if isinstance(item, dict) else None)

                if url and markdown:
                    # Apply token limiting
                    from app.analyzers.article_analyzer import ArticleAnalyzer
                    truncated_content = ArticleAnalyzer.truncate_text(None, markdown, max_chars=65000)

                    if len(markdown) > len(truncated_content):
                        self.logger.info(f"Truncated content for {url}: {len(markdown)} -> {len(truncated_content)} chars")

                    processed_results[url] = truncated_content
                    self.logger.debug(f"✅ Successfully scraped {url} ({len(truncated_content)} chars)")
                else:
                    if url:
                        processed_results[url] = None
                        self.logger.warning(f"❌ No markdown content for {url}")
                    else:
                        self.logger.warning(f"⚠️ Item {idx} has no URL in metadata")

            duration = time.time() - start_time
            successful_count = len([r for r in processed_results.values() if r])
            self.logger.info(f"✅ Firecrawl batch scrape completed: {successful_count}/{len(processed_results)} successful in {duration:.1f}s ({duration/60:.1f} min)")
            return processed_results

        except asyncio.TimeoutError:
            duration = time.time() - start_time
            self.logger.error(f"❌ Firecrawl batch scrape timed out after {duration:.1f}s")
            return {}
        except Exception as e:
            duration = time.time() - start_time
            self.logger.error(f"❌ Error in Firecrawl batch scraping after {duration:.1f}s: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return {}
    
    async def _poll_batch_completion(self, firecrawl_app, batch_id: str, max_wait_time: int = 300) -> Dict[str, Optional[str]]:
        """
        Poll Firecrawl batch API for completion
        
        Args:
            firecrawl_app: Firecrawl application instance
            batch_id: Batch job ID
            max_wait_time: Maximum time to wait in seconds
            
        Returns:
            Dictionary mapping URIs to scraped content
        """
        start_time = time.time()
        poll_interval = 5  # Start with 5 second intervals
        
        while time.time() - start_time < max_wait_time:
            try:
                # IMPORTANT: Use run_in_executor to avoid blocking the event loop
                # Add timeout to prevent hanging if Firecrawl is unresponsive
                loop = asyncio.get_event_loop()
                status_response = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        firecrawl_app.get_batch_scrape_status,
                        batch_id
                    ),
                    timeout=10.0  # 10 second timeout for status check
                )
                
                if not status_response:
                    self.logger.warning(f"No status response for batch {batch_id}")
                    await asyncio.sleep(poll_interval)
                    continue
                
                # Firecrawl v2 returns objects, not dictionaries
                status = getattr(status_response, 'status', None)
                data = getattr(status_response, 'data', [])
                error = getattr(status_response, 'error', None)
                
                self.logger.debug(f"Batch {batch_id} status: {status}")
                
                if status == 'completed':
                    # Get results
                    results = {}

                    self.logger.info(f"📦 Processing {len(data)} items from batch {batch_id}")

                    for idx, item in enumerate(data):
                        # Log the raw item structure for debugging
                        self.logger.info(f"🔍 Raw item {idx} type: {type(item)}")
                        if isinstance(item, dict):
                            self.logger.info(f"🔍 Raw item {idx} keys: {list(item.keys())}")
                        else:
                            self.logger.info(f"🔍 Raw item {idx} attributes: {[a for a in dir(item) if not a.startswith('_')]}")

                        # Handle both object and dict structures
                        # Try object access first, then dict access

                        # Get metadata (can be object or dict)
                        if hasattr(item, 'metadata'):
                            metadata = item.metadata
                        elif isinstance(item, dict):
                            metadata = item.get('metadata', {})
                        else:
                            metadata = getattr(item, 'metadata', {})

                        # Log metadata structure
                        self.logger.info(f"🔍 Metadata type: {type(metadata)}")
                        if isinstance(metadata, dict):
                            self.logger.info(f"🔍 Metadata keys: {list(metadata.keys()) if metadata else 'empty'}")
                        elif metadata:
                            self.logger.info(f"🔍 Metadata attributes: {[attr for attr in dir(metadata) if not attr.startswith('_')]}")

                        # Get URL from metadata (can be object or dict)
                        # The Firecrawl API returns: data[i].metadata.sourceURL
                        url = None
                        if metadata:
                            if isinstance(metadata, dict):
                                url = metadata.get('sourceURL') or metadata.get('source_url')
                            elif hasattr(metadata, 'sourceURL'):
                                url = metadata.sourceURL
                            elif hasattr(metadata, 'source_url'):
                                url = metadata.source_url
                            else:
                                url = getattr(metadata, 'sourceURL', None) or getattr(metadata, 'source_url', None)

                        # Get success flag (can be object or dict)
                        # Note: Firecrawl v2 Document objects don't have a 'success' field
                        # If markdown is present, consider it successful
                        if hasattr(item, 'success'):
                            success = item.success
                        elif isinstance(item, dict):
                            success = item.get('success', True)  # Default to True if not specified
                        else:
                            success = getattr(item, 'success', True)  # Default to True if not specified

                        # Get markdown content (can be object or dict)
                        if hasattr(item, 'markdown'):
                            markdown = item.markdown
                        elif isinstance(item, dict):
                            markdown = item.get('markdown')
                        else:
                            markdown = getattr(item, 'markdown', None)

                        # Get error (can be object or dict)
                        if hasattr(item, 'error'):
                            item_error = item.error
                        elif isinstance(item, dict):
                            item_error = item.get('error')
                        else:
                            item_error = getattr(item, 'error', None)

                        self.logger.info(f"🔍 Item {idx}: url={url}, success={success}, has_markdown={bool(markdown)}, error={item_error}")

                        if url:
                            if success and markdown:
                                results[url] = markdown
                                self.logger.debug(f"✅ Successfully scraped {url} ({len(markdown)} chars)")
                            else:
                                results[url] = None
                                self.logger.warning(f"❌ Failed to scrape {url}: {item_error or 'No markdown content'}")
                        else:
                            self.logger.warning(f"⚠️ Item {idx} has no URL in metadata")

                    self.logger.info(f"Batch {batch_id} completed with {len([r for r in results.values() if r])} successful results out of {len(results)} total")
                    return results
                    
                elif status == 'failed':
                    self.logger.error(f"Batch {batch_id} failed: {error or 'Unknown error'}")
                    return {}
                    
                # Still processing, wait before next poll
                await asyncio.sleep(poll_interval)
                
                # Increase poll interval gradually
                poll_interval = min(poll_interval * 1.2, 30)
                
            except asyncio.TimeoutError:
                self.logger.warning(f"Status check timed out for batch {batch_id}, will retry...")
                await asyncio.sleep(poll_interval)
            except Exception as e:
                self.logger.error(f"Error polling batch status: {e}")
                await asyncio.sleep(poll_interval)
        
        self.logger.warning(f"Batch {batch_id} timed out after {max_wait_time} seconds")
        return {}
    
    async def _fallback_individual_scraping(self, uris: List[str]) -> Dict[str, Optional[str]]:
        """
        Fallback to individual scraping if batch fails

        Args:
            uris: List of URIs to scrape

        Returns:
            Dictionary mapping URIs to scraped content
        """
        results = {}

        for uri in uris:
            try:
                content = await self.scrape_article_content(uri)
                results[uri] = content
            except Exception as e:
                self.logger.error(f"Individual scraping failed for {uri}: {e}")
                results[uri] = None

        return results

    async def close(self):
        """
        Cleanup resources on shutdown

        Gracefully shuts down the dedicated blocking I/O executor
        """
        self.logger.info("Shutting down AutomatedIngestService...")

        try:
            # Shutdown executor gracefully (wait for current tasks to complete)
            self._blocking_executor.shutdown(wait=True)
            self.logger.info("✅ Blocking I/O executor shutdown complete")
        except Exception as e:
            self.logger.error(f"❌ Error during executor shutdown: {e}")

        self.logger.info("AutomatedIngestService shutdown complete") 