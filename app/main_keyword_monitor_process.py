# TODO: RENAME AND GET RID OF FASTAPI!!!!
# TODO: THIS LOGIC NEEDS TO BE SPLIT INTO GRANULAR QUEUE DRIVEN TASKS!!!!
# TODO: DO NOT USE IN PRODUCTION AS IS!!!
import sys
import os
import logging

# Add the parent directory to the Python path FIRST
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.tasks.keyword_monitor import run_keyword_monitor

# Configure logging BEFORE any other imports
from app.core.logging_config import configure_logging

configure_logging()

# Now import everything else
import uvicorn
from dotenv import load_dotenv
import ssl
from fastapi.middleware.cors import CORSMiddleware
import asyncio

# Load environment variables
load_dotenv()

# Get port from environment variable, default to 8000 if not set
PORT = int(os.getenv('PORT', 10000))
CERT_PATH = os.getenv('CERT_PATH', 'cert.pem')
KEY_PATH = os.getenv('KEY_PATH', 'key.pem')
ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')
DISABLE_SSL = os.getenv('DISABLE_SSL', 'false').lower() == 'true'


def configure_app():
    from main import app

    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:8010",
            "https://localhost:8010",
            "https://localhost:10000",
            "http://localhost:10000"
        ] if ENVIRONMENT == 'production' else ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    return app


logging.getLogger().handlers.clear()

# Set up logging
logger = logging.getLogger(__name__)

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)

# Set specific log levels for different modules
logger = logging.getLogger('main')
logger.setLevel(logging.DEBUG)

# EXPLICITLY ENABLE vector routes logging
logging.getLogger('app.routes.vector_routes').setLevel(logging.DEBUG)

# Set higher log levels for noisy modules
logging.getLogger('numba').setLevel(logging.ERROR)  # Changed from WARNING to ERROR
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)
logging.getLogger('litellm').setLevel(logging.WARNING)
logging.getLogger('app.analyzers.prompt_manager').setLevel(logging.DEBUG)
logging.getLogger('app.routes.prompt_routes').setLevel(logging.DEBUG)
logging.getLogger('app.env_loader').setLevel(logging.DEBUG)
logging.getLogger('app.relevance').setLevel(logging.DEBUG)
logging.getLogger('app.collectors.newsapi_collector').setLevel(logging.DEBUG)
logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)

# Start the keyword monitor background task with a delay to prevent blocking startup
async def delayed_keyword_monitor_start():
    """Start keyword monitor after a short delay to prevent blocking startup"""
    try:
        logger.info("Starting keyword monitor background task...")
        await run_keyword_monitor()
        logger.info("Keyword monitor background task started successfully")
    except Exception as e:
        logger.error(f"Failed to start keyword monitor background task: {str(e)}")


# Start the delayed task
if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(delayed_keyword_monitor_start())
