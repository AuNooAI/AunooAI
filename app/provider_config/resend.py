"""Resend provider configuration."""
import os
import logging
import aiohttp
from fastapi import HTTPException

logger = logging.getLogger(__name__)

async def validate(credentials: dict) -> None:
    api_key = credentials.get("api_key")
    if not api_key:
        raise HTTPException(400, "api_key is required")

    payload = {
        "from": "Aunoo <test@invalid-domain-aunooai.com>",
        "to": ["nobody@example.com"],
        "subject": "test",
        "html": "test"
    }

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
        async with s.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload
        ) as r:
            if r.status == 401:
                raise HTTPException(400, "Invalid Resend API key")
            if r.status not in (400, 403, 202):
                raise HTTPException(400, "Resend validation failed")



async def configure(credentials: dict) -> None:
    """Save Resend API key to .env and environment."""
    api_key = credentials.get("api_key")
    env_var = "RESEND_API_KEY"
    env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

    logger.info(f"Resend configure: saving to {env_path}")

    try:
        with open(env_path, "r") as f:
            lines = f.readlines()
        logger.info(f"Resend configure: read {len(lines)} lines from .env")
    except FileNotFoundError:
        lines = []
        logger.warning(f"Resend configure: .env not found at {env_path}, creating new")

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

    logger.info(f"Resend configure: wrote {len(lines)} lines to .env")

    os.environ[env_var] = api_key
    logger.info("Resend configure: environment variable set")

