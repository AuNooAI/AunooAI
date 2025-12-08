"""
Utility functions for working with LLM responses.
Handles common issues with local models (Ollama/vLLM).
"""
import json
import logging
import re
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def parse_llm_json(raw_content: str, fallback_fields: Optional[list] = None) -> dict:
    """Parse JSON from LLM response, handling common issues with local models (Ollama/vLLM).

    Handles:
    - <think>...</think> blocks from Qwen3 models
    - Truncated JSON responses
    - Control characters in strings
    - Malformed JSON with regex fallback for key fields

    Args:
        raw_content: The raw string response from the LLM
        fallback_fields: Optional list of field names to try extracting via regex if JSON parsing fails

    Returns:
        Parsed dictionary from the JSON response

    Raises:
        ValueError: If no JSON could be parsed from the response
    """
    if not raw_content or not raw_content.strip():
        raise ValueError("Empty response from LLM")

    # Strip <think>...</think> blocks (Qwen3 thinking mode)
    content = re.sub(r'<think>.*?</think>', '', raw_content, flags=re.DOTALL).strip()
    if not content:
        content = raw_content

    # Find JSON object
    start = content.find('{')
    end = content.rfind('}')

    # Handle truncated JSON (no closing brace)
    if start != -1 and (end == -1 or end <= start):
        # Try to repair truncated JSON by closing it
        json_str = content[start:]
        # Count unclosed braces and brackets
        brace_count = json_str.count('{') - json_str.count('}')
        bracket_count = json_str.count('[') - json_str.count(']')

        # Check if we're in an incomplete string
        in_string = False
        last_char = ''
        for c in json_str:
            if c == '"' and last_char != '\\':
                in_string = not in_string
            last_char = c

        # Close incomplete string if needed
        if in_string:
            json_str += '"'

        # Close any open arrays/objects
        json_str += ']' * bracket_count
        json_str += '}' * brace_count

        logger.warning(f"Attempted to repair truncated JSON (added {brace_count} braces, {bracket_count} brackets)")
    elif start == -1:
        raise ValueError("No JSON object found in response")
    else:
        json_str = content[start:end+1]

    # First try direct parsing
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass

    # Try with strict=False to allow control characters
    try:
        return json.loads(json_str, strict=False)
    except json.JSONDecodeError:
        pass

    # Clean up: replace literal newlines/tabs with escaped versions
    cleaned = json_str.replace('\n', '\\n').replace('\t', '\\t').replace('\r', '\\r')
    try:
        return json.loads(cleaned, strict=False)
    except json.JSONDecodeError:
        pass

    # Last resort: try to extract key fields using regex
    # This handles cases where JSON is mostly valid but has corruption
    result = {}

    # Default fields to try extracting
    if fallback_fields is None:
        fallback_fields = []

    # Extract numeric fields
    numeric_patterns = [f for f in fallback_fields if 'score' in f.lower() or 'count' in f.lower()]
    for field in numeric_patterns:
        match = re.search(rf'"{field}"\s*:\s*([\d.]+)', content)
        if match:
            try:
                result[field] = float(match.group(1))
            except ValueError:
                pass

    # Extract string fields
    string_patterns = [f for f in fallback_fields if f not in numeric_patterns]
    for field in string_patterns:
        match = re.search(rf'"{field}"\s*:\s*"([^"]*(?:\\"[^"]*)*)"', content)
        if match:
            result[field] = match.group(1).replace('\\"', '"')

    # Also try to extract common fields if not specified
    common_numeric = ['topic_alignment_score', 'keyword_relevance_score', 'confidence_score', 'relevance_score']
    for field in common_numeric:
        if field not in result:
            match = re.search(rf'"{field}"\s*:\s*([\d.]+)', content)
            if match:
                try:
                    result[field] = float(match.group(1))
                except ValueError:
                    pass

    if result:
        logger.warning(f"Extracted partial JSON using regex fallback: {list(result.keys())}")
        return result

    raise ValueError(f"Could not parse JSON: {json_str[:200]}...")


def strip_think_blocks(content: str) -> str:
    """Strip <think>...</think> blocks from Qwen3 model responses."""
    if not content:
        return content
    result = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
    return result if result else content


def is_local_model(model_name: str) -> bool:
    """Check if a model name refers to a local model (Ollama or vLLM)."""
    if not model_name:
        return False
    model_lower = model_name.lower()
    # Ollama models typically have format like "qwen3:latest", "gemma3:12b", etc.
    # vLLM models may have "vllm" in the name
    local_indicators = ['ollama/', ':latest', ':8b', ':12b', ':14b', ':27b', ':32b', '-vllm', 'localhost']
    return any(indicator in model_lower for indicator in local_indicators)
