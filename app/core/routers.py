"""Router registration for the application."""

import logging
from fastapi import FastAPI

logger = logging.getLogger(__name__)


def register_routers(app: FastAPI):
    """Register all application routers."""
    
    # Import all routers
    from app.routes import database
    from app.routes.auth_routes import router as auth_router
    from app.routes.oauth_routes import router as oauth_router
    from app.routes.stats_routes import router as stats_router
    from app.routes.chat_routes import router as chat_router
    from app.routes.database import router as database_router
    from app.routes.dashboard_routes import router as dashboard_router
    from app.routes.topic_routes import router as topic_router
    from app.routes.onboarding_routes import router as onboarding_router
    from app.routes.podcast_routes import router as podcast_router
    from app.routes.vector_routes import router as vector_router
    from app.routes.saved_searches import router as saved_searches_router
    from app.routes.scenario_routes import (
        router as scenario_router,
        page_router as scenario_page_router,
    )
    from app.routes.topic_map_routes import (
        router as topic_map_api_router,
        page_router as topic_map_page_router,
    )
    from app.routes.auspex_routes import router as auspex_router
    from app.routes.newsletter_routes import router as newsletter_router, page_router as newsletter_page_router
    from app.routes.dataset_routes import router as dataset_router
    from app.routes.keyword_monitor_api import router as keyword_monitor_api_router
    from app.routes.keyword_monitor import router as keyword_monitor_router
    from app.routes.api_routes import router as api_router
    from app.routes import media_bias_routes
    from app.routes.model_bias_arena_routes import router as model_bias_arena_router
    from app.routes.web_routes import router as web_router
    from app.routes.forecast_chart_routes import router as forecast_chart_router, web_router as forecast_chart_web_router
    from app.routes.executive_summary_routes import router as executive_summary_router, web_router as executive_summary_web_router
    from app.routes.futures_cone_routes import router as futures_cone_router
    from app.routes.trend_convergence_routes import router as trend_convergence_router
    from app.routes.feed_routes import router as feed_router
    from app.routes.feed_clustering_routes import router as feed_clustering_router
    from app.routes.filter_routes import router as filter_router
    from app.routes.news_feed_routes import router as news_feed_router, page_router as news_feed_page_router
    
    # Register database routes
    app.include_router(database.router)
    
    # Authentication routes (login/logout)
    app.include_router(auth_router)
    
    # OAuth routes (authentication)
    app.include_router(oauth_router)
    
    # Stats and analytics
    app.include_router(stats_router)
    
    # Chat functionality
    app.include_router(chat_router)
    
    # Database management
    app.include_router(database_router)
    
    # Dashboard
    app.include_router(dashboard_router)
    
    # Topics
    app.include_router(topic_router)
    
    # Onboarding
    app.include_router(onboarding_router)
    
    # Podcast functionality
    app.include_router(podcast_router)
    
    # Vector search
    app.include_router(vector_router)
    
    # Saved searches
    app.include_router(saved_searches_router)
    
    # Scenarios
    app.include_router(scenario_router)
    app.include_router(scenario_page_router)
    
    # Topic maps (API + page)
    app.include_router(topic_map_api_router)
    app.include_router(topic_map_page_router)
    
    # Auspex service
    app.include_router(auspex_router)
    
    # Newsletter functionality
    app.include_router(newsletter_router)
    app.include_router(newsletter_page_router)
    
    # Dataset management
    app.include_router(dataset_router)
    
    # Media bias routes
    app.include_router(media_bias_routes.router)
    
    # Model bias arena routes
    app.include_router(model_bias_arena_router)
    
    # API routes with prefix
    app.include_router(api_router, prefix="/api")
    
    # Keyword monitoring
    app.include_router(keyword_monitor_router)
    app.include_router(keyword_monitor_api_router, prefix="/api")
    
    # Web routes (includes vector-analysis-improved, config, etc.)
    app.include_router(web_router)
    
    # Forecast chart routes
    app.include_router(forecast_chart_router)
    app.include_router(forecast_chart_web_router)
    
    # Executive summary routes (Market Signals & Strategic Risks)
    app.include_router(executive_summary_router)
    app.include_router(executive_summary_web_router)
    
    # Futures cone routes
    app.include_router(futures_cone_router)
    
    # Trend convergence routes
    app.include_router(trend_convergence_router)
    
    # Feed system routes
    app.include_router(feed_router)
    
    # Feed clustering routes
    app.include_router(feed_clustering_router)

    # Vantage desk filter routes
    app.include_router(filter_router)
    
    # News feed routes (API and pages)
    app.include_router(news_feed_router)
    app.include_router(news_feed_page_router)
    
    logger.info("All routers registered successfully")