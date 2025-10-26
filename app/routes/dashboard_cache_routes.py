"""Routes for dashboard caching and export functionality."""

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import FileResponse, Response
from typing import Optional
import logging
import tempfile
import json
from pathlib import Path

from app.database import Database, get_database_instance
from app.services.dashboard_cache_service import DashboardCacheService
from app.services.dashboard_export_service import DashboardExportService

router = APIRouter(prefix="/api/dashboard-cache", tags=["dashboard-cache"])
logger = logging.getLogger(__name__)


# =============================================================================
# Save Dashboard Endpoint
# =============================================================================

@router.post("/save")
async def save_dashboard(
    request: Request,
    db: Database = Depends(get_database_instance)
):
    """Save a dashboard to cache.

    Request body should contain:
    - dashboard_type: str (e.g., 'news_feed', 'six_articles')
    - date_range: str (e.g., '24h', '7d')
    - content: dict (dashboard content)
    - topic: Optional[str]
    - persona: Optional[str]
    - profile_id: Optional[int]
    - metadata: Optional[dict] with article_count, model_used, generation_time_seconds
    """
    try:
        data = await request.json()

        # Validate required fields
        dashboard_type = data.get('dashboard_type')
        date_range = data.get('date_range')
        content = data.get('content')

        if not all([dashboard_type, date_range, content]):
            raise HTTPException(
                status_code=400,
                detail="Missing required fields: dashboard_type, date_range, content"
            )

        # Optional fields
        topic = data.get('topic')
        persona = data.get('persona')
        profile_id = data.get('profile_id')
        metadata = data.get('metadata', {})

        # Create service and save
        cache_service = DashboardCacheService(db)

        cache_key = await cache_service.save_dashboard(
            dashboard_type=dashboard_type,
            date_range=date_range,
            content=content,
            topic=topic,
            persona=persona,
            profile_id=profile_id,
            metadata=metadata
        )

        return {
            "success": True,
            "cache_key": cache_key,
            "message": "Dashboard saved successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving dashboard: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save dashboard: {str(e)}")


# =============================================================================
# Get Dashboard Endpoint
# =============================================================================

@router.get("/get/{cache_key}")
async def get_dashboard(
    cache_key: str,
    db: Database = Depends(get_database_instance)
):
    """Retrieve a cached dashboard by cache key."""
    try:
        cache_service = DashboardCacheService(db)
        dashboard = await cache_service.get_dashboard(cache_key)

        if not dashboard:
            raise HTTPException(status_code=404, detail="Dashboard not found")

        return {
            "success": True,
            "dashboard": dashboard
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving dashboard: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve dashboard: {str(e)}")


# =============================================================================
# List Dashboards Endpoint
# =============================================================================

@router.get("/list")
async def list_dashboards(
    limit: int = 20,
    db: Database = Depends(get_database_instance)
):
    """List all cached dashboards, most recently accessed first."""
    try:
        cache_service = DashboardCacheService(db)
        dashboards = await cache_service.list_cached_dashboards(limit=limit)

        return {
            "success": True,
            "dashboards": dashboards,
            "count": len(dashboards)
        }

    except Exception as e:
        logger.error(f"Error listing dashboards: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list dashboards: {str(e)}")


# =============================================================================
# Delete Dashboard Endpoint
# =============================================================================

@router.delete("/delete/{cache_key}")
async def delete_dashboard(
    cache_key: str,
    db: Database = Depends(get_database_instance)
):
    """Delete a cached dashboard."""
    try:
        cache_service = DashboardCacheService(db)
        deleted = await cache_service.delete_dashboard(cache_key)

        if not deleted:
            raise HTTPException(status_code=404, detail="Dashboard not found")

        return {
            "success": True,
            "message": "Dashboard deleted successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting dashboard: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete dashboard: {str(e)}")


# =============================================================================
# Export Endpoints
# =============================================================================

@router.post("/export/markdown")
async def export_dashboard_markdown(
    request: Request,
    db: Database = Depends(get_database_instance)
):
    """Export a dashboard to Markdown format.

    Request body should contain:
    - cache_key: str (optional, if retrieving from cache)
    - dashboard_data: dict (optional, if providing data directly)
    - dashboard_type: str
    - include_metadata: bool (default: true)
    """
    try:
        data = await request.json()

        # Get dashboard data (either from cache or direct)
        cache_key = data.get('cache_key')
        dashboard_data = data.get('dashboard_data')
        dashboard_type = data.get('dashboard_type')
        include_metadata = data.get('include_metadata', True)

        if cache_key:
            # Retrieve from cache
            cache_service = DashboardCacheService(db)
            cached = await cache_service.get_dashboard(cache_key)
            if not cached:
                raise HTTPException(status_code=404, detail="Dashboard not found")
            dashboard_data = cached
            dashboard_type = cached.get('dashboard_type')

        if not dashboard_data or not dashboard_type:
            raise HTTPException(
                status_code=400,
                detail="Must provide either cache_key or (dashboard_data + dashboard_type)"
            )

        # Export to Markdown
        markdown_content = DashboardExportService.export_to_markdown(
            dashboard_data=dashboard_data,
            dashboard_type=dashboard_type,
            include_metadata=include_metadata
        )

        # Return as downloadable file
        return Response(
            content=markdown_content,
            media_type="text/markdown",
            headers={
                "Content-Disposition": f"attachment; filename=dashboard_{dashboard_type}.md"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting to Markdown: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to export to Markdown: {str(e)}")


@router.post("/export/pdf")
async def export_dashboard_pdf(
    request: Request,
    db: Database = Depends(get_database_instance)
):
    """Export a dashboard to PDF format.

    Request body should contain:
    - cache_key: str (optional, if retrieving from cache)
    - dashboard_data: dict (optional, if providing data directly)
    - dashboard_type: str
    """
    try:
        data = await request.json()

        # Get dashboard data
        cache_key = data.get('cache_key')
        dashboard_data = data.get('dashboard_data')
        dashboard_type = data.get('dashboard_type')

        if cache_key:
            cache_service = DashboardCacheService(db)
            cached = await cache_service.get_dashboard(cache_key)
            if not cached:
                raise HTTPException(status_code=404, detail="Dashboard not found")
            dashboard_data = cached
            dashboard_type = cached.get('dashboard_type')

        if not dashboard_data or not dashboard_type:
            raise HTTPException(
                status_code=400,
                detail="Must provide either cache_key or (dashboard_data + dashboard_type)"
            )

        # Export to PDF
        pdf_path = DashboardExportService.export_to_pdf(
            dashboard_data=dashboard_data,
            dashboard_type=dashboard_type
        )

        # Return as downloadable file
        return FileResponse(
            pdf_path,
            media_type="application/pdf",
            filename=f"dashboard_{dashboard_type}.pdf",
            headers={
                "Content-Disposition": f"attachment; filename=dashboard_{dashboard_type}.pdf"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting to PDF: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to export to PDF: {str(e)}")


@router.post("/export/image")
async def export_dashboard_image(
    request: Request,
    db: Database = Depends(get_database_instance)
):
    """Export a dashboard to PNG image format.

    Request body should contain:
    - cache_key: str (optional, if retrieving from cache)
    - dashboard_data: dict (optional, if providing data directly)
    - dashboard_type: str
    - width: int (default: 1200)
    - height: int (default: 800)
    """
    try:
        data = await request.json()

        # Get dashboard data
        cache_key = data.get('cache_key')
        dashboard_data = data.get('dashboard_data')
        dashboard_type = data.get('dashboard_type')
        width = data.get('width', 1200)
        height = data.get('height', 800)

        if cache_key:
            cache_service = DashboardCacheService(db)
            cached = await cache_service.get_dashboard(cache_key)
            if not cached:
                raise HTTPException(status_code=404, detail="Dashboard not found")
            dashboard_data = cached
            dashboard_type = cached.get('dashboard_type')

        if not dashboard_data or not dashboard_type:
            raise HTTPException(
                status_code=400,
                detail="Must provide either cache_key or (dashboard_data + dashboard_type)"
            )

        # Export to image
        image_path = await DashboardExportService.export_to_image(
            dashboard_data=dashboard_data,
            dashboard_type=dashboard_type,
            width=width,
            height=height
        )

        # Return as downloadable file
        return FileResponse(
            image_path,
            media_type="image/png",
            filename=f"dashboard_{dashboard_type}.png",
            headers={
                "Content-Disposition": f"attachment; filename=dashboard_{dashboard_type}.png"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting to image: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to export to image: {str(e)}")
