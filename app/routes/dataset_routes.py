"""Dataset API routes for media bias and other data enrichment sources."""

import os
import shutil
import tempfile
import logging
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse

from app.database import Database, get_database_instance
from app.models.media_bias import MediaBias

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/datasets",
    tags=["datasets"],
)

def get_media_bias(db: Database = Depends(get_database_instance)) -> MediaBias:
    """Dependency to get MediaBias instance."""
    return MediaBias(db)

@router.get("/media_bias")
async def get_media_bias_data(media_bias: MediaBias = Depends(get_media_bias)):
    """Get media bias data and status."""
    try:
        sources = media_bias.get_all_sources()
        status = media_bias.get_status()
        
        return JSONResponse(content={
            "sources": sources,
            "status": status
        })
    except Exception as e:
        logger.error(f"Error retrieving media bias data: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/media_bias/import")
async def import_media_bias(media_bias: MediaBias = Depends(get_media_bias)):
    """Import media bias data from the default CSV file."""
    try:
        # Define path to the default CSV file (included with the application)
        default_csv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 
                                       'data', 'mbfc_raw.csv')
        
        if not os.path.exists(default_csv_path):
            raise HTTPException(
                status_code=404, 
                detail=f"Default media bias CSV file not found at {default_csv_path}"
            )
        
        # Import data
        imported_count, failed_count = media_bias.import_from_csv(default_csv_path)
        
        return JSONResponse(content={
            "message": f"Successfully imported {imported_count} sources (failed: {failed_count})",
            "imported_count": imported_count,
            "failed_count": failed_count,
            "source_file": os.path.basename(default_csv_path)
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error importing media bias data: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/media_bias/upload")
async def upload_media_bias_file(
    file: UploadFile = File(...),
    media_bias: MediaBias = Depends(get_media_bias)
):
    """Upload and import a custom media bias CSV file."""
    if not file.filename.endswith('.csv'):
        raise HTTPException(
            status_code=400,
            detail="Only CSV files are supported"
        )
    
    temp_file = None
    try:
        # Save uploaded file to temp location
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.csv')
        shutil.copyfileobj(file.file, temp_file)
        temp_file.close()
        
        # Import from temp file
        imported_count, failed_count = media_bias.import_from_csv(temp_file.name)
        
        return JSONResponse(content={
            "message": f"Successfully imported {imported_count} sources (failed: {failed_count})",
            "imported_count": imported_count,
            "failed_count": failed_count,
            "source_file": file.filename
        })
    except Exception as e:
        logger.error(f"Error uploading and importing media bias file: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Clean up temp file
        if temp_file:
            try:
                os.unlink(temp_file.name)
            except Exception as e:
                logger.warning(f"Failed to delete temporary file {temp_file.name}: {str(e)}")

@router.post("/media_bias/enable")
async def enable_media_bias_enrichment(
    data: Dict[str, Any],
    media_bias: MediaBias = Depends(get_media_bias)
):
    """Enable or disable media bias enrichment."""
    try:
        enabled = data.get("enabled", False)
        success = media_bias.set_enabled(enabled)
        
        if not success:
            raise HTTPException(
                status_code=500,
                detail="Failed to update media bias enrichment setting"
            )
        
        return JSONResponse(content={
            "message": f"Media bias enrichment {'enabled' if enabled else 'disabled'}",
            "enabled": enabled
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting media bias enrichment: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/media_bias/reset")
async def reset_media_bias(media_bias: MediaBias = Depends(get_media_bias)):
    """Reset (delete) all media bias data."""
    try:
        success = media_bias.reset()
        
        if not success:
            raise HTTPException(
                status_code=500,
                detail="Failed to reset media bias data"
            )
        
        return JSONResponse(content={
            "message": "Media bias data has been reset",
            "success": True
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resetting media bias data: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/media_bias/source/{source}")
async def get_bias_for_source(
    source: str,
    media_bias: MediaBias = Depends(get_media_bias)
):
    """Get media bias data for a specific source."""
    try:
        bias_data = media_bias.get_bias_for_source(source)
        
        if not bias_data:
            return JSONResponse(content={
                "found": False,
                "message": f"No media bias data found for source: {source}"
            })
        
        return JSONResponse(content={
            "found": True,
            "data": bias_data
        })
    except Exception as e:
        logger.error(f"Error getting bias for source {source}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/media_bias/search")
async def search_media_bias(
    query: Optional[str] = None,
    bias: Optional[str] = None,
    factual: Optional[str] = None,
    country: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
    media_bias: MediaBias = Depends(get_media_bias)
):
    """Search and filter media bias sources."""
    try:
        sources, total_count = media_bias.search_sources(
            query=query,
            bias_filter=bias,
            factual_filter=factual,
            country_filter=country,
            page=page,
            per_page=per_page
        )
        
        return JSONResponse(content={
            "sources": sources,
            "total": total_count,
            "page": page,
            "per_page": per_page,
            "total_pages": (total_count + per_page - 1) // per_page
        })
    except Exception as e:
        logger.error(f"Error searching media bias sources: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/media_bias/filters")
async def get_media_bias_filters(media_bias: MediaBias = Depends(get_media_bias)):
    """Get filter options for media bias data."""
    try:
        filters = media_bias.get_filter_options()
        return JSONResponse(content=filters)
    except Exception as e:
        logger.error(f"Error getting media bias filters: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/media_bias/by-id/{source_id}")
async def get_media_bias_by_id(
    source_id: int,
    media_bias: MediaBias = Depends(get_media_bias)
):
    """Get media bias source by ID."""
    try:
        source = media_bias.get_source_by_id(source_id)
        if not source:
            raise HTTPException(
                status_code=404,
                detail=f"Media bias source with ID {source_id} not found"
            )
            
        return JSONResponse(content=source)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting media bias source by ID: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/media_bias/add")
async def add_media_bias_source(
    source_data: Dict[str, Any],
    media_bias: MediaBias = Depends(get_media_bias)
):
    """Add a new media bias source."""
    try:
        source_id = media_bias.add_source(source_data)
        return JSONResponse(content={
            "message": "Media bias source added successfully",
            "id": source_id
        })
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Error adding media bias source: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/media_bias/{source_id}")
async def update_media_bias_source(
    source_id: int,
    source_data: Dict[str, Any],
    media_bias: MediaBias = Depends(get_media_bias)
):
    """Update an existing media bias source."""
    try:
        success = media_bias.update_source(source_id, source_data)
        return JSONResponse(content={
            "message": "Media bias source updated successfully",
            "success": success
        })
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Error updating media bias source: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/media_bias/{source_id}")
async def delete_media_bias_source(
    source_id: int,
    media_bias: MediaBias = Depends(get_media_bias)
):
    """Delete a media bias source."""
    try:
        success = media_bias.delete_source(source_id)
        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Media bias source with ID {source_id} not found"
            )
            
        return JSONResponse(content={
            "message": "Media bias source deleted successfully"
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting media bias source: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 