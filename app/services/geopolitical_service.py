"""Geopolitical Hotspots Service

Service layer for managing geopolitical hotspots analysis,
extracting locations from articles, and calculating threat levels.
"""

import logging
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy import text
from app.database import get_database_instance

logger = logging.getLogger(__name__)

# Default topic for geopolitical hotspots
DEFAULT_GEOPOLITICAL_TOPIC = "Geopolitical Hotspots"

# LLM prompt for generating strategic intelligence narrative
NARRATIVE_GENERATION_PROMPT = """You are a geopolitical intelligence analyst. Analyze the following data about current global hotspots and generate a strategic intelligence briefing.

Data Summary:
- Total Active Hotspots: {total_hotspots}
- Countries Affected: {countries_affected}
- Risk Level Breakdown:
  - Critical: {critical_count}
  - High: {high_count}
  - Medium: {medium_count}
  - Low: {low_count}
- Escalating Situations: {escalating_count}
- De-escalating Situations: {de_escalating_count}
- Top Threat Categories: {top_categories}
- Top Regions: {top_regions}
- Recent Articles (7 days): {recent_articles}

Top Hotspots:
{top_hotspots}

Generate a comprehensive strategic intelligence briefing with the following sections:

## Executive Summary
A 2-3 sentence overview of the current global threat landscape.

## Regional Analysis
Analysis of the most significant regional developments and their implications.

## Emerging Threats
Identification of new or escalating threats that require attention.

## Strategic Outlook
Assessment of likely near-term developments and recommended areas of focus.

Write in a professional, analytical tone appropriate for intelligence consumers. Be specific and actionable. Total length should be 400-600 words.
"""

# LLM prompt for extracting geopolitical location data
LOCATION_EXTRACTION_PROMPT = """Analyze this news article and extract geopolitical location information.

Title: {title}
Summary: {summary}
Category: {category}

Extract the PRIMARY location this article is about (the main geographic focus, not every location mentioned).

Respond with JSON only:
{{
    "location_name": "City or region name (e.g., 'Kyiv', 'Taiwan Strait', 'Gaza')",
    "location_type": "city|region|country|maritime|border",
    "country_code": "ISO 2-letter code (e.g., 'UA', 'TW', 'PS') or null if maritime/international",
    "country_name": "Full country name or null",
    "latitude": latitude as float,
    "longitude": longitude as float,
    "threat_category": "conflict|protest|disaster|diplomatic|economic|terrorism|cyber|health|environmental|military|crime|piracy|infrastructure|commodities",
    "risk_assessment": "critical|high|medium|low|info",
    "tags": ["tag1", "tag2"]
}}

If no specific location can be determined, respond with: {{"no_location": true}}
"""

# Threat categories for geopolitical analysis
THREAT_CATEGORIES = [
    'conflict', 'protest', 'disaster', 'diplomatic',
    'economic', 'terrorism', 'cyber', 'health',
    'environmental', 'military', 'crime', 'piracy',
    'infrastructure', 'commodities'
]

RISK_LEVELS = ['critical', 'high', 'medium', 'low', 'info']

# Risk level thresholds based on intensity score
RISK_THRESHOLDS = {
    'critical': 80,
    'high': 60,
    'medium': 40,
    'low': 20,
    'info': 0
}


def get_risk_level(intensity_score: float) -> str:
    """Convert intensity score to risk level."""
    for level, threshold in RISK_THRESHOLDS.items():
        if intensity_score >= threshold:
            return level
    return 'info'


class GeopoliticalService:
    """Service for managing geopolitical hotspots."""

    def __init__(self):
        pass

    def get_overview_stats(self, topic: Optional[str] = None, days_back: int = 30) -> Dict[str, Any]:
        """Get dashboard overview statistics filtered by article publication dates."""
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        try:
            # Build base filter
            topic_filter = ""
            topic_params = []
            if topic:
                topic_filter = "AND h.topic = ?"
                topic_params.append(topic)

            # Date filter for articles (publication_date is TEXT, needs casting)
            date_filter = """
                AND (
                    a.publication_date::timestamp >= CURRENT_DATE - ? * INTERVAL '1 day'
                    OR a.publication_date::date >= CURRENT_DATE - ? * INTERVAL '1 day'
                )
            """

            # Get hotspot IDs that have articles in the date range
            params = [days_back, days_back] + topic_params
            cursor.execute(f"""
                WITH filtered_hotspots AS (
                    SELECT DISTINCT h.id
                    FROM geopolitical_hotspots h
                    JOIN hotspot_articles ha ON h.id = ha.hotspot_id
                    JOIN articles a ON ha.article_uri = a.uri
                    WHERE 1=1 {date_filter} {topic_filter}
                )
                SELECT
                    COUNT(*) as total_hotspots,
                    COUNT(CASE WHEN h.risk_level = 'critical' THEN 1 END) as critical_count,
                    COUNT(CASE WHEN h.risk_level = 'high' THEN 1 END) as high_count,
                    COUNT(CASE WHEN h.risk_level = 'medium' THEN 1 END) as medium_count,
                    COUNT(CASE WHEN h.risk_level = 'low' THEN 1 END) as low_count,
                    COUNT(CASE WHEN h.risk_level = 'info' THEN 1 END) as info_count,
                    COUNT(DISTINCT h.country_code) as countries_affected,
                    COUNT(CASE WHEN h.trend = 'escalating' THEN 1 END) as escalating_count,
                    COUNT(CASE WHEN h.trend = 'de-escalating' THEN 1 END) as de_escalating_count
                FROM geopolitical_hotspots h
                WHERE h.id IN (SELECT id FROM filtered_hotspots)
            """, params)

            row = cursor.fetchone()

            # Get article counts in date range
            from datetime import datetime, timedelta
            recent_cutoff = datetime.now() - timedelta(days=7)

            article_params = [days_back, days_back] + topic_params + [days_back, days_back]
            cursor.execute(f"""
                SELECT
                    COUNT(DISTINCT ha.article_uri) as total_articles,
                    COUNT(DISTINCT CASE
                        WHEN a.publication_date::timestamp >= CURRENT_DATE - 7 * INTERVAL '1 day'
                        OR a.publication_date::date >= CURRENT_DATE - 7 * INTERVAL '1 day'
                        THEN ha.article_uri
                    END) as recent_articles
                FROM hotspot_articles ha
                JOIN geopolitical_hotspots h ON ha.hotspot_id = h.id
                JOIN articles a ON ha.article_uri = a.uri
                WHERE (
                    a.publication_date::timestamp >= CURRENT_DATE - ? * INTERVAL '1 day'
                    OR a.publication_date::date >= CURRENT_DATE - ? * INTERVAL '1 day'
                ) {topic_filter}
            """, article_params[:2] + topic_params)

            article_row = cursor.fetchone()

            stats = {
                'total_hotspots': row[0] if row else 0,
                'by_risk_level': {
                    'critical': row[1] if row else 0,
                    'high': row[2] if row else 0,
                    'medium': row[3] if row else 0,
                    'low': row[4] if row else 0,
                    'info': row[5] if row else 0,
                },
                'total_articles': article_row[0] if article_row else 0,
                'recent_articles': article_row[1] if article_row else 0,
                'countries_affected': row[6] if row else 0,
                'escalating_count': row[7] if row else 0,
                'de_escalating_count': row[8] if row else 0,
            }

            # Get category distribution (only for hotspots with articles in date range)
            cursor.execute(f"""
                WITH filtered_hotspots AS (
                    SELECT DISTINCT h.id
                    FROM geopolitical_hotspots h
                    JOIN hotspot_articles ha ON h.id = ha.hotspot_id
                    JOIN articles a ON ha.article_uri = a.uri
                    WHERE 1=1 {date_filter} {topic_filter}
                )
                SELECT h.primary_category, COUNT(*) as count
                FROM geopolitical_hotspots h
                WHERE h.id IN (SELECT id FROM filtered_hotspots)
                GROUP BY h.primary_category
                ORDER BY count DESC
            """, params)

            stats['by_category'] = {row[0]: row[1] for row in cursor.fetchall() if row[0]}

            # Get top hotspots (filtered by date range with article counts)
            # Deduplicate: if both a country and a city/region in that country appear,
            # prefer the country-level entry to avoid showing e.g. both "Ukraine" and "Kyiv"
            cursor.execute(f"""
                WITH filtered_hotspots AS (
                    SELECT h.id, COUNT(DISTINCT ha.article_uri) as filtered_count
                    FROM geopolitical_hotspots h
                    JOIN hotspot_articles ha ON h.id = ha.hotspot_id
                    JOIN articles a ON ha.article_uri = a.uri
                    WHERE 1=1 {date_filter} {topic_filter}
                    GROUP BY h.id
                ),
                ranked AS (
                    SELECT h.id, h.location_name, h.country_name, h.intensity_score, h.risk_level,
                           h.primary_category, fh.filtered_count as article_count, h.trend,
                           ROW_NUMBER() OVER (
                               PARTITION BY COALESCE(h.country_code, h.id::text)
                               ORDER BY
                                   CASE WHEN h.location_type = 'country' THEN 0 ELSE 1 END,
                                   h.intensity_score DESC
                           ) as rn
                    FROM geopolitical_hotspots h
                    JOIN filtered_hotspots fh ON h.id = fh.id
                )
                SELECT id, location_name, country_name, intensity_score, risk_level,
                       primary_category, article_count, trend
                FROM ranked
                WHERE rn = 1
                ORDER BY intensity_score DESC
                LIMIT 5
            """, params)

            stats['top_hotspots'] = [
                {
                    'id': row[0],
                    'location_name': row[1],
                    'country_name': row[2],
                    'intensity_score': row[3],
                    'risk_level': row[4],
                    'primary_category': row[5],
                    'article_count': row[6],
                    'trend': row[7]
                }
                for row in cursor.fetchall()
            ]

            return stats

        finally:
            cursor.close()
            conn.close()

    def get_map_data(self, topic: Optional[str] = None,
                     categories: Optional[List[str]] = None,
                     risk_levels: Optional[List[str]] = None,
                     days_back: int = 30) -> List[Dict[str, Any]]:
        """Get all hotspots with coordinates for map display, filtered by article publication dates."""
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        try:
            where_clauses = ["1=1"]
            params = []  # Build params in order they appear in SQL

            if topic:
                where_clauses.append("h.topic = ?")
                params.append(topic)

            if categories:
                placeholders = ', '.join(['?' for _ in categories])
                where_clauses.append(f"h.primary_category IN ({placeholders})")
                params.extend(categories)

            if risk_levels:
                placeholders = ', '.join(['?' for _ in risk_levels])
                where_clauses.append(f"h.risk_level IN ({placeholders})")
                params.extend(risk_levels)

            where_sql = " AND ".join(where_clauses)

            # Add days_back params at end (they appear last in the SQL query)
            params.extend([days_back, days_back])

            # Date filter for articles (publication_date is TEXT, needs casting)
            date_filter = """
                AND (
                    a.publication_date::timestamp >= CURRENT_DATE - ? * INTERVAL '1 day'
                    OR a.publication_date::date >= CURRENT_DATE - ? * INTERVAL '1 day'
                )
            """

            cursor.execute(f"""
                WITH filtered_hotspots AS (
                    SELECT h.id, COUNT(DISTINCT ha.article_uri) as filtered_count
                    FROM geopolitical_hotspots h
                    JOIN hotspot_articles ha ON h.id = ha.hotspot_id
                    JOIN articles a ON ha.article_uri = a.uri
                    WHERE {where_sql} {date_filter}
                    GROUP BY h.id
                    HAVING COUNT(DISTINCT ha.article_uri) > 0
                )
                SELECT h.id, h.location_name, h.location_type, h.country_code, h.country_name,
                       h.latitude, h.longitude, h.intensity_score, h.risk_level, h.trend,
                       fh.filtered_count as article_count,
                       fh.filtered_count as recent_article_count,
                       h.primary_category, h.tags, h.last_article_date
                FROM geopolitical_hotspots h
                JOIN filtered_hotspots fh ON h.id = fh.id
                ORDER BY h.intensity_score DESC
            """, params)

            return [
                {
                    'id': row[0],
                    'location_name': row[1],
                    'location_type': row[2],
                    'country_code': row[3],
                    'country_name': row[4],
                    'latitude': row[5],
                    'longitude': row[6],
                    'intensity_score': row[7],
                    'risk_level': row[8],
                    'trend': row[9],
                    'article_count': row[10],
                    'recent_article_count': row[11],
                    'primary_category': row[12],
                    'tags': row[13],
                    'last_article_date': row[14].isoformat() if row[14] else None
                }
                for row in cursor.fetchall()
            ]

        finally:
            cursor.close()
            conn.close()

    def get_countries_data(self, topic: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get country-level aggregation for choropleth map."""
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        try:
            where_clause = ""
            params = []
            if topic:
                where_clause = "WHERE topic = ?"
                params.append(topic)

            cursor.execute(f"""
                SELECT country_code, country_name, total_hotspots, total_articles,
                       heat_value, max_risk_level, primary_category
                FROM country_hotspot_stats
                {where_clause}
                ORDER BY heat_value DESC
            """, params if params else None)

            return [
                {
                    'country_code': row[0],
                    'country_name': row[1],
                    'total_hotspots': row[2],
                    'total_articles': row[3],
                    'heat_value': row[4],
                    'max_risk_level': row[5],
                    'primary_category': row[6]
                }
                for row in cursor.fetchall()
            ]

        finally:
            cursor.close()
            conn.close()

    def get_hotspots(self, topic: Optional[str] = None,
                     categories: Optional[List[str]] = None,
                     risk_levels: Optional[List[str]] = None,
                     country_code: Optional[str] = None,
                     days_back: int = 30,
                     page: int = 1, page_size: int = 20,
                     sort_by: str = 'intensity',
                     sort_order: str = 'desc') -> Tuple[List[Dict[str, Any]], int]:
        """Get paginated list of hotspots with filters based on article publication dates."""
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        try:
            where_clauses = ["h.id IS NOT NULL"]  # Start with a true condition
            params = []

            if topic:
                where_clauses.append("h.topic = ?")
                params.append(topic)

            if categories:
                placeholders = ', '.join(['?' for _ in categories])
                where_clauses.append(f"h.primary_category IN ({placeholders})")
                params.extend(categories)

            if risk_levels:
                placeholders = ', '.join(['?' for _ in risk_levels])
                where_clauses.append(f"h.risk_level IN ({placeholders})")
                params.extend(risk_levels)

            if country_code:
                where_clauses.append("h.country_code = ?")
                params.append(country_code)

            where_sql = "WHERE " + " AND ".join(where_clauses)

            # Sort mapping
            sort_columns = {
                'intensity': 'h.intensity_score',
                'articles': 'filtered_article_count',
                'recent': 'filtered_article_count',
                'name': 'h.location_name',
                'updated': 'h.updated_at'
            }
            sort_col = sort_columns.get(sort_by, 'h.intensity_score')
            order = 'DESC' if sort_order.lower() == 'desc' else 'ASC'

            # Build the date filter for articles
            # publication_date is stored as TEXT, so we need to cast it
            date_filter_sql = ""
            if days_back:
                date_filter_sql = f"""
                    AND (
                        a.publication_date::timestamp >= CURRENT_DATE - ? * INTERVAL '1 day'
                        OR a.publication_date::date >= CURRENT_DATE - ? * INTERVAL '1 day'
                    )
                """

            # Query that joins with articles and filters by publication date
            # Returns hotspots that have at least one article in the date range
            query = f"""
                WITH filtered_hotspots AS (
                    SELECT h.id,
                           COUNT(DISTINCT ha.article_uri) as filtered_article_count
                    FROM geopolitical_hotspots h
                    JOIN hotspot_articles ha ON h.id = ha.hotspot_id
                    JOIN articles a ON ha.article_uri = a.uri
                    {where_sql}
                    {date_filter_sql}
                    GROUP BY h.id
                    HAVING COUNT(DISTINCT ha.article_uri) > 0
                )
                SELECT COUNT(*) FROM filtered_hotspots
            """

            # Build params for date filter (used twice in the OR clause)
            count_params = params.copy()
            if days_back:
                count_params.extend([days_back, days_back])

            cursor.execute(query, count_params if count_params else None)
            total = cursor.fetchone()[0]

            # Get paginated results with article counts
            offset = (page - 1) * page_size
            results_query = f"""
                WITH filtered_hotspots AS (
                    SELECT h.id,
                           COUNT(DISTINCT ha.article_uri) as filtered_article_count
                    FROM geopolitical_hotspots h
                    JOIN hotspot_articles ha ON h.id = ha.hotspot_id
                    JOIN articles a ON ha.article_uri = a.uri
                    {where_sql}
                    {date_filter_sql}
                    GROUP BY h.id
                    HAVING COUNT(DISTINCT ha.article_uri) > 0
                )
                SELECT h.id, h.location_name, h.location_type, h.country_code, h.country_name,
                       h.latitude, h.longitude, h.intensity_score, h.risk_level, h.trend,
                       fh.filtered_article_count as article_count,
                       fh.filtered_article_count as recent_article_count,
                       h.primary_category, h.tags,
                       h.last_article_date, h.created_at, h.updated_at
                FROM geopolitical_hotspots h
                JOIN filtered_hotspots fh ON h.id = fh.id
                ORDER BY {sort_col} {order}
                LIMIT ? OFFSET ?
            """

            results_params = count_params + [page_size, offset]
            cursor.execute(results_query, results_params)

            hotspots = [
                {
                    'id': row[0],
                    'location_name': row[1],
                    'location_type': row[2],
                    'country_code': row[3],
                    'country_name': row[4],
                    'latitude': row[5],
                    'longitude': row[6],
                    'intensity_score': row[7],
                    'risk_level': row[8],
                    'trend': row[9],
                    'article_count': row[10],
                    'recent_article_count': row[11],
                    'primary_category': row[12],
                    'tags': row[13],
                    'last_article_date': row[14].isoformat() if row[14] else None,
                    'created_at': row[15].isoformat() if row[15] else None,
                    'updated_at': row[16].isoformat() if row[16] else None,
                }
                for row in cursor.fetchall()
            ]

            return hotspots, total

        finally:
            cursor.close()
            conn.close()

    def get_hotspot_by_id(self, hotspot_id: int) -> Optional[Dict[str, Any]]:
        """Get single hotspot by ID with full details."""
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT id, location_name, location_type, country_code, country_name,
                       latitude, longitude, intensity_score, risk_level, trend,
                       article_count, recent_article_count, primary_category, tags,
                       topic, last_article_date, created_at, updated_at
                FROM geopolitical_hotspots
                WHERE id = ?
            """, [hotspot_id])

            row = cursor.fetchone()
            if not row:
                return None

            return {
                'id': row[0],
                'location_name': row[1],
                'location_type': row[2],
                'country_code': row[3],
                'country_name': row[4],
                'latitude': row[5],
                'longitude': row[6],
                'intensity_score': row[7],
                'risk_level': row[8],
                'trend': row[9],
                'article_count': row[10],
                'recent_article_count': row[11],
                'primary_category': row[12],
                'tags': row[13],
                'topic': row[14],
                'last_article_date': row[15].isoformat() if row[15] else None,
                'created_at': row[16].isoformat() if row[16] else None,
                'updated_at': row[17].isoformat() if row[17] else None,
            }

        finally:
            cursor.close()
            conn.close()

    def get_hotspot_articles(self, hotspot_id: int,
                             page: int = 1, page_size: int = 20) -> Tuple[List[Dict[str, Any]], int]:
        """Get articles linked to a hotspot."""
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        try:
            # Get total count
            cursor.execute("""
                SELECT COUNT(*) FROM hotspot_articles WHERE hotspot_id = ?
            """, [hotspot_id])
            total = cursor.fetchone()[0]

            # Get paginated articles
            offset = (page - 1) * page_size
            cursor.execute("""
                SELECT a.uri, a.title, a.news_source, a.publication_date, a.summary,
                       a.category, a.sentiment, ha.relevance_score, ha.mention_type
                FROM hotspot_articles ha
                JOIN articles a ON ha.article_uri = a.uri
                WHERE ha.hotspot_id = ?
                ORDER BY a.publication_date DESC
                LIMIT ? OFFSET ?
            """, [hotspot_id, page_size, offset])

            articles = [
                {
                    'uri': row[0],
                    'title': row[1],
                    'source': row[2],
                    'publication_date': row[3],
                    'summary': row[4],
                    'category': row[5],
                    'sentiment': row[6],
                    'relevance_score': row[7],
                    'mention_type': row[8]
                }
                for row in cursor.fetchall()
            ]

            return articles, total

        finally:
            cursor.close()
            conn.close()

    def get_timeline_data(self, topic: Optional[str] = None,
                          days_back: int = 30) -> List[Dict[str, Any]]:
        """Get temporal trend data for hotspots using article publication dates."""
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        try:
            start_date = datetime.now() - timedelta(days=days_back)

            # Use article publication_date for timeline (same approach as get_daily_article_counts)
            where_clause = "WHERE a.publication_date::timestamp >= ?"
            params = [start_date]

            if topic:
                where_clause += " AND gh.topic = ?"
                params.append(topic)

            cursor.execute(f"""
                SELECT DATE(a.publication_date::timestamp) as date,
                       COUNT(DISTINCT ha.article_uri) as article_count,
                       AVG(gh.intensity_score) as avg_intensity,
                       COUNT(DISTINCT ha.hotspot_id) as hotspot_count
                FROM hotspot_articles ha
                JOIN geopolitical_hotspots gh ON ha.hotspot_id = gh.id
                JOIN articles a ON ha.article_uri = a.uri
                {where_clause}
                AND a.publication_date IS NOT NULL
                AND a.publication_date != ''
                GROUP BY DATE(a.publication_date::timestamp)
                ORDER BY date
            """, params)

            return [
                {
                    'date': row[0].isoformat() if row[0] else None,
                    'article_count': row[1],
                    'avg_intensity': round(row[2], 2) if row[2] else 0,
                    'hotspot_count': row[3]
                }
                for row in cursor.fetchall()
            ]

        finally:
            cursor.close()
            conn.close()

    def get_regions_data(self, topic: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get regional breakdown of hotspots."""
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        try:
            # Region mapping based on country codes
            # Using a simplified regional grouping
            where_clause = ""
            params = []
            if topic:
                where_clause = "WHERE topic = ?"
                params.append(topic)

            cursor.execute(f"""
                WITH region_mapping AS (
                    SELECT
                        id,
                        country_code,
                        article_count,
                        CASE
                            WHEN country_code IN ('US', 'CA', 'MX') THEN 'North America'
                            WHEN country_code IN ('BR', 'AR', 'CO', 'CL', 'PE', 'VE', 'EC', 'BO', 'PY', 'UY') THEN 'South America'
                            WHEN country_code IN ('GB', 'DE', 'FR', 'IT', 'ES', 'PL', 'NL', 'BE', 'SE', 'NO', 'DK', 'FI', 'AT', 'CH', 'PT', 'IE', 'GR', 'CZ', 'RO', 'HU', 'UA', 'BY') THEN 'Europe'
                            WHEN country_code IN ('RU') THEN 'Russia'
                            WHEN country_code IN ('CN', 'JP', 'KR', 'KP', 'TW', 'HK', 'MO', 'MN') THEN 'East Asia'
                            WHEN country_code IN ('IN', 'PK', 'BD', 'LK', 'NP', 'BT', 'AF') THEN 'South Asia'
                            WHEN country_code IN ('ID', 'TH', 'VN', 'PH', 'MY', 'SG', 'MM', 'KH', 'LA', 'BN') THEN 'Southeast Asia'
                            WHEN country_code IN ('SA', 'AE', 'IL', 'IR', 'IQ', 'SY', 'JO', 'LB', 'KW', 'QA', 'BH', 'OM', 'YE', 'TR', 'PS') THEN 'Middle East'
                            WHEN country_code IN ('EG', 'ZA', 'NG', 'KE', 'ET', 'GH', 'TZ', 'DZ', 'MA', 'TN', 'SD', 'LY', 'UG', 'CM', 'CI', 'CD', 'SN', 'ZW', 'AO') THEN 'Africa'
                            WHEN country_code IN ('AU', 'NZ', 'FJ', 'PG', 'NC') THEN 'Oceania'
                            ELSE 'Other'
                        END as region
                    FROM geopolitical_hotspots
                    {where_clause}
                )
                SELECT
                    region,
                    COUNT(*) as hotspot_count,
                    COALESCE(SUM(article_count), 0) as article_count
                FROM region_mapping rm
                GROUP BY region
                ORDER BY hotspot_count DESC
            """, params if params else None)

            return [
                {
                    'region': row[0],
                    'hotspot_count': row[1],
                    'article_count': row[2] or 0
                }
                for row in cursor.fetchall()
            ]

        finally:
            cursor.close()
            conn.close()

    def get_category_distribution(self, topic: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get distribution by threat category."""
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        try:
            where_clauses = ["primary_category IS NOT NULL"]
            params = []
            if topic:
                where_clauses.append("topic = ?")
                params.append(topic)

            where_sql = "WHERE " + " AND ".join(where_clauses)

            cursor.execute(f"""
                SELECT primary_category,
                       COUNT(*) as count,
                       AVG(intensity_score) as avg_intensity,
                       SUM(article_count) as total_articles
                FROM geopolitical_hotspots
                {where_sql}
                GROUP BY primary_category
                ORDER BY count DESC
            """, params if params else None)

            return [
                {
                    'category': row[0],
                    'count': row[1],
                    'avg_intensity': round(row[2], 2) if row[2] else 0,
                    'total_articles': row[3] or 0
                }
                for row in cursor.fetchall()
            ]

        finally:
            cursor.close()
            conn.close()

    def get_all_hotspot_articles(self, page: int = 1, page_size: int = 20,
                                   risk_level: Optional[str] = None,
                                   category: Optional[str] = None,
                                   hotspot_id: Optional[int] = None,
                                   search: Optional[str] = None,
                                   sort_by: str = 'date',
                                   sort_order: str = 'desc') -> Tuple[List[Dict[str, Any]], int]:
        """Get all articles linked to any hotspot with filters."""
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        try:
            where_clauses = []
            params = []

            # Filter by specific hotspot
            if hotspot_id:
                where_clauses.append("gh.id = ?")
                params.append(hotspot_id)

            # Filter by risk level
            if risk_level:
                where_clauses.append("gh.risk_level = ?")
                params.append(risk_level)

            # Filter by category
            if category:
                where_clauses.append("gh.primary_category = ?")
                params.append(category)

            # Search by title or summary
            if search:
                where_clauses.append("(a.title LIKE ? OR a.summary LIKE ?)")
                search_term = f"%{search}%"
                params.extend([search_term, search_term])

            where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

            # Sort mapping
            sort_columns = {
                'date': 'a.publication_date',
                'title': 'a.title',
                'relevance': 'ha.relevance_score',
                'intensity': 'gh.intensity_score'
            }
            sort_col = sort_columns.get(sort_by, 'a.publication_date')
            order = 'DESC' if sort_order.lower() == 'desc' else 'ASC'

            # Get total count (unique articles)
            cursor.execute(f"""
                SELECT COUNT(DISTINCT a.uri)
                FROM hotspot_articles ha
                JOIN articles a ON ha.article_uri = a.uri
                JOIN geopolitical_hotspots gh ON ha.hotspot_id = gh.id
                {where_sql}
            """, params if params else None)
            total = cursor.fetchone()[0]

            # Get paginated results - aggregate all hotspots per article
            offset = (page - 1) * page_size
            cursor.execute(f"""
                WITH article_hotspots AS (
                    SELECT a.uri, a.title, a.news_source, a.publication_date, a.summary,
                           a.category, a.sentiment,
                           json_agg(json_build_object(
                               'id', gh.id,
                               'name', gh.location_name,
                               'risk_level', gh.risk_level,
                               'category', gh.primary_category,
                               'intensity', gh.intensity_score
                           ) ORDER BY gh.intensity_score DESC) as hotspots,
                           MAX(gh.intensity_score) as max_intensity,
                           MAX(ha.relevance_score) as max_relevance
                    FROM hotspot_articles ha
                    JOIN articles a ON ha.article_uri = a.uri
                    JOIN geopolitical_hotspots gh ON ha.hotspot_id = gh.id
                    {where_sql}
                    GROUP BY a.uri, a.title, a.news_source, a.publication_date, a.summary,
                             a.category, a.sentiment
                )
                SELECT uri, title, news_source, publication_date, summary,
                       category, sentiment, max_relevance, hotspots, max_intensity
                FROM article_hotspots
                ORDER BY {sort_col.replace('a.', '').replace('ha.', 'max_').replace('gh.', 'max_')} {order}
                LIMIT ? OFFSET ?
            """, (params + [page_size, offset]) if params else [page_size, offset])

            articles = []
            for row in cursor.fetchall():
                hotspots_data = row[8] if row[8] else []
                # Primary hotspot is first (highest intensity)
                primary = hotspots_data[0] if hotspots_data else {}
                articles.append({
                    'uri': row[0],
                    'title': row[1],
                    'source': row[2],
                    'publication_date': row[3] if row[3] else None,
                    'summary': row[4],
                    'category': row[5],
                    'sentiment': row[6],
                    'relevance_score': row[7],
                    'mention_type': 'primary',
                    # Primary hotspot fields for backward compatibility
                    'hotspot_id': primary.get('id'),
                    'hotspot_name': primary.get('name'),
                    'risk_level': primary.get('risk_level', 'info'),
                    'hotspot_category': primary.get('category'),
                    'intensity_score': row[9],
                    # All linked hotspots
                    'hotspots': hotspots_data
                })

            return articles, total

        finally:
            cursor.close()
            conn.close()

    def get_daily_article_counts(self, topic: Optional[str] = None,
                                  days_back: int = 30) -> List[Dict[str, Any]]:
        """Get daily article counts for timeline chart with rolling average.
        Uses article publication_date for timeline (not submission/extraction date).
        """
        conn = None
        cursor = None
        try:
            conn = get_database_instance().get_connection()
            cursor = conn.cursor()

            from datetime import datetime, timedelta
            start_date = datetime.now() - timedelta(days=days_back)

            # Use article publication_date for timeline, not extracted_at
            # Cast text to timestamp for proper date comparison (handles ISO formats)
            where_clause = "WHERE a.publication_date::timestamp >= ?"
            params = [start_date]

            if topic:
                where_clause += " AND gh.topic = ?"
                params.append(topic)

            cursor.execute(f"""
                SELECT DATE(a.publication_date::timestamp) as date,
                       COUNT(DISTINCT ha.article_uri) as article_count,
                       COUNT(DISTINCT ha.hotspot_id) as hotspot_count,
                       AVG(gh.intensity_score) as avg_intensity
                FROM hotspot_articles ha
                JOIN geopolitical_hotspots gh ON ha.hotspot_id = gh.id
                JOIN articles a ON ha.article_uri = a.uri
                {where_clause}
                AND a.publication_date IS NOT NULL
                AND a.publication_date != ''
                GROUP BY DATE(a.publication_date::timestamp)
                ORDER BY date
            """, params)

            daily_data = []
            for row in cursor.fetchall():
                try:
                    date_val = row[0].isoformat() if row[0] else None
                    daily_data.append({
                        'date': date_val,
                        'article_count': int(row[1]) if row[1] else 0,
                        'hotspot_count': int(row[2]) if row[2] else 0,
                        'avg_intensity': round(float(row[3]), 2) if row[3] else 0
                    })
                except Exception as row_err:
                    logger.warning(f"Error processing row in daily counts: {row_err}, row: {row}")
                    continue

            # Calculate 7-day rolling average
            for i, day in enumerate(daily_data):
                window_start = max(0, i - 6)
                window = daily_data[window_start:i + 1]
                day['rolling_avg'] = round(
                    sum(d['article_count'] for d in window) / len(window), 1
                ) if window else 0

            return daily_data

        except Exception as e:
            logger.error(f"Error in get_daily_article_counts: {e}")
            raise
        finally:
            if cursor:
                try:
                    cursor.close()
                except:
                    pass
            if conn:
                try:
                    conn.close()
                except:
                    pass

    def get_day_of_week_distribution(self, topic: Optional[str] = None,
                                      days_back: int = 30) -> List[Dict[str, Any]]:
        """Get article count distribution by day of week.
        Uses article publication_date (not submission/extraction date).
        """
        conn = None
        cursor = None
        try:
            conn = get_database_instance().get_connection()
            cursor = conn.cursor()

            from datetime import datetime, timedelta
            start_date = datetime.now() - timedelta(days=days_back)

            # Use publication_date for distribution, not extracted_at
            # Cast text to timestamp for proper date comparison
            where_clause = "WHERE a.publication_date::timestamp >= ?"
            params = [start_date]

            if topic:
                where_clause += " AND gh.topic = ?"
                params.append(topic)

            # PostgreSQL uses EXTRACT(DOW FROM ...), SQLite uses strftime('%w', ...)
            cursor.execute(f"""
                SELECT EXTRACT(DOW FROM a.publication_date::timestamp) as day_of_week,
                       COUNT(DISTINCT ha.article_uri) as article_count
                FROM hotspot_articles ha
                JOIN geopolitical_hotspots gh ON ha.hotspot_id = gh.id
                JOIN articles a ON ha.article_uri = a.uri
                {where_clause}
                AND a.publication_date IS NOT NULL
                AND a.publication_date != ''
                GROUP BY EXTRACT(DOW FROM a.publication_date::timestamp)
                ORDER BY day_of_week
            """, params)

            day_names = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
            distribution = {i: 0 for i in range(7)}

            for row in cursor.fetchall():
                try:
                    day_num = int(row[0]) if row[0] is not None else 0
                    if 0 <= day_num <= 6:
                        distribution[day_num] = int(row[1]) if row[1] else 0
                except Exception as row_err:
                    logger.warning(f"Error processing row in day_of_week: {row_err}, row: {row}")
                    continue

            return [
                {'day': day_names[i], 'day_num': i, 'article_count': distribution[i]}
                for i in range(7)
            ]

        except Exception as e:
            logger.error(f"Error in get_day_of_week_distribution: {e}")
            raise
        finally:
            if cursor:
                try:
                    cursor.close()
                except:
                    pass
            if conn:
                try:
                    conn.close()
                except:
                    pass

    def get_category_cooccurrence(self, topic: Optional[str] = None) -> Dict[str, Any]:
        """Get category co-occurrence matrix for heatmap."""
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        try:
            where_clause = ""
            params = []
            if topic:
                where_clause = "WHERE gh1.topic = ? AND gh2.topic = ?"
                params = [topic, topic]

            # Get articles that appear in multiple hotspots with different categories
            cursor.execute(f"""
                SELECT gh1.primary_category as cat1, gh2.primary_category as cat2, COUNT(*) as count
                FROM hotspot_articles ha1
                JOIN hotspot_articles ha2 ON ha1.article_uri = ha2.article_uri AND ha1.hotspot_id < ha2.hotspot_id
                JOIN geopolitical_hotspots gh1 ON ha1.hotspot_id = gh1.id
                JOIN geopolitical_hotspots gh2 ON ha2.hotspot_id = gh2.id
                {where_clause}
                AND gh1.primary_category IS NOT NULL
                AND gh2.primary_category IS NOT NULL
                GROUP BY gh1.primary_category, gh2.primary_category
                ORDER BY count DESC
            """, params if params else None)

            pairs = []
            matrix = {}
            categories_set = set()

            for row in cursor.fetchall():
                cat1, cat2, count = row[0], row[1], row[2]
                pairs.append({'category1': cat1, 'category2': cat2, 'count': count})
                categories_set.add(cat1)
                categories_set.add(cat2)

                # Build matrix
                if cat1 not in matrix:
                    matrix[cat1] = {}
                if cat2 not in matrix:
                    matrix[cat2] = {}
                matrix[cat1][cat2] = count
                matrix[cat2][cat1] = count  # Symmetric

            categories = sorted(list(categories_set))

            return {
                'categories': categories,
                'pairs': pairs[:20],  # Top 20 pairs
                'matrix': matrix
            }

        finally:
            cursor.close()
            conn.close()

    def get_category_trends(self, topic: Optional[str] = None, days_back: int = 90,
                            granularity: str = 'weekly') -> List[Dict[str, Any]]:
        """Get category breakdown over time periods (weekly or monthly)."""
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        try:
            start_date = datetime.now() - timedelta(days=days_back)

            where_clause = "WHERE ha.extracted_at >= ?"
            params = [start_date]

            if topic:
                where_clause += " AND gh.topic = ?"
                params.append(topic)

            # Use DATE_TRUNC for PostgreSQL to group by period
            if granularity == 'monthly':
                date_trunc = "DATE_TRUNC('month', ha.extracted_at)"
            else:  # weekly
                date_trunc = "DATE_TRUNC('week', ha.extracted_at)"

            cursor.execute(f"""
                SELECT {date_trunc} as period,
                       gh.primary_category,
                       COUNT(DISTINCT ha.article_uri) as article_count
                FROM hotspot_articles ha
                JOIN geopolitical_hotspots gh ON ha.hotspot_id = gh.id
                {where_clause}
                AND gh.primary_category IS NOT NULL
                GROUP BY {date_trunc}, gh.primary_category
                ORDER BY period
            """, params)

            # Organize by period
            trends_dict = {}
            for row in cursor.fetchall():
                period = row[0].strftime('%Y-%m-%d') if row[0] else None
                category = row[1]
                count = row[2]

                if period not in trends_dict:
                    trends_dict[period] = {}
                trends_dict[period][category] = count

            # Convert to list format
            trends = [
                {'period': period, 'by_category': cats}
                for period, cats in sorted(trends_dict.items())
            ]

            return trends

        finally:
            cursor.close()
            conn.close()

    def get_actors(self, topic: Optional[str] = None, days_back: int = 30) -> List[Dict[str, Any]]:
        """Get key actors/entities extracted from articles.

        Actors are extracted from hotspot country names and location names,
        as well as article categories indicating state/non-state actors.
        """
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        try:
            start_date = datetime.now() - timedelta(days=days_back)

            where_clause = "WHERE ha.extracted_at >= ?"
            params = [start_date]

            if topic:
                where_clause += " AND gh.topic = ?"
                params.append(topic)

            # Get actors from country names (State actors)
            cursor.execute(f"""
                SELECT gh.country_name as actor,
                       'state' as actor_type,
                       COUNT(DISTINCT ha.article_uri) as mention_count
                FROM hotspot_articles ha
                JOIN geopolitical_hotspots gh ON ha.hotspot_id = gh.id
                {where_clause}
                AND gh.country_name IS NOT NULL
                GROUP BY gh.country_name
                ORDER BY mention_count DESC
                LIMIT 20
            """, params)

            actors = []
            total_mentions = 0

            for row in cursor.fetchall():
                actors.append({
                    'actor': row[0],
                    'actor_type': row[1],
                    'mention_count': row[2]
                })
                total_mentions += row[2]

            # Get actors from location names that indicate organizations or groups
            # (locations with certain categories tend to indicate non-state actors)
            cursor.execute(f"""
                SELECT gh.location_name as actor,
                       CASE
                           WHEN gh.primary_category IN ('terrorism', 'crime', 'piracy') THEN 'non_state'
                           WHEN gh.primary_category IN ('diplomatic', 'military') THEN 'organization'
                           ELSE 'location'
                       END as actor_type,
                       COUNT(DISTINCT ha.article_uri) as mention_count
                FROM hotspot_articles ha
                JOIN geopolitical_hotspots gh ON ha.hotspot_id = gh.id
                {where_clause}
                AND gh.location_type != 'city'
                AND gh.primary_category IN ('terrorism', 'crime', 'piracy', 'diplomatic', 'military')
                GROUP BY gh.location_name, gh.primary_category
                ORDER BY mention_count DESC
                LIMIT 10
            """, params)

            for row in cursor.fetchall():
                actors.append({
                    'actor': row[0],
                    'actor_type': row[1],
                    'mention_count': row[2]
                })
                total_mentions += row[2]

            # Calculate percentages
            for actor in actors:
                actor['percentage'] = round(
                    (actor['mention_count'] / total_mentions * 100) if total_mentions > 0 else 0, 1
                )

            # Sort by mention count
            actors.sort(key=lambda x: x['mention_count'], reverse=True)

            return actors

        finally:
            cursor.close()
            conn.close()

    def get_escalation_markers(self, topic: Optional[str] = None, days_back: int = 30) -> Dict[str, Any]:
        """Get escalation indicators from article analysis.

        Escalation markers are derived from:
        - Hotspot trend status (escalating/de-escalating)
        - Category distribution changes
        - Risk level progression
        """
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        try:
            start_date = datetime.now() - timedelta(days=days_back)

            where_clause = "WHERE ha.extracted_at >= ?"
            params = [start_date]

            if topic:
                where_clause += " AND gh.topic = ?"
                params.append(topic)

            # Get escalation marker types based on categories
            # Map threat categories to escalation marker types
            cursor.execute(f"""
                SELECT
                    CASE
                        WHEN gh.primary_category = 'military' THEN 'Military Buildup'
                        WHEN gh.primary_category = 'diplomatic' THEN 'Diplomatic Breakdown'
                        WHEN gh.primary_category = 'economic' THEN 'Economic Sanctions'
                        WHEN gh.primary_category = 'protest' THEN 'Civil Unrest'
                        WHEN gh.primary_category = 'conflict' THEN 'Armed Conflict'
                        WHEN gh.primary_category = 'terrorism' THEN 'Terrorist Activity'
                        WHEN gh.primary_category = 'cyber' THEN 'Cyber Operations'
                        ELSE 'Other'
                    END as marker_type,
                    COUNT(DISTINCT ha.article_uri) as article_count
                FROM hotspot_articles ha
                JOIN geopolitical_hotspots gh ON ha.hotspot_id = gh.id
                {where_clause}
                AND gh.primary_category IS NOT NULL
                GROUP BY marker_type
                ORDER BY article_count DESC
            """, params)

            markers = []
            total_count = 0

            for row in cursor.fetchall():
                markers.append({
                    'marker_type': row[0],
                    'article_count': row[1]
                })
                total_count += row[1]

            # Calculate percentages
            for marker in markers:
                marker['percentage'] = round(
                    (marker['article_count'] / total_count * 100) if total_count > 0 else 0, 1
                )

            # Get escalation trends over time (weekly)
            cursor.execute(f"""
                SELECT DATE_TRUNC('week', ha.extracted_at) as period,
                       COUNT(DISTINCT ha.article_uri) as total_articles,
                       AVG(gh.intensity_score) as avg_intensity,
                       COUNT(CASE WHEN gh.trend = 'escalating' THEN 1 END) as escalating_count
                FROM hotspot_articles ha
                JOIN geopolitical_hotspots gh ON ha.hotspot_id = gh.id
                {where_clause}
                GROUP BY DATE_TRUNC('week', ha.extracted_at)
                ORDER BY period
            """, params)

            trends = []
            for row in cursor.fetchall():
                week_num = len(trends) + 1
                trends.append({
                    'period': f"Week {week_num}",
                    'period_date': row[0].strftime('%Y-%m-%d') if row[0] else None,
                    'total_articles': row[1],
                    'avg_intensity': round(row[2], 1) if row[2] else 0,
                    'escalating_count': row[3] or 0
                })

            return {
                'markers': markers,
                'trends': trends
            }

        finally:
            cursor.close()
            conn.close()

    def get_unprocessed_articles(self, limit: int = 100, topic: str = None,
                                  process_all: bool = False) -> List[Dict[str, Any]]:
        """Get articles for geopolitical processing.

        Args:
            limit: Max articles to return
            topic: Topic to filter by (default: "Geopolitical Hotspots")
            process_all: If True, include already-processed articles
        """
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        # Use default topic if not specified
        topic = topic or DEFAULT_GEOPOLITICAL_TOPIC

        try:
            if process_all:
                # Include all articles, even already processed
                cursor.execute("""
                    SELECT a.uri, a.title, a.summary, a.category, a.sentiment,
                           a.news_source, a.publication_date
                    FROM articles a
                    WHERE a.topic = ?
                    AND a.category IS NOT NULL
                    AND a.sentiment IS NOT NULL
                    ORDER BY a.publication_date DESC
                    LIMIT ?
                """, [topic, limit])
            else:
                # Only unprocessed articles (current behavior)
                cursor.execute("""
                    SELECT a.uri, a.title, a.summary, a.category, a.sentiment,
                           a.news_source, a.publication_date
                    FROM articles a
                    LEFT JOIN hotspot_articles ha ON a.uri = ha.article_uri
                    WHERE a.topic = ?
                    AND a.category IS NOT NULL
                    AND a.sentiment IS NOT NULL
                    AND ha.article_uri IS NULL
                    ORDER BY a.publication_date DESC
                    LIMIT ?
                """, [topic, limit])

            return [
                {
                    'uri': row[0],
                    'title': row[1],
                    'summary': row[2],
                    'category': row[3],
                    'sentiment': row[4],
                    'news_source': row[5],
                    'publication_date': row[6]
                }
                for row in cursor.fetchall()
            ]

        finally:
            cursor.close()
            conn.close()

    def get_processing_stats(self, topic: str = None) -> Dict[str, Any]:
        """Get statistics about article processing progress.

        Args:
            topic: Topic to filter by (default: "Geopolitical Hotspots")
        """
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        # Use default topic if not specified
        topic = topic or DEFAULT_GEOPOLITICAL_TOPIC

        try:
            # Total curated articles for the specified topic
            cursor.execute("""
                SELECT COUNT(*) FROM articles
                WHERE topic = ? AND category IS NOT NULL AND sentiment IS NOT NULL
            """, [topic])
            total_curated = cursor.fetchone()[0]

            # Already processed articles for this topic
            # Join with articles to filter by topic
            cursor.execute("""
                SELECT COUNT(DISTINCT ha.article_uri)
                FROM hotspot_articles ha
                JOIN articles a ON ha.article_uri = a.uri
                WHERE a.topic = ?
            """, [topic])
            processed = cursor.fetchone()[0]

            # Total hotspots (for the specified topic)
            cursor.execute("""
                SELECT COUNT(*) FROM geopolitical_hotspots WHERE topic = ?
            """, [topic])
            total_hotspots = cursor.fetchone()[0]

            # Log the stats for debugging
            logger.debug(f"Processing stats for topic '{topic}': total_curated={total_curated}, processed={processed}, hotspots={total_hotspots}")

            return {
                'total_curated_articles': total_curated,
                'processed_articles': processed,
                'unprocessed_articles': max(0, total_curated - processed),
                'total_hotspots': total_hotspots,
                'processing_percentage': round((processed / total_curated * 100) if total_curated > 0 else 0, 1),
                'topic': topic
            }

        finally:
            cursor.close()
            conn.close()

    def get_available_topics(self) -> List[Dict[str, Any]]:
        """Get list of ALL topics with article counts for processing."""
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT a.topic,
                       COUNT(*) as total_articles,
                       COUNT(*) - COUNT(ha.article_uri) as unprocessed_count
                FROM articles a
                LEFT JOIN hotspot_articles ha ON a.uri = ha.article_uri
                WHERE a.topic IS NOT NULL
                AND a.category IS NOT NULL
                AND a.sentiment IS NOT NULL
                GROUP BY a.topic
                HAVING COUNT(*) > 0
                ORDER BY unprocessed_count DESC, total_articles DESC
            """)

            return [
                {
                    'topic': row[0],
                    'total_articles': row[1],
                    'unprocessed_count': row[2]
                }
                for row in cursor.fetchall()
            ]

        finally:
            cursor.close()
            conn.close()

    def create_or_update_hotspot(self, location_data: Dict[str, Any], topic: str = None) -> int:
        """Create a new hotspot or update existing one, returns hotspot_id.

        Args:
            location_data: Location information extracted from article
            topic: Topic to associate with the hotspot (default: "Geopolitical Hotspots")
        """
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        # Use default topic if not specified
        topic = topic or DEFAULT_GEOPOLITICAL_TOPIC

        try:
            # Check if hotspot exists at this location
            cursor.execute("""
                SELECT id, article_count, intensity_score
                FROM geopolitical_hotspots
                WHERE location_name = ? AND country_code = ?
            """, [location_data['location_name'], location_data.get('country_code')])

            existing = cursor.fetchone()

            if existing:
                # Update existing hotspot
                hotspot_id = existing[0]
                new_count = existing[1] + 1
                # Recalculate intensity based on article count and risk
                risk_scores = {'critical': 90, 'high': 70, 'medium': 50, 'low': 30, 'info': 10}
                risk_score = risk_scores.get(location_data.get('risk_assessment', 'medium'), 50)
                new_intensity = min(100, (existing[2] + risk_score) / 2 + (new_count * 2))

                cursor.execute("""
                    UPDATE geopolitical_hotspots
                    SET article_count = ?,
                        recent_article_count = recent_article_count + 1,
                        intensity_score = ?,
                        risk_level = ?,
                        last_article_date = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, [new_count, new_intensity, location_data.get('risk_assessment', 'medium'), hotspot_id])
            else:
                # Create new hotspot
                risk_scores = {'critical': 90, 'high': 70, 'medium': 50, 'low': 30, 'info': 10}
                intensity = risk_scores.get(location_data.get('risk_assessment', 'medium'), 50)

                cursor.execute("""
                    INSERT INTO geopolitical_hotspots
                    (location_name, location_type, country_code, country_name,
                     latitude, longitude, intensity_score, risk_level, trend,
                     article_count, recent_article_count, primary_category, tags,
                     topic, last_article_date, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'stable', 1, 1, ?, ?, ?,
                            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    RETURNING id
                """, [
                    location_data['location_name'],
                    location_data.get('location_type', 'city'),
                    location_data.get('country_code'),
                    location_data.get('country_name'),
                    location_data.get('latitude', 0),
                    location_data.get('longitude', 0),
                    intensity,
                    location_data.get('risk_assessment', 'medium'),
                    location_data.get('threat_category'),
                    json.dumps(location_data.get('tags', [])),
                    topic
                ])
                hotspot_id = cursor.fetchone()[0]

            conn.commit()
            return hotspot_id

        finally:
            cursor.close()
            conn.close()

    def link_article_to_hotspot(self, hotspot_id: int, article_uri: str,
                                 relevance_score: float = 1.0, mention_type: str = 'primary'):
        """Link an article to a hotspot.

        Uses UPSERT to update existing links when reprocessing articles.
        """
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO hotspot_articles (hotspot_id, article_uri, relevance_score, mention_type, extracted_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT (hotspot_id, article_uri)
                DO UPDATE SET relevance_score = EXCLUDED.relevance_score,
                              mention_type = EXCLUDED.mention_type,
                              extracted_at = CURRENT_TIMESTAMP
            """, [hotspot_id, article_uri, relevance_score, mention_type])
            conn.commit()

        finally:
            cursor.close()
            conn.close()

    def backfill_article_links(self) -> Dict[str, Any]:
        """
        Backfill hotspot_articles by matching location names in article text.
        This is useful when hotspots exist but links weren't created.
        """
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        try:
            # Get all hotspots
            cursor.execute("""
                SELECT id, location_name, country_name
                FROM geopolitical_hotspots
            """)
            hotspots = cursor.fetchall()

            stats = {
                'hotspots_processed': 0,
                'links_created': 0,
                'hotspots_with_matches': 0,
                'errors': 0
            }

            for hotspot in hotspots:
                hotspot_id = hotspot[0]
                location_name = hotspot[1]
                country_name = hotspot[2]

                try:
                    # Build search patterns - try location name and country
                    search_patterns = [location_name]
                    if country_name and country_name != location_name:
                        search_patterns.append(country_name)

                    # Find articles mentioning this location
                    # Use ILIKE for case-insensitive search (PostgreSQL)
                    placeholders = []
                    params = []
                    for pattern in search_patterns:
                        placeholders.append("(LOWER(a.title) LIKE ? OR LOWER(a.summary) LIKE ?)")
                        search_term = f"%{pattern.lower()}%"
                        params.extend([search_term, search_term])

                    where_clause = " OR ".join(placeholders)

                    cursor.execute(f"""
                        SELECT a.uri
                        FROM articles a
                        LEFT JOIN hotspot_articles ha ON a.uri = ha.article_uri AND ha.hotspot_id = ?
                        WHERE a.topic = ?
                        AND a.category IS NOT NULL
                        AND a.sentiment IS NOT NULL
                        AND ha.article_uri IS NULL
                        AND ({where_clause})
                    """, [hotspot_id, DEFAULT_GEOPOLITICAL_TOPIC] + params)

                    matching_articles = cursor.fetchall()

                    if matching_articles:
                        stats['hotspots_with_matches'] += 1

                        # Insert links
                        for (article_uri,) in matching_articles:
                            cursor.execute("""
                                INSERT INTO hotspot_articles (hotspot_id, article_uri, relevance_score, mention_type, extracted_at)
                                VALUES (?, ?, 0.8, 'backfill', CURRENT_TIMESTAMP)
                                ON CONFLICT (hotspot_id, article_uri) DO NOTHING
                            """, [hotspot_id, article_uri])
                            stats['links_created'] += 1

                        # Update article_count on hotspot
                        cursor.execute("""
                            UPDATE geopolitical_hotspots
                            SET article_count = (
                                SELECT COUNT(*) FROM hotspot_articles WHERE hotspot_id = ?
                            ),
                            updated_at = CURRENT_TIMESTAMP
                            WHERE id = ?
                        """, [hotspot_id, hotspot_id])

                    stats['hotspots_processed'] += 1

                except Exception as e:
                    logger.warning(f"Error processing hotspot {hotspot_id} ({location_name}): {e}")
                    stats['errors'] += 1
                    # Rollback the failed transaction so we can continue
                    conn.rollback()

            conn.commit()

            # Also update recent_article_count based on last 7 days
            # publication_date is stored as TEXT, so cast it
            cursor.execute("""
                UPDATE geopolitical_hotspots gh
                SET recent_article_count = (
                    SELECT COUNT(*)
                    FROM hotspot_articles ha
                    JOIN articles a ON ha.article_uri = a.uri
                    WHERE ha.hotspot_id = gh.id
                    AND a.publication_date::timestamp >= CURRENT_DATE - INTERVAL '7 days'
                )
            """)
            conn.commit()

            logger.info(f"Backfill complete: {stats}")
            return stats

        finally:
            cursor.close()
            conn.close()

    def update_country_stats(self):
        """Recalculate country-level statistics."""
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        try:
            # Clear existing stats
            cursor.execute("DELETE FROM country_hotspot_stats")

            # Recalculate from hotspots
            cursor.execute("""
                INSERT INTO country_hotspot_stats
                (country_code, country_name, total_hotspots, total_articles, heat_value,
                 max_risk_level, primary_category, topic, updated_at)
                SELECT
                    country_code,
                    country_name,
                    COUNT(*) as total_hotspots,
                    SUM(article_count) as total_articles,
                    AVG(intensity_score) as heat_value,
                    (SELECT risk_level FROM geopolitical_hotspots gh2
                     WHERE gh2.country_code = gh.country_code
                     ORDER BY intensity_score DESC LIMIT 1) as max_risk_level,
                    (SELECT primary_category FROM geopolitical_hotspots gh2
                     WHERE gh2.country_code = gh.country_code
                     GROUP BY primary_category ORDER BY COUNT(*) DESC LIMIT 1) as primary_category,
                    topic,
                    CURRENT_TIMESTAMP
                FROM geopolitical_hotspots gh
                WHERE country_code IS NOT NULL
                GROUP BY country_code, country_name, topic
            """)
            conn.commit()

        finally:
            cursor.close()
            conn.close()

    def get_latest_narrative(self, topic: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get the most recent narrative."""
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        try:
            where_clause = ""
            params = []
            if topic:
                where_clause = "WHERE topic = ?"
                params.append(topic)

            cursor.execute(f"""
                SELECT id, narrative_text, executive_summary, regional_analysis,
                       emerging_threats, outlook, hotspot_count, article_count,
                       top_regions, top_categories, risk_breakdown, model_used,
                       topic, generated_at
                FROM geopolitical_narratives
                {where_clause}
                ORDER BY generated_at DESC
                LIMIT 1
            """, params if params else None)

            row = cursor.fetchone()
            if not row:
                return None

            return {
                'id': row[0],
                'narrative_text': row[1],
                'executive_summary': row[2],
                'regional_analysis': row[3],
                'emerging_threats': row[4],
                'outlook': row[5],
                'hotspot_count': row[6],
                'article_count': row[7],
                'top_regions': row[8],
                'top_categories': row[9],
                'risk_breakdown': row[10],
                'model_used': row[11],
                'topic': row[12],
                'generated_at': row[13].isoformat() if row[13] else None
            }

        finally:
            cursor.close()
            conn.close()

    def get_narratives_history(self, topic: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """Get narrative history."""
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        try:
            where_clause = ""
            params = []
            if topic:
                where_clause = "WHERE topic = ?"
                params.append(topic)

            cursor.execute(f"""
                SELECT id, executive_summary, hotspot_count, article_count,
                       model_used, topic, generated_at
                FROM geopolitical_narratives
                {where_clause}
                ORDER BY generated_at DESC
                LIMIT ?
            """, (params + [limit]) if params else [limit])

            return [
                {
                    'id': row[0],
                    'executive_summary': row[1],
                    'hotspot_count': row[2],
                    'article_count': row[3],
                    'model_used': row[4],
                    'topic': row[5],
                    'generated_at': row[6].isoformat() if row[6] else None
                }
                for row in cursor.fetchall()
            ]

        finally:
            cursor.close()
            conn.close()

    def save_narrative(self, narrative_data: Dict[str, Any]) -> int:
        """Save a generated narrative to the database."""
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO geopolitical_narratives
                (narrative_text, executive_summary, regional_analysis, emerging_threats,
                 outlook, hotspot_count, article_count, top_regions, top_categories,
                 risk_breakdown, model_used, topic, generated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                RETURNING id
            """, [
                narrative_data.get('narrative_text', ''),
                narrative_data.get('executive_summary'),
                narrative_data.get('regional_analysis'),
                narrative_data.get('emerging_threats'),
                narrative_data.get('outlook'),
                narrative_data.get('hotspot_count', 0),
                narrative_data.get('article_count', 0),
                json.dumps(narrative_data.get('top_regions', [])),
                json.dumps(narrative_data.get('top_categories', [])),
                json.dumps(narrative_data.get('risk_breakdown', {})),
                narrative_data.get('model_used'),
                narrative_data.get('topic')
            ])

            narrative_id = cursor.fetchone()[0]
            conn.commit()
            return narrative_id

        finally:
            cursor.close()
            conn.close()


async def extract_location_with_llm(title: str, summary: str, category: str, model_name: str = "gpt-4o-mini") -> Dict[str, Any]:
    """Use LLM to extract location information from an article."""
    from app.ai_models import LiteLLMModel

    try:
        prompt = LOCATION_EXTRACTION_PROMPT.format(
            title=title,
            summary=summary or "No summary available",
            category=category or "Unknown"
        )

        model = LiteLLMModel.get_instance(model_name)
        response = model.generate_response([
            {"role": "system", "content": "You are a geopolitical analyst. Respond only with valid JSON."},
            {"role": "user", "content": prompt}
        ])

        # Parse JSON response
        response_text = response.strip()
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
        response_text = response_text.strip()

        result = json.loads(response_text)
        return result

    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse LLM response as JSON: {e}")
        return {"no_location": True, "error": "JSON parse error"}
    except Exception as e:
        logger.error(f"LLM location extraction failed: {e}")
        return {"no_location": True, "error": str(e)}


async def generate_narrative_with_llm(stats: Dict[str, Any], model_name: str = "gpt-4o-mini") -> Dict[str, Any]:
    """Use LLM to generate a strategic intelligence narrative."""
    from app.ai_models import LiteLLMModel

    try:
        # Format top categories
        top_categories = ', '.join([
            f"{cat}: {count}" for cat, count in list(stats.get('by_category', {}).items())[:5]
        ]) or "None identified"

        # Format top regions (from top hotspots)
        top_hotspots = stats.get('top_hotspots', [])
        countries = list(set(h.get('country_name') for h in top_hotspots if h.get('country_name')))
        top_regions = ', '.join(countries[:5]) or "None identified"

        # Format top hotspots list
        hotspots_text = '\n'.join([
            f"- {h['location_name']} ({h.get('country_name', 'Unknown')}): "
            f"{h['risk_level'].upper()} risk, {h['article_count']} articles, {h.get('trend', 'stable')}"
            for h in top_hotspots[:10]
        ]) or "No hotspots identified"

        prompt = NARRATIVE_GENERATION_PROMPT.format(
            total_hotspots=stats.get('total_hotspots', 0),
            countries_affected=stats.get('countries_affected', 0),
            critical_count=stats.get('by_risk_level', {}).get('critical', 0),
            high_count=stats.get('by_risk_level', {}).get('high', 0),
            medium_count=stats.get('by_risk_level', {}).get('medium', 0),
            low_count=stats.get('by_risk_level', {}).get('low', 0),
            escalating_count=stats.get('escalating_count', 0),
            de_escalating_count=stats.get('de_escalating_count', 0),
            top_categories=top_categories,
            top_regions=top_regions,
            recent_articles=stats.get('recent_articles', 0),
            top_hotspots=hotspots_text
        )

        model = LiteLLMModel.get_instance(model_name)
        response = model.generate_response([
            {"role": "system", "content": "You are a senior geopolitical intelligence analyst providing strategic briefings."},
            {"role": "user", "content": prompt}
        ])

        # Parse the sections from the response
        narrative_text = response.strip()

        # Try to extract sections
        sections = {
            'narrative_text': narrative_text,
            'executive_summary': None,
            'regional_analysis': None,
            'emerging_threats': None,
            'outlook': None
        }

        # Simple section extraction
        if '## Executive Summary' in narrative_text:
            parts = narrative_text.split('## Executive Summary')
            if len(parts) > 1:
                exec_part = parts[1]
                next_section = exec_part.find('##')
                if next_section > 0:
                    sections['executive_summary'] = exec_part[:next_section].strip()
                else:
                    sections['executive_summary'] = exec_part.strip()

        if '## Regional Analysis' in narrative_text:
            parts = narrative_text.split('## Regional Analysis')
            if len(parts) > 1:
                reg_part = parts[1]
                next_section = reg_part.find('##')
                if next_section > 0:
                    sections['regional_analysis'] = reg_part[:next_section].strip()
                else:
                    sections['regional_analysis'] = reg_part.strip()

        if '## Emerging Threats' in narrative_text:
            parts = narrative_text.split('## Emerging Threats')
            if len(parts) > 1:
                threat_part = parts[1]
                next_section = threat_part.find('##')
                if next_section > 0:
                    sections['emerging_threats'] = threat_part[:next_section].strip()
                else:
                    sections['emerging_threats'] = threat_part.strip()

        if '## Strategic Outlook' in narrative_text or '## Outlook' in narrative_text:
            for section_name in ['## Strategic Outlook', '## Outlook']:
                if section_name in narrative_text:
                    parts = narrative_text.split(section_name)
                    if len(parts) > 1:
                        outlook_part = parts[1]
                        next_section = outlook_part.find('##')
                        if next_section > 0:
                            sections['outlook'] = outlook_part[:next_section].strip()
                        else:
                            sections['outlook'] = outlook_part.strip()
                    break

        return sections

    except Exception as e:
        logger.error(f"LLM narrative generation failed: {e}")
        return {"error": str(e)}


# Singleton instance
_service = None

def get_geopolitical_service() -> GeopoliticalService:
    """Get or create the geopolitical service singleton."""
    global _service
    if _service is None:
        _service = GeopoliticalService()
    return _service
