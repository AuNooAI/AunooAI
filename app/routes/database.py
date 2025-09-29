from fastapi import APIRouter, HTTPException, Depends, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from app.database import get_database_instance, Database
from app.security.session import verify_session
from typing import List, Optional
from pydantic import BaseModel
import os
import sqlite3
from urllib.parse import unquote_plus
import logging
from sqlalchemy import select, insert, delete, text
from app.database_models import (
    t_keyword_groups as keyword_groups,
    t_monitored_keywords as monitored_keywords,
    t_feed_keyword_groups as feed_keyword_groups,
    t_feed_group_sources as feed_group_sources,
    t_keyword_monitor_settings as keyword_monitor_settings,
    t_keyword_article_matches as keyword_article_matches,
    t_keyword_alerts as keyword_alerts
)
try:
    from scripts.db_merge import DatabaseMerger
except ImportError:
    # Create a stub implementation if scripts module is not available
    class DatabaseMerger:
        def __init__(self, *args, **kwargs):
            logging.warning("Using stub DatabaseMerger (import failed)")
            
        def merge_databases(self, source_db_path):
            logging.warning(f"STUB: Would merge database from {source_db_path}")
            return True
from pathlib import Path
from datetime import datetime
import shutil
from app.config.settings import DATABASE_DIR

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter()

# Add this model for the bulk delete request
class BulkDeleteRequest(BaseModel):
    uris: List[str]
    
    class Config:
        json_schema_extra = {
            "example": {
                "uris": [
                    "https://example.com/article1",
                    "https://example.com/article2"
                ]
            }
        }

class AnnotationCreate(BaseModel):
    content: str
    is_private: bool = False

class AnnotationUpdate(BaseModel):
    content: str
    is_private: bool

@router.get("/api/databases/download/{db_name}")
async def download_database(db_name: str, db: Database = Depends(get_database_instance), session=Depends(verify_session)):
    try:
        # Add debug logging
        print(f"Attempting to download database: {db_name}")
        
        # Ensure the database exists before attempting download
        if not os.path.exists(os.path.join(db.get_database_path(db_name))):
            raise FileNotFoundError(f"Database {db_name} not found")
            
        download_path = db.download_database(db_name)
        
        # Add debug logging
        print(f"Created download path: {download_path}")
        
        if not os.path.exists(download_path):
            raise FileNotFoundError(f"Download file not created at {download_path}")
            
        return FileResponse(
            path=download_path,
            filename=db_name,
            media_type='application/x-sqlite3',
            background=BackgroundTask(lambda: os.unlink(download_path))
        )
    except FileNotFoundError as e:
        print(f"FileNotFoundError: {str(e)}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        print(f"Error downloading database: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/database-info")
async def get_database_info(db: Database = Depends(get_database_instance), session=Depends(verify_session)):
    try:
        # Force a fresh database instance
        db = Database()
        
        # Get fresh connection
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # Get current database path
        db_name = os.path.basename(db.db_path)
        print(f"Getting info for database: {db_name}")  # Debug log
        
        try:
            db_size = os.path.getsize(db.db_path)
        except OSError:
            print(f"Error getting size for {db.db_path}")
            db_size = 0
        
        # Get table information
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        table_info = []
        
        for table in tables:
            table_name = table[0]
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            row_count = cursor.fetchone()[0]
            table_info.append({
                "name": table_name,
                "rows": row_count
            })
        
        # Get article statistics
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                MIN(publication_date) as first_entry,
                MAX(publication_date) as last_entry
            FROM articles
        """)
        article_stats = cursor.fetchone()
        
        # Get topic count
        cursor.execute("SELECT COUNT(DISTINCT topic) FROM articles")
        topic_count = cursor.fetchone()[0]
        
        info = {
            "name": db_name,
            "size": db_size,
            "total_articles": article_stats[0] if article_stats else 0,
            "first_entry": article_stats[1] if article_stats and article_stats[1] else None,
            "last_entry": article_stats[2] if article_stats and article_stats[2] else None,
            "total_topics": topic_count,
            "tables": table_info
        }
        
        print(f"Database info: {info}")  # Debug log
        return info
        
    except Exception as e:
        print(f"Error getting database info: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Add the bulk delete endpoint
@router.delete("/api/bulk_delete_articles")
async def bulk_delete_articles(
    request: BulkDeleteRequest,
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session)
) -> dict:
    """Delete multiple articles and their related data in a single transaction."""
    try:
        if not request.uris:
            raise HTTPException(status_code=400, detail="No URIs provided")
            
        # Log the request for debugging
        logger.debug(f"Bulk delete request received for {len(request.uris)} articles")
        logger.debug(f"First few URIs: {request.uris[:3]}")
        
        deleted_count = db.bulk_delete_articles(request.uris)
        
        if deleted_count == 0:
            logger.warning("No articles were deleted")
            return {
                "status": "warning",
                "message": "No matching articles found",
                "deleted_count": 0
            }
            
        return {
            "status": "success",
            "message": f"Successfully deleted {deleted_count} articles",
            "deleted_count": deleted_count
        }
        
    except Exception as e:
        logger.error(f"Error in bulk_delete_articles: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete articles: {str(e)}"
        )

@router.get("/api/articles/{article_uri}/annotations")
async def get_article_annotations(
    article_uri: str,
    include_private: bool = False,
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session)
):
    try:
        # Use unquote_plus twice to handle double encoding
        decoded_uri = unquote_plus(unquote_plus(article_uri))
        logger.debug(f"Getting annotations for decoded URI: {decoded_uri}")
        return db.get_article_annotations(decoded_uri, include_private)
    except Exception as e:
        logger.error(f"Error getting annotations: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/articles/{article_uri}/annotations")
async def create_article_annotation(
    article_uri: str,
    annotation: AnnotationCreate,
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session)
):
    try:
        # Use unquote_plus twice to handle double encoding
        decoded_uri = unquote_plus(unquote_plus(article_uri))
        logger.debug(f"Creating annotation for decoded URI: {decoded_uri}")
        logger.debug(f"Annotation content: {annotation.content[:100]}...")
        logger.debug(f"Is private: {annotation.is_private}")
        
        author = "admin"  # For now, hardcode the author
        annotation_id = db.add_article_annotation(
            decoded_uri, 
            author, 
            annotation.content, 
            annotation.is_private
        )
        logger.debug(f"Created annotation with ID: {annotation_id}")
        return {"id": annotation_id}
    except sqlite3.IntegrityError as e:
        logger.error(f"Database integrity error: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail="Could not create annotation due to database constraints"
        )
    except Exception as e:
        logger.error(f"Error creating annotation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/api/articles/{article_uri}/annotations/{annotation_id}")
async def update_article_annotation(
    article_uri: str,
    annotation_id: int,
    annotation: AnnotationUpdate,
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session)
):
    success = db.update_article_annotation(
        annotation_id,
        annotation.content,
        annotation.is_private
    )
    if not success:
        raise HTTPException(status_code=404, detail="Annotation not found")
    return {"success": True}

@router.delete("/api/articles/{article_uri}/annotations/{annotation_id}")
async def delete_article_annotation(
    article_uri: str,
    annotation_id: int,
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session)
):
    success = db.delete_article_annotation(annotation_id)
    if not success:
        raise HTTPException(status_code=404, detail="Annotation not found")
    return {"success": True}

@router.post("/api/databases/backup")
async def create_database_backup(db: Database = Depends(get_database_instance), session=Depends(verify_session)):
    """Create a backup of the current database"""
    try:
        from scripts.db_merge import DatabaseMerger
        merger = DatabaseMerger()
        backup_path = merger.create_backup()
        return {"message": f"Database backup created successfully", "backup_file": backup_path.name}
    except Exception as e:
        logger.error(f"Error creating database backup: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/merge_backup")
async def merge_backup_database(backup_name: str = None, uploaded_file: UploadFile = None, session=Depends(verify_session)):
    """Merge articles and settings from a backup database or uploaded file"""
    try:
        from scripts.db_merge import DatabaseMerger
        merger = DatabaseMerger()

        if uploaded_file:
            # Save uploaded file to temp location
            temp_path = Path(DATABASE_DIR) / "temp" / uploaded_file.filename
            temp_path.parent.mkdir(exist_ok=True)

            with temp_path.open("wb") as buffer:
                shutil.copyfileobj(uploaded_file.file, buffer)

            try:
                merger.merge_databases(temp_path)
                return {"message": f"Successfully merged uploaded database: {uploaded_file.filename}"}
            finally:
                # Cleanup temp file
                temp_path.unlink(missing_ok=True)

        elif backup_name:
            backup_path = Path(DATABASE_DIR) / "backups" / backup_name
            if not backup_path.exists():
                raise HTTPException(status_code=404, detail=f"Backup database not found: {backup_name}")

            merger.merge_databases(backup_path)
            return {"message": f"Successfully merged data from {backup_name}"}

        else:
            raise HTTPException(status_code=400, detail="No backup specified")

    except Exception as e:
        logger.error(f"Error merging backup database: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/backups")
async def get_backups(session=Depends(verify_session)):
    """Get list of database backups with sizes"""
    try:
        backup_dir = Path(DATABASE_DIR) / "backups"
        backup_dir.mkdir(exist_ok=True)
        logger.info(f"Looking for backups in: {backup_dir}")

        backups = []

        for backup in backup_dir.glob("*.db"):
            try:
                size = backup.stat().st_size
                size_mb = round(size / (1024 * 1024), 2)
                backup_info = {
                    "name": backup.name,
                    "size": f"{size_mb} MB",
                    "date": datetime.fromtimestamp(backup.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                }
                backups.append(backup_info)
                logger.info(f"Found backup: {backup_info}")
            except Exception as e:
                logger.warning(f"Error processing backup {backup}: {e}")
                continue

        sorted_backups = sorted(backups, key=lambda x: x["date"], reverse=True)
        logger.info(f"Returning {len(sorted_backups)} backups")
        return sorted_backups

    except Exception as e:
        logger.error(f"Error getting backups: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/backups")
async def list_backups(session=Depends(verify_session)):
    """Get list of available database backups"""
    try:
        backup_dir = Path(DATABASE_DIR) / "backups"
        backups = []

        if backup_dir.exists():
            for file in backup_dir.glob("*.db"):
                stats = file.stat()
                backups.append({
                    "name": file.name,
                    "size": f"{stats.st_size / (1024*1024):.1f}MB",
                    "date": datetime.fromtimestamp(stats.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                })

        return backups

    except Exception as e:
        logger.error(f"Error listing backups: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/export-topics")
async def export_topic_configurations(db: Database = Depends(get_database_instance), session=Depends(verify_session)):
    """Export all topic configurations to JSON"""
    try:
        conn = db._temp_get_connection()

        # Export topic configurations including keyword groups, keywords, feed groups, and settings
        export_data = {
            "export_timestamp": datetime.now().isoformat(),
            "version": "1.0",
            "keyword_groups": [],
            "monitored_keywords": [],
            "feed_keyword_groups": [],
            "feed_group_sources": [],
            "keyword_monitor_settings": {}
        }

        # Export keyword groups using SQLAlchemy
        result = conn.execute(select(keyword_groups))
        for row in result.mappings():
            export_data["keyword_groups"].append(dict(row))

        # Export monitored keywords with group references
        result = conn.execute(
            select(
                monitored_keywords.c.keyword,
                monitored_keywords.c.created_at,
                monitored_keywords.c.last_checked,
                keyword_groups.c.name.label("group_name"),
                keyword_groups.c.topic.label("group_topic")
            ).select_from(
                monitored_keywords.join(keyword_groups, monitored_keywords.c.group_id == keyword_groups.c.id)
            )
        )
        for row in result.mappings():
            export_data["monitored_keywords"].append(dict(row))

        # Export feed keyword groups
        result = conn.execute(select(feed_keyword_groups))
        for row in result.mappings():
            export_data["feed_keyword_groups"].append(dict(row))

        # Export feed group sources with group names
        result = conn.execute(
            select(
                feed_group_sources.c.source_type,
                feed_group_sources.c.keywords,
                feed_group_sources.c.enabled,
                feed_group_sources.c.date_range_days,
                feed_group_sources.c.custom_start_date,
                feed_group_sources.c.created_at,
                feed_keyword_groups.c.name.label("group_name")
            ).select_from(
                feed_group_sources.join(feed_keyword_groups, feed_group_sources.c.group_id == feed_keyword_groups.c.id)
            )
        )
        for row in result.mappings():
            export_data["feed_group_sources"].append(dict(row))

        # Export keyword monitor settings
        result = conn.execute(select(keyword_monitor_settings))
        row = result.mappings().first()
        if row:
            export_data["keyword_monitor_settings"] = dict(row)

        return export_data

    except Exception as e:
        logger.error(f"Error exporting topic configurations: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/import-topics")
async def import_topic_configurations(
    import_data: dict,
    merge_mode: bool = False,
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session)
):
    """Import topic configurations from JSON"""
    try:
        conn = db._temp_get_connection()

        # Begin transaction
        trans = conn.begin()

        try:
            # If not merge mode, clear existing data
            if not merge_mode:
                conn.execute(delete(keyword_article_matches))
                conn.execute(delete(keyword_alerts))
                conn.execute(delete(monitored_keywords))
                conn.execute(delete(keyword_groups))
                conn.execute(delete(feed_group_sources))
                conn.execute(delete(feed_keyword_groups))
                conn.execute(delete(keyword_monitor_settings))

            # Import keyword groups
            if "keyword_groups" in import_data:
                for group in import_data["keyword_groups"]:
                    if merge_mode:
                        # Check if group already exists
                        existing = conn.execute(
                            select(keyword_groups.c.id).where(
                                (keyword_groups.c.name == group["name"]) &
                                (keyword_groups.c.topic == group["topic"])
                            )
                        ).first()
                        if existing:
                            continue  # Skip if exists in merge mode

                    conn.execute(
                        insert(keyword_groups).values(
                            name=group["name"],
                            topic=group["topic"],
                            created_at=group.get("created_at"),
                            provider=group.get("provider", "news")
                        )
                    )

            # Import monitored keywords
            if "monitored_keywords" in import_data:
                for keyword in import_data["monitored_keywords"]:
                    # Get the group_id by name and topic
                    group_result = conn.execute(
                        select(keyword_groups.c.id).where(
                            (keyword_groups.c.name == keyword.get("group_name")) &
                            (keyword_groups.c.topic == keyword.get("group_topic"))
                        )
                    ).first()

                    if group_result:
                        group_id = group_result[0]
                        if merge_mode:
                            # Check if keyword already exists
                            existing = conn.execute(
                                select(monitored_keywords.c.id).where(
                                    (monitored_keywords.c.group_id == group_id) &
                                    (monitored_keywords.c.keyword == keyword["keyword"])
                                )
                            ).first()
                            if existing:
                                continue

                        conn.execute(
                            insert(monitored_keywords).values(
                                group_id=group_id,
                                keyword=keyword["keyword"],
                                created_at=keyword.get("created_at"),
                                last_checked=keyword.get("last_checked")
                            )
                        )

            # Import feed keyword groups
            if "feed_keyword_groups" in import_data:
                for feed_group in import_data["feed_keyword_groups"]:
                    if merge_mode:
                        existing = conn.execute(
                            select(feed_keyword_groups.c.id).where(
                                feed_keyword_groups.c.name == feed_group["name"]
                            )
                        ).first()
                        if existing:
                            continue

                    conn.execute(
                        insert(feed_keyword_groups).values(
                            name=feed_group["name"],
                            description=feed_group.get("description"),
                            color=feed_group.get("color", "#FF69B4"),
                            is_active=feed_group.get("is_active", True)
                        )
                    )

            # Import feed group sources
            if "feed_group_sources" in import_data:
                for source in import_data["feed_group_sources"]:
                    # Get group_id by name
                    group_result = conn.execute(
                        select(feed_keyword_groups.c.id).where(
                            feed_keyword_groups.c.name == source.get("group_name")
                        )
                    ).first()

                    if group_result:
                        group_id = group_result[0]
                        if merge_mode:
                            existing = conn.execute(
                                select(feed_group_sources.c.id).where(
                                    (feed_group_sources.c.group_id == group_id) &
                                    (feed_group_sources.c.source_type == source["source_type"]) &
                                    (feed_group_sources.c.keywords == source["keywords"])
                                )
                            ).first()
                            if existing:
                                continue

                        conn.execute(
                            insert(feed_group_sources).values(
                                group_id=group_id,
                                source_type=source["source_type"],
                                keywords=source["keywords"],
                                enabled=source.get("enabled", True),
                                date_range_days=source.get("date_range_days", 7),
                                custom_start_date=source.get("custom_start_date")
                            )
                        )

            # Import keyword monitor settings
            if "keyword_monitor_settings" in import_data and not merge_mode:
                settings = import_data["keyword_monitor_settings"]
                # Delete existing settings first
                conn.execute(delete(keyword_monitor_settings))
                conn.execute(
                    insert(keyword_monitor_settings).values(
                        check_interval=settings.get("check_interval", 15),
                        interval_unit=settings.get("interval_unit", 60),
                        search_fields=settings.get("search_fields", "title,description,content"),
                        language=settings.get("language", "en")
                    )
                )

            # Commit transaction
            trans.commit()

            return {"message": f"Successfully imported topic configurations ({'merged' if merge_mode else 'replaced'})"}

        except Exception as e:
            trans.rollback()
            raise e

    except Exception as e:
        logger.error(f"Error importing topic configurations: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/databases/reset")
async def reset_database(db: Database = Depends(get_database_instance), session=Depends(verify_session)):
    """Reset the database to its initial state"""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Begin transaction
            cursor.execute("BEGIN IMMEDIATE")
            
            try:
                # Disable foreign key checks temporarily
                cursor.execute("PRAGMA foreign_keys = OFF")
                
                # Drop existing tables
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name NOT IN ('sqlite_sequence')
                """)
                tables = cursor.fetchall()
                
                for table in tables:
                    cursor.execute(f"DROP TABLE IF EXISTS {table[0]}")
                
                # Re-enable foreign key checks
                cursor.execute("PRAGMA foreign_keys = ON")
                
                # Reinitialize database with new schema
                db.init_db()
                
                cursor.execute("COMMIT")
                return {"message": "Database reset successfully"}
                
            except Exception as e:
                cursor.execute("ROLLBACK")
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to reset database: {str(e)}"
                )
                
    except Exception as e:
        logger.error(f"Error resetting database: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 