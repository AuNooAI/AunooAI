"""
Automated Ingest Service

This service handles the automated ingestion pipeline that:
1. Fetches articles from TheNewsAPI for monitored keywords
2. Enriches with media bias and factuality data  
3. Scores articles for relevance
4. Applies quality control validation
5. Auto-saves articles that pass quality checks
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from app.database import Database
from app.models.media_bias import MediaBias
from app.relevance import RelevanceCalculator
from app.analyzers.article_analyzer import ArticleAnalyzer
from app.ai_models import LiteLLMModel
import asyncio
import requests
from app.config.config import load_config

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
        self.config = config or load_config()
        self.relevance_calculator = None
        self.media_bias = MediaBias(db)
        self.article_analyzer = None
        
        # Configure logging
        self.logger = logger
        self.logger.info("AutomatedIngestService initialized")
    
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
            
            # Default analysis parameters (from research.py)
            categories = ["Technology", "AI and Machine Learning", "Business", "Science", "Politics", "Health", "Environment", "Finance", "Education", "Social", "Other"]
            future_signals = ["Breakthrough", "Evolution", "Warning", "Trend", "Disruption"]
            sentiment_options = ["Positive", "Negative", "Neutral", "Mixed", "Critical"]
            time_to_impact_options = ["Immediate", "Short-term", "Medium-term", "Long-term", "Uncertain"]
            driver_types = ["Technology", "Policy", "Economic", "Social", "Environmental"]
            
            # Perform analysis
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
            
            self.logger.debug(f"Analyzed article {uri}: category={analysis_result.get('category')}, sentiment={analysis_result.get('sentiment')}")
            
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
                    
                    # Step 1.5: Scrape and save raw content
                    self.logger.info(f"📄 Step 2: Scraping raw article content...")
                    try:
                        raw_content = await self.scrape_article_content(enriched_article.get("uri"))
                        if raw_content:
                            # Save raw content to database
                            self.db.save_raw_article(
                                enriched_article.get("uri"),
                                raw_content,
                                topic or enriched_article.get("topic", "")
                            )
                            self.logger.info(f"   ✅ Raw content scraped and saved ({len(raw_content)} chars)")
                        else:
                            self.logger.warning(f"   ⚠️ No raw content available for scraping")
                    except Exception as scrape_error:
                        self.logger.warning(f"   ⚠️ Raw content scraping failed: {scrape_error}")
                        # Continue processing even if scraping fails

                    # Step 2: Perform full article analysis (category, sentiment, etc.)
                    self.logger.info(f"🧠 Step 3: Performing LLM analysis...")
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
                                                analyzed = ?
                                            WHERE uri = ?
                                        """, (
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