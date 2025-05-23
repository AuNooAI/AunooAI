from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from app.security.session import verify_session
from app.security.oauth_users import OAuthUserManager
from app.database import get_database_instance, Database
from pydantic import BaseModel, EmailStr
from typing import List, Optional
import logging

router = APIRouter(prefix="/admin/oauth", tags=["OAuth Admin"])
logger = logging.getLogger(__name__)

class AllowlistAddRequest(BaseModel):
    email: EmailStr
    added_by: Optional[str] = None

class AllowlistResponse(BaseModel):
    email: str
    added_by: Optional[str]
    added_at: str
    is_active: bool

@router.get("/allowlist", response_model=List[AllowlistResponse])
async def get_allowlist(
    session=Depends(verify_session),
    db: Database = Depends(get_database_instance)
):
    """Get OAuth allowlist entries"""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT email, added_by, added_at, is_active 
                FROM oauth_allowlist 
                ORDER BY added_at DESC
            """)
            
            entries = []
            for row in cursor.fetchall():
                entries.append(AllowlistResponse(
                    email=row[0],
                    added_by=row[1],
                    added_at=row[2],
                    is_active=bool(row[3])
                ))
            
            return entries
            
    except Exception as e:
        logger.error(f"Failed to get allowlist: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve allowlist")

@router.post("/allowlist/add")
async def add_to_allowlist(
    request: AllowlistAddRequest,
    session=Depends(verify_session),
    db: Database = Depends(get_database_instance)
):
    """Add email to OAuth allowlist"""
    try:
        oauth_manager = OAuthUserManager(db)
        success = oauth_manager.add_to_allowlist(
            email=request.email,
            added_by=request.added_by or session.get('user', 'admin')
        )
        
        if success:
            return {"status": "success", "message": f"Added {request.email} to allowlist"}
        else:
            raise HTTPException(status_code=400, detail="Failed to add email to allowlist")
            
    except Exception as e:
        logger.error(f"Failed to add to allowlist: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/allowlist/{email}")
async def remove_from_allowlist(
    email: str,
    session=Depends(verify_session),
    db: Database = Depends(get_database_instance)
):
    """Remove email from OAuth allowlist"""
    try:
        oauth_manager = OAuthUserManager(db)
        success = oauth_manager.remove_from_allowlist(email)
        
        if success:
            return {"status": "success", "message": f"Removed {email} from allowlist"}
        else:
            raise HTTPException(status_code=404, detail="Email not found in allowlist")
            
    except Exception as e:
        logger.error(f"Failed to remove from allowlist: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/users")
async def get_oauth_users(
    session=Depends(verify_session),
    db: Database = Depends(get_database_instance)
):
    """Get all OAuth users"""
    try:
        oauth_manager = OAuthUserManager(db)
        users = oauth_manager.list_oauth_users()
        
        return {
            "users": users,
            "count": len(users)
        }
        
    except Exception as e:
        logger.error(f"Failed to get OAuth users: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve OAuth users")

@router.get("/status")
async def get_oauth_admin_status(
    session=Depends(verify_session),
    db: Database = Depends(get_database_instance)
):
    """Get OAuth system status and configuration"""
    try:
        from app.security.oauth_users import ALLOWED_EMAIL_DOMAINS
        
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Count allowlist entries
            cursor.execute("SELECT COUNT(*) FROM oauth_allowlist WHERE is_active = 1")
            allowlist_count = cursor.fetchone()[0]
            
            # Count OAuth users
            cursor.execute("SELECT COUNT(*) FROM oauth_users WHERE is_active = 1")
            oauth_users_count = cursor.fetchone()[0]
            
            # Get recent logins
            cursor.execute("""
                SELECT provider, COUNT(*) as count 
                FROM oauth_users 
                WHERE is_active = 1 
                GROUP BY provider
            """)
            provider_stats = {row[0]: row[1] for row in cursor.fetchall()}
        
        return {
            "allowlist_enabled": allowlist_count > 0,
            "allowlist_count": allowlist_count,
            "domain_restrictions": ALLOWED_EMAIL_DOMAINS if ALLOWED_EMAIL_DOMAINS and ALLOWED_EMAIL_DOMAINS[0] else None,
            "oauth_users_count": oauth_users_count,
            "provider_stats": provider_stats,
            "security_level": "HIGH" if allowlist_count > 0 or (ALLOWED_EMAIL_DOMAINS and ALLOWED_EMAIL_DOMAINS[0]) else "OPEN"
        }
        
    except Exception as e:
        logger.error(f"Failed to get OAuth admin status: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve status") 