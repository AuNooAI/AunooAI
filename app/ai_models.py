import os
import yaml
from litellm import Router
import logging
from app.env_loader import load_environment, ensure_model_env_vars

# Configure logging
logging.basicConfig(level=logging.INFO)  # Set the default logging level

# Suppress LiteLLM logs
litellm_logger = logging.getLogger('litellm')
litellm_logger.setLevel(logging.CRITICAL)  # Only show CRITICAL messages

# Remove all handlers from the LiteLLM logger
for handler in litellm_logger.handlers[:]:
    litellm_logger.removeHandler(handler)

# Load environment variables and ensure they're properly set for models
ensure_model_env_vars()

def clean_outdated_model_env_vars():
    """
    Remove environment variables for models that are no longer in the config file.
    This ensures that deleted models don't linger in the environment.
    """
    # Load the config file to get the current models
    config_path = os.path.join(os.path.dirname(__file__), 'config', 'litellm_config.yaml')
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    # Extract model names from config
    configured_models = set()
    for model in config.get("model_list", []):
        if "model_name" in model:
            configured_models.add(model["model_name"])
    
    print(f"\n[DEBUG] Models in config: {configured_models}")
    
    # Define provider prefixes for environment variables
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
    
    removed_vars = []
    
    # Check each environment variable
    for env_var in list(os.environ.keys()):
        for prefix, provider in provider_prefixes.items():
            if env_var.startswith(prefix):
                # Extract model name from environment variable
                model_name = env_var.split("_", 3)[-1].lower()
                # Convert underscores to dashes but preserve dots
                if "_" in model_name:
                    model_name = model_name.replace("_", "-")
                
                # If the model is not in the config, remove its environment variable
                if model_name not in configured_models:
                    removed_vars.append((env_var, model_name, provider))
                    del os.environ[env_var]
    
    if removed_vars:
        print("\n[INFO] Removed environment variables for models not in config:")
        for var, model, provider in removed_vars:
            print(f"  - {var} ({model}, {provider})")

# Clean up outdated model environment variables at startup
clean_outdated_model_env_vars()

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
        
        # Include all models in the router to support fallbacks
        filtered_model_list = []
        for model in config["model_list"]:
            # Check if model requires an API key
            if 'api_key' in model['litellm_params']:
                env_key = model['litellm_params']['api_key'].split('/')[-1]
                if env_key not in os.environ:
                    continue
                model_copy = model.copy()
                model_copy['litellm_params']['api_key'] = os.environ[env_key]
            else:
                # For models without API key (like local Ollama - testing)
                model_copy = model.copy()
            
            filtered_model_list.append(model_copy)
            print(f"[DEBUG] Added model to router: {model['model_name']}")
        
        if not filtered_model_list:
            raise ValueError(f"No properly configured models found in config")
        
        print(f"[DEBUG] Creating router with models: {[m['model_name'] for m in filtered_model_list]}")
        
        # Create new router instance with all available models
        self.router = Router(
            model_list=filtered_model_list,
            cache_responses=False,
            routing_strategy=config.get("routing_strategy", "simple-shuffle"),
            set_verbose=False,
            num_retries=config.get("max_retries", 0),
            default_litellm_params={"timeout": config.get("timeout", 30)},
            fallbacks=config.get("fallbacks", [])
        )

    def generate_response(self, messages, _is_fallback=False, _attempted_models=None):
        """
        Generate a response using the LLM.
        
        Args:
            messages: The messages to send to the LLM
            _is_fallback: Internal parameter to track if this is a fallback call
            _attempted_models: Internal parameter to track which models have been attempted
            
        Returns:
            The generated response text or error message
        """
        # Initialize tracking of attempted models if this is the first call
        if _attempted_models is None:
            _attempted_models = set()
        
        # Add current model to attempted models
        _attempted_models.add(self.model_name)
        
        try:
            # Always use the current model instance
            if LiteLLMModel._current_model != self.model_name and not _is_fallback:
                print(f"[DEBUG] Model mismatch - Instance: {self.model_name}, Current: {LiteLLMModel._current_model}")
                return LiteLLMModel._instances[LiteLLMModel._current_model].generate_response(messages)

            print(f"\n[DEBUG] Using model: {self.model_name} (fallback: {_is_fallback})")
            print(f"[DEBUG] Router config: {self.router.model_list}\n")
            
            # Let LiteLLM handle fallbacks automatically
            response = self.router.completion(
                model=self.model_name,
                messages=messages,
                metadata={"model_name": self.model_name},
                caching=False
            )
            
            # Extract content from response - handle different model formats
            try:
                # Standard format
                if hasattr(response, 'choices') and len(response.choices) > 0:
                    if hasattr(response.choices[0], 'message') and hasattr(response.choices[0].message, 'content'):
                        return response.choices[0].message.content
                
                # If we couldn't extract content using the expected structure, try to get the raw response
                # This is needed because different models might return different response structures
                print(f"[DEBUG] Using alternative content extraction for {self.model_name}")
                
                # Try to access the raw response content
                if hasattr(response, 'model_dump'):
                    # For Pydantic models
                    dump = response.model_dump()
                    if 'choices' in dump and dump['choices'] and 'message' in dump['choices'][0]:
                        if 'content' in dump['choices'][0]['message']:
                            return dump['choices'][0]['message']['content']
                
                # Last resort: convert to string and extract the content
                response_str = str(response)
                if "content='" in response_str:
                    # Extract content from the string representation
                    content_start = response_str.find("content='") + 9
                    content_end = response_str.find("'", content_start)
                    if content_start > 9 and content_end > content_start:
                        return response_str[content_start:content_end]
                
                # If all else fails, return the string representation
                return str(response)
                
            except Exception as extract_error:
                print(f"[WARNING] Error extracting content from response: {str(extract_error)}")
                # Return the string representation as a last resort
                return str(response)
            
        except Exception as e:
            error_message = str(e)
            print(f"Error generating response with {self.model_name}: {error_message}")
            
            # Check if this is a context window error
            is_context_window_error = "context length" in error_message.lower() and "tokens" in error_message.lower()
            
            # Try to find a fallback model if this isn't already a fallback call
            if not _is_fallback:
                # Get fallbacks configuration
                config_path = os.path.join(os.path.dirname(__file__), 'config', 'litellm_config.yaml')
                with open(config_path, 'r') as f:
                    config = yaml.safe_load(f)
                
                fallbacks_config = config.get("fallbacks", [])
                
                # Find fallbacks for the current model
                for fallback_dict in fallbacks_config:
                    if self.model_name in fallback_dict:
                        fallback_models = fallback_dict[self.model_name]
                        print(f"[DEBUG] Found fallbacks for {self.model_name}: {fallback_models}")
                        
                        # Try each fallback model that hasn't been attempted yet
                        for fallback_model_name in fallback_models:
                            if fallback_model_name in _attempted_models:
                                print(f"[DEBUG] Skipping already attempted fallback model: {fallback_model_name}")
                                continue
                                
                            print(f"[DEBUG] Attempting fallback to {fallback_model_name}")
                            try:
                                # Get or create the fallback model instance
                                fallback_model = LiteLLMModel.get_instance(fallback_model_name)
                                # Call generate_response on the fallback model with fallback flag
                                return fallback_model.generate_response(
                                    messages, 
                                    _is_fallback=True,
                                    _attempted_models=_attempted_models
                                )
                            except Exception as fallback_error:
                                print(f"[DEBUG] Fallback to {fallback_model_name} failed: {str(fallback_error)}")
                                continue
            
            # If we've reached here, either there are no fallbacks or all fallbacks failed
            # Extract useful information from the error
            user_message = self._extract_user_friendly_error(error_message, self.model_name)
            return user_message

    def _extract_user_friendly_error(self, error_message, model_name):
        """Extract user-friendly error messages from common errors."""
        # Context length exceeded error
        if "context length" in error_message and "tokens" in error_message:
            import re
            # Try to extract the max tokens and actual tokens
            max_tokens_match = re.search(r"maximum context length is (\d+)", error_message)
            actual_tokens_match = re.search(r"resulted in (\d+) tokens", error_message)
            
            if max_tokens_match and actual_tokens_match:
                max_tokens = max_tokens_match.group(1)
                actual_tokens = actual_tokens_match.group(1)
                return f"⚠️ Your request exceeds the maximum context length for {model_name}. " \
                       f"The model can handle {max_tokens} tokens, but your input has {actual_tokens} tokens. " \
                       f"Please reduce the length of your input or try a model with a larger context window."
            else:
                return f"⚠️ Your request exceeds the maximum context length for {model_name}. " \
                       f"Please reduce the length of your input or try a model with a larger context window."
        
        # API key errors
        elif "api key" in error_message.lower() or "apikey" in error_message.lower():
            return f"⚠️ There was an issue with the API key for {model_name}. " \
                   f"Please check your API key configuration."
        
        # Rate limit errors
        elif "rate limit" in error_message.lower() or "ratelimit" in error_message.lower():
            return f"⚠️ Rate limit exceeded for {model_name}. " \
                   f"Please try again later or use a different model."
        
        # Model not available
        elif "model" in error_message.lower() and ("not found" in error_message.lower() or 
                                                 "unavailable" in error_message.lower() or
                                                 "not available" in error_message.lower()):
            return f"⚠️ The model {model_name} is currently unavailable. " \
                   f"Please try a different model."
        
        # Connection errors
        elif "connection" in error_message.lower() or "timeout" in error_message.lower():
            return f"⚠️ Connection error while accessing {model_name}. " \
                   f"Please check your internet connection and try again."
        
        # Fallback for other errors
        else:
            return f"⚠️ An error occurred while using {model_name}. " \
                   f"Please try again or select a different model. Error details: {error_message}"

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
