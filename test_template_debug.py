#!/usr/bin/env python3

import sqlite3
import sys
import os

# Add the app directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

def test_template_data():
    """Test what data would be passed to the template"""
    
    # Connect to the database
    db_path = "app/data/fnaapp.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("=== Testing Template Data Structure ===")
    
    # Simulate the exact query from keyword_alerts_page function (CORRECTED)
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
        WHERE ka.group_id = 34 AND ka.is_read = 0
        ORDER BY ka.detected_at DESC
        LIMIT 5
    """)
    
    alerts = cursor.fetchall()
    print(f"Found {len(alerts)} alerts using the template query")
    
    # Wait, I think there's an issue with the query structure
    # Let me check the actual table structure
    print("\n=== Checking Table Structure ===")
    
    # Check keyword_article_matches structure
    cursor.execute("PRAGMA table_info(keyword_article_matches)")
    kam_columns = cursor.fetchall()
    print("keyword_article_matches columns:")
    for col in kam_columns:
        print(f"  {col[1]} ({col[2]})")
    
    # The issue might be that keyword_article_matches doesn't have keyword_id!
    # Let me check the correct query
    print("\n=== Testing Correct Query ===")
    
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
        WHERE ka.group_id = 34 AND ka.is_read = 0
        ORDER BY ka.detected_at DESC
        LIMIT 5
    """)
    
    alerts = cursor.fetchall()
    print(f"Found {len(alerts)} alerts using the corrected query")
    
    for i, alert in enumerate(alerts):
        alert_id, article_uri = alert[0], alert[1]
        title = alert[6]
        
        print(f"\nAlert {i+1} (ID: {alert_id}):")
        print(f"  Title: {title[:50]}...")
        print(f"  URI: {article_uri}")
        
        # Check for enrichment data
        cursor.execute("""
            SELECT category, sentiment
            FROM articles 
            WHERE uri = ?
        """, (article_uri,))
        
        enrichment_row = cursor.fetchone()
        if enrichment_row:
            category, sentiment = enrichment_row
            if category:
                print(f"  ✓ HAS CATEGORY: '{category}'")
                print(f"  Template should show: 'Added' badge")
            else:
                print(f"  ✗ No category")
                print(f"  Template should show: 'New' badge")
        else:
            print(f"  ✗ No enrichment data")
            print(f"  Template should show: 'New' badge")
    
    conn.close()

if __name__ == "__main__":
    test_template_data() 