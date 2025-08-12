"""
Feed Group Service

Manages feed keyword groups and their sources for the unified feed system.
Handles CRUD operations, source management, and feed group subscriptions.
"""

import json
import logging
import sqlite3
from datetime import datetime
from typing import List, Dict, Optional, Any
from dataclasses import dataclass

from app.database import Database
from app.database_query_facade import DatabaseQueryFacade

# Configure logging
logger = logging.getLogger(__name__)

@dataclass
class FeedGroup:
    """Data class for feed keyword groups."""
    id: Optional[int] = None
    name: str = ""
    description: Optional[str] = None
    color: str = "#FF69B4"
    is_active: bool = True
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

@dataclass
class FeedGroupSource:
    """Data class for feed group sources."""
    id: Optional[int] = None
    group_id: int = 0
    source_type: str = ""  # 'bluesky', or 'arxiv
    keywords: List[str] = None
    enabled: bool = True
    last_checked: Optional[str] = None
    created_at: Optional[str] = None

    def __post_init__(self):
        if self.keywords is None:
            self.keywords = []

class FeedGroupService:
    """Service for managing feed keyword groups."""

    def __init__(self, db: Database = None):
        """Initialize the service with database connection."""
        self.db = db or Database()
        logger.info("FeedGroupService initialized")

    def create_feed_group(self, name: str, description: str = None, color: str = "#FF69B4") -> Dict[str, Any]:
        """
        Create a new feed keyword group.
        
        Args:
            name: Name of the feed group
            description: Optional description
            color: Color for the group (hex code)
            
        Returns:
            Dictionary with success status and group data
        """
        try:
            logger.info(f"Creating feed group: {name}")
            
            if (DatabaseQueryFacade(db, logger)).get_feed_group_by_name(name):
                logger.warning(f"Feed group '{name}' already exists")
                return {
                    "success": False,
                    "error": f"Feed group '{name}' already exists"
                }

            # Create the group
            now = datetime.now().isoformat()
            group_id = (DatabaseQueryFacade(db, logger)).create_feed_group((name, description, color, now, now))

            # Create default subscription for the user
            (DatabaseQueryFacade(db, logger)).create_default_feed_subscription(group_id)

            logger.info(f"Created feed group '{name}' with ID {group_id}")

            return {
                "success": True,
                "group": {
                    "id": group_id,
                    "name": name,
                    "description": description,
                    "color": color,
                    "is_active": True,
                    "created_at": now
                }
            }
                
        except Exception as e:
            logger.error(f"Error creating feed group '{name}': {str(e)}")
            return {
                "success": False,
                "error": f"Failed to create feed group: {str(e)}"
            }

    def get_feed_groups(self, include_inactive: bool = False) -> List[Dict[str, Any]]:
        """
        Get all feed keyword groups.
        
        Args:
            include_inactive: Whether to include inactive groups
            
        Returns:
            List of feed groups with their sources
        """
        try:
            logger.info(f"Fetching feed groups (include_inactive={include_inactive})")
            
            # Build query based on active status
            if include_inactive:
                groups = (DatabaseQueryFacade(db, logger)).get_feed_groups_including_inactive()
            else:
                groups = (DatabaseQueryFacade(db, logger)).get_feed_groups_excluding_inactive()

            result = []
            for group in groups:
                group_dict = {
                    "id": group[0],
                    "name": group[1],
                    "description": group[2],
                    "color": group[3],
                    "is_active": bool(group[4]),
                    "created_at": group[5],
                    "updated_at": group[6]
                }

                # Get sources for this group
                sources = []
                for source in (DatabaseQueryFacade(db, logger)).get_feed_group_sources(group[0]):
                    try:
                        keywords = json.loads(source[2]) if source[2] else []
                    except json.JSONDecodeError:
                        keywords = []

                    sources.append({
                        "id": source[0],
                        "source_type": source[1],
                        "keywords": keywords,
                        "enabled": bool(source[3]),
                        "last_checked": source[4],
                        "created_at": source[5]
                    })

                group_dict["sources"] = sources
                result.append(group_dict)

            logger.info(f"Retrieved {len(result)} feed groups")
            return result
                
        except Exception as e:
            logger.error(f"Error fetching feed groups: {str(e)}")
            return []

    def get_feed_group(self, group_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a specific feed group by ID.
        
        Args:
            group_id: ID of the feed group
            
        Returns:
            Feed group data or None if not found
        """
        try:
            logger.info(f"Fetching feed group with ID {group_id}")
            
            group = (DatabaseQueryFacade(db, logger)).get_feed_group_by_id(group_id)
            if not group:
                logger.warning(f"Feed group with ID {group_id} not found")
                return None

            group_dict = {
                "id": group[0],
                "name": group[1],
                "description": group[2],
                "color": group[3],
                "is_active": bool(group[4]),
                "created_at": group[5],
                "updated_at": group[6]
            }

            # Get sources for this group
            sources = []
            for source in  (DatabaseQueryFacade(db, logger)).get_feed_group_sources(group_id):
                try:
                    keywords = json.loads(source[2]) if source[2] else []
                except json.JSONDecodeError:
                    keywords = []

                sources.append({
                    "id": source[0],
                    "source_type": source[1],
                    "keywords": keywords,
                    "enabled": bool(source[3]),
                    "last_checked": source[4],
                    "created_at": source[5]
                })

            group_dict["sources"] = sources

            logger.info(f"Retrieved feed group '{group_dict['name']}'")
            return group_dict

        except Exception as e:
            logger.error(f"Error fetching feed group {group_id}: {str(e)}")
            return None

    def update_feed_group(self, group_id: int, name: str = None, description: str = None, 
                         color: str = None, is_active: bool = None) -> Dict[str, Any]:
        """
        Update a feed keyword group.
        
        Args:
            group_id: ID of the group to update
            name: New name (optional)
            description: New description (optional)
            color: New color (optional)
            is_active: New active status (optional)
            
        Returns:
            Dictionary with success status and updated group data
        """
        try:
            logger.info(f"Updating feed group {group_id}")
            
            # Check if group exists
            current_group = (DatabaseQueryFacade(db, logger)).get_feed_group_by_id(group_id)
            if not current_group:
                return {
                    "success": False,
                    "error": f"Feed group with ID {group_id} not found"
                }

            # Update data
            if (name is None) and \
                (description is None) and \
                (color is None) and \
                (is_active is not None):
                return {
                    "success": False,
                    "error": "No updates provided"
                }

            (DatabaseQueryFacade(db, logger)).update_feed_group(name, description, color, is_active, group_id)

            # Get updated group
            updated_group = self.get_feed_group(group_id)

            logger.info(f"Updated feed group {group_id}")

            return {
                "success": True,
                "group": updated_group
            }
                
        except Exception as e:
            logger.error(f"Error updating feed group {group_id}: {str(e)}")
            return {
                "success": False,
                "error": f"Failed to update feed group: {str(e)}"
            }

    def delete_feed_group(self, group_id: int) -> Dict[str, Any]:
        """
        Delete a feed keyword group and all associated data.
        
        Args:
            group_id: ID of the group to delete
            
        Returns:
            Dictionary with success status
        """
        try:
            logger.info(f"Deleting feed group {group_id}")
            
            # Check if group exists
            group = (DatabaseQueryFacade(db, logger)).get_feed_group_by_id(group_id)
            if not group:
                return {
                    "success": False,
                    "error": f"Feed group with ID {group_id} not found"
                }

            group_name = group[0]

            (DatabaseQueryFacade(db, logger)).delete_feed_group(group_id)

            logger.info(f"Deleted feed group '{group_name}' (ID: {group_id})")

            return {
                "success": True,
                "message": f"Feed group '{group_name}' deleted successfully"
            }

        except Exception as e:
            logger.error(f"Error deleting feed group {group_id}: {str(e)}")
            return {
                "success": False,
                "error": f"Failed to delete feed group: {str(e)}"
            }

    def add_source_to_group(self, group_id: int, source_type: str, keywords: List[str], 
                           enabled: bool = True, date_range_days: int = 7,
                           custom_start_date: str = None, custom_end_date: str = None) -> Dict[str, Any]:
        """
        Add a source to a feed group.
        
        Args:
            group_id: ID of the feed group
            source_type: Type of source ('bluesky', 'arxiv')
            keywords: List of keywords for this source
            enabled: Whether the source is enabled
            date_range_days: Number of days to search back (default: 7)
            custom_start_date: Custom start date (ISO format, optional)
            custom_end_date: Custom end date (ISO format, optional)
            
        Returns:
            Dictionary with success status and source data
        """
        try:
            logger.info(f"Adding {source_type} source to feed group {group_id}")
            
            valid_source_types = ['bluesky', 'arxiv', 'thenewsapi']
            if source_type not in valid_source_types:
                return {
                    "success": False,
                    "error": f"source_type must be one of: {', '.join(valid_source_types)}"
                }
            
            # Check if group exists
            if not (DatabaseQueryFacade(db, logger)).get_feed_group_by_id(group_id):
                return {
                    "success": False,
                    "error": f"Feed group with ID {group_id} not found"
                }

            # Check if source already exists for this group
            if (DatabaseQueryFacade(db, logger)).get_group_source(group_id, source_type):
                return {
                    "success": False,
                    "error": f"Source type '{source_type}' already exists for this group"
                }

            # Add source
            keywords_json = json.dumps(keywords)
            now = datetime.now().isoformat()

            source_id = (DatabaseQueryFacade(db, logger)).add_source_to_group((group_id, source_type, keywords_json, enabled, date_range_days,
                  custom_start_date, custom_end_date, now))

            logger.info(f"Added {source_type} source (ID: {source_id}) to group {group_id}")

            return {
                "success": True,
                "source": {
                    "id": source_id,
                    "group_id": group_id,
                    "source_type": source_type,
                    "keywords": keywords,
                    "enabled": enabled,
                    "date_range_days": date_range_days,
                    "custom_start_date": custom_start_date,
                    "custom_end_date": custom_end_date,
                    "created_at": now
                }
            }
                
        except Exception as e:
            logger.error(f"Error adding source to group {group_id}: {str(e)}")
            return {
                "success": False,
                "error": f"Failed to add source: {str(e)}"
            }

    def update_source(self, source_id: int, keywords: List[str] = None, enabled: bool = None,
                     date_range_days: int = None, custom_start_date: str = None,
                     custom_end_date: str = None) -> Dict[str, Any]:
        """
        Update a feed group source.
        
        Args:
            source_id: ID of the source to update
            keywords: New keywords list (optional)
            enabled: New enabled status (optional)
            date_range_days: Number of days to search back (optional)
            custom_start_date: Custom start date (ISO format, optional)
            custom_end_date: Custom end date (ISO format, optional)
            
        Returns:
            Dictionary with success status
        """
        try:
            logger.info(f"Updating source {source_id}")

            # Check if source exists
            source = (DatabaseQueryFacade(db, logger)).get_source_by_id(source_id)
            if not source:
                return {
                    "success": False,
                    "error": f"Source with ID {source_id} not found"
                }

            if (keywords is None) and \
                (enabled is None) and \
                (date_range_days is None) and \
                (custom_start_date is None) and \
                (custom_end_date is None):
                return {
                    "success": False,
                    "error": "No updates provided"
                }

            (DatabaseQueryFacade(db, logger)).update_group_source(keywords, enabled, date_range_days, custom_start_date, custom_end_date)

            logger.info(f"Updated source {source_id}")

            return {
                "success": True,
                "message": "Source updated successfully"
            }
                
        except Exception as e:
            logger.error(f"Error updating source {source_id}: {str(e)}")
            return {
                "success": False,
                "error": f"Failed to update source: {str(e)}"
            }

    def delete_source(self, source_id: int) -> Dict[str, Any]:
        """
        Delete a feed group source.
        
        Args:
            source_id: ID of the source to delete
            
        Returns:
            Dictionary with success status
        """
        try:
            logger.info(f"Deleting source {source_id}")
            
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                
                # Check if source exists
                source = (DatabaseQueryFacade(db, logger)).get_source_by_id(source_id)
                if not source:
                    return {
                        "success": False,
                        "error": f"Source with ID {source_id} not found"
                    }
                
                source_type = source[0]
                
                # Delete source
                (DatabaseQueryFacade(db, logger)).delete_group_source(source_id)

                logger.info(f"Deleted {source_type} source (ID: {source_id})")
                
                return {
                    "success": True,
                    "message": f"Source deleted successfully"
                }
                
        except Exception as e:
            logger.error(f"Error deleting source {source_id}: {str(e)}")
            return {
                "success": False,
                "error": f"Failed to delete source: {str(e)}"
            }

    def get_active_groups_with_sources(self) -> List[Dict[str, Any]]:
        """
        Get all active feed groups that have enabled sources.
        Used for feed aggregation.
        
        Returns:
            List of active groups with their enabled sources
        """
        try:
            logger.info("Fetching active groups with enabled sources")
            
            groups = self.get_feed_groups(include_inactive=False)
            active_groups = []
            
            for group in groups:
                enabled_sources = [s for s in group["sources"] if s["enabled"]]
                if enabled_sources:
                    group["sources"] = enabled_sources
                    active_groups.append(group)
            
            logger.info(f"Found {len(active_groups)} active groups with enabled sources")
            return active_groups
            
        except Exception as e:
            logger.error(f"Error fetching active groups: {str(e)}")
            return []

# Export the service instance
feed_group_service = FeedGroupService() 