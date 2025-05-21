#!/usr/bin/env python3
"""Script to import media bias data and update articles with bias info."""

import os
import sys
import logging
import argparse
from typing import Tuple

# Add app directory to path
sys.path.insert(0, os.path.abspath('.'))

from app.database import get_database_instance
from app.models.media_bias import MediaBias

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def import_media_bias_data(csv_file: str) -> Tuple[int, int]:
    """Import media bias data from CSV file.
    
    Args:
        csv_file: Path to the CSV file with media bias data
        
    Returns:
        Tuple with count of (imported items, failed items)
    """
    logger.info(f"Importing media bias data from {csv_file}")
    
    # Get database connection
    db = get_database_instance()
    
    # Create MediaBias instance
    media_bias = MediaBias(db)
    
    # Import data from CSV
    imported_count, failed_count = media_bias.import_from_csv(csv_file)
    
    logger.info(
        f"Media bias data import completed. "
        f"Imported: {imported_count}, Failed: {failed_count}"
    )
    return imported_count, failed_count


def update_articles_with_bias(sample_size: int = 0) -> Tuple[int, int, int]:
    """Update articles with media bias data.
    
    Args:
        sample_size: Optional limit on number of articles to process (0 for all)
        
    Returns:
        Tuple with count of (processed articles, matched articles, no-match articles)
    """
    logger.info("Updating articles with media bias data")
    
    # Get database connection
    db = get_database_instance()
    
    # Create MediaBias instance
    media_bias = MediaBias(db)
    
    processed_count = 0
    matched_count = 0
    no_match_count = 0
    
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get articles to process
            if sample_size > 0:
                cursor.execute(
                    "SELECT uri, news_source FROM articles LIMIT ?", 
                    (sample_size,)
                )
            else:
                cursor.execute("SELECT uri, news_source FROM articles")
                
            articles = cursor.fetchall()
            total_articles = len(articles)
            logger.info(f"Found {total_articles} articles to process")
            
            # Process each article
            for i, (uri, source) in enumerate(articles, 1):
                if i % 100 == 0:
                    logger.info(
                        f"Progress: {i}/{total_articles} articles processed"
                    )
                
                processed_count += 1
                
                if not source:
                    no_match_count += 1
                    continue
                
                # Get media bias for this source
                bias_data = media_bias.get_bias_for_source(source)
                
                if bias_data:
                    # Update article with bias data
                    update_query = """
                        UPDATE articles SET
                            bias = ?,
                            factual_reporting = ?,
                            mbfc_credibility_rating = ?,
                            bias_source = ?,
                            bias_country = ?,
                            press_freedom = ?,
                            media_type = ?,
                            popularity = ?
                        WHERE uri = ?
                    """
                    
                    cursor.execute(update_query, (
                        bias_data.get('bias', ''),
                        bias_data.get('factual_reporting', ''),
                        bias_data.get('mbfc_credibility_rating', ''),
                        bias_data.get('source', ''),
                        bias_data.get('country', ''),
                        bias_data.get('press_freedom', ''),
                        bias_data.get('media_type', ''),
                        bias_data.get('popularity', ''),
                        uri
                    ))
                    
                    matched_count += 1
                else:
                    no_match_count += 1
            
            conn.commit()
            
    except Exception as e:
        logger.error(f"Error updating articles with bias data: {str(e)}")
        raise
    
    logger.info(
        f"Article update completed. Processed: {processed_count}, "
        f"Matched: {matched_count}, No Match: {no_match_count}"
    )
    
    return processed_count, matched_count, no_match_count


def update_research_save_article():
    """Register a hook to enrich articles with media bias data on save."""
    logger.info("Registering media bias enrichment for new articles")
    
    # Get database connection and MediaBias instance
    db = get_database_instance()
    media_bias = MediaBias(db)
    
    # Enable media bias enrichment
    result = media_bias.set_enabled(True)
    logger.info(f"Media bias enrichment enabled: {result}")


def analyze_bias_distribution():
    """Analyze and display statistics about bias distribution in articles."""
    logger.info("Analyzing media bias distribution in articles")
    
    # Get database connection
    db = get_database_instance()
    
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get total article count
            cursor.execute("SELECT COUNT(*) FROM articles")
            total_articles = cursor.fetchone()[0]
            
            # Count articles with bias data
            cursor.execute(
                "SELECT COUNT(*) FROM articles "
                "WHERE bias IS NOT NULL AND bias != ''"
            )
            articles_with_bias = cursor.fetchone()[0]
            
            bias_percentage = 0
            if total_articles > 0:
                bias_percentage = (articles_with_bias / total_articles) * 100
            
            logger.info(
                f"Articles with bias data: {articles_with_bias}/{total_articles} "
                f"({bias_percentage:.2f}%)"
            )
            
            # Get bias distribution
            cursor.execute("""
                SELECT bias, COUNT(*) as count 
                FROM articles 
                WHERE bias IS NOT NULL AND bias != '' 
                GROUP BY bias 
                ORDER BY count DESC
            """)
            bias_distribution = cursor.fetchall()
            
            if bias_distribution:
                logger.info("Bias distribution:")
                for bias, count in bias_distribution:
                    percentage = (
                        (count / articles_with_bias) * 100 
                        if articles_with_bias > 0 else 0
                    )
                    logger.info(f"  - {bias}: {count} ({percentage:.2f}%)")
            
            # Get factual reporting distribution
            cursor.execute("""
                SELECT factual_reporting, COUNT(*) as count 
                FROM articles 
                WHERE factual_reporting IS NOT NULL AND factual_reporting != '' 
                GROUP BY factual_reporting 
                ORDER BY count DESC
            """)
            factual_distribution = cursor.fetchall()
            
            if factual_distribution:
                logger.info("Factual reporting distribution:")
                for factual, count in factual_distribution:
                    percentage = (
                        (count / articles_with_bias) * 100
                        if articles_with_bias > 0 else 0
                    )
                    logger.info(f"  - {factual}: {count} ({percentage:.2f}%)")
    
    except Exception as e:
        logger.error(f"Error analyzing bias distribution: {str(e)}")


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description="Import media bias data and update articles"
    )
    parser.add_argument(
        "--csv", 
        default="mbfc_raw.csv", 
        help="Path to CSV file with media bias data"
    )
    parser.add_argument(
        "--import-only", 
        action="store_true", 
        help="Only import data, don't update articles"
    )
    parser.add_argument(
        "--update-only", 
        action="store_true", 
        help="Only update articles, don't import data"
    )
    parser.add_argument(
        "--sample", 
        type=int, 
        default=0, 
        help="Limit number of articles to update (0 for all)"
    )
    parser.add_argument(
        "--analyze", 
        action="store_true", 
        help="Analyze bias distribution after update"
    )
    
    args = parser.parse_args()
    
    try:
        # Import media bias data
        if not args.update_only:
            import_media_bias_data(args.csv)
        
        # Update articles with bias data
        if not args.import_only:
            update_articles_with_bias(args.sample)
        
        # Register hook for new articles
        update_research_save_article()
        
        # Analyze bias distribution
        if args.analyze:
            analyze_bias_distribution()
            
        logger.info("Media bias data integration completed successfully")
        
    except Exception as e:
        logger.error(f"Error integrating media bias data: {str(e)}")
        return 1
        
    return 0


if __name__ == "__main__":
    sys.exit(main()) 