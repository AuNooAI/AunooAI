from fastapi import APIRouter, HTTPException, Depends, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from app.database import get_database_instance, Database
from typing import List, Optional
from pydantic import BaseModel
import os
import sqlite3
from urllib.parse import unquote_plus
import logging
from scripts.db_merge import DatabaseMerger
from pathlib import Path
from datetime import datetime
import shutil
from config.settings import DATABASE_DIR

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
async def download_database(db_name: str, db: Database = Depends(get_database_instance)):
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
async def get_database_info(db: Database = Depends(get_database_instance)):
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # Get database name and size
        db_name = os.path.basename(db.db_path)
        db_size = os.path.getsize(db.db_path)
        
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
        
        return {
            "name": db_name,
            "size": db_size,
            "total_articles": article_stats[0] if article_stats else 0,
            "first_entry": article_stats[1] if article_stats and article_stats[1] else None,
            "last_entry": article_stats[2] if article_stats and article_stats[2] else None,
            "total_topics": topic_count,
            "tables": table_info
        }
        
    except Exception as e:
        print(f"Error getting database info: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Add the bulk delete endpoint
@router.delete("/api/bulk_delete_articles")
async def bulk_delete_articles(
    request: BulkDeleteRequest,
    db: Database = Depends(get_database_instance)
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
    db: Database = Depends(get_database_instance)
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
    db: Database = Depends(get_database_instance)
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
    db: Database = Depends(get_database_instance)
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
    db: Database = Depends(get_database_instance)
):
    success = db.delete_article_annotation(annotation_id)
    if not success:
        raise HTTPException(status_code=404, detail="Annotation not found")
    return {"success": True}

@router.post("/api/merge_backup")
async def merge_backup_database(backup_name: str = None, uploaded_file: UploadFile = None):
    """Merge articles and settings from a backup database or uploaded file"""
    try:
        db = get_database_instance()
        merger = DatabaseMerger()
        
        if uploaded_file:
            # Save uploaded file to temp location
            temp_path = Path("app/data/temp") / uploaded_file.filename
            temp_path.parent.mkdir(exist_ok=True)
            
            with temp_path.open("wb") as buffer:
                shutil.copyfileobj(uploaded_file.file, buffer)
            
            try:
                merger.merge_databases(temp_path)
                return {"message": f"Successfully merged uploaded database"}
            finally:
                # Cleanup temp file
                temp_path.unlink(missing_ok=True)
                
        elif backup_name:
            backup_path = Path("app/data/backups") / backup_name
            if not backup_path.exists():
                raise HTTPException(status_code=404, detail="Backup database not found")
                
            merger.merge_databases(backup_path)
            return {"message": f"Successfully merged data from {backup_name}"}
            
        else:
            raise HTTPException(status_code=400, detail="No backup specified")
            
    except Exception as e:
        logger.error(f"Error merging backup database: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/backups")
async def get_backups():
    """Get list of database backups with sizes"""
    try:
        # Use the correct backup directory path
        backup_dir = Path("app/data/backups")
        logger.info(f"Looking for backups in: {backup_dir}")
        
        backups = []
        
        if backup_dir.exists():
            logger.info(f"Backup directory exists")
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
async def list_backups():
    """Get list of available database backups"""
    try:
        backup_dir = Path("app/data/backups")
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