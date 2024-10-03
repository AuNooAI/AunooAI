import json
import os

def load_config():
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
    with open(config_path, 'r') as config_file:
        config = json.load(config_file)
    print("Loaded config:", config)  # Debug print
    return config

config = load_config()

print("Config initialized:", config)  # Debug print

# If you're using a single instance instead of a class
# AppConfig = {
#     # Your configuration key-value pairs here
# }
