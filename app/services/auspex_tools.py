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

logger = logging.getLogger(__name__)

class AuspexToolsService:
    """Service providing tools for Auspex AI."""

    def __init__(self):
        self.news_collector = None
        self.db = get_database_instance()

    def _get_news_collector(self) -> TheNewsAPICollector:
        """Get or create news collector instance."""
        if self.news_collector is None:
            self.news_collector = TheNewsAPICollector()
        return self.news_collector

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