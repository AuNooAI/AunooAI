from fastapi import APIRouter, status, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict
import json
import logging
from datetime import datetime

from app.services.auspex_service import get_auspex_service
from app.security.session import verify_session

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auspex", tags=["Auspex"])

async def identify_themes_from_articles(topic: str, timeframe_days: int, model: str = "gpt-4o-mini", limit: int = 50) -> List[str]:
    """Use AI to identify themes from actual article content through semantic analysis."""
    try:
        auspex = get_auspex_service()
        
        # First, get articles for semantic analysis - similar to how Auspex prompts work
        search_query = f"Find articles about {topic} from the last {timeframe_days} days to analyze content and identify emerging themes"
        
        # Create a chat session for theme discovery
        chat_id = await auspex.create_chat_session(topic=topic, user_id=None, title="Theme Discovery")
        
        logger.info(f"Starting semantic theme discovery for topic: {topic}, timeframe: {timeframe_days} days, model: {model}, limit: {limit}")
        
        # Step 1: Search and retrieve articles for analysis
        search_response = ""
        async for chunk in auspex.chat_with_tools(
            chat_id=chat_id, 
            message=search_query,
            model=model,
            limit=limit,
            tools_config={"search_articles": True, "get_sentiment_analysis": False}
        ):
            search_response += chunk
        
        logger.info(f"Retrieved articles for theme analysis: {len(search_response)} characters")
        
        # Step 2: Analyze the actual article content to discover themes
        theme_analysis_prompt = f"""
        Based on the articles retrieved above about "{topic}", perform semantic content analysis to identify 3-5 distinct themes that emerge from the actual article content.

        IMPORTANT: Analyze the ACTUAL CONTENT of the articles, not predefined categories. Look for:
        
        1. **Semantic Clustering**: Group articles by similar concepts, topics, and discussion patterns
        2. **Emergent Themes**: Identify themes that emerge from the content itself, not from external categorization
        3. **Content Patterns**: Look for recurring subjects, concerns, applications, or developments mentioned across articles
        4. **Discussion Trends**: Identify what people are actually talking about and debating

        Focus on themes that represent distinct areas of discussion with different consensus patterns:
        - Specific application domains or use cases being discussed
        - Particular concerns or challenges that emerge from the content  
        - Technical developments or breakthroughs mentioned
        - Policy/regulatory discussions in the articles
        - Economic or business impacts covered
        - Social or ethical considerations raised

        Generate theme names that reflect the ACTUAL CONTENT being discussed, not generic categories.

        Return ONLY a JSON array of theme names derived from the article content, like:
        ["Theme Based on Content 1", "Theme Based on Content 2", "Theme Based on Content 3"]

        Each theme should represent a distinct cluster of related article content.
        """
        
        logger.info(f"Analyzing article content to discover themes...")
        
        theme_response = ""
        async for chunk in auspex.chat_with_tools(
            chat_id=chat_id, 
            message=theme_analysis_prompt,
            model=model,
            limit=10,  # Small limit for analysis
            tools_config={"search_articles": False, "get_sentiment_analysis": False}
        ):
            theme_response += chunk
        
        logger.info(f"Theme analysis response length: {len(theme_response)}")
        logger.info(f"Theme analysis response: {theme_response}")
        
        # Clean up the chat session
        auspex.delete_chat_session(chat_id)
        
        # Parse the JSON response from semantic analysis
        import json
        import re
        
        # Extract JSON array from response - try multiple patterns
        json_patterns = [
            r'```json\s*(\[.*?\])\s*```',  # JSON code block (try first)
            r'\[([^\]]+)\]',              # Original pattern
            r'\[(.*?)\]',                 # More flexible pattern  
            r'(\[.*?\])'                  # Simple array pattern
        ]
        
        themes = None
        for pattern in json_patterns:
            json_match = re.search(pattern, theme_response, re.DOTALL)
            if json_match:
                try:
                    json_str = json_match.group(1) if len(json_match.groups()) > 0 else json_match.group(0)
                    if not json_str.startswith('['):
                        json_str = '[' + json_str + ']'
                    themes = json.loads(json_str)
                    if isinstance(themes, list) and len(themes) > 0:
                        # Filter out empty or very short theme names
                        valid_themes = [theme.strip() for theme in themes if theme and len(theme.strip()) > 5]
                        logger.info(f"Semantically discovered themes for {topic}: {valid_themes}")
                        return valid_themes[:5]  # Limit to 5 themes max
                except (json.JSONDecodeError, IndexError) as e:
                    logger.debug(f"Failed to parse JSON with pattern {pattern}: {e}")
                    continue
        
        logger.warning(f"Could not parse themes from semantic analysis response: {theme_response[:500]}...")
        
        # Fallback: try to extract theme-like phrases from the response text
        fallback_themes = []
        theme_patterns = [
            r'(?:theme|topic|area|domain|focus)(?:\s+\d+)?:\s*([^.\n]+)',
            r'[\"\']([^\"\']{10,50})[\"\']',  # Quoted phrases
            r'(?:^|\n)\s*[-•]\s*([^.\n]{10,50})',  # Bullet points
        ]
        
        for pattern in theme_patterns:
            matches = re.findall(pattern, theme_response, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                clean_theme = match.strip().strip('.,;:')
                if len(clean_theme) > 5 and clean_theme not in fallback_themes:
                    fallback_themes.append(clean_theme)
                if len(fallback_themes) >= 5:
                    break
            if len(fallback_themes) >= 5:
                break
        
        if fallback_themes:
            logger.info(f"Fallback themes extracted from content: {fallback_themes}")
            return fallback_themes
        
        return []
        
    except Exception as e:
        logger.error(f"Error identifying themes: {e}")
        return []

# Request/Response Models
class SuggestRequest(BaseModel):
    kind: str = Field(...)
    scenario_name: str = Field(...)
    scenario_description: str | None = None

class ConsensusAnalysisRequest(BaseModel):
    topic: str = Field(..., description="Topic to analyze for consensus")
    timeframe: str = Field("365d", description="Analysis timeframe")
    categories: List[str] | None = Field(None, description="Optional category filter")
    categoryMode: str = Field("existing", description="Category mode: 'existing', 'thematic', or 'custom'")
    model: str = Field("gpt-4o-mini", description="AI model to use for analysis")
    articleLimit: int = Field(100, description="Number of articles to analyze")

    @field_validator('topic')
    @classmethod
    def sanitize_topic(cls, v: str) -> str:
        """Sanitize topic name - strip whitespace and normalize spaces."""
        if v:
            import re
            return re.sub(r'\s+', ' ', v.strip())
        return v

class ChatSessionRequest(BaseModel):
    topic: str = Field(..., description="Topic for the chat session")
    title: str | None = Field(None, description="Optional title for the chat")
    profile_id: int | None = Field(None, description="Organizational profile ID for contextualized analysis")

    @field_validator('topic')
    @classmethod
    def sanitize_topic(cls, v: str) -> str:
        """Sanitize topic name - strip whitespace and normalize spaces."""
        if v:
            import re
            return re.sub(r'\s+', ' ', v.strip())
        return v

class ChatMessageRequest(BaseModel):
    chat_id: int = Field(..., description="Chat session ID")
    message: str = Field(..., description="User message")
    model: str | None = Field(None, description="Model to use for response")
    limit: int | None = Field(50, description="Number of articles to retrieve and analyze (max articles to search for)")
    tools_config: dict | None = Field(None, description="Individual tool configuration settings")
    profile_id: int | None = Field(None, description="Organizational profile ID for contextualized analysis")
    custom_prompt: str | None = Field(None, description="Custom system prompt to override the default template")
    article_detail_limit: int | None = Field(
        None,
        ge=5,
        le=300,
        description=(
            "Number of articles to include in detailed citation context. "
            "If not specified, defaults to 25. "
            "Range: 5-300. Examples: 10 (quick), 25 (standard), 50 (deep), 100+ (comprehensive)"
        )
    )

class PromptRequest(BaseModel):
    name: str = Field(..., description="Unique prompt name")
    title: str = Field(..., description="Display title")
    content: str = Field(..., description="Prompt content")
    description: str | None = Field(None, description="Optional description")

class PromptUpdateRequest(BaseModel):
    title: str | None = Field(None, description="Updated title")
    content: str | None = Field(None, description="Updated content")
    description: str | None = Field(None, description="Updated description")

# Legacy endpoint for backward compatibility
@router.post("/block-options", status_code=status.HTTP_200_OK)
async def suggest_block_options(req: SuggestRequest, session=Depends(verify_session)):
    """Return list of option suggestions for a building-block."""
    auspex = get_auspex_service()
    return {
        "options": auspex.suggest_options(req.kind, req.scenario_name, req.scenario_description),
    }

# Chat Session Management
@router.post("/chat/sessions", status_code=status.HTTP_201_CREATED)
async def create_chat_session(req: ChatSessionRequest, session=Depends(verify_session)):
    """Create a new Auspex chat session with optional organizational profile."""
    logger.info(f"Creating chat session for topic: {req.topic}, title: {req.title}, profile_id: {req.profile_id}")
    
    auspex = get_auspex_service()
    user_id = session.get('user')  # Get user from session
    logger.info(f"User ID: {user_id}")
    
    chat_id = await auspex.create_chat_session(
        topic=req.topic,
        user_id=user_id,
        title=req.title,
        profile_id=req.profile_id
    )
    
    logger.info(f"Created chat session with ID: {chat_id}, profile: {req.profile_id}")
    
    return {
        "chat_id": chat_id,
        "topic": req.topic,
        "title": req.title or f"Chat about {req.topic}",
        "profile_id": req.profile_id,
        "message": "Chat session created successfully"
    }

@router.get("/chat/sessions", status_code=status.HTTP_200_OK)
async def get_chat_sessions(
    topic: Optional[str] = None,
    limit: int = 50,
    session=Depends(verify_session)
):
    """Get user's chat sessions."""
    auspex = get_auspex_service()
    user_from_session = session.get('user')

    # Handle OAuth users (stored as dicts) vs regular users (strings)
    if isinstance(user_from_session, dict):
        user_id = None  # OAuth users don't have user_id in database
    else:
        user_id = user_from_session

    sessions = auspex.get_chat_sessions(topic=topic, user_id=user_id, limit=limit)
    return {
        "sessions": sessions,
        "total": len(sessions)
    }

@router.get("/chat/sessions/{chat_id}/messages", status_code=status.HTTP_200_OK)
async def get_chat_history(chat_id: int, session=Depends(verify_session)):
    """Get chat history for a session."""
    auspex = get_auspex_service()

    # Verify user owns this chat
    chat_info = auspex.db.get_auspex_chat(chat_id)
    if not chat_info:
        raise HTTPException(status_code=404, detail="Chat session not found")

    user_from_session = session.get('user')
    # Handle OAuth users (stored as dicts) vs regular users (strings)
    if isinstance(user_from_session, dict):
        user_id = None  # OAuth users don't have user_id in database
    else:
        user_id = user_from_session

    # Allow access if chat has no user_id (public/OAuth) or if user_id matches
    if chat_info['user_id'] is not None and chat_info['user_id'] != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    messages = auspex.get_chat_history(chat_id)
    # Filter out system messages for client
    user_messages = [msg for msg in messages if msg['role'] != 'system']
    
    return {
        "chat_id": chat_id,
        "messages": user_messages,
        "total_messages": len(user_messages)
    }

@router.delete("/chat/sessions/{chat_id}", status_code=status.HTTP_200_OK)
async def delete_chat_session(chat_id: int, session=Depends(verify_session)):
    """Delete a chat session."""
    auspex = get_auspex_service()

    # Verify user owns this chat
    chat_info = auspex.db.get_auspex_chat(chat_id)
    if not chat_info:
        raise HTTPException(status_code=404, detail="Chat session not found")

    user_from_session = session.get('user')
    # Handle OAuth users (stored as dicts) vs regular users (strings)
    if isinstance(user_from_session, dict):
        user_id = None  # OAuth users don't have user_id in database
    else:
        user_id = user_from_session

    # Allow access if chat has no user_id (public/OAuth) or if user_id matches
    if chat_info['user_id'] is not None and chat_info['user_id'] != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    success = auspex.delete_chat_session(chat_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete chat session")
    
    return {"message": "Chat session deleted successfully"}

# Chat Messaging
@router.post("/chat/message", status_code=status.HTTP_200_OK)
async def send_chat_message(req: ChatMessageRequest, session=Depends(verify_session)):
    """Send a message to Auspex and get streaming response with configurable citation depth."""
    logger.info(
        f"Received chat message - chat_id: {req.chat_id}, message: '{req.message}', "
        f"model: {req.model}, limit: {req.limit}, article_detail_limit: {req.article_detail_limit}"
    )
    
    auspex = get_auspex_service()
    
    # Verify user owns this chat
    chat_info = auspex.db.get_auspex_chat(req.chat_id)
    if not chat_info:
        logger.error(f"Chat session not found for chat_id: {req.chat_id}")
        raise HTTPException(status_code=404, detail="Chat session not found")

    user_from_session = session.get('user')
    # Handle OAuth users (stored as dicts) vs regular users (strings)
    if isinstance(user_from_session, dict):
        user_id = None  # OAuth users don't have user_id in database
    else:
        user_id = user_from_session

    # Allow access if chat has no user_id (public/OAuth) or if user_id matches
    if chat_info['user_id'] is not None and chat_info['user_id'] != user_id:
        logger.error(f"Access denied - user {user_id} trying to access chat owned by {chat_info['user_id']}")
        raise HTTPException(status_code=403, detail="Access denied")
    
    logger.info(f"Chat verification successful - topic: {chat_info['topic']}, user: {user_id}")
    
    async def generate_response():
        """Generate streaming response with profile context."""
        try:
            logger.info(f"Starting chat_with_tools for chat_id: {req.chat_id}, profile_id: {req.profile_id}")
            
            # Update chat session with profile_id if provided
            if req.profile_id and req.profile_id != chat_info.get('profile_id'):
                logger.info(f"Updating chat session {req.chat_id} with profile_id: {req.profile_id}")
                # Update the chat session to include the profile_id
                auspex.db.update_auspex_chat_profile(req.chat_id, req.profile_id)
            
            async for chunk in auspex.chat_with_tools(req.chat_id, req.message, req.model, req.limit, req.tools_config, req.profile_id, req.custom_prompt, req.article_detail_limit):
                yield f"data: {json.dumps({'content': chunk})}\n\n"
            logger.info("Chat response completed successfully")
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as e:
            logger.error(f"Error in generate_response: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(
        generate_response(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream"
        }
    )

# Prompt Management
@router.get("/prompts", status_code=status.HTTP_200_OK)
async def get_prompts(session=Depends(verify_session)):
    """Get all available Auspex prompts."""
    auspex = get_auspex_service()
    prompts = auspex.get_all_prompts()
    
    return {
        "prompts": prompts,
        "total": len(prompts)
    }

@router.get("/prompts/{prompt_name}", status_code=status.HTTP_200_OK)
async def get_prompt(prompt_name: str, session=Depends(verify_session)):
    """Get a specific prompt."""
    auspex = get_auspex_service()
    prompt = auspex.get_system_prompt(prompt_name)
    
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    
    return prompt

@router.post("/prompts", status_code=status.HTTP_201_CREATED)
async def create_prompt(req: PromptRequest, session=Depends(verify_session)):
    """Create a new Auspex prompt."""
    auspex = get_auspex_service()
    user_id = session.get('user')
    
    try:
        prompt_id = auspex.create_prompt(
            name=req.name,
            title=req.title,
            content=req.content,
            description=req.description,
            user_created=user_id
        )
        
        return {
            "id": prompt_id,
            "name": req.name,
            "message": "Prompt created successfully"
        }
    except Exception as e:
        if "UNIQUE constraint failed" in str(e):
            raise HTTPException(status_code=400, detail="Prompt name already exists")
        raise HTTPException(status_code=500, detail="Failed to create prompt")

@router.put("/prompts/{prompt_name}", status_code=status.HTTP_200_OK)
async def update_prompt(prompt_name: str, req: PromptUpdateRequest, session=Depends(verify_session)):
    """Update an Auspex prompt."""
    auspex = get_auspex_service()
    
    # Check if prompt exists
    existing = auspex.get_system_prompt(prompt_name)
    if not existing:
        raise HTTPException(status_code=404, detail="Prompt not found")
    
    success = auspex.update_prompt(
        name=prompt_name,
        title=req.title,
        content=req.content,
        description=req.description
    )
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update prompt")
    
    return {"message": "Prompt updated successfully"}

@router.delete("/prompts/{prompt_name}", status_code=status.HTTP_200_OK)
async def delete_prompt(prompt_name: str, session=Depends(verify_session)):
    """Delete an Auspex prompt."""
    auspex = get_auspex_service()
    
    # Check if prompt exists and is not default
    existing = auspex.get_system_prompt(prompt_name)
    if not existing:
        raise HTTPException(status_code=404, detail="Prompt not found")
    
    if existing.get('is_default'):
        raise HTTPException(status_code=400, detail="Cannot delete default prompt")
    
    success = auspex.delete_prompt(prompt_name)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete prompt")
    
    return {"message": "Prompt deleted successfully"}

# Consensus Analysis
@router.post("/consensus-analysis", status_code=status.HTTP_200_OK)
async def get_consensus_analysis(req: ConsensusAnalysisRequest, session=Depends(verify_session)):
    """Get consensus analysis for a topic using Auspex AI."""
    logger.info(f"Generating consensus analysis for topic: {req.topic}, timeframe: {req.timeframe}")
    
    auspex = get_auspex_service()
    user_id = session.get('user')

    import time
    analysis_start_time = time.time()

    try:
        # Create a temporary chat session for the analysis
        chat_id = await auspex.create_chat_session(
            topic=req.topic,
            user_id=user_id,
            title=f"Consensus Analysis: {req.topic}"
        )
        
        # Get available categories for the topic
        tools = auspex.tools
        logger.info(f"Getting article categories for topic: {req.topic}")
        categories_data = await tools.get_article_categories(req.topic)
        category_distribution = categories_data.get("category_distribution", {})
        logger.info(f"Category distribution from database: {category_distribution}")
        logger.info(f"Total categories found: {len(category_distribution)}")
        
        # Determine which categories to analyze based on mode
        logger.info(f"Category mode: {req.categoryMode}")
        logger.info(f"User provided categories: {req.categories}")
        
        if req.categoryMode == "thematic":
            # Use AI to identify themes from articles
            logger.info("Using thematic analysis mode - AI will identify themes")
            timeframe_days = 365  # Default
            if req.timeframe.endswith('d'):
                try:
                    timeframe_days = int(req.timeframe[:-1])
                except ValueError:
                    timeframe_days = 365
            elif req.timeframe == 'all':
                timeframe_days = 3650  # 10 years for "all time"
                
            logger.info(f"Calling identify_themes_from_articles with topic='{req.topic}', timeframe_days={timeframe_days}, model={req.model}, limit={req.articleLimit}")
            target_categories = await identify_themes_from_articles(req.topic, timeframe_days, req.model, req.articleLimit)
            logger.info(f"identify_themes_from_articles returned: {target_categories}")
            
            if not target_categories:
                target_categories = ["General Analysis"]
                logger.info("No themes identified, using General Analysis fallback")
            else:
                logger.info(f"AI identified themes: {target_categories}")
        elif req.categories:
            # User specified categories - filter out null/empty ones
            target_categories = [cat for cat in req.categories if cat and cat.strip() and cat != 'null']
            logger.info(f"Using user-specified categories: {target_categories}")
        else:
            # Default to top 5 categories by article count - filter out null/empty ones
            logger.info("Using existing categories mode (default) - analyzing database categories")
            valid_categories = [(cat, count) for cat, count in category_distribution.items() 
                              if cat and cat.strip() and cat != 'null']
            logger.info(f"Valid categories after filtering: {valid_categories}")
            
            if not valid_categories:
                # No categories found - create a general analysis category
                logger.warning(f"No valid categories found for topic '{req.topic}' in database, using general analysis")
                logger.warning(f"Raw category distribution was: {category_distribution}")
                target_categories = ["General Analysis"]
            else:
                sorted_categories = sorted(valid_categories, key=lambda x: x[1], reverse=True)
                target_categories = [cat[0] for cat in sorted_categories[:5]]
                logger.info(f"Defaulting to top 5 categories by article count: {target_categories}")
                logger.info(f"Category distribution: {dict(sorted_categories[:5])}")
        
        # Ensure we have at least one category to analyze
        if not target_categories or len(target_categories) == 0:
            logger.warning("No target categories determined, using general analysis")
            target_categories = ["General Analysis"]
        
        # Filter out any None or empty string categories
        target_categories = [cat for cat in target_categories if cat and isinstance(cat, str) and cat.strip()]
        
        if not target_categories:
            logger.warning("All categories were invalid, using general analysis fallback")
            target_categories = ["General Analysis"]
        
        logger.info(f"Conducting per-category analysis for {len(target_categories)} categories: {target_categories}")
        
        # Conduct separate analysis for each category
        category_analyses = {}
        
        logger.info(f"Starting category analysis loop with categories: {target_categories}")
        
        for i, category in enumerate(target_categories):
            logger.info(f"Processing category {i+1}/{len(target_categories)}: '{category}'")
            logger.info(f"Analyzing category: {category}")
            
            # Convert timeframe to days for proper tool usage
            timeframe_days = 365  # Default
            if req.timeframe.endswith('d'):
                try:
                    timeframe_days = int(req.timeframe[:-1])
                except ValueError:
                    timeframe_days = 365
            elif req.timeframe == 'all':
                timeframe_days = 3650  # 10 years for "all time"
            
            # Special handling for "Trends" and "General Analysis" categories
            if category == "Trends":
                category_prompt = f"""
                Please conduct an AI-powered emerging trends analysis for the topic "{req.topic}" based on articles from the last {timeframe_days} days.

                IMPORTANT SEARCH INSTRUCTIONS:
                1. Search broadly across ALL articles in the "{req.topic}" topic from the last {timeframe_days} days
                2. Use AI analysis to identify emerging patterns, trends, and signals that may not fit into traditional categories
                3. Look for novel developments, cross-category patterns, and emerging themes
                4. Focus on identifying trends that are just beginning to surface or gain momentum

                For this trends analysis, analyze and return ONLY a valid JSON object with this exact structure:

                {{
                    "articles_analyzed": [number of articles found and analyzed],
                    "1_consensus_type": {{
                        "summary": "Emerging Trends",
                        "distribution": {{
                            "positive": [percentage of optimistic trend signals],
                            "neutral": [percentage of neutral trend signals], 
                            "critical": [percentage of concerning trend signals]
                        }}
                    }},
                    "2_timeline_consensus": {{
                        "summary": "[when these trends are expected to mature]",
                        "distribution": {{
                            "Immediate (2024-2025)": [number of immediate trend signals],
                            "Short-term (2025-2027)": [number of short-term trend signals],
                            "Mid-term (2027-2030)": [number of mid-term trend signals],
                            "Long-term (2030-2035+)": [number of long-term trend signals]
                        }}
                    }},
                    "3_confidence_level": {{
                        "majority_agreement": [percentage confidence in trend identification]
                    }},
                    "4_optimistic_outliers": [
                        {{
                            "scenario": "[optimistic emerging trend]",
                            "timeline": "[when this trend might accelerate]",
                            "source": "[article or pattern source]"
                        }}
                    ],
                    "5_pessimistic_outliers": [
                        {{
                            "scenario": "[concerning emerging trend]",
                            "timeline": "[when this risk might materialize]",
                            "source": "[article or pattern source]"
                        }}
                    ],
                    "6_key_articles": [
                        {{
                            "title": "[article title]",
                            "relevance": "[why this article reveals an emerging trend]",
                            "sentiment": "[positive/neutral/critical]"
                        }}
                    ],
                    "7_strategic_implications": {{
                        "summary": "[key strategic insights about emerging trends]",
                        "decision_principles": [
                            {{
                                "principle": "[key decision principle]",
                                "rationale": "[why this matters strategically]"
                            }}
                        ],
                        "recommendations": [
                            {{
                                "action": "[specific actionable recommendation]",
                                "priority": "[High/Medium/Low]",
                                "timeline": "[immediate/short-term/mid-term]"
                            }}
                        ],
                        "success_metrics": ["[measurable success indicator]"]
                    }}
                }}

                Focus on identifying patterns and signals that traditional category analysis might miss. Return ONLY the JSON object, no additional text.
                """
            elif category == "General Analysis":
                category_prompt = f"""
                Please conduct a comprehensive general consensus analysis for the topic "{req.topic}" based on articles from the last {timeframe_days} days.

                IMPORTANT SEARCH INSTRUCTIONS:
                1. Search broadly across ALL articles in the "{req.topic}" topic from the last {timeframe_days} days
                2. Analyze the overall consensus and patterns across all available content
                3. Provide a comprehensive view of the topic without category restrictions
                4. Focus on the dominant themes, sentiments, and timeline patterns

                For this general analysis, analyze and return ONLY a valid JSON object with this exact structure:

                {{
                    "articles_analyzed": [number of articles found and analyzed],
                    "1_consensus_type": {{
                        "summary": "[one of: Positive Growth, Business Transformation, Mixed Consensus, Regulatory Response, Societal Impact, Safety/Security, Geopolitical Strategy, Defense Applications]",
                        "distribution": {{
                            "positive": [percentage],
                            "neutral": [percentage], 
                            "critical": [percentage]
                        }}
                    }},
                    "2_timeline_consensus": {{
                        "summary": "[dominant timeline across all articles]",
                        "distribution": {{
                            "Immediate (2024-2025)": [number of articles],
                            "Short-term (2025-2027)": [number of articles],
                            "Mid-term (2027-2030)": [number of articles],
                            "Long-term (2030-2035+)": [number of articles]
                        }}
                    }},
                    "3_confidence_level": {{
                        "majority_agreement": [percentage 0-100]
                    }},
                    "4_optimistic_outliers": [
                        {{
                            "scenario": "[optimistic scenario description]",
                            "timeline": "[when this might happen]",
                            "source": "[article title or source if available]"
                        }}
                    ],
                    "5_pessimistic_outliers": [
                        {{
                            "scenario": "[pessimistic scenario description]",
                            "timeline": "[when this might happen]",
                            "source": "[article title or source if available]"
                        }}
                    ],
                    "6_key_articles": [
                        {{
                            "title": "[article title]",
                            "relevance": "[why this article is key to understanding the consensus]",
                            "sentiment": "[positive/neutral/critical]"
                        }}
                    ],
                    "7_strategic_implications": {{
                        "summary": "[key strategic insights for planning]",
                        "decision_principles": [
                            {{
                                "principle": "[key decision principle]",
                                "rationale": "[why this matters strategically]"
                            }}
                        ],
                        "recommendations": [
                            {{
                                "action": "[specific actionable recommendation]",
                                "priority": "[High/Medium/Low]",
                                "timeline": "[immediate/short-term/mid-term]"
                            }}
                        ],
                        "success_metrics": ["[measurable success indicator]"]
                    }}
                }}

                Provide a comprehensive analysis of the overall consensus in this topic. Return ONLY the JSON object, no additional text.
                """
            else:
                # Create category-specific prompt that uses proper search methodology
                category_prompt = f"""
                Please conduct a focused consensus analysis for the "{category}" category within the topic "{req.topic}" based on articles from the last {timeframe_days} days.

                IMPORTANT SEARCH INSTRUCTIONS:
                1. Search for articles in the "{category}" category within the "{req.topic}" topic
                2. Use a timeframe of {timeframe_days} days to match the requested period: {req.timeframe}
                3. Find articles specifically relevant to the "{category}" category
                4. Analyze ALL available articles in this category, not just a small sample

                For this specific category, analyze and return ONLY a valid JSON object with this exact structure:

            {{
                "articles_analyzed": [number of articles found and analyzed],
                "1_consensus_type": {{
                    "summary": "[one of: Positive Growth, Business Transformation, Mixed Consensus, Regulatory Response, Societal Impact, Safety/Security, Geopolitical Strategy, Defense Applications]",
                    "distribution": {{
                        "positive": [percentage],
                        "neutral": [percentage], 
                        "critical": [percentage]
                    }}
                }},
                "2_timeline_consensus": {{
                    "summary": "[dominant timeline]",
                    "distribution": {{
                        "Immediate (2024-2025)": [number of articles],
                        "Short-term (2025-2027)": [number of articles],
                        "Mid-term (2027-2030)": [number of articles],
                        "Long-term (2030-2035+)": [number of articles]
                    }}
                }},
                "3_confidence_level": {{
                    "majority_agreement": [percentage 0-100]
                }},
                "4_optimistic_outliers": [
                    {{
                        "scenario": "[optimistic scenario description]",
                        "timeline": "[when this might happen]",
                        "source": "[article title or source if available]",
                        "source_percentage": [percentage of sources supporting this view],
                        "year": [estimated year]
                    }}
                ],
                "5_pessimistic_outliers": [
                    {{
                        "scenario": "[pessimistic scenario description]",
                        "timeline": "[when this might happen]",
                        "source": "[article title or source if available]",
                        "source_percentage": [percentage of sources supporting this view],
                        "year": [estimated year]
                    }}
                ],
                "6_key_articles": [
                    {{
                        "title": "[article title]",
                        "relevance": "[why this article is key]",
                        "sentiment": "[positive/neutral/critical]"
                    }}
                ],
                "7_strategic_implications": {{
                    "summary": "[key strategic insights for planning]",
                    "decision_principles": [
                        {{
                            "principle": "[key decision principle]",
                            "rationale": "[why this matters strategically]"
                        }}
                    ],
                    "recommendations": [
                        {{
                            "action": "[specific actionable recommendation]",
                            "priority": "[High/Medium/Low]",
                            "timeline": "[immediate/short-term/mid-term]"
                        }}
                    ],
                    "success_metrics": ["[measurable success indicator]"]
                }}
            }}

            Base your analysis on actual sentiment patterns, time-to-impact data, and article content from the database for this specific category only.

            IMPORTANT:
            - Provide up to 3 optimistic outliers and up to 3 pessimistic outliers if the data supports multiple distinct scenarios
            - Include source_percentage and year for each outlier for timeline positioning
            - Provide 2-3 decision principles, 3-4 prioritized recommendations, and 2-3 success metrics
            - Ensure key_articles includes actual article titles from the analyzed data with URLs if available

            Return ONLY the JSON object, no additional text.
            """
            
            # Get category-specific analysis
            # Each category should get the FULL article limit since they search independently
            # The categories will find different articles within their specific domain
            is_mega_context = req.model in ["gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano", "gemini-1.5-pro"]
            
            # Give each category the full article limit - they search independently
            category_limit = req.articleLimit
            
            logger.info(f"Using article limit of {category_limit} for category '{category}' (model: {req.model}, mega_context: {is_mega_context})")
            logger.info(f"Each category will independently search for up to {category_limit} articles within their domain")
            logger.info(f"Timeframe conversion: {req.timeframe} -> {timeframe_days} days")
            logger.info(f"Expected to find articles similar to database count for '{category}' in '{req.topic}'")
            
            # Use a more natural search query that will trigger the sophisticated search system
            if category == "Trends":
                search_query = f"Find all articles in {req.topic} from the last {timeframe_days} days to identify emerging trends and patterns for comprehensive analysis"
            elif category == "General Analysis":
                search_query = f"Find all articles in {req.topic} from the last {timeframe_days} days for comprehensive general consensus analysis"
            else:
                search_query = f"Find all articles about {category} in {req.topic} from the last {timeframe_days} days for comprehensive consensus analysis"
            
            category_response = ""
            async for chunk in auspex.chat_with_tools(
                chat_id=chat_id, 
                message=search_query,
                model=req.model,
                limit=category_limit,
                tools_config={"search_articles": True, "get_sentiment_analysis": True}
            ):
                category_response += chunk
            
            # Now ask for the structured analysis based on the search results
            analysis_prompt = f"""
            Based on the search results above, provide ONLY a JSON object with this structure:

            {{
                "articles_analyzed": [count from search results],
                "1_consensus_type": {{
                    "summary": "[consensus type - describe using clear narrative WITHOUT numbered citations. Use markdown links [Article Title](URL) to cite specific articles.]",
                    "distribution": {{"positive": 30, "neutral": 40, "critical": 30}}
                }},
                "2_timeline_consensus": {{
                    "summary": "[timeline - describe using clear narrative WITHOUT numbered citations. Use markdown links [Article Title](URL) to cite specific articles.]",
                    "distribution": {{"Immediate (2025)": 5, "Short-term (2025-2027)": 10, "Mid-term (2027-2030)": 8, "Long-term (2030-2035+)": 2}}
                }},
                "3_confidence_level": {{
                    "majority_agreement": 65
                }},
                "4_optimistic_outliers": [
                    {{"scenario": "[scenario]", "timeline": "[when]", "source": "[source with markdown link format if URL available]"}}
                ],
                "5_pessimistic_outliers": [
                    {{"scenario": "[scenario]", "timeline": "[when]", "source": "[source with markdown link format if URL available]"}}
                ],
                "6_key_articles": [
                    {{"title": "[title]", "relevance": "[why relevant]", "sentiment": "[positive/neutral/critical]"}}
                ],
                "7_strategic_implications": {{
                    "summary": "[insights - write as clear narrative WITHOUT numbered citations. Use markdown links [Article Title](URL) to cite specific articles from the search results.]",
                    "recommendations": ["[rec1]", "[rec2]"]
                }}
            }}

            CRITICAL INSTRUCTIONS FOR CITATIONS:
            1. Do NOT use numbered citations like ([1], [2], [3]) or plain publication names like (The Hindu, Times of India)
            2. Instead, use markdown links with the ACTUAL article URLs from the search results above
            3. Format: [Article Title](https://example.com/article-url)

            EXAMPLE OF CORRECT CITATION FORMAT:
            Bad: "Multiple sources ([1], [3], [4]) agree that..."
            Bad: "Multiple sources (The Hindu, Times of India) agree that..."
            Good: "Multiple sources including [EU strikes deal on climate](https://thehindu.com/article123) and [UN warns of warming](https://timesofindia.com/article456) agree that..."

            4. You MUST extract article titles and URLs from the search results provided above
            5. Every time you mention evidence or a source, link to the actual article
            6. Write as a flowing narrative with embedded links, not as a list of sources

            Return ONLY this JSON object, no other text.
            """
            
            structured_response = ""
            async for chunk in auspex.chat_with_tools(
                chat_id=chat_id, 
                message=analysis_prompt,
                model=req.model,
                limit=10,  # Small limit for analysis only
                tools_config={"search_articles": False, "get_sentiment_analysis": False}
            ):
                structured_response += chunk
            
            # Combine the search results with the structured analysis
            category_response = category_response + "\n\nSTRUCTURED ANALYSIS:\n" + structured_response
            
            category_analyses[category] = category_response
            logger.info(f"Completed analysis for {category}: {len(category_response)} characters")

        # Generate cross-category evidence synthesis
        logger.info("Generating cross-category evidence synthesis...")
        synthesis_prompt = f"""Based on the consensus analyses across {len(target_categories)} categories for the topic "{req.topic}", provide a high-level evidence synthesis.

CATEGORY ANALYSES SUMMARY:
{json.dumps({cat: analysis[:500] + '...' for cat, analysis in category_analyses.items()}, indent=2)}

Please provide a JSON response with the following structure:
{{
    "8_evidence_synthesis": {{
        "key_patterns": [
            {{
                "pattern": "[Cross-cutting theme or pattern identified across categories]",
                "supporting_categories": ["[category name]", "[category name]"],
                "significance": "[Why this pattern matters strategically]"
            }}
        ],
        "consensus_strength": {{
            "overall_agreement_level": "[High/Medium/Low]",
            "areas_of_strong_consensus": ["[specific area]"],
            "areas_of_divergence": ["[specific area where views differ]"]
        }},
        "timeline_clusters": {{
            "immediate_actions": "[What needs attention now based on all evidence]",
            "short_term_outlook": "[2025-2027 synthesis]",
            "mid_term_outlook": "[2027-2030 synthesis]",
            "long_term_outlook": "[2030+ synthesis]"
        }},
        "strategic_priorities": [
            {{
                "priority": "[Strategic action or decision needed]",
                "rationale": "[Why this is a top priority across all evidence]",
                "urgency": "[High/Medium/Low]",
                "supporting_evidence": "[Which categories/data points support this]"
            }}
        ]
    }}
}}

IMPORTANT: Provide 2-3 key patterns, assess consensus strength honestly, describe timeline clusters based on actual data, and identify 3-5 strategic priorities."""

        synthesis_response = ""
        async for chunk in auspex.chat(
            chat_id=chat_id,
            message=synthesis_prompt,
            stream=True
        ):
            synthesis_response += chunk

        logger.info(f"Generated evidence synthesis: {len(synthesis_response)} characters")

        # Combine all category analyses into final response
        combined_analysis = {
            "topic": req.topic,
            "timeframe": req.timeframe,
            "total_categories_analyzed": len(target_categories),
            "category_analyses": category_analyses,
            "evidence_synthesis": synthesis_response,
            "summary": f"Conducted separate consensus analysis for {len(target_categories)} categories within {req.topic}"
        }

        full_response = json.dumps(combined_analysis, indent=2)

        # Save analysis to database
        import uuid
        import time
        analysis_id = str(uuid.uuid4())
        analysis_end_time = time.time()
        analysis_duration = analysis_end_time - analysis_start_time if 'analysis_start_time' in locals() else 0

        # Get total articles analyzed across all categories
        total_articles = 0
        for cat_analysis in category_analyses.values():
            # Try to extract article count from each analysis
            try:
                if '"articles_analyzed":' in cat_analysis:
                    import re
                    match = re.search(r'"articles_analyzed":\s*(\d+)', cat_analysis)
                    if match:
                        total_articles += int(match.group(1))
            except:
                pass

        db = get_database_instance()
        db.facade.save_consensus_analysis(
            analysis_id=analysis_id,
            user_id=user_id,
            topic=req.topic,
            timeframe=req.timeframe,
            selected_categories=req.categories if req.categories else [],
            raw_output=combined_analysis,
            total_articles_analyzed=total_articles,
            analysis_duration_seconds=analysis_duration
        )

        # Clean up the temporary chat session
        auspex.delete_chat_session(chat_id)

        logger.info(f"Generated consensus analysis of length: {len(full_response)}, saved as {analysis_id}")

        return {
            "success": True,
            "topic": req.topic,
            "timeframe": req.timeframe,
            "analysis": full_response,
            "analysis_id": analysis_id,
            "categories": req.categories,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error generating consensus analysis: {e}")
        # Clean up chat session if it was created
        try:
            if 'chat_id' in locals():
                auspex.delete_chat_session(chat_id)
        except:
            pass
        
        raise HTTPException(status_code=500, detail=f"Failed to generate consensus analysis: {str(e)}")

# Get raw consensus analysis by ID
@router.get("/consensus-analysis/{analysis_id}/raw", status_code=status.HTTP_200_OK)
async def get_consensus_analysis_raw(analysis_id: str, session=Depends(verify_session)):
    """Retrieve raw consensus analysis output by ID."""
    logger.info(f"Retrieving raw consensus analysis: {analysis_id}")

    try:
        db = get_database_instance()
        analysis_data = db.facade.get_consensus_analysis(analysis_id)

        if not analysis_data:
            raise HTTPException(status_code=404, detail="Analysis not found")

        return {
            "success": True,
            "analysis_id": analysis_id,
            "topic": analysis_data.get('topic'),
            "timeframe": analysis_data.get('timeframe'),
            "created_at": analysis_data.get('created_at').isoformat() if analysis_data.get('created_at') else None,
            "total_articles_analyzed": analysis_data.get('total_articles_analyzed'),
            "analysis_duration_seconds": analysis_data.get('analysis_duration_seconds'),
            "raw_output": analysis_data.get('raw_output')
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving consensus analysis {analysis_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve analysis: {str(e)}")

# System Information
@router.get("/system/info", status_code=status.HTTP_200_OK)
async def get_system_info(session=Depends(verify_session)):
    """Get Auspex system information."""
    auspex = get_auspex_service()
    
    # Get available topics
    topics = auspex.db.get_topics()
    
    # Get prompt count
    prompts = auspex.get_all_prompts()
    
    return {
        "version": "2.0.0",
        "features": {
            "tools_integration": True,
            "chat_persistence": True,
            "prompt_management": True,
            "streaming_responses": True,
            "real_time_news": True,
            "sentiment_analysis": True,
            "category_analysis": True,
            "semantic_search": True,
            "diversity_filtering": True,
            "structured_analysis": True,
            "follow_up_queries": True
        },
        "available_topics": topics,
        "available_prompts": len(prompts),
        "tools": [
            "search_news",
            "get_topic_articles", 
            "analyze_sentiment_trends",
            "get_article_categories",
            "search_articles_by_keywords",
            "semantic_search_and_analyze",
            "follow_up_query"
        ],
        "status": "operational"
    }

# Diagnostic endpoint
@router.get("/debug/test-tools", status_code=status.HTTP_200_OK)
async def test_auspex_tools(session=Depends(verify_session)):
    """Test Auspex tools functionality."""
    auspex = get_auspex_service()
    results = {
        "database_check": False,
        "tools_service_check": False,
        "topic_articles_test": {"success": False, "error": None},
        "sentiment_analysis_test": {"success": False, "error": None},
        "categories_test": {"success": False, "error": None}
    }
    
    try:
        # Test database connection
        topics = auspex.db.get_topics()
        results["database_check"] = True
        results["available_topics"] = len(topics)
        
        # Test tools service
        tools = auspex.tools
        results["tools_service_check"] = tools is not None
        
        if tools and len(topics) > 0:
            test_topic = topics[0]['name']
            
            # Test topic articles
            try:
                result = await tools.get_topic_articles(test_topic, limit=5)
                results["topic_articles_test"]["success"] = "error" not in result
                results["topic_articles_test"]["article_count"] = result.get("total_articles", 0)
                if "error" in result:
                    results["topic_articles_test"]["error"] = result["error"]
            except Exception as e:
                results["topic_articles_test"]["error"] = str(e)
            
            # Test sentiment analysis
            try:
                result = await tools.analyze_sentiment_trends(test_topic, "month")
                results["sentiment_analysis_test"]["success"] = "error" not in result
                results["sentiment_analysis_test"]["article_count"] = result.get("total_articles", 0)
                if "error" in result:
                    results["sentiment_analysis_test"]["error"] = result["error"]
            except Exception as e:
                results["sentiment_analysis_test"]["error"] = str(e)
            
            # Test categories
            try:
                result = await tools.get_article_categories(test_topic)
                results["categories_test"]["success"] = "error" not in result
                results["categories_test"]["category_count"] = len(result.get("category_distribution", {}))
                if "error" in result:
                    results["categories_test"]["error"] = result["error"]
            except Exception as e:
                results["categories_test"]["error"] = str(e)
                
    except Exception as e:
        results["general_error"] = str(e)
    
    return {
        "status": "test_completed",
        "timestamp": datetime.now().isoformat(),
        "results": results
    } 