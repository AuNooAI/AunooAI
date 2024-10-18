from openai import OpenAI
import os
from dotenv import load_dotenv
import anthropic
import json

load_dotenv()

class AIModel:
    def __init__(self, model_name):
        self.model_name = model_name

    def generate_response(self, messages):
        raise NotImplementedError("This method should be implemented by subclasses")

class OpenAIModel(AIModel):
    def __init__(self, model_name):
        super().__init__(model_name)
        self.client = OpenAI(api_key=os.getenv(f"OPENAI_API_KEY_{model_name.replace('-', '_').upper()}"))

    def generate_response(self, messages):
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=messages
        )
        return response.choices[0].message.content

class AnthropicModel(AIModel):
    def __init__(self, model_name):
        super().__init__(model_name)
        self.client = anthropic.Anthropic(api_key=os.getenv(f"ANTHROPIC_API_KEY_{model_name.replace('-', '_').upper()}"))

    def generate_response(self, messages):
        prompt = "\n\n".join([f"{m['role']}: {m['content']}" for m in messages])
        response = self.client.completions.create(
            model=self.model_name,
            prompt=prompt,
            max_tokens_to_sample=4000
        )
        return response.completion

def get_ai_model(model_name):
    if model_name.startswith("gpt-"):
        return OpenAIModel(model_name)
    elif model_name.startswith("claude-"):
        return AnthropicModel(model_name)
    else:
        raise ValueError(f"Unsupported model: {model_name}")

def get_available_models():
    models = []
    for key in os.environ:
        if key.startswith("OPENAI_API_KEY_") or key.startswith("ANTHROPIC_API_KEY_"):
            model_name = key.split("_", 3)[-1].lower().replace("_", "-")
            provider = "openai" if key.startswith("OPENAI") else "anthropic"
            models.append({"name": model_name, "provider": provider})
    return models

def ai_get_available_models():
    config_path = os.path.join(os.path.dirname(__file__), 'config', 'ai_config.json')
    print(f"Looking for config file at: {config_path}")
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        models = config.get('ai_models', [])
        
        # Remove duplicates while preserving order
        unique_models = []
        seen = set()
        for model in models:
            model_key = (model['name'], model['provider'])
            if model_key not in seen:
                seen.add(model_key)
                unique_models.append(model)
        
        print(f"Available unique models from config: {unique_models}")
        return unique_models
    except Exception as e:
        print(f"Error reading config file: {str(e)}")
        return []
