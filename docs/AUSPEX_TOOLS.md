# Auspex Tools Integration

This document explains how Auspex integrates with various tools to provide enhanced AI capabilities.

## Overview

Auspex 2.0 includes powerful tools that allow the AI assistant to access real-time data and perform advanced analysis. These tools are seamlessly integrated into chat conversations and automatically triggered based on user queries.

## Available Tools

### 1. **Search News** (`search_news`)
- **Purpose**: Search for current news articles using TheNewsAPI
- **Parameters**:
  - `query`: Search query string
  - `max_results`: Maximum number of results (default: 10)
  - `language`: Language code (default: "en")  
  - `days_back`: How many days back to search (default: 7)
  - `categories`: Optional news categories to filter by
- **Triggered by**: Keywords like "latest", "recent", "current", "new"

### 2. **Get Topic Articles** (`get_topic_articles`)
- **Purpose**: Retrieve articles from the database for a specific topic
- **Parameters**:
  - `topic`: Topic name to search for
  - `limit`: Maximum articles to return (default: 50)
  - `days_back`: Number of days back to search (default: 30)
- **Triggered by**: Always used for context in topic-based conversations

### 3. **Analyze Sentiment Trends** (`analyze_sentiment_trends`)
- **Purpose**: Analyze sentiment patterns over time for a topic
- **Parameters**:
  - `topic`: Topic to analyze
  - `time_period`: "week", "month", or "quarter" (default: "month")
- **Triggered by**: Keywords like "sentiment", "feeling", "opinion"

### 4. **Get Article Categories** (`get_article_categories`)
- **Purpose**: Get category distribution for articles on a topic
- **Parameters**:
  - `topic`: Topic to analyze categories for
- **Triggered by**: Keywords like "categories", "types", "kinds"

### 5. **Search Articles by Keywords** (`search_articles_by_keywords`)
- **Purpose**: Search database articles using specific keywords
- **Parameters**:
  - `keywords`: Array of keywords to search for
  - `topic`: Optional topic to search within
  - `limit`: Maximum results (default: 25)
- **Triggered by**: Complex keyword-based queries

## Architecture

### Current Implementation (Simplified)

The current implementation uses a direct tools service approach:

```
User Query → Auspex Service → Tools Service → Database/API → Response
```

- **AuspexService**: Main service handling chat logic
- **AuspexToolsService**: Direct tool implementations
- **Database**: Local article storage
- **TheNewsAPI**: Real-time news source

### Tools Service (`app/services/auspex_tools.py`)

The `AuspexToolsService` class provides direct access to all tools without MCP overhead. This approach is simpler and more efficient for single-process applications.

### Automatic Tool Selection

Auspex automatically determines which tools to use based on message content:

```python
# Example: User asks "What's the latest news on AI?"
# Triggers: search_news + get_topic_articles

# Example: User asks "How do people feel about this topic?"  
# Triggers: analyze_sentiment_trends + get_topic_articles
```

## MCP Server (Alternative Implementation)

We also provide a full MCP (Model Context Protocol) server implementation that can run as a separate process:

### Files:
- `app/services/mcp_server.py`: MCP server implementation
- `scripts/run_mcp_server.py`: Server startup script
- `scripts/run_mcp_server.bat`: Windows batch file

### Running the MCP Server:

**Python:**
```bash
python scripts/run_mcp_server.py
```

**Windows:**
```bash
scripts\run_mcp_server.bat
```

### MCP Benefits:
- **Isolation**: Tools run in separate process
- **Scalability**: Can distribute across multiple servers  
- **Protocol Standard**: Uses industry standard MCP
- **Language Agnostic**: Can be consumed by any MCP client

### MCP Usage:
The MCP server communicates via stdio and provides the same tools as JSON-RPC endpoints.

## Configuration

### Environment Variables:
- `THENEWSAPI_KEY`: API key for TheNewsAPI (required for news search)
- `DATABASE_URL`: Database connection string

### Database Requirements:
- Articles table with proper indexing
- Topics table
- Recent articles by topic query support

## Error Handling

All tools include comprehensive error handling:
- **Network errors**: Graceful fallback for API failures
- **Database errors**: Safe error messages without exposing internals
- **Input validation**: Parameter validation with helpful error messages
- **Timeout handling**: Prevents hanging requests

## Performance

### Optimizations:
- **Lazy loading**: News collector only instantiated when needed
- **Result limiting**: Configurable limits prevent excessive data transfer
- **Date filtering**: Efficient date-based queries
- **Deduplication**: Removes duplicate articles from multi-keyword searches

### Caching:
- Database queries are optimized with proper indexing
- API results can be cached (implementation dependent)

## Usage Examples

### Direct API Usage:
```python
from app.services.auspex_tools import get_auspex_tools_service

tools = get_auspex_tools_service()

# Search recent news
news = await tools.search_news("artificial intelligence", max_results=5)

# Analyze sentiment  
sentiment = await tools.analyze_sentiment_trends("AI", "month")

# Get categories
categories = await tools.get_article_categories("technology")
```

### Chat Integration:
Tools are automatically triggered in Auspex chat based on message content. Users simply ask natural language questions and the appropriate tools are selected and executed.

## Future Enhancements

Potential improvements:
- **More data sources**: Additional news APIs, social media, etc.
- **Advanced NLP**: Better keyword extraction and intent detection
- **Real-time notifications**: Push updates for trending topics
- **Custom tool creation**: User-defined analysis tools
- **Export capabilities**: Data export in various formats 