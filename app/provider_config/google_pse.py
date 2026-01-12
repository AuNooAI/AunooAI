"""Google Programmable Search Engine provider configuration."""
import os
import logging
import aiohttp
from fastapi import HTTPException

logger = logging.getLogger(__name__)


async def validate(credentials: dict) -> None:
    """Validate Google PSE credentials by making a test search."""
    api_key = credentials.get("api_key")
    cse_id = credentials.get("cse_id")

    if not api_key:
        logger.error("Google PSE validation failed: api_key is required")
        raise HTTPException(status_code=400, detail="api_key is required")
    if not cse_id:
        logger.error("Google PSE validation failed: cse_id is required")
        raise HTTPException(status_code=400, detail="cse_id is required")

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.get(
                "https://www.googleapis.com/customsearch/v1",
                params={"key": api_key, "cx": cse_id, "q": "test", "num": 1}
            ) as resp:
                if resp.status == 400:
                    error_data = await resp.json()
                    error_msg = error_data.get("error", {}).get("message", "Invalid credentials")
                    logger.error("Google PSE validation failed: %s", error_msg)
                    raise HTTPException(status_code=400, detail=error_msg)
                elif resp.status == 403:
                    logger.error("Google PSE validation failed: Invalid Google API key or insufficient permissions")
                    raise HTTPException(status_code=400, detail="Invalid Google API key or insufficient permissions")
                elif resp.status != 200:
                    logger.error("Google PSE validation failed: Invalid Google PSE credentials")
                    raise HTTPException(status_code=400, detail="Invalid Google PSE credentials")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Google PSE validation failed: %s", str(e))
        raise HTTPException(status_code=400, detail=f"Google PSE validation failed: {str(e)}")


async def configure(credentials: dict) -> None:
    """Save Google PSE credentials to .env and environment."""
    api_key = credentials.get("api_key")
    cse_id = credentials.get("cse_id")

    api_key_var = "GOOGLE_API_KEY"
    cse_id_var = "GOOGLE_CSE_ID"
    env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

    logger.info(f"Google PSE configure: saving to {env_path}")

    try:
        with open(env_path, "r") as f:
            lines = f.readlines()
        logger.info(f"Google PSE configure: read {len(lines)} lines from .env")
    except FileNotFoundError:
        lines = []
        logger.warning(f"Google PSE configure: .env not found at {env_path}, creating new")

    api_key_line = f'{api_key_var}="{api_key}"\n'
    cse_id_line = f'{cse_id_var}="{cse_id}"\n'

    api_key_found = False
    cse_id_found = False

    for i, line in enumerate(lines):
        if line.startswith(f"{api_key_var}="):
            lines[i] = api_key_line
            api_key_found = True
        elif line.startswith(f"{cse_id_var}="):
            lines[i] = cse_id_line
            cse_id_found = True

    if not api_key_found:
        lines.append(api_key_line)
    if not cse_id_found:
        lines.append(cse_id_line)

    with open(env_path, "w") as f:
        f.writelines(lines)

    logger.info(f"Google PSE configure: wrote {len(lines)} lines to .env")

    os.environ[api_key_var] = api_key
    os.environ[cse_id_var] = cse_id
    logger.info("Google PSE configure: environment variables set")

