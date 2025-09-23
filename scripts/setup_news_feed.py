#!/usr/bin/env python3
"""
Setup script for the daily news feed system.
Creates necessary database tables and sets up cron jobs.
"""

import sys
import os
import sqlite3
import logging
from datetime import datetime

# Add the app directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.database import get_database_instance
from app.tasks.news_feed_scheduler import NewsFeedScheduler

def setup_database():
    """Create necessary database tables for news feed system"""
    
    print("Setting up database tables for news feed system...")
    
    db = get_database_instance()
    
    # Create daily_news_feeds table
    create_feeds_table = """
    CREATE TABLE IF NOT EXISTS daily_news_feeds (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        topic TEXT NOT NULL,
        feed_date DATE NOT NULL,
        overview_data TEXT NOT NULL,
        six_articles_data TEXT NOT NULL,
        generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        processing_time_seconds REAL,
        model_used TEXT,
        UNIQUE(topic, feed_date)
    );
    """
    
    # Create index for efficient lookups
    create_index = """
    CREATE INDEX IF NOT EXISTS idx_feeds_topic_date 
    ON daily_news_feeds(topic, feed_date DESC);
    """
    
    try:
        db.execute(create_feeds_table)
        db.execute(create_index)
        print("✓ Database tables created successfully")
        return True
    except Exception as e:
        print(f"✗ Error creating database tables: {e}")
        return False


def create_cron_jobs():
    """Create sample cron job configurations"""
    
    print("\nCreating sample cron job configurations...")
    
    # Get the absolute path to the project directory
    project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    python_path = sys.executable
    
    cron_jobs = f"""
# Daily News Feed Generation - runs at 6:00 AM every day
0 6 * * * cd {project_dir} && {python_path} -m app.tasks.news_feed_scheduler --action generate

# Weekly cleanup of old feeds - runs at 2:00 AM every Sunday
0 2 * * 0 cd {project_dir} && {python_path} -m app.tasks.news_feed_scheduler --action cleanup --cleanup-days 30

# Example: Generate specific topic feed at 8:00 AM
# 0 8 * * * cd {project_dir} && {python_path} -m app.tasks.news_feed_scheduler --action generate --topic "artificial intelligence"
"""
    
    cron_file_path = os.path.join(project_dir, 'cron_jobs_news_feed.txt')
    
    try:
        with open(cron_file_path, 'w') as f:
            f.write(cron_jobs.strip())
        
        print(f"✓ Sample cron jobs saved to: {cron_file_path}")
        print("\nTo install these cron jobs, run:")
        print(f"  crontab {cron_file_path}")
        print("\nTo view current cron jobs:")
        print("  crontab -l")
        
        return True
    except Exception as e:
        print(f"✗ Error creating cron jobs file: {e}")
        return False


def test_news_feed_generation():
    """Test the news feed generation system"""
    
    print("\nTesting news feed generation...")
    
    try:
        import asyncio
        from app.schemas.news_feed import NewsFeedRequest
        from app.services.news_feed_service import get_news_feed_service
        
        async def test_generation():
            db = get_database_instance()
            service = get_news_feed_service(db)
            
            # Test with a small request
            request = NewsFeedRequest(
                topic="technology",
                max_articles=10,
                model="gpt-4o"
            )
            
            print("  Generating test overview...")
            articles_data = await service._get_articles_for_date(
                datetime.now().replace(hour=0, minute=0, second=0, microsecond=0),
                10,
                "technology"
            )
            
            if articles_data:
                print(f"  ✓ Found {len(articles_data)} articles for testing")
                
                # Test overview generation (quick test)
                overview = await service._generate_overview(articles_data[:5], datetime.now(), request)
                print(f"  ✓ Generated overview with {len(overview.top_stories)} stories")
                
                return True
            else:
                print("  ⚠ No articles found for testing - this is normal for a fresh installation")
                print("  ⚠ Add some articles first, then test the news feed generation")
                return True
        
        result = asyncio.run(test_generation())
        return result
        
    except Exception as e:
        print(f"  ✗ Error testing news feed generation: {e}")
        print(f"  This might be due to missing API keys or no articles in database")
        return False


def main():
    """Main setup function"""
    
    print("=" * 60)
    print("Daily News Feed System Setup")
    print("=" * 60)
    
    # Configure logging
    logging.basicConfig(level=logging.WARNING)  # Reduce noise during setup
    
    success_count = 0
    total_steps = 3
    
    # Step 1: Setup database
    if setup_database():
        success_count += 1
    
    # Step 2: Create cron jobs
    if create_cron_jobs():
        success_count += 1
    
    # Step 3: Test generation (optional)
    print("\nTesting news feed generation (optional)...")
    if test_news_feed_generation():
        success_count += 1
    else:
        print("  Note: Testing failed, but setup can continue")
    
    # Summary
    print("\n" + "=" * 60)
    print(f"Setup completed: {success_count}/{total_steps} steps successful")
    print("=" * 60)
    
    if success_count >= 2:  # Database and cron jobs are essential
        print("\n✓ News feed system is ready to use!")
        print("\nNext steps:")
        print("1. Access the news feed at: http://localhost:8000/news-feed")
        print("2. Set up cron jobs for automated generation")
        print("3. Ensure you have articles in your database")
        print("4. Configure AI model API keys in your environment")
        
        print("\nAPI Endpoints:")
        print("- GET /api/news-feed/daily - Generate full daily feed")
        print("- GET /api/news-feed/overview - Generate overview only")
        print("- GET /api/news-feed/six-articles - Generate detailed report")
        print("- GET /api/news-feed/markdown/overview - Get markdown format")
        
        print("\nManual generation:")
        print("python -m app.tasks.news_feed_scheduler --action generate")
        
    else:
        print("\n⚠ Setup completed with issues. Please check the errors above.")
    
    return success_count >= 2


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
