"""
Keyword Normalizer Module

Normalizes keywords for universal compatibility across news APIs:
- NewsAPI
- TheNewsAPI
- NewsData.io

Key rules:
- Strip parentheses () and brackets []
- Remove boolean operators: AND, OR, NOT
- Convert exclusions to -term format
- Max 30 characters per keyword
- No special characters except - prefix for exclusions
- Simple wildcards allowed: * suffix only
"""

import re
import logging
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)

# Maximum length for a single keyword (universal compatibility)
MAX_KEYWORD_LENGTH = 30

# Boolean operators to remove
BOOLEAN_OPERATORS = {'AND', 'OR', 'NOT'}

# Characters to strip (except - for exclusions and * for wildcards)
INVALID_CHARS_PATTERN = re.compile(r'[()[\]{}"\'\\/|&^%$#@!+=<>~`]')

# Pattern to detect exclusion keywords
EXCLUSION_PATTERNS = [
    re.compile(r'^-\s*(.+)$'),           # -term
    re.compile(r'^NOT\s+(.+)$', re.I),   # NOT term
    re.compile(r'^\s*!\s*(.+)$'),        # !term
]


def normalize_keyword(keyword: str) -> Optional[str]:
    """
    Normalize a single keyword for API compatibility.

    Args:
        keyword: Raw keyword string

    Returns:
        Normalized keyword string, or None if keyword is invalid/empty
    """
    if not keyword:
        return None

    original = keyword
    keyword = keyword.strip()

    if not keyword:
        return None

    # Check if this is an exclusion keyword
    is_exclusion = False
    for pattern in EXCLUSION_PATTERNS:
        match = pattern.match(keyword)
        if match:
            is_exclusion = True
            keyword = match.group(1).strip()
            break

    # Also check if it already starts with -
    if keyword.startswith('-'):
        is_exclusion = True
        keyword = keyword[1:].strip()

    # Remove boolean operators from the keyword
    words = keyword.split()
    filtered_words = []
    for word in words:
        upper_word = word.upper()
        if upper_word not in BOOLEAN_OPERATORS:
            filtered_words.append(word)

    keyword = ' '.join(filtered_words)

    # Remove invalid characters (but preserve * for wildcards)
    keyword = INVALID_CHARS_PATTERN.sub('', keyword)

    # Clean up multiple spaces
    keyword = ' '.join(keyword.split())

    # Validate wildcard usage (only allowed at end)
    if '*' in keyword:
        # Only keep * if it's at the very end
        if keyword.endswith('*'):
            # Valid wildcard position
            pass
        else:
            # Remove wildcards in invalid positions
            keyword = keyword.replace('*', '')

    keyword = keyword.strip()

    if not keyword:
        logger.debug(f"Keyword '{original}' normalized to empty, skipping")
        return None

    # Truncate to max length
    if len(keyword) > MAX_KEYWORD_LENGTH:
        # Try to truncate at word boundary
        truncated = keyword[:MAX_KEYWORD_LENGTH]
        last_space = truncated.rfind(' ')
        if last_space > MAX_KEYWORD_LENGTH // 2:
            keyword = truncated[:last_space].strip()
        else:
            keyword = truncated.strip()
        logger.debug(f"Truncated keyword '{original}' to '{keyword}'")

    # Add exclusion prefix back if needed
    if is_exclusion:
        keyword = f"-{keyword}"

    if keyword != original:
        logger.debug(f"Normalized keyword: '{original}' -> '{keyword}'")

    return keyword


def validate_keyword_for_api(keyword: str) -> Tuple[bool, str]:
    """
    Validate a keyword for API compatibility.

    Args:
        keyword: Keyword to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not keyword:
        return False, "Keyword cannot be empty"

    keyword = keyword.strip()

    # Check for boolean operators
    words = keyword.split()
    for word in words:
        if word.upper() in BOOLEAN_OPERATORS:
            return False, f"Boolean operator '{word}' not allowed. Use simple terms."

    # Check for parentheses
    if '(' in keyword or ')' in keyword:
        return False, "Parentheses not allowed. Use simple terms."

    # Check for brackets
    if '[' in keyword or ']' in keyword:
        return False, "Brackets not allowed. Use simple terms."

    # Check for quotes
    if '"' in keyword or "'" in keyword:
        return False, "Quotes not allowed. Just use plain text."

    # Check length
    check_keyword = keyword[1:] if keyword.startswith('-') else keyword
    if len(check_keyword) > MAX_KEYWORD_LENGTH:
        return False, f"Keyword too long ({len(check_keyword)} chars). Max {MAX_KEYWORD_LENGTH} characters."

    # Check for invalid wildcard position
    if '*' in keyword and not keyword.rstrip('-').endswith('*'):
        return False, "Wildcard (*) only allowed at end of keyword."

    return True, ""


def normalize_keywords_batch(keywords: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """
    Normalize an entire structured keywords dictionary.

    Expected structure:
    {
        "companies": ["Company1", "Company2"],
        "technologies": ["Tech1", "Tech2"],
        "general": ["keyword1", "keyword2"],
        "people": ["Person1", "Person2"],
        "exclusions": ["-term1", "-term2"]
    }

    Args:
        keywords: Dictionary with keyword categories

    Returns:
        Normalized keywords dictionary
    """
    if not keywords:
        return {
            "companies": [],
            "technologies": [],
            "general": [],
            "people": [],
            "exclusions": []
        }

    normalized = {}

    for category, keyword_list in keywords.items():
        if not isinstance(keyword_list, list):
            logger.warning(f"Category '{category}' is not a list, skipping")
            normalized[category] = []
            continue

        normalized_list = []
        for kw in keyword_list:
            if not isinstance(kw, str):
                continue

            # For exclusions category, ensure they have - prefix
            if category == 'exclusions':
                if not kw.strip().startswith('-'):
                    kw = f"-{kw.strip()}"

            normalized_kw = normalize_keyword(kw)
            if normalized_kw:
                # Avoid duplicates within same category
                if normalized_kw not in normalized_list:
                    normalized_list.append(normalized_kw)

        normalized[category] = normalized_list

    # Ensure all expected categories exist
    for expected in ['companies', 'technologies', 'general', 'people', 'exclusions']:
        if expected not in normalized:
            normalized[expected] = []

    return normalized


def normalize_keyword_list(keywords: List[str]) -> List[str]:
    """
    Normalize a flat list of keywords.

    Args:
        keywords: List of keyword strings

    Returns:
        List of normalized keyword strings
    """
    if not keywords:
        return []

    normalized = []
    seen = set()

    for kw in keywords:
        if not isinstance(kw, str):
            continue

        normalized_kw = normalize_keyword(kw)
        if normalized_kw and normalized_kw.lower() not in seen:
            normalized.append(normalized_kw)
            seen.add(normalized_kw.lower())

    return normalized


def get_validation_errors(keywords: List[str]) -> List[Dict[str, str]]:
    """
    Get validation errors for a list of keywords.

    Args:
        keywords: List of keywords to validate

    Returns:
        List of error dictionaries with 'keyword' and 'error' keys
    """
    errors = []

    for kw in keywords:
        is_valid, error_msg = validate_keyword_for_api(kw)
        if not is_valid:
            errors.append({
                'keyword': kw,
                'error': error_msg
            })

    return errors


def split_complex_keyword(keyword: str) -> List[str]:
    """
    Split a complex keyword (with OR, parentheses) into simple keywords.

    Example:
        "(AI OR ML)" -> ["AI", "ML"]
        "AI AND robotics" -> ["AI", "robotics"]

    Args:
        keyword: Complex keyword string

    Returns:
        List of simple keyword strings
    """
    if not keyword:
        return []

    # Remove parentheses
    keyword = keyword.replace('(', ' ').replace(')', ' ')

    # Split on OR/AND operators
    parts = re.split(r'\s+(?:OR|AND)\s+', keyword, flags=re.IGNORECASE)

    # Normalize each part
    result = []
    for part in parts:
        normalized = normalize_keyword(part)
        if normalized:
            result.append(normalized)

    return result


def format_for_display(keyword: str) -> str:
    """
    Format a keyword for display in the UI.

    Args:
        keyword: Keyword string

    Returns:
        Display-formatted string
    """
    if not keyword:
        return ""

    if keyword.startswith('-'):
        return f"Exclude: {keyword[1:]}"
    elif keyword.endswith('*'):
        return f"{keyword[:-1]}... (wildcard)"

    return keyword
