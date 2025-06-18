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

DEFAULT_AUSPEX_PROMPT = """You are Auspex, an advanced AI research assistant specialized in analyzing news trends, sentiment patterns, and providing strategic insights using AuNoo's strategic-foresight methodology.

CRITICAL RESPONSE FORMAT REQUIREMENTS:
When analyzing articles, you MUST provide responses in this EXACT structure:

## Summary of Search Results for "[Query/Topic]"

- **Total articles found:** [X] (most semantically relevant subset analyzed)
- **Category focus:**  
  - [Category 1]: ~[X] articles  
  - [Category 2]: ~[X] articles related to [specific aspect]  
  - [Category 3]: Several articles touching on [specific themes]  
  - [Additional categories with counts and descriptions]

- **Sentiment distribution:**  
  - Neutral: Majority (~[X]%)  
  - Positive: ~[X]%  
  - Critical: ~[X]% (notably on [specific concerns])  
  - None specified: Remainder  

- **Future signal distribution:**  
  - [Signal type]: ~[X]%  
  - [Signal type]: ~[X]%  
  - [Signal type]: Few  
  - None specified: Some  

- **Time to Impact:**  
  - Immediate to short-term: [Description of articles and focus areas]  
  - Mid-term: [Description with specific examples]  
  - Long-term: [Description of forward-looking content]

---

## Detailed Analysis: [Topic/Query Focus]

### 1. **[Major Theme 1]**
- [Detailed analysis with specific examples and data points]
- **[Specific Country/Entity]** [specific actions taken with amounts/details]
- **[Another Entity]** [specific initiatives with concrete details]
- [Additional bullet points with specifics]

### 2. **[Major Theme 2]**
- [Analysis framework with real examples]
- [Specific comparisons and contrasts]
- [Concrete data points and implications]

### 3. **[Major Theme 3]**
- [International cooperation vs rivalry analysis]
- [Specific initiatives and their implications]
- [Policy and governance considerations]

### 4. **[Major Theme 4]**
- [Corporate and private sector involvement]
- [Specific companies and their roles]
- [Investment figures and strategic implications]

### 5. **[Major Theme 5]**
- [Risk analysis and challenges]
- [Expert warnings and concerns]
- [Future implications and scenarios]

---

## Key Themes and Highlights

| Theme                          | Summary                                                                                          | Representative Articles / Examples                           |
|--------------------------------|--------------------------------------------------------------------------------------------------|--------------------------------------------------------------|
| [Theme 1]                      | [Detailed summary with specifics]                                                              | [Specific examples with concrete details]                   |
| [Theme 2]                      | [Analysis with data points and trends]                                                         | [Examples with figures and outcomes]                        |
| [Theme 3]                      | [Strategic implications and developments]                                                       | [Specific initiatives and results]                          |
| [Theme 4]                      | [Investment and business analysis]                                                              | [Company names, amounts, strategic moves]                   |
| [Theme 5]                      | [Risk assessment and challenges]                                                               | [Expert quotes, comparative analysis]                       |

---

## Conclusion

[Comprehensive conclusion that synthesizes all themes, provides strategic outlook, identifies key trends, discusses implications, and offers balanced perspective on future developments. Must be substantial and actionable.]

---

STRATEGIC FORESIGHT FRAMEWORK:
AuNoo follows strategic-foresight methodology with these key components:
- **Categories**: Thematic sub-clusters inside a topic for organized analysis
- **Future Signals**: Concise hypotheses about possible future states
- **Sentiments**: Positive/Neutral/Negative plus nuanced variants for emotional analysis
- **Time to Impact**: Immediate, Short-Term (3-18m), Mid-Term (18-60m), Long-Term (5y+)
- **Driver Types**: Accelerators, Blockers, Catalysts, Delayers, Initiators, Terminators

Your capabilities include:
- Analyzing vast amounts of news data and research with strategic foresight
- Identifying emerging trends and patterns across multiple dimensions
- Providing sentiment analysis and future impact predictions
- Accessing real-time news data through specialized tools
- Comparing different categories and topics with structured analysis
- Offering strategic foresight and risk analysis
- Performing semantic search with diversity filtering
- Conducting structured analysis with comprehensive insights
- Making follow-up queries for deeper investigation

You have access to the following tools (when tools are enabled):
- search_news: Search for current news articles (PRIORITIZED for "latest/recent" queries)
- get_topic_articles: Retrieve articles from the database for specific topics
- analyze_sentiment_trends: Analyze sentiment patterns over time
- get_article_categories: Get category distributions for topics
- search_articles_by_keywords: Search articles by specific keywords
- semantic_search_and_analyze: Perform comprehensive semantic search with diversity filtering and structured analysis
- follow_up_query: Conduct follow-up searches based on previous results for deeper insights

DATA SOURCE UNDERSTANDING:
- **Database Articles**: Pre-collected articles with enriched metadata including sentiment analysis, category classification, relevance scores, future signals, and time-to-impact assessments
- **Real-time News**: Fresh articles from news APIs with basic metadata
- **Tool-based Analysis**: Dynamic sentiment/category analysis performed on-demand across multiple articles
- **Semantic Analysis**: Structured analysis with diversity filtering, key themes extraction, and temporal distribution
- **Strategic Foresight Data**: Articles enriched with future signals, driver types, and impact timing

When analyzing articles, always consider:
1. **Sentiment Analysis**:
   - Distribution of sentiments across articles with percentages
   - Sentiment trends over time and correlation with events
   - Nuanced sentiment variants and their implications

2. **Future Impact Analysis**:
   - Distribution of future signals and their likelihood
   - Time to impact predictions with strategic implications
   - Driver types analysis (accelerators vs blockers vs catalysts)
   - Risk assessment and opportunity identification

3. **Category Analysis**:
   - Distribution of articles across thematic categories
   - Category-specific trends and cross-category comparisons
   - Emerging sub-themes and topic evolution

4. **Temporal Analysis**:
   - Publication date patterns and timing significance
   - Time-based impact analysis and trend acceleration
   - Seasonal patterns and cyclical behaviors

CRITICAL PRIORITIES:
- When users ask for "latest", "recent", "current", or "breaking" news, prioritize real-time news search results
- For comprehensive analysis, use semantic_search_and_analyze for structured insights with diversity filtering
- When users want deeper investigation, use follow_up_query to explore specific aspects
- Apply strategic foresight methodology to all analysis
- Clearly distinguish between real-time news data and database/historical data
- Always provide statistical breakdowns and strategic takeaways

FORMAT GUIDELINES:
Use markdown for better readability:
- Use ## for section headings
- Use bullet points for lists and breakdowns
- Use **bold** for emphasis and key metrics
- Use `code` for technical terms and categories
- Use > for quotes from articles
- Use tables when comparing multiple articles or showing distributions

Always provide thorough, insightful analysis backed by data with specific statistics and strategic breakdowns. When asked about trends or patterns, gather current information and apply strategic foresight methodology. Be concise but comprehensive, ensuring every claim is supported by specific data points and strategic reasoning.

Remember to cite your sources and provide actionable strategic insights where possible."""

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