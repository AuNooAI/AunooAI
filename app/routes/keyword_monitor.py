from fastapi import APIRouter, HTTPException, Depends, Request
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
from app.database import Database, get_database_instance
from app.tasks.keyword_monitor import KeywordMonitor
from app.security.session import verify_session
import logging
import json
import traceback
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
import io
import csv
from pathlib import Path
import sqlite3

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
    """Delete all keyword groups associated with a specific topic"""
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
            
            # Delete all keyword groups for this topic
            cursor.execute("DELETE FROM keyword_groups WHERE topic = ?", (topic_name,))
            
            conn.commit()
            return {"success": True, "groups_deleted": groups_deleted}
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
        monitor = KeywordMonitor(db)
        await monitor.check_keywords()
        return {"status": "success"}
    except ValueError as e:
        if "Rate limit exceeded" in str(e) or "request limit reached" in str(e):
            # Return a specific status code for rate limiting
            raise HTTPException(
                status_code=429,  # Too Many Requests
                detail="API daily request limit reached. Please try again tomorrow."
            )
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error checking keywords: {str(e)}")
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
            
            # Modify the query to optionally include read articles
            read_condition = "" if show_read else "AND ka.is_read = 0"
            
            cursor.execute(f"""
                SELECT ka.*, a.*, mk.keyword as matched_keyword
                FROM keyword_alerts ka
                JOIN articles a ON ka.article_uri = a.uri
                JOIN monitored_keywords mk ON ka.keyword_id = mk.id
                WHERE 1=1 {read_condition}
                ORDER BY ka.detected_at DESC
            """)
            
            alerts = cursor.fetchall()
            
            # Format alerts with matched keywords
            formatted_alerts = []
            for alert in alerts:
                formatted_alerts.append({
                    'id': alert[0],
                    'detected_at': alert[1],
                    'matched_keywords': [alert[2]],  # Add matched keyword
                    'article': {
                        'url': alert[6],
                        'title': alert[7],
                        'source': alert[8],
                        'publication_date': alert[9],
                        'summary': alert[10]
                    }
                })
            
            return templates.TemplateResponse(
                "keyword_alerts.html",
                {
                    "request": request,
                    "alerts": formatted_alerts,
                    "session": session
                }
            )
            
    except Exception as e:
        logger.error(f"Error fetching keyword alerts: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/keyword-alerts", response_class=HTMLResponse)
async def keyword_alerts_page(request: Request, session=Depends(verify_session)):
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get all groups with their alerts and status
            cursor.execute("""
                WITH alert_counts AS (
                    SELECT 
                        kg.id as group_id,
                        COUNT(DISTINCT CASE WHEN ka.is_read = 0 THEN ka.id END) as unread_count,
                        COUNT(DISTINCT ka.id) as total_count
                    FROM keyword_groups kg
                    LEFT JOIN monitored_keywords mk ON kg.id = mk.group_id
                    LEFT JOIN keyword_alerts ka ON mk.id = ka.keyword_id
                    GROUP BY kg.id
                )
                SELECT 
                    kg.id,
                    kg.name,
                    kg.topic,
                    ac.unread_count,
                    ac.total_count,
                    (
                        SELECT GROUP_CONCAT(keyword, '||')
                        FROM monitored_keywords
                        WHERE group_id = kg.id
                    ) as keywords
                FROM keyword_groups kg
                LEFT JOIN alert_counts ac ON kg.id = ac.group_id
                ORDER BY ac.unread_count DESC, kg.name
            """)
            
            groups = []
            for row in cursor.fetchall():
                group = {
                    'id': row[0],
                    'name': row[1],
                    'topic': row[2],
                    'unread_count': row[3] or 0,
                    'total_count': row[4] or 0,
                    'keywords': row[5].split('||') if row[5] else [],
                    'alerts': []
                }
                # ... rest of the group processing ...
                groups.append(group)
            
            return templates.TemplateResponse(
                "keyword_alerts.html",
                {
                    "request": request,
                    "groups": groups,
                    "session": session
                }
            )
            
    except Exception as e:
        logger.error(f"Error loading keyword alerts page: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

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
                    "is_enabled": settings[7],
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
    try:
        with db.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Check if the keyword_article_matches table exists
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='keyword_article_matches'
            """)
            use_new_table = cursor.fetchone() is not None
            
            if use_new_table:
                # Get total count for this specific group using the new table
                cursor.execute("""
                    SELECT COUNT(DISTINCT id) as total
                    FROM keyword_article_matches
                    WHERE group_id = ?
                """, (group_id,))
                total_count = cursor.fetchone()['total']
                
                # Get unread count for this specific group using the new table
                cursor.execute("""
                    SELECT COUNT(DISTINCT id) as unread_count
                    FROM keyword_article_matches
                    WHERE group_id = ? AND is_read = 0
                """, (group_id,))
                unread_count = cursor.fetchone()['unread_count']
                
                # Get filtered alerts for this group using the new table
                read_condition = "" if show_read else "AND kam.is_read = 0"
                cursor.execute(f"""
                    SELECT 
                        kam.id,
                        kam.is_read,
                        kam.detected_at,
                        kam.keyword_ids,
                        a.uri,
                        a.title,
                        a.summary,
                        a.news_source,
                        a.publication_date,
                        (
                            SELECT GROUP_CONCAT(keyword, '||')
                            FROM monitored_keywords
                            WHERE id IN (SELECT value FROM json_each('['||REPLACE(kam.keyword_ids, ',', ',')||']'))
                        ) as matched_keywords
                    FROM keyword_article_matches kam
                    JOIN articles a ON kam.article_uri = a.uri
                    JOIN keyword_groups kg ON kam.group_id = kg.id
                    WHERE kg.topic = ? AND kam.group_id = ? {read_condition}
                    ORDER BY kam.detected_at DESC
                """, (topic, group_id))
                
                alerts = []
                for row in cursor.fetchall():
                    row_dict = dict(row)
                    
                    # Parse matched keywords
                    keywords_list = row_dict["matched_keywords"].split('||') if row_dict["matched_keywords"] else []
                    
                    # Ensure all keywords are properly trimmed
                    keywords_list = [keyword.strip() for keyword in keywords_list]
                    
                    alerts.append({
                        "id": row_dict["id"],
                        "is_read": bool(row_dict["is_read"]),
                        "article": {
                            "url": row_dict["uri"],
                            "title": row_dict["title"],
                            "summary": row_dict["summary"],
                            "source": row_dict["news_source"],
                            "publication_date": row_dict["publication_date"]
                        },
                        "matched_keyword": keywords_list[0] if keywords_list else "",
                        "matched_keywords": keywords_list,
                        "detected_at": row_dict["detected_at"]
                    })
            else:
                # Get total count for this specific group using the old table
                cursor.execute("""
                    SELECT COUNT(DISTINCT ka.id) as total
                    FROM keyword_alerts ka
                    JOIN monitored_keywords mk ON ka.keyword_id = mk.id
                    JOIN keyword_groups kg ON mk.group_id = kg.id
                    WHERE kg.topic = ? AND kg.id = ?
                """, (topic, group_id))
                total_count = cursor.fetchone()['total']
                
                # Get unread count for this specific group using the old table
                cursor.execute("""
                    SELECT COUNT(DISTINCT ka.id) as unread_count
                    FROM keyword_alerts ka
                    JOIN monitored_keywords mk ON ka.keyword_id = mk.id
                    JOIN keyword_groups kg ON mk.group_id = kg.id
                    WHERE kg.topic = ? AND kg.id = ? AND ka.is_read = 0
                """, (topic, group_id))
                unread_count = cursor.fetchone()['unread_count']
                
                # Get filtered alerts for this group using the old table
                read_condition = "" if show_read else "AND ka.is_read = 0"
                cursor.execute(f"""
                    SELECT 
                        ka.id,
                        ka.is_read,
                        ka.detected_at,
                        a.uri,
                        a.title,
                        a.summary,
                        a.news_source,
                        a.publication_date,
                        mk.keyword as matched_keyword
                    FROM keyword_alerts ka
                    JOIN articles a ON ka.article_uri = a.uri
                    JOIN monitored_keywords mk ON ka.keyword_id = mk.id
                    JOIN keyword_groups kg ON mk.group_id = kg.id
                    WHERE kg.topic = ? AND kg.id = ? {read_condition}
                    ORDER BY ka.detected_at DESC
                """, (topic, group_id))
                
                alerts = []
                for row in cursor.fetchall():
                    row_dict = dict(row)
                    alerts.append({
                        "id": row_dict["id"],
                        "is_read": bool(row_dict["is_read"]),
                        "article": {
                            "url": row_dict["uri"],
                            "title": row_dict["title"],
                            "summary": row_dict["summary"],
                            "source": row_dict["news_source"],
                            "publication_date": row_dict["publication_date"]
                        },
                        "matched_keyword": row_dict["matched_keyword"],
                        "matched_keywords": [row_dict["matched_keyword"].strip()] if row_dict["matched_keyword"] else [],
                        "detected_at": row_dict["detected_at"]
                    })
            
            return {
                "topic": topic,
                "alerts": alerts,
                "total_count": total_count,
                "unread_count": unread_count
            }
            
    except Exception as e:
        logger.error(f"Error in get_group_alerts: {str(e)}")
        logger.error("Full traceback:", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/articles/by-topic/{topic_name}")
async def delete_articles_by_topic(topic_name: str, db=Depends(get_database_instance)):
    """Delete all articles associated with a specific topic"""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if articles table has a topic column
            cursor.execute("PRAGMA table_info(articles)")
            columns = cursor.fetchall()
            has_topic_column = any(col[1] == 'topic' for col in columns)
            
            if has_topic_column:
                # Delete articles directly associated with this topic
                cursor.execute("DELETE FROM articles WHERE topic = ?", (topic_name,))
                deleted_count = cursor.rowcount
            else:
                # We'll need to find articles from news_search_results or paper_search_results
                cursor.execute("""
                    DELETE FROM articles 
                    WHERE uri IN (
                        SELECT article_uri FROM news_search_results 
                        WHERE topic = ?
                    )
                """, (topic_name,))
                news_deleted = cursor.rowcount
                
                cursor.execute("""
                    DELETE FROM articles 
                    WHERE uri IN (
                        SELECT article_uri FROM paper_search_results 
                        WHERE topic = ?
                    )
                """, (topic_name,))
                papers_deleted = cursor.rowcount
                
                deleted_count = news_deleted + papers_deleted
            
            conn.commit()
            return {"success": True, "articles_deleted": deleted_count}
    except Exception as e:
        logging.error(f"Error deleting articles for topic {topic_name}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 