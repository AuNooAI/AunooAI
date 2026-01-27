#!/usr/bin/env python3
"""Auto-detect campaigns by clustering related threats.

This script analyzes threats and groups them into campaigns based on:
- Common threat actor
- Similar target industries/countries
- Time proximity (threats within the same time window)
- Related malware families

Usage:
    python scripts/detect_campaigns.py [--dry-run] [--min-threats 3] [--days 30]
"""

import argparse
import json
import logging
import sys
import os
from datetime import datetime, timedelta
from typing import Dict, List, Set, Tuple
from collections import defaultdict

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import get_database_instance

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_recent_threats(days: int = 30) -> List[Dict]:
    """Get threats from the last N days for clustering."""
    conn = get_database_instance().get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT t.id, t.threat_name, t.threat_type, t.threat_actor_id, t.threat_actor_name,
                   t.target_countries, t.target_industries, t.malware_families,
                   t.first_seen_date, t.last_seen_date, t.severity_level,
                   t.metadata
            FROM threat_intel_threats t
            WHERE t.first_seen_date >= CURRENT_DATE - ? * INTERVAL '1 day'
               OR t.last_seen_date >= CURRENT_DATE - ? * INTERVAL '1 day'
            ORDER BY t.first_seen_date DESC
        """, [days, days])

        return [
            {
                'id': row[0],
                'threat_name': row[1],
                'threat_type': row[2],
                'threat_actor_id': row[3],
                'threat_actor_name': row[4],
                'target_countries': row[5] or [],
                'target_industries': row[6] or [],
                'malware_families': row[7] or [],
                'first_seen_date': row[8],
                'last_seen_date': row[9],
                'severity_level': row[10],
                'metadata': row[11] or {}
            }
            for row in cursor.fetchall()
        ]
    finally:
        cursor.close()
        conn.close()


def get_existing_campaigns() -> Dict[str, int]:
    """Get existing campaign names to avoid duplicates."""
    conn = get_database_instance().get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT id, LOWER(name) FROM threat_intel_campaigns")
        return {row[1]: row[0] for row in cursor.fetchall()}
    finally:
        cursor.close()
        conn.close()


def calculate_similarity(threat1: Dict, threat2: Dict) -> float:
    """Calculate similarity score between two threats (0-1)."""
    score = 0.0
    weights_sum = 0.0

    # Same threat actor (high weight)
    if threat1.get('threat_actor_id') and threat1['threat_actor_id'] == threat2.get('threat_actor_id'):
        score += 0.4
    weights_sum += 0.4

    # Overlapping target countries
    countries1 = set(threat1.get('target_countries') or [])
    countries2 = set(threat2.get('target_countries') or [])
    if countries1 and countries2:
        overlap = len(countries1 & countries2) / max(len(countries1 | countries2), 1)
        score += 0.2 * overlap
    weights_sum += 0.2

    # Overlapping target industries
    industries1 = set(threat1.get('target_industries') or [])
    industries2 = set(threat2.get('target_industries') or [])
    if industries1 and industries2:
        overlap = len(industries1 & industries2) / max(len(industries1 | industries2), 1)
        score += 0.2 * overlap
    weights_sum += 0.2

    # Same threat type
    if threat1.get('threat_type') == threat2.get('threat_type'):
        score += 0.1
    weights_sum += 0.1

    # Overlapping malware families
    malware1 = set(threat1.get('malware_families') or [])
    malware2 = set(threat2.get('malware_families') or [])
    if malware1 and malware2:
        overlap = len(malware1 & malware2) / max(len(malware1 | malware2), 1)
        score += 0.1 * overlap
    weights_sum += 0.1

    return score / weights_sum if weights_sum > 0 else 0


def cluster_threats(threats: List[Dict], similarity_threshold: float = 0.5) -> List[List[Dict]]:
    """Cluster threats based on similarity."""
    if not threats:
        return []

    # Simple greedy clustering
    clusters = []
    used = set()

    for i, threat in enumerate(threats):
        if i in used:
            continue

        # Start new cluster with this threat
        cluster = [threat]
        used.add(i)

        # Find similar threats
        for j, other in enumerate(threats):
            if j in used:
                continue

            # Check similarity with all threats in cluster
            avg_similarity = sum(
                calculate_similarity(cluster_threat, other)
                for cluster_threat in cluster
            ) / len(cluster)

            if avg_similarity >= similarity_threshold:
                cluster.append(other)
                used.add(j)

        clusters.append(cluster)

    return clusters


def generate_campaign_name(cluster: List[Dict]) -> str:
    """Generate a campaign name from clustered threats."""
    # Try to use threat actor name
    actor_names = [t['threat_actor_name'] for t in cluster if t.get('threat_actor_name')]
    if actor_names:
        actor = max(set(actor_names), key=actor_names.count)
        return f"{actor} Campaign"

    # Try to use common target
    all_industries = []
    for t in cluster:
        all_industries.extend(t.get('target_industries') or [])
    if all_industries:
        industry = max(set(all_industries), key=all_industries.count)
        return f"{industry.title()} Sector Campaign"

    all_countries = []
    for t in cluster:
        all_countries.extend(t.get('target_countries') or [])
    if all_countries:
        country = max(set(all_countries), key=all_countries.count)
        return f"{country} Targeting Campaign"

    # Fallback to threat type
    threat_types = [t['threat_type'] for t in cluster if t.get('threat_type')]
    if threat_types:
        threat_type = max(set(threat_types), key=threat_types.count)
        return f"{threat_type.title().replace('_', ' ')} Campaign"

    return f"Unnamed Campaign {datetime.now().strftime('%Y%m%d')}"


def create_campaign(cluster: List[Dict], dry_run: bool = False) -> int:
    """Create a campaign from a cluster of threats."""
    campaign_name = generate_campaign_name(cluster)

    # Aggregate data from cluster
    actor_ids = [t['threat_actor_id'] for t in cluster if t.get('threat_actor_id')]
    actor_id = max(set(actor_ids), key=actor_ids.count) if actor_ids else None

    actor_names = [t['threat_actor_name'] for t in cluster if t.get('threat_actor_name')]
    actor_name = max(set(actor_names), key=actor_names.count) if actor_names else None

    all_countries = set()
    all_industries = set()
    all_malware = set()
    for t in cluster:
        all_countries.update(t.get('target_countries') or [])
        all_industries.update(t.get('target_industries') or [])
        all_malware.update(t.get('malware_families') or [])

    # Get date range
    dates = [t['first_seen_date'] for t in cluster if t.get('first_seen_date')]
    start_date = min(dates) if dates else None

    # Generate description
    threat_names = [t['threat_name'] for t in cluster]
    description = f"Auto-detected campaign grouping {len(cluster)} related threats: {', '.join(threat_names[:5])}"
    if len(threat_names) > 5:
        description += f" and {len(threat_names) - 5} more"

    if dry_run:
        logger.info(f"  [DRY RUN] Would create campaign: {campaign_name}")
        logger.info(f"    - Threats: {len(cluster)}")
        logger.info(f"    - Actor: {actor_name}")
        logger.info(f"    - Countries: {list(all_countries)[:5]}")
        logger.info(f"    - Industries: {list(all_industries)[:5]}")
        return -1

    conn = get_database_instance().get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO threat_intel_campaigns
            (name, description, threat_actor_id, threat_actor_name,
             start_date, is_active, target_countries, target_industries,
             malware_used, threat_count, article_count, metadata,
             created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, true, ?, ?, ?, ?, 0, ?,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            RETURNING id
        """, [
            campaign_name,
            description,
            actor_id,
            actor_name,
            start_date,
            list(all_countries) if all_countries else None,
            list(all_industries) if all_industries else None,
            list(all_malware) if all_malware else None,
            len(cluster),
            '{"auto_detected": true}'
        ])

        campaign_id = cursor.fetchone()[0]

        # Link threats to campaign via metadata
        threat_ids = [t['id'] for t in cluster]
        for threat_id in threat_ids:
            # Get current metadata and update it
            cursor.execute("SELECT metadata FROM threat_intel_threats WHERE id = ?", [threat_id])
            row = cursor.fetchone()
            current_metadata = row[0] if row and row[0] else {}
            if isinstance(current_metadata, str):
                current_metadata = json.loads(current_metadata)
            current_metadata['campaign_id'] = campaign_id
            cursor.execute("""
                UPDATE threat_intel_threats
                SET metadata = ?
                WHERE id = ?
            """, [json.dumps(current_metadata), threat_id])

        conn.commit()
        logger.info(f"  Created campaign: {campaign_name} (ID: {campaign_id}) with {len(cluster)} threats")
        return campaign_id

    finally:
        cursor.close()
        conn.close()


def main():
    parser = argparse.ArgumentParser(description='Auto-detect campaigns from threat clusters')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview campaigns without creating them')
    parser.add_argument('--min-threats', type=int, default=3,
                        help='Minimum threats to form a campaign (default: 3)')
    parser.add_argument('--days', type=int, default=30,
                        help='Look back period in days (default: 30)')
    parser.add_argument('--similarity', type=float, default=0.5,
                        help='Similarity threshold for clustering (default: 0.5)')
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("CAMPAIGN AUTO-DETECTION")
    logger.info("=" * 60)

    if args.dry_run:
        logger.info("DRY RUN MODE - No changes will be saved")

    # Get existing campaigns
    existing_campaigns = get_existing_campaigns()
    logger.info(f"Found {len(existing_campaigns)} existing campaigns")

    # Get recent threats
    logger.info(f"\nFetching threats from last {args.days} days...")
    threats = get_recent_threats(args.days)
    logger.info(f"Found {len(threats)} threats to analyze")

    if len(threats) < args.min_threats:
        logger.info("Not enough threats to form campaigns")
        return

    # Filter out threats already in campaigns
    threats_without_campaign = [
        t for t in threats
        if not t.get('metadata', {}).get('campaign_id')
    ]
    logger.info(f"{len(threats_without_campaign)} threats not yet in campaigns")

    if len(threats_without_campaign) < args.min_threats:
        logger.info("Not enough unassigned threats to form new campaigns")
        return

    # Cluster threats
    logger.info(f"\nClustering threats (similarity threshold: {args.similarity})...")
    clusters = cluster_threats(threats_without_campaign, args.similarity)

    # Filter clusters by minimum size
    significant_clusters = [c for c in clusters if len(c) >= args.min_threats]
    logger.info(f"Found {len(significant_clusters)} potential campaigns (>= {args.min_threats} threats)")

    if not significant_clusters:
        logger.info("No significant clusters found")
        return

    # Create campaigns
    campaigns_created = 0
    for i, cluster in enumerate(significant_clusters):
        campaign_name = generate_campaign_name(cluster).lower()

        # Skip if similar campaign exists
        if campaign_name in existing_campaigns:
            logger.info(f"\nSkipping cluster {i+1}: Campaign '{campaign_name}' already exists")
            continue

        logger.info(f"\nCluster {i+1}: {len(cluster)} threats")
        campaign_id = create_campaign(cluster, args.dry_run)
        if campaign_id > 0:
            campaigns_created += 1

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("DETECTION COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Threats analyzed:     {len(threats)}")
    logger.info(f"Clusters found:       {len(significant_clusters)}")
    logger.info(f"Campaigns created:    {campaigns_created}")

    if args.dry_run:
        logger.info("\nThis was a dry run. Run without --dry-run to create campaigns.")


if __name__ == '__main__':
    main()
