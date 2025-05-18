import os
import yaml
from litellm import Router
import logging
from app.env_loader import ensure_model_env_vars
from typing import Optional, Dict, Any
from litellm import completion
import copy

# Configure logging
logging.basicConfig(level=logging.INFO)  # Set the default logging level
logger = logging.getLogger(__name__)

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
        'AUNOOAI_API_KEY_': 'aunooai',
        'OPENAI_API_KEY_': 'openai',
        'OPENAI_COMPATIBLE_API_KEY_': 'openai_compatible',
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
    def __init__(self, model_config: Dict[str, Any]):
        self.config = model_config
        self.model = model_config["model"]
        self.api_key = model_config.get("api_key")
        self.max_tokens = model_config.get("max_tokens", 2000)
        self.temperature = model_config.get("temperature", 0.7)
        # Ensure a uniform attribute name that other components expect.
        # ``LiteLLMModel`` uses ``model_name`` so we mirror that here.
        self.model_name = self.model  # type: ignore[attr-defined]

    async def generate(self, prompt: str) -> Any:
        try:
            model_to_pass_to_litellm = self.model
            custom_provider = self.config.get("custom_llm_provider")
            if custom_provider == "openai" and self.model.startswith("aunooai/"):
                model_to_pass_to_litellm = self.model.split('/', 1)[1]

            # Generate completion
            response = completion(
                model=model_to_pass_to_litellm,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                custom_llm_provider=custom_provider,
                api_base=self.config.get("api_base"),
                api_key=self.api_key  # Pass api_key directly
            )

            return response.choices[0]

        except Exception as e:
            logger.error(f"Error generating with model {self.model}: {str(e)}")
            raise

    def generate_response(self, messages):
        """Generate a response from a list of chat *messages*.

        This mirrors the signature expected by the rest of the codebase
        (e.g., *chat_routes.py*).  It keeps the implementation minimal and
        synchronous, delegating the heavy-lifting to *litellm.completion* just
        like the *generate* coroutine but without forcing callers to use
        ``await``.

        Parameters
        ----------
        messages : list[dict]
            The usual OpenAI-style message list:
            ``{\\"role\\": \\"user|system|assistant\\", \\"content\\": str}``.
        """
        try:
            model_to_pass_to_litellm = self.model
            custom_provider = self.config.get("custom_llm_provider")
            if custom_provider == "openai" and self.model.startswith("aunooai/"):
                model_to_pass_to_litellm = self.model.split('/', 1)[1]

            response = completion(
                model=model_to_pass_to_litellm,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                custom_llm_provider=custom_provider,
                api_base=self.config.get("api_base"),
                api_key=self.api_key  # Ensure this essential fix is kept
            )

            # Restore original return logic
            if (
                hasattr(response, "choices")
                and response.choices
                and hasattr(response.choices[0], "message")
                and hasattr(response.choices[0].message, "content")
            ):
                return response.choices[0].message.content

            # Fallback: try to cast to str so the caller gets *something*.
            return str(response)

        except Exception as e:
            logger.error(
                "Error in generate_response with model %s: %s",
                self.model,
                str(e),
            )
            # Propagate so higher-level error handling (fallbacks, HTTP 500 etc.)
            # works.
            raise

def load_model_config() -> Dict[str, Dict[str, Any]]:
    """Load model configuration from *litellm_config.yaml*.

    The YAML may use either the legacy ``models`` mapping **or** the newer
    ``model_list`` structure introduced by LiteLLM.  For backward
    compatibility we merge both:

    * ``models`` – a mapping keyed by model name.
    * ``model_list`` – a list of entries that include ``model_name``.

    Returns
    -------
    dict[str, dict]
        Dictionary keyed by model name with its configuration as the value.
    """

    # Locate the config file relative to this module to avoid path issues when
    # the working directory changes (e.g. when running tests or uvicorn).
    config_path = os.path.join(
        os.path.dirname(__file__),
        "config",
        "litellm_config.yaml",
    )

    try:
        with open(config_path, "r") as f:
            raw_config = yaml.safe_load(f) or {}

        # Start with the explicit ``models`` mapping if present (legacy format)
        models: Dict[str, Dict[str, Any]] = raw_config.get("models", {}).copy()

        # Merge in any entries from the ``model_list`` format that are missing
        # from the mapping.  We deliberately *do not* overwrite existing keys
        # so that explicit config wins over derived config.
        for model_entry in raw_config.get("model_list", []):
            model_name = model_entry.get("model_name")
            if not model_name:
                continue  # Skip invalid entries

            if model_name not in models:
                # Convert the liteLLM style to the expected structure.
                litellm_params = model_entry.get("litellm_params", {})
                models[model_name] = {
                    "model": litellm_params.get("model", model_name),
                    # Provide sane defaults if they are not specified.
                    "max_tokens": litellm_params.get("max_tokens", 2000),
                    "temperature": litellm_params.get("temperature", 0.7),
                    # Store the raw litellm params so callers can access them
                    # when needed (e.g., api_key extraction).
                    **litellm_params,
                }

        return models

    except FileNotFoundError:
        logger.error(
            "litellm_config.yaml not found at %s. No models available.", config_path
        )
        return {}
    except Exception as e:
        logger.error(f"Error loading model config: {str(e)}")
        return {}

def get_ai_model(model_name: str) -> Optional[AIModel]:
    """Get an initialized AI model by name."""
    try:
        config = load_model_config()
        model_config = config.get(model_name)
        
        if not model_config:
            logger.error(f"Model {model_name} not found in config")
            return None

        return AIModel(model_config)

    except Exception as e:
        logger.error(f"Error initializing model {model_name}: {str(e)}")
        return None

class LiteLLMModel(AIModel):
    """Handler for models using LiteLLM."""
    
    _instances = {}  # Class-level dictionary to track instances
    _current_model = None  # Track the currently active model

    def __init__(self, model_name):
        self.model_name = model_name
        # Create a basic config dictionary that AIModel expects
        model_config = {
            "model": model_name,
            "max_tokens": 2000,
            "temperature": 0.7
        }
        super().__init__(model_config)
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
            # Create a deep copy to avoid modifying the original
            model_copy = copy.deepcopy(model)
            
            # Check if model requires an API key
            if 'api_key' in model_copy['litellm_params']:
                env_key = model_copy['litellm_params']['api_key'].split('/')[-1]
                if env_key not in os.environ:
                    continue
                model_copy['litellm_params']['api_key'] = os.environ[env_key]
            
            # Ensure all necessary parameters are preserved
            if 'api_base' in model_copy['litellm_params']:
                print(f"[DEBUG] Preserving api_base for {model_copy['model_name']}: {model_copy['litellm_params']['api_base']}")
            
            filtered_model_list.append(model_copy)
            print(f"[DEBUG] Added model to router: {model_copy['model_name']} with config: {model_copy['litellm_params']}")
        
        if not filtered_model_list:
            raise ValueError(f"No properly configured models found in config")
        
        print(f"[DEBUG] Creating router with models: {[m['model_name'] for m in filtered_model_list]}")
        
        # Create new router instance with all available models
        self.router = Router(
            model_list=filtered_model_list,
            cache_responses=False,
            routing_strategy=config.get("routing_strategy", "simple-shuffle"),
            set_verbose=True,  # Enable verbose mode for debugging
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
            
            # Get the model's configuration from the router
            model_config = next((m for m in self.router.model_list if m["model_name"] == self.model_name), None)
            if not model_config:
                raise ValueError(f"Model {self.model_name} not found in router configuration")
            
            print(f"\n[DEBUG] Making completion call with config:")
            print(f"Model: {self.model_name}")
            print(f"API Base: {model_config['litellm_params'].get('api_base')}")
            print(f"Provider: {model_config['litellm_params'].get('custom_llm_provider')}")
            print(f"Full config: {model_config['litellm_params']}\n")
            
            # Let LiteLLM handle fallbacks automatically
            response = self.router.completion(
                model=self.model_name,
                messages=messages,
                metadata={"model_name": self.model_name},
                caching=False,
                api_base=model_config["litellm_params"].get("api_base"),
                api_key=model_config["litellm_params"].get("api_key"),
                custom_llm_provider=model_config["litellm_params"].get("custom_llm_provider")
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

def get_available_models():
    """Get models that have API keys configured in the environment."""
    models = []
    seen = set()  # Track unique model names
    
    # Load the config file to get the correct model names
    config_path = os.path.join(os.path.dirname(__file__), 'config', 'litellm_config.yaml')
    model_name_to_env_var = {}  # Map to store which env var corresponds to which model
    
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            # Build a mapping from environment variable names to actual model names in config
            for model_entry_config in config.get('model_list', []): # Renamed to avoid conflict
                model_name_cfg = model_entry_config['model_name'] # Renamed
                if 'api_key' in model_entry_config.get('litellm_params', {}):
                    env_var_path = model_entry_config['litellm_params']['api_key']
                    if env_var_path.startswith("os.environ/"):
                        env_var = env_var_path.split("/")[-1]
                        model_name_to_env_var[env_var] = model_name_cfg
    except Exception as e:
        print(f"Warning: Couldn't load config models for env var mapping: {e}")
    
    # Expanded provider prefixes based on LiteLLM supported providers
    provider_prefixes = {
        'AUNOOAI_API_KEY_': 'aunooai',
        'OPENAI_API_KEY_': 'openai',
        'OPENAI_COMPATIBLE_API_KEY_': 'openai_compatible',
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
    
    print("\nChecking environment variables for API keys (in get_available_models):")
    for key in os.environ:
        for prefix, provider_from_prefix in provider_prefixes.items(): # Renamed
            if key.startswith(prefix):
                value = os.environ[key]
                if value and not value.startswith("os.environ/"):
                    # Use the mapping we created from config file if available
                    model_name_resolved = model_name_to_env_var.get(key)
                    if not model_name_resolved:
                        # Fallback to extracting from env var name if not in specific config map
                        model_name_from_env = key.split("_", 3)[-1].lower()
                        if "_" in model_name_from_env: # Renamed
                            model_name_from_env = model_name_from_env.replace("_", "-")
                        model_name_resolved = model_name_from_env
                    
                    model_key_tuple = (model_name_resolved, provider_from_prefix) # Renamed
                    if model_key_tuple not in seen:
                        seen.add(model_key_tuple)
                        models.append({
                            "name": model_name_resolved,
                            "provider": provider_from_prefix
                        })
                        print(f"Added model via env var: {model_name_resolved} ({provider_from_prefix}, based on {key})")
    
    if not models:
        print("No configured models found based on environment variables (in get_available_models).")
    else:
        print(f"\nFinal models from get_available_models (based on set env vars): {models}")
    
    return models

def ai_get_available_models():
    """Get all supported models from litellm configuration that have their API keys set.
    This is used for displaying available options in the UI.
    The provider name is derived from the 'model' field in litellm_params (e.g., 'aunooai' from 'aunooai/mixtral')
    or 'custom_llm_provider' as a fallback if no prefix exists in the model string.
    
    Returns:
        list: List of dicts with supported models, each containing:
            - name: The model name (e.g., 'gpt-4o')
            - provider: The provider name (e.g., 'aunooai', 'openai')
    """
    config_path = os.path.join(os.path.dirname(__file__), 'config', 'litellm_config.yaml')
    print(f"Looking for config file for UI models at: {config_path}")
    
    ui_models = []
    seen_ui_models = set() # To track (name, display_provider) tuples

    try:
        with open(config_path, 'r') as f:
            config_data = yaml.safe_load(f)
        
        if not config_data or 'model_list' not in config_data:
            print("Config file is empty or 'model_list' is missing.")
            return []

        for model_entry in config_data.get('model_list', []):
            model_name = model_entry.get('model_name')
            if not model_name:
                print(f"Skipping model entry due to missing 'model_name': {model_entry}")
                continue

            litellm_params = model_entry.get('litellm_params', {})
            
            # Determine display provider for this entry
            display_provider = ""
            litellm_model_str = litellm_params.get('model', '') 

            # PRIORITY 1: Provider from model string prefix (e.g., "aunooai" from "aunooai/mixtral")
            if '/' in litellm_model_str:
                display_provider = litellm_model_str.split('/', 1)[0]
            # PRIORITY 2: Fallback to custom_llm_provider if no prefix in model string
            else:
                display_provider = litellm_params.get('custom_llm_provider', '') 
                if not display_provider: 
                     print(f"Warning: Model '{model_name}' has no provider prefix in 'model' field ('{litellm_model_str}') and no 'custom_llm_provider'. Provider will be empty.")

            # Check if its API key (as specified in this entry) is set
            api_key_config_path = litellm_params.get('api_key', '') 
            key_is_set_for_this_entry = False
            if api_key_config_path.startswith("os.environ/"):
                env_var_to_check = api_key_config_path.split('/')[-1]
                if os.environ.get(env_var_to_check): 
                    key_is_set_for_this_entry = True
            
            if key_is_set_for_this_entry:
                model_tuple_for_ui = (model_name, display_provider)
                if model_tuple_for_ui not in seen_ui_models:
                    seen_ui_models.add(model_tuple_for_ui)
                    ui_models.append({
                        "name": model_name,
                        "provider": display_provider
                    })
                    print(f"Added to UI list: {model_name} (provider: {display_provider}) from config entry.")
            else:
                print(f"Skipping for UI list (API key not set for this entry): {model_name} (provider: {display_provider}) - Key path: {api_key_config_path}")
        
        print(f"\nFinal unique models for UI (from ai_get_available_models): {ui_models}")
        return ui_models
        
    except FileNotFoundError:
        print(f"Config file not found at {config_path}. No models available for UI.")
        return []
    except Exception as e:
        print(f"Error reading or processing config file in ai_get_available_models: {str(e)}")
        return []
