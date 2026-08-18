"""Application factory for creating and configuring the FastAPI app."""

import logging
import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

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

        # ── Optional: override the default thread-pool executor ───────
        # Python defaults to ``min(32, cpu_count+4)`` workers for the
        # executor used by asyncio.to_thread / loop.run_in_executor(None).
        # On the 20-core production box that's 24 — usually fine. Set
        # SERVICE_EXECUTOR_MAX_WORKERS only if you actually need to
        # shrink (under-resourced box) or grow (very many background
        # services hammering it). Leaving unset preserves Python's default.
        import os, asyncio
        _ex_override = os.getenv("SERVICE_EXECUTOR_MAX_WORKERS")
        if _ex_override:
            from concurrent.futures import ThreadPoolExecutor
            loop = asyncio.get_running_loop()
            loop.set_default_executor(
                ThreadPoolExecutor(max_workers=int(_ex_override),
                                   thread_name_prefix="aunoo_pool_")
            )

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

        # LLM usage ledger — global litellm callbacks + batch writer.
        # Installed before any background task can make an LLM call so
        # spend is measured from call one.
        try:
            from app.services.llm_usage_logger import install as _install_llm_ledger
            _install_llm_ledger()
        except Exception:
            logger.exception("llm_usage_logger install failed (non-fatal)")
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

        # ── Background monitor tasks ──────────────────────────────────────
        # Each starts after a stagger delay so startup isn't blocked, and each
        # registers its task handle with the shutdown coordinator. On SIGTERM
        # the lifespan handler cancels these instead of letting them run until
        # systemd's stop-timeout SIGKILLs the process (which caused ~90s of
        # full 502 downtime on every restart).
        import importlib
        from app.utils.shutdown import register_task, is_shutting_down

        def _schedule_background_task(task_module, task_function, delay, label):
            """Import ``task_module.task_function`` after ``delay`` seconds and
            run it as a tracked background task."""
            async def _delayed_start():
                await asyncio.sleep(delay)
                # Don't spawn a fresh long-lived task if a restart already began
                # during the stagger window.
                if is_shutting_down():
                    return
                try:
                    mod = importlib.import_module(task_module)
                    func = getattr(mod, task_function)
                    logger.info(f"Starting {label} background task...")
                    register_task(asyncio.create_task(func()))
                    logger.info(f"{label} background task started successfully")
                except Exception as e:
                    logger.error(f"Failed to start {label}: {e}")
            register_task(asyncio.create_task(_delayed_start()))
            logger.info(f"Scheduled {label} to start in {delay}s")

        # (module, function, delay_seconds, label). Event-loop monitor first so
        # loop-lag telemetry covers the whole startup window. Forecast tracker
        # and Wiley candidate scheduler self-gate on their env flags (the task
        # exits immediately when the flag is unset), so they're always safe to
        # schedule here.
        _BACKGROUND_TASKS = [
            ("app.utils.event_loop_monitor", "run_event_loop_monitor", 3, "event-loop monitor"),
            ("app.tasks.keyword_monitor", "run_keyword_monitor", 5, "keyword monitor"),
            ("app.tasks.emerging_topics_monitor", "run_emerging_topics_monitor", 10, "emerging topics monitor"),
            ("app.tasks.observer_agent_monitor", "run_observer_agent_monitor", 15, "observer agent monitor"),
            ("app.tasks.newsfeed_dashboard_monitor", "run_newsfeed_dashboard_monitor", 20, "newsfeed dashboard monitor"),
            ("app.tasks.rss_feed_monitor", "run_rss_feed_monitor", 25, "RSS feed monitor"),
            ("app.tasks.timeline_task", "run_timeline_task", 30, "timeline mementos"),
            ("app.tasks.forecast_tracker_monitor", "run_forecast_tracker_monitor", 30, "forecast tracker monitor"),
            ("app.tasks.wiley_candidate_scheduler", "run_wiley_candidate_scheduler", 45, "Wiley candidate scheduler"),
        ]
        for _mod, _func, _delay, _label in _BACKGROUND_TASKS:
            _schedule_background_task(_mod, _func, _delay, _label)

        # Background-task workers only exist inside the process that started
        # them, so any row this database still has as "running" was orphaned by
        # a previous process. Close them now, or a caller polling one waits
        # forever on a task that will never finish and never fail.
        try:
            from app.services.background_task_manager import get_task_manager
            get_task_manager().reconcile_interrupted_tasks()
        except Exception as e:
            logger.warning("Background-task reconciliation skipped: %s", e)

        # Dynamically schedule background tasks for enabled analysis modules
        from app.core.modules import get_enabled_modules

        for module in get_enabled_modules():
            if module.task_module and module.task_function:
                _schedule_background_task(
                    module.task_module, module.task_function,
                    module.task_delay, module.name)
                for extra in module.extra_tasks:
                    _schedule_background_task(
                        extra.module, extra.function,
                        extra.delay, f"{module.name} ({extra.function})")

    except Exception as e:
        logging.error(f"Error during startup: {str(e)}", exc_info=True)
        raise

    yield  # Application is running

    # Shutdown logic
    try:
        logger = logging.getLogger('main')
        logger.info("Application shutting down...")

        # Signal cooperative loops to stop, then cancel the registered
        # background tasks so we don't wait out systemd's stop-timeout.
        try:
            from app.utils.shutdown import cancel_registered_tasks
            await cancel_registered_tasks(timeout=15.0)
        except Exception as e:
            logger.error(f"Failed to cancel background tasks: {e}")

        # Close async database pool
        try:
            from app.services.async_db import close_async_db
            await close_async_db()
            logger.info("Async database pool closed")
        except Exception as e:
            logger.error(f"Failed to close async database pool: {e}")

        # Cleanup AutomatedIngestService executor
        try:
            from app.database import get_database_instance
            from app.services.automated_ingest_service import AutomatedIngestService

            # Get the ingest service instance if it exists
            db = get_database_instance()
            if db and hasattr(db, '_ingest_service'):
                ingest_service = db._ingest_service
                await ingest_service.close()
                logger.info("AutomatedIngestService cleanup complete")
        except Exception as e:
            logger.error(f"Failed to cleanup AutomatedIngestService: {e}")

        # Clean up any other resources here
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

    # Dedicated Brand Watcher tenants: server-rendered templates read this via
    # request.app.state to trim the shared nav (React pages use /api/modules)
    from app.core.modules import is_dedicated_bw
    app.state.dedicated_bw = is_dedicated_bw()

    # Add validation error handler for debugging
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        logger.error(f"Validation error on {request.url.path}: {exc.errors()}")
        # Convert errors to JSON-serializable format (handle ValueError objects etc.)
        errors = []
        for err in exc.errors():
            error_dict = dict(err)
            # Convert any non-serializable objects to strings
            if 'ctx' in error_dict and error_dict['ctx']:
                ctx = error_dict['ctx']
                if isinstance(ctx, dict):
                    for key, value in ctx.items():
                        if isinstance(value, Exception):
                            ctx[key] = str(value)
            errors.append(error_dict)
        return JSONResponse(
            status_code=422,
            content={"detail": errors}
        )

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
    from app.routes.onboarding_routes import set_templates as set_onboarding_templates
    set_auth_templates(templates)
    set_web_templates(templates)
    set_onboarding_templates(templates)
    
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