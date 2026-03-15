"""Firecrawl provider configuration."""
import os
import logging
from fastapi import HTTPException

logger = logging.getLogger(__name__)


async def validate(credentials: dict) -> None:
    """Validate Firecrawl API key by scraping a test page."""
    api_key = credentials.get("api_key")
    if not api_key:
        logger.error("Firecrawl validation failed: api_key is required")
        raise HTTPException(status_code=400, detail="api_key is required")

    try:
        from firecrawl import Firecrawl
        firecrawl = Firecrawl(api_key=api_key)
        firecrawl.scrape("https://example.com", formats=["markdown"])
    except Exception as e:
        error_msg = str(e)
        if "401" in error_msg:
            logger.error("Firecrawl validation failed: Invalid Firecrawl API key")
            raise HTTPException(status_code=400, detail="Invalid Firecrawl API key")
        logger.error("Firecrawl validation failed: %s", error_msg)
        raise HTTPException(status_code=400, detail=f"Firecrawl validation failed: {error_msg}")


async def configure(credentials: dict) -> None:
    """Save Firecrawl API key to .env and environment."""
    api_key = credentials.get("api_key")
    primary_env_var = "PROVIDER_FIRECRAWL_KEY"
    secondary_env_var = "FIRECRAWL_API_KEY"
    env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

    logger.info(f"Firecrawl configure: saving to {env_path}")

    try:
        with open(env_path, "r") as f:
            lines = f.readlines()
        logger.info(f"Firecrawl configure: read {len(lines)} lines from .env")
    except FileNotFoundError:
        lines = []
        logger.warning(f"Firecrawl configure: .env not found at {env_path}, creating new")

    primary_line = f'{primary_env_var}="{api_key}"\n'
    secondary_line = f'{secondary_env_var}="{api_key}"\n'

    primary_found = False
    secondary_found = False

    for i, line in enumerate(lines):
        if line.startswith(f"{primary_env_var}="):
            lines[i] = primary_line
            primary_found = True
        elif line.startswith(f"{secondary_env_var}="):
            lines[i] = secondary_line
            secondary_found = True

    if not primary_found:
        lines.append(primary_line)
    if not secondary_found:
        lines.append(secondary_line)

    with open(env_path, "w") as f:
        f.writelines(lines)

    logger.info(f"Firecrawl configure: wrote {len(lines)} lines to .env")

    os.environ[primary_env_var] = api_key
    os.environ[secondary_env_var] = api_key
    logger.info("Firecrawl configure: environment variables set")

