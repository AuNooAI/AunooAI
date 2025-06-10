"""Centralized logging configuration for the application."""

import logging
import sys
import os

# Disable numba JIT compilation to prevent verbose bytecode dumps
os.environ['NUMBA_DISABLE_JIT'] = '1'
# Set numba log level via environment variable
os.environ['NUMBA_LOG_LEVEL'] = 'ERROR'

def configure_logging():
    """Configure logging for the entire application."""
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)  # Changed from WARNING to INFO
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create console handler with custom format
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)  # Changed from WARNING to INFO
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # Suppress verbose loggers
    suppress_loggers = [
        'numba',
        'numba.core',
        'numba.core.byteflow',
        'numba.core.ssa',
        'numba.core.interpreter',
        'numba.core.types',
        'numba.core.typing',
        'numba.core.compiler',
        'numba.cuda',
        'httpx',
        'httpcore',
        'httpcore.connection',
        'httpcore.http11',
        'litellm',
        'LiteLLM',
        'app.analyzers.prompt_manager',
        'app.routes.prompt_routes',
        'app.env_loader',
        'app.relevance',
        'app.utils.audio',
        'uvicorn.access',
        'uvicorn.error',
        'watchfiles.main',
        'tensorflow',
        'h5py',
        'matplotlib',
        'PIL'
    ]
    
    for logger_name in suppress_loggers:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.ERROR)
        logger.propagate = False
        
        # Also add a null handler to completely suppress output
        if logger_name.startswith('numba'):
            null_handler = logging.NullHandler()
            logger.addHandler(null_handler)
            logger.handlers = [null_handler]  # Remove all other handlers
    
    # Set specific levels for app loggers
    app_loggers = {
        'app': logging.INFO,
        'app.main': logging.INFO,
        'app.core': logging.INFO,
        'app.routes': logging.INFO,
        'app.routes.vector_routes': logging.INFO,  # Explicitly enable vector routes logging
        'app.database': logging.INFO,
        'app.startup': logging.INFO
    }
    
    for logger_name, level in app_loggers.items():
        logger = logging.getLogger(logger_name)
        logger.setLevel(level)
    
    # Disable propagation for all loggers to prevent duplicates
    for name in logging.root.manager.loggerDict:
        if name.startswith('numba') or name in suppress_loggers:
            logging.getLogger(name).propagate = False
            logging.getLogger(name).setLevel(logging.ERROR) 