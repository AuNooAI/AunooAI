import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
import asyncio
import time
from urllib.parse import urlparse, urlunparse

from app.schemas.news_feed import (
    DailyOverview, SixArticlesReport, TopStory, NewsArticle, 
    RelatedArticle, ArticleSource, BiasRating, FactualityRating,
    NewsFeedRequest, NewsFeedResponse
)
from app.database import Database, get_database_instance
from app.services.auspex_service import get_auspex_service
from app.database_query_facade import DatabaseQueryFacade

logger = logging.getLogger(__name__)


class NewsFeedService:
    """
    Service for generating Techmeme-style daily news feeds using AI analysis.
    Leverages the existing Auspex service for AI content generation.
    """
    
    def __init__(self, db: Database):
        self.db = db
        self.facade = DatabaseQueryFacade(db, logger)
        self.auspex = get_auspex_service()
    
    async def generate_daily_feed(self, request: NewsFeedRequest) -> NewsFeedResponse:
        """Generate both overview and six articles report"""
        start_time = time.time()
        
        # Use today if no date specified
        target_date = request.date or datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Get articles for the date range
        articles_data = await self._get_articles_for_date_range(
            request.date_range or "24h", 
            request.max_articles, 
            request.topic, 
            target_date
        )
        
        if not articles_data:
            raise ValueError("No articles found for the specified date and criteria")
        
        # Generate article list and six articles report concurrently
        article_list_task = self._generate_article_list(articles_data, target_date, request, page=1, per_page=20)
        six_articles_task = self._generate_six_articles_report_cached(articles_data, target_date, request)
        
        article_list, six_articles = await asyncio.gather(article_list_task, six_articles_task)
        
        processing_time = time.time() - start_time
        
        return NewsFeedResponse(
            overview=article_list,
            six_articles=six_articles,
            processing_time_seconds=processing_time
        )
    
    async def _get_articles_for_date_range(self, date_range: str, max_articles: int, topic: Optional[str] = None, custom_date: Optional[datetime] = None) -> List[Dict]:
        """Get articles for a date range with bias and factuality data"""
        
        # Calculate date range based on selection
        now = datetime.now()
        
        if date_range == 'custom' and custom_date:
            # Single custom date
            target_date = custom_date.replace(hour=0, minute=0, second=0, microsecond=0)
            start_date = target_date
            end_date = target_date + timedelta(days=1)
            date_condition = "DATE(publication_date) = ?"
            params = [target_date.strftime('%Y-%m-%d')]
        elif date_range == '24h':
            start_date = now - timedelta(days=1)
            end_date = now
            date_condition = "publication_date >= ? AND publication_date <= ?"
            params = [start_date.isoformat(), end_date.isoformat()]
        elif date_range == '7d':
            start_date = now - timedelta(days=7)
            end_date = now
            date_condition = "publication_date >= ? AND publication_date <= ?"
            params = [start_date.isoformat(), end_date.isoformat()]
        elif date_range == '30d':
            start_date = now - timedelta(days=30)
            end_date = now
            date_condition = "publication_date >= ? AND publication_date <= ?"
            params = [start_date.isoformat(), end_date.isoformat()]
        elif date_range == '3m':
            start_date = now - timedelta(days=90)
            end_date = now
            date_condition = "publication_date >= ? AND publication_date <= ?"
            params = [start_date.isoformat(), end_date.isoformat()]
        elif date_range == '1y':
            start_date = now - timedelta(days=365)
            end_date = now
            date_condition = "publication_date >= ? AND publication_date <= ?"
            params = [start_date.isoformat(), end_date.isoformat()]
        elif date_range == 'all':
            date_condition = "publication_date IS NOT NULL"
            params = []
            start_date = None
            end_date = now
        else:
            # Default to last 24 hours
            start_date = now - timedelta(days=1)
            end_date = now
            date_condition = "publication_date >= ? AND publication_date <= ?"
            params = [start_date.isoformat(), end_date.isoformat()]
        
        logger.info(f"Getting articles for date range: {start_date.isoformat() if start_date else 'all time'} to {end_date.isoformat()}")
        
        # Build query with bias and factuality fields
        query = f"""
        SELECT 
            uri, title, summary, news_source, publication_date, submission_date,
            category, sentiment, sentiment_explanation, time_to_impact, time_to_impact_explanation,
            tags, bias, factual_reporting, mbfc_credibility_rating, bias_source, 
            bias_country, press_freedom, media_type, popularity,
            future_signal, future_signal_explanation, driver_type, driver_type_explanation
        FROM articles 
        WHERE {date_condition}
        AND category IS NOT NULL
        AND sentiment IS NOT NULL 
        AND bias IS NOT NULL
        AND factual_reporting IS NOT NULL
        """
        
        if topic:
            query += " AND (topic = ? OR title LIKE ? OR summary LIKE ?)"
            topic_pattern = f"%{topic}%"
            params.extend([topic, topic_pattern, topic_pattern])
        
        # Filter out promotional/spam content and order by quality
        query += """ 
        AND title NOT LIKE '%Call@%'
        AND title NOT LIKE '%+91%'
        AND title NOT LIKE '%best%agency%'
        AND title NOT LIKE '%#1%'
        AND summary NOT LIKE '%Call@%'
        AND summary NOT LIKE '%phone%number%'
        AND news_source NOT LIKE '%medium.com/@%'
        ORDER BY 
            CASE WHEN factual_reporting = 'High' THEN 3
                 WHEN factual_reporting = 'Mostly Factual' THEN 2
                 ELSE 1 END DESC,
            CASE WHEN news_source LIKE '%.com' AND news_source NOT LIKE '%medium.com%' THEN 2
                 WHEN news_source LIKE '%reuters%' OR news_source LIKE '%bloomberg%' OR news_source LIKE '%techcrunch%' THEN 3
                 ELSE 1 END DESC,
            publication_date DESC 
        LIMIT ?
        """
        params.append(max_articles)
        
        try:
            results = self.db.fetch_all(query, params)
            logger.info(f"Found {len(results)} articles for date range: {date_range}")
            
            # Convert sqlite3.Row objects to dictionaries
            articles_list = []
            for row in results:
                if hasattr(row, 'keys'):  # Check if it's a Row object
                    article_dict = dict(row)
                    articles_list.append(article_dict)
                else:
                    articles_list.append(row)  # Already a dict
            
            return articles_list
        except Exception as e:
            logger.error(f"Error fetching articles: {e}")
            return []
    
    async def _get_articles_for_date(self, date: datetime, max_articles: int, topic: Optional[str] = None) -> List[Dict]:
        """Backward compatibility wrapper for _get_articles_for_date_range"""
        return await self._get_articles_for_date_range("custom", max_articles, topic, date)
    
    async def _get_organizational_profile(self, profile_id: Optional[int]) -> Optional[Dict]:
        """Fetch organizational profile by ID"""
        if not profile_id:
            logger.info("No profile_id provided, using default analysis")
            return None
            
        try:
            logger.info(f"Fetching organizational profile for ID: {profile_id}")
            profile_row = self.facade.get_organizational_profile_for_ui(profile_id)
            if not profile_row:
                logger.warning(f"No organizational profile found for ID: {profile_id}")
                return None
                
            import json
            profile = {
                'id': profile_row[0],
                'name': profile_row[1],
                'description': profile_row[2],
                'industry': profile_row[3],
                'organization_type': profile_row[4],
                'region': profile_row[5],
                'key_concerns': json.loads(profile_row[6]) if profile_row[6] else [],
                'strategic_priorities': json.loads(profile_row[7]) if profile_row[7] else [],
                'risk_tolerance': profile_row[8],
                'innovation_appetite': profile_row[9],
                'decision_making_style': profile_row[10],
                'stakeholder_focus': json.loads(profile_row[11]) if profile_row[11] else [],
                'competitive_landscape': json.loads(profile_row[12]) if profile_row[12] else [],
                'regulatory_environment': json.loads(profile_row[13]) if profile_row[13] else [],
                'custom_context': profile_row[14],
                'is_default': bool(profile_row[15])
            }
            logger.info(f"Successfully loaded profile: {profile['name']} ({profile['industry']})")
            return profile
        except Exception as e:
            logger.error(f"Error fetching organizational profile {profile_id}: {e}")
            # Don't fail the entire request if profile loading fails
            logger.warning("Continuing with default analysis due to profile loading error")
            return None
    
    async def _get_total_articles_count_for_date_range(self, date_range: str, topic: Optional[str] = None, custom_date: Optional[datetime] = None) -> int:
        """Get the total count of articles for a date range (without limit)"""
        
        # Calculate date range based on selection (same logic as _get_articles_for_date_range)
        now = datetime.now()
        
        if date_range == 'custom' and custom_date:
            target_date = custom_date.replace(hour=0, minute=0, second=0, microsecond=0)
            date_condition = "DATE(publication_date) = ?"
            params = [target_date.strftime('%Y-%m-%d')]
        elif date_range == '24h':
            start_date = now - timedelta(days=1)
            end_date = now
            date_condition = "publication_date >= ? AND publication_date <= ?"
            params = [start_date.isoformat(), end_date.isoformat()]
        elif date_range == '7d':
            start_date = now - timedelta(days=7)
            end_date = now
            date_condition = "publication_date >= ? AND publication_date <= ?"
            params = [start_date.isoformat(), end_date.isoformat()]
        elif date_range == '30d':
            start_date = now - timedelta(days=30)
            end_date = now
            date_condition = "publication_date >= ? AND publication_date <= ?"
            params = [start_date.isoformat(), end_date.isoformat()]
        elif date_range == '3m':
            start_date = now - timedelta(days=90)
            end_date = now
            date_condition = "publication_date >= ? AND publication_date <= ?"
            params = [start_date.isoformat(), end_date.isoformat()]
        elif date_range == '1y':
            start_date = now - timedelta(days=365)
            end_date = now
            date_condition = "publication_date >= ? AND publication_date <= ?"
            params = [start_date.isoformat(), end_date.isoformat()]
        elif date_range == 'all':
            date_condition = "publication_date IS NOT NULL"
            params = []
        else:
            # Default to last 24 hours
            start_date = now - timedelta(days=1)
            end_date = now
            date_condition = "publication_date >= ? AND publication_date <= ?"
            params = [start_date.isoformat(), end_date.isoformat()]
        
        # Build count query with same filtering as _get_articles_for_date_range
        query = f"""
        SELECT COUNT(*) 
        FROM articles 
        WHERE {date_condition}
        AND category IS NOT NULL
        AND sentiment IS NOT NULL 
        AND bias IS NOT NULL
        AND factual_reporting IS NOT NULL
        AND title NOT LIKE '%Call@%'
        AND title NOT LIKE '%+91%'
        AND title NOT LIKE '%best%agency%'
        AND title NOT LIKE '%#1%'
        AND summary NOT LIKE '%Call@%'
        AND summary NOT LIKE '%phone%number%'
        AND news_source NOT LIKE '%medium.com/@%'
        """
        
        if topic:
            query += " AND (topic = ? OR title LIKE ? OR summary LIKE ?)"
            topic_pattern = f"%{topic}%"
            params.extend([topic, topic_pattern, topic_pattern])
        
        try:
            result = self.db.fetch_one(query, params)
            return result[0] if result else 0
        except Exception as e:
            logger.error(f"Error getting total articles count for date range: {e}")
            return 0
    
    async def _get_total_articles_count_for_date(self, date: datetime, topic: Optional[str] = None) -> int:
        """Backward compatibility wrapper for single date count"""
        return await self._get_total_articles_count_for_date_range("custom", topic, date)
    
    async def _find_related_articles(self, article_uri: str, top_k: int = 5) -> List[Dict]:
        """Find thematically related articles using enhanced similarity search"""
        if not article_uri:
            logger.warning("No article URI provided for related articles search")
            return []
            
        try:
            logger.info(f"Searching for {top_k} related articles for URI: {article_uri}")
            
            # First, get the original article to understand its themes
            original_article = None
            current_articles = getattr(self, '_current_articles_data', [])
            
            logger.debug(f"Looking for URI {article_uri} in {len(current_articles)} articles")
            
            for article in current_articles:
                if article.get('uri') == article_uri:
                    original_article = article
                    logger.debug(f"Found exact URI match: {article_uri}")
                    break
            
            # If exact match fails, try partial matching
            if not original_article and current_articles:
                for article in current_articles:
                    article_uri_clean = article.get('uri', '').strip()
                    if article_uri_clean and article_uri in article_uri_clean:
                        original_article = article
                        logger.debug(f"Found partial URI match: {article_uri_clean}")
                        break
            
            if not original_article:
                logger.warning(f"Could not find original article for URI: {article_uri}")
                logger.debug(f"Available URIs: {[a.get('uri', 'NO_URI')[:50] for a in current_articles[:3]]}")
                # Use vector search anyway with a fallback approach
                try:
                    from app.vector_store import similar_articles
                    similar_results = similar_articles(article_uri, top_k=top_k)
                    
                    related_articles = []
                    for result in similar_results:
                        if result.get('metadata') and result.get('score', 0) > 0.2:
                            metadata = result['metadata']
                            related_articles.append({
                                'title': metadata.get('title', 'Untitled'),
                                'source': metadata.get('news_source', 'Unknown Source'),
                                'url': metadata.get('uri', ''),
                                'bias': metadata.get('bias'),
                                'summary': metadata.get('summary', 'No summary available'),
                                'similarity_score': result.get('score', 0.0),
                                'factual_reporting': metadata.get('factual_reporting', ''),
                                'category': metadata.get('category', '')
                            })
                    
                    logger.info(f"Fallback vector search found {len(related_articles)} related articles")
                    return related_articles
                    
                except Exception as e:
                    logger.error(f"Fallback vector search failed: {e}")
                    return []
            
            # Extract key entities and themes from the original article
            original_title = original_article.get('title', '').lower()
            original_summary = original_article.get('summary', '').lower()
            original_category = original_article.get('category', '')
            
            # Get vector similarity results
            from app.vector_store import similar_articles
            similar_results = similar_articles(article_uri, top_k=top_k * 3)  # Get more candidates
            logger.info(f"Vector search returned {len(similar_results)} similar articles")
            
            # Enhanced filtering for thematic relevance
            related_articles = []
            similarity_threshold = 0.2  # Increased threshold for better quality
            
            for i, result in enumerate(similar_results):
                if result.get('metadata'):
                    metadata = result['metadata']
                    similarity_score = result.get('score', 0.0)
                    
                    # Skip articles with very low similarity
                    if similarity_score < similarity_threshold:
                        continue
                    
                    # Calculate thematic relevance boost
                    thematic_score = self._calculate_thematic_relevance(
                        original_article, metadata, similarity_score
                    )
                    
                    # Only include if thematically relevant
                    if thematic_score > 0.3:  # Minimum thematic relevance
                        related_article = {
                            'title': metadata.get('title', 'Untitled'),
                            'source': metadata.get('news_source', 'Unknown Source'),
                            'url': metadata.get('uri', ''),
                            'bias': metadata.get('bias'),
                            'summary': metadata.get('summary', 'No summary available'),
                            'similarity_score': thematic_score,  # Use enhanced score
                            'category': metadata.get('category', ''),
                            'factual_reporting': metadata.get('factual_reporting', '')
                        }
                        related_articles.append(related_article)
                        logger.debug(f"Related article {len(related_articles)}: {related_article['title']} (thematic score: {thematic_score:.3f})")
                        
                        # Stop when we have enough high-quality matches
                        if len(related_articles) >= top_k:
                            break
            
            logger.info(f"Successfully processed {len(related_articles)} thematically related articles")
            return related_articles
            
        except ImportError as e:
            logger.error(f"Vector store import failed: {e}")
            return []
        except Exception as e:
            logger.error(f"Error finding related articles for {article_uri}: {e}")
            logger.exception("Full traceback:")
            return []
    
    def _calculate_thematic_relevance(self, original_article: Dict, candidate_metadata: Dict, base_similarity: float) -> float:
        """Calculate enhanced thematic relevance score"""
        
        # Start with base similarity
        score = base_similarity
        
        # Extract key information
        orig_title = original_article.get('title', '').lower()
        orig_summary = original_article.get('summary', '').lower()
        orig_category = original_article.get('category', '')
        
        cand_title = candidate_metadata.get('title', '').lower()
        cand_summary = candidate_metadata.get('summary', '').lower()
        cand_category = candidate_metadata.get('category', '')
        
        # Boost for same category
        if orig_category and cand_category and orig_category == cand_category:
            score += 0.2
            
        # Boost for entity/company name overlap
        # Extract potential entity names (capitalized words, common company indicators)
        import re
        orig_entities = set(re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', original_article.get('title', '')))
        orig_entities.update(re.findall(r'\b(?:Tesla|Apple|Google|Microsoft|Amazon|Meta|OpenAI|Anthropic|DeepMind)\b', orig_title, re.IGNORECASE))
        
        cand_entities = set(re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', candidate_metadata.get('title', '')))
        cand_entities.update(re.findall(r'\b(?:Tesla|Apple|Google|Microsoft|Amazon|Meta|OpenAI|Anthropic|DeepMind)\b', cand_title, re.IGNORECASE))
        
        # Strong boost for entity overlap
        entity_overlap = len(orig_entities.intersection(cand_entities))
        if entity_overlap > 0:
            score += entity_overlap * 0.3  # Significant boost for entity matches
            
        # Boost for keyword overlap in titles
        orig_keywords = set(word for word in orig_title.split() if len(word) > 3)
        cand_keywords = set(word for word in cand_title.split() if len(word) > 3)
        keyword_overlap = len(orig_keywords.intersection(cand_keywords)) / max(len(orig_keywords), 1)
        score += keyword_overlap * 0.15
        
        # Penalize if articles are too similar (likely duplicates)
        if base_similarity > 0.9:
            score *= 0.5  # Reduce score for likely duplicates
            
        return min(score, 1.0)  # Cap at 1.0
    
    async def _generate_article_list(self, articles_data: List[Dict], date: datetime, request: NewsFeedRequest, page: int = 1, per_page: int = 20) -> Dict:
        """Generate paginated article list similar to topic dashboard"""
        
        # Get the actual total count from database (not limited by max_articles)
        total_articles = await self._get_total_articles_count_for_date_range(
            request.date_range or "24h", 
            request.topic, 
            request.date
        )
        
        # Calculate pagination
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated_articles = articles_data[start_idx:end_idx]
        
        # Convert articles to the expected format
        article_items = []
        for article in paginated_articles:
            # Convert sqlite3.Row to dict if needed
            if hasattr(article, 'keys'):
                article_dict = dict(article)
            else:
                article_dict = article
                
            article_items.append({
                'uri': article_dict.get('uri', ''),
                'title': article_dict.get('title', 'Untitled'),
                'summary': article_dict.get('summary', 'No summary available'),
                'news_source': article_dict.get('news_source'),  # Let frontend handle None/empty
                'publication_date': article_dict.get('publication_date'),
                'category': article_dict.get('category'),
                'sentiment': article_dict.get('sentiment'),
                'sentiment_explanation': article_dict.get('sentiment_explanation'),
                'time_to_impact': article_dict.get('time_to_impact'),
                'time_to_impact_explanation': article_dict.get('time_to_impact_explanation'),
                'driver_type': article_dict.get('driver_type'),
                'driver_type_explanation': article_dict.get('driver_type_explanation'),
                'tags': article_dict.get('tags', '').split(',') if article_dict.get('tags') else [],
                'url': article_dict.get('url', ''),  # For archive links
                'bias': article_dict.get('bias'),
                'factual_reporting': article_dict.get('factual_reporting'),
                'mbfc_credibility_rating': article_dict.get('mbfc_credibility_rating'),
                'bias_source': article_dict.get('bias_source'),
                'bias_country': article_dict.get('bias_country'),
                'press_freedom': article_dict.get('press_freedom'),
                'media_type': article_dict.get('media_type'),
                'popularity': article_dict.get('popularity'),
                'future_signal': article_dict.get('future_signal'),
                'future_signal_explanation': article_dict.get('future_signal_explanation')
            })
        
        return {
            'items': article_items,
            'total_items': total_articles,  # Match the field name expected by frontend
            'total_articles': total_articles,  # Keep for backward compatibility
            'page': page,
            'per_page': per_page,
            'total_pages': (total_articles + per_page - 1) // per_page,
            'date': date.isoformat()
        }
    
    async def _generate_six_articles_report(self, articles_data: List[Dict], date: datetime, request: NewsFeedRequest) -> List[Dict]:
        """Generate detailed six articles report using Auspex service"""
        
        logger.info(f"Starting six articles generation for {len(articles_data)} articles on {date.date()}")
        
        # Get organizational profile if specified
        try:
            org_profile = await self._get_organizational_profile(request.profile_id)
            logger.info(f"Organizational profile loaded: {org_profile['name'] if org_profile else 'None'}")
        except Exception as e:
            logger.error(f"Error loading organizational profile: {e}")
            org_profile = None
        
        # Create AI prompt for six articles analysis with organizational context
        try:
            prompt = self._build_six_articles_analyst_prompt(articles_data, date, org_profile)
            logger.info("Successfully built six articles prompt")
        except Exception as e:
            logger.error(f"Error building six articles prompt: {e}")
            raise
        
        # Store current articles data FIRST for URI matching in related articles
        self._current_articles_data = articles_data
        logger.info(f"Stored {len(articles_data)} articles for URI matching")
        
        # Use direct LLM for now (TODO: migrate to Auspex after testing org profiles)
        try:
            import litellm
            
            # Create messages for the AI with explicit CEO Daily format enforcement
            system_message = """You are a CEO-focused news analyst. You MUST return articles in the new CEO Daily format.

CRITICAL: Use ONLY these field names in your JSON response:
- title (string)
- source (string) 
- date (string YYYY-MM-DD)
- url (string)
- executive_takeaway (string, max 20 words)
- summary (string)
- strategic_relevance (string)
- time_horizon (string: "Immediate", "Medium", or "Long-term")
- risk_opportunity (string: "risk", "opportunity", or "mixed")
- signal_strength (string: "weak", "moderate", or "strong")
- executive_action (array of strings)
- category (string: "policy", "market", "tech", "workforce", "security", or "society")
- scores (object with relevance, novelty, credibility, representativeness numbers 0-5)

FORBIDDEN: Do NOT use these old field names: why_interesting, devils_advocate, perspectives

Return ONLY a JSON array starting with [ and ending with ]. No other text."""

            messages = [
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt}
            ]
            
            # Get AI response using litellm directly with settings optimized for JSON
            response = await litellm.acompletion(
                model=request.model,
                messages=messages,
                temperature=0.3,  # Lower temperature for more consistent JSON output
                max_tokens=4000,
                # Don't use JSON mode as it requires object format, we need array format
            )
            
            response_text = response.choices[0].message.content
            
            # Parse AI response - now returns array directly
            logger.info(f"=== SIX ARTICLES GENERATION DEBUG ===")
            logger.info(f"Model used: {request.model}")
            logger.info(f"Prompt first 500 chars: {prompt[:500]}")
            logger.info(f"System message: {system_message}")
            logger.info(f"Parsing AI response (length: {len(response_text)})")
            logger.info(f"AI response first 500 chars: {response_text[:500]}")
            logger.info(f"AI response last 200 chars: {response_text[-200:]}")
            logger.info(f"Response contains 'executive_takeaway': {'executive_takeaway' in response_text}")
            logger.info(f"Response contains 'why_interesting': {'why_interesting' in response_text}")
            logger.info(f"=== END DEBUG ===")
            
            articles_data_parsed = self._parse_six_articles_response(response_text)
            
            # If parsing failed (empty array), use fallback
            if not articles_data_parsed:
                logger.warning("JSON parsing returned empty array, using fallback articles")
                logger.debug(f"Failed response text: {response_text}")
                return await self._create_fallback_six_articles(articles_data, date)
            
            # Convert to structured data using new format
            articles = []
            for i, article_data in enumerate(articles_data_parsed):
                try:
                    logger.info(f"Processing article {i+1}/{len(articles_data_parsed)}: {article_data.get('title', 'Untitled')}")
                    article = await self._create_six_article_from_analyst_data(article_data)
                    if article:
                        articles.append(article)
                        logger.info(f"Successfully created article {i+1} with {len(article.get('related_articles', []))} related articles")
                    else:
                        logger.warning(f"Failed to create article {i+1}")
                except Exception as e:
                    logger.error(f"Error processing article {i+1}: {e}")
                    continue
            
            # If no valid articles were created, use fallback
            if not articles:
                logger.info("No valid articles created from parsed data, using fallback articles")
                return await self._create_fallback_six_articles(articles_data, date)
            
            # Return just the articles array for the new format
            return articles
            
        except Exception as e:
            logger.error(f"Error generating six articles report: {e}")
            # Fallback to simple report
            return await self._create_fallback_six_articles(articles_data, date)
    
    async def _generate_six_articles_report_cached(self, articles_data: List[Dict], date: datetime, request: NewsFeedRequest) -> List[Dict]:
        """Generate six articles report with caching and enhanced political analysis"""
        
        # Create cache key based on date and topic only (stable across varying article counts)
        # Added v3 to invalidate cache after CEO Daily format enforcement
        cache_key = f"six_articles_v3_{date.strftime('%Y-%m-%d')}_{request.topic or 'all'}"
        
        # Check database cache first (more persistent)
        try:
            db = get_database_instance()
            cached_result = db.get_article_analysis_cache(
                article_uri=f"six_articles_{cache_key}",
                analysis_type="six_articles",
                model_used=request.model
            )
            if cached_result:
                logger.info(f"Using database cached six articles for {cache_key}")
                import json
                return json.loads(cached_result["content"])
        except Exception as e:
            logger.debug(f"Database cache check failed: {e}")
        
        # Try to get from in-memory cache as fallback
        if hasattr(self, '_six_articles_cache') and cache_key in self._six_articles_cache:
            cache_entry = self._six_articles_cache[cache_key]
            # Check if cache is less than 1 hour old
            if (datetime.now() - cache_entry['timestamp']).seconds < 3600:
                logger.info(f"Using in-memory cached six articles for {cache_key}")
                return cache_entry['data']
        
        # Generate new analysis with enhanced political analysis
        six_articles = await self._generate_six_articles_with_political_analysis(articles_data, date, request)
        
        # Cache the result in database
        try:
            db = get_database_instance()
            import json
            cache_content = json.dumps(six_articles, ensure_ascii=False, indent=2)
            cache_metadata = {
                "date": date.isoformat(),
                "topic": request.topic,
                "article_count": len(articles_data),
                "format_version": "ceo_daily_v3"
            }
            
            success = db.save_article_analysis_cache(
                article_uri=f"six_articles_{cache_key}",
                analysis_type="six_articles",
                content=cache_content,
                model_used=request.model,
                metadata=cache_metadata
            )
            
            if success:
                logger.info(f"Cached six articles in database for {cache_key}")
            else:
                logger.warning(f"Failed to cache six articles in database for {cache_key}")
                
        except Exception as e:
            logger.error(f"Error caching six articles to database: {e}")
        
        # Keep in-memory cache as fallback
        if not hasattr(self, '_six_articles_cache'):
            self._six_articles_cache = {}
        
        self._six_articles_cache[cache_key] = {
            'data': six_articles,
            'timestamp': datetime.now()
        }
        
        # Keep cache size reasonable (max 10 entries)
        if len(self._six_articles_cache) > 10:
            oldest_key = min(self._six_articles_cache.keys(), 
                           key=lambda k: self._six_articles_cache[k]['timestamp'])
            del self._six_articles_cache[oldest_key]
        
        return six_articles
    
    async def _generate_six_articles_with_political_analysis(self, articles_data: List[Dict], date: datetime, request: NewsFeedRequest) -> List[Dict]:
        """Generate six articles with enhanced political analysis based on related articles"""
        
        # Group articles by news source and bias to find related articles with political leanings
        articles_by_source = {}
        articles_with_bias = []
        
        for article in articles_data:
            source = article.get('news_source', 'Unknown')
            bias = article.get('bias')
            
            if source not in articles_by_source:
                articles_by_source[source] = []
            articles_by_source[source].append(article)
            
            if bias and bias.lower() in ['left', 'left-center', 'right', 'right-center', 'mixed']:
                articles_with_bias.append(article)
        
        # Get organizational profile if specified
        org_profile = await self._get_organizational_profile(request.profile_id)
        
        # Enhanced prompt that considers related articles and political leanings
        prompt = self._build_enhanced_six_articles_analyst_prompt(articles_data, articles_with_bias, articles_by_source, date, org_profile)
        
        try:
            # Use direct LLM for now (TODO: migrate to Auspex after testing org profiles)
            import litellm
            
            # Generate AI analysis with explicit system message for new format
            system_message = """You are a CEO-focused news analyst. You MUST return articles in the new CEO Daily format.

CRITICAL: Use ONLY these field names in your JSON response:
- title (string)
- source (string) 
- date (string YYYY-MM-DD)
- url (string)
- executive_takeaway (string, max 20 words)
- summary (string)
- strategic_relevance (string)
- time_horizon (string: "Immediate", "Medium", or "Long-term")
- risk_opportunity (string: "risk", "opportunity", or "mixed")
- signal_strength (string: "weak", "moderate", or "strong")
- executive_action (array of strings)
- category (string: "policy", "market", "tech", "workforce", "security", or "society")
- scores (object with relevance, novelty, credibility, representativeness numbers 0-5)

FORBIDDEN: Do NOT use these old field names: why_interesting, devils_advocate, perspectives

Return ONLY a JSON array starting with [ and ending with ]. No other text."""
            
            response = await litellm.acompletion(
                model=request.model,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=4000
            )
            
            content = response.choices[0].message.content.strip()
            logger.info(f"=== ENHANCED SIX ARTICLES GENERATION DEBUG ===")
            logger.info(f"Model used: {request.model}")
            logger.info(f"Enhanced prompt first 500 chars: {prompt[:500]}")
            logger.info(f"System message: {system_message}")
            logger.info(f"AI response for enhanced six articles (length: {len(content)})")
            logger.info(f"AI response first 500 chars: {content[:500]}")
            logger.info(f"Response contains 'executive_takeaway': {'executive_takeaway' in content}")
            logger.info(f"Response contains 'why_interesting': {'why_interesting' in content}")
            logger.info(f"=== END ENHANCED DEBUG ===")
            
            # Parse response
            articles = self._parse_six_articles_response(content)
            
            # If parsing failed (empty array), use fallback
            if not articles:
                logger.info("JSON parsing returned empty array in cached version, using fallback articles")
                return await self._create_fallback_six_articles(articles_data, date)
            
            # Store current articles data for URI matching in related articles
            self._current_articles_data = articles_data
            
            # Convert to the expected format
            result_articles = []
            for article_data in articles:
                article = await self._create_six_article_from_analyst_data(article_data)
                if article:
                    result_articles.append(article)
            
            # If no valid articles were created, use fallback
            if not result_articles:
                logger.info("No valid articles created from parsed data in cached version, using fallback articles")
                return await self._create_fallback_six_articles(articles_data, date)
            
            return result_articles
            
        except Exception as e:
            logger.error(f"Error generating enhanced six articles report: {e}")
            # Fallback to original method
            return await self._generate_six_articles_report(articles_data, date, request)
    
    def _build_overview_prompt(self, articles_data: List[Dict], date: datetime) -> str:
        """Build AI prompt for daily overview generation"""
        
        # Prepare article summaries for AI
        articles_summary = self._prepare_articles_for_prompt(articles_data, max_articles=20)
        
        return f"""
Create a Techmeme-style daily news overview for {date.strftime('%B %d, %Y')}.

ARTICLES DATA:
{articles_summary}

REQUIREMENTS:
- Generate 3-5 top stories in Techmeme style (concise, impactful headlines)
- Each story should have a compelling headline and 2-3 sentence summary
- Focus on the most significant, interesting, or trending stories
- Include brief topic descriptions that explain why each story matters
- Maintain journalistic objectivity while highlighting key insights

OUTPUT FORMAT (JSON):
{{
    "title": "Daily News Overview - {date.strftime('%B %d, %Y')}",
    "top_stories": [
        {{
            "headline": "Compelling headline that captures the essence",
            "summary": "2-3 sentence summary of the key points and implications",
            "primary_article_uri": "URI of the main article",
            "topic_description": "Why this story matters and its broader context",
            "related_article_uris": ["URI1", "URI2"]
        }}
    ]
}}

Focus on stories with:
- High impact or significance
- Broad interest or unique insights  
- Clear relevance to current events
- Good source credibility

Return ONLY the JSON response."""
    
    def _build_six_articles_analyst_prompt(self, articles_data: List[Dict], date: datetime, org_profile: Optional[Dict] = None) -> str:
        """Build AI prompt for six articles detailed analysis with organizational context"""
        
        # Prepare all articles for comprehensive analysis
        articles_summary = self._prepare_articles_for_prompt(articles_data, max_articles=50)
        
        # Build audience profile from organizational data or use defaults
        if org_profile:
            audience_profile = self._build_audience_profile_from_org(org_profile)
        else:
            audience_profile = """## Audience Defaults
- **Risk appetite**: Moderate (innovation with caution)
- **Priorities**: Regulation, enterprise adoption, scaling limits, market dynamics, security/safety, workforce impact
- **Time**: Will only read 6 items/day — each must add distinct value"""
        
        return f"""🎯 CEO Daily Top-6 AI Articles — Analyst Prompt

You are an analyst selecting the 6 most important articles published in the last 24 hours for executives (CEOs and senior decision-makers) interested in AI's strategic, technical, and societal impacts.

{audience_profile}

## Selection Rules
Choose exactly 6 articles from the provided corpus (news, filings, research, regulator posts). Each must score high on at least two:
1) Strategic relevance, 2) Novelty, 3) Credibility, 4) Representativeness (captures a bigger debate/trend).

- **Diversity**: Cover ≥3 domains (e.g., policy, business/market, tech/R&D, workforce/society).
- **No redundancy**: Don't select multiple pieces on the same event unless they provide non-overlapping value (e.g., a filing + a data-driven analysis).
- **Recency**: Past 24 hours only.

## Article Corpus
{articles_summary}

## EXAMPLE OUTPUT (you must follow this exact structure):
[
  {{
    "title": "EU AI Act enforcement begins with first company fines (Reuters, 2025-09-15, Sarah Johnson)",
    "source": "Reuters",
    "date": "2025-09-15",
    "url": "https://reuters.com/technology/eu-ai-act-enforcement-begins",
    "executive_takeaway": "EU begins AI Act enforcement with €50M fines, affecting global AI deployment timelines.",
    "summary": "European regulators issued first AI Act penalties totaling €50 million to three companies for non-compliance with transparency requirements. The enforcement covers foundation models and high-risk AI systems deployed after August 2025.",
    "strategic_relevance": "Sets precedent for global AI regulation enforcement, requiring immediate compliance review for any EU operations. Could influence similar regulatory approaches in other jurisdictions and affect AI deployment strategies worldwide.",
    "time_horizon": "Immediate",
    "risk_opportunity": "risk",
    "signal_strength": "strong",
    "executive_action": [
      "Review EU AI Act compliance for all AI systems in European markets",
      "Assess potential regulatory risk exposure in other jurisdictions"
    ],
    "category": "policy",
    "scores": {{"relevance": 5, "novelty": 4, "credibility": 5, "representativeness": 5}}
  }}
]

## What to Output per Article

**title** — Full headline with source and date: "Headline (Source, YYYY-MM-DD, Author)"
**source** — Publisher name (e.g., "Reuters")
**date** — YYYY-MM-DD
**url** — Plain canonical URL (no markdown, no tracking params)
**executive_takeaway** — 1 sentence: the critical gist for a CEO in ~15 words
**summary** — 2–3 sentences of core facts/developments
**strategic_relevance** — 1 short paragraph on why this matters (policy, competition, tech, workforce, risk posture)
**time_horizon** — Immediate (0–6m) | Medium (6–18m) | Long-term (18m+)
**risk_opportunity** — "risk" | "opportunity" | "mixed" + brief rationale
**signal_strength** — "weak" | "moderate" | "strong" with a short justification
**executive_action** — Array of 1–2 bullets: what to watch, decide, or delegate now
**category** — "policy" | "market" | "tech" | "workforce" | "security" | "society"
**scores** — Optional scoring object: {{"relevance": 0-5, "novelty": 0-5, "credibility": 0-5, "representativeness": 0-5}}

## REQUIRED JSON OUTPUT FORMAT
You MUST return exactly this JSON structure with these exact field names:

[
  {{
    "title": "Full headline (Source, YYYY-MM-DD, Author if available)",
    "source": "Publisher name only",
    "date": "YYYY-MM-DD",
    "url": "Clean URL without tracking parameters",
    "executive_takeaway": "One sentence under 20 words with critical CEO insight",
    "summary": "2-3 sentences of core facts and developments",
    "strategic_relevance": "One paragraph on why this matters for executive decisions",
    "time_horizon": "Immediate",
    "risk_opportunity": "risk",
    "signal_strength": "strong",
    "executive_action": [
      "First actionable item for executives",
      "Second actionable item if relevant"
    ],
    "category": "policy",
    "scores": {{"relevance": 5, "novelty": 4, "credibility": 5, "representativeness": 4}}
  }}
]

MANDATORY FIELD REQUIREMENTS:
- title: Must include source and date in parentheses
- executive_takeaway: Must be under 20 words, one sentence
- time_horizon: Must be exactly "Immediate", "Medium", or "Long-term"
- risk_opportunity: Must be exactly "risk", "opportunity", or "mixed"
- signal_strength: Must be exactly "weak", "moderate", or "strong"
- category: Must be exactly one of "policy", "market", "tech", "workforce", "security", "society"
- executive_action: Must be array of 1-2 short action items

## Style & Constraints
- Be concise but analytical; each field <100 words (takeaway ≤ 20 words).
- Prefer primary reporting and regulator/court/filing documents over PR or opinion.
- No duplicates, no filler, no hype words.
- Use plain URLs (LinkedIn-safe). Strip tracking (?utm_…, &ref=…, fbclid, etc.).
- If multiple sources cover the same development, pick the most authoritative or the one with new data.

CRITICAL OUTPUT REQUIREMENTS:
- Your response MUST start with [ and end with ]
- Return ONLY a valid JSON array - NO other text
- No markdown formatting (no ```json blocks)
- No explanatory text, comments, or notes
- Ensure all strings are properly escaped with \\"
- Do not include any text like "Here are the six articles" or similar
- Your entire response should be parseable by JSON.parse()

DO NOT USE THESE OLD FIELD NAMES:
- why_interesting (use strategic_relevance instead)
- devils_advocate (remove this entirely)
- perspectives (remove this entirely)

ONLY USE THE NEW FIELD NAMES SPECIFIED ABOVE:
executive_takeaway, strategic_relevance, time_horizon, risk_opportunity, signal_strength, executive_action, category, scores

START YOUR RESPONSE WITH [ AND END WITH ] - NOTHING ELSE."""

    def _build_audience_profile_from_org(self, org_profile: Dict) -> str:
        """Build audience profile section from organizational profile data"""
        
        # Map risk tolerance
        risk_mapping = {
            'low': 'Conservative (prioritizes stability and proven solutions)',
            'medium': 'Moderate (balanced between innovation and caution)',
            'high': 'Aggressive (embraces high-risk, high-reward opportunities)'
        }
        
        # Map innovation appetite
        innovation_mapping = {
            'conservative': 'Conservative (adopts proven technologies)',
            'moderate': 'Moderate (selective early adoption)',
            'aggressive': 'Aggressive (cutting-edge technology adoption)'
        }
        
        # Build strategic interests from key concerns and priorities
        strategic_interests = []
        strategic_interests.extend(org_profile.get('key_concerns', []))
        strategic_interests.extend(org_profile.get('strategic_priorities', []))
        
        # Add default AI interests if none specified
        if not strategic_interests:
            strategic_interests = ['AI regulation', 'enterprise adoption', 'market shifts', 'workforce impact', 'security & safety']
        
        profile_text = f"""## Audience Profile ({org_profile.get('name', 'Organization')})
- **Organization**: {org_profile.get('name', 'Unknown')} ({org_profile.get('organization_type', 'General')})
- **Industry**: {org_profile.get('industry', 'General')}
- **Region**: {org_profile.get('region', 'Global')}
- **Risk Appetite**: {risk_mapping.get(org_profile.get('risk_tolerance', 'medium'), 'Moderate')}
- **Innovation Appetite**: {innovation_mapping.get(org_profile.get('innovation_appetite', 'moderate'), 'Moderate')}
- **Strategic Interests**: {', '.join(strategic_interests)}
- **Key Stakeholders**: {', '.join(org_profile.get('stakeholder_focus', ['General stakeholders']))}
- **Decision Making**: {org_profile.get('decision_making_style', 'Collaborative')} approach"""
        
        # Add custom context if available
        if org_profile.get('custom_context'):
            profile_text += f"\n- **Additional Context**: {org_profile.get('custom_context')}"
        
        # Add competitive and regulatory context
        if org_profile.get('competitive_landscape'):
            profile_text += f"\n- **Competitive Focus**: {', '.join(org_profile.get('competitive_landscape'))}"
        
        if org_profile.get('regulatory_environment'):
            profile_text += f"\n- **Regulatory Concerns**: {', '.join(org_profile.get('regulatory_environment'))}"
        
        return profile_text

    def _build_enhanced_six_articles_analyst_prompt(self, articles_data: List[Dict], articles_with_bias: List[Dict], articles_by_source: Dict, date: datetime, org_profile: Optional[Dict] = None) -> str:
        """Build enhanced AI prompt that considers related articles and political leanings"""
        
        # Prepare all articles for analysis
        articles_summary = self._prepare_articles_for_prompt(articles_data, max_articles=50)
        
        # Prepare bias analysis context
        bias_context = ""
        if articles_with_bias:
            bias_breakdown = {}
            for article in articles_with_bias:
                bias = article.get('bias', 'Unknown')
                if bias not in bias_breakdown:
                    bias_breakdown[bias] = []
                bias_breakdown[bias].append(f"- {article.get('title', 'Untitled')} ({article.get('news_source', 'Unknown')})")
            
            bias_context = "\n## Political Bias Context Available\n"
            for bias, articles_list in bias_breakdown.items():
                bias_context += f"\n**{bias} Sources:**\n" + "\n".join(articles_list[:3]) + "\n"
        
        # Prepare source grouping context
        source_context = ""
        if len(articles_by_source) > 1:
            source_context = "\n## Source Distribution\n"
            for source, source_articles in articles_by_source.items():
                if len(source_articles) > 1:
                    source_context += f"- {source}: {len(source_articles)} articles\n"
        
        # Build audience profile from organizational data or use defaults
        if org_profile:
            audience_profile = self._build_audience_profile_from_org(org_profile)
        else:
            audience_profile = """## Audience Defaults
- **Risk appetite**: Moderate (innovation with caution)
- **Priorities**: Regulation, enterprise adoption, scaling limits, market dynamics, security/safety, workforce impact
- **Time**: Will only read 6 items/day — each must add distinct value"""
        
        return f"""🎯 CEO Daily Top-6 AI Articles — Analyst Prompt

You are an analyst selecting the 6 most important articles published in the last 24 hours for executives (CEOs and senior decision-makers) interested in AI's strategic, technical, and societal impacts.

{audience_profile}

## Selection Rules
Choose exactly 6 articles from the provided corpus (news, filings, research, regulator posts). Each must score high on at least two:
1) Strategic relevance, 2) Novelty, 3) Credibility, 4) Representativeness (captures a bigger debate/trend).

- **Diversity**: Cover ≥3 domains (e.g., policy, business/market, tech/R&D, workforce/society).
- **No redundancy**: Don't select multiple pieces on the same event unless they provide non-overlapping value (e.g., a filing + a data-driven analysis).
- **Recency**: Past 24 hours only.

## Article Corpus
{articles_summary}

## EXAMPLE OUTPUT (you must follow this exact structure):
[
  {{
    "title": "EU AI Act enforcement begins with first company fines (Reuters, 2025-09-15, Sarah Johnson)",
    "source": "Reuters",
    "date": "2025-09-15",
    "url": "https://reuters.com/technology/eu-ai-act-enforcement-begins",
    "executive_takeaway": "EU begins AI Act enforcement with €50M fines, affecting global AI deployment timelines.",
    "summary": "European regulators issued first AI Act penalties totaling €50 million to three companies for non-compliance with transparency requirements. The enforcement covers foundation models and high-risk AI systems deployed after August 2025.",
    "strategic_relevance": "Sets precedent for global AI regulation enforcement, requiring immediate compliance review for any EU operations. Could influence similar regulatory approaches in other jurisdictions and affect AI deployment strategies worldwide.",
    "time_horizon": "Immediate",
    "risk_opportunity": "risk",
    "signal_strength": "strong",
    "executive_action": [
      "Review EU AI Act compliance for all AI systems in European markets",
      "Assess potential regulatory risk exposure in other jurisdictions"
    ],
    "category": "policy",
    "scores": {{"relevance": 5, "novelty": 4, "credibility": 5, "representativeness": 5}}
  }}
]

## What to Output per Article

**title** — Full headline with source and date: "Headline (Source, YYYY-MM-DD, Author)"
**source** — Publisher name (e.g., "Reuters")
**date** — YYYY-MM-DD
**url** — Plain canonical URL (no markdown, no tracking params)
**executive_takeaway** — 1 sentence: the critical gist for a CEO in ~15 words
**summary** — 2–3 sentences of core facts/developments
**strategic_relevance** — 1 short paragraph on why this matters (policy, competition, tech, workforce, risk posture)
**time_horizon** — Immediate (0–6m) | Medium (6–18m) | Long-term (18m+)
**risk_opportunity** — "risk" | "opportunity" | "mixed" + brief rationale
**signal_strength** — "weak" | "moderate" | "strong" with a short justification
**executive_action** — Array of 1–2 bullets: what to watch, decide, or delegate now
**category** — "policy" | "market" | "tech" | "workforce" | "security" | "society"
**scores** — Optional scoring object: {{"relevance": 0-5, "novelty": 0-5, "credibility": 0-5, "representativeness": 0-5}}

## REQUIRED JSON OUTPUT FORMAT
You MUST return exactly this JSON structure with these exact field names:

[
  {{
    "title": "Full headline (Source, YYYY-MM-DD, Author if available)",
    "source": "Publisher name only",
    "date": "YYYY-MM-DD",
    "url": "Clean URL without tracking parameters",
    "executive_takeaway": "One sentence under 20 words with critical CEO insight",
    "summary": "2-3 sentences of core facts and developments",
    "strategic_relevance": "One paragraph on why this matters for executive decisions",
    "time_horizon": "Immediate",
    "risk_opportunity": "risk",
    "signal_strength": "strong",
    "executive_action": [
      "First actionable item for executives",
      "Second actionable item if relevant"
    ],
    "category": "policy",
    "scores": {{"relevance": 5, "novelty": 4, "credibility": 5, "representativeness": 4}}
  }}
]

MANDATORY FIELD REQUIREMENTS:
- title: Must include source and date in parentheses
- executive_takeaway: Must be under 20 words, one sentence
- time_horizon: Must be exactly "Immediate", "Medium", or "Long-term"
- risk_opportunity: Must be exactly "risk", "opportunity", or "mixed"
- signal_strength: Must be exactly "weak", "moderate", or "strong"
- category: Must be exactly one of "policy", "market", "tech", "workforce", "security", "society"
- executive_action: Must be array of 1-2 short action items

## Style & Constraints
- Be concise but analytical; each field <100 words (takeaway ≤ 20 words).
- Prefer primary reporting and regulator/court/filing documents over PR or opinion.
- No duplicates, no filler, no hype words.
- Use plain URLs (LinkedIn-safe). Strip tracking (?utm_…, &ref=…, fbclid, etc.).
- If multiple sources cover the same development, pick the most authoritative or the one with new data.

CRITICAL OUTPUT REQUIREMENTS:
- Your response MUST start with [ and end with ]
- Return ONLY a valid JSON array - NO other text
- No markdown formatting (no ```json blocks)
- No explanatory text, comments, or notes
- Ensure all strings are properly escaped with \\"
- Do not include any text like "Here are the six articles" or similar
- Your entire response should be parseable by JSON.parse()

DO NOT USE THESE OLD FIELD NAMES:
- why_interesting (use strategic_relevance instead)
- devils_advocate (remove this entirely)
- perspectives (remove this entirely)

ONLY USE THE NEW FIELD NAMES SPECIFIED ABOVE:
executive_takeaway, strategic_relevance, time_horizon, risk_opportunity, signal_strength, executive_action, category, scores

START YOUR RESPONSE WITH [ AND END WITH ] - NOTHING ELSE."""

    def _prepare_articles_for_prompt(self, articles_data: List[Dict], max_articles: int = 50) -> str:
        """Prepare articles data for AI prompt"""
        
        articles_text = []
        for i, article in enumerate(articles_data[:max_articles]):
            bias_info = f"Bias: {article.get('bias', 'Unknown')}" if article.get('bias') else ""
            factuality_info = f"Factuality: {article.get('factual_reporting', 'Unknown')}" if article.get('factual_reporting') else ""
            
            article_text = f"""
Article {i+1}:
URI: {article.get('uri', '')}
Title: {article.get('title', '')}
Source: {article.get('news_source', '')} {bias_info} {factuality_info}
Published: {article.get('publication_date', '')}
Category: {article.get('category', '')}
Summary: {article.get('summary', '')[:300]}...
Sentiment: {article.get('sentiment', '')}
Time to Impact: {article.get('time_to_impact', '')}
Tags: {article.get('tags', '')}
"""
            articles_text.append(article_text.strip())
        
        return "\n\n".join(articles_text)
    
    def _parse_overview_response(self, response_text: str) -> Dict[str, Any]:
        """Parse AI response for overview"""
        try:
            # Extract JSON from response
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing overview JSON: {e}")
        
        # Fallback structure
        return {
            "title": f"Daily News Overview",
            "top_stories": []
        }
    
    def _parse_six_articles_response(self, response_text: str) -> List[Dict[str, Any]]:
        """Parse AI response for six articles report with robust error handling"""
        try:
            # Clean the response text
            response_text = response_text.strip()
            logger.debug(f"Parsing response text of length: {len(response_text)}")
            
            # Try multiple parsing strategies
            import re
            
            # Strategy 0: Check if response starts with explanatory text and remove it
            if not response_text.startswith('[') and not response_text.startswith('{'):
                # Look for the start of JSON after any explanatory text
                json_start_patterns = [
                    r'(?:Here is|Here are|Below is|Below are).*?(\[.*\])',
                    r'(?:The six articles|Six articles|Articles).*?(\[.*\])',
                    r'^.*?(\[.*\])(?:\s*$|$)',  # Any text followed by JSON array
                ]
                
                for pattern in json_start_patterns:
                    match = re.search(pattern, response_text, re.DOTALL | re.IGNORECASE)
                    if match:
                        potential_json = match.group(1)
                        logger.debug(f"Found potential JSON after explanatory text: {potential_json[:100]}...")
                        try:
                            result = json.loads(potential_json)
                            if isinstance(result, list):
                                logger.info(f"Successfully parsed JSON after removing explanatory text: {len(result)} articles")
                                return result
                        except json.JSONDecodeError:
                            continue
            
            # Strategy 1: Look for JSON array in code blocks
            json_match = re.search(r'```json\s*(\[.*?\])\s*```', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
                logger.debug("Found JSON in code block, attempting to parse")
                try:
                    result = json.loads(json_str)
                    logger.info(f"Successfully parsed JSON from code block: {len(result)} articles")
                    return result
                except json.JSONDecodeError as e:
                    logger.debug(f"Code block JSON parse failed: {e}")
            
            # Strategy 2: Look for JSON object with articles array
            json_match = re.search(r'(\{.*?"articles"\s*:\s*\[.*?\].*?\})', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
                logger.debug("Found JSON object with articles array, attempting to parse")
                try:
                    result = json.loads(json_str)
                    if 'articles' in result and isinstance(result['articles'], list):
                        logger.info(f"Successfully parsed JSON object with articles array: {len(result['articles'])} articles")
                        return result['articles']
                except json.JSONDecodeError as e:
                    logger.debug(f"JSON object parse failed: {e}")
            
            # Strategy 3: Look for plain JSON array
            json_match = re.search(r'(\[.*?\])', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
                logger.debug("Found JSON array, attempting to parse")
                try:
                    result = json.loads(json_str)
                    logger.info(f"Successfully parsed plain JSON array: {len(result)} articles")
                    return result
                except json.JSONDecodeError as e:
                    logger.debug(f"Plain JSON parse failed: {e}")
            
            # Strategy 4: Extract JSON array from response (original method with better cleaning)
            json_start = response_text.find('[')
            json_end = response_text.rfind(']') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                logger.debug("Found JSON boundaries, cleaning and parsing")
                logger.debug(f"Raw JSON string first 100 chars: {json_str[:100]}")
                
                # More aggressive cleaning
                json_str = json_str.replace('\n', ' ').replace('\t', ' ').replace('\r', ' ')
                # Remove trailing commas before closing brackets/braces
                json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
                # Fix common quote issues
                json_str = re.sub(r'(["\'])\s*\n\s*(["\'])', r'\1 \2', json_str)
                # Remove any non-printable characters
                json_str = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', json_str)
                # Fix multiple spaces
                json_str = re.sub(r'\s+', ' ', json_str)
                
                logger.debug(f"Cleaned JSON string first 100 chars: {json_str[:100]}")
                
                try:
                    result = json.loads(json_str)
                    logger.info(f"Successfully parsed cleaned JSON: {len(result)} articles")
                    return result
                except json.JSONDecodeError as e:
                    logger.warning(f"Cleaned JSON parse failed at position {e.pos}: {e}")
                    logger.warning(f"Failed JSON around error position: {json_str[max(0, e.pos-50):e.pos+50]}")
                    logger.debug(f"Full failed JSON string: {json_str}")
            
            # Strategy 5: Try to extract individual article objects
            logger.debug("Attempting to extract individual article objects")
            article_pattern = r'\{\s*"title"[^}]*\}'
            article_matches = re.findall(article_pattern, response_text, re.DOTALL)
            if article_matches:
                logger.debug(f"Found {len(article_matches)} potential article objects")
                articles = []
                for match in article_matches:
                    try:
                        article = json.loads(match)
                        articles.append(article)
                    except:
                        continue
                if articles:
                    logger.info(f"Successfully extracted {len(articles)} articles from individual objects")
                    return articles
                
        except Exception as e:
            logger.warning(f"Error parsing six articles JSON, using fallback: {e}")
            logger.debug(f"Response text (first 1000 chars): {response_text[:1000]}")
        
        # Fallback structure - return empty array
        logger.info("Using empty array fallback for six articles parsing")
        return []
    
    async def _create_six_article_from_analyst_data(self, article_data: Dict[str, Any]) -> Optional[Dict]:
        """Create article object from new analyst format with related articles"""
        try:
            # Find the original article URI to get related articles
            article_uri = article_data.get('uri', '')
            if not article_uri:
                # Try to match by title if no URI provided
                title = article_data.get('title', '')
                source = article_data.get('source', '')
                logger.debug(f"No URI in AI response, trying to match by title: {title}")
                
                for article in getattr(self, '_current_articles_data', []):
                    # Try exact title match first
                    if article.get('title') == title:
                        article_uri = article.get('uri', '')
                        logger.debug(f"Found exact title match: {article_uri}")
                        break
                    # Try partial title match if exact fails
                    elif title and article.get('title') and title.lower() in article.get('title', '').lower():
                        article_uri = article.get('uri', '')
                        logger.debug(f"Found partial title match: {article_uri}")
                        break
                    # Try source + partial title match
                    elif (source and article.get('news_source') == source and 
                          title and article.get('title') and 
                          any(word in article.get('title', '').lower() for word in title.lower().split() if len(word) > 3)):
                        article_uri = article.get('uri', '')
                        logger.debug(f"Found source + keyword match: {article_uri}")
                        break
                
                if not article_uri:
                    logger.warning(f"Could not find URI for article: {title} from {source}")
                    # Use the first available article as fallback
                    if getattr(self, '_current_articles_data', []):
                        article_uri = self._current_articles_data[0].get('uri', '')
                        logger.debug(f"Using fallback URI: {article_uri}")
            
            # Find related articles if we have a URI
            related_articles = []
            if article_uri:
                try:
                    logger.info(f"Attempting to find related articles for: {article_uri}")
                    related_articles = await self._find_related_articles(article_uri, top_k=3)
                    logger.info(f"Found {len(related_articles)} related articles")
                except Exception as e:
                    logger.error(f"Failed to find related articles: {e}")
                    related_articles = []  # Continue without related articles
            
            # Find the original article data to get bias/factuality info
            original_metadata = None
            if article_uri:
                for article in getattr(self, '_current_articles_data', []):
                    if article.get('uri') == article_uri:
                        original_metadata = article
                        break
            
            return {
                # Core CEO Daily fields
                'title': article_data.get('title', 'Untitled'),
                'source': article_data.get('source', 'Unknown Source'),
                'date': article_data.get('date', ''),
                'url': (lambda raw: (lambda parsed: urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', '', '')))(urlparse(raw)) if raw else '')(article_data.get('url') or article_uri or ''),
                'executive_takeaway': article_data.get('executive_takeaway', ''),
                'summary': article_data.get('summary', ''),
                'strategic_relevance': article_data.get('strategic_relevance', ''),
                'time_horizon': article_data.get('time_horizon', ''),
                'risk_opportunity': article_data.get('risk_opportunity', ''),
                'signal_strength': article_data.get('signal_strength', ''),
                'executive_action': (article_data.get('executive_action') if isinstance(article_data.get('executive_action'), list) else ([article_data.get('executive_action')] if isinstance(article_data.get('executive_action'), str) and article_data.get('executive_action') else [])),
                'category': article_data.get('category', ''),
                'scores': article_data.get('scores'),

                # Related articles and metadata
                'related_articles': related_articles,
                # Add bias and factuality from original article metadata
                'bias': original_metadata.get('bias') if original_metadata else None,
                'factual_reporting': original_metadata.get('factual_reporting') if original_metadata else None,
                'uri': article_uri,  # Include URI for reference

                # Legacy fields (kept for compatibility; UI now ignores them)
                'why_interesting': article_data.get('why_interesting', ''),
                'devils_advocate': article_data.get('devils_advocate', ''),
                'perspectives': article_data.get('perspectives', {}) or {}
            }
        except Exception as e:
            logger.error(f"Error creating article from analyst data: {e}")
            return None
    
    async def _create_top_story(self, story_data: Dict[str, Any], articles_data: List[Dict]) -> Optional[TopStory]:
        """Create TopStory object from AI-generated data and article database"""
        
        primary_uri = story_data.get('primary_article_uri', '')
        if not primary_uri:
            return None
        
        # Find primary article in data
        primary_article_data = None
        for article in articles_data:
            if article.get('uri') == primary_uri:
                primary_article_data = article
                break
        
        if not primary_article_data:
            logger.warning(f"Primary article not found: {primary_uri}")
            return None
        
        # Create primary article object
        primary_article = self._create_news_article(primary_article_data)
        
        # Find related articles
        related_articles = []
        related_uris = story_data.get('related_article_uris', [])
        for uri in related_uris:
            for article in articles_data:
                if article.get('uri') == uri:
                    related_article = RelatedArticle(
                        title=article.get('title', ''),
                        source=article.get('news_source', ''),
                        url=article.get('uri'),
                        bias=self._map_bias(article.get('bias')),
                        summary=article.get('summary', '')[:200] + "..." if len(article.get('summary', '')) > 200 else article.get('summary', '')
                    )
                    related_articles.append(related_article)
                    break
        
        # Extract bias analysis from story data
        bias_analysis = story_data.get('bias_analysis', {})
        perspective_breakdown = story_data.get('perspective_breakdown', {})
        
        return TopStory(
            headline=story_data.get('headline', ''),
            summary=story_data.get('summary', ''),
            primary_article=primary_article,
            related_articles=related_articles,
            topic_description=story_data.get('topic_description', ''),
            bias_analysis=bias_analysis,
            factuality_assessment=bias_analysis.get('factuality_assessment', ''),
            perspective_breakdown=perspective_breakdown
        )
    
    def _create_news_article(self, article_data: Dict) -> NewsArticle:
        """Create NewsArticle object from database data"""
        
        source = ArticleSource(
            name=article_data.get('news_source', ''),
            bias=self._map_bias(article_data.get('bias')),
            factuality=self._map_factuality(article_data.get('factual_reporting')),
            credibility_rating=article_data.get('mbfc_credibility_rating'),
            country=article_data.get('bias_country')
        )
        
        # Parse publication date
        pub_date = None
        if article_data.get('publication_date'):
            try:
                pub_date = datetime.fromisoformat(article_data['publication_date'].replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                pass
        
        # Parse tags
        tags = []
        if article_data.get('tags'):
            tags = [tag.strip() for tag in article_data['tags'].split(',') if tag.strip()]
        
        return NewsArticle(
            uri=article_data.get('uri', ''),
            title=article_data.get('title', ''),
            summary=article_data.get('summary', ''),
            url=article_data.get('uri'),
            publication_date=pub_date,
            source=source,
            sentiment=article_data.get('sentiment'),
            category=article_data.get('category'),
            time_to_impact=article_data.get('time_to_impact'),
            tags=tags
        )
    
    def _map_bias(self, bias_str: Optional[str]) -> Optional[BiasRating]:
        """Map bias string to BiasRating enum"""
        if not bias_str:
            return None
        
        bias_mapping = {
            'left': BiasRating.LEFT,
            'left-center': BiasRating.LEFT_CENTER,
            'center': BiasRating.CENTER,
            'right-center': BiasRating.RIGHT_CENTER,
            'right': BiasRating.RIGHT,
            'mixed': BiasRating.MIXED
        }
        
        return bias_mapping.get(bias_str.lower())
    
    def _map_factuality(self, factuality_str: Optional[str]) -> Optional[FactualityRating]:
        """Map factuality string to FactualityRating enum"""
        if not factuality_str:
            return None
        
        factuality_mapping = {
            'very high': FactualityRating.VERY_HIGH,
            'high': FactualityRating.HIGH,
            'mostly factual': FactualityRating.MOSTLY_FACTUAL,
            'mixed': FactualityRating.MIXED,
            'low': FactualityRating.LOW,
            'very low': FactualityRating.VERY_LOW
        }
        
        return factuality_mapping.get(factuality_str.lower())
    
    def _calculate_bias_distribution(self, articles_data: List[Dict]) -> Dict[str, int]:
        """Calculate bias distribution from articles"""
        bias_counts = {}
        for article in articles_data:
            bias = article.get('bias') or 'unknown'  # Handle None values
            bias_counts[bias] = bias_counts.get(bias, 0) + 1
        return bias_counts
    
    def _calculate_factuality_distribution(self, articles_data: List[Dict]) -> Dict[str, int]:
        """Calculate factuality distribution from articles"""
        factuality_counts = {}
        for article in articles_data:
            factuality = article.get('factual_reporting') or 'unknown'  # Handle None values
            factuality_counts[factuality] = factuality_counts.get(factuality, 0) + 1
        return factuality_counts


    def _create_fallback_overview(self, articles_data: List[Dict], date: datetime) -> DailyOverview:
        """Create a simple fallback overview when AI generation fails"""
        
        # Create simple top stories from the most recent articles
        top_stories = []
        for i, article in enumerate(articles_data[:5]):  # Take top 5 articles
            try:
                # Create basic story structure
                primary_article = NewsArticle(
                    uri=article.get('uri', ''),
                    title=article.get('title', 'Unknown Title'),
                    summary=article.get('summary', 'No summary available'),
                    url=article.get('uri', ''),
                    publication_date=datetime.fromisoformat(article.get('publication_date', datetime.now().isoformat())),
                    source=ArticleSource(
                        name=article.get('news_source', 'Unknown Source'),
                        bias=self._map_bias(article.get('bias')),
                        factuality=self._map_factuality(article.get('factual_reporting'))
                    ),
                    sentiment=article.get('sentiment'),
                    category=article.get('category'),
                    time_to_impact=article.get('time_to_impact')
                )
                
                top_story = TopStory(
                    headline=article.get('title', 'Unknown Title'),
                    summary=article.get('summary', 'No summary available')[:200] + "..." if len(article.get('summary', '')) > 200 else article.get('summary', ''),
                    primary_article=primary_article,
                    related_articles=[],
                    topic_description=f"Story #{i+1} from {article.get('news_source', 'Unknown Source')}",
                    factuality_assessment=f"Factuality: {article.get('factual_reporting', 'Unknown')}"
                )
                
                top_stories.append(top_story)
                
            except Exception as e:
                logger.warning(f"Error creating fallback story for article {i}: {e}")
                continue
        
        return DailyOverview(
            title=f"Daily News Overview - {date.strftime('%B %d, %Y')}",
            date=date,
            generated_at=datetime.now(),
            top_stories=top_stories,
            total_articles_analyzed=len(articles_data),
            summary="Fallback overview generated due to AI processing error."
        )
    
    async def _create_fallback_six_articles(self, articles_data: List[Dict], date: datetime) -> List[Dict]:
        """Create a simple fallback six articles report when AI generation fails"""
        
        # Create simple articles in the new format
        articles = []
        for i, article_data in enumerate(articles_data[:6]):  # Take top 6 articles
            try:
                # Find related articles for this article
                related_articles = []
                article_uri = article_data.get('uri', '')
                
                # Debug the URI matching issue
                logger.info(f"Fallback article {i+1} URI: {article_uri}")
                logger.info(f"Available articles in _current_articles_data: {len(getattr(self, '_current_articles_data', []))}")
                
                # Ensure we have the current articles data set
                if not hasattr(self, '_current_articles_data'):
                    self._current_articles_data = articles_data
                    logger.info("Set _current_articles_data for fallback processing")
                
                if article_uri:
                    try:
                        related_articles = await self._find_related_articles(article_uri, top_k=3)
                        logger.info(f"Fallback article {i+1}: found {len(related_articles)} related articles")
                    except Exception as e:
                        logger.error(f"Error finding related articles for fallback article {i+1}: {e}")
                        related_articles = []
                else:
                    logger.warning(f"No URI available for fallback article {i+1}: {article_data.get('title', 'Unknown')}")
                
                article = {
                    'title': article_data.get('title', 'Unknown Title'),
                    'source': article_data.get('news_source'),  # Let frontend handle None/empty
                    'date': article_data.get('publication_date', ''),
                    'summary': article_data.get('summary', 'No summary available'),
                    'why_interesting': f"Article #{i+1} - Selected from available articles for analysis",
                    'devils_advocate': "This article may not represent the most strategic information available",
                    'perspectives': {
                        'left': 'Analysis not available in fallback mode',
                        'center': 'Analysis not available in fallback mode', 
                        'right': 'Analysis not available in fallback mode'
                    },
                    'related_articles': related_articles,
                    'bias': article_data.get('bias'),
                    'factual_reporting': article_data.get('factual_reporting'),
                    'uri': article_data.get('uri', '')
                }
                
                articles.append(article)
                
            except Exception as e:
                logger.warning(f"Error creating fallback article {i}: {e}")
                continue
        
        return articles


# Singleton instance
_news_feed_service = None

def get_news_feed_service(db: Database) -> NewsFeedService:
    """Get or create news feed service instance"""
    global _news_feed_service
    if _news_feed_service is None:
        _news_feed_service = NewsFeedService(db)

    return _news_feed_service
