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

def calculate_scenario_positions(scenario_type: str, scenario_index: int, total_of_type: int, timeframe: str = None) -> Dict[str, float]:
    """Calculate x,y positions for scenarios using a clean grid-based layout"""
    
    # Determine time period from timeframe
    time_period = 'mid'  # default
    if timeframe:
        if any(year in timeframe for year in ['2025', '2026', '2027']):
            time_period = 'short'
        elif any(year in timeframe for year in ['2033', '2034', '2035', '2036', '2037', '2038', '2039', '2040']):
            time_period = 'long'
    
    # Define clean grid positions - 3 columns (time periods) x 5 rows (scenario types)
    # Each cell is roughly 30% wide x 18% tall with margins
    
    # Column positions (time-based)
    time_columns = {
        'short': {'x_start': 5, 'x_width': 28},   # Left column: 5-33%
        'mid': {'x_start': 36, 'x_width': 28},    # Middle column: 36-64%  
        'long': {'x_start': 67, 'x_width': 28}    # Right column: 67-95%
    }
    
    # Row positions (type-based, top to bottom)
    type_rows = {
        'preferable': {'y_start': 2, 'y_height': 16},    # Row 1: 2-18%
        'probable': {'y_start': 20, 'y_height': 16},     # Row 2: 20-36%
        'plausible': {'y_start': 38, 'y_height': 16},    # Row 3: 38-54%
        'possible': {'y_start': 56, 'y_height': 16},     # Row 4: 56-72%
        'wildcard': {'y_start': 74, 'y_height': 16}      # Row 5: 74-90%
    }
    
    col = time_columns[time_period]
    row = type_rows.get(scenario_type, type_rows['plausible'])
    
    # For multiple scenarios of same type in same time period, stack them vertically
    if total_of_type == 1:
        # Single scenario - center in the cell
        x = col['x_start'] + (col['x_width'] / 2)
        y = row['y_start'] + (row['y_height'] / 2)
    elif total_of_type == 2:
        # Two scenarios - stack vertically in the cell
        x = col['x_start'] + (col['x_width'] / 2)
        if scenario_index == 0:
            y = row['y_start'] + (row['y_height'] * 0.3)  # Upper third
        else:
            y = row['y_start'] + (row['y_height'] * 0.7)  # Lower third
    elif total_of_type == 3:
        # Three scenarios - distribute evenly in the cell
        x = col['x_start'] + (col['x_width'] / 2)
        if scenario_index == 0:
            y = row['y_start'] + (row['y_height'] * 0.2)
        elif scenario_index == 1:
            y = row['y_start'] + (row['y_height'] * 0.5)
        else:
            y = row['y_start'] + (row['y_height'] * 0.8)
    else:
        # More than 3 scenarios - distribute across width and height
        scenarios_per_row = min(2, total_of_type)
        row_index = scenario_index // scenarios_per_row
        col_index = scenario_index % scenarios_per_row
        
        # Calculate position within the cell
        x_offset = (col_index + 0.5) / scenarios_per_row
        y_offset = (row_index + 0.5) / ((total_of_type + scenarios_per_row - 1) // scenarios_per_row)
        
        x = col['x_start'] + (col['x_width'] * x_offset)
        y = row['y_start'] + (row['y_height'] * y_offset)
    
    # Ensure positions stay within bounds
    x = max(1, min(99, x))
    y = max(1, min(99, y))
    
    return {'x': x, 'y': y}

def _extract_from_code_block(text: str) -> str:
    """Extract JSON from ```json code blocks"""
    if '```json' in text:
        json_start = text.find('```json') + 7
        json_end = text.find('```', json_start)
        if json_end > json_start:
            return text[json_start:json_end].strip()
    return ""

def _extract_complete_json(text: str) -> str:
    """Extract complete JSON object from text with better handling"""
    if '{' not in text or '}' not in text:
        return ""
    
    # Find the first opening brace
    json_start = text.find('{')
    
    # Find the matching closing brace by counting braces
    brace_count = 0
    json_end = json_start
    in_string = False
    escape_next = False
    
    for i in range(json_start, len(text)):
        char = text[i]
        
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
                if brace_count == 0:
                    json_end = i + 1
                    break
    
    if json_end > json_start and brace_count == 0:
        return text[json_start:json_end]
    
    # If we couldn't find a complete JSON, try to find the largest valid portion
    if brace_count > 0:
        # We have unclosed braces, try to find the last complete object
        last_complete = json_start
        temp_count = 0
        
        for i in range(json_start, len(text)):
            if text[i] == '{':
                temp_count += 1
            elif text[i] == '}':
                temp_count -= 1
                if temp_count == 0:
                    last_complete = i + 1
        
        if last_complete > json_start:
            return text[json_start:last_complete]
    
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
    
    # Check if JSON appears to be truncated
    if not json_str.rstrip().endswith('}'):
        # Try to find the last complete object/array
        last_complete_brace = json_str.rfind('}')
        if last_complete_brace > 0:
            # Find the opening brace that matches
            brace_count = 0
            for i in range(last_complete_brace, -1, -1):
                if json_str[i] == '}':
                    brace_count += 1
                elif json_str[i] == '{':
                    brace_count -= 1
                    if brace_count == 0:
                        json_str = json_str[:last_complete_brace + 1]
                        break
    
    # Fix common issues
    # 1. Remove trailing commas
    json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
    
    # 2. Fix unescaped quotes in strings (basic attempt)
    # This is tricky and not perfect, but handles some cases
    lines = json_str.split('\n')
    fixed_lines = []
    for line in lines:
        # Skip lines that are clearly JSON structure
        if ':' in line and '"' in line:
            # Try to fix unescaped quotes in values
            if line.count('"') % 2 != 0:
                # Odd number of quotes, likely an unescaped quote
                line = re.sub(r'(?<!\\)"(?![,}\]\s]*$)', r'\\"', line)
        fixed_lines.append(line)
    json_str = '\n'.join(fixed_lines)
    
    # 3. Remove comments (// style)
    json_str = re.sub(r'//.*?\n', '\n', json_str)
    
    # 4. Fix missing quotes around keys (be more careful)
    json_str = re.sub(r'(\n\s*)([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'\1"\2":', json_str)
    
    return json_str

def _create_fallback_response(topic: str, future_horizon: int) -> Dict:
    """Create a fallback response when JSON parsing fails"""
    current_year = datetime.now().year
    
    # Create scenarios distributed across time periods
    scenarios = []
    
    # Short-term scenarios (2025-2027)
    short_term_scenarios = [
        {
            "type": "probable",
            "title": f"Continued {topic} Development",
            "description": "Most likely continuation of current trends in the short term",
            "timeframe": f"{current_year}-{current_year + 2}",
            "sentiment": "Neutral-Positive",
            "drivers": [{"type": "Trend", "description": "Current market momentum"}],
            "signals": ["Market growth", "Technology adoption"],
            "probability": "High likelihood",
            "position": calculate_scenario_positions("probable", 0, 3, f"{current_year}-{current_year + 2}")
        },
        {
            "type": "plausible",
            "title": f"Accelerated {topic} Innovation",
            "description": "Faster than expected technological breakthroughs in the short term",
            "timeframe": f"{current_year + 1}-{current_year + 2}",
            "sentiment": "Positive",
            "drivers": [{"type": "Innovation", "description": "Research breakthroughs"}],
            "signals": ["R&D investment", "Patent filings"],
            "probability": "Moderate likelihood",
            "position": calculate_scenario_positions("plausible", 0, 3, f"{current_year + 1}-{current_year + 2}")
        },
        {
            "type": "preferable",
            "title": f"Sustainable {topic} Development",
            "description": "Environmentally sustainable and ethical development in the short term",
            "timeframe": f"{current_year}-{current_year + 2}",
            "sentiment": "Positive",
            "drivers": [{"type": "Sustainability", "description": "Environmental focus"}],
            "signals": ["ESG investments", "Sustainability initiatives"],
            "probability": "Desired outcome",
            "position": calculate_scenario_positions("preferable", 0, 2, f"{current_year}-{current_year + 2}")
        },
        {
            "type": "wildcard",
            "title": f"Unexpected {topic} Crisis",
            "description": "Unforeseen crisis disrupts the field in the short term",
            "timeframe": f"{current_year + 1}-{current_year + 2}",
            "sentiment": "Critical",
            "drivers": [{"type": "Crisis", "description": "Unexpected event"}],
            "signals": ["Risk indicators", "Vulnerability assessments"],
            "probability": "Low but high impact",
            "position": calculate_scenario_positions("wildcard", 0, 2, f"{current_year + 1}-{current_year + 2}")
        }
    ]
    
    # Mid-term scenarios (2028-2032)
    mid_term_scenarios = [
        {
            "type": "probable",
            "title": f"Mainstream {topic} Adoption",
            "description": "Widespread adoption across industries in the mid-term",
            "timeframe": f"{current_year + 3}-{current_year + 7}",
            "sentiment": "Positive",
            "drivers": [{"type": "Adoption", "description": "Industry acceptance"}],
            "signals": ["Investment increase", "Regulatory clarity"],
            "probability": "High likelihood",
            "position": calculate_scenario_positions("probable", 1, 3, f"{current_year + 3}-{current_year + 7}")
        },
        {
            "type": "plausible",
            "title": f"Regulatory Challenges for {topic}",
            "description": "Increased regulatory scrutiny and compliance requirements",
            "timeframe": f"{current_year + 4}-{current_year + 8}",
            "sentiment": "Critical",
            "drivers": [{"type": "Regulation", "description": "Government oversight"}],
            "signals": ["Policy discussions", "Compliance requirements"],
            "probability": "Moderate likelihood",
            "position": calculate_scenario_positions("plausible", 1, 3, f"{current_year + 4}-{current_year + 8}")
        },
        {
            "type": "plausible",
            "title": f"Global {topic} Competition",
            "description": "Intensified international competition in the mid-term",
            "timeframe": f"{current_year + 3}-{current_year + 7}",
            "sentiment": "Mixed",
            "drivers": [{"type": "Competition", "description": "Global market dynamics"}],
            "signals": ["International investments", "Trade policies"],
            "probability": "Moderate likelihood",
            "position": calculate_scenario_positions("plausible", 2, 3, f"{current_year + 3}-{current_year + 7}")
        },
        {
            "type": "possible",
            "title": f"Market Consolidation in {topic}",
            "description": "Major consolidation reduces market players in the mid-term",
            "timeframe": f"{current_year + 5}-{current_year + 8}",
            "sentiment": "Neutral",
            "drivers": [{"type": "Consolidation", "description": "Market maturation"}],
            "signals": ["M&A activity", "Market concentration"],
            "probability": "Lower likelihood",
            "position": calculate_scenario_positions("possible", 0, 3, f"{current_year + 5}-{current_year + 8}")
        },
        {
            "type": "preferable",
            "title": f"Inclusive {topic} Access",
            "description": "Broad, equitable access across all demographics",
            "timeframe": f"{current_year + 4}-{current_year + 8}",
            "sentiment": "Positive",
            "drivers": [{"type": "Inclusion", "description": "Equity focus"}],
            "signals": ["Accessibility initiatives", "Education programs"],
            "probability": "Desired outcome",
            "position": calculate_scenario_positions("preferable", 1, 2, f"{current_year + 4}-{current_year + 8}")
        }
    ]
    
    # Long-term scenarios (2033+)
    long_term_scenarios = [
        {
            "type": "probable",
            "title": f"Mature {topic} Market",
            "description": "Market maturation and standardization in the long term",
            "timeframe": f"{current_year + 8}-{current_year + future_horizon}",
            "sentiment": "Neutral",
            "drivers": [{"type": "Maturation", "description": "Market stabilization"}],
            "signals": ["Standards development", "Competition increase"],
            "probability": "High likelihood",
            "position": calculate_scenario_positions("probable", 2, 3, f"{current_year + 8}-{current_year + future_horizon}")
        },
        {
            "type": "possible",
            "title": f"Disruptive {topic} Technology",
            "description": "Breakthrough technology disrupts current approaches in the long term",
            "timeframe": f"{current_year + 8}-{current_year + future_horizon}",
            "sentiment": "Mixed",
            "drivers": [{"type": "Disruption", "description": "Technological breakthrough"}],
            "signals": ["Research papers", "Startup activity"],
            "probability": "Lower likelihood",
            "position": calculate_scenario_positions("possible", 1, 3, f"{current_year + 8}-{current_year + future_horizon}")
        },
        {
            "type": "possible",
            "title": f"Alternative {topic} Approaches",
            "description": "Alternative methodologies gain traction in the long term",
            "timeframe": f"{current_year + 10}-{current_year + future_horizon}",
            "sentiment": "Positive",
            "drivers": [{"type": "Alternative", "description": "New approaches"}],
            "signals": ["Academic research", "Pilot projects"],
            "probability": "Lower likelihood",
            "position": calculate_scenario_positions("possible", 2, 3, f"{current_year + 10}-{current_year + future_horizon}")
        },
        {
            "type": "wildcard",
            "title": f"Paradigm Shift in {topic}",
            "description": "Fundamental change in understanding or approach in the long term",
            "timeframe": f"{current_year + 10}-{current_year + future_horizon}",
            "sentiment": "Mixed",
            "drivers": [{"type": "Paradigm", "description": "Fundamental shift"}],
            "signals": ["Theoretical breakthroughs", "Paradigm challenges"],
            "probability": "Low but transformative",
            "position": calculate_scenario_positions("wildcard", 1, 2, f"{current_year + 10}-{current_year + future_horizon}")
        }
    ]
    
    # Combine all scenarios
    scenarios = short_term_scenarios + mid_term_scenarios + long_term_scenarios
    
    return {
        "topic": topic,
        "generated_at": datetime.now().isoformat(),
        "future_horizon": f"{future_horizon} years",
        "scenarios": scenarios,
        "timeline": [
            {"year": current_year, "label": "Present"},
            {"year": current_year + 2, "label": "Short-term"},
            {"year": current_year + 5, "label": "Mid-term"},
            {"year": current_year + 8, "label": "Long-term"},
            {"year": current_year + future_horizon, "label": "Horizon"}
        ],
        "summary": {
            "total_scenarios": 13,
            "key_uncertainties": ["Technology development pace", "Regulatory response", "Market adoption"],
            "dominant_themes": ["Continued growth", "Regulatory challenges", "Technology evolution"]
        },
        "fallback_used": True
    }

def _attempt_json_completion(text: str) -> str:
    """Attempt to complete truncated JSON by adding missing closing braces"""
    if not text.strip():
        return text
    
    # Count unclosed braces and brackets
    brace_count = 0
    bracket_count = 0
    in_string = False
    escape_next = False
    
    for char in text:
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
    
    # If we have unclosed structures, try to close them
    completion = text
    
    # Remove any trailing comma that might be incomplete
    completion = completion.rstrip().rstrip(',')
    
    # Close any unclosed strings (basic attempt)
    if in_string:
        completion += '"'
    
    # Close unclosed brackets first
    completion += ']' * max(0, bracket_count)
    
    # Close unclosed braces
    completion += '}' * max(0, brace_count)
    
    return completion

def _preprocess_response(response: str) -> str:
    """Remove forbidden fields that cause JSON truncation"""
    import re
    
    # List of forbidden field patterns to remove
    forbidden_patterns = [
        r'"generated_at":\s*"[^"]*",?\s*',
        r'"future_horizon":\s*"[^"]*",?\s*', 
        r'"drivers":\s*\[[^\]]*\],?\s*',
        r'"signals":\s*\[[^\]]*\],?\s*',
        r'"branching_point":\s*"[^"]*",?\s*',
        r'"probability":\s*"[^"]*",?\s*',
        r'"timeline":\s*\[[^\]]*\],?\s*',
        r'"summary":\s*\{[^}]*\},?\s*'
    ]
    
    # Remove each forbidden pattern
    cleaned = response
    for pattern in forbidden_patterns:
        cleaned = re.sub(pattern, '', cleaned, flags=re.DOTALL)
    
    # Clean up any double commas or trailing commas
    cleaned = re.sub(r',\s*,', ',', cleaned)
    cleaned = re.sub(r',(\s*[}\]])', r'\1', cleaned)
    
    return cleaned

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
        
        # Prepare analysis summary - keep full sample size for GPT-4.1's large context
        analysis_summary = prepare_analysis_summary(articles, topic)
        
        # Format the prompt to request concise responses (input stays full, output gets shorter)
        formatted_prompt = f"""CRITICAL: You MUST follow the exact JSON format below. Do NOT add any extra fields like "generated_at", "future_horizon", "drivers", "signals", "branching_point", or "probability". 

Analyze {len(articles)} articles about "{topic}" and generate exactly 13 scenarios.

REQUIRED DISTRIBUTION:
- 3 probable scenarios
- 3 plausible scenarios  
- 3 possible scenarios
- 2 preferable scenarios
- 2 wildcard scenarios

ARTICLE DATA:
{analysis_summary}

FORBIDDEN FIELDS: Do NOT include generated_at, future_horizon, drivers, signals, branching_point, probability, timeline, summary, or any nested objects.

RESPONSE FORMAT - Use EXACTLY this structure with ONLY these 5 fields per scenario:

{{
  "topic": "{topic}",
  "scenarios": [
    {{
      "type": "probable",
      "title": "Brief title here",
      "description": "One sentence description under 40 words.",
      "timeframe": "2025-2027",
      "sentiment": "Positive"
    }},
    {{
      "type": "probable",
      "title": "Second probable scenario",
      "description": "Another one sentence description under 40 words.",
      "timeframe": "2028-2032", 
      "sentiment": "Mixed"
    }},
    {{
      "type": "probable",
      "title": "Third probable scenario",
      "description": "Third one sentence description under 40 words.",
      "timeframe": "2025-2027",
      "sentiment": "Negative"
    }},
    {{
      "type": "plausible",
      "title": "First plausible title",
      "description": "Plausible description under 40 words.",
      "timeframe": "2028-2032",
      "sentiment": "Positive"
    }},
    {{
      "type": "plausible", 
      "title": "Second plausible title",
      "description": "Another plausible description under 40 words.",
      "timeframe": "2033-2035",
      "sentiment": "Mixed"
    }},
    {{
      "type": "plausible",
      "title": "Third plausible title", 
      "description": "Third plausible description under 40 words.",
      "timeframe": "2028-2032",
      "sentiment": "Positive"
    }},
    {{
      "type": "possible",
      "title": "First possible title",
      "description": "Possible scenario description under 40 words.",
      "timeframe": "2033-2035",
      "sentiment": "Mixed"
    }},
    {{
      "type": "possible",
      "title": "Second possible title",
      "description": "Another possible description under 40 words.",
      "timeframe": "2028-2032", 
      "sentiment": "Negative"
    }},
    {{
      "type": "possible",
      "title": "Third possible title",
      "description": "Third possible description under 40 words.",
      "timeframe": "2033-2035",
      "sentiment": "Positive"
    }},
    {{
      "type": "preferable",
      "title": "First preferable title",
      "description": "Preferable outcome description under 40 words.",
      "timeframe": "2025-2027",
      "sentiment": "Positive"
    }},
    {{
      "type": "preferable", 
      "title": "Second preferable title",
      "description": "Another preferable description under 40 words.",
      "timeframe": "2028-2032",
      "sentiment": "Positive"
    }},
    {{
      "type": "wildcard",
      "title": "First wildcard title",
      "description": "Disruptive wildcard description under 40 words.",
      "timeframe": "2025-2027",
      "sentiment": "Mixed"
    }},
    {{
      "type": "wildcard",
      "title": "Second wildcard title", 
      "description": "Another wildcard description under 40 words.",
      "timeframe": "2033-2035",
      "sentiment": "Negative"
    }}
  ]
}}

CRITICAL RULES:
1. Return ONLY the JSON structure shown above
2. Use ONLY these 5 fields per scenario: type, title, description, timeframe, sentiment  
3. Do NOT add generated_at, future_horizon, drivers, signals, probability, or any other fields
4. Keep descriptions under 40 words each
5. Start response with {{ and end with }}
6. No explanations, no markdown, no extra text

Generate the JSON now:"""
        
        # Get AI model and generate response
        ai_model = get_ai_model(model)
        if not ai_model:
            raise HTTPException(status_code=400, detail=f"Model '{model}' not available")
        
        logger.info(f"Generating futures cone with {model}")
        
        # Generate the futures cone
        response = ai_model.generate_response([{"role": "user", "content": formatted_prompt}])
        
        # Preprocess response to remove forbidden fields that cause truncation
        response = _preprocess_response(response)
        logger.info(f"Preprocessed response length: {len(response)} characters")
        
        # Parse JSON response with robust error handling and debugging
        try:
            futures_cone_data = None
            json_str = ""
            
            # Log response details for debugging
            logger.info(f"AI response length: {len(response)} characters")
            logger.info(f"Response ends with: '{response[-50:]}'" if len(response) > 50 else f"Full response: '{response}'")
            
            # Check if response appears to be truncated
            is_truncated = not response.rstrip().endswith('}') and '{' in response
            if is_truncated:
                logger.warning("Response appears to be truncated - missing closing brace")
            
            # Try multiple JSON extraction methods
            extraction_methods = [
                # Method 1: Extract from JSON code blocks
                lambda text: _extract_from_code_block(text),
                # Method 2: Find complete JSON object
                lambda text: _extract_complete_json(text),
                # Method 3: Clean and parse entire response
                lambda text: _clean_and_parse_json(text),
                # Method 4: Attempt to complete truncated JSON
                lambda text: _attempt_json_completion(_extract_complete_json(text)) if _extract_complete_json(text) else ""
            ]
            
            for i, method in enumerate(extraction_methods):
                try:
                    json_str = method(response)
                    if json_str:
                        futures_cone_data = json.loads(json_str)
                        logger.info(f"Successfully parsed JSON using extraction method {i+1}")
                        
                        # Validate we got the expected structure
                        if 'scenarios' in futures_cone_data and len(futures_cone_data['scenarios']) > 0:
                            logger.info(f"Found {len(futures_cone_data['scenarios'])} scenarios in response")
                            break
                        else:
                            logger.warning(f"Method {i+1} parsed JSON but missing scenarios")
                            futures_cone_data = None
                except (json.JSONDecodeError, AttributeError, IndexError) as e:
                    logger.debug(f"Method {i+1} failed: {str(e)}")
                    continue
            
            if not futures_cone_data:
                # Last resort: try to fix common JSON issues
                logger.info("Attempting to fix common JSON issues")
                json_str = _fix_common_json_issues(response)
                futures_cone_data = json.loads(json_str)
                logger.info("Successfully fixed and parsed JSON")
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response after all attempts: {e}")
            logger.error(f"Raw response length: {len(response)}")
            logger.error(f"Raw response (first 1000 chars): {response[:1000]}")
            logger.error(f"Raw response (last 500 chars): {response[-500:]}")
            
            # Create a fallback response with minimal scenarios
            futures_cone_data = _create_fallback_response(topic, future_horizon)
            logger.warning("Using fallback response due to JSON parsing failure")
        except Exception as e:
            logger.error(f"Unexpected error during JSON parsing: {e}")
            raise HTTPException(
                status_code=500, 
                detail="Failed to process AI response. Please try again."
            )
        
        # Post-process scenarios for proper positioning and missing fields
        if 'scenarios' in futures_cone_data:
            scenarios_by_type = {}
            for scenario in futures_cone_data['scenarios']:
                scenario_type = scenario.get('type', 'plausible')
                if scenario_type not in scenarios_by_type:
                    scenarios_by_type[scenario_type] = []
                scenarios_by_type[scenario_type].append(scenario)
            
            # Recalculate positions and add missing fields
            for scenario_type, scenarios in scenarios_by_type.items():
                for i, scenario in enumerate(scenarios):
                    # Add position
                    timeframe = scenario.get('timeframe', '')
                    position = calculate_scenario_positions(scenario_type, i, len(scenarios), timeframe)
                    scenario['position'] = position
                    
                    # Add missing fields for complete structure
                    if 'drivers' not in scenario:
                        scenario['drivers'] = [{"type": "Trend", "description": "Based on analysis data"}]
                    if 'signals' not in scenario:
                        scenario['signals'] = ["Market indicators", "Technology trends"]
                    if 'probability' not in scenario:
                        prob_map = {
                            'probable': 'High likelihood',
                            'plausible': 'Moderate likelihood', 
                            'possible': 'Lower likelihood',
                            'preferable': 'Desired outcome',
                            'wildcard': 'Low but impactful'
                        }
                        scenario['probability'] = prob_map.get(scenario_type, 'Moderate likelihood')
                    if 'branching_point' not in scenario:
                        scenario['branching_point'] = None
        
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