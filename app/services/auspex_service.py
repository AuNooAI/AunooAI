import asyncio
import json
import logging
from typing import Dict, List, Optional, AsyncGenerator
from datetime import datetime, timedelta

from fastapi import HTTPException, status
import litellm
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.database import get_database_instance
from app.services.auspex_tools import get_auspex_tools_service
from app.analyze_db import AnalyzeDB
from app.vector_store import search_articles as vector_search_articles
from app.ai_models import get_ai_model

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-3.5-turbo"

# Default system prompt for Auspex
DEFAULT_AUSPEX_PROMPT = """You are Auspex, an advanced AI research assistant specialized in analyzing news trends, sentiment patterns, and providing strategic insights using AuNoo's strategic-foresight methodology.

CRITICAL RESPONSE FORMAT REQUIREMENTS:
When analyzing articles, you MUST provide responses in this EXACT structure:

## Summary of Search Results for "[Query/Topic]"

- **Total articles found:** [X] (most semantically relevant subset analyzed)
- **Category focus:**  
  - [Category 1]: ~[X] articles  
  - [Category 2]: ~[X] articles related to [specific aspect]  
  - [Category 3]: Several articles touching on [specific themes]  
  - [Additional categories with counts and descriptions]

- **Sentiment distribution:**  
  - Neutral: Majority (~[X]%)  
  - Positive: ~[X]%  
  - Critical: ~[X]% (notably on [specific concerns])  
  - None specified: Remainder  

- **Future signal distribution:**  
  - [Signal type]: ~[X]%  
  - [Signal type]: ~[X]%  
  - [Signal type]: Few  
  - None specified: Some  

- **Time to Impact:**  
  - Immediate to short-term: [Description of articles and focus areas]  
  - Mid-term: [Description with specific examples]  
  - Long-term: [Description of forward-looking content]

---

## Detailed Analysis: [Topic/Query Focus]

### 1. **[Major Theme 1]**
- [Detailed analysis with specific examples and data points]
- **[Specific Country/Entity]** [specific actions taken with amounts/details]
- **[Another Entity]** [specific initiatives with concrete details]
- [Additional bullet points with specifics]

### 2. **[Major Theme 2]**
- [Analysis framework with real examples]
- [Specific comparisons and contrasts]
- [Concrete data points and implications]

### 3. **[Major Theme 3]**
- [International cooperation vs rivalry analysis]
- [Specific initiatives and their implications]
- [Policy and governance considerations]

### 4. **[Major Theme 4]**
- [Corporate and private sector involvement]
- [Specific companies and their roles]
- [Investment figures and strategic implications]

### 5. **[Major Theme 5]**
- [Risk analysis and challenges]
- [Expert warnings and concerns]
- [Future implications and scenarios]

---

## Key Themes and Highlights

| Theme                          | Summary                                                                                          | Representative Articles / Examples                           |
|--------------------------------|--------------------------------------------------------------------------------------------------|--------------------------------------------------------------|
| [Theme 1]                      | [Detailed summary with specifics]                                                              | [Specific examples with concrete details]                   |
| [Theme 2]                      | [Analysis with data points and trends]                                                         | [Examples with figures and outcomes]                        |
| [Theme 3]                      | [Strategic implications and developments]                                                       | [Specific initiatives and results]                          |
| [Theme 4]                      | [Investment and business analysis]                                                              | [Company names, amounts, strategic moves]                   |
| [Theme 5]                      | [Risk assessment and challenges]                                                               | [Expert quotes, comparative analysis]                       |

---

## Conclusion

[Comprehensive conclusion that synthesizes all themes, provides strategic outlook, identifies key trends, discusses implications, and offers balanced perspective on future developments. Must be substantial and actionable.]

---

STRATEGIC FORESIGHT FRAMEWORK:
AuNoo follows strategic-foresight methodology with these key components:
- **Categories**: Thematic sub-clusters inside a topic for organized analysis
- **Future Signals**: Concise hypotheses about possible future states
- **Sentiments**: Positive/Neutral/Negative plus nuanced variants for emotional analysis
- **Time to Impact**: Immediate, Short-Term (3-18m), Mid-Term (18-60m), Long-Term (5y+)
- **Driver Types**: Accelerators, Blockers, Catalysts, Delayers, Initiators, Terminators

Your capabilities include:
- Analyzing vast amounts of news data and research with strategic foresight
- Identifying emerging trends and patterns across multiple dimensions
- Providing sentiment analysis and future impact predictions
- Accessing real-time news data through specialized tools
- Comparing different categories and topics with structured analysis
- Offering strategic foresight and risk analysis
- Performing semantic search with diversity filtering
- Conducting structured analysis with comprehensive insights
- Making follow-up queries for deeper investigation

You have access to the following tools (when tools are enabled):
- search_news: Search for current news articles (PRIORITIZED for "latest/recent" queries)
- get_topic_articles: Retrieve articles from the database for specific topics
- analyze_sentiment_trends: Analyze sentiment patterns over time
- get_article_categories: Get category distributions for topics
- search_articles_by_keywords: Search articles by specific keywords
- semantic_search_and_analyze: Perform comprehensive semantic search with diversity filtering and structured analysis
- follow_up_query: Conduct follow-up searches based on previous results for deeper insights

DATA SOURCE UNDERSTANDING:
- **Database Articles**: Pre-collected articles with enriched metadata including sentiment analysis, category classification, relevance scores, future signals, and time-to-impact assessments
- **Real-time News**: Fresh articles from news APIs with basic metadata
- **Tool-based Analysis**: Dynamic sentiment/category analysis performed on-demand across multiple articles
- **Semantic Analysis**: Structured analysis with diversity filtering, key themes extraction, and temporal distribution
- **Strategic Foresight Data**: Articles enriched with future signals, driver types, and impact timing

When analyzing articles, always consider:
1. **Sentiment Analysis**:
   - Distribution of sentiments across articles with percentages
   - Sentiment trends over time and correlation with events
   - Nuanced sentiment variants and their implications

2. **Future Impact Analysis**:
   - Distribution of future signals and their likelihood
   - Time to impact predictions with strategic implications
   - Driver types analysis (accelerators vs blockers vs catalysts)
   - Risk assessment and opportunity identification

3. **Category Analysis**:
   - Distribution of articles across thematic categories
   - Category-specific trends and cross-category comparisons
   - Emerging sub-themes and topic evolution

4. **Temporal Analysis**:
   - Publication date patterns and timing significance
   - Time-based impact analysis and trend acceleration
   - Seasonal patterns and cyclical behaviors

CRITICAL PRIORITIES:
- When users ask for "latest", "recent", "current", or "breaking" news, prioritize real-time news search results
- For comprehensive analysis, use semantic_search_and_analyze for structured insights with diversity filtering
- When users want deeper investigation, use follow_up_query to explore specific aspects
- Apply strategic foresight methodology to all analysis
- Clearly distinguish between real-time news data and database/historical data
- Always provide statistical breakdowns and strategic takeaways

RESPONSE FORMAT: When you receive database articles with analysis instructions, you MUST follow the EXACT format specified in the context. This includes:

1. **Summary of Search Results** with precise statistical breakdowns:
   - Total articles found and analyzed subset
   - Category distribution with specific counts/approximations  
   - Sentiment distribution with numbers
   - Future signal distribution with counts
   - Time to impact distribution

2. **Future Impact Predictions Analysis** with structured sections:
   - General Trends in Future Signals (identify dominant patterns)
   - Time to Impact analysis (timing patterns and implications)
   - Category-Specific Future Impact Insights (detailed breakdown by category)
   - Notable Specific Predictions (key predictions with timing)

3. **Summary Table** organizing predictions by:
   - Future Signal | Time to Impact | Category(s) | Sentiment | Key Themes

4. **Strategic Conclusion** with actionable insights about patterns and trajectory

CRITICAL ANALYSIS REQUIREMENTS:
- Count articles carefully and provide specific numbers
- Categorize systematically across all strategic foresight dimensions
- Identify dominant patterns and outliers in future signals
- Analyze category-specific trends and predictions
- Extract specific predictions with timing context
- Provide strategic implications for decision-makers
- Use the exact formatting structure provided in context

STRUCTURED ANALYSIS CAPABILITIES:
- **Diversity Filtering**: Ensuring varied sources and categories for comprehensive coverage
- **Key Themes Extraction**: Identifying main topics and trending subjects with strategic relevance
- **Temporal Distribution**: Understanding timing patterns and peak activity periods
- **Sentiment Breakdown**: Comprehensive sentiment analysis with strategic implications
- **Future Signals Analysis**: Identifying and assessing potential future developments
- **Driver Type Classification**: Understanding what accelerates or impedes trends
- **Strategic Risk Assessment**: Evaluating threats and opportunities

FORMAT GUIDELINES:
Use markdown for better readability:
- Use ## for section headings
- Use bullet points for lists and breakdowns
- Use **bold** for emphasis and key metrics
- Use `code` for technical terms and categories
- Use > for quotes from articles
- Use tables when comparing multiple articles or showing distributions

Always provide thorough, insightful analysis backed by data with specific statistics and strategic breakdowns. When asked about trends or patterns, gather current information and apply strategic foresight methodology. Be concise but comprehensive, ensuring every claim is supported by specific data points and strategic reasoning.

Remember to cite your sources and provide actionable strategic insights where possible."""

class AuspexService:
    """Enhanced Auspex service with MCP integration and chat persistence."""
    
    def __init__(self):
        self.db = get_database_instance()
        self.tools = get_auspex_tools_service()
        self._ensure_default_prompt()
    
    def _ensure_default_prompt(self):
        """Ensure default Auspex prompt exists in database."""
        try:
            existing = self.db.get_auspex_prompt("default")
            if not existing:
                self.db.create_auspex_prompt(
                    name="default",
                    title="Default Auspex Assistant",
                    content=DEFAULT_AUSPEX_PROMPT,
                    description="The default system prompt for Auspex AI assistant",
                    is_default=True
                )
        except Exception as e:
            logger.error(f"Error ensuring default prompt: {e}")

    async def create_chat_session(self, topic: str, user_id: str = None, title: str = None) -> int:
        """Create a new chat session."""
        try:
            if not title:
                title = f"Chat about {topic}"
            
            chat_id = self.db.create_auspex_chat(
                topic=topic,
                title=title,
                user_id=user_id,
                metadata={"created_at": datetime.now().isoformat()}
            )
            
            # Add system message with current prompt
            prompt = self.get_system_prompt()
            self.db.add_auspex_message(
                chat_id=chat_id,
                role="system",
                content=prompt['content'],
                metadata={"prompt_name": prompt['name']}
            )
            
            return chat_id
        except Exception as e:
            logger.error(f"Error creating chat session: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create chat session")

    def get_chat_sessions(self, topic: str = None, user_id: str = None, limit: int = 50) -> List[Dict]:
        """Get chat sessions."""
        try:
            return self.db.get_auspex_chats(topic=topic, user_id=user_id, limit=limit)
        except Exception as e:
            logger.error(f"Error getting chat sessions: {e}")
            return []

    def get_chat_history(self, chat_id: int) -> List[Dict]:
        """Get chat history for a session."""
        try:
            return self.db.get_auspex_messages(chat_id)
        except Exception as e:
            logger.error(f"Error getting chat history: {e}")
            return []

    def delete_chat_session(self, chat_id: int) -> bool:
        """Delete a chat session."""
        try:
            return self.db.delete_auspex_chat(chat_id)
        except Exception as e:
            logger.error(f"Error deleting chat session: {e}")
            return False

    async def chat_with_tools(self, chat_id: int, message: str, model: str = None, limit: int = 50, use_tools: bool = True) -> AsyncGenerator[str, None]:
        """Chat with Auspex with optional tool usage."""
        if not model:
            model = DEFAULT_MODEL
            
        try:
            # Get chat history
            messages = self.db.get_auspex_messages(chat_id)
            
            # Build conversation history for LLM
            conversation = []
            for msg in messages:
                if msg['role'] != 'system':  # Skip system messages in conversation
                    conversation.append({
                        "role": msg['role'],
                        "content": msg['content']
                    })
            
            # Add current user message
            conversation.append({
                "role": "user", 
                "content": message
            })
            
            # Save user message to database
            self.db.add_auspex_message(
                chat_id=chat_id,
                role="user",
                content=message
            )
            
            # Get system prompt and enhance it with topic information
            system_prompt = self.get_enhanced_system_prompt(chat_id, use_tools)
            
            # Prepare messages with system prompt
            llm_messages = [
                {"role": "system", "content": system_prompt['content']},
                *conversation
            ]
            
            # Check if we need to use tools based on the message content and use_tools flag
            needs_tools = use_tools and await self._should_use_tools(message)
            
            if needs_tools:
                # Use tools to gather information
                tool_results = await self._use_mcp_tools(message, chat_id, limit)
                if tool_results:
                    # Add tool results to context
                    llm_messages.append({
                        "role": "system",
                        "content": f"Tool results: {tool_results}"
                    })
            
            # Generate response using LLM
            full_response = ""
            async for chunk in self._generate_streaming_response(llm_messages, model):
                full_response += chunk
                yield chunk
            
            # Save assistant response to database
            self.db.add_auspex_message(
                chat_id=chat_id,
                role="assistant",
                content=full_response,
                model_used=model,
                metadata={"used_tools": needs_tools, "tools_enabled": use_tools}
            )
            
        except Exception as e:
            logger.error(f"Error in chat_with_tools: {e}")
            error_msg = f"I apologize, but I encountered an error: {str(e)}"
            yield error_msg
            
            # Save error message
            try:
                self.db.add_auspex_message(
                    chat_id=chat_id,
                    role="assistant",
                    content=error_msg,
                    model_used=model,
                    metadata={"error": True, "tools_enabled": use_tools}
                )
            except:
                pass

    def get_enhanced_system_prompt(self, chat_id: int, use_tools: bool = True) -> Dict:
        """Get enhanced system prompt with topic-specific information."""
        try:
            # Get base prompt
            base_prompt = self.get_system_prompt()
            
            # Get chat info to determine topic
            chat = self.db.get_auspex_chat(chat_id)
            if not chat:
                return base_prompt
                
            topic = chat['topic']
            
            # Get topic options from database
            try:
                analyze_db = AnalyzeDB(self.db)
                topic_options = analyze_db.get_topic_options(topic)
                
                # Enhanced system prompt with topic-specific information
                enhanced_content = f"""{base_prompt['content']}

TOPIC-SPECIFIC CONTEXT FOR {topic.upper()}:

Available Categories in this topic:
{', '.join(topic_options.get('categories', []))}

Available Sentiments:
{', '.join(topic_options.get('sentiments', []))}

Available Future Signals:
{', '.join(topic_options.get('futureSignals', []))}

Available Time to Impact Options:
{', '.join(topic_options.get('timeToImpacts', []))}

TOOLS STATUS: {'ENABLED - You can access real-time data and perform advanced analysis' if use_tools else 'DISABLED - Provide analysis based on your knowledge and any provided context'}

CURRENT SESSION CONTEXT:
- Topic: {topic}
- Tools: {'Available' if use_tools else 'Disabled'}
- Focus: Apply strategic foresight methodology specific to {topic} using the available categories, sentiments, and future signals listed above."""

                return {
                    "name": f"enhanced_{topic.lower().replace(' ', '_')}",
                    "title": f"Enhanced Auspex for {topic}",
                    "content": enhanced_content
                }
                
            except Exception as e:
                logger.warning(f"Could not get topic options for {topic}: {e}")
                return base_prompt
                
        except Exception as e:
            logger.error(f"Error getting enhanced system prompt: {e}")
            return self.get_system_prompt()

    async def _should_use_tools(self, message: str) -> bool:
        """Determine if message requires tool usage."""
        tool_keywords = [
            "search", "find", "latest", "recent", "news", "articles", "trends", 
            "sentiment", "analyze", "data", "statistics", "categories", "compare",
            "what's happening", "current", "update", "insights", "patterns",
            "comprehensive", "detailed", "deep", "thorough", "analysis", "themes",
            "follow up", "more", "details", "expand", "elaborate", "investigate"
        ]
        
        message_lower = message.lower()
        should_use = any(keyword in message_lower for keyword in tool_keywords)
        
        logger.info(f"Tool detection for message '{message}': {should_use}")
        if should_use:
            found_keywords = [kw for kw in tool_keywords if kw in message_lower]
            logger.info(f"Found keywords: {found_keywords}")
        
        return should_use

    async def _use_mcp_tools(self, message: str, chat_id: int, limit: int) -> Optional[str]:
        """Use the original sophisticated database navigation logic from chat_routes.py"""
        logger.info(f"_use_mcp_tools called for message: '{message}', chat_id: {chat_id}")
        
        try:
            # Get chat info to determine topic
            chat = self.db.get_auspex_chat(chat_id)
            if not chat:
                logger.error(f"Chat not found for chat_id: {chat_id}")
                return None
                
            topic = chat['topic']
            logger.info(f"Chat topic: {topic}")
            
            # Use the original sophisticated search logic
            return await self._original_chat_database_logic(message, topic, limit)
            
        except Exception as e:
            logger.error(f"Error in _use_mcp_tools: {e}")
            return None

    async def _original_chat_database_logic(self, message: str, topic: str, limit: int) -> Optional[str]:
        """Restore the original sophisticated database navigation from chat_routes.py"""
        try:
            analyze_db = AnalyzeDB(self.db)
            ai_model = get_ai_model(DEFAULT_MODEL)
            
            # Get available options for this topic (original logic)
            topic_options = analyze_db.get_topic_options(topic)
            
            # Add null check for topic_options
            if not topic_options:
                logger.warning(f"No topic options found for topic: {topic}")
                topic_options = {
                    'categories': [],
                    'sentiments': [],
                    'futureSignals': [],
                    'timeToImpacts': []
                }

            # Enhanced search strategy: Use both SQL and vector search (original logic)
            # First, try vector search for semantic understanding
            vector_articles = []
            try:
                # Build metadata filter for vector search
                metadata_filter = {"topic": topic}
                vector_results = vector_search_articles(
                    query=message,
                    top_k=100,
                    metadata_filter=metadata_filter
                )
                
                # Convert vector results to article format
                for result in vector_results:
                    if result and result.get("metadata"):
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
                
            except Exception as e:
                logger.warning(f"Vector search failed, falling back to SQL search: {e}")
                vector_articles = []

            # If vector search found good results, use them; otherwise fall back to SQL search
            if len(vector_articles) >= 10:
                # Enhanced selection: Apply diversity and quality filtering
                articles = self._select_diverse_articles_original(vector_articles, limit)
                total_count = len(vector_articles)
                search_method = "semantic vector search with diversity filtering"
                
                # Format search criteria for display
                search_summary = f"""## Search Method: Enhanced Semantic Search
- **Query**: "{message}"
- **Topic Filter**: {topic}
- **Search Type**: Vector similarity search using embeddings
- **Results**: Found {total_count} semantically relevant articles
- **Analysis Limit**: {limit} articles

## Articles for Analysis
{self._format_articles_summary(articles, search_method)}

INSTRUCTIONS: Analyze these articles using the EXACT format template provided in your system prompt. Count articles by category, sentiment, future signals, and time to impact. Provide specific examples, data points, and strategic insights. Use the structured format with detailed sections, table, and comprehensive conclusion."""
            else:
                # Fall back to original SQL-based search logic
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
                    {"role": "user", "content": message}
                ]

                # Get search parameters from LLM
                try:
                    search_response = ai_model.generate_response(search_intent_messages)
                    logger.debug(f"LLM search response: {search_response}")
                    
                    json_str = self._extract_json_from_response_original(search_response)
                    logger.debug(f"Extracted JSON: {json_str}")
                    search_strategy = json.loads(json_str)
                    logger.debug(f"Search strategy: {json.dumps(search_strategy, indent=2)}")
                    
                    # Add null check for search_strategy
                    if not search_strategy or not search_strategy.get("queries"):
                        logger.warning(f"Invalid search strategy returned for message: {message}")
                        # Fallback to simple keyword search
                        articles, total_count = self.db.search_articles(
                            topic=topic,
                            keyword=message,
                            page=1,
                            per_page=limit
                        )
                        search_method = "fallback keyword search"
                    else:
                        all_articles = []
                        total_count = 0
                        
                        for query in search_strategy.get("queries", []):
                            if not query or not query.get("params"):
                                continue
                                
                            params = query["params"]
                            logger.debug(f"Executing query: {query['description']}")
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
                            if articles_batch:
                                all_articles.extend(articles_batch)
                                total_count += count
                        
                        # Remove duplicates based on article URI
                        seen_uris = set()
                        unique_articles = []
                        for article in all_articles:
                            if article and article.get('uri') and article['uri'] not in seen_uris:
                                seen_uris.add(article['uri'])
                                unique_articles.append(article)
                        
                        articles = unique_articles[:limit]  # Use user's selected limit
                        search_method = "structured keyword search"

                        # Format search criteria for display
                        active_filters = []
                        for query in search_strategy.get("queries", []):
                            params = query.get("params", {})
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
                    # Fallback to basic search
                    articles, total_count = self.db.search_articles(
                        topic=topic,
                        keyword=message,
                        page=1,
                        per_page=limit
                    )
                    search_method = "basic keyword search (fallback)"
                    search_summary = f"## Basic Search (Fallback)\nKeyword search for: {message}"

            # Format articles for context (original format)
            context = "\n\n".join([
                f"Title: {article['title']}\n"
                f"Summary: {article['summary']}\n"
                f"Category: {article['category']}\n"
                f"Future Signal: {article['future_signal']}\n"
                f"Sentiment: {article['sentiment']}\n"
                f"Time to Impact: {article['time_to_impact']}\n"
                f"Tags: {', '.join(article['tags']) if article.get('tags') else 'None'}\n"
                f"Publication Date: {article.get('publication_date', 'Unknown')}"
                + (f"\nSimilarity Score: {article.get('similarity_score', 'N/A')}" if 'similarity_score' in article else "")
                for article in articles
            ])

            # Build the final context in original format with sophisticated analysis instructions
            final_context = f"""
{search_summary}

Here are the {len(articles)} most relevant articles out of {total_count} total matches:

{context}

User Question: {message}

IMPORTANT ANALYSIS INSTRUCTIONS:
You MUST provide a comprehensive analysis with the following EXACT structure and format:

## Summary of Search Results

- **Total articles found in database for query:** {total_count}
- **Analyzed subset:** {len(articles)} most relevant articles
- **General category distribution (approximate):**
  [Provide detailed breakdown of categories with counts like "AI and Society: Several", "The Path to AGI: Multiple", etc.]

- **Sentiment distribution:**
  [Provide specific counts like "Positive: ~9", "Neutral: ~15", "Negative: ~3", etc.]

- **Future signal distribution among articles with this metadata:**
  [Provide breakdown like "AI will accelerate: ~18", "AI will evolve gradually: ~6", etc.]

- **Time to impact distribution:**
  [Provide breakdown like "Immediate: Few", "Short-term: Several", etc.]

---

## Future Impact Predictions Analysis

### 1. **General Trends in Future Signals**
[Analyze the dominant future signals and what they indicate about expectations]

### 2. **Time to Impact**
[Analyze the timing patterns and what they suggest about expected changes]

### 3. **Category-Specific Future Impact Insights**
[For each major category, provide detailed analysis of future signals, sentiment, and predictions]

### 4. **Notable Specific Predictions**
[List key specific predictions from the articles with timing and context]

---

## Summary Table of Future Impact Predictions by Key Dimensions

| Future Signal        | Time to Impact     | Category(s)                  | Sentiment        | Key Themes                                   |
|----------------------|--------------------|-----------------------------|------------------|----------------------------------------------|
[Create detailed table organizing the predictions by these dimensions]

---

## Conclusion

[Provide strategic insights about the overall patterns, implications, and future trajectory based on the analysis]

CRITICAL: Count and categorize the articles carefully. Use specific numbers and approximations. Analyze the strategic foresight data (categories, sentiments, future signals, time to impact) systematically. Provide actionable insights for decision-makers."""

            logger.debug(f"Sending {len(articles)} articles to LLM for analysis using {search_method}")
            return final_context

        except Exception as e:
            logger.error(f"Error in original chat database logic: {e}")
            # Fallback: Try simple search as last resort
            try:
                articles, count = self.db.search_articles(
                    topic=topic,
                    keyword=message,
                    page=1,
                    per_page=limit
                )
                if articles:
                    return f"""## Fallback Search Results
Found {count} articles using simple keyword search for "{message}" in topic {topic}.

## Articles Summary
{self._format_articles_summary(articles[:limit], "fallback search")}

INSTRUCTIONS: Analyze these articles using the EXACT format template provided in your system prompt."""
                else:
                    return f"""## No Results Found
No articles found for query "{message}" in topic {topic}. 

Please try:
- Using different keywords
- Checking if the topic has articles in the database
- Using a broader search term

You can ask me for help with alternative search strategies."""
            except Exception as fallback_error:
                logger.error(f"Fallback search also failed: {fallback_error}")
                return f"""## Search Error
I encountered an error while searching for "{message}" in topic {topic}. 

Error details: {str(e)}

Please try rephrasing your question or contact support if the issue persists."""

    def _select_diverse_articles_original(self, articles, limit):
        """Original select_diverse_articles function from chat_routes.py"""
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

    def _extract_json_from_response_original(self, response: str) -> str:
        """Original extract_json_from_response function from chat_routes.py"""
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
            
        except Exception as e:
            logger.error(f"Error in comprehensive data gathering: {e}")
            return None

    def _determine_search_strategy(self, message: str, topic_options: Dict) -> List[Dict]:
        """Determine database search strategy based on message content and available options."""
        strategies = []
        message_lower = message.lower()
        
        # Check for trend analysis
        if any(word in message_lower for word in ["trend", "pattern", "over time", "temporal"]):
            strategies.append({
                "description": "Trend analysis - all recent articles",
                "params": {
                    "category": None,
                    "keyword": None,
                    "sentiment": None,
                    "future_signal": None,
                    "tags": None,
                    "date_range": "90"
                }
            })
        
        # Check for category-specific requests
        for category in topic_options.get('categories', []):
            if category.lower() in message_lower:
                strategies.append({
                    "description": f"Category-specific search: {category}",
                    "params": {
                        "category": [category],
                        "keyword": None,
                        "sentiment": None,
                        "future_signal": None,
                        "tags": None,
                        "date_range": "30"
                    }
                })
                break
        
        # Check for sentiment-specific requests
        for sentiment in topic_options.get('sentiments', []):
            if sentiment.lower() in message_lower:
                strategies.append({
                    "description": f"Sentiment-specific search: {sentiment}",
                    "params": {
                        "category": None,
                        "keyword": None,
                        "sentiment": sentiment,
                        "future_signal": None,
                        "tags": None,
                        "date_range": "30"
                    }
                })
                break
        
        # Check for future signal requests
        for signal in topic_options.get('futureSignals', []):
            if signal.lower() in message_lower:
                strategies.append({
                    "description": f"Future signal search: {signal}",
                    "params": {
                        "category": None,
                        "keyword": None,
                        "sentiment": None,
                        "future_signal": signal,
                        "tags": None,
                        "date_range": "60"
                    }
                })
                break
        
        # Default keyword search if no specific strategy found
        if not strategies:
            strategies.append({
                "description": "General keyword search",
                "params": {
                    "category": None,
                    "keyword": message,
                    "sentiment": None,
                    "future_signal": None,
                    "tags": None,
                    "date_range": "30"
                }
            })
        
        return strategies

    def _select_diverse_articles(self, articles: List[Dict], limit: int) -> List[Dict]:
        """Select diverse articles from a larger pool based on category, source, and relevance."""
        if len(articles) <= limit:
            return articles
        
        # Sort by similarity score first (best matches first)
        sorted_articles = sorted(articles, key=lambda x: x.get('similarity_score', 1.0))
        
        selected = []
        seen_categories = set()
        seen_sources = set()
        
        # First pass: Select top articles ensuring diversity
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

    def _format_articles_summary(self, articles: List[Dict], search_type: str) -> str:
        """Format articles into a structured summary for the LLM."""
        if not articles:
            return f"No articles found via {search_type}"
        
        # Calculate statistics
        total_articles = len(articles)
        unique_sources = len(set(article.get('news_source', 'Unknown') for article in articles))
        
        # Date range
        dates = [article.get('publication_date') for article in articles if article.get('publication_date')]
        date_range = f"from {min(dates)} to {max(dates)}" if dates else "unknown date range"
        
        # Category distribution
        categories = {}
        for article in articles:
            cat = article.get('category', 'Unknown')
            categories[cat] = categories.get(cat, 0) + 1
        
        # Sentiment distribution
        sentiments = {}
        for article in articles:
            sent = article.get('sentiment', 'Unknown')
            sentiments[sent] = sentiments.get(sent, 0) + 1
        
        # Format summary
        summary = f"""Search Method: {search_type}
Total Articles: {total_articles}
Unique Sources: {unique_sources}
Date Range: {date_range}

Category Distribution:
{chr(10).join([f"- {cat}: {count} articles ({count/total_articles*100:.1f}%)" for cat, count in categories.items()])}

Sentiment Distribution:
{chr(10).join([f"- {sent}: {count} articles ({count/total_articles*100:.1f}%)" for sent, count in sentiments.items()])}

Article Details:
{chr(10).join([
    f"[{i+1}] {article['title'][:100]}..." + 
    f"\\n    Category: {article.get('category', 'N/A')} | Sentiment: {article.get('sentiment', 'N/A')}" +
    f" | Future Signal: {article.get('future_signal', 'N/A')}" +
    (f" | Similarity: {article.get('similarity_score', 0):.3f}" if 'similarity_score' in article else "") +
    f"\\n    Summary: {article.get('summary', 'No summary')[:200]}..."
    for i, article in enumerate(articles[:10])  # Show first 10 articles
])}
{f'\\n... and {len(articles) - 10} more articles' if len(articles) > 10 else ''}"""
        
        return summary

    async def _generate_streaming_response(self, messages: List[Dict], model: str) -> AsyncGenerator[str, None]:
        """Generate streaming response from LLM."""
        try:
            # Create the streaming response
            response_stream = await litellm.acompletion(
                model=model,
                messages=messages,
                stream=True,
                temperature=0.7,
                max_tokens=2000
            )
            
            # Handle the async generator properly
            async for chunk in response_stream:
                try:
                    # Check if chunk has the expected structure
                    if (hasattr(chunk, 'choices') and 
                        len(chunk.choices) > 0 and 
                        hasattr(chunk.choices[0], 'delta') and 
                        hasattr(chunk.choices[0].delta, 'content') and
                        chunk.choices[0].delta.content is not None):
                        yield chunk.choices[0].delta.content
                except AttributeError as attr_err:
                    logger.warning(f"Unexpected chunk structure: {attr_err}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error generating streaming response: {e}")
            yield f"Error generating response: {str(e)}"

    def get_system_prompt(self, prompt_name: str = None) -> Dict:
        """Get system prompt for Auspex."""
        try:
            if prompt_name:
                prompt = self.db.get_auspex_prompt(prompt_name)
            else:
                prompt = self.db.get_default_auspex_prompt()
            
            if not prompt:
                # Return default if none found
                return {
                    "name": "default",
                    "title": "Default Auspex Assistant", 
                    "content": DEFAULT_AUSPEX_PROMPT
                }
            
            return prompt
        except Exception as e:
            logger.error(f"Error getting system prompt: {e}")
            return {
                "name": "default",
                "title": "Default Auspex Assistant",
                "content": DEFAULT_AUSPEX_PROMPT
            }

    def get_all_prompts(self) -> List[Dict]:
        """Get all available Auspex prompts."""
        try:
            return self.db.get_auspex_prompts()
        except Exception as e:
            logger.error(f"Error getting prompts: {e}")
            return []

    def create_prompt(self, name: str, title: str, content: str, description: str = None, user_created: str = None) -> int:
        """Create a new Auspex prompt."""
        try:
            return self.db.create_auspex_prompt(
                name=name,
                title=title,
                content=content,
                description=description,
                user_created=user_created
            )
        except Exception as e:
            logger.error(f"Error creating prompt: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create prompt")

    def update_prompt(self, name: str, title: str = None, content: str = None, description: str = None) -> bool:
        """Update an Auspex prompt."""
        try:
            return self.db.update_auspex_prompt(
                name=name,
                title=title,
                content=content,
                description=description
            )
        except Exception as e:
            logger.error(f"Error updating prompt: {e}")
            return False

    def delete_prompt(self, name: str) -> bool:
        """Delete an Auspex prompt."""
        try:
            return self.db.delete_auspex_prompt(name)
        except Exception as e:
            logger.error(f"Error deleting prompt: {e}")
            return False

    # Keep existing suggest_options method for backward compatibility
    def suggest_options(self, kind: str, scenario_name: str, scenario_description: str = None) -> List[str]:
        """Ask the LLM for a short list of options suitable for the given building-block kind."""
        # Background context for strategic foresight
        BACKGROUND_SNIPPET = (
            "AuNoo follows strategic-foresight methodology.\n"
            "Categories: thematic sub-clusters inside a topic.\n"
            "Future Signals: concise hypotheses about possible future states.\n"
            "Sentiments: Positive / Neutral / Negative plus nuanced variants.\n"
            "Time to Impact: Immediate; Short-Term (3-18m); Mid-Term (18-60m); "
            "Long-Term (5y+).\n"
            "Driver Types: Accelerators, Blockers, Catalysts, Delayers, Initiators, "
            "Terminators."
        )

        # Map block kind to extra context
        KIND_CONTEXT = {
            "categorization": (
                "Focus on concrete thematic clusters relevant to the scenario."
            ),
            "sentiment": (
                "Use Positive / Negative / Neutral or nuanced variants where helpful."
            ),
            "relationship": (
                "Think in terms of blocker, catalyst, accelerator, "
                "initiator or supporting datapoint."
            ),
            "weighting": (
                "Return objective scale descriptors "
                "(e.g., Highly objective, Anecdotal)."
            ),
            "classification": "Propose discrete, mutually exclusive classes.",
            "summarization": "No additional options required.",
            "keywords": "Return succinct single- or two-word tags.",
        }

        prompt_parts = [
            BACKGROUND_SNIPPET,
            KIND_CONTEXT.get(kind.lower(), ""),
            (
                "Generate a concise comma-separated list of options "
                f"for a building-block of type '{kind}'."
            ),
            f"Scenario name: {scenario_name}.",
        ]
        
        if scenario_description:
            prompt_parts.append(f"Scenario description: {scenario_description}.")

        prompt_parts.append(
            "Return ONLY the list in plain text, no numbering, no explanations.",
        )

        prompt = "\n".join(prompt_parts)

        try:
            response = litellm.completion(model=DEFAULT_MODEL, messages=[{"role": "user", "content": prompt}])
            text = response.choices[0].message["content"].strip()
            options = [o.strip() for o in text.replace("\n", ",").split(",") if o.strip()]
            if not options:
                raise ValueError("LLM returned empty list")
            return options[:10]
        except Exception as exc:
            logger.error("Auspex LLM call failed: %s", exc)
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="LLM suggestion failed") from exc

# Global service instance
_service_instance = None

def get_auspex_service() -> AuspexService:
    """Get the global Auspex service instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = AuspexService()
    return _service_instance 