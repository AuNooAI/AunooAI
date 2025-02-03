from fastapi import Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from app.database import Database
from app.utils.session import verify_session
from app.logger import logger
from app.templates import templates

router = APIRouter()

@router.get("/keyword-alerts", response_class=HTMLResponse)
async def keyword_alerts_page(request: Request, session=Depends(verify_session)):
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get monitor settings
            cursor.execute("SELECT is_enabled FROM keyword_monitor_settings WHERE id = 1")
            settings = cursor.fetchone()
            monitor_enabled = bool(settings[0]) if settings else False
            
            # Get last check time
            cursor.execute("SELECT MAX(check_time) FROM keyword_monitor_checks")
            last_check = cursor.fetchone()[0]
            last_check_time = last_check if last_check else None
            
            # Get alerts with article details
            cursor.execute("""
                SELECT 
                    ka.id,
                    ka.group_id,
                    ka.detected_at,
                    ka.matched_keyword,
                    a.uri,
                    a.title,
                    a.url,
                    a.source,
                    a.publication_date,
                    a.summary
                FROM keyword_alerts ka
                JOIN articles a ON ka.article_uri = a.uri
                WHERE ka.read = 0
                ORDER BY ka.detected_at DESC
            """)
            
            alerts_data = cursor.fetchall()
            alerts = []
            for row in alerts_data:
                alerts.append({
                    'id': row[0],
                    'group_id': row[1],
                    'detected_at': row[2],
                    'matched_keyword': row[3],
                    'article': {
                        'uri': row[4],
                        'title': row[5],
                        'url': row[6],
                        'source': row[7],
                        'publication_date': row[8],
                        'summary': row[9]
                    }
                })
            
            return templates.TemplateResponse(
                "keyword_alerts.html",
                {
                    "request": request,
                    "session": session,
                    "alerts": alerts,
                    "last_check_time": last_check_time,
                    "settings": {"is_enabled": monitor_enabled}
                }
            )
            
    except Exception as e:
        logger.error(f"Error loading keyword alerts page: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 