import os
import yaml
import time
from datetime import datetime
from litellm import Router
import logging
from app.env_loader import ensure_model_env_vars
from typing import Optional, Dict, Any
from litellm import completion
import litellm
from litellm import (
    RateLimitError,
    AuthenticationError,
    BadRequestError,
    InvalidRequestError,
    BudgetExceededError,
    JSONSchemaValidationError,
    ContextWindowExceededError,
    ServiceUnavailableError,
    Timeout,
    APIConnectionError,
    APIError
)
from app.exceptions import LLMErrorClassifier, ErrorSeverity, PipelineError
from app.utils.retry import retry_sync_with_backoff, RetryConfig
from app.utils.circuit_breaker import CircuitBreaker, CircuitBreakerOpen

# Configure logging
logging.basicConfig(level=logging.INFO)  # Set the default logging level
logger = logging.getLogger(__name__)

# Suppress LiteLLM logs
litellm_logger = logging.getLogger('litellm')
litellm_logger.setLevel(logging.ERROR)  # Changed from CRITICAL to ERROR for consistency

# Remove all handlers from the LiteLLM logger
for handler in litellm_logger.handlers[:]:
    litellm_logger.removeHandler(handler)

# Add a null handler to prevent propagation
litellm_logger.addHandler(logging.NullHandler())

# Configure LiteLLM to drop unsupported params
litellm.drop_params = True  # Drop unsupported params instead of erroring

# Note: LiteLLM doesn't support httpx connection pooling configuration
# File descriptor leaks are managed by:
# 1. System FD limit set to 8192 (in systemd service)
# 2. Connection manager with periodic cleanup (in main.py startup)
# 3. Automatic cleanup via connection manager monitoring

# Load environment variables and ensure they're properly set for models
ensure_model_env_vars()

def get_litellm_config_path():
    """Get the LiteLLM config path - check environment variable first, then use litellm_config.yaml."""
    # Check if environment variable specifies a config path
    env_config_path = os.environ.get('LITELLM_CONFIG_PATH')
    if env_config_path and os.path.exists(env_config_path):
        logger.debug(f"Using environment-specified config: {env_config_path}")
        return env_config_path
    
    # Default to litellm_config.yaml
    config_dir = os.path.join(os.path.dirname(__file__), 'config')
    config_path = os.path.join(config_dir, 'litellm_config.yaml')
    logger.debug(f"Using default config: {config_path}")
    return config_path

def clean_outdated_model_env_vars():
    """
    Remove environment variables for models that are no longer in the config file.
    This ensures that deleted models don't linger in the environment.
    """
    # Load the config file to get the current models
    config_path = get_litellm_config_path()
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    # Extract model names from config
    configured_models = set()
    for model in config.get("model_list", []):
        if "model_name" in model:
            configured_models.add(model["model_name"])
    
    logger.debug(f"Models in config: {configured_models}")    
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
        'XAI_API_KEY_': 'xai',
        'AUNOOAI_API_KEY_': 'aunooai'  # Add support for AUNOOAI provider
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
        logger.info("Removed environment variables for models not in config:")
        for var, model, provider in removed_vars:
            logger.info(f"  - {var} ({model}, {provider})")

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
            # Set API key if provided
            if self.api_key:
                os.environ[f"{self.model.upper()}_API_KEY"] = self.api_key

            # Generate completion
            response = completion(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=self.max_tokens,
                temperature=self.temperature
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
            ``{"role": "user|system|assistant", "content": str}``.
        """

        try:
            # Set API key if provided (important when multiple models/
            # providers coexist)
            if self.api_key:
                os.environ[f"{self.model.upper()}_API_KEY"] = self.api_key

            response = completion(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )

            # Extract the content field in a generic way.
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
        logger.info(f"🚀 Initializing LiteLLMModel with model: {model_name}")
        self.model_name = model_name
        # Create a basic config dictionary that AIModel expects
        model_config = {
            "model": model_name,
            "max_tokens": 2000,
            "temperature": 0.7
        }
        super().__init__(model_config)
        logger.debug(f"✅ AIModel base class initialized for {model_name}")
        self.router = None
        self.model_name_to_path = {}  # Map model names to their full paths

        # Initialize circuit breaker for this model
        self.circuit_breaker = CircuitBreaker(model_name)

        # Initialize router with detailed logging
        try:
            self.init_router()
            logger.info(f"🎯 LiteLLMModel successfully initialized for {model_name}")
        except Exception as e:
            logger.error(f"❌ Failed to initialize LiteLLMModel for {model_name}: {str(e)}")
            raise

        # Store this instance
        LiteLLMModel._instances[model_name] = self
        logger.debug(f"📝 Stored instance for {model_name}, current instances: {list(LiteLLMModel._instances.keys())}")

    @classmethod
    def get_instance(cls, model_name):
        """Get or create an instance for the given model name"""
        logger.debug(f"🔍 Requesting instance for model: {model_name}")
        if model_name not in cls._instances:
            logger.info(f"🆕 Creating new instance for {model_name}")
            instance = cls(model_name)
        else:
            logger.debug(f"♻️ Reusing existing instance for {model_name}")
            instance = cls._instances[model_name]
        return instance

    def init_router(self):
        logger.info(f"🔧 Starting router initialization for model: {self.model_name}")
        
        # Ensure router is cleared before reinitializing
        self.router = None
        
        # Load and merge configurations from both config files
        config_dir = os.path.join(os.path.dirname(__file__), 'config')
        local_config_path = os.path.join(config_dir, 'litellm_config.yaml.local')
        default_config_path = os.path.join(config_dir, 'litellm_config.yaml')
        
        # Start with an empty merged config
        merged_config = {
            "model_list": [],
            "routing_strategy": "least-busy",
            "max_retries": 0,
            "timeout": 30,
            "fallbacks": []
        }
        
        # Load default config first
        if os.path.exists(default_config_path):
            logger.info(f"📖 Loading default config from: {default_config_path}")
            try:
                with open(default_config_path, 'r') as f:
                    default_config = yaml.safe_load(f) or {}
                merged_config["model_list"].extend(default_config.get("model_list", []))
                # Update other settings from default config
                for key in ["routing_strategy", "max_retries", "timeout"]:
                    if key in default_config:
                        merged_config[key] = default_config[key]
                if "fallbacks" in default_config:
                    merged_config["fallbacks"].extend(default_config["fallbacks"])
                logger.debug(f"✅ Default config loaded, found {len(default_config.get('model_list', []))} models")
            except Exception as e:
                logger.warning(f"⚠️ Failed to load default config file: {str(e)}")
        
        # Load local config and merge
        if os.path.exists(local_config_path):
            logger.info(f"📖 Loading local config from: {local_config_path}")
            try:
                with open(local_config_path, 'r') as f:
                    local_config = yaml.safe_load(f) or {}
                merged_config["model_list"].extend(local_config.get("model_list", []))
                # Local config settings override default config
                for key in ["routing_strategy", "max_retries", "timeout"]:
                    if key in local_config:
                        merged_config[key] = local_config[key]
                if "fallbacks" in local_config:
                    merged_config["fallbacks"].extend(local_config["fallbacks"])
                logger.debug(f"✅ Local config loaded, found {len(local_config.get('model_list', []))} models")
            except Exception as e:
                logger.warning(f"⚠️ Failed to load local config file: {str(e)}")
        
        # Use the merged config
        config = merged_config
        logger.info(f"🔗 Merged configs - total models found: {len(config.get('model_list', []))}")
        
        if not config.get("model_list"):
            logger.error("❌ No model configurations found in either config file")
            raise ValueError("No model configurations found in either config file")
        
        # Get currently configured models with their API keys
        configured_models = get_available_models()
        logger.info(f"🔑 Found {len(configured_models)} configured models with API keys")
        
        # Verify the model is configured
        configured_model_names = [cm['name'] for cm in configured_models]
        if not any(cm['name'] == self.model_name for cm in configured_models):
            logger.error(f"❌ Model {self.model_name} is not in configured models: {configured_model_names}")
            raise ValueError(f"Model {self.model_name} is not in configured models: {configured_model_names}")
        
        logger.info(f"✅ Model {self.model_name} is properly configured")
        
        # Include all models in the router to support fallbacks
        filtered_model_list = []
        processed_models = []
        
        for model in config["model_list"]:
            model_name = model.get('model_name', 'unknown')
            logger.debug(f"🔍 Processing model {model_name} from config")
            
            # Check if model requires an API key
            if 'api_key' in model['litellm_params']:
                env_key = model['litellm_params']['api_key'].split('/')[-1]
                logger.debug(f"🔑 Model {model_name} requires API key: {env_key}")
                
                if env_key not in os.environ:
                    logger.warning(f"⚠️ API key {env_key} not found in environment for model {model_name}, skipping")
                    continue
                    
                logger.debug(f"✅ API key found for {model_name}")
                model_copy = model.copy()
                model_copy['litellm_params'] = model_copy['litellm_params'].copy()
                model_copy['litellm_params']['api_key'] = os.environ[env_key]
                
                # For custom OpenAI providers, use just the model name without the provider prefix
                if (model_copy['litellm_params'].get('custom_llm_provider') == 'openai' and 
                    model_copy['litellm_params'].get('api_base')):
                    original_model = model_copy['litellm_params']['model']
                    # Extract just the model name (e.g., "mixtral" from "aunooai/mixtral")
                    model_name_only = original_model.split('/')[-1] if '/' in original_model else original_model
                    model_copy['litellm_params']['model'] = model_name_only
                    logger.info(f"🔄 Custom OpenAI provider detected - changed model path from '{original_model}' to '{model_name_only}' for {model_name}")
                else:
                    logger.debug(f"🔄 Preserving full model path '{model_copy['litellm_params']['model']}' for {model_name}")
                
            else:
                # For models without API key (like local Ollama - testing)
                logger.debug(f"🏠 Model {model_name} does not require API key (local model)")
                model_copy = model.copy()
            
            filtered_model_list.append(model_copy)
            processed_models.append(model_name)
            
            # Store the mapping from model name to full model path
            self.model_name_to_path[model['model_name']] = model['litellm_params']['model']
            logger.debug(f"📝 Mapped {model['model_name']} -> {model['litellm_params']['model']}")
        
        if not filtered_model_list:
            logger.error("❌ No properly configured models found in config")
            raise ValueError(f"No properly configured models found in config")
        
        logger.info(f"🎯 Creating router with {len(filtered_model_list)} models: {processed_models}")
        
        # Log router configuration details
        routing_strategy = config.get("routing_strategy", "simple-shuffle")
        max_retries = config.get("max_retries", 0)
        timeout = config.get("timeout", 30)
        fallbacks = config.get("fallbacks", [])
        
        logger.debug(f"⚙️ Router settings - Strategy: {routing_strategy}, Retries: {max_retries}, Timeout: {timeout}s")
        if fallbacks:
            logger.info(f"🔄 Fallback configuration found: {fallbacks}")
        
        # Create new router instance with all available models
        try:
            self.router = Router(
                model_list=filtered_model_list,
                cache_responses=False,
                routing_strategy=routing_strategy,
                set_verbose=False,
                num_retries=max_retries,
                default_litellm_params={
                    "timeout": timeout,
                    "max_retries": max_retries,
                    # Removed client_session_max_size - not supported by OpenAI
                },
                fallbacks=fallbacks
            )
            logger.info(f"✅ Router successfully created for {self.model_name}")
        except Exception as e:
            logger.error(f"❌ Failed to create router: {str(e)}")
            raise

    def _retry_sync(self, func, *args, retryable_exceptions=None, config=None, **kwargs):
        """
        Synchronous retry helper to avoid event loop conflicts.

        Args:
            func: Function to retry
            *args: Positional arguments for func
            retryable_exceptions: Tuple of exception types to retry on
            config: RetryConfig instance
            **kwargs: Keyword arguments for func

        Returns:
            Result of successful function call

        Raises:
            Last exception if all retries exhausted
        """
        if retryable_exceptions is None:
            retryable_exceptions = (Exception,)

        return retry_sync_with_backoff(
            func,
            *args,
            retryable_exceptions=retryable_exceptions,
            config=config,
            **kwargs
        )

    def _generate_with_retry(self, messages):
        """Helper method for retry logic - makes actual LLM call"""
        response = self.router.completion(
            model=self.model_name,
            messages=messages,
            metadata={"model_name": self.model_name},
            caching=False
        )

        # Extract content
        if hasattr(response, 'choices') and len(response.choices) > 0:
            if hasattr(response.choices[0], 'message') and hasattr(response.choices[0].message, 'content'):
                return response.choices[0].message.content

        return str(response)

    def _try_fallback_model(self, messages, attempted_models, reason):
        """
        Try fallback models when primary model fails.

        Args:
            messages: Messages to send
            attempted_models: Set of already attempted model names
            reason: Reason for fallback

        Returns:
            Response from fallback model, or None if all fallbacks exhausted
        """
        logger.info(f"🔄 Attempting fallback for {self.model_name}: {reason}")

        # Get fallbacks configuration
        config_dir = os.path.join(os.path.dirname(__file__), 'config')
        local_config_path = os.path.join(config_dir, 'litellm_config.yaml.local')
        default_config_path = os.path.join(config_dir, 'litellm_config.yaml')

        config_path = local_config_path if os.path.exists(local_config_path) else default_config_path
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)

        fallbacks_config = config.get("fallbacks", [])

        # Find fallbacks for the current model
        for fallback_dict in fallbacks_config:
            if self.model_name in fallback_dict:
                fallback_models = fallback_dict[self.model_name]
                logger.info(f"🎯 Found {len(fallback_models)} fallback models: {fallback_models}")

                # Try each fallback model that hasn't been attempted yet
                for fallback_model_name in fallback_models:
                    if fallback_model_name in attempted_models:
                        logger.debug(f"⏭️ Skipping already attempted fallback: {fallback_model_name}")
                        continue

                    logger.info(f"🔄 Attempting fallback to {fallback_model_name}")
                    try:
                        # Get or create the fallback model instance
                        fallback_model = LiteLLMModel.get_instance(fallback_model_name)
                        # Call generate_response on the fallback model
                        result = fallback_model.generate_response(
                            messages,
                            _is_fallback=True,
                            _attempted_models=attempted_models
                        )
                        logger.info(f"✅ Fallback to {fallback_model_name} succeeded")
                        return result
                    except Exception as fallback_error:
                        logger.warning(f"❌ Fallback to {fallback_model_name} failed: {str(fallback_error)}")
                        continue

        logger.warning(f"⚠️ All fallback options exhausted for {self.model_name}")
        return None

    def generate_response(self, messages, _is_fallback=False, _attempted_models=None):
        """
        Generate a response using the LLM with proper exception handling.

        Args:
            messages: The messages to send to the LLM
            _is_fallback: Internal parameter to track if this is a fallback call
            _attempted_models: Internal parameter to track which models have been attempted

        Returns:
            The generated response text or error message

        Raises:
            PipelineError: For FATAL errors that should stop pipeline processing
        """
        # Initialize tracking of attempted models if this is the first call
        if _attempted_models is None:
            _attempted_models = set()

        # Add current model to attempted models
        _attempted_models.add(self.model_name)

        logger.info(f"🤖 Starting response generation with {self.model_name} (fallback: {_is_fallback})")
        logger.debug(f"📊 Request details - Messages: {len(messages)}, Attempted models: {list(_attempted_models)}")

        try:
            # Check circuit breaker before making request
            try:
                self.circuit_breaker.check_circuit()
            except CircuitBreakerOpen as e:
                logger.error(f"🔴 CIRCUIT BREAKER: Circuit is OPEN for {self.model_name}")
                logger.error(f"🔴 Reason: {e}")
                logger.error(f"🔴 ACTION: Blocking request, attempting fallback model")
                # Try fallback if available
                if not _is_fallback:
                    logger.info(f"🔄 Attempting fallback model for {self.model_name}")
                    fallback_result = self._try_fallback_model(messages, _attempted_models, "Circuit breaker open")
                    if fallback_result:
                        logger.info(f"✅ Fallback model succeeded")
                        return fallback_result
                    logger.warning(f"⚠️ No fallback available - returning error message to user")
                return f"⚠️ {self.model_name} is temporarily unavailable due to repeated failures. Please try again later or use a different model."

            logger.debug(f"🎯 Using router with model: {self.model_name}")
            logger.info(f"🚀 Sending request to LiteLLM router for {self.model_name}")

            response = self.router.completion(
                model=self.model_name,
                messages=messages,
                metadata={"model_name": self.model_name},
                caching=False
            )

            logger.info(f"✅ Received response from {self.model_name}")

            # Record success in circuit breaker
            self.circuit_breaker.record_success()

            # Extract content from response
            if hasattr(response, 'choices') and len(response.choices) > 0:
                if hasattr(response.choices[0], 'message') and hasattr(response.choices[0].message, 'content'):
                    content = response.choices[0].message.content
                    logger.info(f"✅ Successfully extracted content from {self.model_name} (length: {len(content) if content else 0})")
                    return content

            # Fallback content extraction
            return str(response)

        # ========= FATAL ERRORS - Must stop processing =========
        except AuthenticationError as e:
            logger.error(f"🚨 ERROR CLASSIFICATION: FATAL - AuthenticationError")
            logger.error(f"🚨 Model: {self.model_name}")
            logger.error(f"🚨 Error: {e}")
            logger.error(f"🚨 ACTION: Stopping pipeline - Check API key configuration and restart service")
            logger.error(f"🚨 Circuit breaker: Recording failure")
            self.circuit_breaker.record_failure(e)
            raise PipelineError(
                f"Authentication failed - invalid API key for {self.model_name}",
                severity=ErrorSeverity.FATAL,
                original_exception=e
            )

        except BudgetExceededError as e:
            logger.error(f"🚨 ERROR CLASSIFICATION: FATAL - BudgetExceededError")
            logger.error(f"🚨 Model: {self.model_name}")
            logger.error(f"🚨 Error: {e}")
            logger.error(f"🚨 ACTION: Stopping pipeline - API budget or quota limit reached")
            logger.error(f"🚨 Circuit breaker: Recording failure")
            self.circuit_breaker.record_failure(e)
            raise PipelineError(
                f"Budget exceeded for {self.model_name} - check account limits",
                severity=ErrorSeverity.FATAL,
                original_exception=e
            )

        # ========= RECOVERABLE ERRORS - Retry with backoff =========
        except RateLimitError as e:
            logger.warning(f"⚠️ ERROR CLASSIFICATION: RECOVERABLE - RateLimitError")
            logger.warning(f"⚠️ Model: {self.model_name}")
            logger.warning(f"⚠️ Error: {e}")
            logger.warning(f"⚠️ ACTION: Attempting retry with exponential backoff (max 3 attempts, base delay 2.0s)")
            logger.warning(f"⚠️ Circuit breaker: Recording failure")
            self.circuit_breaker.record_failure(e)

            # Try retry with exponential backoff
            try:
                config = RetryConfig(max_attempts=3, base_delay=2.0)
                logger.info(f"🔄 Starting retry sequence for {self.model_name} - RateLimitError")
                result = self._retry_sync(
                    self._generate_with_retry,
                    messages,
                    retryable_exceptions=(RateLimitError,),
                    config=config
                )
                # Record success after successful retry
                logger.info(f"✅ Retry succeeded for {self.model_name}")
                logger.info(f"✅ Circuit breaker: Recording success")
                self.circuit_breaker.record_success()
                return result
            except Exception as retry_error:
                # All retries exhausted - try fallback model
                logger.error(f"❌ All retry attempts exhausted for {self.model_name}")
                logger.error(f"❌ ACTION: Attempting fallback model")
                if not _is_fallback:
                    fallback_result = self._try_fallback_model(messages, _attempted_models, "Rate limit exceeded")
                    if fallback_result:
                        logger.info(f"✅ Fallback model succeeded")
                        return fallback_result
                    logger.warning(f"⚠️ No fallback available - returning error message to user")
                return f"⚠️ Rate limit exceeded for {self.model_name}. Please try again later or use a different model."

        except (Timeout, APIConnectionError) as e:
            error_type = type(e).__name__
            logger.warning(f"⚠️ ERROR CLASSIFICATION: RECOVERABLE - {error_type}")
            logger.warning(f"⚠️ Model: {self.model_name}")
            logger.warning(f"⚠️ Error: {e}")
            logger.warning(f"⚠️ ACTION: Attempting retry with exponential backoff (max 2 attempts, base delay 1.0s)")
            logger.warning(f"⚠️ Circuit breaker: Recording failure")
            self.circuit_breaker.record_failure(e)

            # Try retry once
            try:
                config = RetryConfig(max_attempts=2, base_delay=1.0)
                logger.info(f"🔄 Starting retry sequence for {self.model_name} - {error_type}")
                result = self._retry_sync(
                    self._generate_with_retry,
                    messages,
                    retryable_exceptions=(Timeout, APIConnectionError),
                    config=config
                )
                # Record success after successful retry
                logger.info(f"✅ Retry succeeded for {self.model_name}")
                logger.info(f"✅ Circuit breaker: Recording success")
                self.circuit_breaker.record_success()
                return result
            except (Timeout, APIConnectionError):
                # Retry failed - try fallback
                logger.error(f"❌ All retry attempts exhausted for {self.model_name}")
                logger.error(f"❌ ACTION: Attempting fallback model")
                if not _is_fallback:
                    fallback_result = self._try_fallback_model(messages, _attempted_models, f"Network error: {str(e)}")
                    if fallback_result:
                        logger.info(f"✅ Fallback model succeeded")
                        return fallback_result
                    logger.warning(f"⚠️ No fallback available - returning error message to user")
                return f"⚠️ Connection error while accessing {self.model_name}. Please check your internet connection and try again."

        # ========= SKIPPABLE ERRORS - Skip this request =========
        except ContextWindowExceededError as e:
            logger.warning(f"⚠️ ERROR CLASSIFICATION: SKIPPABLE - ContextWindowExceededError")
            logger.warning(f"⚠️ Model: {self.model_name}")
            logger.warning(f"⚠️ Error: {e}")
            logger.warning(f"⚠️ ACTION: Skipping this request, attempting fallback model")
            logger.warning(f"⚠️ Circuit breaker: Recording failure")
            self.circuit_breaker.record_failure(e)

            # Try fallback with smaller context window
            if not _is_fallback:
                logger.info(f"🔄 Attempting fallback model for {self.model_name}")
                fallback_result = self._try_fallback_model(
                    messages, _attempted_models,
                    "Content too large for context window"
                )
                if fallback_result:
                    logger.info(f"✅ Fallback model succeeded")
                    return fallback_result
                logger.warning(f"⚠️ No fallback available - returning error message to user")

            # No fallback available - return error message
            return (
                f"⚠️ Content exceeds maximum length for {self.model_name}. "
                "Please reduce content size or split into smaller chunks."
            )

        except (BadRequestError, InvalidRequestError, JSONSchemaValidationError) as e:
            error_type = type(e).__name__
            logger.warning(f"⚠️ ERROR CLASSIFICATION: SKIPPABLE - {error_type}")
            logger.warning(f"⚠️ Model: {self.model_name}")
            logger.warning(f"⚠️ Error: {e}")
            logger.warning(f"⚠️ ACTION: Skipping this request - Invalid request format")
            logger.warning(f"⚠️ Circuit breaker: Recording failure")
            self.circuit_breaker.record_failure(e)
            return (
                f"⚠️ Invalid request for {self.model_name}. "
                f"Details: {str(e)}"
            )

        # ========= DEGRADED ERRORS - Try fallback =========
        except (ServiceUnavailableError, APIError) as e:
            error_type = type(e).__name__
            logger.warning(f"⚠️ ERROR CLASSIFICATION: DEGRADED - {error_type}")
            logger.warning(f"⚠️ Model: {self.model_name}")
            logger.warning(f"⚠️ Error: {e}")
            logger.warning(f"⚠️ ACTION: Service degraded, attempting fallback model")
            logger.warning(f"⚠️ Circuit breaker: Recording failure")
            self.circuit_breaker.record_failure(e)

            if not _is_fallback:
                logger.info(f"🔄 Attempting fallback model for {self.model_name}")
                fallback_result = self._try_fallback_model(messages, _attempted_models, f"Service error: {str(e)}")
                if fallback_result:
                    logger.info(f"✅ Fallback model succeeded")
                    return fallback_result
                logger.warning(f"⚠️ No fallback available - returning error message to user")

            return f"⚠️ {self.model_name} is currently unavailable. Please try a different model."

        # ========= UNKNOWN ERRORS - Classify and handle =========
        except Exception as e:
            error_message = str(e)
            error_type = type(e).__name__
            logger.error(f"❌ ERROR: Unknown exception type - {error_type}")
            logger.error(f"❌ Model: {self.model_name}")
            logger.error(f"❌ Error: {e}")
            logger.error(f"❌ Circuit breaker: Recording failure")
            self.circuit_breaker.record_failure(e)

            # Classify the error
            severity = LLMErrorClassifier.classify(e)
            logger.error(f"❌ ERROR CLASSIFICATION: {severity.value} - {error_type}")

            if severity == ErrorSeverity.FATAL:
                logger.error(f"🚨 ACTION: Stopping pipeline - Unknown error classified as FATAL")
                raise PipelineError(
                    f"Unexpected error with {self.model_name}: {error_message}",
                    severity=ErrorSeverity.FATAL,
                    original_exception=e
                )

            # Try fallback for non-fatal unknown errors
            logger.warning(f"⚠️ ACTION: Attempting fallback model (error classified as {severity.value})")
            if not _is_fallback:
                fallback_result = self._try_fallback_model(messages, _attempted_models, f"Error: {error_message}")
                if fallback_result:
                    logger.info(f"✅ Fallback model succeeded")
                    return fallback_result
                logger.warning(f"⚠️ No fallback available - returning error message to user")

            return f"⚠️ An error occurred while using {self.model_name}. Please try again or select a different model. Error: {error_message}"

    def _extract_user_friendly_error(self, error_message, model_name):
        """Extract user-friendly error messages from common errors."""
        logger.debug(f"🔍 Extracting user-friendly error from: {error_message[:200]}...")
        
        # Context length exceeded error
        if "context length" in error_message and "tokens" in error_message:
            import re
            # Try to extract the max tokens and actual tokens
            max_tokens_match = re.search(r"maximum context length is (\d+)", error_message)
            actual_tokens_match = re.search(r"resulted in (\d+) tokens", error_message)
            
            if max_tokens_match and actual_tokens_match:
                max_tokens = max_tokens_match.group(1)
                actual_tokens = actual_tokens_match.group(1)
                logger.info(f"📏 Context length error details - Max: {max_tokens}, Actual: {actual_tokens}")
                return f"⚠️ Your request exceeds the maximum context length for {model_name}. " \
                       f"The model can handle {max_tokens} tokens, but your input has {actual_tokens} tokens. " \
                       f"Please reduce the length of your input or try a model with a larger context window."
            else:
                logger.warning(f"📏 Context length error but couldn't extract token details")
                return f"⚠️ Your request exceeds the maximum context length for {model_name}. " \
                       f"Please reduce the length of your input or try a model with a larger context window."
        
        # API key errors
        elif "api key" in error_message.lower() or "apikey" in error_message.lower():
            logger.warning(f"🔑 API key error for {model_name}")
            return f"⚠️ There was an issue with the API key for {model_name}. " \
                   f"Please check your API key configuration."
        
        # Rate limit errors
        elif "rate limit" in error_message.lower() or "ratelimit" in error_message.lower():
            logger.warning(f"🚦 Rate limit error for {model_name}")
            return f"⚠️ Rate limit exceeded for {model_name}. " \
                   f"Please try again later or use a different model."

        # Quota/billing errors (OpenAI credits exhausted)
        elif any(phrase in error_message.lower() for phrase in [
            "exceeded your current quota",
            "insufficient_quota",
            "billing",
            "quota exceeded",
            "insufficient quota"
        ]):
            logger.error(f"💳 Quota/billing error for {model_name}")
            return f"⚠️ API quota exceeded for {model_name}. " \
                   f"Your API credits may be exhausted or billing may need attention. " \
                   f"Please check your API provider's billing dashboard."

        # Model not available
        elif "model" in error_message.lower() and ("not found" in error_message.lower() or 
                                                 "unavailable" in error_message.lower() or
                                                 "not available" in error_message.lower()):
            logger.warning(f"🚫 Model unavailable error for {model_name}")
            return f"⚠️ The model {model_name} is currently unavailable. " \
                   f"Please try a different model."
        
        # Connection errors
        elif "connection" in error_message.lower() or "timeout" in error_message.lower():
            logger.warning(f"🔌 Connection error for {model_name}")
            return f"⚠️ Connection error while accessing {model_name}. " \
                   f"Please check your internet connection and try again."
        
        # Fallback for other errors
        else:
            logger.warning(f"❓ Unknown error type for {model_name}")
            return f"⚠️ An error occurred while using {model_name}. " \
                   f"Please try again or select a different model. Error details: {error_message}"

def get_available_models():
    """Get models that have API keys configured in the environment."""
    logger.debug("🔍 Scanning for configured models from litellm_config.yaml...")

    models = []

    # Provider-level API keys
    provider_keys = {
        'openai': os.getenv('OPENAI_API_KEY'),
        'anthropic': os.getenv('ANTHROPIC_API_KEY'),
        'gemini': os.getenv('GEMINI_API_KEY'),
        'google': os.getenv('GEMINI_API_KEY'),  # Gemini uses Google provider
        'huggingface': os.getenv('HUGGINGFACE_API_KEY'),
        'azure': os.getenv('AZURE_API_KEY'),
        'cohere': os.getenv('COHERE_API_KEY'),
        'mistral': os.getenv('MISTRAL_API_KEY')
    }

    # Read models from litellm_config.yaml
    try:
        import yaml
        config_path = os.path.join(os.path.dirname(__file__), 'config', 'litellm_config.yaml')
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)

            model_list = config.get('model_list', [])

            for model_config in model_list:
                model_name = model_config.get('model_name')
                litellm_params = model_config.get('litellm_params', {})
                model_path = litellm_params.get('model', '')

                # Extract provider from model path (e.g., "openai/gpt-4" -> "openai")
                if '/' in model_path:
                    provider = model_path.split('/')[0]
                else:
                    provider = 'unknown'

                # Check if provider key is configured
                api_key = litellm_params.get('api_key', '')
                if api_key.startswith('os.environ/'):
                    # Extract env var name
                    env_var = api_key.replace('os.environ/', '')
                    key_value = os.getenv(env_var)

                    # Only include model if the API key is configured
                    if key_value and key_value.strip() and not key_value.startswith('your-'):
                        models.append({
                            "name": model_name,
                            "provider": provider
                        })
                        logger.debug(f"✅ Found configured model: {model_name} ({provider})")
                    else:
                        logger.debug(f"⏭️ Skipping {model_name} - {env_var} not configured")
        else:
            logger.warning(f"⚠️ litellm_config.yaml not found at {config_path}")

    except Exception as e:
        logger.error(f"❌ Error reading litellm_config.yaml: {e}")

    if not models:
        logger.warning("⚠️ No configured models found. Please check your environment variables.")
    else:
        logger.info(f"🎯 Found {len(models)} configured models: {[m['name'] for m in models]}")

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
    config_dir = os.path.join(os.path.dirname(__file__), 'config')
    local_config_path = os.path.join(config_dir, 'litellm_config.yaml.local')
    default_config_path = os.path.join(config_dir, 'litellm_config.yaml')
    
    config_path = local_config_path if os.path.exists(local_config_path) else default_config_path
    logger.debug(f"Looking for config file at: {config_path}")
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
        
        logger.debug(f"Available unique models from config: {unique_models}")
        return unique_models
    except Exception as e:
        logger.error(f"Error reading config file: {str(e)}")
        return []
