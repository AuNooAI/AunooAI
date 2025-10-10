from fastapi import APIRouter, HTTPException, Query, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.security.session import verify_session
from typing import List, Dict, Optional, Callable, Any
import logging
import json
import hashlib
import re
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from pydantic import BaseModel
from enum import Enum

from app.database import Database, get_database_instance
from app.database_query_facade import DatabaseQueryFacade
from app.services.auspex_service import get_auspex_service

# Context limits for different AI models (copied from futures cone)
CONTEXT_LIMITS = {
    'gpt-3.5-turbo': 16385,
    'gpt-3.5-turbo-16k': 16385,
    'gpt-4': 8192,
    'gpt-4-32k': 32768,
    'gpt-4-turbo': 128000,
    'gpt-4-turbo-preview': 128000,
    'gpt-4o': 128000,
    'gpt-4o-mini': 128000,
    'gpt-4.1': 1000000,
    'gpt-4.1-mini': 1000000,
    'gpt-4.1-nano': 1000000,
    'claude-3-opus': 200000,
    'claude-3-sonnet': 200000,
    'claude-3-haiku': 200000,
    'claude-3.5-sonnet': 200000,
    'claude-4': 200000,
    'claude-4-opus': 200000,
    'claude-4-sonnet': 200000,
    'claude-4-haiku': 200000,
    'gemini-pro': 32768,
    'gemini-1.5-pro': 2097152,
    'llama-2-70b': 4096,
    'llama-3-70b': 8192,
    'mixtral-8x7b': 32768,
    'default': 16385
}

# Consistency mode enum for analysis control
class ConsistencyMode(str, Enum):
    DETERMINISTIC = "deterministic"      # Maximum consistency, temp=0.0
    LOW_VARIANCE = "low_variance"        # High consistency, temp=0.2  
    BALANCED = "balanced"                # Good balance, temp=0.4
    CREATIVE = "creative"                # Current behavior, temp=0.7

router = APIRouter()
logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory="templates")

# Pydantic models for organizational profiles
class OrganizationalProfile(BaseModel):
    id: Optional[int] = None
    name: str
    description: Optional[str] = None
    industry: Optional[str] = None
    organization_type: Optional[str] = None
    region: Optional[str] = None
    key_concerns: List[str] = []
    strategic_priorities: List[str] = []
    risk_tolerance: str = "medium"
    innovation_appetite: str = "moderate"
    decision_making_style: str = "collaborative"
    stakeholder_focus: List[str] = []
    competitive_landscape: List[str] = []
    regulatory_environment: List[str] = []
    custom_context: Optional[str] = None
    is_default: bool = False

class ProfileCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    industry: Optional[str] = None
    organization_type: Optional[str] = None
    region: Optional[str] = None
    key_concerns: List[str] = []
    strategic_priorities: List[str] = []
    risk_tolerance: str = "medium"
    innovation_appetite: str = "moderate"
    decision_making_style: str = "collaborative"
    stakeholder_focus: List[str] = []
    competitive_landscape: List[str] = []
    regulatory_environment: List[str] = []
    custom_context: Optional[str] = None

def calculate_optimal_sample_size(model: str, sample_size_mode: str = 'auto', custom_limit: int = None) -> int:
    """Calculate optimal sample size based on model capabilities and mode"""
    
    if sample_size_mode == 'custom' and custom_limit:
        return custom_limit
    
    # Calculate based on mode and model capabilities
    context_limit = CONTEXT_LIMITS.get(model, CONTEXT_LIMITS['default'])
    is_mega_context = context_limit >= 1000000
    
    if sample_size_mode == 'focused':
        base_sample_size = 50 if is_mega_context else 25
    elif sample_size_mode == 'balanced':
        base_sample_size = 100 if is_mega_context else 50
    elif sample_size_mode == 'comprehensive':
        base_sample_size = 200 if is_mega_context else 100
    else:  # auto or default
        # Auto-size based on context window
        base_size = 150 if is_mega_context else 75
        
        # For trend convergence analysis, we need good coverage for pattern identification
        base_size = int(base_size * 1.2)  # Increase for better pattern coverage
        base_sample_size = base_size
    
    # Ensure reasonable limits
    max_limit = 1000 if is_mega_context else 400
    min_limit = 20  # Minimum for good pattern diversity
    
    return max(min_limit, min(base_sample_size, max_limit))

def _extract_from_code_block(text: str) -> str:
    """Extract JSON from code blocks if present"""
    import re
    code_block_pattern = r'```(?:json)?\s*\n(.*?)\n```'
    match = re.search(code_block_pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text

def _extract_complete_json(text: str) -> str:
    """Extract the first complete JSON object from text"""
    import re
    # Find the first { and last } to extract complete JSON
    start = text.find('{')
    if start == -1:
        return text
    
    brace_count = 0
    end = start
    
    for i, char in enumerate(text[start:], start):
        if char == '{':
            brace_count += 1
        elif char == '}':
            brace_count -= 1
            if brace_count == 0:
                end = i + 1
                break
    
    if brace_count == 0:
        return text[start:end]
    return text

def _clean_and_parse_json(text: str) -> str:
    """Clean and parse JSON response"""
    # Remove any leading/trailing whitespace and non-JSON content
    text = text.strip()
    
    # Extract from code blocks if present
    text = _extract_from_code_block(text)
    
    # Extract complete JSON
    text = _extract_complete_json(text)
    
    # Fix common JSON issues
    text = _fix_common_json_issues(text)
    
    return text

def _fix_common_json_issues(text: str) -> str:
    """Fix common JSON formatting issues"""
    import re
    
    # Remove any text before the first {
    text = re.sub(r'^[^{]*', '', text)
    
    # Remove any text after the last }
    text = re.sub(r'}[^}]*$', '}', text)
    
    # Fix trailing commas
    text = re.sub(r',(\s*[}\]])', r'\1', text)
    
    return text

def _fix_json_strings(text: str) -> str:
    """Fix unterminated strings and other JSON string issues"""
    import re
    
    # First, try to find the complete JSON object
    start_brace = text.find('{')
    if start_brace == -1:
        return text
    
    # Count braces to find the end
    brace_count = 0
    end_pos = start_brace
    
    for i, char in enumerate(text[start_brace:], start_brace):
        if char == '{':
            brace_count += 1
        elif char == '}':
            brace_count -= 1
            if brace_count == 0:
                end_pos = i + 1
                break
    
    # Extract the complete JSON object
    if brace_count == 0:
        text = text[start_brace:end_pos]
    
    # Fix unterminated strings more carefully
    def fix_string(match):
        string_content = match.group(1)
        # If string doesn't end with quote, add one
        if not string_content.endswith('"'):
            string_content += '"'
        return f'"{string_content}'
    
    # Fix unterminated strings in key-value pairs
    text = re.sub(r'"([^"]*?)(?=,|\s*:|\s*[}\]])', fix_string, text)
    
    # Fix unterminated strings at the end of arrays/objects
    text = re.sub(r'"([^"]*?)(?=\s*[}\]])', fix_string, text)
    
    # Fix any remaining unterminated strings
    text = re.sub(r'"([^"]*?)(?=\s*[}\]])', fix_string, text)
    
    return text

def _complete_json_manually(text: str) -> str:
    """Manually complete truncated JSON by adding missing closing braces and brackets"""
    import re
    
    # Find the start of the JSON object
    start_brace = text.find('{')
    if start_brace == -1:
        return text
    
    # Count all braces and brackets
    brace_count = 0
    bracket_count = 0
    in_string = False
    escape_next = False
    
    for i, char in enumerate(text[start_brace:], start_brace):
        if escape_next:
            escape_next = False
            continue
        
        if char == '\\':
            escape_next = True
            continue
        
        if char == '"' and not escape_next:
            in_string = not in_string
            continue
        
        if not in_string:
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
            elif char == '[':
                bracket_count += 1
            elif char == ']':
                bracket_count -= 1
    
    # Add missing closing braces and brackets
    result = text[start_brace:]
    result += ']' * bracket_count
    result += '}' * brace_count
    
    return result

async def _save_analysis_version(topic: str, analysis_data: Dict, db: Database):
    """Save analysis version for potential reload"""
    try:
        # Save the version
        (DatabaseQueryFacade(db, logger)).save_analysis_version((
            topic,
            json.dumps(analysis_data),
            analysis_data.get('model_used', 'unknown'),
            analysis_data.get('analysis_depth', 'standard')
        ))
            
        logger.info(f"Saved analysis version for topic: {topic}")
    except Exception as e:
        logger.error(f"Failed to save analysis version: {str(e)}")

async def _load_latest_analysis_version(topic: str, db: Database) -> Optional[Dict]:
    """Load the latest analysis version for a topic"""
    try:
        result = (DatabaseQueryFacade(db, logger)).get_latest_analysis_version(topic)

        if result:
            analysis_data = json.loads(result[0])
            logger.info(f"Loaded previous analysis version for topic: {topic}")
            return analysis_data
        else:
            logger.info(f"No previous analysis version found for topic: {topic}")
            return None
    except Exception as e:
        logger.error(f"Failed to load analysis version: {str(e)}")
        return None

def _attempt_json_completion(text: str) -> str:
    """Attempt to complete incomplete JSON"""
    import re
    
    # Count braces to see if JSON is incomplete
    open_braces = text.count('{')
    close_braces = text.count('}')
    
    if open_braces > close_braces:
        # Add missing closing braces
        missing_braces = open_braces - close_braces
        text += '}' * missing_braces
    
    # Fix common incomplete structures
    if not text.strip().endswith('}'):
        # Try to find the last complete object and close it
        last_brace = text.rfind('}')
        if last_brace != -1:
            text = text[:last_brace + 1]
    
    return text

def _preprocess_response(response: str) -> str:
    """Preprocess AI response to extract valid JSON"""
    
    # Clean the response
    cleaned = _clean_and_parse_json(response)
    
    # Try to parse as JSON
    try:
        json.loads(cleaned)
        return cleaned
    except json.JSONDecodeError:
        # Try to fix common issues
        fixed = _attempt_json_completion(cleaned)
        try:
            json.loads(fixed)
            return fixed
        except json.JSONDecodeError:
            # If still invalid, return the original cleaned text
            return cleaned

@router.get("/api/trend-convergence/{topic}")
async def generate_trend_convergence(
    topic: str,
    timeframe_days: int = Query(365),
    model: str = Query(...),
    analysis_depth: str = Query("standard"),
    sample_size_mode: str = Query("auto"),
    custom_limit: int = Query(None),
    persona: str = Query("executive", description="Analysis persona: executive, analyst, strategist"),
    customer_type: str = Query("general", description="Customer type: general, enterprise, startup"),
    consistency_mode: ConsistencyMode = Query(ConsistencyMode.BALANCED, description="AI consistency: deterministic, low_variance, balanced, creative"),
    enable_caching: bool = Query(True, description="Enable result caching"),
    cache_duration_hours: int = Query(24, description="Cache validity period"),
    profile_id: int = Query(None, description="Organizational profile ID for context"),
    db: Database = Depends(get_database_instance),
    session: dict = Depends(verify_session)
):
    """Generate trend convergence analysis with improved consistency"""
    
    try:
        logger.info(f"Generating trend convergence analysis for topic: {topic}, model: {model}, consistency: {consistency_mode.value}")
        
        # Generate comprehensive cache key for all parameters
        cache_key = generate_comprehensive_cache_key(
            topic, timeframe_days, model, analysis_depth, sample_size_mode,
            custom_limit, profile_id, consistency_mode, persona, customer_type
        )
        
        # Try to get cached result first if caching is enabled
        if enable_caching:
            cached_result = await get_cached_analysis(cache_key, db, cache_duration_hours)
            if cached_result:
                logger.info(f"Returning cached analysis for {topic} (consistency: {consistency_mode.value})")
                return cached_result
        
        # Calculate optimal sample size based on model and mode
        # For GPT-4.1 (1M context): base_size=150 * 1.2 = 180 articles
        # For smaller models: base_size=75 * 1.2 = 90 articles
        optimal_sample_size = calculate_optimal_sample_size(model, sample_size_mode, custom_limit)
        logger.info(f"Using sample size: {optimal_sample_size} articles for model: {model}")
        
        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=timeframe_days)

        articles = (DatabaseQueryFacade(db, logger)).get_articles_with_dynamic_limit(
            consistency_mode,
            topic,
            start_date,
            end_date,
            optimal_sample_size
        )

        if not articles:
            raise HTTPException(
                status_code=404, 
                detail=f"No articles found for topic '{topic}' in the specified timeframe"
            )
        
        logger.info(f"Found {len(articles)} articles for analysis")
        
        # Use deterministic article selection for consistency
        diverse_articles = select_articles_deterministic(articles, min(len(articles), optimal_sample_size), consistency_mode)
        logger.info(f"Selected {len(diverse_articles)} diverse articles using {consistency_mode.value} mode")
        
        # Prepare analysis summary using diverse articles
        analysis_summary = prepare_analysis_summary(diverse_articles, topic)
        
        # Get organizational profile if specified
        organizational_profile = None
        if profile_id:
            try:
                profile_row = (DatabaseQueryFacade(db, logger)).get_organisational_profile(profile_id)
                if profile_row:
                    organizational_profile = {
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
                        'custom_context': profile_row[14]
                    }
                else:
                    logger.warning(f"Organizational profile {profile_id} not found, using default template")
            except Exception as e:
                logger.error(f"Error loading organizational profile: {str(e)}")
                
        # Get configurable prompt template based on persona, customer type, and profile
        prompt_template = get_enhanced_prompt_template(persona, customer_type, organizational_profile)
        
        # Create the AI prompt for trend convergence analysis
        org_context = ""
        if organizational_profile:
            org_context = f"""

ORGANIZATIONAL CONTEXT:
- Organization: {organizational_profile['name']}
- Industry: {organizational_profile['industry']}
- Type: {organizational_profile['organization_type']}
- Description: {organizational_profile['description']}
- Key Concerns: {', '.join(organizational_profile['key_concerns'])}
- Strategic Priorities: {', '.join(organizational_profile['strategic_priorities'])}
- Risk Tolerance: {organizational_profile['risk_tolerance']}
- Innovation Appetite: {organizational_profile['innovation_appetite']}
- Decision Making Style: {organizational_profile['decision_making_style']}
- Key Stakeholders: {', '.join(organizational_profile['stakeholder_focus'])}
- Competitive Landscape: {', '.join(organizational_profile['competitive_landscape'])}
- Regulatory Environment: {', '.join(organizational_profile['regulatory_environment'])}
- Additional Context: {organizational_profile['custom_context']}
"""
            
        formatted_prompt = f"""Analyze {len(articles)} articles about "{topic}" and create a comprehensive strategic planning document.{org_context}

STRATEGIC FOCUS: {prompt_template['focus']}
EXECUTIVE FRAMEWORK: {prompt_template['framework_emphasis']}
NEXT STEPS APPROACH: {prompt_template['next_steps_style']}

REQUIRED OUTPUT FORMAT - Use EXACTLY this JSON structure:

{{
  "topic": "{topic}",
  "strategic_recommendations": {{
    "near_term": {{
      "timeframe": "2025-2027",
      "trends": [
        {{
          "name": "Trend Name",
          "description": "Brief description of the trend",
          "strength": "High|Medium|Low",
          "momentum": "Increasing|Steady|Decreasing",
          "key_indicators": ["indicator1", "indicator2", "indicator3"],
          "strategic_actions": ["action1", "action2", "action3"]
        }}
      ]
    }},
    "mid_term": {{
      "timeframe": "2027-2032",
      "trends": [
        {{
          "name": "Trend Name",
          "description": "Brief description of the trend",
          "strength": "High|Medium|Low",
          "momentum": "Increasing|Steady|Decreasing",
          "key_indicators": ["indicator1", "indicator2", "indicator3"],
          "strategic_actions": ["action1", "action2", "action3"]
        }}
      ]
    }},
    "long_term": {{
      "timeframe": "2032+",
      "trends": [
        {{
          "name": "Trend Name",
          "description": "Brief description of the trend",
          "strength": "High|Medium|Low",
          "momentum": "Increasing|Steady|Decreasing",
          "key_indicators": ["indicator1", "indicator2", "indicator3"],
          "strategic_actions": ["action1", "action2", "action3"]
        }}
      ]
    }}
  }},
  "convergences": [
    {{
      "name": "Convergence Name",
      "description": "Description of how trends converge",
      "probability": "High|Medium|Low",
      "impact": "Transformative|Significant|Moderate",
      "timeframe": "2025-2028",
      "converging_trends": ["Trend Name 1", "Trend Name 2"],
      "key_indicators": ["indicator1", "indicator2"]
    }}
  ],
  "executive_decision_framework": {{
    "principles": [
      {{
        "name": "Principle Name",
        "description": "Brief description of the decision principle",
        "rationale": "Why this principle is important",
        "implementation": "How to apply this principle"
      }}
    ]
  }},
  "next_steps": [
    {{
      "priority": "High|Medium|Low",
      "action": "Specific actionable step",
      "timeline": "When to complete this",
      "stakeholders": ["stakeholder1", "stakeholder2"],
      "success_metrics": ["metric1", "metric2"]
    }}
  ]
}}

ARTICLE DATA:
{analysis_summary}

ANALYSIS INSTRUCTIONS:
- Identify 2-3 major trends for each time horizon (near-term, mid-term, long-term)
- Find 2-4 convergence points where trends intersect across timeframes
- Create 4-5 executive decision principles for strategic planning
- Provide 3-5 specific, actionable next steps with priorities and timelines
- Focus on cross-cutting patterns and systemic changes
- Include specific strategic actions for each trend
- Provide clear success metrics for next steps

STRATEGIC FOCUS:
- Near-term (2025-2027): Immediate strategic actions and market positioning
- Mid-term (2027-2032): Medium-term planning and competitive advantage
- Long-term (2032+): Future vision and transformation opportunities

EXECUTIVE FRAMEWORK:
- Decision principles should guide strategic choices
- Focus on risk management and opportunity capture
- Consider stakeholder impact and resource allocation

NEXT STEPS:
- Prioritize by impact and feasibility
- Include clear timelines and ownership
- Define measurable success metrics

RESPONSE FORMAT: Return ONLY the JSON object above, no additional text."""
        
        # Use Auspex service for reliable AI response handling (like consensus analysis)
        auspex = get_auspex_service()
        
        try:
            # Create a temporary chat session for the analysis
            user_id = session.get('user', 'system')  # Use actual user or fallback to system
            chat_id = await auspex.create_chat_session(
                topic=topic,
                user_id=user_id,
                title=f"Trend Convergence Analysis: {topic}"
            )
            
            # Get the AI response using consistency-aware wrapper
            response_text = await generate_analysis_with_consistency(
                auspex, chat_id, formatted_prompt, model, consistency_mode
            )
            
            # Clean up the temporary chat session
            auspex.delete_chat_session(chat_id)
            
            logger.info(f"AI response received for topic: {topic}")
            logger.info(f"Raw AI response (first 200 chars): {response_text[:200]}...")
            
            # Extract JSON from the response (same approach as AI timeline)
            import re
            
            # First try to find JSON in code blocks
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', response_text, re.DOTALL)
            if json_match:
                try:
                    trend_convergence_data = json.loads(json_match.group(1))
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse JSON from code block: {e}")
                    raise HTTPException(status_code=500, detail="Failed to parse AI response JSON from code block")
            else:
                # Try to find JSON without code blocks
                json_start = response_text.find('{')
                json_end = response_text.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    try:
                        trend_convergence_data = json.loads(response_text[json_start:json_end])
                    except json.JSONDecodeError as e:
                        logger.warning(f"Failed to parse extracted JSON: {e}")
                        logger.info(f"Extracted JSON: {response_text[json_start:json_end][:500]}...")
                        raise HTTPException(status_code=500, detail="Failed to parse AI response as valid JSON")
                else:
                    logger.warning("No valid JSON found in response")
                    logger.info(f"Raw response: {response_text[:500]}...")
                    raise HTTPException(status_code=500, detail="No valid JSON found in AI response")
            
        except Exception as e:
            logger.error(f"AI model error: {str(e)}")
            raise HTTPException(status_code=500, detail=f"AI model error: {str(e)}")
        
        # Validate and enhance the response
        if not isinstance(trend_convergence_data, dict):
            raise HTTPException(status_code=500, detail="AI response is not a valid dictionary")
        
        # Ensure required fields exist
        if 'strategic_recommendations' not in trend_convergence_data:
            trend_convergence_data['strategic_recommendations'] = {}
        if 'convergences' not in trend_convergence_data:
            trend_convergence_data['convergences'] = []
        if 'executive_decision_framework' not in trend_convergence_data:
            trend_convergence_data['executive_decision_framework'] = {"principles": []}
        if 'next_steps' not in trend_convergence_data:
            trend_convergence_data['next_steps'] = []
        
        # Validate that the response is valid JSON
        try:
            # Test that we can serialize and deserialize the data
            json.dumps(trend_convergence_data)
        except (TypeError, ValueError) as e:
            logger.error(f"Invalid JSON structure in response: {e}")
            raise HTTPException(status_code=500, detail="AI response contains invalid JSON structure")
        
        # Add metadata
        trend_convergence_data.update({
            'generated_at': datetime.now().isoformat(),
            'articles_analyzed': len(diverse_articles),
            'total_articles_found': len(articles),
            'timeframe_days': timeframe_days,
            'model_used': model,
            'analysis_depth': analysis_depth,
            'persona': persona,
            'customer_type': customer_type,
            'consistency_mode': consistency_mode.value,
            'caching_enabled': enable_caching,
            'organizational_profile': organizational_profile,
            'version': 3  # Increment version for consistency features
        })
        
        # Save this version for potential reload (legacy system)
        await _save_analysis_version(topic, trend_convergence_data, db)
        
        # Save with enhanced caching system if caching is enabled
        if enable_caching:
            await save_analysis_with_cache(cache_key, topic, trend_convergence_data, db)
        
        # Count trends across all timeframes
        total_trends = 0
        if 'strategic_recommendations' in trend_convergence_data:
            for timeframe in ['near_term', 'mid_term', 'long_term']:
                if timeframe in trend_convergence_data['strategic_recommendations']:
                    total_trends += len(trend_convergence_data['strategic_recommendations'][timeframe].get('trends', []))
        
        logger.info(f"Successfully generated strategic analysis with {total_trends} trends across timeframes")
        
        # Data is now used directly by the frontend - no transformation needed
        
        return trend_convergence_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating trend convergence analysis: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

def select_diverse_articles(articles: List, limit: int) -> List:
    """Select diverse articles based on category, sentiment, and recency."""
    if len(articles) <= limit:
        return articles

    # Convert to dictionary format for easier processing
    article_dicts = []
    for i, article in enumerate(articles):
        article_dict = {
            'id': i,
            'title': article['title'],
            'summary': article['summary'],
            'uri': article['uri'],
            'publication_date': article['publication_date'],
            'sentiment': article['sentiment'],
            'category': article['category'],
            'future_signal': article['future_signal'],
            'driver_type': article['driver_type'],
            'time_to_impact': article['time_to_impact'],
            'similarity_score': 1.0 - (i / len(articles))  # Higher score for newer articles
        }
        article_dicts.append(article_dict)
    
    # Group articles by different dimensions
    by_category = defaultdict(list)
    by_sentiment = defaultdict(list)
    by_time_impact = defaultdict(list)
    
    for article in article_dicts:
        by_category[article.get("category", "Other")].append(article)
        by_sentiment[article.get("sentiment", "Neutral")].append(article)
        by_time_impact[article.get("time_to_impact", "Unknown")].append(article)
    
    selected = []
    
    # Strategy 1: Ensure category diversity (60% of selections)
    category_quota = int(limit * 0.6)
    categories = list(by_category.keys())
    per_category = max(1, category_quota // len(categories))
    
    for category in categories:
        cat_articles = by_category[category]
        # Sort by similarity score (newer articles first)
        cat_articles.sort(key=lambda x: x.get("similarity_score", 0), reverse=True)
        selected.extend(cat_articles[:per_category])
        if len(selected) >= category_quota:
            break
    
    # Strategy 2: Ensure sentiment diversity (25% of selections)
    sentiment_quota = int(limit * 0.25)
    remaining_articles = [a for a in article_dicts if a not in selected]
    
    sentiments = ["Positive", "Negative", "Neutral", "Critical"]
    for sentiment in sentiments:
        sent_articles = [a for a in remaining_articles if a.get("sentiment", "").startswith(sentiment)]
        if sent_articles and len(selected) < limit:
            sent_articles.sort(key=lambda x: x.get("similarity_score", 0), reverse=True)
            selected.extend(sent_articles[:max(1, sentiment_quota // len(sentiments))])
    
    # Strategy 3: Fill remaining with highest-scoring articles
    remaining_articles = [a for a in article_dicts if a not in selected]
    remaining_articles.sort(key=lambda x: x.get("similarity_score", 0), reverse=True)
    
    while len(selected) < limit and remaining_articles:
        selected.append(remaining_articles.pop(0))
    
    # Convert back to original format
    selected_original = []
    for article_dict in selected:
        # Find the original article by matching key fields
        for original_article in articles:
            if (original_article['title'] == article_dict['title'] and
                original_article['publication_date'] == article_dict['publication_date']):
                selected_original.append(original_article)
                break

    return selected_original[:limit]

def select_articles_deterministic(articles: List, limit: int, 
                                consistency_mode: ConsistencyMode) -> List:
    """
    Select articles with deterministic, reproducible results.
    
    Key improvements:
    1. Stable sorting using multiple criteria
    2. Hash-based selection for consistency
    3. Deterministic category distribution
    4. Predictable tie-breaking
    """
    
    if len(articles) <= limit:
        return articles
    
    # Create stable article representation
    article_data = []
    for i, article in enumerate(articles):
        # Create deterministic hash from stable content
        stable_content = f"{article['title']}|{article['publication_date']}|{article['category'] or 'Unknown'}"  # title|date|category
        article_hash = hashlib.md5(stable_content.encode()).hexdigest()[:8]

        article_data.append({
            'original_index': i,
            'original_article': article,
            'title': article['title'],
            'publication_date': article['publication_date'],
            'category': article['category'] or 'Unknown',
            'sentiment': article['sentiment'] or 'Neutral',
            'hash': article_hash,
            'recency_score': 1.0 - (i / len(articles))
        })
    
    # Deterministic sorting: category, then date, then hash
    if consistency_mode in [ConsistencyMode.DETERMINISTIC, ConsistencyMode.LOW_VARIANCE]:
        article_data.sort(key=lambda x: (x['category'], x['publication_date'], x['hash']))
    else:
        # Still stable but prioritizes recency
        article_data.sort(key=lambda x: (x['recency_score'], x['hash']), reverse=True)
    
    # Deterministic category-based selection
    selected = []
    by_category = defaultdict(list)
    
    for article in article_data:
        by_category[article['category']].append(article)
    
    # Sort categories by name for consistency
    sorted_categories = sorted(by_category.keys())
    category_quota = int(limit * 0.6)
    articles_per_category = max(1, category_quota // len(sorted_categories))
    
    # Select from each category deterministically
    for category in sorted_categories:
        cat_articles = by_category[category]
        if consistency_mode == ConsistencyMode.DETERMINISTIC:
            # Pure deterministic: sort by hash after recency
            cat_articles.sort(key=lambda x: (x['recency_score'], x['hash']), reverse=True)
        else:
            # Weighted by recency but stable
            cat_articles.sort(key=lambda x: x['recency_score'], reverse=True)
        
        selected.extend(cat_articles[:articles_per_category])
        if len(selected) >= category_quota:
            break
    
    # Fill remaining slots deterministically
    remaining_articles = [a for a in article_data if a not in selected]
    remaining_articles.sort(key=lambda x: (x['recency_score'], x['hash']), reverse=True)
    
    while len(selected) < limit and remaining_articles:
        selected.append(remaining_articles.pop(0))
    
    # Return original article format
    return [item['original_article'] for item in selected[:limit]]

def prepare_analysis_summary(articles: List, topic: str) -> str:
    """Prepare a structured summary of article data for the AI prompt"""
    
    # Analyze patterns in the data
    sentiments = []
    categories = []
    drivers = []
    signals = []
    time_impacts = []
    
    for article in articles[:50]:  # Limit to avoid token limits
        if article['sentiment']:
            sentiments.append(article['sentiment'])
        if article['category']:
            categories.append(article['category'])
        if article['driver_type']:
            drivers.append(article['driver_type'])
        if article['future_signal']:
            signals.append(article['future_signal'])
        if article['time_to_impact']:
            time_impacts.append(article['time_to_impact'])
    
    # Count frequencies
    sentiment_counts = Counter(sentiments)
    category_counts = Counter(categories)
    driver_counts = Counter(drivers)
    signal_counts = Counter(signals)
    time_impact_counts = Counter(time_impacts)
    
    # Build analysis summary
    summary = f"""**Topic Analysis for: {topic}**

**Data Overview:**
- Total articles analyzed: {len(articles)}
- Date range: {str(articles[-1]['publication_date'])[:10] if articles and articles[-1]['publication_date'] else 'Unknown'} to {str(articles[0]['publication_date'])[:10] if articles and articles[0]['publication_date'] else 'Unknown'}

**Sentiment Distribution:**
{chr(10).join([f"- {sent}: {count} articles" for sent, count in sentiment_counts.most_common(5)])}

**Category Distribution:**
{chr(10).join([f"- {cat}: {count} articles" for cat, count in category_counts.most_common(5)])}

**Most Common Drivers:**
{chr(10).join([f"- {driver}: {count} mentions" for driver, count in driver_counts.most_common(5)])}

**Future Signals Identified:**
{chr(10).join([f"- {signal}: {count} mentions" for signal, count in signal_counts.most_common(5)])}

**Time to Impact Distribution:**
{chr(10).join([f"- {impact}: {count} articles" for impact, count in time_impact_counts.most_common(5)])}
"""
    
    return summary

def get_enhanced_prompt_template(persona: str = "executive", customer_type: str = "general", organizational_profile: Dict = None) -> Dict[str, str]:
    """Get enhanced configurable prompt template based on persona, customer type, and organizational profile"""
    
    # Base templates
    templates = {
        "executive": {
            "general": {
                "focus": "Strategic decision-making and competitive positioning",
                "framework_emphasis": "Risk management and opportunity capture",
                "next_steps_style": "High-level strategic initiatives with clear ownership"
            },
            "enterprise": {
                "focus": "Enterprise transformation and digital strategy",
                "framework_emphasis": "Change management and stakeholder alignment",
                "next_steps_style": "Cross-functional initiatives with governance"
            },
            "startup": {
                "focus": "Market positioning and growth strategy",
                "framework_emphasis": "Agile decision-making and resource optimization",
                "next_steps_style": "Rapid execution with measurable milestones"
            }
        },
        "analyst": {
            "general": {
                "focus": "Data-driven insights and trend analysis",
                "framework_emphasis": "Evidence-based decision making",
                "next_steps_style": "Analytical approach with clear metrics"
            },
            "enterprise": {
                "focus": "Comprehensive market analysis and competitive intelligence",
                "framework_emphasis": "Systematic evaluation and benchmarking",
                "next_steps_style": "Detailed research and reporting cycles"
            },
            "startup": {
                "focus": "Market validation and product-market fit",
                "framework_emphasis": "Lean methodology and rapid iteration",
                "next_steps_style": "MVP testing and customer feedback loops"
            }
        },
        "strategist": {
            "general": {
                "focus": "Long-term vision and strategic planning",
                "framework_emphasis": "Scenario planning and strategic foresight",
                "next_steps_style": "Strategic roadmap with key milestones"
            },
            "enterprise": {
                "focus": "Corporate strategy and portfolio management",
                "framework_emphasis": "Strategic alignment and value creation",
                "next_steps_style": "Strategic initiatives with clear value drivers"
            },
            "startup": {
                "focus": "Strategic positioning and competitive advantage",
                "framework_emphasis": "Innovation strategy and market disruption",
                "next_steps_style": "Strategic pivots and market expansion"
            }
        }
    }
    
    # Get base template
    base_template = templates.get(persona, templates["executive"]).get(customer_type, templates["executive"]["general"])
    
    # Enhance with organizational profile if provided
    if organizational_profile:
        enhanced_template = base_template.copy()
        
        # Customize focus based on organization type and industry
        org_type = organizational_profile.get('organization_type', '').lower()
        industry = organizational_profile.get('industry', '').lower()
        
        if 'publisher' in org_type or 'academic' in industry or 'scientific' in industry:
            enhanced_template['focus'] += f" with specific attention to {organizational_profile.get('industry', 'publishing')} industry dynamics"
            enhanced_template['framework_emphasis'] += ", intellectual property considerations, and content ecosystem sustainability"
            enhanced_template['next_steps_style'] += " while balancing traditional publishing values with digital innovation"
        
        # Add key concerns to framework emphasis
        key_concerns = organizational_profile.get('key_concerns', [])
        if key_concerns:
            concerns_str = ', '.join(key_concerns[:3])  # Limit to top 3 concerns
            enhanced_template['framework_emphasis'] += f", with particular focus on {concerns_str}"
        
        # Adjust decision making style
        decision_style = organizational_profile.get('decision_making_style', 'collaborative')
        if decision_style == 'collaborative':
            enhanced_template['next_steps_style'] += " emphasizing stakeholder consensus and collaborative implementation"
        elif decision_style == 'data-driven':
            enhanced_template['next_steps_style'] += " with strong emphasis on metrics, KPIs, and evidence-based validation"
        elif decision_style == 'agile':
            enhanced_template['next_steps_style'] += " prioritizing rapid iteration, flexibility, and adaptive execution"
        
        # Add risk tolerance consideration
        risk_tolerance = organizational_profile.get('risk_tolerance', 'medium')
        if risk_tolerance == 'low':
            enhanced_template['framework_emphasis'] += ", prioritizing risk mitigation and conservative approaches"
        elif risk_tolerance == 'high':
            enhanced_template['framework_emphasis'] += ", embracing calculated risks and innovative approaches"
        
        return enhanced_template
    
    return base_template

# Consistency-aware AI interface functions
async def generate_analysis_with_consistency(
    auspex_service, chat_id: int, prompt: str, model: str, 
    consistency_mode: ConsistencyMode
) -> str:
    """
    Generate AI analysis with consistency controls without modifying auspex service.
    
    This function wraps the auspex service to add consistency features while
    maintaining full backwards compatibility.
    """
    
    # Enhance prompt based on consistency mode
    enhanced_prompt = enhance_prompt_for_consistency(prompt, consistency_mode)
    
    # Collect response
    response_chunks = []
    async for chunk in auspex_service.chat_with_tools(
        chat_id=chat_id,
        message=enhanced_prompt,
        model=model,
        limit=10,
        tools_config={"search_articles": False, "get_sentiment_analysis": False}
    ):
        response_chunks.append(chunk)
    
    full_response = "".join(response_chunks)
    
    # Apply post-processing for consistency
    if consistency_mode in [ConsistencyMode.DETERMINISTIC, ConsistencyMode.LOW_VARIANCE]:
        full_response = apply_consistency_post_processing(full_response, consistency_mode)
    
    return full_response

def enhance_prompt_for_consistency(prompt: str, mode: ConsistencyMode) -> str:
    """Add consistency instructions to prompt based on mode."""
    
    consistency_instructions = {
        ConsistencyMode.DETERMINISTIC: """
CONSISTENCY REQUIREMENTS (DETERMINISTIC MODE):
- Use consistent terminology throughout analysis
- Sort trend names alphabetically when priority is equal
- Base strategic recommendations on most frequently mentioned themes
- Use standardized strength/momentum terminology (High/Medium/Low, Increasing/Steady/Decreasing)
- Generate recommendations in consistent order: most critical first
- Apply deterministic categorization patterns

""",
        ConsistencyMode.LOW_VARIANCE: """
CONSISTENCY GUIDELINES (LOW VARIANCE MODE):
- Prioritize consistent terminology and framework
- Focus on trends supported by multiple articles
- Use evidence-based trend identification
- Maintain consistent analysis structure

""",
        ConsistencyMode.BALANCED: """
ANALYSIS APPROACH (BALANCED MODE):
- Balance consistency with fresh insights
- Use structured approach while allowing creative connections
- Focus on well-supported trends with room for interpretation

""",
        ConsistencyMode.CREATIVE: ""  # No additional instructions
    }
    
    instruction = consistency_instructions.get(mode, "")
    return instruction + prompt

def apply_consistency_post_processing(response: str, mode: ConsistencyMode) -> str:
    """Apply post-processing to normalize response for consistency."""
    
    if mode not in [ConsistencyMode.DETERMINISTIC, ConsistencyMode.LOW_VARIANCE]:
        return response
    
    # Normalize common terminology
    normalizations = {
        # Trend strength variations
        r'\b(very high|extremely high)\b': 'High',
        r'\b(moderate|medium)\b': 'Medium',  
        r'\b(limited|small|minor)\b': 'Low',
        
        # Momentum variations
        r'\b(growing|rising|expanding)\b': 'Increasing',
        r'\b(stable|consistent|maintained)\b': 'Steady',
        r'\b(declining|reducing|slowing)\b': 'Decreasing',
        
        # Technology terminology
        r'\bAI/ML\b': 'AI and ML',
        r'\bmachine learning\b': 'ML',
        r'\bartificial intelligence\b': 'AI',
    }
    
    processed = response
    for pattern, replacement in normalizations.items():
        processed = re.sub(pattern, replacement, processed, flags=re.IGNORECASE)
    
    return processed

# Enhanced caching system functions
def generate_comprehensive_cache_key(
    topic: str,
    timeframe_days: int,
    model: str,
    analysis_depth: str,
    sample_size_mode: str,
    custom_limit: Optional[int],
    profile_id: Optional[int],
    consistency_mode: ConsistencyMode,
    persona: str,
    customer_type: str
) -> str:
    """
    Generate comprehensive cache key including ALL parameters that affect results.
    
    This ensures cache hits only occur when analysis parameters are truly identical.
    """
    
    # Include all parameters that could affect the result
    cache_params = {
        'topic': topic,
        'timeframe_days': timeframe_days,
        'model': model,
        'analysis_depth': analysis_depth,
        'sample_size_mode': sample_size_mode,
        'custom_limit': custom_limit,
        'profile_id': profile_id,
        'consistency_mode': consistency_mode.value,
        'persona': persona,
        'customer_type': customer_type,
        'algorithm_version': '3.0',  # Increment when algorithm changes
        'article_selection_method': 'deterministic_v2'
    }
    
    # Create hash from stable parameter representation
    params_string = json.dumps(cache_params, sort_keys=True, default=str)
    cache_hash = hashlib.sha256(params_string.encode()).hexdigest()[:16]
    
    return f"trend_convergence_{cache_hash}"

async def get_cached_analysis(
    cache_key: str,
    db: Database,
    max_age_hours: int = 24
) -> Optional[Dict[str, Any]]:
    """Get cached analysis if valid and recent enough."""

    try:
        # Use database facade for PostgreSQL compatibility
        result = (DatabaseQueryFacade(db, logger)).get_cached_trend_analysis(cache_key)

        if result:
            # Use column name access for dictionary-like objects
            analysis_data = json.loads(result['version_data'])
            created_at = datetime.fromisoformat(result['created_at'])
            age_hours = (datetime.now() - created_at).total_seconds() / 3600

            if age_hours <= max_age_hours:
                # Add cache metadata
                analysis_data['_cache_info'] = {
                    'cached': True,
                    'age_hours': round(age_hours, 2),
                    'cache_key': cache_key
                }

                logger.info(f"Cache hit: {cache_key} (age: {age_hours:.1f}h)")
                return analysis_data
            else:
                logger.info(f"Cache expired: {cache_key} (age: {age_hours:.1f}h)")

    except Exception as e:
        logger.error(f"Error retrieving cached analysis: {e}")

    return None

async def save_analysis_with_cache(
    cache_key: str,
    topic: str,
    analysis_data: Dict[str, Any],
    db: Database
):
    """Save analysis with comprehensive cache information."""

    try:
        # Ensure enhanced cache table exists
        await ensure_cache_table_v2(db)

        cache_metadata = {
            'article_count': analysis_data.get('articles_analyzed', 0),
            'total_trends': sum(
                len(timeframe.get('trends', []))
                for timeframe in analysis_data.get('strategic_recommendations', {}).values()
                if isinstance(timeframe, dict)
            ),
            'model_used': analysis_data.get('model_used'),
            'consistency_mode': analysis_data.get('consistency_mode'),
            'generation_time': analysis_data.get('generated_at')
        }

        # Use database facade for PostgreSQL compatibility
        (DatabaseQueryFacade(db, logger)).save_cached_trend_analysis(
            cache_key,
            topic,
            json.dumps(analysis_data),
            json.dumps(cache_metadata),
            datetime.now().isoformat()
        )

        logger.info(f"Cached analysis: {cache_key}")

    except Exception as e:
        logger.error(f"Failed to cache analysis: {e}")

async def ensure_cache_table_v2(db: Database):
    """Ensure the enhanced cache table exists."""

    try:
        # Use database facade for PostgreSQL compatibility
        (DatabaseQueryFacade(db, logger)).ensure_analysis_cache_table()
    except Exception as e:
        logger.error(f"Failed to ensure cache table: {e}")

@router.get("/api/trend-convergence/{topic}/previous")
async def load_previous_analysis(
    topic: str,
    db: Database = Depends(get_database_instance)
):
    """Load the latest previous analysis version for a topic"""
    try:
        previous_analysis = await _load_latest_analysis_version(topic, db)
        if previous_analysis:
            return previous_analysis
        else:
            raise HTTPException(status_code=404, detail="No previous analysis found for this topic")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error loading previous analysis: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.get("/trend-convergence", response_class=HTMLResponse)
async def trend_convergence_page(request: Request, session: dict = Depends(verify_session)):
    """Render the trend convergence analysis page"""
    return templates.TemplateResponse("trend_convergence.html", {"request": request, "session": session})

# Organizational Profile Management Endpoints

@router.get("/api/organizational-profiles")
async def get_organizational_profiles(db: Database = Depends(get_database_instance)):
    """Get all organizational profiles"""
    try:
        profiles_data = (DatabaseQueryFacade(db, logger)).get_organisational_profiles()
        profiles = []

        for profile_row in profiles_data:
            profile = {
                'id': profile_row['id'],
                'name': profile_row['name'],
                'description': profile_row['description'],
                'industry': profile_row['industry'],
                'organization_type': profile_row['organization_type'],
                'region': profile_row['region'],
                'key_concerns': json.loads(profile_row['key_concerns']) if profile_row['key_concerns'] else [],
                'strategic_priorities': json.loads(profile_row['strategic_priorities']) if profile_row['strategic_priorities'] else [],
                'risk_tolerance': profile_row['risk_tolerance'],
                'innovation_appetite': profile_row['innovation_appetite'],
                'decision_making_style': profile_row['decision_making_style'],
                'stakeholder_focus': json.loads(profile_row['stakeholder_focus']) if profile_row['stakeholder_focus'] else [],
                'competitive_landscape': json.loads(profile_row['competitive_landscape']) if profile_row['competitive_landscape'] else [],
                'regulatory_environment': json.loads(profile_row['regulatory_environment']) if profile_row['regulatory_environment'] else [],
                'custom_context': profile_row['custom_context'],
                'is_default': bool(profile_row['is_default']),
                'created_at': profile_row['created_at'],
                'updated_at': profile_row['updated_at']
            }
            profiles.append(profile)

        return {"success": True, "profiles": profiles}

    except Exception as e:
        logger.error(f"Error fetching organizational profiles: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch profiles: {str(e)}")

@router.post("/api/organizational-profiles") 
async def create_organizational_profile(
    profile_data: ProfileCreateRequest,
    db: Database = Depends(get_database_instance)
):
    """Create a new organizational profile"""
    try:
        # Check if profile name already exists
        existing = (DatabaseQueryFacade(db, logger)).get_organisational_profile(profile_data.name)
        
        if existing:
            raise HTTPException(status_code=409, detail="Profile with this name already exists")
        
        # Insert new profile
        profile_id = (DatabaseQueryFacade(db, logger)).create_organisational_profile((
            profile_data.name,
            profile_data.description,
            profile_data.industry,
            profile_data.organization_type,
            profile_data.region,
            json.dumps(profile_data.key_concerns),
            json.dumps(profile_data.strategic_priorities),
            profile_data.risk_tolerance,
            profile_data.innovation_appetite,
            profile_data.decision_making_style,
            json.dumps(profile_data.stakeholder_focus),
            json.dumps(profile_data.competitive_landscape),
            json.dumps(profile_data.regulatory_environment),
            profile_data.custom_context
        ))
        
        return {"success": True, "profile_id": profile_id, "message": "Profile created successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating organizational profile: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to create profile: {str(e)}")

@router.put("/api/organizational-profiles/{profile_id}")
async def update_organizational_profile(
    profile_id: int,
    profile_data: ProfileCreateRequest,
    db: Database = Depends(get_database_instance)
):
    """Update an existing organizational profile"""
    try:
        # Check if profile exists
        existing = (DatabaseQueryFacade(db, logger)).get_organisational_profile_by_id(profile_id)
        
        if not existing:
            raise HTTPException(status_code=404, detail="Profile not found")
        
        # Check if new name conflicts with existing profiles (excluding current)
        name_conflict = (DatabaseQueryFacade(db, logger)).check_organisational_profile_name_conflict(profile_data.name, profile_id)
        
        if name_conflict:
            raise HTTPException(status_code=409, detail="Profile with this name already exists")
        
        # Update profile
        (DatabaseQueryFacade(db, logger)).update_organisational_profile((
            profile_data.name,
            profile_data.description,
            profile_data.industry,
            profile_data.organization_type,
            profile_data.region,
            json.dumps(profile_data.key_concerns),
            json.dumps(profile_data.strategic_priorities),
            profile_data.risk_tolerance,
            profile_data.innovation_appetite,
            profile_data.decision_making_style,
            json.dumps(profile_data.stakeholder_focus),
            json.dumps(profile_data.competitive_landscape),
            json.dumps(profile_data.regulatory_environment),
            profile_data.custom_context,
            profile_id
        ))
        
        return {"success": True, "message": "Profile updated successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating organizational profile: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to update profile: {str(e)}")

@router.delete("/api/organizational-profiles/{profile_id}")
async def delete_organizational_profile(
    profile_id: int,
    db: Database = Depends(get_database_instance)
):
    """Delete an organizational profile"""
    try:
        # Check if profile exists and is not default
        profile = (DatabaseQueryFacade(db, logger)).check_if_profile_exists_and_is_not_default(profile_id)
        
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")
            
        if profile[0]:  # is_default
            raise HTTPException(status_code=400, detail="Cannot delete default profiles")
        
        # Delete profile
        (DatabaseQueryFacade(db, logger)).delete_organisational_profile(profile_id)
        
        return {"success": True, "message": "Profile deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting organizational profile: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete profile: {str(e)}")

@router.get("/api/organizational-profiles/{profile_id}")
async def get_organizational_profile(
    profile_id: int,
    db: Database = Depends(get_database_instance)
):
    """Get a specific organizational profile"""
    try:
        profile_row = (DatabaseQueryFacade(db, logger)).get_organizational_profile_for_ui(profile_id)
        
        if not profile_row:
            raise HTTPException(status_code=404, detail="Profile not found")
        
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
            'is_default': bool(profile_row[15]),
            'created_at': profile_row[16],
            'updated_at': profile_row[17]
        }
        
        return {"success": True, "profile": profile}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching organizational profile: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch profile: {str(e)}") 