"""
Auspex Tools Service
Provides tools for Auspex AI without MCP overhead.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from app.collectors.thenewsapi_collector import TheNewsAPICollector
from app.database import get_database_instance
from app.analyze_db import AnalyzeDB
from app.vector_store import search_articles as vector_search_articles
from app.ai_models import get_ai_model, get_available_models
from app.retrieval.reranker import rerank, overfetch_limit

# Import sampling framework
from app.services.sampling import (
    get_registry,
    SamplingContext,
    RecencyDiversitySampling,
    QualitySampling,
    SemanticSampling
)

logger = logging.getLogger(__name__)

class AuspexToolsService:
    """Service providing tools for Auspex AI with sophisticated database navigation."""

    def __init__(self):
        self.news_collector = None
        self.db = get_database_instance()
        self.analyze_db = AnalyzeDB(self.db)

    def _get_news_collector(self) -> TheNewsAPICollector:
        """Get or create news collector instance."""
        if self.news_collector is None:
            self.news_collector = TheNewsAPICollector()
        return self.news_collector

    def _extract_json_from_response(self, response: str) -> str:
        """Extract JSON object from LLM response, handling any extra text."""
        try:
            # Try to find JSON object between curly braces
            start = response.find('{')
            end = response.rfind('}') + 1
            if start >= 0 and end > start:
                json_str = response[start:end]
                # Clean up double curly braces
                json_str = json_str.replace('{{', '{').replace('}}', '}')
                # Remove any leading/trailing whitespace
                json_str = json_str.strip()
                logger.debug(f"Cleaned JSON string: {json_str}")
                return json_str
            return response
        except Exception as e:
            logger.error(f"Error extracting JSON: {str(e)}")
            return response

    def _select_diverse_articles(self, articles: List[Dict], limit: int, topic: str = None, sampling_strategy: str = None) -> List[Dict]:
        """Select diverse articles from a larger pool using the sampling framework.

        Args:
            articles: List of articles to sample from
            limit: Maximum number of articles to return
            topic: Current topic (None for cross-topic mode)
            sampling_strategy: Strategy name to use (default varies by context)

        Returns:
            Selected articles
        """
        if len(articles) <= limit:
            return articles

        # Create sampling context
        context = SamplingContext(topic=topic)
        context.update_stats(articles)

        # Store similarity scores in context for semantic-aware sampling
        for article in articles:
            sim = article.get('similarity_score')
            if sim is not None:
                article_id = str(article.get('id') or article.get('uri', ''))
                context.similarity_scores[article_id] = sim

        # Get strategy from registry or use default
        registry = get_registry()

        if sampling_strategy:
            # Use specified strategy
            pipeline = registry.create_pipeline_from_preset(sampling_strategy)
            if not pipeline:
                strategy_class = registry.get_strategy(sampling_strategy)
                if strategy_class:
                    sampler = strategy_class()
                else:
                    # Fallback to recency_diversity
                    sampler = RecencyDiversitySampling()
            else:
                return pipeline.execute(articles, limit, context)
        else:
            # Default behavior: use semantic sampling for searches (preserves relevance)
            # but RecencyDiversity for general retrieval
            has_similarity = any(a.get('similarity_score') is not None for a in articles)
            if has_similarity:
                # For semantic search results, use a 70% semantic / 30% diversity blend
                sampler = RecencyDiversitySampling(recency_ratio=0.7)
                # Override to use semantic sorting for "recency" portion
                # This maintains compatibility with the old 70/30 split
            else:
                sampler = RecencyDiversitySampling()

        return sampler.sample(articles, limit, context)

    # Topic values that indicate cross-topic (all topics) mode
    CROSS_TOPIC_VALUES = {"__all__", "All Topics", "all", "all_topics", "", None}

    def _normalize_topic(self, topic: Optional[str]) -> Optional[str]:
        """
        Normalize topic for database queries.
        Special values like '__all__', 'All Topics' are converted to None for cross-topic mode.
        """
        if topic is None or topic in self.CROSS_TOPIC_VALUES:
            return None
        return topic

    async def enhanced_database_search(self, query: str, topic: str = None, limit: int = 50, model: str = None) -> Dict:
        """Enhanced database search with hybrid vector/SQL search and intelligent query parsing.

        If topic is None or a special value like '__all__' (cross-topic mode), searches across all topics.
        """
        try:
            # Normalize topic - convert '__all__', 'All Topics', etc. to None for cross-topic mode
            topic = self._normalize_topic(topic)

            # Get model from configured models if not specified
            if model is None:
                available = get_available_models()
                if available:
                    model = available[0]['name']
                else:
                    raise ValueError("No configured models available")

            # Get available options for this topic (or all topics if None)
            topic_options = self.analyze_db.get_topic_options(topic)

            # Enhanced search strategy: Use both SQL and vector search
            # First, try vector search for semantic understanding
            vector_articles = []
            try:
                # Build metadata filter for vector search (skip topic filter for cross-topic mode)
                metadata_filter = {"topic": topic} if topic else {}
                
                # EXPLICIT CHECK for common date patterns (safety net)
                explicit_date_patterns = {
                    "trends from the last 7 days": 7,
                    "trends from the past 7 days": 7,
                    "trends in the last 7 days": 7,
                    "trends over the last 7 days": 7,
                    "last 7 days": 7,
                    "past 7 days": 7,
                    "last week": 7,
                    "past week": 7,
                    "last month": 30,
                    "past month": 30,
                    "last 30 days": 30,
                    "past 30 days": 30,
                }
                
                query_lower = query.lower()
                explicit_days_back = None
                for pattern, days in explicit_date_patterns.items():
                    if pattern in query_lower:
                        explicit_days_back = days
                        logger.info(f"EXPLICIT DATE PATTERN MATCH: '{pattern}' -> {days} days")
                        break
                
                if explicit_days_back:
                    cutoff_datetime = datetime.now() - timedelta(days=explicit_days_back)
                    cutoff_timestamp = int(cutoff_datetime.timestamp())
                    # Use proper syntax for combining filters
                    # For cross-topic mode (topic=None), only filter by date
                    if topic:
                        vector_date_filter = {
                            "$and": [
                                {"topic": topic},
                                {"publication_date_ts": {"$gte": cutoff_timestamp}}
                            ]
                        }
                    else:
                        vector_date_filter = {"publication_date_ts": {"$gte": cutoff_timestamp}}
                    logger.info(f"EXPLICIT date filter applied: publication_date_ts >= {cutoff_timestamp} ({cutoff_datetime.strftime('%Y-%m-%d %H:%M:%S')})")
                    logger.info(f"Vector date filter: {vector_date_filter}")
                else:
                    # No date filter - use topic filter if available, empty dict for cross-topic
                    vector_date_filter = {"topic": topic} if topic else {}
                
                fetch_k = overfetch_limit(limit)
                vector_results = vector_search_articles(
                    query=query,
                    top_k=fetch_k,
                    metadata_filter=vector_date_filter
                )

                # Convert vector results to article format
                for result in vector_results:
                    if result.get("metadata"):
                        vector_articles.append({
                            "uri": result["metadata"].get("uri"),
                            "title": result["metadata"].get("title"),
                            "summary": result["metadata"].get("summary"),
                            "category": result["metadata"].get("category"),
                            "sentiment": result["metadata"].get("sentiment"),
                            "future_signal": result["metadata"].get("future_signal"),
                            "time_to_impact": result["metadata"].get("time_to_impact"),
                            "publication_date": result["metadata"].get("publication_date"),
                            "news_source": result["metadata"].get("news_source"),
                            "tags": result["metadata"].get("tags", "").split(",") if result["metadata"].get("tags") else [],
                            "similarity_score": result.get("score", 0),
                            "_from_vector_db": True,  # Mark as from internal vector database
                            "source_type": "database"  # Explicit source type for routing
                        })

                vector_articles = await rerank(
                    query=query,
                    candidates=vector_articles,
                    text_fn=lambda c: f"{c.get('title', '')}. {c.get('summary', '')}",
                    top_k=limit,
                    topic=topic,
                )

                logger.debug(f"Vector search found {len(vector_articles)} semantically relevant articles")
                
                # Post-processing date filter (fallback for articles without timestamp metadata)
                time_keywords = ['past', 'last', 'recent', 'days', 'week', 'month', 'yesterday', 'today', 'current', 'latest', 'new']
                analysis_keywords = ['analyze', 'analysis', 'provided', 'news articles', 'articles', 'developments', 'trends']
                
                query_lower = query.lower()
                has_time_words = any(time_word in query_lower for time_word in time_keywords)
                has_analysis_words = any(analysis_word in query_lower for analysis_word in analysis_keywords)
                
                logger.info(f"Fallback date filtering check for query: '{query}'")
                logger.info(f"Has time words: {has_time_words} (found: {[word for word in time_keywords if word in query_lower]})")
                logger.info(f"Has analysis words: {has_analysis_words} (found: {[word for word in analysis_keywords if word in query_lower]})")
                
                # Apply fallback date filtering for articles that might lack timestamp metadata
                if has_time_words or has_analysis_words:
                    days_back = 14  # Default for analysis requests
                    
                    # More comprehensive pattern matching for time periods
                    if any(phrase in query_lower for phrase in ['past 7 days', 'last 7 days', 'from the last 7 days']):
                        days_back = 7
                    elif any(phrase in query_lower for phrase in ['past week', 'last week', 'from the last week']):
                        days_back = 7
                    elif 'latest' in query_lower:
                        days_back = 7
                    elif 'yesterday' in query_lower:
                        days_back = 1
                    elif any(phrase in query_lower for phrase in ['past month', 'last month', 'from the last month']):
                        days_back = 30
                    elif any(phrase in query_lower for phrase in ['past 30 days', 'last 30 days', 'from the last 30 days']):
                        days_back = 30
                    elif 'comprehensive' in query_lower or 'detailed' in query_lower:
                        days_back = 30
                    elif 'recent' in query_lower or 'current' in query_lower:
                        days_back = 14
                    elif 'trends' in query_lower and any(time_word in query_lower for time_word in ['last', 'past', 'from']):
                        # Special handling for trend queries with time references
                        if '7' in query_lower or 'week' in query_lower:
                            days_back = 7
                        elif '30' in query_lower or 'month' in query_lower:
                            days_back = 30
                        else:
                            days_back = 14  # Default for trends
                    
                    logger.info(f"Fallback date filtering triggered: {days_back} days back")
                    
                    cutoff_date = datetime.now() - timedelta(days=days_back)
                    original_count = len(vector_articles)
                    
                    # Filter articles by publication_date string (fallback for articles without timestamp)
                    filtered_vector_articles = []
                    for article in vector_articles:
                        article_date_str = article.get('publication_date', '')
                        if article_date_str:
                            try:
                                if ' ' in article_date_str:
                                    date_part = article_date_str.split(' ')[0]
                                else:
                                    date_part = article_date_str[:10]
                                
                                article_date = datetime.strptime(date_part, '%Y-%m-%d')
                                if article_date >= cutoff_date:
                                    filtered_vector_articles.append(article)
                                else:
                                    logger.debug(f"Fallback filter: excluded article from {date_part}: {article.get('title', 'Unknown')[:50]}...")
                            except Exception as e:
                                logger.warning(f"Could not parse date '{article_date_str}' for article {article.get('uri', 'unknown')}: {e}")
                                filtered_vector_articles.append(article)  # Include on error
                        else:
                            filtered_vector_articles.append(article)  # Include articles without dates
                    
                    if original_count != len(filtered_vector_articles):
                        logger.info(f"Fallback date filtering: {original_count} -> {len(filtered_vector_articles)} articles (past {days_back} days, cutoff: {cutoff_date.strftime('%Y-%m-%d')})")
                        vector_articles = filtered_vector_articles
                    else:
                        logger.info(f"Fallback date filtering: No articles filtered out (all {original_count} articles are recent)")
                else:
                    logger.info("Fallback date filtering: Not triggered (no time or analysis keywords found)")
                
            except Exception as e:
                logger.warning(f"Vector search failed, falling back to SQL search: {e}")
                vector_articles = []

            # If vector search found good results, use them; otherwise fall back to SQL search
            if len(vector_articles) >= 10:
                # Enhanced selection: Apply diversity and quality filtering via sampling framework
                articles = self._select_diverse_articles(vector_articles, limit, topic=topic)
                total_count = len(vector_articles)
                search_method = "semantic vector search with diversity filtering"
                
                # Format search criteria for display
                search_summary = f"""## Search Method: Enhanced Semantic Search
- **Query**: "{query}"
- **Topic Filter**: {topic}
- **Search Type**: Vector similarity search using embeddings
- **Results**: Found {total_count} semantically relevant articles
- **Analysis Limit**: {limit} articles

## Results Overview
Analyzing the {len(articles)} most semantically similar articles
"""
            else:
                # Fall back to intelligent SQL-based search logic
                # First, let the LLM determine if this is a search request and what parameters to use
                available_options = f"""Available search options:
1. Categories: {', '.join(topic_options['categories'])}
2. Sentiments: {', '.join(topic_options['sentiments'])}
3. Future Signals: {', '.join(topic_options['futureSignals'])}
4. Time to Impact: {', '.join(topic_options['timeToImpacts'])}
5. Keywords in title, summary, or tags
6. Date ranges (last week/month/year)"""

                search_intent_messages = [
                    {"role": "system", "content": f"""You are an AI assistant that helps search through articles about {topic}.
Your job is to create effective search queries based on user questions.

{available_options}

IMPORTANT: You must follow these exact steps in order:

1. SPECIAL QUERY TYPES:
   a) For trend analysis requests:
      - Do NOT use keywords like "trends" or "patterns"
      - Instead, use ONLY the date_range parameter
      - Return ALL articles within that timeframe
      Example:
      {{
          "queries": [
              {{
                  "description": "Get all articles from the last 90 days for trend analysis",
                  "params": {{
                      "category": null,
                      "keyword": null,
                      "sentiment": null,
                      "future_signal": null,
                      "tags": null,
                      "date_range": "90"
                  }}
              }}
          ]
      }}
   
   b) For general analysis requests (without specific time frame):
      - Default to recent articles (14 days)
      - Use broader date range for comprehensive analysis (30 days)
      Examples:
      "analyze articles" → date_range: "14"
      "comprehensive analysis" → date_range: "30"
      "detailed analysis" → date_range: "30"

Return your search strategy in this format:
{{
    "queries": [
        {{
            "description": "Brief description of what this query searches for",
            "params": {{
                "category": ["Exact category names"] or null,
                "keyword": "main search term OR alternative term OR another term",
                "sentiment": "exact sentiment" or null,
                "future_signal": "exact signal" or null,
                "time_to_impact": "exact impact timing" or null,
                "tags": ["relevant", "search", "terms"],
                "date_range": "7/30/365" or null
            }}
        }}
    ]
}}"""},
                    {"role": "user", "content": query}
                ]

                # Get search parameters from LLM
                ai_model = get_ai_model(model)
                search_response = ai_model.generate_response(search_intent_messages)
                logger.debug(f"LLM search response: {search_response}")
                
                try:
                    json_str = self._extract_json_from_response(search_response)
                    logger.debug(f"Extracted JSON: {json_str}")
                    search_strategy = json.loads(json_str)
                    logger.debug(f"Search strategy: {json.dumps(search_strategy, indent=2)}")
                    
                    # Fallback: If no date_range specified but query looks like analysis, add default
                    query_lower = query.lower()
                    analysis_terms = ['analyze', 'analysis', 'provided', 'articles', 'news', 'developments']
                    if any(term in query_lower for term in analysis_terms):
                        for query_config in search_strategy.get("queries", []):
                            params = query_config.get("params", {})
                            if not params.get("date_range"):
                                # Apply smart defaults based on query content
                                if 'comprehensive' in query_lower or 'detailed' in query_lower:
                                    params["date_range"] = "30"
                                    logger.debug(f"Added 30-day date range for comprehensive analysis")
                                else:
                                    params["date_range"] = "14"
                                    logger.debug(f"Added 14-day date range for general analysis")
                    
                    all_articles = []
                    total_count = 0
                    
                    for query_config in search_strategy["queries"]:
                        params = query_config["params"]
                        logger.debug(f"Executing query: {query_config['description']}")
                        logger.debug(f"Query params: {json.dumps(params, indent=2)}")
                        
                        # Calculate date range if specified
                        pub_date_start = None
                        pub_date_end = None
                        if params.get("date_range"):
                            if params["date_range"] != "all":
                                pub_date_end = datetime.now()
                                pub_date_start = pub_date_end - timedelta(days=int(params["date_range"]))
                                pub_date_end = pub_date_end.strftime('%Y-%m-%d')
                                pub_date_start = pub_date_start.strftime('%Y-%m-%d')

                        # If we have a category match, use only that
                        if params.get("category"):
                            articles_batch, count = self.db.facade.search_articles(
                                topic=topic,
                                category=params.get("category"),
                                pub_date_start=pub_date_start,
                                pub_date_end=pub_date_end,
                                page=1,
                                per_page=limit
                            )
                        # Otherwise, use keyword search
                        else:
                            articles_batch, count = self.db.facade.search_articles(
                                topic=topic,
                                keyword=params.get("keyword"),
                                sentiment=[params.get("sentiment")] if params.get("sentiment") else None,
                                future_signal=[params.get("future_signal")] if params.get("future_signal") else None,
                                tags=params.get("tags"),
                                pub_date_start=pub_date_start,
                                pub_date_end=pub_date_end,
                                page=1,
                                per_page=limit
                            )
                        
                        logger.debug(f"Query returned {count} articles")
                        all_articles.extend(articles_batch)
                        total_count += count
                    
                    # Remove duplicates based on article URI
                    seen_uris = set()
                    unique_articles = []
                    for article in all_articles:
                        if article['uri'] not in seen_uris:
                            seen_uris.add(article['uri'])
                            unique_articles.append(article)
                    
                    articles = unique_articles[:limit]
                    search_method = "structured keyword search"

                    # Format search criteria for display
                    active_filters = []
                    for query_config in search_strategy.get("queries", []):
                        params = query_config.get("params", {})
                        if params.get("keyword"):
                            active_filters.append(f"Keywords: {params.get('keyword').replace('|', ' OR ')}")
                        if params.get("category"):
                            active_filters.append(f"Categories: {', '.join(params.get('category'))}")
                        if params.get("sentiment"):
                            active_filters.append(f"Sentiment: {params.get('sentiment')}")
                        if params.get("future_signal"):
                            active_filters.append(f"Future Signal: {params.get('future_signal')}")
                        if params.get("tags"):
                            active_filters.append(f"Tags: {', '.join(params.get('tags'))}")

                    search_summary = f"""## Search Method: {search_method.title()}
{chr(10).join(['- ' + f for f in active_filters])}
- **Analysis Limit**: {limit} articles

## Results Overview
Found {total_count} total matching articles
Analyzing the {len(articles)} most recent articles
"""
                except Exception as e:
                    logger.error(f"Search error: {str(e)}", exc_info=True)
                    articles = []
                    total_count = 0
                    search_method = "error fallback"
                    search_summary = "## Search Error\nFell back to basic search due to parsing error."

            return {
                "query": query,
                "topic": topic,
                "search_method": search_method,
                "search_summary": search_summary,
                "total_articles": total_count,
                "analyzed_articles": len(articles),
                "articles": articles,
                "topic_options": topic_options
            }

        except Exception as e:
            logger.error(f"Error in enhanced database search: {e}")
            return {
                "error": f"Error in enhanced database search: {str(e)}",
                "query": query,
                "topic": topic,
                "total_articles": 0,
                "articles": []
            }

    async def search_news(self, query: str, max_results: int = 10, 
                         language: str = "en", days_back: int = 7, 
                         categories: List[str] = None) -> Dict:
        """Search for news articles using TheNewsAPI."""
        try:
            collector = self._get_news_collector()
            
            # Calculate date range
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days_back)
            
            # Search for articles
            articles = await collector.search_articles(
                query=query,
                topic=query,  # Add topic parameter
                max_results=max_results,
                start_date=start_date,
                end_date=end_date,
                language=language,
                categories=categories
            )
            
            result = {
                "query": query,
                "total_results": len(articles),
                "time_period": f"{days_back} days",
                "language": language,
                "articles": articles[:max_results]
            }
            
            return result
        except Exception as e:
            logger.error(f"Error searching news: {e}")
            return {
                "error": f"Error searching news: {str(e)}",
                "query": query,
                "total_results": 0,
                "articles": []
            }

    async def google_web_search(self, query: str, max_results: int = 10) -> Dict:
        """Search using Google Programmable Search Engine."""
        import os
        import aiohttp

        api_key = os.environ.get('GOOGLE_API_KEY') or os.environ.get('GOOGLE_SEARCH_API_KEY')
        search_engine_id = os.environ.get('GOOGLE_CSE_ID') or os.environ.get('GOOGLE_SEARCH_ENGINE_ID')

        if not api_key or not search_engine_id:
            logger.debug("Google Search API key or CSE ID not configured")
            return {
                "error": (
                    "Google web search is not configured on this site: set "
                    "GOOGLE_API_KEY and GOOGLE_CSE_ID"
                ),
                "query": query,
                "total_results": 0,
                "articles": []
            }

        try:
            url = "https://www.googleapis.com/customsearch/v1"
            params = {
                'key': api_key,
                'cx': search_engine_id,
                'q': query,
                'num': min(max_results, 10)  # Google CSE max is 10 per request
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Google Search API error: {response.status} - {error_text}")
                        # Google's own words: a bare status code cannot tell a
                        # disabled API apart from a spent quota or a bad key,
                        # and those are fixed in different places.
                        detail = ""
                        try:
                            detail = (await response.json()).get("error", {}).get("message", "")
                        except Exception:
                            detail = error_text[:200]
                        return {
                            "error": (
                                f"Google Search API error {response.status}"
                                + (f": {detail}" if detail else "")
                            ),
                            "query": query,
                            "total_results": 0,
                            "articles": []
                        }

                    data = await response.json()
                    items = data.get('items', [])

                    articles = []
                    for item in items:
                        articles.append({
                            'title': item.get('title', ''),
                            'url': item.get('link', ''),
                            'summary': item.get('snippet', ''),
                            'source': item.get('displayLink', ''),
                            'category': 'Web Search',
                            'sentiment': 'neutral',  # Default sentiment for web results
                        })

                    logger.info(f"Google Search returned {len(articles)} results for: {query}")
                    return {
                        "query": query,
                        "total_results": len(articles),
                        "search_method": "google_pse",
                        "articles": articles
                    }

        except Exception as e:
            logger.error(f"Error in Google web search: {e}")
            return {
                "error": f"Error in Google web search: {str(e)}",
                "query": query,
                "total_results": 0,
                "articles": []
            }

    async def get_topic_articles(self, topic: str = None, limit: int = 50,
                               days_back: int = 30) -> Dict:
        """Get articles from database for a specific topic.

        If topic is None (cross-topic mode), returns articles from all topics.
        """
        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)

        try:
            articles = self.db.facade.get_recent_articles_by_topic(
                topic_name=topic,  # None for cross-topic mode
                limit=limit,
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d")
            )

            result = {
                "topic": topic if topic else "All Topics",
                "total_articles": len(articles),
                "time_period": f"{days_back} days",
                "articles": articles
            }

            return result
        except Exception as e:
            logger.error(f"Error getting topic articles: {e}")
            return {
                "error": f"Error getting topic articles: {str(e)}",
                "topic": topic,
                "total_articles": 0,
                "articles": []
            }

    async def analyze_sentiment_trends(self, topic: str = None,
                                     time_period: str = "month") -> Dict:
        """Analyze sentiment trends for articles.

        If topic is None (cross-topic mode), analyzes across all topics.
        """
        # Map time period to days
        period_days = {
            "week": 7,
            "month": 30,
            "quarter": 90
        }.get(time_period, 30)

        try:
            # Get articles for the period
            end_date = datetime.now()
            start_date = end_date - timedelta(days=period_days)

            articles, _ = self.db.facade.search_articles(
                topic=topic,  # None for cross-topic mode
                pub_date_start=start_date.strftime("%Y-%m-%d"),
                pub_date_end=end_date.strftime("%Y-%m-%d"),
                page=1,
                per_page=1000
            )

            # Analyze sentiment distribution
            sentiment_counts = {}
            for article in articles:
                sentiment = article.get('sentiment') or 'Unknown'
                if sentiment in (None, 'None', '', 'null'):
                    sentiment = 'Unknown'
                sentiment_counts[sentiment] = sentiment_counts.get(sentiment, 0) + 1

            total_articles = len(articles)
            sentiment_percentages = {
                sentiment: (count / total_articles * 100) if total_articles > 0 else 0
                for sentiment, count in sentiment_counts.items()
            }

            result = {
                "topic": topic if topic else "All Topics",
                "time_period": time_period,
                "total_articles": total_articles,
                "sentiment_distribution": sentiment_counts,
                "sentiment_percentages": sentiment_percentages
            }

            return result
        except Exception as e:
            logger.error(f"Error analyzing sentiment trends: {e}")
            return {
                "error": f"Error analyzing sentiment trends: {str(e)}",
                "topic": topic,
                "total_articles": 0,
                "sentiment_distribution": {},
                "sentiment_percentages": {}
            }

    async def get_article_categories(self, topic: str = None) -> Dict:
        """Get article categories and their distribution.

        If topic is None (cross-topic mode), returns categories from all topics.
        """
        try:
            articles, _ = self.db.facade.search_articles(topic=topic, page=1, per_page=1000)

            # Analyze category distribution
            category_counts = {}
            for article in articles:
                category = article.get('category') or 'Uncategorized'
                if category in (None, 'None', '', 'null'):
                    category = 'Uncategorized'
                category_counts[category] = category_counts.get(category, 0) + 1

            total_articles = len(articles)
            category_percentages = {
                category: (count / total_articles * 100) if total_articles > 0 else 0
                for category, count in category_counts.items()
            }

            result = {
                "topic": topic if topic else "All Topics",
                "total_articles": total_articles,
                "category_distribution": category_counts,
                "category_percentages": category_percentages
            }
            
            return result
        except Exception as e:
            logger.error(f"Error getting article categories: {e}")
            return {
                "error": f"Error getting article categories: {str(e)}",
                "topic": topic,
                "total_articles": 0,
                "category_distribution": {},
                "category_percentages": {}
            }

    async def search_articles_by_categories(self, categories: List[str], 
                                           topic: str, 
                                           limit: int = 50,
                                           days_back: int = 30) -> Dict:
        """Search articles filtered by specific categories."""
        try:
            # Calculate date range
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days_back)
            
            articles, total_count = self.db.facade.search_articles(
                topic=topic,
                category=categories,
                pub_date_start=start_date.strftime("%Y-%m-%d"),
                pub_date_end=end_date.strftime("%Y-%m-%d"),
                page=1,
                per_page=limit
            )
            
            result = {
                "topic": topic,
                "categories": categories,
                "total_articles": total_count,
                "time_period": f"{days_back} days",
                "articles": articles,
                "search_method": "category-filtered database search"
            }
            
            return result
        except Exception as e:
            logger.error(f"Error searching articles by categories: {e}")
            return {
                "error": f"Error searching articles by categories: {str(e)}",
                "topic": topic,
                "categories": categories,
                "total_articles": 0,
                "articles": []
            }

    async def search_articles_by_keywords(self, keywords: List[str], 
                                        topic: Optional[str] = None, 
                                        limit: int = 25) -> Dict:
        """Search articles by keywords."""
        try:
            # Search for each keyword and combine results
            all_articles = []
            for keyword in keywords:
                articles, _ = self.db.facade.search_articles(
                    keyword=keyword,
                    topic=topic,
                    page=1,
                    per_page=limit
                )
                all_articles.extend(articles)
            
            # Remove duplicates based on URI
            seen_uris = set()
            unique_articles = []
            for article in all_articles:
                if article['uri'] not in seen_uris:
                    seen_uris.add(article['uri'])
                    unique_articles.append(article)
            
            # Limit results
            unique_articles = unique_articles[:limit]
            
            result = {
                "keywords": keywords,
                "topic": topic,
                "total_results": len(unique_articles),
                "articles": unique_articles
            }
            
            return result
        except Exception as e:
            logger.error(f"Error searching articles by keywords: {e}")
            return {
                "error": f"Error searching articles by keywords: {str(e)}",
                "keywords": keywords,
                "topic": topic,
                "total_results": 0,
                "articles": []
            }

    # Words too common to retrieve on. Only used when a question has to be
    # turned back into keywords for the rows that carry no embedding.
    _QUERY_STOPWORDS = frozenset({
        'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with',
        'by', 'from', 'about', 'into', 'over', 'after', 'before', 'between',
        'what', 'which', 'who', 'whom', 'whose', 'when', 'where', 'why', 'how',
        'is', 'are', 'was', 'were', 'be', 'been', 'being', 'do', 'does', 'did',
        'has', 'have', 'had', 'can', 'could', 'will', 'would', 'should',
        'this', 'that', 'these', 'those', 'their', 'they', 'them', 'you',
        'your', 'our', 'any', 'all', 'some', 'more', 'most', 'other', 'such',
        'than', 'then', 'also', 'very', 'say', 'says', 'said', 'tell', 'show',
        'give', 'find', 'article', 'articles', 'news', 'recent', 'latest',
    })

    def _query_terms(self, query: str, max_terms: int = 6) -> List[str]:
        """The words in a question worth searching for on their own.

        Acronyms come first, then longer words before shorter ones, because
        length is a cheap stand-in for specificity: "reimbursement" narrows a
        result set and "programme" barely does.
        """
        ranked = []
        seen = set()
        for raw in (query or "").split():
            token = raw.strip('.,!?;:"\'()[]{}')
            word = token.lower()
            if not word or word in seen:
                continue
            acronym = len(token) >= 2 and token.isupper() and token.isalpha()
            if not acronym and (len(word) < 4 or word in self._QUERY_STOPWORDS):
                continue
            seen.add(word)
            ranked.append((not acronym, -len(word), word))
        ranked.sort()
        return [term for _, _, term in ranked[:max_terms]]

    @staticmethod
    def _terms_matched(row: Dict, terms: List[str]) -> int:
        """How many of a question's terms appear in one article's text."""
        text = f"{row.get('title') or ''} {row.get('summary') or ''}".lower()
        return sum(1 for term in terms if term in text)

    async def _retrieve_for_question(self, query: str, topic: Optional[str],
                                     limit: int) -> Dict:
        """Find the articles that answer a question.

        Two passes, because neither covers the store on its own. The pgvector
        index answers the question as a question, but it only holds the rows
        we have embedded, so a keyword pass over the question's own terms
        picks up the rest. Both sets go to the reranker together; it decides
        the final order, and where it is switched off the semantic hits still
        come first.
        """
        topic = self._normalize_topic(topic)
        query = (query or "").strip()
        if not query or query == "*":
            rows, _ = self.db.facade.search_articles(topic=topic, page=1, per_page=limit)
            return {
                "articles": rows,
                "candidates": len(rows),
                "search_method": "topic listing: no query given",
            }

        seen = set()
        semantic: List[Dict] = []
        try:
            hits = vector_search_articles(
                query=query,
                top_k=overfetch_limit(limit),
                metadata_filter={"topic": topic} if topic else {},
            )
            for hit in hits:
                metadata = hit.get("metadata") or {}
                uri = metadata.get("uri")
                if not uri or uri in seen:
                    continue
                seen.add(uri)
                row = dict(metadata)
                row["similarity_score"] = hit.get("score", 0)
                semantic.append(row)
        except Exception as e:
            logger.warning(f"Vector pass failed for '{query}': {e}")

        keyword: List[Dict] = []
        terms = self._query_terms(query)
        for term in terms:
            try:
                rows, _ = self.db.facade.search_articles(
                    keyword=term, topic=topic, page=1, per_page=limit)
            except Exception as e:
                logger.warning(f"Keyword pass failed for '{term}': {e}")
                continue
            for row in rows:
                uri = row.get('uri')
                if not uri or uri in seen:
                    continue
                seen.add(uri)
                keyword.append(row)

        # Each term was searched on its own, so one shared word is enough to
        # land in this list. Sorting by how many of the question's terms a row
        # actually contains puts the rows that answer it above the ones that
        # merely say "AI" - which is all the ordering there is when the
        # reranker is unavailable.
        keyword.sort(key=lambda row: -self._terms_matched(row, terms))

        candidates = semantic + keyword
        ranked = await rerank(
            query=query,
            candidates=candidates,
            text_fn=lambda c: f"{c.get('title') or ''}. {c.get('summary') or ''}",
            top_k=limit,
        )
        # rerank() adds this key when it ran; without it the order is cosine
        # for the vector half and term-overlap for the keyword half. Say which,
        # because the two are not equally good and a caller cannot tell.
        reranked = bool(ranked) and 'rerank_score' in ranked[0]
        return {
            "articles": ranked,
            "candidates": len(candidates),
            "search_method": (
                f"{len(semantic)} from the vector index, {len(keyword)} more matching "
                f"{', '.join(terms) if terms else 'nothing else'}, "
                + ("reranked against the question"
                   if reranked else
                   "ordered by similarity only (the reranker did not load)")
            ),
        }

    async def semantic_search_and_analyze(self, query: str, topic: str = None,
                                        analysis_type: str = "comprehensive",
                                        limit: int = 50) -> Dict:
        """Search the article store for a question and describe what came back.

        Retrieval is semantic (see ``_retrieve_for_question``). The analysis
        that follows is counting - sources, categories, sentiment split, dates
        - not a model reading the articles.

        If topic is None (cross-topic mode), searches across all topics.
        """
        try:
            found = await self._retrieve_for_question(query, topic, limit)
            articles = found["articles"]
            analysis = self._perform_structured_analysis(articles, analysis_type)

            result = {
                "query": query,
                "topic": self._normalize_topic(topic) or "All Topics",
                "analysis_type": analysis_type,
                "search_method": found["search_method"],
                "total_articles_found": found["candidates"],
                "articles_analyzed": len(articles),
                "analysis": analysis,
                "articles": articles
            }

            return result
        except Exception as e:
            logger.error(f"Error in semantic search and analysis: {e}")
            return {
                "error": f"Error in semantic search and analysis: {str(e)}",
                "query": query,
                "topic": topic,
                "analysis": {}
            }

    def _perform_structured_analysis(self, articles: List[Dict], analysis_type: str) -> Dict:
        """Perform structured analysis on articles."""
        analysis = {
            "summary": {
                "total_articles": len(articles),
                "date_range": self._get_date_range(articles),
                "sources": list(set(article.get('source', 'Unknown') for article in articles)),
                "categories": list(set(article.get('category', 'Uncategorized') for article in articles))
            },
            "sentiment_breakdown": self._analyze_sentiment_breakdown(articles),
            "key_themes": self._extract_key_themes(articles),
            "temporal_distribution": self._analyze_temporal_distribution(articles)
        }
        
        if analysis_type == "comprehensive":
            analysis["detailed_insights"] = self._generate_detailed_insights(articles)
            analysis["trending_topics"] = self._identify_trending_topics(articles)
        
        return analysis

    def _get_date_range(self, articles: List[Dict]) -> Dict:
        """Get date range of articles."""
        if not articles:
            return {"start": None, "end": None}
        
        dates = [article.get('published_date') for article in articles if article.get('published_date')]
        if not dates:
            return {"start": None, "end": None}
        
        return {
            "start": min(dates),
            "end": max(dates)
        }

    def _analyze_sentiment_breakdown(self, articles: List[Dict]) -> Dict:
        """Analyze sentiment breakdown."""
        sentiment_counts = {}
        for article in articles:
            sentiment = article.get('sentiment') or 'Unknown'
            if sentiment in (None, 'None', '', 'null'):
                sentiment = 'Unknown'
            sentiment_counts[sentiment] = sentiment_counts.get(sentiment, 0) + 1
        
        total = len(articles)
        return {
            "counts": sentiment_counts,
            "percentages": {
                sentiment: (count / total * 100) if total > 0 else 0
                for sentiment, count in sentiment_counts.items()
            }
        }

    def _extract_key_themes(self, articles: List[Dict]) -> List[str]:
        """Extract key themes from articles."""
        # Simple keyword extraction from titles and summaries
        all_text = " ".join([
            # `or ''` because a stored title or summary can be NULL, and
            # .get(k, '') hands back that None rather than the default.
            (article.get('title') or '') + " " + (article.get('summary') or '')
            for article in articles
        ]).lower()
        
        # Basic keyword extraction (in a real implementation, use NLP)
        common_words = ['the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'can', 'cannot', 'this', 'that', 'these', 'those']
        
        words = [word.strip('.,!?;:"()[]') for word in all_text.split()]
        word_counts = {}
        for word in words:
            if len(word) > 3 and word not in common_words:
                word_counts[word] = word_counts.get(word, 0) + 1
        
        # Return top themes
        sorted_themes = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)
        return [theme[0] for theme in sorted_themes[:10]]

    def _analyze_temporal_distribution(self, articles: List[Dict]) -> Dict:
        """Analyze temporal distribution of articles."""
        date_counts = {}
        for article in articles:
            date = article.get('published_date', '')
            if date:
                # Group by date (YYYY-MM-DD)
                date_key = date.split(' ')[0] if ' ' in date else date[:10]
                date_counts[date_key] = date_counts.get(date_key, 0) + 1
        
        return {
            "daily_counts": date_counts,
            "peak_date": max(date_counts.items(), key=lambda x: x[1])[0] if date_counts else None
        }

    def _generate_detailed_insights(self, articles: List[Dict]) -> Dict:
        """Generate detailed insights."""
        return {
            "source_diversity": len(set(article.get('source', 'Unknown') for article in articles)),
            "category_diversity": len(set(article.get('category', 'Uncategorized') for article in articles)),
            "avg_relevance_score": sum(article.get('relevance_score', 0) for article in articles) / len(articles) if articles else 0,
            "high_relevance_articles": len([a for a in articles if a.get('relevance_score', 0) > 0.7])
        }

    def _identify_trending_topics(self, articles: List[Dict]) -> List[str]:
        """Identify trending topics from recent articles."""
        # Simple implementation - could be enhanced with more sophisticated analysis
        recent_articles = sorted(articles, key=lambda x: x.get('published_date', ''), reverse=True)[:20]
        themes = self._extract_key_themes(recent_articles)
        return themes[:5]

    async def follow_up_query(self, original_query: str, follow_up: str, 
                            topic: str, context_articles: List[Dict] = None) -> Dict:
        """Answer a follow-up in the context of the question that came before."""
        try:
            # The follow-up on its own is usually a fragment ("and in the UK?"),
            # so it is searched together with the question it refines.
            enhanced_query = f"{original_query} {follow_up}".strip()
            found = await self._retrieve_for_question(enhanced_query, topic, 25)
            articles = list(found["articles"])

            # Articles carried over from the previous answer widen the search:
            # their recurring terms are what the conversation is about, which
            # the follow-up itself may never spell out.
            if context_articles:
                seen = {a.get('uri') for a in articles}
                for keyword in self._extract_context_keywords(context_articles)[:3]:
                    try:
                        rows, _ = self.db.facade.search_articles(
                            keyword=keyword,
                            topic=self._normalize_topic(topic),
                            page=1,
                            per_page=10
                        )
                    except Exception as e:
                        logger.warning(f"Context keyword pass failed for '{keyword}': {e}")
                        continue
                    for row in rows:
                        uri = row.get('uri')
                        if uri and uri not in seen:
                            seen.add(uri)
                            articles.append(row)
                articles = await rerank(
                    query=enhanced_query,
                    candidates=articles,
                    text_fn=lambda c: f"{c.get('title') or ''}. {c.get('summary') or ''}",
                    top_k=25,
                )

            # Perform analysis on follow-up results
            analysis = self._perform_structured_analysis(articles, "focused")

            result = {
                "original_query": original_query,
                "follow_up_query": follow_up,
                "enhanced_query": enhanced_query,
                "topic": topic,
                "search_method": found["search_method"],
                "total_results": len(articles),
                "analysis": analysis,
                "articles": articles
            }
            
            return result
        except Exception as e:
            logger.error(f"Error in follow-up query: {e}")
            return {
                "error": f"Error in follow-up query: {str(e)}",
                "original_query": original_query,
                "follow_up_query": follow_up,
                "topic": topic
            }

    def _extract_context_keywords(self, articles: List[Dict]) -> List[str]:
        """Extract keywords from context articles for follow-up queries."""
        # Extract important terms from titles and summaries
        all_text = " ".join([
            # `or ''` because a stored title or summary can be NULL, and
            # .get(k, '') hands back that None rather than the default.
            (article.get('title') or '') + " " + (article.get('summary') or '')
            for article in articles
        ]).lower()
        
        # Simple keyword extraction
        words = all_text.split()
        word_counts = {}
        stop_words = {'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
        
        for word in words:
            clean_word = word.strip('.,!?;:"()[]')
            if len(clean_word) > 3 and clean_word not in stop_words:
                word_counts[clean_word] = word_counts.get(clean_word, 0) + 1
        
        # Return top keywords
        sorted_keywords = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)
        return [keyword[0] for keyword in sorted_keywords[:10]]

# Global service instance
_tools_service_instance = None

def get_auspex_tools_service() -> AuspexToolsService:
    """Get the global Auspex tools service instance."""
    global _tools_service_instance
    if _tools_service_instance is None:
        _tools_service_instance = AuspexToolsService()
    return _tools_service_instance 