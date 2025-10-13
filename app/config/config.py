import json
import os
import yaml
from typing import Dict, List

def load_config() -> Dict:
    """Load configuration with support for topics."""
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
    with open(config_path, 'r') as config_file:
        config = json.load(config_file)

    # Load AI models from both litellm config files
    litellm_config_path = os.path.join(os.path.dirname(__file__), 'litellm_config.yaml')
    litellm_local_config_path = os.path.join(os.path.dirname(__file__), 'litellm_config.yaml.local')
    
    try:
        # Load default config first
        merged_config = {"model_list": []}
        
        if os.path.exists(litellm_config_path):
            with open(litellm_config_path, 'r') as f:
                default_config = yaml.safe_load(f) or {}
                merged_config["model_list"].extend(default_config.get("model_list", []))
        
        # Load and merge local config
        if os.path.exists(litellm_local_config_path):
            with open(litellm_local_config_path, 'r') as f:
                local_config = yaml.safe_load(f) or {}
                merged_config["model_list"].extend(local_config.get("model_list", []))
        
        # Convert litellm config format to existing ai_models format
        ai_models = []
        for model in merged_config.get('model_list', []):
            provider = model['litellm_params']['model'].split('/')[0]
            ai_models.append({
                "name": model['model_name'],
                "provider": provider
            })
        config['ai_models'] = ai_models
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

def validate_topic_exists(topic_name: str) -> bool:
    """Validate that a topic exists in config.json.

    Args:
        topic_name: Name of the topic to validate

    Returns:
        True if topic exists in config.json, False otherwise
    """
    if not topic_name:
        return False
    config = load_config()
    topic_names = {topic['name'] for topic in config.get('topics', [])}
    return topic_name in topic_names

def get_topic_description(topic_name: str) -> str:
    """Get description for a specific topic from config.json.

    Args:
        topic_name: Name of the topic

    Returns:
        Topic description string, or empty string if not found
    """
    config = load_config()
    for topic in config.get('topics', []):
        if topic.get('name') == topic_name:
            return topic.get('description', '')
    return ''

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

def get_news_query(topic_id: str) -> str:
    config = load_news_monitoring()
    news_filters = config.get("news_filters", {})
    return news_filters.get(topic_id, "")

def set_news_query(topic_id: str, query: str) -> None:
    config = load_news_monitoring()
    if "news_filters" not in config:
        config["news_filters"] = {}
    config["news_filters"][topic_id] = query
    save_news_monitoring(config)

def get_paper_query(topic_id: str) -> str:
    config = load_news_monitoring()
    paper_filters = config.get("paper_filters", {})
    return paper_filters.get(topic_id, "")

def set_paper_query(topic_id: str, query: str) -> None:
    config = load_news_monitoring()
    if "paper_filters" not in config:
        config["paper_filters"] = {}
    config["paper_filters"][topic_id] = query
    save_news_monitoring(config)
