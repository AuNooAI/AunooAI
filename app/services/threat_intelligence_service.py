"""Threat Intelligence Service

Service layer for managing threat intelligence analysis,
extracting threats from articles, tracking threat actors, and managing IOCs.
"""

import logging
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy import text
from app.database import get_database_instance

logger = logging.getLogger(__name__)

# Default topic for threat intelligence
DEFAULT_THREAT_INTEL_TOPIC = "Threat Intelligence"

# LLM prompt for generating threat intelligence narrative
NARRATIVE_GENERATION_PROMPT = """You are a senior cybersecurity threat intelligence analyst. Analyze the following data about current cyber threats and generate a strategic threat intelligence briefing.

Data Summary:
- Total Active Threats: {total_threats}
- Threat Actors Tracked: {total_actors}
- Severity Breakdown:
  - Critical: {critical_count}
  - High: {high_count}
  - Medium: {medium_count}
  - Low: {low_count}
- Escalating Threats: {escalating_count}
- New Threats (7 days): {new_threats}
- Top Threat Types: {top_types}
- Top Targeted Industries: {top_industries}
- Recent Articles (7 days): {recent_articles}

Top Threats:
{top_threats}

Active Threat Actors:
{active_actors}

Generate a comprehensive threat intelligence briefing with the following sections:

## Executive Summary
A 2-3 sentence overview of the current cyber threat landscape.

## Threat Landscape Analysis
Analysis of the most significant threats and their implications for organizations.

## Emerging Threats
Identification of new or escalating threats that require immediate attention.

## Defensive Recommendations
Specific, actionable recommendations for defending against the identified threats.

Write in a professional, analytical tone appropriate for security operations teams and CISOs. Be specific and actionable. Total length should be 500-700 words.
"""

# LLM prompt for extracting threat data from articles
THREAT_EXTRACTION_PROMPT = """Analyze this cybersecurity news article and extract threat intelligence information.

Title: {title}
Summary: {summary}
Category: {category}

Extract threat intelligence data from this article. Focus on:
1. The specific threat (malware, vulnerability, attack campaign, etc.)
2. Attribution to any known threat actors or countries
3. Target information (industries, countries, organizations)
4. Technical indicators (CVEs, MITRE ATT&CK techniques, IOCs)

Respond with JSON only:
{{
    "threat_name": "Name of the threat (e.g., 'LockBit 3.0', 'CVE-2024-XXXX', 'Volt Typhoon Campaign')",
    "threat_type": "malware|ransomware|apt|phishing|vulnerability|data_breach|botnet|ddos|supply_chain|credential_theft|cryptojacking|insider_threat|iot_ot|mobile",
    "threat_subtype": "More specific classification (optional)",
    "severity_level": "critical|high|medium|low|info",
    "description": "Brief description of the threat",

    "threat_actor_name": "Name of attributed threat actor (e.g., 'APT29', 'LockBit Gang') or null",
    "actor_type": "nation_state|cybercrime|hacktivist|insider|script_kiddie|unknown",
    "attributed_country": "ISO 2-letter code of attributing country or null",
    "attributed_country_name": "Full country name or null",

    "target_countries": ["ISO 2-letter codes of targeted countries"],
    "target_industries": ["technology", "healthcare", "finance", "government", "energy", "manufacturing", "education", "retail", "telecommunications", "transportation"],
    "target_latitude": latitude as float or null (primary target location),
    "target_longitude": longitude as float or null,

    "cve_ids": ["CVE-XXXX-XXXXX format"],
    "mitre_techniques": ["TXXXX format MITRE ATT&CK technique IDs"],
    "malware_families": ["Names of malware families"],

    "iocs": [
        {{"type": "ip|domain|hash_md5|hash_sha256|url|email", "value": "indicator value"}}
    ],

    "tags": ["relevant tags"]
}}

If no threat intelligence can be extracted, respond with: {{"no_threat": true}}
"""

# Threat categories for threat intelligence
THREAT_CATEGORIES = [
    'malware', 'ransomware', 'apt', 'phishing', 'vulnerability',
    'data_breach', 'botnet', 'ddos', 'supply_chain', 'credential_theft',
    'cryptojacking', 'insider_threat', 'iot_ot', 'mobile'
]

# Severity levels with score ranges
SEVERITY_LEVELS = ['critical', 'high', 'medium', 'low', 'info']

SEVERITY_SCORE_RANGES = {
    'critical': (80, 100),
    'high': (60, 79),
    'medium': (40, 59),
    'low': (20, 39),
    'info': (0, 19)
}

SEVERITY_COLORS = {
    'critical': '#DC2626',  # Red
    'high': '#F97316',      # Orange
    'medium': '#EAB308',    # Yellow
    'low': '#22C55E',       # Green
    'info': '#3B82F6'       # Blue
}

# Threat actor types
ACTOR_TYPES = [
    'nation_state', 'cybercrime', 'hacktivist', 'insider', 'script_kiddie', 'unknown'
]

# Target industries
TARGET_INDUSTRIES = [
    'technology', 'healthcare', 'finance', 'government', 'energy',
    'manufacturing', 'education', 'retail', 'telecommunications', 'transportation',
    'critical_infrastructure', 'defense', 'media', 'legal', 'hospitality'
]


def get_severity_level(score: float) -> str:
    """Convert severity score to level."""
    for level, (low, high) in SEVERITY_SCORE_RANGES.items():
        if low <= score <= high:
            return level
    return 'medium'


def get_severity_score(level: str) -> int:
    """Get middle of severity score range for a level."""
    ranges = SEVERITY_SCORE_RANGES.get(level, (40, 59))
    return (ranges[0] + ranges[1]) // 2


class ThreatIntelligenceService:
    """Service for managing threat intelligence."""

    def __init__(self):
        pass

    def get_overview_stats(self, topic: Optional[str] = None, days_back: int = 30) -> Dict[str, Any]:
        """Get dashboard overview statistics."""
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        try:
            topic_filter = ""
            topic_params = []
            if topic:
                topic_filter = "AND t.topic = ?"
                topic_params.append(topic)

            # Date filter for recent articles
            date_filter = f"""
                AND (
                    a.publication_date::timestamp >= CURRENT_DATE - ? * INTERVAL '1 day'
                    OR a.publication_date::date >= CURRENT_DATE - ? * INTERVAL '1 day'
                )
            """

            # Get threat IDs that have articles in the date range
            params = [days_back, days_back] + topic_params
            cursor.execute(f"""
                WITH filtered_threats AS (
                    SELECT DISTINCT t.id
                    FROM threat_intel_threats t
                    JOIN threat_articles ta ON t.id = ta.threat_id
                    JOIN articles a ON ta.article_uri = a.uri
                    WHERE 1=1 {date_filter} {topic_filter}
                )
                SELECT
                    COUNT(*) as total_threats,
                    COUNT(CASE WHEN t.severity_level = 'critical' THEN 1 END) as critical_count,
                    COUNT(CASE WHEN t.severity_level = 'high' THEN 1 END) as high_count,
                    COUNT(CASE WHEN t.severity_level = 'medium' THEN 1 END) as medium_count,
                    COUNT(CASE WHEN t.severity_level = 'low' THEN 1 END) as low_count,
                    COUNT(CASE WHEN t.severity_level = 'info' THEN 1 END) as info_count,
                    COUNT(CASE WHEN t.trend = 'escalating' THEN 1 END) as escalating_count,
                    COUNT(CASE WHEN t.trend = 'declining' THEN 1 END) as declining_count
                FROM threat_intel_threats t
                WHERE t.id IN (SELECT id FROM filtered_threats)
            """, params)

            row = cursor.fetchone()

            # Get article counts
            article_params = [days_back, days_back] + topic_params
            cursor.execute(f"""
                SELECT
                    COUNT(DISTINCT ta.article_uri) as total_articles,
                    COUNT(DISTINCT CASE
                        WHEN a.publication_date::timestamp >= CURRENT_DATE - 7 * INTERVAL '1 day'
                        OR a.publication_date::date >= CURRENT_DATE - 7 * INTERVAL '1 day'
                        THEN ta.article_uri
                    END) as recent_articles
                FROM threat_articles ta
                JOIN threat_intel_threats t ON ta.threat_id = t.id
                JOIN articles a ON ta.article_uri = a.uri
                WHERE (
                    a.publication_date::timestamp >= CURRENT_DATE - ? * INTERVAL '1 day'
                    OR a.publication_date::date >= CURRENT_DATE - ? * INTERVAL '1 day'
                ) {topic_filter}
            """, article_params[:2] + topic_params)

            article_row = cursor.fetchone()

            # Get threat actor count
            cursor.execute("SELECT COUNT(*) FROM threat_intel_actors")
            actor_count = cursor.fetchone()[0]

            # Get new threats in last 7 days
            cursor.execute(f"""
                SELECT COUNT(*) FROM threat_intel_threats t
                WHERE t.created_at >= CURRENT_DATE - 7 * INTERVAL '1 day'
                {topic_filter}
            """, topic_params if topic_params else None)
            new_threats = cursor.fetchone()[0]

            stats = {
                'total_threats': row[0] if row else 0,
                'by_severity': {
                    'critical': row[1] if row else 0,
                    'high': row[2] if row else 0,
                    'medium': row[3] if row else 0,
                    'low': row[4] if row else 0,
                    'info': row[5] if row else 0,
                },
                'total_articles': article_row[0] if article_row else 0,
                'recent_articles': article_row[1] if article_row else 0,
                'total_actors': actor_count,
                'escalating_count': row[6] if row else 0,
                'declining_count': row[7] if row else 0,
                'new_threats': new_threats,
            }

            # Get threat type distribution
            cursor.execute(f"""
                WITH filtered_threats AS (
                    SELECT DISTINCT t.id
                    FROM threat_intel_threats t
                    JOIN threat_articles ta ON t.id = ta.threat_id
                    JOIN articles a ON ta.article_uri = a.uri
                    WHERE 1=1 {date_filter} {topic_filter}
                )
                SELECT t.threat_type, COUNT(*) as count
                FROM threat_intel_threats t
                WHERE t.id IN (SELECT id FROM filtered_threats)
                GROUP BY t.threat_type
                ORDER BY count DESC
            """, params)

            stats['by_type'] = {row[0]: row[1] for row in cursor.fetchall() if row[0]}

            # Get top threats
            cursor.execute(f"""
                WITH filtered_threats AS (
                    SELECT t.id, COUNT(DISTINCT ta.article_uri) as filtered_count
                    FROM threat_intel_threats t
                    JOIN threat_articles ta ON t.id = ta.threat_id
                    JOIN articles a ON ta.article_uri = a.uri
                    WHERE 1=1 {date_filter} {topic_filter}
                    GROUP BY t.id
                )
                SELECT t.id, t.threat_name, t.threat_type, t.severity_level, t.severity_score,
                       t.threat_actor_name, ft.filtered_count as article_count, t.trend
                FROM threat_intel_threats t
                JOIN filtered_threats ft ON t.id = ft.id
                ORDER BY t.severity_score DESC, ft.filtered_count DESC
                LIMIT 5
            """, params)

            stats['top_threats'] = [
                {
                    'id': row[0],
                    'threat_name': row[1],
                    'threat_type': row[2],
                    'severity_level': row[3],
                    'severity_score': row[4],
                    'threat_actor_name': row[5],
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
                     threat_types: Optional[List[str]] = None,
                     severity_levels: Optional[List[str]] = None,
                     days_back: int = 30) -> List[Dict[str, Any]]:
        """Get threats with coordinates for map display."""
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        try:
            where_clauses = ["t.target_latitude IS NOT NULL AND t.target_longitude IS NOT NULL"]
            params = [days_back, days_back]

            if topic:
                where_clauses.append("t.topic = ?")
                params.append(topic)

            if threat_types:
                placeholders = ', '.join(['?' for _ in threat_types])
                where_clauses.append(f"t.threat_type IN ({placeholders})")
                params.extend(threat_types)

            if severity_levels:
                placeholders = ', '.join(['?' for _ in severity_levels])
                where_clauses.append(f"t.severity_level IN ({placeholders})")
                params.extend(severity_levels)

            where_sql = " AND ".join(where_clauses)

            cursor.execute(f"""
                WITH filtered_threats AS (
                    SELECT t.id, COUNT(DISTINCT ta.article_uri) as filtered_count
                    FROM threat_intel_threats t
                    JOIN threat_articles ta ON t.id = ta.threat_id
                    JOIN articles a ON ta.article_uri = a.uri
                    WHERE {where_sql}
                    AND (
                        a.publication_date::timestamp >= CURRENT_DATE - ? * INTERVAL '1 day'
                        OR a.publication_date::date >= CURRENT_DATE - ? * INTERVAL '1 day'
                    )
                    GROUP BY t.id
                    HAVING COUNT(DISTINCT ta.article_uri) > 0
                )
                SELECT t.id, t.threat_name, t.threat_type, t.threat_subtype,
                       t.severity_level, t.severity_score, t.trend,
                       t.threat_actor_name, t.attributed_country, t.attributed_country_name,
                       t.target_countries, t.target_latitude, t.target_longitude,
                       t.target_industries, ft.filtered_count as article_count,
                       t.first_seen_date, t.last_seen_date
                FROM threat_intel_threats t
                JOIN filtered_threats ft ON t.id = ft.id
                ORDER BY t.severity_score DESC
            """, params + [days_back, days_back])

            return [
                {
                    'id': row[0],
                    'threat_name': row[1],
                    'threat_type': row[2],
                    'threat_subtype': row[3],
                    'severity_level': row[4],
                    'severity_score': row[5],
                    'trend': row[6],
                    'threat_actor_name': row[7],
                    'attributed_country': row[8],
                    'attributed_country_name': row[9],
                    'target_countries': row[10],
                    'latitude': row[11],
                    'longitude': row[12],
                    'target_industries': row[13],
                    'article_count': row[14],
                    'first_seen_date': row[15].isoformat() if row[15] else None,
                    'last_seen_date': row[16].isoformat() if row[16] else None,
                }
                for row in cursor.fetchall()
            ]

        finally:
            cursor.close()
            conn.close()

    def get_threats(self, topic: Optional[str] = None,
                    threat_types: Optional[List[str]] = None,
                    severity_levels: Optional[List[str]] = None,
                    actor_id: Optional[int] = None,
                    days_back: int = 30,
                    page: int = 1, page_size: int = 20,
                    sort_by: str = 'severity',
                    sort_order: str = 'desc') -> Tuple[List[Dict[str, Any]], int]:
        """Get paginated list of threats with filters."""
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        try:
            where_clauses = ["t.id IS NOT NULL"]
            params = []

            if topic:
                where_clauses.append("t.topic = ?")
                params.append(topic)

            if threat_types:
                placeholders = ', '.join(['?' for _ in threat_types])
                where_clauses.append(f"t.threat_type IN ({placeholders})")
                params.extend(threat_types)

            if severity_levels:
                placeholders = ', '.join(['?' for _ in severity_levels])
                where_clauses.append(f"t.severity_level IN ({placeholders})")
                params.extend(severity_levels)

            if actor_id:
                where_clauses.append("t.threat_actor_id = ?")
                params.append(actor_id)

            where_sql = "WHERE " + " AND ".join(where_clauses)

            # Sort mapping
            sort_columns = {
                'severity': 't.severity_score',
                'articles': 'filtered_article_count',
                'name': 't.threat_name',
                'type': 't.threat_type',
                'updated': 't.updated_at'
            }
            sort_col = sort_columns.get(sort_by, 't.severity_score')
            order = 'DESC' if sort_order.lower() == 'desc' else 'ASC'

            date_filter_sql = f"""
                AND (
                    a.publication_date::timestamp >= CURRENT_DATE - ? * INTERVAL '1 day'
                    OR a.publication_date::date >= CURRENT_DATE - ? * INTERVAL '1 day'
                )
            """

            # Count query
            count_params = params.copy() + [days_back, days_back]
            cursor.execute(f"""
                WITH filtered_threats AS (
                    SELECT t.id, COUNT(DISTINCT ta.article_uri) as filtered_article_count
                    FROM threat_intel_threats t
                    JOIN threat_articles ta ON t.id = ta.threat_id
                    JOIN articles a ON ta.article_uri = a.uri
                    {where_sql}
                    {date_filter_sql}
                    GROUP BY t.id
                    HAVING COUNT(DISTINCT ta.article_uri) > 0
                )
                SELECT COUNT(*) FROM filtered_threats
            """, count_params if count_params else None)
            total = cursor.fetchone()[0]

            # Results query
            offset = (page - 1) * page_size
            results_params = count_params + [page_size, offset]
            cursor.execute(f"""
                WITH filtered_threats AS (
                    SELECT t.id, COUNT(DISTINCT ta.article_uri) as filtered_article_count
                    FROM threat_intel_threats t
                    JOIN threat_articles ta ON t.id = ta.threat_id
                    JOIN articles a ON ta.article_uri = a.uri
                    {where_sql}
                    {date_filter_sql}
                    GROUP BY t.id
                    HAVING COUNT(DISTINCT ta.article_uri) > 0
                )
                SELECT t.id, t.threat_name, t.threat_type, t.threat_subtype,
                       t.severity_level, t.severity_score, t.trend,
                       t.threat_actor_id, t.threat_actor_name,
                       t.attributed_country, t.attributed_country_name,
                       t.target_countries, t.target_industries,
                       ft.filtered_article_count as article_count,
                       t.first_seen_date, t.last_seen_date,
                       t.cve_ids, t.mitre_techniques, t.malware_families,
                       t.created_at, t.updated_at
                FROM threat_intel_threats t
                JOIN filtered_threats ft ON t.id = ft.id
                ORDER BY {sort_col} {order}
                LIMIT ? OFFSET ?
            """, results_params)

            threats = [
                {
                    'id': row[0],
                    'threat_name': row[1],
                    'threat_type': row[2],
                    'threat_subtype': row[3],
                    'severity_level': row[4],
                    'severity_score': row[5],
                    'trend': row[6],
                    'threat_actor_id': row[7],
                    'threat_actor_name': row[8],
                    'attributed_country': row[9],
                    'attributed_country_name': row[10],
                    'target_countries': row[11],
                    'target_industries': row[12],
                    'article_count': row[13],
                    'first_seen_date': row[14].isoformat() if row[14] else None,
                    'last_seen_date': row[15].isoformat() if row[15] else None,
                    'cve_ids': row[16],
                    'mitre_techniques': row[17],
                    'malware_families': row[18],
                    'created_at': row[19].isoformat() if row[19] else None,
                    'updated_at': row[20].isoformat() if row[20] else None,
                }
                for row in cursor.fetchall()
            ]

            return threats, total

        finally:
            cursor.close()
            conn.close()

    def get_threat_by_id(self, threat_id: int) -> Optional[Dict[str, Any]]:
        """Get single threat by ID with full details."""
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT id, threat_name, threat_type, threat_subtype,
                       severity_level, severity_score, trend,
                       threat_actor_id, threat_actor_name,
                       attributed_country, attributed_country_name,
                       target_countries, target_latitude, target_longitude,
                       target_industries, cve_ids, mitre_techniques, malware_families,
                       first_seen_date, last_seen_date, article_count, recent_article_count,
                       description, tags, metadata, topic, created_at, updated_at
                FROM threat_intel_threats
                WHERE id = ?
            """, [threat_id])

            row = cursor.fetchone()
            if not row:
                return None

            return {
                'id': row[0],
                'threat_name': row[1],
                'threat_type': row[2],
                'threat_subtype': row[3],
                'severity_level': row[4],
                'severity_score': row[5],
                'trend': row[6],
                'threat_actor_id': row[7],
                'threat_actor_name': row[8],
                'attributed_country': row[9],
                'attributed_country_name': row[10],
                'target_countries': row[11],
                'target_latitude': row[12],
                'target_longitude': row[13],
                'target_industries': row[14],
                'cve_ids': row[15],
                'mitre_techniques': row[16],
                'malware_families': row[17],
                'first_seen_date': row[18].isoformat() if row[18] else None,
                'last_seen_date': row[19].isoformat() if row[19] else None,
                'article_count': row[20],
                'recent_article_count': row[21],
                'description': row[22],
                'tags': row[23],
                'metadata': row[24],
                'topic': row[25],
                'created_at': row[26].isoformat() if row[26] else None,
                'updated_at': row[27].isoformat() if row[27] else None,
            }

        finally:
            cursor.close()
            conn.close()

    def get_threat_articles(self, threat_id: int,
                            page: int = 1, page_size: int = 20) -> Tuple[List[Dict[str, Any]], int]:
        """Get articles linked to a threat."""
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT COUNT(*) FROM threat_articles WHERE threat_id = ?
            """, [threat_id])
            total = cursor.fetchone()[0]

            offset = (page - 1) * page_size
            cursor.execute("""
                SELECT a.uri, a.title, a.news_source, a.publication_date, a.summary,
                       a.category, a.sentiment, ta.relevance_score, ta.mention_type
                FROM threat_articles ta
                JOIN articles a ON ta.article_uri = a.uri
                WHERE ta.threat_id = ?
                ORDER BY a.publication_date DESC
                LIMIT ? OFFSET ?
            """, [threat_id, page_size, offset])

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

    # ============================================================================
    # Threat Actors
    # ============================================================================

    def get_actors(self, actor_type: Optional[str] = None,
                   page: int = 1, page_size: int = 20,
                   sort_by: str = 'threat_count',
                   sort_order: str = 'desc') -> Tuple[List[Dict[str, Any]], int]:
        """Get paginated list of threat actors."""
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        try:
            where_clauses = []
            params = []

            if actor_type:
                where_clauses.append("actor_type = ?")
                params.append(actor_type)

            where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

            sort_columns = {
                'threat_count': 'threat_count',
                'article_count': 'article_count',
                'name': 'name',
                'sophistication': 'sophistication_level',
                'last_active': 'last_active'
            }
            sort_col = sort_columns.get(sort_by, 'threat_count')
            order = 'DESC' if sort_order.lower() == 'desc' else 'ASC'

            cursor.execute(f"""
                SELECT COUNT(*) FROM threat_intel_actors {where_sql}
            """, params if params else None)
            total = cursor.fetchone()[0]

            offset = (page - 1) * page_size
            cursor.execute(f"""
                SELECT id, name, aliases, actor_type,
                       attributed_country, attributed_country_name,
                       description, motivation, sophistication_level,
                       target_industries, target_regions,
                       known_ttps, associated_malware,
                       first_observed, last_active,
                       threat_count, article_count,
                       created_at, updated_at
                FROM threat_intel_actors
                {where_sql}
                ORDER BY {sort_col} {order}
                LIMIT ? OFFSET ?
            """, (params + [page_size, offset]) if params else [page_size, offset])

            actors = [
                {
                    'id': row[0],
                    'name': row[1],
                    'aliases': row[2],
                    'actor_type': row[3],
                    'attributed_country': row[4],
                    'attributed_country_name': row[5],
                    'description': row[6],
                    'motivation': row[7],
                    'sophistication_level': row[8],
                    'target_industries': row[9],
                    'target_regions': row[10],
                    'known_ttps': row[11],
                    'associated_malware': row[12],
                    'first_observed': row[13].isoformat() if row[13] else None,
                    'last_active': row[14].isoformat() if row[14] else None,
                    'threat_count': row[15],
                    'article_count': row[16],
                    'created_at': row[17].isoformat() if row[17] else None,
                    'updated_at': row[18].isoformat() if row[18] else None,
                }
                for row in cursor.fetchall()
            ]

            return actors, total

        finally:
            cursor.close()
            conn.close()

    def get_actor_by_id(self, actor_id: int) -> Optional[Dict[str, Any]]:
        """Get single threat actor by ID with full details."""
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT id, name, aliases, actor_type,
                       attributed_country, attributed_country_name,
                       description, motivation, sophistication_level,
                       target_industries, target_regions,
                       known_ttps, associated_malware,
                       first_observed, last_active,
                       threat_count, article_count, metadata,
                       created_at, updated_at
                FROM threat_intel_actors
                WHERE id = ?
            """, [actor_id])

            row = cursor.fetchone()
            if not row:
                return None

            return {
                'id': row[0],
                'name': row[1],
                'aliases': row[2],
                'actor_type': row[3],
                'attributed_country': row[4],
                'attributed_country_name': row[5],
                'description': row[6],
                'motivation': row[7],
                'sophistication_level': row[8],
                'target_industries': row[9],
                'target_regions': row[10],
                'known_ttps': row[11],
                'associated_malware': row[12],
                'first_observed': row[13].isoformat() if row[13] else None,
                'last_active': row[14].isoformat() if row[14] else None,
                'threat_count': row[15],
                'article_count': row[16],
                'metadata': row[17],
                'created_at': row[18].isoformat() if row[18] else None,
                'updated_at': row[19].isoformat() if row[19] else None,
            }

        finally:
            cursor.close()
            conn.close()

    def get_actor_threats(self, actor_id: int,
                          page: int = 1, page_size: int = 20) -> Tuple[List[Dict[str, Any]], int]:
        """Get threats associated with a threat actor."""
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT COUNT(*) FROM threat_intel_threats WHERE threat_actor_id = ?
            """, [actor_id])
            total = cursor.fetchone()[0]

            offset = (page - 1) * page_size
            cursor.execute("""
                SELECT id, threat_name, threat_type, severity_level, severity_score,
                       trend, article_count, first_seen_date, last_seen_date
                FROM threat_intel_threats
                WHERE threat_actor_id = ?
                ORDER BY severity_score DESC
                LIMIT ? OFFSET ?
            """, [actor_id, page_size, offset])

            threats = [
                {
                    'id': row[0],
                    'threat_name': row[1],
                    'threat_type': row[2],
                    'severity_level': row[3],
                    'severity_score': row[4],
                    'trend': row[5],
                    'article_count': row[6],
                    'first_seen_date': row[7].isoformat() if row[7] else None,
                    'last_seen_date': row[8].isoformat() if row[8] else None,
                }
                for row in cursor.fetchall()
            ]

            return threats, total

        finally:
            cursor.close()
            conn.close()

    # ============================================================================
    # Timeline & Analysis
    # ============================================================================

    def get_timeline_data(self, topic: Optional[str] = None,
                          days_back: int = 30) -> List[Dict[str, Any]]:
        """Get temporal trend data for threats."""
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        try:
            start_date = datetime.now() - timedelta(days=days_back)

            where_clause = "WHERE a.publication_date::timestamp >= ?"
            params = [start_date]

            if topic:
                where_clause += " AND t.topic = ?"
                params.append(topic)

            cursor.execute(f"""
                SELECT DATE(a.publication_date::timestamp) as date,
                       COUNT(DISTINCT ta.article_uri) as article_count,
                       AVG(t.severity_score) as avg_severity,
                       COUNT(DISTINCT ta.threat_id) as threat_count
                FROM threat_articles ta
                JOIN threat_intel_threats t ON ta.threat_id = t.id
                JOIN articles a ON ta.article_uri = a.uri
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
                    'avg_severity': round(row[2], 2) if row[2] else 0,
                    'threat_count': row[3]
                }
                for row in cursor.fetchall()
            ]

        finally:
            cursor.close()
            conn.close()

    def get_daily_counts(self, topic: Optional[str] = None,
                         days_back: int = 30) -> List[Dict[str, Any]]:
        """Get daily article counts with rolling average."""
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        try:
            start_date = datetime.now() - timedelta(days=days_back)

            where_clause = "WHERE a.publication_date::timestamp >= ?"
            params = [start_date]

            if topic:
                where_clause += " AND t.topic = ?"
                params.append(topic)

            cursor.execute(f"""
                SELECT DATE(a.publication_date::timestamp) as date,
                       COUNT(DISTINCT ta.article_uri) as article_count,
                       COUNT(DISTINCT ta.threat_id) as threat_count,
                       AVG(t.severity_score) as avg_severity
                FROM threat_articles ta
                JOIN threat_intel_threats t ON ta.threat_id = t.id
                JOIN articles a ON ta.article_uri = a.uri
                {where_clause}
                AND a.publication_date IS NOT NULL
                AND a.publication_date != ''
                GROUP BY DATE(a.publication_date::timestamp)
                ORDER BY date
            """, params)

            daily_data = [
                {
                    'date': row[0].isoformat() if row[0] else None,
                    'article_count': row[1],
                    'threat_count': row[2],
                    'avg_severity': round(row[3], 2) if row[3] else 0
                }
                for row in cursor.fetchall()
            ]

            # Calculate rolling average
            for i, day in enumerate(daily_data):
                window_start = max(0, i - 6)
                window = daily_data[window_start:i + 1]
                day['rolling_avg'] = round(
                    sum(d['article_count'] for d in window) / len(window), 1
                ) if window else 0

            return daily_data

        finally:
            cursor.close()
            conn.close()

    def get_category_distribution(self, topic: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get distribution by threat type."""
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        try:
            where_clauses = ["threat_type IS NOT NULL"]
            params = []
            if topic:
                where_clauses.append("topic = ?")
                params.append(topic)

            where_sql = "WHERE " + " AND ".join(where_clauses)

            cursor.execute(f"""
                SELECT threat_type,
                       COUNT(*) as count,
                       AVG(severity_score) as avg_severity,
                       SUM(article_count) as total_articles
                FROM threat_intel_threats
                {where_sql}
                GROUP BY threat_type
                ORDER BY count DESC
            """, params if params else None)

            return [
                {
                    'category': row[0],
                    'count': row[1],
                    'avg_severity': round(row[2], 2) if row[2] else 0,
                    'total_articles': row[3] or 0
                }
                for row in cursor.fetchall()
            ]

        finally:
            cursor.close()
            conn.close()

    def get_category_trends(self, topic: Optional[str] = None, days_back: int = 90,
                            granularity: str = 'weekly') -> List[Dict[str, Any]]:
        """Get threat type breakdown over time periods."""
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        try:
            start_date = datetime.now() - timedelta(days=days_back)

            where_clause = "WHERE ta.extracted_at >= ?"
            params = [start_date]

            if topic:
                where_clause += " AND t.topic = ?"
                params.append(topic)

            if granularity == 'monthly':
                date_trunc = "DATE_TRUNC('month', ta.extracted_at)"
            else:
                date_trunc = "DATE_TRUNC('week', ta.extracted_at)"

            cursor.execute(f"""
                SELECT {date_trunc} as period,
                       t.threat_type,
                       COUNT(DISTINCT ta.article_uri) as article_count
                FROM threat_articles ta
                JOIN threat_intel_threats t ON ta.threat_id = t.id
                {where_clause}
                AND t.threat_type IS NOT NULL
                GROUP BY {date_trunc}, t.threat_type
                ORDER BY period
            """, params)

            trends_dict = {}
            for row in cursor.fetchall():
                period = row[0].strftime('%Y-%m-%d') if row[0] else None
                threat_type = row[1]
                count = row[2]

                if period not in trends_dict:
                    trends_dict[period] = {}
                trends_dict[period][threat_type] = count

            return [
                {'period': period, 'by_type': types}
                for period, types in sorted(trends_dict.items())
            ]

        finally:
            cursor.close()
            conn.close()

    def get_ttp_analysis(self, topic: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get MITRE ATT&CK technique breakdown."""
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        try:
            where_clauses = ["mitre_techniques IS NOT NULL"]
            params = []
            if topic:
                where_clauses.append("topic = ?")
                params.append(topic)

            where_clause = " AND ".join(where_clauses)

            cursor.execute(f"""
                SELECT mitre_techniques FROM threat_intel_threats
                WHERE {where_clause}
            """, params if params else None)

            technique_counts = {}
            for row in cursor.fetchall():
                techniques = row[0] or []
                if isinstance(techniques, str):
                    import json
                    try:
                        techniques = json.loads(techniques)
                    except:
                        techniques = []
                for tech in techniques:
                    technique_counts[tech] = technique_counts.get(tech, 0) + 1

            # MITRE technique to tactic mapping (simplified)
            tactic_map = {
                'T1566': 'Initial Access',
                'T1190': 'Initial Access',
                'T1133': 'Initial Access',
                'T1059': 'Execution',
                'T1053': 'Execution',
                'T1547': 'Persistence',
                'T1543': 'Persistence',
                'T1548': 'Privilege Escalation',
                'T1055': 'Defense Evasion',
                'T1027': 'Defense Evasion',
                'T1003': 'Credential Access',
                'T1110': 'Credential Access',
                'T1087': 'Discovery',
                'T1021': 'Lateral Movement',
                'T1071': 'Command and Control',
                'T1041': 'Exfiltration',
                'T1486': 'Impact',
                'T1490': 'Impact',
            }

            # Sort by count and return array
            sorted_techniques = sorted(
                technique_counts.items(),
                key=lambda x: x[1],
                reverse=True
            )[:20]

            return [
                {
                    'technique_id': tech_id,
                    'technique_name': tech_id,  # Could be looked up
                    'tactic': tactic_map.get(tech_id.split('.')[0], 'Unknown'),
                    'threat_count': count
                }
                for tech_id, count in sorted_techniques
            ]

        finally:
            cursor.close()
            conn.close()

    # ============================================================================
    # IOCs
    # ============================================================================

    def get_iocs(self, indicator_type: Optional[str] = None,
                 threat_id: Optional[int] = None,
                 page: int = 1, page_size: int = 50) -> Tuple[List[Dict[str, Any]], int]:
        """Get IOCs with filters."""
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        try:
            where_clauses = []
            params = []

            if indicator_type:
                where_clauses.append("indicator_type = ?")
                params.append(indicator_type)

            if threat_id:
                where_clauses.append("threat_id = ?")
                params.append(threat_id)

            where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

            cursor.execute(f"""
                SELECT COUNT(*) FROM threat_intel_iocs {where_sql}
            """, params if params else None)
            total = cursor.fetchone()[0]

            offset = (page - 1) * page_size
            cursor.execute(f"""
                SELECT id, indicator_type, indicator_value, threat_id,
                       confidence, first_seen, last_seen, is_active, description
                FROM threat_intel_iocs
                {where_sql}
                ORDER BY last_seen DESC NULLS LAST
                LIMIT ? OFFSET ?
            """, (params + [page_size, offset]) if params else [page_size, offset])

            iocs = [
                {
                    'id': row[0],
                    'indicator_type': row[1],
                    'indicator_value': row[2],
                    'threat_id': row[3],
                    'confidence': row[4],
                    'first_seen': row[5].isoformat() if row[5] else None,
                    'last_seen': row[6].isoformat() if row[6] else None,
                    'is_active': row[7],
                    'description': row[8],
                }
                for row in cursor.fetchall()
            ]

            return iocs, total

        finally:
            cursor.close()
            conn.close()

    # ============================================================================
    # Campaigns
    # ============================================================================

    def get_campaigns(self, is_active: Optional[bool] = None,
                      page: int = 1, page_size: int = 20) -> Tuple[List[Dict[str, Any]], int]:
        """Get campaigns with filters."""
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        try:
            where_clauses = []
            params = []

            if is_active is not None:
                where_clauses.append("is_active = ?")
                params.append(is_active)

            where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

            cursor.execute(f"""
                SELECT COUNT(*) FROM threat_intel_campaigns {where_sql}
            """, params if params else None)
            total = cursor.fetchone()[0]

            offset = (page - 1) * page_size
            cursor.execute(f"""
                SELECT id, name, description, threat_actor_id, threat_actor_name,
                       start_date, end_date, is_active,
                       target_countries, target_industries,
                       techniques_used, malware_used,
                       threat_count, article_count
                FROM threat_intel_campaigns
                {where_sql}
                ORDER BY start_date DESC NULLS LAST
                LIMIT ? OFFSET ?
            """, (params + [page_size, offset]) if params else [page_size, offset])

            campaigns = [
                {
                    'id': row[0],
                    'name': row[1],
                    'description': row[2],
                    'threat_actor_id': row[3],
                    'threat_actor_name': row[4],
                    'start_date': row[5].isoformat() if row[5] else None,
                    'end_date': row[6].isoformat() if row[6] else None,
                    'is_active': row[7],
                    'target_countries': row[8],
                    'target_industries': row[9],
                    'techniques_used': row[10],
                    'malware_used': row[11],
                    'threat_count': row[12],
                    'article_count': row[13],
                }
                for row in cursor.fetchall()
            ]

            return campaigns, total

        finally:
            cursor.close()
            conn.close()

    # ============================================================================
    # Articles
    # ============================================================================

    def get_all_threat_articles(self, page: int = 1, page_size: int = 20,
                                severity_level: Optional[str] = None,
                                threat_type: Optional[str] = None,
                                threat_id: Optional[int] = None,
                                search: Optional[str] = None,
                                sort_by: str = 'date',
                                sort_order: str = 'desc') -> Tuple[List[Dict[str, Any]], int]:
        """Get all articles linked to any threat with filters."""
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        try:
            where_clauses = []
            params = []

            if threat_id:
                where_clauses.append("t.id = ?")
                params.append(threat_id)

            if severity_level:
                where_clauses.append("t.severity_level = ?")
                params.append(severity_level)

            if threat_type:
                where_clauses.append("t.threat_type = ?")
                params.append(threat_type)

            if search:
                where_clauses.append("(a.title LIKE ? OR a.summary LIKE ?)")
                search_term = f"%{search}%"
                params.extend([search_term, search_term])

            where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

            sort_columns = {
                'date': 'a.publication_date',
                'title': 'a.title',
                'relevance': 'ta.relevance_score',
                'severity': 't.severity_score'
            }
            sort_col = sort_columns.get(sort_by, 'a.publication_date')
            order = 'DESC' if sort_order.lower() == 'desc' else 'ASC'

            cursor.execute(f"""
                SELECT COUNT(DISTINCT a.uri)
                FROM threat_articles ta
                JOIN articles a ON ta.article_uri = a.uri
                JOIN threat_intel_threats t ON ta.threat_id = t.id
                {where_sql}
            """, params if params else None)
            total = cursor.fetchone()[0]

            offset = (page - 1) * page_size
            cursor.execute(f"""
                WITH article_threats AS (
                    SELECT a.uri, a.title, a.news_source, a.publication_date, a.summary,
                           a.category, a.sentiment,
                           json_agg(json_build_object(
                               'id', t.id,
                               'name', t.threat_name,
                               'severity_level', t.severity_level,
                               'type', t.threat_type,
                               'severity_score', t.severity_score
                           ) ORDER BY t.severity_score DESC) as threats,
                           MAX(t.severity_score) as max_severity,
                           MAX(ta.relevance_score) as max_relevance
                    FROM threat_articles ta
                    JOIN articles a ON ta.article_uri = a.uri
                    JOIN threat_intel_threats t ON ta.threat_id = t.id
                    {where_sql}
                    GROUP BY a.uri, a.title, a.news_source, a.publication_date, a.summary,
                             a.category, a.sentiment
                )
                SELECT uri, title, news_source, publication_date, summary,
                       category, sentiment, max_relevance, threats, max_severity
                FROM article_threats
                ORDER BY {sort_col.replace('a.', '').replace('ta.', 'max_').replace('t.', 'max_')} {order}
                LIMIT ? OFFSET ?
            """, (params + [page_size, offset]) if params else [page_size, offset])

            articles = []
            for row in cursor.fetchall():
                threats_data = row[8] if row[8] else []
                primary = threats_data[0] if threats_data else {}
                articles.append({
                    'uri': row[0],
                    'title': row[1],
                    'source': row[2],
                    'publication_date': row[3] if row[3] else None,
                    'summary': row[4],
                    'category': row[5],
                    'sentiment': row[6],
                    'relevance_score': row[7],
                    'threat_id': primary.get('id'),
                    'threat_name': primary.get('name'),
                    'severity_level': primary.get('severity_level', 'info'),
                    'threat_type': primary.get('type'),
                    'severity_score': row[9],
                    'threats': threats_data
                })

            return articles, total

        finally:
            cursor.close()
            conn.close()

    # ============================================================================
    # Processing
    # ============================================================================

    def get_processing_stats(self, topic: str = None) -> Dict[str, Any]:
        """Get statistics about article processing progress."""
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        topic = topic or DEFAULT_THREAT_INTEL_TOPIC

        try:
            cursor.execute("""
                SELECT COUNT(*) FROM articles
                WHERE topic = ? AND category IS NOT NULL AND sentiment IS NOT NULL
            """, [topic])
            total_curated = cursor.fetchone()[0]

            cursor.execute("""
                SELECT COUNT(DISTINCT ta.article_uri)
                FROM threat_articles ta
                JOIN articles a ON ta.article_uri = a.uri
                WHERE a.topic = ?
            """, [topic])
            processed = cursor.fetchone()[0]

            cursor.execute("""
                SELECT COUNT(*) FROM threat_intel_threats WHERE topic = ?
            """, [topic])
            total_threats = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM threat_intel_actors")
            total_actors = cursor.fetchone()[0]

            return {
                'total_curated_articles': total_curated,
                'processed_articles': processed,
                'unprocessed_articles': max(0, total_curated - processed),
                'total_threats': total_threats,
                'total_actors': total_actors,
                'processing_percentage': round((processed / total_curated * 100) if total_curated > 0 else 0, 1),
                'topic': topic
            }

        finally:
            cursor.close()
            conn.close()

    def get_unprocessed_articles(self, limit: int = 100, topic: str = None,
                                  process_all: bool = False) -> List[Dict[str, Any]]:
        """Get articles for threat intelligence processing."""
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        topic = topic or DEFAULT_THREAT_INTEL_TOPIC

        try:
            if process_all:
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
                cursor.execute("""
                    SELECT a.uri, a.title, a.summary, a.category, a.sentiment,
                           a.news_source, a.publication_date
                    FROM articles a
                    LEFT JOIN threat_articles ta ON a.uri = ta.article_uri
                    WHERE a.topic = ?
                    AND a.category IS NOT NULL
                    AND a.sentiment IS NOT NULL
                    AND ta.article_uri IS NULL
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

    def get_available_topics(self) -> List[Dict[str, Any]]:
        """Get list of topics with article counts for processing."""
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT a.topic,
                       COUNT(*) as total_articles,
                       COUNT(*) - COUNT(ta.article_uri) as unprocessed_count
                FROM articles a
                LEFT JOIN threat_articles ta ON a.uri = ta.article_uri
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

    def create_or_update_threat(self, threat_data: Dict[str, Any], topic: str = None) -> int:
        """Create a new threat or update existing one."""
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        topic = topic or DEFAULT_THREAT_INTEL_TOPIC

        try:
            # Check if threat exists
            cursor.execute("""
                SELECT id, article_count, severity_score
                FROM threat_intel_threats
                WHERE threat_name = ?
            """, [threat_data['threat_name']])

            existing = cursor.fetchone()

            if existing:
                threat_id = existing[0]
                new_count = existing[1] + 1
                new_score = min(100, (existing[2] + get_severity_score(threat_data.get('severity_level', 'medium'))) / 2 + 2)

                cursor.execute("""
                    UPDATE threat_intel_threats
                    SET article_count = ?,
                        recent_article_count = recent_article_count + 1,
                        severity_score = ?,
                        severity_level = ?,
                        last_seen_date = CURRENT_DATE,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, [new_count, new_score, threat_data.get('severity_level', 'medium'), threat_id])
            else:
                severity_score = get_severity_score(threat_data.get('severity_level', 'medium'))

                # Create or find threat actor if provided
                actor_id = None
                if threat_data.get('threat_actor_name'):
                    actor_id = self._get_or_create_actor(cursor, threat_data)

                cursor.execute("""
                    INSERT INTO threat_intel_threats
                    (threat_name, threat_type, threat_subtype, severity_level, severity_score, trend,
                     threat_actor_id, threat_actor_name, attributed_country, attributed_country_name,
                     target_countries, target_latitude, target_longitude, target_industries,
                     cve_ids, mitre_techniques, malware_families,
                     first_seen_date, last_seen_date, article_count, recent_article_count,
                     description, tags, topic, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, 'stable', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                            CURRENT_DATE, CURRENT_DATE, 1, 1, ?, ?, ?,
                            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    RETURNING id
                """, [
                    threat_data['threat_name'],
                    threat_data.get('threat_type', 'unknown'),
                    threat_data.get('threat_subtype'),
                    threat_data.get('severity_level', 'medium'),
                    severity_score,
                    actor_id,
                    threat_data.get('threat_actor_name'),
                    threat_data.get('attributed_country'),
                    threat_data.get('attributed_country_name'),
                    threat_data.get('target_countries'),
                    threat_data.get('target_latitude'),
                    threat_data.get('target_longitude'),
                    threat_data.get('target_industries'),
                    threat_data.get('cve_ids'),
                    threat_data.get('mitre_techniques'),
                    threat_data.get('malware_families'),
                    threat_data.get('description'),
                    threat_data.get('tags'),
                    topic
                ])
                threat_id = cursor.fetchone()[0]

            # Create IOCs if provided
            if threat_data.get('iocs'):
                for ioc in threat_data['iocs']:
                    try:
                        cursor.execute("""
                            INSERT INTO threat_intel_iocs
                            (indicator_type, indicator_value, threat_id, first_seen, last_seen)
                            VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                            ON CONFLICT (indicator_type, indicator_value)
                            DO UPDATE SET last_seen = CURRENT_TIMESTAMP, threat_id = EXCLUDED.threat_id
                        """, [ioc['type'], ioc['value'], threat_id])
                    except Exception as e:
                        logger.warning(f"Failed to insert IOC: {e}")

            conn.commit()
            return threat_id

        finally:
            cursor.close()
            conn.close()

    def _get_or_create_actor(self, cursor, threat_data: Dict[str, Any]) -> int:
        """Get or create a threat actor."""
        actor_name = threat_data.get('threat_actor_name')
        if not actor_name:
            return None

        cursor.execute("""
            SELECT id FROM threat_intel_actors WHERE name = ?
        """, [actor_name])
        existing = cursor.fetchone()

        if existing:
            # Update counts
            cursor.execute("""
                UPDATE threat_intel_actors
                SET threat_count = threat_count + 1,
                    last_active = CURRENT_DATE,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, [existing[0]])
            return existing[0]

        # Create new actor
        cursor.execute("""
            INSERT INTO threat_intel_actors
            (name, actor_type, attributed_country, attributed_country_name,
             target_industries, threat_count, article_count,
             first_observed, last_active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 1, 0, CURRENT_DATE, CURRENT_DATE,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            RETURNING id
        """, [
            actor_name,
            threat_data.get('actor_type', 'unknown'),
            threat_data.get('attributed_country'),
            threat_data.get('attributed_country_name'),
            threat_data.get('target_industries')
        ])
        return cursor.fetchone()[0]

    def link_article_to_threat(self, threat_id: int, article_uri: str,
                                relevance_score: float = 1.0, mention_type: str = 'primary'):
        """Link an article to a threat."""
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO threat_articles (threat_id, article_uri, relevance_score, mention_type, extracted_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT (threat_id, article_uri)
                DO UPDATE SET relevance_score = EXCLUDED.relevance_score,
                              mention_type = EXCLUDED.mention_type,
                              extracted_at = CURRENT_TIMESTAMP
            """, [threat_id, article_uri, relevance_score, mention_type])
            conn.commit()

        finally:
            cursor.close()
            conn.close()

    # ============================================================================
    # Narratives
    # ============================================================================

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
                SELECT id, narrative_text, executive_summary, threat_landscape,
                       emerging_threats, recommendations, threat_count, article_count,
                       top_threat_types, top_actors, severity_breakdown, model_used,
                       topic, generated_at
                FROM threat_intel_narratives
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
                'threat_landscape': row[3],
                'emerging_threats': row[4],
                'recommendations': row[5],
                'threat_count': row[6],
                'article_count': row[7],
                'top_threat_types': row[8],
                'top_actors': row[9],
                'severity_breakdown': row[10],
                'model_used': row[11],
                'topic': row[12],
                'generated_at': row[13].isoformat() if row[13] else None
            }

        finally:
            cursor.close()
            conn.close()

    def save_narrative(self, narrative_data: Dict[str, Any]) -> int:
        """Save a generated narrative."""
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO threat_intel_narratives
                (narrative_text, executive_summary, threat_landscape, emerging_threats,
                 recommendations, threat_count, article_count, top_threat_types, top_actors,
                 severity_breakdown, model_used, topic, generated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                RETURNING id
            """, [
                narrative_data.get('narrative_text', ''),
                narrative_data.get('executive_summary'),
                narrative_data.get('threat_landscape'),
                narrative_data.get('emerging_threats'),
                narrative_data.get('recommendations'),
                narrative_data.get('threat_count', 0),
                narrative_data.get('article_count', 0),
                narrative_data.get('top_threat_types'),
                narrative_data.get('top_actors'),
                json.dumps(narrative_data.get('severity_breakdown', {})),
                narrative_data.get('model_used'),
                narrative_data.get('topic')
            ])

            narrative_id = cursor.fetchone()[0]
            conn.commit()
            return narrative_id

        finally:
            cursor.close()
            conn.close()


async def extract_threat_with_llm(title: str, summary: str, category: str, model_name: str = "gpt-4o-mini") -> Dict[str, Any]:
    """Use LLM to extract threat intelligence from an article."""
    from app.ai_models import LiteLLMModel

    try:
        prompt = THREAT_EXTRACTION_PROMPT.format(
            title=title,
            summary=summary or "No summary available",
            category=category or "Unknown"
        )

        model = LiteLLMModel.get_instance(model_name)
        response = model.generate_response([
            {"role": "system", "content": "You are a cybersecurity threat intelligence analyst. Respond only with valid JSON."},
            {"role": "user", "content": prompt}
        ])

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
        return {"no_threat": True, "error": "JSON parse error"}
    except Exception as e:
        logger.error(f"LLM threat extraction failed: {e}")
        return {"no_threat": True, "error": str(e)}


async def generate_narrative_with_llm(stats: Dict[str, Any], model_name: str = "gpt-4o-mini") -> Dict[str, Any]:
    """Use LLM to generate a threat intelligence narrative."""
    from app.ai_models import LiteLLMModel

    try:
        top_types = ', '.join([
            f"{t}: {c}" for t, c in list(stats.get('by_type', {}).items())[:5]
        ]) or "None identified"

        top_threats = stats.get('top_threats', [])
        threats_text = '\n'.join([
            f"- {t['threat_name']} ({t['threat_type']}): {t['severity_level'].upper()} severity, "
            f"{t['article_count']} articles, {t.get('threat_actor_name', 'Unknown actor')}"
            for t in top_threats[:10]
        ]) or "No threats identified"

        # Get top actors info
        active_actors = "No actor data available"

        prompt = NARRATIVE_GENERATION_PROMPT.format(
            total_threats=stats.get('total_threats', 0),
            total_actors=stats.get('total_actors', 0),
            critical_count=stats.get('by_severity', {}).get('critical', 0),
            high_count=stats.get('by_severity', {}).get('high', 0),
            medium_count=stats.get('by_severity', {}).get('medium', 0),
            low_count=stats.get('by_severity', {}).get('low', 0),
            escalating_count=stats.get('escalating_count', 0),
            new_threats=stats.get('new_threats', 0),
            top_types=top_types,
            top_industries="Various",
            recent_articles=stats.get('recent_articles', 0),
            top_threats=threats_text,
            active_actors=active_actors
        )

        model = LiteLLMModel.get_instance(model_name)
        response = model.generate_response([
            {"role": "system", "content": "You are a senior cybersecurity threat intelligence analyst providing strategic briefings."},
            {"role": "user", "content": prompt}
        ])

        narrative_text = response.strip()

        sections = {
            'narrative_text': narrative_text,
            'executive_summary': None,
            'threat_landscape': None,
            'emerging_threats': None,
            'recommendations': None
        }

        # Extract sections
        for section_name, key in [
            ('## Executive Summary', 'executive_summary'),
            ('## Threat Landscape Analysis', 'threat_landscape'),
            ('## Emerging Threats', 'emerging_threats'),
            ('## Defensive Recommendations', 'recommendations')
        ]:
            if section_name in narrative_text:
                parts = narrative_text.split(section_name)
                if len(parts) > 1:
                    section_text = parts[1]
                    next_section = section_text.find('##')
                    if next_section > 0:
                        sections[key] = section_text[:next_section].strip()
                    else:
                        sections[key] = section_text.strip()

        return sections

    except Exception as e:
        logger.error(f"LLM narrative generation failed: {e}")
        return {"error": str(e)}


# Singleton instance
_service = None


def get_threat_intelligence_service() -> ThreatIntelligenceService:
    """Get or create the threat intelligence service singleton."""
    global _service
    if _service is None:
        _service = ThreatIntelligenceService()
    return _service
