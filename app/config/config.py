import json
import os
from typing import Dict, List

def load_config() -> Dict:
    """Load and merge configuration files."""
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    ai_config_path = os.path.join(os.path.dirname(__file__), 'ai_config.json')
    with open(ai_config_path, 'r') as f:
        ai_config = json.load(f)
    
    # Add AI models to the config without overwriting topics
    config['ai_models'] = ai_config.get('ai_models', [])
    
    return config

def get_topic_config(config: Dict, topic_name: str) -> Dict:
    """Get configuration for a specific topic."""
    for topic in config.get('topics', []):
        if topic['name'] == topic_name:
            return topic
    raise ValueError(f"Topic '{topic_name}' not found in configuration")

def get_all_topics(config: Dict) -> List[str]:
    """Get list of all topic names."""
    return [topic['name'] for topic in config.get('topics', [])]
