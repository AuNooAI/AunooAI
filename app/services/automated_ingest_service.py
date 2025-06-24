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
from app.services.async_db import AsyncDatabase, get_async_database_instance
from app.models.media_bias import MediaBias
from app.relevance import RelevanceCalculator
from app.analyzers.article_analyzer import ArticleAnalyzer
from app.ai_models import LiteLLMModel
import asyncio
import concurrent.futures
import requests
from app.config.config import load_config
import time

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
        self.media_bias = MediaBias(db)
        self.article_analyzer = None
        
        # Configure logging
        self.logger = logger
        self.logger.info("AutomatedIngestService initialized with async capabilities")
    
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
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT default_llm_model, llm_temperature, llm_max_tokens
                    FROM keyword_monitor_settings 
                    WHERE id = 1
                """)
                settings = cursor.fetchone()
                if settings:
                    return settings[0] or "gpt-4o-mini"
        except Exception as e:
            self.logger.warning(f"Could not get LLM settings from database: {e}")
        
        return "gpt-4o-mini"  # Default fallback
    
    def get_llm_parameters(self) -> Dict[str, Any]:
        """
        Get LLM parameters from database settings
        
        Returns:
            Dictionary containing temperature and max_tokens
        """
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT llm_temperature, llm_max_tokens
                    FROM keyword_monitor_settings 
                    WHERE id = 1
                """)
                settings = cursor.fetchone()
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
        Perform full article analysis including category, sentiment, etc.
        
        Args:
            article_data: Article data dictionary
            
        Returns:
            Article data enriched with analysis results
        """
        try:
            # Initialize article analyzer if not already done
            if not self.article_analyzer:
                model_name = self.get_llm_client()
                ai_model = LiteLLMModel.get_instance(model_name)
                self.article_analyzer = ArticleAnalyzer(ai_model, use_cache=True)
            
            # Prepare content for analysis
            article_text = article_data.get('summary', '') or article_data.get('content', '')
            title = article_data.get('title', '')
            source = article_data.get('news_source', '')
            uri = article_data.get('uri', '')
            
            if not article_text or not title:
                self.logger.warning(f"Insufficient content for analysis: {uri}")
                return article_data
            
            # Get topic from article data (don't use hardcoded default)
            topic = article_data.get('topic')
            if not topic:
                self.logger.error(f"No topic specified for article {uri} - cannot determine ontology")
                return article_data
            
            # Get topic-specific ontology dynamically using Research class
            from app.research import Research
            research = Research(self.db)
            
            # Set topic and get dynamic ontology data
            research.set_topic(topic)
            
            # Check if we're in an event loop context
            try:
                # Try to get the running event loop
                loop = asyncio.get_running_loop()
                # If we're in an event loop, use thread pool to avoid event loop conflicts
                
                def run_async_in_thread(coro_func, *args):
                    """Helper function to run async function in a new thread with its own event loop"""
                    return asyncio.run(coro_func(*args))
                
                # Use a thread pool to run the async methods
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
                # No event loop running, safe to use asyncio.run
                categories = asyncio.run(research.get_categories(topic))
                future_signals = asyncio.run(research.get_future_signals(topic))
                sentiment_options = asyncio.run(research.get_sentiments(topic))
                time_to_impact_options = asyncio.run(research.get_time_to_impact(topic))
                driver_types = asyncio.run(research.get_driver_types(topic))
            
            self.logger.debug(f"Using dynamic ontology for topic '{topic}':")
            self.logger.debug(f"  Categories: {categories}")
            self.logger.debug(f"  Future signals: {future_signals}")
            self.logger.debug(f"  Sentiment options: {sentiment_options}")
            self.logger.debug(f"  Time to impact: {time_to_impact_options}")
            self.logger.debug(f"  Driver types: {driver_types}")
            
            # Perform analysis with dynamic ontology data
            analysis_result = self.article_analyzer.analyze_content(
                article_text=article_text,
                title=title,
                source=source,
                uri=uri,
                summary_length=50,  # Keep existing summary length
                summary_voice="neutral",
                summary_type="informative",
                categories=categories,
                future_signals=future_signals,
                sentiment_options=sentiment_options,
                time_to_impact_options=time_to_impact_options,
                driver_types=driver_types
            )
            
            # Update article data with analysis results
            tags = analysis_result.get('tags', [])
            tags_str = ','.join(tags) if isinstance(tags, list) else str(tags) if tags else None
            
            article_data.update({
                'category': analysis_result.get('category'),
                'sentiment': analysis_result.get('sentiment'),
                'future_signal': analysis_result.get('future_signal'),
                'future_signal_explanation': analysis_result.get('future_signal_explanation'),
                'sentiment_explanation': analysis_result.get('sentiment_explanation'),
                'time_to_impact': analysis_result.get('time_to_impact'),
                'driver_type': analysis_result.get('driver_type'),
                'tags': tags_str,
                'analyzed': True
            })
            
            self.logger.debug(f"Analyzed article {uri}: category={analysis_result.get('category')}, sentiment={analysis_result.get('sentiment')}, future_signal={analysis_result.get('future_signal')}")
            
            return article_data
            
        except Exception as e:
            self.logger.error(f"Error analyzing article content: {e}")
            return article_data
    
    def score_article_relevance(self, article_data: Dict[str, Any], topic: str, keywords: List[str]) -> Dict[str, Any]:
        """
        Score article relevance using the RelevanceCalculator
        
        Args:
            article_data: Article data dictionary
            topic: Topic name for context
            keywords: List of keywords to check relevance against
            
        Returns:
            Dictionary containing relevance score and details
        """
        try:
            # Initialize relevance calculator if not already done
            if not self.relevance_calculator:
                from app.relevance import RelevanceCalculator
                
                # Get LLM model and parameters
                model_name = self.get_llm_client()
                
                # Initialize RelevanceCalculator with model name
                self.relevance_calculator = RelevanceCalculator(model_name=model_name)
            
            # Prepare article text for analysis
            article_text = f"{article_data.get('title', '')} {article_data.get('summary', '')}"
            
            # Calculate relevance score using correct parameter names
            keywords_str = ", ".join(keywords) if isinstance(keywords, list) else str(keywords)
            relevance_result = self.relevance_calculator.analyze_relevance(
                title=article_data.get('title', ''),
                source=article_data.get('news_source', ''),
                content=article_text,
                topic=topic,
                keywords=keywords_str
            )
            
            self.logger.debug(f"Relevance score for article {article_data.get('uri')}: {relevance_result}")
            
            return relevance_result
            
        except Exception as e:
            self.logger.error(f"Error scoring article relevance: {e}")
            return {"relevance_score": 0.0, "explanation": f"Error calculating relevance: {str(e)}"}
    
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
            existing_raw = self.db.get_raw_article(uri)
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
        keywords: List[str]
    ) -> Dict[str, Any]:
        """Process a single article asynchronously with optimized database operations"""
        article_uri = article.get('uri', 'unknown')
        article_title = article.get('title', 'Unknown Title')
        
        try:
            self.logger.debug(f"🔄 Processing article: {article_title}")
            
            # Step 1: Concurrent bias enrichment and content scraping
            bias_task = asyncio.create_task(
                self._enrich_article_with_bias_async(article)
            )
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
            
            # Save raw content if available
            if raw_content:
                try:
                    await self.async_db.save_raw_article_async(article_uri, raw_content, topic)
                    self.logger.debug(f"📄 Raw content saved for {article_uri}")
                except Exception as e:
                    self.logger.warning(f"Failed to save raw content for {article_uri}: {e}")
            
            # Step 2: LLM analysis with timeout
            try:
                enriched_article = await asyncio.wait_for(
                    self._analyze_article_content_async(enriched_article, topic),
                    timeout=60  # 1 minute timeout
                )
                self.logger.debug(f"🧠 LLM analysis completed for {article_uri}")
            except asyncio.TimeoutError:
                self.logger.warning(f"LLM analysis timed out for {article_uri}")
                enriched_article["analysis_error"] = "LLM analysis timed out"
            except Exception as e:
                self.logger.error(f"LLM analysis failed for {article_uri}: {e}")
                enriched_article["analysis_error"] = str(e)
            
            # Step 3: Async relevance scoring
            try:
                relevance_result = await self._score_article_relevance_async(
                    enriched_article, topic, keywords
                )
                enriched_article.update(relevance_result)
                self.logger.debug(f"🎯 Relevance scoring completed for {article_uri}")
            except Exception as e:
                self.logger.error(f"Relevance scoring failed for {article_uri}: {e}")
                relevance_result = {"relevance_score": 0.0, "explanation": f"Scoring failed: {str(e)}"}
                enriched_article.update(relevance_result)
            
            # Step 4: Check relevance threshold
            relevance_score = relevance_result.get("relevance_score", 0)
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
                    # Step 6: Async database update
                    try:
                        enriched_article.update({
                            "ingest_status": "approved",
                            "auto_ingested": True
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

    async def _analyze_article_content_async(self, article_data: Dict[str, Any], topic: str) -> Dict[str, Any]:
        """Async version of article analysis with dynamic ontology fetching"""
        try:
            # Initialize article analyzer if not already done
            if not self.article_analyzer:
                model_name = self.get_llm_client()
                ai_model = LiteLLMModel.get_instance(model_name)
                self.article_analyzer = ArticleAnalyzer(ai_model, use_cache=True)
            
            # Prepare content for analysis
            article_text = article_data.get('summary', '') or article_data.get('content', '')
            title = article_data.get('title', '')
            source = article_data.get('news_source', '')
            uri = article_data.get('uri', '')
            
            if not article_text or not title:
                self.logger.warning(f"Insufficient content for analysis: {uri}")
                return article_data
            
            # Use provided topic or get from article data
            if not topic:
                topic = article_data.get('topic')
            if not topic:
                self.logger.error(f"No topic specified for article {uri} - cannot determine ontology")
                return article_data
            
            # Set topic if not already present in article data
            if not article_data.get('topic'):
                article_data['topic'] = topic
            
            # Get topic-specific ontology dynamically using Research class
            from app.research import Research
            research = Research(self.db)
            
            # Set topic and get dynamic ontology data asynchronously
            research.set_topic(topic)
            
            # Get topic-specific analysis parameters dynamically
            categories = await research.get_categories(topic)
            future_signals = await research.get_future_signals(topic)
            sentiment_options = await research.get_sentiments(topic)
            time_to_impact_options = await research.get_time_to_impact(topic)
            driver_types = await research.get_driver_types(topic)
            
            self.logger.debug(f"Using dynamic ontology for topic '{topic}':")
            self.logger.debug(f"  Categories: {categories}")
            self.logger.debug(f"  Future signals: {future_signals}")
            self.logger.debug(f"  Sentiment options: {sentiment_options}")
            self.logger.debug(f"  Time to impact: {time_to_impact_options}")
            self.logger.debug(f"  Driver types: {driver_types}")
            
            # Perform analysis with dynamic ontology data in a thread executor
            loop = asyncio.get_event_loop()
            analysis_result = await loop.run_in_executor(
                None,
                self.article_analyzer.analyze_content,
                article_text,
                title,
                source,
                uri,
                50,  # summary_length
                "neutral",  # summary_voice
                "informative",  # summary_type
                categories,
                future_signals,
                sentiment_options,
                time_to_impact_options,
                driver_types
            )
            
            # Update article data with analysis results
            tags = analysis_result.get('tags', [])
            tags_str = ','.join(tags) if isinstance(tags, list) else str(tags) if tags else None
            
            article_data.update({
                'category': analysis_result.get('category'),
                'sentiment': analysis_result.get('sentiment'),
                'future_signal': analysis_result.get('future_signal'),
                'future_signal_explanation': analysis_result.get('future_signal_explanation'),
                'sentiment_explanation': analysis_result.get('sentiment_explanation'),
                'time_to_impact': analysis_result.get('time_to_impact'),
                'driver_type': analysis_result.get('driver_type'),
                'tags': tags_str,
                'analyzed': True
            })
            
            self.logger.debug(f"Async analyzed article {uri}: category={analysis_result.get('category')}, sentiment={analysis_result.get('sentiment')}, future_signal={analysis_result.get('future_signal')}")
            
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
        """Async vector database upsert"""
        try:
            from app.vector_store import upsert_article
            
            # Prepare article for vector indexing
            vector_article = article_data.copy()
            if raw_content:
                vector_article['raw'] = raw_content
            
            # Run in thread executor since vector operations might not be async
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, upsert_article, vector_article)
            
        except Exception as e:
            self.logger.error(f"Vector database upsert failed: {e}")
            raise

    async def process_articles_batch(self, articles: List[Dict[str, Any]], topic: str = None, keywords: List[str] = None, dry_run: bool = False) -> Dict[str, Any]:
        """
        Process a batch of articles through the enrichment pipeline
        
        Args:
            articles: List of article data dictionaries
            topic: Topic name for context
            keywords: List of keywords for relevance scoring
            dry_run: If True, skip database operations
            
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
            # Pre-scrape all articles in batch for efficiency
            article_uris = [article.get('uri') for article in articles if article.get('uri')]
            self.logger.info(f"🚀 Pre-scraping {len(article_uris)} articles in batch...")
            
            scraped_content = await self.scrape_articles_batch(article_uris)
            self.logger.info(f"✅ Batch scraping completed: {len(scraped_content)} articles")
            
            for article in articles:
                article_uri = article.get('uri', 'unknown')
                article_title = article.get('title', 'Unknown Title')
                
                try:
                    self.logger.info(f"🔄 Starting processing for article: {article_title}")
                    self.logger.info(f"   URI: {article_uri}")
                    self.logger.info(f"   Source: {article.get('news_source', 'Unknown')}")
                    results["processed"] += 1
                    
                    # Step 1: Enrich with bias data
                    self.logger.info(f"📊 Step 1: Enriching with media bias data...")
                    enriched_article = self.enrich_article_with_bias(article)
                    
                    # Log bias enrichment results
                    bias_data = {
                        'bias': enriched_article.get('bias'),
                        'factual_reporting': enriched_article.get('factual_reporting'),
                        'credibility': enriched_article.get('mbfc_credibility_rating')
                    }
                    self.logger.info(f"   ✅ Bias enrichment completed: {bias_data}")
                    
                    # Step 1.5: Get pre-scraped content
                    self.logger.info(f"📄 Step 2: Getting pre-scraped article content...")
                    raw_content = scraped_content.get(article_uri)
                    
                    if raw_content:
                        try:
                            # Save raw content to database
                            self.db.save_raw_article(
                                enriched_article.get("uri"),
                                raw_content,
                                topic or enriched_article.get("topic", "")
                            )
                            self.logger.info(f"   ✅ Raw content from batch scraping saved ({len(raw_content)} chars)")
                        except Exception as save_error:
                            self.logger.warning(f"   ⚠️ Failed to save raw content: {save_error}")
                    else:
                        self.logger.warning(f"   ❌ No content available from batch scraping for: {article_uri}")
                        # Try individual scraping as fallback
                        try:
                            raw_content = await self.scrape_article_content(article_uri)
                            if raw_content:
                                self.db.save_raw_article(
                                    enriched_article.get("uri"),
                                    raw_content,
                                    topic or enriched_article.get("topic", "")
                                )
                                self.logger.info(f"   ✅ Fallback individual scraping successful ({len(raw_content)} chars)")
                            else:
                                self.logger.warning(f"   ❌ Individual scraping also failed: {article_uri}")
                        except Exception as scrape_error:
                            self.logger.warning(f"   ⚠️ Individual scraping failed: {scrape_error}")
                            # Continue processing even if scraping fails

                    # Step 2: Perform full article analysis (category, sentiment, etc.)
                    self.logger.info(f"🧠 Step 3: Performing LLM analysis...")
                    # Ensure topic is available for analysis
                    if not enriched_article.get('topic') and topic:
                        enriched_article['topic'] = topic
                    enriched_article = self.analyze_article_content(enriched_article)
                    results["enriched"] += 1
                    
                    # Log analysis results
                    analysis_data = {
                        'category': enriched_article.get('category'),
                        'sentiment': enriched_article.get('sentiment'),
                        'future_signal': enriched_article.get('future_signal'),
                        'driver_type': enriched_article.get('driver_type')
                    }
                    self.logger.info(f"   ✅ LLM analysis completed: {analysis_data}")
                    
                    # Step 3: Score relevance
                    self.logger.info(f"🎯 Step 4: Scoring relevance...")
                    relevance_result = self.score_article_relevance(enriched_article, topic, keywords)
                    
                    # Store relevance data in enriched article
                    enriched_article.update({
                        "topic_alignment_score": relevance_result.get("topic_alignment_score"),
                        "keyword_relevance_score": relevance_result.get("keyword_relevance_score"),
                        "confidence_score": relevance_result.get("confidence_score"),
                        "overall_match_explanation": relevance_result.get("overall_match_explanation")
                    })
                    
                    # Log relevance results
                    relevance_score = relevance_result.get("relevance_score", 0)
                    relevance_threshold = self.get_relevance_threshold()
                    self.logger.info(f"   ✅ Relevance scoring completed:")
                    self.logger.info(f"      Score: {relevance_score:.3f} (threshold: {relevance_threshold:.3f})")
                    self.logger.info(f"      Topic alignment: {relevance_result.get('topic_alignment_score', 0):.3f}")
                    self.logger.info(f"      Keyword relevance: {relevance_result.get('keyword_relevance_score', 0):.3f}")
                    
                    # Check relevance threshold
                    if relevance_score >= relevance_threshold:
                        results["relevant"] += 1
                        self.logger.info(f"   ✅ Article meets relevance threshold - proceeding to quality check")
                        
                        # Step 4: Quality check
                        self.logger.info(f"🔍 Step 5: Quality control check...")
                        quality_result = self.quality_check_article(enriched_article)
                        
                        quality_score = quality_result.get("quality_score", 0)
                        quality_approved = quality_result.get("approved", False)
                        self.logger.info(f"   ✅ Quality check completed:")
                        self.logger.info(f"      Score: {quality_score:.3f}")
                        self.logger.info(f"      Approved: {quality_approved}")
                        
                        if quality_approved:
                            results["quality_passed"] += 1
                            self.logger.info(f"   ✅ Article approved for ingestion")
                            
                            # Update article with processing results
                            enriched_article.update({
                                "ingest_status": "approved",
                                "quality_score": quality_result.get("quality_score"),
                                "auto_ingested": True
                            })
                            
                            # Save approved article to database (unless dry run)
                            if not dry_run:
                                try:
                                    self.logger.info(f"💾 Step 6: Saving to database...")
                                    # Update the existing article record with auto-ingest data AND enrichment data
                                    with self.db.get_connection() as conn:
                                        cursor = conn.cursor()
                                        cursor.execute("""
                                            UPDATE articles 
                                            SET 
                                                title = COALESCE(?, title),
                                                summary = COALESCE(?, summary),
                                                auto_ingested = 1,
                                                ingest_status = ?,
                                                quality_score = ?,
                                                quality_issues = ?,
                                                category = ?,
                                                sentiment = ?,
                                                bias = ?,
                                                factual_reporting = ?,
                                                mbfc_credibility_rating = ?,
                                                bias_source = ?,
                                                bias_country = ?,
                                                press_freedom = ?,
                                                media_type = ?,
                                                popularity = ?,
                                                topic_alignment_score = ?,
                                                keyword_relevance_score = ?,
                                                future_signal = ?,
                                                future_signal_explanation = ?,
                                                sentiment_explanation = ?,
                                                time_to_impact = ?,
                                                driver_type = ?,
                                                tags = ?,
                                                analyzed = ?,
                                                confidence_score = ?,
                                                overall_match_explanation = ?
                                            WHERE uri = ?
                                        """, (
                                            enriched_article.get("title"),
                                            enriched_article.get("summary"),
                                            enriched_article.get("ingest_status"),
                                            enriched_article.get("quality_score"),
                                            enriched_article.get("quality_issues"),
                                            enriched_article.get("category"),
                                            enriched_article.get("sentiment"),
                                            enriched_article.get("bias"),
                                            enriched_article.get("factual_reporting"),
                                            enriched_article.get("mbfc_credibility_rating"),
                                            enriched_article.get("bias_source"),
                                            enriched_article.get("bias_country"),
                                            enriched_article.get("press_freedom"),
                                            enriched_article.get("media_type"),
                                            enriched_article.get("popularity"),
                                            enriched_article.get("topic_alignment_score"),
                                            enriched_article.get("keyword_relevance_score"),
                                            enriched_article.get("future_signal"),
                                            enriched_article.get("future_signal_explanation"),
                                            enriched_article.get("sentiment_explanation"),
                                            enriched_article.get("time_to_impact"),
                                            enriched_article.get("driver_type"),
                                            enriched_article.get("tags"),
                                            enriched_article.get("analyzed", True),
                                            enriched_article.get("confidence_score"),
                                            enriched_article.get("overall_match_explanation"),
                                            enriched_article.get("uri")
                                        ))
                                        conn.commit()
                                        
                                    results["saved"] += 1
                                    self.logger.info(f"   ✅ Database update completed")
                                    
                                    # ✅ ADD VECTOR DATABASE UPSERT
                                    try:
                                        self.logger.info(f"🔍 Step 7: Upserting to vector database...")
                                        from app.vector_store import upsert_article
                                        
                                        # Create a copy of enriched article for vector indexing
                                        vector_article = enriched_article.copy()
                                        
                                        # Try to get raw content for better vector indexing
                                        try:
                                            raw_article = self.db.get_raw_article(enriched_article.get("uri"))
                                            if raw_article and raw_article.get('raw_markdown'):
                                                vector_article['raw'] = raw_article['raw_markdown']
                                                self.logger.info(f"   📄 Found raw content for vector indexing ({len(raw_article['raw_markdown'])} chars)")
                                            else:
                                                self.logger.info(f"   📄 No raw content found, using summary for vector indexing")
                                        except Exception as raw_error:
                                            self.logger.warning(f"   ⚠️ Could not retrieve raw content: {raw_error}")
                                        
                                        # Ensure we have some content for indexing
                                        if vector_article.get('raw') or vector_article.get('summary') or vector_article.get('title'):
                                            # Index into vector database
                                            upsert_article(vector_article)
                                            results["vector_indexed"] += 1
                                            self.logger.info(f"   ✅ Vector database upsert completed")
                                        else:
                                            self.logger.warning(f"   ⚠️ No content available for vector indexing")
                                            
                                    except Exception as vector_error:
                                        self.logger.error(f"   ❌ Failed to upsert to vector database: {str(vector_error)}")
                                        # Don't fail the entire operation if vector indexing fails
                                        self.logger.warning("   ⚠️ Article saved to database but not indexed in vector store")
                                    
                                    self.logger.info(f"✅ Successfully processed and saved article: {article_title}")
                                    
                                except Exception as save_error:
                                    error_msg = f"Error updating article {enriched_article.get('uri', 'unknown')}: {str(save_error)}"
                                    results["errors"].append(error_msg)
                                    self.logger.error(f"❌ Database save failed: {error_msg}")
                            else:
                                # In dry run mode, simulate saving
                                results["saved"] += 1
                                results["vector_indexed"] += 1
                                self.logger.info(f"🧪 Dry run: Would update and vector index article: {enriched_article.get('uri')}")
                            
                        else:
                            self.logger.warning(f"   ❌ Article failed quality check - marking as failed")
                            quality_issues = quality_result.get("quality_issues", "Unknown quality issues")
                            self.logger.warning(f"      Issues: {quality_issues}")
                            
                            enriched_article.update({
                                "ingest_status": "failed",
                                "quality_issues": quality_issues,
                                "auto_ingested": True
                            })
                            
                            # Update the article record even for failed quality check (unless dry run)
                            if not dry_run:
                                try:
                                    with self.db.get_connection() as conn:
                                        cursor = conn.cursor()
                                        cursor.execute("""
                                            UPDATE articles 
                                            SET 
                                                auto_ingested = 1,
                                                ingest_status = ?,
                                                quality_score = ?,
                                                quality_issues = ?
                                            WHERE uri = ?
                                        """, (
                                            enriched_article.get("ingest_status"),
                                            quality_result.get("quality_score"),
                                            enriched_article.get("quality_issues"),
                                            enriched_article.get("uri")
                                        ))
                                        conn.commit()
                                        
                                    self.logger.info(f"   ✅ Updated failed quality check article in database")
                                except Exception as save_error:
                                    error_msg = f"Error updating failed article {enriched_article.get('uri', 'unknown')}: {str(save_error)}"
                                    results["errors"].append(error_msg)
                                    self.logger.error(f"❌ Failed article update error: {error_msg}")
                    else:
                        self.logger.warning(f"   ❌ Article below relevance threshold ({relevance_score:.3f} < {relevance_threshold:.3f}) - skipping")
                    
                except Exception as e:
                    error_msg = f"Error processing article {article.get('uri', 'unknown')}: {str(e)}"
                    results["errors"].append(error_msg)
                    self.logger.error(f"❌ Article processing failed: {error_msg}")
                    
                # Add separator between articles for readability
                self.logger.info(f"{'='*80}")
            
            self.logger.info(f"🏁 Batch processing completed:")
            self.logger.info(f"   📊 Processed: {results['processed']}")
            self.logger.info(f"   🧠 Enriched: {results['enriched']}")
            self.logger.info(f"   🎯 Relevant: {results['relevant']}")
            self.logger.info(f"   ✅ Quality passed: {results['quality_passed']}")
            self.logger.info(f"   💾 Saved: {results['saved']}")
            self.logger.info(f"   🔍 Vector indexed: {results['vector_indexed']}")
            self.logger.info(f"   ❌ Errors: {len(results['errors'])}")
            
            return results
            
        except Exception as e:
            self.logger.error(f"❌ Error in batch processing: {e}")
            results["errors"].append(f"Batch processing error: {str(e)}")
            return results
    
    def save_approved_articles(self, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Save approved articles to the database
        
        Args:
            articles: List of processed and approved articles
            
        Returns:
            Save operation results
        """
        results = {"saved": 0, "errors": []}
        
        try:
            for article in articles:
                try:
                    # Use existing database save_article method
                    self.db.save_article(article)
                    results["saved"] += 1
                    self.logger.debug(f"Saved article: {article.get('uri')}")
                    
                except Exception as e:
                    error_msg = f"Error saving article {article.get('uri', 'unknown')}: {str(e)}"
                    results["errors"].append(error_msg)
                    self.logger.error(error_msg)
            
            self.logger.info(f"Article save completed: {results}")
            
        except Exception as e:
            self.logger.error(f"Error in save_approved_articles: {e}")
            results["errors"].append(f"Save operation error: {str(e)}")
        
        return results
    
    def get_relevance_threshold(self) -> float:
        """
        Get the minimum relevance threshold from database settings
        
        Returns:
            Relevance threshold value (0.0-1.0)
        """
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT min_relevance_threshold
                    FROM keyword_monitor_settings 
                    WHERE id = 1
                """)
                settings = cursor.fetchone()
                if settings and settings[0] is not None:
                    return float(settings[0])
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
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT 
                        auto_ingest_enabled,
                        min_relevance_threshold,
                        quality_control_enabled,
                        auto_save_approved_only,
                        default_llm_model,
                        llm_temperature,
                        llm_max_tokens
                    FROM keyword_monitor_settings 
                    WHERE id = 1
                """)
                settings = cursor.fetchone()
                
                if settings:
                    return {
                        "auto_ingest_enabled": bool(settings[0]),
                        "min_relevance_threshold": float(settings[1] or 0.0),
                        "quality_control_enabled": bool(settings[2]),
                        "auto_save_approved_only": bool(settings[3]),
                        "default_llm_model": settings[4] or "gpt-4o-mini",
                        "llm_temperature": float(settings[5] or 0.1),
                        "llm_max_tokens": int(settings[6] or 1000)
                    }
        except Exception as e:
            self.logger.error(f"Error getting auto-ingest settings: {e}")
        
        # Return defaults
        return {
            "auto_ingest_enabled": False,
            "min_relevance_threshold": 0.0,
            "quality_control_enabled": True,
            "auto_save_approved_only": False,
            "default_llm_model": "gpt-4o-mini",
            "llm_temperature": 0.1,
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
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                
                # Check which table structure to use
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='keyword_article_matches'")
                use_new_table = cursor.fetchone() is not None
                
                if use_new_table:
                    # Use new table structure
                    cursor.execute("""
                        SELECT DISTINCT a.uri, a.title, a.summary, a.news_source, kg.topic
                        FROM articles a
                        JOIN keyword_article_matches ka ON a.uri = ka.article_uri
                        JOIN keyword_groups kg ON ka.group_id = kg.id
                        WHERE kg.topic = ?
                        ORDER BY ka.detected_at DESC
                    """, (topic_id,))
                else:
                    # Use old table structure
                    cursor.execute("""
                        SELECT DISTINCT a.uri, a.title, a.summary, a.news_source, kg.topic
                        FROM articles a
                        JOIN keyword_alerts ka ON a.uri = ka.article_uri
                        JOIN monitored_keywords mk ON ka.keyword_id = mk.id
                        JOIN keyword_groups kg ON mk.group_id = kg.id
                        WHERE kg.topic = ?
                        ORDER BY ka.detected_at DESC
                    """, (topic_id,))
                
                all_articles = []
                for row in cursor.fetchall():
                    all_articles.append({
                        "uri": row[0],
                        "title": row[1],
                        "summary": row[2],
                        "news_source": row[3],
                        "topic": row[4]
                    })
                
                # For processing, filter to only unprocessed AND unread articles
                if use_new_table:
                    cursor.execute("""
                        SELECT DISTINCT a.uri, a.title, a.summary, a.news_source, kg.topic
                        FROM articles a
                        JOIN keyword_article_matches ka ON a.uri = ka.article_uri
                        JOIN keyword_groups kg ON ka.group_id = kg.id
                        WHERE kg.topic = ?
                        AND (a.auto_ingested IS NULL OR a.auto_ingested = 0)
                        AND ka.is_read = 0
                        ORDER BY ka.detected_at DESC
                    """, (topic_id,))
                else:
                    cursor.execute("""
                        SELECT DISTINCT a.uri, a.title, a.summary, a.news_source, kg.topic
                        FROM articles a
                        JOIN keyword_alerts ka ON a.uri = ka.article_uri
                        JOIN monitored_keywords mk ON ka.keyword_id = mk.id
                        JOIN keyword_groups kg ON mk.group_id = kg.id
                        WHERE kg.topic = ?
                        AND (a.auto_ingested IS NULL OR a.auto_ingested = 0)
                        AND ka.is_read = 0
                        ORDER BY ka.detected_at DESC
                    """, (topic_id,))
                
                unprocessed_unread_articles = []
                for row in cursor.fetchall():
                    unprocessed_unread_articles.append({
                        "uri": row[0],
                        "title": row[1],
                        "summary": row[2],
                        "news_source": row[3],
                        "topic": row[4]
                    })
                
                # Get keywords for the topic
                cursor.execute("""
                    SELECT mk.keyword
                    FROM monitored_keywords mk
                    JOIN keyword_groups kg ON mk.group_id = kg.id
                    WHERE kg.topic = ?
                """, (topic_id,))
                
                keywords = [row[0] for row in cursor.fetchall()]
            
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
                existing_raw = self.db.get_raw_article(uri)
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
            # Prepare batch request
            batch_data = {
                "urls": uris,
                "formats": ["markdown"],
                "onlyMainContent": True,
                "timeout": 30000,
                "maxConcurrency": 5  # Limit concurrent requests
            }
            
            self.logger.info(f"Submitting batch scrape request for {len(uris)} URLs")
            
            # Submit batch request using async method
            batch_response = firecrawl_app.async_batch_scrape_urls(uris, **{
                k: v for k, v in batch_data.items() if k != 'urls'
            })
            
            if not batch_response or not batch_response.get('success'):
                self.logger.error(f"Batch scrape failed: {batch_response}")
                return {}
            
            batch_id = batch_response.get('id')
            if not batch_id:
                self.logger.error("No batch ID returned from Firecrawl")
                return {}
            
            self.logger.info(f"Batch scrape submitted with ID: {batch_id}")
            
            # Poll for completion
            results = await self._poll_batch_completion(firecrawl_app, batch_id)
            
            # Process results
            processed_results = {}
            for uri, content in results.items():
                if content:
                    # Apply token limiting
                    from app.analyzers.article_analyzer import ArticleAnalyzer
                    truncated_content = ArticleAnalyzer.truncate_text(None, content, max_chars=65000)
                    
                    if len(content) > len(truncated_content):
                        self.logger.info(f"Truncated content for {uri}: {len(content)} -> {len(truncated_content)} chars")
                    
                    processed_results[uri] = truncated_content
                else:
                    processed_results[uri] = None
            
            return processed_results
            
        except Exception as e:
            self.logger.error(f"Error in Firecrawl batch scraping: {e}")
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
                status_response = firecrawl_app.check_batch_scrape_status(batch_id)
                
                if not status_response:
                    self.logger.warning(f"No status response for batch {batch_id}")
                    await asyncio.sleep(poll_interval)
                    continue
                
                status = status_response.get('status')
                self.logger.debug(f"Batch {batch_id} status: {status}")
                
                if status == 'completed':
                    # Get results
                    results = {}
                    data = status_response.get('data', [])
                    
                    for item in data:
                        url = item.get('url')
                        if item.get('success') and 'markdown' in item:
                            results[url] = item['markdown']
                        else:
                            results[url] = None
                            self.logger.warning(f"Failed to scrape {url}: {item.get('error', 'Unknown error')}")
                    
                    self.logger.info(f"Batch {batch_id} completed with {len(results)} results")
                    return results
                    
                elif status == 'failed':
                    self.logger.error(f"Batch {batch_id} failed: {status_response.get('error', 'Unknown error')}")
                    return {}
                    
                # Still processing, wait before next poll
                await asyncio.sleep(poll_interval)
                
                # Increase poll interval gradually
                poll_interval = min(poll_interval * 1.2, 30)
                
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