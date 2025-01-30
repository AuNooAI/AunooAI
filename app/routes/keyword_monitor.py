from fastapi import APIRouter, HTTPException, Depends
from typing import List
from pydantic import BaseModel
from datetime import datetime
from app.database import get_database_instance
from app.tasks.keyword_monitor import KeywordMonitor
import logging

router = APIRouter(prefix="/api/keyword-monitor")

class KeywordGroup(BaseModel):
    name: str
    topic: str

class Keyword(BaseModel):
    group_id: int
    keyword: str

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

@router.post("/alerts/{alert_id}/read")
async def mark_alert_read(alert_id: int, db=Depends(get_database_instance)):
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE keyword_alerts SET is_read = 1 WHERE id = ?",
                (alert_id,)
            )
            conn.commit()
            return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/check-now")
async def check_keywords_now(db=Depends(get_database_instance)):
    """Manually trigger a keyword check"""
    try:
        monitor = KeywordMonitor(db)
        await monitor.check_keywords()
        return {"success": True, "message": "Keyword check completed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/alerts")
async def get_alerts(db=Depends(get_database_instance)):
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get all unread alerts with article and keyword info
            cursor.execute("""
                SELECT 
                    ka.id as alert_id,
                    ka.detected_at,
                    mk.keyword,
                    kg.id as group_id,
                    kg.name as group_name,
                    kg.topic,
                    a.uri,
                    a.title,
                    a.news_source,
                    a.publication_date,
                    a.summary
                FROM keyword_alerts ka
                JOIN monitored_keywords mk ON ka.keyword_id = mk.id
                JOIN keyword_groups kg ON mk.group_id = kg.id
                JOIN articles a ON ka.article_uri = a.uri
                WHERE ka.is_read = 0
                ORDER BY ka.detected_at DESC
            """)
            
            alerts = cursor.fetchall()
            
            # Group alerts by keyword group
            groups = {}
            for alert in alerts:
                group_id = alert[3]  # group_id from the query
                if group_id not in groups:
                    groups[group_id] = {
                        'id': group_id,
                        'name': alert[4],  # group_name
                        'topic': alert[5],  # topic
                        'alerts': []
                    }
                
                groups[group_id]['alerts'].append({
                    'id': alert[0],  # alert_id
                    'detected_at': alert[1],
                    'keyword': alert[2],
                    'article': {
                        'url': alert[6],  # uri
                        'title': alert[7],
                        'source': alert[8],
                        'publication_date': alert[9],
                        'summary': alert[10]
                    }
                })
            
            return {"groups": list(groups.values())}
            
    except Exception as e:
        logger.error(f"Error fetching keyword alerts: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 