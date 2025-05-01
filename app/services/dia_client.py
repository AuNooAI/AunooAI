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


async def tts(text: str, output_format: str = "mp3", url: Optional[str] = None) -> bytes:
    """Call Dia /v1/tts endpoint and return raw audio bytes.

    Args:
        text: Complete text with `[S1]`, `[S2]` tags.
        output_format: Audio format, e.g. `mp3`, `wav`.
        url: Optional override for the base url.
            Defaults to env variable `DIA_TTS_URL` or the local
            `/v1/tts` endpoint on `http://localhost:8000`.
    """
    if not text.strip():
        raise ValueError("Empty text for Dia TTS")

    default_url = "http://localhost:8000/v1/tts"
    endpoint = url or os.getenv(DIA_TTS_URL_ENV, default_url)
    payload = {"text": text, "output_format": output_format}

    logger.debug(
        "Dia TTS call -> %s (chars=%d)",
        endpoint,
        len(text),
    )

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(endpoint, json=payload, headers=_get_headers())
        resp.raise_for_status()
        logger.debug(
            "Dia TTS returned %d bytes", len(resp.content)
        )
        return resp.content 