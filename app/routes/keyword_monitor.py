from fastapi import APIRouter, HTTPException, Depends, Request
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
from app.database import Database, get_database_instance
from app.tasks.keyword_monitor import KeywordMonitor, get_task_status
from app.security.session import verify_session
from app.models.media_bias import MediaBias
import logging
import json
import traceback
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
import io
import csv
from pathlib import Path
import sqlite3
from fastapi.responses import JSONResponse
from app.config.config import load_config
from app.ai_models import ai_get_available_models

# Set up logger
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/keyword-monitor")

# Set up templates
templates = Jinja2Templates(directory="templates")

class KeywordGroup(BaseModel):
    name: str
    topic: str

class Keyword(BaseModel):
    group_id: int
    keyword: str

class KeywordMonitorSettings(BaseModel):
    check_interval: int
    interval_unit: int
    search_fields: str
    language: str
    sort_by: str
    page_size: int
    daily_request_limit: int = 100

class PollingToggle(BaseModel):
    enabled: bool

@router.post("/groups")
async def create_group(group: KeywordGroup, db=Depends(get_database_instance)):
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO keyword_groups (name, topic) VALUES (?, ?)",
                (group.name, group.topic)
            )
            conn.commit()
            return {"id": cursor.lastrowid}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/keywords")
async def add_keyword(keyword: Keyword, db=Depends(get_database_instance)):
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO monitored_keywords (group_id, keyword) VALUES (?, ?)",
                (keyword.group_id, keyword.keyword)
            )
            conn.commit()
            return {"id": cursor.lastrowid}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/keywords/{keyword_id}")
async def delete_keyword(keyword_id: int, db=Depends(get_database_instance)):
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM monitored_keywords WHERE id = ?", (keyword_id,))
            conn.commit()
            return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/groups/{group_id}")
async def delete_group(group_id: int, db=Depends(get_database_instance)):
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM keyword_groups WHERE id = ?", (group_id,))
            conn.commit()
            return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/groups/by-topic/{topic_name}")
async def delete_groups_by_topic(topic_name: str, db=Depends(get_database_instance)):
    """Delete all keyword groups associated with a specific topic and clean up orphaned data"""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # First, get all group IDs associated with this topic
            cursor.execute("SELECT id FROM keyword_groups WHERE topic = ?", (topic_name,))
            groups = cursor.fetchall()
            
            if not groups:
                return {"success": True, "groups_deleted": 0}
            
            group_ids = [group[0] for group in groups]
            groups_deleted = len(group_ids)
            
            # Find all keyword IDs belonging to these groups
            keyword_ids = []
            for group_id in group_ids:
                cursor.execute("SELECT id FROM monitored_keywords WHERE group_id = ?", (group_id,))
                keywords = cursor.fetchall()
                keyword_ids.extend([kw[0] for kw in keywords])
            
            # Delete all keyword alerts related to these keywords
            alerts_deleted = 0
            if keyword_ids:
                ids_str = ','.join('?' for _ in keyword_ids)
                
                # Check if the keyword_article_matches table exists
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name='keyword_article_matches'
                """)
                use_new_table = cursor.fetchone() is not None
                
                if use_new_table:
                    # For the new table structure
                    for group_id in group_ids:
                        cursor.execute("DELETE FROM keyword_article_matches WHERE group_id = ?", (group_id,))
                        alerts_deleted += cursor.rowcount
                else:
                    # For the original table structure
                    cursor.execute(f"DELETE FROM keyword_alerts WHERE keyword_id IN ({ids_str})", keyword_ids)
                    alerts_deleted = cursor.rowcount
            
            # Delete all keywords for these groups
            keywords_deleted = 0
            if group_ids:
                ids_str = ','.join('?' for _ in group_ids)
                cursor.execute(f"DELETE FROM monitored_keywords WHERE group_id IN ({ids_str})", group_ids)
                keywords_deleted = cursor.rowcount
            
            # Delete all keyword groups for this topic
            cursor.execute("DELETE FROM keyword_groups WHERE topic = ?", (topic_name,))
            
            conn.commit()
            return {
                "success": True, 
                "groups_deleted": groups_deleted,
                "keywords_deleted": keywords_deleted,
                "alerts_deleted": alerts_deleted
            }
    except Exception as e:
        logging.error(f"Error deleting keyword groups for topic {topic_name}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/alerts/{alert_id}/read")
async def mark_alert_read(alert_id: int, db=Depends(get_database_instance)):
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if the alert is in the keyword_article_matches table
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='keyword_article_matches'
            """)
            use_new_table = cursor.fetchone() is not None
            
            if use_new_table:
                # Check if the alert ID is in the new table
                cursor.execute("SELECT 1 FROM keyword_article_matches WHERE id = ?", (alert_id,))
                if cursor.fetchone():
                    # Update the new table
                    cursor.execute(
                        "UPDATE keyword_article_matches SET is_read = 1 WHERE id = ?",
                        (alert_id,)
                    )
                else:
                    # Update the old table
                    cursor.execute(
                        "UPDATE keyword_alerts SET is_read = 1 WHERE id = ?",
                        (alert_id,)
                    )
            else:
                # Update the old table
                cursor.execute(
                    "UPDATE keyword_alerts SET is_read = 1 WHERE id = ?",
                    (alert_id,)
                )
            
            conn.commit()
            return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/check-now")
async def check_now(db=Depends(get_database_instance)):
    """Trigger an immediate keyword check"""
    try:
        # Log number of keywords being monitored
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM monitored_keywords")
            keyword_count = cursor.fetchone()[0]
            logger.info(f"Running manual keyword check - {keyword_count} keywords configured")
        
        monitor = KeywordMonitor(db)
        result = await monitor.check_keywords()
        
        if result.get("success", False):
            logger.info(f"Keyword check completed successfully: {result.get('new_articles', 0)} new articles found")
            return result
        else:
            logger.error(f"Keyword check failed: {result.get('error', 'Unknown error')}")
            raise HTTPException(status_code=500, detail=result.get('error', 'Unknown error'))
            
    except ValueError as e:
        logger.error(f"Value error in check_now: {str(e)}")
        if "Rate limit exceeded" in str(e) or "request limit reached" in str(e):
            # Return a specific status code for rate limiting
            raise HTTPException(
                status_code=429,  # Too Many Requests
                detail="API daily request limit reached. Please try again tomorrow."
            )
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error checking keywords: {str(e)}")
        logger.error(traceback.format_exc())  # Log the full traceback
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/alerts")
async def get_alerts(
    request: Request,
    session=Depends(verify_session),
    db: Database = Depends(get_database_instance),
    show_read: bool = False
):
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Initialize media bias for article enrichment
            media_bias = MediaBias(db)
            
            # Modify the query to optionally include read articles
            read_condition = "" if show_read else "AND ka.is_read = 0"
            
            cursor.execute(f"""
                SELECT ka.*, a.*, mk.keyword as matched_keyword
                FROM keyword_alerts ka
                JOIN articles a ON ka.article_uri = a.uri
                JOIN monitored_keywords mk ON ka.keyword_id = mk.id
                WHERE 1=1 {read_condition}
                ORDER BY ka.detected_at DESC
                LIMIT 100
            """)
            
            columns = [column[0] for column in cursor.description]
            alerts = []
            
            for row in cursor.fetchall():
                alert_data = dict(zip(columns, row))
                
                # Restructure for consistent response format
                article_data = {
                    "title": alert_data.get("title", ""),
                    "url": alert_data.get("url", ""),
                    "uri": alert_data.get("uri", ""),
                    "summary": alert_data.get("summary", ""),
                    "source": alert_data.get("source", ""),
                    "publication_date": alert_data.get("publication_date", "")
                }
                
                # Try to get media bias data using both source name and URL
                bias_data = None
                if article_data["source"]:
                    # First try with the source name
                    bias_data = media_bias.get_bias_for_source(article_data["source"])
                
                # If no match with source name, try with the URL
                if not bias_data and article_data["url"]:
                    bias_data = media_bias.get_bias_for_source(article_data["url"])
                    
                if bias_data:
                    article_data["bias"] = bias_data.get("bias")
                    article_data["factual_reporting"] = bias_data.get("factual_reporting")
                    article_data["mbfc_credibility_rating"] = bias_data.get("mbfc_credibility_rating")
                    article_data["bias_country"] = bias_data.get("country")
                    article_data["press_freedom"] = bias_data.get("press_freedom")
                    article_data["media_type"] = bias_data.get("media_type")
                    article_data["popularity"] = bias_data.get("popularity")
                
                formatted_alerts.append({
                    'id': alert_data.get("id", ""),
                    'is_read': bool(alert_data.get("is_read", 0)),
                    'detected_at': alert_data.get("detected_at", ""),
                    'article': article_data,
                    'matched_keyword': alert_data.get("matched_keyword", "")
                })
            
            return {
                "alerts": formatted_alerts
            }
    except Exception as e:
        logger.error(f"Error fetching alerts: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/keyword-alerts", response_class=HTMLResponse)
async def keyword_alerts_page(request: Request, session=Depends(verify_session), db: Database = Depends(get_database_instance)):
    """Render the main keyword alerts dashboard page."""
    try:
        # Fetch all active groups and their unread alerts
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Fetch keyword groups with unread alert counts and latest alert time
            cursor.execute("""
                SELECT 
                    kg.id, kg.name, kg.topic,
                    COUNT(DISTINCT CASE WHEN ka.is_read = 0 THEN ka.id ELSE NULL END) as unread_count,
                    MAX(ka.detected_at) as latest_alert_time,
                    GROUP_CONCAT(DISTINCT mk.keyword) as keywords,
                    SUM(CASE WHEN ka.is_read = 0 THEN 1 ELSE 0 END) as total_unread_alerts,
                    COUNT(ka.id) as total_alerts
                FROM keyword_groups kg
                LEFT JOIN monitored_keywords mk ON kg.id = mk.group_id
                LEFT JOIN keyword_alerts ka ON mk.id = ka.keyword_id
                GROUP BY kg.id, kg.name, kg.topic
                ORDER BY latest_alert_time DESC, kg.name ASC
            """)
            groups_data = cursor.fetchall()
            
            groups = []
            status_colors = {
                "stable": "secondary",
                "growing": "success",
                "declining": "warning",
                "new": "primary"
            }
            
            for group_row in groups_data:
                group_dict = {
                    "id": group_row[0],
                    "name": group_row[1],
                    "topic": group_row[2],
                    "unread_count": group_row[3] or 0,
                    "latest_alert_time": group_row[4],
                    "keywords": group_row[5].split(',') if group_row[5] else [],
                    "total_unread_alerts": group_row[6] or 0,
                    "total_alerts": group_row[7] or 0,
                    "growth_status": "stable", # Placeholder, to be calculated
                    "alerts": [] # Will be populated if needed or by a separate fetch
                }
                
                # Fetch first 3 unread alerts for this group for quick preview
                cursor.execute("""
                    SELECT ka.id, ka.article_uri, ka.detected_at, ka.is_read, mk.keyword as matched_keyword,
                           a.title, a.summary, a.news_source as source, a.publication_date, a.uri as article_url,
                           a.bias, a.factual_reporting, a.mbfc_credibility_rating, 
                           a.bias_country, a.press_freedom, a.media_type, a.popularity
                    FROM keyword_alerts ka
                    JOIN monitored_keywords mk ON ka.keyword_id = mk.id
                    JOIN articles a ON ka.article_uri = a.uri
                    WHERE mk.group_id = ? AND ka.is_read = 0
                    ORDER BY ka.detected_at DESC
                    LIMIT 3
                """, (group_dict["id"],))
                alerts_data = cursor.fetchall()
                
                for alert_row in alerts_data:
                    group_dict["alerts"].append({
                        "id": alert_row[0],
                        "article_uri": alert_row[1],
                        "detected_at": alert_row[2],
                        "is_read": bool(alert_row[3]),
                        "matched_keyword": alert_row[4],
                        "article": {
                            "title": alert_row[5],
                            "summary": alert_row[6],
                            "source": alert_row[7],
                            "publication_date": alert_row[8],
                            "url": alert_row[9],
                            "bias": alert_row[10],
                            "factual_reporting": alert_row[11],
                            "mbfc_credibility_rating": alert_row[12],
                            "bias_country": alert_row[13],
                            "press_freedom": alert_row[14],
                            "media_type": alert_row[15],
                            "popularity": alert_row[16]
                        }
                    })
                groups.append(group_dict)

        # Get background task status
        bg_task_status = get_task_status()
        settings_data = get_monitor_settings(db)
        
        # Get available LLM models and enterprise status
        available_llm_models = ai_get_available_models()
        is_enterprise = db.is_enterprise_active()
        
        context = {
            "request": request,
            "groups": groups,
            "status_colors": status_colors,
            "last_check_time": bg_task_status.get('last_check_time'),
            "last_error": bg_task_status.get('last_error'),
            "next_check_time": bg_task_status.get('next_check_time'),
            "is_enabled": settings_data.get('is_enabled', True), # Default to True if not set
            "display_interval": format_interval(settings_data.get('check_interval_seconds', 3600)),
            "now": datetime.utcnow().isoformat(),
            "available_llm_models": available_llm_models, # Pass models to template
            "is_enterprise_active": is_enterprise # Pass enterprise status to template
        }
        return templates.TemplateResponse(
            "keyword_alerts.html",
            context
        )
    except Exception as e:
        logger.error(f"Error in keyword_alerts_page: {str(e)}")
        traceback.print_exc()
        return templates.TemplateResponse(
            "keyword_alerts.html",
            {
                "request": request,
                "groups": [],
                "status_colors": {},
                "error": str(e)
            }
        )

@router.get("/settings")
async def get_settings(db=Depends(get_database_instance)):
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Create keyword_monitor_status table if it doesn't exist
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS keyword_monitor_status (
                    id INTEGER PRIMARY KEY,
                    requests_today INTEGER DEFAULT 0,
                    last_reset_date TEXT,
                    last_check_time TEXT,
                    last_error TEXT
                )
            """)
            
            # Insert default row if it doesn't exist
            cursor.execute("""
                INSERT OR IGNORE INTO keyword_monitor_status (id, requests_today)
                VALUES (1, 0)
            """)
            conn.commit()
            
            # Debug: Check both tables
            cursor.execute("SELECT * FROM keyword_monitor_status WHERE id = 1")
            status_data = cursor.fetchone()
            logger.debug(f"Status data: {status_data}")
            
            cursor.execute("SELECT * FROM keyword_monitor_settings WHERE id = 1")
            settings_data = cursor.fetchone()
            logger.debug(f"Settings data: {settings_data}")
            
            # Get accurate keyword count
            cursor.execute("""
                SELECT COUNT(*) 
                FROM monitored_keywords mk
                WHERE EXISTS (
                    SELECT 1 
                    FROM keyword_groups kg 
                    WHERE kg.id = mk.group_id
                )
            """)
            total_keywords = cursor.fetchone()[0]
            
            # Log the count for debugging
            logger.debug(f"Active keywords count: {total_keywords}")
            
            # Get settings and status together
            cursor.execute("""
                SELECT 
                    s.check_interval,
                    s.interval_unit,
                    s.search_fields,
                    s.language,
                    s.sort_by,
                    s.page_size,
                    s.daily_request_limit,
                    s.is_enabled,
                    COALESCE(kms.requests_today, 0) as requests_today,
                    kms.last_error
                FROM keyword_monitor_settings s
                LEFT JOIN (
                    SELECT id, requests_today, last_error 
                    FROM keyword_monitor_status 
                    WHERE id = 1 AND last_reset_date = date('now')
                ) kms ON kms.id = 1
                WHERE s.id = 1
            """)
            
            settings = cursor.fetchone()
            logger.debug(f"Settings query result: {settings}")
            
            if settings:
                response_data = {
                    "check_interval": settings[0],
                    "interval_unit": settings[1],
                    "search_fields": settings[2],
                    "language": settings[3],
                    "sort_by": settings[4],
                    "page_size": settings[5],
                    "daily_request_limit": settings[6],
                    "is_enabled": bool(settings[7]),
                    "requests_today": settings[8] if settings[8] is not None else 0,
                    "last_error": settings[9],
                    "total_keywords": total_keywords
                }
                logger.debug(f"Returning response data: {response_data}")
                return response_data
            else:
                return {
                    "check_interval": 15,
                    "interval_unit": 60,
                    "search_fields": "title,description,content",
                    "language": "en",
                    "sort_by": "publishedAt",
                    "page_size": 10,
                    "daily_request_limit": 100,
                    "is_enabled": True,
                    "requests_today": 0,
                    "last_error": None,
                    "total_keywords": total_keywords
                }
            
    except Exception as e:
        logger.error(f"Error getting settings: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/settings")
async def save_settings(settings: KeywordMonitorSettings, db=Depends(get_database_instance)):
    """Save keyword monitor settings"""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Create table if it doesn't exist
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS keyword_monitor_settings (
                    id INTEGER PRIMARY KEY,
                    check_interval INTEGER NOT NULL,
                    interval_unit INTEGER NOT NULL,
                    search_fields TEXT NOT NULL,
                    language TEXT NOT NULL,
                    sort_by TEXT NOT NULL,
                    page_size INTEGER NOT NULL,
                    daily_request_limit INTEGER NOT NULL
                )
            """)
            
            # Update or insert settings
            cursor.execute("""
                INSERT OR REPLACE INTO keyword_monitor_settings (
                    id, check_interval, interval_unit, search_fields,
                    language, sort_by, page_size, daily_request_limit
                ) VALUES (
                    1, ?, ?, ?, ?, ?, ?, ?
                )
            """, (
                settings.check_interval,
                settings.interval_unit,
                settings.search_fields,
                settings.language,
                settings.sort_by,
                settings.page_size,
                settings.daily_request_limit
            ))
            
            conn.commit()
            return {"success": True}
            
    except Exception as e:
        logger.error(f"Error saving settings: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/trends")
async def get_trends(db=Depends(get_database_instance)):
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get data for the last 7 days
            cursor.execute("""
                WITH RECURSIVE dates(date) AS (
                    SELECT date('now', '-6 days')
                    UNION ALL
                    SELECT date(date, '+1 day')
                    FROM dates
                    WHERE date < date('now')
                ),
                daily_counts AS (
                    SELECT 
                        kg.id as group_id,
                        kg.name as group_name,
                        date(ka.detected_at) as detection_date,
                        COUNT(*) as article_count
                    FROM keyword_alerts ka
                    JOIN monitored_keywords mk ON ka.keyword_id = mk.id
                    JOIN keyword_groups kg ON mk.group_id = kg.id
                    WHERE ka.detected_at >= date('now', '-6 days')
                    GROUP BY kg.id, kg.name, date(ka.detected_at)
                )
                SELECT 
                    kg.id,
                    kg.name,
                    dates.date,
                    COALESCE(dc.article_count, 0) as count
                FROM keyword_groups kg
                CROSS JOIN dates
                LEFT JOIN daily_counts dc 
                    ON dc.group_id = kg.id 
                    AND dc.detection_date = dates.date
                ORDER BY kg.id, dates.date
            """)
            
            results = cursor.fetchall()
            
            # Process results into the required format
            trends = {}
            for row in results:
                group_id, group_name, date, count = row
                if group_id not in trends:
                    trends[group_id] = {
                        'id': group_id,
                        'name': group_name,
                        'dates': [],
                        'counts': []
                    }
                trends[group_id]['dates'].append(date)
                trends[group_id]['counts'].append(count)
            
            return trends
            
    except Exception as e:
        logger.error(f"Error getting trends: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/toggle-polling")
async def toggle_polling(toggle: PollingToggle, db=Depends(get_database_instance)):
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # First check if settings exist
            cursor.execute("SELECT 1 FROM keyword_monitor_settings WHERE id = 1")
            exists = cursor.fetchone() is not None
            
            if exists:
                # Just update is_enabled if settings exist
                cursor.execute("""
                    UPDATE keyword_monitor_settings 
                    SET is_enabled = ?
                    WHERE id = 1
                """, (toggle.enabled,))
            else:
                # Insert with defaults if no settings exist
                cursor.execute("""
                    INSERT INTO keyword_monitor_settings (
                        id,
                        check_interval,
                        interval_unit,
                        search_fields,
                        language,
                        sort_by,
                        page_size,
                        is_enabled
                    ) VALUES (
                        1,
                        15,
                        60,
                        'title,description,content',
                        'en',
                        'publishedAt',
                        10,
                        ?
                    )
                """, (toggle.enabled,))
            
            conn.commit()
            return {"status": "success", "enabled": toggle.enabled}
            
    except Exception as e:
        logger.error(f"Error toggling polling: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/fix-duplicate-alerts")
async def fix_duplicate_alerts(db=Depends(get_database_instance)):
    """Fix duplicate alerts by removing duplicates and ensuring the unique constraint exists"""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if the unique constraint exists
            cursor.execute("""
                SELECT sql FROM sqlite_master 
                WHERE type='table' AND name='keyword_alerts'
            """)
            table_def = cursor.fetchone()[0]
            
            # If the unique constraint is missing, we need to recreate the table
            if "UNIQUE(keyword_id, article_uri)" not in table_def:
                logger.info("Fixing keyword_alerts table: adding unique constraint")
                
                # Create a temporary table with the correct schema
                cursor.execute("""
                    CREATE TABLE keyword_alerts_temp (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        keyword_id INTEGER NOT NULL,
                        article_uri TEXT NOT NULL,
                        detected_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        is_read INTEGER DEFAULT 0,
                        FOREIGN KEY (keyword_id) REFERENCES monitored_keywords(id) ON DELETE CASCADE,
                        FOREIGN KEY (article_uri) REFERENCES articles(uri) ON DELETE CASCADE,
                        UNIQUE(keyword_id, article_uri)
                    )
                """)
                
                # Copy data to the temporary table, keeping only one row per keyword_id/article_uri pair
                cursor.execute("""
                    INSERT OR IGNORE INTO keyword_alerts_temp (keyword_id, article_uri, detected_at, is_read)
                    SELECT keyword_id, article_uri, MIN(detected_at), MIN(is_read)
                    FROM keyword_alerts
                    GROUP BY keyword_id, article_uri
                """)
                
                # Get the count of rows before and after to report how many duplicates were removed
                cursor.execute("SELECT COUNT(*) FROM keyword_alerts")
                before_count = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM keyword_alerts_temp")
                after_count = cursor.fetchone()[0]
                
                # Drop the original table and rename the temporary one
                cursor.execute("DROP TABLE keyword_alerts")
                cursor.execute("ALTER TABLE keyword_alerts_temp RENAME TO keyword_alerts")
                
                conn.commit()
                
                return {
                    "success": True, 
                    "message": f"Fixed keyword_alerts table: removed {before_count - after_count} duplicate alerts",
                    "duplicates_removed": before_count - after_count
                }
            else:
                # Even if the constraint exists, we should still remove any duplicates
                # that might have been created before the constraint was added
                cursor.execute("""
                    DELETE FROM keyword_alerts
                    WHERE id NOT IN (
                        SELECT MIN(id)
                        FROM keyword_alerts
                        GROUP BY keyword_id, article_uri
                    )
                """)
                
                deleted_count = cursor.rowcount
                conn.commit()
                
                return {
                    "success": True,
                    "message": f"Removed {deleted_count} duplicate alerts",
                    "duplicates_removed": deleted_count
                }
                
    except Exception as e:
        logger.error(f"Error fixing duplicate alerts: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/export-alerts")
async def export_alerts(db=Depends(get_database_instance)):
    try:
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write headers
        writer.writerow([
            'Group Name',
            'Topic',
            'Article Title',
            'Source',
            'URL',
            'Publication Date',
            'Matched Keywords',
            'Detection Time'
        ])
        
        # Get all alerts with related data
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if the keyword_article_matches table exists
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='keyword_article_matches'
            """)
            use_new_table = cursor.fetchone() is not None
            
            if use_new_table:
                # Use the new table structure
                cursor.execute("""
                    SELECT 
                        kg.name as group_name,
                        kg.topic,
                        a.title,
                        a.news_source,
                        a.uri,
                        a.publication_date,
                        (
                            SELECT GROUP_CONCAT(keyword, ', ')
                            FROM monitored_keywords
                            WHERE id IN (SELECT value FROM json_each('['||REPLACE(kam.keyword_ids, ',', ',')||']'))
                        ) as matched_keywords,
                        kam.detected_at
                    FROM keyword_article_matches kam
                    JOIN keyword_groups kg ON kam.group_id = kg.id
                    JOIN articles a ON kam.article_uri = a.uri
                    ORDER BY kam.detected_at DESC
                """)
            else:
                # Use the original table structure
                cursor.execute("""
                    SELECT 
                        kg.name as group_name,
                        kg.topic,
                        a.title,
                        a.news_source,
                        a.uri,
                        a.publication_date,
                        mk.keyword as matched_keyword,
                        ka.detected_at
                    FROM keyword_alerts ka
                    JOIN monitored_keywords mk ON ka.keyword_id = mk.id
                    JOIN keyword_groups kg ON mk.group_id = kg.id
                    JOIN articles a ON ka.article_uri = a.uri
                    ORDER BY ka.detected_at DESC
                """)
            
            # Write data
            for row in cursor.fetchall():
                writer.writerow([
                    row[0],  # group_name
                    row[1],  # topic
                    row[2],  # title
                    row[3],  # news_source
                    row[4],  # uri
                    row[5],  # publication_date
                    row[6],  # matched_keywords
                    row[7]   # detected_at
                ])
        
        # Prepare the output
        output.seek(0)
        
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={
                'Content-Disposition': f'attachment; filename=keyword_alerts_{datetime.now().strftime("%Y-%m-%d")}.csv'
            }
        )
    except Exception as e:
        logger.error(f"Error exporting alerts: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

async def save_keyword_alert(db: Database, article_data: dict):
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO keyword_alert_articles 
            (url, title, summary, source, topic, keywords)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            article_data['url'],
            article_data['title'],
            article_data['summary'],
            article_data['source'],
            article_data['topic'],
            ','.join(article_data['matched_keywords'])
        ))

@router.post("/alerts/{alert_id}/unread")
async def mark_alert_unread(alert_id: int, db: Database = Depends(get_database_instance)):
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if the alert is in the keyword_article_matches table
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='keyword_article_matches'
            """)
            use_new_table = cursor.fetchone() is not None
            
            if use_new_table:
                # Check if the alert ID is in the new table
                cursor.execute("SELECT 1 FROM keyword_article_matches WHERE id = ?", (alert_id,))
                if cursor.fetchone():
                    # Update the new table
                    cursor.execute(
                        "UPDATE keyword_article_matches SET is_read = 0 WHERE id = ?",
                        (alert_id,)
                    )
                else:
                    # Update the old table
                    cursor.execute(
                        "UPDATE keyword_alerts SET is_read = 0 WHERE id = ?",
                        (alert_id,)
                    )
            else:
                # Update the old table
                cursor.execute(
                    "UPDATE keyword_alerts SET is_read = 0 WHERE id = ?",
                    (alert_id,)
                )
            
            conn.commit()
            return {"success": True}
    except Exception as e:
        logger.error(f"Error in mark_alert_unread: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/alerts/{topic}")
async def get_group_alerts(
    topic: str,
    group_id: int,
    show_read: bool = False,
    db: Database = Depends(get_database_instance)
):
    """Get alerts for a specific keyword group."""
    try:
        # Initialize media bias for article enrichment
        media_bias = MediaBias(db)
        logger.info(f"Processing alerts for topic '{topic}', group ID {group_id}")
        
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Determine if we're using the new table structure
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='keyword_article_matches'")
            use_new_table = cursor.fetchone() is not None
            
            if use_new_table:
                read_condition = "" if show_read else "AND ka.is_read = 0"
                
                # Using new structure (keyword_article_matches table)
                cursor.execute(f"""
                    SELECT 
                        ka.id, 
                        ka.article_uri,
                        ka.group_id,
                        ka.keyword_ids,
                        ka.is_read,
                        ka.detected_at,
                        a.title,
                        a.summary,
                        a.uri,
                        a.news_source,
                        a.publication_date,
                        a.topic_alignment_score,
                        a.keyword_relevance_score,
                        a.confidence_score,
                        a.overall_match_explanation,
                        a.extracted_article_topics,
                        a.extracted_article_keywords
                    FROM keyword_article_matches ka
                    JOIN articles a ON ka.article_uri = a.uri
                    WHERE ka.group_id = ? {read_condition}
                    ORDER BY ka.detected_at DESC
                """, (group_id,))
            else:
                # Fallback to old structure (keyword_alerts table)
                read_condition = "" if show_read else "AND ka.is_read = 0"
                cursor.execute(f"""
                    SELECT 
                        ka.id, 
                        ka.article_uri,
                        ka.keyword_id,
                        mk.keyword as matched_keyword,
                        ka.is_read,
                        ka.detected_at,
                        a.title,
                        a.summary,
                        a.uri,
                        a.news_source,
                        a.publication_date
                    FROM keyword_alerts ka
                    JOIN articles a ON ka.article_uri = a.uri
                    JOIN monitored_keywords mk ON ka.keyword_id = mk.id
                    WHERE mk.group_id = ? {read_condition}
                    ORDER BY ka.detected_at DESC
                """, (group_id,))
            
            # Store the main query results before executing count queries
            main_query_results = cursor.fetchall()
            
            # Get unread count for this group
            if use_new_table:
                cursor.execute("""
                    SELECT COUNT(ka.id)
                    FROM keyword_article_matches ka
                    WHERE ka.group_id = ? AND ka.is_read = 0
                """, (group_id,))
            else:
                cursor.execute("""
                    SELECT COUNT(ka.id)
                    FROM keyword_alerts ka
                    JOIN monitored_keywords mk ON ka.keyword_id = mk.id
                    WHERE mk.group_id = ? AND ka.is_read = 0
                """, (group_id,))
                
            unread_count = cursor.fetchone()[0]
            
            # Get total count for this group
            if use_new_table:
                cursor.execute("""
                    SELECT COUNT(ka.id)
                    FROM keyword_article_matches ka
                    WHERE ka.group_id = ?
                """, (group_id,))
            else:
                cursor.execute("""
                    SELECT COUNT(ka.id)
                    FROM keyword_alerts ka
                    JOIN monitored_keywords mk ON ka.keyword_id = mk.id
                    WHERE mk.group_id = ?
                """, (group_id,))
                
            total_count = cursor.fetchone()[0]
            
            alerts = []
            for alert in main_query_results:
                if use_new_table:
                    alert_id, article_uri, group_id_from_alert, keyword_ids, is_read, detected_at, title, summary, uri, news_source, publication_date, topic_alignment_score, keyword_relevance_score, confidence_score, overall_match_explanation, extracted_article_topics, extracted_article_keywords = alert
                    
                    # Get matched keywords from the keyword_ids (comma-separated list)
                    matched_keywords = []
                    if keyword_ids:
                        keyword_id_list = [int(kid.strip()) for kid in keyword_ids.split(',') if kid.strip()]
                        if keyword_id_list:
                            placeholders = ','.join(['?'] * len(keyword_id_list))
                            cursor.execute(f"""
                                SELECT DISTINCT keyword
                                FROM monitored_keywords
                                WHERE id IN ({placeholders})
                            """, keyword_id_list)
                            matched_keywords = [kw[0] for kw in cursor.fetchall()]
                    
                    matched_keyword = matched_keywords[0] if matched_keywords else "Unknown"
                else:
                    alert_id, article_uri, keyword_id, matched_keyword, is_read, detected_at, title, summary, uri, news_source, publication_date = alert
                    topic_alignment_score = keyword_relevance_score = confidence_score = None
                    overall_match_explanation = extracted_article_topics = extracted_article_keywords = None
                    
                    # Get all matched keywords for this article and group
                    cursor.execute("""
                        SELECT DISTINCT mk.keyword
                        FROM keyword_alerts ka
                        JOIN monitored_keywords mk ON ka.keyword_id = mk.id
                        WHERE ka.article_uri = ? AND mk.group_id = ?
                    """, (article_uri, group_id))
                    
                    matched_keywords = [kw[0] for kw in cursor.fetchall()]
                
                # Try to get media bias data using both source name and URL with multiple variations
                logging.debug(f"Looking up media bias for source: {news_source}")
                
                # Check for Vanity Fair specifically
                if news_source and ('vanity fair' in news_source.lower() or 'vanityfair' in news_source.lower().replace(' ', '')):
                    logger.info(f"Found Vanity Fair article: {title}")
                
                # Try multiple source name variations for better matching
                source_variations = []
                if news_source:
                    # Original source name
                    source_variations.append(news_source)
                    
                    # Common source name variations
                    source_lower = news_source.lower()
                    source_variations.extend([
                        source_lower,                          # lowercase
                        source_lower.replace(" ", ""),         # no spaces
                        source_lower.replace(" ", "."),        # dots instead of spaces
                        source_lower + ".com",                 # add .com
                        "www." + source_lower,                 # add www
                        "www." + source_lower + ".com",        # add www and .com
                    ])
                
                    # Extra manipulations for specific sources
                    if "forbes" in source_lower:
                        source_variations.append("forbes.com")
                    elif "cnn" in source_lower:
                        source_variations.append("cnn.com")
                    elif "yahoo" in source_lower:
                        source_variations.append("yahoo.com")
                    elif "verge" in source_lower:
                        source_variations.append("theverge.com")
                
                # Try all source variations
                bias_data = None
                source_found = None
                
                for variation in source_variations:
                    logger.debug(f"Trying source variation: {variation}")
                    bias_data = media_bias.get_bias_for_source(variation)
                    if bias_data:
                        logger.info(f"Found bias data using variation '{variation}': {bias_data}")
                        source_found = variation
                        break
                
                # If no match with source variations, try with the URI
                if not bias_data and uri:
                    logger.debug(f"No bias data found for source variations, trying URI: {uri}")
                    bias_data = media_bias.get_bias_for_source(uri)
                    if bias_data:
                        logger.info(f"Found bias data using URI '{uri}': {bias_data}")
                        source_found = uri
                
                # If we found bias data, ensure the source is enabled
                if bias_data and 'enabled' in bias_data and bias_data['enabled'] == 0:
                    logger.info(f"Automatically enabling media bias source: {bias_data.get('source')}")
                    try:
                        with db.get_connection() as conn:
                            cursor = conn.cursor()
                            cursor.execute(
                                "UPDATE mediabias SET enabled = 1 WHERE source = ?",
                                (bias_data.get('source'),)
                            )
                            conn.commit()
                            logger.info(f"Successfully enabled media bias source: {bias_data.get('source')}")
                            # Update the bias data to show it's now enabled
                            bias_data['enabled'] = 1
                    except Exception as e:
                        logger.error(f"Error enabling media bias source {bias_data.get('source')}: {e}")
                elif not bias_data:
                    logger.info(f"No bias data found for source '{news_source}' or its variations")
                
                article_data = {
                    "url": uri,
                    "uri": article_uri,
                    "title": title,
                    "summary": summary,
                    "source": news_source,
                    "publication_date": publication_date,
                    "topic_alignment_score": topic_alignment_score,
                    "keyword_relevance_score": keyword_relevance_score,
                    "confidence_score": confidence_score,
                    "overall_match_explanation": overall_match_explanation,
                    "extracted_article_topics": extracted_article_topics,
                    "extracted_article_keywords": extracted_article_keywords
                }
                
                # Add bias data if found
                if bias_data:
                    logger.debug(f"Found bias data for {news_source}: {bias_data.get('bias')}, {bias_data.get('factual_reporting')}")
                    article_data["bias"] = bias_data.get("bias")
                    article_data["factual_reporting"] = bias_data.get("factual_reporting")
                    article_data["mbfc_credibility_rating"] = bias_data.get("mbfc_credibility_rating")
                    article_data["bias_country"] = bias_data.get("country")
                    article_data["press_freedom"] = bias_data.get("press_freedom")
                    article_data["media_type"] = bias_data.get("media_type")
                    article_data["popularity"] = bias_data.get("popularity")
                    
                    # Double check the bias data was actually assigned
                    logger.info(f"After assigning, article_data has bias: {article_data.get('bias')}, factual: {article_data.get('factual_reporting')}")
                else:
                    logger.debug(f"No media bias data found for {news_source}")
                
                alerts.append({
                    "id": alert_id,
                    "article": article_data,
                    "matched_keyword": matched_keyword,
                    "matched_keywords": matched_keywords,
                    "is_read": bool(is_read),
                    "detected_at": detected_at
                })
            
            # Get group name
            cursor.execute("SELECT name FROM keyword_groups WHERE id = ?", (group_id,))
            group_row = cursor.fetchone()
            group_name = group_row[0] if group_row else "Unknown Group"
            
            # Log the full response data
            response_data = {
                "topic": topic,
                "group_id": group_id, 
                "group_name": group_name,
                "alerts": [{"id": a["id"], "source": a["article"]["source"], "has_bias": bool(a["article"].get("bias"))} for a in alerts],
                "unread_count": unread_count,
                "total_count": total_count
            }
            logger.info(f"Returning response: {response_data}")
            
            return {
                "topic": topic,
                "group_id": group_id, 
                "group_name": group_name,
                "alerts": alerts,
                "unread_count": unread_count,
                "total_count": total_count
            }
            
    except Exception as e:
        logger.error(f"Error getting group alerts: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/articles/by-topic/{topic_name}")
async def delete_articles_by_topic(topic_name: str, db=Depends(get_database_instance)):
    """Delete all articles associated with a specific topic and their related data"""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if the keyword_article_matches table exists
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='keyword_article_matches'
            """)
            use_new_table = cursor.fetchone() is not None
            
            alerts_deleted = 0
            articles_deleted = 0
            
            # First find relevant article URIs
            article_uris = []
            
            # From news_search_results
            cursor.execute("""
                SELECT article_uri FROM news_search_results 
                WHERE topic = ?
            """, (topic_name,))
            article_uris.extend([row[0] for row in cursor.fetchall()])
            
            # From paper_search_results
            cursor.execute("""
                SELECT article_uri FROM paper_search_results 
                WHERE topic = ?
            """, (topic_name,))
            article_uris.extend([row[0] for row in cursor.fetchall()])
            
            # Direct topic reference if the column exists
            cursor.execute("PRAGMA table_info(articles)")
            columns = cursor.fetchall()
            has_topic_column = any(col[1] == 'topic' for col in columns)
            
            if has_topic_column:
                cursor.execute("SELECT uri FROM articles WHERE topic = ?", (topic_name,))
                article_uris.extend([row[0] for row in cursor.fetchall()])
            
            # Remove duplicates
            article_uris = list(set(article_uris))
            
            if article_uris:
                # Delete related keyword alerts first
                if use_new_table:
                    for uri in article_uris:
                        cursor.execute("DELETE FROM keyword_article_matches WHERE article_uri = ?", (uri,))
                        alerts_deleted += cursor.rowcount
                else:
                    for uri in article_uris:
                        cursor.execute("DELETE FROM keyword_alerts WHERE article_uri = ?", (uri,))
                        alerts_deleted += cursor.rowcount
                
                # Delete news_search_results
                cursor.execute("DELETE FROM news_search_results WHERE topic = ?", (topic_name,))
                
                # Delete paper_search_results
                cursor.execute("DELETE FROM paper_search_results WHERE topic = ?", (topic_name,))
                
                # Delete articles
                for uri in article_uris:
                    cursor.execute("DELETE FROM articles WHERE uri = ?", (uri,))
                    if cursor.rowcount > 0:
                        articles_deleted += cursor.rowcount
            
            conn.commit()
            return {
                "success": True, 
                "articles_deleted": articles_deleted,
                "alerts_deleted": alerts_deleted
            }
    except Exception as e:
        logging.error(f"Error deleting articles for topic {topic_name}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/bluesky-posts")
async def get_bluesky_posts(
    query: str,
    topic: str,
    count: int = 10,
    db: Database = Depends(get_database_instance)
):
    """Fetch Bluesky posts for a given query and topic."""
    try:
        # Log what we're receiving in the request
        logger.debug(f"Bluesky posts request: query='{query}', topic='{topic}', count={count}")
        
        # Import the collector here to avoid circular imports
        from app.collectors.bluesky_collector import BlueskyCollector
        
        try:
            bluesky_collector = BlueskyCollector()
            posts = await bluesky_collector.search_articles(
                query=query,
                topic=topic,
                max_results=count
            )
            
            # Log the raw data for debugging
            logger.debug(f"Bluesky returned {len(posts)} posts")
            
            # Format the posts for display with safer access to fields
            formatted_posts = []
            for post in posts:
                try:
                    # Create a post with defaults for all required fields
                    formatted_post = {
                        "title": "Untitled Post",
                        "date": "",
                        "source": "Bluesky",
                        "summary": "No content available",
                        "url": "#",
                        "author": "Unknown",
                        "image_url": None
                    }
                    
                    # Safely update each field if available
                    if post.get('title'):
                        formatted_post["title"] = post.get('title')
                        
                    if post.get('published_date'):
                        formatted_post["date"] = post.get('published_date')
                        
                    if post.get('summary'):
                        formatted_post["summary"] = post.get('summary')
                        
                    if post.get('url'):
                        formatted_post["url"] = post.get('url')
                    
                    # Handle authors safely
                    authors = post.get('authors', [])
                    if authors and len(authors) > 0:
                        formatted_post["author"] = authors[0]
                    
                    # Handle images safely
                    raw_data = post.get('raw_data', {})
                    images = raw_data.get('images', [])
                    if images and len(images) > 0 and isinstance(images[0], dict):
                        url = images[0].get('url')
                        if url:
                            formatted_post["image_url"] = url
                    
                    formatted_posts.append(formatted_post)
                except Exception as post_error:
                    # Log any errors processing individual posts but continue
                    logger.error(f"Error formatting Bluesky post: {str(post_error)}")
                    continue
            
            # Return the posts we were able to process
            return JSONResponse(content=formatted_posts)
        
        except ValueError as e:
            if "credentials not configured" in str(e):
                logger.warning("Bluesky credentials not configured - returning empty results")
                return JSONResponse(content=[])
            else:
                logger.error(f"Bluesky collector error: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Error with Bluesky collector: {str(e)}")
                
    except Exception as e:
        logger.error(f"Error fetching Bluesky posts: {str(e)}")
        logger.exception("Full exception details:")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/clean-orphaned-topics")
async def clean_orphaned_topics(db=Depends(get_database_instance)):
    """Find and clean up orphaned topic data by comparing keyword groups against the main topics list"""
    try:
        # Get active topics list from config
        try:
            config = load_config()
            active_topics = set(topic["name"] for topic in config.get("topics", []))
        except Exception as e:
            logger.error(f"Error loading config: {str(e)}")
            active_topics = set()
        
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if keyword_groups table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='keyword_groups'")
            if not cursor.fetchone():
                return {
                    "status": "success",
                    "message": "No keyword_groups table found",
                    "orphaned_topics": []
                }
            
            # Get all topics referenced in keyword groups
            try:
                cursor.execute("SELECT DISTINCT topic FROM keyword_groups")
                keyword_topics = set(row[0] for row in cursor.fetchall())
            except sqlite3.OperationalError as e:
                logger.error(f"Database error: {str(e)}")
                return {
                    "status": "error",
                    "message": f"Database error: {str(e)}",
                    "orphaned_topics": []
                }
            
            # Find orphaned topics (in keyword_groups but not in active topics)
            orphaned_topics = keyword_topics - active_topics
            
            if not orphaned_topics:
                return {
                    "status": "success",
                    "message": "No orphaned topics found",
                    "orphaned_topics": []
                }
            
            # Clean up each orphaned topic
            cleanup_results = {}
            for topic in orphaned_topics:
                # Clean up keyword groups
                try:
                    groups_result = await delete_groups_by_topic(topic, db)
                    cleanup_results[topic] = {
                        "groups_deleted": groups_result.get("groups_deleted", 0),
                        "keywords_deleted": groups_result.get("keywords_deleted", 0),
                        "alerts_deleted": groups_result.get("alerts_deleted", 0)
                    }
                except Exception as e:
                    logger.error(f"Error cleaning up orphaned topic {topic}: {str(e)}")
                    cleanup_results[topic] = {"error": str(e)}
            
            return {
                "status": "success",
                "message": f"Cleaned up {len(orphaned_topics)} orphaned topics",
                "orphaned_topics": list(orphaned_topics),
                "cleanup_results": cleanup_results
            }
            
    except Exception as e:
        logger.error(f"Error cleaning orphaned topics: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/clean-orphaned-articles")
async def clean_orphaned_articles(db=Depends(get_database_instance)):
    """Find and clean up orphaned articles that are no longer associated with any topic"""
    try:
        try:
            config = load_config()
            active_topics = set(topic["name"] for topic in config.get("topics", []))
        except Exception as e:
            logger.error(f"Error loading config: {str(e)}")
            active_topics = set()
        
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if articles table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='articles'")
            if not cursor.fetchone():
                return {
                    "status": "success",
                    "message": "No articles table found",
                    "orphaned_count": 0
                }
            
            # Get all article URIs that might be orphaned
            orphaned_article_uris = set()
            
            # Check if articles table has a topic column
            try:
                cursor.execute("PRAGMA table_info(articles)")
                columns = cursor.fetchall()
                has_topic_column = any(col[1] == 'topic' for col in columns)
                
                # First, check direct topic references if the column exists
                if has_topic_column:
                    try:
                        cursor.execute("""
                            SELECT uri, topic FROM articles
                            WHERE topic IS NOT NULL AND topic != ''
                        """)
                        
                        for row in cursor.fetchall():
                            uri, topic = row
                            if topic not in active_topics:
                                orphaned_article_uris.add(uri)
                    except sqlite3.OperationalError as e:
                        logger.error(f"Error querying articles table: {str(e)}")
            except Exception as e:
                logger.error(f"Error checking articles schema: {str(e)}")
            
            # Check if news_search_results table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='news_search_results'")
            if cursor.fetchone():
                try:
                    # Next, check news_search_results references
                    cursor.execute("""
                        SELECT nsr.article_uri, nsr.topic
                        FROM news_search_results nsr
                        GROUP BY nsr.article_uri, nsr.topic
                    """)
                    
                    for row in cursor.fetchall():
                        uri, topic = row
                        if topic not in active_topics:
                            orphaned_article_uris.add(uri)
                except sqlite3.OperationalError as e:
                    logger.error(f"Error querying news_search_results: {str(e)}")
            
            # Check if paper_search_results table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='paper_search_results'")
            if cursor.fetchone():
                try:
                    # Check paper_search_results references
                    cursor.execute("""
                        SELECT psr.article_uri, psr.topic
                        FROM paper_search_results psr
                        GROUP BY psr.article_uri, psr.topic
                    """)
                    
                    for row in cursor.fetchall():
                        uri, topic = row
                        if topic not in active_topics:
                            orphaned_article_uris.add(uri)
                except sqlite3.OperationalError as e:
                    logger.error(f"Error querying paper_search_results: {str(e)}")
            
            # Now check for articles that are not in any search results
            try:
                has_news_results = False
                has_paper_results = False
                
                # Check if search result tables exist
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='news_search_results'")
                has_news_results = cursor.fetchone() is not None
                
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='paper_search_results'")
                has_paper_results = cursor.fetchone() is not None
                
                if has_news_results or has_paper_results:
                    query = """
                        SELECT a.uri FROM articles a
                        WHERE 1=1
                    """
                    
                    if has_news_results:
                        query += """ AND NOT EXISTS (
                            SELECT 1 FROM news_search_results nsr WHERE nsr.article_uri = a.uri
                        )"""
                    
                    if has_paper_results:
                        query += """ AND NOT EXISTS (
                            SELECT 1 FROM paper_search_results psr WHERE psr.article_uri = a.uri
                        )"""
                    
                    cursor.execute(query)
                    orphaned_article_uris.update(row[0] for row in cursor.fetchall())
            except sqlite3.OperationalError as e:
                logger.error(f"Error checking articles without search results: {str(e)}")
            
            if not orphaned_article_uris:
                return {
                    "status": "success",
                    "message": "No orphaned articles found",
                    "orphaned_count": 0
                }
            
            # Clean up the orphaned articles
            alerts_deleted = 0
            articles_deleted = 0
            
            # Check if keyword_article_matches table exists
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='keyword_article_matches'
            """)
            use_new_table = cursor.fetchone() is not None
            
            # Process articles in smaller batches to avoid SQL parameter limits
            batch_size = 100
            article_batches = [list(orphaned_article_uris)[i:i+batch_size] 
                               for i in range(0, len(orphaned_article_uris), batch_size)]
            
            # Delete associated alerts first
            for batch in article_batches:
                try:
                    for uri in batch:
                        if use_new_table:
                            cursor.execute("DELETE FROM keyword_article_matches WHERE article_uri = ?", (uri,))
                            alerts_deleted += cursor.rowcount
                        else:
                            cursor.execute("DELETE FROM keyword_alerts WHERE article_uri = ?", (uri,))
                            alerts_deleted += cursor.rowcount
                except sqlite3.OperationalError as e:
                    logger.error(f"Error deleting alerts: {str(e)}")
            
            # Delete from search results tables
            for batch in article_batches:
                try:
                    placeholders = ','.join(['?'] * len(batch))
                    
                    # Check if tables exist before attempting delete
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='news_search_results'")
                    if cursor.fetchone():
                        cursor.execute(f"DELETE FROM news_search_results WHERE article_uri IN ({placeholders})", batch)
                    
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='paper_search_results'")
                    if cursor.fetchone():
                        cursor.execute(f"DELETE FROM paper_search_results WHERE article_uri IN ({placeholders})", batch)
                except sqlite3.OperationalError as e:
                    logger.error(f"Error deleting search results: {str(e)}")
            
            # Finally delete the articles
            for batch in article_batches:
                try:
                    placeholders = ','.join(['?'] * len(batch))
                    cursor.execute(f"DELETE FROM articles WHERE uri IN ({placeholders})", batch)
                    articles_deleted += cursor.rowcount
                except sqlite3.OperationalError as e:
                    logger.error(f"Error deleting articles: {str(e)}")
            
            conn.commit()
            
            return {
                "status": "success",
                "message": f"Cleaned up {articles_deleted} orphaned articles",
                "orphaned_count": articles_deleted,
                "alerts_deleted": alerts_deleted
            }
            
    except Exception as e:
        logger.error(f"Error cleaning orphaned articles: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/clean-all-orphaned")
async def clean_all_orphaned(db=Depends(get_database_instance)):
    """Clean up all orphaned data - both topics and articles in one operation"""
    try:
        # First clean orphaned topics
        try:
            topics_result = await clean_orphaned_topics(db)
            logger.info(f"Completed orphaned topics cleanup: {topics_result}")
        except Exception as e:
            logger.error(f"Error in topics cleanup: {str(e)}")
            topics_result = {
                "status": "error",
                "message": f"Error cleaning up orphaned topics: {str(e)}",
                "orphaned_topics": []
            }
        
        # Then clean orphaned articles
        try:
            articles_result = await clean_orphaned_articles(db)
            logger.info(f"Completed orphaned articles cleanup: {articles_result}")
        except Exception as e:
            logger.error(f"Error in articles cleanup: {str(e)}")
            articles_result = {
                "status": "error",
                "message": f"Error cleaning up orphaned articles: {str(e)}",
                "orphaned_count": 0
            }
        
        return {
            "status": "success",
            "topics_result": topics_result,
            "articles_result": articles_result
        }
    except Exception as e:
        logger.error(f"Error cleaning all orphaned data: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status")
async def get_keyword_monitor_status(db=Depends(get_database_instance)):
    """Get the current status of the keyword monitor including background task info."""
    try:
        # Get background task status
        bg_task_status = get_task_status()
        
        # Get monitor settings
        settings_data = get_monitor_settings(db)
        
        # Get API usage info
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT requests_today, last_reset_date 
                FROM keyword_monitor_status 
                WHERE id = 1
            """)
            status_row = cursor.fetchone()
            
            api_usage = {
                "requests_today": status_row[0] if status_row else 0,
                "limit": settings_data.get('daily_request_limit', 100),
                "last_reset_date": status_row[1] if status_row else None
            }
        
        return {
            "background_task": bg_task_status,
            "settings": settings_data,
            "api_usage": api_usage
        }
    except Exception as e:
        logger.error(f"Error getting keyword monitor status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/analyze-relevance")
async def analyze_relevance(
    request: Request,
    session=Depends(verify_session),
    db: Database = Depends(get_database_instance)
):
    """Analyze relevance of articles using the selected LLM model."""
    try:
        # Check if enterprise features are active
        if not db.is_enterprise_active():
            raise HTTPException(
                status_code=403, 
                detail="Relevance analysis is an enterprise feature. Please activate your license."
            )
        
        # Parse request body
        body = await request.json()
        model_name = body.get("model_name")
        topic = body.get("topic")
        group_id = body.get("group_id")
        article_uris = body.get("article_uris", [])
        
        if not model_name:
            raise HTTPException(status_code=400, detail="Model name is required")
        
        if not topic:
            raise HTTPException(status_code=400, detail="Topic is required")
        
        if not article_uris:
            raise HTTPException(status_code=400, detail="At least one article URI is required")
        
        logger.info(f"Starting relevance analysis for {len(article_uris)} articles using model: {model_name}")
        
        # Initialize relevance calculator
        from app.enterprise.relevance import RelevanceCalculator, RelevanceCalculatorError
        
        try:
            calculator = RelevanceCalculator(model_name)
        except RelevanceCalculatorError as e:
            logger.error(f"Failed to initialize relevance calculator: {str(e)}")
            raise HTTPException(status_code=400, detail=f"Failed to initialize model: {str(e)}")
        
        # Get keywords for the topic/group
        keywords_str = ""
        if group_id:
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT GROUP_CONCAT(keyword, ', ') as keywords
                    FROM monitored_keywords 
                    WHERE group_id = ?
                """, (group_id,))
                result = cursor.fetchone()
                keywords_str = result[0] if result and result[0] else ""
        
        # Fetch articles and their content
        articles_to_analyze = []
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            for uri in article_uris:
                # Get article data
                cursor.execute("""
                    SELECT uri, title, news_source, summary
                    FROM articles 
                    WHERE uri = ?
                """, (uri,))
                article_row = cursor.fetchone()
                
                if not article_row:
                    logger.warning(f"Article not found: {uri}")
                    continue
                
                # Get raw content if available
                cursor.execute("""
                    SELECT raw_markdown 
                    FROM raw_articles 
                    WHERE uri = ?
                """, (uri,))
                raw_row = cursor.fetchone()
                
                content = raw_row[0] if raw_row else article_row[3]  # Use raw content or fallback to summary
                
                articles_to_analyze.append({
                    "uri": article_row[0],
                    "title": article_row[1] or "",
                    "source": article_row[2] or "",
                    "content": content or ""
                })
        
        if not articles_to_analyze:
            raise HTTPException(status_code=404, detail="No valid articles found for analysis")
        
        # Perform relevance analysis
        try:
            analyzed_articles = calculator.analyze_articles_batch(
                articles_to_analyze, 
                topic, 
                keywords_str
            )
        except RelevanceCalculatorError as e:
            logger.error(f"Relevance analysis failed: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")
        
        # Save results to database
        updated_count = 0
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            for article in analyzed_articles:
                try:
                    # Convert lists to JSON strings for storage
                    extracted_topics_json = json.dumps(article.get("extracted_article_topics", []))
                    extracted_keywords_json = json.dumps(article.get("extracted_article_keywords", []))
                    
                    cursor.execute("""
                        UPDATE articles SET
                            topic_alignment_score = ?,
                            keyword_relevance_score = ?,
                            confidence_score = ?,
                            overall_match_explanation = ?,
                            extracted_article_topics = ?,
                            extracted_article_keywords = ?
                        WHERE uri = ?
                    """, (
                        article.get("topic_alignment_score"),
                        article.get("keyword_relevance_score"),
                        article.get("confidence_score"),
                        article.get("overall_match_explanation"),
                        extracted_topics_json,
                        extracted_keywords_json,
                        article["uri"]
                    ))
                    
                    if cursor.rowcount > 0:
                        updated_count += 1
                        
                except Exception as e:
                    logger.error(f"Failed to save relevance data for article {article['uri']}: {str(e)}")
                    continue
            
            conn.commit()
        
        logger.info(f"Relevance analysis completed. Updated {updated_count} articles.")
        
        return {
            "success": True,
            "analyzed_count": len(analyzed_articles),
            "updated_count": updated_count,
            "model_used": model_name,
            "topic": topic,
            "keywords": keywords_str,
            "results": [
                {
                    "uri": article["uri"],
                    "title": article["title"],
                    "topic_alignment_score": article.get("topic_alignment_score", 0.0),
                    "keyword_relevance_score": article.get("keyword_relevance_score", 0.0),
                    "confidence_score": article.get("confidence_score", 0.0),
                    "overall_match_explanation": article.get("overall_match_explanation", "")
                }
                for article in analyzed_articles
            ]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in relevance analysis endpoint: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

def get_monitor_settings(db: Database) -> dict:
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                check_interval,
                interval_unit,
                search_fields,
                language,
                sort_by,
                page_size,
                is_enabled,
                daily_request_limit,
                search_date_range
            FROM keyword_monitor_settings 
            WHERE id = 1
        """)
        row = cursor.fetchone()
        
        if row:
            return {
                "check_interval": row[0],
                "interval_unit": row[1],
                "search_fields": row[2],
                "language": row[3],
                "sort_by": row[4],
                "page_size": row[5],
                "is_enabled": bool(row[6]),
                "daily_request_limit": row[7],
                "search_date_range": row[8],
                "check_interval_seconds": row[0] * row[1]
            }
        else:
            # Return default values if no settings found
            return {
                "check_interval": 15,
                "interval_unit": 60,
                "search_fields": "title,description,content",
                "language": "en",
                "sort_by": "publishedAt",
                "page_size": 10,
                "is_enabled": True,
                "daily_request_limit": 100,
                "search_date_range": 7,
                "check_interval_seconds": 900
            }

def format_interval(seconds):
    """Format interval in seconds to a human-readable string"""
    if seconds < 60:
        return f"{seconds} seconds"
    elif seconds < 3600:
        minutes = seconds // 60
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    elif seconds < 86400:
        hours = seconds // 3600
        return f"{hours} hour{'s' if hours != 1 else ''}"
    else:
        days = seconds // 86400
        return f"{days} day{'s' if days != 1 else ''}" 