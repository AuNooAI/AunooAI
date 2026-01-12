"""FastAPI endpoint for provider configuration."""
import os
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any

from app.provider_config.registry import get_provider, list_providers

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/providers", tags=["providers"])


class ConfigureRequest(BaseModel):
    """Request body for configuring a provider."""
    provider: str
    credentials: dict[str, Any]


class ConfigureResponse(BaseModel):
    """Response body for successful configuration."""
    status: str = "success"


@router.post("/configure", response_model=ConfigureResponse)
async def configure_provider(request: ConfigureRequest) -> ConfigureResponse:
    """
    Validate and save credentials for a provider.
    
    Steps:
    1. Load matching provider module from registry
    2. Call validate(credentials)
    3. If validation passes → call configure(credentials)
    4. Return success
    
    If validation fails, credentials are NOT saved.
    """
    # Get provider module
    try:
        provider = get_provider(request.provider)
    except KeyError:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown provider: {request.provider}. Available: {list_providers()}"
        )

    # Validate credentials (raises HTTPException on failure)
    logger.info(f"Validating {request.provider} credentials...")
    await provider.validate(request.credentials)
    logger.info(f"Validation passed for {request.provider}")

    # Save credentials (only reached if validation passed)
    logger.info(f"Configuring {request.provider}...")
    await provider.configure(request.credentials)
    logger.info(f"Configuration complete for {request.provider}")

    return ConfigureResponse(status="success")


@router.get("/available_providers")
async def get_providers() -> dict[str, list[str]]:
    """List all available providers."""
    return {"providers": list_providers()}


@router.get("/debug_path")
async def debug_path() -> dict:
    """Debug: show the .env path that would be used."""
    from app.provider_config import bluesky
    env_path = os.path.abspath(os.path.join(os.path.dirname(bluesky.__file__), "..", "..", ".env"))
    return {
        "bluesky_module_file": bluesky.__file__,
        "calculated_env_path": env_path,
        "env_exists": os.path.exists(env_path),
        "cwd": os.getcwd()
    }

