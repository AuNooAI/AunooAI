import json
import os
from typing import Dict

# Add this near the top with other settings
NEWSAPI_KEY = '2681933b8eef47749950d0f1d159d8b7'

def load_config() -> Dict:
    """Load configuration with support for topics."""
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
    with open(config_path, 'r') as config_file:
        config = json.load(config_file)
    print("Loaded config with topics:", config)  # Debug print
    return config

config = load_config()

# Add this line to define DATABASE_DIR
DATABASE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')

# Firecrawl API key
FIRECRAWL_API_KEY = 'fc-bdb70992b4f14ff3bbcc9f54342323fe'

# Ensure the directory exists
os.makedirs(DATABASE_DIR, exist_ok=True)

# Get list of available topics
AVAILABLE_TOPICS = [topic['name'] for topic in config.get('topics', [])]

print("Available topics:", AVAILABLE_TOPICS)  # Debug print
print("DATABASE_DIR:", DATABASE_DIR)  # Debug print
