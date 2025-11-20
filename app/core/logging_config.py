"""Centralized logging configuration for the application."""

import logging
import sys
import os

# Enable numba JIT compilation for UMAP performance
# Comment out the JIT disable to allow numba compilation like working version
# os.environ['NUMBA_DISABLE_JIT'] = '1'  # ← This was causing UMAP to hang!
# Enable numba debug logging to match working version behavior
os.environ['NUMBA_LOG_LEVEL'] = 'DEBUG'

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
    
    # Suppress verbose loggers (but allow numba to work for UMAP)
    # IMPORTANT: For Docker debugging, we need to see automated_ingest_service, env_loader, and relevance logs
    suppress_loggers = [
        # 'numba',  # ← Allow numba logging for UMAP debugging
        # 'numba.core',  # ← Allow numba.core logging
        # 'numba.core.ssa',  # ← Allow SSA logging like working version
        'numba.core.byteflow',  # Still suppress some verbose ones
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
        # 'app.env_loader',  # ← DO NOT SUPPRESS - needed for Docker debugging
        # 'app.relevance',  # ← DO NOT SUPPRESS - needed for Docker debugging
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
        
        # Only suppress non-essential numba loggers (not core/ssa)
        if logger_name.startswith('numba') and logger_name not in ['numba', 'numba.core', 'numba.core.ssa']:
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
        'app.startup': logging.INFO,
        'app.services.automated_ingest_service': logging.INFO,  # Enable automated ingest logging for Docker debugging
        'app.env_loader': logging.INFO,  # Enable environment loading logs for Docker debugging
        'app.relevance': logging.INFO,  # Enable relevance calculator logs for Docker debugging
        'numba': logging.DEBUG,  # Enable numba debug logging like working version
        'numba.core': logging.DEBUG,  # Enable numba.core debug logging
        'numba.core.ssa': logging.DEBUG,  # Enable SSA debug logging like working version
    }
    
    for logger_name, level in app_loggers.items():
        logger = logging.getLogger(logger_name)
        logger.setLevel(level)
    
    # Disable propagation for all loggers to prevent duplicates
    for name in logging.root.manager.loggerDict:
        if name.startswith('numba') or name in suppress_loggers:
            logging.getLogger(name).propagate = False
            logging.getLogger(name).setLevel(logging.ERROR) 