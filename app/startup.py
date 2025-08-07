import logging
import os
from app.env_loader import load_environment, ensure_model_env_vars
from utils.misc import masked_string
from crawlers import CrawlerFactory

logger = logging.getLogger(__name__)

def initialize_application():
    """
    Initialize the application at startup, loading environment variables
    and ensuring AI models are properly configured.
    """
    logger.info("Initializing application...")
    
    # Load environment variables
    env_path = load_environment()
    logger.info(f"Loaded environment variables from: {env_path}")
    
    # Ensure AI model variables are set
    ensure_model_env_vars()
    
    # Verify Firecrawl configuration
    verify_firecrawl_config()
    
    # Log available AI models and their configuration
    from app.ai_models import get_available_models
    available_models = get_available_models()
    
    if not available_models:
        logger.error("No AI models are configured! The application will have limited functionality.")
        logger.error("Please check your API keys in the .env file")
        
        # Debug: List environment variables
        logger.info("Available API keys:")
        for key, value in os.environ.items():
            if 'API_KEY' in key:
                masked = masked_string(value)
                logger.info(f"  {key}={masked}")
    else:
        logger.info("Successfully configured AI models:")
        for model in available_models:
            logger.info(f"  - {model['name']}")
    
    # Initialize crawler
    CrawlerFactory.get_crawler(logger=logger)
    
    return True

def verify_firecrawl_config():
    """
    Verify that Firecrawl API keys are properly configured
    """
    # TODO: MOVE TO A CONFIG VALIDATION CLASS
    try:
        firecrawl_key = os.environ.get("FIRECRAWL_API_KEY")
        provider_key = os.environ.get("PROVIDER_FIRECRAWL_KEY")
        
        if firecrawl_key or provider_key:
            key_to_use = provider_key or firecrawl_key
            masked = masked_string(key_to_use)
            logger.info(f"Firecrawl API key found: {masked}")
            
            # Set both environment variables to ensure consistency
            if firecrawl_key and not provider_key:
                os.environ["PROVIDER_FIRECRAWL_KEY"] = firecrawl_key
                logger.info("Set PROVIDER_FIRECRAWL_KEY from FIRECRAWL_API_KEY")
            elif provider_key and not firecrawl_key:
                os.environ["FIRECRAWL_API_KEY"] = provider_key
                logger.info("Set FIRECRAWL_API_KEY from PROVIDER_FIRECRAWL_KEY")
                
            return True
        else:
            logger.warning("No Firecrawl API keys found in environment variables")
            logger.warning("Article scraping functionality will be limited")
            return False
    except Exception as e:
        logger.error(f"Error verifying Firecrawl configuration: {str(e)}")
        return False
