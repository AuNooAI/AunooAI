#!/usr/bin/env python3
"""Media bias API routes."""

import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from app.database import get_database_instance, Database
from app.models.media_bias import MediaBias
from app.security.session import verify_session

# Set up router
router = APIRouter(
    prefix="/api/media_bias",
    tags=["media_bias"]
)

# Configure logging
logger = logging.getLogger(__name__)


class MediaBiasStatus(BaseModel):
    """Media bias status model."""
    
    enabled: bool
    total_sources: int
    last_updated: Optional[str] = None


class MediaBiasResponse(BaseModel):
    """Media bias response model."""
    
    success: bool
    data: Optional[Dict[str, Any]] = None
    message: str = ""


@router.get("", response_model=MediaBiasResponse)
async def get_media_bias(
    source: str = Query(..., description="The news source to get bias data for"),
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session)
):
    """Get media bias data for a source."""
    try:
        logger.debug(f"Getting media bias data for source: {source}")
        
        # Create MediaBias instance
        media_bias = MediaBias(db)
        
        # Get bias data
        bias_data = media_bias.get_bias_for_source(source)
        
        if bias_data:
            return MediaBiasResponse(
                success=True,
                data=bias_data,
                message=f"Found bias data for {source}"
            )
        else:
            return MediaBiasResponse(
                success=False,
                message=f"No bias data found for {source}"
            )
            
    except Exception as e:
        logger.error(f"Error getting media bias data: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error getting media bias data: {str(e)}"
        )


@router.get("/status", response_model=MediaBiasStatus)
async def get_media_bias_status(db: Database = Depends(get_database_instance), session=Depends(verify_session)):
    """Get media bias system status."""
    try:
        # Create MediaBias instance
        media_bias = MediaBias(db)
        
        # Get status
        status = media_bias.get_status()
        
        return MediaBiasStatus(
            enabled=status.get("enabled", False),
            total_sources=status.get("total_sources", 0),
            last_updated=status.get("last_updated")
        )
        
    except Exception as e:
        logger.error(f"Error getting media bias status: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error getting media bias status: {str(e)}"
        )


@router.post("/enable", response_model=MediaBiasStatus)
async def enable_media_bias(db: Database = Depends(get_database_instance), session=Depends(verify_session)):
    """Enable media bias enrichment."""
    try:
        # Create MediaBias instance
        media_bias = MediaBias(db)
        
        # Enable media bias
        media_bias.set_enabled(True)
        
        # Get updated status
        status = media_bias.get_status()
        
        return MediaBiasStatus(
            enabled=status.get("enabled", False),
            total_sources=status.get("total_sources", 0),
            last_updated=status.get("last_updated")
        )
        
    except Exception as e:
        logger.error(f"Error enabling media bias: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error enabling media bias: {str(e)}"
        )


@router.post("/disable", response_model=MediaBiasStatus)
async def disable_media_bias(db: Database = Depends(get_database_instance), session=Depends(verify_session)):
    """Disable media bias enrichment."""
    try:
        # Create MediaBias instance
        media_bias = MediaBias(db)
        
        # Disable media bias
        media_bias.set_enabled(False)
        
        # Get updated status
        status = media_bias.get_status()
        
        return MediaBiasStatus(
            enabled=status.get("enabled", False),
            total_sources=status.get("total_sources", 0),
            last_updated=status.get("last_updated")
        )
        
    except Exception as e:
        logger.error(f"Error disabling media bias: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error disabling media bias: {str(e)}"
        ) 