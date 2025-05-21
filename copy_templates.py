#!/usr/bin/env python3
"""
Script to copy newsletter prompt templates from aunooai.db to app/data/fnaapp.db.

This script copies all newsletter prompt templates from the source database
to the target database to ensure Visual Elements and Media tabs appear correctly.
"""

import sqlite3
import os
import logging
from datetime import datetime

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def copy_prompt_templates(source_db_path, target_db_path):
    """Copy prompt templates from source to target database."""
    
    # Make sure both database files exist
    if not os.path.exists(source_db_path):
        raise FileNotFoundError(f"Source database not found: {source_db_path}")
    
    if not os.path.exists(target_db_path):
        raise FileNotFoundError(f"Target database not found: {target_db_path}")
    
    logger.info(f"Copying templates from {source_db_path} to {target_db_path}")
    
    # Connect to source database
    with sqlite3.connect(source_db_path) as source_conn:
        source_cursor = source_conn.cursor()
        
        # Check which table exists in source db
        source_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND (name='newsletter_prompts' OR name='newsletter_prompt_templates')")
        source_tables = [row[0] for row in source_cursor.fetchall()]
        
        if not source_tables:
            logger.error("No prompt template tables found in source database")
            return False
        
        source_table = source_tables[0]
        logger.info(f"Using source table: {source_table}")
        
        # Get templates from source database
        source_cursor.execute(f"SELECT content_type_id, prompt_template, description, last_updated FROM {source_table}")
        templates = source_cursor.fetchall()
        
        if not templates:
            logger.warning("No templates found in source database")
            return False
        
        logger.info(f"Found {len(templates)} templates in source database")
    
    # Connect to target database
    with sqlite3.connect(target_db_path) as target_conn:
        target_cursor = target_conn.cursor()
        
        # Check which table exists in target db
        target_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND (name='newsletter_prompts' OR name='newsletter_prompt_templates')")
        target_tables = [row[0] for row in target_cursor.fetchall()]
        
        if not target_tables:
            # Create the table if it doesn't exist
            logger.info("Creating newsletter_prompt_templates table in target database")
            target_cursor.execute("""
                CREATE TABLE IF NOT EXISTS newsletter_prompt_templates (
                    content_type_id TEXT PRIMARY KEY,
                    prompt_template TEXT NOT NULL,
                    description TEXT NOT NULL,
                    last_updated TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            target_table = "newsletter_prompt_templates"
        else:
            target_table = target_tables[0]
        
        logger.info(f"Using target table: {target_table}")
        
        # Get existing templates in target
        target_cursor.execute(f"SELECT content_type_id FROM {target_table}")
        existing_ids = {row[0] for row in target_cursor.fetchall()}
        
        # Insert or update templates
        templates_added = 0
        templates_updated = 0
        
        for template in templates:
            content_type_id, prompt_template, description, last_updated = template
            
            if not last_updated:
                last_updated = datetime.now().isoformat()
                
            if content_type_id in existing_ids:
                # Update existing template
                target_cursor.execute(
                    f"""
                    UPDATE {target_table} 
                    SET prompt_template = ?, description = ?, last_updated = ?
                    WHERE content_type_id = ?
                    """,
                    (prompt_template, description, last_updated, content_type_id)
                )
                templates_updated += 1
                logger.info(f"Updated template: {content_type_id}")
            else:
                # Insert new template
                target_cursor.execute(
                    f"""
                    INSERT INTO {target_table} 
                    (content_type_id, prompt_template, description, last_updated)
                    VALUES (?, ?, ?, ?)
                    """,
                    (content_type_id, prompt_template, description, last_updated)
                )
                templates_added += 1
                logger.info(f"Added template: {content_type_id}")
        
        # Explicitly add key_charts and latest_podcast if they don't exist
        critical_templates = [
            (
                "key_charts",
                "Generate informative charts showing sentiment trends and future signals for '{topic}'.",
                "Prompt template for generating chart descriptions and insights for data visualizations",
                datetime.now().isoformat()
            ),
            (
                "latest_podcast",
                "Summarize the transcript of this podcast about '{topic}', highlighting key insights and takeaways in 2-3 concise paragraphs.",
                "Prompt template for summarizing podcast content related to the topic",
                datetime.now().isoformat()
            )
        ]
        
        for template in critical_templates:
            content_type_id, prompt_template, description, last_updated = template
            
            # Check if template exists
            target_cursor.execute(
                f"SELECT COUNT(*) FROM {target_table} WHERE content_type_id = ?",
                (content_type_id,)
            )
            exists = target_cursor.fetchone()[0] > 0
            
            if not exists:
                # Insert critical template
                target_cursor.execute(
                    f"""
                    INSERT INTO {target_table} 
                    (content_type_id, prompt_template, description, last_updated)
                    VALUES (?, ?, ?, ?)
                    """,
                    template
                )
                templates_added += 1
                logger.info(f"Added critical template: {content_type_id}")
        
        # Commit changes
        target_conn.commit()
        
        logger.info(f"Successfully processed templates: {templates_added} added, {templates_updated} updated")
        return True


def main():
    """Main function to copy templates between databases."""
    try:
        source_db_path = "aunooai.db"
        target_db_path = os.path.join("app", "data", "fnaapp.db")
        
        # Ensure target directory exists
        os.makedirs(os.path.join("app", "data"), exist_ok=True)
        
        success = copy_prompt_templates(source_db_path, target_db_path)
        
        if success:
            print(f"Successfully copied templates from {source_db_path} to {target_db_path}")
            print("The newsletter compiler should now show all tabs correctly.")
        else:
            print(f"Failed to copy templates from {source_db_path} to {target_db_path}")
            
    except Exception as e:
        logger.error(f"Error copying templates: {str(e)}")
        print(f"Error: {str(e)}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main()) 