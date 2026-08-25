from fastapi import APIRouter, HTTPException, Query, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from app.security.session import verify_session, verify_session_api
from typing import Optional, List, Dict
import logging
from datetime import datetime, timedelta
import json
import asyncio
import secrets
import string
import hashlib

from app.database import Database, get_database_instance
from app.services.news_feed_service import get_news_feed_service
from app.schemas.news_feed import NewsFeedRequest, NewsFeedResponse
from app.database_query_facade import DatabaseQueryFacade

router = APIRouter(prefix="/api/news-feed", tags=["news-feed"])
logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory="templates")
templates.env.auto_reload = True  # Force template reload on changes
templates.env.cache = {}  # Disable template compilation cache


@router.get("/available-dates")
async def get_available_dates(
    session=Depends(verify_session_api),
    db: Database = Depends(get_database_instance)
):
    """Get dates that have articles available"""
    logger.info("Starting available-dates request")
    try:
        logger.info("Executing query for available dates")
        # Use the same filtering criteria as the news feed service including spam filtering
        query = """
        SELECT DATE(publication_date) as date, COUNT(*) as count 
        FROM articles 
        WHERE publication_date IS NOT NULL 
        AND category IS NOT NULL
        AND sentiment IS NOT NULL 
        AND bias IS NOT NULL
        AND factual_reporting IS NOT NULL
        AND title NOT LIKE '%Call@%'
        AND title NOT LIKE '%+91%'
        AND title NOT LIKE '%best%agency%'
        AND title NOT LIKE '%#1%'
        AND summary NOT LIKE '%Call@%'
        AND summary NOT LIKE '%phone%number%'
        AND news_source NOT LIKE '%medium.com/@%'
        GROUP BY DATE(publication_date) 
        ORDER BY date DESC 
        LIMIT 60
        """
        
        results = db.fetch_all(query)
        logger.info(f"Query completed, got {len(results)} results")
        
        # Convert to list of dictionaries
        available_dates = []
        for row in results:
            if hasattr(row, 'keys'):  # Handle Row objects
                date_dict = dict(row)
            else:
                date_dict = {"date": row[0], "count": row[1]}
            available_dates.append(date_dict)
        
        logger.info(f"Processed {len(available_dates)} available dates")
        return {"success": True, "dates": available_dates}
        
    except Exception as e:
        logger.error(f"Error getting available dates: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/daily")
async def generate_daily_news_feed(
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format, defaults to today"),
    topic: Optional[str] = Query(None, description="Optional topic filter"),
    max_articles: int = Query(50, ge=10, le=200, description="Maximum articles to analyze"),
    model: str = Query("gpt-5.4-mini", description="AI model to use for generation"),
    include_bias_analysis: bool = Query(True, description="Include bias and factuality analysis"),
    session=Depends(verify_session_api),
    db: Database = Depends(get_database_instance)
):
    """Generate daily news feed with overview and six articles report"""
    
    try:
        # Parse date if provided
        target_date = None
        if date:
            try:
                target_date = datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
        
        # Create request
        request = NewsFeedRequest(
            date=target_date,
            topic=topic,
            max_articles=max_articles,
            include_bias_analysis=include_bias_analysis,
            model=model
        )
        
        # Generate feed
        news_feed_service = get_news_feed_service(db)
        feed_response = await news_feed_service.generate_daily_feed(request)
        
        logger.info(f"Generated news feed for {target_date or 'today'} with {len(feed_response.overview.top_stories)} stories")
        
        return feed_response
        
    except ValueError as e:
        logger.error(f"Validation error in news feed generation: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error generating news feed: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/articles")
async def get_news_articles_only(
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format"),
    date_range: Optional[str] = Query("24h", description="Date range: 24h, 7d, 30d, 3m, 1y, all, or custom"),
    topic: Optional[str] = Query(None, description="Optional topic filter"),
    max_articles: int = Query(1000, ge=10, le=10000),
    model: str = Query("gpt-5.4-mini"),
    page: int = Query(1, ge=1, description="Page number for pagination"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    profile_id: Optional[int] = Query(None, description="Organizational profile ID for contextualized analysis"),
    starred_articles: Optional[str] = Query(None, description="Comma-separated URIs of starred articles"),
    session=Depends(verify_session_api),
    db: Database = Depends(get_database_instance)
):
    """Get paginated article list similar to topic dashboard"""

    try:
        # Parse date if provided
        target_date = None
        if date:
            try:
                target_date = datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

        # DEBUG: Log the incoming parameters
        logger.info(f"[NEWS FEED API] Incoming request - date_range={date_range}, topic={repr(topic)}, page={page}, per_page={per_page}")

        # Create request
        request = NewsFeedRequest(
            date=target_date,
            date_range=date_range,
            topic=topic,
            max_articles=max_articles,
            model=model,
            profile_id=profile_id
        )

        # Calculate SQL pagination parameters
        # For grouping by category, fetch all articles up to max_articles (not just per_page)
        offset = 0
        limit = max_articles

        logger.info(f"[NEWS FEED API] Calling _get_articles_for_date_range with offset={offset}, limit={limit}")

        # Generate article list - fetch ONLY the requested page from database
        news_feed_service = get_news_feed_service(db)
        articles_data = await news_feed_service._get_articles_for_date_range(
            date_range or "24h",
            max_articles,  # Kept for backwards compatibility
            topic,
            target_date,
            None,  # bias_filter
            offset,  # SQL OFFSET for pagination
            limit    # SQL LIMIT for pagination
        )

        logger.info(f"[NEWS FEED API] Returned {len(articles_data) if articles_data else 0} articles")
        
        if not articles_data:
            # Get the actual total count even when no articles returned (due to max_articles limit)
            actual_total = await news_feed_service._get_total_articles_count_for_date_range(
                date_range or "24h",
                request.topic,
                target_date
            )
            # Return empty result instead of 404
            return {
                "articles": {
                    "items": [],
                    "total_items": actual_total,
                    "total_articles": actual_total,
                    "page": page,
                    "per_page": per_page,
                    "total_pages": (actual_total + per_page - 1) // per_page if actual_total > 0 else 0,
                    "date": (target_date or datetime.now()).isoformat()
                }
            }
        
        article_list = await news_feed_service._generate_article_list(articles_data, target_date or datetime.now(), request, page=page, per_page=per_page)
        
        return {"articles": article_list}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating news overview: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/articles/clustered")
async def get_clustered_articles(
    date_range: Optional[str] = Query("7d", description="Date range: 24h, 7d, 30d, 3m, 1y, all"),
    topic: Optional[str] = Query(None, description="Optional topic filter"),
    category: Optional[str] = Query(None, description="Optional category filter"),
    max_articles: int = Query(100, ge=10, le=500),
    similarity_threshold: float = Query(0.3, ge=0.1, le=0.8, description="Max cosine distance for clustering (lower = stricter)"),
    max_cluster_size: int = Query(4, ge=2, le=8, description="Max articles per cluster"),
    session=Depends(verify_session_api),
    db: Database = Depends(get_database_instance)
):
    """Get articles clustered by semantic similarity.

    Groups related articles together based on vector embedding similarity.
    Returns clusters where each has a primary article and related articles.
    """
    from app.vector_store import cluster_articles_by_similarity
    from starlette.concurrency import run_in_threadpool

    try:
        # Get articles using the news feed service
        news_feed_service = get_news_feed_service(db)
        articles_data = await news_feed_service._get_articles_for_date_range(
            date_range or "7d",
            max_articles,
            topic,
            None  # custom_date
        )

        if not articles_data:
            return {"clusters": [], "total_articles": 0, "total_clusters": 0}

        # Filter by category if specified
        if category:
            articles_data = [a for a in articles_data if a.get('category') == category]

        if not articles_data:
            return {"clusters": [], "total_articles": 0, "total_clusters": 0}

        # Extract URIs for clustering
        article_uris = [a.get('uri') for a in articles_data if a.get('uri')]

        # Run clustering in thread pool (it's a sync function)
        clusters = await run_in_threadpool(
            cluster_articles_by_similarity,
            article_uris,
            similarity_threshold,
            max_cluster_size
        )

        # Transform clusters to include full article data with proper field mapping
        transformed_clusters = []
        for cluster in clusters:
            primary = cluster.get('primary', {})
            related = cluster.get('related', [])

            transformed_cluster = {
                'primary': {
                    'uri': primary.get('uri'),
                    'title': primary.get('title'),
                    'summary': primary.get('summary'),
                    'news_source': primary.get('news_source'),
                    'publication_date': primary.get('publication_date'),
                    'category': primary.get('category'),
                    'topic': primary.get('topic'),
                    'sentiment': primary.get('sentiment'),
                    'time_to_impact': primary.get('time_to_impact'),
                    'tags': primary.get('tags'),
                    'bias': primary.get('bias'),
                    'factual_reporting': primary.get('factual_reporting'),
                    'mbfc_credibility_rating': primary.get('mbfc_credibility_rating'),
                },
                'related': [
                    {
                        'uri': r.get('uri'),
                        'title': r.get('title'),
                        'summary': r.get('summary'),
                        'news_source': r.get('news_source'),
                        'publication_date': r.get('publication_date'),
                        'similarity_score': r.get('similarity_score'),
                        'bias': r.get('bias'),
                        'factual_reporting': r.get('factual_reporting'),
                    }
                    for r in related
                ],
                'article_count': 1 + len(related)
            }
            transformed_clusters.append(transformed_cluster)

        return {
            "clusters": transformed_clusters,
            "total_articles": len(article_uris),
            "total_clusters": len(transformed_clusters)
        }

    except Exception as e:
        logger.error(f"Error getting clustered articles: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/articles/list")
async def get_articles_list(
    date_range: Optional[str] = Query("7d", description="Date range: 24h, 72h, 7d, 30d, 3m, 1y, all"),
    topic: Optional[str] = Query(None, description="Optional topic filter"),
    page: int = Query(1, ge=1, description="Page number for pagination"),
    per_page: int = Query(25, ge=1, le=100, description="Items per page"),
    session=Depends(verify_session_api),
    db: Database = Depends(get_database_instance)
):
    """Get articles as a flat list sorted by publication date (newest first).

    Unlike the clustered view, this returns articles in a simple chronological list
    sorted by when they were published, without any grouping or clustering.
    Only returns enriched articles (those with category and sentiment set).
    """
    try:
        # Get DB facade
        db_facade = DatabaseQueryFacade(db, logger)

        # Calculate date range parameters
        now = datetime.now()
        if date_range == "24h":
            start_date = now - timedelta(days=1)
        elif date_range == "72h":
            start_date = now - timedelta(days=3)
        elif date_range == "7d":
            start_date = now - timedelta(days=7)
        elif date_range == "30d":
            start_date = now - timedelta(days=30)
        elif date_range == "3m":
            start_date = now - timedelta(days=90)
        elif date_range == "1y":
            start_date = now - timedelta(days=365)
        elif date_range == "all":
            start_date = None
        else:
            start_date = now - timedelta(days=7)  # Default to 7d

        # Calculate offset for pagination
        offset = (page - 1) * per_page

        # Get articles sorted chronologically by publication date
        # Use 'T' format for end_date to match ISO format in database (e.g., '2026-01-28T14:25:03+00:00')
        articles_data = db_facade.get_news_feed_articles_chronological(
            start_date=start_date.strftime('%Y-%m-%d') if start_date else None,
            end_date=now.strftime('%Y-%m-%dT23:59:59'),
            topic=topic,
            offset=offset,
            limit=per_page
        )

        # Get total count for pagination
        total_count = db_facade.get_news_feed_articles_chronological_count(
            start_date=start_date.strftime('%Y-%m-%d') if start_date else None,
            end_date=now.strftime('%Y-%m-%dT23:59:59'),
            topic=topic
        )

        total_pages = (total_count + per_page - 1) // per_page if total_count > 0 else 0

        return {
            "articles": articles_data,
            "total_count": total_count,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages
        }

    except Exception as e:
        logger.error(f"Error getting articles list: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/six-articles")
async def get_six_articles_report(
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format"),
    date_range: Optional[str] = Query("24h", description="Date range: 24h, 7d, 30d, 3m, 1y, all, or custom"),
    topic: Optional[str] = Query(None, description="Optional topic filter"),
    max_articles: int = Query(50, ge=20, le=200),
    model: str = Query("gpt-5.4-mini"),
    page: int = Query(1, ge=1, description="Page number for pagination"),
    profile_id: Optional[int] = Query(None, description="Organizational profile ID for contextualized analysis"),
    starred_articles: Optional[str] = Query(None, description="Comma-separated URIs of starred articles"),
    persona: Optional[str] = Query("CEO", description="Target persona: CEO, CMO, CTO, CISO, or Custom"),
    article_count: int = Query(6, ge=1, le=8, description="Number of articles to select (1-8)"),
    session=Depends(verify_session),
    db: Database = Depends(get_database_instance),
    force_regenerate: bool = Query(False, description="Bypass cache and regenerate fresh output")
):
    """Generate only the six articles detailed report"""

    try:
        # Get user_id from session for loading custom config
        user_id = session.get("user_id")
        username = session.get('user', {}).get('username')

        # Parse date if provided
        target_date = None
        if date:
            try:
                target_date = datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

        # Parse starred articles if provided
        starred_uris = None
        if starred_articles:
            starred_uris = [uri.strip() for uri in starred_articles.split(',') if uri.strip()]
            logger.info(f"Received {len(starred_uris)} starred articles for six articles generation")

        # Get user's hidden briefings to exclude from generation
        hidden_headlines = []
        if username:
            try:
                from app.database_query_facade import DatabaseQueryFacade
                facade = DatabaseQueryFacade(db, logger)
                hidden_list = facade.get_user_preference(username, 'hidden_briefings') or []
                if isinstance(hidden_list, list):
                    hidden_headlines = [h.lower().strip() for h in hidden_list if isinstance(h, str)]
                    if hidden_headlines:
                        logger.info(f"Excluding {len(hidden_headlines)} hidden briefing headlines from generation")
            except Exception as e:
                logger.warning(f"Could not load hidden briefings: {e}")

        # Create request with user_id
        request = NewsFeedRequest(
            date=target_date,
            date_range=date_range,
            topic=topic,
            max_articles=max_articles,
            model=model,
            profile_id=profile_id,
            persona=persona,
            article_count=article_count,
            starred_articles=starred_uris,
            user_id=user_id
        )

        # Generate only six articles report
        news_feed_service = get_news_feed_service(db)
        articles_data = await news_feed_service._get_articles_for_date_range(
            date_range or "24h",
            max_articles,
            topic,
            target_date
        )

        if not articles_data:
            # Return empty result instead of 404
            return {"six_articles": []}

        # Filter out articles matching hidden headlines (case-insensitive partial match)
        if hidden_headlines:
            original_count = len(articles_data)
            articles_data = [
                article for article in articles_data
                if not any(
                    hidden in (article.get('title') or '').lower()
                    for hidden in hidden_headlines
                )
            ]
            filtered_count = original_count - len(articles_data)
            if filtered_count > 0:
                logger.info(f"Filtered out {filtered_count} articles matching hidden briefing headlines")
        
        if force_regenerate:
            # Generate fresh and update caches implicitly via cached method write path
            six_articles = await news_feed_service._generate_six_articles_with_political_analysis(articles_data, target_date or datetime.now(), request)
            # Best-effort: write to cache for subsequent loads
            try:
                await news_feed_service._generate_six_articles_report_cached(articles_data, target_date or datetime.now(), request)
            except Exception as _:
                pass
        else:
            six_articles = await news_feed_service._generate_six_articles_report_cached(articles_data, target_date or datetime.now(), request)
        
        logger.info(f"Generated {len(six_articles)} six articles")
        if six_articles and len(six_articles) > 0:
            logger.info(f"First article has related_articles: {bool(six_articles[0].get('related_articles'))}")
            if six_articles[0].get('related_articles'):
                logger.info(f"First article related_articles count: {len(six_articles[0]['related_articles'])}")
        
        return {"six_articles": six_articles}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating six articles report: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


# ---------- HTML Page Routes ---------- #
page_router = APIRouter(tags=["news-feed-pages"])


@page_router.get("/news-feed", response_class=HTMLResponse)
async def news_feed_page(request: Request, session=Depends(verify_session)):
    """Render the main news feed page (modernized v2)"""
    return templates.TemplateResponse("news_feed_new.html", {
        "request": request,
        "page_title": "News Narrator",
        "show_share_button": True,
        "session": session,
        "current_page": "investigate"
    })


@page_router.get("/news-feed-v2", response_class=HTMLResponse)
async def news_feed_v2_page(request: Request, session=Depends(verify_session)):
    """Render the NEW modernized news feed page (v2 - Proof of Concept)"""
    return templates.TemplateResponse("news_feed_new.html", {
        "request": request,
        "page_title": "News Narrator v2 - Proof of Concept",
        "show_share_button": True,
        "session": session,
        "current_page": "investigate"
    })


@page_router.get("/explore", response_class=HTMLResponse)
async def explore_page(request: Request, session=Depends(verify_session)):
    """Render the Explore page (React-based news feed)"""
    return templates.TemplateResponse("explore_react.html", {
        "request": request,
        "session": session,
        "current_page": "investigate"
    })


@page_router.get("/news-feed/overview", response_class=HTMLResponse)
async def news_overview_page(
    request: Request,
    session=Depends(verify_session),
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format")
):
    """Render the news overview page"""
    return templates.TemplateResponse("news_overview.html", {
        "request": request,
        "date": date,
        "page_title": "Daily News Overview",
        "show_share_button": True,
        "session": session
    })


@page_router.get("/news-feed/six-articles", response_class=HTMLResponse)
async def six_articles_page(
    request: Request,
    session=Depends(verify_session),
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format")
):
    """Render the six articles detailed report page"""
    return templates.TemplateResponse("six_articles.html", {
        "request": request,
        "date": date,
        "page_title": "Six Most Interesting Articles",
        "show_share_button": True,
        "session": {}  # Empty session for public access
    })


@router.get("/markdown/overview", dependencies=[Depends(verify_session_api)])
async def get_overview_markdown(
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format"),
    topic: Optional[str] = Query(None, description="Optional topic filter"),
    db: Database = Depends(get_database_instance)
):
    """Get news overview in markdown format"""
    
    try:
        # Parse date if provided
        target_date = None
        if date:
            try:
                target_date = datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
        
        # Create request
        request = NewsFeedRequest(
            date=target_date,
            topic=topic,
            max_articles=30,
            model="gpt-5.4-mini"
        )
        
        # Generate overview
        news_feed_service = get_news_feed_service(db)
        articles_data = await news_feed_service._get_articles_for_date(
            target_date or datetime.now().replace(hour=0, minute=0, second=0, microsecond=0),
            request.max_articles,
            request.topic
        )
        
        if not articles_data:
            raise HTTPException(status_code=404, detail="No articles found")
        
        overview = await news_feed_service._generate_overview(articles_data, target_date or datetime.now(), request)
        
        # Convert to markdown
        markdown_content = _convert_overview_to_markdown(overview)
        
        return {"markdown": markdown_content, "overview": overview}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating markdown overview: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/markdown/six-articles", dependencies=[Depends(verify_session_api)])
async def get_six_articles_markdown(
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format"),
    topic: Optional[str] = Query(None, description="Optional topic filter"),
    db: Database = Depends(get_database_instance)
):
    """Get six articles report in markdown format"""
    
    try:
        # Parse date if provided
        target_date = None
        if date:
            try:
                target_date = datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
        
        # Create request
        request = NewsFeedRequest(
            date=target_date,
            topic=topic,
            max_articles=50,
            model="gpt-5.4-mini"
        )
        
        # Generate six articles report
        news_feed_service = get_news_feed_service(db)
        articles_data = await news_feed_service._get_articles_for_date(
            target_date or datetime.now().replace(hour=0, minute=0, second=0, microsecond=0),
            request.max_articles,
            request.topic
        )
        
        if not articles_data:
            raise HTTPException(status_code=404, detail="No articles found")
        
        six_articles = await news_feed_service._generate_six_articles_report(articles_data, target_date or datetime.now(), request)
        
        # Convert to markdown
        markdown_content = _convert_six_articles_to_markdown(six_articles)
        
        return {"markdown": markdown_content, "six_articles": six_articles}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating markdown six articles: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/six-articles/config")
async def get_six_articles_config(
    session=Depends(verify_session),
    db: Database = Depends(get_database_instance)
):
    """
    Get Six Articles configuration (system prompt, personas, format spec)
    Returns user-specific config or defaults if none exists
    """
    try:
        # Extract username from session (handles both nested and OAuth formats)
        user = session.get("user")
        if user and isinstance(user, dict):
            username = user.get("username")
        else:
            username = user

        # Try to load user-specific config from database
        config = db.facade.get_six_articles_config(username)

        if config:
            return config

        # Return defaults if no custom config exists
        default_config = {
            "systemPrompt": None,  # Will use hardcoded default in service
            "personas": {
                "CEO": {
                    "priorities": "Regulation, enterprise adoption, scaling limits, market dynamics, security/safety, workforce impact, strategic partnerships",
                    "riskAppetite": "moderate",
                    "focus": "business strategy, market positioning, competitive advantage, and regulatory compliance"
                },
                "CMO": {
                    "priorities": "Market trends, customer behavior, brand impact, advertising innovation, customer experience, competitive positioning",
                    "riskAppetite": "high",
                    "focus": "marketing strategies, customer engagement, brand differentiation, and market opportunities"
                },
                "CTO": {
                    "priorities": "Technical breakthroughs, infrastructure, scalability, development tools, architecture patterns, security vulnerabilities",
                    "riskAppetite": "high",
                    "focus": "technical architecture, development practices, technology stack decisions, and engineering excellence"
                },
                "CISO": {
                    "priorities": "Security threats, vulnerabilities, compliance requirements, risk management, data protection, incident response",
                    "riskAppetite": "low",
                    "focus": "security risks, compliance requirements, threat mitigation, and data protection"
                }
            },
            "formatSpec": None  # Will use hardcoded default in service
        }

        return default_config

    except Exception as e:
        logger.error(f"Error retrieving Six Articles config: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve configuration")


@router.post("/six-articles/config")
async def save_six_articles_config(
    config: dict,
    session=Depends(verify_session),
    db: Database = Depends(get_database_instance)
):
    """
    Save Six Articles configuration (system prompt, personas, format spec)
    Stored per-user in database
    """
    try:
        # Extract username from session (handles both nested and OAuth formats)
        user = session.get("user")
        if user and isinstance(user, dict):
            username = user.get("username")
        else:
            username = user

        # Validate config structure
        if "personas" in config:
            required_personas = ["CEO", "CMO", "CTO", "CISO"]
            for persona in required_personas:
                if persona not in config["personas"]:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Missing required persona: {persona}"
                    )

        # Save to database
        success = db.facade.save_six_articles_config(username, config)

        if not success:
            raise HTTPException(status_code=500, detail="Failed to save configuration")

        logger.info(f"Six Articles config saved for user {username}")
        return {"status": "success", "message": "Configuration saved successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving Six Articles config: {e}")
        raise HTTPException(status_code=500, detail="Failed to save configuration")


@router.get("/six-articles/config/defaults")
async def get_six_articles_defaults(session=Depends(verify_session)):
    """
    Get default Six Articles configuration
    Useful for reset functionality
    """
    default_config = {
        "systemPrompt": None,  # Indicates use of hardcoded default
        "personas": {
            "CEO": {
                "priorities": "Regulation, enterprise adoption, scaling limits, market dynamics, security/safety, workforce impact, strategic partnerships",
                "riskAppetite": "moderate",
                "focus": "business strategy, market positioning, competitive advantage, and regulatory compliance"
            },
            "CMO": {
                "priorities": "Market trends, customer behavior, brand impact, advertising innovation, customer experience, competitive positioning",
                "riskAppetite": "high",
                "focus": "marketing strategies, customer engagement, brand differentiation, and market opportunities"
            },
            "CTO": {
                "priorities": "Technical breakthroughs, infrastructure, scalability, development tools, architecture patterns, security vulnerabilities",
                "riskAppetite": "high",
                "focus": "technical architecture, development practices, technology stack decisions, and engineering excellence"
            },
            "CISO": {
                "priorities": "Security threats, vulnerabilities, compliance requirements, risk management, data protection, incident response",
                "riskAppetite": "low",
                "focus": "security risks, compliance requirements, threat mitigation, and data protection"
            }
        },
        "formatSpec": None  # Indicates use of hardcoded default
    }

    return default_config


def _convert_overview_to_markdown(overview) -> str:
    """Convert overview to markdown format"""
    
    markdown_lines = []
    
    # Title and date
    markdown_lines.append(f"# {overview.title}")
    markdown_lines.append(f"*{overview.date.strftime('%A, %B %d, %Y')}*")
    markdown_lines.append("")
    
    # Top stories
    for i, story in enumerate(overview.top_stories, 1):
        markdown_lines.append(f"## {i}. {story.headline}")
        markdown_lines.append("")
        markdown_lines.append(story.summary)
        markdown_lines.append("")
        
        if story.topic_description:
            markdown_lines.append(f"**Why it matters:** {story.topic_description}")
            markdown_lines.append("")
        
        # Primary source
        if story.primary_article.source.name:
            source_info = story.primary_article.source.name
            if story.primary_article.source.bias:
                source_info += f" ({story.primary_article.source.bias.value})"
            markdown_lines.append(f"**Source:** {source_info}")
            
        # Related articles
        if story.related_articles:
            markdown_lines.append("**More coverage:**")
            for related in story.related_articles:
                bias_info = f" ({related.bias.value})" if related.bias else ""
                markdown_lines.append(f"- {related.source}{bias_info}: {related.title}")
        
        markdown_lines.append("")
        markdown_lines.append("---")
        markdown_lines.append("")
    
    # Footer
    markdown_lines.append(f"*Generated at {overview.generated_at.strftime('%H:%M UTC')} from {overview.total_articles_analyzed} articles*")
    
    return "\n".join(markdown_lines)


def _convert_six_articles_to_markdown(six_articles) -> str:
    """Convert six articles report to markdown format"""
    
    markdown_lines = []
    
    # Title and date
    markdown_lines.append(f"# {six_articles.title}")
    markdown_lines.append(f"*{six_articles.date.strftime('%A, %B %d, %Y')}*")
    markdown_lines.append("")
    
    # Executive summary
    if six_articles.executive_summary:
        markdown_lines.append("## Executive Summary")
        markdown_lines.append("")
        markdown_lines.append(six_articles.executive_summary)
        markdown_lines.append("")
    
    # Key themes
    if six_articles.key_themes:
        markdown_lines.append("## Key Themes")
        markdown_lines.append("")
        for theme in six_articles.key_themes:
            markdown_lines.append(f"- {theme}")
        markdown_lines.append("")
    
    # Articles
    markdown_lines.append("## Featured Articles")
    markdown_lines.append("")
    
    for i, article in enumerate(six_articles.articles, 1):
        markdown_lines.append(f"### {i}. {article.headline}")
        markdown_lines.append("")
        markdown_lines.append(article.summary)
        markdown_lines.append("")
        
        if article.topic_description:
            markdown_lines.append(f"**Analysis:** {article.topic_description}")
            markdown_lines.append("")
        
        # Source and bias info
        source_info = article.primary_article.source.name
        if article.primary_article.source.bias:
            source_info += f" (Bias: {article.primary_article.source.bias.value})"
        if article.primary_article.source.factuality:
            source_info += f" (Factuality: {article.primary_article.source.factuality.value})"
        
        markdown_lines.append(f"**Source:** {source_info}")
        markdown_lines.append("")
        
        # Perspective breakdown
        if article.perspective_breakdown:
            markdown_lines.append("**Different Perspectives:**")
            for perspective, points in article.perspective_breakdown.items():
                if points:
                    markdown_lines.append(f"- **{perspective.title()}:** {', '.join(points)}")
            markdown_lines.append("")
        
        # Related coverage
        if article.related_articles:
            markdown_lines.append("**Related Coverage:**")
            for related in article.related_articles:
                bias_info = f" ({related.bias.value})" if related.bias else ""
                markdown_lines.append(f"- {related.source}{bias_info}: {related.title}")
        
        markdown_lines.append("")
        markdown_lines.append("---")
        markdown_lines.append("")
    
    # Bias distribution
    if six_articles.bias_distribution:
        markdown_lines.append("## Source Bias Distribution")
        markdown_lines.append("")
        for bias, count in six_articles.bias_distribution.items():
            if count > 0:
                markdown_lines.append(f"- {bias.title()}: {count} articles")
        markdown_lines.append("")
    
    # Footer
    markdown_lines.append(f"*Generated at {six_articles.generated_at.strftime('%H:%M UTC')}*")
    
    return "\n".join(markdown_lines)


def generate_share_token() -> str:
    """Generate a random share token for secure URLs"""
    # Generate a random 12-character token using letters and numbers
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(12))


@router.post("/share", dependencies=[Depends(verify_session_api)])
async def create_shared_feed(
    request: Request,
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format"),
    topic: Optional[str] = Query(None, description="Optional topic filter"),
    feed_type: str = Query("overview", description="Type of feed: overview or six-articles"),
    db: Database = Depends(get_database_instance)
):
    """Create a shareable link for a news feed"""
    
    try:
        # Parse date if provided
        target_date = None
        if date:
            try:
                target_date = datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
        
        # Generate the feed first to ensure it exists
        feed_request = NewsFeedRequest(
            date=target_date,
            topic=topic,
            max_articles=50 if feed_type == "six-articles" else 30,
            model="gpt-5.4-mini"
        )
        
        news_feed_service = get_news_feed_service(db)
        
        if feed_type == "overview":
            articles_data = await news_feed_service._get_articles_for_date(
                target_date or datetime.now().replace(hour=0, minute=0, second=0, microsecond=0),
                feed_request.max_articles,
                feed_request.topic
            )
            
            if not articles_data:
                raise HTTPException(status_code=404, detail="No articles found for the specified criteria")
            
            try:
                feed_data = await news_feed_service._generate_article_list(articles_data, target_date or datetime.now(), feed_request)
                feed_json = json.dumps(feed_data, default=str)
            except Exception as e:
                logger.error(f"Error generating article list for sharing: {e}")
                raise HTTPException(status_code=500, detail=f"Error generating feed data: {str(e)}")
            
        elif feed_type == "six-articles":
            articles_data = await news_feed_service._get_articles_for_date(
                target_date or datetime.now().replace(hour=0, minute=0, second=0, microsecond=0),
                feed_request.max_articles,
                feed_request.topic
            )
            
            if not articles_data:
                raise HTTPException(status_code=404, detail="No articles found for the specified criteria")
            
            try:
                feed_data = await news_feed_service._generate_six_articles_report(articles_data, target_date or datetime.now(), feed_request)
                feed_json = json.dumps(feed_data, default=str)
            except Exception as e:
                logger.error(f"Error generating six articles for sharing: {e}")
                raise HTTPException(status_code=500, detail=f"Error generating feed data: {str(e)}")
            
        else:
            raise HTTPException(status_code=400, detail="Invalid feed_type. Use 'overview' or 'six-articles'")
        
        # Generate share token
        share_token = generate_share_token()
        
        # Create shared feeds table if it doesn't exist
        try:
            create_table_query = """
            CREATE TABLE IF NOT EXISTS shared_news_feeds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                share_token TEXT UNIQUE NOT NULL,
                feed_type TEXT NOT NULL,
                feed_data TEXT NOT NULL,
                date_filter TEXT,
                topic_filter TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                access_count INTEGER DEFAULT 0
            )
            """
            db.execute_query(create_table_query)
        except Exception as e:
            logger.error(f"Error creating shared_news_feeds table: {e}")
            raise HTTPException(status_code=500, detail=f"Database setup error: {str(e)}")
        
        # Calculate expiration (30 days from now)
        expires_at = datetime.now() + timedelta(days=30)
        
        # Store the shared feed
        try:
            insert_query = """
            INSERT INTO shared_news_feeds 
            (share_token, feed_type, feed_data, date_filter, topic_filter, expires_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """
            
            db.execute_query(insert_query, (
                share_token,
                feed_type,
                feed_json,
                date,
                topic,
                expires_at.isoformat()
            ))
        except Exception as e:
            logger.error(f"Error storing shared feed: {e}")
            raise HTTPException(status_code=500, detail=f"Database storage error: {str(e)}")
        
        # Generate shareable URLs
        base_url = str(request.url).replace(str(request.url.path), "")
        share_url = f"{base_url}/shared/{share_token}"
        
        return {
            "success": True,
            "share_token": share_token,
            "share_url": share_url,
            "expires_at": expires_at.isoformat(),
            "feed_type": feed_type
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating shared feed: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/shared/{share_token}", response_class=HTMLResponse)
async def view_shared_feed(
    request: Request,
    share_token: str,
    db: Database = Depends(get_database_instance)
):
    """View a shared news feed"""
    
    try:
        # Look up the shared feed
        query = """
        SELECT feed_type, feed_data, date_filter, topic_filter, expires_at, access_count
        FROM shared_news_feeds 
        WHERE share_token = ?
        """
        
        result = db.fetch_one(query, (share_token,))
        
        if not result:
            raise HTTPException(status_code=404, detail="Shared feed not found")
        
        feed_type, feed_data_json, date_filter, topic_filter, expires_at, access_count = result
        
        # Check if expired
        if expires_at:
            expires_date = datetime.fromisoformat(expires_at)
            if datetime.now() > expires_date:
                raise HTTPException(status_code=410, detail="Shared feed has expired")
        
        # Increment access count
        update_query = "UPDATE shared_news_feeds SET access_count = access_count + 1 WHERE share_token = ?"
        db.execute_query(update_query, (share_token,))
        
        # Parse feed data
        feed_data = json.loads(feed_data_json)
        
        # Render appropriate template
        if feed_type == "overview":
            return templates.TemplateResponse("shared_news_overview.html", {
                "request": request,
                "feed_data": feed_data,
                "date_filter": date_filter,
                "topic_filter": topic_filter,
                "page_title": f"Shared News Overview - {feed_data.get('title', 'Daily News')}",
                "share_token": share_token,
                "is_shared": True,
                "session": {}  # Empty session for public access
            })
        elif feed_type == "six-articles":
            return templates.TemplateResponse("shared_six_articles.html", {
                "request": request,
                "feed_data": feed_data,
                "date_filter": date_filter,
                "topic_filter": topic_filter,
                "page_title": f"Shared Report - {feed_data.get('title', 'Six Articles')}",
                "share_token": share_token,
                "is_shared": True,
                "session": {}  # Empty session for public access
            })
        else:
            raise HTTPException(status_code=400, detail="Invalid feed type")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error viewing shared feed: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/api/shared/{share_token}")
async def get_shared_feed_data(
    share_token: str,
    db: Database = Depends(get_database_instance)
):
    """Get shared feed data as JSON"""
    
    try:
        # Look up the shared feed
        query = """
        SELECT feed_type, feed_data, date_filter, topic_filter, expires_at, access_count
        FROM shared_news_feeds 
        WHERE share_token = ?
        """
        
        result = db.fetch_one(query, (share_token,))
        
        if not result:
            raise HTTPException(status_code=404, detail="Shared feed not found")
        
        feed_type, feed_data_json, date_filter, topic_filter, expires_at, access_count = result
        
        # Check if expired
        if expires_at:
            expires_date = datetime.fromisoformat(expires_at)
            if datetime.now() > expires_date:
                raise HTTPException(status_code=410, detail="Shared feed has expired")
        
        # Increment access count
        update_query = "UPDATE shared_news_feeds SET access_count = access_count + 1 WHERE share_token = ?"
        db.execute_query(update_query, (share_token,))
        
        # Parse and return feed data
        feed_data = json.loads(feed_data_json)
        
        return {
            "success": True,
            "feed_type": feed_type,
            "feed_data": feed_data,
            "date_filter": date_filter,
            "topic_filter": topic_filter,
            "access_count": access_count + 1,
            "share_token": share_token
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting shared feed data: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/category-icons")
async def get_category_icons(
    categories: Optional[str] = Query(None, description="Comma-separated list of categories"),
    session=Depends(verify_session),
    db: Database = Depends(get_database_instance)
):
    """Get category icons (Font Awesome icon classes) for given categories.

    Icons are either pre-defined or generated once and stored in the database.
    Returns a mapping of category -> icon HTML string.
    """
    try:
        # Pre-defined category icons (Font Awesome)
        predefined_icons = {
            'Technology': '<i class="fas fa-laptop-code"></i>',
            'Business': '<i class="fas fa-briefcase"></i>',
            'Politics': '<i class="fas fa-landmark"></i>',
            'Science': '<i class="fas fa-flask"></i>',
            'Health': '<i class="fas fa-heartbeat"></i>',
            'Environment': '<i class="fas fa-leaf"></i>',
            'Education': '<i class="fas fa-graduation-cap"></i>',
            'Entertainment': '<i class="fas fa-film"></i>',
            'Sports': '<i class="fas fa-football-ball"></i>',
            'Economy': '<i class="fas fa-chart-line"></i>',
            'Finance': '<i class="fas fa-dollar-sign"></i>',
            'Security': '<i class="fas fa-shield-alt"></i>',
            'Military': '<i class="fas fa-fighter-jet"></i>',
            'International': '<i class="fas fa-globe"></i>',
            'Law': '<i class="fas fa-gavel"></i>',
            'Society': '<i class="fas fa-users"></i>',
            'Culture': '<i class="fas fa-palette"></i>',
            'Transportation': '<i class="fas fa-car"></i>',
            'Energy': '<i class="fas fa-bolt"></i>',
            'Space': '<i class="fas fa-rocket"></i>',
            'AI': '<i class="fas fa-robot"></i>',
            'Uncategorized': '<i class="fas fa-folder"></i>'
        }

        icon_map = {}

        # If specific categories requested
        if categories:
            category_list = [c.strip() for c in categories.split(',') if c.strip()]
        else:
            # Return all predefined icons
            return {
                "success": True,
                "icons": predefined_icons
            }

        # Build icon map for requested categories
        for category in category_list:
            # Check predefined first
            if category in predefined_icons:
                icon_map[category] = predefined_icons[category]
            else:
                # Try partial match
                found = False
                for key, icon in predefined_icons.items():
                    if key.lower() in category.lower() or category.lower() in key.lower():
                        icon_map[category] = icon
                        found = True
                        break

                # Use default if no match
                if not found:
                    icon_map[category] = '<i class="fas fa-file-alt"></i>'

        return {
            "success": True,
            "icons": icon_map
        }

    except Exception as e:
        logger.error(f"Error getting category icons: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/generate-category-icon")
async def generate_category_icon(
    category: str = Query(..., description="Category name"),
    session=Depends(verify_session),
    db: Database = Depends(get_database_instance)
):
    """Generate an AI-created icon for a category using DALL-E or similar.

    This endpoint will generate a unique icon image for custom categories
    and store it in the database/filesystem for future use.

    Note: This requires DALL-E API access and incurs costs.
    For now, we return Font Awesome icon classes as a lightweight alternative.
    """
    try:
        # TODO: Implement AI image generation using DALL-E when needed
        # For now, return a sensible Font Awesome icon

        # Simple keyword matching for common themes
        category_lower = category.lower()
        icon_html = '<i class="fas fa-file-alt"></i>'  # default

        theme_icons = {
            'tech': '<i class="fas fa-microchip"></i>',
            'cyber': '<i class="fas fa-user-secret"></i>',
            'data': '<i class="fas fa-database"></i>',
            'cloud': '<i class="fas fa-cloud"></i>',
            'mobile': '<i class="fas fa-mobile-alt"></i>',
            'web': '<i class="fas fa-globe"></i>',
            'code': '<i class="fas fa-code"></i>',
            'software': '<i class="fas fa-laptop-code"></i>',
            'hardware': '<i class="fas fa-server"></i>',
            'network': '<i class="fas fa-network-wired"></i>',
            'crypto': '<i class="fas fa-lock"></i>',
            'medical': '<i class="fas fa-stethoscope"></i>',
            'legal': '<i class="fas fa-balance-scale"></i>',
            'money': '<i class="fas fa-money-bill"></i>',
            'trade': '<i class="fas fa-exchange-alt"></i>',
            'climate': '<i class="fas fa-cloud-sun"></i>',
            'food': '<i class="fas fa-utensils"></i>',
            'travel': '<i class="fas fa-plane"></i>',
            'automotive': '<i class="fas fa-car"></i>',
            'real estate': '<i class="fas fa-home"></i>',
            'retail': '<i class="fas fa-shopping-cart"></i>',
            'manufacturing': '<i class="fas fa-industry"></i>',
            'agriculture': '<i class="fas fa-tractor"></i>',
            'media': '<i class="fas fa-newspaper"></i>',
            'telecom': '<i class="fas fa-phone"></i>',
            'research': '<i class="fas fa-microscope"></i>'
        }

        for keyword, icon in theme_icons.items():
            if keyword in category_lower:
                icon_html = icon
                break

        return {
            "success": True,
            "category": category,
            "icon": icon_html,
            "method": "font-awesome"  # vs "ai-generated" when DALL-E is implemented
        }

    except Exception as e:
        logger.error(f"Error generating category icon: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/category-counts", dependencies=[Depends(verify_session_api)])
async def get_category_counts(
    date_range: Optional[str] = Query("7d", description="Date range: 24h, 7d, 30d, 3m, 1y, all"),
    topic: Optional[str] = Query(None, description="Optional topic filter"),
    db: Database = Depends(get_database_instance)
):
    """Get total article counts per category from database.

    Returns a dictionary mapping category names to their total article counts,
    applying the same filters as the main news feed.
    """
    from starlette.concurrency import run_in_threadpool

    try:
        # Calculate date range
        now = datetime.now()

        if date_range == '24h':
            start_date = (now - timedelta(days=1)).strftime('%Y-%m-%d')
            end_date = now.strftime('%Y-%m-%d %H:%M:%S')
        elif date_range == '72h':
            start_date = (now - timedelta(days=3)).strftime('%Y-%m-%d')
            end_date = now.strftime('%Y-%m-%d %H:%M:%S')
        elif date_range == '7d':
            start_date = (now - timedelta(days=7)).strftime('%Y-%m-%d')
            end_date = now.strftime('%Y-%m-%d %H:%M:%S')
        elif date_range == '30d':
            start_date = (now - timedelta(days=30)).strftime('%Y-%m-%d')
            end_date = now.strftime('%Y-%m-%d %H:%M:%S')
        elif date_range == '3m':
            start_date = (now - timedelta(days=90)).strftime('%Y-%m-%d')
            end_date = now.strftime('%Y-%m-%d %H:%M:%S')
        elif date_range == '1y':
            start_date = (now - timedelta(days=365)).strftime('%Y-%m-%d')
            end_date = now.strftime('%Y-%m-%d %H:%M:%S')
        elif date_range == 'all':
            start_date = None
            end_date = None
        else:
            start_date = (now - timedelta(days=7)).strftime('%Y-%m-%d')
            end_date = now.strftime('%Y-%m-%d %H:%M:%S')

        # Build the query with same filters as news feed
        if start_date and end_date:
            date_filter = f"AND publication_date >= '{start_date}' AND publication_date <= '{end_date}'"
        else:
            date_filter = ""

        topic_filter = ""
        if topic:
            # Handle topic filter - escape single quotes
            safe_topic = topic.replace("'", "''")
            topic_filter = f"""
            AND (
                topic = '{safe_topic}'
                OR title LIKE '%{safe_topic}%'
                OR summary LIKE '%{safe_topic}%'
            )
            """

        query = f"""
            SELECT category, COUNT(*) as count
            FROM articles
            WHERE category IS NOT NULL
            AND category != ''
            AND sentiment IS NOT NULL
            AND publication_date IS NOT NULL
            {date_filter}
            {topic_filter}
            AND title NOT LIKE '%Call@%'
            AND title NOT LIKE '%+91%'
            AND title NOT LIKE '%best%agency%'
            AND title NOT LIKE '%#1%'
            AND summary NOT LIKE '%Call@%'
            AND summary NOT LIKE '%phone%number%'
            AND news_source NOT LIKE '%medium.com/@%'
            GROUP BY category
            ORDER BY count DESC
        """

        results = await run_in_threadpool(db.fetch_all, query)

        # Convert to dictionary
        category_counts = {}
        for row in results:
            category_counts[row['category']] = row['count']

        logger.info(f"Category counts: {len(category_counts)} categories, date_range={date_range}, topic={topic}")

        return {"category_counts": category_counts}

    except Exception as e:
        logger.error(f"Error getting category counts: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/category/{category}/articles", dependencies=[Depends(verify_session_api)])
async def get_category_articles(
    category: str,
    date_range: Optional[str] = Query("7d", description="Date range: 24h, 7d, 30d, 3m, 1y, all"),
    topic: Optional[str] = Query(None, description="Optional topic filter"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=10, le=200, description="Articles per page"),
    db: Database = Depends(get_database_instance)
):
    """Get paginated articles for a specific category.

    Returns articles for the specified category with full article data.
    """
    from starlette.concurrency import run_in_threadpool

    try:
        # Calculate date range
        now = datetime.now()

        if date_range == '24h':
            start_date = (now - timedelta(days=1)).strftime('%Y-%m-%d')
            end_date = now.strftime('%Y-%m-%d %H:%M:%S')
        elif date_range == '72h':
            start_date = (now - timedelta(days=3)).strftime('%Y-%m-%d')
            end_date = now.strftime('%Y-%m-%d %H:%M:%S')
        elif date_range == '7d':
            start_date = (now - timedelta(days=7)).strftime('%Y-%m-%d')
            end_date = now.strftime('%Y-%m-%d %H:%M:%S')
        elif date_range == '30d':
            start_date = (now - timedelta(days=30)).strftime('%Y-%m-%d')
            end_date = now.strftime('%Y-%m-%d %H:%M:%S')
        elif date_range == '3m':
            start_date = (now - timedelta(days=90)).strftime('%Y-%m-%d')
            end_date = now.strftime('%Y-%m-%d %H:%M:%S')
        elif date_range == '1y':
            start_date = (now - timedelta(days=365)).strftime('%Y-%m-%d')
            end_date = now.strftime('%Y-%m-%d %H:%M:%S')
        elif date_range == 'all':
            start_date = None
            end_date = None
        else:
            start_date = (now - timedelta(days=7)).strftime('%Y-%m-%d')
            end_date = now.strftime('%Y-%m-%d %H:%M:%S')

        # Build filters
        if start_date and end_date:
            date_filter = f"AND publication_date >= '{start_date}' AND publication_date <= '{end_date}'"
        else:
            date_filter = ""

        topic_filter = ""
        if topic:
            safe_topic = topic.replace("'", "''")
            topic_filter = f"""
            AND (
                topic = '{safe_topic}'
                OR title LIKE '%{safe_topic}%'
                OR summary LIKE '%{safe_topic}%'
            )
            """

        # Escape category for query
        safe_category = category.replace("'", "''")

        # Get total count first
        count_query = f"""
            SELECT COUNT(*) as total
            FROM articles
            WHERE category = '{safe_category}'
            AND sentiment IS NOT NULL
            AND publication_date IS NOT NULL
            {date_filter}
            {topic_filter}
            AND title NOT LIKE '%Call@%'
            AND title NOT LIKE '%+91%'
            AND title NOT LIKE '%best%agency%'
            AND title NOT LIKE '%#1%'
            AND summary NOT LIKE '%Call@%'
            AND summary NOT LIKE '%phone%number%'
            AND news_source NOT LIKE '%medium.com/@%'
        """

        count_result = await run_in_threadpool(db.fetch_one, count_query)
        total_count = count_result['total'] if count_result else 0

        # Calculate pagination
        offset = (page - 1) * per_page
        total_pages = (total_count + per_page - 1) // per_page if total_count > 0 else 0

        # Get articles
        query = f"""
            SELECT
                uri, title, summary, news_source, publication_date,
                category, topic, sentiment, sentiment_explanation,
                time_to_impact, time_to_impact_explanation, tags,
                bias, factual_reporting, mbfc_credibility_rating,
                bias_country, future_signal, future_signal_explanation
            FROM articles
            WHERE category = '{safe_category}'
            AND sentiment IS NOT NULL
            AND publication_date IS NOT NULL
            {date_filter}
            {topic_filter}
            AND title NOT LIKE '%Call@%'
            AND title NOT LIKE '%+91%'
            AND title NOT LIKE '%best%agency%'
            AND title NOT LIKE '%#1%'
            AND summary NOT LIKE '%Call@%'
            AND summary NOT LIKE '%phone%number%'
            AND news_source NOT LIKE '%medium.com/@%'
            ORDER BY publication_date DESC
            LIMIT {per_page} OFFSET {offset}
        """

        results = await run_in_threadpool(db.fetch_all, query)

        # Transform to article format (flat structure for frontend compatibility)
        articles = []
        for row in results:
            articles.append({
                'uri': row['uri'],
                'title': row['title'],
                'summary': row['summary'],
                'news_source': row['news_source'],
                'bias': row['bias'],
                'factual_reporting': row['factual_reporting'],
                'mbfc_credibility_rating': row['mbfc_credibility_rating'],
                'bias_country': row['bias_country'],
                'publication_date': row['publication_date'],
                'category': row['category'],
                'topic': row['topic'],
                'sentiment': row['sentiment'],
                'sentiment_explanation': row['sentiment_explanation'],
                'time_to_impact': row['time_to_impact'],
                'time_to_impact_explanation': row['time_to_impact_explanation'],
                'tags': row['tags'] if row['tags'] else '',
                'future_signal': row['future_signal'],
                'future_signal_explanation': row['future_signal_explanation']
            })

        logger.info(f"Category articles: {len(articles)} of {total_count} for '{category}', page {page}")

        return {
            "articles": articles,
            "total_count": total_count,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "category": category
        }

    except Exception as e:
        logger.error(f"Error getting category articles: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


# ============================================================================
# Dashboard Schedule Routes
# ============================================================================

from pydantic import BaseModel, Field

class DashboardScheduleSettings(BaseModel):
    """Settings for scheduled dashboard generation."""
    schedule_enabled: Optional[bool] = None
    schedule_type: Optional[str] = None  # 'interval' or 'daily'
    check_interval: Optional[int] = Field(None, ge=1, le=168)
    interval_unit: Optional[str] = None
    schedule_time: Optional[str] = None  # HH:MM format for daily schedules
    generate_briefing: Optional[bool] = None
    generate_highlights: Optional[bool] = None
    generate_narratives: Optional[bool] = None
    persona: Optional[str] = None


@router.get("/dashboard/schedule/status")
async def get_dashboard_schedule_status(
    session=Depends(verify_session)
):
    """Get current dashboard schedule and monitor status."""
    from sqlalchemy import text

    db = get_database_instance()
    conn = db._temp_get_connection()

    try:
        # Get settings
        settings_result = conn.execute(text("""
            SELECT
                schedule_enabled, schedule_type, check_interval, interval_unit, schedule_time,
                generate_briefing, generate_highlights, generate_narratives,
                persona, model, topic_filter
            FROM newsfeed_dashboard_settings
            WHERE id = 1
        """))
        settings = settings_result.mappings().first()

        # Get status
        status_result = conn.execute(text("""
            SELECT
                last_run_time, next_run_time, last_run_status,
                last_error, is_running, run_count
            FROM newsfeed_dashboard_monitor_status
            WHERE id = 1
        """))
        status = status_result.mappings().first()

        conn.close()

        return {
            "settings": dict(settings) if settings else None,
            "status": dict(status) if status else None
        }

    except Exception as e:
        logger.error(f"Error getting schedule status: {e}")
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dashboard/schedule/settings")
async def update_dashboard_schedule_settings(
    request: DashboardScheduleSettings,
    session=Depends(verify_session)
):
    """Update dashboard schedule settings."""
    from sqlalchemy import text
    from datetime import datetime, timedelta

    db = get_database_instance()
    conn = db._temp_get_connection()

    try:
        updates = []
        params = {}

        if request.schedule_enabled is not None:
            updates.append("schedule_enabled = :schedule_enabled")
            params["schedule_enabled"] = request.schedule_enabled
        if request.schedule_type is not None:
            updates.append("schedule_type = :schedule_type")
            params["schedule_type"] = request.schedule_type
        if request.check_interval is not None:
            updates.append("check_interval = :check_interval")
            params["check_interval"] = request.check_interval
        if request.interval_unit is not None:
            updates.append("interval_unit = :interval_unit")
            params["interval_unit"] = request.interval_unit
        if request.schedule_time is not None:
            updates.append("schedule_time = :schedule_time")
            # Convert HH:MM string to time
            from datetime import time as dt_time
            try:
                hour, minute = map(int, request.schedule_time.split(':'))
                params["schedule_time"] = dt_time(hour, minute)
            except:
                params["schedule_time"] = dt_time(9, 0)  # Default to 9:00
        if request.generate_briefing is not None:
            updates.append("generate_briefing = :generate_briefing")
            params["generate_briefing"] = request.generate_briefing
        if request.generate_highlights is not None:
            updates.append("generate_highlights = :generate_highlights")
            params["generate_highlights"] = request.generate_highlights
        if request.generate_narratives is not None:
            updates.append("generate_narratives = :generate_narratives")
            params["generate_narratives"] = request.generate_narratives
        if request.persona is not None:
            updates.append("persona = :persona")
            params["persona"] = request.persona

        updates.append("updated_at = NOW()")

        if updates:
            conn.execute(text(f"""
                UPDATE newsfeed_dashboard_settings
                SET {', '.join(updates)}
                WHERE id = 1
            """), params)

        # Update next_run_time in status if schedule is being enabled
        if request.schedule_enabled:
            schedule_type = request.schedule_type or 'interval'

            if schedule_type == 'daily' and request.schedule_time:
                # For daily schedule, calculate next occurrence of the time
                from datetime import time as dt_time
                try:
                    hour, minute = map(int, request.schedule_time.split(':'))
                    schedule_time = dt_time(hour, minute)
                except:
                    schedule_time = dt_time(9, 0)

                now = datetime.now()
                next_run = now.replace(hour=schedule_time.hour, minute=schedule_time.minute, second=0, microsecond=0)
                if next_run <= now:
                    next_run += timedelta(days=1)
            else:
                # For interval schedule
                interval = request.check_interval or 24
                unit = request.interval_unit or 'hours'

                if unit == 'hours':
                    next_run = datetime.now() + timedelta(hours=interval)
                else:
                    next_run = datetime.now() + timedelta(days=interval)

            conn.execute(text("""
                UPDATE newsfeed_dashboard_monitor_status
                SET next_run_time = :next_run, updated_at = NOW()
                WHERE id = 1
            """), {"next_run": next_run})

        conn.commit()
        conn.close()

        return {"success": True, "message": "Settings updated"}

    except Exception as e:
        logger.error(f"Error updating schedule settings: {e}")
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dashboard/schedule/run-now")
async def run_dashboard_generation_now(
    topic: Optional[str] = Query(None, description="Topic filter"),
    session=Depends(verify_session)
):
    """Trigger immediate dashboard generation."""
    from app.tasks.newsfeed_dashboard_monitor import run_dashboard_generation_now

    try:
        db = get_database_instance()
        result = await run_dashboard_generation_now(db, topic_filter=topic)

        return {
            "success": result.get("success", False),
            "briefing_generated": result.get("briefing_generated", False),
            "highlights_generated": result.get("highlights_generated", False),
            "narratives_generated": result.get("narratives_generated", False),
            "error": result.get("error"),
        }
    except Exception as e:
        logger.error(f"Failed to run dashboard generation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Internal functions for scheduled generation
async def _generate_six_articles_internal(
    persona: str = "CEO",
    model: str = "gpt-5.4-mini",
    topic: Optional[str] = None
) -> Optional[List[Dict]]:
    """
    Internal function to generate six articles briefing for scheduler.

    Returns:
        List of generated article dicts, or None if generation failed
    """
    from app.services.news_feed_service import get_news_feed_service
    from app.schemas.news_feed import NewsFeedRequest

    db = get_database_instance()
    news_feed_service = get_news_feed_service(db)

    # Build request
    request = NewsFeedRequest(
        topic=topic,
        max_articles=50,
        model=model,
        persona=persona
    )

    # Get articles using the correct async method
    articles_data = await news_feed_service._get_articles_for_date_range(
        date_range="24h",
        max_articles=50,
        topic=topic
    )

    if not articles_data:
        logger.warning("No articles found for briefing generation")
        return None

    # Generate (forces fresh generation, bypassing cache)
    target_date = datetime.now()
    six_articles = await news_feed_service._generate_six_articles_with_political_analysis(
        articles_data, target_date, request
    )
    logger.info(f"Six articles briefing generated successfully ({len(six_articles) if six_articles else 0} articles)")
    return six_articles


async def _regenerate_highlights_internal(topic: Optional[str] = None):
    """Internal function to regenerate highlights for scheduler.
    Calls the incident tracking API to generate and cache incidents.
    """
    from app.routes.vector_routes import analyze_incidents, _IncidentTrackingRequest
    from app.database import get_database_instance
    from sqlalchemy import text

    logger.info(f"Highlights regeneration requested for topic: {topic}")

    try:
        # Get all topics if none specified
        if not topic:
            db = get_database_instance()
            conn = db._temp_get_connection()
            result = conn.execute(text("SELECT DISTINCT topic FROM keyword_groups WHERE topic IS NOT NULL LIMIT 25"))
            topics_list = [row[0] for row in result.fetchall()]
            conn.close()
        else:
            topics_list = [topic]

        if not topics_list:
            logger.warning("No topics found for highlights generation")
            return None

        # Calculate date range (last 7 days by default)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)

        # Create request for incident tracking
        request = _IncidentTrackingRequest(
            topics=topics_list,
            days_limit=7,
            start_date=start_date.strftime('%Y-%m-%d'),
            end_date=end_date.strftime('%Y-%m-%d'),
            max_articles=100,
            model='gpt-5.4-mini',
            force_regenerate=True  # Force regenerate to ensure fresh data is cached
        )

        # Call the incident tracking endpoint (will save to cache)
        result = await analyze_incidents(request, session=None)

        logger.info(f"Highlights generated: {len(result.get('incidents', []))} incidents")
        return result

    except Exception as e:
        logger.error(f"Failed to regenerate highlights: {e}", exc_info=True)
        raise


async def _regenerate_narratives_internal(topic: Optional[str] = None):
    """Internal function to regenerate narratives for scheduler.
    Calls the article insights API to generate and cache narratives.
    """
    from app.routes.dashboard_routes import get_article_insights, ArticleInsightsRequest
    from app.database import get_database_instance
    from sqlalchemy import text

    logger.info(f"Narratives regeneration requested for topic: {topic}")

    try:
        db = get_database_instance()

        # Get all topics if none specified
        if not topic:
            conn = db._temp_get_connection()
            result = conn.execute(text("SELECT DISTINCT topic FROM keyword_groups WHERE topic IS NOT NULL LIMIT 25"))
            topics_list = [row[0] for row in result.fetchall()]
            conn.close()
        else:
            topics_list = [topic]

        if not topics_list:
            logger.warning("No topics found for narratives generation")
            return None

        # Calculate date range (last 7 days by default)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)

        all_themes = []

        # Generate narratives for each topic
        for topic_name in topics_list:
            try:
                # Create request for article insights
                request = ArticleInsightsRequest(
                    start_date=start_date.strftime('%Y-%m-%d'),
                    end_date=end_date.strftime('%Y-%m-%d'),
                    days_limit=7,
                    force_regenerate=True,  # Force regenerate to ensure fresh data is cached
                    model='gpt-5.4-mini'
                )

                # Create a mock session dict for the endpoint
                mock_session = {'user_id': 'scheduler', 'role': 'admin'}

                # Call the article insights endpoint (will save to cache)
                themes = await get_article_insights(
                    topic_name=topic_name,
                    request=request,
                    db=db,
                    session=mock_session
                )

                if themes:
                    all_themes.extend(themes)
                    logger.info(f"Generated {len(themes)} themes for topic: {topic_name}")

            except HTTPException as http_err:
                # Expected errors like "not enough articles"
                logger.info(f"Skipping narratives for topic {topic_name}: {http_err.detail}")
            except Exception as e:
                logger.warning(f"Failed to generate narratives for topic {topic_name}: {e}")

        logger.info(f"Narratives generated: {len(all_themes)} total themes")
        return all_themes

    except Exception as e:
        logger.error(f"Failed to regenerate narratives: {e}", exc_info=True)
        raise


# ============================================================================
# Dashboard Snapshot Functions - For persisting auto-generated dashboard state
# ============================================================================

def save_dashboard_snapshot(
    topic: Optional[str],
    persona: str,
    model: str,
    briefing_articles: Optional[List[Dict]] = None,
    highlights_data: Optional[Dict] = None,
    narratives_data: Optional[Dict] = None,
    articles_analyzed: Optional[int] = None,
    generation_duration: Optional[float] = None,
    error_message: Optional[str] = None
) -> Optional[int]:
    """
    Save a dashboard snapshot to the database.
    Replaces any existing snapshot for the same topic.

    Returns the snapshot ID if successful, None otherwise.
    """
    from sqlalchemy import text, delete, insert
    from app.database import get_database_instance
    import json

    db = get_database_instance()
    conn = db._temp_get_connection()

    try:
        # Delete existing snapshot for this topic
        conn.execute(text("""
            DELETE FROM newsfeed_dashboard_snapshots
            WHERE topic IS NOT DISTINCT FROM :topic
        """), {"topic": topic})

        # Insert new snapshot
        result = conn.execute(text("""
            INSERT INTO newsfeed_dashboard_snapshots (
                topic, persona, model,
                briefing_articles, briefing_generated,
                highlights_data, highlights_generated,
                narratives_data, narratives_generated,
                articles_analyzed, generation_duration_seconds, error_message,
                generated_at
            ) VALUES (
                :topic, :persona, :model,
                :briefing_articles, :briefing_generated,
                :highlights_data, :highlights_generated,
                :narratives_data, :narratives_generated,
                :articles_analyzed, :generation_duration, :error_message,
                NOW()
            )
            RETURNING id
        """), {
            "topic": topic,
            "persona": persona,
            "model": model,
            "briefing_articles": json.dumps(briefing_articles) if briefing_articles else None,
            "briefing_generated": briefing_articles is not None and len(briefing_articles) > 0,
            "highlights_data": json.dumps(highlights_data) if highlights_data else None,
            "highlights_generated": highlights_data is not None,
            "narratives_data": json.dumps(narratives_data) if narratives_data else None,
            "narratives_generated": narratives_data is not None,
            "articles_analyzed": articles_analyzed,
            "generation_duration": generation_duration,
            "error_message": error_message,
        })

        row = result.fetchone()
        conn.commit()

        snapshot_id = row[0] if row else None
        logger.info(f"Saved dashboard snapshot (ID: {snapshot_id}) for topic: {topic}")
        return snapshot_id

    except Exception as e:
        logger.error(f"Error saving dashboard snapshot: {e}", exc_info=True)
        conn.rollback()
        return None
    finally:
        conn.close()


def get_latest_dashboard_snapshot(topic: Optional[str] = None) -> Optional[Dict]:
    """
    Get the latest dashboard snapshot for a topic.

    Args:
        topic: Topic filter, or None for all-topics snapshot

    Returns:
        Snapshot dict with briefing_articles, highlights_data, narratives_data, etc.
    """
    from sqlalchemy import text
    from app.database import get_database_instance

    db = get_database_instance()
    conn = db._temp_get_connection()

    try:
        result = conn.execute(text("""
            SELECT
                id, topic, generated_at, persona, model,
                briefing_articles, briefing_generated,
                highlights_data, highlights_generated,
                narratives_data, narratives_generated,
                articles_analyzed, generation_duration_seconds, error_message
            FROM newsfeed_dashboard_snapshots
            WHERE topic IS NOT DISTINCT FROM :topic
            ORDER BY generated_at DESC
            LIMIT 1
        """), {"topic": topic})

        row = result.mappings().first()
        if not row:
            return None

        return dict(row)

    except Exception as e:
        logger.error(f"Error getting dashboard snapshot: {e}", exc_info=True)
        return None
    finally:
        conn.close()


@router.get("/dashboard/snapshot/latest")
async def get_latest_snapshot(
    topic: Optional[str] = Query(None, description="Topic filter"),
    session=Depends(verify_session_api)
):
    """
    Get the latest auto-generated dashboard snapshot.

    Returns the most recent snapshot with briefing articles, highlights, and narratives
    that were auto-generated by the scheduler.
    """
    snapshot = get_latest_dashboard_snapshot(topic)

    if not snapshot:
        return {
            "success": True,
            "has_snapshot": False,
            "snapshot": None,
            "message": "No auto-generated dashboard found. Enable scheduling to auto-generate dashboards."
        }

    return {
        "success": True,
        "has_snapshot": True,
        "snapshot": {
            "id": snapshot["id"],
            "topic": snapshot["topic"],
            "generated_at": snapshot["generated_at"].isoformat() if snapshot["generated_at"] else None,
            "persona": snapshot["persona"],
            "model": snapshot["model"],
            "briefing_articles": snapshot["briefing_articles"],
            "briefing_generated": snapshot["briefing_generated"],
            "highlights_data": snapshot["highlights_data"],
            "highlights_generated": snapshot["highlights_generated"],
            "narratives_data": snapshot["narratives_data"],
            "narratives_generated": snapshot["narratives_generated"],
            "articles_analyzed": snapshot["articles_analyzed"],
            "generation_duration_seconds": snapshot["generation_duration_seconds"],
        }
    }


# ============================================================================
# Saved Incidents and Narratives - Persistent Storage
# ============================================================================

@router.get("/saved/incidents")
async def get_saved_incidents(
    topic: Optional[str] = Query(None, description="Topic filter"),
    session=Depends(verify_session_api),
    db: Database = Depends(get_database_instance)
):
    """Get all saved incidents for the current user."""
    from sqlalchemy import text

    try:
        user_id = session.get("user_id")
        logger.info(f"[get_saved_incidents] Fetching incidents for topic: {topic}, user_id: {user_id}")
        conn = db._temp_get_connection()

        if topic:
            result = conn.execute(text("""
                SELECT id, incident_name, topic, incident_data, saved_at
                FROM saved_incidents
                WHERE (user_id = :user_id OR user_id IS NULL)
                AND topic = :topic
                ORDER BY saved_at DESC
            """), {"user_id": user_id, "topic": topic})
        else:
            result = conn.execute(text("""
                SELECT id, incident_name, topic, incident_data, saved_at
                FROM saved_incidents
                WHERE (user_id = :user_id OR user_id IS NULL)
                ORDER BY saved_at DESC
            """), {"user_id": user_id})

        rows = result.mappings().all()
        conn.close()

        logger.info(f"[get_saved_incidents] Found {len(rows)} rows for topic: {topic}")

        incidents = []
        for row in rows:
            # Handle JSONB - might be dict or might need parsing
            raw_data = row["incident_data"]
            if raw_data is None:
                incident_data = {}
            elif isinstance(raw_data, str):
                # If it's a string, parse it
                import json as json_module
                incident_data = json_module.loads(raw_data)
            else:
                # Already a dict from JSONB
                incident_data = dict(raw_data) if raw_data else {}

            incident_data["_saved_id"] = row["id"]
            incident_data["_saved_at"] = row["saved_at"].isoformat() if row["saved_at"] else None
            incidents.append(incident_data)
            logger.info(f"[get_saved_incidents] Incident: {incident_data.get('name')} topic: {incident_data.get('topic')}")

        logger.info(f"[get_saved_incidents] Returning {len(incidents)} incidents")
        return {
            "success": True,
            "incidents": incidents,
            "count": len(incidents)
        }
    except Exception as e:
        logger.error(f"Error getting saved incidents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/saved/incidents")
async def save_incident(
    incident_data: dict,
    session=Depends(verify_session_api),
    db: Database = Depends(get_database_instance)
):
    """Save an incident with full data."""
    from sqlalchemy import text
    import json

    try:
        user_id = session.get("user_id")
        incident_name = incident_data.get("name") or incident_data.get("title")
        topic = incident_data.get("topic", "")
        logger.info(f"[save_incident] Saving incident: {incident_name}, topic: {topic}, user_id: {user_id}")

        if not incident_name:
            raise HTTPException(status_code=400, detail="Incident name is required")

        conn = db._temp_get_connection()

        # Handle upsert manually to deal with NULL user_id (NULL != NULL in unique constraints)
        # First try to update existing row
        if user_id is not None:
            update_result = conn.execute(text("""
                UPDATE saved_incidents
                SET incident_data = :data, updated_at = NOW()
                WHERE incident_name = :name AND topic = :topic AND user_id = :user_id
            """), {
                "name": incident_name,
                "topic": topic,
                "user_id": user_id,
                "data": json.dumps(incident_data)
            })
        else:
            update_result = conn.execute(text("""
                UPDATE saved_incidents
                SET incident_data = :data, updated_at = NOW()
                WHERE incident_name = :name AND topic = :topic AND user_id IS NULL
            """), {
                "name": incident_name,
                "topic": topic,
                "data": json.dumps(incident_data)
            })

        # If no rows updated, insert new row
        if update_result.rowcount == 0:
            logger.info(f"[save_incident] No existing row found, inserting new incident")
            conn.execute(text("""
                INSERT INTO saved_incidents (incident_name, topic, user_id, incident_data, updated_at)
                VALUES (:name, :topic, :user_id, :data, NOW())
            """), {
                "name": incident_name,
                "topic": topic,
                "user_id": user_id,
                "data": json.dumps(incident_data)
            })
        else:
            logger.info(f"[save_incident] Updated existing incident row")

        conn.commit()
        conn.close()

        logger.info(f"Saved incident: {incident_name} for topic: {topic}")
        return {"success": True, "message": f"Incident '{incident_name}' saved"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving incident: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/saved/incidents/{incident_name}")
async def delete_saved_incident(
    incident_name: str,
    topic: str = Query(..., description="Topic of the incident"),
    session=Depends(verify_session_api),
    db: Database = Depends(get_database_instance)
):
    """Delete a saved incident."""
    from sqlalchemy import text

    try:
        user_id = session.get("user_id")
        conn = db._temp_get_connection()

        result = conn.execute(text("""
            DELETE FROM saved_incidents
            WHERE incident_name = :name AND topic = :topic
            AND (user_id = :user_id OR user_id IS NULL)
        """), {"name": incident_name, "topic": topic, "user_id": user_id})

        conn.commit()
        deleted = result.rowcount > 0
        conn.close()

        if deleted:
            logger.info(f"Deleted saved incident: {incident_name}")
            return {"success": True, "message": f"Incident '{incident_name}' removed"}
        else:
            raise HTTPException(status_code=404, detail="Incident not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting incident: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/saved/incidents/{incident_name}/articles")
async def add_article_to_incident(
    incident_name: str,
    request_body: dict,
    session=Depends(verify_session_api),
    db: Database = Depends(get_database_instance)
):
    """Add an article to an existing saved incident."""
    from sqlalchemy import text
    import json

    try:
        user_id = session.get("user_id")
        topic = request_body.get("topic", "")
        article_uri = request_body.get("article_uri")

        if not article_uri:
            raise HTTPException(status_code=400, detail="article_uri is required")

        conn = db._temp_get_connection()

        # First, fetch the existing incident
        result = conn.execute(text("""
            SELECT id, incident_data
            FROM saved_incidents
            WHERE incident_name = :name AND topic = :topic
            AND (user_id = :user_id OR user_id IS NULL)
        """), {"name": incident_name, "topic": topic, "user_id": user_id})

        row = result.mappings().fetchone()

        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail="Incident not found")

        # Parse existing incident data
        incident_data = row["incident_data"] if row["incident_data"] else {}

        # Ensure article_uris list exists
        if "article_uris" not in incident_data:
            incident_data["article_uris"] = []

        # Check if article is already in the incident
        if article_uri in incident_data["article_uris"]:
            conn.close()
            return {
                "success": True,
                "message": "Article already in incident",
                "updated_incident": incident_data
            }

        # Add the new article URI
        incident_data["article_uris"].append(article_uri)

        # Optionally add article metadata if provided
        if "article_metadata" in request_body:
            if "article_metadata" not in incident_data:
                incident_data["article_metadata"] = []
            incident_data["article_metadata"].append(request_body["article_metadata"])

        # Update the incident in the database
        conn.execute(text("""
            UPDATE saved_incidents
            SET incident_data = :data, updated_at = NOW()
            WHERE incident_name = :name AND topic = :topic
            AND (user_id = :user_id OR user_id IS NULL)
        """), {
            "data": json.dumps(incident_data),
            "name": incident_name,
            "topic": topic,
            "user_id": user_id
        })

        conn.commit()
        conn.close()

        logger.info(f"Added article to incident: {incident_name}")
        return {
            "success": True,
            "message": f"Article added to incident '{incident_name}'",
            "updated_incident": incident_data
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding article to incident: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/saved/incidents/{incident_name}/notes")
async def add_note_to_incident(
    incident_name: str,
    request_body: dict,
    session=Depends(verify_session_api),
    db: Database = Depends(get_database_instance)
):
    """Add an analyst note to an existing saved incident."""
    from sqlalchemy import text
    import json
    from datetime import datetime

    try:
        user_id = session.get("user_id")
        topic = request_body.get("topic", "")
        analyst = request_body.get("analyst", "")
        comment = request_body.get("comment", "")
        saved_id = request_body.get("saved_id")  # Unique database ID

        if not analyst or not comment:
            raise HTTPException(status_code=400, detail="analyst and comment are required")

        conn = db._temp_get_connection()

        # Fetch the existing incident - prefer saved_id if provided for precise targeting
        if saved_id:
            result = conn.execute(text("""
                SELECT id, incident_data
                FROM saved_incidents
                WHERE id = :saved_id
                AND (user_id = :user_id OR user_id IS NULL)
            """), {"saved_id": saved_id, "user_id": user_id})
        else:
            result = conn.execute(text("""
                SELECT id, incident_data
                FROM saved_incidents
                WHERE incident_name = :name AND topic = :topic
                AND (user_id = :user_id OR user_id IS NULL)
            """), {"name": incident_name, "topic": topic, "user_id": user_id})

        row = result.mappings().fetchone()

        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail="Incident not found")

        incident_db_id = row["id"]

        # Parse existing incident data
        incident_data = row["incident_data"] if row["incident_data"] else {}

        # Create the new note
        from datetime import timezone
        now = datetime.now(timezone.utc)
        note = {
            "id": f"{int(now.timestamp() * 1000)}",  # Timestamp-based ID
            "timestamp": now.isoformat().replace('+00:00', 'Z'),  # Proper ISO 8601 with Z suffix
            "analyst": analyst,
            "comment": comment
        }

        # Ensure analyst_notes list exists
        if "analyst_notes" not in incident_data:
            incident_data["analyst_notes"] = []

        # Add the new note at the beginning (most recent first)
        incident_data["analyst_notes"].insert(0, note)

        # Update the incident in the database using the unique ID
        conn.execute(text("""
            UPDATE saved_incidents
            SET incident_data = :data, updated_at = NOW()
            WHERE id = :incident_id
        """), {
            "data": json.dumps(incident_data),
            "incident_id": incident_db_id
        })

        conn.commit()
        conn.close()

        logger.info(f"Added note to incident: {incident_name} (id={incident_db_id}) by {analyst}")
        return {
            "success": True,
            "note": note,
            "updated_incident": incident_data
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding note to incident: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/saved/narratives")
async def get_saved_narratives(
    topic: Optional[str] = Query(None, description="Topic filter"),
    session=Depends(verify_session_api),
    db: Database = Depends(get_database_instance)
):
    """Get all saved narratives for the current user."""
    from sqlalchemy import text

    try:
        user_id = session.get("user_id")
        conn = db._temp_get_connection()

        if topic:
            result = conn.execute(text("""
                SELECT id, narrative_name, topic, narrative_data, saved_at
                FROM saved_narratives
                WHERE (user_id = :user_id OR user_id IS NULL)
                AND topic = :topic
                ORDER BY saved_at DESC
            """), {"user_id": user_id, "topic": topic})
        else:
            result = conn.execute(text("""
                SELECT id, narrative_name, topic, narrative_data, saved_at
                FROM saved_narratives
                WHERE (user_id = :user_id OR user_id IS NULL)
                ORDER BY saved_at DESC
            """), {"user_id": user_id})

        rows = result.mappings().all()
        conn.close()

        narratives = []
        for row in rows:
            narrative_data = row["narrative_data"] if row["narrative_data"] else {}
            narrative_data["_saved_id"] = row["id"]
            narrative_data["_saved_at"] = row["saved_at"].isoformat() if row["saved_at"] else None
            narratives.append(narrative_data)

        return {
            "success": True,
            "narratives": narratives,
            "count": len(narratives)
        }
    except Exception as e:
        logger.error(f"Error getting saved narratives: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/saved/narratives")
async def save_narrative(
    narrative_data: dict,
    session=Depends(verify_session_api),
    db: Database = Depends(get_database_instance)
):
    """Save a narrative with full data."""
    from sqlalchemy import text
    import json

    try:
        user_id = session.get("user_id")
        narrative_name = narrative_data.get("name") or narrative_data.get("theme_name")
        topic = narrative_data.get("topic", "")

        if not narrative_name:
            raise HTTPException(status_code=400, detail="Narrative name is required")

        conn = db._temp_get_connection()

        # Upsert - insert or update on conflict
        conn.execute(text("""
            INSERT INTO saved_narratives (narrative_name, topic, user_id, narrative_data, updated_at)
            VALUES (:name, :topic, :user_id, :data, NOW())
            ON CONFLICT (narrative_name, topic, user_id)
            DO UPDATE SET narrative_data = :data, updated_at = NOW()
        """), {
            "name": narrative_name,
            "topic": topic,
            "user_id": user_id,
            "data": json.dumps(narrative_data)
        })

        conn.commit()
        conn.close()

        logger.info(f"Saved narrative: {narrative_name} for topic: {topic}")
        return {"success": True, "message": f"Narrative '{narrative_name}' saved"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving narrative: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/saved/narratives/{narrative_name}")
async def delete_saved_narrative(
    narrative_name: str,
    topic: Optional[str] = Query(None, description="Topic of the narrative"),
    session=Depends(verify_session_api),
    db: Database = Depends(get_database_instance)
):
    """Delete a saved narrative."""
    from sqlalchemy import text

    try:
        user_id = session.get("user_id")
        conn = db._temp_get_connection()

        if topic:
            result = conn.execute(text("""
                DELETE FROM saved_narratives
                WHERE narrative_name = :name AND topic = :topic
                AND (user_id = :user_id OR user_id IS NULL)
            """), {"name": narrative_name, "topic": topic, "user_id": user_id})
        else:
            result = conn.execute(text("""
                DELETE FROM saved_narratives
                WHERE narrative_name = :name
                AND (user_id = :user_id OR user_id IS NULL)
            """), {"name": narrative_name, "user_id": user_id})

        conn.commit()
        deleted = result.rowcount > 0
        conn.close()

        if deleted:
            logger.info(f"Deleted saved narrative: {narrative_name}")
            return {"success": True, "message": f"Narrative '{narrative_name}' removed"}
        else:
            raise HTTPException(status_code=404, detail="Narrative not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting narrative: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/filter-options", dependencies=[Depends(verify_session_api)])
async def get_filter_options(
    date_range: Optional[str] = Query("7d", description="Date range: 24h, 7d, 30d, 3m, 1y, all"),
    topic: Optional[str] = Query(None, description="Optional topic filter"),
    db: Database = Depends(get_database_instance)
):
    """Get available filter options (sources, factuality levels) for article list.

    Returns distinct sources and factuality levels from articles matching
    the current date range and topic filters.
    """
    from starlette.concurrency import run_in_threadpool

    try:
        # Calculate date range
        now = datetime.now()

        if date_range == '24h':
            start_date = (now - timedelta(days=1)).strftime('%Y-%m-%d')
            end_date = now.strftime('%Y-%m-%d %H:%M:%S')
        elif date_range == '72h':
            start_date = (now - timedelta(days=3)).strftime('%Y-%m-%d')
            end_date = now.strftime('%Y-%m-%d %H:%M:%S')
        elif date_range == '7d':
            start_date = (now - timedelta(days=7)).strftime('%Y-%m-%d')
            end_date = now.strftime('%Y-%m-%d %H:%M:%S')
        elif date_range == '30d':
            start_date = (now - timedelta(days=30)).strftime('%Y-%m-%d')
            end_date = now.strftime('%Y-%m-%d %H:%M:%S')
        elif date_range == '3m':
            start_date = (now - timedelta(days=90)).strftime('%Y-%m-%d')
            end_date = now.strftime('%Y-%m-%d %H:%M:%S')
        elif date_range == '1y':
            start_date = (now - timedelta(days=365)).strftime('%Y-%m-%d')
            end_date = now.strftime('%Y-%m-%d %H:%M:%S')
        elif date_range == 'all':
            start_date = None
            end_date = None
        else:
            start_date = (now - timedelta(days=7)).strftime('%Y-%m-%d')
            end_date = now.strftime('%Y-%m-%d %H:%M:%S')

        # Use facade to get filter options
        db_facade = DatabaseQueryFacade(db, logger)
        result = await run_in_threadpool(
            db_facade.get_article_filter_options,
            start_date,
            end_date,
            topic
        )

        logger.info(f"Filter options: {len(result['sources'])} sources, {len(result['factuality'])} factuality levels, {len(result['bias'])} bias levels")

        return result

    except Exception as e:
        logger.error(f"Error getting filter options: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/topic/{topic_name}/categories", dependencies=[Depends(verify_session_api)])
async def get_topic_categories(
    topic_name: str,
):
    """Get the configured categories for a specific topic.

    Returns the categories defined in config.json for the given topic.
    """
    from app.config.config import load_config

    try:
        config = load_config()
        topic_configs = {t['name']: t for t in config.get('topics', [])}

        if topic_name not in topic_configs:
            raise HTTPException(status_code=404, detail=f"Topic '{topic_name}' not found")

        topic_config = topic_configs[topic_name]
        categories = topic_config.get('categories', [])

        return {
            "topic": topic_name,
            "categories": categories
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting topic categories: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
