"""NewsData.io provider configuration."""
import os
import logging
import aiohttp
from fastapi import HTTPException

logger = logging.getLogger(__name__)


async def validate(credentials: dict) -> None:
    """Validate NewsData.io API key by fetching latest news."""
    api_key = credentials.get("api_key")
    if not api_key:
        logger.error("NewsData.io validation failed: api_key is required")
        raise HTTPException(status_code=400, detail="api_key is required")

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.get(
                "https://newsdata.io/api/1/latest",
                params={"apikey": api_key, "country": "us", "size": 1}
            ) as resp:
                if resp.status != 200:
                    error_data = await resp.json()
                    error_msg = error_data.get("results", {}).get("message", "Invalid NewsData.io API key")
                    logger.error("NewsData.io validation failed: %s", error_msg)
                    raise HTTPException(status_code=400, detail=error_msg)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("NewsData.io validation failed: %s", str(e))
        raise HTTPException(status_code=400, detail=f"NewsData.io validation failed: {str(e)}")


async def configure(credentials: dict) -> None:
    """Save NewsData.io API key to .env and environment."""
    api_key = credentials.get("api_key")
    primary_env_var = "PROVIDER_NEWSDATA_API_KEY"
    secondary_env_var = "NEWSDATA_API_KEY"
    env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

    logger.info(f"NewsData configure: saving to {env_path}")

    try:
        with open(env_path, "r") as f:
            lines = f.readlines()
        logger.info(f"NewsData configure: read {len(lines)} lines from .env")
    except FileNotFoundError:
        lines = []
        logger.warning(f"NewsData configure: .env not found at {env_path}, creating new")

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

    logger.info(f"NewsData configure: wrote {len(lines)} lines to .env")

    os.environ[primary_env_var] = api_key
    os.environ[secondary_env_var] = api_key
    logger.info("NewsData configure: environment variables set")

