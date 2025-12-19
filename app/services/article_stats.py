"""
Article Statistics Service

Computes statistics directly from retrieved articles for display in the Insights panel.
This provides accurate, pre-computed stats rather than relying on LLM-generated or parsed text.
"""

from typing import List, Dict, Any, Optional
from collections import Counter
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


def compute_article_stats(articles: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Compute comprehensive statistics from a list of articles.

    Args:
        articles: List of article dictionaries with fields like:
            - uri, title, url, summary, category, sentiment
            - future_signal, time_to_impact, publication_date
            - news_source, tags, similarity_score

    Returns:
        Dictionary containing computed statistics for frontend display
    """
    if not articles:
        return _empty_stats()

    # Filter out None/invalid articles
    valid_articles = [a for a in articles if a and isinstance(a, dict)]
    if not valid_articles:
        return _empty_stats()

    total = len(valid_articles)

    # Sentiment breakdown (normalize values)
    sentiments = [_normalize_sentiment(a.get('sentiment')) for a in valid_articles]
    sentiment_counts = Counter(sentiments)

    # Category distribution
    categories = [_normalize_category(a.get('category')) for a in valid_articles]
    category_counts = Counter(categories)

    # Source distribution
    sources = [a.get('news_source', 'Unknown') or 'Unknown' for a in valid_articles]
    source_counts = Counter(sources)

    # Future signals distribution
    signals = [a.get('future_signal', 'None') or 'None' for a in valid_articles]
    signal_counts = Counter(signals)

    # Time to impact distribution
    impacts = [a.get('time_to_impact', 'Unknown') or 'Unknown' for a in valid_articles]
    impact_counts = Counter(impacts)

    # Date range
    dates = _extract_dates(valid_articles)
    date_range = _compute_date_range(dates)

    # Top sources with article URLs
    top_sources = _get_top_sources(valid_articles, limit=15)

    return {
        "total_articles": total,
        "sentiment_breakdown": {
            "positive": sentiment_counts.get('positive', 0),
            "neutral": sentiment_counts.get('neutral', 0),
            "negative": sentiment_counts.get('negative', 0),
            "mixed": sentiment_counts.get('mixed', 0),
            "critical": sentiment_counts.get('critical', 0)
        },
        "category_distribution": dict(category_counts.most_common(10)),
        "source_distribution": dict(source_counts.most_common(20)),
        "signal_distribution": dict(signal_counts.most_common(10)),
        "time_to_impact_distribution": dict(impact_counts.most_common(10)),
        "date_range": date_range,
        "top_sources": top_sources
    }


def _empty_stats() -> Dict[str, Any]:
    """Return empty statistics structure."""
    return {
        "total_articles": 0,
        "sentiment_breakdown": {
            "positive": 0,
            "neutral": 0,
            "negative": 0,
            "mixed": 0,
            "critical": 0
        },
        "category_distribution": {},
        "source_distribution": {},
        "signal_distribution": {},
        "time_to_impact_distribution": {},
        "date_range": {
            "earliest": None,
            "latest": None
        },
        "top_sources": []
    }


def _normalize_sentiment(sentiment: Optional[str]) -> str:
    """Normalize sentiment values to lowercase standard form."""
    if not sentiment:
        return 'neutral'

    s = str(sentiment).lower().strip()

    # Map common variations
    sentiment_map = {
        'positive': 'positive',
        'pos': 'positive',
        'negative': 'negative',
        'neg': 'negative',
        'neutral': 'neutral',
        'mixed': 'mixed',
        'critical': 'critical',
        'crit': 'critical',
        'none': 'neutral',
        '': 'neutral'
    }

    return sentiment_map.get(s, s)


def _normalize_category(category: Optional[str]) -> str:
    """Normalize category values, handling null/empty cases."""
    if not category or category.lower() in ('null', 'none', 'uncategorized', ''):
        return 'Uncategorized'
    return str(category).strip()


def _extract_dates(articles: List[Dict[str, Any]]) -> List[datetime]:
    """Extract valid dates from articles."""
    dates = []

    for article in articles:
        date_str = article.get('publication_date')
        if not date_str or date_str == 'Unknown':
            continue

        try:
            # Handle various date formats
            if isinstance(date_str, datetime):
                dates.append(date_str)
            elif 'T' in str(date_str):
                # ISO format: 2024-12-15T10:30:00
                dates.append(datetime.fromisoformat(date_str.replace('Z', '+00:00').split('+')[0]))
            elif ' ' in str(date_str):
                # Format: 2024-12-15 10:30:00
                dates.append(datetime.strptime(date_str.split(' ')[0], '%Y-%m-%d'))
            else:
                # Format: 2024-12-15
                dates.append(datetime.strptime(date_str[:10], '%Y-%m-%d'))
        except (ValueError, TypeError) as e:
            logger.debug(f"Could not parse date '{date_str}': {e}")
            continue

    return dates


def _compute_date_range(dates: List[datetime]) -> Dict[str, Optional[str]]:
    """Compute the earliest and latest dates."""
    if not dates:
        return {"earliest": None, "latest": None}

    earliest = min(dates)
    latest = max(dates)

    return {
        "earliest": earliest.strftime('%Y-%m-%d'),
        "latest": latest.strftime('%Y-%m-%d')
    }


def _get_top_sources(articles: List[Dict[str, Any]], limit: int = 15) -> List[Dict[str, Any]]:
    """
    Get top sources with article counts and sample URLs.

    Returns list of dicts with: name, count, sample_url (optional)
    """
    source_articles: Dict[str, List[Dict[str, Any]]] = {}

    for article in articles:
        source = article.get('news_source', 'Unknown') or 'Unknown'
        if source not in source_articles:
            source_articles[source] = []
        source_articles[source].append(article)

    # Sort by count, take top N
    sorted_sources = sorted(source_articles.items(), key=lambda x: len(x[1]), reverse=True)[:limit]

    result = []
    for source_name, source_arts in sorted_sources:
        entry = {
            "name": source_name,
            "count": len(source_arts)
        }

        # Add a sample URL from this source
        for art in source_arts:
            url = art.get('url') or art.get('uri')
            if url:
                entry["sample_url"] = url
                break

        result.append(entry)

    return result


def format_stats_for_display(stats: Dict[str, Any]) -> str:
    """
    Format stats as a human-readable summary string.
    Useful for logging or debugging.
    """
    lines = [
        f"Total Articles: {stats.get('total_articles', 0)}",
        "",
        "Sentiment Breakdown:"
    ]

    sentiment = stats.get('sentiment_breakdown', {})
    for key in ['positive', 'neutral', 'negative', 'mixed', 'critical']:
        count = sentiment.get(key, 0)
        if count > 0:
            lines.append(f"  {key.capitalize()}: {count}")

    if stats.get('category_distribution'):
        lines.append("")
        lines.append("Top Categories:")
        for cat, count in list(stats['category_distribution'].items())[:5]:
            lines.append(f"  {cat}: {count}")

    date_range = stats.get('date_range', {})
    if date_range.get('earliest') and date_range.get('latest'):
        lines.append("")
        lines.append(f"Date Range: {date_range['earliest']} to {date_range['latest']}")

    return "\n".join(lines)
