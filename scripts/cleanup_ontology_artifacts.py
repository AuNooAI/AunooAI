#!/usr/bin/env python3
"""
Database Cleanup Script for Ontology Artifacts

This script identifies and optionally cleans up articles in the database that contain
ontology values (categories, future_signals, sentiments, time_to_impact, driver_types)
that don't match the current topic configuration.

Usage:
    python scripts/cleanup_ontology_artifacts.py --analyze   # Just analyze issues
    python scripts/cleanup_ontology_artifacts.py --clean     # Clean up issues
    python scripts/cleanup_ontology_artifacts.py --reprocess # Re-process articles with correct ontology
"""

import os
import sys
import argparse
import json
from typing import Dict, List, Set, Any, Optional
from datetime import datetime

# Add app directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.database import Database
from app.config.config import load_config
from app.services.automated_ingest_service import AutomatedIngestService

class OntologyCleanup:
    """Tool for cleaning up ontology artifacts in the database"""
    
    def __init__(self):
        self.db = Database()
        self.config = load_config()
        self.topic_ontologies = {topic['name']: topic for topic in self.config['topics']}
        
    def get_valid_ontology_values(self, topic: str) -> Dict[str, Set[str]]:
        """Get valid ontology values for a topic"""
        if topic not in self.topic_ontologies:
            return {}
        
        topic_config = self.topic_ontologies[topic]
        return {
            'categories': set(topic_config.get('categories', [])),
            'future_signals': set(topic_config.get('future_signals', [])),
            'sentiment': set(topic_config.get('sentiment', [])),
            'time_to_impact': set(topic_config.get('time_to_impact', [])),
            'driver_types': set(topic_config.get('driver_types', []))
        }
    
    def analyze_ontology_issues(self) -> Dict[str, Any]:
        """Analyze the database for ontology issues"""
        print("🔍 Analyzing database for ontology issues...")
        
        results = {
            'total_articles': 0,
            'articles_with_issues': 0,
            'auto_ingested_articles': 0,
            'auto_ingested_with_issues': 0,
            'issues_by_topic': {},
            'issue_details': [],
            'most_common_invalid_values': {}
        }
        
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get all articles with ontology data
            cursor.execute("""
                SELECT uri, title, topic, category, future_signal, sentiment, 
                       time_to_impact, driver_type, auto_ingested, submission_date
                FROM articles 
                WHERE (category IS NOT NULL AND category != '') 
                   OR (future_signal IS NOT NULL AND future_signal != '')
                   OR (sentiment IS NOT NULL AND sentiment != '')
                   OR (time_to_impact IS NOT NULL AND time_to_impact != '')
                   OR (driver_type IS NOT NULL AND driver_type != '')
                ORDER BY submission_date DESC
            """)
            
            articles = cursor.fetchall()
            results['total_articles'] = len(articles)
            
            invalid_values = {
                'categories': {},
                'future_signals': {},
                'sentiment': {},
                'time_to_impact': {},
                'driver_types': {}
            }
            
            for article in articles:
                uri, title, topic, category, future_signal, sentiment, time_to_impact, driver_type, auto_ingested, submission_date = article
                
                if auto_ingested:
                    results['auto_ingested_articles'] += 1
                
                if not topic:
                    # Can't validate without topic
                    continue
                
                # Get valid values for this topic
                valid_values = self.get_valid_ontology_values(topic)
                if not valid_values:
                    print(f"⚠️ Unknown topic '{topic}' for article: {uri}")
                    continue
                
                # Check each ontology field
                issues = []
                
                if category and category not in valid_values['categories']:
                    issues.append(f"Invalid category: '{category}'")
                    invalid_values['categories'][category] = invalid_values['categories'].get(category, 0) + 1
                
                if future_signal and future_signal not in valid_values['future_signals']:
                    issues.append(f"Invalid future_signal: '{future_signal}'")
                    invalid_values['future_signals'][future_signal] = invalid_values['future_signals'].get(future_signal, 0) + 1
                
                if sentiment and sentiment not in valid_values['sentiment']:
                    issues.append(f"Invalid sentiment: '{sentiment}'")
                    invalid_values['sentiment'][sentiment] = invalid_values['sentiment'].get(sentiment, 0) + 1
                
                if time_to_impact and time_to_impact not in valid_values['time_to_impact']:
                    issues.append(f"Invalid time_to_impact: '{time_to_impact}'")
                    invalid_values['time_to_impact'][time_to_impact] = invalid_values['time_to_impact'].get(time_to_impact, 0) + 1
                
                if driver_type and driver_type not in valid_values['driver_types']:
                    issues.append(f"Invalid driver_type: '{driver_type}'")
                    invalid_values['driver_types'][driver_type] = invalid_values['driver_types'].get(driver_type, 0) + 1
                
                if issues:
                    results['articles_with_issues'] += 1
                    if auto_ingested:
                        results['auto_ingested_with_issues'] += 1
                    
                    # Track by topic
                    if topic not in results['issues_by_topic']:
                        results['issues_by_topic'][topic] = 0
                    results['issues_by_topic'][topic] += 1
                    
                    results['issue_details'].append({
                        'uri': uri,
                        'title': title[:100] + '...' if len(title) > 100 else title,
                        'topic': topic,
                        'auto_ingested': bool(auto_ingested),
                        'submission_date': str(submission_date),
                        'issues': issues
                    })
            
            # Sort most common invalid values
            for field, values in invalid_values.items():
                if values:
                    results['most_common_invalid_values'][field] = sorted(
                        values.items(), key=lambda x: x[1], reverse=True
                    )[:10]  # Top 10 most common
        
        return results
    
    def print_analysis_report(self, results: Dict[str, Any]):
        """Print a detailed analysis report"""
        print("\n" + "="*80)
        print("📊 ONTOLOGY CLEANUP ANALYSIS REPORT")
        print("="*80)
        print(f"📚 Total articles analyzed: {results['total_articles']:,}")
        print(f"❌ Articles with ontology issues: {results['articles_with_issues']:,}")
        print(f"🤖 Auto-ingested articles: {results['auto_ingested_articles']:,}")
        print(f"⚠️ Auto-ingested with issues: {results['auto_ingested_with_issues']:,}")
        
        if results['articles_with_issues'] > 0:
            percentage = (results['articles_with_issues'] / results['total_articles']) * 100
            print(f"📈 Percentage with issues: {percentage:.1f}%")
        
        # Issues by topic
        if results['issues_by_topic']:
            print(f"\n📝 Issues by Topic:")
            for topic, count in sorted(results['issues_by_topic'].items(), key=lambda x: x[1], reverse=True):
                print(f"  • {topic}: {count:,} articles")
        
        # Most common invalid values
        print(f"\n🚨 Most Common Invalid Values:")
        for field, values in results['most_common_invalid_values'].items():
            if values:
                print(f"  {field.replace('_', ' ').title()}:")
                for value, count in values[:5]:  # Top 5
                    print(f"    • '{value}': {count:,} occurrences")
        
        # Sample problematic articles
        if results['issue_details']:
            print(f"\n📋 Sample Problematic Articles (first 10):")
            for i, article in enumerate(results['issue_details'][:10]):
                print(f"  {i+1}. {article['title']}")
                print(f"     Topic: {article['topic']} | Auto-ingested: {article['auto_ingested']}")
                print(f"     Issues: {'; '.join(article['issues'])}")
                print(f"     URI: {article['uri']}")
                print()
    
    def clean_invalid_values(self, dry_run: bool = True) -> Dict[str, Any]:
        """Clean invalid ontology values from the database"""
        action = "DRY RUN - Would clean" if dry_run else "Cleaning"
        print(f"🧹 {action} invalid ontology values...")
        
        results = {
            'cleaned_articles': 0,
            'fields_cleaned': {
                'category': 0,
                'future_signal': 0,
                'sentiment': 0,
                'time_to_impact': 0,
                'driver_type': 0
            }
        }
        
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get all articles with ontology data
            cursor.execute("""
                SELECT uri, topic, category, future_signal, sentiment, time_to_impact, driver_type
                FROM articles 
                WHERE topic IS NOT NULL
                  AND ((category IS NOT NULL AND category != '') 
                       OR (future_signal IS NOT NULL AND future_signal != '')
                       OR (sentiment IS NOT NULL AND sentiment != '')
                       OR (time_to_impact IS NOT NULL AND time_to_impact != '')
                       OR (driver_type IS NOT NULL AND driver_type != ''))
            """)
            
            articles = cursor.fetchall()
            
            for article in articles:
                uri, topic, category, future_signal, sentiment, time_to_impact, driver_type = article
                
                # Get valid values for this topic
                valid_values = self.get_valid_ontology_values(topic)
                if not valid_values:
                    continue
                
                # Check what needs to be cleaned
                updates = []
                params = []
                
                if category and category not in valid_values['categories']:
                    updates.append("category = NULL")
                    results['fields_cleaned']['category'] += 1
                
                if future_signal and future_signal not in valid_values['future_signals']:
                    updates.append("future_signal = NULL")
                    results['fields_cleaned']['future_signal'] += 1
                
                if sentiment and sentiment not in valid_values['sentiment']:
                    updates.append("sentiment = NULL")
                    results['fields_cleaned']['sentiment'] += 1
                
                if time_to_impact and time_to_impact not in valid_values['time_to_impact']:
                    updates.append("time_to_impact = NULL")
                    results['fields_cleaned']['time_to_impact'] += 1
                
                if driver_type and driver_type not in valid_values['driver_types']:
                    updates.append("driver_type = NULL")
                    results['fields_cleaned']['driver_type'] += 1
                
                if updates:
                    results['cleaned_articles'] += 1
                    
                    if not dry_run:
                        # Actually perform the update
                        update_sql = f"UPDATE articles SET {', '.join(updates)} WHERE uri = ?"
                        cursor.execute(update_sql, (uri,))
            
            if not dry_run:
                conn.commit()
                print(f"✅ Committed changes to database")
        
        return results
    
    def reprocess_articles(self, max_articles: int = None, dry_run: bool = True) -> Dict[str, Any]:
        """Re-process articles with correct ontology using the automated ingest service"""
        action = "DRY RUN - Would reprocess" if dry_run else "Reprocessing"
        print(f"🔄 {action} articles with correct ontology...")
        
        results = {
            'reprocessed_articles': 0,
            'successful_reprocessing': 0,
            'failed_reprocessing': 0,
            'errors': []
        }
        
        if dry_run:
            print("This would:")
            print("1. Identify articles with invalid ontology values")
            print("2. Re-run the analysis with correct topic-specific ontology")
            print("3. Update the database with corrected values")
            return results
        
        # Initialize the automated ingest service
        ingest_service = AutomatedIngestService(self.db)
        
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get articles that need reprocessing
            cursor.execute("""
                SELECT uri, title, summary, news_source, topic, category, future_signal, 
                       sentiment, time_to_impact, driver_type
                FROM articles 
                WHERE topic IS NOT NULL
                  AND auto_ingested = 1
                  AND ((category IS NOT NULL AND category != '') 
                       OR (future_signal IS NOT NULL AND future_signal != '')
                       OR (sentiment IS NOT NULL AND sentiment != '')
                       OR (time_to_impact IS NOT NULL AND time_to_impact != '')
                       OR (driver_type IS NOT NULL AND driver_type != ''))
                ORDER BY submission_date DESC
                LIMIT ?
            """, (max_articles or 1000,))
            
            articles = cursor.fetchall()
            
            for article in articles:
                uri, title, summary, news_source, topic, category, future_signal, sentiment, time_to_impact, driver_type = article
                
                # Check if this article has invalid values
                valid_values = self.get_valid_ontology_values(topic)
                if not valid_values:
                    continue
                
                has_invalid_values = (
                    (category and category not in valid_values['categories']) or
                    (future_signal and future_signal not in valid_values['future_signals']) or
                    (sentiment and sentiment not in valid_values['sentiment']) or
                    (time_to_impact and time_to_impact not in valid_values['time_to_impact']) or
                    (driver_type and driver_type not in valid_values['driver_types'])
                )
                
                if has_invalid_values:
                    results['reprocessed_articles'] += 1
                    
                    try:
                        # Create article data for reprocessing
                        article_data = {
                            'uri': uri,
                            'title': title,
                            'summary': summary,
                            'news_source': news_source,
                            'topic': topic
                        }
                        
                        # Re-analyze with correct ontology
                        updated_article = ingest_service.analyze_article_content(article_data)
                        
                        # Update database with corrected values
                        cursor.execute("""
                            UPDATE articles 
                            SET category = ?, sentiment = ?, future_signal = ?, 
                                future_signal_explanation = ?, sentiment_explanation = ?,
                                time_to_impact = ?, driver_type = ?, tags = ?, analyzed = ?
                            WHERE uri = ?
                        """, (
                            updated_article.get('category'),
                            updated_article.get('sentiment'),
                            updated_article.get('future_signal'),
                            updated_article.get('future_signal_explanation'),
                            updated_article.get('sentiment_explanation'),
                            updated_article.get('time_to_impact'),
                            updated_article.get('driver_type'),
                            updated_article.get('tags'),
                            updated_article.get('analyzed', True),
                            uri
                        ))
                        
                        results['successful_reprocessing'] += 1
                        print(f"✅ Reprocessed: {title[:50]}...")
                        
                    except Exception as e:
                        error_msg = f"Failed to reprocess {uri}: {str(e)}"
                        results['errors'].append(error_msg)
                        results['failed_reprocessing'] += 1
                        print(f"❌ {error_msg}")
            
            conn.commit()
        
        return results

def main():
    parser = argparse.ArgumentParser(description='Clean up ontology artifacts in the database')
    parser.add_argument('--analyze', action='store_true', help='Analyze ontology issues')
    parser.add_argument('--clean', action='store_true', help='Clean invalid ontology values')
    parser.add_argument('--reprocess', action='store_true', help='Re-process articles with correct ontology')
    parser.add_argument('--dry-run', action='store_true', help='Perform dry run (no actual changes)')
    parser.add_argument('--max-articles', type=int, help='Maximum articles to process (default: 1000)')
    
    args = parser.parse_args()
    
    if not any([args.analyze, args.clean, args.reprocess]):
        parser.print_help()
        return
    
    cleanup = OntologyCleanup()
    
    if args.analyze:
        results = cleanup.analyze_ontology_issues()
        cleanup.print_analysis_report(results)
    
    if args.clean:
        results = cleanup.clean_invalid_values(dry_run=args.dry_run)
        print(f"\n🧹 Cleanup Results:")
        print(f"  Cleaned articles: {results['cleaned_articles']:,}")
        print(f"  Fields cleaned:")
        for field, count in results['fields_cleaned'].items():
            if count > 0:
                print(f"    • {field}: {count:,} instances")
    
    if args.reprocess:
        results = cleanup.reprocess_articles(
            max_articles=args.max_articles, 
            dry_run=args.dry_run
        )
        print(f"\n🔄 Reprocessing Results:")
        print(f"  Articles reprocessed: {results['reprocessed_articles']:,}")
        print(f"  Successful: {results['successful_reprocessing']:,}")
        print(f"  Failed: {results['failed_reprocessing']:,}")
        if results['errors']:
            print(f"  Errors: {len(results['errors'])}")

if __name__ == "__main__":
    main() 