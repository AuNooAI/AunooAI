#!/usr/bin/env python3
"""Calculate threat trends based on activity changes.

This script analyzes threat activity and updates trend status based on:
- Article count changes (7-day vs previous 7-day)
- New IOCs discovered
- Severity changes

Usage:
    python scripts/calculate_threat_trends.py [--dry-run] [--days 7]
"""

import argparse
import logging
import sys
import os
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import get_database_instance

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_threat_article_counts(days: int = 7) -> Dict[int, Dict]:
    """Get article counts for each threat in current and previous periods.

    Returns dict of threat_id -> {
        'current': count in last N days,
        'previous': count in N-2N days ago,
        'total': total article count
    }
    """
    conn = get_database_instance().get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            WITH current_period AS (
                SELECT t.id as threat_id, COUNT(DISTINCT ta.article_uri) as article_count
                FROM threat_intel_threats t
                LEFT JOIN threat_articles ta ON t.id = ta.threat_id
                LEFT JOIN articles a ON ta.article_uri = a.uri
                WHERE a.publication_date::date >= CURRENT_DATE - ? * INTERVAL '1 day'
                GROUP BY t.id
            ),
            previous_period AS (
                SELECT t.id as threat_id, COUNT(DISTINCT ta.article_uri) as article_count
                FROM threat_intel_threats t
                LEFT JOIN threat_articles ta ON t.id = ta.threat_id
                LEFT JOIN articles a ON ta.article_uri = a.uri
                WHERE a.publication_date::date >= CURRENT_DATE - (? * 2) * INTERVAL '1 day'
                  AND a.publication_date::date < CURRENT_DATE - ? * INTERVAL '1 day'
                GROUP BY t.id
            )
            SELECT
                t.id,
                t.threat_name,
                t.trend,
                t.article_count as total_articles,
                t.severity_score,
                COALESCE(cp.article_count, 0) as current_count,
                COALESCE(pp.article_count, 0) as previous_count
            FROM threat_intel_threats t
            LEFT JOIN current_period cp ON t.id = cp.threat_id
            LEFT JOIN previous_period pp ON t.id = pp.threat_id
            ORDER BY t.id
        """, [days, days, days])

        results = {}
        for row in cursor.fetchall():
            results[row[0]] = {
                'id': row[0],
                'threat_name': row[1],
                'current_trend': row[2],
                'total_articles': row[3] or 0,
                'severity_score': row[4] or 50,
                'current_count': row[5],
                'previous_count': row[6]
            }
        return results

    finally:
        cursor.close()
        conn.close()


def get_threat_ioc_counts(days: int = 7) -> Dict[int, Dict]:
    """Get IOC counts for each threat in current and previous periods.

    Returns dict of threat_id -> {
        'current_iocs': count in last N days,
        'previous_iocs': count in N-2N days ago
    }
    """
    conn = get_database_instance().get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            WITH current_iocs AS (
                SELECT threat_id, COUNT(*) as ioc_count
                FROM threat_intel_iocs
                WHERE created_at >= CURRENT_TIMESTAMP - ? * INTERVAL '1 day'
                  AND threat_id IS NOT NULL
                GROUP BY threat_id
            ),
            previous_iocs AS (
                SELECT threat_id, COUNT(*) as ioc_count
                FROM threat_intel_iocs
                WHERE created_at >= CURRENT_TIMESTAMP - (? * 2) * INTERVAL '1 day'
                  AND created_at < CURRENT_TIMESTAMP - ? * INTERVAL '1 day'
                  AND threat_id IS NOT NULL
                GROUP BY threat_id
            )
            SELECT
                t.id,
                COALESCE(ci.ioc_count, 0) as current_iocs,
                COALESCE(pi.ioc_count, 0) as previous_iocs
            FROM threat_intel_threats t
            LEFT JOIN current_iocs ci ON t.id = ci.threat_id
            LEFT JOIN previous_iocs pi ON t.id = pi.threat_id
        """, [days, days, days])

        results = {}
        for row in cursor.fetchall():
            results[row[0]] = {
                'current_iocs': row[1],
                'previous_iocs': row[2]
            }
        return results

    finally:
        cursor.close()
        conn.close()


def calculate_trend(
    current_articles: int,
    previous_articles: int,
    current_iocs: int,
    previous_iocs: int,
    severity_score: float
) -> Tuple[str, Dict]:
    """Calculate trend based on activity metrics.

    Scoring factors:
    - Article change: +/-50 points (weight: 50%)
    - IOC change: +/-30 points (weight: 30%)
    - Severity bonus: +/-20 points for critical/high threats (weight: 20%)

    Thresholds:
    - Escalating: total_score >= 20
    - Declining: total_score <= -20
    - Stable: -20 < total_score < 20

    Returns:
        (trend_status, metrics_dict)
    """
    metrics = {
        'article_change_pct': 0.0,
        'ioc_change_pct': 0.0,
        'article_score': 0,
        'ioc_score': 0,
        'severity_score': 0,
        'total_score': 0
    }

    # Article change score (weight: 50%)
    if previous_articles > 0:
        article_change = (current_articles - previous_articles) / previous_articles * 100
        metrics['article_change_pct'] = article_change
        # Map percentage change to -50 to +50 score
        # +100% change = +50 points, -100% change = -50 points
        metrics['article_score'] = max(-50, min(50, article_change / 2))
    elif current_articles > 0:
        # New activity where there was none
        metrics['article_change_pct'] = 100
        metrics['article_score'] = 40  # Strong positive signal

    # IOC change score (weight: 30%)
    if previous_iocs > 0:
        ioc_change = (current_iocs - previous_iocs) / previous_iocs * 100
        metrics['ioc_change_pct'] = ioc_change
        # Map percentage change to -30 to +30 score
        metrics['ioc_score'] = max(-30, min(30, ioc_change * 0.3))
    elif current_iocs > 0:
        # New IOCs discovered
        metrics['ioc_change_pct'] = 100
        metrics['ioc_score'] = 25  # Positive signal

    # Severity bonus (weight: 20%)
    # High severity threats get bonus for any positive activity
    if severity_score >= 80:  # Critical
        if current_articles > 0 or current_iocs > 0:
            metrics['severity_score'] = 15
    elif severity_score >= 60:  # High
        if current_articles > 0 or current_iocs > 0:
            metrics['severity_score'] = 10

    # Calculate total score
    metrics['total_score'] = metrics['article_score'] + metrics['ioc_score'] + metrics['severity_score']

    # Determine trend
    if metrics['total_score'] >= 20:
        trend = 'escalating'
    elif metrics['total_score'] <= -20:
        trend = 'declining'
    else:
        trend = 'stable'

    return trend, metrics


def update_threat_trends(trends: Dict[int, str], dry_run: bool = False) -> int:
    """Update threat trends in database.

    Returns count of updated records.
    """
    if dry_run or not trends:
        return 0

    conn = get_database_instance().get_connection()
    cursor = conn.cursor()

    try:
        updated = 0
        for threat_id, trend in trends.items():
            cursor.execute("""
                UPDATE threat_intel_threats
                SET trend = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                  AND (trend IS NULL OR trend != ?)
            """, [trend, threat_id, trend])
            if cursor.rowcount > 0:
                updated += 1

        conn.commit()
        return updated

    finally:
        cursor.close()
        conn.close()


def update_recent_article_counts(days: int = 7, dry_run: bool = False) -> int:
    """Update recent_article_count field for all threats.

    Returns count of updated records.
    """
    if dry_run:
        return 0

    conn = get_database_instance().get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            UPDATE threat_intel_threats t
            SET recent_article_count = (
                SELECT COUNT(DISTINCT ta.article_uri)
                FROM threat_articles ta
                JOIN articles a ON ta.article_uri = a.uri
                WHERE ta.threat_id = t.id
                  AND a.publication_date::date >= CURRENT_DATE - ? * INTERVAL '1 day'
            ),
            updated_at = CURRENT_TIMESTAMP
        """, [days])

        updated = cursor.rowcount
        conn.commit()
        return updated

    finally:
        cursor.close()
        conn.close()


def main():
    parser = argparse.ArgumentParser(description='Calculate threat trends from activity metrics')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview changes without updating database')
    parser.add_argument('--days', type=int, default=7,
                        help='Period length in days (default: 7)')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Show detailed metrics for each threat')
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("THREAT TREND CALCULATION")
    logger.info("=" * 60)

    if args.dry_run:
        logger.info("DRY RUN MODE - No changes will be saved")

    logger.info(f"Period: {args.days} days (comparing to previous {args.days} days)")

    # Get article counts
    logger.info("\nFetching article counts...")
    article_data = get_threat_article_counts(args.days)
    logger.info(f"Found {len(article_data)} threats to analyze")

    # Get IOC counts
    logger.info("Fetching IOC counts...")
    ioc_data = get_threat_ioc_counts(args.days)

    # Calculate trends
    logger.info("\nCalculating trends...")
    trends_to_update = {}
    escalating_count = 0
    declining_count = 0
    stable_count = 0
    changed_count = 0

    for threat_id, data in article_data.items():
        ioc_info = ioc_data.get(threat_id, {'current_iocs': 0, 'previous_iocs': 0})

        new_trend, metrics = calculate_trend(
            current_articles=data['current_count'],
            previous_articles=data['previous_count'],
            current_iocs=ioc_info['current_iocs'],
            previous_iocs=ioc_info['previous_iocs'],
            severity_score=data['severity_score']
        )

        trends_to_update[threat_id] = new_trend

        # Count by trend type
        if new_trend == 'escalating':
            escalating_count += 1
        elif new_trend == 'declining':
            declining_count += 1
        else:
            stable_count += 1

        # Count changed
        if data['current_trend'] != new_trend:
            changed_count += 1

        # Verbose output
        if args.verbose and (new_trend != 'stable' or data['current_trend'] != new_trend):
            logger.info(f"\n  {data['threat_name']} (ID: {threat_id})")
            logger.info(f"    Current trend: {data['current_trend']} -> {new_trend}")
            logger.info(f"    Articles: {data['previous_count']} -> {data['current_count']} ({metrics['article_change_pct']:+.1f}%)")
            logger.info(f"    IOCs: {ioc_info['previous_iocs']} -> {ioc_info['current_iocs']} ({metrics['ioc_change_pct']:+.1f}%)")
            logger.info(f"    Score: {metrics['total_score']:.1f} (article: {metrics['article_score']:.1f}, ioc: {metrics['ioc_score']:.1f}, severity: {metrics['severity_score']:.1f})")

    # Update database
    if not args.dry_run:
        logger.info("\nUpdating threat trends...")
        updated = update_threat_trends(trends_to_update)
        logger.info(f"Updated {updated} threat records")

        logger.info("Updating recent article counts...")
        count_updated = update_recent_article_counts(args.days)
        logger.info(f"Updated article counts for {count_updated} threats")

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("TREND CALCULATION COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Threats analyzed:  {len(article_data)}")
    logger.info(f"Escalating:        {escalating_count}")
    logger.info(f"Stable:            {stable_count}")
    logger.info(f"Declining:         {declining_count}")
    logger.info(f"Trends changed:    {changed_count}")

    if args.dry_run:
        logger.info("\nThis was a dry run. Run without --dry-run to update the database.")


if __name__ == '__main__':
    main()
