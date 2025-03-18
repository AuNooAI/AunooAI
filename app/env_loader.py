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
    """
    try:
        # Firecrawl API key synchronization
        firecrawl_key = os.environ.get("FIRECRAWL_API_KEY")
        provider_firecrawl_key = os.environ.get("PROVIDER_FIRECRAWL_KEY")
        
        if firecrawl_key and not provider_firecrawl_key:
            os.environ["PROVIDER_FIRECRAWL_KEY"] = firecrawl_key
            logger.info("Synchronized FIRECRAWL_API_KEY to PROVIDER_FIRECRAWL_KEY")
        elif provider_firecrawl_key and not firecrawl_key:
            os.environ["FIRECRAWL_API_KEY"] = provider_firecrawl_key
            logger.info("Synchronized PROVIDER_FIRECRAWL_KEY to FIRECRAWL_API_KEY")
            
        # NewsAPI key synchronization
        newsapi_key = os.environ.get("NEWSAPI_KEY")
        provider_newsapi_key = os.environ.get("PROVIDER_NEWSAPI_KEY")
        
        if newsapi_key and not provider_newsapi_key:
            os.environ["PROVIDER_NEWSAPI_KEY"] = newsapi_key
            logger.info("Synchronized NEWSAPI_KEY to PROVIDER_NEWSAPI_KEY")
        elif provider_newsapi_key and not newsapi_key:
            os.environ["NEWSAPI_KEY"] = provider_newsapi_key
            logger.info("Synchronized PROVIDER_NEWSAPI_KEY to NEWSAPI_KEY")
            
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