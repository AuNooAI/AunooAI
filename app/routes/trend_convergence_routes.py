from fastapi import APIRouter, HTTPException, Query, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.security.session import verify_session
from typing import List, Dict, Optional
import logging
import json
from datetime import datetime, timedelta
from collections import Counter, defaultdict

from app.database import Database, get_database_instance
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

router = APIRouter()
logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory="templates")

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
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Create analysis_versions table if it doesn't exist
            create_table_query = """
            CREATE TABLE IF NOT EXISTS analysis_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT NOT NULL,
                version_data TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                model_used TEXT,
                analysis_depth TEXT
            )
            """
            cursor.execute(create_table_query)
            
            # Save the version
            insert_query = """
            INSERT INTO analysis_versions (topic, version_data, model_used, analysis_depth)
            VALUES (?, ?, ?, ?)
            """
            cursor.execute(insert_query, (
                topic,
                json.dumps(analysis_data),
                analysis_data.get('model_used', 'unknown'),
                analysis_data.get('analysis_depth', 'standard')
            ))
            
            conn.commit()
            
        logger.info(f"Saved analysis version for topic: {topic}")
    except Exception as e:
        logger.error(f"Failed to save analysis version: {str(e)}")

async def _load_latest_analysis_version(topic: str, db: Database) -> Optional[Dict]:
    """Load the latest analysis version for a topic"""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            query = """
            SELECT version_data FROM analysis_versions 
            WHERE topic = ? 
            ORDER BY created_at DESC 
            LIMIT 1
            """
            cursor.execute(query, (topic,))
            result = cursor.fetchone()
            
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
    db: Database = Depends(get_database_instance),
    session: dict = Depends(verify_session)
):
    """Generate trend convergence analysis for a given topic"""
    
    try:
        logger.info(f"Generating trend convergence analysis for topic: {topic}, model: {model}")
        
        # Calculate optimal sample size based on model and mode
        # For GPT-4.1 (1M context): base_size=150 * 1.2 = 180 articles
        # For smaller models: base_size=75 * 1.2 = 90 articles
        optimal_sample_size = calculate_optimal_sample_size(model, sample_size_mode, custom_limit)
        logger.info(f"Using sample size: {optimal_sample_size} articles for model: {model}")
        
        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=timeframe_days)
        
        # Fetch articles from database with dynamic limit
        query = """
        SELECT title, summary, uri, publication_date, sentiment, category, 
               future_signal, driver_type, time_to_impact
        FROM articles 
        WHERE topic = ? 
        AND publication_date >= ? 
        AND publication_date <= ?
        AND (summary IS NOT NULL AND summary != '')
        ORDER BY publication_date DESC
        LIMIT ?
        """
        
        articles = db.fetch_all(query, (topic, start_date.isoformat(), end_date.isoformat(), optimal_sample_size))
        
        if not articles:
            raise HTTPException(
                status_code=404, 
                detail=f"No articles found for topic '{topic}' in the specified timeframe"
            )
        
        logger.info(f"Found {len(articles)} articles for analysis")
        
        # Select diverse articles for better trend analysis
        diverse_articles = select_diverse_articles(articles, min(len(articles), optimal_sample_size))
        logger.info(f"Selected {len(diverse_articles)} diverse articles for analysis")
        
        # Prepare analysis summary using diverse articles
        analysis_summary = prepare_analysis_summary(diverse_articles, topic)
        
        # Get configurable prompt template based on persona and customer type
        prompt_template = get_prompt_template(persona, customer_type)
        
        # Create the AI prompt for trend convergence analysis
        formatted_prompt = f"""Analyze {len(articles)} articles about "{topic}" and create a comprehensive strategic planning document.

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
            
            # Get the AI response using Auspex service
            response_text = ""
            async for chunk in auspex.chat_with_tools(
                chat_id=chat_id,
                message=formatted_prompt,
                model=model,
                limit=10,  # Small limit since we're not searching articles
                tools_config={"search_articles": False, "get_sentiment_analysis": False}
            ):
                response_text += chunk
            
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
            'version': 1
        })
        
        # Save this version for potential reload
        await _save_analysis_version(topic, trend_convergence_data, db)
        
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
            'title': article[0],
            'summary': article[1],
            'uri': article[2],
            'publication_date': article[3],
            'sentiment': article[4],
            'category': article[5],
            'future_signal': article[6],
            'driver_type': article[7],
            'time_to_impact': article[8],
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
            if (original_article[0] == article_dict['title'] and 
                original_article[3] == article_dict['publication_date']):
                selected_original.append(original_article)
                break
    
    return selected_original[:limit]

def prepare_analysis_summary(articles: List, topic: str) -> str:
    """Prepare a structured summary of article data for the AI prompt"""
    
    # Analyze patterns in the data
    sentiments = []
    categories = []
    drivers = []
    signals = []
    time_impacts = []
    
    for article in articles[:50]:  # Limit to avoid token limits
        if article[4]:  # sentiment
            sentiments.append(article[4])
        if article[5]:  # category
            categories.append(article[5])
        if article[7]:  # driver_type
            drivers.append(article[7])
        if article[6]:  # future_signal
            signals.append(article[6])
        if article[8]:  # time_to_impact
            time_impacts.append(article[8])
    
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
- Date range: {str(articles[-1][3])[:10] if articles and articles[-1][3] else 'Unknown'} to {str(articles[0][3])[:10] if articles and articles[0][3] else 'Unknown'}

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

def get_prompt_template(persona: str = "executive", customer_type: str = "general") -> Dict[str, str]:
    """Get configurable prompt template based on persona and customer type"""
    
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
    
    return templates.get(persona, templates["executive"]).get(customer_type, templates["executive"]["general"])

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