import os
import logging
from dotenv import load_dotenv
from pathlib import Path

logger = logging.getLogger(__name__)

def load_environment():
    """
    Load environment variables from the .env file.
    """
    try:
        # Get base directory (where app is located)
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env_path = os.path.join(base_dir, '.env')
        
        logger.info(f"Loading environment from: {env_path}")
        
        # Check if .env file exists
        if not os.path.exists(env_path):
            logger.warning(f"No .env file found at {env_path}")
            return None
            
        # Load environment variables
        load_dotenv(env_path, override=True)
        
        # Ensure keys are properly synchronized
        sync_api_keys()
        
        logger.info(f"Environment variables loaded from {env_path}")
        return env_path
    
    except Exception as e:
        logger.error(f"Error loading environment variables: {str(e)}")
        return None

def sync_api_keys():
    """
    Ensure all API keys are properly synchronized between different naming formats.
    Supports both legacy and new standardized naming conventions.
    """
    try:
        # Define the mapping between legacy and standardized names
        api_key_mappings = [
            # (legacy_name, intermediate_name, standardized_name)
            ("FIRECRAWL_API_KEY", "PROVIDER_FIRECRAWL_KEY", "PROVIDER_FIRECRAWL_API_KEY"),
            ("NEWSAPI_KEY", "PROVIDER_NEWSAPI_KEY", "PROVIDER_NEWSAPI_API_KEY"), 
            ("THENEWSAPI_KEY", "PROVIDER_THENEWSAPI_KEY", "PROVIDER_THENEWSAPI_API_KEY"),
            ("ELEVENLABS_API_KEY", None, "PROVIDER_ELEVENLABS_API_KEY"),
            ("DIA_API_KEY", None, "PROVIDER_DIA_API_KEY"),
            ("DIA_TTS_URL", None, "PROVIDER_DIA_TTS_URL"),
        ]
        
        for mapping in api_key_mappings:
            legacy_name, intermediate_name, standard_name = mapping
            
            # Get values from all possible sources
            legacy_value = os.environ.get(legacy_name)
            intermediate_value = os.environ.get(intermediate_name) if intermediate_name else None
            standard_value = os.environ.get(standard_name)
            
            # Determine which value to use (preference: standard > intermediate > legacy)
            primary_value = standard_value or intermediate_value or legacy_value
            
            if primary_value:
                # Set all variants to ensure compatibility
                if legacy_name and not os.environ.get(legacy_name):
                    os.environ[legacy_name] = primary_value
                    logger.info(f"Synchronized {legacy_name} from {standard_name}")
                    
                if intermediate_name and not os.environ.get(intermediate_name):
                    os.environ[intermediate_name] = primary_value
                    logger.info(f"Synchronized {intermediate_name} from {standard_name}")
                    
                if not os.environ.get(standard_name):
                    os.environ[standard_name] = primary_value
                    logger.info(f"Synchronized {standard_name} from source")
        
        # Special handling for Bluesky (already uses correct naming)
        bluesky_username = os.environ.get("PROVIDER_BLUESKY_USERNAME")
        bluesky_password = os.environ.get("PROVIDER_BLUESKY_PASSWORD")
        if bluesky_username and bluesky_password:
            logger.info("Bluesky credentials configured")
            
        logger.info("API key synchronization complete")
    except Exception as e:
        logger.error(f"Error synchronizing API keys: {str(e)}")

def ensure_model_env_vars():
    """
    Ensure that environment variables are properly set for all AI models.
    """
    try:
        # OpenAI API key synchronization
        openai_key = os.environ.get("OPENAI_API_KEY")
        
        if openai_key:
            # Ensure model-specific keys are set for OpenAI
            for model_key in ["OPENAI_API_KEY_GPT_3.5_TURBO", "OPENAI_API_KEY_GPT_4O", "OPENAI_API_KEY_GPT_4O_MINI"]:
                if not os.environ.get(model_key):
                    os.environ[model_key] = openai_key
                    logger.info(f"Set {model_key} from OPENAI_API_KEY")
                    
        # Anthropic API key synchronization
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
        
        if anthropic_key:
            # Ensure model-specific keys are set for Anthropic
            for model_key in ["ANTHROPIC_API_KEY_CLAUDE_3_7_SONNET_LATEST"]:
                if not os.environ.get(model_key):
                    os.environ[model_key] = anthropic_key
                    logger.info(f"Set {model_key} from ANTHROPIC_API_KEY")
                    
        # Log the configured keys (masked for security)
        for key, value in os.environ.items():
            if "_API_KEY" in key and value:
                masked_value = f"{value[:4]}...{value[-4:]}" if len(value) > 8 else "[SET]"
                logger.debug(f"API Key configured: {key}={masked_value}")
                
    except Exception as e:
        logger.error(f"Error ensuring model environment variables: {str(e)}") 