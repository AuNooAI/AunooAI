import json
import os
import yaml
from typing import Dict, List

def load_config() -> Dict:
    """Load configuration with support for topics."""
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
    with open(config_path, 'r') as config_file:
        config = json.load(config_file)

    # Load AI models from litellm config instead of ai_config.json
    litellm_config_path = os.path.join(os.path.dirname(__file__), 'litellm_config.yaml')
    try:
        with open(litellm_config_path, 'r') as f:
            litellm_config = yaml.safe_load(f)
            # Convert litellm config format to existing ai_models format
            ai_models = []
            for model_entry in litellm_config.get('model_list', []):
                litellm_params = model_entry.get('litellm_params', {})
                # Corrected provider logic: Prioritize model string prefix
                model_str_from_params = litellm_params.get('model', '')
                if '/' in model_str_from_params:
                    provider = model_str_from_params.split('/', 1)[0]
                else:
                    provider = litellm_params.get('custom_llm_provider', '')
                # Ensure provider is not empty if no prefix and no custom_llm_provider, could default or log warning
                if not provider:
                    print(f"Warning: Model '{model_entry['model_name']}' has no determinable provider. Check 'model' prefix and 'custom_llm_provider'.")
                    # provider = "unknown" # Or some default
                
                ai_models.append({
                    "name": model_entry['model_name'],
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
