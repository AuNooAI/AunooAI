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
        """Get dashboard overview statistics."""
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        try:
            # Build WHERE clause for topic filter
            where_clause = ""
            params = []
            if topic:
                where_clause = "WHERE topic = ?"
                params.append(topic)

            # Get total hotspots and risk breakdown
            cursor.execute(f"""
                SELECT
                    COUNT(*) as total_hotspots,
                    COUNT(CASE WHEN risk_level = 'critical' THEN 1 END) as critical_count,
                    COUNT(CASE WHEN risk_level = 'high' THEN 1 END) as high_count,
                    COUNT(CASE WHEN risk_level = 'medium' THEN 1 END) as medium_count,
                    COUNT(CASE WHEN risk_level = 'low' THEN 1 END) as low_count,
                    COUNT(CASE WHEN risk_level = 'info' THEN 1 END) as info_count,
                    COALESCE(SUM(article_count), 0) as total_articles,
                    COALESCE(SUM(recent_article_count), 0) as recent_articles,
                    COUNT(DISTINCT country_code) as countries_affected,
                    COUNT(CASE WHEN trend = 'escalating' THEN 1 END) as escalating_count,
                    COUNT(CASE WHEN trend = 'de-escalating' THEN 1 END) as de_escalating_count
                FROM geopolitical_hotspots
                {where_clause}
            """, params if params else None)

            row = cursor.fetchone()
            stats = {
                'total_hotspots': row[0] if row else 0,
                'by_risk_level': {
                    'critical': row[1] if row else 0,
                    'high': row[2] if row else 0,
                    'medium': row[3] if row else 0,
                    'low': row[4] if row else 0,
                    'info': row[5] if row else 0,
                },
                'total_articles': row[6] if row else 0,
                'recent_articles': row[7] if row else 0,
                'countries_affected': row[8] if row else 0,
                'escalating_count': row[9] if row else 0,
                'de_escalating_count': row[10] if row else 0,
            }

            # Get category distribution
            cursor.execute(f"""
                SELECT primary_category, COUNT(*) as count
                FROM geopolitical_hotspots
                {where_clause}
                GROUP BY primary_category
                ORDER BY count DESC
            """, params if params else None)

            stats['by_category'] = {row[0]: row[1] for row in cursor.fetchall() if row[0]}

            # Get top hotspots
            cursor.execute(f"""
                SELECT id, location_name, country_name, intensity_score, risk_level,
                       primary_category, article_count, trend
                FROM geopolitical_hotspots
                {where_clause}
                ORDER BY intensity_score DESC
                LIMIT 5
            """, params if params else None)

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
        """Get all hotspots with coordinates for map display."""
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        try:
            where_clauses = []
            params = []

            if topic:
                where_clauses.append("topic = ?")
                params.append(topic)

            if categories:
                placeholders = ', '.join(['?' for _ in categories])
                where_clauses.append(f"primary_category IN ({placeholders})")
                params.extend(categories)

            if risk_levels:
                placeholders = ', '.join(['?' for _ in risk_levels])
                where_clauses.append(f"risk_level IN ({placeholders})")
                params.extend(risk_levels)

            where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

            cursor.execute(f"""
                SELECT id, location_name, location_type, country_code, country_name,
                       latitude, longitude, intensity_score, risk_level, trend,
                       article_count, recent_article_count, primary_category, tags,
                       last_article_date
                FROM geopolitical_hotspots
                {where_sql}
                ORDER BY intensity_score DESC
            """, params if params else None)

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
                     page: int = 1, page_size: int = 20,
                     sort_by: str = 'intensity',
                     sort_order: str = 'desc') -> Tuple[List[Dict[str, Any]], int]:
        """Get paginated list of hotspots with filters."""
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        try:
            where_clauses = []
            params = []

            if topic:
                where_clauses.append("topic = ?")
                params.append(topic)

            if categories:
                placeholders = ', '.join(['?' for _ in categories])
                where_clauses.append(f"primary_category IN ({placeholders})")
                params.extend(categories)

            if risk_levels:
                placeholders = ', '.join(['?' for _ in risk_levels])
                where_clauses.append(f"risk_level IN ({placeholders})")
                params.extend(risk_levels)

            if country_code:
                where_clauses.append("country_code = ?")
                params.append(country_code)

            where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

            # Sort mapping
            sort_columns = {
                'intensity': 'intensity_score',
                'articles': 'article_count',
                'recent': 'recent_article_count',
                'name': 'location_name',
                'updated': 'updated_at'
            }
            sort_col = sort_columns.get(sort_by, 'intensity_score')
            order = 'DESC' if sort_order.lower() == 'desc' else 'ASC'

            # Get total count
            cursor.execute(f"SELECT COUNT(*) FROM geopolitical_hotspots {where_sql}", params if params else None)
            total = cursor.fetchone()[0]

            # Get paginated results
            offset = (page - 1) * page_size
            cursor.execute(f"""
                SELECT id, location_name, location_type, country_code, country_name,
                       latitude, longitude, intensity_score, risk_level, trend,
                       article_count, recent_article_count, primary_category, tags,
                       last_article_date, created_at, updated_at
                FROM geopolitical_hotspots
                {where_sql}
                ORDER BY {sort_col} {order}
                LIMIT ? OFFSET ?
            """, (params + [page_size, offset]) if params else [page_size, offset])

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
        """Get temporal trend data for hotspots."""
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        try:
            start_date = datetime.now() - timedelta(days=days_back)

            where_clause = "WHERE hds.date >= ?"
            params = [start_date]

            if topic:
                where_clause += " AND gh.topic = ?"
                params.append(topic)

            cursor.execute(f"""
                SELECT hds.date,
                       SUM(hds.article_count) as article_count,
                       AVG(hds.intensity_score) as avg_intensity,
                       COUNT(DISTINCT hds.hotspot_id) as hotspot_count
                FROM hotspot_daily_stats hds
                JOIN geopolitical_hotspots gh ON hds.hotspot_id = gh.id
                {where_clause}
                GROUP BY hds.date
                ORDER BY hds.date
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
                        country_code,
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
                    SUM((SELECT article_count FROM geopolitical_hotspots WHERE country_code = rm.country_code LIMIT 1)) as article_count
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

    def get_unprocessed_articles(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get curated articles that haven't been processed for hotspots yet."""
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        try:
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
            """, [DEFAULT_GEOPOLITICAL_TOPIC, limit])

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

    def get_processing_stats(self) -> Dict[str, Any]:
        """Get statistics about article processing progress."""
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        try:
            # Total curated articles
            cursor.execute("""
                SELECT COUNT(*) FROM articles
                WHERE topic = ? AND category IS NOT NULL AND sentiment IS NOT NULL
            """, [DEFAULT_GEOPOLITICAL_TOPIC])
            total_curated = cursor.fetchone()[0]

            # Already processed (linked to hotspots)
            cursor.execute("""
                SELECT COUNT(DISTINCT ha.article_uri)
                FROM hotspot_articles ha
                JOIN articles a ON ha.article_uri = a.uri
                WHERE a.topic = ?
            """, [DEFAULT_GEOPOLITICAL_TOPIC])
            processed = cursor.fetchone()[0]

            # Total hotspots
            cursor.execute("SELECT COUNT(*) FROM geopolitical_hotspots")
            total_hotspots = cursor.fetchone()[0]

            return {
                'total_curated_articles': total_curated,
                'processed_articles': processed,
                'unprocessed_articles': total_curated - processed,
                'total_hotspots': total_hotspots,
                'processing_percentage': round((processed / total_curated * 100) if total_curated > 0 else 0, 1)
            }

        finally:
            cursor.close()
            conn.close()

    def create_or_update_hotspot(self, location_data: Dict[str, Any]) -> int:
        """Create a new hotspot or update existing one, returns hotspot_id."""
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

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
                    DEFAULT_GEOPOLITICAL_TOPIC
                ])
                hotspot_id = cursor.fetchone()[0]

            conn.commit()
            return hotspot_id

        finally:
            cursor.close()
            conn.close()

    def link_article_to_hotspot(self, hotspot_id: int, article_uri: str,
                                 relevance_score: float = 1.0, mention_type: str = 'primary'):
        """Link an article to a hotspot."""
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO hotspot_articles (hotspot_id, article_uri, relevance_score, mention_type, linked_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT (hotspot_id, article_uri) DO NOTHING
            """, [hotspot_id, article_uri, relevance_score, mention_type])
            conn.commit()

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
