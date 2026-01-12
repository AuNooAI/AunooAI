"""Dia TTS provider configuration."""
import os
import logging
import aiohttp
from fastapi import HTTPException

logger = logging.getLogger(__name__)

""" 
At present, we are not using the Dia TTS provider.
If you want to use it, you can implement the validation and configuration functions below.
"""
async def validate(credentials: dict) -> None:
    pass

async def configure(credentials: dict) -> None:
    pass
