import json
import os

def load_config():
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config.json')
    with open(config_path, 'r') as config_file:
        config = json.load(config_file)
    print("Loaded config:", config)  # Debug print
    return config

config = load_config()

# Add this line to define DATABASE_DIR
DATABASE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')

# Firecrawl API key
FIRECRAWL_API_KEY = 'fc-bdb70992b4f14ff3bbcc9f54342323fe'

# Ensure the directory exists
os.makedirs(DATABASE_DIR, exist_ok=True)

print("Config initialized:", config)  # Debug print
print("DATABASE_DIR:", DATABASE_DIR)  # Debug print
