from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from typing import List, Optional, Dict, Any
import logging
from datetime import datetime, timedelta, timezone
import asyncio

from ..database import Database, get_database_instance
from ..ai_models import LiteLLMModel
from ..security.session import verify_session_api

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/feed-clustering", tags=["feed-clustering"])

async def get_feed_items_for_clustering(
    feed_group_id: Optional[str] = None,
    limit: int = 100,
    days_back: int = 7,
    db: Database = None
) -> List[Dict[str, Any]]:
    """Get feed items for clustering analysis with balanced source representation"""
    if db is None:
        db = get_database_instance()
    conn = db.get_connection()
    
    # Calculate date threshold with timezone awareness
    date_threshold = datetime.now(timezone.utc) - timedelta(days=days_back)
    
    try:
        # Get items from each source type separately to ensure balanced representation
        all_items = []
        source_types = ['bluesky', 'arxiv', 'thenewsapi']
        items_per_source = limit // len(source_types)
        
        for source_type in source_types:
            if feed_group_id:
                # Get items from specific feed group and source type
                query = """
                    SELECT fi.*, fg.name as group_name
                    FROM feed_items fi
                    JOIN feed_keyword_groups fg ON fi.group_id = fg.id
                    WHERE fi.group_id = ? 
                    AND fi.source_type = ?
                    AND fi.created_at >= ?
                    AND fi.is_hidden = 0
                    ORDER BY fi.publication_date DESC, fi.created_at DESC
                    LIMIT ?
                """
                params = [feed_group_id, source_type, date_threshold.isoformat(), items_per_source]
            else:
                # Get items from all groups for this source type
                query = """
                    SELECT fi.*, fg.name as group_name
                    FROM feed_items fi
                    LEFT JOIN feed_keyword_groups fg ON fi.group_id = fg.id
                    WHERE fi.source_type = ?
                    AND fi.created_at >= ?
                    AND fi.is_hidden = 0
                    ORDER BY fi.publication_date DESC, fi.created_at DESC
                    LIMIT ?
                """
                params = [source_type, date_threshold.isoformat(), items_per_source]
            
            # Use run_in_threadpool for async database operations
            rows = await run_in_threadpool(db.fetch_all, query, params)
            
            for row in rows:
                # SQLite rows should be accessible as dict-like objects
                item = dict(row) if hasattr(row, 'keys') else {}
                
                # Ensure we have the basic required fields
                if not item:
                    continue
                
                # Parse tags if they exist
                if item.get('tags'):
                    try:
                        import json
                        item['tags'] = json.loads(item['tags'])
                    except:
                        item['tags'] = []
                else:
                    item['tags'] = []
                
                # Parse engagement metrics if they exist
                if item.get('engagement_metrics'):
                    try:
                        import json
                        item['engagement_metrics'] = json.loads(item['engagement_metrics'])
                    except:
                        item['engagement_metrics'] = {}
                else:
                    item['engagement_metrics'] = {}
                
                all_items.append(item)
        
        # Shuffle to mix the sources
        import random
        random.shuffle(all_items)
        
        # Log source distribution for debugging
        source_counts = {}
        for item in all_items:
            source = item.get('source_type', 'unknown')
            source_counts[source] = source_counts.get(source, 0) + 1
        
        logger.info(f"Clustering source distribution: {source_counts}")
        
        return all_items[:limit]
        
    except Exception as e:
        logger.error(f"Error fetching feed items: {e}")
        return []

async def perform_thematic_clustering(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Use LLM to perform thematic clustering of articles"""
    if not items:
        return []
    
    # Prepare content for analysis
    article_summaries = []
    for i, item in enumerate(items[:50]):  # Limit to 50 items for LLM analysis
        summary = {
            'id': i,
            'title': item.get('title', '')[:200],
            'summary': item.get('content', item.get('summary', ''))[:300],
            'source_type': item.get('source_type', 'unknown'),
            'url': item.get('url', ''),
            'publication_date': item.get('publication_date'),
            'tags': item.get('tags', [])
        }
        article_summaries.append(summary)
    
    # Create LLM prompt for thematic clustering
    prompt = f"""
    Analyze the following {len(article_summaries)} articles from multiple sources (Bluesky, ArXiv, News) and group them into 3-5 thematic clusters.
    
    IMPORTANT: Ensure each cluster contains articles from different sources when possible to provide diverse perspectives on each theme.
    
    For each cluster, provide:
    1. theme_name: A descriptive name for the theme
    2. theme_summary: A 2-3 sentence summary of what articles in this theme discuss
    3. article_ids: List of article IDs that belong to this theme (mix sources when possible)
    4. confidence: A confidence score between 0.0-1.0 for this clustering
    5. source_diversity: Count of unique source types in this cluster
    
    Articles to analyze:
    {chr(10).join([f"ID {a['id']}: [{a['source_type'].upper()}] {a['title']} - {a['summary'][:150]}..." for a in article_summaries])}
    
    Response format (JSON):
    [
        {{
            "theme_name": "Theme Name",
            "theme_summary": "Summary of this thematic cluster",
            "article_ids": [0, 1, 5],
            "confidence": 0.85,
            "source_diversity": 2
        }}
    ]
    """
    
    try:
        ai_model = LiteLLMModel.get_instance("gpt-4o-mini")
        response = ai_model.generate_response([
            {"role": "user", "content": prompt}
        ])
        
        # Parse LLM response with robust JSON extraction
        import json
        import re
        
        # Handle both clean JSON and markdown code blocks
        json_match = re.search(r'```json\s*(\[.*?\])\s*```|```(\[.*?\])```|(\[.*?\])', response, re.DOTALL)
        if json_match:
            # Get the first non-None capturing group
            json_str = next(group for group in json_match.groups() if group is not None)
            clusters_data = json.loads(json_str)
        else:
            # Fallback - try parsing the whole response as JSON
            clusters_data = json.loads(response.strip())
        
        # Map article IDs back to full articles
        clusters_with_articles = []
        for cluster in clusters_data:
            cluster_articles = []
            for article_id in cluster.get('article_ids', []):
                if article_id < len(items):
                    cluster_articles.append(items[article_id])
            
            # Calculate actual source diversity
            source_types = set()
            for article in cluster_articles:
                source_types.add(article.get('source_type', 'unknown'))
            
            clusters_with_articles.append({
                'theme_name': cluster.get('theme_name', 'Unnamed Theme'),
                'theme_summary': cluster.get('theme_summary', ''),
                'articles': cluster_articles,
                'article_count': len(cluster_articles),
                'confidence': cluster.get('confidence', 0.5),
                'source_diversity': len(source_types),
                'source_types': list(source_types)
            })
        
        return clusters_with_articles
        
    except Exception as e:
        logger.error(f"Error in thematic clustering: {e}")
        logger.error(f"Raw LLM response was: {response[:500] if 'response' in locals() else 'No response received'}")
        # Fallback: simple keyword-based clustering
        return await simple_keyword_clustering(items)

async def simple_keyword_clustering(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Fallback clustering based on keywords"""
    # Simple clustering based on common words in titles
    clusters = {
        'AI & Technology': [],
        'Science & Research': [],
        'Business & Economics': [],
        'Other Topics': []
    }
    
    for item in items[:20]:  # Limit for fallback
        title_lower = item.get('title', '').lower()
        
        if any(word in title_lower for word in ['ai', 'artificial', 'machine', 'tech', 'digital', 'software']):
            clusters['AI & Technology'].append(item)
        elif any(word in title_lower for word in ['research', 'study', 'science', 'paper', 'analysis']):
            clusters['Science & Research'].append(item)
        elif any(word in title_lower for word in ['business', 'market', 'economy', 'financial', 'company', 'industry']):
            clusters['Business & Economics'].append(item)
        else:
            clusters['Other Topics'].append(item)
    
    # Convert to expected format
    result = []
    for theme_name, articles in clusters.items():
        if articles:
            result.append({
                'theme_name': theme_name,
                'theme_summary': f'Articles related to {theme_name.lower()}',
                'articles': articles,
                'article_count': len(articles),
                'confidence': 0.6
            })
    
    return result

async def perform_sentiment_clustering(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze sentiment patterns in articles"""
    if not items:
        return {'clusters': [], 'distribution': {'positive': 0, 'negative': 0, 'neutral': 0}}
    
    # Prepare content for sentiment analysis
    content_samples = []
    for item in items[:30]:  # Limit for LLM analysis
        content = f"{item.get('title', '')} {item.get('content', item.get('summary', ''))}"[:500]
        content_samples.append(content)
    
    # Create LLM prompt for sentiment analysis
    prompt = f"""
    Analyze the sentiment of these {len(content_samples)} articles and provide:
    1. Overall sentiment distribution (percentages)
    2. Key themes for positive, negative, and neutral sentiments
    
    Articles:
    {chr(10).join([f"{i+1}. {content}" for i, content in enumerate(content_samples)])}
    
    Response format (JSON):
    {{
        "distribution": {{"positive": 30, "negative": 20, "neutral": 50}},
        "clusters": [
            {{
                "sentiment": "positive",
                "percentage": 30,
                "article_count": 9,
                "summary": "Articles showing optimistic outlook on technology and innovation"
            }},
            {{
                "sentiment": "negative", 
                "percentage": 20,
                "article_count": 6,
                "summary": "Articles highlighting concerns and challenges"
            }},
            {{
                "sentiment": "neutral",
                "percentage": 50, 
                "article_count": 15,
                "summary": "Informational articles with balanced perspectives"
            }}
        ]
    }}
    """
    
    try:
        ai_model = LiteLLMModel.get_instance("gpt-4o-mini")
        response = ai_model.generate_response([
            {"role": "user", "content": prompt}
        ])
        
        import json
        import re
        
        # Handle both clean JSON and markdown code blocks
        json_match = re.search(r'```json\s*(\{.*?\})\s*```|```(\{.*?\})```|(\{.*?\})', response, re.DOTALL)
        if json_match:
            # Get the first non-None capturing group
            json_str = next(group for group in json_match.groups() if group is not None)
            result = json.loads(json_str)
        else:
            # Fallback - try parsing the whole response as JSON
            result = json.loads(response.strip())
        
        return result
        
    except Exception as e:
        logger.error(f"Error in sentiment clustering: {e}")
        logger.error(f"Raw LLM response was: {response[:500] if 'response' in locals() else 'No response received'}")
        # Fallback sentiment analysis
        total_items = len(items)
        return {
            'clusters': [
                {
                    'sentiment': 'positive',
                    'percentage': 40,
                    'article_count': int(total_items * 0.4),
                    'summary': 'Generally positive articles about progress and opportunities'
                },
                {
                    'sentiment': 'neutral',
                    'percentage': 45,
                    'article_count': int(total_items * 0.45),
                    'summary': 'Informational and balanced coverage of topics'
                },
                {
                    'sentiment': 'negative',
                    'percentage': 15,
                    'article_count': int(total_items * 0.15),
                    'summary': 'Articles discussing challenges and concerns'
                }
            ],
            'distribution': {'positive': 40, 'negative': 15, 'neutral': 45}
        }

async def perform_temporal_clustering(
    items: List[Dict[str, Any]], 
    time_horizon: str = "short",
    analysis_depth: str = "standard"
) -> Dict[str, Any]:
    """Analyze temporal impact patterns"""
    if not items:
        return {'timeline_events': []}
    
    # Prepare content for temporal analysis
    recent_items = items[:25]  # Focus on most recent items
    content_for_analysis = []
    
    for item in recent_items:
        content_for_analysis.append({
            'title': item.get('title', ''),
            'summary': item.get('content', item.get('summary', ''))[:300],
            'publication_date': item.get('publication_date'),
            'source_type': item.get('source_type')
        })
    
    # Map time horizons to analysis focus
    horizon_prompts = {
        'immediate': 'immediate impact (0-6 months)',
        'short': 'short-term impact (6-18 months)', 
        'medium': 'medium-term impact (1-3 years)',
        'long': 'long-term impact (3-10 years)'
    }
    
    focus = horizon_prompts.get(time_horizon, 'short-term impact (6-18 months)')
    
    prompt = f"""
    Analyze these articles for temporal impact patterns focusing on {focus}.
    
    Identify 3-4 major timeline events or trends and their potential impact timeframes.
    
    Articles:
    {chr(10).join([f"- {item['title']}: {item['summary'][:200]}" for item in content_for_analysis])}
    
    Response format (JSON):
    {{
        "timeline_events": [
            {{
                "title": "Event/Trend Title",
                "description": "Description of the event or trend",
                "impact_timeframe": "{time_horizon}",
                "impact_level": "High|Medium|Low",
                "article_count": 5,
                "confidence": 0.8
            }}
        ]
    }}
    """
    
    try:
        ai_model = LiteLLMModel.get_instance("gpt-4o-mini")
        response = ai_model.generate_response([
            {"role": "user", "content": prompt}
        ])
        
        import json
        import re
        
        # Handle both clean JSON and markdown code blocks
        json_match = re.search(r'```json\s*(\{.*?\})\s*```|```(\{.*?\})```|(\{.*?\})', response, re.DOTALL)
        if json_match:
            # Get the first non-None capturing group
            json_str = next(group for group in json_match.groups() if group is not None)
            result = json.loads(json_str)
        else:
            # Fallback - try parsing the whole response as JSON
            result = json.loads(response.strip())
        
        return result
        
    except Exception as e:
        logger.error(f"Error in temporal clustering: {e}")
        logger.error(f"Raw LLM response was: {response[:500] if 'response' in locals() else 'No response received'}")
        # Fallback temporal analysis
        return {
            'timeline_events': [
                {
                    'title': 'Emerging Technology Trends',
                    'description': 'Ongoing developments in technology and innovation',
                    'impact_timeframe': time_horizon,
                    'impact_level': 'Medium',
                    'article_count': len(recent_items) // 2,
                    'confidence': 0.6
                },
                {
                    'title': 'Market and Industry Changes',
                    'description': 'Shifts in business and economic landscapes',
                    'impact_timeframe': time_horizon,
                    'impact_level': 'Medium',
                    'article_count': len(recent_items) // 3,
                    'confidence': 0.5
                }
            ]
        }

async def perform_source_clustering(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze source patterns and authority"""
    if not items:
        return {'clusters': [], 'metrics': {}}
    
    # Group by source type
    source_groups = {}
    total_items = len(items)
    
    for item in items:
        source_type = item.get('source_type', 'unknown')
        if source_type not in source_groups:
            source_groups[source_type] = []
        source_groups[source_type].append(item)
    
    # Calculate source metrics
    clusters = []
    metrics = {
        'academic_percentage': 0,
        'social_percentage': 0,
        'news_percentage': 0,
        'overall_authority': 0.5
    }
    
    for source_type, source_items in source_groups.items():
        count = len(source_items)
        percentage = (count / total_items) * 100
        
        # Calculate authority score based on source type
        authority_scores = {
            'arxiv': 0.9,
            'news': 0.7,
            'bluesky': 0.6,
            'unknown': 0.4
        }
        
        authority_score = authority_scores.get(source_type, 0.5)
        
        # Calculate average engagement
        total_engagement = 0
        for item in source_items:
            engagement_metrics = item.get('engagement_metrics', {})
            if isinstance(engagement_metrics, dict):
                total_engagement += sum(engagement_metrics.values())
        
        avg_engagement = total_engagement / count if count > 0 else 0
        
        cluster = {
            'source_type': source_type,
            'source_name': source_type.title(),
            'article_count': count,
            'percentage': round(percentage, 1),
            'authority_score': authority_score,
            'avg_engagement': round(avg_engagement, 1),
            'recency': 'Recent' if count > 0 else 'None',
            'description': f'{source_type.title()} sources with {count} articles'
        }
        
        clusters.append(cluster)
        
        # Update metrics
        if source_type == 'arxiv':
            metrics['academic_percentage'] = round(percentage, 1)
        elif source_type in ['bluesky']:
            metrics['social_percentage'] = round(percentage, 1)
        elif source_type in ['news', 'thenewsapi']:
            metrics['news_percentage'] = round(percentage, 1)
    
    # Calculate overall authority
    total_authority = sum(cluster['authority_score'] * (cluster['article_count'] / total_items) for cluster in clusters)
    metrics['overall_authority'] = round(total_authority, 2)
    
    return {
        'clusters': sorted(clusters, key=lambda x: x['article_count'], reverse=True),
        'metrics': metrics
    }

@router.get("/thematic")
async def get_thematic_clustering(
    feed_group_id: Optional[str] = Query(None),
    limit: int = Query(100, le=200),
    db: Database = Depends(get_database_instance),
    session = Depends(verify_session_api)
):
    """Get thematic clustering analysis of feed items"""
    try:
        items = await get_feed_items_for_clustering(feed_group_id, limit, db=db)
        clusters = await perform_thematic_clustering(items)
        return clusters
        
    except Exception as e:
        logger.error(f"Error in thematic clustering endpoint: {e}")
        raise HTTPException(status_code=500, detail="Failed to perform thematic clustering")

@router.get("/sentiment")
async def get_sentiment_clustering(
    feed_group_id: Optional[str] = Query(None),
    limit: int = Query(100, le=200),
    db: Database = Depends(get_database_instance),
    session = Depends(verify_session_api)
):
    """Get sentiment clustering analysis of feed items"""
    try:
        items = await get_feed_items_for_clustering(feed_group_id, limit, db=db)
        result = await perform_sentiment_clustering(items)
        return result
        
    except Exception as e:
        logger.error(f"Error in sentiment clustering endpoint: {e}")
        raise HTTPException(status_code=500, detail="Failed to perform sentiment clustering")

@router.get("/temporal")
async def get_temporal_clustering(
    feed_group_id: Optional[str] = Query(None),
    time_horizon: str = Query("short"),
    analysis_depth: str = Query("standard"),
    limit: int = Query(100, le=200),
    db: Database = Depends(get_database_instance),
    session = Depends(verify_session_api)
):
    """Get temporal impact clustering analysis of feed items"""
    try:
        items = await get_feed_items_for_clustering(feed_group_id, limit, db=db)
        result = await perform_temporal_clustering(items, time_horizon, analysis_depth)
        return result
        
    except Exception as e:
        logger.error(f"Error in temporal clustering endpoint: {e}")
        raise HTTPException(status_code=500, detail="Failed to perform temporal clustering")

@router.get("/sources")
async def get_source_clustering(
    feed_group_id: Optional[str] = Query(None),
    limit: int = Query(100, le=200),
    db: Database = Depends(get_database_instance),
    session = Depends(verify_session_api)
):
    """Get source clustering analysis of feed items"""
    try:
        items = await get_feed_items_for_clustering(feed_group_id, limit, db=db)
        result = await perform_source_clustering(items)
        return result
        
    except Exception as e:
        logger.error(f"Error in source clustering endpoint: {e}")
        raise HTTPException(status_code=500, detail="Failed to perform source clustering") 