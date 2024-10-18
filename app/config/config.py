import json
import os

def load_config():
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    ai_config_path = os.path.join(os.path.dirname(__file__), 'ai_config.json')
    with open(ai_config_path, 'r') as f:
        ai_config = json.load(f)
    
    # Merge the configurations
    config.update(ai_config)
    
    return config
