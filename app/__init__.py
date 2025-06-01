# Configure logging as early as possible before any other imports
try:
    from app.core.logging_config import configure_logging
    configure_logging()
except ImportError:
    # If logging config is not available yet, that's okay
    pass 