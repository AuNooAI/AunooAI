import json
import os
from dotenv import load_dotenv
from typing import Dict
import shutil
import logging

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
