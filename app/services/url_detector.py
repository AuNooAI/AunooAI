"""
URL Detection Utility for Auspex.

Provides functions to detect and extract URLs from user messages,
and determine if a message is primarily a URL lookup request.
"""

import re
from typing import List, Tuple
import logging

logger = logging.getLogger(__name__)

# Comprehensive URL regex pattern
URL_PATTERN = re.compile(
    r'https?://'  # http:// or https://
    r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain
    r'localhost|'  # localhost
    r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # or ip
    r'(?::\d+)?'  # optional port
    r'(?:/?|[/?]\S+)',
    re.IGNORECASE
)

# Patterns that suggest a URL lookup intent
URL_LOOKUP_PATTERNS = [
    r'what\s+(is|does|about|happened)',
    r'tell\s+me\s+about',
    r'(look\s*up|lookup|search\s+for|find)',
    r'(info|information|details)\s+(on|about)',
    r'(analyze|analysis|analyse)\s+(this|the)',
    r'(summarize|summary|summarise)',
    r'what\s+do\s+(you|we)\s+(have|know)',
    r'(have|do)\s+(you|we)\s+have',
    r'is\s+this\s+(in|from)',
    r'check\s+(this|the|if)',
]


def detect_urls(message: str) -> List[str]:
    """
    Extract all URLs from a message.

    Args:
        message: User message text

    Returns:
        List of URLs found in the message
    """
    urls = URL_PATTERN.findall(message)
    # Clean up any trailing punctuation
    cleaned_urls = []
    for url in urls:
        # Remove trailing punctuation that might have been captured
        url = url.rstrip('.,;:!?\'\")')
        if url:
            cleaned_urls.append(url)

    logger.debug(f"Detected URLs in message: {cleaned_urls}")
    return cleaned_urls


def is_url_query(message: str) -> Tuple[bool, List[str]]:
    """
    Determine if a message is primarily a URL lookup request.

    A URL query is when:
    1. The message contains at least one URL, AND
    2. The message is asking about the URL (lookup patterns) OR
    3. The message is primarily just the URL(s) with minimal other text

    Args:
        message: User message text

    Returns:
        Tuple of (is_url_query, list_of_urls)
    """
    urls = detect_urls(message)

    if not urls:
        return False, []

    message_lower = message.lower()

    # Check if message matches URL lookup patterns
    for pattern in URL_LOOKUP_PATTERNS:
        if re.search(pattern, message_lower):
            logger.info(f"URL query detected - lookup pattern matched: {pattern}")
            return True, urls

    # Check if message is primarily just URLs (minimal other text)
    # Remove URLs from message and check remaining length
    message_without_urls = message
    for url in urls:
        message_without_urls = message_without_urls.replace(url, '')

    # Clean remaining text
    remaining_text = ' '.join(message_without_urls.split())
    remaining_words = [w for w in remaining_text.split() if len(w) > 2]

    # If remaining text is very short (<=5 words), it's likely a URL query
    if len(remaining_words) <= 5:
        logger.info(f"URL query detected - minimal text around URL(s)")
        return True, urls

    # Also check if the URL appears at the start or end with a question
    if '?' in message:
        logger.info(f"URL query detected - URL with question mark")
        return True, urls

    return False, urls


def normalize_url(url: str) -> str:
    """
    Normalize a URL for comparison.

    - Removes trailing slashes
    - Removes common tracking parameters
    - Converts to lowercase domain

    Args:
        url: URL to normalize

    Returns:
        Normalized URL
    """
    # Remove trailing slash
    url = url.rstrip('/')

    # Remove common tracking parameters
    tracking_params = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_term',
                       'utm_content', 'fbclid', 'gclid', 'ref', 'source']

    # Simple parameter removal (more sophisticated would use urllib.parse)
    for param in tracking_params:
        # Remove param=value& or &param=value or ?param=value
        url = re.sub(rf'[?&]{param}=[^&]*', '', url)

    # Clean up any leftover ? or & at the end
    url = re.sub(r'[?&]$', '', url)

    return url
