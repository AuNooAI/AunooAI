#!/usr/bin/env python3
"""Batch enrichment script for threat actor data.

This script:
1. Generates descriptions for all actors missing them
2. Runs NER on linked articles to extract additional entities
3. Updates actor records with enriched data

Usage:
    python scripts/enrich_actor_data.py [--dry-run] [--limit N]
"""

import argparse
import logging
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import get_database_instance
from app.services.threat_intelligence_service import get_threat_intelligence_service

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_actors_without_descriptions(limit: int = None) -> list:
    """Get all actors that don't have descriptions."""
    conn = get_database_instance().get_connection()
    cursor = conn.cursor()

    try:
        query = """
            SELECT id, name, actor_type, threat_count
            FROM threat_intel_actors
            WHERE description IS NULL OR description = ''
            ORDER BY threat_count DESC
        """
        if limit:
            query += f" LIMIT {limit}"

        cursor.execute(query)
        return [
            {'id': row[0], 'name': row[1], 'actor_type': row[2], 'threat_count': row[3]}
            for row in cursor.fetchall()
        ]
    finally:
        cursor.close()
        conn.close()


def enrich_actor_with_ner(actor_id: int, dry_run: bool = False) -> dict:
    """Run NER on all articles linked to an actor and aggregate entities.

    Args:
        actor_id: The actor ID to enrich
        dry_run: If True, don't save changes

    Returns:
        Dictionary with aggregated NER entities
    """
    from app.utils.ner_extractor import extract_entities_batch

    conn = get_database_instance().get_connection()
    cursor = conn.cursor()

    try:
        # Get all article text linked to this actor
        cursor.execute("""
            SELECT DISTINCT a.title, a.summary
            FROM threat_intel_threats t
            JOIN threat_articles ta ON t.id = ta.threat_id
            JOIN articles a ON ta.article_uri = a.uri
            WHERE t.threat_actor_id = ?
            AND (a.title IS NOT NULL OR a.summary IS NOT NULL)
            LIMIT 50
        """, [actor_id])

        articles = cursor.fetchall()
        if not articles:
            return {'organizations': [], 'locations': [], 'persons': [], 'products': []}

        # Combine title and summary for each article
        texts = [
            f"{row[0] or ''} {row[1] or ''}".strip()
            for row in articles
        ]

        # Run batch NER extraction
        all_entities = extract_entities_batch(texts)

        # Aggregate entities across all articles
        aggregated = {
            'organizations': set(),
            'locations': set(),
            'persons': set(),
            'products': set()
        }

        for entities in all_entities:
            for org in entities.get('organizations', []):
                aggregated['organizations'].add(org)
            for loc in entities.get('locations', []):
                aggregated['locations'].add(loc)
            for person in entities.get('persons', []):
                aggregated['persons'].add(person)
            for product in entities.get('products', []):
                aggregated['products'].add(product)

        result = {
            'organizations': list(aggregated['organizations'])[:20],
            'locations': list(aggregated['locations'])[:20],
            'persons': list(aggregated['persons'])[:20],
            'products': list(aggregated['products'])[:20]
        }

        # Update actor metadata if not dry run
        if not dry_run and any(result.values()):
            import json

            # Get existing metadata
            cursor.execute("SELECT metadata FROM threat_intel_actors WHERE id = ?", [actor_id])
            row = cursor.fetchone()
            existing_metadata = row[0] if row and row[0] else {}

            # Merge NER data into metadata
            existing_metadata['ner_organizations'] = result['organizations']
            existing_metadata['ner_locations'] = result['locations']
            existing_metadata['ner_persons'] = result['persons']
            existing_metadata['ner_products'] = result['products']

            cursor.execute("""
                UPDATE threat_intel_actors
                SET metadata = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, [json.dumps(existing_metadata), actor_id])
            conn.commit()

        return result

    finally:
        cursor.close()
        conn.close()


def main():
    parser = argparse.ArgumentParser(description='Enrich threat actor data')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview changes without saving')
    parser.add_argument('--limit', type=int, default=None,
                        help='Limit number of actors to process')
    parser.add_argument('--descriptions-only', action='store_true',
                        help='Only generate descriptions, skip NER')
    parser.add_argument('--ner-only', action='store_true',
                        help='Only run NER extraction, skip descriptions')
    args = parser.parse_args()

    logger.info("Starting actor data enrichment...")
    if args.dry_run:
        logger.info("DRY RUN MODE - No changes will be saved")

    service = get_threat_intelligence_service()

    # Get actors without descriptions
    actors = get_actors_without_descriptions(args.limit)
    logger.info(f"Found {len(actors)} actors without descriptions")

    descriptions_generated = 0
    ner_enriched = 0
    errors = 0

    for i, actor in enumerate(actors):
        logger.info(f"\n[{i+1}/{len(actors)}] Processing: {actor['name']} (ID: {actor['id']})")

        # Generate description
        if not args.ner_only:
            try:
                if args.dry_run:
                    logger.info(f"  Would generate description for {actor['name']}")
                else:
                    description = service.generate_actor_description(actor['id'])
                    if description:
                        logger.info(f"  Generated description: {description[:80]}...")
                        descriptions_generated += 1
                    else:
                        logger.info(f"  No articles linked, skipping description")
            except Exception as e:
                logger.error(f"  Error generating description: {e}")
                errors += 1

        # Run NER enrichment
        if not args.descriptions_only:
            try:
                ner_result = enrich_actor_with_ner(actor['id'], dry_run=args.dry_run)
                total_entities = sum(len(v) for v in ner_result.values())
                if total_entities > 0:
                    logger.info(f"  NER extracted: {len(ner_result['organizations'])} orgs, "
                                f"{len(ner_result['locations'])} locations, "
                                f"{len(ner_result['persons'])} persons, "
                                f"{len(ner_result['products'])} products")
                    if not args.dry_run:
                        ner_enriched += 1
                else:
                    logger.info(f"  No NER entities found")
            except Exception as e:
                logger.error(f"  Error running NER: {e}")
                errors += 1

    # Summary
    logger.info("\n" + "="*60)
    logger.info("ENRICHMENT SUMMARY")
    logger.info("="*60)
    logger.info(f"Actors processed:        {len(actors)}")
    logger.info(f"Descriptions generated:  {descriptions_generated}")
    logger.info(f"Actors NER-enriched:     {ner_enriched}")
    logger.info(f"Errors:                  {errors}")

    if args.dry_run:
        logger.info("\nThis was a dry run. Run without --dry-run to save changes.")


if __name__ == '__main__':
    main()
