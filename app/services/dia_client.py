"""Async wrapper around Dia TTS HTTP service."""
from __future__ import annotations

import os
import httpx
import logging
from typing import Optional

logger = logging.getLogger(__name__)

DIA_TTS_URL_ENV = "DIA_TTS_URL"
DIA_API_KEY_ENV = "DIA_API_KEY"


def _get_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    api_key = os.getenv(DIA_API_KEY_ENV)
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


async def tts(
    text: str,
    output_format: str = "mp3",
    speed_factor: Optional[float] = None,
    seed: Optional[int] = None,
    max_tokens: Optional[int] = None,
    audio_prompt: Optional[str] = None,
    url: Optional[str] = None,
) -> bytes:
    """Call Dia /v1/tts endpoint and return raw audio bytes.

    Args:
        text: Complete text with `[S1]`, `[S2]` tags.
        output_format: Audio format, e.g. `mp3`, `wav`.
        speed_factor: Optional speed factor for the TTS.
        seed: Optional seed for the TTS.
        max_tokens: Optional max tokens for the TTS.
        audio_prompt: Optional audio prompt for the TTS.
        url: Optional override for the base url.
            Defaults to env variable `DIA_TTS_URL` or the local
            `/v1/tts` endpoint on `http://localhost:8000`.
    """
    if not text.strip():
        raise ValueError("Empty text for Dia TTS")

    default_url = "http://localhost:8000/v1/tts"
    endpoint = url or os.getenv(DIA_TTS_URL_ENV, default_url)
    payload = {"text": text, "output_format": output_format}
    if speed_factor is not None:
        payload["speed_factor"] = speed_factor
    if seed is not None:
        payload["seed"] = seed
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    if audio_prompt is not None:
        # Assume `audio_prompt` is a base64 string or path handled by caller
        payload["audio_prompt"] = audio_prompt

    logger.debug(
        "Dia TTS call -> %s (chars=%d)",
        endpoint,
        len(text),
    )

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            endpoint,
            json=payload,
            headers=_get_headers(),
        )
        resp.raise_for_status()
        logger.debug(
            "Dia TTS returned %d bytes", len(resp.content)
        )
        return resp.content 