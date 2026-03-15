#!/usr/bin/env python3
"""Reprocess all articles for threat intelligence extraction.

This script processes all curated articles through the threat extraction
pipeline, optionally clearing existing threat data first.

Usage:
    python scripts/reprocess_threat_articles.py [--clear] [--batch-size 50] [--topic "Threat Intelligence"]
"""

import argparse
import asyncio
import logging
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import get_database_instance
from app.services.threat_intelligence_service import (
    get_threat_intelligence_service,
    extract_threat_with_llm,
    extract_iocs_from_text,
    is_placeholder_cve,
    is_placeholder_domain,
    is_placeholder_ip
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def clear_threat_data(keep_actors: bool = False):
    """Clear all threat intelligence data."""
    conn = get_database_instance().get_connection()
    cursor = conn.cursor()

    try:
        logger.info("Clearing existing threat data...")

        # Clear in order of dependencies
        cursor.execute("DELETE FROM threat_articles")
        logger.info(f"  Deleted {cursor.rowcount} threat-article links")

        cursor.execute("DELETE FROM threat_intel_iocs")
        logger.info(f"  Deleted {cursor.rowcount} IOCs")

        cursor.execute("DELETE FROM threat_daily_stats")
        logger.info(f"  Deleted {cursor.rowcount} daily stats")

        cursor.execute("DELETE FROM threat_intel_threats")
        logger.info(f"  Deleted {cursor.rowcount} threats")

        if not keep_actors:
            cursor.execute("DELETE FROM threat_intel_actors")
            logger.info(f"  Deleted {cursor.rowcount} actors")

        conn.commit()
        logger.info("Threat data cleared successfully")

    finally:
        cursor.close()
        conn.close()


def get_all_curated_articles(topic: str = None, limit: int = None) -> list:
    """Get all analyzed articles with summaries for processing."""
    conn = get_database_instance().get_connection()
    cursor = conn.cursor()

    try:
        query = """
            SELECT a.uri, a.title, a.summary, a.category
            FROM articles a
            WHERE a.summary IS NOT NULL
            AND a.analyzed = true
        """
        params = []

        if topic:
            query += " AND a.topic = ?"
            params.append(topic)

        query += " ORDER BY a.publication_date DESC"

        if limit:
            query += f" LIMIT {limit}"

        cursor.execute(query, params)

        articles = [
            {
                'uri': row[0],
                'title': row[1],
                'summary': row[2],
                'category': row[3]
            }
            for row in cursor.fetchall()
        ]

        return articles

    finally:
        cursor.close()
        conn.close()


async def process_article(article: dict, service, model: str, topic: str) -> dict:
    """Process a single article for threat extraction."""
    try:
        # Extract threat using LLM
        result = await extract_threat_with_llm(
            article['title'] or "",
            article['summary'] or "",
            article['category'] or "",
            model
        )

        if result.get('no_threat'):
            return {'status': 'skipped', 'reason': 'no_threat'}

        # Validate required fields
        if not result.get('threat_name') or not result.get('threat_type'):
            return {'status': 'skipped', 'reason': 'missing_fields'}

        # Skip placeholder CVE names
        threat_name = result.get('threat_name', '')
        if threat_name.upper().startswith('CVE-') and is_placeholder_cve(threat_name):
            return {'status': 'skipped', 'reason': 'placeholder_cve'}

        # Extract IOCs from article text
        article_text = f"{article.get('title', '')} {article.get('summary', '')}"
        extracted_iocs = extract_iocs_from_text(article_text)

        # Filter and merge IOCs
        llm_iocs = result.get('iocs', [])
        filtered_iocs = []
        for ioc in llm_iocs:
            ioc_type = ioc.get('type', '')
            ioc_value = ioc.get('value', '')
            if ioc_type == 'domain' and is_placeholder_domain(ioc_value):
                continue
            if ioc_type == 'ip' and is_placeholder_ip(ioc_value):
                continue
            filtered_iocs.append(ioc)

        # Merge extracted IOCs
        existing_values = {(ioc.get('type'), ioc.get('value')) for ioc in filtered_iocs}
        for ioc in extracted_iocs:
            if (ioc['type'], ioc['value']) not in existing_values:
                filtered_iocs.append(ioc)

        result['iocs'] = filtered_iocs

        # Run NER extraction
        try:
            from app.utils.ner_extractor import extract_entities
            ner_entities = extract_entities(article_text)

            if ner_entities.get('organizations'):
                result['ner_organizations'] = ner_entities['organizations']
            if ner_entities.get('locations'):
                result['ner_locations'] = ner_entities['locations']
            if ner_entities.get('persons'):
                result['ner_persons'] = ner_entities['persons']
            if ner_entities.get('products'):
                result['ner_products'] = ner_entities['products']
        except Exception as e:
            logger.warning(f"NER extraction failed: {e}")

        # Create or update threat
        threat_id = service.create_or_update_threat(result, topic=topic)

        # Link article to threat
        service.link_article_to_threat(
            threat_id,
            article['uri'],
            relevance_score=1.0,
            mention_type='primary'
        )

        has_actor = bool(result.get('threat_actor_name') and
                        result['threat_actor_name'].lower() not in
                        {'unknown', 'null', 'none', 'n/a', ''})

        return {
            'status': 'success',
            'threat_name': result['threat_name'],
            'has_actor': has_actor,
            'ioc_count': len(filtered_iocs)
        }

    except Exception as e:
        logger.error(f"Error processing article {article['uri']}: {e}")
        return {'status': 'error', 'error': str(e)}


async def main():
    parser = argparse.ArgumentParser(description='Reprocess articles for threat intelligence')
    parser.add_argument('--clear', action='store_true',
                        help='Clear existing threat data before processing')
    parser.add_argument('--keep-actors', action='store_true',
                        help='Keep existing actors when clearing (use with --clear)')
    parser.add_argument('--batch-size', type=int, default=50,
                        help='Number of articles to process in each batch')
    parser.add_argument('--topic', type=str, default='Threat Intelligence',
                        help='Filter by topic (default: Threat Intelligence)')
    parser.add_argument('--all-topics', action='store_true',
                        help='Process articles from all topics')
    parser.add_argument('--model', type=str, default='gpt-4o-mini',
                        help='LLM model to use for extraction')
    parser.add_argument('--limit', type=int, default=None,
                        help='Limit total articles to process')
    parser.add_argument('--delay', type=float, default=0.3,
                        help='Delay between API calls in seconds')
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("THREAT INTELLIGENCE ARTICLE REPROCESSING")
    logger.info("=" * 60)

    # Clear existing data if requested
    if args.clear:
        clear_threat_data(keep_actors=args.keep_actors)

    # Determine topic filter
    topic_filter = None if args.all_topics else args.topic
    topic_label = "all topics" if args.all_topics else args.topic

    # Get all articles
    logger.info(f"\nFetching curated articles from {topic_label}...")
    articles = get_all_curated_articles(topic=topic_filter, limit=args.limit)
    logger.info(f"Found {len(articles)} articles to process")

    if not articles:
        logger.info("No articles to process")
        return

    # Process in batches
    service = get_threat_intelligence_service()
    topic = args.topic  # Store threats under this topic

    stats = {
        'processed': 0,
        'threats_created': 0,
        'actors_identified': 0,
        'iocs_extracted': 0,
        'skipped': 0,
        'errors': 0
    }

    total = len(articles)
    for i, article in enumerate(articles):
        try:
            # Progress
            if (i + 1) % 10 == 0 or i == 0:
                pct = ((i + 1) / total) * 100
                logger.info(f"\nProgress: {i + 1}/{total} ({pct:.1f}%)")
                logger.info(f"  Threats: {stats['threats_created']}, Actors: {stats['actors_identified']}, IOCs: {stats['iocs_extracted']}")

            # Rate limiting
            await asyncio.sleep(args.delay)

            # Process
            result = await process_article(article, service, args.model, topic)

            if result['status'] == 'success':
                stats['processed'] += 1
                stats['threats_created'] += 1
                if result.get('has_actor'):
                    stats['actors_identified'] += 1
                stats['iocs_extracted'] += result.get('ioc_count', 0)
                logger.debug(f"  ✓ {article['title'][:50]}... -> {result['threat_name']}")
            elif result['status'] == 'skipped':
                stats['skipped'] += 1
                logger.debug(f"  - Skipped: {result.get('reason')}")
            else:
                stats['errors'] += 1
                logger.warning(f"  ✗ Error: {result.get('error')}")

        except Exception as e:
            stats['errors'] += 1
            logger.error(f"Error processing article {i + 1}: {e}")

    # Final summary
    logger.info("\n" + "=" * 60)
    logger.info("PROCESSING COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Total articles:     {total}")
    logger.info(f"Processed:          {stats['processed']}")
    logger.info(f"Threats created:    {stats['threats_created']}")
    logger.info(f"Actors identified:  {stats['actors_identified']}")
    logger.info(f"IOCs extracted:     {stats['iocs_extracted']}")
    logger.info(f"Skipped:            {stats['skipped']}")
    logger.info(f"Errors:             {stats['errors']}")


if __name__ == '__main__':
    asyncio.run(main())
