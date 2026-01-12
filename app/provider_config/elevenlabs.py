"""ElevenLabs provider configuration."""
import os
import logging
from fastapi import HTTPException

logger = logging.getLogger(__name__)


async def validate(credentials: dict) -> None:
    """Validate ElevenLabs API key using the SDK text-to-speech endpoint."""
    api_key = credentials.get("api_key")
    if not api_key:
        logger.error("ElevenLabs validation failed: api_key is required")
        raise HTTPException(status_code=400, detail="api_key is required")

    try:
        from elevenlabs import ElevenLabs
        
        api_key_trimmed = api_key.strip()
        client = ElevenLabs(api_key=api_key_trimmed)
        
        # Perform a minimal TTS request to validate the key
        audio = client.text_to_speech.convert(
            voice_id="EXAVITQu4vr4xnSDxMaL",  # Rachel (default voice)
            model_id="eleven_turbo_v2",
            text="Test"
        )
        next(audio)
        
        logger.info("ElevenLabs API key validated successfully via TTS")
    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e).lower()
        if "401" in error_msg or "unauthorized" in error_msg or "invalid" in error_msg:
            logger.error("ElevenLabs validation failed: Invalid ElevenLabs API key")
            raise HTTPException(status_code=400, detail="Invalid ElevenLabs API key")
        logger.error("ElevenLabs validation failed: %s", str(e))
        raise HTTPException(status_code=400, detail=f"ElevenLabs validation failed: {str(e)}")


async def configure(credentials: dict) -> None:
    """Save ElevenLabs API key to .env and environment."""
    api_key = credentials.get("api_key")
    primary_env_var = "ELEVENLABS_API_KEY"
    secondary_env_var = "PROVIDER_ELEVENLABS_API_KEY"
    env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

    logger.info(f"ElevenLabs configure: saving to {env_path}")

    try:
        with open(env_path, "r") as f:
            lines = f.readlines()
        logger.info(f"ElevenLabs configure: read {len(lines)} lines from .env")
    except FileNotFoundError:
        lines = []
        logger.warning(f"ElevenLabs configure: .env not found at {env_path}, creating new")

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

    logger.info(f"ElevenLabs configure: wrote {len(lines)} lines to .env")

    os.environ[primary_env_var] = api_key
    os.environ[secondary_env_var] = api_key
    logger.info("ElevenLabs configure: environment variables set")

