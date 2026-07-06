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

        # CRITICAL: Check if user account is active (Added 2025-10-21)
        if not user.get('is_active', True):
            logger.warning(f"Login attempt for inactive user: {username}")
            return templates.TemplateResponse(
                "login.html",
                {
                    "request": request,
                    "session": request.session,
                    "error": "This account has been deactivated. Please contact an administrator."
                },
                status_code=status.HTTP_401_UNAUTHORIZED
            )

        request.session["user"] = username
        
        # Check if password change is required
        from app.core.modules import is_dedicated_bw
        if user.get('force_password_change'):
            return RedirectResponse(url="/change_password", status_code=status.HTTP_302_FOUND)
        elif not user.get('completed_onboarding') and not is_dedicated_bw():
            # Dedicated Brand Watcher tenants skip the topic wizard — brands are
            # configured in the Brand Watcher tab, not via general topic onboarding.
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

# ─── Password reset via signed link (admin-initiated, no session required) ───
# The token binds username + expiry + a prefix of the CURRENT password hash,
# so a link stops working the moment the password changes (single-use in
# practice) and expires after 24h regardless.

import hashlib as _hashlib
import hmac as _hmac
import os as _os
import time as _time
from urllib.parse import quote as _quote

_PW_RESET_TTL_SECONDS = 24 * 3600


def _pw_reset_secret() -> bytes:
    return (_os.environ.get("FLASK_SECRET_KEY") or "aunoo-pw-reset").encode()


def _pw_reset_token(username: str, exp: int, password_hash: str) -> str:
    msg = f"pw-reset:{username.lower()}:{exp}:{(password_hash or '')[:20]}"
    return _hmac.new(_pw_reset_secret(), msg.encode(), _hashlib.sha256).hexdigest()


def build_password_reset_link(username: str, db) -> str:
    """Signed reset URL for a user (called by the admin reset endpoint)."""
    user = db.facade.get_user_by_username(username)
    if not user:
        raise ValueError("User not found")
    exp = int(_time.time()) + _PW_RESET_TTL_SECONDS
    token = _pw_reset_token(username, exp, user.get("password_hash") or "")
    domain = _os.getenv("DOMAIN", "localhost:10015")
    protocol = "https" if "localhost" not in domain else "http"
    return (f"{protocol}://{domain}/reset-password"
            f"?u={_quote(username)}&exp={exp}&token={token}")


def _pw_reset_check(db, username: str, exp: int, token: str) -> bool:
    if _time.time() > exp:
        return False
    user = db.facade.get_user_by_username(username)
    if not user or not user.get("password_hash"):
        return False
    expected = _pw_reset_token(username, exp, user.get("password_hash") or "")
    return _hmac.compare_digest(token, expected)


@router.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page(request: Request, u: str = "", exp: int = 0, token: str = ""):
    db = get_database_instance()
    valid = bool(u and token) and _pw_reset_check(db, u, exp, token)
    return templates.TemplateResponse("reset_password.html", {
        "request": request, "token_valid": valid,
        "username": u, "exp": exp, "token": token,
    })


@router.post("/reset-password", response_class=HTMLResponse)
async def reset_password_submit(
    request: Request,
    u: str = Form(...),
    exp: int = Form(...),
    token: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
):
    db = get_database_instance()
    if not _pw_reset_check(db, u, exp, token):
        return templates.TemplateResponse("reset_password.html", {
            "request": request, "token_valid": False,
            "username": u, "exp": exp, "token": token,
        })
    ctx = {"request": request, "token_valid": True,
           "username": u, "exp": exp, "token": token}
    if new_password != confirm_password:
        return templates.TemplateResponse("reset_password.html",
                                          {**ctx, "error": "Passwords do not match"})
    if len(new_password) < 8:
        return templates.TemplateResponse("reset_password.html",
                                          {**ctx, "error": "Password must be at least 8 characters"})
    db.update_user_password(u, new_password)
    logger.info(f"Password reset completed via signed link for user: {u}")
    return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
