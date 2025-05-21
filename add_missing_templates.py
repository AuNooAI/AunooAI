#!/usr/bin/env python3
"""
Script to add missing templates for the newsletter compiler.

This script directly adds the missing templates for key_charts and latest_podcast
to the database, which are needed for the newsletter compiler to function properly.
"""

import sqlite3
import json
import os
import sys
from datetime import datetime

def check_template_exists(cursor, content_type_id):
    """Check if a template with the given content_type_id already exists."""
    cursor.execute(
        "SELECT COUNT(*) FROM newsletter_prompt_templates WHERE content_type_id = ?",
        (content_type_id,)
    )
    return cursor.fetchone()[0] > 0

def add_template(cursor, template_data):
    """Add a template to the database if it doesn't already exist."""
    content_type_id = template_data["content_type_id"]
    
    # Check if the template already exists
    if check_template_exists(cursor, content_type_id):
        print(f"Template for {content_type_id} already exists, skipping...")
        return False
    
    # Add the template
    cursor.execute(
        """
        INSERT INTO newsletter_prompt_templates 
        (content_type_id, prompt_template, description, last_updated)
        VALUES (?, ?, ?, ?)
        """,
        (
            content_type_id,
            template_data["prompt_template"],
            template_data["description"],
            template_data["last_updated"]
        )
    )
    return True

def main():
    # Define the database path
    db_path = "aunooai.db"
    
    # Check if file exists
    if not os.path.exists(db_path):
        print(f"Database file {db_path} not found.")
        sys.exit(1)
    
    # Define templates to add
    templates = [
        {
            "content_type_id": "key_charts",
            "prompt_template": "Generate informative charts showing sentiment trends and future signals for '{topic}'.",
            "description": "Prompt template for generating chart descriptions and insights for data visualizations",
            "last_updated": datetime.now().isoformat()
        },
        {
            "content_type_id": "latest_podcast",
            "prompt_template": "Summarize the transcript of this podcast about '{topic}', highlighting key insights and takeaways in 2-3 concise paragraphs.",
            "description": "Prompt template for summarizing podcast content related to the topic",
            "last_updated": datetime.now().isoformat()
        }
    ]
    
    try:
        # Connect to the database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if the table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='newsletter_prompt_templates'"
        )
        table_exists = cursor.fetchone() is not None
        
        # Create the table if it doesn't exist
        if not table_exists:
            print("Creating newsletter_prompt_templates table...")
            cursor.execute(
                """
                CREATE TABLE newsletter_prompt_templates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content_type_id TEXT NOT NULL UNIQUE,
                    prompt_template TEXT NOT NULL,
                    description TEXT,
                    last_updated TEXT NOT NULL
                )
                """
            )
        
        # Add templates
        templates_added = 0
        for template in templates:
            if add_template(cursor, template):
                templates_added += 1
                print(f"Added template for {template['content_type_id']}")
        
        # Commit changes and close connection
        conn.commit()
        conn.close()
        
        print(f"Successfully added {templates_added} missing templates to the database.")
        print("The newsletter compiler should now show the Visual Elements and Media tabs correctly.")
        
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 