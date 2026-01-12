"""Bluesky provider configuration."""
import os
import logging
from fastapi import HTTPException

logger = logging.getLogger(__name__)


async def validate(credentials: dict) -> None:
    """Validate Bluesky credentials by attempting login."""
    username = credentials.get("username")
    password = credentials.get("password")

    if not username:
        logger.error("Bluesky validation failed: username is required")
        raise HTTPException(status_code=400, detail="username is required")
    if not password:
        logger.error("Bluesky validation failed: password is required")
        raise HTTPException(status_code=400, detail="password is required")

    try:
        from atproto import Client
        client = Client()
        client.login(username, password)
    except Exception as e:
        logger.error("Bluesky validation failed: %s", str(e))
        raise HTTPException(status_code=400, detail=f"Bluesky authentication failed: {str(e)}")


async def configure(credentials: dict) -> None:
    """Save Bluesky credentials to .env and environment."""
    username = credentials.get("username")
    password = credentials.get("password")

    username_var = "PROVIDER_BLUESKY_USERNAME"
    password_var = "PROVIDER_BLUESKY_PASSWORD"
    # Use absolute path to ensure it works regardless of server's working directory
    env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
    
    logger.info(f"Bluesky configure: saving to {env_path}")

    try:
        with open(env_path, "r") as f:
            lines = f.readlines()
        logger.info(f"Bluesky configure: read {len(lines)} lines from .env")
    except FileNotFoundError:
        lines = []
        logger.warning(f"Bluesky configure: .env not found at {env_path}, creating new")

    username_line = f'{username_var}="{username}"\n'
    password_line = f'{password_var}="{password}"\n'

    username_found = False
    password_found = False

    for i, line in enumerate(lines):
        if line.startswith(f"{username_var}="):
            lines[i] = username_line
            username_found = True
        elif line.startswith(f"{password_var}="):
            lines[i] = password_line
            password_found = True

    if not username_found:
        lines.append(username_line)
    if not password_found:
        lines.append(password_line)

    with open(env_path, "w") as f:
        f.writelines(lines)
    
    logger.info(f"Bluesky configure: wrote {len(lines)} lines to .env")

    os.environ[username_var] = username
    os.environ[password_var] = password
    logger.info("Bluesky configure: environment variables set")

