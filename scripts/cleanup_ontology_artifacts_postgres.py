#!/usr/bin/env python3
"""
PostgreSQL cleanup script for ontology artifacts (markdown, typos, case issues).

Cleans up:
- time_to_impact: ** Mid-term, ** Short-term, Medium-term, etc.
- sentiment: ** Neutral, ** Positive, Mixed, etc.
- driver_type: ** Catalyst, catalyst (lowercase), Initiative, etc.
- category: Any markdown artifacts

Usage:
    python scripts/cleanup_ontology_artifacts_postgres.py --analyze  # Analyze issues
    python scripts/cleanup_ontology_artifacts_postgres.py --execute  # Perform cleanup
"""

import sys
import os
import logging
import psycopg2

# Add app directory to path
sys.path.insert(0, os.path.abspath('.'))

from app.config.settings import load_config, db_settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Ontology field mappings
ONTOLOGY_MAPPINGS = {
    'time_to_impact': {
        '** Immediate': 'Immediate',
        '** Short-term': 'Short-term',
        '** Mid-term': 'Mid-term',
        '** Long-term': 'Long-term',
        'Medium-term': 'Mid-term',  # Common typo
        'Midterm': 'Mid-term',
        'Short term': 'Short-term',
        'Long term': 'Long-term',
    },
    'sentiment': {
        '** Hyperbolic': 'Hyperbolic',
        '** Positive': 'Positive',
        '** Neutral': 'Neutral',
        '** Negative': 'Negative',
        '** Critical': 'Critical',
        'Mixed': 'Neutral',  # Mixed sentiment -> Neutral
    },
    'driver_type': {
        '** Accelerator': 'Accelerator',
        '** Delayer': 'Delayer',
        '** Blocker': 'Blocker',
        '** Catalyst': 'Catalyst',
        '** Initiator': 'Initiator',
        '** Terminator': 'Terminator',
        '** Unknown': 'Unknown',
        'catalyst': 'Catalyst',  # Lowercase
        'accelerator': 'Accelerator',
        'delayer': 'Delayer',
        'blocker': 'Blocker',
        'initiator': 'Initiator',
        'terminator': 'Terminator',
        'Initiative': 'Initiator',  # Common typo
        'Inhibitor': 'Blocker',  # Synonym
    }
}


def get_postgres_connection():
    """Create PostgreSQL connection."""
    try:
        conn = psycopg2.connect(
            host=db_settings.DB_HOST,
            port=db_settings.DB_PORT,
            user=db_settings.DB_USER,
            password=db_settings.DB_PASSWORD,
            dbname=db_settings.DB_NAME
        )
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to PostgreSQL: {e}")
        raise


def analyze_artifacts(conn):
    """Analyze artifacts in all ontology fields."""
    results = {}

    for field, mappings in ONTOLOGY_MAPPINGS.items():
        results[field] = {}

        with conn.cursor() as cursor:
            # Get all distinct values for this field
            cursor.execute(f"""
                SELECT {field}, COUNT(*) as count
                FROM articles
                WHERE {field} IS NOT NULL
                  AND {field} <> ''
                GROUP BY {field}
                ORDER BY count DESC
            """)

            values = cursor.fetchall()

            for value, count in values:
                if value in mappings:
                    results[field][value] = {
                        'count': count,
                        'mapped_to': mappings[value]
                    }

    return results


def print_analysis_report(results):
    """Print analysis report."""
    total_artifacts = sum(sum(v['count'] for v in field_data.values())
                         for field_data in results.values())

    print("\n" + "="*80)
    print("📊 ONTOLOGY ARTIFACTS CLEANUP ANALYSIS (PostgreSQL)")
    print("="*80)
    print(f"🔍 Total articles with artifacts: {total_artifacts:,}")

    for field, artifacts in results.items():
        if not artifacts:
            continue

        field_total = sum(v['count'] for v in artifacts.values())
        print(f"\n📁 {field.replace('_', ' ').title()} ({field_total:,} articles)")

        for value, info in sorted(artifacts.items(), key=lambda x: x[1]['count'], reverse=True):
            print(f"  • '{value}' → '{info['mapped_to']}': {info['count']:,} articles")


def cleanup_artifacts(conn, dry_run=True):
    """Clean up ontology artifacts."""
    results = analyze_artifacts(conn)

    total_artifacts = sum(sum(v['count'] for v in field_data.values())
                         for field_data in results.values())

    if total_artifacts == 0:
        logger.info("✅ No ontology artifacts found. Database is clean!")
        return

    print_analysis_report(results)

    if dry_run:
        print(f"\n{'='*80}")
        print(f"🔍 [DRY RUN] Would clean up {total_artifacts:,} articles")
        print(f"Run with --execute flag to perform actual cleanup")
        print(f"{'='*80}")
        return

    # Perform cleanup
    print(f"\n{'='*80}")
    print(f"🧹 Cleaning up {total_artifacts:,} articles...")
    print(f"{'='*80}")

    total_updated = 0

    with conn.cursor() as cursor:
        # Process each field
        for field, mappings in ONTOLOGY_MAPPINGS.items():
            for invalid_value, valid_value in mappings.items():
                # Check if any articles have this invalid value
                cursor.execute(f"""
                    SELECT COUNT(*) FROM articles
                    WHERE {field} = %s
                """, (invalid_value,))

                count = cursor.fetchone()[0]
                if count == 0:
                    continue

                # Update articles with this invalid value
                cursor.execute(f"""
                    UPDATE articles
                    SET {field} = %s
                    WHERE {field} = %s
                """, (valid_value, invalid_value))

                updated = cursor.rowcount
                total_updated += updated

                if updated > 0:
                    logger.info(f"  ✅ Updated {updated:,} articles: {field} '{invalid_value}' → '{valid_value}'")

        conn.commit()
        logger.info(f"✅ Committed all changes to database")

    print(f"\n{'='*80}")
    print(f"✅ CLEANUP COMPLETE!")
    print(f"{'='*80}")
    print(f"📊 Total articles updated: {total_updated:,}")
    print(f"{'='*80}")


def main():
    """Main execution."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Clean up ontology artifacts (PostgreSQL)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze issues without making changes
  python scripts/cleanup_ontology_artifacts_postgres.py --analyze

  # Perform cleanup
  python scripts/cleanup_ontology_artifacts_postgres.py --execute
        """
    )
    parser.add_argument('--analyze', action='store_true',
                       help='Analyze issues without making changes (default behavior)')
    parser.add_argument('--execute', action='store_true',
                       help='Actually perform the cleanup')

    args = parser.parse_args()

    # Default to analyze mode if neither flag is specified
    if not args.execute:
        args.analyze = True

    try:
        logger.info("="*80)
        logger.info("Ontology Artifacts Cleanup Script (PostgreSQL)")
        logger.info("="*80)
        logger.info(f"Mode: {'EXECUTE' if args.execute else 'ANALYZE (DRY RUN)'}")
        logger.info(f"Database: {db_settings.DB_NAME} @ {db_settings.DB_HOST}:{db_settings.DB_PORT}")
        logger.info("="*80)

        conn = get_postgres_connection()
        cleanup_artifacts(conn, dry_run=not args.execute)
        conn.close()

        logger.info("\n✅ Script completed successfully!")

    except Exception as e:
        logger.error(f"❌ Error during cleanup: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
