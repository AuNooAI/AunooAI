import os
from dotenv import load_dotenv
from typing import Optional

# Load environment variables from .env file if it exists
load_dotenv()

class Settings:
    # Firecrawl settings
    @property
    def FIRECRAWL_API_KEY(self) -> Optional[str]:
        # Try both variants of the key name for maximum compatibility
        return os.getenv("FIRECRAWL_API_KEY") or os.getenv("PROVIDER_FIRECRAWL_KEY")
    
    # NewsAPI settings
    @property
    def NEWSAPI_KEY(self) -> Optional[str]:
        # Try both variants of the key name for maximum compatibility
        return os.getenv("NEWSAPI_KEY") or os.getenv("PROVIDER_NEWSAPI_KEY")
    
    # TheNewsAPI settings
    @property
    def THENEWSAPI_KEY(self) -> Optional[str]:
        # Try both variants of the key name for maximum compatibility
        return os.getenv("THENEWSAPI_KEY") or os.getenv("PROVIDER_THENEWSAPI_KEY")

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