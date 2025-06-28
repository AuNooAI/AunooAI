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
from app.ai_models import get_ai_model

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

    def _select_diverse_articles(self, articles: List[Dict], limit: int) -> List[Dict]:
        """Select diverse articles from a larger pool based on category, source, and recency."""
        if len(articles) <= limit:
            return articles
        
        # Sort by similarity score first (best matches first)
        sorted_articles = sorted(articles, key=lambda x: x.get('similarity_score', 1.0))
        
        selected = []
        seen_categories = set()
        seen_sources = set()
        
        # First pass: Select top articles ensuring category diversity
        for article in sorted_articles:
            if len(selected) >= limit:
                break
                
            category = article.get('category', 'Unknown')
            source = article.get('news_source', 'Unknown')
            
            # Prefer articles from new categories and sources
            category_bonus = 0 if category in seen_categories else 1
            source_bonus = 0 if source in seen_sources else 0.5
            
            # Add if we have space and it adds diversity, or if it's a very good match
            if (len(selected) < limit * 0.7 or  # Always fill 70% with top matches
                category_bonus > 0 or source_bonus > 0):
                selected.append(article)
                seen_categories.add(category)
                seen_sources.add(source)
        
        # Fill remaining slots with best remaining articles
        remaining_needed = limit - len(selected)
        if remaining_needed > 0:
            remaining_articles = [a for a in sorted_articles if a not in selected]
            selected.extend(remaining_articles[:remaining_needed])
        
        return selected[:limit]

    async def enhanced_database_search(self, query: str, topic: str, limit: int = 50, model: str = "gpt-3.5-turbo") -> Dict:
        """Enhanced database search with hybrid vector/SQL search and intelligent query parsing."""
        try:
            # Get available options for this topic
            topic_options = self.analyze_db.get_topic_options(topic)
            
            # Enhanced search strategy: Use both SQL and vector search
            # First, try vector search for semantic understanding
            vector_articles = []
            try:
                # Build metadata filter for vector search
                metadata_filter = {"topic": topic}
                
                # Parse query for date filtering using LLM
                vector_date_filter = None  # Initialize date filter variable
                search_intent_messages = [
                    {"role": "system", "content": f"""You are an AI assistant that helps search through articles about {topic}.
Your job is to determine if this query requires date filtering.

IMPORTANT: If the query mentions analyzing "articles", "news", or "content" without specifying historical analysis, assume they want RECENT articles (default 14 days).

Return ONLY a JSON object with date filtering information:
{{
    "needs_date_filter": true/false,
    "date_range_days": number or null
}}

Examples:
- "past 7 days" → {{"needs_date_filter": true, "date_range_days": 7}}
- "last week" → {{"needs_date_filter": true, "date_range_days": 7}}
- "recent trends" → {{"needs_date_filter": true, "date_range_days": 30}}
- "what happened yesterday" → {{"needs_date_filter": true, "date_range_days": 1}}
- "analyze the provided news articles" → {{"needs_date_filter": true, "date_range_days": 14}}
- "analyze recent articles" → {{"needs_date_filter": true, "date_range_days": 14}}
- "current developments" → {{"needs_date_filter": true, "date_range_days": 14}}
- "latest articles" → {{"needs_date_filter": true, "date_range_days": 7}}
- "historical analysis of all articles" → {{"needs_date_filter": false, "date_range_days": null}}
- "comprehensive analysis" → {{"needs_date_filter": true, "date_range_days": 30}}"""},
                    {"role": "user", "content": query}
                ]
                
                ai_model = get_ai_model(model)
                date_filter_response = ai_model.generate_response(search_intent_messages)
                
                try:
                    date_filter_json = self._extract_json_from_response(date_filter_response)
                    date_filter_info = json.loads(date_filter_json)
                    
                    # ChromaDB DOES support date range operators with proper timestamp format
                    if date_filter_info.get("needs_date_filter") and date_filter_info.get("date_range_days"):
                        days_back = date_filter_info["date_range_days"]
                        cutoff_datetime = datetime.now() - timedelta(days=days_back)
                        cutoff_timestamp = int(cutoff_datetime.timestamp())
                        
                        # Add timestamp-based date filter to ChromaDB metadata filter
                        metadata_filter["publication_date_ts"] = {"$gte": cutoff_timestamp}
                        logger.debug(f"Added ChromaDB date filter: publication_date_ts >= {cutoff_timestamp} ({cutoff_datetime.strftime('%Y-%m-%d')})")
                        vector_date_filter = None  # No need for post-processing
                    else:
                        vector_date_filter = None
                except Exception as e:
                    logger.warning(f"Could not parse date filter from LLM: {e}")
                    vector_date_filter = None
                
                vector_results = vector_search_articles(
                    query=query,
                    top_k=limit,
                    metadata_filter=metadata_filter
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
                            "similarity_score": result.get("score", 0)
                        })
                
                logger.debug(f"Vector search found {len(vector_articles)} semantically relevant articles")
                
                # Post-processing date filter (fallback for articles without timestamp metadata)
                time_keywords = ['past', 'last', 'recent', 'days', 'week', 'month', 'yesterday', 'today', 'current', 'latest', 'new']
                analysis_keywords = ['analyze', 'analysis', 'provided', 'news articles', 'articles', 'developments', 'trends']
                
                query_lower = query.lower()
                has_time_words = any(time_word in query_lower for time_word in time_keywords)
                has_analysis_words = any(analysis_word in query_lower for analysis_word in analysis_keywords)
                
                # Apply fallback date filtering for articles that might lack timestamp metadata
                if has_time_words or has_analysis_words:
                    days_back = 14  # Default for analysis requests
                    
                    if 'past 7 days' in query_lower or 'last week' in query_lower or 'latest' in query_lower:
                        days_back = 7
                    elif 'yesterday' in query_lower:
                        days_back = 1
                    elif 'past month' in query_lower or 'last month' in query_lower:
                        days_back = 30
                    elif 'comprehensive' in query_lower or 'detailed' in query_lower:
                        days_back = 30
                    elif 'recent' in query_lower or 'current' in query_lower:
                        days_back = 14
                    
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
                        logger.info(f"Fallback date filtering: {original_count} -> {len(filtered_vector_articles)} articles (past {days_back} days)")
                        vector_articles = filtered_vector_articles
                
            except Exception as e:
                logger.warning(f"Vector search failed, falling back to SQL search: {e}")
                vector_articles = []

            # If vector search found good results, use them; otherwise fall back to SQL search
            if len(vector_articles) >= 10:
                # Enhanced selection: Apply diversity and quality filtering
                articles = self._select_diverse_articles(vector_articles, limit)
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
                            articles_batch, count = self.db.search_articles(
                                topic=topic,
                                category=params.get("category"),
                                pub_date_start=pub_date_start,
                                pub_date_end=pub_date_end,
                                page=1,
                                per_page=limit
                            )
                        # Otherwise, use keyword search
                        else:
                            articles_batch, count = self.db.search_articles(
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

    async def get_topic_articles(self, topic: str, limit: int = 50, 
                               days_back: int = 30) -> Dict:
        """Get articles from database for a specific topic."""
        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        try:
            articles = self.db.get_recent_articles_by_topic(
                topic_name=topic,
                limit=limit,
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d")
            )
            
            result = {
                "topic": topic,
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

    async def analyze_sentiment_trends(self, topic: str, 
                                     time_period: str = "month") -> Dict:
        """Analyze sentiment trends for articles."""
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
            
            articles, _ = self.db.search_articles(
                topic=topic,
                pub_date_start=start_date.strftime("%Y-%m-%d"),
                pub_date_end=end_date.strftime("%Y-%m-%d"),
                page=1,
                per_page=1000
            )
            
            # Analyze sentiment distribution
            sentiment_counts = {}
            for article in articles:
                sentiment = article.get('sentiment', 'Unknown')
                sentiment_counts[sentiment] = sentiment_counts.get(sentiment, 0) + 1
            
            total_articles = len(articles)
            sentiment_percentages = {
                sentiment: (count / total_articles * 100) if total_articles > 0 else 0
                for sentiment, count in sentiment_counts.items()
            }
            
            result = {
                "topic": topic,
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

    async def get_article_categories(self, topic: str) -> Dict:
        """Get article categories and their distribution."""
        try:
            articles, _ = self.db.search_articles(topic=topic, page=1, per_page=1000)
            
            # Analyze category distribution
            category_counts = {}
            for article in articles:
                category = article.get('category', 'Uncategorized')
                category_counts[category] = category_counts.get(category, 0) + 1
            
            total_articles = len(articles)
            category_percentages = {
                category: (count / total_articles * 100) if total_articles > 0 else 0
                for category, count in category_counts.items()
            }
            
            result = {
                "topic": topic,
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
            
            articles, total_count = self.db.search_articles(
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
                articles, _ = self.db.search_articles(
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

    async def semantic_search_and_analyze(self, query: str, topic: str, 
                                        analysis_type: str = "comprehensive",
                                        limit: int = 50) -> Dict:
        """Perform semantic search with diversity filtering and structured analysis."""
        try:
            # For comprehensive analysis requests, get all articles for the topic
            # rather than searching for the specific query text
            if any(word in query.lower() for word in ["comprehensive", "analysis", "detailed", "insights", "structured", "breakdown"]):
                # Get articles by topic only for comprehensive analysis
                articles, _ = self.db.search_articles(
                    topic=topic,
                    page=1,
                    per_page=limit * 2  # Get more for diversity filtering
                )
            else:
                # For specific queries, search by keyword
                articles, _ = self.db.search_articles(
                    keyword=query,
                    topic=topic,
                    page=1,
                    per_page=limit * 2  # Get more for diversity filtering
                )
            
            # Apply diversity filtering (simplified version)
            diverse_articles = self._apply_diversity_filter(articles, limit)
            
            # Perform structured analysis
            analysis = self._perform_structured_analysis(diverse_articles, analysis_type)
            
            result = {
                "query": query,
                "topic": topic,
                "analysis_type": analysis_type,
                "total_articles_found": len(articles),
                "articles_analyzed": len(diverse_articles),
                "analysis": analysis,
                "articles": diverse_articles
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

    def _apply_diversity_filter(self, articles: List[Dict], limit: int) -> List[Dict]:
        """Apply diversity filtering to articles."""
        if len(articles) <= limit:
            return articles
        
        # Simple diversity filter based on source and category
        diverse_articles = []
        seen_sources = set()
        seen_categories = set()
        
        # First pass: prioritize diverse sources and categories
        for article in articles:
            source = article.get('source', 'Unknown')
            category = article.get('category', 'Uncategorized')
            
            if len(diverse_articles) >= limit:
                break
                
            # Prefer articles from new sources and categories
            if source not in seen_sources or category not in seen_categories:
                diverse_articles.append(article)
                seen_sources.add(source)
                seen_categories.add(category)
        
        # Second pass: fill remaining slots
        for article in articles:
            if len(diverse_articles) >= limit:
                break
            if article not in diverse_articles:
                diverse_articles.append(article)
        
        return diverse_articles[:limit]

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
            sentiment = article.get('sentiment', 'Unknown')
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
            article.get('title', '') + " " + article.get('summary', '')
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
        """Perform a follow-up query based on previous results."""
        try:
            # Combine original query with follow-up for better context
            enhanced_query = f"{original_query} {follow_up}"
            
            # Search for new articles
            new_articles, _ = self.db.search_articles(
                keyword=enhanced_query,
                topic=topic,
                page=1,
                per_page=25
            )
            
            # If we have context articles, try to find related content
            if context_articles:
                # Extract keywords from context articles for better search
                context_keywords = self._extract_context_keywords(context_articles)
                for keyword in context_keywords[:3]:  # Use top 3 keywords
                    keyword_articles, _ = self.db.search_articles(
                        keyword=keyword,
                        topic=topic,
                        page=1,
                        per_page=10
                    )
                    new_articles.extend(keyword_articles)
            
            # Remove duplicates and limit results
            seen_uris = set()
            unique_articles = []
            for article in new_articles:
                if article['uri'] not in seen_uris:
                    seen_uris.add(article['uri'])
                    unique_articles.append(article)
            
            unique_articles = unique_articles[:25]
            
            # Perform analysis on follow-up results
            analysis = self._perform_structured_analysis(unique_articles, "focused")
            
            result = {
                "original_query": original_query,
                "follow_up_query": follow_up,
                "enhanced_query": enhanced_query,
                "topic": topic,
                "total_results": len(unique_articles),
                "analysis": analysis,
                "articles": unique_articles
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
            article.get('title', '') + " " + article.get('summary', '')
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