"""Application factory for creating and configuring the FastAPI app."""

import logging
import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.middleware.setup import setup_middleware
from app.core.templates import setup_templates
from app.core.routers import register_routers
from app.database import Database
from app.startup import initialize_application
from app.core.logging_config import configure_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management."""
    # Startup logic
    try:
        # Use the new centralized application initialization
        from app.startup import initialize_application

        # Configure logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        )

        # Set specific log levels for different modules
        logger = logging.getLogger('main')
        logger.setLevel(logging.INFO)

        # EXPLICITLY ENABLE vector routes logging
        logging.getLogger('app.routes.vector_routes').setLevel(logging.INFO)

        # Set higher log levels for noisy modules
        logging.getLogger('numba').setLevel(logging.ERROR)
        logging.getLogger('httpx').setLevel(logging.WARNING)
        logging.getLogger('httpcore').setLevel(logging.WARNING)
        logging.getLogger('litellm').setLevel(logging.WARNING)
        logging.getLogger('app.analyzers.prompt_manager').setLevel(logging.WARNING)
        logging.getLogger('app.routes.prompt_routes').setLevel(logging.WARNING)
        logging.getLogger('app.env_loader').setLevel(logging.WARNING)
        logging.getLogger('app.relevance').setLevel(logging.WARNING)

        # Initialize async database
        try:
            from app.services.async_db import initialize_async_db
            await initialize_async_db()
            logger.info("Async database initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize async database: {e}")

        # Initialize the application
        success = initialize_application()
        if success:
            logger.info("Application initialized successfully")
        else:
            logger.error("Failed to initialize application")

        # Start the keyword monitor background task with a delay to prevent blocking startup
        async def delayed_keyword_monitor_start():
            """Start keyword monitor after a short delay to prevent blocking startup"""
            await asyncio.sleep(5)  # Wait 5 seconds after startup
            try:
                from app.tasks.keyword_monitor import run_keyword_monitor
                logger.info("Starting keyword monitor background task...")
                asyncio.create_task(run_keyword_monitor())
                logger.info("Keyword monitor background task started successfully")
            except Exception as e:
                logger.error(f"Failed to start keyword monitor background task: {str(e)}")

        # Start the delayed task
        asyncio.create_task(delayed_keyword_monitor_start())
        logger.info("Scheduled keyword monitor to start in 5 seconds")

    except Exception as e:
        logging.error(f"Error during startup: {str(e)}", exc_info=True)
        raise

    yield  # Application is running

    # Shutdown logic
    try:
        logger = logging.getLogger('main')
        logger.info("Application shutting down...")

        # Close async database pool
        try:
            from app.services.async_db import close_async_db
            await close_async_db()
            logger.info("Async database pool closed")
        except Exception as e:
            logger.error(f"Failed to close async database pool: {e}")

        # Clean up any resources here
        # For example, close database connections, stop background tasks, etc.

        logger.info("Application shutdown complete")
    except Exception as e:
        logging.error(f"Error during shutdown: {str(e)}", exc_info=True)
        raise


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    # Ensure logging is configured (in case app is created without run.py)
    configure_logging()

    # Initialize FastAPI app with lifespan management
    app = FastAPI(title="AuNoo AI", lifespan=lifespan)
    
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