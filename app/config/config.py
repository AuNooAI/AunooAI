import json
import os
from typing import Dict, List

def load_config() -> Dict:
    """Load configuration with support for topics."""
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
    with open(config_path, 'r') as config_file:
        config = json.load(config_file)

    # Load AI models config
    ai_config_path = os.path.join(os.path.dirname(__file__), 'ai_config.json')
    try:
        with open(ai_config_path, 'r') as f:
            ai_config = json.load(f)
            config['ai_models'] = ai_config.get('ai_models', [])
    except FileNotFoundError:
        config['ai_models'] = []

    # Load provider config
    provider_config_path = os.path.join(os.path.dirname(__file__), 'provider_config.json')
    try:
        with open(provider_config_path, 'r') as f:
            provider_config = json.load(f)
            config['providers'] = provider_config.get('providers', [])
    except FileNotFoundError:
        config['providers'] = []

    return config

def get_topic_config(config: Dict, topic_name: str) -> Dict:
    """Get configuration for a specific topic."""
    # Always load fresh config
    config = load_config()
    for topic in config.get('topics', []):
        if topic['name'] == topic_name:
            return topic
    raise ValueError(f"Topic '{topic_name}' not found in configuration")

def get_all_topics(config: Dict) -> List[str]:
    """Get list of all topic names."""
    # Always load fresh config
    config = load_config()
    return [topic['name'] for topic in config.get('topics', [])]

def load_news_monitoring() -> Dict:
    news_config_path = os.path.join(os.path.dirname(__file__), 'news_monitoring.json')
    try:
        with open(news_config_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {"news_filters": [], "paper_filters": []}

def save_news_monitoring(filters: Dict) -> None:
    news_config_path = os.path.join(os.path.dirname(__file__), 'news_monitoring.json')
    with open(news_config_path, 'w') as f:
        json.dump(filters, f, indent=2)

def get_news_filters() -> List[str]:
    config = load_news_monitoring()
    return config.get("news_filters", [])

def get_paper_filters() -> List[str]:
    config = load_news_monitoring()
    return config.get("paper_filters", [])
