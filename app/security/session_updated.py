"""
Updated session.py with is_active validation for multi-user support.

CRITICAL SECURITY UPDATES:
1. Checks is_active flag on every session validation
2. Supports both traditional and OAuth users
3. Clears session for deactivated users
4. Validates user exists in database

USAGE:
Replace app/security/session.py with this file after migration.
"""

from fastapi import Request, HTTPException, status
from app.security.oauth_users import get_oauth_user_by_session
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def verify_session(request: Request):
    """
    Verify session for both traditional and OAuth users.

    CRITICAL SECURITY: Checks is_active flag to prevent deactivated users
    from maintaining active sessions.

    Raises:
        HTTPException: 307 redirect to login if session invalid or user inactive
    """
    session_data = request.session

    # Check for traditional session user
    if session_data.get("user"):
        username = session_data["user"]

        # CRITICAL: Verify user still exists and is active
        from app.database import get_database_instance
        db = get_database_instance()
        user = db.facade.get_user_by_username(username)

        if not user:
            logger.warning(f"Session for non-existent user: {username}")
            request.session.clear()
            raise HTTPException(
                status_code=status.HTTP_307_TEMPORARY_REDIRECT,
                headers={"Location": "/login?error=invalid_session"}
            )

        if not user.get('is_active', True):
            logger.warning(f"Session for inactive user: {username}")
            request.session.clear()
            raise HTTPException(
                status_code=status.HTTP_307_TEMPORARY_REDIRECT,
                headers={"Location": "/login?error=account_inactive"}
            )

        return session_data

    # Check for OAuth user
    oauth_user = get_oauth_user_by_session(session_data)
    if oauth_user and oauth_user.get('is_oauth'):
        # CRITICAL: Check if OAuth user entry in users table is active
        from app.database import get_database_instance
        db = get_database_instance()

        # OAuth users are stored by email as username
        user = db.facade.get_user_by_email(oauth_user.get('email'))

        if not user or not user.get('is_active', True):
            logger.warning(f"OAuth session for inactive user: {oauth_user.get('email')}")
            request.session.clear()
            raise HTTPException(
                status_code=status.HTTP_307_TEMPORARY_REDIRECT,
                headers={"Location": "/login?error=account_inactive"}
            )

        return session_data

    # No valid session found
    logger.debug("No valid session found, redirecting to login")
    raise HTTPException(
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
        headers={"Location": "/login"}
    )


def verify_session_api(request: Request):
    """
    Verify session for API endpoints - returns 401 instead of redirect.

    CRITICAL SECURITY: Checks is_active flag for both traditional and OAuth users.

    Raises:
        HTTPException: 401 if session invalid or user inactive
    """
    session_data = request.session

    # Check for traditional session user
    if session_data.get("user"):
        username = session_data["user"]

        # CRITICAL: Verify user is active
        from app.database import get_database_instance
        db = get_database_instance()
        user = db.facade.get_user_by_username(username)

        if not user or not user.get('is_active', True):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Account inactive or not found"
            )

        return session_data

    # Check for OAuth user
    oauth_user = get_oauth_user_by_session(session_data)
    if oauth_user and oauth_user.get('is_oauth'):
        # Check if OAuth user is active
        from app.database import get_database_instance
        db = get_database_instance()
        user = db.facade.get_user_by_email(oauth_user.get('email'))

        if not user or not user.get('is_active', True):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Account inactive"
            )

        return session_data

    # No valid session found - return 401 for API endpoints
    logger.debug("No valid session found for API request")
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required"
    )


def verify_session_optional(request: Request):
    """
    Verify session but return None if not authenticated (no redirect).

    Returns:
        dict or None: Session data if valid, None if not authenticated
    """
    try:
        return verify_session(request)
    except HTTPException:
        return None


def require_admin(request: Request):
    """
    Dependency to require admin role.

    Raises:
        HTTPException: 403 if user is not admin

    Returns:
        dict: Session data if user is admin
    """
    session = verify_session(request)
    username = session.get("user")

    if not username:
        # OAuth user - get email
        oauth_user = get_oauth_user_by_session(session)
        if oauth_user:
            username = oauth_user.get('email')

    if not username:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Authentication required"
        )

    # Check if user is admin
    from app.database import get_database_instance
    db = get_database_instance()

    if not db.facade.check_user_is_admin(username):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )

    return session


def get_current_username(request: Request) -> Optional[str]:
    """
    Get current logged-in username (or email for OAuth users).

    Returns:
        str or None: Username/email if authenticated, None otherwise
    """
    try:
        session = verify_session(request)

        # Traditional user
        if session.get("user"):
            return session.get("user")

        # OAuth user
        oauth_user = get_oauth_user_by_session(session)
        if oauth_user:
            return oauth_user.get('email')

        return None
    except:
        return None


def get_current_user_info(request: Request):
    """
    Get current user information from session (traditional or OAuth).

    Returns:
        dict or None: User info with role, email, is_active, is_oauth flags
    """
    session_data = request.session

    # Check for OAuth user first
    oauth_user = get_oauth_user_by_session(session_data)
    if oauth_user:
        # Get role from users table
        from app.database import get_database_instance
        db = get_database_instance()
        user = db.facade.get_user_by_email(oauth_user.get('email'))

        return {
            'username': oauth_user.get('email'),
            'email': oauth_user.get('email'),
            'name': oauth_user.get('name'),
            'role': user.get('role', 'user') if user else 'user',
            'is_active': user.get('is_active', True) if user else True,
            'is_oauth': True
        }

    # Check for traditional user
    if session_data.get("user"):
        username = session_data['user']
        from app.database import get_database_instance
        db = get_database_instance()
        user = db.facade.get_user_by_username(username)

        if user:
            return {
                'username': user['username'],
                'email': user.get('email'),
                'role': user.get('role', 'user'),
                'is_active': user.get('is_active', True),
                'is_oauth': False
            }

    return None


def is_oauth_user(request: Request) -> bool:
    """
    Check if current user is logged in via OAuth.

    Returns:
        bool: True if OAuth user, False otherwise
    """
    session_data = request.session
    return bool(session_data.get('provider') and session_data.get('oauth_user'))


def get_user_display_name(request: Request) -> str:
    """
    Get display name for current user.

    Returns:
        str: Display name (name for OAuth, username for traditional)
    """
    user_info = get_current_user_info(request)

    if not user_info:
        return "Anonymous"

    if user_info.get('is_oauth'):
        return user_info.get('name') or user_info.get('email', 'OAuth User')
    else:
        return user_info.get('username', 'User')
