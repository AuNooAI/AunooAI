from fastapi import APIRouter, HTTPException, Query, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.security.session import verify_session
from typing import List, Dict
import logging
import json
from datetime import datetime, timedelta
from collections import Counter

from app.database import Database, get_database_instance
from app.ai_models import get_ai_model

# Context limits for different AI models (copied from consensus analysis)
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
        
        # For futures cone analysis, we need good coverage for scenario diversity
        base_size = int(base_size * 1.3)  # Increase for better scenario coverage
        base_sample_size = base_size
    
    # Ensure reasonable limits
    max_limit = 1000 if is_mega_context else 400
    min_limit = 20  # Minimum for good scenario diversity
    
    return max(min_limit, min(base_sample_size, max_limit))

def calculate_scenario_positions(scenario_type: str, scenario_index: int, total_of_type: int) -> Dict[str, float]:
    """Calculate x,y positions for scenarios on the cone with better spacing"""
    base_positions = {
        'probable': {'x_start': 25, 'x_end': 60, 'y_center': 50, 'y_spread': 12},
        'plausible': {'x_start': 30, 'x_end': 70, 'y_center': 40, 'y_spread': 20},
        'possible': {'x_start': 35, 'x_end': 75, 'y_center': 30, 'y_spread': 30},
        'preferable': {'x_start': 40, 'x_end': 65, 'y_center': 20, 'y_spread': 15},
        'wildcard': {'x_start': 60, 'x_end': 80, 'y_center': 70, 'y_spread': 25}
    }
    
    pos = base_positions.get(scenario_type, base_positions['plausible'])
    
    # Better distribution logic to avoid overlaps
    if total_of_type == 1:
        x_progress = 0.5
        y = pos['y_center']
    elif total_of_type == 2:
        x_progress = 0.3 if scenario_index == 0 else 0.7
        y_offset = (-0.5 + scenario_index) * (pos['y_spread'] * 0.6)
        y = pos['y_center'] + y_offset
    else:
        x_progress = scenario_index / (total_of_type - 1)
        # Use sine wave distribution for better visual spacing
        import math
        y_offset = math.sin((scenario_index / (total_of_type - 1)) * math.pi - math.pi/2) * (pos['y_spread'] / 2)
        y = pos['y_center'] + y_offset
    
    x = pos['x_start'] + (pos['x_end'] - pos['x_start']) * x_progress
    
    # Add some randomization to avoid exact overlaps
    import random
    random.seed(hash(scenario_type + str(scenario_index)))  # Deterministic randomness
    x += random.uniform(-2, 2)
    y += random.uniform(-2, 2)
    
    return {'x': max(15, min(85, x)), 'y': max(15, min(85, y))}

def _extract_from_code_block(text: str) -> str:
    """Extract JSON from ```json code blocks"""
    if '```json' in text:
        json_start = text.find('```json') + 7
        json_end = text.find('```', json_start)
        if json_end > json_start:
            return text[json_start:json_end].strip()
    return ""

def _extract_complete_json(text: str) -> str:
    """Extract complete JSON object from text"""
    if '{' in text and '}' in text:
        json_start = text.find('{')
        
        # Find the matching closing brace
        brace_count = 0
        json_end = json_start
        
        for i in range(json_start, len(text)):
            if text[i] == '{':
                brace_count += 1
            elif text[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    json_end = i + 1
                    break
        
        if json_end > json_start:
            return text[json_start:json_end]
    return ""

def _clean_and_parse_json(text: str) -> str:
    """Clean text and try to extract JSON"""
    # Remove common prefixes/suffixes
    text = text.strip()
    
    # Remove markdown formatting
    text = text.replace('```json', '').replace('```', '')
    
    # Find JSON boundaries
    if '{' in text and '}' in text:
        json_start = text.find('{')
        json_end = text.rfind('}') + 1
        return text[json_start:json_end]
    
    return text

def _fix_common_json_issues(text: str) -> str:
    """Fix common JSON formatting issues"""
    import re
    
    # Extract potential JSON
    json_str = _extract_complete_json(text)
    if not json_str:
        json_str = _clean_and_parse_json(text)
    
    if not json_str:
        raise json.JSONDecodeError("No JSON found", "", 0)
    
    # Fix common issues
    # 1. Remove trailing commas
    json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
    
    # 2. Fix unescaped quotes in strings (basic attempt)
    # This is tricky and not perfect, but handles some cases
    json_str = re.sub(r'(?<!\\)"(?=[^"]*"[^"]*:)', r'\\"', json_str)
    
    # 3. Remove comments (// style)
    json_str = re.sub(r'//.*?\n', '\n', json_str)
    
    # 4. Fix missing quotes around keys
    json_str = re.sub(r'(\w+)(\s*:)', r'"\1"\2', json_str)
    
    return json_str

def _create_fallback_response(topic: str, future_horizon: int) -> Dict:
    """Create a fallback response when JSON parsing fails"""
    current_year = datetime.now().year
    
    return {
        "topic": topic,
        "generated_at": datetime.now().isoformat(),
        "future_horizon": f"{future_horizon} years",
        "scenarios": [
            {
                "type": "probable",
                "title": f"Continued {topic} Development",
                "description": "Most likely continuation of current trends",
                "timeframe": f"{current_year}-{current_year + 3}",
                "sentiment": "Neutral-Positive",
                "drivers": [{"type": "Trend", "description": "Current market momentum"}],
                "signals": ["Market growth", "Technology adoption"],
                "probability": "High likelihood",
                "position": {"x": 45, "y": 50}
            },
            {
                "type": "probable",
                "title": f"Mainstream {topic} Adoption",
                "description": "Widespread adoption across industries",
                "timeframe": f"{current_year + 1}-{current_year + 4}",
                "sentiment": "Positive",
                "drivers": [{"type": "Adoption", "description": "Industry acceptance"}],
                "signals": ["Investment increase", "Regulatory clarity"],
                "probability": "High likelihood",
                "position": {"x": 50, "y": 45}
            },
            {
                "type": "probable",
                "title": f"Mature {topic} Market",
                "description": "Market maturation and standardization",
                "timeframe": f"{current_year + 2}-{current_year + 5}",
                "sentiment": "Neutral",
                "drivers": [{"type": "Maturation", "description": "Market stabilization"}],
                "signals": ["Standards development", "Competition increase"],
                "probability": "High likelihood",
                "position": {"x": 40, "y": 52}
            },
            {
                "type": "plausible",
                "title": f"Accelerated {topic} Innovation",
                "description": "Faster than expected technological breakthroughs",
                "timeframe": f"{current_year + 1}-{current_year + 3}",
                "sentiment": "Positive",
                "drivers": [{"type": "Innovation", "description": "Research breakthroughs"}],
                "signals": ["R&D investment", "Patent filings"],
                "probability": "Moderate likelihood",
                "position": {"x": 35, "y": 35}
            },
            {
                "type": "plausible",
                "title": f"Regulatory Challenges for {topic}",
                "description": "Increased regulatory scrutiny and compliance requirements",
                "timeframe": f"{current_year + 2}-{current_year + 6}",
                "sentiment": "Critical",
                "drivers": [{"type": "Regulation", "description": "Government oversight"}],
                "signals": ["Policy discussions", "Compliance requirements"],
                "probability": "Moderate likelihood",
                "position": {"x": 65, "y": 40}
            },
            {
                "type": "plausible",
                "title": f"Global {topic} Competition",
                "description": "Intensified international competition",
                "timeframe": f"{current_year + 1}-{current_year + 5}",
                "sentiment": "Mixed",
                "drivers": [{"type": "Competition", "description": "Global market dynamics"}],
                "signals": ["International investments", "Trade policies"],
                "probability": "Moderate likelihood",
                "position": {"x": 55, "y": 38}
            },
            {
                "type": "possible",
                "title": f"Disruptive {topic} Technology",
                "description": "Breakthrough technology disrupts current approaches",
                "timeframe": f"{current_year + 3}-{current_year + 8}",
                "sentiment": "Mixed",
                "drivers": [{"type": "Disruption", "description": "Technological breakthrough"}],
                "signals": ["Research papers", "Startup activity"],
                "probability": "Lower likelihood",
                "position": {"x": 70, "y": 25}
            },
            {
                "type": "possible",
                "title": f"Market Consolidation in {topic}",
                "description": "Major consolidation reduces market players",
                "timeframe": f"{current_year + 4}-{current_year + 8}",
                "sentiment": "Neutral",
                "drivers": [{"type": "Consolidation", "description": "Market maturation"}],
                "signals": ["M&A activity", "Market concentration"],
                "probability": "Lower likelihood",
                "position": {"x": 75, "y": 30}
            },
            {
                "type": "possible",
                "title": f"Alternative {topic} Approaches",
                "description": "Alternative methodologies gain traction",
                "timeframe": f"{current_year + 2}-{current_year + 7}",
                "sentiment": "Positive",
                "drivers": [{"type": "Alternative", "description": "New approaches"}],
                "signals": ["Academic research", "Pilot projects"],
                "probability": "Lower likelihood",
                "position": {"x": 65, "y": 28}
            },
            {
                "type": "preferable",
                "title": f"Sustainable {topic} Development",
                "description": "Environmentally sustainable and ethical development",
                "timeframe": f"{current_year + 1}-{current_year + 6}",
                "sentiment": "Positive",
                "drivers": [{"type": "Sustainability", "description": "Environmental focus"}],
                "signals": ["ESG investments", "Sustainability initiatives"],
                "probability": "Desired outcome",
                "position": {"x": 45, "y": 15}
            },
            {
                "type": "preferable",
                "title": f"Inclusive {topic} Access",
                "description": "Broad, equitable access across all demographics",
                "timeframe": f"{current_year + 2}-{current_year + 7}",
                "sentiment": "Positive",
                "drivers": [{"type": "Inclusion", "description": "Equity focus"}],
                "signals": ["Accessibility initiatives", "Education programs"],
                "probability": "Desired outcome",
                "position": {"x": 55, "y": 18}
            },
            {
                "type": "wildcard",
                "title": f"Unexpected {topic} Crisis",
                "description": "Unforeseen crisis disrupts the entire field",
                "timeframe": f"{current_year + 1}-{current_year + 4}",
                "sentiment": "Critical",
                "drivers": [{"type": "Crisis", "description": "Unexpected event"}],
                "signals": ["Risk indicators", "Vulnerability assessments"],
                "probability": "Low but high impact",
                "position": {"x": 75, "y": 75}
            },
            {
                "type": "wildcard",
                "title": f"Paradigm Shift in {topic}",
                "description": "Fundamental change in understanding or approach",
                "timeframe": f"{current_year + 3}-{current_year + 10}",
                "sentiment": "Mixed",
                "drivers": [{"type": "Paradigm", "description": "Fundamental shift"}],
                "signals": ["Theoretical breakthroughs", "Paradigm challenges"],
                "probability": "Low but transformative",
                "position": {"x": 80, "y": 65}
            }
        ],
        "timeline": [
            {"year": current_year, "label": "Present"},
            {"year": current_year + max(1, future_horizon // 4), "label": "Short-term"},
            {"year": current_year + max(2, future_horizon // 2), "label": "Mid-term"},
            {"year": current_year + max(3, (future_horizon * 3) // 4), "label": "Long-term"},
            {"year": current_year + future_horizon, "label": "Horizon"}
        ],
        "summary": {
            "total_scenarios": 13,
            "key_uncertainties": ["Technology development pace", "Regulatory response", "Market adoption"],
            "dominant_themes": ["Continued growth", "Regulatory challenges", "Technology evolution"]
        },
        "fallback_used": True
    }

@router.get("/api/futures-cone/{topic}")
def generate_futures_cone(
    topic: str,
    timeframe_days: int = Query(365),
    model: str = Query(...),
    future_horizon: int = Query(5),
    analysis_depth: str = Query("standard"),
    sample_size_mode: str = Query("auto"),
    custom_limit: int = Query(None),
    db: Database = Depends(get_database_instance)
):
    """Generate a data-driven futures cone for a given topic"""
    
    try:
        logger.info(f"Generating futures cone for topic: {topic}, model: {model}")
        
        # Calculate optimal sample size based on model and mode
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
        
        # Prepare analysis summary
        analysis_summary = prepare_analysis_summary(articles, topic)
        
        # Format the prompt using f-string instead of .format()
        formatted_prompt = f"""## **Generate a Data-Driven Futures Cone Using Analytical Signals**

You are an AI foresight analyst analyzing "{topic}". Generate a structured futures cone with diverse scenario types distributed across probability layers.

**CRITICAL REQUIREMENTS - You MUST generate exactly these scenario counts:**
- **probable**: Exactly 3 scenarios - Most likely futures, center cone, high confidence
- **plausible**: Exactly 3 scenarios - Alternative but realistic futures, middle cone area  
- **possible**: Exactly 3 scenarios - Low-probability but impactful futures, outer cone edges
- **preferable**: Exactly 2 scenarios - Desired/optimal futures, upper cone area
- **wildcard**: Exactly 2 scenarios - Disruptive surprise scenarios, extreme edges, unexpected

**Total: 13 scenarios required (3+3+3+2+2=13)**

**Analysis Data:**
{analysis_summary}

**Output Format - Return ONLY valid JSON (no markdown, no comments, no extra text):**
{{
  "topic": "{topic}",
  "generated_at": "2025-01-25T10:00:00Z",
  "future_horizon": "{future_horizon} years",
  "scenarios": [
    {{
      "type": "probable",
      "title": "Main Probable Path 1",
      "description": "Most likely future based on majority signals",
      "timeframe": "2025-2030",
      "sentiment": "Neutral-Positive",
      "drivers": [{{"type": "Accelerator", "description": "Primary driver"}}],
      "signals": ["Signal from data"],
      "branching_point": null,
      "probability": "High likelihood",
      "position": {{"x": 45, "y": 48}}
    }},
    {{
      "type": "probable",
      "title": "Main Probable Path 2",
      "description": "Second most likely future path",
      "timeframe": "2025-2030",
      "sentiment": "Positive",
      "drivers": [{{"type": "Accelerator", "description": "Secondary driver"}}],
      "signals": ["Another signal from data"],
      "branching_point": null,
      "probability": "High likelihood",
      "position": {{"x": 50, "y": 45}}
    }},
    {{
      "type": "probable",
      "title": "Main Probable Path 3",
      "description": "Third most likely future path",
      "timeframe": "2025-2030",
      "sentiment": "Neutral",
      "drivers": [{{"type": "Accelerator", "description": "Tertiary driver"}}],
      "signals": ["Third signal from data"],
      "branching_point": null,
      "probability": "High likelihood",
      "position": {{"x": 40, "y": 52}}
    }},
    {{
      "type": "wildcard",
      "title": "Disruptive Surprise 1",
      "description": "Low-probability but high-impact surprise scenario",
      "timeframe": "2027-2035",
      "sentiment": "Mixed",
      "drivers": [{{"type": "Disruptor", "description": "Unexpected catalyst"}}],
      "signals": ["Weak signal from data"],
      "branching_point": "Critical uncertainty",
      "probability": "Low but impactful",
      "position": {{"x": 75, "y": 85}}
    }},
    {{
      "type": "wildcard",
      "title": "Disruptive Surprise 2",
      "description": "Second low-probability but high-impact surprise scenario",
      "timeframe": "2026-2032",
      "sentiment": "Critical",
      "drivers": [{{"type": "Disruptor", "description": "Second unexpected catalyst"}}],
      "signals": ["Another weak signal from data"],
      "branching_point": "Another critical uncertainty",
      "probability": "Low but impactful",
      "position": {{"x": 80, "y": 20}}
    }}
  ],
  "timeline": [
    {{"year": 2025, "label": "Present"}},
    {{"year": 2030, "label": "Mid-term"}}
  ],
  "summary": {{
    "total_scenarios": 13,
    "key_uncertainties": ["Major uncertainties"],
    "dominant_themes": ["Common themes"]
  }}
}}

**CRITICAL: You must generate exactly 13 scenarios total:**
- 3 probable scenarios
- 3 plausible scenarios  
- 3 possible scenarios
- 2 preferable scenarios
- 2 wildcard scenarios

Base each scenario on the analysis data provided. Do not generate fewer scenarios.

**IMPORTANT: Return ONLY the JSON object. No explanations, no markdown formatting, no code blocks. Start with {{ and end with }}.**"""
        
        # Get AI model and generate response
        ai_model = get_ai_model(model)
        if not ai_model:
            raise HTTPException(status_code=400, detail=f"Model '{model}' not available")
        
        logger.info(f"Generating futures cone with {model}")
        
        # Generate the futures cone
        response = ai_model.generate_response([{"role": "user", "content": formatted_prompt}])
        
        # Parse JSON response with robust error handling
        try:
            futures_cone_data = None
            json_str = ""
            
            # Try multiple JSON extraction methods
            extraction_methods = [
                # Method 1: Extract from JSON code blocks
                lambda text: _extract_from_code_block(text),
                # Method 2: Find complete JSON object
                lambda text: _extract_complete_json(text),
                # Method 3: Clean and parse entire response
                lambda text: _clean_and_parse_json(text)
            ]
            
            for method in extraction_methods:
                try:
                    json_str = method(response)
                    if json_str:
                        futures_cone_data = json.loads(json_str)
                        logger.info("Successfully parsed JSON using extraction method")
                        break
                except (json.JSONDecodeError, AttributeError, IndexError):
                    continue
            
            if not futures_cone_data:
                # Last resort: try to fix common JSON issues
                json_str = _fix_common_json_issues(response)
                futures_cone_data = json.loads(json_str)
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response after all attempts: {e}")
            logger.error(f"Raw response (first 500 chars): {response[:500]}")
            
            # Create a fallback response with minimal scenarios
            futures_cone_data = _create_fallback_response(topic, future_horizon)
            logger.warning("Using fallback response due to JSON parsing failure")
        except Exception as e:
            logger.error(f"Unexpected error during JSON parsing: {e}")
            raise HTTPException(
                status_code=500, 
                detail="Failed to process AI response. Please try again."
            )
        
        # Post-process scenarios for proper positioning
        if 'scenarios' in futures_cone_data:
            scenarios_by_type = {}
            for scenario in futures_cone_data['scenarios']:
                scenario_type = scenario.get('type', 'plausible')
                if scenario_type not in scenarios_by_type:
                    scenarios_by_type[scenario_type] = []
                scenarios_by_type[scenario_type].append(scenario)
            
            # Recalculate positions
            for scenario_type, scenarios in scenarios_by_type.items():
                for i, scenario in enumerate(scenarios):
                    if 'position' not in scenario or not scenario['position']:
                        position = calculate_scenario_positions(scenario_type, i, len(scenarios))
                        scenario['position'] = position
        
        # Ensure timeline exists
        if 'timeline' not in futures_cone_data or not futures_cone_data['timeline']:
            current_year = datetime.now().year
            futures_cone_data['timeline'] = [
                {'year': current_year, 'label': 'Present'},
                {'year': current_year + max(1, future_horizon // 4), 'label': 'Short-term'},
                {'year': current_year + max(2, future_horizon // 2), 'label': 'Mid-term'},
                {'year': current_year + max(3, (future_horizon * 3) // 4), 'label': 'Long-term'},
                {'year': current_year + future_horizon, 'label': 'Horizon'}
            ]
        
        # Add metadata
        futures_cone_data.update({
            'generated_at': datetime.now().isoformat(),
            'articles_analyzed': len(articles),
            'timeframe_days': timeframe_days,
            'model_used': model
        })
        
        logger.info(f"Successfully generated futures cone with {len(futures_cone_data.get('scenarios', []))} scenarios")
        
        return futures_cone_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating futures cone: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

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

@router.get("/futures-cone", response_class=HTMLResponse)
async def futures_cone_page(request: Request, session: dict = Depends(verify_session)):
    """Render the futures cone visualization page"""
    return templates.TemplateResponse("futures_cone.html", {"request": request, "session": session}) 