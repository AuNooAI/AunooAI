from fastapi import APIRouter, Depends, HTTPException
from app.security.session import verify_session
from app.services.auspex_service import get_auspex_service
from app.services.auspex_tools import get_auspex_tools_service

router = APIRouter(prefix="/api/test", tags=["Test"])

@router.get("/auspex-tools")
async def test_auspex_tools(session=Depends(verify_session)):
    """Test Auspex tools functionality."""
    tools = get_auspex_tools_service()
    
    results = {}
    
    # Test topic articles
    try:
        result = await tools.get_topic_articles('technology', limit=5)
        results['topic_articles'] = {
            'success': 'error' not in result,
            'article_count': result.get('total_articles', 0),
            'error': result.get('error')
        }
    except Exception as e:
        results['topic_articles'] = {'success': False, 'error': str(e)}
    
    # Test sentiment analysis
    try:
        result = await tools.analyze_sentiment_trends('technology', 'month')
        results['sentiment_analysis'] = {
            'success': 'error' not in result,
            'article_count': result.get('total_articles', 0),
            'error': result.get('error')
        }
    except Exception as e:
        results['sentiment_analysis'] = {'success': False, 'error': str(e)}
    
    # Test categories
    try:
        result = await tools.get_article_categories('technology')
        results['categories'] = {
            'success': 'error' not in result,
            'category_count': len(result.get('category_distribution', {})),
            'error': result.get('error')
        }
    except Exception as e:
        results['categories'] = {'success': False, 'error': str(e)}
    
    return {
        'status': 'completed',
        'tools_tested': 3,
        'results': results
    }

@router.get("/auspex-chat-sessions")
async def test_chat_sessions(session=Depends(verify_session)):
    """Test Auspex chat session functionality."""
    auspex = get_auspex_service()
    user_id = session.get('user')
    
    try:
        # Get existing sessions
        sessions = auspex.get_chat_sessions(user_id=user_id, limit=10)
        
        return {
            'status': 'completed',
            'user_id': user_id,
            'session_count': len(sessions),
            'sessions': sessions[:3]  # Just show first 3 for brevity
        }
    except Exception as e:
        return {
            'status': 'error',
            'error': str(e)
        }

@router.post("/create-test-chat")
async def create_test_chat(session=Depends(verify_session)):
    """Create a test chat session."""
    auspex = get_auspex_service()
    user_id = session.get('user')
    
    try:
        # Create test chat
        chat_id = await auspex.create_chat_session(
            topic='technology',
            user_id=user_id,
            title='Test Chat Session'
        )
        
        return {
            'status': 'success',
            'chat_id': chat_id,
            'topic': 'technology',
            'title': 'Test Chat Session'
        }
    except Exception as e:
        return {
            'status': 'error',
            'error': str(e)
        }

@router.get("/test-news-api")
async def test_news_api():
    """Test TheNewsAPI connectivity and configuration."""
    try:
        from app.services.auspex_tools import get_auspex_tools_service
        
        tools = get_auspex_tools_service()
        
        # Test a simple search
        result = await tools.search_news(
            query="AI technology",
            max_results=5,
            days_back=1
        )
        
        return {
            "status": "success" if 'error' not in result else "error",
            "message": "TheNewsAPI is working correctly" if 'error' not in result else f"TheNewsAPI error: {result.get('error')}",
            "results_count": result.get('total_results', 0),
            "sample_result": result.get('articles', [])[:1] if result.get('articles') else None,
            "api_configured": True
        }
        
    except ValueError as e:
        if "not configured" in str(e):
            return {
                "status": "error",
                "message": "TheNewsAPI key not configured. Please set PROVIDER_THENEWSAPI_API_KEY environment variable.",
                "api_configured": False
            }
        else:
            return {
                "status": "error", 
                "message": f"Configuration error: {str(e)}",
                "api_configured": False
            }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Unexpected error: {str(e)}",
            "api_configured": False
        } 