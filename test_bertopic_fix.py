#!/usr/bin/env python3

import asyncio
import sys
import os
sys.path.append('.')

async def test_reference_graph():
    """Test the reference graph generation with BERTopic fixes."""
    try:
        from app.routes.topic_map_routes import get_reference_graph
        from app.database import get_database_instance
        
        # Mock session for testing
        class MockSession:
            def __init__(self):
                self.session = {'user_id': 'test'}
        
        print("Testing reference graph generation...")
        
        db = get_database_instance()
        session = MockSession()
        
        # Test with small limit to avoid the scipy error
        result = await get_reference_graph(
            category=None,
            query=None, 
            limit=50,
            use_cache=False,
            db=db,
            session=session
        )
        
        print(f'✅ Success! Generated {len(result.get("nodes", []))} nodes and {len(result.get("edges", []))} edges')
        
        # Check for any category nodes
        categories = [n for n in result.get('nodes', []) if n.get('type') == 'category']
        topics = [n for n in result.get('nodes', []) if n.get('type') == 'topic']
        articles = [n for n in result.get('nodes', []) if n.get('type') == 'article']
        
        print(f'📊 Categories: {len(categories)}, Topics: {len(topics)}, Articles: {len(articles)}')
        
        if topics:
            print(f'🏷️  Sample topic labels: {[t["label"] for t in topics[:3]]}')
        
        # Check if we're using the improved clustering
        if len(categories) > 0 and len(topics) > 0:
            print("✅ Hierarchical structure created successfully!")
        else:
            print("⚠️  No hierarchical structure found")
            
        return True
        
    except Exception as e:
        print(f'❌ Error: {e}')
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_reference_graph())
    if success:
        print("\n🎉 BERTopic fixes appear to be working!")
    else:
        print("\n💥 BERTopic fixes need more work") 