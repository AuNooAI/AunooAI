import os
import logging
from typing import Optional
from app.env_loader import load_environment

# Configure logging
logger = logging.getLogger(__name__)

# Load environment variables using the centralized loader
load_environment()


class Settings:
    # Firecrawl settings
    @property
    def FIRECRAWL_API_KEY(self) -> Optional[str]:
        # Try both variants of the key name for maximum compatibility
        provider_key = os.getenv("PROVIDER_FIRECRAWL_KEY")
        direct_key = os.getenv("FIRECRAWL_API_KEY")
        
        if provider_key:
            logger.info("Using PROVIDER_FIRECRAWL_KEY from environment")
            return provider_key
        elif direct_key:
            logger.info("Using FIRECRAWL_API_KEY from environment")
            return direct_key
        else:
            logger.warning("No Firecrawl API key found in environment variables")
            return None
    
    # NewsAPI settings
    @property
    def NEWSAPI_KEY(self) -> Optional[str]:
        # Try both variants of the key name for maximum compatibility
        return os.getenv("NEWSAPI_KEY") or os.getenv("PROVIDER_NEWSAPI_KEY")
    
    # TheNewsAPI settings
    @property
    def THENEWSAPI_KEY(self) -> Optional[str]:
        # Try both variants of the key name for maximum compatibility
        return (os.getenv("THENEWSAPI_KEY") or 
                os.getenv("PROVIDER_THENEWSAPI_KEY"))

    # Get OpenAI API key
    @property
    def OPENAI_API_KEY(self) -> Optional[str]:
        return os.getenv("OPENAI_API_KEY")
        
    # Get Anthropic API key
    @property 
    def ANTHROPIC_API_KEY(self) -> Optional[str]:
        return os.getenv("ANTHROPIC_API_KEY")
    
    # Get HuggingFace API key
    @property
    def HUGGINGFACE_API_KEY(self) -> Optional[str]:
        return os.getenv("HUGGINGFACE_API_KEY")
    
    # Get Gemini API key
    @property
    def GEMINI_API_KEY(self) -> Optional[str]:
        return os.getenv("GEMINI_API_KEY")


settings = Settings() 