"""Application factory for creating and configuring the FastAPI app."""

import logging
import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.middleware.setup import setup_middleware
from app.core.templates import setup_templates
from app.core.routers import register_routers
from app.database import Database
from app.startup import initialize_application
from app.core.logging_config import configure_logging

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    
    # Ensure logging is configured (in case app is created without run.py)
    configure_logging()
    
    # Initialize FastAPI app
    app = FastAPI(title="AuNoo AI")
    
    # Setup middleware
    setup_middleware(app)
    
    # Mount static files
    app.mount("/static", StaticFiles(directory="static"), name="static")
    
    # Setup templates
    templates = setup_templates()
    
    # Store templates in app state for access by routes
    app.state.templates = templates
    
    # Initialize components
    db = Database()
    app.state.db = db
    
    # Initialize OAuth providers
    try:
        from app.security.oauth import setup_oauth_providers
        configured_providers = setup_oauth_providers()
        logger.info(f"OAuth providers initialized: {configured_providers}")
    except Exception as e:
        logger.warning(f"OAuth initialization failed: {e}")
    
    # Set up templates for all routes that need them
    from app.routes.auth_routes import set_templates as set_auth_templates
    from app.routes.web_routes import set_templates as set_web_templates
    set_auth_templates(templates)
    set_web_templates(templates)
    
    # Register all routers
    register_routers(app)
    
    # Initialize application components
    try:
        initialize_application()
        logger.info("Application initialization completed successfully")
    except Exception as e:
        logger.error(f"Application initialization failed: {e}")
    
    logger.info("FastAPI application created and configured")
    return app