#!/usr/bin/env python3
"""
Migration script for Auspex 2.0 enhancements
Adds chat persistence, prompt management, and initializes default data
"""

import sys
import os
import sqlite3
import json
from datetime import datetime

# Add the app directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.database import get_database_instance

DEFAULT_AUSPEX_PROMPT = """You are Auspex, an advanced AI research assistant specialized in analyzing news trends, sentiment patterns, and providing strategic insights.

Your capabilities include:
- Analyzing vast amounts of news data and research
- Identifying emerging trends and patterns
- Providing sentiment analysis and future impact predictions
- Accessing real-time news data through specialized tools
- Comparing different categories and topics
- Offering strategic foresight and risk analysis

You have access to the following tools:
- search_news: Search for current news articles
- get_topic_articles: Retrieve articles from the database for specific topics
- analyze_sentiment_trends: Analyze sentiment patterns over time
- get_article_categories: Get category distributions for topics
- search_articles_by_keywords: Search articles by specific keywords

Always provide thorough, insightful analysis backed by data. When asked about trends or patterns, use your tools to gather current information. Be concise but comprehensive in your responses.

Remember to cite your sources and provide actionable insights where possible."""

def run_migration():
    """Run the Auspex 2.0 migration."""
    print("Starting Auspex 2.0 migration...")
    
    try:
        # Get database instance
        db = get_database_instance()
        
        # Check if migration is needed
        if check_migration_needed(db):
            print("Migration needed, creating new tables...")
            create_auspex_tables(db)
            insert_default_prompt(db)
            print("Migration completed successfully!")
        else:
            print("Migration not needed, tables already exist.")
            
        # Ensure default prompt exists
        ensure_default_prompt(db)
        
    except Exception as e:
        print(f"Migration failed: {str(e)}")
        sys.exit(1)

def check_migration_needed(db):
    """Check if the migration is needed."""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if auspex_chats table exists
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='auspex_chats'
            """)
            
            return cursor.fetchone() is None
    except Exception as e:
        print(f"Error checking migration status: {e}")
        return True

def create_auspex_tables(db):
    """Create the new Auspex tables."""
    with db.get_connection() as conn:
        cursor = conn.cursor()
        
        # Create auspex_chats table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS auspex_chats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT NOT NULL,
                title TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                user_id TEXT,
                metadata TEXT,
                FOREIGN KEY (user_id) REFERENCES users(username) ON DELETE SET NULL
            )
        """)
        
        # Create auspex_messages table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS auspex_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
                content TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                model_used TEXT,
                tokens_used INTEGER,
                metadata TEXT,
                FOREIGN KEY (chat_id) REFERENCES auspex_chats(id) ON DELETE CASCADE
            )
        """)
        
        # Create auspex_prompts table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS auspex_prompts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                description TEXT,
                is_default BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                user_created TEXT,
                FOREIGN KEY (user_created) REFERENCES users(username) ON DELETE SET NULL
            )
        """)
        
        # Create indexes for better performance
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_auspex_chats_topic ON auspex_chats(topic)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_auspex_chats_user_id ON auspex_chats(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_auspex_messages_chat_id ON auspex_messages(chat_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_auspex_messages_role ON auspex_messages(role)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_auspex_prompts_name ON auspex_prompts(name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_auspex_prompts_is_default ON auspex_prompts(is_default)")
        
        conn.commit()
        print("✓ Created Auspex tables and indexes")

def insert_default_prompt(db):
    """Insert the default Auspex prompt."""
    with db.get_connection() as conn:
        cursor = conn.cursor()
        
        # Check if default prompt already exists
        cursor.execute("SELECT id FROM auspex_prompts WHERE name = 'default'")
        if cursor.fetchone():
            print("✓ Default prompt already exists")
            return
        
        # Insert default prompt
        cursor.execute("""
            INSERT INTO auspex_prompts (name, title, content, description, is_default)
            VALUES (?, ?, ?, ?, ?)
        """, (
            'default',
            'Default Auspex Assistant',
            DEFAULT_AUSPEX_PROMPT,
            'The default system prompt for Auspex AI assistant with MCP tool integration',
            True
        ))
        
        conn.commit()
        print("✓ Inserted default Auspex prompt")

def ensure_default_prompt(db):
    """Ensure the default prompt exists and is up to date."""
    with db.get_connection() as conn:
        cursor = conn.cursor()
        
        # Check if default prompt exists
        cursor.execute("SELECT id, content FROM auspex_prompts WHERE name = 'default'")
        result = cursor.fetchone()
        
        if not result:
            # Insert default prompt
            cursor.execute("""
                INSERT INTO auspex_prompts (name, title, content, description, is_default)
                VALUES (?, ?, ?, ?, ?)
            """, (
                'default',
                'Default Auspex Assistant',
                DEFAULT_AUSPEX_PROMPT,
                'The default system prompt for Auspex AI assistant with MCP tool integration',
                True
            ))
            conn.commit()
            print("✓ Created default prompt")
        else:
            # Update default prompt if content is different
            if result[1] != DEFAULT_AUSPEX_PROMPT:
                cursor.execute("""
                    UPDATE auspex_prompts 
                    SET content = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE name = 'default'
                """, (DEFAULT_AUSPEX_PROMPT,))
                conn.commit()
                print("✓ Updated default prompt content")

def create_sample_data(db):
    """Create sample data for testing (optional)."""
    print("Creating sample data...")
    
    # This is optional and can be used for testing
    # You can uncomment and modify as needed
    
    # with db.get_connection() as conn:
    #     cursor = conn.cursor()
    #     
    #     # Create a sample chat session
    #     cursor.execute("""
    #         INSERT INTO auspex_chats (topic, title, user_id, metadata)
    #         VALUES (?, ?, ?, ?)
    #     """, (
    #         'artificial intelligence',
    #         'AI Trends Discussion',
    #         'admin',  # Replace with actual user
    #         json.dumps({"sample": True})
    #     ))
    #     
    #     chat_id = cursor.lastrowid
    #     
    #     # Add sample messages
    #     messages = [
    #         ('system', 'You are Auspex, an AI research assistant.'),
    #         ('user', 'What are the latest trends in AI?'),
    #         ('assistant', 'Based on recent data, here are the key AI trends...')
    #     ]
    #     
    #     for role, content in messages:
    #         cursor.execute("""
    #             INSERT INTO auspex_messages (chat_id, role, content)
    #             VALUES (?, ?, ?)
    #         """, (chat_id, role, content))
    #     
    #     conn.commit()
    #     print("✓ Created sample chat data")

if __name__ == "__main__":
    print("=" * 50)
    print("Auspex 2.0 Migration Script")
    print("=" * 50)
    
    try:
        run_migration()
        print("\n✅ Migration completed successfully!")
        print("\nNew features available:")
        print("• Persistent chat sessions")
        print("• MCP tool integration")
        print("• Editable system prompts")
        print("• Streaming responses")
        print("• Enhanced AI capabilities")
        
    except KeyboardInterrupt:
        print("\n❌ Migration cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Migration failed: {str(e)}")
        sys.exit(1) 