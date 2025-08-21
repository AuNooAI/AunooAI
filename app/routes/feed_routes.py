"""
Feed System API Routes

Provides REST API endpoints for the unified feed system including:
- Feed group management (CRUD operations)
- Source management for feed groups  
- Unified feed retrieval
- Feed item actions (hide, star)
"""

import json
import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel, Field

from app.database import get_database_instance, Database
from app.database_query_facade import DatabaseQueryFacade
from app.security.session import verify_session, verify_session_api
from app.services.feed_group_service import FeedGroupService
from app.services.unified_feed_service import UnifiedFeedService

# Configure logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["feeds"])

# Pydantic models for request/response validation
class CreateFeedGroupRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Name of the feed group")
    description: Optional[str] = Field(None, max_length=500, description="Optional description")
    color: Optional[str] = Field("#FF69B4", pattern=r"^#[0-9A-Fa-f]{6}$", description="Hex color code")

class UpdateFeedGroupRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="New name")
    description: Optional[str] = Field(None, max_length=500, description="New description")
    color: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$", description="New hex color code")
    is_active: Optional[bool] = Field(None, description="Active status")

class AddSourceRequest(BaseModel):
    source_type: str = Field(..., pattern=r"^(bluesky|arxiv|thenewsapi)$", 
                            description="Type of source")
    keywords: List[str] = Field(..., min_items=0, max_items=20, 
                               description="List of keywords for this source")
    enabled: Optional[bool] = Field(True, description="Enable this source")
    date_range_days: Optional[int] = Field(7, ge=1, le=365, 
                                          description="Number of days to search back (1-365)")
    custom_start_date: Optional[str] = Field(None, 
                                           description="Custom start date (ISO format)")
    custom_end_date: Optional[str] = Field(None,
                                         description="Custom end date (ISO format)")

class UpdateSourceRequest(BaseModel):
    keywords: Optional[List[str]] = Field(None, min_items=0, max_items=20, 
                                        description="Updated keywords list")
    enabled: Optional[bool] = Field(None, description="Enable/disable this source")
    date_range_days: Optional[int] = Field(None, ge=1, le=365,
                                          description="Number of days to search back (1-365)")
    custom_start_date: Optional[str] = Field(None,
                                           description="Custom start date (ISO format)")
    custom_end_date: Optional[str] = Field(None,
                                         description="Custom end date (ISO format)")

class FeedGroupResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    color: str
    is_active: bool
    created_at: str
    updated_at: str
    sources: List[Dict[str, Any]]

class FeedItemResponse(BaseModel):
    id: int
    source_type: str
    title: str
    content: Optional[str]
    author: Optional[str]
    author_handle: Optional[str]
    url: str
    publication_date: Optional[str]
    engagement_metrics: Dict[str, Any]
    tags: List[str]
    mentions: List[str]
    images: List[str]
    is_hidden: bool
    is_starred: bool
    created_at: str
    group_name: str
    group_color: str

class UnifiedFeedResponse(BaseModel):
    success: bool
    items: List[FeedItemResponse]
    total_count: int
    limit: int
    offset: int
    has_more: bool

# Feed Group Management Endpoints

@router.get("/feed-groups", response_model=List[FeedGroupResponse])
async def get_feed_groups(
    include_inactive: bool = Query(False, description="Include inactive groups"),
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session_api)
):
    """Get all feed keyword groups."""
    try:
        logger.info(f"API: Getting feed groups (include_inactive={include_inactive})")
        
        feed_service = FeedGroupService(db)
        groups = feed_service.get_feed_groups(include_inactive=include_inactive)
        
        logger.info(f"API: Retrieved {len(groups)} feed groups")
        return groups
        
    except Exception as e:
        logger.error(f"API: Error getting feed groups: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get feed groups: {str(e)}")

@router.post("/feed-groups", status_code=201)
async def create_feed_group(
    request: CreateFeedGroupRequest,
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session_api)
):
    """Create a new feed keyword group."""
    try:
        logger.info(f"API: Creating feed group '{request.name}'")
        
        feed_service = FeedGroupService(db)
        result = feed_service.create_feed_group(
            name=request.name,
            description=request.description,
            color=request.color
        )
        
        if not result["success"]:
            logger.warning(f"API: Failed to create feed group: {result['error']}")
            raise HTTPException(status_code=400, detail=result["error"])
        
        logger.info(f"API: Created feed group '{request.name}' with ID {result['group']['id']}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"API: Error creating feed group: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to create feed group: {str(e)}")

@router.get("/feed-groups/{group_id}", response_model=FeedGroupResponse)
async def get_feed_group(
    group_id: int,
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session_api)
):
    """Get a specific feed group by ID."""
    try:
        logger.info(f"API: Getting feed group {group_id}")
        
        feed_service = FeedGroupService(db)
        group = feed_service.get_feed_group(group_id)
        
        if not group:
            logger.warning(f"API: Feed group {group_id} not found")
            raise HTTPException(status_code=404, detail=f"Feed group {group_id} not found")
        
        logger.info(f"API: Retrieved feed group '{group['name']}'")
        return group
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"API: Error getting feed group {group_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get feed group: {str(e)}")

@router.put("/feed-groups/{group_id}")
async def update_feed_group(
    group_id: int,
    request: UpdateFeedGroupRequest,
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session_api)
):
    """Update a feed keyword group."""
    try:
        logger.info(f"API: Updating feed group {group_id}")
        
        feed_service = FeedGroupService(db)
        result = feed_service.update_feed_group(
            group_id=group_id,
            name=request.name,
            description=request.description,
            color=request.color,
            is_active=request.is_active
        )
        
        if not result["success"]:
            if "not found" in result["error"]:
                raise HTTPException(status_code=404, detail=result["error"])
            else:
                raise HTTPException(status_code=400, detail=result["error"])
        
        logger.info(f"API: Updated feed group {group_id}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"API: Error updating feed group {group_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to update feed group: {str(e)}")

@router.delete("/feed-groups/{group_id}")
async def delete_feed_group(
    group_id: int,
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session_api)
):
    """Delete a feed keyword group and all associated data."""
    try:
        logger.info(f"API: Deleting feed group {group_id}")
        
        feed_service = FeedGroupService(db)
        result = feed_service.delete_feed_group(group_id)
        
        if not result["success"]:
            if "not found" in result["error"]:
                raise HTTPException(status_code=404, detail=result["error"])
            else:
                raise HTTPException(status_code=400, detail=result["error"])
        
        logger.info(f"API: Deleted feed group {group_id}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"API: Error deleting feed group {group_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete feed group: {str(e)}")

# Source Management Endpoints

@router.get("/feed-groups/{group_id}/sources")
async def get_group_sources(
    group_id: int,
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session_api)
):
    """Get all sources for a specific feed group."""
    try:
        logger.info(f"API: Getting sources for group {group_id}")
        
        feed_service = FeedGroupService(db)
        group = feed_service.get_feed_group(group_id)
        
        if not group:
            logger.warning(f"API: Feed group {group_id} not found")
            raise HTTPException(status_code=404, detail=f"Feed group {group_id} not found")
        
        logger.info(f"API: Retrieved {len(group['sources'])} sources for group {group_id}")
        return {
            "success": True,
            "sources": group["sources"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"API: Error getting sources for group {group_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get sources: {str(e)}")

@router.post("/feed-groups/{group_id}/sources", status_code=201)
async def add_source_to_group(
    group_id: int,
    request: AddSourceRequest,
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session_api)
):
    """Add a source to a feed group."""
    try:
        logger.info(f"API: Adding {request.source_type} source to group {group_id}")
        
        feed_service = FeedGroupService(db)
        result = feed_service.add_source_to_group(
            group_id=group_id,
            source_type=request.source_type,
            keywords=request.keywords,
            enabled=request.enabled,
            date_range_days=request.date_range_days,
            custom_start_date=request.custom_start_date,
            custom_end_date=request.custom_end_date
        )
        
        if not result["success"]:
            if "not found" in result["error"]:
                raise HTTPException(status_code=404, detail=result["error"])
            else:
                raise HTTPException(status_code=400, detail=result["error"])
        
        logger.info(f"API: Added {request.source_type} source to group {group_id}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"API: Error adding source to group {group_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to add source: {str(e)}")

@router.put("/feed-groups/{group_id}/sources/{source_id}")
async def update_source(
    group_id: int,
    source_id: int,
    request: UpdateSourceRequest,
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session_api)
):
    """Update a source in a feed group."""
    try:
        logger.info(f"API: Updating source {source_id} in group {group_id}")
        
        feed_service = FeedGroupService(db)
        result = feed_service.update_source(
            source_id=source_id,
            keywords=request.keywords,
            enabled=request.enabled,
            date_range_days=request.date_range_days,
            custom_start_date=request.custom_start_date,
            custom_end_date=request.custom_end_date
        )
        
        if not result["success"]:
            if "not found" in result["error"]:
                raise HTTPException(status_code=404, detail=result["error"])
            else:
                raise HTTPException(status_code=400, detail=result["error"])
        
        logger.info(f"API: Updated source {source_id}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"API: Error updating source {source_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to update source: {str(e)}")

@router.delete("/feed-groups/{group_id}/sources/{source_id}")
async def delete_source(
    group_id: int,
    source_id: int,
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session_api)
):
    """Delete a source from a feed group."""
    try:
        logger.info(f"API: Deleting source {source_id} from group {group_id}")
        
        feed_service = FeedGroupService(db)
        result = feed_service.delete_source(source_id)
        
        if not result["success"]:
            if "not found" in result["error"]:
                raise HTTPException(status_code=404, detail=result["error"])
            else:
                raise HTTPException(status_code=400, detail=result["error"])
        
        logger.info(f"API: Deleted source {source_id}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"API: Error deleting source {source_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete source: {str(e)}")

# Feed Retrieval Endpoints

@router.get("/unified-feed", response_model=UnifiedFeedResponse)
async def get_unified_feed(
    limit: int = Query(50, ge=1, le=1000, description="Number of items to return"),
    offset: int = Query(0, ge=0, description="Number of items to skip"),
    group_ids: Optional[str] = Query(None, description="Comma-separated group IDs to filter by"),
    source_types: Optional[str] = Query(None, description="Comma-separated source types to filter by"),
    combination_sources: Optional[str] = Query(None, description="Comma-separated sources for combination filter (matches with combination_dates)"),
    combination_dates: Optional[str] = Query(None, description="Comma-separated date ranges for combination filter (matches with combination_sources)"),
    dateRange: Optional[str] = Query(None, description="Date range filter (today, week, month, quarter)"),
    search: Optional[str] = Query(None, description="Search in title and content"),
    author: Optional[str] = Query(None, description="Filter by author"),
    min_engagement: Optional[int] = Query(None, description="Minimum engagement score"),
    starred: Optional[str] = Query(None, description="Filter by starred status (starred/unstarred)"),
    topic: Optional[str] = Query(None, description="Filter by topic"),
    sort: Optional[str] = Query("publication_date", description="Sort by: publication_date, created_at, or engagement"),
    include_hidden: bool = Query(False, description="Include hidden items"),
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session_api)
):
    """Get unified feed from all active subscribed groups.
    Supports combination_sources and combination_dates for advanced filtering.
    All filters are applied server-side for better performance and accuracy.
    """
    try:
        logger.info(f"API: Getting unified feed (limit={limit}, offset={offset})")
        
        # Parse query parameters
        group_id_list = None
        if group_ids:
            try:
                group_id_list = [int(x.strip()) for x in group_ids.split(",") if x.strip()]
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid group_ids format")
        
        # Combination filter logic
        combination_source_list = None
        combination_date_list = None
        if combination_sources and combination_dates:
            combination_source_list = [x.strip() for x in combination_sources.split(",") if x.strip()]
            combination_date_list = [x.strip() for x in combination_dates.split(",") if x.strip()]
            if len(combination_source_list) != len(combination_date_list):
                raise HTTPException(status_code=400, detail="combination_sources and combination_dates must have the same length")
        else:
            combination_source_list = None
            combination_date_list = None
        
        source_type_list = None
        if source_types:
            source_type_list = [x.strip() for x in source_types.split(",") if x.strip()]
            # Validate source types
            valid_types = ["bluesky", "arxiv", "thenewsapi"]
            invalid_types = [t for t in source_type_list if t not in valid_types]
            if invalid_types:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Invalid source types: {invalid_types}. Valid types: {valid_types}"
                )
        
        feed_service = UnifiedFeedService(db)
        result = feed_service.get_unified_feed(
            limit=limit,
            offset=offset,
            group_ids=group_id_list,
            source_types=source_type_list,
            include_hidden=include_hidden,
            combination_sources=combination_source_list,
            combination_dates=combination_date_list,
            dateRange=dateRange,
            search=search,
            author=author,
            min_engagement=min_engagement,
            starred=starred,
            topic=topic,
            sort=sort
        )
        
        if not result["success"]:
            raise HTTPException(status_code=500, detail=result["error"])
        
        logger.info(f"API: Retrieved {len(result['items'])} feed items")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"API: Error getting unified feed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get unified feed: {str(e)}")

@router.get("/feed-groups/{group_id}/feed", response_model=UnifiedFeedResponse)
async def get_group_feed(
    group_id: int,
    limit: int = Query(50, ge=1, le=1000, description="Number of items to return"),
    offset: int = Query(0, ge=0, description="Number of items to skip"),
    source_types: Optional[str] = Query(None, description="Comma-separated source types to filter by"),
    combination_sources: Optional[str] = Query(None, description="Comma-separated sources for combination filter (matches with combination_dates)"),
    combination_dates: Optional[str] = Query(None, description="Comma-separated date ranges for combination filter (matches with combination_sources)"),
    dateRange: Optional[str] = Query(None, description="Date range filter (today, week, month, quarter)"),
    search: Optional[str] = Query(None, description="Search in title and content"),
    author: Optional[str] = Query(None, description="Filter by author"),
    min_engagement: Optional[int] = Query(None, description="Minimum engagement score"),
    starred: Optional[str] = Query(None, description="Filter by starred status (starred/unstarred)"),
    topic: Optional[str] = Query(None, description="Filter by topic"),
    sort: Optional[str] = Query("publication_date", description="Sort by: publication_date, created_at, or engagement"),
    include_hidden: bool = Query(False, description="Include hidden items"),
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session_api)
):
    """Get feed items for a specific group. Supports combination_sources and combination_dates for advanced filtering.
    All filters are applied server-side for better performance and accuracy."""
    try:
        logger.info(f"API: Getting feed for group {group_id}")
        
        # Combination filter logic
        combination_source_list = None
        combination_date_list = None
        if combination_sources and combination_dates:
            combination_source_list = [x.strip() for x in combination_sources.split(",") if x.strip()]
            combination_date_list = [x.strip() for x in combination_dates.split(",") if x.strip()]
            if len(combination_source_list) != len(combination_date_list):
                raise HTTPException(status_code=400, detail="combination_sources and combination_dates must have the same length")
        else:
            combination_source_list = None
            combination_date_list = None
        
        source_type_list = None
        if source_types:
            source_type_list = [x.strip() for x in source_types.split(",") if x.strip()]
        
        feed_service = UnifiedFeedService(db)
        result = feed_service.get_group_feed(
            group_id=group_id,
            limit=limit,
            offset=offset,
            source_types=source_type_list,
            include_hidden=include_hidden,
            combination_sources=combination_source_list,
            combination_dates=combination_date_list,
            dateRange=dateRange,
            search=search,
            author=author,
            min_engagement=min_engagement,
            starred=starred,
            topic=topic,
            sort=sort
        )
        
        if not result["success"]:
            raise HTTPException(status_code=500, detail=result["error"])
        
        logger.info(f"API: Retrieved {len(result['items'])} items for group {group_id}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"API: Error getting group feed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get group feed: {str(e)}")

# Feed Item Action Endpoints

@router.post("/feed-items/{item_id}/hide")
async def hide_feed_item(
    item_id: int,
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session_api)
):
    """Hide a specific feed item."""
    try:
        logger.info(f"API: Hiding feed item {item_id}")
        
        feed_service = UnifiedFeedService(db)
        result = feed_service.hide_feed_item(item_id)
        
        if not result["success"]:
            if "not found" in result["error"]:
                raise HTTPException(status_code=404, detail=result["error"])
            else:
                raise HTTPException(status_code=400, detail=result["error"])
        
        logger.info(f"API: Hidden feed item {item_id}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"API: Error hiding feed item {item_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to hide item: {str(e)}")

@router.post("/feed-items/{item_id}/star")
async def star_feed_item(
    item_id: int,
    starred: bool = Body(True, description="Whether to star or unstar the item"),
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session_api)
):
    """Star or unstar a specific feed item."""
    try:
        action = "star" if starred else "unstar"
        logger.info(f"API: {action}ring feed item {item_id}")
        
        feed_service = UnifiedFeedService(db)
        result = feed_service.star_feed_item(item_id, starred)
        
        if not result["success"]:
            if "not found" in result["error"]:
                raise HTTPException(status_code=404, detail=result["error"])
            else:
                raise HTTPException(status_code=400, detail=result["error"])
        
        logger.info(f"API: {result['action'].title()} feed item {item_id}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"API: Error starring feed item {item_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to star item: {str(e)}")

@router.post("/feed-items/{item_id}/tags")
async def add_tags_to_feed_item(
    item_id: int,
    tags_data: dict = Body(..., description="Tags data"),
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session_api)
):
    """Add tags to a feed item."""
    try:
        logger.info(f"API: Adding tags to feed item {item_id}")
        
        tags = tags_data.get("tags", [])
        if not tags or not isinstance(tags, list):
            raise HTTPException(status_code=400, detail="Tags must be provided as a list")
        
        # Clean and validate tags
        clean_tags = []
        for tag in tags:
            if isinstance(tag, str) and tag.strip():
                clean_tag = tag.strip()[:50]  # Limit tag length
                if clean_tag not in clean_tags:  # Avoid duplicates
                    clean_tags.append(clean_tag)
        
        if not clean_tags:
            raise HTTPException(status_code=400, detail="No valid tags provided")

        result = (DatabaseQueryFacade(db, logger)).get_feed_item_tags(item_id)

        if not result:
            raise HTTPException(status_code=404, detail="Feed item not found")

        # Get existing tags
        existing_tags_str = result[0] or ""
        existing_tags = []

        if existing_tags_str:
            try:
                existing_tags = json.loads(existing_tags_str) if existing_tags_str.startswith('[') else existing_tags_str.split(',')
            except (json.JSONDecodeError, AttributeError):
                existing_tags = existing_tags_str.split(',') if existing_tags_str else []

        # Combine with new tags (avoiding duplicates)
        all_tags = list(existing_tags)
        for tag in clean_tags:
            if tag not in all_tags:
                all_tags.append(tag)

        # Update database
        tags_json = json.dumps(all_tags)
        (DatabaseQueryFacade(db, logger)).update_feed_tags((tags_json, item_id))

        logger.info(f"API: Added tags {clean_tags} to feed item {item_id}")
        return {
            "success": True,
            "message": f"Added {len(clean_tags)} tags to item",
            "tags_added": clean_tags,
            "total_tags": len(all_tags)
        }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"API: Error adding tags to feed item: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to add tags: {str(e)}")

# Feed Collection Endpoint (for manual/scheduled collection)

@router.post("/feed-groups/{group_id}/collect")
async def collect_feed_items(
    group_id: int,
    max_items: int = Query(20, ge=1, le=100, description="Maximum items to collect per source"),
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session_api)
):
    """Manually trigger feed collection for a specific group."""
    try:
        logger.info(f"API: Manually collecting feed items for group {group_id}")
        
        feed_service = UnifiedFeedService(db)
        result = await feed_service.collect_feed_items_for_group(group_id, max_items)
        
        if not result["success"]:
            if "not found" in result["error"]:
                raise HTTPException(status_code=404, detail=result["error"])
            else:
                raise HTTPException(status_code=400, detail=result["error"])
        
        logger.info(f"API: Collected {result['items_collected']} items for group {group_id}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"API: Error collecting for group {group_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to collect items: {str(e)}")

@router.post("/feed-collection/collect-all")
async def collect_all_groups(
    max_items_per_group: int = Query(20, ge=1, le=100, description="Maximum items per group"),
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session_api)
):
    """Manually trigger feed collection for all active groups."""
    try:
        logger.info("API: Manually collecting feed items for all active groups")
        
        feed_service = UnifiedFeedService(db)
        result = await feed_service.collect_all_active_groups(max_items_per_group)
        
        if not result["success"]:
            raise HTTPException(status_code=500, detail=result["error"])
        
        logger.info(f"API: Collected {result['total_items_collected']} items across {result['groups_processed']} groups")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"API: Error collecting for all groups: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to collect items: {str(e)}")

@router.post("/feed-collection/collect")
async def collect_by_source(
    source_type: str = Query(..., pattern=r"^(bluesky|arxiv|thenewsapi)$", description="Source type to collect"),
    max_items: int = Query(20, ge=1, le=100, description="Maximum items to collect"),
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session_api)
):
    """Collect items for a specific source type across all active groups."""
    try:
        logger.info(f"API: Collecting {source_type} items across all groups")
        
        feed_service = UnifiedFeedService(db)
        
        # Collect from all active groups for this source type
        groups = (DatabaseQueryFacade(db, logger)).get_feed_keywords_by_source_type(source_type)
            
        if not groups:
            return {
                "success": True,
                "message": f"No active groups configured for {source_type}",
                "items_collected": 0
            }
        
        total_collected = 0
        
        for group_id, group_name in groups:
            try:
                result = await feed_service.collect_feed_items_for_group(group_id, max_items)
                if result["success"]:
                    total_collected += result.get("items_collected", 0)
                    logger.info(f"Collected {result.get('items_collected', 0)} items for group {group_name}")
            except Exception as e:
                logger.error(f"Error collecting for group {group_name}: {str(e)}")
                continue
        
        logger.info(f"API: Total collected {total_collected} {source_type} items")
        return {
            "success": True,
            "message": f"Collected {total_collected} {source_type} items from {len(groups)} groups",
            "items_collected": total_collected,
            "groups_processed": len(groups)
        }
        
    except Exception as e:
        logger.error(f"API: Error collecting {source_type} items: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to collect {source_type} items: {str(e)}")

# Stats endpoint
@router.get("/feed-groups/{group_id}/stats")
async def get_group_stats(
    group_id: int,
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session_api)
):
    """Get statistics for a specific feed group."""
    try:
        logger.info(f"API: Getting stats for group {group_id}")
        
        total_items, source_counts, recent_items = (DatabaseQueryFacade(db, logger)).get_statistics_for_specific_feed_group(group_id)
            
        stats = {
            "success": True,
            "group_id": group_id,
            "total_items": total_items,
            "recent_items": recent_items,
            "source_breakdown": source_counts
        }

        logger.info(f"API: Retrieved stats for group {group_id}: {total_items} items")
        return stats
            
    except Exception as e:
        logger.error(f"API: Error getting group stats: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get group stats: {str(e)}")

@router.get("/feed-items/{item_id}/enrichment")
async def get_feed_item_enrichment(
    item_id: int,
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session_api)
):
    """Get enrichment data for a specific feed item."""
    try:
        logger.info(f"API: Getting enrichment data for feed item {item_id}")
        
        result = (DatabaseQueryFacade(db, logger)).get_feed_item_url(item_id)

        if not result:
            raise HTTPException(status_code=404, detail="Feed item not found")

        item_url = result[0]

        enrichment_data = (DatabaseQueryFacade(db, logger)).get_enrichment_data_for_article(item_url)

        if not enrichment_data:
            return {
                "success": True,
                "enriched": False,
                "message": "No enrichment data found for this item"
            }

        # Parse the enrichment data
        (category, sentiment, driver_type, time_to_impact,
         topic_alignment_score, keyword_relevance_score, confidence_score,
         overall_match_explanation, extracted_article_topics,
         extracted_article_keywords, auto_ingested, ingest_status,
         quality_score, quality_issues, sentiment_explanation,
         future_signal, future_signal_explanation, driver_type_explanation,
         time_to_impact_explanation, summary, tags,
         submission_date, analyzed) = enrichment_data

        # Article is enriched if it has any non-null enrichment data
        # Check all the enrichment fields to see if any have meaningful data
        is_enriched = bool(
            category or sentiment or driver_type or time_to_impact or
            topic_alignment_score or keyword_relevance_score or confidence_score or
            overall_match_explanation or extracted_article_topics or
            extracted_article_keywords or quality_score or quality_issues or
            sentiment_explanation or future_signal or future_signal_explanation or
            driver_type_explanation or time_to_impact_explanation or
            (summary and summary.strip()) or (tags and tags.strip()) or
            analyzed == 1
        )

        logger.info(f"API: Enrichment check for {item_url}: category={category}, sentiment={sentiment}, analyzed={analyzed}, topic_alignment_score={topic_alignment_score}, quality_score={quality_score}, is_enriched={is_enriched}")
        logger.info(f"API: All enrichment data for {item_url}: {enrichment_data}")

        enrichment_result = {
            "success": True,
            "enriched": is_enriched,
            "data": {
                "category": category,
                "sentiment": sentiment,
                "sentiment_explanation": sentiment_explanation,
                "driver_type": driver_type,
                "driver_type_explanation": driver_type_explanation,
                "time_to_impact": time_to_impact,
                "time_to_impact_explanation": time_to_impact_explanation,
                "future_signal": future_signal,
                "future_signal_explanation": future_signal_explanation,
                "topic_alignment_score": topic_alignment_score,
                "keyword_relevance_score": keyword_relevance_score,
                "confidence_score": confidence_score,
                "overall_match_explanation": overall_match_explanation,
                "extracted_topics": extracted_article_topics,
                "extracted_keywords": extracted_article_keywords,
                "summary": summary,
                "tags": tags,
                "quality_score": quality_score,
                "quality_issues": quality_issues,
                "auto_ingested": bool(auto_ingested),
                "ingest_status": ingest_status,
                "submission_date": submission_date,
                "analyzed": bool(analyzed)
            }
        }

        logger.info(f"API: Retrieved enrichment data for item {item_id}: enriched={bool(category)}")
        return enrichment_result
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"API: Error getting enrichment data for item {item_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get enrichment data: {str(e)}")

@router.post("/feed-items/{item_id}/save-enriched")
async def save_enriched_feed_item(
    item_id: int,
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session_api)
):
    """Save an enriched feed item to the main articles database."""
    try:
        logger.info(f"API: Saving enriched feed item {item_id} to articles database")
        
        # Get the feed item details
        feed_item = (DatabaseQueryFacade(db, logger)).get_feed_item_details(item_id)

        if not feed_item:
            raise HTTPException(status_code=404, detail="Feed item not found")

        url, title, content, author, publication_date, source_type, group_id = feed_item

        # Get enrichment data from articles table
        enrichment_data = (DatabaseQueryFacade(db, logger)).get_enrichment_data_for_article_with_extra_fields(url)

        if not enrichment_data:
            # Create a basic article entry without enrichment
            article_id = (DatabaseQueryFacade(db, logger)).create_article_without_enrichment((url, title, content or '', source_type, publication_date))
            logger.info(f"API: Created basic article entry with ID {article_id}")

        else:
            # Check if article already exists with enrichment
            existing = (DatabaseQueryFacade(db, logger)).check_if_article_exists_with_enrichment(url)

            if existing:
                logger.info(f"API: Enriched article already exists with ID {existing[0]}")
                return {
                    "success": True,
                    "message": "Article already saved",
                    "article_id": existing[0],
                    "already_existed": True
                }

            # Update the existing article entry to mark as analyzed and ensure it's complete
            (category, sentiment, driver_type, time_to_impact,
             topic_alignment_score, keyword_relevance_score, confidence_score,
             overall_match_explanation, extracted_article_topics,
             extracted_article_keywords, auto_ingested, ingest_status,
             quality_score, quality_issues, sentiment_explanation,
             future_signal, future_signal_explanation, driver_type_explanation,
             time_to_impact_explanation, summary, tags, topic) = enrichment_data

            (DatabaseQueryFacade(db, logger)).update_feed_article_data((title, summary or content or '', source_type, publication_date, url))

            # Get the article ID
            article_id = (DatabaseQueryFacade(db, logger)).get_article_id_by_url(url)

            logger.info(f"API: Updated existing article with ID {article_id} as analyzed")
            
            return {
                "success": True,
                "message": "Article saved successfully to main database",
                "article_id": article_id,
                "enriched": bool(enrichment_data),
                "already_existed": False
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"API: Error saving enriched feed item {item_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to save enriched article: {str(e)}")

# Health check endpoint
@router.get("/feed-system/health")
async def feed_system_health(
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session_api)
):
    """Check the health of the feed system."""
    try:
        logger.info("API: Checking feed system health")
        
        # Check database connectivity
        group_count = (DatabaseQueryFacade(db, logger)).get_keyword_groups_count()

        item_count = (DatabaseQueryFacade(db, logger)).get_feed_item_count()
        
        # Check services
        feed_group_service = FeedGroupService(db)
        unified_feed_service = UnifiedFeedService(db)
        
        health_data = {
            "status": "healthy",
            "database": "connected",
            "feed_groups": group_count,
            "feed_items": item_count,
            "services": {
                "feed_group_service": "initialized",
                "unified_feed_service": "initialized",
                "arxiv_collector": "available" if unified_feed_service.arxiv_collector else "unavailable",
                "bluesky_collector": "available" if unified_feed_service.bluesky_collector else "unavailable"
            }
        }
        
        logger.info(f"API: Feed system health check completed - {group_count} groups, {item_count} items")
        return health_data
        
    except Exception as e:
        logger.error(f"API: Feed system health check failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}") 