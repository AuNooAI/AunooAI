from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from app.database import get_database_instance, Database
from typing import List
from pydantic import BaseModel
import os
import sqlite3

router = APIRouter()

# Add this model for the bulk delete request
class BulkDeleteRequest(BaseModel):
    uris: List[str]

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
async def bulk_delete_articles(request: BulkDeleteRequest, db: Database = Depends(get_database_instance)):
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # Start a transaction
        cursor.execute("BEGIN TRANSACTION")
        
        try:
            # Delete all articles with the given URIs
            placeholders = ','.join('?' * len(request.uris))
            query = f"DELETE FROM articles WHERE uri IN ({placeholders})"
            cursor.execute(query, request.uris)
            
            deleted_count = cursor.rowcount
            conn.commit()
            
            return {"deleted_count": deleted_count}
            
        except Exception as e:
            conn.rollback()
            raise e
            
        finally:
            conn.close()
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting articles: {str(e)}") 