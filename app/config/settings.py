import json
import os
from dotenv import load_dotenv
from typing import Dict

load_dotenv()

# Change this line to read from environment with new prefix
NEWSAPI_KEY = os.getenv('PROVIDER_NEWSAPI_KEY')  # Changed to use PROVIDER_ prefix

def load_config() -> Dict:
    """Load configuration with support for topics."""
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
    with open(config_path, 'r') as config_file:
        config = json.load(config_file)
    return config

config = load_config()

# Add this line to define DATABASE_DIR
DATABASE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')

# Firecrawl API key with default value
FIRECRAWL_API_KEY = os.getenv('PROVIDER_FIRECRAWL_KEY', '')

# Ensure the directory exists
os.makedirs(DATABASE_DIR, exist_ok=True)

# Get list of available topics
AVAILABLE_TOPICS = [topic['name'] for topic in config.get('topics', [])]
