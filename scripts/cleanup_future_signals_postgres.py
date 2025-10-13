#!/usr/bin/env python3
"""
PostgreSQL cleanup script for invalid future_signal values.

This script maps invalid/shortened future_signal values to their correct equivalents
based on semantic meaning and the current topic configuration.

Usage:
    python scripts/cleanup_future_signals_postgres.py --analyze  # Analyze issues only
    python scripts/cleanup_future_signals_postgres.py --execute  # Perform cleanup
"""

import sys
import os
import logging
from collections import defaultdict
import psycopg2
from psycopg2.extras import execute_batch

# Add app directory to path
sys.path.insert(0, os.path.abspath('.'))

from app.config.settings import load_config, db_settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Mapping of invalid future_signal values to their correct equivalents
# Based on semantic analysis of the shortened versions from AI responses
SIGNAL_MAPPING = {
    # AI and Machine Learning topic mappings (shortened → full)
    'Acceleration': 'AI will accelerate',
    'Gradual Evolution': 'AI will evolve gradually',
    'Disruption': 'AI will accelerate',  # Disruption implies rapid acceleration
    'Hype': 'AI is hype',
    'Plateau': 'AI has plateaued',

    # Invalid values that are actually driver_types, sentiment, or time_to_impact
    # These should be set to 'Other' as they're fundamentally wrong
    'Delayer': 'Other',
    'Blocker': 'Other',
    'Accelerator': 'Other',
    'Catalyst': 'Other',
    'Initiator': 'Other',
    'Terminator': 'Other',
    'Critical': 'Other',
    'Negative': 'Other',
    'Neutral': 'Other',
    'Positive': 'Other',
    'Hyperbolic': 'Other',
    'Long-term': 'Other',
    'Short-term': 'Other',
    'Mid-term': 'Other',
    'Immediate': 'Other',

    # Variations with markdown artifacts
    '** Acceleration': 'AI will accelerate',
    '** Gradual Evolution': 'AI will evolve gradually',
    '** Disruption': 'AI will accelerate',
    '** Hype': 'AI is hype',
    '** Plateau': 'AI has plateaued',

    # Typos
    'Acceleraton': 'AI will accelerate',

    # Edge cases - invalid signals that don't map to any defined value
    'Caution': 'Other',
    'Speculative': 'Other',
    'Stability': 'Other',
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


def get_topic_valid_signals():
    """Load valid future signals for each topic from config."""
    config = load_config()
    topic_signals = {}

    for topic in config.get('topics', []):
        topic_name = topic.get('name')
        future_signals = topic.get('future_signals', [])
        if topic_name and future_signals:
            topic_signals[topic_name] = set(future_signals)
            logger.info(f"Topic '{topic_name}' has {len(future_signals)} valid signals: {future_signals}")

    return topic_signals


def analyze_invalid_signals(conn):
    """Analyze all articles with invalid future_signal values."""
    topic_signals = get_topic_valid_signals()

    if not topic_signals:
        logger.error("No topic configurations found!")
        return {}, {}

    invalid_stats = defaultdict(lambda: defaultdict(int))
    mapping_stats = defaultdict(lambda: defaultdict(int))
    total_invalid = 0

    with conn.cursor() as cursor:
        # Get all articles with future_signal values
        cursor.execute("""
            SELECT topic, future_signal, COUNT(*) as count
            FROM articles
            WHERE future_signal IS NOT NULL
              AND future_signal <> ''
              AND analyzed = true
            GROUP BY topic, future_signal
            ORDER BY topic, count DESC
        """)

        results = cursor.fetchall()
        logger.info(f"Analyzing {len(results)} distinct future_signal values across all topics...")

        for topic, future_signal, count in results:
            # Check if topic has valid signals defined
            if topic not in topic_signals:
                logger.warning(f"Topic '{topic}' not found in config")
                invalid_stats['unknown_topic'][future_signal] += count
                continue

            # Check if the signal is valid for this topic (allow "Other" as fallback)
            if future_signal not in topic_signals[topic] and future_signal != "Other":
                invalid_stats[topic][future_signal] += count
                total_invalid += count

                # Check if we have a mapping for this invalid value
                if future_signal in SIGNAL_MAPPING:
                    mapped_value = SIGNAL_MAPPING[future_signal]
                    mapping_stats[topic][f"{future_signal} → {mapped_value}"] += count

    return invalid_stats, mapping_stats, total_invalid


def print_analysis_report(invalid_stats, mapping_stats, total_invalid):
    """Print a detailed analysis report."""
    print("\n" + "="*80)
    print("📊 FUTURE SIGNAL CLEANUP ANALYSIS REPORT (PostgreSQL)")
    print("="*80)
    print(f"🔍 Total articles with invalid future_signal values: {total_invalid:,}")

    # Invalid signals by topic
    if invalid_stats:
        print(f"\n❌ Invalid signals by topic:")
        for topic, signals in sorted(invalid_stats.items()):
            topic_total = sum(signals.values())
            print(f"\n  📁 Topic: {topic} ({topic_total:,} articles)")
            for signal, count in sorted(signals.items(), key=lambda x: x[1], reverse=True):
                mapped = f" → {SIGNAL_MAPPING[signal]}" if signal in SIGNAL_MAPPING else " [NO MAPPING]"
                print(f"    • '{signal}': {count:,} articles{mapped}")

    # Mapping preview
    if mapping_stats:
        print(f"\n🔄 Proposed mappings:")
        for topic, mappings in sorted(mapping_stats.items()):
            print(f"\n  📁 Topic: {topic}")
            for mapping, count in sorted(mappings.items(), key=lambda x: x[1], reverse=True):
                print(f"    • {mapping}: {count:,} articles")

    # Unmapped signals
    unmapped = []
    for topic, signals in invalid_stats.items():
        for signal in signals:
            if signal not in SIGNAL_MAPPING:
                unmapped.append(signal)

    if unmapped:
        print(f"\n⚠️  Signals without mappings (will be skipped):")
        for signal in sorted(set(unmapped)):
            print(f"    • '{signal}'")


def cleanup_invalid_signals(conn, dry_run=True):
    """Clean up invalid future_signal values using intelligent mapping."""
    invalid_stats, mapping_stats, total_invalid = analyze_invalid_signals(conn)

    if total_invalid == 0:
        logger.info("✅ No invalid future_signal values found. Database is clean!")
        return

    print_analysis_report(invalid_stats, mapping_stats, total_invalid)

    if dry_run:
        print(f"\n{'='*80}")
        print(f"🔍 [DRY RUN] Would clean up {total_invalid:,} articles")
        print(f"Run with --execute flag to perform actual cleanup")
        print(f"{'='*80}")
        return

    # Perform cleanup
    print(f"\n{'='*80}")
    print(f"🧹 Cleaning up {total_invalid:,} articles...")
    print(f"{'='*80}")

    total_updated = 0
    total_skipped = 0

    with conn.cursor() as cursor:
        # Process each invalid signal → valid signal mapping
        for invalid_signal, valid_signal in SIGNAL_MAPPING.items():
            # Check if any articles have this invalid signal
            cursor.execute("""
                SELECT COUNT(*) FROM articles
                WHERE future_signal = %s
                  AND analyzed = true
            """, (invalid_signal,))

            count = cursor.fetchone()[0]
            if count == 0:
                continue

            # Update articles with this invalid signal
            cursor.execute("""
                UPDATE articles
                SET future_signal = %s,
                    future_signal_explanation = CASE
                        WHEN future_signal_explanation LIKE '%%VALIDATION ERROR%%'
                        THEN 'Corrected from: ' || %s || '. ' || future_signal_explanation
                        ELSE 'Corrected from: ' || %s || '. ' || COALESCE(future_signal_explanation, '')
                    END
                WHERE future_signal = %s
                  AND analyzed = true
            """, (valid_signal, invalid_signal, invalid_signal, invalid_signal))

            updated = cursor.rowcount
            total_updated += updated

            if updated > 0:
                logger.info(f"  ✅ Updated {updated:,} articles: '{invalid_signal}' → '{valid_signal}'")

        conn.commit()
        logger.info(f"✅ Committed all changes to database")

    print(f"\n{'='*80}")
    print(f"✅ CLEANUP COMPLETE!")
    print(f"{'='*80}")
    print(f"📊 Total articles updated: {total_updated:,}")
    print(f"📊 Total articles skipped: {total_skipped:,}")
    print(f"{'='*80}")


def main():
    """Main execution."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Clean up invalid future_signal values (PostgreSQL)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze issues without making changes
  python scripts/cleanup_future_signals_postgres.py --analyze

  # Perform cleanup
  python scripts/cleanup_future_signals_postgres.py --execute
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
        logger.info("Future Signal Cleanup Script (PostgreSQL)")
        logger.info("="*80)
        logger.info(f"Mode: {'EXECUTE' if args.execute else 'ANALYZE (DRY RUN)'}")
        logger.info(f"Database: {db_settings.DB_NAME} @ {db_settings.DB_HOST}:{db_settings.DB_PORT}")
        logger.info("="*80)

        conn = get_postgres_connection()
        cleanup_invalid_signals(conn, dry_run=not args.execute)
        conn.close()

        logger.info("\n✅ Script completed successfully!")

    except Exception as e:
        logger.error(f"❌ Error during cleanup: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
