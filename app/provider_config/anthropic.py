"""Anthropic provider configuration."""
import os
import logging
import aiohttp
from fastapi import HTTPException

logger = logging.getLogger(__name__)


async def validate(credentials: dict) -> None:
    """Validate Anthropic API key by making a minimal API call."""
    api_key = credentials.get("api_key")
    if not api_key:
        logger.error("Anthropic validation failed: api_key is required")
        raise HTTPException(status_code=400, detail="api_key is required")

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
            async with session.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "claude-3-haiku-20240307",
                    "max_tokens": 1,
                    "messages": [{"role": "user", "content": "hi"}]
                }
            ) as resp:
                if resp.status == 401:
                    logger.error("Anthropic validation failed: Invalid Anthropic API key")
                    raise HTTPException(status_code=400, detail="Invalid Anthropic API key")
                elif resp.status == 400:
                    error_data = await resp.json()
                    error_type = error_data.get("error", {}).get("type", "")
                    if "authentication" in error_type.lower() or "api_key" in error_type.lower():
                        logger.error("Anthropic validation failed: Invalid Anthropic API key")
                        raise HTTPException(status_code=400, detail="Invalid Anthropic API key")
                elif resp.status not in [200, 201]:
                    error_data = await resp.json()
                    error_msg = error_data.get("error", {}).get("message", "Invalid Anthropic API key")
                    logger.error("Anthropic validation failed: %s", error_msg)
                    raise HTTPException(status_code=400, detail=error_msg)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Anthropic validation failed: %s", str(e))
        raise HTTPException(status_code=400, detail=f"Anthropic validation failed: {str(e)}")


async def configure(credentials: dict) -> None:
    """Save Anthropic API key to .env and environment."""
    api_key = credentials.get("api_key")
    env_var = "ANTHROPIC_API_KEY"
    env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

    logger.info(f"Anthropic configure: saving to {env_path}")

    try:
        with open(env_path, "r") as f:
            lines = f.readlines()
        logger.info(f"Anthropic configure: read {len(lines)} lines from .env")
    except FileNotFoundError:
        lines = []
        logger.warning(f"Anthropic configure: .env not found at {env_path}, creating new")

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

    logger.info(f"Anthropic configure: wrote {len(lines)} lines to .env")

    os.environ[env_var] = api_key
    logger.info("Anthropic configure: environment variable set")

