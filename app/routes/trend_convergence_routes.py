from fastapi import APIRouter, HTTPException, Query, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.security.session import verify_session
from typing import List, Dict, Optional, Callable, Any
import logging
import json
import hashlib
import re
import uuid
import time
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from pydantic import BaseModel
from enum import Enum

from app.database import Database, get_database_instance
from app.database_query_facade import DatabaseQueryFacade
from app.services.auspex_service import get_auspex_service
from app.services.prompt_loader import PromptLoader

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

def filter_articles_by_source_quality(articles: List, source_quality: str) -> List:
    """
    Filter articles based on source quality setting.

    Args:
        articles: List of article dictionaries
        source_quality: 'all' or 'high_quality'

    Returns:
        Filtered list of articles
    """
    if source_quality == 'all':
        return articles

    # High quality filter: factual_reporting in ['High', 'Very High'] AND mbfc_credibility_rating in ['High', 'Very High']
    high_quality_articles = []
    for article in articles:
        factual = (article.get('factual_reporting') or '').strip()
        credibility = (article.get('mbfc_credibility_rating') or '').strip()

        # Accept if both factuality and credibility are High or Very High
        if (factual in ['High', 'Very High', 'high', 'very high']) and \
           (credibility in ['High', 'Very High', 'high', 'very high']):
            high_quality_articles.append(article)

    return high_quality_articles

def weight_articles_for_dashboard(articles: List, dashboard_type: str) -> List:
    """
    Weight/prioritize articles based on dashboard-specific criteria.
    Returns articles sorted by relevance for that dashboard type.

    Args:
        articles: List of article dictionaries
        dashboard_type: 'consensus', 'strategic', 'signals', 'timeline', 'horizons'

    Returns:
        Articles sorted by dashboard-specific relevance
    """
    from datetime import datetime, timedelta
    import copy

    scored_articles = []
    now = datetime.now()

    for article in articles:
        score = 0.0
        # Convert RowMapping to dict if needed
        if hasattr(article, '_mapping'):
            article_dict = dict(article._mapping)
        elif hasattr(article, '__dict__'):
            article_dict = dict(article.__dict__)
        else:
            article_dict = dict(article)

        # Parse publication date
        pub_date_str = article_dict.get('publication_date', '')
        try:
            if pub_date_str:
                pub_date = datetime.fromisoformat(pub_date_str.replace('Z', '+00:00'))
                # Remove timezone info to make it naive for comparison
                if pub_date.tzinfo is not None:
                    pub_date = pub_date.replace(tzinfo=None)
            else:
                pub_date = now
        except:
            pub_date = now

        days_old = (now - pub_date).days

        if dashboard_type == 'consensus':
            # Prioritize articles with high agreement signals
            # Boost articles with quality indicators
            quality_score = article_dict.get('quality_score', 0) or 0
            score += float(quality_score) * 2

            # Boost articles from high-credibility sources
            if (article_dict.get('mbfc_credibility_rating') or '').lower() in ['high', 'very high']:
                score += 5

            # Slight preference for recent but not too recent (30-180 days old)
            if 30 <= days_old <= 180:
                score += 3

        elif dashboard_type == 'strategic':
            # Prioritize authoritative sources and long-form analysis
            # High factuality and credibility
            if (article_dict.get('factual_reporting') or '').lower() in ['high', 'very high']:
                score += 5
            if (article_dict.get('mbfc_credibility_rating') or '').lower() in ['high', 'very high']:
                score += 5

            # Quality score boost
            quality_score = article_dict.get('quality_score', 0) or 0
            score += float(quality_score) * 3

            # Moderate recency preference (within 1 year)
            if days_old <= 365:
                score += 2

        elif dashboard_type == 'signals':
            # Prioritize recent articles (last 90 days) and emerging trends
            if days_old <= 30:
                score += 10  # Very recent
            elif days_old <= 90:
                score += 7   # Recent
            elif days_old <= 180:
                score += 3   # Moderately recent

            # Boost articles marked with future signals
            if article_dict.get('future_signal'):
                score += 5

            # Time to impact indicators
            if (article_dict.get('time_to_impact') or '').lower() in ['immediate', 'short-term']:
                score += 4

        elif dashboard_type == 'timeline':
            # Prioritize articles with temporal mentions
            # Boost articles with time_to_impact data
            if article_dict.get('time_to_impact'):
                score += 7

            # Distribute across time periods - prefer variety
            if days_old <= 60:
                score += 4
            elif days_old <= 180:
                score += 5  # Sweet spot for timeline analysis
            elif days_old <= 365:
                score += 3

            # Quality matters for timeline accuracy
            quality_score = article_dict.get('quality_score', 0) or 0
            score += float(quality_score) * 2

        elif dashboard_type == 'horizons':
            # Prioritize speculative/forward-looking content
            # Future signals are key
            if article_dict.get('future_signal'):
                score += 8

            # Longer time to impact = more relevant for futures
            time_impact = (article_dict.get('time_to_impact') or '').lower()
            if 'long' in time_impact or 'mid' in time_impact:
                score += 6

            # Some recency but not critical
            if days_old <= 180:
                score += 2

        else:  # Default/unknown dashboard type
            # Basic quality scoring
            quality_score = article_dict.get('quality_score', 0) or 0
            score += float(quality_score)

        article_dict['dashboard_score'] = score
        scored_articles.append((score, article_dict))

    # Sort by score (highest first) and return articles
    scored_articles.sort(key=lambda x: x[0], reverse=True)
    return [article for (score, article) in scored_articles]

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

@router.get("/api/trend-convergence/models")
async def get_trend_convergence_models():
    """Get available AI models for trend convergence analysis"""
    try:
        # Import AI models
        from app.ai_models import list_available_models

        # Get available models
        models = list_available_models()

        # Format for frontend with context limits
        formatted_models = []
        for model_id, model_name in models.items():
            context_limit = CONTEXT_LIMITS.get(model_id, CONTEXT_LIMITS['default'])
            formatted_models.append({
                'id': model_id,
                'name': model_name,
                'context_limit': context_limit
            })

        return formatted_models
    except Exception as e:
        logger.error(f"Error fetching models: {str(e)}")
        # Return default models as fallback
        return [
            {'id': 'gpt-4o-mini', 'name': 'GPT-4o Mini', 'context_limit': 128000},
            {'id': 'gpt-4.1-mini', 'name': 'GPT-4.1 Mini', 'context_limit': 1000000},
            {'id': 'claude-3.5-sonnet', 'name': 'Claude 3.5 Sonnet', 'context_limit': 200000}
        ]

@router.get("/api/trend-convergence/{topic}")
async def generate_trend_convergence(
    topic: str,
    timeframe_days: int = Query(365),
    model: str = Query(...),
    source_quality: str = Query("all", description="Source quality filter: all, high_quality"),
    sample_size_mode: str = Query("auto"),
    custom_limit: int = Query(None),
    persona: str = Query("executive", description="Analysis persona: executive, analyst, strategist"),
    customer_type: str = Query("general", description="Customer type: general, enterprise, startup"),
    consistency_mode: ConsistencyMode = Query(ConsistencyMode.BALANCED, description="AI consistency: deterministic, low_variance, balanced, creative"),
    enable_caching: bool = Query(True, description="Enable result caching"),
    cache_duration_hours: int = Query(24, description="Cache validity period"),
    profile_id: int = Query(None, description="Organizational profile ID for context"),
    tab: str = Query(None, description="Specific tab to generate: consensus, strategic, signals, timeline, horizons, or None for all"),
    db: Database = Depends(get_database_instance),
    session: dict = Depends(verify_session)
):
    """Generate trend convergence analysis with improved consistency and tab-specific generation"""
    
    try:
        logger.info(f"Generating trend convergence analysis for topic: {topic}, model: {model}, consistency: {consistency_mode.value}")

        # Generate unique run ID for this analysis
        import uuid
        run_id = str(uuid.uuid4())

        # Generate comprehensive cache key for all parameters including tab
        cache_key = generate_comprehensive_cache_key(
            topic, timeframe_days, model, source_quality, sample_size_mode,
            custom_limit, profile_id, consistency_mode, persona, customer_type, tab
        )

        # Try to get cached result first if caching is enabled
        if enable_caching:
            cached_result = await get_cached_analysis(cache_key, db, cache_duration_hours)
            if cached_result:
                logger.info(f"Returning cached analysis for {topic} (consistency: {consistency_mode.value})")

                # Log cache hit
                facade = DatabaseQueryFacade(db, logger)
                facade.create_analysis_run_log(
                    run_id=run_id,
                    analysis_type='trend_convergence',
                    topic=topic,
                    model_used=model,
                    sample_size=optimal_sample_size if 'optimal_sample_size' in locals() else None,
                    timeframe_days=timeframe_days,
                    consistency_mode=consistency_mode.value,
                    profile_id=profile_id,
                    persona=persona,
                    customer_type=customer_type,
                    cache_key=cache_key,
                    cache_hit=True,
                    metadata={'source_quality': source_quality}
                )
                facade.complete_analysis_run_log(run_id, status='completed')

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

        # Filter by source quality if specified
        filtered_articles = filter_articles_by_source_quality(articles, source_quality)
        logger.info(f"After source quality filter ({source_quality}): {len(filtered_articles)} articles")

        if not filtered_articles:
            if source_quality == 'high_quality':
                # Inform user that no high-quality articles exist, suggest alternative
                total_count = len(articles)
                raise HTTPException(
                    status_code=422,
                    detail=f"No high-quality articles found for topic '{topic}'. Found {total_count} total articles. Please change 'Source Quality' filter to 'All Sources' in the configuration panel."
                )
            else:
                raise HTTPException(
                    status_code=404,
                    detail=f"No articles found for topic '{topic}'. Please check the topic name or add more articles to the database."
                )

        # Weight/prioritize articles for the specific dashboard type (if tab is specified)
        if tab:
            weighted_articles = weight_articles_for_dashboard(filtered_articles, tab)
            logger.info(f"Articles weighted for dashboard type: {tab}")
        else:
            # No specific tab, use default weighting (balanced)
            weighted_articles = filtered_articles

        # Use deterministic article selection for consistency
        diverse_articles = select_articles_deterministic(weighted_articles, min(len(weighted_articles), optimal_sample_size), consistency_mode)
        logger.info(f"Selected {len(diverse_articles)} diverse articles using {consistency_mode.value} mode")

        # Create analysis run log
        facade = DatabaseQueryFacade(db, logger)
        facade.create_analysis_run_log(
            run_id=run_id,
            analysis_type='trend_convergence',
            topic=topic,
            model_used=model,
            sample_size=optimal_sample_size,
            timeframe_days=timeframe_days,
            consistency_mode=consistency_mode.value,
            profile_id=profile_id,
            persona=persona,
            customer_type=customer_type,
            cache_key=cache_key,
            cache_hit=False,
            metadata={
                'source_quality': source_quality,
                'sample_size_mode': sample_size_mode,
                'custom_limit': custom_limit
            }
        )

        # Log all articles being reviewed
        facade.log_articles_for_analysis_run(run_id, diverse_articles)

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


        # Determine which prompt to use based on tab parameter
        if tab == "consensus":
            # Use specialized consensus analysis prompt
            logger.info("Generating Consensus Analysis tab only")
            formatted_prompt = generate_consensus_analysis_prompt(
                topic, diverse_articles, org_context, prompt_template
            )
        elif tab == "strategic":
            # Use specialized strategic recommendations prompt
            logger.info("Generating Strategic Recommendations tab only")
            formatted_prompt = generate_strategic_recommendations_prompt(
                topic, diverse_articles, org_context, prompt_template
            )
        elif tab == "signals":
            # Use specialized market signals prompt
            logger.info("Generating Market Signals tab only")
            formatted_prompt = generate_market_signals_prompt(
                topic, diverse_articles, org_context
            )
        elif tab == "timeline":
            # Use specialized impact timeline prompt
            logger.info("Generating Impact Timeline tab only")
            formatted_prompt = generate_impact_timeline_prompt(
                topic, diverse_articles, org_context
            )
        elif tab == "horizons":
            # Use specialized future horizons prompt
            logger.info("Generating Future Horizons tab only")
            formatted_prompt = generate_future_horizons_prompt(
                topic, diverse_articles, org_context
            )
            logger.info(f"Future Horizons prompt (first 500 chars): {formatted_prompt[:500]}")
            logger.info(f"Checking if prompt contains 'Three Horizons': {'Three Horizons' in formatted_prompt}")
            logger.info(f"Checking if prompt contains 'h1|h2|h3': {'h1|h2|h3' in formatted_prompt}")
        else:
            # Generate all tabs with unified prompt (legacy mode)
            logger.info("Generating all tabs with unified prompt")
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
      "consensus_percentage": 80,
      "consensus_type": "Positive Growth|Mixed Consensus|Regulatory Response|Safety/Security|Societal Impact",
      "probability": "High|Medium|Low",
      "impact": "Transformative|Significant|Moderate",
      "timeframe": "2025-2028",
      "timeline_start_year": 2024,
      "timeline_end_year": 2050,
      "timeline_consensus": "Short-term (2025-2027)|Mid-term (2027-2030)|Long-term (2030-2035+)",
      "sentiment_distribution": {{
        "positive": 60,
        "neutral": 25,
        "critical": 15
      }},
      "articles_analyzed": 45,
      "converging_trends": ["Trend Name 1", "Trend Name 2"],
      "key_indicators": ["indicator1", "indicator2"],
      "optimistic_outlier": {{
        "year": 2024,
        "description": "Optimistic scenario description",
        "source_percentage": 25
      }},
      "pessimistic_outlier": {{
        "year": 2040,
        "description": "Pessimistic scenario description",
        "source_percentage": 35
      }},
      "strategic_implication": "Strategic implication or action recommendation",
      "key_articles": [
        {{
          "title": "Article title from source data",
          "url": "https://example.com/article",
          "summary": "Brief summary of why this article supports this convergence",
          "sentiment": "positive|neutral|critical"
        }}
      ]
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
  ],
  "future_signals": [
    {{
      "name": "Signal name describing the future indicator",
      "description": "Brief description of the signal",
      "frequency": "Badge|Emerging|Established|Dominant",
      "time_to_impact": "Immediate/Short-term|Mid-term|Long-term"
    }}
  ],
  "disruption_scenarios": [
    {{
      "title": "Scenario title",
      "description": "Description of the potential disruption or risk",
      "probability": "High|Medium|Low",
      "severity": "Critical|Significant|Moderate"
    }}
  ],
  "opportunities": [
    {{
      "title": "Opportunity title",
      "description": "Description of the strategic opportunity",
      "feasibility": "High|Medium|Low",
      "potential_impact": "Transformative|Significant|Moderate"
    }}
  ],
  "key_insights": [
    {{
      "quote": "Key insight or quote from analysis",
      "source": "Source attribution (e.g., 'Industry Analysis', 'Market Research')",
      "relevance": "How this insight relates to the topic"
    }}
  ],
  "impact_timeline": [
    {{
      "title": "Impact area title",
      "description": "Brief description of the impact",
      "timeline_start": 2024,
      "timeline_end": 2030,
      "tooltip_positions": [
        {{"year": 2025, "label": "Tooltip"}},
        {{"year": 2028, "label": "Tooltip"}}
      ]
    }}
  ],
  "scenarios": [
    {{
      "title": "Scenario title",
      "description": "Description of the scenario",
      "probability": "Plausible|Probable|Possible|Preferable|Wildcard",
      "timeframe": "2025-2027",
      "icon": "📝"
    }}
  ]
}}

ARTICLE DATA:
{analysis_summary}

ANALYSIS INSTRUCTIONS:
- Identify 2 major trends for each time horizon (near-term, mid-term, long-term)
- Find 3-4 convergence points where trends intersect across timeframes
- For each convergence, calculate consensus percentage (typically 70-90% for strong consensus)
- For each convergence, identify BOTH optimistic and pessimistic outliers with specific years, descriptions, and source percentages
- For each convergence, determine the consensus_type (Positive Growth, Mixed Consensus, Regulatory Response, Safety/Security, or Societal Impact)
- For each convergence, analyze sentiment distribution across articles (positive, neutral, critical percentages that sum to 100)
- For each convergence, specify timeline_consensus (Short-term 2025-2027, Mid-term 2027-2030, or Long-term 2030-2035+)
- For each convergence, set articles_analyzed to the number of relevant articles supporting this convergence
- For each convergence, include 2-3 key supporting articles from the article data with real URLs and summaries
- For each convergence, provide a strategic_implication that explains the business/organizational impact
- Create 4 impact timeline items showing key impact areas
- Create 4-6 scenarios across probability categories (Plausible: 2-3, Probable: 2-3)
- Create 3-4 executive decision principles for strategic planning
- Provide 3-4 specific, actionable next steps with priorities
- Identify 3-4 future signals with their frequency and time to impact
- Identify 2 disruption scenarios or strategic risks
- Identify 2 strategic opportunities
- Extract 4-6 key insights from evidence synthesis - these should be compelling quotes or observations from the analysis with clear source attribution and relevance explanation
- Focus on cross-cutting patterns and concise, actionable content
- Keep all descriptions brief and to the point

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

RESPONSE FORMAT:
- Return ONLY the JSON object above, no additional text
- Keep all descriptions concise (under 80 words each)
- Ensure proper JSON formatting with all brackets and commas
- Do not include any explanatory text outside the JSON

ARTICLES FOR ANALYSIS:
Below are the {len(articles)} articles to analyze. When citing articles in key_articles, use the actual title and uri from these articles:

"""

        # Add article details to the prompt
        for i, article in enumerate(articles[:100], 1):  # Limit to first 100 to avoid token limits
            formatted_prompt += f"""
Article {i}:
- Title: {article.get('title', 'Untitled')}
- URI: {article.get('uri', 'No URI')}
- Summary: {article.get('summary', 'No summary')[:200]}
- Publication Date: {article.get('publication_date', 'Unknown')}
- Sentiment: {article.get('sentiment', 'Unknown')}
- Category: {article.get('category', 'Unknown')}
"""

        formatted_prompt += "\nNow analyze these articles and provide the JSON response."
        
        # Use Auspex service for reliable AI response handling (like consensus analysis)
        auspex = get_auspex_service()
        
        try:
            # Create a temporary chat session for the analysis
            # Note: user_id must be None if user doesn't exist in users table due to foreign key constraint
            user_from_session = session.get('user')
            user_id = None  # Default to None for foreign key safety

            if user_from_session and not isinstance(user_from_session, dict):
                # Only use user_id if it's a string (username) from the users table
                # OAuth users are stored as dicts and should use user_id=None
                user_id = user_from_session

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

            # Check for common API errors in the response text
            if "Error generating response:" in response_text:
                error_message = response_text

                # Check for specific error types
                if "RateLimitError" in error_message or "exceeded your current quota" in error_message:
                    logger.error(f"API quota/rate limit error: {error_message}")
                    raise HTTPException(
                        status_code=429,
                        detail=f"API quota exceeded for model '{model}'. Please switch to a different model or add credits to your API account."
                    )
                elif "AuthenticationError" in error_message or "Invalid API key" in error_message:
                    logger.error(f"API authentication error: {error_message}")
                    raise HTTPException(
                        status_code=401,
                        detail=f"API authentication failed for model '{model}'. Please check your API key configuration."
                    )
                elif "ServiceUnavailableError" in error_message or "overloaded" in error_message:
                    logger.error(f"API service unavailable: {error_message}")
                    raise HTTPException(
                        status_code=503,
                        detail=f"AI service temporarily unavailable for model '{model}'. Please try again in a few moments."
                    )
                else:
                    logger.error(f"AI service error: {error_message}")
                    raise HTTPException(
                        status_code=500,
                        detail=f"AI model error: {error_message[:200]}..."
                    )

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

        # Handle tab-specific responses differently than unified responses
        if tab:
            # For tab-specific requests, the response contains only that tab's data
            # We need to ensure the proper structure is returned
            logger.info(f"Processing tab-specific response for tab: {tab}")

            # Create a base structure
            full_response = {
                'topic': topic,
                'strategic_recommendations': {},
                'convergences': [],
                'executive_decision_framework': {"principles": []},
                'next_steps': [],
                'future_signals': [],
                'disruption_scenarios': [],
                'opportunities': [],
                'key_insights': [],
                'impact_timeline': [],
                'scenarios': []
            }

            # Merge the tab-specific data into the full structure
            full_response.update(trend_convergence_data)
            trend_convergence_data = full_response
        else:
            # For unified responses, ensure all required fields exist
            if 'strategic_recommendations' not in trend_convergence_data:
                trend_convergence_data['strategic_recommendations'] = {}
            if 'convergences' not in trend_convergence_data:
                trend_convergence_data['convergences'] = []
            if 'executive_decision_framework' not in trend_convergence_data:
                trend_convergence_data['executive_decision_framework'] = {"principles": []}
            if 'next_steps' not in trend_convergence_data:
                trend_convergence_data['next_steps'] = []
            if 'future_signals' not in trend_convergence_data:
                trend_convergence_data['future_signals'] = []
            if 'disruption_scenarios' not in trend_convergence_data:
                trend_convergence_data['disruption_scenarios'] = []
            if 'opportunities' not in trend_convergence_data:
                trend_convergence_data['opportunities'] = []
            if 'key_insights' not in trend_convergence_data:
                trend_convergence_data['key_insights'] = []
            if 'impact_timeline' not in trend_convergence_data:
                trend_convergence_data['impact_timeline'] = []
            if 'scenarios' not in trend_convergence_data:
                trend_convergence_data['scenarios'] = []
        
        # Validate that the response is valid JSON
        try:
            # Test that we can serialize and deserialize the data
            json.dumps(trend_convergence_data)
        except (TypeError, ValueError) as e:
            logger.error(f"Invalid JSON structure in response: {e}")
            raise HTTPException(status_code=500, detail="AI response contains invalid JSON structure")

        # Validate Three Horizons scenarios
        if 'scenarios' in trend_convergence_data and isinstance(trend_convergence_data['scenarios'], list):
            for i, scenario in enumerate(trend_convergence_data['scenarios']):
                if not isinstance(scenario, dict):
                    logger.error(f"Scenario {i} is not a dict: {scenario}")
                    continue

                # Log actual type value for debugging
                actual_type = scenario.get('type', 'MISSING')
                logger.info(f"Scenario {i} '{scenario.get('title', 'NO TITLE')}' has type: '{actual_type}'")

                # Validate type is one of h1, h2, h3
                if actual_type not in ['h1', 'h2', 'h3']:
                    logger.error(f"INVALID TYPE: Scenario {i} has type '{actual_type}' instead of h1/h2/h3")
                    logger.error(f"Full scenario: {scenario}")

        # Normalize sentiment distributions in categories (fix data quality issues)
        if 'categories' in trend_convergence_data:
            for category in trend_convergence_data['categories']:
                if '1_consensus_type' in category and 'distribution' in category['1_consensus_type']:
                    dist = category['1_consensus_type']['distribution']
                    if all(key in dist for key in ['positive', 'neutral', 'critical']):
                        total = dist['positive'] + dist['neutral'] + dist['critical']

                        # If sum is around 1.0, they're fractions - convert to percentages
                        if 0.9 < total <= 1.1:
                            dist['positive'] *= 100
                            dist['neutral'] *= 100
                            dist['critical'] *= 100
                        # If sum is < 10, they're raw counts - scale to percentages
                        elif total < 10 and total > 0:
                            factor = 100.0 / total
                            dist['positive'] *= factor
                            dist['neutral'] *= factor
                            dist['critical'] *= factor

        # Add metadata
        trend_convergence_data.update({
            'generated_at': datetime.now().isoformat(),
            'articles_analyzed': len(diverse_articles),
            'total_articles_found': len(articles),
            'timeframe_days': timeframe_days,
            'model_used': model,
            'source_quality': source_quality,
            'persona': persona,
            'customer_type': customer_type,
            'consistency_mode': consistency_mode.value,
            'caching_enabled': enable_caching,
            'organizational_profile': organizational_profile,
            'version': 3  # Increment version for consistency features
        })

        # Save tab-specific analyses to dedicated tables
        if tab and tab in ['consensus', 'timeline', 'strategic', 'horizons']:
            analysis_id = str(uuid.uuid4())
            trend_convergence_data['analysis_id'] = analysis_id

            # Calculate analysis duration (approximate - from run creation)
            analysis_duration = (datetime.now() - datetime.fromisoformat(trend_convergence_data['generated_at'])).total_seconds()

            user_id = session.get('user_id')

            if tab == 'consensus':
                # Prepare article list for storage
                article_list = []
                for idx, article in enumerate(diverse_articles, 1):
                    article_list.append({
                        'id': idx,
                        'title': article.get('title', 'Untitled'),
                        'source': article.get('source', 'Unknown Source'),
                        'url': article.get('uri', article.get('url', '')),
                        'publication_date': str(article.get('publication_date', ''))[:10] if article.get('publication_date') else 'Unknown'
                    })

                # Add article_list to response data for frontend
                trend_convergence_data['article_list'] = article_list

                facade.save_consensus_analysis(
                    analysis_id=analysis_id,
                    user_id=user_id,
                    topic=topic,
                    timeframe=f"{timeframe_days} days",
                    selected_categories=[],
                    raw_output=trend_convergence_data,
                    article_list=article_list,
                    total_articles_analyzed=len(diverse_articles),
                    analysis_duration_seconds=analysis_duration
                )
                logger.info(f"Saved consensus analysis {analysis_id} to database")

                # Store reference articles for consensus analysis
                article_uris = [a.get('uri') for a in diverse_articles if a.get('uri')]
                facade.save_consensus_reference_articles(
                    consensus_id=analysis_id,
                    article_uris=article_uris,
                    topic=topic
                )
                logger.info(f"Stored {len(article_uris)} reference articles for consensus analysis {analysis_id}")

            elif tab == 'timeline':
                facade.save_impact_timeline_analysis(
                    analysis_id=analysis_id,
                    user_id=user_id,
                    topic=topic,
                    model_used=model,
                    raw_output=trend_convergence_data,
                    total_articles_analyzed=len(diverse_articles),
                    analysis_duration_seconds=analysis_duration
                )
                logger.info(f"Saved impact timeline analysis {analysis_id} to database")

                # Store reference articles for impact timeline
                article_uris = [a.get('uri') for a in diverse_articles if a.get('uri')]
                facade.save_impact_timeline_articles(
                    timeline_id=analysis_id,
                    article_uris=article_uris,
                    topic=topic
                )
                logger.info(f"Stored {len(article_uris)} reference articles for timeline analysis {analysis_id}")

            elif tab == 'strategic':
                facade.save_strategic_recommendations_analysis(
                    analysis_id=analysis_id,
                    user_id=user_id,
                    topic=topic,
                    model_used=model,
                    raw_output=trend_convergence_data,
                    total_articles_analyzed=len(diverse_articles),
                    analysis_duration_seconds=analysis_duration
                )
                logger.info(f"Saved strategic recommendations analysis {analysis_id} to database")

                # Store reference articles for strategic recommendations
                article_uris = [a.get('uri') for a in diverse_articles if a.get('uri')]
                facade.save_strategic_recommendation_articles(
                    recommendation_id=analysis_id,
                    article_uris=article_uris,
                    topic=topic
                )
                logger.info(f"Stored {len(article_uris)} reference articles for strategic recommendations {analysis_id}")

            elif tab == 'horizons':
                facade.save_future_horizons_analysis(
                    analysis_id=analysis_id,
                    user_id=user_id,
                    topic=topic,
                    model_used=model,
                    raw_output=trend_convergence_data,
                    total_articles_analyzed=len(diverse_articles),
                    analysis_duration_seconds=analysis_duration
                )
                logger.info(f"Saved future horizons analysis {analysis_id} to database")

                # Store reference articles for future horizons
                article_uris = [a.get('uri') for a in diverse_articles if a.get('uri')]
                facade.save_future_horizon_articles(
                    horizon_id=analysis_id,
                    article_uris=article_uris,
                    topic=topic
                )
                logger.info(f"Stored {len(article_uris)} reference articles for future horizons {analysis_id}")

            elif tab == 'signals':
                # Save market signals analysis (if not already being saved elsewhere)
                facade.save_market_signals_analysis(
                    analysis_id=analysis_id,
                    user_id=user_id,
                    topic=topic,
                    model_used=model,
                    raw_output=trend_convergence_data,
                    total_articles_analyzed=len(diverse_articles),
                    analysis_duration_seconds=analysis_duration
                )
                logger.info(f"Saved market signals analysis {analysis_id} to database")

                # Store reference articles for market signals
                article_uris = [a.get('uri') for a in diverse_articles if a.get('uri')]
                facade.save_market_signal_articles(
                    signal_id=analysis_id,
                    article_uris=article_uris,
                    topic=topic
                )
                logger.info(f"Stored {len(article_uris)} reference articles for market signals {analysis_id}")

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

        # Complete the analysis run log
        facade.complete_analysis_run_log(
            run_id=run_id,
            articles_analyzed=len(diverse_articles),
            status='completed'
        )

        # Add cache metadata for freshly generated data
        now = datetime.now()
        trend_convergence_data['_cache_info'] = {
            'cached': False,
            'age_hours': 0,
            'cache_key': cache_key,
            'created_at': now.isoformat(),
            'last_updated': now.strftime('%d.%m.%Y'),
            'run_id': run_id  # Include run_id for reference
        }

        # Data is now used directly by the frontend - no transformation needed

        return trend_convergence_data
        
    except HTTPException:
        # Log failed analysis if run_id exists
        if 'run_id' in locals() and 'facade' in locals():
            try:
                facade.complete_analysis_run_log(
                    run_id=run_id,
                    status='failed',
                    error_message='HTTP exception occurred'
                )
            except:
                pass
        raise
    except Exception as e:
        logger.error(f"Error generating trend convergence analysis: {str(e)}")

        # Log failed analysis if run_id exists
        if 'run_id' in locals() and 'facade' in locals():
            try:
                facade.complete_analysis_run_log(
                    run_id=run_id,
                    status='failed',
                    error_message=str(e)
                )
            except:
                pass

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

    for article in articles:  # Process all articles
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

# ============================================================================
# TAB-SPECIFIC PROMPT GENERATION FUNCTIONS
# ============================================================================

def generate_consensus_analysis_prompt(
    topic: str,
    articles: List,
    org_context: str,
    prompt_template: Dict[str, str]
) -> str:
    """
    Generate specialized prompt for Consensus Analysis tab using Auspex numbered field structure.
    Focus on evidence synthesis, convergence identification, and key insights.
    Matches skunkworkx consensus_analysis.html data structure.
    """

    analysis_summary = prepare_analysis_summary(articles, topic)

    prompt = f"""Conduct a DEEP EVIDENCE SYNTHESIS analysis of {len(articles)} articles about "{topic}".{org_context}

MISSION: Identify 3-4 major CONSENSUS CATEGORIES where trends, forecasts, and expert opinions align across multiple sources. This is NOT a summary - it's a cross-source analysis revealing patterns of agreement and disagreement.

CRITICAL CITATION INSTRUCTIONS:
- Use numbered citations [1], [2], [3] to reference articles
- The numbered article list is provided below with titles, sources, and URLs
- Example: "Multiple sources including [1] and [3] agree that..." or "According to [1], [2], and [5]..."
- Use 3-5 citations per category_description to support key claims
- Do NOT use plain text source names like "(The Hindu, Times of India)"

REQUIRED OUTPUT FORMAT - Use EXACTLY this Auspex numbered field JSON structure:
{{
  "categories": [
    {{
      "category_name": "Category Name (e.g., 'AI Safety Consensus', 'Climate Action Timeline', 'Market Transformation')",
      "category_description": "EVIDENCE-BASED description synthesizing insights from multiple sources. Use numbered citations: 'Multiple sources including [1], [3], and [7] agree that... while [2] and [5] emphasize...'",
      "articles_analyzed": {len(articles)},
      "1_consensus_type": {{
        "summary": "Positive Growth|Mixed Consensus|Regulatory Response|Safety/Security|Societal Impact|Technical Advancement|Market Shift",
        "distribution": {{
          "positive": 55,
          "neutral": 30,
          "critical": 15
        }},
        "confidence_level": 85
      }},
      "2_timeline_consensus": {{
        "distribution": {{
          "Immediate (2025)": 10,
          "Short-term (2025-2027)": 45,
          "Mid-term (2027-2030)": 30,
          "Long-term (2030-2035+)": 15
        }},
        "consensus_window": {{
          "start_year": 2027,
          "end_year": 2035,
          "label": "Mid-term (2027-2035)"
        }}
      }},
      "3_confidence_level": {{
        "majority_agreement": 80,
        "consensus_strength": "Strong|Moderate|Emerging",
        "evidence_quality": "High|Medium|Low"
      }},
      "4_optimistic_outliers": [
        {{
          "scenario": "Specific optimistic scenario title",
          "details": "Detailed description of this optimistic view. Include which sources predict this.",
          "year": 2025,
          "source_percentage": 20,
          "reference": "Source names or article titles supporting this view"
        }}
      ],
      "5_pessimistic_outliers": [
        {{
          "scenario": "Specific pessimistic scenario title",
          "details": "Detailed description of this pessimistic view. Include which sources predict this.",
          "year": 2035,
          "source_percentage": 15,
          "reference": "Source names or article titles supporting this view"
        }}
      ],
      "6_key_articles": [
        {{
          "title": "Actual article title from data",
          "url": "Actual URL from data",
          "summary": "How this article supports this consensus category",
          "sentiment": "positive|neutral|critical",
          "relevance_score": 0.95
        }}
      ],
      "7_strategic_implications": "Clear business/organizational impact. What should decision-makers do? What risks or opportunities does this reveal?",
      "8_key_decision_windows": [
        {{
          "urgency": "Critical|High|Medium|Low",
          "window": "Immediate (0-6 months)|Short-term (6-18 months)|Mid-term (18-36 months)",
          "action": "Specific actionable milestone or decision point",
          "rationale": "Why this action is important and time-sensitive",
          "owner": "Recommended team/role (e.g., 'Executive Team', 'Product Team', 'Strategy Team')",
          "dependencies": ["dependency1", "dependency2"],
          "success_metrics": ["metric1", "metric2"]
        }}
      ],
      "9_timeframe_analysis": {{
        "immediate": "Actions to take immediately (0-6 months)",
        "short_term": "Strategic positioning for 6-18 months",
        "mid_term": "Long-term implications and preparation (18-36 months)",
        "key_milestones": [
          {{
            "year": 2025,
            "milestone": "Expected milestone or checkpoint",
            "significance": "Why this milestone matters"
          }}
        ]
      }}
    }}
  ],
  "key_insights": [
    {{
      "quote": "Compelling insight or data point synthesized from evidence. Example: '75% of sources agree that X will happen by Y, with only Z expressing skepticism'",
      "source": "Multi-source synthesis|Industry Analysis|Expert Consensus|Market Research",
      "relevance": "Why this insight matters for strategic decision-making"
    }}
  ]
}}

EVIDENCE SYNTHESIS INSTRUCTIONS:

1. IDENTIFY 3-4 CONSENSUS CATEGORIES:
   - Look for themes where multiple sources agree (even if phrased differently)
   - Calculate consensus percentage based on actual source agreement
   - Don't just list what sources say - identify PATTERNS across sources
   - Each category should represent a distinct area of agreement/disagreement

2. QUANTIFY EVERYTHING ACCURATELY:
   - Consensus confidence = (# sources supporting view) / (total sources) * 100
   - Source percentages for outliers must be realistic (typically 5-25%)
   - Sentiment distribution must sum to 100%
   - Timeline distribution must sum to 100%
   - Count articles_analyzed for each category

3. CROSS-REFERENCE SOURCES:
   - Each category must cite at least 3-5 supporting articles in 6_key_articles
   - Descriptions should reference specific sources: "According to Article A..., corroborated by Article B..."
   - Identify both majority and minority positions
   - Include actual article titles and URLs from provided data

4. EXTRACT 4-6 KEY INSIGHTS (top-level):
   - These should reveal cross-cutting patterns across ALL categories
   - Include compelling statistics or data points
   - Show unexpected agreements or surprising disagreements
   - Each insight should synthesize multiple sources

5. IDENTIFY OUTLIERS PER CATEGORY (ONLY IF GENUINELY PRESENT):
   - Optimistic outliers (4_optimistic_outliers) = minority views predicting faster/better outcomes
   - Pessimistic outliers (5_pessimistic_outliers) = minority views predicting slower/worse outcomes
   - ONLY include outliers if sources genuinely present dissenting views (>5% of sources)
   - May have 0-3 optimistic outliers and 0-3 pessimistic outliers per category
   - DO NOT fabricate outliers if sources show strong consensus
   - Calculate what % of sources hold each outlier view (must be realistic: 5-25%)
   - Be specific about years and scenarios
   - Each outlier must cite actual sources from the data

6. STRATEGIC IMPLICATIONS (7_strategic_implications):
   - For each category, explain business/organizational impact
   - What decisions should be made based on this consensus?
   - What risks or opportunities does this reveal?
   - Be specific and actionable, not generic

7. KEY DECISION WINDOWS (8_key_decision_windows) - 3-5 per category:
   - Identify specific time-sensitive action points
   - Urgency levels: Critical (red), High (orange), Medium (blue), Low (gray)
   - Assign realistic timeframes: Immediate (0-6 months), Short-term (6-18 months), Mid-term (18-36 months)
   - Specify who should own each action
   - Define measurable success metrics
   - Note any dependencies or prerequisites
   - Make actions concrete and executable, not generic advice

8. TIMEFRAME ANALYSIS (9_timeframe_analysis) per category:
   - Break down implications across three timeframes:
   - **Immediate (0-6 months)**: What needs to happen right now? Urgent decisions, immediate actions
   - **Short-term (6-18 months)**: Strategic positioning, capability building, resource allocation
   - **Mid-term (18-36 months)**: Long-term preparation, transformation initiatives, competitive positioning
   - Identify 2-3 key milestones within the consensus timeline with specific years
   - For each milestone, explain its significance and what it means for the organization

9. TIMELINE CONSENSUS (2_timeline_consensus):
   - Calculate realistic distribution across time periods based on article data
   - consensus_window should capture the PRIMARY timeframe where most impact is expected
   - IMPORTANT: start_year should reflect when impact BEGINS to manifest (can be > 2025, NOT always 2025)
   - start_year and end_year define the thick colored bar on the timeline visualization (2025-2050 range)
   - Example: If impact mainly occurs 2030-2040, use start_year: 2030, end_year: 2040
   - Make sure this aligns with the distribution percentages

10. CONSENSUS TYPE (1_consensus_type):
   - Choose the type that best represents the nature of this consensus category
   - Calculate accurate sentiment distribution from articles (positive, neutral, critical)
   - CRITICAL: Distribution values MUST sum to 100 (they are percentages, not decimals or counts)
   - Example: {{"positive": 60, "neutral": 30, "critical": 10}} (sums to 100)
   - Confidence level should reflect strength of agreement (typically 60-95%)

QUALITY REQUIREMENTS:
- Every claim must reference specific sources
- Percentages must be calculated from actual article counts and be realistic
- Descriptions must synthesize across sources, not just summarize one
- Timeline predictions must be grounded in source data
- No generic statements - be specific and evidence-based
- All article references in 6_key_articles must use real titles and URLs from data
- Outliers should be genuinely different perspectives, not just variations

ARTICLE DATA FOR ANALYSIS:
{analysis_summary}

NUMBERED ARTICLE LIST (Use these numbers for citations):
"""

    # Add numbered article list
    for idx, article in enumerate(articles, 1):  # Include all articles
        title = article.get('title', 'Untitled')
        source = article.get('source', 'Unknown Source')
        url = article.get('uri', article.get('url', ''))
        pub_date = str(article.get('publication_date', ''))[:10] if article.get('publication_date') else 'Unknown'

        prompt += f"\n[{idx}] {title}"
        prompt += f"\n    Source: {source} | Date: {pub_date}"
        if url:
            prompt += f"\n    URL: {url}"
        prompt += "\n"

    prompt += f"""
STRATEGIC FOCUS: {prompt_template['focus']}

Now analyze these articles and return ONLY the JSON object with the Auspex numbered field structure. Focus on SYNTHESIS across sources, not individual summaries."""

    return prompt


def generate_strategic_recommendations_prompt(
    topic: str,
    articles: List,
    org_context: str,
    prompt_template: Dict[str, str]
) -> str:
    """
    Generate specialized prompt for Strategic Recommendations tab.
    Focus on near/mid/long-term trends and actionable recommendations.
    """

    analysis_summary = prepare_analysis_summary(articles, topic)

    prompt = f"""Analyze {len(articles)} articles about "{topic}" and generate strategic recommendations across three time horizons.{org_context}

CRITICAL CITATION INSTRUCTIONS:
- Use numbered citations [1], [2], [3] to reference articles
- The numbered article list is provided below with titles, sources, and URLs
- Example: "Multiple sources including [1] and [3] indicate that..." or "According to [1], [2], and [5]..."
- Use 2-4 citations per description to support key claims
- Do NOT use plain text source names like "(The Hindu, Times of India)"

REQUIRED OUTPUT FORMAT:
{{
  "strategic_recommendations": {{
    "near_term": {{
      "timeframe": "2025-2027",
      "trends": [
        {{
          "name": "Trend name",
          "description": "Detailed trend description with numbered citations [1], [2] to support analysis",
          "confidence": "High|Medium|Low",
          "key_drivers": ["driver1", "driver2"],
          "potential_impact": "Impact description with supporting citations [3], [4]"
        }}
      ]
    }},
    "mid_term": {{
      "timeframe": "2027-2030",
      "trends": [...]
    }},
    "long_term": {{
      "timeframe": "2030-2035+",
      "trends": [...]
    }}
  }},
  "executive_decision_framework": {{
    "principles": [
      {{
        "name": "Principle name",
        "description": "Principle description with citations [1], [2]",
        "rationale": "Why important, supported by [3]",
        "implementation": "How to apply"
      }}
    ]
  }},
  "next_steps": [
    {{
      "priority": "High|Medium|Low",
      "action": "Specific actionable step with supporting evidence [1], [2]",
      "timeline": "When to complete",
      "stakeholders": ["stakeholder1"],
      "success_metrics": ["metric1"]
    }}
  ]
}}

INSTRUCTIONS:
- Identify 2 major trends for each time horizon
- Create 3-4 executive decision principles
- Provide 3-4 specific, actionable next steps with priorities
- Focus on actionable insights for {prompt_template['focus']}
- Use decision-making style: {prompt_template['next_steps_style']}
- Support ALL descriptions with numbered citations from the article list below

ARTICLE DATA:
{analysis_summary}

Return ONLY the JSON object."""

    return prompt


def generate_market_signals_prompt(
    topic: str,
    articles: List,
    org_context: str
) -> str:
    """
    Generate specialized prompt for Market Signals tab.
    Focus on future signals, disruptions, and opportunities.
    """

    analysis_summary = prepare_analysis_summary(articles, topic)

    prompt = f"""Analyze {len(articles)} articles about "{topic}" and identify market signals, disruptions, and opportunities.{org_context}

CRITICAL CITATION INSTRUCTIONS:
- Use numbered citations [1], [2], [3] to reference articles
- The numbered article list is provided below with titles, sources, and URLs
- Example: "Multiple sources including [1] and [3] indicate that..." or "According to [1], [2], and [5]..."
- Use 2-4 citations per description to support key claims
- Do NOT use plain text source names like "(The Hindu, Times of India)"

REQUIRED OUTPUT FORMAT:
{{
  "future_signals": [
    {{
      "name": "Signal name",
      "description": "Signal description with numbered citations [1], [2] to support claims",
      "frequency": "Badge|Emerging|Established|Dominant",
      "time_to_impact": "Immediate/Short-term|Mid-term|Long-term"
    }}
  ],
  "disruption_scenarios": [
    {{
      "title": "Disruption title",
      "description": "Description of disruption or risk with numbered citations [1], [3] to support analysis",
      "probability": "High|Medium|Low",
      "severity": "Critical|Significant|Moderate"
    }}
  ],
  "opportunities": [
    {{
      "title": "Opportunity title",
      "description": "Description of opportunity with numbered citations [2], [4] to support potential",
      "feasibility": "High|Medium|Low",
      "potential_impact": "Transformative|Significant|Moderate"
    }}
  ]
}}

INSTRUCTIONS:
- Identify 3-4 future signals with frequency and time to impact
- Identify 2 disruption scenarios or strategic risks
- Identify 2 strategic opportunities
- Support ALL descriptions with numbered citations from the article list below

ARTICLE DATA:
{analysis_summary}

Return ONLY the JSON object."""

    return prompt


def generate_impact_timeline_prompt(
    topic: str,
    articles: List,
    org_context: str
) -> str:
    """
    Generate specialized prompt for Impact Timeline tab.
    Focus on timeline visualization of key impact areas.
    Uses PromptLoader to load prompt from data/prompts/impact_timeline/current.json
    """

    # Load prompt from JSON file
    prompt_data = PromptLoader.load_prompt("impact_timeline", "current")
    logger.info(f"Loaded Impact Timeline prompt version: {prompt_data.get('version')}")

    # Prepare analysis summary from articles
    analysis_summary = prepare_analysis_summary(articles, topic)

    # Prepare variables for prompt template
    variables = {
        "topic": topic,
        "article_count": len(articles),
        "articles": analysis_summary,
        "org_context": org_context if org_context else ""
    }

    # Fill prompt template
    system_prompt, user_prompt = PromptLoader.get_prompt_template(
        prompt_data,
        variables
    )

    # Combine system and user prompts for the existing chat_with_tools interface
    full_prompt = f"{system_prompt}\n\n{user_prompt}"

    return full_prompt


def generate_future_horizons_prompt(
    topic: str,
    articles: List,
    org_context: str
) -> str:
    """
    Generate specialized prompt for Future Horizons tab.
    Focus on Three Horizons framework showing transition from current state to future vision.
    """

    analysis_summary = prepare_analysis_summary(articles, topic)

    # Create numbered article reference list for citations
    article_references = "\n".join([
        f"[{i+1}] {article.get('title', 'Untitled')} - {article.get('source_name', 'Unknown')} - {str(article.get('publication_date', ''))[:10]}"
        for i, article in enumerate(articles[:50])  # Limit to first 50 articles
    ])

    prompt = f"""Analyze {len(articles)} articles about "{topic}" and generate future scenarios using the Three Horizons framework.{org_context}

THREE HORIZONS FRAMEWORK DEFINITIONS:
- **Horizon 1 (H1) - Current State/Declining**: The dominant paradigm today. Business-as-usual trends and systems that are gradually declining as new innovations emerge. Represents what's working now but won't sustain long-term.
- **Horizon 2 (H2) - Transition/Innovation**: Emerging innovations and disruptions. Entrepreneurial activity, pilot projects, and the transitional period where old and new systems coexist. The space of experimentation and change.
- **Horizon 3 (H3) - Future Vision/Emerging**: Transformative visions becoming reality. The preferred future state where new paradigms are fully established. Represents radical departures from current norms.

REQUIRED OUTPUT FORMAT:
{{
  "scenarios": [
    {{
      "type": "h1|h2|h3",
      "title": "Scenario title (max 12 words)",
      "description": "Detailed description with inline citations [1] [2] (2-3 sentences)",
      "timeframe": "2025-2040",
      "sentiment": "Positive|Negative|Mixed|Neutral|Mixed/Positive|Critical/Neutral|Negative/Disruptive|Trend/Evolution|Breakthrough|Disruption/Warning|Warning/Disruption"
    }}
  ]
}}

REQUIRED DISTRIBUTION:
- 4-5 H1 scenarios (current systems and business-as-usual trends that are declining)
- 4-5 H2 scenarios (emerging innovations, pilot projects, transitional disruptions)
- 3-4 H3 scenarios (transformative future visions, new paradigms)
Total: 12-14 scenarios

TIMEFRAME GUIDELINES (all scenarios in 2025-2040 range):
- H1 scenarios: Focus on 2025-2032 (current systems gradually declining)
- H2 scenarios: Focus on 2027-2037 (transition period, peak around 2030-2033)
- H3 scenarios: Focus on 2033-2040 (future visions emerging and taking hold)
- Distribute scenarios to show the transition arc from H1 → H2 → H3

ARTICLE REFERENCES (cite these using [1], [2], etc. in your scenario descriptions):
{article_references}

ARTICLE DATA SUMMARY:
{analysis_summary}

CRITICAL REQUIREMENTS:
- Use "type" field exactly as specified: "h1", "h2", or "h3" (lowercase)
- H1 scenarios should describe current dominant systems and why they're declining
- H2 scenarios should highlight innovations, experiments, and transitional tensions
- H3 scenarios should paint visions of transformed future states
- Keep titles concise (max 12 words)
- **IMPORTANT: Include citations [1], [2], [3] etc. in scenario descriptions to reference specific articles**
- Each scenario description should cite 2-4 relevant articles
- Descriptions should be 2-3 sentences with specific details and citations
- Base all scenarios on actual article data and signals from the reference list above
- Sentiment should reflect the nature of the scenario using the exact values provided
- All timeframes must be in 2025-2040 range
- Show the narrative arc: H1 declining → H2 innovating → H3 emerging

Return ONLY the JSON object with the scenarios array."""

    return prompt

# ============================================================================
# END TAB-SPECIFIC PROMPT FUNCTIONS
# ============================================================================

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
    source_quality: str,
    sample_size_mode: str,
    custom_limit: Optional[int],
    profile_id: Optional[int],
    consistency_mode: ConsistencyMode,
    persona: str,
    customer_type: str,
    tab: Optional[str] = None
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
        'source_quality': source_quality,
        'sample_size_mode': sample_size_mode,
        'custom_limit': custom_limit,
        'profile_id': profile_id,
        'consistency_mode': consistency_mode.value,
        'persona': persona,
        'customer_type': customer_type,
        'tab': tab,  # Add tab parameter for separate caching per tab
        'algorithm_version': '4.0',  # Increment for tab-specific prompts
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
                    'cache_key': cache_key,
                    'created_at': created_at.isoformat(),
                    'last_updated': created_at.strftime('%d.%m.%Y')
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
    """Render the React-based trend convergence analysis page with Auspex modal"""
    from fastapi.templating import Jinja2Templates

    templates = Jinja2Templates(directory="templates")
    return templates.TemplateResponse(
        "trend_convergence_react.html",
        {"request": request, "session": session}
    )

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
        existing = (DatabaseQueryFacade(db, logger)).get_organisational_profile_by_name(profile_data.name)
        
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


@router.get("/api/trend-convergence/consensus/{analysis_id}/raw")
async def get_consensus_analysis_raw(
    analysis_id: str,
    session=Depends(verify_session),
    db: Database = Depends(get_database_instance)
):
    """Retrieve a stored consensus analysis by ID with article list."""
    try:
        facade = DatabaseQueryFacade(db, logger)
        analysis_data = facade.get_consensus_analysis(analysis_id)

        if not analysis_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Analysis not found: {analysis_id}"
            )

        return {
            "success": True,
            "analysis_id": analysis_id,
            "topic": analysis_data.get('topic'),
            "created_at": analysis_data.get('created_at').isoformat() if analysis_data.get('created_at') else None,
            "total_articles_analyzed": analysis_data.get('total_articles_analyzed'),
            "analysis_duration_seconds": analysis_data.get('analysis_duration_seconds'),
            "raw_output": analysis_data.get('raw_output'),
            "article_list": analysis_data.get('article_list')
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving consensus analysis {analysis_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve analysis: {str(e)}"
        )


@router.get("/api/trend-convergence/timeline/{analysis_id}/raw")
async def get_impact_timeline_raw(
    analysis_id: str,
    session=Depends(verify_session),
    db: Database = Depends(get_database_instance)
):
    """Retrieve a stored impact timeline analysis by ID."""
    try:
        facade = DatabaseQueryFacade(db, logger)
        analysis_data = facade.get_impact_timeline_analysis(analysis_id)

        if not analysis_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Analysis not found: {analysis_id}"
            )

        return {
            "success": True,
            "analysis_id": analysis_id,
            "topic": analysis_data.get('topic'),
            "model_used": analysis_data.get('model_used'),
            "created_at": analysis_data.get('created_at').isoformat() if analysis_data.get('created_at') else None,
            "total_articles_analyzed": analysis_data.get('total_articles_analyzed'),
            "analysis_duration_seconds": analysis_data.get('analysis_duration_seconds'),
            "raw_output": analysis_data.get('raw_output')
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving impact timeline analysis {analysis_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve analysis: {str(e)}"
        )


@router.get("/api/trend-convergence/strategic/{analysis_id}/raw")
async def get_strategic_recommendations_raw(
    analysis_id: str,
    session=Depends(verify_session),
    db: Database = Depends(get_database_instance)
):
    """Retrieve a stored strategic recommendations analysis by ID."""
    try:
        facade = DatabaseQueryFacade(db, logger)
        analysis_data = facade.get_strategic_recommendations_analysis(analysis_id)

        if not analysis_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Analysis not found: {analysis_id}"
            )

        return {
            "success": True,
            "analysis_id": analysis_id,
            "topic": analysis_data.get('topic'),
            "model_used": analysis_data.get('model_used'),
            "created_at": analysis_data.get('created_at').isoformat() if analysis_data.get('created_at') else None,
            "total_articles_analyzed": analysis_data.get('total_articles_analyzed'),
            "analysis_duration_seconds": analysis_data.get('analysis_duration_seconds'),
            "raw_output": analysis_data.get('raw_output')
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving strategic recommendations analysis {analysis_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve analysis: {str(e)}"
        )


@router.get("/api/trend-convergence/horizons/{analysis_id}/raw")
async def get_future_horizons_raw(
    analysis_id: str,
    session=Depends(verify_session),
    db: Database = Depends(get_database_instance)
):
    """Retrieve a stored future horizons analysis by ID."""
    try:
        facade = DatabaseQueryFacade(db, logger)
        analysis_data = facade.get_future_horizons_analysis(analysis_id)

        if not analysis_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Analysis not found: {analysis_id}"
            )

        return {
            "success": True,
            "analysis_id": analysis_id,
            "topic": analysis_data.get('topic'),
            "model_used": analysis_data.get('model_used'),
            "created_at": analysis_data.get('created_at').isoformat() if analysis_data.get('created_at') else None,
            "total_articles_analyzed": analysis_data.get('total_articles_analyzed'),
            "analysis_duration_seconds": analysis_data.get('analysis_duration_seconds'),
            "raw_output": analysis_data.get('raw_output')
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving future horizons analysis {analysis_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve analysis: {str(e)}"
        )


# ============================================================================
# Reference Article Retrieval Endpoints
# ============================================================================

@router.get("/api/trend-convergence/consensus/{analysis_id}/articles")
async def get_consensus_articles(
    analysis_id: str,
    topic: str = Query(..., description="Topic name for filtering"),
    session: dict = Depends(verify_session),
    db: Database = Depends(get_database_instance)
):
    """Retrieve reference articles for a consensus analysis run"""
    try:
        facade = DatabaseQueryFacade(db, logger)
        articles = facade.get_consensus_reference_articles(analysis_id, topic)
        return {"articles": articles, "count": len(articles)}
    except Exception as e:
        logger.error(f"Error retrieving consensus reference articles for {analysis_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve articles: {str(e)}"
        )


@router.get("/api/trend-convergence/strategic/{analysis_id}/articles")
async def get_strategic_articles(
    analysis_id: str,
    topic: str = Query(..., description="Topic name for filtering"),
    session: dict = Depends(verify_session),
    db: Database = Depends(get_database_instance)
):
    """Retrieve reference articles for a strategic recommendations run"""
    try:
        facade = DatabaseQueryFacade(db, logger)
        articles = facade.get_strategic_recommendation_articles(analysis_id, topic)
        return {"articles": articles, "count": len(articles)}
    except Exception as e:
        logger.error(f"Error retrieving strategic recommendation articles for {analysis_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve articles: {str(e)}"
        )


@router.get("/api/trend-convergence/market-signals/{analysis_id}/articles")
async def get_market_signal_articles(
    analysis_id: str,
    topic: str = Query(..., description="Topic name for filtering"),
    session: dict = Depends(verify_session),
    db: Database = Depends(get_database_instance)
):
    """Retrieve reference articles for a market signals analysis run"""
    try:
        facade = DatabaseQueryFacade(db, logger)
        articles = facade.get_market_signal_articles(analysis_id, topic)
        return {"articles": articles, "count": len(articles)}
    except Exception as e:
        logger.error(f"Error retrieving market signal articles for {analysis_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve articles: {str(e)}"
        )


@router.get("/api/trend-convergence/timeline/{analysis_id}/articles")
async def get_timeline_articles(
    analysis_id: str,
    topic: str = Query(..., description="Topic name for filtering"),
    session: dict = Depends(verify_session),
    db: Database = Depends(get_database_instance)
):
    """Retrieve reference articles for an impact timeline analysis run"""
    try:
        facade = DatabaseQueryFacade(db, logger)
        articles = facade.get_impact_timeline_articles(analysis_id, topic)
        return {"articles": articles, "count": len(articles)}
    except Exception as e:
        logger.error(f"Error retrieving impact timeline articles for {analysis_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve articles: {str(e)}"
        )


@router.get("/api/trend-convergence/horizons/{analysis_id}/articles")
async def get_horizon_articles(
    analysis_id: str,
    topic: str = Query(..., description="Topic name for filtering"),
    session: dict = Depends(verify_session),
    db: Database = Depends(get_database_instance)
):
    """Retrieve reference articles for a future horizons analysis run"""
    try:
        facade = DatabaseQueryFacade(db, logger)
        articles = facade.get_future_horizon_articles(analysis_id, topic)
        return {"articles": articles, "count": len(articles)}
    except Exception as e:
        logger.error(f"Error retrieving future horizon articles for {analysis_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve articles: {str(e)}"
        )
