#!/usr/bin/env python3

import sqlite3
import sys
import os

# Add the app directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

def test_enrichment_detection():
    """Test if enrichment detection is working correctly"""
    
    # Connect to the database
    db_path = "app/data/fnaapp.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("=== Testing Enrichment Detection ===")
    
    # Test 1: Check if we have enriched articles
    cursor.execute("""
        SELECT COUNT(*) FROM articles 
        WHERE category IS NOT NULL AND category != ''
    """)
    enriched_count = cursor.fetchone()[0]
    print(f"Total enriched articles: {enriched_count}")
    
    # Test 2: Check if we have keyword alerts for enriched articles
    cursor.execute("""
        SELECT COUNT(*) 
        FROM keyword_article_matches kam 
        JOIN articles a ON kam.article_uri = a.uri 
        WHERE a.category IS NOT NULL AND a.category != ''
    """)
    enriched_alerts_count = cursor.fetchone()[0]
    print(f"Keyword alerts for enriched articles: {enriched_alerts_count}")
    
    # Test 3: Get a specific example
    cursor.execute("""
        SELECT kam.id, a.uri, a.title, a.category, a.sentiment
        FROM keyword_article_matches kam 
        JOIN articles a ON kam.article_uri = a.uri 
        WHERE a.category IS NOT NULL AND a.category != ''
        LIMIT 3
    """)
    
    examples = cursor.fetchall()
    print(f"\nExample enriched articles in keyword alerts:")
    for alert_id, uri, title, category, sentiment in examples:
        print(f"  Alert ID: {alert_id}")
        print(f"  Title: {title[:60]}...")
        print(f"  Category: {category}")
        print(f"  Sentiment: {sentiment}")
        print(f"  URI: {uri}")
        print()
    
    # Test 4: Simulate the exact query from the backend
    print("=== Simulating Backend Query ===")
    
    # Get a group ID that has alerts
    cursor.execute("""
        SELECT group_id, COUNT(*) as alert_count
        FROM keyword_article_matches 
        GROUP BY group_id 
        ORDER BY alert_count DESC 
        LIMIT 1
    """)
    
    group_result = cursor.fetchone()
    if group_result:
        group_id, alert_count = group_result
        print(f"Testing with group {group_id} ({alert_count} alerts)")
        
        # Simulate the exact backend query
        cursor.execute("""
            SELECT 
                ka.id, 
                ka.article_uri,
                ka.keyword_ids,
                NULL as matched_keyword,
                ka.is_read,
                ka.detected_at,
                a.title,
                a.summary,
                a.uri,
                a.news_source,
                a.publication_date
            FROM keyword_article_matches ka
            JOIN articles a ON ka.article_uri = a.uri
            WHERE ka.group_id = ? AND ka.is_read = 0
            ORDER BY ka.detected_at DESC
            LIMIT 5
        """, (group_id,))
        
        alerts = cursor.fetchall()
        print(f"Found {len(alerts)} unread alerts for group {group_id}")
        
        for alert in alerts:
            alert_id, article_uri = alert[0], alert[1]
            title = alert[6]
            
            # Now check for enrichment data (simulating the backend logic)
            cursor.execute("""
                SELECT category, sentiment
                FROM articles 
                WHERE uri = ?
            """, (article_uri,))
            
            enrichment_row = cursor.fetchone()
            if enrichment_row:
                category, sentiment = enrichment_row
                if category:
                    print(f"  ✓ Alert {alert_id}: HAS CATEGORY '{category}'")
                    print(f"    Title: {title[:50]}...")
                else:
                    print(f"  ✗ Alert {alert_id}: No category")
            else:
                print(f"  ✗ Alert {alert_id}: No enrichment data")
    
    conn.close()

if __name__ == "__main__":
    test_enrichment_detection() 