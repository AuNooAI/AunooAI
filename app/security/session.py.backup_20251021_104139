from fastapi import Request, HTTPException, status
from app.security.oauth_users import get_oauth_user_by_session
import logging

logger = logging.getLogger(__name__)

def verify_session(request: Request):
    """Verify session for both traditional and OAuth users"""
    session_data = request.session
    
    # Check for traditional session user
    if session_data.get("user"):
        return session_data
    
    # Check for OAuth user
    oauth_user = get_oauth_user_by_session(session_data)
    if oauth_user and oauth_user.get('is_oauth'):
        return session_data
    
    # No valid session found
    logger.debug("No valid session found, redirecting to login")
    raise HTTPException(
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
        headers={"Location": "/login"}
    )

def verify_session_api(request: Request):
    """Verify session for API endpoints - returns 401 instead of redirect"""
    session_data = request.session
    
    # Check for traditional session user
    if session_data.get("user"):
        return session_data
    
    # Check for OAuth user
    oauth_user = get_oauth_user_by_session(session_data)
    if oauth_user and oauth_user.get('is_oauth'):
        return session_data
    
    # No valid session found - return 401 for API endpoints
    logger.debug("No valid session found for API request")
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required"
    )

def verify_session_optional(request: Request):
    """Verify session but return None if not authenticated (no redirect)"""
    try:
        return verify_session(request)
    except HTTPException:
        return None

def get_current_user_info(request: Request):
    """Get current user information from session (traditional or OAuth)"""
    session_data = request.session
    
    # Check for OAuth user first
    oauth_user = get_oauth_user_by_session(session_data)
    if oauth_user:
        return oauth_user
    
    # Check for traditional user
    if session_data.get("user"):
        return {
            'username': session_data['user'],
            'is_oauth': False
        }
    
    return None

def is_oauth_user(request: Request) -> bool:
    """Check if current user is logged in via OAuth"""
    session_data = request.session
    return bool(session_data.get('provider') and session_data.get('oauth_user'))

def get_user_display_name(request: Request) -> str:
    """Get display name for current user"""
    user_info = get_current_user_info(request)
    
    if not user_info:
        return "Anonymous"
    
    if user_info.get('is_oauth'):
        return user_info.get('name') or user_info.get('email', 'OAuth User')
    else:
        return user_info.get('username', 'User') 