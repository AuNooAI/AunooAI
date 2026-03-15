"""Gemini provider configuration."""
import os
import logging
import aiohttp
from fastapi import HTTPException

logger = logging.getLogger(__name__)


async def validate(credentials: dict) -> None:
    """Validate Gemini API key by listing models."""
    api_key = credentials.get("api_key")
    if not api_key:
        logger.error("Gemini validation failed: api_key is required")
        raise HTTPException(status_code=400, detail="api_key is required")

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.get(
                f"https://generativelanguage.googleapis.com/v1/models?key={api_key}"
            ) as resp:
                if resp.status == 400:
                    error_data = await resp.json()
                    error_msg = error_data.get("error", {}).get("message", "")
                    if "API key" in error_msg:
                        logger.error("Gemini validation failed: Invalid Gemini API key")
                        raise HTTPException(status_code=400, detail="Invalid Gemini API key")
                    logger.error("Gemini validation failed: %s", error_msg or "Invalid Gemini API key")
                    raise HTTPException(status_code=400, detail=error_msg or "Invalid Gemini API key")
                elif resp.status != 200:
                    logger.error("Gemini validation failed: Invalid Gemini API key")
                    raise HTTPException(status_code=400, detail="Invalid Gemini API key")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Gemini validation failed: %s", str(e))
        raise HTTPException(status_code=400, detail=f"Gemini validation failed: {str(e)}")


async def configure(credentials: dict) -> None:
    """Save Gemini API key to .env and environment."""
    api_key = credentials.get("api_key")
    env_var = "GEMINI_API_KEY"
    env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

    logger.info(f"Gemini configure: saving to {env_path}")

    try:
        with open(env_path, "r") as f:
            lines = f.readlines()
        logger.info(f"Gemini configure: read {len(lines)} lines from .env")
    except FileNotFoundError:
        lines = []
        logger.warning(f"Gemini configure: .env not found at {env_path}, creating new")

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

    logger.info(f"Gemini configure: wrote {len(lines)} lines to .env")

    os.environ[env_var] = api_key
    logger.info("Gemini configure: environment variable set")

