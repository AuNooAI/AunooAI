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
            
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                
                # Check if group name already exists
                cursor.execute(
                    "SELECT id FROM feed_keyword_groups WHERE name = ?",
                    (name,)
                )
                
                if cursor.fetchone():
                    logger.warning(f"Feed group '{name}' already exists")
                    return {
                        "success": False,
                        "error": f"Feed group '{name}' already exists"
                    }
                
                # Create the group
                now = datetime.now().isoformat()
                cursor.execute("""
                    INSERT INTO feed_keyword_groups 
                    (name, description, color, created_at, updated_at) 
                    VALUES (?, ?, ?, ?, ?)
                """, (name, description, color, now, now))
                
                group_id = cursor.lastrowid
                
                # Create default subscription for the user
                cursor.execute("""
                    INSERT INTO user_feed_subscriptions (group_id) 
                    VALUES (?)
                """, (group_id,))
                
                conn.commit()
                
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
            
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                
                # Build query based on active status
                if include_inactive:
                    query = "SELECT * FROM feed_keyword_groups ORDER BY name"
                    params = ()
                else:
                    query = "SELECT * FROM feed_keyword_groups WHERE is_active = 1 ORDER BY name"
                    params = ()
                
                cursor.execute(query, params)
                groups = cursor.fetchall()
                
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
                    cursor.execute("""
                        SELECT id, source_type, keywords, enabled, last_checked, created_at
                        FROM feed_group_sources 
                        WHERE group_id = ? 
                        ORDER BY source_type
                    """, (group[0],))
                    
                    sources = []
                    for source in cursor.fetchall():
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
            
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute(
                    "SELECT * FROM feed_keyword_groups WHERE id = ?",
                    (group_id,)
                )
                
                group = cursor.fetchone()
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
                cursor.execute("""
                    SELECT id, source_type, keywords, enabled, last_checked, created_at
                    FROM feed_group_sources 
                    WHERE group_id = ? 
                    ORDER BY source_type
                """, (group_id,))
                
                sources = []
                for source in cursor.fetchall():
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
            
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                
                # Check if group exists
                cursor.execute(
                    "SELECT * FROM feed_keyword_groups WHERE id = ?",
                    (group_id,)
                )
                
                current_group = cursor.fetchone()
                if not current_group:
                    return {
                        "success": False,
                        "error": f"Feed group with ID {group_id} not found"
                    }
                
                # Prepare update data
                updates = []
                params = []
                
                if name is not None:
                    updates.append("name = ?")
                    params.append(name)
                
                if description is not None:
                    updates.append("description = ?")
                    params.append(description)
                
                if color is not None:
                    updates.append("color = ?")
                    params.append(color)
                
                if is_active is not None:
                    updates.append("is_active = ?")
                    params.append(is_active)
                
                if not updates:
                    return {
                        "success": False,
                        "error": "No updates provided"
                    }
                
                # Add updated_at timestamp
                updates.append("updated_at = ?")
                params.append(datetime.now().isoformat())
                params.append(group_id)
                
                # Execute update
                cursor.execute(f"""
                    UPDATE feed_keyword_groups 
                    SET {', '.join(updates)}
                    WHERE id = ?
                """, params)
                
                conn.commit()
                
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
            
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                
                # Check if group exists
                cursor.execute(
                    "SELECT name FROM feed_keyword_groups WHERE id = ?",
                    (group_id,)
                )
                
                group = cursor.fetchone()
                if not group:
                    return {
                        "success": False,
                        "error": f"Feed group with ID {group_id} not found"
                    }
                
                group_name = group[0]
                
                # Delete group (CASCADE will handle related data)
                cursor.execute(
                    "DELETE FROM feed_keyword_groups WHERE id = ?",
                    (group_id,)
                )
                
                conn.commit()
                
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
            
            valid_source_types = ['bluesky', 'arxiv']
            if source_type not in valid_source_types:
                return {
                    "success": False,
                    "error": f"source_type must be one of: {', '.join(valid_source_types)}"
                }
            
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                
                # Check if group exists
                cursor.execute(
                    "SELECT id FROM feed_keyword_groups WHERE id = ?",
                    (group_id,)
                )
                
                if not cursor.fetchone():
                    return {
                        "success": False,
                        "error": f"Feed group with ID {group_id} not found"
                    }
                
                # Check if source already exists for this group
                cursor.execute("""
                    SELECT id FROM feed_group_sources 
                    WHERE group_id = ? AND source_type = ?
                """, (group_id, source_type))
                
                if cursor.fetchone():
                    return {
                        "success": False,
                        "error": f"Source type '{source_type}' already exists for this group"
                    }
                
                # Add source
                keywords_json = json.dumps(keywords)
                now = datetime.now().isoformat()
                
                cursor.execute("""
                    INSERT INTO feed_group_sources 
                    (group_id, source_type, keywords, enabled, date_range_days, 
                     custom_start_date, custom_end_date, created_at) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (group_id, source_type, keywords_json, enabled, date_range_days,
                      custom_start_date, custom_end_date, now))
                
                source_id = cursor.lastrowid
                conn.commit()
                
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
            
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                
                # Check if source exists
                cursor.execute(
                    "SELECT * FROM feed_group_sources WHERE id = ?",
                    (source_id,)
                )
                
                source = cursor.fetchone()
                if not source:
                    return {
                        "success": False,
                        "error": f"Source with ID {source_id} not found"
                    }
                
                # Prepare update data
                updates = []
                params = []
                
                if keywords is not None:
                    updates.append("keywords = ?")
                    params.append(json.dumps(keywords))
                
                if enabled is not None:
                    updates.append("enabled = ?")
                    params.append(enabled)
                
                if date_range_days is not None:
                    updates.append("date_range_days = ?")
                    params.append(date_range_days)
                
                if custom_start_date is not None:
                    updates.append("custom_start_date = ?")
                    params.append(custom_start_date)
                
                if custom_end_date is not None:
                    updates.append("custom_end_date = ?")
                    params.append(custom_end_date)
                
                if not updates:
                    return {
                        "success": False,
                        "error": "No updates provided"
                    }
                
                params.append(source_id)
                
                # Execute update
                cursor.execute(f"""
                    UPDATE feed_group_sources 
                    SET {', '.join(updates)}
                    WHERE id = ?
                """, params)
                
                conn.commit()
                
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
                cursor.execute(
                    "SELECT source_type FROM feed_group_sources WHERE id = ?",
                    (source_id,)
                )
                
                source = cursor.fetchone()
                if not source:
                    return {
                        "success": False,
                        "error": f"Source with ID {source_id} not found"
                    }
                
                source_type = source[0]
                
                # Delete source
                cursor.execute(
                    "DELETE FROM feed_group_sources WHERE id = ?",
                    (source_id,)
                )
                
                conn.commit()
                
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