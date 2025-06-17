import asyncio
import json
import logging
from typing import Dict, List, Optional, AsyncGenerator
from datetime import datetime

from fastapi import HTTPException, status
import litellm
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.database import get_database_instance
from app.services.auspex_tools import get_auspex_tools_service

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-3.5-turbo"

# Default system prompt for Auspex
DEFAULT_AUSPEX_PROMPT = """You are Auspex, an advanced AI research assistant specialized in analyzing news trends, sentiment patterns, and providing strategic insights.

Your capabilities include:
- Analyzing vast amounts of news data and research
- Identifying emerging trends and patterns
- Providing sentiment analysis and future impact predictions
- Accessing real-time news data through specialized tools
- Comparing different categories and topics
- Offering strategic foresight and risk analysis
- Performing semantic search with diversity filtering
- Conducting structured analysis with comprehensive insights
- Making follow-up queries for deeper investigation

You have access to the following tools:
- search_news: Search for current news articles (PRIORITIZED for "latest/recent" queries)
- get_topic_articles: Retrieve articles from the database for specific topics
- analyze_sentiment_trends: Analyze sentiment patterns over time
- get_article_categories: Get category distributions for topics
- search_articles_by_keywords: Search articles by specific keywords
- semantic_search_and_analyze: Perform comprehensive semantic search with diversity filtering and structured analysis
- follow_up_query: Conduct follow-up searches based on previous results for deeper insights

DATA SOURCE UNDERSTANDING:
- **Database Articles**: Pre-collected articles with enriched metadata including sentiment analysis, category classification, and relevance scores
- **Real-time News**: Fresh articles from news APIs with basic metadata
- **Tool-based Analysis**: Dynamic sentiment/category analysis performed on-demand across multiple articles
- **Semantic Analysis**: Structured analysis with diversity filtering, key themes extraction, and temporal distribution

When tool data is provided to you, it will be clearly marked at the beginning of your context. Always acknowledge when you're using tool data and explain what insights you're drawing from it.

CRITICAL PRIORITIES:
- When users ask for "latest", "recent", "current", or "breaking" news, prioritize real-time news search results
- For comprehensive analysis, use semantic_search_and_analyze for structured insights with diversity filtering
- When users want deeper investigation, use follow_up_query to explore specific aspects
- Clearly distinguish between real-time news data and database/historical data
- If news search provides results, focus primarily on those for latest information queries
- Only use database articles as fallback when news search fails or for historical analysis

RESPONSE FORMAT: When you receive tool results, always:
1. **IMMEDIATELY** identify the data source (Latest News Search vs Database Articles vs Semantic Analysis)
2. Acknowledge which tools were used (you'll see a "Tools Used" section)
3. Summarize the key findings from the tool data
4. Provide your analysis and insights based on this data
5. Be transparent about what the data shows vs. your interpretation
6. For sentiment analysis, clarify whether you're using individual article sentiments or aggregate tool-based analysis
7. Present structured analysis results clearly with key themes, temporal patterns, and insights

STRUCTURED ANALYSIS CAPABILITIES:
- **Diversity Filtering**: Ensuring varied sources and categories for comprehensive coverage
- **Key Themes Extraction**: Identifying main topics and trending subjects
- **Temporal Distribution**: Understanding timing patterns and peak activity periods
- **Sentiment Breakdown**: Comprehensive sentiment analysis with percentages
- **Source Analysis**: Evaluating source diversity and credibility
- **Follow-up Investigation**: Ability to drill down into specific aspects of findings

FOLLOW-UP QUERY USAGE:
- Use follow_up_query when users ask for more details about specific findings
- When initial results suggest interesting patterns that warrant deeper investigation
- To explore different angles or aspects of a topic based on previous results
- To find related content using context from previous searches

Always provide thorough, insightful analysis backed by data. When asked about trends or patterns, use your tools to gather current information. Be concise but comprehensive in your responses.

Remember to cite your sources and provide actionable insights where possible."""

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

    async def chat_with_tools(self, chat_id: int, message: str, model: str = None, limit: int = 50) -> AsyncGenerator[str, None]:
        """Chat with Auspex using MCP tools."""
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
            
            # Get system prompt
            system_prompt = self.get_system_prompt()
            
            # Prepare messages with system prompt
            llm_messages = [
                {"role": "system", "content": system_prompt['content']},
                *conversation
            ]
            
            # Check if we need to use tools based on the message content
            needs_tools = await self._should_use_tools(message)
            
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
                metadata={"used_tools": needs_tools}
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
                    metadata={"error": True}
                )
            except:
                pass

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
        """Use MCP tools to gather information."""
        logger.info(f"_use_mcp_tools called for message: '{message}', chat_id: {chat_id}")
        
        try:
            # Get chat info to determine topic
            chat = self.db.get_auspex_chat(chat_id)
            if not chat:
                logger.error(f"Chat not found for chat_id: {chat_id}")
                return None
                
            topic = chat['topic']
            logger.info(f"Chat topic: {topic}")
            
            # Determine which tools to use based on message content
            tool_results = []
            tools_used = []
            
            # Check for comprehensive analysis requests
            asking_for_comprehensive = any(word in message.lower() for word in [
                "comprehensive", "detailed", "thorough", "analysis", "deep", "structured"
            ])
            
            # Check for follow-up requests
            asking_for_followup = any(phrase in message.lower() for phrase in [
                "follow up", "more details", "expand", "elaborate", "tell me more", "dig deeper"
            ])
            
            # Check if user is asking for latest/recent news
            asking_for_news = any(word in message.lower() for word in ["latest", "recent", "current", "new", "breaking"])
            logger.info(f"Analysis type - News: {asking_for_news}, Comprehensive: {asking_for_comprehensive}, Follow-up: {asking_for_followup}")
            
            # Handle comprehensive analysis with semantic search
            if asking_for_comprehensive:
                logger.info("Using semantic search and analysis...")
                try:
                    result = await self.tools.semantic_search_and_analyze(
                        query=message,
                        topic=topic,
                        analysis_type="comprehensive",
                        limit=limit
                    )
                    if 'error' not in result:
                        tools_used.append("🔍 Semantic Analysis")
                        tool_results.append(f"**Comprehensive Semantic Analysis:**\n{json.dumps(result, indent=2)}")
                        logger.info("Semantic analysis successful")
                    else:
                        tool_results.append(f"⚠️ Semantic analysis failed: {result['error']}")
                except Exception as e:
                    logger.error(f"Error using semantic analysis tool: {e}")
                    tool_results.append(f"⚠️ Semantic analysis error: {str(e)}")
            
            # Handle follow-up queries
            elif asking_for_followup:
                logger.info("Using follow-up query tool...")
                try:
                    # Get previous messages for context
                    chat_messages = self.db.get_auspex_messages(chat_id)
                    previous_user_messages = [msg for msg in chat_messages if msg['role'] == 'user']
                    
                    if len(previous_user_messages) > 1:
                        original_query = previous_user_messages[-2]['content']  # Previous user message
                        
                        result = await self.tools.follow_up_query(
                            original_query=original_query,
                            follow_up=message,
                            topic=topic
                        )
                        if 'error' not in result:
                            tools_used.append("🔄 Follow-up Query")
                            tool_results.append(f"**Follow-up Query Results:**\n{json.dumps(result, indent=2)}")
                            logger.info("Follow-up query successful")
                        else:
                            tool_results.append(f"⚠️ Follow-up query failed: {result['error']}")
                    else:
                        # Fall back to semantic search if no previous context
                        result = await self.tools.semantic_search_and_analyze(
                            query=message,
                            topic=topic,
                            analysis_type="focused",
                            limit=min(limit, 25)
                        )
                        if 'error' not in result:
                            tools_used.append("🔍 Focused Analysis")
                            tool_results.append(f"**Focused Analysis:**\n{json.dumps(result, indent=2)}")
                except Exception as e:
                    logger.error(f"Error using follow-up query tool: {e}")
                    tool_results.append(f"⚠️ Follow-up query error: {str(e)}")
            
            # Handle latest news requests
            elif asking_for_news:
                logger.info("Attempting to use news search tool...")
                # Prioritize news search for latest information
                try:
                    result = await self.tools.search_news(
                        query=f"{topic} {message}",  # Include user query for better relevance
                        max_results=min(limit, 15),
                        days_back=3  # More recent for "latest" queries
                    )
                    logger.info(f"News search result: {result}")
                    
                    if 'error' not in result and result.get('total_results', 0) > 0:
                        tools_used.append("🔍 Latest News Search")
                        tool_results.append(f"**Latest News Search Results (Primary Source):**\n{json.dumps(result, indent=2)}")
                        logger.info("News search successful")
                    else:
                        logger.warning(f"News search failed or returned no results: {result}")
                        tool_results.append(f"⚠️ Latest news search failed: {result.get('error', 'No recent articles found')}")
                        # Fall back to semantic search for structured analysis
                        try:
                            logger.info("Falling back to semantic analysis...")
                            db_result = await self.tools.semantic_search_and_analyze(
                                query=message,
                                topic=topic,
                                analysis_type="focused",
                                limit=min(limit, 25)
                            )
                            if 'error' not in db_result:
                                tools_used.append("📄 Semantic Fallback")
                                tool_results.append(f"**Semantic Analysis (Fallback):**\n{json.dumps(db_result, indent=2)}")
                                logger.info("Semantic fallback successful")
                        except Exception as e:
                            logger.error(f"Error using semantic fallback: {e}")
                except Exception as e:
                    logger.error(f"Error using search_news tool: {e}")
                    tool_results.append(f"⚠️ News search error: {str(e)}")
            else:
                logger.info("Using semantic search as primary source...")
                # For general queries, use semantic search with structured analysis
                try:
                    result = await self.tools.semantic_search_and_analyze(
                        query=message,
                        topic=topic,
                        analysis_type="comprehensive",
                        limit=limit
                    )
                    if 'error' not in result:
                        tools_used.append("🔍 Semantic Search")
                        tool_results.append(f"**Semantic Search & Analysis:**\n{json.dumps(result, indent=2)}")
                        logger.info("Semantic search successful")
                    else:
                        logger.warning(f"Semantic search failed: {result['error']}")
                        # Fall back to basic topic articles
                        try:
                            logger.info("Falling back to basic topic articles...")
                            db_result = await self.tools.get_topic_articles(
                                topic=topic,
                                limit=min(limit, 25),
                                days_back=30
                            )
                            if 'error' not in db_result:
                                tools_used.append("📄 Topic Articles")
                                tool_results.append(f"**Topic Articles Database:**\n{json.dumps(db_result, indent=2)}")
                                logger.info("Basic fallback successful")
                        except Exception as e:
                            logger.error(f"Error using basic fallback: {e}")
                except Exception as e:
                    logger.error(f"Error using semantic search tool: {e}")
                    tool_results.append(f"⚠️ Semantic search error: {str(e)}")
            
            # Handle sentiment analysis requests
            if any(word in message.lower() for word in ["sentiment", "feeling", "opinion", "mood"]):
                logger.info("Adding sentiment analysis...")
                try:
                    result = await self.tools.analyze_sentiment_trends(
                        topic=topic,
                        time_period="month"
                    )
                    if 'error' not in result:
                        tools_used.append("📊 Sentiment Analysis")
                        tool_results.append(f"**Sentiment Analysis Results:**\n{json.dumps(result, indent=2)}")
                    else:
                        tool_results.append(f"⚠️ Sentiment analysis failed: {result['error']}")
                except Exception as e:
                    logger.error(f"Error using sentiment analysis tool: {e}")
                    tool_results.append(f"⚠️ Sentiment analysis error: {str(e)}")
            
            # Handle category analysis requests
            if any(word in message.lower() for word in ["categories", "types", "kinds", "distribution"]):
                logger.info("Adding category analysis...")
                try:
                    result = await self.tools.get_article_categories(topic=topic)
                    if 'error' not in result:
                        tools_used.append("📂 Category Analysis")
                        tool_results.append(f"**Category Analysis Results:**\n{json.dumps(result, indent=2)}")
                    else:
                        tool_results.append(f"⚠️ Category analysis failed: {result['error']}")
                except Exception as e:
                    logger.error(f"Error using categories tool: {e}")
                    tool_results.append(f"⚠️ Category analysis error: {str(e)}")
            
            # Add tools used summary at the beginning
            if tools_used:
                tool_summary = f"🔧 **Tools Used:** {', '.join(tools_used)}\n\n"
                tool_results.insert(0, tool_summary)
                logger.info(f"Final tool results: {len(tool_results)} sections")
            else:
                logger.warning("No tools were used!")
            
            final_result = "\n\n".join(tool_results) if tool_results else None
            logger.info(f"Returning tool results: {bool(final_result)}")
            return final_result
            
        except Exception as e:
            logger.error(f"Error using MCP tools: {e}")
            return None

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