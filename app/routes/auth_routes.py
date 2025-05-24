"""Authentication routes for login, logout, and password management."""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Request, Form, HTTPException, status, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.database import Database, get_database_instance
from app.security.auth import verify_password, get_password_hash
from app.security.session import verify_session

logger = logging.getLogger(__name__)

router = APIRouter()

# This will be set by the main app
templates: Optional[Jinja2Templates] = None

def set_templates(template_instance: Jinja2Templates):
    """Set the templates instance for this router."""
    global templates
    templates = template_instance


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Display the login page."""
    if request.session.get("user"):
        return RedirectResponse(url="/")
    return templates.TemplateResponse(
        "login.html",
        {"request": request}
    )


@router.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Database = Depends(get_database_instance)
):
    """Handle user login."""
    try:
        # Check for admin/admin credentials
        if username == "admin" and password == "admin":
            # Get or create admin user
            user = db.get_user(username)
            if not user:
                # Create admin user with force_password_change flag
                hashed_password = get_password_hash(password)
                db.create_user(username, hashed_password, force_password_change=True)
                user = db.get_user(username)
            elif not user.get('force_password_change'):
                # If admin/admin is used but force_password_change is False, force it again
                db.set_force_password_change(username, True)
                user = db.get_user(username)
        else:
            # Get user from database for non-admin login
            user = db.get_user(username)
            
        logger.debug(f"Login attempt for user: {username}")
        logger.debug(f"User found in database: {user is not None}")
        
        if not user:
            logger.warning(f"User not found: {username}")
            return templates.TemplateResponse(
                "login.html",
                {
                    "request": request,
                    "session": request.session,
                    "error": "Invalid credentials"
                },
                status_code=status.HTTP_401_UNAUTHORIZED
            )

        is_valid = verify_password(password, user['password'])
        logger.debug(f"Password verification result: {is_valid}")

        if not is_valid:
            logger.warning(f"Invalid password for user: {username}")
            return templates.TemplateResponse(
                "login.html",
                {
                    "request": request,
                    "session": request.session,
                    "error": "Invalid credentials"
                },
                status_code=status.HTTP_401_UNAUTHORIZED
            )

        request.session["user"] = username
        
        # Check if password change is required
        if user.get('force_password_change'):
            return RedirectResponse(url="/change_password", status_code=status.HTTP_302_FOUND)
        elif not user.get('completed_onboarding'):
            return RedirectResponse(url="/onboarding", status_code=status.HTTP_302_FOUND)
            
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
        
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid username or password"}
        )


@router.get("/logout")
async def logout(request: Request):
    """Handle user logout."""
    request.session.clear()
    return RedirectResponse(url="/login")