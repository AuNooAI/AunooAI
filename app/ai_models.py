from dotenv import load_dotenv
import os
import yaml
from litellm import Router
import logging

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)  # Set the default logging level

# Suppress LiteLLM logs
litellm_logger = logging.getLogger('litellm')
litellm_logger.setLevel(logging.CRITICAL)  # Only show CRITICAL messages

# Remove all handlers from the LiteLLM logger
for handler in litellm_logger.handlers[:]:
    litellm_logger.removeHandler(handler)

class AIModel:
    def __init__(self, model_name):
        self.model_name = model_name

    def generate_response(self, messages):
        raise NotImplementedError("This method should be implemented by subclasses")

class LiteLLMModel(AIModel):
    """Handler for models using LiteLLM."""
    
    _instances = {}  # Class-level dictionary to track instances
    _current_model = None  # Track the currently active model

    def __init__(self, model_name):
        super().__init__(model_name)
        print(f"\n[DEBUG] Entering class LiteLLMModel with model: {model_name}")
        self.router = None
        self.init_router()
        
        # Store this instance and set as current
        LiteLLMModel._instances[model_name] = self
        LiteLLMModel._current_model = model_name

    @classmethod
    def get_instance(cls, model_name):
        """Get or create an instance for the given model name"""
        if model_name not in cls._instances:
            instance = cls(model_name)
        else:
            instance = cls._instances[model_name]
            # Update current model
            cls._current_model = model_name
        return instance

    def init_router(self):
        print(f"\n[DEBUG] Starting init_router with model: {self.model_name}")  # Debug line
        
        # Ensure router is cleared before reinitializing
        self.router = None
        
        config_path = os.path.join(os.path.dirname(__file__), 'config', 'litellm_config.yaml')
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        # Get currently configured models with their API keys
        configured_models = get_available_models()
        
        # Verify the model is configured
        if not any(cm['name'] == self.model_name for cm in configured_models):
            raise ValueError(f"Model {self.model_name} is not in configured models: {[cm['name'] for cm in configured_models]}")
        
        # Filter model list to only include the selected model
        filtered_model_list = []
        for model in config["model_list"]:
            if model['model_name'] == self.model_name:  # Strict equality check
                # Check if model requires an API key
                if 'api_key' in model['litellm_params']:
                    env_key = model['litellm_params']['api_key'].split('/')[-1]
                    if env_key not in os.environ:
                        continue
                    model_copy = model.copy()
                    model_copy['litellm_params']['api_key'] = os.environ[env_key]
                else:
                    # For models without API key (like Ollama)
                    model_copy = model.copy()
                
                filtered_model_list.append(model_copy)
                print(f"[DEBUG] Added model to router: {self.model_name}")
                break
        
        if not filtered_model_list:
            raise ValueError(f"Model {self.model_name} not found in config or not properly configured")
        
        print(f"[DEBUG] Creating router with models: {[m['model_name'] for m in filtered_model_list]}")
        
        # Create new router instance with minimal configuration
        self.router = Router(
            model_list=filtered_model_list,
            cache_responses=False,
            routing_strategy="simple-shuffle",
            set_verbose=False,
            num_retries=0,
            default_litellm_params={"timeout": 120}
        )

    def generate_response(self, messages):
        try:
            # Always use the current model instance
            if LiteLLMModel._current_model != self.model_name:
                print(f"[DEBUG] Model mismatch - Instance: {self.model_name}, Current: {LiteLLMModel._current_model}")
                return LiteLLMModel._instances[LiteLLMModel._current_model].generate_response(messages)

            print(f"\n[DEBUG] Using current model: {self.model_name}")
            print(f"[DEBUG] Router config: {self.router.model_list}\n")
            
            response = self.router.completion(
                model=self.model_name,
                messages=messages,
                metadata={"model_name": self.model_name},
                caching=False
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"Error generating response with LiteLLM: {str(e)}")
            raise

def get_ai_model(model_name):
    """Get an AI model instance."""
    print(f"[DEBUG] get_ai_model called with: {model_name}")
    return LiteLLMModel.get_instance(model_name)

def get_available_models():
    """Get models that have API keys configured in the environment."""
    models = []
    seen = set()  # Track unique model names
    
    # Expanded provider prefixes based on LiteLLM supported providers
    provider_prefixes = {
        'OPENAI_API_KEY_': 'openai',
        'ANTHROPIC_API_KEY_': 'anthropic',
        'AZURE_API_KEY_': 'azure',
        'HUGGINGFACE_API_KEY_': 'huggingface',
        'COHERE_API_KEY_': 'cohere',
        'REPLICATE_API_KEY_': 'replicate',
        'TOGETHER_API_KEY_': 'together',
        'MISTRAL_API_KEY_': 'mistral',
        'GEMINI_API_KEY_': 'google',
        'VERTEX_AI_KEY_': 'vertex_ai',
        'OLLAMA_API_KEY_': 'ollama',
        'BEDROCK_API_KEY_': 'bedrock',
        'AI21_API_KEY_': 'ai21',
        'CLOUDFLARE_API_KEY_': 'cloudflare',
        'PALM_API_KEY_': 'palm',
        'PERPLEXITY_API_KEY_': 'perplexity',
        'GROQ_API_KEY_': 'groq',
        'XAI_API_KEY_': 'xai'
    }
    
    print("\nChecking environment variables for API keys:")
    for key in os.environ:
        for prefix, provider in provider_prefixes.items():
            if key.startswith(prefix):
                value = os.environ[key]
                if value and not value.startswith("os.environ/"):
                    # Extract model name from environment variable
                    model_name = key.split("_", 3)[-1].lower()
                    # Convert underscores to dashes but preserve dots
                    if "_" in model_name:
                        model_name = model_name.replace("_", "-")
                    
                    # Only add if we haven't seen this model/provider combination
                    model_key = (model_name, provider)
                    if model_key not in seen:
                        seen.add(model_key)
                        models.append({
                            "name": model_name,
                            "provider": provider
                        })
                        print(f"Added model: {model_name} ({provider}, {key})")
    
    if not models:
        print("No configured models found. Please check your environment variables.")
    else:
        print(f"\nFinal configured models: {models}")
    
    return models

def ai_get_available_models():
    """Get all supported models from litellm configuration.
    This returns all models that the system supports, regardless of whether 
    they have API keys configured. Used for displaying available options
    that could be configured in the system.
    
    Returns:
        list: List of dicts with supported models, each containing:
            - name: The model name (e.g., 'gpt-4o')
            - provider: The provider name (e.g., 'openai', 'anthropic')
    """
    config_path = os.path.join(os.path.dirname(__file__), 'config', 'litellm_config.yaml')
    print(f"Looking for config file at: {config_path}")
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        # Convert litellm format to existing format
        models = []
        for model in config.get('model_list', []):
            provider = model['litellm_params']['model'].split('/')[0]
            models.append({
                "name": model['model_name'],
                "provider": provider
            })
        
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
