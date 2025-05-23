from typing import Optional, Dict, Any, List
import logging
import time
import json
from pathlib import Path
import asyncio
from datetime import datetime, timedelta

from fastapi import APIRouter, Query, Depends, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from cachetools import TTLCache
import redis
import io
import csv

from app.vector_store import (
    search_articles,
    upsert_article,
    similar_articles,
    _get_collection as _vector_collection,
    get_chroma_client,
)
from app.database import Database, get_database_instance
from app.security.session import verify_session

router = APIRouter(prefix="/api", tags=["vector-search-enhanced"])

# Performance monitoring
search_metrics = {
    "total_searches": 0,
    "average_response_time": 0.0,
    "cache_hits": 0,
    "cache_misses": 0
}

# In-memory cache for frequent searches (fallback if Redis unavailable)
memory_cache = TTLCache(maxsize=1000, ttl=3600)

def get_redis_client():
    """Get Redis client with fallback to memory cache."""
    try:
        import redis
        return redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
    except:
        return None

def cache_key(query: str, filters: Dict[str, Any]) -> str:
    """Generate cache key from query and filters."""
    return f"search:{hash(query + str(sorted(filters.items())))}"

class SearchRequest(BaseModel):
    """Enhanced search request model."""
    q: str = Field(..., description="Search query")
    filters: Dict[str, Any] = Field(default_factory=dict)
    top_k: int = Field(default=100, ge=1, le=10000)
    use_cache: bool = Field(default=True)
    track_performance: bool = Field(default=True)

class SearchResponse(BaseModel):
    """Enhanced search response model."""
    results: List[Dict[str, Any]]
    facets: Dict[str, Dict[str, int]]
    timeline: Dict[str, Dict[str, int]]
    comparison: Optional[Dict[str, Any]] = None
    filtered_facets: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    performance: Dict[str, Any] = Field(default_factory=dict)

@router.post("/enhanced-vector-search")
async def enhanced_vector_search(
    request: SearchRequest,
    background_tasks: BackgroundTasks,
    session=Depends(verify_session)
) -> SearchResponse:
    """Enhanced search endpoint with caching, performance monitoring, and analytics."""
    
    start_time = time.time()
    logger = logging.getLogger(__name__)
    
    # Generate cache key
    cache_key_str = cache_key(request.q, request.filters)
    
    # Try cache first
    cached_result = None
    redis_client = get_redis_client()
    
    if request.use_cache:
        if redis_client:
            try:
                cached_data = redis_client.get(cache_key_str)
                if cached_data:
                    cached_result = json.loads(cached_data)
                    search_metrics["cache_hits"] += 1
                    logger.info(f"Cache hit for query: {request.q[:50]}...")
            except Exception as e:
                logger.warning(f"Redis cache error: {e}")
        
        # Fallback to memory cache
        if not cached_result and cache_key_str in memory_cache:
            cached_result = memory_cache[cache_key_str]
            search_metrics["cache_hits"] += 1
    
    if cached_result:
        # Add performance metadata to cached result
        cached_result["performance"]["from_cache"] = True
        cached_result["performance"]["response_time"] = time.time() - start_time
        return SearchResponse(**cached_result)
    
    search_metrics["cache_misses"] += 1
    
    try:
        # Import KISSQL components
        from app.kissql.parser import parse_full_query
        from app.kissql.executor import execute_query
        
        # Parse and execute search
        query_obj = parse_full_query(request.q)
        
        # Add filters from request
        for field, value in request.filters.items():
            from app.kissql.parser import Constraint
            query_obj.constraints.append(
                Constraint(field=field, operator="=", value=value)
            )
        
        # Execute query
        result = execute_query(query_obj, top_k=request.top_k)
        
        # Build response
        response_data = {
            "results": result.get("results", []),
            "facets": result.get("facets", {}),
            "timeline": result.get("timeline", {}),
            "comparison": result.get("comparison"),
            "filtered_facets": result.get("filtered_facets"),
            "metadata": {
                "total_results": len(result.get("results", [])),
                "query_parsed": str(query_obj),
                "timestamp": datetime.now().isoformat(),
                "filters_applied": len(request.filters),
            },
            "performance": {
                "response_time": time.time() - start_time,
                "from_cache": False,
                "cache_key": cache_key_str,
            }
        }
        
        # Cache the result
        if request.use_cache:
            cache_data = json.dumps(response_data, default=str)
            
            if redis_client:
                try:
                    redis_client.setex(cache_key_str, 3600, cache_data)  # 1 hour TTL
                except Exception as e:
                    logger.warning(f"Redis cache write error: {e}")
            
            # Also cache in memory
            memory_cache[cache_key_str] = response_data
        
        # Update metrics in background
        if request.track_performance:
            background_tasks.add_task(update_search_metrics, time.time() - start_time)
        
        return SearchResponse(**response_data)
        
    except Exception as e:
        logger.error(f"Enhanced search error: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

@router.get("/search-suggestions")
async def get_search_suggestions(
    q: str = Query(..., min_length=2, max_length=100),
    limit: int = Query(default=10, ge=1, le=50),
    session=Depends(verify_session)
) -> Dict[str, List[str]]:
    """Get real-time search suggestions based on partial query."""
    
    try:
        # Simple implementation - could be enhanced with ML-based suggestions
        suggestions = []
        
        # Get recent successful searches from cache/analytics
        redis_client = get_redis_client()
        if redis_client:
            try:
                # Get patterns from recent searches
                recent_patterns = redis_client.smembers("search_patterns")
                suggestions.extend([
                    pattern for pattern in recent_patterns 
                    if q.lower() in pattern.lower()
                ][:limit//2])
            except:
                pass
        
        # Add field-based suggestions
        field_suggestions = []
        if "=" in q or ":" in q:
            # User is typing a filter - suggest field values
            if "category=" in q:
                field_suggestions.extend([
                    'category="AI Business"',
                    'category="AI at Work and Employment"',
                    'category="AI and Society"'
                ])
            elif "sentiment=" in q:
                field_suggestions.extend([
                    'sentiment="Positive"',
                    'sentiment="Negative"',
                    'sentiment="Neutral"'
                ])
        else:
            # General search suggestions
            field_suggestions.extend([
                "AI artificial intelligence",
                "machine learning ML",
                "neural networks",
                "automation",
                "technology trends"
            ])
        
        suggestions.extend([
            s for s in field_suggestions 
            if q.lower() in s.lower()
        ][:limit - len(suggestions)])
        
        return {
            "suggestions": suggestions[:limit],
            "query": q,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Suggestions error: {e}")
        return {"suggestions": [], "query": q, "error": str(e)}

@router.get("/export-results")
async def export_search_results(
    query: str = Query(...),
    format: str = Query("csv", regex="^(csv|json|excel)$"),
    include_metadata: bool = Query(default=True),
    include_filters: bool = Query(default=True),
    selected_ids: Optional[str] = Query(None, description="Comma-separated list of IDs"),
    session=Depends(verify_session)
) -> StreamingResponse:
    """Export search results in various formats."""
    
    try:
        # Re-run the search to get current results
        from app.kissql.parser import parse_full_query
        from app.kissql.executor import execute_query
        
        query_obj = parse_full_query(query)
        result = execute_query(query_obj, top_k=10000)
        
        results = result.get("results", [])
        
        # Filter to selected IDs if provided
        if selected_ids:
            selected_set = set(selected_ids.split(","))
            results = [r for r in results if r.get("id") in selected_set]
        
        # Prepare export data
        export_data = []
        for item in results:
            row = {
                "id": item.get("id"),
                "title": item.get("metadata", {}).get("title", ""),
                "summary": item.get("metadata", {}).get("summary", ""),
                "score": item.get("score", 0),
                "publication_date": item.get("metadata", {}).get("publication_date", ""),
                "news_source": item.get("metadata", {}).get("news_source", ""),
                "category": item.get("metadata", {}).get("category", ""),
                "sentiment": item.get("metadata", {}).get("sentiment", ""),
            }
            
            if include_metadata:
                row.update({
                    "topic": item.get("metadata", {}).get("topic", ""),
                    "driver_type": item.get("metadata", {}).get("driver_type", ""),
                    "future_signal": item.get("metadata", {}).get("future_signal", ""),
                    "uri": item.get("metadata", {}).get("uri", ""),
                })
            
            export_data.append(row)
        
        # Generate appropriate response based on format
        if format == "csv":
            output = io.StringIO()
            if export_data:
                writer = csv.DictWriter(output, fieldnames=export_data[0].keys())
                writer.writeheader()
                writer.writerows(export_data)
            
            response = StreamingResponse(
                io.BytesIO(output.getvalue().encode('utf-8')),
                media_type="text/csv",
                headers={"Content-Disposition": "attachment; filename=search_results.csv"}
            )
            
        elif format == "json":
            json_data = {
                "timestamp": datetime.now().isoformat(),
                "query": query,
                "total_results": len(export_data),
                "data": export_data
            }
            
            if include_filters:
                json_data["facets"] = result.get("facets", {})
                json_data["timeline"] = result.get("timeline", {})
            
            response = StreamingResponse(
                io.BytesIO(json.dumps(json_data, indent=2).encode('utf-8')),
                media_type="application/json",
                headers={"Content-Disposition": "attachment; filename=search_results.json"}
            )
            
        else:  # Excel format would require additional library
            raise HTTPException(status_code=501, detail="Excel export not implemented")
        
        return response
        
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Export error: {e}")
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")

@router.get("/search-analytics")
async def get_search_analytics(
    session=Depends(verify_session)
) -> Dict[str, Any]:
    """Get search analytics and performance metrics."""
    
    try:
        redis_client = get_redis_client()
        analytics_data = {
            "performance_metrics": search_metrics.copy(),
            "cache_stats": {
                "memory_cache_size": len(memory_cache),
                "memory_cache_hits": search_metrics["cache_hits"],
                "memory_cache_misses": search_metrics["cache_misses"],
                "cache_hit_rate": (
                    search_metrics["cache_hits"] / 
                    max(1, search_metrics["cache_hits"] + search_metrics["cache_misses"])
                ) * 100
            },
            "timestamp": datetime.now().isoformat()
        }
        
        if redis_client:
            try:
                # Get additional Redis-based analytics
                redis_info = redis_client.info()
                analytics_data["redis_stats"] = {
                    "connected_clients": redis_info.get("connected_clients", 0),
                    "used_memory": redis_info.get("used_memory_human", "N/A"),
                    "total_commands_processed": redis_info.get("total_commands_processed", 0)
                }
                
                # Get popular search patterns
                popular_patterns = redis_client.zrevrange("popular_searches", 0, 9, withscores=True)
                analytics_data["popular_searches"] = [
                    {"query": pattern, "count": int(score)} 
                    for pattern, score in popular_patterns
                ]
                
            except Exception as e:
                analytics_data["redis_error"] = str(e)
        
        return analytics_data
        
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Analytics error: {e}")
        return {"error": str(e), "timestamp": datetime.now().isoformat()}

@router.post("/clear-cache")
async def clear_search_cache(
    pattern: Optional[str] = None,
    session=Depends(verify_session)
) -> Dict[str, Any]:
    """Clear search cache, optionally by pattern."""
    
    try:
        cleared_count = 0
        
        # Clear memory cache
        if pattern:
            keys_to_remove = [k for k in memory_cache.keys() if pattern in k]
            for key in keys_to_remove:
                del memory_cache[key]
                cleared_count += 1
        else:
            cleared_count = len(memory_cache)
            memory_cache.clear()
        
        # Clear Redis cache
        redis_client = get_redis_client()
        if redis_client:
            try:
                if pattern:
                    keys = redis_client.keys(f"*{pattern}*")
                    if keys:
                        redis_client.delete(*keys)
                        cleared_count += len(keys)
                else:
                    redis_client.flushdb()
            except Exception as e:
                return {"error": f"Redis clear error: {e}"}
        
        return {
            "success": True,
            "cleared_count": cleared_count,
            "pattern": pattern,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Cache clear error: {e}")
        return {"error": str(e)}

@router.websocket("/search-stream")
async def search_stream_websocket(websocket):
    """WebSocket endpoint for real-time search streaming."""
    
    # Basic authentication check for WebSocket
    # Check for session in cookies or authorization header
    try:
        # Get cookies from WebSocket headers
        cookies = websocket.cookies
        if not cookies.get('session'):
            await websocket.close(code=1008, reason="Authentication required")
            return
    except Exception:
        await websocket.close(code=1008, reason="Authentication failed")
        return
    
    await websocket.accept()
    logger = logging.getLogger(__name__)
    
    try:
        while True:
            # Receive search query from client
            data = await websocket.receive_json()
            query = data.get("query", "")
            
            if not query:
                continue
            
            # Send progress updates
            await websocket.send_json({
                "type": "progress",
                "step": "parsing",
                "message": "Parsing query..."
            })
            
            # Parse query
            from app.kissql.parser import parse_full_query
            query_obj = parse_full_query(query)
            
            await websocket.send_json({
                "type": "progress", 
                "step": "searching",
                "message": "Searching articles..."
            })
            
            # Execute search
            from app.kissql.executor import execute_query
            result = execute_query(query_obj, top_k=data.get("top_k", 100))
            
            await websocket.send_json({
                "type": "progress",
                "step": "processing", 
                "message": "Processing results..."
            })
            
            # Send final results
            await websocket.send_json({
                "type": "results",
                "data": result,
                "query": query,
                "timestamp": datetime.now().isoformat()
            })
            
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await websocket.send_json({
            "type": "error",
            "message": str(e)
        })
    finally:
        await websocket.close()

# Background task functions
async def update_search_metrics(response_time: float):
    """Update search performance metrics."""
    
    search_metrics["total_searches"] += 1
    
    # Update rolling average
    count = search_metrics["total_searches"]
    old_avg = search_metrics["average_response_time"]
    search_metrics["average_response_time"] = (
        (old_avg * (count - 1) + response_time) / count
    )
    
    # Store in Redis for persistence
    redis_client = get_redis_client()
    if redis_client:
        try:
            redis_client.hset("search_metrics", mapping=search_metrics)
        except:
            pass

@router.on_event("startup")
async def startup_enhanced_routes():
    """Initialize enhanced routes and load cached metrics."""
    
    logger = logging.getLogger(__name__)
    logger.info("Starting enhanced vector routes...")
    
    # Load metrics from Redis if available
    redis_client = get_redis_client()
    if redis_client:
        try:
            stored_metrics = redis_client.hgetall("search_metrics")
            if stored_metrics:
                for key, value in stored_metrics.items():
                    if key in search_metrics:
                        search_metrics[key] = float(value) if '.' in value else int(value)
                logger.info("Loaded search metrics from Redis")
        except Exception as e:
            logger.warning(f"Could not load metrics from Redis: {e}")

@router.on_event("shutdown") 
async def shutdown_enhanced_routes():
    """Save metrics and cleanup on shutdown."""
    
    logger = logging.getLogger(__name__)
    
    # Save metrics to Redis
    redis_client = get_redis_client()
    if redis_client:
        try:
            redis_client.hset("search_metrics", mapping=search_metrics)
            logger.info("Saved search metrics to Redis")
        except Exception as e:
            logger.warning(f"Could not save metrics to Redis: {e}")
    
    logger.info("Enhanced vector routes shutdown complete") 