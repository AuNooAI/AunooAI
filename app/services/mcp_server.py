"""
MCP Server for Auspex AI Tools
Provides Model Context Protocol tools for Auspex to access news data and other resources.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence

from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.types import (
    Resource, 
    Tool, 
    TextContent, 
    ImageContent, 
    EmbeddedResource
)
import mcp.server.stdio
import mcp.types as types

from app.collectors.thenewsapi_collector import TheNewsAPICollector
from app.database import get_database_instance

logger = logging.getLogger(__name__)

class AuspexMCPServer:
    """MCP Server providing tools for Auspex AI."""

    def __init__(self):
        self.server = Server("auspex-mcp-server")
        self.news_collector = None
        self.db = get_database_instance()
        self._setup_tools()
        self._setup_resources()

    def _setup_tools(self):
        """Register MCP tools."""
        
        @self.server.list_tools()
        async def handle_list_tools() -> list[Tool]:
            """List available tools."""
            return [
                Tool(
                    name="search_news",
                    description="Search for news articles using TheNewsAPI",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query for news articles"
                            },
                            "max_results": {
                                "type": "integer",
                                "description": "Maximum number of results to return (default: 10)",
                                "default": 10
                            },
                            "language": {
                                "type": "string",
                                "description": "Language code (default: en)",
                                "default": "en"
                            },
                            "days_back": {
                                "type": "integer",
                                "description": "Number of days back to search (default: 7)",
                                "default": 7
                            },
                            "categories": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "News categories to filter by"
                            }
                        },
                        "required": ["query"]
                    }
                ),
                Tool(
                    name="get_topic_articles",
                    description="Get articles from database for a specific topic",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "topic": {
                                "type": "string",
                                "description": "Topic name to search for"
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum number of articles to return (default: 50)",
                                "default": 50
                            },
                            "days_back": {
                                "type": "integer",
                                "description": "Number of days back to search (default: 30)",
                                "default": 30
                            }
                        },
                        "required": ["topic"]
                    }
                ),
                Tool(
                    name="analyze_sentiment_trends",
                    description="Analyze sentiment trends for articles in database",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "topic": {
                                "type": "string",
                                "description": "Topic to analyze sentiment for"
                            },
                            "time_period": {
                                "type": "string",
                                "description": "Time period: 'week', 'month', or 'quarter'",
                                "default": "month"
                            }
                        },
                        "required": ["topic"]
                    }
                ),
                Tool(
                    name="get_article_categories",
                    description="Get article categories and their distribution for a topic",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "topic": {
                                "type": "string",
                                "description": "Topic to get categories for"
                            }
                        },
                        "required": ["topic"]
                    }
                ),
                Tool(
                    name="search_articles_by_keywords",
                    description="Search articles in database by keywords",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "keywords": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Keywords to search for"
                            },
                            "topic": {
                                "type": "string",
                                "description": "Topic to search within (optional)"
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum number of results (default: 25)",
                                "default": 25
                            }
                        },
                        "required": ["keywords"]
                    }
                )
            ]

        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
            """Handle tool calls."""
            try:
                if name == "search_news":
                    return await self._search_news(arguments)
                elif name == "get_topic_articles":
                    return await self._get_topic_articles(arguments)
                elif name == "analyze_sentiment_trends":
                    return await self._analyze_sentiment_trends(arguments)
                elif name == "get_article_categories":
                    return await self._get_article_categories(arguments)
                elif name == "search_articles_by_keywords":
                    return await self._search_articles_by_keywords(arguments)
                else:
                    raise ValueError(f"Unknown tool: {name}")
            except Exception as e:
                logger.error(f"Error in tool {name}: {str(e)}")
                return [types.TextContent(type="text", text=f"Error: {str(e)}")]

    def _setup_resources(self):
        """Register MCP resources."""
        
        @self.server.list_resources()
        async def handle_list_resources() -> list[Resource]:
            """List available resources."""
            return [
                Resource(
                    uri="topics://all",
                    name="All Topics",
                    description="List of all available topics in the database",
                    mimeType="application/json"
                ),
                Resource(
                    uri="prompts://default",
                    name="Default Auspex Prompt",
                    description="The default system prompt for Auspex",
                    mimeType="text/plain"
                )
            ]

        @self.server.read_resource()
        async def handle_read_resource(uri: str) -> str:
            """Read resource content."""
            if uri == "topics://all":
                topics = self.db.get_topics()
                return json.dumps(topics, indent=2)
            elif uri == "prompts://default":
                prompt = self.db.get_default_auspex_prompt()
                if prompt:
                    return prompt['content']
                return "You are Auspex, an AI research assistant specialized in analyzing news and trends."
            else:
                raise ValueError(f"Unknown resource: {uri}")

    async def _search_news(self, arguments: dict) -> list[types.TextContent]:
        """Search for news articles using TheNewsAPI."""
        if not self.news_collector:
            self.news_collector = TheNewsAPICollector()
        
        query = arguments["query"]
        max_results = arguments.get("max_results", 10)
        language = arguments.get("language", "en")
        days_back = arguments.get("days_back", 7)
        categories = arguments.get("categories", [])
        
        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        try:
            articles = await self.news_collector.search_articles(
                query=query,
                topic="search",
                max_results=max_results,
                start_date=start_date,
                end_date=end_date,
                language=language,
                categories=categories if categories else None
            )
            
            result = {
                "query": query,
                "total_results": len(articles),
                "search_period": f"{days_back} days",
                "articles": articles
            }
            
            return [types.TextContent(
                type="text",
                text=json.dumps(result, indent=2, default=str)
            )]
        except Exception as e:
            logger.error(f"Error searching news: {e}")
            return [types.TextContent(
                type="text",
                text=f"Error searching news: {str(e)}"
            )]

    async def _get_topic_articles(self, arguments: dict) -> list[types.TextContent]:
        """Get articles from database for a specific topic."""
        topic = arguments["topic"]
        limit = arguments.get("limit", 50)
        days_back = arguments.get("days_back", 30)
        
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
            
            return [types.TextContent(
                type="text",
                text=json.dumps(result, indent=2, default=str)
            )]
        except Exception as e:
            logger.error(f"Error getting topic articles: {e}")
            return [types.TextContent(
                type="text",
                text=f"Error getting topic articles: {str(e)}"
            )]

    async def _analyze_sentiment_trends(self, arguments: dict) -> list[types.TextContent]:
        """Analyze sentiment trends for articles."""
        topic = arguments["topic"]
        time_period = arguments.get("time_period", "month")
        
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
            
            return [types.TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]
        except Exception as e:
            logger.error(f"Error analyzing sentiment trends: {e}")
            return [types.TextContent(
                type="text",
                text=f"Error analyzing sentiment trends: {str(e)}"
            )]

    async def _get_article_categories(self, arguments: dict) -> list[types.TextContent]:
        """Get article categories and their distribution."""
        topic = arguments["topic"]
        
        try:
            articles, _ = self.db.search_articles(topic=topic, per_page=1000)
            
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
            
            return [types.TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]
        except Exception as e:
            logger.error(f"Error getting article categories: {e}")
            return [types.TextContent(
                type="text",
                text=f"Error getting article categories: {str(e)}"
            )]

    async def _search_articles_by_keywords(self, arguments: dict) -> list[types.TextContent]:
        """Search articles by keywords."""
        keywords = arguments["keywords"]
        topic = arguments.get("topic")
        limit = arguments.get("limit", 25)
        
        try:
            # Search for each keyword and combine results
            all_articles = []
            for keyword in keywords:
                articles, _ = self.db.search_articles(
                    keyword=keyword,
                    topic=topic,
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
            
            return [types.TextContent(
                type="text",
                text=json.dumps(result, indent=2, default=str)
            )]
        except Exception as e:
            logger.error(f"Error searching articles by keywords: {e}")
            return [types.TextContent(
                type="text",
                text=f"Error searching articles by keywords: {str(e)}"
            )]

    async def run_stdio(self):
        """Run the MCP server with stdio transport."""
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="auspex-mcp-server",
                    server_version="1.0.0",
                    capabilities=self.server.get_capabilities(
                        notification_options=None,
                        experimental_capabilities={}
                    )
                )
            )

# Global server instance
_server_instance = None

def get_mcp_server() -> AuspexMCPServer:
    """Get the global MCP server instance."""
    global _server_instance
    if _server_instance is None:
        _server_instance = AuspexMCPServer()
    return _server_instance

if __name__ == "__main__":
    import asyncio
    
    # Run the MCP server as a standalone process
    server = AuspexMCPServer()
    asyncio.run(server.run_stdio()) 