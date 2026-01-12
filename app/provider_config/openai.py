"""OpenAI provider configuration."""
import os
import logging
import aiohttp
from fastapi import HTTPException

logger = logging.getLogger(__name__)


async def validate(credentials: dict) -> None:
    """Validate OpenAI API key by listing models."""
    api_key = credentials.get("api_key")
    if not api_key:
        logger.error("OpenAI validation failed: api_key is required")
        raise HTTPException(status_code=400, detail="api_key is required")

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"}
            ) as resp:
                if resp.status == 401:
                    logger.error("OpenAI validation failed: Invalid OpenAI API key")
                    raise HTTPException(status_code=400, detail="Invalid OpenAI API key")
                elif resp.status != 200:
                    error_data = await resp.json()
                    error_msg = error_data.get("error", {}).get("message", "Invalid OpenAI API key")
                    logger.error("OpenAI validation failed: %s", error_msg)
                    raise HTTPException(status_code=400, detail=error_msg)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("OpenAI validation failed: %s", str(e))
        raise HTTPException(status_code=400, detail=f"OpenAI validation failed: {str(e)}")


async def configure(credentials: dict) -> None:
    """Save OpenAI API key to .env and environment."""
    api_key = credentials.get("api_key")
    env_var = "OPENAI_API_KEY"
    env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

    logger.info(f"OpenAI configure: saving to {env_path}")

    try:
        with open(env_path, "r") as f:
            lines = f.readlines()
        logger.info(f"OpenAI configure: read {len(lines)} lines from .env")
    except FileNotFoundError:
        lines = []
        logger.warning(f"OpenAI configure: .env not found at {env_path}, creating new")

    key_line = f'{env_var}="{api_key}"\n'
    key_found = False

    for i, line in enumerate(lines):
        if line.startswith(f"{env_var}="):
            lines[i] = key_line
            key_found = True
            break

    if not key_found:
        lines.append(key_line)

    with open(env_path, "w") as f:
        f.writelines(lines)

    logger.info(f"OpenAI configure: wrote {len(lines)} lines to .env")

    os.environ[env_var] = api_key
    logger.info("OpenAI configure: environment variable set")

