#!/usr/bin/env python
"""
Script to directly check the database for newsletter prompt templates.
"""
import os
import sqlite3
import json
import sys

def get_database_path():
    """Get the path to the SQLite database file."""
    db_dir = os.path.join(os.getcwd(), "db")
    os.makedirs(db_dir, exist_ok=True)
    
    # Look for existing .db files in the current directory
    db_files = [f for f in os.listdir() if f.endswith('.db')]
    
    if db_files:
        return db_files[0]  # Return the first one found
    else:
        # Look in the db directory
        db_files = [f for f in os.listdir(db_dir) if f.endswith('.db')]
        if db_files:
            return os.path.join(db_dir, db_files[0])
    
    # Fallback to default
    return "aunooai.db"

def check_database():
    """Check what's in the database."""
    db_path = get_database_path()
    print(f"Using database: {db_path}")
    
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row  # This enables column access by name
        cursor = conn.cursor()
        
        # Check if newsletter_prompts table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='newsletter_prompts'")
        if not cursor.fetchone():
            print("newsletter_prompts table does not exist!")
            sys.exit(1)
        
        # Get all templates
        cursor.execute("SELECT * FROM newsletter_prompts")
        rows = cursor.fetchall()
        
        print(f"Found {len(rows)} templates in the database:")
        
        templates = []
        for row in rows:
            template = {
                "content_type_id": row["content_type_id"],
                "prompt_template": row["prompt_template"],
                "description": row["description"],
                "last_updated": row["last_updated"]
            }
            templates.append(template)
            print(f"- {template['content_type_id']}")
        
        # Print as JSON for easy copying
        print("\nJSON representation:")
        print(json.dumps(templates, indent=2))
        
        conn.close()
        
    except Exception as e:
        print(f"Error checking database: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    check_database() 