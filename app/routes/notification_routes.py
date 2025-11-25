"""
Notification routes for the Aunoo application.
Provides API endpoints for managing user notifications.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.database import get_database_instance
from app.security.session import verify_session
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

class NotificationCreate(BaseModel):
    username: Optional[str] = None
    type: str
    title: str
    message: str
    link: Optional[str] = None

class NotificationMarkRead(BaseModel):
    notification_ids: list[int]

@router.get("/api/notifications")
async def get_notifications(
    unread_only: bool = False,
    limit: int = 50,
    session=Depends(verify_session)
):
    """Get notifications for the current user."""
    try:
        db = get_database_instance()
        username = session.get("user", {}).get("username")

        if not username:
            raise HTTPException(status_code=401, detail="User not authenticated")

        notifications = db.facade.get_user_notifications(
            username=username,
            unread_only=unread_only,
            limit=limit
        )

        return {
            "notifications": notifications,
            "count": len(notifications)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/notifications/unread-count")
async def get_unread_count(session=Depends(verify_session)):
    """Get count of unread notifications for the current user."""
    try:
        db = get_database_instance()
        username = session.get("user", {}).get("username")

        if not username:
            raise HTTPException(status_code=401, detail="User not authenticated")

        count = db.facade.get_unread_count(username=username)

        return {"count": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/notifications/{notification_id}/mark-read")
async def mark_notification_read(
    notification_id: int,
    session=Depends(verify_session)
):
    """Mark a single notification as read."""
    try:
        db = get_database_instance()
        username = session.get("user", {}).get("username")

        if not username:
            raise HTTPException(status_code=401, detail="User not authenticated")

        success = db.facade.mark_notification_as_read(
            notification_id=notification_id,
            username=username
        )

        return {"success": success}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/notifications/mark-all-read")
async def mark_all_notifications_read(session=Depends(verify_session)):
    """Mark all notifications as read for the current user."""
    try:
        db = get_database_instance()
        username = session.get("user", {}).get("username")

        if not username:
            raise HTTPException(status_code=401, detail="User not authenticated")

        count = db.facade.mark_all_notifications_as_read(username=username)

        return {"count": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/api/notifications/read")
async def delete_read_notifications(session=Depends(verify_session)):
    """Delete all read notifications for the current user."""
    try:
        db = get_database_instance()
        username = session.get("user", {}).get("username")

        if not username:
            raise HTTPException(status_code=401, detail="User not authenticated")

        count = db.facade.delete_read_notifications(username=username)

        return {"count": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/api/notifications/{notification_id}")
async def delete_notification(
    notification_id: int,
    session=Depends(verify_session)
):
    """Delete a single notification."""
    try:
        db = get_database_instance()
        username = session.get("user", {}).get("username")

        if not username:
            raise HTTPException(status_code=401, detail="User not authenticated")

        success = db.facade.delete_notification(
            notification_id=notification_id,
            username=username
        )

        return {"success": success}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/notifications/create")
async def create_notification(
    notification: NotificationCreate,
    session=Depends(verify_session)
):
    """Create a new notification. Users can create notifications for themselves, admins can create for any user."""
    try:
        db = get_database_instance()

        # Get current user from session
        current_username = session.get("user", {}).get("username")
        logger.info(f"[Notification Create] Current user from session: {current_username}")
        logger.info(f"[Notification Create] Requested username: {notification.username}")
        logger.info(f"[Notification Create] Notification type: {notification.type}")

        # If username is not specified in the request, use current user
        # If username IS specified, only allow if admin or if it's the current user
        target_username = notification.username or current_username

        if not target_username:
            logger.error("[Notification Create] No username available (neither in request nor session)")
            raise HTTPException(status_code=400, detail="Username is required but not found in session")

        # For non-admin users, ensure they can only create notifications for themselves
        is_admin = session.get("user", {}).get("is_admin", False)
        if not is_admin and target_username != current_username:
            raise HTTPException(status_code=403, detail="Cannot create notifications for other users")

        logger.info(f"[Notification Create] Creating notification for user: {target_username}")
        notification_id = db.facade.create_notification(
            username=target_username,
            type=notification.type,
            title=notification.title,
            message=notification.message,
            link=notification.link
        )

        logger.info(f"[Notification Create] Successfully created notification ID: {notification_id}")
        return {"notification_id": notification_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Notification Create] Error creating notification: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
