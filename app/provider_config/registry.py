"""Provider registry - maps provider names to their handler modules."""
from app.provider_config import (
    openai,
    anthropic,
    gemini,
    newsapi,
    thenewsapi,
    newsdata,
    firecrawl,
    elevenlabs,
    diatts,
    huggingface,
    bluesky,
    google_pse,
)

# Provider name → handler module mapping
PROVIDERS = {
    "openai": openai,
    "anthropic": anthropic,
    "gemini": gemini,
    "newsapi": newsapi,
    "thenewsapi": thenewsapi,
    "newsdata": newsdata,
    "firecrawl": firecrawl,
    "elevenlabs": elevenlabs,
    "diatts": diatts,
    "huggingface": huggingface,
    "bluesky": bluesky,
    "google_pse": google_pse,
}


def get_provider(name: str):
    """Get provider module by name.
    
    Args:
        name: Provider name (e.g., 'openai', 'anthropic')
        
    Returns:
        Provider module with validate() and configure() functions
        
    Raises:
        KeyError: If provider is not found
    """
    return PROVIDERS[name]


def list_providers() -> list[str]:
    """List all available provider names."""
    return list(PROVIDERS.keys())

