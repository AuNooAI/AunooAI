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

@router.get("/api/config")
async def get_config(session=Depends(verify_session)):
    """Get application configuration including topics"""
    try:
        from app.config.config import load_config
        config = load_config()
        return config
    except Exception as e:
        logging.error(f"Failed to load config: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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

        # Detect database type
        db_type = os.getenv('DB_TYPE', 'sqlite').lower()
        logger.info(f"Getting database info for type: {db_type}")

        if db_type == 'postgresql':
            # PostgreSQL-specific logic
            from app.config.settings import db_settings

            conn = db._temp_get_connection()

            # Get database name
            db_name = db_settings.DB_NAME
            logger.info(f"Getting info for PostgreSQL database: {db_name}")

            # Get database size
            size_result = conn.execute(text("""
                SELECT pg_database_size(current_database())
            """))
            db_size = size_result.scalar() or 0

            # Get table information from PostgreSQL information_schema
            table_result = conn.execute(text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_type = 'BASE TABLE'
                ORDER BY table_name
            """))
            tables = table_result.mappings().fetchall()
            table_info = []

            for table_row in tables:
                table_name = table_row['table_name']
                # Get row count for each table
                count_result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                row_count = count_result.scalar()
                table_info.append({
                    "name": table_name,
                    "rows": row_count
                })

            # Get article statistics
            article_stats_result = conn.execute(text("""
                SELECT
                    COUNT(*) as total,
                    MIN(publication_date) as first_entry,
                    MAX(publication_date) as last_entry
                FROM articles
            """))
            article_stats = article_stats_result.mappings().fetchone()

            # Get topic count
            topic_result = conn.execute(text("SELECT COUNT(DISTINCT topic) FROM articles"))
            topic_count = topic_result.scalar()

            info = {
                "name": db_name,
                "size": db_size,
                "db_type": "postgresql",
                "host": db_settings.DB_HOST,
                "port": db_settings.DB_PORT,
                "total_articles": article_stats['total'] if article_stats else 0,
                "first_entry": str(article_stats['first_entry']) if article_stats and article_stats['first_entry'] else None,
                "last_entry": str(article_stats['last_entry']) if article_stats and article_stats['last_entry'] else None,
                "total_topics": topic_count,
                "tables": table_info
            }

        else:
            # SQLite-specific logic (original code)
            conn = db.get_connection()
            cursor = conn.cursor()

            # Get current database path
            db_name = os.path.basename(db.db_path)
            logger.info(f"Getting info for SQLite database: {db_name}")

            try:
                db_size = os.path.getsize(db.db_path)
            except OSError:
                logger.warning(f"Error getting size for {db.db_path}")
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
                "db_type": "sqlite",
                "path": db.db_path,
                "total_articles": article_stats[0] if article_stats else 0,
                "first_entry": article_stats[1] if article_stats and article_stats[1] else None,
                "last_entry": article_stats[2] if article_stats and article_stats[2] else None,
                "total_topics": topic_count,
                "tables": table_info
            }

        logger.info(f"Database info retrieved: {info.get('name')}, {len(info.get('tables', []))} tables")
        return info

    except Exception as e:
        logger.error(f"Error getting database info: {str(e)}")
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

@router.post("/api/reset-articles-data")
async def reset_articles_data(
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session)
):
    """
    Reset all article-related data including:
    - articles and raw_articles
    - article_annotations
    - keyword_alerts, keyword_article_matches
    - keyword_groups, monitored_keywords
    - podcasts
    - feed_items, feed_group_sources
    - model_bias_arena_runs, model_bias_arena_results, model_bias_arena_articles
    - analysis_versions, analysis_versions_v2, article_analysis_cache
    - signal_alerts, incident_status
    - ChromaDB vector store
    """
    try:
        conn = db._temp_get_connection()

        # Disable foreign key checks temporarily for smoother deletion
        conn.execute(text("PRAGMA foreign_keys = OFF"))

        # Delete in correct order to respect foreign key relationships
        tables_to_clear = [
            # Dependent tables first
            'keyword_article_matches',
            'keyword_alerts',
            'article_annotations',
            'model_bias_arena_articles',
            'model_bias_arena_results',
            'model_bias_arena_runs',
            'feed_items',
            'feed_group_sources',
            'signal_alerts',
            'incident_status',
            'article_analysis_cache',
            'analysis_versions_v2',
            'analysis_versions',
            'podcasts',
            'raw_articles',
            # Main tables
            'monitored_keywords',
            'keyword_groups',
            'articles'
        ]

        deleted_counts = {}
        for table in tables_to_clear:
            try:
                # Get count before deletion
                count_result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                count = count_result.scalar()

                # Delete all rows
                conn.execute(text(f"DELETE FROM {table}"))
                deleted_counts[table] = count
                logger.info(f"Deleted {count} rows from {table}")
            except Exception as e:
                logger.warning(f"Error clearing table {table}: {str(e)}")
                # Continue with other tables even if one fails

        # Re-enable foreign key checks
        conn.execute(text("PRAGMA foreign_keys = ON"))

        # Commit the existing transaction
        conn.commit()

        # Run VACUUM to reclaim disk space
        logger.info("Running VACUUM to reclaim disk space...")
        conn.execute(text("VACUUM"))
        logger.info("VACUUM completed")

        # Also clear ChromaDB vector store
        try:
            from app.vector_store import get_chroma_client
            client = get_chroma_client()
            try:
                client.delete_collection("articles")
                logger.info("Deleted ChromaDB 'articles' collection")
                deleted_counts['chromadb_articles'] = 'Collection deleted'
            except Exception as chroma_error:
                logger.warning(f"ChromaDB collection may not exist or already deleted: {str(chroma_error)}")
        except Exception as e:
            logger.warning(f"Could not clear ChromaDB: {str(e)}")

        total_deleted = sum(v for v in deleted_counts.values() if isinstance(v, int))
        logger.info(f"Successfully reset articles data. Total rows deleted: {total_deleted}")

        return {
            "message": f"Successfully reset articles data (including ChromaDB). Deleted {total_deleted} total rows.",
            "details": deleted_counts
        }

    except Exception as e:
        logger.error(f"Error resetting articles data: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/reindex-chromadb")
async def reindex_chromadb(
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session)
):
    """Re-index all articles from SQLite into ChromaDB vector store"""
    try:
        from app.vector_store import upsert_article, get_chroma_client
        from app.database_query_facade import DatabaseQueryFacade

        client = get_chroma_client()

        # Delete existing collection to start fresh
        try:
            client.delete_collection("articles")
            logger.info("Deleted existing ChromaDB 'articles' collection")
        except Exception as e:
            logger.warning(f"Could not delete existing collection (may not exist): {str(e)}")

        # Count total articles to index
        facade = DatabaseQueryFacade(db, logger)
        total_articles = 0
        for _ in facade.get_iter_articles(limit=None):
            total_articles += 1

        logger.info(f"Starting reindex of {total_articles} articles into ChromaDB")

        # Re-index all articles
        indexed = 0
        failed = 0

        for article in facade.get_iter_articles(limit=None):
            try:
                upsert_article(article)
                indexed += 1

                # Log progress every 100 articles
                if indexed % 100 == 0:
                    logger.info(f"Progress: {indexed}/{total_articles} articles indexed")

            except Exception as e:
                failed += 1
                logger.warning(f"Failed to index article {article.get('uri')}: {str(e)}")

                # Stop if too many failures
                if failed > 10:
                    raise Exception(f"Too many failures ({failed}), stopping reindex")

        logger.info(f"ChromaDB reindex completed: {indexed} indexed, {failed} failed")

        return {
            "message": f"Successfully reindexed {indexed} articles into ChromaDB",
            "indexed": indexed,
            "failed": failed,
            "total": total_articles
        }

    except Exception as e:
        logger.error(f"Error reindexing ChromaDB: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/clear-topic-articles/{topic_name}")
async def clear_topic_articles(
    topic_name: str,
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session)
):
    """Clear all articles for a specific topic without deleting the topic itself"""
    try:
        conn = db._temp_get_connection()

        # Get count before deletion
        count_result = conn.execute(
            text("SELECT COUNT(*) FROM articles WHERE topic = :topic"),
            {"topic": topic_name}
        )
        article_count = count_result.scalar()

        if article_count == 0:
            return {
                "message": f"No articles found for topic '{topic_name}'",
                "articles_deleted": 0
            }

        # Delete articles for this topic
        conn.execute(
            text("DELETE FROM articles WHERE topic = :topic"),
            {"topic": topic_name}
        )
        logger.info(f"Deleted {article_count} articles for topic '{topic_name}'")

        # Also delete from raw_articles if it has a topic column
        try:
            conn.execute(
                text("DELETE FROM raw_articles WHERE topic = :topic"),
                {"topic": topic_name}
            )
        except Exception as e:
            logger.warning(f"Could not delete from raw_articles (may not have topic column): {str(e)}")

        # Commit the existing transaction
        conn.commit()

        # Run VACUUM to reclaim disk space
        logger.info("Running VACUUM to reclaim disk space...")
        conn.execute(text("VACUUM"))
        logger.info("VACUUM completed")

        return {
            "message": f"Successfully cleared {article_count} articles for topic '{topic_name}'",
            "articles_deleted": article_count,
            "topic_name": topic_name
        }

    except Exception as e:
        logger.error(f"Error clearing articles for topic '{topic_name}': {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/reset-auspex-chats")
async def reset_auspex_chats(
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session)
):
    """Reset all Auspex chat history (messages and chats)"""
    try:
        conn = db._temp_get_connection()

        # Get counts before deletion
        messages_result = conn.execute(text("SELECT COUNT(*) FROM auspex_messages"))
        messages_count = messages_result.scalar()

        chats_result = conn.execute(text("SELECT COUNT(*) FROM auspex_chats"))
        chats_count = chats_result.scalar()

        # Delete messages first (foreign key to chats)
        conn.execute(text("DELETE FROM auspex_messages"))
        logger.info(f"Deleted {messages_count} messages from auspex_messages")

        # Delete chats
        conn.execute(text("DELETE FROM auspex_chats"))
        logger.info(f"Deleted {chats_count} chats from auspex_chats")

        # Commit the existing transaction
        conn.commit()

        # Run VACUUM to reclaim disk space
        logger.info("Running VACUUM to reclaim disk space...")
        conn.execute(text("VACUUM"))
        logger.info("VACUUM completed")

        return {
            "message": f"Successfully reset Auspex chats. Deleted {chats_count} chats and {messages_count} messages.",
            "chats_deleted": chats_count,
            "messages_deleted": messages_count
        }

    except Exception as e:
        logger.error(f"Error resetting Auspex chats: {str(e)}")
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
                    ).mappings().first()

                    if group_result:
                        group_id = group_result['id']
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
                    ).mappings().first()

                    if group_result:
                        group_id = group_result['id']
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

                # Run VACUUM to reclaim disk space
                logger.info("Running VACUUM to reclaim disk space...")
                cursor.execute("VACUUM")
                logger.info("VACUUM completed")

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

@router.get("/api/export-articles-enriched")
async def export_articles_enriched(
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session)
):
    """Export enriched article data (without raw markdown content)"""
    try:
        conn = db._temp_get_connection()

        # Export enriched articles data
        export_data = {
            "export_timestamp": datetime.now().isoformat(),
            "export_type": "enriched",
            "version": "1.0",
            "articles": []
        }

        # Query enriched articles from the articles table
        result = conn.execute(text("""
            SELECT
                uri, title, news_source, publication_date, submission_date,
                summary, category, future_signal, future_signal_explanation,
                sentiment, sentiment_explanation, time_to_impact, time_to_impact_explanation,
                tags, driver_type, driver_type_explanation, topic, analyzed,
                bias, factual_reporting, mbfc_credibility_rating, bias_source,
                bias_country, press_freedom, media_type, popularity,
                topic_alignment_score, keyword_relevance_score, confidence_score,
                overall_match_explanation, extracted_article_topics, extracted_article_keywords,
                ingest_status, quality_score, quality_issues, auto_ingested
            FROM articles
            ORDER BY submission_date DESC
        """))

        for row in result.mappings():
            export_data["articles"].append(dict(row))

        export_data["total_articles"] = len(export_data["articles"])
        logger.info(f"Exported {export_data['total_articles']} enriched articles")

        return export_data

    except Exception as e:
        logger.error(f"Error exporting enriched articles: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/export-articles-raw")
async def export_articles_raw(
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session)
):
    """Export complete article data including raw markdown content"""
    try:
        conn = db._temp_get_connection()

        # Export complete article data
        export_data = {
            "export_timestamp": datetime.now().isoformat(),
            "export_type": "raw",
            "version": "1.0",
            "articles": []
        }

        # Query all article data including raw content
        result = conn.execute(text("""
            SELECT
                a.uri, a.title, a.news_source, a.publication_date, a.submission_date,
                a.summary, a.category, a.future_signal, a.future_signal_explanation,
                a.sentiment, a.sentiment_explanation, a.time_to_impact, a.time_to_impact_explanation,
                a.tags, a.driver_type, a.driver_type_explanation, a.topic, a.analyzed,
                a.bias, a.factual_reporting, a.mbfc_credibility_rating, a.bias_source,
                a.bias_country, a.press_freedom, a.media_type, a.popularity,
                a.topic_alignment_score, a.keyword_relevance_score, a.confidence_score,
                a.overall_match_explanation, a.extracted_article_topics, a.extracted_article_keywords,
                a.ingest_status, a.quality_score, a.quality_issues, a.auto_ingested,
                r.raw_markdown, r.last_updated
            FROM articles a
            LEFT JOIN raw_articles r ON a.uri = r.uri
            ORDER BY a.submission_date DESC
        """))

        for row in result.mappings():
            export_data["articles"].append(dict(row))

        export_data["total_articles"] = len(export_data["articles"])
        logger.info(f"Exported {export_data['total_articles']} raw articles")

        return export_data

    except Exception as e:
        logger.error(f"Error exporting raw articles: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

class ArticleImportRequest(BaseModel):
    merge_mode: bool = True
    skip_duplicates: bool = True
    update_existing: bool = False

@router.post("/api/import-articles")
async def import_articles(
    import_data: dict,
    merge_mode: bool = True,
    skip_duplicates: bool = True,
    update_existing: bool = False,
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session)
):
    """
    Import article data with robust validation and conflict resolution

    Args:
        import_data: JSON data containing articles to import
        merge_mode: If True, keep existing articles; if False, clear before import
        skip_duplicates: If True, skip articles with duplicate URIs
        update_existing: If True, update existing articles with new data
    """
    try:
        conn = db._temp_get_connection()

        # Validate import data structure
        if "articles" not in import_data:
            raise HTTPException(status_code=400, detail="Invalid import data: missing 'articles' field")

        articles = import_data.get("articles", [])
        if not isinstance(articles, list):
            raise HTTPException(status_code=400, detail="Invalid import data: 'articles' must be a list")

        # Track import statistics
        stats = {
            "total_records": len(articles),
            "imported": 0,
            "updated": 0,
            "skipped": 0,
            "failed": 0,
            "errors": []
        }

        # Begin transaction
        trans = conn.begin()

        try:
            # If not merge mode, clear existing data (with confirmation required in UI)
            if not merge_mode:
                logger.warning("Clearing existing articles (non-merge mode)")
                conn.execute(text("DELETE FROM raw_articles"))
                conn.execute(text("DELETE FROM articles"))

            # Process each article
            for idx, article in enumerate(articles):
                try:
                    # Validate required field
                    if not article.get("uri"):
                        stats["failed"] += 1
                        stats["errors"].append(f"Record {idx + 1}: Missing required field 'uri'")
                        continue

                    uri = article["uri"]

                    # Check if article already exists
                    existing = conn.execute(
                        text("SELECT uri FROM articles WHERE uri = :uri"),
                        {"uri": uri}
                    ).first()

                    if existing:
                        if skip_duplicates and not update_existing:
                            stats["skipped"] += 1
                            continue
                        elif update_existing:
                            # Update existing article
                            update_fields = []
                            update_values = {"uri": uri}

                            # Build update query dynamically for non-null fields
                            for field in [
                                "title", "news_source", "publication_date", "summary", "category",
                                "future_signal", "future_signal_explanation", "sentiment", "sentiment_explanation",
                                "time_to_impact", "time_to_impact_explanation", "tags", "driver_type",
                                "driver_type_explanation", "topic", "analyzed", "bias", "factual_reporting",
                                "mbfc_credibility_rating", "bias_source", "bias_country", "press_freedom",
                                "media_type", "popularity", "topic_alignment_score", "keyword_relevance_score",
                                "confidence_score", "overall_match_explanation", "extracted_article_topics",
                                "extracted_article_keywords", "ingest_status", "quality_score", "quality_issues",
                                "auto_ingested"
                            ]:
                                if field in article and article[field] is not None:
                                    update_fields.append(f"{field} = :{field}")
                                    update_values[field] = article[field]

                            if update_fields:
                                update_query = f"UPDATE articles SET {', '.join(update_fields)} WHERE uri = :uri"
                                conn.execute(text(update_query), update_values)

                            # Update raw_articles if raw_markdown is present
                            if "raw_markdown" in article and article["raw_markdown"] is not None:
                                raw_exists = conn.execute(
                                    text("SELECT uri FROM raw_articles WHERE uri = :uri"),
                                    {"uri": uri}
                                ).first()

                                if raw_exists:
                                    conn.execute(
                                        text("""
                                            UPDATE raw_articles
                                            SET raw_markdown = :raw_markdown,
                                                last_updated = CURRENT_TIMESTAMP,
                                                topic = :topic
                                            WHERE uri = :uri
                                        """),
                                        {
                                            "uri": uri,
                                            "raw_markdown": article["raw_markdown"],
                                            "topic": article.get("topic")
                                        }
                                    )
                                else:
                                    conn.execute(
                                        text("""
                                            INSERT INTO raw_articles (uri, raw_markdown, topic, submission_date, last_updated)
                                            VALUES (:uri, :raw_markdown, :topic, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                                        """),
                                        {
                                            "uri": uri,
                                            "raw_markdown": article["raw_markdown"],
                                            "topic": article.get("topic")
                                        }
                                    )

                            stats["updated"] += 1
                        else:
                            stats["skipped"] += 1
                            continue
                    else:
                        # Insert new article
                        insert_fields = ["uri"]
                        insert_placeholders = [":uri"]
                        insert_values = {"uri": uri}

                        # Build insert query for available fields
                        for field in [
                            "title", "news_source", "publication_date", "summary", "category",
                            "future_signal", "future_signal_explanation", "sentiment", "sentiment_explanation",
                            "time_to_impact", "time_to_impact_explanation", "tags", "driver_type",
                            "driver_type_explanation", "topic", "analyzed", "bias", "factual_reporting",
                            "mbfc_credibility_rating", "bias_source", "bias_country", "press_freedom",
                            "media_type", "popularity", "topic_alignment_score", "keyword_relevance_score",
                            "confidence_score", "overall_match_explanation", "extracted_article_topics",
                            "extracted_article_keywords", "ingest_status", "quality_score", "quality_issues",
                            "auto_ingested"
                        ]:
                            if field in article and article[field] is not None:
                                insert_fields.append(field)
                                insert_placeholders.append(f":{field}")
                                insert_values[field] = article[field]

                        insert_query = f"""
                            INSERT INTO articles ({', '.join(insert_fields)})
                            VALUES ({', '.join(insert_placeholders)})
                        """
                        conn.execute(text(insert_query), insert_values)

                        # Insert raw_articles if raw_markdown is present
                        if "raw_markdown" in article and article["raw_markdown"] is not None:
                            conn.execute(
                                text("""
                                    INSERT INTO raw_articles (uri, raw_markdown, topic, submission_date, last_updated)
                                    VALUES (:uri, :raw_markdown, :topic, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                                """),
                                {
                                    "uri": uri,
                                    "raw_markdown": article["raw_markdown"],
                                    "topic": article.get("topic")
                                }
                            )

                        stats["imported"] += 1

                except Exception as e:
                    stats["failed"] += 1
                    error_msg = f"Record {idx + 1} (URI: {article.get('uri', 'unknown')}): {str(e)}"
                    stats["errors"].append(error_msg)
                    logger.warning(f"Failed to import article: {error_msg}")
                    continue

            # Commit transaction
            trans.commit()

            # Build response message
            message_parts = []
            if stats["imported"] > 0:
                message_parts.append(f"imported {stats['imported']}")
            if stats["updated"] > 0:
                message_parts.append(f"updated {stats['updated']}")
            if stats["skipped"] > 0:
                message_parts.append(f"skipped {stats['skipped']}")
            if stats["failed"] > 0:
                message_parts.append(f"failed {stats['failed']}")

            message = f"Article import completed: {', '.join(message_parts)} of {stats['total_records']} records"

            logger.info(message)
            return {
                "message": message,
                "statistics": stats
            }

        except Exception as e:
            trans.rollback()
            raise e

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error importing articles: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 