import json
import os
from dotenv import load_dotenv
from typing import Dict
import shutil
import logging
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)

load_dotenv()

# Use standardized naming with backward compatibility
NEWSAPI_KEY = os.getenv('PROVIDER_NEWSAPI_API_KEY') or os.getenv('PROVIDER_NEWSAPI_KEY')

def init_config():
    """Initialize config.json from sample if it doesn't exist."""
    try:
        # Get absolute paths
        config_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(config_dir, 'config.json')
        config_sample_path = os.path.join(config_dir, 'config.json.sample')
        
        logger.info(f"Checking config files:")
        logger.info(f"Config path: {config_path}")
        logger.info(f"Config sample path: {config_sample_path}")
        
        # Create config directory if it doesn't exist
        os.makedirs(config_dir, exist_ok=True)
        
        if not os.path.exists(config_path):
            if os.path.exists(config_sample_path):
                logger.info("config.json not found, copying from config.json.sample")
                shutil.copy2(config_sample_path, config_path)
                logger.info("Successfully created config.json from sample")
            else:
                logger.error(f"Neither config.json nor config.json.sample found in {config_dir}")
                raise FileNotFoundError(f"No configuration file found in {config_dir}")
        
        return config_path
    except Exception as e:
        logger.error(f"Error initializing config: {str(e)}")
        raise

def load_config():
    """Load configuration from config.json."""
    config_path = init_config()  # Initialize config file if needed
    with open(config_path, 'r') as config_file:
        return json.load(config_file)

config = load_config()

# Add this line to define DATABASE_DIR
DATABASE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')

# Firecrawl API key with standardized naming and backward compatibility
FIRECRAWL_API_KEY = os.getenv('PROVIDER_FIRECRAWL_API_KEY') or os.getenv('PROVIDER_FIRECRAWL_KEY', '')

# Ensure the directory exists
os.makedirs(DATABASE_DIR, exist_ok=True)

# Get list of available topics
AVAILABLE_TOPICS = [topic['name'] for topic in config.get('topics', [])]

# Database settings for PostgreSQL migration
class DatabaseSettings:
    """Database configuration settings"""

    def __init__(self):
        """Initialize database settings from environment"""
        self.DB_TYPE = os.getenv('DB_TYPE', 'sqlite')
        self.DB_HOST = os.getenv('DB_HOST', 'localhost')
        self.DB_PORT = os.getenv('DB_PORT', '5432')
        self.DB_USER = os.getenv('DB_USER', 'aunoo_user')
        self.DB_PASSWORD = os.getenv('DB_PASSWORD', '')
        self.DB_NAME = os.getenv('DB_NAME', 'aunoo_db')

        # Connection pool settings
        self.DB_POOL_SIZE = int(os.getenv('DB_POOL_SIZE', '15'))
        self.DB_MAX_OVERFLOW = int(os.getenv('DB_MAX_OVERFLOW', '10'))
        self.DB_POOL_TIMEOUT = int(os.getenv('DB_POOL_TIMEOUT', '30'))
        self.DB_POOL_RECYCLE = int(os.getenv('DB_POOL_RECYCLE', '3600'))

    @property
    def database_url(self):
        """Get async database URL"""
        return self.get_database_url()

    def get_database_url(self):
        """Get database URL from environment"""
        if self.DB_TYPE == 'postgresql':
            # PostgreSQL connection with URL-encoded credentials
            user = quote_plus(self.DB_USER)
            password = quote_plus(self.DB_PASSWORD)
            return f"postgresql+asyncpg://{user}:{password}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        else:
            # SQLite connection (default)
            db_path = os.path.join(DATABASE_DIR, 'fnaapp.db')
            return f"sqlite+aiosqlite:///{db_path}"

    def get_sync_database_url(self):
        """Get synchronous database URL for Alembic migrations"""
        if self.DB_TYPE == 'postgresql':
            # PostgreSQL connection (sync) with URL-encoded credentials
            user = quote_plus(self.DB_USER)
            password = quote_plus(self.DB_PASSWORD)
            return f"postgresql+psycopg2://{user}:{password}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        else:
            # SQLite connection (default)
            db_path = os.path.join(DATABASE_DIR, 'fnaapp.db')
            return f"sqlite:///{db_path}"

# Create instance for easy access
db_settings = DatabaseSettings()
